"""The strategies, from simplest to less simple.

Each one changes one thing from the previous, so a comparison shows what that
one change is worth:

- `Naive` (v1): every tick, cancel everything and re-join the best bid and ask.
- `KeepPlace` (v1b): the same quotes, but leave an order alone if it's already
  at the right price, so it keeps its place in line.
- `InventorySkew` (v2): `KeepPlace`, plus lean against the position: when
  long, quote the bid further away (buy less) and when short, the ask; stop
  quoting the side that would go past a position limit.
- `ImbalanceFilter` (v3): `InventorySkew`, plus step back from the side the
  book says is about to be run over: if sellers heavily outnumber buyers at
  the top of the book, don't bid (the price is likely to drop through us),
  and the reverse. `signals.py` checks whether that signal holds in the data.
- `AvellanedaStoikov` (v4): the classic model from the 2008 paper "High-
  frequency trading in a limit order book". Quotes around a *reservation
  price* that shifts against the position, with a spread that widens when the
  market is volatile. On a one-tick-wide market, it mostly decides when to
  step back from the best price.
"""

import math
from collections import deque

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


class ImbalanceFilter(InventorySkew):
    name = "v3 imbalance filter"

    def __init__(self, size: int, max_position: int, skew_ticks: int, threshold: float, levels: int = 1):
        """
        threshold: skip a side when imbalance is past this against it (0 to 1)
        levels:    price levels per side to add up when measuring imbalance
        """
        super().__init__(size, max_position, skew_ticks)
        self.threshold = threshold
        self.levels = levels

    def targets(self, bt: lobster.Backtest) -> dict:
        targets = super().targets(bt)
        bid_size = sum(q for _, q in bt.top("buy", self.levels))
        ask_size = sum(q for _, q in bt.top("sell", self.levels))
        if bid_size + ask_size == 0:
            return targets
        imbalance = (bid_size - ask_size) / (bid_size + ask_size)
        if imbalance < -self.threshold:
            targets["buy"] = None  # Sellers dominate: a bid would likely get run over
        if imbalance > self.threshold:
            targets["sell"] = None  # Buyers dominate: an ask would likely get run over
        return targets


class AvellanedaStoikov(KeepPlace):
    name = "v4 avellaneda-stoikov"

    def __init__(
        self,
        size: int,
        max_position: int,
        gamma: float = 1e-5,
        horizon_s: float = 60.0,
        k: float = 1.0,
        vol_window_s: int = 60,
    ):
        """
        The model, with everything measured in ticks, seconds and order-sizes:

            reservation  r      = mid - q * gamma * sigma^2 * horizon
            spread       delta  = gamma * sigma^2 * horizon + (2 / gamma) * ln(1 + gamma / k)
            quotes              = r - delta / 2  and  r + delta / 2

        q:        position in order-sizes (+2 = long two orders' worth)
        sigma^2:  variance of the mid's per-second change (ticks^2), measured
                  over the last `vol_window_s` seconds. BTC's is large (its mid
                  moves ~$1/s, i.e. ~100 ticks), which is why gamma is tiny.
        gamma:    risk aversion; higher shifts quotes harder against the position
        horizon:  how far ahead (seconds) the model worries about inventory
        k:        how quickly fills fall off as quotes move away from the mid;
                  higher means a tighter spread
        """
        super().__init__(size)
        self.max_position = max_position
        self.gamma = gamma
        self.horizon_s = horizon_s
        self.k = k
        self.mids = deque(maxlen=vol_window_s + 1)

    def variance(self) -> float | None:
        if len(self.mids) < 10:
            return None
        changes = [b - a for a, b in zip(self.mids, list(self.mids)[1:])]
        mean = sum(changes) / len(changes)
        return sum((c - mean) ** 2 for c in changes) / (len(changes) - 1)

    def targets(self, bt: lobster.Backtest) -> dict:
        bid, ask = bt.best_bid(), bt.best_ask()
        if not (bid and ask):
            return {"buy": None, "sell": None}
        mid = (bid[0] + ask[0]) / 2
        self.mids.append(mid)  # on_tick runs once per second, so one sample per second
        sigma2 = self.variance()
        if sigma2 is None:
            return {"buy": None, "sell": None}  # Not enough history to quote yet

        q = bt.position / self.size
        risk = self.gamma * sigma2 * self.horizon_s
        reservation = mid - q * risk
        half_spread = (risk + (2 / self.gamma) * math.log(1 + self.gamma / self.k)) / 2

        # Never cross the book: at best join the best bid / ask
        buy = min(math.floor(reservation - half_spread), bid[0])
        sell = max(math.ceil(reservation + half_spread), ask[0])
        if bt.position >= self.max_position:
            buy = None
        if bt.position <= -self.max_position:
            sell = None
        return {"buy": buy, "sell": sell}

