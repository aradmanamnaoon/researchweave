//! WCAG 2.x text-role audit of the Slint Theme tokens (not visual certification).

fn luminance(hex: &str) -> f64 {
    assert_eq!(hex.len(), 7);
    assert!(hex.starts_with('#'));
    let channel = |start| {
        let v = u8::from_str_radix(&hex[start..start + 2], 16).unwrap() as f64 / 255.0;
        if v <= 0.04045 {
            v / 12.92
        } else {
            ((v + 0.055) / 1.055).powf(2.4)
        }
    };
    0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)
}

fn contrast(a: &str, b: &str) -> f64 {
    let a = luminance(a);
    let b = luminance(b);
    (a.max(b) + 0.05) / (a.min(b) + 0.05)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wcag_reference_and_theme_roles() {
        assert!((contrast("#000000", "#ffffff") - 21.0).abs() < 1e-9);
        assert!((contrast("#ffffff", "#ffffff") - 1.0).abs() < 1e-9);
        // Canvas, surface, body, muted, accent, primary-on-accent.
        for (name, canvas, surface, body, muted, accent, primary) in [
            (
                "light", "#f6f5f1", "#ffffff", "#172438", "#5b677a", "#147a75", "#ffffff",
            ),
            (
                "dark", "#101923", "#172438", "#f4f6f8", "#b9c5d3", "#55c7bd", "#101923",
            ),
            (
                "contrast", "#000000", "#111111", "#ffffff", "#ffffff", "#ffff00", "#000000",
            ),
        ] {
            for (role, foreground, background) in [
                ("body-canvas", body, canvas),
                ("body-surface", body, surface),
                ("muted-canvas", muted, canvas),
                ("muted-surface", muted, surface),
                ("primary-accent", primary, accent),
                ("accent-surface", accent, surface),
            ] {
                let ratio = contrast(foreground, background);
                assert!(ratio >= 4.5, "{name}/{role} {ratio:.2}:1 is below 4.5:1");
            }
        }
        for (name, foreground, background) in [
            ("light-evidence-violet", "#7564b5", "#ffffff"),
            ("light-discovery-copper", "#9a5b3a", "#f6f5f1"),
            ("dark-evidence-violet", "#a997e8", "#172438"),
            ("dark-discovery-copper", "#e0a17b", "#172438"),
        ] {
            let ratio = contrast(foreground, background);
            assert!(ratio >= 4.5, "{name} {ratio:.2}:1 is below 4.5:1");
        }
    }
}
