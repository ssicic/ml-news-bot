# ML news bot

Sends me the 5 most important data science / ML / AI engineering posts of the day on Telegram, with a short summary for each.

It reads about 20 RSS feeds (AI labs, a few engineering blogs, Hacker News, tool releases) and runs once a day on GitHub Actions. Links that were already sent are kept in `state/seen.json`.

## How the top 5 is picked

No LLM by default. Each new post gets a score from:

- **coverage**: how many sources wrote about the same story that day (stories are matched by shared title words like "gpt-6.2")
- **source weight** set in `sources.toml`, plus Hacker News points
- **title words**: launches, releases, papers and benchmarks go up; partnerships, webinars and listicles go down

Then one post per story and one per source (two for Hacker News). The summary is the feed's own description, or the page's meta description when the feed has none.

If an `ANTHROPIC_API_KEY` secret is set, Claude picks the 5 instead. If that call fails, the bot falls back to the scoring above.

## Setup

1. Create a bot with **@BotFather** in Telegram and copy the token.
2. Add the secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` under *Settings → Secrets and variables → Actions*. `python setup.py` does both and finds the chat id for you.
3. *Actions → ML news digest → Run workflow* to test it. After that it runs every day at 06:00 UTC.

## Local run

```bash
pip install -r requirements.txt
python bot.py --dry-run   # prints the message, sends nothing
```

## Changing it

Feeds, weights and keywords live in `sources.toml`. Set `top_n = 0` there to get every new link instead of the top 5. The schedule is the `cron` line in `.github/workflows/digest.yml`.
