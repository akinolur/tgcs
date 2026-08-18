import json
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, assert_never

import typer

from tgcs.layouts import Layout

if TYPE_CHECKING:
    from telethon.sync import TelegramClient

    from tgcs.container import Container
    from tgcs.paths import FilePathManager

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)


@app.command(name="ls")
def get_chats(ctx: typer.Context):
    """List known chats with status and message counts."""
    container: "Container" = ctx.obj
    _get_chats(container.path_manager)


def _dates(path_manager: "FilePathManager", group_name: str) -> list[str]:
    history_path = path_manager.history_folder_path(group_name)
    if not os.path.exists(history_path):
        return []
    return sorted(
        d
        for d in os.listdir(history_path)
        if not d.startswith(".") and os.path.isdir(os.path.join(history_path, d))
    )


def _history_files(
    path_manager: "FilePathManager", group_name: str, layout: Layout
) -> list[str]:
    """History files of one chat, oldest first.

    The single layout keeps everything in the raw file; the daily layout has one
    file per date folder.
    """
    if layout is Layout.SINGLE:
        raw_path = path_manager.raw_history_path(group_name)
        return [raw_path] if os.path.exists(raw_path) else []
    elif layout is Layout.DAILY:
        return [
            path_manager.date_history_path(group_name, date)
            for date in _dates(path_manager, group_name)
        ]
    else:
        assert_never(layout)


