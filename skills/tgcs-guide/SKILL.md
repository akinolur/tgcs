---
name: tgcs-guide
description: Use when user asks about the "tgcs" project - installation, setup, configuration, CLI usage, or actual Telegram chat data (groups and private chats - messages, threads, summaries, activity)
---

## Setup

1. Install the core: `git clone https://github.com/akinolur/tgcs.git && cd tgcs && uv tool install --editable .`
2. Get `api_id` and `api_hash`: [references/obtaining_api_id.md](references/obtaining_api_id.md)
3. `tgcs init` - write the default config
4. Set `api_id` and `api_hash` in `~/.config/tgcs/config.toml`
5. `tgcs auth login` - scan the QR code in Telegram (Settings > Devices > Scan QR). It asks for the 2FA password if set. `tgcs auth status` shows the result
6. In the Telegram client, make a folder `tgcs` (or the `group_folder` value) and put groups and private chats into it
7. `tgcs chats update` - find the chats in the folder
8. `tgcs chats download --all --days 30` - first download

Daily download with cron:
```
0 9 * * * (tgcs chats update && tgcs chats download --all --days 7) > /tmp/tgcs.log 2>&1
```

Summaries are optional, see [references/summarization.md](references/summarization.md).

## Configuration

**Config file:** `~/.config/tgcs/config.toml` (XDG; override with `--config PATH`)

```toml
# data_dir = "~/.local/share/tgcs" # default

[telegram]
api_id = 12345678
api_hash = "abc123..."
# group_folder = "tgcs" # Telegram folder to sync chats from

[settings]
# previous_days = 0 # default download window: 0 = yesterday and today
# layout = "daily" # default history layout: "daily" or "single"
```

The `[telegram_bot]` and `[llm]` sections and `summary_template` are for summarization only, see [references/summarization.md](references/summarization.md).

---

## CLI Reference

Entry point: `tgcs`
Global options: `--version/-V`, `--config/-c PATH`, `--verbose/-v`. Add `--help` to any command.

### `tgcs auth`

```bash
tgcs auth login # QR-code login
tgcs auth status # show the session status
```

### `tgcs chats`

```bash
tgcs chats ls # list chats with status, last message, msg counts
tgcs chats ls --format json
tgcs chats update # fetch chat metadata from the Telegram folder
tgcs chats download CHAT_NAME # download history for one chat
tgcs chats download --all # download all enabled chats
tgcs chats download --all --days 7 # override settings.previous_days
tgcs chats layout --chat CHAT_NAME # show current layout (daily/single)
tgcs chats layout --chat CHAT_NAME single # switch to single-file layout
```

`chats download` exits with code 1 if one or more chats fail.

### `tgcs threads`

```bash
# List threads (most recent date by default)
tgcs threads ls --chat CHAT_NAME
tgcs threads ls --chat CHAT_NAME --date YYYY-MM-DD
tgcs threads ls --chat CHAT_NAME --from YYYY-MM-DD --to YYYY-MM-DD
tgcs threads ls --chat CHAT_NAME --days N
tgcs threads ls --chat CHAT_NAME --days 3 --min-msgs 10 # filter (default: 4)
tgcs threads ls --chat CHAT_NAME --sort count # sort by msg count

# Show all messages in a thread (spans date boundaries)
tgcs threads show --chat CHAT_NAME ROOT_ID

# Export threads to individual JSONL files
tgcs threads dump --chat CHAT_NAME
tgcs threads dump --chat CHAT_NAME --min-msgs 10 --force
```

Output of `threads ls`:
```
DATE        MESSAGES  ROOT_ID  URL
2025-05-22        42   629942  https://t.me/example_group/629942/
2025-05-22        28   629800  https://t.me/example_group/629800/
```

Output of `threads show`:
```
[629942] user123: Here is the first message text
[629943] other_user: Reply text here
```

---

## Data Directory Layout

Base: `~/.local/share/tgcs/` - change it with `data_dir` in the config.

```
user.session # Telegram user session
bot.session # Telegram bot session (notifications)
.metadata.lock
{chat_name}/ # one folder per chat
```

Each chat uses one of two layouts: `metadata.json` `layout` key, else
`[settings] layout` in the config; default `daily`. Check or change it with
`tgcs chats layout --chat CHAT_NAME`.

