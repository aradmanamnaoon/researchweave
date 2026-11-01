//! Native, dynamically loaded PDFium render + positioned text proof.
// F37 caption anchors are now displayed as unverified, read-only suggestions
// with source-page navigation. There is still NO image/table extraction,
// accepted review decision or persistent figure/table content.
#[allow(dead_code)]
#[path = "pdf_figure_candidates.rs"]
pub mod figure_candidates;

use firecrawl_pdfium::{PageChar, PageRect, Pdfium, PixelFormat, RenderConfig};
use sha2::{Digest, Sha256};
use std::io::Read;
use std::path::{Path, PathBuf};
#[cfg(test)]
use std::{fs::File, io::BufWriter};

#[derive(Debug)]
pub struct SearchRect {
    pub byte_start: usize,
    pub byte_end: usize,
    pub page_rect: PageRect,
    pub pixel_rect: firecrawl_pdfium::PixelRect,
}
#[derive(Debug)]
pub struct PdfRender {
    /// Zero-based PDF page index shown by this render.
    pub page_index: usize,
    pub page_count: usize,
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
    pub extracted_text: String,
    /// Exact number of search occurrences on this page. Rectangles are bounded.
    pub match_count: usize,
    pub matches: Vec<SearchRect>,
}

#[cfg(target_os = "windows")]
const PDFIUM_LIBRARY: &str = "pdfium.dll";
#[cfg(target_os = "macos")]
const PDFIUM_LIBRARY: &str = "libpdfium.dylib";
#[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
const PDFIUM_LIBRARY: &str = "libpdfium.so";

fn packaged_runtime_candidates(exe_dir: &Path) -> Vec<PathBuf> {
    vec![
        exe_dir.join(PDFIUM_LIBRARY),
        #[cfg(target_os = "macos")]
        exe_dir.join("../Frameworks").join(PDFIUM_LIBRARY),
        #[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
        exe_dir.join("../lib").join(PDFIUM_LIBRARY),
    ]
}

pub fn runtime_library() -> Result<PathBuf, String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let exe_dir = exe.parent().ok_or("No executable directory")?;
    for candidate in packaged_runtime_candidates(exe_dir) {
        if candidate.is_file() {
            return candidate.canonicalize().map_err(|e| e.to_string());
        }
    }
    if let Ok(custom) = std::env::var("PDFIUM_LIB_PATH") {
        let path = PathBuf::from(custom);
        let path = if path.is_dir() {
            path.join(PDFIUM_LIBRARY)
        } else {
            path
        };
        if path.is_file() {
            return path.canonicalize().map_err(|e| e.to_string());
        }
    }
    let platform_dir = if cfg!(target_os = "windows") {
        "windows-x64"
    } else if cfg!(all(target_os = "macos", target_arch = "aarch64")) {
        "macos-arm64"
    } else if cfg!(target_os = "macos") {
        "macos-x64"
    } else {
        "linux-x64"
    };
    for ancestor in exe_dir.ancestors() {
        let roots = [
            ancestor.join("target/pdfium").join(platform_dir),
            ancestor.join("target/pdfium/win-x64"),
        ];
        for root in roots {
            for relative in [
                PathBuf::from(PDFIUM_LIBRARY),
                PathBuf::from("bin").join(PDFIUM_LIBRARY),
                PathBuf::from("lib").join(PDFIUM_LIBRARY),
            ] {
                let candidate = root.join(relative);
                if candidate.is_file() {
                    return candidate.canonicalize().map_err(|e| e.to_string());
                }
            }
        }
    }
    Err(format!(
        "Pinned PDFium runtime ({PDFIUM_LIBRARY}) not installed; run the verified packaging PDFium fetcher"
    ))
}

pub fn render_search(pdf_path: &Path, query: &str) -> Result<PdfRender, String> {
    render_search_at(pdf_path, query, 0)
}

const MAX_NATIVE_PDF_BYTES: u64 = 128 * 1024 * 1024;

