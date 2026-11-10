//! Coinbase's level2 message format, and converting it into our own types.
//!
//! The structs here mirror Coinbase's JSON exactly (field names, strings for
//! numbers). `serde` generates the parsing code from them. Anything we don't
//! list is ignored.

use serde::Deserialize;

use lobster_engine::{Price, Quantity, Side};

use crate::decimal::{DecimalError, parse_fixed};
use crate::l2book::LevelUpdate;

/// How many decimal places a product's prices and sizes use.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProductSpec {
    /// Decimal places in a price. 2 means one tick is $0.01.
    pub price_decimals: u32,
    /// Decimal places in a size. 8 means one lot is 0.00000001 BTC (a satoshi).
    pub quantity_decimals: u32,
}

/// BTC-USD: prices in cents, sizes in satoshis.
pub const BTC_USD: ProductSpec = ProductSpec {
    price_decimals: 2,
    quantity_decimals: 8,
};

/// One line of a recording file, as written by `lobster-recorder`.
#[derive(Debug, Deserialize)]
pub struct RecordedLine {
    /// When our computer received the message, in nanoseconds since 1970.
    pub recv_ns: u64,
    /// The message exactly as Coinbase sent it.
    pub msg: Message,
}

/// A Coinbase websocket message. The `channel` field decides which variant it is.
#[derive(Debug, Deserialize)]
#[serde(tag = "channel")]
pub enum Message {
    #[serde(rename = "l2_data")]
    L2Data(L2Data),
    #[serde(rename = "market_trades")]
    MarketTrades(MarketTrades),
    #[serde(rename = "heartbeats")]
    Heartbeats(Sequenced),
    #[serde(rename = "subscriptions")]
    Subscriptions(Sequenced),
}

impl Message {
    /// Returns the message's per-connection sequence number.
    pub fn sequence_num(&self) -> u64 {
        match self {
            Message::L2Data(data) => data.sequence_num,
            Message::MarketTrades(trades) => trades.sequence_num,
            Message::Heartbeats(other) | Message::Subscriptions(other) => other.sequence_num,
        }
    }
}

/// A message where we only need the sequence number.
#[derive(Debug, Deserialize)]
pub struct Sequenced {
    pub sequence_num: u64,
}

/// An `l2_data` message: one or more batches of level updates.
#[derive(Debug, Deserialize)]
pub struct L2Data {
    pub sequence_num: u64,
    /// When Coinbase sent the message (RFC 3339 text, e.g. "2026-11-10T18:29:27.923Z").
    pub timestamp: String,
    pub events: Vec<L2Event>,
}

/// One batch of updates inside an `l2_data` message.
#[derive(Debug, Deserialize)]
pub struct L2Event {
    #[serde(rename = "type")]
    pub kind: EventKind,
    pub product_id: String,
    pub updates: Vec<RawUpdate>,
}

/// A `market_trades` message: trades that actually happened.
///
/// Coinbase batches trades over 250 ms, so one message can hold many. The
/// first message after subscribing is a snapshot of recent trades.
#[derive(Debug, Deserialize)]
pub struct MarketTrades {
    pub sequence_num: u64,
    pub timestamp: String,
    pub events: Vec<TradeEvent>,
}

/// One batch of trades inside a `market_trades` message.
#[derive(Debug, Deserialize)]
pub struct TradeEvent {
    #[serde(rename = "type")]
    pub kind: EventKind,
    pub trades: Vec<RawTrade>,
}

/// One trade, exactly as Coinbase sends it.
#[derive(Debug, Deserialize)]
pub struct RawTrade {
    pub trade_id: String,
    pub product_id: String,
    pub price: String,
    pub size: String,
    /// The side of the order that was resting on the book (the maker).
    pub side: TradeSide,
    pub time: String,
}

/// Coinbase writes trade sides in capitals.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum TradeSide {
    Buy,
    Sell,
}

/// A snapshot replaces the whole book; an update changes some levels.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum EventKind {
    Snapshot,
    Update,
}

/// One price level change, exactly as Coinbase sends it.
#[derive(Debug, Deserialize)]
pub struct RawUpdate {
    pub side: RawSide,
    pub event_time: String,
    pub price_level: String,
    pub new_quantity: String,
}

