# ML news bot

Daily Telegram digest of new posts from data science, ML engineering and AI engineering blogs, labs, newsletters, Hacker News and tool releases.

Runs on GitHub Actions once a day, so nothing has to stay on your laptop. Links that were already sent are remembered in `state/seen.json`.

## Setup

1. In Telegram, open **@BotFather**, send `/newbot`, and copy the token.
2. Send your new bot any message, then get your chat id:
   ```bash
   pip install -r requirements.txt
   TELEGRAM_BOT_TOKEN=<token> python get_chat_id.py
   ```
3. Push this folder to a GitHub repo and add two secrets under
   *Settings → Secrets and variables → Actions*: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
4. *Actions → ML news digest → Run workflow* to test it. After that it runs every day at 06:00 UTC.

## AI picks (optional)

Add an `ANTHROPIC_API_KEY` secret and Claude picks the 5 most important links each day, with one sentence on why each matters. Without the key (or if the call fails) the bot falls back to picking by source weight.

## Local run

```bash
python bot.py --dry-run   # prints the digest, sends nothing
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python bot.py
```

## Changing sources

Edit `sources.toml`. Broad feeds use `filter = true` so only posts matching the keyword list get through. To change the time, edit the `cron` line in `.github/workflows/digest.yml`.
