"""One-step setup: paste the bot token, message the bot, done.

Finds your chat id, saves both GitHub secrets and sends a first digest.
Needs the `gh` CLI logged in.
"""

import getpass
import subprocess
import time

import requests

REPO = "ssicic/ml-news-bot"

token = getpass.getpass("Paste the bot token from @BotFather (input is hidden): ").strip()
me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20).json()
if not me.get("ok"):
    raise SystemExit("That token doesn't work. Copy it again from @BotFather.")
username = me["result"]["username"]
print(f"\nOK, bot @{username} found.")
print(f"Now open https://t.me/{username} in Telegram, press Start (or send any message)...")

chat_id = None
while chat_id is None:
    updates = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json()
    for u in updates.get("result", []):
        if "message" in u:
            chat_id = str(u["message"]["chat"]["id"])
    if chat_id is None:
        time.sleep(3)
print("Got your chat.")

for name, value in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)):
    subprocess.run(["gh", "secret", "set", name, "-R", REPO], input=value, text=True, check=True)

requests.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    json={"chat_id": chat_id, "text": "Bot is set up. First digest is on its way 📰"},
    timeout=20,
)
subprocess.run(["gh", "workflow", "run", "digest.yml", "-R", REPO], check=True)
print("\nDone. The first digest should arrive in 1-2 minutes, then every day at 07:00.")
