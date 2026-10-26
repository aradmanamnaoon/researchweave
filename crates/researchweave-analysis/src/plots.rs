//! Bounded, deterministic SVG scatter and line plots.
use super::{AnalysisError, Dataset};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

fn set_pixel(pixels: &mut [u8], width: u32, height: u32, x: i32, y: i32, color: [u8; 3]) {
    if x < 0 || y < 0 || x >= width as i32 || y >= height as i32 {
        return;
    }
    let offset = (y as usize * width as usize + x as usize) * 3;
    pixels[offset..offset + 3].copy_from_slice(&color);
}

fn draw_line(
    pixels: &mut [u8],
    width: u32,
    height: u32,
    start: (i32, i32),
    end: (i32, i32),
    color: [u8; 3],
) {
    let (mut x0, mut y0) = start;
    let (x1, y1) = end;
    let dx = (x1 - x0).abs();
    let sx = if x0 < x1 { 1 } else { -1 };
    let dy = -(y1 - y0).abs();
    let sy = if y0 < y1 { 1 } else { -1 };
    let mut error = dx + dy;
    loop {
        set_pixel(pixels, width, height, x0, y0, color);
        if x0 == x1 && y0 == y1 {
            break;
        }
        let twice = 2 * error;
        if twice >= dy {
            error += dy;
            x0 += sx;
        }
        if twice <= dx {
            error += dx;
            y0 += sy;
        }
    }
}

fn draw_disc(
    pixels: &mut [u8],
    width: u32,
    height: u32,
    center: (i32, i32),
    radius: i32,
    color: [u8; 3],
) {
    for dy in -radius..=radius {
        for dx in -radius..=radius {
            if dx * dx + dy * dy <= radius * radius {
                set_pixel(pixels, width, height, center.0 + dx, center.1 + dy, color);
            }
        }
    }
}

fn encode_png(
    width: u32,
    height: u32,
    kind: &str,
    coordinates: &[(f64, f64)],
    axes: (f64, f64, f64, f64),
) -> Result<Vec<u8>, AnalysisError> {
    let bytes = width as usize * height as usize * 3;
    if bytes > 8 * 1024 * 1024 {
        return Err(AnalysisError::ResourceLimit(
            "PNG raster exceeds 8 MiB before compression".into(),
        ));
    }
    let mut pixels = vec![255_u8; bytes];
    let dark = [51, 51, 51];
    let blue = [35, 95, 156];
    let (x0, x1, y0, y1) = axes;
    draw_line(
        &mut pixels,
        width,
        height,
        (x0.round() as i32, y0.round() as i32),
        (x0.round() as i32, y1.round() as i32),
        dark,
    );
    draw_line(
        &mut pixels,
        width,
        height,
        (x0.round() as i32, y1.round() as i32),
        (x1.round() as i32, y1.round() as i32),
        dark,
    );
    if kind == "line" {
        for pair in coordinates.windows(2) {
            draw_line(
                &mut pixels,
                width,
                height,
                (pair[0].0.round() as i32, pair[0].1.round() as i32),
                (pair[1].0.round() as i32, pair[1].1.round() as i32),
                blue,
            );
        }
    } else {
        for &(x, y) in coordinates {
            draw_disc(
                &mut pixels,
                width,
                height,
                (x.round() as i32, y.round() as i32),
                3,
                blue,
            );
        }
    }
    let mut encoded = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut encoded, width, height);
        encoder.set_color(png::ColorType::Rgb);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder
            .write_header()
            .map_err(|_| AnalysisError::Integrity("PNG header encoding failed".into()))?;
        writer
            .write_image_data(&pixels)
            .map_err(|_| AnalysisError::Integrity("PNG image encoding failed".into()))?;
    }
    Ok(encoded)
}

fn escape_xml(value: &str) -> String {
    value
        .chars()
        .map(|ch| match ch {
            '&' => "&amp;".to_owned(),
            '<' => "&lt;".to_owned(),
            '>' => "&gt;".to_owned(),
            '"' => "&quot;".to_owned(),
            '\'' => "&apos;".to_owned(),
            ch if ch.is_control() => " ".to_owned(),
            ch => ch.to_string(),
        })
        .collect()
}

