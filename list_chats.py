import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient


env_file = os.getenv("ENV_FILE", ".env")
load_dotenv(env_file)
if env_file != ".env":
    load_dotenv(".env")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing {name}")
    return value


api_id = int(require_env("TELEGRAM_API_ID"))
api_hash = require_env("TELEGRAM_API_HASH")
session_name = os.getenv("SESSION_NAME", "telegram_forwarder_session")

session_path = Path(session_name).expanduser()
if session_path.parent != Path("."):
    session_path.parent.mkdir(parents=True, exist_ok=True)

client = TelegramClient(str(session_path), api_id, api_hash)


async def main():
    async for dialog in client.iter_dialogs():
        print(f"{dialog.name} => {dialog.id}")


if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
