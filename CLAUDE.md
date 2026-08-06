## Project Overview

Telegram chat history downloader and summarizer. See `README.md` for setup, commands,
and a high-level overview.

## Architecture

The project follows a workflow-based architecture:

1. **Data Collection**: `TelegramChatHistoryDownloader` fetches chat history from Telegram groups and stores it in JSON format, organized by date.

2. **Data Processing**: `SummaryCreator` processes the downloaded data, identifying which dates need to be summarized.

3. **Workflow Execution**: A configurable pipeline (`workflows/`) processes each date:
   - `PrepareThreadsStep`: Organizes messages into threads based on reply chains
   - `GenerateThreadsNameStep`: Uses an LLM to generate descriptive names for each thread
   - `RepairJsonStep`: Ensures JSON output from the LLM is valid
   - `PostProcessStep`: Formats the final summary using a Mustache template (`~/.config/tgcs/summary.mustache`)
   - `TgNotificationStep` (optional): Sends notifications via Telegram

4. **File Management**: `FilePathManager` handles all file paths and directory structure.

Data layout:
```
data/{group_name}/
  metadata.json
  additional_requirements.md
  history/{date}/
    history.json
    summary.md
    lock
```

`metadata.json` holds two independent flags, both default `true`:
- `downloading_enabled`. managed by `chats update` from Telegram folder membership
- `summarization_enabled`. user-owned, never changed by `chats update`

## Workflow System

Each step in `workflows/` implements the `Step` interface with a `process` method that
transforms the data. When modifying the project, consider whether your changes fit into
an existing workflow step or if a new step is needed.
