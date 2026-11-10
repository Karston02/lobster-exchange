//! Turning decimal strings like `"73232.08"` into exact integers.
//!
//! Coinbase sends prices and sizes as strings. Parsing them as floats would
//! bring back the rounding errors that integer ticks exist to avoid, so we
//! parse the digits ourselves.

use std::fmt;

/// Why a decimal string couldn't be converted.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DecimalError {
    /// The string was empty, or had no digits.
    Empty,
    /// The string contained something other than digits and one `.`.
    InvalidCharacter(char),
    /// More than one `.`.
    MultipleDots,
    /// Non-zero digits beyond the allowed number of decimal places.
    TooPrecise,
    /// The number is too big for a `u64`.
    Overflow,
}

impl fmt::Display for DecimalError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            DecimalError::Empty => write!(f, "empty number"),
            DecimalError::InvalidCharacter(c) => write!(f, "invalid character {c:?}"),
            DecimalError::MultipleDots => write!(f, "more than one decimal point"),
            DecimalError::TooPrecise => write!(f, "more decimal places than allowed"),
            DecimalError::Overflow => write!(f, "number too large"),
        }
    }
}

impl std::error::Error for DecimalError {}

/// Parses `text` as a count of units with `decimals` places.
///
/// For example, with 2 decimal places (cents), `"73232.08"` becomes `7323208`,
/// and `"5"` becomes `500`. Trailing zeros past the precision are fine
/// (`"1.50"` with 1 place is `15`), but other extra digits are an error.
pub fn parse_fixed(text: &str, decimals: u32) -> Result<u64, DecimalError> {
    let mut value: u64 = 0;
    let mut seen_dot = false;
    let mut fraction_digits = 0;
    let mut any_digit = false;

    for c in text.chars() {
        match c {
            '.' if seen_dot => return Err(DecimalError::MultipleDots),
            '.' => seen_dot = true,
            '0'..='9' => {
                any_digit = true;
                let digit = u64::from(c as u8 - b'0');
                if seen_dot && fraction_digits == decimals {
                    // Past our precision: only zeros are allowed here
                    if digit != 0 {
                        return Err(DecimalError::TooPrecise);
                    }
                    continue;
                }
                if seen_dot {
                    fraction_digits += 1;
                }
                value = value
                    .checked_mul(10)
                    .and_then(|v| v.checked_add(digit))
                    .ok_or(DecimalError::Overflow)?;
            }
            other => return Err(DecimalError::InvalidCharacter(other)),
        }
    }

    if !any_digit {
        return Err(DecimalError::Empty);
    }

    // Pad missing decimal places: "73232.1" with 2 places is 7323210
    for _ in fraction_digits..decimals {
        value = value.checked_mul(10).ok_or(DecimalError::Overflow)?;
    }
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_prices_into_cents() {
        assert_eq!(parse_fixed("73232.08", 2), Ok(7_323_208));
        assert_eq!(parse_fixed("0.01", 2), Ok(1));
        assert_eq!(parse_fixed("5", 2), Ok(500));
        assert_eq!(parse_fixed("73232.1", 2), Ok(7_323_210));
        assert_eq!(parse_fixed("7.", 2), Ok(700));
        assert_eq!(parse_fixed(".5", 2), Ok(50));
    }

    #[test]
    fn parses_quantities_into_satoshis() {
        assert_eq!(parse_fixed("0.3404195", 8), Ok(34_041_950));
        assert_eq!(parse_fixed("0.00000001", 8), Ok(1));
        assert_eq!(parse_fixed("11282.6", 8), Ok(1_128_260_000_000));
        assert_eq!(parse_fixed("0", 8), Ok(0));
    }

    #[test]
    fn trailing_zeros_past_precision_are_allowed() {
        assert_eq!(parse_fixed("1.500", 1), Ok(15));
    }

    #[test]
    fn rejects_bad_input() {
        assert_eq!(parse_fixed("", 2), Err(DecimalError::Empty));
        assert_eq!(parse_fixed(".", 2), Err(DecimalError::Empty));
        assert_eq!(parse_fixed("1.2.3", 2), Err(DecimalError::MultipleDots));
        assert_eq!(
            parse_fixed("-1", 2),
            Err(DecimalError::InvalidCharacter('-'))
        );
        assert_eq!(
            parse_fixed("1e5", 2),
            Err(DecimalError::InvalidCharacter('e'))
        );
        assert_eq!(parse_fixed("1.005", 2), Err(DecimalError::TooPrecise));
        assert_eq!(
            parse_fixed("99999999999999999999", 0),
            Err(DecimalError::Overflow)
        );
    }

    #[test]
    fn largest_real_price_fits() {
        // The highest ask seen in the first recording
        assert_eq!(parse_fixed("138991023.41", 2), Ok(13_899_102_341));
    }
}
