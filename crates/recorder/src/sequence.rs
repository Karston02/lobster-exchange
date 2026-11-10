//! Detecting dropped or out-of-order messages.
//!
//! Coinbase numbers every message on a connection (`sequence_num`). If a
//! number is skipped, we missed an update and our copy of the book is wrong
//! from that point on.

/// What the latest sequence number says about the stream.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SequenceCheck {
    /// The first message on this connection.
    First,
    /// Exactly one more than the previous message.
    InOrder,
    /// One or more messages were skipped.
    Gap { expected: u64, got: u64 },
    /// A number we've already seen (a duplicate or an older message).
    Stale { last: u64, got: u64 },
}

/// Tracks the sequence numbers of one connection.
#[derive(Debug, Default)]
pub struct SequenceTracker {
    last: Option<u64>,
}

impl SequenceTracker {
    /// Records `got` and reports how it relates to the previous number.
    pub fn observe(&mut self, got: u64) -> SequenceCheck {
        let check = match self.last {
            None => SequenceCheck::First,
            Some(last) if got == last + 1 => SequenceCheck::InOrder,
            Some(last) if got > last + 1 => SequenceCheck::Gap {
                expected: last + 1,
                got,
            },
            Some(last) => SequenceCheck::Stale { last, got },
        };
        // Only move forward: a stale message must not rewind the tracker
        if self.last.is_none_or(|last| got > last) {
            self.last = Some(got);
        }
        check
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn consecutive_numbers_are_in_order() {
        let mut tracker = SequenceTracker::default();
        assert_eq!(tracker.observe(0), SequenceCheck::First);
        assert_eq!(tracker.observe(1), SequenceCheck::InOrder);
        assert_eq!(tracker.observe(2), SequenceCheck::InOrder);
    }

    #[test]
    fn skipped_numbers_are_a_gap() {
        let mut tracker = SequenceTracker::default();
        tracker.observe(5);
        assert_eq!(
            tracker.observe(8),
            SequenceCheck::Gap {
                expected: 6,
                got: 8
            }
        );
        // After a gap, tracking continues from the new number
        assert_eq!(tracker.observe(9), SequenceCheck::InOrder);
    }

    #[test]
    fn repeated_or_older_numbers_are_stale_and_do_not_rewind() {
        let mut tracker = SequenceTracker::default();
        tracker.observe(10);
        assert_eq!(
            tracker.observe(10),
            SequenceCheck::Stale { last: 10, got: 10 }
        );
        assert_eq!(
            tracker.observe(3),
            SequenceCheck::Stale { last: 10, got: 3 }
        );
        assert_eq!(tracker.observe(11), SequenceCheck::InOrder);
    }
}
