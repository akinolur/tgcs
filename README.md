# tgcs

CLI for downloading Telegram group chat history and generating summaries.
Useful for a daily digest or as a data source for an AI agent.

## Features

- Incrementally download group history
- Group messages into threads by reply chains
- Simple data format, good for AI agent
- QR-code login, no phone number required
- Customizable Mustache output templates
- Telegram bot notifications to get daily summary
- LLM thread names and summaries (OpenAI-compatible APIs, e.g. Groq)

## Install

```bash
git clone https://github.com/akinolur/tgcs.git && cd tgcs
# if you want just to download chats history:
uv tool install --editable .
# if you want to do daily summaries:
uv tool install --editable ".[summary]"
```

## Quick Start

Get your Telegram's api_id and api_hash. [Instruction](https://core.telegram.org/api/obtaining_api_id)

```bash
tgcs init                  # create config + templates
# edit ~/.config/tgcs/config.toml with your credentials (api_id, api_hash)
tgcs auth login            # authenticate (QR code)
tgcs chats update          # fetch chat metadata
tgcs chats download --all  # download history
tgcs summarize --all       # generate summaries
```

Config lives in `~/.config/tgcs/config.toml` (set `[telegram]`, `[llm]`, and
`[telegram_bot]` sections). 
Data and telegram session files live in `~/.local/share/tgcs`.

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

## Install skill

The repo ships an agent skill (`.claude/skills/tgcs-guide`) that teaches coding agents
how to use tgcs and read its data.

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

