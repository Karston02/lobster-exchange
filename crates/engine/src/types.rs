//! Core types used throughout the engine.

/// Which side of the book an order is on.
///
/// An `enum` is a type that can be exactly one of a fixed set of variants.
/// An order is either a Buy or a Sell, never both and never anything else,
/// and the compiler enforces that.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Side {
    /// A buyer. Buy orders rest on the **bid** side of the book.
    Buy,
    /// A seller. Sell orders rest on the **ask** side of the book.
    Sell,
}

impl Side {
    /// Returns the other side. A buy order matches against sells, and vice versa.
    pub fn opposite(self) -> Side {
        match self {
            Side::Buy => Side::Sell,
            Side::Sell => Side::Buy,
        }
    }
}

/// A price, in integer ticks (e.g. cents). Never a float; see ARCHITECTURE.md #1.
///
/// This is a "newtype": a struct wrapping a single `u64`. It costs nothing at
/// runtime, but the compiler now treats `Price` and `Quantity` as different
/// types, so you can't accidentally pass a quantity where a price belongs.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Price(pub u64);

/// A quantity, in integer lots (the smallest tradable amount).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Quantity(pub u64);

/// A unique identifier for an order.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct OrderId(pub u64);

/// A limit order: "I want to buy/sell this much, at this price or better."
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Order {
    pub id: OrderId,
    pub side: Side,
    pub price: Price,
    /// How much is still unfilled. Shrinks as the order gets partially filled.
    pub quantity: Quantity,
}

impl Order {
    /// Creates a new limit order.
    pub fn new(id: OrderId, side: Side, price: Price, quantity: Quantity) -> Self {
        Order {
            id,
            side,
            price,
            quantity,
        }
    }

    /// Returns whether this order would trade against a resting order at `resting_price`.
    ///
    /// - A **buy** crosses if the resting sell is at or *below* our price
    ///   (someone is selling for no more than we're willing to pay).
    /// - A **sell** crosses if the resting buy is at or *above* our price
    ///   (someone is paying at least what we're asking).
    pub fn crosses(&self, resting_price: Price) -> bool {
        match self.side {
            Side::Buy => resting_price <= self.price,
            Side::Sell => resting_price >= self.price,
        }
    }
}

/// A completed match between two orders.
///
/// - The **maker** is the order that was already resting on the book
///   (it "made" liquidity available).
/// - The **taker** is the incoming order that crossed the book
///   (it "took" that liquidity).
///
/// Trades always happen at the **maker's** price.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Trade {
    pub maker_order_id: OrderId,
    pub taker_order_id: OrderId,
    pub price: Price,
    pub quantity: Quantity,
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Builds a test order with a fixed id and quantity, so tests read cleanly.
    fn order(side: Side, price: u64) -> Order {
        Order::new(OrderId(1), side, Price(price), Quantity(10))
    }

    #[test]
    fn opposite_side() {
        assert_eq!(Side::Buy.opposite(), Side::Sell);
        assert_eq!(Side::Sell.opposite(), Side::Buy);
    }

    #[test]
    fn prices_compare_like_numbers() {
        assert!(Price(100) < Price(101));
        assert_eq!(Price(100), Price(100));
    }

    #[test]
    fn buy_crosses_cheaper_or_equal_sell() {
        let buy = order(Side::Buy, 100);
        assert!(buy.crosses(Price(99))); // Seller asks less than we pay: trade
        assert!(buy.crosses(Price(100))); // Exact match: trade
        assert!(!buy.crosses(Price(101))); // Seller wants more: no trade
    }

    #[test]
    fn sell_crosses_higher_or_equal_buy() {
        let sell = order(Side::Sell, 100);
        assert!(sell.crosses(Price(101))); // Buyer pays more than we ask: trade
        assert!(sell.crosses(Price(100))); // Exact match: trade
    }
}
