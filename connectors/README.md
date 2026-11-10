# Connectors

Code that talks to real brokers and data sources, as opposed to the simulated
exchange in `crates/`.

## Schwab (`connectors/schwab/`)

Uses [schwab-py](https://schwab-py.readthedocs.io/). Needs an approved app on
developer.schwab.com.

**Setup** (once): put your app's credentials in a `.env` file at the repo root.
It's gitignored; never commit it.

```
SCHWAB_API_KEY=...
SCHWAB_APP_SECRET=...
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182
# Optional, defaults to ~/.lobster/schwab_token.json (outside the repo):
# SCHWAB_TOKEN_PATH=/path/to/your/existing/token.json
```

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
| `connect.py` | Credentials from `.env` / environment, the authenticated async client |
| `record.py` | Records level one quotes, order book snapshots and 1-minute bars to `data/schwab/` |
| `inspect_recording.py` | Message counts, the fields each stream really sends, and an example of each |

Nothing here places orders yet. Order placement will come with the `Broker`
interface, behind dry-run mode and safety limits.
