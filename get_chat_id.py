"""Print the chat id of whoever last messaged your bot.

1. Send any message to your bot in Telegram.
2. TELEGRAM_BOT_TOKEN=... python get_chat_id.py
"""

import os

import requests

token = os.environ["TELEGRAM_BOT_TOKEN"]
updates = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json()
chats = {u["message"]["chat"]["id"]: u["message"]["chat"] for u in updates.get("result", []) if "message" in u}
if not chats:
    print("No messages yet. Send your bot a message in Telegram and run this again.")
for chat_id, chat in chats.items():
    print(chat_id, chat.get("username") or chat.get("title"))
