//! Bounded, privacy-safe history of actual completed PDF renders/searches.
use serde::{Deserialize, Serialize};
use std::path::Path;
use uuid::Uuid;

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Activity {
    pub jobs: Vec<Outcome>,
    pub notifications: Vec<Outcome>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Outcome {
    pub id: String,
    pub succeeded: bool,
    pub kind: String,
}

impl Activity {
    pub fn load(path: &Path) -> Result<Self, String> {
        let bytes = match std::fs::read(path) {
            Ok(bytes) => bytes,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Self::default()),
            Err(e) => return Err(format!("Activity read failed: {e}")),
        };
        if bytes.len() > 32_768 {
            return Err("Activity file too large".into());
        }
        let state: Self = serde_json::from_slice(&bytes).map_err(|_| "Invalid activity history")?;
        if state.jobs.len() > 30
            || state.notifications.len() > 30
            || state
                .jobs
                .iter()
                .chain(state.notifications.iter())
                .any(|o| {
                    !["PDF render", "PDF search"].contains(&o.kind.as_str())
                        || Uuid::parse_str(&o.id).is_err()
                })
        {
            return Err("Invalid activity entries".into());
        }
        Ok(state)
    }

    pub fn record(&mut self, kind: &str, succeeded: bool) {
        let item = Outcome {
            id: Uuid::new_v4().to_string(),
            kind: kind.into(),
            succeeded,
        };
        self.jobs.push(item.clone());
        self.notifications.push(item);
        for records in [&mut self.jobs, &mut self.notifications] {
            if records.len() > 30 {
                records.drain(..records.len() - 30);
            }
        }
    }

    pub fn save(&self, path: &Path) -> Result<(), String> {
        let parent = path.parent().ok_or("Invalid activity path")?;
        std::fs::create_dir_all(parent).map_err(|e| format!("Activity directory error: {e}"))?;
        let tmp = parent.join(format!(".activity-{}.tmp", Uuid::new_v4()));
        std::fs::write(
            &tmp,
            serde_json::to_vec(self).map_err(|_| "Serialize activity failed")?,
        )
        .map_err(|e| format!("Activity write failed: {e}"))?;
        if let Err(error) = crate::writing_autosave::replace_file(&tmp, path) {
            let _ = std::fs::remove_file(&tmp);
            return Err(format!("Activity replace failed: {error}"));
        }
        Ok(())
    }

    pub fn jobs_text(&self) -> String {
        Self::summary(&self.jobs, "No completed PDF operations")
    }
    pub fn notifications_text(&self) -> String {
        Self::summary(&self.notifications, "No notifications")
    }
    fn summary(entries: &[Outcome], empty: &str) -> String {
        if entries.is_empty() {
            return empty.into();
        }
        entries
            .iter()
            .rev()
            .map(|e| {
                format!(
                    "{}: {}",
                    e.kind,
                    if e.succeeded { "completed" } else { "failed" }
                )
            })
            .collect::<Vec<_>>()
            .join("\n")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn restart_bounds_privacy_and_dismiss() {
        let path = std::env::temp_dir().join(format!("rw-activity-{}.json", Uuid::new_v4()));
        let mut activity = Activity::default();
        for _ in 0..40 {
            activity.record("PDF search", false);
        }
        activity.save(&path).unwrap();
        let mut reopened = Activity::load(&path).unwrap();
        assert_eq!(reopened.jobs.len(), 30);
        assert_eq!(reopened.notifications.len(), 30);
        assert!(!reopened.jobs_text().contains("C:\\"));
        reopened.notifications.clear();
        reopened.save(&path).unwrap();
        assert_eq!(
            Activity::load(&path).unwrap().notifications_text(),
            "No notifications"
        );
        let before = Activity::load(&path).unwrap();
        let mut changed = before.clone();
        changed.record("PDF render", true);
        changed.save(&path).unwrap();
        assert_eq!(Activity::load(&path).unwrap(), changed);
        let invalid = path.with_extension("blocked-directory");
        std::fs::create_dir(&invalid).unwrap();
        assert!(changed.save(&invalid).is_err());
        assert!(Activity::load(&invalid).is_err());
        std::fs::remove_dir(&invalid).unwrap();
        std::fs::remove_file(path).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn locked_existing_activity_file_does_not_report_success_or_mutate_history() {
        use std::os::windows::fs::OpenOptionsExt;
        let path = std::env::temp_dir().join(format!("rw-activity-lock-{}.json", Uuid::new_v4()));
        let mut old = Activity::default();
        old.record("PDF render", true);
        old.save(&path).unwrap();
        // No file sharing flags: Windows ReplaceFileW must fail closed while
        // this handle exists; it must not delete the previously saved state.
        let lock = std::fs::OpenOptions::new()
            .read(true)
            .share_mode(0)
            .open(&path)
            .unwrap();
        let mut changed = old.clone();
        changed.record("PDF search", false);
        assert!(changed.save(&path).is_err());
        drop(lock);
        assert_eq!(Activity::load(&path).unwrap(), old);
        changed.save(&path).unwrap();
        assert_eq!(Activity::load(&path).unwrap(), changed);
        std::fs::remove_file(path).unwrap();
    }
}
