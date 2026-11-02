//! Read-only PDF figure/table *caption anchors* for a human-review preview.
//!
//! `firecrawl-pdfium = 0.1.0` exposes positioned text, but not enumeration of
//! PDF image or drawing objects. Consequently these are candidate caption
//! anchors, NOT extracted figure images, table cells, or semantic structure.
//! No source file is modified, and no candidate is automatically accepted.

use firecrawl_pdfium::{PageChar, PageRect, Pdfium, Rotation};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::path::Path;

use super::{read_bounded_pdf, runtime_library};

const MAX_PAGES: usize = 64;
const MAX_PAGE_CHARS: usize = 40_000;
const MAX_CAPTIONS_PER_PAGE: usize = 32;
const MAX_CAPTIONS_TOTAL: usize = 128;
const MAX_CAPTION_CHARS: usize = 300;

pub const REVIEW_WARNING: &str = "These are unverified PDF text-layer caption anchors only. No figure pixels or table cells were extracted. Check the original page, verify the caption and bounds, and explicitly confirm or reject each candidate before using it.";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CandidateKind {
    Figure,
    Table,
}

/// PDF page-space coordinates in points (1 point = 1/72 inch), with y
/// increasing upward. These bound *caption glyphs only*; they do not bound
/// the underlying figure or table. Apply page rotation when displaying them.
#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub struct PdfPointsRect {
    pub left: f64,
    pub bottom: f64,
    pub right: f64,
    pub top: f64,
}