def _last_dt(history_files: list[str]) -> str:
    if not history_files:
        return "-"
    history_file = history_files[-1]
    if not os.path.exists(history_file):
        return "-"
    with open(history_file, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        if size == 0:
            return "-"
        f.seek(-min(4096, size), 2)
        chunk = f.read()
    for line in reversed(chunk.split(b"\n")):
        line = line.strip()
        if line:
            try:
                raw = json.loads(line).get("date")
                if not raw:
                    continue
                dt = datetime.fromisoformat(raw).astimezone(timezone.utc)
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                continue
    return "-"


_COUNT_CHUNK = 1 << 20


def _count_lines(history_file: str) -> int:
    """Count records the way `wc -l` does, plus a final unterminated one."""
    total = 0
    tail = b""
    with open(history_file, "rb") as f:
        while chunk := f.read(_COUNT_CHUNK):
            total += chunk.count(b"\n")
            tail = chunk
    if tail and not tail.endswith(b"\n"):
        total += 1
    return total


def _msg_count(history_files: list[str]) -> int:
    total = 0
    for history_file in history_files:
        if not os.path.exists(history_file):
            continue
        total += _count_lines(history_file)
    return total


def _get_chats(path_manager: "FilePathManager") -> None:
    all_groups = sorted(path_manager.all_groups_list())

    rows = []
    for name, downloading_enabled, summarization_enabled in all_groups:
        layout = path_manager.layout(name)
        history_files = _history_files(path_manager, name, layout)
        rows.append(
            (
                name,
                str(layout),
                "on" if downloading_enabled else "off",
                "on" if summarization_enabled else "off",
                _last_dt(history_files),
                _msg_count(history_files),
            )
        )
    col1 = max(len("NAME"), *(len(r[0]) for r in rows)) if rows else len("NAME")
    col6 = (
        max(len("MESSAGES"), *(len(str(r[5])) for r in rows))
        if rows
        else len("MESSAGES")
    )
    print(
        f"{'NAME':<{col1}}  {'LAYOUT':<6}  {'DOWNLOAD':<8}  {'SUMMARY':<7}  {'LAST MESSAGE':<16}  {'MESSAGES':>{col6}}"  # noqa: E501
    )
    for name, layout, download, summary, last_dt, msg_count in rows:
        print(
            f"{name:<{col1}}  {layout:<6}  {download:<8}  {summary:<7}  {last_dt:<16}  {msg_count:>{col6}}"  # noqa: E501
        )


@app.command(name="layout")
def chat_layout(
    ctx: typer.Context,
    name: str = typer.Option(..., "--chat", "-g", help="chat name"),
    value: Optional[Layout] = typer.Argument(
        None, help="new layout; omit to show the current one"
    ),
):
    """Show or set the history layout of a chat."""
    container: "Container" = ctx.obj
    path_manager = container.path_manager
    if value is None:
        typer.echo(str(path_manager.layout(name)))
        return
    previous = path_manager.layout(name)
    if not path_manager.set_layout(name, value):
        typer.echo(f"{name}: unknown chat. Run 'tgcs chats update' first.")
        raise typer.Exit(code=1)
    typer.echo(f"{name}: layout set to {str(value)}")
    if previous is Layout.SINGLE and value is Layout.DAILY:
        # the single layout never wrote date folders, and the next download only
        # splits its own window, so backfill the whole raw file now
        typer.echo(
            f"Rebuilding date folders from {path_manager.raw_history_path(name)}"
        )
        _split_raw_history(path_manager, name)


def _split_raw_history(path_manager: "FilePathManager", group_name: str) -> None:
    # imported lazily: splitting is pure file work, but the module pulls in telethon
    from tgcs.telegram.downloader import TelegramChatHistoryDownloader

    downloader = TelegramChatHistoryDownloader(client=None, path_manager=path_manager)
    downloader._create_daily_chat_history_from_raw_history(group_name)


@app.command(name="update")
def get_chats_metadata(ctx: typer.Context):
    """Fetch chat metadata from Telegram folder."""
    container: "Container" = ctx.obj
    group_folder = container.cfg.group_folder
    if not group_folder:
        typer.echo(f"telegram.group_folder is not set. Edit {container.config_path}.")
        raise typer.Exit(code=1)
    from tgcs.telegram.downloader import FolderNotFoundError

    try:
        _get_chats_metadata(group_folder, container.user_client, container.path_manager)
    except FolderNotFoundError as ex:
        typer.echo(str(ex))
        typer.echo(f"Fix telegram.group_folder in {container.config_path}.")
        raise typer.Exit(code=1) from ex


def _get_chats_metadata(
    group_folder: str,
    user_client: "TelegramClient",
    path_manager: "FilePathManager",
) -> None:
    from tgcs.telegram.downloader import TelegramChatHistoryDownloader

    tg_downloader = TelegramChatHistoryDownloader(user_client, path_manager)
    group_names_dict: dict[str, bool] = tg_downloader.download_chat_metadata(
        group_folder
    )
    rows = _response_rows(list(group_names_dict.keys()))
    logger.info("Metadata downloaded:\n" + "\n".join(rows))


def _response_rows(group_names: list[str]):
    rows = []
    for i, group_name in enumerate(group_names, start=1):
        rows.append(f"[{i}] {group_name}")
    return rows


@app.command(name="download")
def download(
    ctx: typer.Context,
    group_name: str = typer.Argument(None),
    all: bool = typer.Option(False, "--all", "-a"),
    days: int = typer.Option(
        None,
        "--days",
        "-d",
        min=0,
        help="Number of previous days to download (overrides settings.previous_days)",
    ),
):
    """Download recent message history for one or all chats."""
    container: "Container" = ctx.obj
    previous_days = days if days is not None else container.cfg.previous_days
    if not group_name and not all:
        typer.echo("You must specify either a group name or --all.")
        raise typer.Exit(code=1)
    elif all:
        logger.info("Downloading all groups")
        failed = _download_all(
            user_client=container.user_client,
            path_manager=container.path_manager,
            default_previous_days=container.cfg.previous_days,
            previous_days=previous_days,
        )
    else:
        logger.info(f"Downloading group: {group_name}")
        failed = _download_group(
            user_client=container.user_client,
            path_manager=container.path_manager,
            group_name=group_name,
            previous_days=previous_days,
            default_previous_days=container.cfg.previous_days,
        )
    if failed:
        # cron must not see a green run when chats were skipped
        typer.echo(f"{failed} chat(s) failed to download.", err=True)
        raise typer.Exit(code=1)


def _chat_peer_from_metadata(metadata: dict):
    from telethon.tl.types import InputPeerChannel

    chat_id = metadata["id"]
    access_hash = metadata.get("access_hash", 0)
    return InputPeerChannel(chat_id, access_hash) if access_hash else chat_id


def _download_one(
    tg_downloader, path_manager: "FilePathManager", group_name: str, days: int
) -> bool:
    """Download one chat. Never raises, so one bad chat cannot stop the rest."""
    metadata_path = path_manager.group_metadata_path(group_name)
    if not os.path.exists(metadata_path):
        logger.error(f"{group_name}: unknown chat. Run 'tgcs chats update' first.")
        return False
    try:
        with open(metadata_path) as f:
            metadata = json.load(f)
        name, count = tg_downloader.download_chat_history(
            _chat_peer_from_metadata(metadata), days
        )
        logger.info(f"{name}: {count} new messages")
        return True
    except Exception as ex:
        logger.error(f"{group_name}: {ex}")
        return False


def _download_group(
    user_client: "TelegramClient",
    path_manager: "FilePathManager",
    group_name: str,
    previous_days: int | None = None,
    default_previous_days: int = 0,
) -> int:
    """Returns the number of chats that failed."""
    from tgcs.telegram.downloader import TelegramChatHistoryDownloader

    days = previous_days if previous_days is not None else default_previous_days
    tg_downloader = TelegramChatHistoryDownloader(user_client, path_manager)
    return 0 if _download_one(tg_downloader, path_manager, group_name, days) else 1


def _download_all(
    user_client: "TelegramClient",
    path_manager: "FilePathManager",
    default_previous_days: int,
    previous_days: int | None = None,
) -> int:
    """Returns the number of chats that failed."""
    from tgcs.telegram.downloader import TelegramChatHistoryDownloader

    days = previous_days if previous_days is not None else default_previous_days
    tg_downloader = TelegramChatHistoryDownloader(user_client, path_manager)
    group_names = [name for name in path_manager.download_groups_list() if name]
    if not group_names:
        logger.warning("No chats with downloading enabled. Run 'tgcs chats update'.")
        return 0
    failed = 0
    for tg_chat in group_names:
        if not _download_one(tg_downloader, path_manager, tg_chat, days):
            failed += 1
    return failed
