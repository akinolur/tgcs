# tgcs (telegram chats summary)

CLI to download the history of Telegram groups and private chats to local files.
Use it as a data source for an AI agent, or to get a daily digest.

## Features

- Incremental download of messages and reactions
- Messages grouped into threads by reply chains
- Plain JSONL files, easy for agents and `jq`
- QR-code login, no phone number required
- Optional LLM summaries, sent to you by a Telegram bot

## Security note

tgcs uses a Telegram user session. The session gives full access to your account until you revoke it. Keep `~/.local/share/tgcs/*.session` private. To uninstall, delete the session files and revoke the session in Telegram > Settings > Devices.

Telegram can limit requests ([`FLOOD_WAIT`](https://core.telegram.org/api/errors#420-flood)) and can [ban](https://core.telegram.org/api/obtaining_api_id#using-the-api-id) accounts that abuse the API. Obey the [API Terms of Service](https://core.telegram.org/api/terms).

## Install

```bash
git clone https://github.com/akinolur/tgcs.git && cd tgcs
uv tool install --editable .
```

## Quick start

Get your `api_id` and `api_hash`: [instructions](https://core.telegram.org/api/obtaining_api_id).

```bash
tgcs init                            # create ~/.config/tgcs/config.toml
# set api_id and api_hash in the config
tgcs auth login                      # scan the QR code
# in Telegram, put the chats into the folder "tgcs"
tgcs chats update                    # find chats in the folder
tgcs chats download --all --days 30  # download the last 30 days
tgcs threads ls --chat CHAT_NAME     # show threads
```

Data is in `~/.local/share/tgcs`. Add `--help` to any command.

## Usage ideas

- Run `tgcs chats update && tgcs chats download --all --days 7` every day with cron
- Give the data to a personal agent (Hermes, nanobot) with the tgcs-guide skill. Ask it about your chats
- Let your agent make its own periodic summaries from the threads

## Agent skill

The skill `skills/tgcs-guide` tells an agent how to set up and use tgcs, and how to read its data. For all other setup details, ask your agent.

```bash
npx skills add akinolur/tgcs -s tgcs-guide              # Claude Code, Codex, and others
hermes skills install akinolur/tgcs/skills/tgcs-guide   # Hermes
```

## Summaries

tgcs can make a daily summary of each group: an LLM gives a name to each thread, and a Telegram bot sends you the result. This part is optional and needs extra dependencies:

```bash
uv tool install --editable ".[summary]"
```

Then set the `[llm]` and `[telegram_bot]` sections in the config and run:

```bash
tgcs summarize --all --tg --days 7
```

Any OpenAI-compatible API works. The Groq free tier is enough for daily summaries.

Daily cron example:

```
0 9 * * * (tgcs chats update && tgcs chats download --all --days 7 && tgcs summarize --all --tg --days 7) > /tmp/tgcs.log 2>&1
```
