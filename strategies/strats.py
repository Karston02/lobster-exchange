"""The strategies, from simplest to less simple.

Each one changes one thing from the previous, so a comparison shows what that
one change is worth:

- `Naive` (v1): every tick, cancel everything and re-join the best bid and ask.
- `KeepPlace` (v1b): the same quotes, but leave an order alone if it's already
  at the right price, so it keeps its place in line.
- `InventorySkew` (v2): `KeepPlace`, plus lean against the position: when
  long, quote the bid further away (buy less) and when short, the ask; stop
  quoting the side that would go past a position limit.
"""

import lobster


class Naive:
    name = "v1 naive"

    def __init__(self, size: int):
        self.size = size

    def on_tick(self, bt: lobster.Backtest) -> None:
        for order in bt.open_orders():
            bt.cancel(order.id)
        bid, ask = bt.best_bid(), bt.best_ask()
        if bid and ask:
            bt.submit_limit("buy", bid[0], self.size)
            bt.submit_limit("sell", ask[0], self.size)


class KeepPlace:
    name = "v1b keep place"

    def __init__(self, size: int):
        self.size = size

    def targets(self, bt: lobster.Backtest) -> dict:
        """The price to quote on each side, or None to not quote it."""
        bid, ask = bt.best_bid(), bt.best_ask()
        if not (bid and ask):
            return {"buy": None, "sell": None}
        return {"buy": bid[0], "sell": ask[0]}

    def on_tick(self, bt: lobster.Backtest) -> None:
        targets = self.targets(bt)
        resting = {"buy": [], "sell": []}
        for order in bt.open_orders():
            resting[order.side].append(order)

        for side, price in targets.items():
            keep = None
            for order in resting[side]:
                # Keep one order that's already at the right price; cancel the rest
                if keep is None and order.price == price:
                    keep = order
                else:
                    bt.cancel(order.id)
            if price is not None and keep is None:
                bt.submit_limit(side, price, self.size)


class InventorySkew(KeepPlace):
    name = "v2 inventory skew"

    def __init__(self, size: int, max_position: int, skew_ticks: int):
        """
        size:         lots per order
        max_position: stop adding to a position past this many lots
        skew_ticks:   how many ticks to move the quote away per order-size of position
        """
        super().__init__(size)
        self.max_position = max_position
        self.skew_ticks = skew_ticks

    def targets(self, bt: lobster.Backtest) -> dict:
        bid, ask = bt.best_bid(), bt.best_ask()
        if not (bid and ask):
            return {"buy": None, "sell": None}

        # Position measured in order sizes: +3 means we've bought 3 orders' worth
        units = bt.position / self.size
        buy = bid[0] - round(max(units, 0) * self.skew_ticks)
        sell = ask[0] + round(max(-units, 0) * self.skew_ticks)

        if bt.position >= self.max_position:
            buy = None  # Long enough: stop buying
        if bt.position <= -self.max_position:
            sell = None  # Short enough: stop selling
        return {"buy": buy, "sell": sell}
