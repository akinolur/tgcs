import json
import logging
import os
from datetime import datetime, timezone

import typer

from tgcs.container import container

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)


@app.command(name="ls")
def get_chats():
    """List known chats with status and message counts."""
    all_groups = sorted(container.path_manager.all_groups_list())

    def _dates(group_name):
        history_path = container.path_manager.history_folder_path(group_name)
        if not os.path.exists(history_path):
            return []
        return sorted(
            d
            for d in os.listdir(history_path)
            if not d.startswith(".") and os.path.isdir(os.path.join(history_path, d))
        )

    def _last_dt(group_name, dates):
        if not dates:
            return "—"
        history_file = container.path_manager.date_history_path(group_name, dates[-1])
        if not os.path.exists(history_file):
            return "—"
        with open(history_file, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return "—"
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
        return "—"

    def _msg_count(group_name, dates):
        total = 0
        for date in dates:
            history_file = container.path_manager.date_history_path(group_name, date)
            if not os.path.exists(history_file):
                continue
            with open(history_file, "rb") as f:
                total += sum(1 for line in f if line.strip())
        return total

    rows = []
    for name, is_enabled in all_groups:
        dates = _dates(name)
        rows.append(
            (
                name,
                "enabled" if is_enabled else "disabled",
                _last_dt(name, dates),
                _msg_count(name, dates),
            )
        )
    col1 = max(len("NAME"), *(len(r[0]) for r in rows)) if rows else len("NAME")
    col2 = max(len("STATUS"), *(len(r[1]) for r in rows)) if rows else len("STATUS")
    col4 = (
        max(len("MESSAGES"), *(len(str(r[3])) for r in rows))
        if rows
        else len("MESSAGES")
    )
    print(
        f"{'NAME':<{col1}}  {'STATUS':<{col2}}  {'LAST MESSAGE':<16}  {'MESSAGES':>{col4}}"  # noqa: E501
    )
    for name, status, last_dt, msg_count in rows:
        print(f"{name:<{col1}}  {status:<{col2}}  {last_dt:<16}  {msg_count:>{col4}}")


@app.command(name="update")
def get_chats_metadata():
    """Fetch chat metadata from Telegram folder."""
    if not container.cfg.group_folder:
        from tgcs.app_config import default_config_path

        typer.echo(f"telegram.group_folder is not set. Edit {default_config_path()}.")
        raise typer.Exit(code=1)
    from tgcs.telegram.downloader import TelegramChatHistoryDownloader

    tg_downloader = TelegramChatHistoryDownloader(
        container.user_client, container.path_manager
    )
    try:
        group_names_dict: dict[str, bool] = tg_downloader.download_chat_metadata(
            container.cfg.group_folder
        )
        rows = _response_rows(list(group_names_dict.keys()))
        logger.info("Metadata downloaded:\n" + "\n".join(rows))
    finally:
        tg_downloader.disconnect()


def _response_rows(group_names: list[str]):
    rows = []
    for i, group_name in enumerate(group_names, start=1):
        rows.append(f"[{i}] {group_name}")
    return rows


@app.command(name="download")
def download(
    group_name: str = typer.Argument(None),
    all: bool = typer.Option(False, "--all", "-a"),
    days: int = typer.Option(
        None,
        "--days",
        "-d",
        help="Number of previous days to download (overrides PREVIOUS_DAYS env var)",
    ),
):
    """Download recent message history for one or all chats."""
    previous_days = days if days is not None else container.cfg.previous_days
    if not group_name and not all:
        typer.echo("You must specify either a group name or --all.")
        raise typer.Exit(code=1)
    elif all:
        logger.info("Downloading all groups")
        _download_all(previous_days)
    else:
        logger.info(f"Downloading group: {group_name}")
        _download_group(group_name, previous_days)


def _chat_peer_from_metadata(metadata: dict):
    from telethon.tl.types import InputPeerChannel

    chat_id = metadata["id"]
    access_hash = metadata.get("access_hash", 0)
    return InputPeerChannel(chat_id, access_hash) if access_hash else chat_id


def _download_group(group_name: str, previous_days: int | None = None):
    from tgcs.telegram.downloader import TelegramChatHistoryDownloader

    days = previous_days if previous_days is not None else container.cfg.previous_days
    tg_downloader = TelegramChatHistoryDownloader(
        container.user_client, container.path_manager
    )
    try:
        metadata_path = container.path_manager.group_metadata_path(group_name)
        with open(metadata_path) as f:
            metadata = json.load(f)
        name, count = tg_downloader.download_chat_history(
            _chat_peer_from_metadata(metadata), days
        )
        logger.info(f"{name}: {count} new messages")
    except Exception as ex:
        logger.error(str(ex))
    finally:
        tg_downloader.disconnect()


def _download_all(previous_days: int | None = None):
    from tgcs.telegram.downloader import TelegramChatHistoryDownloader

    days = previous_days if previous_days is not None else container.cfg.previous_days
    tg_downloader = TelegramChatHistoryDownloader(
        container.user_client, container.path_manager
    )
    group_names = container.path_manager.groups_list()
    try:
        for tg_chat in group_names:
            if not tg_chat:
                continue
            metadata_path = container.path_manager.group_metadata_path(tg_chat)
            with open(metadata_path) as f:
                metadata = json.load(f)
            name, count = tg_downloader.download_chat_history(
                _chat_peer_from_metadata(metadata), days
            )
            logger.info(f"{name}: {count} new messages")
    except Exception as ex:
        logger.error(str(ex))
    finally:
        tg_downloader.disconnect()
