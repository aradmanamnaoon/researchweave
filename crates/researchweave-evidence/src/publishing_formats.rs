//! Deterministic offline manuscript renderers; no network or submission calls.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

fn escape_xml(text: &str) -> String {
    let sanitized: String = text
        .chars()
        .filter(|character| matches!(*character, '\t' | '\n' | '\r') || *character >= '\u{20}')
        .collect();
    sanitized
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn word_runs(text: &str) -> String {
    let mut output = String::new();
    for (index, line) in text.split('\n').enumerate() {
        if index > 0 {
            output.push_str("<w:r><w:br/></w:r>");
        }
        if !line.is_empty() {
            output.push_str(&format!(
                "<w:r><w:t xml:space=\"preserve\">{}</w:t></w:r>",
                escape_xml(line)
            ));
        }
    }
    if output.is_empty() {
        output.push_str("<w:r><w:t xml:space=\"preserve\"></w:t></w:r>");
    }
    output
}

pub(super) fn encode64(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let n = (u32::from(chunk[0]) << 16)
            | (u32::from(*chunk.get(1).unwrap_or(&0)) << 8)
            | u32::from(*chunk.get(2).unwrap_or(&0));
        out.push(ALPHABET[((n >> 18) & 63) as usize] as char);
        out.push(ALPHABET[((n >> 12) & 63) as usize] as char);
        out.push(if chunk.len() > 1 {
            ALPHABET[((n >> 6) & 63) as usize] as char
        } else {
            '='
        });
        out.push(if chunk.len() > 2 {
            ALPHABET[(n & 63) as usize] as char
        } else {
            '='
        });
    }
    out
}

fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = !0u32;
    for byte in bytes {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            crc = (crc >> 1) ^ (if crc & 1 == 1 { 0xedb88320 } else { 0 });
        }
    }
    !crc
}

pub(super) fn zip(files: &[(&str, Vec<u8>)]) -> Result<Vec<u8>, String> {
    let mut output = Vec::new();
    let mut directory = Vec::new();
    for (name, data) in files {
        let offset = u32::try_from(output.len()).map_err(|_| "archive too large")?;
        let len = u32::try_from(data.len()).map_err(|_| "archive too large")?;
        let name_len = u16::try_from(name.len()).map_err(|_| "archive name too long")?;
        let crc = crc32(data);
        output.extend_from_slice(&0x04034b50u32.to_le_bytes());
        output.extend_from_slice(&20u16.to_le_bytes());
        output.extend_from_slice(&0u16.to_le_bytes());
        output.extend_from_slice(&0u16.to_le_bytes());
        output.extend_from_slice(&0u16.to_le_bytes());
        output.extend_from_slice(&0u16.to_le_bytes());
        output.extend_from_slice(&crc.to_le_bytes());
        output.extend_from_slice(&len.to_le_bytes());
        output.extend_from_slice(&len.to_le_bytes());
        output.extend_from_slice(&name_len.to_le_bytes());
        output.extend_from_slice(&0u16.to_le_bytes());
        output.extend_from_slice(name.as_bytes());
        output.extend_from_slice(data);
        directory.extend_from_slice(&0x02014b50u32.to_le_bytes());
        directory.extend_from_slice(&20u16.to_le_bytes());
        directory.extend_from_slice(&20u16.to_le_bytes());
        directory.extend_from_slice(&0u16.to_le_bytes());
        directory.extend_from_slice(&0u16.to_le_bytes());
        directory.extend_from_slice(&0u16.to_le_bytes());
        directory.extend_from_slice(&0u16.to_le_bytes());
        directory.extend_from_slice(&crc.to_le_bytes());
        directory.extend_from_slice(&len.to_le_bytes());
        directory.extend_from_slice(&len.to_le_bytes());
        directory.extend_from_slice(&name_len.to_le_bytes());
        directory.extend_from_slice(&0u16.to_le_bytes());
        directory.extend_from_slice(&0u16.to_le_bytes());
        directory.extend_from_slice(&0u16.to_le_bytes());
        directory.extend_from_slice(&0u16.to_le_bytes());
        directory.extend_from_slice(&0u32.to_le_bytes());
        directory.extend_from_slice(&offset.to_le_bytes());
        directory.extend_from_slice(name.as_bytes());
    }
    let offset = u32::try_from(output.len()).map_err(|_| "archive too large")?;
    let size = u32::try_from(directory.len()).map_err(|_| "archive too large")?;
    let count = u16::try_from(files.len()).map_err(|_| "too many archive entries")?;
    output.extend_from_slice(&directory);
    output.extend_from_slice(&0x06054b50u32.to_le_bytes());
    output.extend_from_slice(&0u16.to_le_bytes());
    output.extend_from_slice(&0u16.to_le_bytes());
    output.extend_from_slice(&count.to_le_bytes());
    output.extend_from_slice(&count.to_le_bytes());
    output.extend_from_slice(&size.to_le_bytes());
    output.extend_from_slice(&offset.to_le_bytes());
    output.extend_from_slice(&0u16.to_le_bytes());
    Ok(output)
}