### `daily` layout (default)

Splits the history into one folder per date. Use for active chats.

```
{chat_name}/
  metadata.json # id, title, username, link_prefix, downloading_enabled, summarization_enabled, layout
  additional_requirements.md # optional custom prompt for the LLM
  history/
    raw_chat_history.jsonl # full raw download, all dates
    {YYYY-MM-DD}/
      history.jsonl # one JSON message per line
      summary.md # final markdown summary
      thread_names_raw.txt # raw LLM response (resumable cache)
      processing.lock # lock while processing
      notified # marker: summary sent to Telegram
  threads/
    {YYYY-MM-DD}-{root_id}.jsonl # exported by threads dump
```

### `single` layout

For low-traffic chats (e.g. private 1-1 chats), where per-day folders would
each hold a message or two. The whole chat stays in one raw file. Summarization
skips `single` chats.

```
{chat_name}/
  metadata.json
  history/
    raw_chat_history.jsonl # entire chat history, never split
  threads/
    all-{root_id}.jsonl # exported by threads dump
```

Switching back to `daily` (`tgcs chats layout --chat NAME daily`) rebuilds
every date folder from the raw file. Switching `daily` -> `single` does not
delete existing date folders.

### Message format (`history.jsonl`, `raw_chat_history.jsonl`)

Field names mostly follow the [Telegram Desktop export
format](https://core.telegram.org/import-export).

```json
{"id": 629918, "type": "message", "date": "2025-05-22T02:39:52+00:00",
 "from_username": "user_a", "from_id": "user100000000", "text": "Text here",
 "reply_to_message_id": 629899, "reactions": {"👍": 3}}
```

### Chat metadata (`metadata.json`)

```json
{"id": 1358715993, "title": "Group Title", "username": "group_username",
 "link_prefix": "https://t.me/group_username/", "access_hash": 4659813876910449785,
 "downloading_enabled": true, "summarization_enabled": true, "layout": "daily"}
```

- `downloading_enabled` - managed by `tgcs chats update` from Telegram folder membership
- `summarization_enabled` - user-owned, never changed by `chats update`
- `layout` - `daily` or `single`

---

## Answering questions about chat content

Data is usually **already downloaded**. Answer by grepping local files, not by running `chats download` (slow, can hit a DB lock).

**1. Check freshness first.** `tgcs chats ls` shows a `LAST MESSAGE` column per chat:

```
NAME                         STATUS    LAST MESSAGE      MESSAGES
example_group                 enabled   2026-05-29 22:45     48849
```

If `LAST MESSAGE` for the target chat is **not today**, the local data is stale. Tell the user to download first and stop:

```bash
tgcs chats download CHAT_NAME --days N # N = days back to cover the question
```

**2. If fresh, grep the chat's data** (see "Searching History" below).

## Searching History

History files are one JSON object per line. Use `grep` + `jq`.
`raw_chat_history.jsonl` has all messages in both layouts.

```bash
DATA=~/.local/share/tgcs # adjust to actual data_dir

# Keyword search in one chat
grep -i "keyword" $DATA/example_group/history/raw_chat_history.jsonl | jq .

# Keyword search across all chats
grep -i "keyword" $DATA/*/history/raw_chat_history.jsonl

# All messages from a user in one chat
jq 'select(.from_username == "username")' $DATA/example_group/history/raw_chat_history.jsonl

# Count messages per date (daily layout)
wc -l $DATA/example_group/history/*/history.jsonl

# Find a specific message by ID
jq 'select(.id == 629942)' $DATA/example_group/history/raw_chat_history.jsonl
```

---

## Summarization

Optional. For setup, config, commands, and how to present summaries to the user, read [references/summarization.md](references/summarization.md).

---

## Installing this skill in other agents

```bash
npx skills add akinolur/tgcs -s tgcs-guide # pick agents interactively
npx skills add akinolur/tgcs -s tgcs-guide -a claude -y # one agent
hermes skills install akinolur/tgcs/skills/tgcs-guide # Hermes
npx skills add akinolur/tgcs -s tgcs-guide -a universal -g -y # ~/.config/agents/skills
ln -s ~/.config/agents/skills/tgcs-guide ~/.nanobot/workspace/skills/tgcs-guide # nanobot
```

Refresh with `npx skills update`.
