import json
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import typer

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


def _last_dt(path_manager: "FilePathManager", group_name: str, dates: list[str]) -> str:
    if not dates:
        return "-"
    history_file = path_manager.date_history_path(group_name, dates[-1])
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


def _count_lines(history_file: str) -> int:
    with open(history_file, "rb") as f:
        return sum(1 for line in f if line.strip())


def _msg_count(
    path_manager: "FilePathManager", group_name: str, dates: list[str]
) -> int:
    total = 0
    for date in dates:
        history_file = path_manager.date_history_path(group_name, date)
        if not os.path.exists(history_file):
            continue
        total += _count_lines(history_file)
    return total


def _get_chats(path_manager: "FilePathManager") -> None:
    all_groups = sorted(path_manager.all_groups_list())

    rows = []
    for name, downloading_enabled, summarization_enabled in all_groups:
        dates = _dates(path_manager, name)
        rows.append(
            (
                name,
                "on" if downloading_enabled else "off",
                "on" if summarization_enabled else "off",
                _last_dt(path_manager, name, dates),
                _msg_count(path_manager, name, dates),
            )
        )
    col1 = max(len("NAME"), *(len(r[0]) for r in rows)) if rows else len("NAME")
    col5 = (
        max(len("MESSAGES"), *(len(str(r[4])) for r in rows))
        if rows
        else len("MESSAGES")
    )
    print(
        f"{'NAME':<{col1}}  {'DOWNLOAD':<8}  {'SUMMARY':<7}  {'LAST MESSAGE':<16}  {'MESSAGES':>{col5}}"  # noqa: E501
    )
    for name, download, summary, last_dt, msg_count in rows:
        print(
            f"{name:<{col1}}  {download:<8}  {summary:<7}  {last_dt:<16}  {msg_count:>{col5}}"  # noqa: E501
        )


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
