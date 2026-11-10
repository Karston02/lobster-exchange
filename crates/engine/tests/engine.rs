//! Integration tests: drive the engine only through its public API
//! (`Command` in, `Event` out), the same way the bot and replayer will.

use lobster_engine::{
    CancelReason, Command, Engine, Event, OrderId, Price, Quantity, RejectReason, Side, Trade,
};

fn limit(id: u64, side: Side, price: u64, quantity: u64) -> Command {
    Command::NewLimit {
        id: OrderId(id),
        side,
        price: Price(price),
        quantity: Quantity(quantity),
    }
}

fn market(id: u64, side: Side, quantity: u64) -> Command {
    Command::NewMarket {
        id: OrderId(id),
        side,
        quantity: Quantity(quantity),
    }
}

fn trade(maker: u64, taker: u64, price: u64, quantity: u64) -> Event {
    Event::Trade(Trade {
        maker_order_id: OrderId(maker),
        taker_order_id: OrderId(taker),
        price: Price(price),
        quantity: Quantity(quantity),
    })
}

fn accepted(id: u64) -> Event {
    Event::Accepted { id: OrderId(id) }
}

fn rejected(id: u64, reason: RejectReason) -> Event {
    Event::Rejected {
        id: OrderId(id),
        reason,
    }
}

#[test]
fn resting_limit_order_is_just_accepted() {
    let mut engine = Engine::new();
    let events = engine.process(limit(1, Side::Buy, 100, 5));

    assert_eq!(events, vec![accepted(1)]);
    assert_eq!(engine.book().best_bid(), Some(Price(100)));
}

#[test]
fn crossing_limit_order_is_accepted_then_trades() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Sell, 100, 5));
    engine.process(limit(2, Side::Sell, 101, 5));

    let events = engine.process(limit(3, Side::Buy, 101, 8));
    assert_eq!(
        events,
        vec![accepted(3), trade(1, 3, 100, 5), trade(2, 3, 101, 3)]
    );
}

#[test]
fn market_order_remainder_is_cancelled_for_no_liquidity() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Sell, 100, 3));

    let events = engine.process(market(2, Side::Buy, 10));
    assert_eq!(
        events,
        vec![
            accepted(2),
            trade(1, 2, 100, 3),
            Event::Cancelled {
                id: OrderId(2),
                remaining: Quantity(7),
                reason: CancelReason::NoLiquidity,
            },
        ]
    );
}

#[test]
fn fully_filled_market_order_has_no_cancel_event() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Sell, 100, 5));

    let events = engine.process(market(2, Side::Buy, 5));
    assert_eq!(events, vec![accepted(2), trade(1, 2, 100, 5)]);
}

#[test]
fn cancel_reports_what_was_left() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Sell, 100, 10));
    engine.process(limit(2, Side::Buy, 100, 4));

    let events = engine.process(Command::Cancel { id: OrderId(1) });
    assert_eq!(
        events,
        vec![Event::Cancelled {
            id: OrderId(1),
            remaining: Quantity(6),
            reason: CancelReason::Requested,
        }]
    );
}

#[test]
fn zero_quantity_is_rejected() {
    let mut engine = Engine::new();
    assert_eq!(
        engine.process(limit(1, Side::Buy, 100, 0)),
        vec![rejected(1, RejectReason::ZeroQuantity)]
    );
    assert_eq!(
        engine.process(market(2, Side::Buy, 0)),
        vec![rejected(2, RejectReason::ZeroQuantity)]
    );
    assert_eq!(engine.book().order_count(), 0);
}

#[test]
fn zero_price_limit_is_rejected() {
    let mut engine = Engine::new();
    assert_eq!(
        engine.process(limit(1, Side::Buy, 0, 5)),
        vec![rejected(1, RejectReason::ZeroPrice)]
    );
}

#[test]
fn duplicate_resting_id_is_rejected_and_book_is_unchanged() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Buy, 100, 5));

    assert_eq!(
        engine.process(limit(1, Side::Buy, 99, 5)),
        vec![rejected(1, RejectReason::DuplicateOrderId)]
    );
    assert_eq!(engine.book().order_count(), 1);
    assert_eq!(engine.book().best_bid(), Some(Price(100)));
}

#[test]
fn cancelling_unknown_order_is_rejected() {
    let mut engine = Engine::new();
    assert_eq!(
        engine.process(Command::Cancel { id: OrderId(42) }),
        vec![rejected(42, RejectReason::UnknownOrderId)]
    );
}

#[test]
fn same_commands_always_produce_same_events() {
    // Determinism: replaying a session must give identical results
    let commands = [
        limit(1, Side::Sell, 101, 5),
        limit(2, Side::Sell, 100, 5),
        limit(3, Side::Buy, 99, 5),
        market(4, Side::Buy, 7),
        Command::Cancel { id: OrderId(3) },
        limit(5, Side::Sell, 99, 2),
    ];

    let run = || {
        let mut engine = Engine::new();
        commands
            .iter()
            .flat_map(|command| engine.process(*command))
            .collect::<Vec<_>>()
    };
    assert_eq!(run(), run());
}
