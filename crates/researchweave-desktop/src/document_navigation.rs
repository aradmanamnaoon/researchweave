//! UTF-8-safe document navigation for ResearchWeave's plain-text/Markdown
//! writing surface. Search and outline never alter the manuscript or its
//! scientific/citation provenance.

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Heading {
    pub title: String,
    pub level: usize,
    pub offset: usize,
}

/// Collect Markdown ATX headings while ignoring fenced code blocks.
/// UTF-8 byte offsets match Slint TextEdit::set-selection-offsets.
pub fn outline(body: &str, limit: usize) -> Vec<Heading> {
    let mut results = Vec::new();
    let mut fenced: Option<u8> = None;
    let mut offset = 0;
    for line in body.split_inclusive('\n') {
        let trimmed = line.trim_start();
        let marker = if trimmed.as_bytes().starts_with(&[96, 96, 96]) {
            Some(96)
        } else if trimmed.starts_with("~~~") {
            Some(b'~')
        } else {
            None
        };
        if let Some(marker) = marker {
            if fenced.is_none() {
                fenced = Some(marker);
            } else if fenced == Some(marker) {
                fenced = None;
            }
        } else if fenced.is_none() {
            let level = trimmed.bytes().take_while(|byte| *byte == b'#').count();
            if (1..=6).contains(&level) && trimmed.as_bytes().get(level) == Some(&b' ') {
                let title = trimmed[level..].trim().trim_end_matches('#').trim();
                if !title.is_empty() {
                    results.push(Heading {
                        title: title.chars().take(100).collect(),
                        level,
                        offset: offset + (line.len() - trimmed.len()),
                    });
                    if results.len() >= limit {
                        break;
                    }
                }
            }
        }
        offset += line.len();
    }
    results
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SearchMatch {
    pub start: usize,
    pub end: usize,
    pub wrapped: bool,
}

/// Find the next exact occurrence after the previous result, wrapping around.
/// A byte offset is reduced to a UTF-8 boundary before slicing.
pub fn find_next(body: &str, needle: &str, previous_end: usize) -> Option<SearchMatch> {
    if needle.is_empty() || needle.len() > 4096 {
        return None;
    }
    let mut from = previous_end.min(body.len());
    while !body.is_char_boundary(from) {
        from -= 1;
    }
    if let Some(relative) = body[from..].find(needle) {
        let start = from + relative;
        return Some(SearchMatch {
            start,
            end: start + needle.len(),
            wrapped: false,
        });
    }
    body[..from].find(needle).map(|start| SearchMatch {
        start,
        end: start + needle.len(),
        wrapped: true,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn outline_uses_utf8_offsets_and_ignores_code_fences() {
        let body = "# مقدمه\n\nResearch content.\n~~~md\n# fake\n~~~\n## نتایج 🧠\n";
        let headings = outline(body, 10);
        assert_eq!(headings.len(), 2);
        assert_eq!(headings[0].title, "مقدمه");
        assert_eq!(headings[1].level, 2);
        assert_eq!(
            body.get(headings[1].offset..headings[1].offset + 2),
            Some("##")
        );
    }

    #[test]
    fn find_next_wraps_without_splitting_unicode() {
        let body = "پژوهش: data. 🧠 پژوهش: data.";
        let first = find_next(body, "پژوهش", 0).unwrap();
        let second = find_next(body, "پژوهش", first.end).unwrap();
        let wrapped = find_next(body, "پژوهش", second.end).unwrap();
        assert!(body.is_char_boundary(first.start));
        assert!(body.is_char_boundary(second.end));
        assert!(second.start > first.start);
        assert_eq!(wrapped.start, first.start);
        assert!(wrapped.wrapped);
    }

    #[test]
    fn searching_long_document_is_bounded_and_nonmutating() {
        let text = "A replicated observation.\n".repeat(20_000);
        let original = text.clone();
        let matches = find_next(&text, "observation", text.len() / 2).unwrap();
        assert_eq!(&text[matches.start..matches.end], "observation");
        assert_eq!(text, original);
        assert!(find_next(&text, "", 0).is_none());
    }
}
