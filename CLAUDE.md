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

Data layout:
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
