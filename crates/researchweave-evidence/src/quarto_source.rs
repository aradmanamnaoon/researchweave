//! F31 source-only, inert Quarto Markdown projection of a validated manuscript.
//! No renderer/toolchain, executable cells, shell, network, or write operations.
use crate::manuscript_document::{Block, DocumentError, Inline, ManuscriptDocument};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fmt::Write;

const MAX_QMD_BYTES: usize = 1_048_576;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QuartoSourcePreview {
    pub format: &'static str,
    pub media_type: &'static str,
    pub filename_suffix: &'static str,
    pub source_document_sha256: String,
    pub qmd_sha256: String,
    pub qmd: String,
    pub loss_codes: Vec<String>,
    pub executable_cells_present: bool,
    pub renderer_invoked: bool,
    pub citations_resolved: bool,
}

fn escape(text: &str, table: bool) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match c {
            '\\' | '*' | '_' | '`' | '[' | ']' | '#' | '!' | '{' | '}' | '$' | '^' | '~' => {
                out.push('\\');
                out.push(c);
            }
            '|' if table => out.push_str("\\|"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '&' => out.push_str("&amp;"),
            '\n' if table => out.push_str(" / "),
            '\n' => out.push_str("  \n"),
            '\t' => out.push(' '),
            _ => out.push(c),
        }
    }
    out
}

fn inlines(items: &[Inline], table: bool, losses: &mut BTreeSet<String>) -> String {
    let mut out = String::new();
    for item in items {
        match item {
            Inline::Text(t) => out.push_str(&escape(t, table)),
            Inline::Strong(children) => {
                out.push_str("**");
                out.push_str(&inlines(children, table, losses));
                out.push_str("**");
            }
            Inline::Emphasis(children) => {
                out.push('*');
                out.push_str(&inlines(children, table, losses));
                out.push('*');
            }
            Inline::Citation(id) => {
                losses.insert("unresolved_reference_citation".into());
                out.push_str(&escape(&format!("[unresolved citation: {id}]"), table));
            }
        }
    }
    out
}