fn read_bounded_pdf(pdf_path: &Path) -> Result<Vec<u8>, String> {
    // Use one open handle for metadata and content. A path could otherwise be
    // swapped or the file could grow between metadata(path) and read(path).
    let file = std::fs::File::open(pdf_path).map_err(|e| e.to_string())?;
    if file.metadata().map_err(|e| e.to_string())?.len() > MAX_NATIVE_PDF_BYTES {
        return Err("PDF exceeds the bounded native file budget".into());
    }
    let mut contents = Vec::new();
    file.take(MAX_NATIVE_PDF_BYTES + 1)
        .read_to_end(&mut contents)
        .map_err(|e| e.to_string())?;
    if contents.len() as u64 > MAX_NATIVE_PDF_BYTES {
        return Err("PDF exceeds the bounded native file budget".into());
    }
    Ok(contents)
}

/// Find the next page containing an exact, case-sensitive query. Starts after
/// the current page, wraps once, and includes the current page only last.
/// This text-only pass does not render intermediate pages or mutate a source.
pub fn find_next_matching_page(
    pdf_path: &Path,
    query: &str,
    current_page_index: usize,
) -> Result<Option<usize>, String> {
    if query.trim().is_empty() || query.len() > 256 {
        return Err("PDF find-next requires a nonblank query of at most 256 bytes".into());
    }
    const MAX_SCAN_PAGES: usize = 512;
    const MAX_TOTAL_TEXT_BYTES: usize = 16 * 1024 * 1024;
    let contents = read_bounded_pdf(pdf_path)?;
    let runtime = runtime_library()?;
    let pdfium = Pdfium::load_from_path(runtime).map_err(|e| e.to_string())?;
    let doc = pdfium
        .load_document(contents, None)
        .map_err(|e| e.to_string())?;
    let page_count = doc.page_count();
    if page_count == 0 || page_count > MAX_SCAN_PAGES || current_page_index >= page_count {
        return Err("PDF find-next page count or current index exceeds the supported range".into());
    }
    let mut total_bytes = 0_usize;
    for offset in 1..=page_count {
        let page_index = (current_page_index + offset) % page_count;
        let text = doc
            .page(page_index)
            .map_err(|e| e.to_string())?
            .text()
            .map_err(|e| e.to_string())?;
        total_bytes = total_bytes.saturating_add(text.text().len());
        if total_bytes > MAX_TOTAL_TEXT_BYTES {
            return Err("PDF find-next extracted text exceeds the bounded scan budget".into());
        }
        if text.text().contains(query) {
            return Ok(Some(page_index));
        }
    }
    Ok(None)
}

/// Render and search one explicit page in a PDF. Page indexes are zero-based.
/// The caller owns document navigation and never assumes that page zero is the
/// only page. Invalid indexes fail without silently displaying a different page.
pub fn render_search_at(
    pdf_path: &Path,
    query: &str,
    page_index: usize,
) -> Result<PdfRender, String> {
    // Bound the complete input file on a single open handle before loading
    // PDFium or allocating a render. The previous direct fs::read could
    // allocate arbitrarily large attacker-supplied PDFs.
    let contents = read_bounded_pdf(pdf_path)?;
    render_search_at_bytes(contents, query, page_index)
}

/// Render a caption's source page only if the exact bounded bytes used by
/// PDFium match the SHA-256 produced by the earlier caption scan. This is the
/// entry point for F37 caption navigation; validating the path in a separate
/// preliminary operation would leave a file-substitution race.
///
/// The caller must pass `FigureTablePreview::source_sha256` from the selected
/// scan, and must invalidate older UI jobs when the source path changes.
pub fn render_search_at_verified(
    pdf_path: &Path,
    query: &str,
    page_index: usize,
    expected_sha256: &str,
) -> Result<PdfRender, String> {
    if expected_sha256.len() != 64
        || !expected_sha256
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err("PDF caption source SHA-256 must be 64 lowercase hex characters".into());
    }
    // The same open handle supplies both the hash and the actual PDF parser
    // input. A same-path replacement never passes an old scan's source hash.
    let contents = read_bounded_pdf(pdf_path)?;
    verify_source_sha256(&contents, expected_sha256)?;
    render_search_at_bytes(contents, query, page_index)
}