/// Coinbase calls the sell side "offer".
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RawSide {
    Bid,
    Offer,
}

impl From<RawSide> for Side {
    fn from(side: RawSide) -> Side {
        match side {
            RawSide::Bid => Side::Buy,
            RawSide::Offer => Side::Sell,
        }
    }
}

impl RawUpdate {
    /// Converts the strings into exact integer ticks and lots.
    pub fn to_level_update(&self, spec: ProductSpec) -> Result<LevelUpdate, DecimalError> {
        Ok(LevelUpdate {
            side: self.side.into(),
            price: Price(parse_fixed(&self.price_level, spec.price_decimals)?),
            quantity: Quantity(parse_fixed(&self.new_quantity, spec.quantity_decimals)?),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Real lines from the first recording, shortened
    const SNAPSHOT: &str = r#"{"recv_ns":1794335368253140000,"msg":{"channel":"l2_data","timestamp":"2026-11-10T18:29:27.923086058Z","sequence_num":0,"events":[{"type":"snapshot","product_id":"BTC-USD","updates":[{"side":"bid","event_time":"2026-11-10T18:29:27.637976Z","price_level":"73232.08","new_quantity":"0.3404195"},{"side":"offer","event_time":"2026-11-10T18:29:27.637976Z","price_level":"73233.5","new_quantity":"0.01"}]}]}}"#;
    const HEARTBEAT: &str = r#"{"recv_ns":1794335369000000000,"msg":{"channel":"heartbeats","client_id":"","timestamp":"2026-11-10T18:29:28.6Z","sequence_num":3,"events":[{"current_time":"2026-11-10 18:29:28.6 +0000 UTC","heartbeat_counter":5}]}}"#;

    #[test]
    fn parses_a_snapshot_line() {
        let line: RecordedLine = serde_json::from_str(SNAPSHOT).unwrap();
        assert_eq!(line.recv_ns, 1_794_335_368_253_140_000);
        let Message::L2Data(data) = line.msg else {
            panic!("expected l2_data");
        };
        assert_eq!(data.sequence_num, 0);
        assert_eq!(data.events[0].kind, EventKind::Snapshot);
        assert_eq!(data.events[0].product_id, "BTC-USD");

        let updates: Vec<LevelUpdate> = data.events[0]
            .updates
            .iter()
            .map(|u| u.to_level_update(BTC_USD).unwrap())
            .collect();
        assert_eq!(
            updates,
            vec![
                LevelUpdate {
                    side: Side::Buy,
                    price: Price(7_323_208),
                    quantity: Quantity(34_041_950),
                },
                LevelUpdate {
                    side: Side::Sell,
                    price: Price(7_323_350),
                    quantity: Quantity(1_000_000),
                },
            ]
        );
    }

    #[test]
    fn parses_a_heartbeat_line() {
        let line: RecordedLine = serde_json::from_str(HEARTBEAT).unwrap();
        assert!(matches!(line.msg, Message::Heartbeats(_)));
        assert_eq!(line.msg.sequence_num(), 3);
    }

    #[test]
    fn parses_a_market_trades_line() {
        let text = r#"{"recv_ns":2,"msg":{"channel":"market_trades","client_id":"","timestamp":"2026-11-10T18:30:00.1Z","sequence_num":7,"events":[{"type":"update","trades":[{"trade_id":"123","product_id":"BTC-USD","price":"73232.08","size":"0.0015","side":"SELL","time":"2026-11-10T18:30:00.05Z"}]}]}}"#;
        let line: RecordedLine = serde_json::from_str(text).unwrap();
        assert_eq!(line.msg.sequence_num(), 7);
        let Message::MarketTrades(trades) = line.msg else {
            panic!("expected market_trades");
        };
        let trade = &trades.events[0].trades[0];
        assert_eq!(trades.events[0].kind, EventKind::Update);
        assert_eq!(trade.side, TradeSide::Sell);
        assert_eq!(
            parse_fixed(&trade.size, BTC_USD.quantity_decimals),
            Ok(150_000)
        );
    }

    #[test]
    fn unknown_channel_is_an_error() {
        let text = r#"{"recv_ns":1,"msg":{"channel":"ticker","sequence_num":1}}"#;
        assert!(serde_json::from_str::<RecordedLine>(text).is_err());
    }
}
