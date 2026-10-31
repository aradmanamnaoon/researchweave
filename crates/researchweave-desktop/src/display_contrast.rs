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
                "light", "#f5f4ef", "#ffffff", "#202b37", "#566574", "#3b5b88", "#ffffff",
            ),
            (
                "dark", "#111b26", "#1c2a36", "#f5f7fa", "#c2cfdc", "#98bcd5", "#14202c",
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
            ("light-evidence-violet", "#6957a6", "#ffffff"),
            ("light-discovery-copper", "#9b6042", "#f5f4ef"),
            ("dark-evidence-violet", "#b4a0e4", "#1c2a36"),
            ("dark-discovery-copper", "#e4a880", "#1c2a36"),
        ] {
            let ratio = contrast(foreground, background);
            assert!(ratio >= 4.5, "{name} {ratio:.2}:1 is below 4.5:1");
        }
        for (name, foreground, background) in [
            ("light-rail", "#c7d6e1", "#263245"),
            ("dark-rail", "#c7d6e1", "#172638"),
            ("high-contrast-rail", "#ffffff", "#000000"),
        ] {
            let ratio = contrast(foreground, background);
            assert!(
                ratio >= 4.5,
                "{name} rail contrast {ratio:.2}:1 is below 4.5:1"
            );
        }
    }

    #[test]
    fn audited_colors_match_the_actual_slint_theme() {
        let ui = include_str!("../ui/main.slint");
        for (role, dark, light) in [
            ("canvas", "#111b26", "#f5f4ef"),
            ("surface", "#1c2a36", "#ffffff"),
            ("ink", "#f5f7fa", "#202b37"),
            ("muted-ink", "#c2cfdc", "#566574"),
            ("accent", "#98bcd5", "#3b5b88"),
            ("accent-ink", "#14202c", "#ffffff"),
            ("evidence-violet", "#b4a0e4", "#6957a6"),
            ("discovery-copper", "#e4a880", "#9b6042"),
            ("rail-background", "#172638", "#263245"),
            ("rail-muted", "#c7d6e1", "#c7d6e1"),
        ] {
            let prefix = format!("    in-out property <color> {role}:");
            let declaration = ui
                .lines()
                .find(|line| line.starts_with(&prefix))
                .unwrap_or_else(|| panic!("missing Slint theme role: {role}"));
            assert!(
                declaration.contains(&format!("dark-mode ? {dark} : {light}")),
                "theme role {role} drifted from its audited contrast values"
            );
        }
    }
}
