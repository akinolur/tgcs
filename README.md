# tgcs (telegram chats summary)

CLI for downloading Telegram group chat history and generating summaries.
Useful for a daily digest or as a data source for an AI agent.

## Features

- Incrementally download group history. Text and reactions
- Group messages into threads by reply chains
- Simple data format suitable for AI agents
- QR-code login, no phone number required
- Customizable Mustache output templates
- Telegram bot notifications for daily summaries
- LLM thread names and summaries (OpenAI-compatible APIs, e.g., Groq)

## Security note

tgcs uses a Telegram user session that can remain authorized until it is revoked. The session grants broad access to your Telegram account, so keep the `.session` file secure and never share it. When uninstalling tgcs, delete the file and revoke the session under Telegram Settings > Devices.

tgcs manages Telegram API requests automatically, but Telegram may still impose a [`FLOOD_WAIT`](https://core.telegram.org/api/errors#420-flood) interval before an action can be repeated. Telegram also warns that API abuse, such as flooding or spam, can result in a [permanent ban](https://core.telegram.org/api/obtaining_api_id#using-the-api-id). Use tgcs in accordance with Telegram's [API Terms of Service](https://core.telegram.org/api/terms).

## Install

```bash
git clone https://github.com/akinolur/tgcs.git && cd tgcs
uv tool install --editable ".[summary]"
# if you want just to download chats history:
uv tool install --editable .
```

## Quick Start

Get your Telegram `api_id` and `api_hash`. [Instructions](https://core.telegram.org/api/obtaining_api_id)

```bash
tgcs init                            # create config + templates
# edit ~/.config/tgcs/config.toml with your credentials (api_id, api_hash)
tgcs auth login                      # authenticate (QR code)
# in Telegram client: create folder "tgcs" and place some groups there
tgcs chats update                    # fetch chat metadata
tgcs chats download --all --days 30  # download the last 30 days
tgcs threads ls --chat GROUP_NAME    # display threads
```

Config lives in `~/.config/tgcs/config.toml` (set `[telegram]`, `[llm]`, and
`[telegram_bot]` sections).
Data and telegram session files live in `~/.local/share/tgcs`.

## Usage ideas

- set up daily cron-job with `0 9 * * * (tgcs chats update && tgcs chats download --all --days 7 && tgcs summarize --all --tg --days 7) > /tmp/tgcs.log 2>&1`
- set up personal agent like Hermes or nanobot and install tgcs-guide skill. Your agent can tell you about groups history
- for more flexibility: use tgcs only to fetch data and group it into threads, and tell your agent to do periodical summary
- if you use tgcs embedded summarization, you can create open Groq account. It's free tier is enough for daily summary


## Install skill

The repo ships an agent skill (`.claude/skills/tgcs-guide`) that teaches coding agents
how to configure, use tgcs and read its data.

Install with [skills CLI](https://github.com/vercel-labs/skills), which knows most agents

```bash
npx skills add akinolur/tgcs -s tgcs-guide # pick agents interactively
npx skills add akinolur/tgcs -s tgcs-guide -a claude -y # a specific agent, project-level
```

Refresh later with `npx skills update`.

### Any other location

The skill is just a folder with `SKILL.md`, so it works anywhere the agent reads skills
from. Either install into the vendor-neutral `universal` location and link it in:

```bash
npx skills add akinolur/tgcs -s tgcs-guide -a universal -g -y # ~/.config/agents/skills
ln -s ~/.config/agents/skills/tgcs-guide ~/.nanobot/workspace/skills/tgcs-guide # install to nanobot
```

## Commands

| Command | Description |
| --- | --- |
| `tgcs init` | Create default config and templates |
| `tgcs auth login` / `status` | Authenticate via QR code / show status |
| `tgcs chats update` / `ls` / `download` | Manage and download chat history |
| `tgcs threads ls` / `show` / `dump` | Browse message threads |
| `tgcs summarize` / `preview` | Generate summaries / preview template |
| `tgcs notification` | Send saved summaries via Telegram |

Add `--help` to any command. Global flags: `-c/--config`, `-v/--verbose`, `-V/--version`.