pub fn render(dataset: &Dataset, args: &Map<String, Value>) -> Result<Value, AnalysisError> {
    const KEYS: &[&str] = &[
        "dataset_id",
        "revision",
        "kind",
        "format",
        "x",
        "y",
        "width",
        "height",
    ];
    if args.keys().any(|key| !KEYS.contains(&key.as_str())) {
        return Err(AnalysisError::InvalidInput(
            "unsupported plot argument".into(),
        ));
    }
    let kind = args
        .get("kind")
        .and_then(Value::as_str)
        .unwrap_or("scatter");
    if !matches!(kind, "scatter" | "line") {
        return Err(AnalysisError::InvalidInput("unsupported plot kind".into()));
    }
    let format = args.get("format").and_then(Value::as_str).unwrap_or("svg");
    if !matches!(format, "svg" | "png") {
        return Err(AnalysisError::InvalidInput(
            "unsupported plot format".into(),
        ));
    }
    let x = args
        .get("x")
        .and_then(Value::as_str)
        .ok_or_else(|| AnalysisError::InvalidInput("x".into()))?;
    let y = args
        .get("y")
        .and_then(Value::as_str)
        .ok_or_else(|| AnalysisError::InvalidInput("y".into()))?;
    if x == y || !dataset.columns.iter().any(|c| c == x) || !dataset.columns.iter().any(|c| c == y)
    {
        return Err(AnalysisError::InvalidInput(
            "unknown or repeated plot columns".into(),
        ));
    }
    let dimension = |name: &str, default: u64| -> Result<u64, AnalysisError> {
        let value = match args.get(name) {
            None => default,
            Some(v) => v
                .as_u64()
                .ok_or_else(|| AnalysisError::InvalidInput(name.into()))?,
        };
        if !(240..=1600).contains(&value) {
            return Err(AnalysisError::InvalidInput(format!(
                "{name} outside plot bounds"
            )));
        }
        Ok(value)
    };
    let width = dimension("width", 720)?;
    let height = dimension("height", 480)?;
    let mut points: Vec<(f64, f64)> = Vec::new();
    let mut excluded = 0usize;
    for row in &dataset.records {
        let (Some(vx), Some(vy)) = (row.get(x), row.get(y)) else {
            excluded += 1;
            continue;
        };
        if vx.is_null() || vy.is_null() {
            excluded += 1;
            continue;
        }
        let parse = |value: &Value| -> Result<f64, AnalysisError> {
            let number = if let Some(n) = value.as_f64() {
                n
            } else if let Some(s) = value.as_str() {
                s.parse::<f64>().map_err(|_| {
                    AnalysisError::InvalidInput("non-numeric plot coordinate".into())
                })?
            } else {
                return Err(AnalysisError::InvalidInput(
                    "non-numeric plot coordinate".into(),
                ));
            };
            if !number.is_finite() {
                return Err(AnalysisError::InvalidInput(
                    "non-finite plot coordinate".into(),
                ));
            }
            Ok(number)
        };
        points.push((parse(vx)?, parse(vy)?));
        if points.len() > 5000 {
            return Err(AnalysisError::ResourceLimit(
                "plot exceeds 5000 points".into(),
            ));
        }
    }
    if points.len() < 2 {
        return Err(AnalysisError::InvalidInput(
            "plot requires at least two complete points".into(),
        ));
    }
    if kind == "line" && points.windows(2).any(|p| p[1].0 <= p[0].0) {
        return Err(AnalysisError::InvalidInput(
            "line x values must strictly ascend".into(),
        ));
    }
    let min_x = points.iter().map(|p| p.0).fold(f64::INFINITY, f64::min);
    let max_x = points.iter().map(|p| p.0).fold(f64::NEG_INFINITY, f64::max);
    let min_y = points.iter().map(|p| p.1).fold(f64::INFINITY, f64::min);
    let max_y = points.iter().map(|p| p.1).fold(f64::NEG_INFINITY, f64::max);
    if min_x == max_x
        || min_y == max_y
        || !((max_x - min_x).is_finite() && (max_y - min_y).is_finite())
    {
        return Err(AnalysisError::InvalidInput(
            "plot axes must have finite nonzero range".into(),
        ));
    }
    let x0 = 64.0;
    let x1 = width as f64 - 24.0;
    let y0 = 24.0;
    let y1 = height as f64 - 56.0;
    let coordinates: Vec<(f64, f64)> = points
        .iter()
        .map(|(a, b)| {
            (
                x0 + (a - min_x) / (max_x - min_x) * (x1 - x0),
                y1 - (b - min_y) / (max_y - min_y) * (y1 - y0),
            )
        })
        .collect();
    if coordinates
        .iter()
        .any(|(a, b)| !a.is_finite() || !b.is_finite())
    {
        return Err(AnalysisError::InvalidInput(
            "plot coordinate overflow".into(),
        ));
    }
    let label_x = escape_xml(x);
    let label_y = escape_xml(y);
    let title = format!("{label_y} versus {label_x}");
    let alt = format!("{kind} plot of {y} versus {x}; {} complete points, {excluded} excluded; x range [{min_x}, {max_x}], y range [{min_y}, {max_y}].", points.len());
    let rows: Vec<Value> = points.iter().map(|(a, b)| json!({"x":a,"y":b})).collect();
    if format == "png" {
        let png = encode_png(
            width as u32,
            height as u32,
            kind,
            &coordinates,
            (x0, x1, y0, y1),
        )?;
        let digest = hex::encode(Sha256::digest(&png));
        return Ok(json!({
            "format":"png","mime_type":"image/png","kind":kind,
            "png_base64":STANDARD.encode(&png),"png_sha256":digest,"png_bytes":png.len(),
            "alt_text":alt,
            "data_table":{"columns":[{"key":"x","source":x},{"key":"y","source":y}],"rows":rows},
            "n_complete":points.len(),"n_excluded":excluded,
            "dataset_id":dataset.dataset_id,"dataset_revision":dataset.revision,
            "source_hash":dataset.source_hash,"width":width,"height":height,
            "axes":{"x":[min_x,max_x],"y":[min_y,max_y]},
            "visual_text_embedded":false
        }));
    }
    let mut svg = format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\" role=\"img\" aria-label=\"{}\"><title>{title}</title><rect width=\"100%\" height=\"100%\" fill=\"white\"/><path d=\"M{x0:.3} {y0:.3} V{y1:.3} H{x1:.3}\" stroke=\"#333\" fill=\"none\"/><text x=\"{}\" y=\"{}\" font-size=\"14\" text-anchor=\"middle\">{label_x}</text><text x=\"16\" y=\"{}\" font-size=\"14\">{label_y}</text>",
        escape_xml(&alt), width/2, height-12, height/2
    );
    if kind == "line" {
        let mut path = String::new();
        for (i, (px, py)) in coordinates.iter().enumerate() {
            path.push_str(&format!(
                "{}{px:.3},{py:.3}",
                if i == 0 { "M" } else { " L" }
            ));
        }
        svg.push_str(&format!(
            "<path d=\"{path}\" fill=\"none\" stroke=\"#235f9c\" stroke-width=\"2\"/>"
        ));
    } else {
        for (px, py) in &coordinates {
            svg.push_str(&format!(
                "<circle cx=\"{px:.3}\" cy=\"{py:.3}\" r=\"3\" fill=\"#235f9c\"/>"
            ));
        }
    }
    svg.push_str("</svg>");
    Ok(json!({
        "format":"svg","kind":kind,"svg":svg,"alt_text":alt,
        "data_table":{"columns":[{"key":"x","source":x},{"key":"y","source":y}],"rows":rows},
        "n_complete":points.len(),"n_excluded":excluded,
        "dataset_id":dataset.dataset_id,"dataset_revision":dataset.revision,
        "source_hash":dataset.source_hash,"width":width,"height":height,
        "axes":{"x":[min_x,max_x],"y":[min_y,max_y]}
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::AnalysisService;
    use researchweave_core::{DispatchContext, OperationHandler};
    use std::fs;

    #[test]
    fn svg_table_escape_unicode_revision_restart_and_fail_closed() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        fs::write(imports.join("study.csv"), "x,نام<&\"'\n1,2\n2,3\n3,4\n,5\n").unwrap();
        let db = root.path().join("db");
        let ctx = DispatchContext {
            request_id: uuid::Uuid::new_v4(),
            project_id: uuid::Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        let service = AnalysisService::new(&db, &imports).unwrap();
        let imported = service.execute("dataset.import", &json!({"filename":"study.csv"}), &ctx);
        let args = json!({"dataset_id":imported["data"]["dataset_id"],
            "revision":imported["data"]["revision"],"kind":"scatter",
            "x":"x","y":"نام<&\"'","width":480,"height":320});
        let first = service.execute("plot.render", &args, &ctx);
        assert!(first.get("status").is_none(), "{first}");
        let second =
            AnalysisService::new(&db, &imports)
                .unwrap()
                .execute("plot.render", &args, &ctx);
        assert_eq!(first, second);
        let data = &first["data"];
        assert_eq!(data["n_complete"], 3);
        assert_eq!(data["n_excluded"], 1);
        assert_eq!(data["data_table"]["rows"][0], json!({"x":1.0,"y":2.0}));
        assert_eq!(data["dataset_revision"], imported["data"]["revision"]);
        let svg = data["svg"].as_str().unwrap();
        assert!(svg.contains("نام&lt;&amp;&quot;&apos;"));
        assert!(!svg.contains("study.csv"));
        assert!(!svg.contains(root.path().to_str().unwrap()));
        assert!(data["alt_text"]
            .as_str()
            .unwrap()
            .contains("3 complete points"));
        let invalid = json!({"dataset_id":imported["data"]["dataset_id"],
            "revision":imported["data"]["revision"],"kind":"scatter",
            "x":"x","y":"نام<&\"'","width":100});
        assert_eq!(
            service.execute("plot.render", &invalid, &ctx)["status"],
            "failed"
        );
        let unsupported = json!({"dataset_id":imported["data"]["dataset_id"],
            "revision":imported["data"]["revision"],"kind":"histogram","x":"x","y":"نام<&\"'"});
        assert_eq!(
            service.execute("plot.render", &unsupported, &ctx)["status"],
            "failed"
        );
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|c| c.operation == "plot.render"));

        let png_args = json!({"dataset_id":imported["data"]["dataset_id"],
            "revision":imported["data"]["revision"],"kind":"scatter","format":"png",
            "x":"x","y":"نام<&\"'","width":480,"height":320});
        let png_first = service.execute("plot.render", &png_args, &ctx);
        assert!(png_first.get("status").is_none(), "{png_first}");
        let png_second =
            AnalysisService::new(&db, &imports)
                .unwrap()
                .execute("plot.render", &png_args, &ctx);
        assert_eq!(png_first, png_second);
        let encoded = png_first["data"]["png_base64"].as_str().unwrap();
        let bytes = STANDARD.decode(encoded).unwrap();
        assert_eq!(&bytes[..8], b"\x89PNG\r\n\x1a\n");
        assert_eq!(u32::from_be_bytes(bytes[16..20].try_into().unwrap()), 480);
        assert_eq!(u32::from_be_bytes(bytes[20..24].try_into().unwrap()), 320);
        assert_eq!(png_first["data"]["mime_type"], "image/png");
        assert_eq!(
            png_first["data"]["data_table"]["rows"]
                .as_array()
                .unwrap()
                .len(),
            3
        );
        assert!(png_first["data"]["png_sha256"].as_str().unwrap().len() == 64);
        assert!(!encoded.contains(root.path().to_str().unwrap()));
    }
}