fn verify_source_sha256(bytes: &[u8], expected_sha256: &str) -> Result<(), String> {
    let actual = hex::encode(Sha256::digest(bytes));
    if actual != expected_sha256 {
        return Err(
            "PDF source bytes changed since the caption scan; scan again before navigation".into(),
        );
    }
    Ok(())
}

/// A text-layer match does not necessarily have the same index in the
/// positioned PDFium glyph collection. In particular, generated whitespace
/// and unsupported Unicode may change the number or ordering of characters.
/// Only map text ranges when the entire extracted stream has a proven one-to-
/// one correspondence with positioned glyphs. The match count is still the
/// count of literal occurrences in the extracted text if mapping is unsafe.
fn matched_glyph_bounds(
    extracted_text: &str,
    chars: &[PageChar],
    query: &str,
    page_bounds: Option<PageRect>,
) -> (usize, Vec<(usize, usize, PageRect)>) {
    const MAX_PAGE_SEARCH_RECTS: usize = 256;
    if query.is_empty() {
        return (0, Vec::new());
    }
    let reliable_mapping = page_bounds
        .filter(|bounds| valid_page_rect(*bounds, *bounds))
        .is_some()
        && extracted_text.chars().count() == chars.len()
        && extracted_text
            .chars()
            .zip(chars)
            .all(|(displayed, glyph)| glyph.unicode == Some(displayed));
    let mut match_count = 0_usize;
    let mut hits = Vec::new();
    let mut previous_byte_end = 0;
    let mut previous_char_end = 0;
    for (byte_start, _) in extracted_text.match_indices(query) {
        match_count = match_count.saturating_add(1);
        if !reliable_mapping || match_count > MAX_PAGE_SEARCH_RECTS {
            continue;
        }
        let byte_end = byte_start + query.len();
        let start = previous_char_end
            + extracted_text[previous_byte_end..byte_start]
                .chars()
                .count();
        let end = start + query.chars().count();
        previous_byte_end = byte_end;
        previous_char_end = end;
        let Some(glyphs) = chars.get(start..end) else {
            continue;
        };
        let mut bounds = None;
        let mut valid = true;
        for glyph in glyphs {
            if glyph.unicode.is_some_and(char::is_whitespace) {
                continue;
            }
            let rect = glyph.loose_bounds;
            if !valid_page_rect(
                rect,
                page_bounds.expect("reliable mapping requires page bounds"),
            ) {
                valid = false;
                break;
            }
            bounds = Some(match bounds {
                Some(existing) => union_rect(existing, rect),
                None => rect,
            });
        }
        if valid {
            if let Some(rect) = bounds {
                hits.push((byte_start, byte_end, rect));
            }
        }
    }
    (match_count, hits)
}

fn union_rect(left: PageRect, right: PageRect) -> PageRect {
    PageRect::new(
        left.left.min(right.left),
        left.bottom.min(right.bottom),
        left.right.max(right.right),
        left.top.max(right.top),
    )
}

fn valid_page_rect(rect: PageRect, page: PageRect) -> bool {
    [
        rect.left,
        rect.right,
        rect.bottom,
        rect.top,
        page.left,
        page.right,
        page.bottom,
        page.top,
    ]
    .into_iter()
    .all(f64::is_finite)
        && page.left < page.right
        && page.bottom < page.top
        && rect.left < rect.right
        && rect.bottom < rect.top
        && rect.left >= page.left - 2.0
        && rect.right <= page.right + 2.0
        && rect.bottom >= page.bottom - 2.0
        && rect.top <= page.top + 2.0
}