pub(super) fn docx(sections: &[(String, String)]) -> Result<Vec<u8>, String> {
    if sections.is_empty() {
        return Err("DOCX requires at least one manuscript section".into());
    }
    let mut xml = String::from(
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>"#,
    );
    for (title, body) in sections {
        let style =
            if title.eq_ignore_ascii_case("title") || title.eq_ignore_ascii_case("title page") {
                "Title"
            } else {
                "Heading1"
            };
        xml.push_str(&format!(
            "<w:p><w:pPr><w:pStyle w:val=\"{style}\"/><w:keepNext/></w:pPr>{}</w:p>",
            word_runs(title)
        ));
        for paragraph in body
            .split("\n\n")
            .filter(|paragraph| !paragraph.trim().is_empty())
        {
            xml.push_str(&format!(
                "<w:p><w:pPr><w:pStyle w:val=\"Normal\"/></w:pPr>{}</w:p>",
                word_runs(paragraph)
            ));
        }
    }
    xml.push_str(
        r#"<w:sectPr><w:headerReference w:type="default" r:id="rId3"/><w:footerReference w:type="default" r:id="rId4"/><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr></w:body></w:document>"#,
    );
    let styles = br#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="360" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:spacing w:before="480" w:after="360"/></w:pPr><w:rPr><w:b/><w:sz w:val="40"/><w:szCs w:val="40"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="360" w:after="160"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:after="120"/></w:pPr><w:rPr><w:i/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Header"><w:name w:val="header"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="right"/></w:pPr><w:rPr><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="footer"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr></w:style>
</w:styles>"#.to_vec();
    let settings = br#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:zoom w:percent="100"/><w:proofState w:spelling="clean" w:grammar="clean"/><w:compat/></w:settings>"#.to_vec();
    let header = br#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:pPr><w:pStyle w:val="Header"/></w:pPr><w:r><w:t>ResearchWeave manuscript</w:t></w:r></w:p></w:hdr>"#.to_vec();
    let footer = br#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:pPr><w:pStyle w:val="Footer"/><w:jc w:val="center"/></w:pPr><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>"#.to_vec();
    zip(&[
        ("[Content_Types].xml", br#"<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/><Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/><Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>"#.to_vec()),
        ("_rels/.rels", br#"<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>"#.to_vec()),
        ("docProps/core.xml", br#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>ResearchWeave manuscript export</dc:title><dc:creator>ResearchWeave</dc:creator><cp:lastModifiedBy>ResearchWeave</cp:lastModifiedBy><cp:revision>1</cp:revision></cp:coreProperties>"#.to_vec()),
        ("docProps/app.xml", br#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>ResearchWeave</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop></Properties>"#.to_vec()),
        ("word/_rels/document.xml.rels", br#"<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/><Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/></Relationships>"#.to_vec()),
        ("word/document.xml", xml.into_bytes()),
        ("word/styles.xml", styles),
        ("word/settings.xml", settings),
        ("word/header1.xml", header),
        ("word/footer1.xml", footer),
    ])
}

fn pdf(sections: &[(String, String)]) -> Result<Vec<u8>, String> {
    // Minimal valid PDF with standard Helvetica/WinAnsi. Unsupported Unicode is
    // rendered as '?' rather than silently encoded into invalid PDF text.
    let mut lines = Vec::new();
    for (title, body) in sections {
        lines.push(title.as_str());
        lines.extend(body.lines());
    }
    if lines.len() > 45 {
        return Err("PDF exceeds single-page renderer; use DOCX or HTML".into());
    }
    let mut stream = String::from("BT /F1 11 Tf 50 790 Td 14 TL\n");
    for line in lines {
        let safe = line
            .chars()
            .map(|c| {
                if c.is_ascii_graphic() || c == ' ' {
                    c
                } else {
                    '?'
                }
            })
            .collect::<String>()
            .replace('\\', "\\\\")
            .replace('(', "\\(")
            .replace(')', "\\)");
        if safe.len() > 110 {
            return Err("PDF line too long; use DOCX or HTML".into());
        }
        stream.push_str(&format!("({safe}) Tj T*\n"));
    }
    stream.push_str("ET\n");
    let objects = [
        "<< /Type /Catalog /Pages 2 0 R >>".to_string(),
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>".to_string(),
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>".to_string(),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>".to_string(),
        format!("<< /Length {} >>\nstream\n{}endstream", stream.len(), stream),
    ];
    let mut out = b"%PDF-1.4\n".to_vec();
    let mut offsets = vec![0usize];
    for (i, object) in objects.iter().enumerate() {
        offsets.push(out.len());
        out.extend_from_slice(format!("{} 0 obj\n{}\nendobj\n", i + 1, object).as_bytes());
    }
    let xref = out.len();
    out.extend_from_slice(b"xref\n0 6\n0000000000 65535 f \n");
    for offset in offsets.iter().skip(1) {
        out.extend_from_slice(format!("{offset:010} 00000 n \n").as_bytes());
    }
    out.extend_from_slice(
        format!("trailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n{xref}\n%%EOF\n").as_bytes(),
    );
    Ok(out)
}

pub(super) fn export(
    format: &str,
    sections: &[(String, String)],
    markdown: &str,
) -> Result<Value, String> {
    let (bytes, mime, fidelity) = match format {
        "markdown" => (
            markdown.as_bytes().to_vec(),
            "text/markdown",
            "native_markdown",
        ),
        "html" => {
            let mut html = String::from(
                "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"></head><body>\n",
            );
            for (title, body) in sections {
                html.push_str(&format!("<h1>{}</h1>\n", escape_xml(title)));
                for paragraph in body.split("\n\n").filter(|part| !part.trim().is_empty()) {
                    html.push_str(&format!("<p>{}</p>\n", escape_xml(paragraph)));
                }
            }
            html.push_str("</body></html>\n");
            (
                html.into_bytes(),
                "text/html",
                "plain_text_structure_preserved_markup_not_interpreted",
            )
        }
        "docx" => (
            docx(sections)?,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "semantic_heading_styles_page_layout_header_footer_page_numbers_unicode_paragraph_structure_preserved_citation_tokens_literal",
        ),
        "pdf" => (
            pdf(sections)?,
            "application/pdf",
            "basic_single_page_ascii_pdf_limited_fidelity",
        ),
        _ => return Err("unsupported manuscript export format".into()),
    };
    if bytes.len() > 16 * 1024 * 1024 {
        return Err("export exceeds size limit".into());
    }
    let structural_features = match format {
        "docx" => json!([
            "semantic_heading_styles",
            "paragraph_boundaries",
            "single_line_breaks",
            "a4_page_layout",
            "header",
            "page_number_footer",
            "unicode_utf8",
            "core_document_properties"
        ]),
        "html" => json!(["section_headings", "paragraph_boundaries", "unicode_utf8"]),
        "markdown" => json!(["section_headings", "plain_text"]),
        "pdf" => json!(["single_page", "ascii_text"]),
        _ => json!([]),
    };
    Ok(
        json!({"format":format,"mime_type":mime,"byte_length":bytes.len(),
        "sha256":hex::encode(Sha256::digest(&bytes)),"base64":encode64(&bytes),
        "fidelity":fidelity,"editable":format!="pdf","structural_features":structural_features,
        "submission_performed":false,"scientific_claims_verified":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    fn stored_zip_entries(bytes: &[u8]) -> BTreeMap<String, Vec<u8>> {
        let mut entries = BTreeMap::new();
        let mut cursor = 0usize;
        while cursor + 30 <= bytes.len() {
            let signature = u32::from_le_bytes(bytes[cursor..cursor + 4].try_into().unwrap());
            if signature != 0x04034b50 {
                break;
            }
            let method = u16::from_le_bytes(bytes[cursor + 8..cursor + 10].try_into().unwrap());
            assert_eq!(method, 0, "test parser supports stored ZIP entries only");
            let size =
                u32::from_le_bytes(bytes[cursor + 18..cursor + 22].try_into().unwrap()) as usize;
            let name_len =
                u16::from_le_bytes(bytes[cursor + 26..cursor + 28].try_into().unwrap()) as usize;
            let extra_len =
                u16::from_le_bytes(bytes[cursor + 28..cursor + 30].try_into().unwrap()) as usize;
            let name_start = cursor + 30;
            let name_end = name_start + name_len;
            let data_start = name_end + extra_len;
            let data_end = data_start + size;
            assert!(data_end <= bytes.len());
            let name = String::from_utf8(bytes[name_start..name_end].to_vec()).unwrap();
            entries.insert(name, bytes[data_start..data_end].to_vec());
            cursor = data_end;
        }
        entries
    }

    #[test]
    fn all_formats_are_deterministic_valid_containers_and_receipted() {
        let sections = vec![("Results".into(), "A & B < C".into())];
        for format in ["markdown", "html", "docx", "pdf"] {
            let first = export(format, &sections, "## Results\n\nA & B < C\n").unwrap();
            let second = export(format, &sections, "## Results\n\nA & B < C\n").unwrap();
            assert_eq!(first, second);
            assert_eq!(first["submission_performed"], false);
            let encoded = first["base64"].as_str().unwrap();
            assert!(!encoded.is_empty());
            assert_eq!(first["sha256"].as_str().unwrap().len(), 64);
            match format {
                "html" => {
                    let html = String::from_utf8({
                        let mut text = String::new();
                        for (title, body) in &sections {
                            text.push_str(&escape_xml(title));
                            text.push_str(&escape_xml(body));
                        }
                        text.into_bytes()
                    })
                    .unwrap();
                    assert!(html.contains("&amp;"));
                    assert!(html.contains("&lt;"));
                }
                "docx" => {
                    let file = docx(&sections).unwrap();
                    assert!(file.starts_with(b"PK\x03\x04"));
                    assert!(file.windows(4).any(|part| part == b"PK\x05\x06"));
                    let entries = stored_zip_entries(&file);
                    for required in [
                        "[Content_Types].xml",
                        "_rels/.rels",
                        "docProps/core.xml",
                        "docProps/app.xml",
                        "word/document.xml",
                        "word/_rels/document.xml.rels",
                        "word/styles.xml",
                        "word/settings.xml",
                        "word/header1.xml",
                        "word/footer1.xml",
                    ] {
                        assert!(entries.contains_key(required), "missing {required}");
                    }
                }
                "pdf" => {
                    let file = pdf(&sections).unwrap();
                    assert!(file.starts_with(b"%PDF-1.4"));
                    assert!(file.ends_with(b"%%EOF\n"));
                    assert!(file.windows(5).any(|part| part == b"xref\n"));
                }
                _ => {}
            }
        }
        assert!(export("latex", &sections, "").is_err());
        assert!(pdf(&[("Long".into(), "x".repeat(111))]).is_err());
    }

    #[test]
    fn docx_preserves_unicode_relationships_styles_page_numbers_and_long_documents() {
        let sections = vec![
            (
                "Title".into(),
                "A structured manuscript\nwith a deliberate line break.".into(),
            ),
            (
                "نتایج".into(),
                "پژوهش فارسی & evidence < verified\n\nSecond paragraph.".into(),
            ),
        ];
        let file = docx(&sections).unwrap();
        let entries = stored_zip_entries(&file);
        let document = String::from_utf8(entries["word/document.xml"].clone()).unwrap();
        assert!(document.contains("w:pStyle w:val=\"Title\""));
        assert!(document.contains("w:pStyle w:val=\"Heading1\""));
        assert!(document.contains("<w:r><w:br/></w:r>"));
        assert!(document.contains("نتایج"));
        assert!(document.contains("پژوهش فارسی &amp; evidence &lt; verified"));
        assert!(document.contains("w:headerReference"));
        assert!(document.contains("w:footerReference"));
        assert!(document.contains("w:pgSz w:w=\"11906\" w:h=\"16838\""));

        let styles = String::from_utf8(entries["word/styles.xml"].clone()).unwrap();
        for style in ["Normal", "Title", "Heading1", "Caption", "Header", "Footer"] {
            assert!(styles.contains(&format!("w:styleId=\"{style}\"")));
        }
        let relationships =
            String::from_utf8(entries["word/_rels/document.xml.rels"].clone()).unwrap();
        for target in ["styles.xml", "settings.xml", "header1.xml", "footer1.xml"] {
            assert!(relationships.contains(&format!("Target=\"{target}\"")));
        }
        let footer = String::from_utf8(entries["word/footer1.xml"].clone()).unwrap();
        assert!(footer.contains(" PAGE "));

        let long_body = (0..400)
            .map(|index| format!("Paragraph {index} with deterministic content."))
            .collect::<Vec<_>>()
            .join("\n\n");
        let long = docx(&[("Methods".into(), long_body)]).unwrap();
        assert!(long.len() > file.len());
        assert!(docx(&[]).is_err());

        let sanitized = docx(&[("Results".into(), "before\u{0}after".into())]).unwrap();
        let sanitized_entries = stored_zip_entries(&sanitized);
        let sanitized_document =
            String::from_utf8(sanitized_entries["word/document.xml"].clone()).unwrap();
        assert!(sanitized_document.contains("beforeafter"));
        assert!(!sanitized_document.contains('\0'));
    }
}
