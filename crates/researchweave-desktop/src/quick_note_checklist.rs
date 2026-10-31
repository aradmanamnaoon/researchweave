//! Checklist editing for versioned quick-note bodies.
//! We preserve the existing plaintext card schema and project CAS guards.

const MAX_BODY_CHARS: usize = 20_000;

/// An immutable snapshot of one actual Markdown checklist line. Indices count
/// physical source lines from zero (including prose and empty lines), so UI
/// buttons can identify an item without searching for duplicate label text.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct ItemRow {
    pub line_index: usize,
    pub text: String,
    pub checked: bool,
}

fn check_bounds(body: &str) -> Result<(), String> {
    if body.contains('\0') || body.chars().count() > MAX_BODY_CHARS {
        return Err("Checklist text exceeds safe note bounds".into());
    }
    Ok(())
}

/// Returns the marker's checkbox byte offset, completion state, and exact
/// display text. Markdown list markers must begin at the physical line start,
/// after optional ASCII spaces/tabs; embedded prose is never an item.
fn checkbox_line(line: &str) -> Option<(usize, bool, &str)> {
    let content = line.trim_start_matches([' ', '\t']);
    let checkbox_offset = line.len() - content.len() + 3;
    let (checked, suffix) = if let Some(rest) = content.strip_prefix("- [ ]") {
        (false, rest)
    } else {
        (true, content.strip_prefix("- [x]")?)
    };
    let label = if suffix.is_empty() {
        ""
    } else if let Some(rest) = suffix.strip_prefix(' ') {
        rest
    } else {
        // "- [ ]word" is not a valid checkbox marker.
        suffix.strip_prefix('\t')?
    };
    // A control character in a list label could mislead accessible buttons.
    // Ordinary UTF-8 including Persian, emoji, and zero-width joiners remains.
    if label.chars().any(|c| c.is_control() && c != '\t') {
        return None;
    }
    Some((checkbox_offset, checked, label))
}

fn physical_line(segment: &str) -> &str {
    // Do not normalize the caller's newline convention: original byte offsets
    // are needed for a one-character edit on mixed CRLF/LF input.
    segment
        .strip_suffix("\r\n")
        .or_else(|| segment.strip_suffix('\n'))
        .unwrap_or(segment)
}

/// Parses checkbox lines while preserving original source line indices.
/// Non-checklist lines are skipped, never converted or reindexed.
pub(crate) fn parse_items(body: &str) -> Result<Vec<ItemRow>, String> {
    check_bounds(body)?;
    let mut result = Vec::new();
    for (line_index, segment) in body.split_inclusive('\n').enumerate() {
        if let Some((_, checked, label)) = checkbox_line(physical_line(segment)) {
            result.push(ItemRow {
                line_index,
                text: label.to_owned(),
                checked,
            });
        }
    }
    Ok(result)
}

/// Convenience UI adapter. Invalid or oversized drafts render no checklist
/// rows; toggling still returns a descriptive error through `toggle_at_line`.
pub(crate) fn rows(body: &str) -> Vec<ItemRow> {
    parse_items(body).unwrap_or_default()
}