fn render_search_at_bytes(
    contents: Vec<u8>,
    query: &str,
    page_index: usize,
) -> Result<PdfRender, String> {
    let runtime = runtime_library()?;
    let pdfium = Pdfium::load_from_path(runtime).map_err(|e| e.to_string())?;
    let doc = pdfium
        .load_document(contents, None)
        .map_err(|e| e.to_string())?;
    let page_count = doc.page_count();
    if page_count == 0 {
        return Err("PDF contains no pages".into());
    }
    if page_index >= page_count {
        return Err(format!(
            "PDF page {} is outside the valid range 1–{page_count}",
            page_index.saturating_add(1)
        ));
    }
    let page = doc.page(page_index).map_err(|e| e.to_string())?;
    let render = page
        .render(
            &RenderConfig::new()
                .dpi(120.0)
                .pixel_format(PixelFormat::Rgba8)
                .max_output_bytes(64 * 1024 * 1024),
        )
        .map_err(|e| e.to_string())?;
    // Bound the native per-glyph allocation before extracting a hostile page.
    let text = page.text_with_limit(120_000).map_err(|e| e.to_string())?;
    const MAX_PAGE_TEXT_BYTES: usize = 16 * 1024 * 1024;
    if text.text().len() > MAX_PAGE_TEXT_BYTES {
        return Err("PDF text layer exceeds the bounded per-page budget".into());
    }
    let (match_count, located) =
        matched_glyph_bounds(text.text(), text.chars(), query, page.bounding_box().ok());
    let hits = located
        .into_iter()
        .map(|(byte_start, byte_end, page_rect)| SearchRect {
            byte_start,
            byte_end,
            page_rect,
            pixel_rect: render.transform().page_rect_to_pixel(page_rect),
        })
        .collect();
    let (width, height) = (render.width(), render.height());
    let stride = render.stride();
    let bpp = render.format().bytes_per_pixel();
    if bpp != 4 {
        return Err(format!("Expected four-channel render, got {bpp}"));
    }
    let width = usize::try_from(width).map_err(|_| "PDF render width out of range")?;
    let height = usize::try_from(height).map_err(|_| "PDF render height out of range")?;
    let required = width
        .checked_mul(height)
        .and_then(|pixels| pixels.checked_mul(4))
        .filter(|bytes| *bytes > 0 && *bytes <= 64 * 1024 * 1024)
        .ok_or("PDF render exceeds the bounded RGBA image budget")?;
    let min_stride = width.checked_mul(4).ok_or("PDF render stride overflow")?;
    let stride_bytes = stride
        .checked_mul(height)
        .ok_or("PDF render buffer overflow")?;
    if stride < min_stride || stride_bytes > render.pixels().len() {
        return Err("PDF render pixel buffer layout is inconsistent".into());
    }
    let mut rgba = vec![0; required];
    for y in 0..height {
        for x in 0..width {
            let src = &render.pixels()[y * stride + x * 4..][..4];
            let out = &mut rgba[(y * width + x) * 4..][..4];
            out.copy_from_slice(src);
        }
    }
    Ok(PdfRender {
        page_index,
        page_count,
        width: u32::try_from(width).map_err(|_| "PDF render width invalid")?,
        height: u32::try_from(height).map_err(|_| "PDF render height invalid")?,
        rgba,
        extracted_text: text.text().to_owned(),
        match_count,
        matches: hits,
    })
}