/// Deterministic UTF-8 `.qmd` preview. Never calls a renderer or saves a file.
/// All AST constraints are checked by the canonical manuscript validator.
pub fn render_quarto_source(
    doc: &ManuscriptDocument,
) -> Result<QuartoSourcePreview, DocumentError> {
    doc.validate()?;
    let source_document_sha256 = doc.sha256()?;
    // JSON-quoted strings are also YAML double-quoted scalars, avoiding title
    // front-matter injection. Execution is explicitly disabled.
    let quoted_title = serde_json::to_string(&doc.title)
        .map_err(|_| DocumentError::Invalid("invalid Quarto title"))?;
    let mut qmd =
        format!("---\ntitle: {quoted_title}\nformat: html\nexecute:\n  enabled: false\n---\n\n");
    let mut losses = BTreeSet::new();
    for block in &doc.blocks {
        match block {
            Block::Heading { level, content } => {
                writeln!(
                    qmd,
                    "{} {}\n",
                    "#".repeat(usize::from(*level)),
                    inlines(content, false, &mut losses)
                )
                .unwrap();
            }
            Block::Paragraph { content } => {
                writeln!(qmd, "{}\n", inlines(content, false, &mut losses)).unwrap();
            }
            Block::PageBreak => {
                // HTML and TeX have different page-break semantics; do not
                // emit untrusted TeX or pretend to preserve this block.
                losses.insert("page_break_not_rendered".into());
                qmd.push_str("<!-- ResearchWeave page break unrepresented in Quarto HTML -->\n\n");
            }
            Block::List { ordered, items } => {
                for (index, item) in items.iter().enumerate() {
                    let marker = if *ordered {
                        format!("{}. ", index + 1)
                    } else {
                        "- ".into()
                    };
                    writeln!(qmd, "{}{}", marker, inlines(item, false, &mut losses)).unwrap();
                }
                qmd.push('\n');
            }
            Block::Table { headers, rows } => {
                writeln!(
                    qmd,
                    "| {} |",
                    headers
                        .iter()
                        .map(|h| escape(h, true))
                        .collect::<Vec<_>>()
                        .join(" | ")
                )
                .unwrap();
                writeln!(
                    qmd,
                    "| {} |",
                    (0..headers.len())
                        .map(|_| "---")
                        .collect::<Vec<_>>()
                        .join(" | ")
                )
                .unwrap();
                for cells in rows {
                    writeln!(
                        qmd,
                        "| {} |",
                        cells
                            .iter()
                            .map(|c| inlines(c, true, &mut losses))
                            .collect::<Vec<_>>()
                            .join(" | ")
                    )
                    .unwrap();
                }
                qmd.push('\n');
            }
        }
        if qmd.len() > MAX_QMD_BYTES {
            return Err(DocumentError::Limit("Quarto UTF-8 source size"));
        }
    }
    let qmd_sha256 = hex::encode(Sha256::digest(qmd.as_bytes()));
    Ok(QuartoSourcePreview {
        format: "quarto-markdown-source-preview-v1",
        media_type: "text/markdown; charset=utf-8",
        filename_suffix: ".qmd",
        source_document_sha256,
        qmd_sha256,
        qmd,
        loss_codes: losses.into_iter().collect(),
        executable_cells_present: false,
        renderer_invoked: false,
        citations_resolved: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> ManuscriptDocument {
        ManuscriptDocument {
            title: "\u{062a}\u{062c}\u{0631}\u{0628}\u{0647}: --- # \"not-yaml\"".into(),
            blocks: vec![
                Block::Heading {
                    level: 2,
                    content: vec![Inline::Text("Evidence & <script>".into())],
                },
                Block::Paragraph {
                    content: vec![
                        Inline::Text("\\input{secret.tex} ".into()),
                        Inline::Strong(vec![Inline::Text("bold *symbol*".into())]),
                        Inline::Emphasis(vec![Inline::Text("italic".into())]),
                        Inline::Citation("22222222-2222-4222-8222-222222222222".into()),
                    ],
                },
                Block::List {
                    ordered: true,
                    items: vec![
                        vec![Inline::Text("First | row".into())],
                        vec![Inline::Text("Second".into())],
                    ],
                },
                Block::Table {
                    headers: vec!["A | B".into(), "Outcome".into()],
                    rows: vec![vec![
                        vec![Inline::Text("x|y".into())],
                        vec![Inline::Text(
                            "\u{067e}\u{0698}\u{0648}\u{0647}\u{0634}".into(),
                        )],
                    ]],
                },
                Block::PageBreak,
            ],
        }
    }

    #[test]
    fn inert_loss_aware_quarto_preserves_text_without_untrusted_execution() {
        let a = render_quarto_source(&fixture()).unwrap();
        assert_eq!(a, render_quarto_source(&fixture()).unwrap());
        assert_eq!(a.source_document_sha256, fixture().sha256().unwrap());
        assert_eq!(a.qmd_sha256, hex::encode(Sha256::digest(a.qmd.as_bytes())));
        assert!(a.qmd.starts_with("---\ntitle: \""));
        assert!(a.qmd.contains("execute:\n  enabled: false"));
        assert!(a.qmd.contains("## Evidence &amp; &lt;script&gt;"));
        assert!(a.qmd.contains("\\\\input\\{secret.tex\\}"));
        assert!(a.qmd.contains("| A \\| B | Outcome |"));
        assert!(a.qmd.contains("2. Second"));
        assert_eq!(
            a.loss_codes,
            vec!["page_break_not_rendered", "unresolved_reference_citation"]
        );
        assert!(!a.renderer_invoked && !a.executable_cells_present && !a.citations_resolved);
    }

    #[test]
    fn invalid_document_ast_never_gets_quarto_source() {
        let mut doc = fixture();
        doc.blocks.push(Block::Heading {
            level: 0,
            content: vec![Inline::Text("invalid".into())],
        });
        assert!(render_quarto_source(&doc).is_err());
        let mut doc = fixture();
        doc.blocks.push(Block::Paragraph {
            content: vec![Inline::Citation("fabricated".into())],
        });
        assert!(render_quarto_source(&doc).is_err());
    }
}