impl From<PageRect> for PdfPointsRect {
    fn from(rect: PageRect) -> Self {
        let rect = rect.normalized();
        Self {
            left: rect.left,
            bottom: rect.bottom,
            right: rect.right,
            top: rect.top,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct FigureTableCandidate {
    /// Stable for the exact source bytes and this deterministic scan order.
    pub id: String,
    pub kind: CandidateKind,
    /// Zero-based PDF page index; `page_number` is one-based for display.
    pub page_index: usize,
    pub page_number: usize,
    pub page_label: Option<String>,
    pub page_rotation_degrees_clockwise: u16,
    pub page_bounds_points: PdfPointsRect,
    pub caption_bounds_points: PdfPointsRect,
    pub caption_first_line: String,
    pub caption_truncated: bool,
    /// Uncalibrated text-label heuristic, NOT confidence in table contents or
    /// in image detection. Range [0, 1].
    pub anchor_heuristic_confidence: f32,
    pub confidence_basis: &'static str,
    pub content_extracted: bool,
    pub human_confirmation_required: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct FigureTablePreview {
    /// SHA-256 of the exact bytes provided to PDFium.
    pub source_sha256: String,
    pub page_count: usize,
    pub pages_inspected: usize,
    /// True when the page/caption budget prevented a complete document scan.
    pub scan_truncated: bool,
    pub candidates: Vec<FigureTableCandidate>,
    pub warning: &'static str,
}

#[derive(Debug, Default)]
struct CaptionLine {
    text: String,
    glyph_count: usize,
    bounds: Option<PageRect>,
    previous_glyph: Option<PageRect>,
    truncated: bool,
}

#[derive(Debug)]
struct CaptionAnchor {
    kind: CandidateKind,
    first_line: String,
    bounds: PageRect,
    heuristic_confidence: f32,
    caption_truncated: bool,
}

fn valid_rect(rect: PageRect, page_bounds: PageRect) -> bool {
    let rect = rect.normalized();
    let page = page_bounds.normalized();
    [rect.left, rect.bottom, rect.right, rect.top]
        .into_iter()
        .all(f64::is_finite)
        && rect.width() > 0.0
        && rect.height() > 0.0
        && rect.left >= page.left - 2.0
        && rect.bottom >= page.bottom - 2.0
        && rect.right <= page.right + 2.0
        && rect.top <= page.top + 2.0
}

fn merge_bounds(a: PageRect, b: PageRect) -> PageRect {
    PageRect::new(
        a.left.min(b.left),
        a.bottom.min(b.bottom),
        a.right.max(b.right),
        a.top.max(b.top),
    )
}

fn detect_caption_label(text: &str) -> Option<(CandidateKind, f32)> {
    let text = text.trim_start();
    let (kind, tail, baseline) = if text
        .get(..6)
        .is_some_and(|prefix| prefix.eq_ignore_ascii_case("figure"))
    {
        (CandidateKind::Figure, text.get(6..)?, 0.65_f32)
    } else if text
        .get(..4)
        .is_some_and(|prefix| prefix.eq_ignore_ascii_case("fig."))
    {
        (CandidateKind::Figure, text.get(4..)?, 0.60_f32)
    } else if text
        .get(..5)
        .is_some_and(|prefix| prefix.eq_ignore_ascii_case("table"))
    {
        (CandidateKind::Table, text.get(5..)?, 0.65_f32)
    } else {
        return None;
    };
    // A label must begin with whitespace followed by a numbered identifier.
    // Reject prose such as "Table of contents" and "Figure illustrates".
    if !tail.starts_with(char::is_whitespace) {
        return None;
    }
    let tail = tail.trim_start();
    let number = tail
        .split(|c: char| c.is_whitespace() || matches!(c, ':' | '.' | ',' | '–' | '—'))
        .next()?;
    if number.is_empty()
        || number.len() > 12
        || !number.chars().any(|c| c.is_ascii_digit())
        || !number
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-')
    {
        return None;
    }
    // This is a ranking aid for human review, not a calibrated probability.
    let has_caption_detail = tail.len() > number.len() + 3;
    Some((kind, baseline + if has_caption_detail { 0.05 } else { 0.0 }))
}

fn finish_line(line: &mut CaptionLine, hits: &mut Vec<CaptionAnchor>, truncated: &mut bool) {
    if let (Some(bounds), Some((kind, confidence))) =
        (line.bounds, detect_caption_label(&line.text))
    {
        if hits.len() < MAX_CAPTIONS_PER_PAGE {
            hits.push(CaptionAnchor {
                kind,
                first_line: line.text.trim().to_owned(),
                bounds,
                heuristic_confidence: confidence,
                caption_truncated: line.truncated,
            });
        } else {
            *truncated = true;
        }
    }
    *line = CaptionLine::default();
}

/// Use PDFium's per-character positions directly. Its text() string includes
/// synthetic whitespace and may have different indexes from chars(), so
/// mapping string offsets back to glyph offsets would create false anchors.
fn locate_caption_anchors(chars: &[PageChar], page_bounds: PageRect) -> (Vec<CaptionAnchor>, bool) {
    let mut hits = Vec::new();
    let mut truncated = false;
    let mut line = CaptionLine::default();

    for glyph in chars {
        let Some(ch) = glyph.unicode else {
            finish_line(&mut line, &mut hits, &mut truncated);
            continue;
        };
        if ch == '\n' || ch == '\r' || (ch.is_control() && ch != '\t') {
            finish_line(&mut line, &mut hits, &mut truncated);
            continue;
        }
        if ch.is_whitespace() {
            if !line.text.ends_with(' ') && !line.text.is_empty() {
                line.text.push(' ');
            }
            continue;
        }
        let rect = glyph.loose_bounds.normalized();
        if !valid_rect(rect, page_bounds) {
            finish_line(&mut line, &mut hits, &mut truncated);
            continue;
        }
        if let Some(previous) = line.previous_glyph {
            let baseline_shift =
                ((rect.top + rect.bottom) - (previous.top + previous.bottom)) / 2.0;
            let allowed_shift = (rect.height().max(previous.height()) * 0.70).max(3.0);
            // A large baseline jump or a jump back across the page means
            // another visual line/column, even if PDFium emitted no newline.
            if baseline_shift.abs() > allowed_shift || rect.left < previous.left - 5.0 {
                finish_line(&mut line, &mut hits, &mut truncated);
            } else if rect.left - previous.right > (rect.height() * 0.40).max(3.0)
                && !line.text.ends_with(' ')
            {
                line.text.push(' ');
            }
        }
        line.bounds = Some(match line.bounds {
            Some(existing) => merge_bounds(existing, rect),
            None => rect,
        });
        line.previous_glyph = Some(rect);
        if line.glyph_count < MAX_CAPTION_CHARS {
            line.text.push(ch);
        } else {
            line.truncated = true;
        }
        line.glyph_count += 1;
    }
    finish_line(&mut line, &mut hits, &mut truncated);
    (hits, truncated)
}

/// Scan a bounded number of document pages for possible Figure N / Table N
/// text-layer caption lines. The preview is not persisted or silently applied.
/// The caller must show the warning and source-page image for review.
pub fn preview_pdf_figure_table_candidates(pdf_path: &Path) -> Result<FigureTablePreview, String> {
    // The existing bounded read rejects large/swap-grown files before
    // attempting to load the native parser, using one file handle.
    let bytes = read_bounded_pdf(pdf_path)?;
    let digest = hex::encode(Sha256::digest(&bytes));
    let runtime = runtime_library()?;
    let pdfium = Pdfium::load_from_path(runtime).map_err(|e| e.to_string())?;
    let doc = pdfium
        .load_document(bytes, None)
        .map_err(|e| e.to_string())?;
    let page_count = doc.page_count();
    if page_count == 0 {
        return Err("PDF has no pages for caption review".into());
    }

    let mut preview = FigureTablePreview {
        source_sha256: digest,
        page_count,
        pages_inspected: 0,
        scan_truncated: page_count > MAX_PAGES,
        candidates: Vec::new(),
        warning: REVIEW_WARNING,
    };

    for page_index in 0..page_count.min(MAX_PAGES) {
        let page = doc.page(page_index).map_err(|e| e.to_string())?;
        let page_bounds = page.bounding_box().map_err(|e| e.to_string())?;
        if !valid_rect(page_bounds, page_bounds) {
            return Err(format!(
                "Invalid PDF page geometry at page {}",
                page_index + 1
            ));
        }
        let text = page
            .text_with_limit(MAX_PAGE_CHARS)
            .map_err(|e| format!("PDF page {} text extraction: {e}", page_index + 1))?;
        let (anchors, page_truncated) = locate_caption_anchors(text.chars(), page_bounds);
        preview.pages_inspected += 1;
        preview.scan_truncated |= page_truncated;
        let rotation = match page.rotation() {
            Rotation::None => 0,
            Rotation::Clockwise90 => 90,
            Rotation::Rotate180 => 180,
            Rotation::Clockwise270 => 270,
        };
        let page_label = doc.page_label(page_index);
        for anchor in anchors {
            if preview.candidates.len() == MAX_CAPTIONS_TOTAL {
                preview.scan_truncated = true;
                return Ok(preview);
            }
            let number = preview.candidates.len();
            preview.candidates.push(FigureTableCandidate {
                id: format!("{}:p{}:c{}", preview.source_sha256, page_index, number),
                kind: anchor.kind,
                page_index,
                page_number: page_index + 1,
                page_label: page_label.clone(),
                page_rotation_degrees_clockwise: rotation,
                page_bounds_points: page_bounds.into(),
                caption_bounds_points: anchor.bounds.into(),
                caption_first_line: anchor.first_line,
                caption_truncated: anchor.caption_truncated,
                anchor_heuristic_confidence: anchor.heuristic_confidence,
                confidence_basis: "Uncalibrated Figure/Fig./Table numbered text-prefix heuristic",
                content_extracted: false,
                human_confirmation_required: true,
            });
        }
    }
    Ok(preview)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn glyph(ch: char, x: f64, y: f64) -> PageChar {
        let bounds = PageRect::new(x, y, x + 5.0, y + 9.0);
        PageChar {
            unicode: Some(ch),
            code: ch as u32,
            bounds,
            loose_bounds: bounds,
            origin: firecrawl_pdfium::PagePoint::new(x, y),
        }
    }

    #[test]
    fn only_numbered_caption_labels_qualify() {
        for (text, expected_kind, expected_score) in [
            ("Figure 2: Study flow", CandidateKind::Figure, 0.70_f32),
            ("Fig. S3 – Illustration", CandidateKind::Figure, 0.65_f32),
            ("TABLE 4. Outcome measures", CandidateKind::Table, 0.70_f32),
        ] {
            let (kind, score) = detect_caption_label(text).unwrap();
            assert_eq!(kind, expected_kind);
            assert!((score - expected_score).abs() < 0.0001);
        }
        for text in [
            "Table of contents",
            "Figure shows effects",
            "table one",
            "Figures 2–3",
            "A figure 1 caption",
            "Figuring 2",
            "Table1",
            "Figure 1bad!",
            "Table abc",
        ] {
            assert!(
                detect_caption_label(text).is_none(),
                "unexpected label: {text}"
            );
        }
    }

    #[test]
    fn glyph_geometry_is_distinct_from_figure_content() {
        let page = PageRect::new(0.0, 0.0, 420.0, 260.0);
        let first: Vec<_> = "Figure 1: A diagram"
            .chars()
            .enumerate()
            .map(|(i, c)| glyph(c, 20.0 + i as f64 * 5.0, 120.0))
            .collect();
        let mut mixed = first;
        mixed.extend(
            "Table 2: Summary"
                .chars()
                .enumerate()
                .map(|(i, c)| glyph(c, 20.0 + i as f64 * 5.0, 50.0)),
        );
        let (hits, truncated) = locate_caption_anchors(&mixed, page);
        assert!(!truncated);
        assert_eq!(hits.len(), 2);
        assert_eq!(hits[0].kind, CandidateKind::Figure);
        assert_eq!(hits[1].kind, CandidateKind::Table);
        assert!(hits[0].bounds.top < 130.0);
        assert!(hits[1].bounds.bottom >= 50.0);
    }

    #[test]
    fn malformed_geometry_never_yields_a_location() {
        let page = PageRect::new(0.0, 0.0, 420.0, 260.0);
        let mut chars: Vec<_> = "Table 1: Results"
            .chars()
            .enumerate()
            .map(|(i, c)| glyph(c, i as f64 * 5.0, 40.0))
            .collect();
        chars[0].loose_bounds.left = f64::NAN;
        assert!(locate_caption_anchors(&chars, page).0.is_empty());
    }

    #[test]
    fn rejects_sparse_oversized_input_before_loading_pdfium() {
        let path = std::env::temp_dir().join(format!("rw-f37-{}.pdf", uuid::Uuid::new_v4()));
        let file = std::fs::File::create(&path).unwrap();
        file.set_len(128 * 1024 * 1024 + 1).unwrap();
        let err = preview_pdf_figure_table_candidates(&path).unwrap_err();
        assert!(err.contains("bounded native file budget"));
        std::fs::remove_file(&path).unwrap();
    }

    #[test]
    fn preview_model_declares_review_and_no_extracted_content() {
        let warning = REVIEW_WARNING.to_lowercase();
        assert!(warning.contains("unverified"));
        assert!(warning.contains("no figure pixels or table cells"));
        assert!(warning.contains("confirm or reject"));
    }

    #[test]
    fn native_pdfium_preview_keeps_source_provenance_and_caption_only_bounds() {
        if runtime_library().is_err() {
            eprintln!("PDFium runtime missing; native F37 fixture requires packaging runtime");
            return;
        }
        use lopdf::{dictionary, Object, Stream};
        let path = std::env::temp_dir().join(format!("rw-f37-native-{}.pdf", uuid::Uuid::new_v4()));
        let mut pdf = lopdf::Document::with_version("1.5");
        let pages = pdf.new_object_id();
        let font = pdf.add_object(dictionary! {
            "Type"=>"Font", "Subtype"=>"Type1", "BaseFont"=>"Helvetica"
        });
        let resources = pdf.add_object(dictionary! { "Font"=> dictionary! { "F1"=>font } });
        let content = lopdf::content::Content {
            operations: vec![
                lopdf::content::Operation::new("BT", vec![]),
                lopdf::content::Operation::new("Tf", vec!["F1".into(), 14.into()]),
                lopdf::content::Operation::new("Td", vec![25.into(), 170.into()]),
                lopdf::content::Operation::new(
                    "Tj",
                    vec![Object::string_literal("Figure 1: Study flow")],
                ),
                lopdf::content::Operation::new("ET", vec![]),
                lopdf::content::Operation::new("BT", vec![]),
                lopdf::content::Operation::new("Tf", vec!["F1".into(), 14.into()]),
                lopdf::content::Operation::new("Td", vec![25.into(), 85.into()]),
                lopdf::content::Operation::new(
                    "Tj",
                    vec![Object::string_literal("Table 2: Results")],
                ),
                lopdf::content::Operation::new("ET", vec![]),
            ],
        };
        let stream = pdf.add_object(Stream::new(dictionary! {}, content.encode().unwrap()));
        let page = pdf.add_object(dictionary! {
            "Type"=>"Page", "Parent"=>pages, "Resources"=>resources,
            "Contents"=>stream, "MediaBox"=>vec![0.into(),0.into(),420.into(),260.into()]
        });
        pdf.objects.insert(
            pages,
            dictionary! {
                "Type"=>"Pages", "Kids"=>vec![page.into()], "Count"=>1
            }
            .into(),
        );
        let root = pdf.add_object(dictionary! { "Type"=>"Catalog", "Pages"=>pages });
        pdf.trailer.set("Root", root);
        pdf.save(&path).unwrap();
        let expected_sha = hex::encode(Sha256::digest(std::fs::read(&path).unwrap()));
        let preview = preview_pdf_figure_table_candidates(&path).unwrap();
        assert_eq!(preview.source_sha256, expected_sha);
        let inspected =
            super::super::render_search_at_verified(&path, "", 0, &preview.source_sha256).unwrap();
        assert_eq!((inspected.page_index, inspected.page_count), (0, 1));
        assert_eq!((preview.page_count, preview.pages_inspected), (1, 1));
        assert!(!preview.scan_truncated);
        assert_eq!(preview.candidates.len(), 2);
        for candidate in &preview.candidates {
            assert_eq!(candidate.page_number, 1);
            assert!(candidate.caption_bounds_points.left >= 0.0);
            assert!(candidate.caption_bounds_points.right <= 420.0);
            assert!(candidate.caption_bounds_points.top <= 260.0);
            assert!(!candidate.content_extracted);
            assert!(candidate.human_confirmation_required);
            assert_eq!(candidate.page_rotation_degrees_clockwise, 0);
        }
        assert_eq!(preview.candidates[0].kind, CandidateKind::Figure);
        assert_eq!(preview.candidates[1].kind, CandidateKind::Table);
        assert!(
            preview.candidates[0].caption_bounds_points.bottom
                > preview.candidates[1].caption_bounds_points.top
        );
        std::fs::remove_file(&path).unwrap();
    }
}