#[cfg(test)]
pub fn save_png(result: &PdfRender, output: &Path) -> Result<(), String> {
    let writer = BufWriter::new(File::create(output).map_err(|e| e.to_string())?);
    let mut enc = png::Encoder::new(writer, result.width, result.height);
    enc.set_color(png::ColorType::Rgba);
    enc.set_depth(png::BitDepth::Eight);
    enc.write_header()
        .map_err(|e| e.to_string())?
        .write_image_data(&result.rgba)
        .map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use lopdf::{dictionary, Object, Stream};

    fn glyph(ch: char, left: f64, bottom: f64) -> PageChar {
        let rect = PageRect::new(left, bottom, left + 5.0, bottom + 10.0);
        PageChar {
            unicode: Some(ch),
            code: ch as u32,
            bounds: rect,
            loose_bounds: rect,
            origin: firecrawl_pdfium::PagePoint::new(left, bottom),
        }
    }

    #[test]
    fn substituted_same_path_pdf_fails_source_verification_before_pdfium_load() {
        let path =
            std::env::temp_dir().join(format!("rw-caption-sha-{}.pdf", uuid::Uuid::new_v4()));
        let original = b"%PDF-1.4 original bytes";
        std::fs::write(&path, original).unwrap();
        let old_digest = hex::encode(Sha256::digest(original));
        // The pathname and source length remain identical. Metadata alone
        // cannot prove that it is the previously scanned PDF.
        let replacement = b"%PDF-1.4 replaced bytes";
        assert_eq!(original.len(), replacement.len());
        std::fs::write(&path, replacement).unwrap();
        let error = render_search_at_verified(&path, "", 0, &old_digest).unwrap_err();
        assert!(error.contains("source bytes changed"), "{error}");
        assert!(verify_source_sha256(&read_bounded_pdf(&path).unwrap(), &old_digest).is_err());
        assert!(render_search_at_verified(&path, "", 0, "ABC")
            .unwrap_err()
            .contains("64 lowercase"));
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn verified_source_hash_is_of_the_exact_bounded_parser_input() {
        let path = std::env::temp_dir().join(format!("rw-pdf-hash-{}.pdf", uuid::Uuid::new_v4()));
        let data = b"%PDF-1.4\n% Fixed input test.\n";
        std::fs::write(&path, data).unwrap();
        let read = read_bounded_pdf(&path).unwrap();
        let digest = hex::encode(Sha256::digest(&read));
        assert_eq!(read, data);
        verify_source_sha256(&read, &digest).unwrap();
        assert!(verify_source_sha256(b"different", &digest).is_err());
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn unicode_byte_offsets_map_only_when_glyph_stream_agrees_exactly() {
        let page = PageRect::new(0.0, 0.0, 420.0, 260.0);
        let extracted = "é漢Ω é漢Ω";
        let chars: Vec<_> = extracted
            .chars()
            .enumerate()
            .map(|(i, ch)| glyph(ch, i as f64 * 9.0 + 20.0, 30.0))
            .collect();
        let (count, rects) = matched_glyph_bounds(extracted, &chars, "漢Ω", Some(page));
        assert_eq!(count, 2);
        assert_eq!(rects.len(), 2);
        assert_eq!((rects[0].0, rects[0].1), (2, 7));
        assert_eq!((rects[1].0, rects[1].1), (10, 15));
        assert!(rects[0].2.left < rects[1].2.left);
    }

    #[test]
    fn generated_whitespace_or_unsupported_unicode_suppresses_unproven_rectangles() {
        let page = PageRect::new(0.0, 0.0, 420.0, 260.0);
        let displayed = "café\n漢字";
        let mut chars: Vec<_> = "café漢字"
            .chars()
            .enumerate()
            .map(|(i, c)| glyph(c, i as f64 * 8.0 + 10.0, 20.0))
            .collect();
        // The PDF text accessor can inject a newline not present in PDFium
        // character indices. A naïve byte/character offset maps onto the
        // wrong glyph, and must never be turned into a highlight rectangle.
        let (count, hits) = matched_glyph_bounds(displayed, &chars, "漢字", Some(page));
        assert_eq!(count, 1);
        assert!(hits.is_empty());

        chars = "café\n漢字"
            .chars()
            .enumerate()
            .map(|(i, c)| glyph(c, i as f64 * 8.0 + 10.0, 20.0))
            .collect();
        chars[5].unicode = None; // PDFium cannot represent this Unicode glyph.
        let (count, hits) = matched_glyph_bounds(displayed, &chars, "漢字", Some(page));
        assert_eq!(count, 1);
        assert!(hits.is_empty());
        chars[5].unicode = Some('漢');
        chars[5].loose_bounds.left = f64::NAN;
        let (count, hits) = matched_glyph_bounds(displayed, &chars, "漢字", Some(page));
        assert_eq!(count, 1);
        assert!(hits.is_empty());
        assert_eq!(matched_glyph_bounds(displayed, &chars, "", Some(page)).0, 0);
    }

    fn fixture(path: &Path) {
        fixture_pages(path, &["ResearchWeave PDFium anchor"]);
    }
    fn fixture_pages(path: &Path, contents_by_page: &[&str]) {
        assert!(!contents_by_page.is_empty());
        let mut doc = lopdf::Document::with_version("1.5");
        let pages = doc.new_object_id();
        let font = doc.add_object(
            dictionary! { "Type" => "Font", "Subtype" => "Type1", "BaseFont" => "Helvetica" },
        );
        let resources = doc.add_object(dictionary! { "Font" => dictionary! { "F1" => font } });
        let mut page_items = Vec::new();
        for page_text in contents_by_page {
            let contents = lopdf::content::Content {
                operations: vec![
                    lopdf::content::Operation::new("BT", vec![]),
                    lopdf::content::Operation::new("Tf", vec!["F1".into(), 24.into()]),
                    lopdf::content::Operation::new("Td", vec![50.into(), 175.into()]),
                    lopdf::content::Operation::new("Tj", vec![Object::string_literal(*page_text)]),
                    lopdf::content::Operation::new("ET", vec![]),
                ],
            };
            let stream = doc.add_object(Stream::new(dictionary! {}, contents.encode().unwrap()));
            let page = doc.add_object(dictionary! {
                "Type"=>"Page", "Parent"=>pages, "Resources"=>resources,
                "Contents"=>stream, "MediaBox"=>vec![0.into(),0.into(),420.into(),260.into()]
            });
            page_items.push(page.into());
        }
        doc.objects.insert(
            pages,
            dictionary! {
                "Type"=>"Pages", "Kids"=>page_items,
                "Count"=>i64::try_from(contents_by_page.len()).unwrap()
            }
            .into(),
        );
        let root = doc.add_object(dictionary! { "Type"=>"Catalog", "Pages"=>pages });
        doc.trailer.set("Root", root);
        doc.save(path).unwrap();
    }
    #[test]
    fn runtime_is_explicit_or_reports_install_instruction() {
        if let Err(message) = runtime_library() {
            assert!(message.contains("verified packaging PDFium fetcher"));
        }
    }

    #[test]
    fn packaged_runtime_search_includes_platform_layout() {
        let root = Path::new("/application/ResearchWeave.app/Contents/MacOS");
        let candidates = packaged_runtime_candidates(root);
        assert!(!candidates.is_empty());
        assert!(candidates.iter().all(|candidate| candidate
            .file_name()
            .is_some_and(|name| name == PDFIUM_LIBRARY)));
    }

    #[test]
    fn oversized_sparse_pdf_is_rejected_before_loading_native_pdfium() {
        let source =
            std::env::temp_dir().join(format!("rw-oversized-pdf-{}.pdf", uuid::Uuid::new_v4()));
        let file = std::fs::File::create(&source).unwrap();
        file.set_len(MAX_NATIVE_PDF_BYTES + 1).unwrap();
        drop(file);
        let error = render_search_at(&source, "", 0).unwrap_err();
        assert!(error.contains("bounded native file budget"), "{error}");
        assert!(read_bounded_pdf(&source).is_err());
        std::fs::remove_file(&source).unwrap();
    }
    #[test]
    fn native_pdfium_renders_and_only_maps_proven_text() {
        if runtime_library().is_err() {
            eprintln!("PDFium runtime missing; download with packaging script");
            return;
        }
        let input = std::env::temp_dir().join(format!("rw-pdfium-{}.pdf", uuid::Uuid::new_v4()));
        fixture(&input);
        if let Ok(destination) = std::env::var("RW_PDFIUM_FIXTURE") {
            std::fs::copy(&input, destination).unwrap();
        }
        let rendered = render_search(&input, "PDFium").expect("PDFium render + extract");
        assert!(rendered.width >= 400 && rendered.height >= 200);
        assert_eq!(
            rendered.rgba.len(),
            rendered.width as usize * rendered.height as usize * 4
        );
        assert!(rendered.extracted_text.contains("PDFium"));
        assert_eq!(rendered.match_count, 1);
        // A match can exist in extracted text without a provably identical
        // positioned glyph stream. In that case its rectangle must be absent.
        assert!(rendered.matches.len() <= 1);
        let without_search = render_search_at(&input, "", 0).unwrap();
        assert_eq!(without_search.match_count, 0);
        assert!(without_search.matches.is_empty());
        if let Some(hit) = rendered.matches.first() {
            assert!(hit.page_rect.width() > 0.0 && hit.page_rect.height() > 0.0);
            assert!(hit.pixel_rect.width > 0.0 && hit.pixel_rect.height > 0.0);
        }
        let digest = hex::encode(Sha256::digest(read_bounded_pdf(&input).unwrap()));
        let verified = render_search_at_verified(&input, "PDFium", 0, &digest).unwrap();
        assert_eq!(verified.matches.len(), rendered.matches.len());
        assert_eq!(verified.extracted_text, rendered.extracted_text);
        if let Ok(destination) = std::env::var("RW_PDFIUM_RENDER_PNG") {
            save_png(&rendered, Path::new(&destination)).unwrap();
        }
        std::fs::remove_file(input).unwrap();
    }

    #[test]
    fn native_pdfium_renders_second_page_and_rejects_invalid_navigation() {
        let input =
            std::env::temp_dir().join(format!("rw-multipage-pdfium-{}.pdf", uuid::Uuid::new_v4()));
        fixture_pages(
            &input,
            &["First page unrelated text", "Second page PDFium landmark"],
        );
        if let Ok(destination) = std::env::var("RW_PDFIUM_MULTIPAGE_FIXTURE") {
            std::fs::copy(&input, destination).unwrap();
        }
        if runtime_library().is_err() {
            eprintln!("PDFium runtime missing; download with packaging script");
            std::fs::remove_file(input).unwrap();
            return;
        }
        let first = render_search_at(&input, "PDFium", 0).unwrap();
        assert_eq!((first.page_index, first.page_count), (0, 2));
        assert!(first.matches.is_empty());
        let second = render_search_at(&input, "PDFium", 1).unwrap();
        assert_eq!((second.page_index, second.page_count), (1, 2));
        assert!(second
            .extracted_text
            .contains("Second page PDFium landmark"));
        assert!(second.matches.len() <= 1);
        assert_eq!(second.match_count, 1);
        assert!(render_search_at(&input, "PDFium", 2)
            .unwrap_err()
            .contains("valid range 1"));
        std::fs::remove_file(input).unwrap();
    }

    #[test]
    fn find_next_page_wraps_once_and_leaves_missing_queries_absent() {
        let input = std::env::temp_dir().join(format!("rw-find-next-{}.pdf", uuid::Uuid::new_v4()));
        fixture_pages(
            &input,
            &[
                "First page alpha",
                "Second page PDFium landmark",
                "Third page beta",
            ],
        );
        if runtime_library().is_err() {
            eprintln!("PDFium runtime missing; download with packaging script");
            std::fs::remove_file(input).unwrap();
            return;
        }
        assert_eq!(
            find_next_matching_page(&input, "PDFium", 0).unwrap(),
            Some(1)
        );
        assert_eq!(
            find_next_matching_page(&input, "PDFium", 1).unwrap(),
            Some(1)
        );
        assert_eq!(
            find_next_matching_page(&input, "PDFium", 2).unwrap(),
            Some(1)
        );
        assert_eq!(find_next_matching_page(&input, "missing", 0).unwrap(), None);
        assert!(find_next_matching_page(&input, "", 0).is_err());
        assert!(find_next_matching_page(&input, " ", 0).is_err());
        assert!(find_next_matching_page(&input, &"x".repeat(257), 0).is_err());
        assert!(find_next_matching_page(&input, "PDFium", 3).is_err());
        std::fs::remove_file(input).unwrap();
    }

    #[test]
    fn bounded_find_next_pdf_read_rejects_oversize_before_pdfium() {
        let input =
            std::env::temp_dir().join(format!("rw-bounded-find-{}.pdf", uuid::Uuid::new_v4()));
        std::fs::write(&input, b"PDF").unwrap();
        assert_eq!(read_bounded_pdf(&input).unwrap(), b"PDF");
        std::fs::OpenOptions::new()
            .write(true)
            .open(&input)
            .unwrap()
            .set_len(MAX_NATIVE_PDF_BYTES + 1)
            .unwrap();
        assert!(read_bounded_pdf(&input)
            .unwrap_err()
            .contains("bounded native file budget"));
        std::fs::remove_file(input).unwrap();
    }
}
