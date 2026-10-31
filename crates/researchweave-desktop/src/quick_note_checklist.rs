//! Checklist editing for versioned quick-note bodies.
//! We preserve the existing plaintext card schema and project CAS guards.

const MAX_BODY_CHARS: usize = 20_000;

pub(crate) fn prepare(body: &str) -> Result<String, String> {
    if body.contains('\0') || body.chars().count() > MAX_BODY_CHARS {
        return Err("Checklist text exceeds safe note bounds".into());
    }
    let items: Vec<String> = body
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(|line| {
            if line.starts_with("- [ ] ") || line.starts_with("- [x] ") {
                line.to_owned()
            } else {
                let content = line
                    .strip_prefix("- ")
                    .or_else(|| line.strip_prefix("* "))
                    .unwrap_or(line);
                format!("- [ ] {content}")
            }
        })
        .collect();
    if items.is_empty() {
        return Err("Write at least one checklist item first".into());
    }
    let result = items.join("\n");
    if result.chars().count() > MAX_BODY_CHARS {
        return Err("Checklist would exceed the note size limit".into());
    }
    Ok(result)
}

pub(crate) fn has_unchecked(body: &str) -> bool {
    body.lines().any(|line| {
        let trimmed = line.trim_start();
        trimmed.starts_with("- [ ] ")
    })
}

pub(crate) fn complete_next(body: &str) -> Result<String, String> {
    if body.contains('\0') || body.chars().count() > MAX_BODY_CHARS {
        return Err("Checklist text exceeds safe note bounds".into());
    }
    let mut result = body.to_owned();
    let mut offset = 0;
    for line in body.split_inclusive('\n') {
        if let Some(index) = line.find("- [ ] ") {
            if line[..index].chars().all(char::is_whitespace) {
                let checkbox = offset + index + 3;
                result.replace_range(checkbox..checkbox + 1, "x");
                return Ok(result);
            }
        }
        offset += line.len();
    }
    Err("No unchecked checklist item remains".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn converts_mixed_persian_and_english_lines_without_repeating_markers() {
        let body = "MRI review\n- مطالعه\n- [x] Finished\n\n* Edit methods";
        let result = prepare(body).unwrap();
        assert_eq!(
            result,
            "- [ ] MRI review\n- [ ] مطالعه\n- [x] Finished\n- [ ] Edit methods"
        );
        assert_eq!(prepare(&result).unwrap(), result);
        assert!(has_unchecked(&result));
    }

    #[test]
    fn completion_changes_only_first_open_item_without_touching_other_text() {
        let body = "- [x] Done\n  - [ ] فارسی\r\n- [ ] Analyze\nnot - [ ] a task";
        let changed = complete_next(body).unwrap();
        assert_eq!(
            changed,
            "- [x] Done\n  - [x] فارسی\r\n- [ ] Analyze\nnot - [ ] a task"
        );
        assert_eq!(
            complete_next(&changed).unwrap(),
            changed.replace("- [ ] Analyze", "- [x] Analyze")
        );
        assert!(!has_unchecked("Not a task - [ ] hidden in prose"));
        assert!(complete_next("- [x] Done").is_err());
    }

    #[test]
    fn empty_or_excessive_input_fails_without_modification() {
        assert!(prepare(" \n\n ").is_err());
        assert!(prepare(&"a".repeat(MAX_BODY_CHARS)).is_err());
        assert!(complete_next("- [ ] valid\0").is_err());
        assert!(complete_next(&"x".repeat(MAX_BODY_CHARS + 1)).is_err());
    }
}
