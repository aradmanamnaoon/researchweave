//! Deterministic Unicode-scalar quote anchors into immutable manuscript text.
//! No cursor-position guesses, fuzzy matching, or automatic relocation.

pub(crate) fn unique_scalar_span(body: &str, quote: &str) -> Result<(usize, usize), String> {
    let quote_length = quote.chars().count();
    if quote.trim().is_empty() || quote_length > 2_048 || quote.chars().any(|ch| ch == '\0') {
        return Err("Choose a nonempty exact quote of at most 2048 Unicode characters".into());
    }
    if body.chars().count() > 1_000_000 {
        return Err("Saved manuscript exceeds bounded review range".into());
    }
    let mut matches = body.match_indices(quote);
    let (start_byte, _) = matches
        .next()
        .ok_or("Quoted text is not present in the latest saved manuscript revision")?;
    if matches.next().is_some() {
        return Err(
            "Quoted text occurs more than once; select a longer unique exact passage".into(),
        );
    }
    let start_scalar = body[..start_byte].chars().count();
    let end_scalar = start_scalar + quote_length;
    Ok((start_scalar, end_scalar))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unicode_scalar_offsets_preserve_multibyte_quote_without_splitting() {
        let source = "English 🫀 Português 汉字 فارسي 🧠 done";
        let (start, end) = unique_scalar_span(source, "汉字 فارسي 🧠").unwrap();
        assert_eq!(
            source
                .chars()
                .skip(start)
                .take(end - start)
                .collect::<String>(),
            "汉字 فارسي 🧠"
        );
        assert_ne!(
            source.find("汉字").unwrap(),
            source[..source.find("汉字").unwrap()].chars().count()
        );
    }

    #[test]
    fn refuses_ambiguous_missing_or_control_quote() {
        assert!(unique_scalar_span("repeat repeat", "repeat")
            .unwrap_err()
            .contains("more than once"));
        assert!(unique_scalar_span("text", "no").is_err());
        assert!(unique_scalar_span("text", "   ").is_err());
        assert!(unique_scalar_span("a\0b", "\0").is_err());
        assert!(unique_scalar_span("a", &"a".repeat(2_049)).is_err());
    }
}
