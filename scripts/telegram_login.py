"""Create the session string for the test account (ADR-006). Run once, on your machine.

    python scripts/telegram_login.py

Asks for the phone number, the login code and the two-step password if the account
has one, then prints TESTFORGE_TG_SESSION=... to store as a GitHub Secret or in .env.
The session string gives full access to the test account: never commit it or paste
it into a chat. api_id and api_hash come from https://my.telegram.org.
"""

import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = int(os.environ.get("TESTFORGE_TG_API_ID") or input("api_id: "))
    api_hash = os.environ.get("TESTFORGE_TG_API_HASH") or input("api_hash: ")
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        session = client.session.save()
    print(f"\nTESTFORGE_TG_SESSION={session}")


if __name__ == "__main__":
    asyncio.run(main())