/// Toggle exactly the requested zero-based physical source line, preserving
/// every other byte including blank lines, indentation and mixed line endings.
/// The UI should compare its draft snapshot/revision before calling this to
/// prevent a stale button index from addressing a newly inserted line.
pub(crate) fn toggle_at_line(body: &str, line_index: usize) -> Result<String, String> {
    check_bounds(body)?;
    let mut offset = 0usize;
    for (index, segment) in body.split_inclusive('\n').enumerate() {
        if index == line_index {
            let (relative_offset, checked, _) = checkbox_line(physical_line(segment))
                .ok_or("Selected line is not a Markdown checklist item")?;
            let checkbox_at = offset + relative_offset;
            let mut result = body.to_owned();
            result.replace_range(
                checkbox_at..checkbox_at + 1,
                if checked { " " } else { "x" },
            );
            return Ok(result);
        }
        offset += segment.len();
    }
    Err("Checklist line index is outside the current note".into())
}

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
    rows(body).iter().any(|item| !item.checked)
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

    #[test]
    fn row_indices_include_prose_blanks_and_crlf_with_unicode_and_duplicate_labels() {
        let body = concat!(
            "Meeting details\r\n",
            "- [ ] پژوهش 🧬\n",
            "\n",
            "  - [x] Анализ MRI\r\n",
            "- [ ] پژوهش 🧬\r\n",
            "not - [ ] a task\n",
            "\t- [ ] \tGreek μ and العربية"
        );
        assert_eq!(
            rows(body),
            vec![
                ItemRow {
                    line_index: 1,
                    text: "پژوهش 🧬".into(),
                    checked: false,
                },
                ItemRow {
                    line_index: 3,
                    text: "Анализ MRI".into(),
                    checked: true,
                },
                ItemRow {
                    line_index: 4,
                    text: "پژوهش 🧬".into(),
                    checked: false,
                },
                ItemRow {
                    line_index: 6,
                    text: "\tGreek μ and العربية".into(),
                    checked: false,
                },
            ]
        );
        let changed = toggle_at_line(body, 4).unwrap();
        // The first duplicate at line 1 remains untouched; line 4 changes.
        assert_eq!(
            changed,
            body.replace(
                "- [ ] پژوهش 🧬\r\nnot - [ ] a task",
                "- [x] پژوهش 🧬\r\nnot - [ ] a task"
            )
        );
        assert_eq!(rows(&changed)[2].line_index, 4);
        assert!(rows(&changed)[2].checked);
        assert!(!rows(&changed)[0].checked);
        assert_eq!(toggle_at_line(&changed, 4).unwrap(), body);
    }

    #[test]
    fn exact_line_only_and_invalid_markers_are_rejected_without_touching_other_text() {
        let body = concat!(
            "- [ ] first\n",
            "- [X] uppercase is not Markdown checked\r\n",
            "prose - [x] inline\n",
            "- [ ]missing separator\n",
            "- [x]done-no-separator\r\n",
            "* [ ] other list style\n",
            "   \n",
            "\u{00a0}- [ ] Unicode indent is not a source marker\n",
            "- [x] checked"
        );
        assert_eq!(
            rows(body).iter().map(|r| r.line_index).collect::<Vec<_>>(),
            vec![0, 8]
        );
        for invalid in 1..8 {
            assert!(
                toggle_at_line(body, invalid).is_err(),
                "unexpected toggle at line {invalid}"
            );
        }
        assert!(toggle_at_line(body, 9).is_err());
        assert!(toggle_at_line(body, usize::MAX).is_err());
        assert_eq!(
            toggle_at_line(body, 8).unwrap(),
            body.strip_suffix("- [x] checked").unwrap().to_owned() + "- [ ] checked"
        );
        assert!(toggle_at_line("", 0).is_err());
        assert!(rows("").is_empty());
    }

    #[test]
    fn accepts_empty_task_without_mutating_trailing_newline_conventions() {
        let body = "- [ ]\r\n- [x]\n- [ ] \r\n- [x] ";
        assert_eq!(
            rows(body)
                .iter()
                .map(|r| (r.line_index, r.checked, r.text.as_str()))
                .collect::<Vec<_>>(),
            vec![(0, false, ""), (1, true, ""), (2, false, ""), (3, true, "")]
        );
        let changed = toggle_at_line(body, 0).unwrap();
        assert_eq!(changed, "- [x]\r\n- [x]\n- [ ] \r\n- [x] ");
        assert_eq!(toggle_at_line(&changed, 0).unwrap(), body);
        assert_eq!(
            toggle_at_line(body, 3).unwrap(),
            "- [ ]\r\n- [x]\n- [ ] \r\n- [ ] "
        );
        assert!(!rows("  - [ ]\n").is_empty());
        assert_eq!(
            rows("- [ ]\n"),
            vec![ItemRow {
                line_index: 0,
                text: "".into(),
                checked: false
            }]
        );
    }

    #[test]
    fn checked_and_unchecked_toggles_are_exact_in_every_line_ending_case() {
        for terminator in ["\n", "\r\n", ""] {
            for initial in [' ', 'x'] {
                let prefix = format!("preface{terminator}not an item{terminator}");
                let body = format!("{prefix}\t- [{initial}] عِلْم 𝜇🧬{terminator}suffix");
                let changed = toggle_at_line(&body, if terminator.is_empty() { 0 } else { 2 });
                if terminator.is_empty() {
                    assert!(changed.is_err());
                } else {
                    let changed = changed.unwrap();
                    assert_eq!(
                        changed,
                        body.replacen(
                            &format!("- [{initial}]"),
                            &format!("- [{}]", if initial == ' ' { 'x' } else { ' ' }),
                            1
                        )
                    );
                    assert_eq!(toggle_at_line(&changed, 2).unwrap(), body);
                }
            }
        }
    }

    #[test]
    fn size_limits_and_nul_fail_closed_even_for_valid_checkboxes() {
        let boundary = format!("- [ ] {}", "界".repeat(MAX_BODY_CHARS - 6));
        assert_eq!(boundary.chars().count(), MAX_BODY_CHARS);
        assert_eq!(rows(&boundary).len(), 1);
        assert!(toggle_at_line(&boundary, 0).unwrap().starts_with("- [x] "));
        let excessive = boundary.clone() + "界";
        assert!(parse_items(&excessive).is_err());
        assert!(rows(&excessive).is_empty());
        assert!(toggle_at_line(&excessive, 0).is_err());
        assert!(parse_items("- [ ] valid\0").is_err());
        assert!(rows("- [ ] valid\0").is_empty());
        assert!(toggle_at_line("- [x] valid\0", 0).is_err());
        assert!(rows("- [ ] unsafe \u{1b}[31m").is_empty());
    }
}
