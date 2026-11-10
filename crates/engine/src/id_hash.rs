//! A fast hasher for maps keyed by order id.
//!
//! Rust's default `HashMap` hasher (SipHash) is designed to resist "hash
//! flooding", where an attacker picks keys that all land in the same bucket.
//! That protection costs time on every lookup. Our keys are plain integer ids
//! from our own replayer and bot, so we trade it for speed with a much simpler
//! multiply-based hash (the same idea as `FxHash`, used inside the Rust compiler).

use std::collections::HashMap;
use std::hash::{BuildHasherDefault, Hasher};

/// A `HashMap` keyed by anything hashable, using [`IdHasher`].
pub(crate) type IdMap<K, V> = HashMap<K, V, BuildHasherDefault<IdHasher>>;

/// Multiply-and-rotate hasher for integer keys. Not resistant to hash flooding.
#[derive(Default)]
pub(crate) struct IdHasher {
    hash: u64,
}

/// An odd constant with well-mixed bits (from `FxHash`). Multiplying by it
/// spreads small, sequential ids across the whole 64-bit range.
const SEED: u64 = 0x51_7c_c1_b7_27_22_0a_95;

impl IdHasher {
    fn add(&mut self, word: u64) {
        self.hash = (self.hash.rotate_left(5) ^ word).wrapping_mul(SEED);
    }
}

impl Hasher for IdHasher {
    // `OrderId(u64)` hashes through this fast path
    fn write_u64(&mut self, n: u64) {
        self.add(n);
    }

    // Fallback for any other key type: mix in one byte at a time
    fn write(&mut self, bytes: &[u8]) {
        for &byte in bytes {
            self.add(u64::from(byte));
        }
    }

    fn finish(&self) -> u64 {
        self.hash
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::OrderId;
    use std::collections::HashSet;
    use std::hash::{BuildHasher, BuildHasherDefault};

    #[test]
    fn sequential_ids_get_distinct_hashes() {
        let build = BuildHasherDefault::<IdHasher>::default();
        let hashes: HashSet<u64> = (0..10_000).map(|id| build.hash_one(OrderId(id))).collect();
        assert_eq!(hashes.len(), 10_000);
    }

    #[test]
    fn works_as_a_map() {
        let mut map: IdMap<OrderId, u64> = IdMap::default();
        for id in 0..1_000 {
            map.insert(OrderId(id), id * 2);
        }
        assert_eq!(map.get(&OrderId(500)), Some(&1_000));
        assert_eq!(map.remove(&OrderId(7)), Some(14));
        assert_eq!(map.len(), 999);
    }
}
