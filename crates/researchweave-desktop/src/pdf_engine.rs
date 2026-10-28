//! Native, dynamically loaded PDFium render + positioned text proof.
use firecrawl_pdfium::{PageRect, Pdfium, PixelFormat, RenderConfig};
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
    const MAX_PDF_BYTES: u64 = 128 * 1024 * 1024;
    const MAX_SCAN_PAGES: usize = 512;
    const MAX_TOTAL_TEXT_BYTES: usize = 16 * 1024 * 1024;
    let file_len = std::fs::metadata(pdf_path)
        .map_err(|e| e.to_string())?
        .len();
    if file_len > MAX_PDF_BYTES {
        return Err("PDF exceeds the bounded find-next file budget".into());
    }
    let runtime = runtime_library()?;
    let pdfium = Pdfium::load_from_path(runtime).map_err(|e| e.to_string())?;
    let doc = pdfium
        .load_document(std::fs::read(pdf_path).map_err(|e| e.to_string())?, None)
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
    let runtime = runtime_library()?;
    let pdfium = Pdfium::load_from_path(runtime).map_err(|e| e.to_string())?;
    let contents = std::fs::read(pdf_path).map_err(|e| e.to_string())?;
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
    let text = page.text().map_err(|e| e.to_string())?;
    let mut hits = Vec::new();
    let mut match_count = 0_usize;
    let mut previous_byte_end = 0_usize;
    let mut previous_char_end = 0_usize;
    const MAX_PAGE_SEARCH_RECTS: usize = 256;
    if !query.is_empty() {
        for (byte_start, _) in text.text().match_indices(query) {
            match_count = match_count.saturating_add(1);
            if match_count > MAX_PAGE_SEARCH_RECTS {
                continue;
            }
            let byte_end = byte_start + query.len();
            // The match iterator yields non-overlapping UTF-8 ranges, so the
            // unvisited prefix is counted once rather than O(N²) for many hits.
            let start =
                previous_char_end + text.text()[previous_byte_end..byte_start].chars().count();
            let end = start + query.chars().count();
            previous_byte_end = byte_end;
            previous_char_end = end;
            let glyphs = &text.chars()[start.min(text.chars().len())..end.min(text.chars().len())];
            if glyphs.is_empty() {
                continue;
            }
            let mut rect = glyphs[0].loose_bounds;
            for glyph in &glyphs[1..] {
                let b = glyph.loose_bounds;
                rect.left = rect.left.min(b.left);
                rect.bottom = rect.bottom.min(b.bottom);
                rect.right = rect.right.max(b.right);
                rect.top = rect.top.max(b.top);
            }
            hits.push(SearchRect {
                byte_start,
                byte_end,
                page_rect: rect,
                pixel_rect: render.transform().page_rect_to_pixel(rect),
            });
        }
    }
    let (width, height) = (render.width(), render.height());
    let stride = render.stride();
    let bpp = render.format().bytes_per_pixel();
    if bpp != 4 {
        return Err(format!("Expected four-channel render, got {bpp}"));
    }
    let mut rgba = vec![0; width as usize * height as usize * 4];
    for y in 0..height as usize {
        for x in 0..width as usize {
            let src = &render.pixels()[y * stride + x * 4..][..4];
            let out = &mut rgba[(y * width as usize + x) * 4..][..4];
            out.copy_from_slice(src);
        }
    }
    Ok(PdfRender {
        page_index,
        page_count,
        width,
        height,
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
    fn native_pdfium_renders_and_maps_text() {
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
        assert_eq!(rendered.matches.len(), 1);
        assert_eq!(rendered.match_count, 1);
        let without_search = render_search_at(&input, "", 0).unwrap();
        assert_eq!(without_search.match_count, 0);
        assert!(without_search.matches.is_empty());
        let hit = &rendered.matches[0];
        assert!(hit.page_rect.width() > 0.0 && hit.page_rect.height() > 0.0);
        assert!(hit.pixel_rect.width > 0.0 && hit.pixel_rect.height > 0.0);
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
        assert_eq!(second.matches.len(), 1);
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
}
