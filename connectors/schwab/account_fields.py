"""Lists the fields Schwab's account, order, quote and price history responses really contain.

Names and counts only, never values, so the output is safe to paste into a
chat. Use it to check the server's parser (dashboard/server/account/parse.py)
against what Schwab actually sends:

    python connectors/schwab/account_fields.py
"""

import asyncio

from connect import async_client
from inspect_recording import field_names


async def main() -> None:
    client = async_client()
    try:
        accounts = await client.get_accounts(fields=[client.Account.Fields.POSITIONS])
        accounts.raise_for_status()
        orders = await client.get_orders_for_all_linked_accounts()
        orders.raise_for_status()
        quotes = await client.get_quotes(["SPY"])
        quotes.raise_for_status()
        history = await client.get_price_history_every_day("SPY", need_extended_hours_data=False)
        history.raise_for_status()
        sections = (
            ("accounts", accounts.json()),
            ("orders (last 60 days)", orders.json()),
            ("quotes (SPY)", quotes.json()),
            ("price history (SPY, daily)", history.json()),
        )
        for title, data in sections:
            print(f"\n{title}:")
            for path, count in sorted(field_names(data).items()):
                print(f"  {path}  ({count})")
    finally:
        await client.close_async_session()


if __name__ == "__main__":
    asyncio.run(main())
