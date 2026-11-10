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

#[test]
fn market_sell_remainder_is_cancelled_for_no_liquidity() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Buy, 100, 2));

    let events = engine.process(market(2, Side::Sell, 5));
    assert_eq!(
        events,
        vec![
            accepted(2),
            trade(1, 2, 100, 2),
            Event::Cancelled {
                id: OrderId(2),
                remaining: Quantity(3),
                reason: CancelReason::NoLiquidity,
            },
        ]
    );
}

#[test]
fn cancelled_order_can_no_longer_trade() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Sell, 100, 5));
    engine.process(Command::Cancel { id: OrderId(1) });

    // The only seller is gone, so this buy just rests
    let events = engine.process(limit(2, Side::Buy, 100, 5));
    assert_eq!(events, vec![accepted(2)]);
    assert_eq!(engine.book().best_ask(), None);
}

#[test]
fn id_of_a_fully_filled_order_can_be_reused() {
    // Documents a known limitation: ids are only checked against resting orders
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Sell, 100, 5));
    engine.process(limit(2, Side::Buy, 100, 5)); // Order 1 is now fully filled

    assert_eq!(
        engine.process(limit(1, Side::Sell, 101, 5)),
        vec![accepted(1)]
    );
}

#[test]
fn book_is_never_left_crossed() {
    // After every command, the best bid must stay below the best ask
    let mut engine = Engine::new();
    let commands = [
        limit(1, Side::Sell, 101, 5),
        limit(2, Side::Buy, 99, 5),
        limit(3, Side::Buy, 102, 3),  // Crosses and fills against order 1
        limit(4, Side::Sell, 98, 10), // Sweeps the bids and rests the rest
        market(5, Side::Buy, 4),
        limit(6, Side::Buy, 97, 1),
    ];
    for command in commands {
        engine.process(command);
        if let (Some(bid), Some(ask)) = (engine.book().best_bid(), engine.book().best_ask()) {
            assert!(
                bid < ask,
                "book crossed after {command:?}: bid {bid:?}, ask {ask:?}"
            );
        }
    }
}

fn ioc(id: u64, side: Side, price: u64, quantity: u64) -> Command {
    Command::NewImmediateOrCancel {
        id: OrderId(id),
        side,
        price: Price(price),
        quantity: Quantity(quantity),
    }
}

#[test]
fn ioc_fills_within_its_limit_and_cancels_the_rest() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Sell, 100, 3));
    engine.process(limit(2, Side::Sell, 102, 5)); // Above the IOC's limit

    let events = engine.process(ioc(3, Side::Buy, 101, 10));
    assert_eq!(
        events,
        vec![
            accepted(3),
            trade(1, 3, 100, 3),
            Event::Cancelled {
                id: OrderId(3),
                remaining: Quantity(7),
                reason: CancelReason::NoLiquidity,
            },
        ]
    );
    // Unlike a limit order, nothing rests, and the 102 ask is untouched
    assert_eq!(engine.book().best_bid(), None);
    assert_eq!(engine.book().best_ask(), Some(Price(102)));
}

#[test]
fn ioc_that_cannot_trade_is_cancelled_in_full() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Buy, 99, 5));

    let events = engine.process(ioc(2, Side::Sell, 100, 4));
    assert_eq!(
        events,
        vec![
            accepted(2),
            Event::Cancelled {
                id: OrderId(2),
                remaining: Quantity(4),
                reason: CancelReason::NoLiquidity,
            },
        ]
    );
    assert_eq!(engine.book().order_count(), 1);
}

#[test]
fn ioc_takes_the_front_of_the_line_first() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Buy, 100, 5));
    engine.process(limit(2, Side::Buy, 100, 5));

    let events = engine.process(ioc(3, Side::Sell, 100, 6));
    assert_eq!(
        events,
        vec![accepted(3), trade(1, 3, 100, 5), trade(2, 3, 100, 1)]
    );
}

#[test]
fn ioc_with_zero_price_is_rejected() {
    let mut engine = Engine::new();
    assert_eq!(
        engine.process(ioc(1, Side::Buy, 0, 5)),
        vec![rejected(1, RejectReason::ZeroPrice)]
    );
}

#[test]
fn reduce_shrinks_an_order_and_keeps_its_place_in_line() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Buy, 100, 10));
    engine.process(limit(2, Side::Buy, 100, 5));

    let events = engine.process(Command::Reduce {
        id: OrderId(1),
        by: Quantity(7),
    });
    assert_eq!(
        events,
        vec![Event::Reduced {
            id: OrderId(1),
            remaining: Quantity(3),
        }]
    );
    // Order 1 is still first in line: a sell of 3 fills it, not order 2
    let events = engine.process(limit(3, Side::Sell, 100, 3));
    assert_eq!(events, vec![accepted(3), trade(1, 3, 100, 3)]);
}

#[test]
fn reducing_by_everything_left_cancels() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Sell, 100, 4));
    let events = engine.process(Command::Reduce {
        id: OrderId(1),
        by: Quantity(9),
    });
    assert_eq!(
        events,
        vec![Event::Cancelled {
            id: OrderId(1),
            remaining: Quantity(4),
            reason: CancelReason::Requested,
        }]
    );
    assert_eq!(engine.book().order_count(), 0);
}

#[test]
fn reduce_rejects_zero_and_unknown_orders() {
    let mut engine = Engine::new();
    engine.process(limit(1, Side::Buy, 100, 5));
    let reduce = |id: u64, by: u64| Command::Reduce {
        id: OrderId(id),
        by: Quantity(by),
    };
    assert_eq!(
        engine.process(reduce(1, 0)),
        vec![rejected(1, RejectReason::ZeroQuantity)]
    );
    assert_eq!(
        engine.process(reduce(2, 1)),
        vec![rejected(2, RejectReason::UnknownOrderId)]
    );
}
