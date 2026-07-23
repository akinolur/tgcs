# tgcs

Download Telegram group chat history and generate concise, LLM-powered per-thread
summaries - optionally delivered back to you as a Telegram notification.

## Features

- Download group history, organized by date
- Group messages into threads by reply chains
- LLM thread names and summaries (OpenAI-compatible APIs, e.g. Groq)
- Customizable Mustache output templates
- Optional Telegram bot notifications
- QR-code login, no phone number required

## Requirements

- Python >= 3.11 and [uv](https://docs.astral.sh/uv/)
- Telegram `api_id` / `api_hash` (https://my.telegram.org)
- [Optionally] An OpenAI-compatible LLM API key

## Install

```bash
git clone https://github.com/akinolur/tgcs.git && cd tgcs
# if you want just to download chats history:
uv tool install --editable .
# if you want to do daily summaries:
uv tool install --editable ".[summary]"
```

## Quick Start

Get your Telegram's api_id and api_hash. Instruction: https://core.telegram.org/api/obtaining_api_id

```bash
tgcs init                  # create config + templates
# edit ~/.config/tgcs/config.toml with your credentials (api_id, api_hash)
tgcs auth login            # authenticate (QR code)
tgcs chats update          # fetch chat metadata
tgcs chats download --all  # download history
tgcs summarize             # generate summaries
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
