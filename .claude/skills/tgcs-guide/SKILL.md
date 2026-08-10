---
name: tgcs-guide
description: Use when user asks about the "tgcs" project - configuration, CLI usage, setup, or actual Telegram group data (messages, threads, summaries, activity)
---

## Configuration

**Config file:** `~/.config/tgcs/config.toml` (XDG; override with `--config PATH`)

Generate a default config: `tgcs init`

```toml
# data_dir = "~/.local/share/tgcs" # default

[telegram]
api_id = 12345678
api_hash = "abc123..."
group_folder = "My TG Folder" # folder name in Telegram to sync groups from

[telegram_bot]
bot_token = "123456:ABC-DEF..." # bot token for notifications
tg_users = ["123456789"] # user IDs to send summaries to

[llm]
api_key = "gsk_..."
model = "llama-3.3-70b-versatile"
url = "https://api.groq.com/openai/v1" # any OpenAI-compatible endpoint

[settings]
previous_days = 5 # default download window
summary_template = "~/.config/tgcs/summary.mustache" # Mustache template for summary output
```

---

## CLI Reference

Entry point: `tgcs`
Global options: `--version/-V`, `--config/-c PATH`, `--verbose/-v`

### `tgcs chats`

```bash
tgcs chats ls # list all groups with status/msg counts
tgcs chats update # fetch group metadata (needs telegram.group_folder)
tgcs chats download GROUP_NAME # download history for one group
tgcs chats download --all # download all enabled groups
tgcs chats download --all --days 7 # override settings.previous_days
```

### `tgcs summarize`

```bash
tgcs summarize --all # summarize all enabled groups
tgcs summarize --all --tg # + send Telegram notifications
tgcs summarize --chat GROUP_NAME # single group
tgcs summarize --all --days 3 # last 3 days only
tgcs summarize preview # render template with sample data (for testing)
```

### `tgcs threads`

```bash
# List threads (most recent date by default)
tgcs threads ls --chat GROUP_NAME
tgcs threads ls --chat GROUP_NAME --date YYYY-MM-DD
tgcs threads ls --chat GROUP_NAME --from YYYY-MM-DD --to YYYY-MM-DD
tgcs threads ls --chat GROUP_NAME --days N
tgcs threads ls --chat GROUP_NAME --days 3 --min-msgs 10 # filter (default: 4)
tgcs threads ls --chat GROUP_NAME --sort count # sort by msg count

# Group can be specified by number (from chats ls)
tgcs threads ls --chat 1

# Show all messages in a thread (spans date boundaries)
tgcs threads show --chat GROUP_NAME ROOT_ID

# Export threads to individual JSONL files
tgcs threads dump --chat GROUP_NAME
tgcs threads dump --chat GROUP_NAME --min-msgs 10 --force
```

Output of `threads ls`:
```
DATE        MESSAGES  ROOT_ID  URL
2025-05-22        42   629942  https://t.me/example_group/629942/
2025-05-22        28   629800  https://t.me/example_group/629800/
```

## Presenting thread summaries

When showing thread data to the user (from `threads ls` output, `summary.md`, or any other source), always format it as markdown matching the `tgcs notification` style (default template):

```
#group_name
Date: YYYY-MM-DD

- Thread name ([N](https://t.me/group/ROOT_ID/))
- Another thread ([M](https://t.me/group/ROOT_ID2/))
```

Output format is a Mustache template at `~/.config/tgcs/summary.mustache` (created by `tgcs init`, picked up automatically). Edit it, then run `tgcs summarize preview` to test.

Available Mustache variables:
- `{{group_name}}` — Telegram group name
- `{{date}}` — date in `YYYY-MM-DD` format
- `{{#threads}}` / `{{/threads}}` — loop over threads
  - `{{name}}` — thread name (from LLM)
  - `{{count}}` — message count
  - `{{url}}` — deep link to the thread

- **Thread name**: use the name from `summary.md`. If `summary.md` is not available, ask the user to run `tgcs summarize --chat GROUP_NAME` first before presenting the report.
- **N**: message count (MESSAGES column from `threads ls`).
- **Link**: URL from `threads ls` output — points to the first message in the thread.
- For multiple dates: repeat the header block for each date.

---

Output of `threads show`:
```
[629942] user123: Here is the first message text
[629943] other_user: Reply text here
```

### `tgcs notification`

```bash
tgcs notification --all # notify all groups
tgcs notification --chat GROUP_NAME # single group
tgcs notification --all --days 3
```

---

## Data Directory Layout

Base: `~/.local/share/tgcs/` — **configurable** via `data_dir` in `~/.config/tgcs/config.toml`:
```toml
data_dir = "/path/to/your/data"
```

```
{group_name}/
  metadata.json # id, title, username, link_prefix, enabled
  additional_requirements.md # custom prompt injected into LLM
  history/
    {YYYY-MM-DD}/
      history.jsonl # one JSON message per line
      summary.md # final markdown summary
      thread_names_raw.txt # raw LLM response (resumable cache)
      processing.lock # lock while processing
      notified # marker: summary sent to Telegram
  threads/
    {YYYY-MM-DD}-{root_id}.jsonl # exported by threads dump

bot.session # Telegram bot session
user.session / {phone}.session # Telegram user session
```

### Message format (`history.jsonl`)

Field names mostly follow the [Telegram Desktop export
format](https://core.telegram.org/import-export).

```json
{"id": 629918, "type": "message", "date": "2025-05-22T02:39:52+00:00",
 "from_username": "user_a", "from_id": "user100000000", "text": "Text here",
 "reply_to_message_id": 629899, "reactions": {"👍": 3}}
```

### Summary format (`summary.md`)

```markdown
#example_group
Date: 2025-07-24

- Thread topic name ([6](https://t.me/example_group/641337/))
- Another topic ([5](https://t.me/example_group/641383/))
```

### Group metadata (`metadata.json`)

```json
{"id": 1358715993, "title": "Group Title", "username": "group_username",
 "link_prefix": "https://t.me/group_username/", "enabled": true,
 "access_hash": 4659813876910449785}
```

---

## Answering questions about chat content

Data is usually **already downloaded** — answer by grepping local files, not by running `chats download` (slow, can hit a DB lock).

**1. Check freshness first.** `tgcs chats ls` shows a `LAST MESSAGE` column per group:

```
NAME                         STATUS    LAST MESSAGE      MESSAGES
example_group                 enabled   2026-05-29 22:45     48849
```

If `LAST MESSAGE` for the target group is **not today**, the local data is stale — tell the user to download first and stop:

```bash
tgcs chats download GROUP_NAME --days N # N = days back to cover the question
```

**2. If fresh, grep the group's data** (see "Searching History" below).

## Searching History

`history.jsonl` is one JSON object per line — use `grep` + `jq`.

```bash
# Data dir shorthand — adjust path to actual data_dir
DATA=~/.local/share/tgcs

# Keyword search in one group (all dates)
grep -i "keyword" $DATA/example_group/history/*/history.jsonl | jq .

# Keyword search across all groups
grep -ri "keyword" $DATA/*/history/*/history.jsonl | jq .

# All messages from a user in one group
jq 'select(.from_username == "username")' $DATA/example_group/history/*/history.jsonl

# Count messages per date
wc -l $DATA/example_group/history/*/history.jsonl

# Find a specific message by ID
jq 'select(.id == 629942)' $DATA/example_group/history/*/history.jsonl
```

---

## References

- Instruction how to get telegram api_id and api_hash. [references/obtaining_api_id.md](references/obtaining_api_id.md)
