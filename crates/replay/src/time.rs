//! Parsing Coinbase's timestamps into nanoseconds since 1970 (Unix time).
//!
//! Coinbase writes times like `2026-11-10T18:47:22.588345Z` (RFC 3339, always
//! UTC, with 0 to 9 fractional digits). Integers sort and subtract exactly,
//! which is what the replayer needs to put trades and book changes in order.

use std::fmt;

/// Why a timestamp couldn't be parsed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TimeError(String);

impl fmt::Display for TimeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "bad timestamp {:?}", self.0)
    }
}

impl std::error::Error for TimeError {}

/// Parses `YYYY-MM-DDTHH:MM:SS[.fraction]Z` into nanoseconds since 1970.
pub fn parse_utc_ns(text: &str) -> Result<u64, TimeError> {
    let error = || TimeError(text.to_string());
    let bytes = text.as_bytes();
    if bytes.len() < 20 || bytes[4] != b'-' || bytes[7] != b'-' || bytes[10] != b'T' {
        return Err(error());
    }
    if bytes[13] != b':' || bytes[16] != b':' || bytes[bytes.len() - 1] != b'Z' {
        return Err(error());
    }

    // Reads a fixed-width run of digits, e.g. the "47" in "18:47:22"
    let number = |range: std::ops::Range<usize>| -> Result<u64, TimeError> {
        let digits = text.get(range).ok_or_else(error)?;
        if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
            return Err(error());
        }
        digits.parse().map_err(|_| error())
    };
    let year = number(0..4)?;
    let month = number(5..7)?;
    let day = number(8..10)?;
    let hour = number(11..13)?;
    let minute = number(14..16)?;
    let second = number(17..19)?;
    if !(1..=12).contains(&month) || !(1..=31).contains(&day) || hour > 23 || minute > 59 {
        return Err(error());
    }
    if second > 60 {
        return Err(error());
    }

    // Optional fraction between the seconds and the 'Z', padded to 9 digits
    let mut nanos = 0;
    let end = bytes.len() - 1;
    if end > 19 {
        if bytes[19] != b'.' || end - 20 > 9 {
            return Err(error());
        }
        let fraction = number(20..end)?;
        nanos = fraction * 10u64.pow(9 - (end - 20) as u32);
    }

    let days = days_from_civil(year as i64, month as i64, day as i64);
    if days < 0 {
        return Err(error());
    }
    let seconds = days as u64 * 86_400 + hour * 3_600 + minute * 60 + second;
    Ok(seconds * 1_000_000_000 + nanos)
}

/// Days since 1970-01-01 for a calendar date (Howard Hinnant's algorithm).
fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let year = if month <= 2 { year - 1 } else { year };
    let era = year.div_euclid(400);
    let year_of_era = year - era * 400;
    let month_index = (month + 9) % 12; // March = 0
    let day_of_year = (153 * month_index + 2) / 5 + day - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    era * 146_097 + day_of_era - 719_468
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unix_epoch_is_zero() {
        assert_eq!(parse_utc_ns("1970-01-01T00:00:00Z"), Ok(0));
    }

    #[test]
    fn parses_coinbase_timestamps() {
        // 2026-11-10T18:47:22Z is 1794336442 seconds after 1970
        assert_eq!(
            parse_utc_ns("2026-11-10T18:47:22.588345Z"),
            Ok(1_794_336_442_588_345_000)
        );
        assert_eq!(
            parse_utc_ns("2026-11-10T18:29:27.923086058Z"),
            Ok(1_794_335_367_923_086_058)
        );
        assert_eq!(
            parse_utc_ns("2026-11-10T18:29:27Z"),
            Ok(1_794_335_367_000_000_000)
        );
    }

    #[test]
    fn handles_leap_days() {
        let feb_28 = parse_utc_ns("2028-02-28T00:00:00Z").unwrap();
        let mar_01 = parse_utc_ns("2028-03-01T00:00:00Z").unwrap();
        assert_eq!(mar_01 - feb_28, 2 * 86_400 * 1_000_000_000);
    }

    #[test]
    fn rejects_malformed_input() {
        for bad in [
            "",
            "2026-11-10 18:47:22Z",
            "2026-11-10T18:47:22",
            "2026-13-10T18:47:22Z",
            "2026-11-10T18:47:22.Z",
            "2026-11-10T18:47:22.1234567890Z",
            "2026-11-10T18:4x:22Z",
        ] {
            assert!(parse_utc_ns(bad).is_err(), "{bad} should be rejected");
        }
    }
}
