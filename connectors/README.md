# Connectors

Code that talks to real brokers and data sources, as opposed to the simulated
exchange in `crates/`.

## Schwab (`connectors/schwab/`)

Uses [schwab-py](https://schwab-py.readthedocs.io/). Needs an approved app on
developer.schwab.com.

**Setup** (once): copy `.env.example` at the repo root to `.env` and fill in
your app's credentials. `.env` is gitignored; never commit it. The settings
are read by `config/settings.py`, shared by the whole app. The token defaults
to `~/.lobster/schwab_token.json`, outside the repo.

```sh
uv pip install schwab-py
```

**Record** during market hours (9:30 to 4:00 US Eastern), then **inspect** what came in:

```sh
python connectors/schwab/record.py AAPL SPY
python connectors/schwab/inspect_recording.py
```

| File | Job |
|---|---|
| `connect.py` | The authenticated async client, using the app's settings |
| `record.py` | Records level one quotes, order book snapshots and 1-minute bars to `data/schwab/` |
| `login.py` | Logs in (opens a browser) and saves the token the server uses. Run again every 7 days |
| `account_fields.py` | Lists the field names Schwab's account and order responses contain (no values) |
| `inspect_recording.py` | Message counts, the fields each stream really sends, and an example of each |

Nothing here places orders yet. Order placement will come with the `Broker`
interface, behind dry-run mode and safety limits.
