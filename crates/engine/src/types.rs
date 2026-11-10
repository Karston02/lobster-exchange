/// which side of the book an order is on (you're either a buyer or seller)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Side {
    /// A buyer. Buy orders rest on the bid side of the book
    Buy,
    /// A seller. Sell orders rest on the ask side of the book
    Sell,
}

impl Side {
    /// the other side. A buy order matches against sells, and vice versa.
    pub fn opposite(self) -> Side {
        match self {
            Side::Buy => Side::Sell,
            Side::Sell => Side::Buy,
        }
    }

    /// Returns whether an order on this side with price `limit` would trade
    /// against a resting order at `resting_price`.
    ///
    /// A buy crosses sells at or below its limit; a sell crosses buys at or
    /// above its limit. This is the one place that rule lives.
    pub fn crosses(self, limit: Price, resting_price: Price) -> bool {
        match self {
            Side::Buy => resting_price <= limit,
            Side::Sell => resting_price >= limit,
        }
    }
}

/**
 * A price, in integer ticks (e.g. cents). Never a float; see ARCHITECTURE.md #1.
 *
 * This is a "newtype": which means it wraps a single value and is treated
 * distinct from the underlying type it wraps. It's free at runtime but now
 * the compiler is going to treat Price and Quantity as distinct types.
 */
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

/// The Order struct represents a limit order in the order book.
impl Order {
    pub fn new(id: OrderId, side: Side, price: Price, quantity: Quantity) -> Self {
        Order {
            id,
            side,
            price,
            quantity,
        }
    }

    /**
     * This determines whether the order would cross with a resting (existing) order at the given price.
     * A buy order crosses if the resting sell is at or below our price.
     * A sell order crosses if the resting buy is at or above our price.
     */
    pub fn crosses(&self, resting_price: Price) -> bool {
        self.side.crosses(self.price, resting_price)
    }
}

/**
 * Represents a completed trade between a maker and a taker.
 * The maker is the order that was already resting on the book and the taker is
 * the incoming order that it "took" liquidity from.
 */
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

    /// helper so tests read cleanly.
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
        assert!(buy.crosses(Price(99))); // seller asks less than we pay: trade
        assert!(buy.crosses(Price(100))); // exact match: trade
        assert!(!buy.crosses(Price(101))); // seller wants more: no trade
    }

    #[test]
    fn sell_crosses_higher_or_equal_buy() {
        let sell = order(Side::Sell, 100);
        assert!(sell.crosses(Price(101))); // buyer pays more than we ask: trade
        assert!(sell.crosses(Price(100))); // exact match: trade
        assert!(!sell.crosses(Price(99))); // buyer pays less than we ask: no trade
    }
}
