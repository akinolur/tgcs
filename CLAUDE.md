## Project Overview

Telegram chat history downloader and summarizer

## General rules

- respect XDG specification
- write concrete default values to the config during `tgcs init`, such as `# group_folder = "tgcs"`, instead of empty placeholders
- at the CLI layer, load only the dependencies required by the selected command; load optional dependencies lazily and only after validation
- prefer focused, compact solutions with a small blast radius

## Architecture

Project features can be divided into 2 groups:
- core: cli, telegram integration, work with history
- summarization
These groups must be strictly divided and almost independent. User must be able to install core dependencies without summarization dependencies and use core cli commands.

**File Management**: `FilePathManager` handles all file paths and directory structure.

Each chat picks one of two history layouts (`Layout` in `layouts.py`), from its own
`metadata.json` `layout` key or, when absent, `[settings] layout` in the config.

`daily` (the default) splits the raw history into one folder per date:
```
{data_dir}/
  user.session
  bot.session
  {group_name}/
    metadata.json
    additional_requirements.md
    history/
      raw_chat_history.jsonl
      {date}/
        history.jsonl
        summary.md
        thread_names_raw.txt
        processing.lock
        notified
    threads/
      {date}-{root_id}.jsonl
```

`single` is for low-traffic chats, where per-day folders would each hold a message or two.
The download is never split: the whole chat stays in `raw_chat_history.jsonl`, and
`threads/` files are keyed `all-{root_id}.jsonl`. Summarization is a daily-layout feature:
`summarize` and `notification` skip a `single` chat outright, so date folders left over
from a previous `daily` life are never processed again. Switching back to `daily` rebuilds
every date folder from the raw file (`chats layout ... daily`), not just the last download
window.
```
{data_dir}/
  {group_name}/
    metadata.json
    history/
      raw_chat_history.jsonl
    threads/
      all-{root_id}.jsonl
```

`metadata.json` holds two independent flags, both default `true`:
- `downloading_enabled`. managed by `chats update` from Telegram folder membership
- `summarization_enabled`. user-owned, never changed by `chats update`

## Workflow System

**Summarization workflow parts:**
Workflow Execution: A configurable pipeline (`workflows/`) processes each date:
   - `PrepareThreadsStep`: Organizes messages into threads based on reply chains
   - `GenerateThreadsNameStep`: Uses an LLM to generate descriptive names for each thread
   - `RepairJsonStep`: Ensures JSON output from the LLM is valid
   - `PostProcessStep`: Formats the final summary using a Mustache template (`~/.config/tgcs/summary.mustache`)
   - `TgNotificationStep` (optional): Sends notifications via Telegram

Each step in `workflows/` implements the `Step` interface with a `process` method that transforms the data. When modifying the project, consider whether your changes fit into an existing workflow step or if a new step is needed.

## Testing approach
- for end-to-end tests, use a fake container with fake dependencies
- most unit tests need only fake dependencies, not a fake container
- avoid monkeypatching
