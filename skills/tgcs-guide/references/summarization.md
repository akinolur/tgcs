# Summarization

Optional. Needs extra dependencies: `uv tool install --editable ".[summary]"`.
Works only for `daily` layout chats with `summarization_enabled: true`.

Config:
```toml
[settings]
summary_template = "~/.config/tgcs/summary.mustache"

[telegram_bot]
bot_token = "123456:ABC-DEF..." # bot token for notifications
tg_users = ["123456789"] # user IDs to send summaries to

[llm]
api_key = "gsk_..."
model = "llama-3.3-70b-versatile"
url = "https://api.groq.com/openai/v1" # any OpenAI-compatible endpoint
```

Prompt: `~/.config/tgcs/prompts/summary.toml` (created by `tgcs init`).

```bash
tgcs summarize --all # summarize all enabled chats
tgcs summarize --all --tg # + send Telegram notifications
tgcs summarize --chat CHAT_NAME # single chat
tgcs summarize --all --days 3 # last 3 days only
tgcs summarize preview # render template with sample data
tgcs notification --all # send saved summaries
tgcs notification --chat CHAT_NAME --days 3
```

Daily cron with summaries:
```
0 9 * * * (tgcs chats update && tgcs chats download --all --days 7 && tgcs summarize --all --tg --days 7) > /tmp/tgcs.log 2>&1
```

## Summary template

`~/.config/tgcs/summary.mustache` (created by `tgcs init`). Edit it, then run `tgcs summarize preview`.

Variables:
- `{{group_name}}` - chat name
- `{{date}}` - date in `YYYY-MM-DD` format
- `{{#threads}}` / `{{/threads}}` - loop over threads
  - `{{name}}` - thread name (from LLM)
  - `{{count}}` - message count
  - `{{url}}` - deep link to the thread

## Presenting thread summaries

When showing thread data to the user (from `threads ls`, `summary.md`, or any other source), always format it as markdown in the default template style:

```
#group_name
Date: YYYY-MM-DD

- Thread name ([N](https://t.me/group/ROOT_ID/))
- Another thread ([M](https://t.me/group/ROOT_ID2/))
```

- **Thread name**: use the name from `summary.md`. If `summary.md` is not available, ask the user to run `tgcs summarize --chat CHAT_NAME` first.
- **N**: message count (MESSAGES column from `threads ls`).
- **Link**: URL from `threads ls`, points to the first message in the thread.
- For multiple dates: repeat the header block for each date.
