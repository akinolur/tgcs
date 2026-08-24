import json
import logging
import os
from collections import OrderedDict
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from telethon import functions
from telethon.tl import types

from tgcs.dates import today
from tgcs.layouts import Layout

# from telethon.errors import ChatsIdInvalidError

if TYPE_CHECKING:
    from telethon.sync import TelegramClient
    from telethon.tl.custom.message import Message

    from tgcs.paths import FilePathManager

logger = logging.getLogger(__name__)

_LAST_LINE_CHUNK = 4096


class FolderNotFoundError(Exception):
    """The configured telegram folder does not exist."""


def _extract_reactions(message: "Message") -> dict[str, int]:
    if message.reactions is None:
        return {}
    result = {}
    for rc in message.reactions.results:
        if isinstance(rc.reaction, types.ReactionEmoji):
            result[rc.reaction.emoticon] = rc.count
    return result


def _format_from_id(message: "Message") -> str | None:
    """Format the sender as the export does: "user123" / "channel123" / "chat123"."""
    peer = message.from_id
    if isinstance(peer, types.PeerUser):
        return f"user{peer.user_id}"
    if isinstance(peer, types.PeerChannel):
        return f"channel{peer.channel_id}"
    if isinstance(peer, types.PeerChat):
        return f"chat{peer.chat_id}"
    # anonymous admins and channel posts have no from_id; sender_id then holds
    # the channel the message was posted as
    if message.sender_id is None:
        return None
    return f"channel{message.sender_id}"


def _read_last_line(path: str) -> bytes:
    """Return the last line of a JSONL file without reading the whole file.

    Seeks backward in chunks from EOF, stops at the newline that precedes the
    last record
    """
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        if end == 0:
            return b""

        # lines end with \n; skip the trailing newline of the last line
        # so rfind below locates the *preceding* newline (= start of last record).
        f.seek(end - 1)
        pos = end - 1 if f.read(1) == b"\n" else end

        while pos > 0:
            chunk = min(_LAST_LINE_CHUNK, pos)
            pos -= chunk
            f.seek(pos)
            data = f.read(chunk)
            idx = data.rfind(b"\n")
            if idx != -1:
                f.seek(pos + idx + 1)
                return f.readline()

        # no newline found - the whole file is a single line
        f.seek(0)
        return f.readline()


def _truncate_partial_tail(path: str) -> bool:
    """Drop a trailing partial record left behind by an interrupted append.

    An append can only ever land as a prefix of what it meant to write, so the
    damage is confined to the bytes after the last newline. Without this repair
    one killed run would leave an unparseable last line and `_read_last_line`
    would raise on every later download of the chat - fatal under the single
    layout, where this file is the only copy of the history.
    """
    with open(path, "rb+") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        if end == 0:
            return False
        f.seek(end - 1)
        if f.read(1) == b"\n":
            return False

        pos = end
        while pos > 0:
            chunk = min(_LAST_LINE_CHUNK, pos)
            pos -= chunk
            f.seek(pos)
            idx = f.read(chunk).rfind(b"\n")
            if idx != -1:
                f.truncate(pos + idx + 1)
                return True

        # no newline anywhere - the whole file is one partial record
        f.truncate(0)
        return True


def _dump_jsonl(messages) -> str:
    return "".join(json.dumps(msg, ensure_ascii=False) + "\n" for msg in messages)


def _fsync_dir(path: str) -> None:
    """Persist a directory entry, so a rename survives a power loss."""
    fd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _append_jsonl(path: str, messages) -> None:
    """Append records in one write, then fsync so they are actually on disk."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(_dump_jsonl(messages))
        f.flush()
        os.fsync(f.fileno())


def _rewrite_jsonl(path: str, messages) -> None:
    """Replace the file atomically via a tmp sibling, so a crash cannot destroy it."""
    # the pid keeps two concurrent runs from writing the same tmp file
    tmp_path = f"{path}.{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(_dump_jsonl(messages))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)
    _fsync_dir(path)


class TelegramChatHistoryDownloader:
    def __init__(
        self,
        client: "TelegramClient",
        path_manager: "FilePathManager",
        download_limit=1000,
    ):
        self._client = client
        self._download_limit = download_limit
        self.path_manager = path_manager

    def _update_raw_chat_history(self, messages, group_name):
        filename = self.path_manager.raw_history_path(group_name)
        if not messages:
            return 0
        if not os.path.exists(filename):
            _rewrite_jsonl(filename, messages)
            return len(messages)

        if _truncate_partial_tail(filename):
            logger.warning(f"{group_name}: dropped a partial record from {filename}")
        last_line = _read_last_line(filename)
        if not last_line.strip():
            # empty, or emptied by the repair above
            _rewrite_jsonl(filename, messages)
            return len(messages)
        last_known_id = json.loads(last_line)["id"]

        new_messages = [m for m in messages if m["id"] > last_known_id]

        # fall back to full dedup/rewrite if there are overlapping IDs
        has_overlap = len(new_messages) < len(messages)
        if has_overlap:
            with open(filename, "r", encoding="utf-8") as f:
                existing = {json.loads(line)["id"]: json.loads(line) for line in f}
            original_count = len(existing)
            for msg in messages:
                existing[msg["id"]] = msg
            merged = sorted(existing.values(), key=lambda x: x["id"])
            _rewrite_jsonl(filename, merged)
            return len(merged) - original_count

        if new_messages:
            _append_jsonl(filename, new_messages)
        return len(new_messages)

    def _create_daily_chat_history(
        self, messages, group_name, incomplete_from: date | None = None
    ):
        """Write one history file per day.

        `incomplete_from` (today) is the first day that can still receive
        messages; it and anything after it are skipped so a partial day is
        never written. Every earlier day is written even when it is the newest
        data we have - a chat that went quiet must not lose its last day.
        """
        # group messages by date
        messages_by_date = OrderedDict()
        for message in messages:
            date_str = message["date"].split("T")[0]
            if date_str not in messages_by_date:
                messages_by_date[date_str] = []
            messages_by_date[date_str].append(message)

        cutoff = incomplete_from.isoformat() if incomplete_from else None
        for date_str, day_messages in messages_by_date.items():
            if cutoff and date_str >= cutoff:
                continue
            filename = self.path_manager.date_history_path(group_name, date_str)
            # assumption: if the file exists, its history is complete
            if os.path.exists(filename):
                continue
            self.path_manager.create_folders_if_not_exists(group_name, date_str)
            # atomic: a day file is never rewritten once it exists, so a crash
            # mid-write would leave a truncated day forever
            _rewrite_jsonl(filename, day_messages)

    def _get_info_about_chat_history(self, group_name):
        filename = self.path_manager.raw_history_path(group_name)
        if not os.path.exists(filename):
            return None, None, None, None
        with open(filename, "rb") as f:
            first = json.loads(f.readline())
        last = json.loads(_read_last_line(filename))
        return (
            first["id"],
            datetime.fromisoformat(first["date"]),
            last["id"],
            datetime.fromisoformat(last["date"]),
        )

    def _prepare_message(self, message):
        # field names follow the telegram desktop export format
        # (core.telegram.org/import-export); "reactions" is our own extension,
        # the export format has no place for it
        return {
            "id": message.id,
            "type": "message",
            "date": message.date.isoformat(),
            # not the export's "from": that holds a display name, this is the
            # @username, so it gets its own name
            "from_username": message.sender.username if message.sender else None,
            "from_id": _format_from_id(message),
            "text": message.message,
            "reply_to_message_id": message.reply_to_msg_id,
            "reactions": _extract_reactions(message),
        }

    def get_entity_safely(self, id):
        client = self._client
        try:
            # first, try to get it as a channel
            return client(functions.channels.GetChannelsRequest([id])).chats[0]
        except ValueError:
            try:
                # if not a channel, try as a chat
                return client(functions.messages.GetChatsRequest(id=[id])).chats[0]
            except ValueError:
                # except (ValueError, ChatsIdInvalidError):
                try:
                    # if not a chat, try as a user
                    return client(functions.users.GetUsersRequest([id])).users[0]
                except ValueError:
                    # if all fails, try one last time with get_entity
                    return client.get_entity(id)

    def _display_title(self, entity):
        title = getattr(entity, "title", None)
        if title is not None:
            return title
        # types.User has no .title
        return f"{entity.first_name} {entity.last_name or ''}".strip()

    def _get_group_name(self, entity):
        group_name = entity.username
        if not group_name:
            title = self._display_title(entity)
            group_name = str(title).lower().strip().replace(" ", "_")
        return group_name

    def download_chat_history(
        self, chat_peer, previous_days=0, start_from_yesterday=True
    ):
        # group_name = group_name.strip().strip('"')
        client = self._client
        # find the group by name
        # entity = self.get_entity_safely(chat_peer)
        entity = client.get_entity(chat_peer)
        # if isinstance(group_id, int):
        group_name = self._get_group_name(entity)
        self._save_chat_metadata(group_name, entity)

        messages = []
        # utc: telegram timestamps and the date-named folders are both utc
        offset_date = today() - timedelta(days=previous_days)
        if start_from_yesterday:
            offset_date = offset_date - timedelta(days=1)
        _, first_message_date, last_message_id, _ = self._get_info_about_chat_history(
            group_name
        )
        iter_messages_params = {
            "entity": entity,
            "limit": self._download_limit,
            "offset_date": offset_date,
            "reverse": True,
        }
        ignore_min_id = first_message_date and first_message_date.date() > offset_date
        if last_message_id and not ignore_min_id:
            iter_messages_params["min_id"] = last_message_id
        # print(f"{iter_messages_params=}")

        while True:
            fetched_messages = list(client.iter_messages(**iter_messages_params))
            if not fetched_messages:
                # if no more messages are returned, break the loop
                break

            for message in fetched_messages:
                message_data = self._prepare_message(message)
                messages.append(message_data)
            logger.debug(f"accumulated messages: {len(messages)}")
            iter_messages_params["offset_id"] = fetched_messages[-1].id
            # if we fetched fewer messages than the limit, we are done
            if len(fetched_messages) < self._download_limit:
                break

        # save chat history to a file
        self.path_manager.create_folders_if_not_exists(group_name)
        new_messages_count = self._update_raw_chat_history(messages, group_name)
        logger.debug(f"new messages: {new_messages_count}")
        # the single layout keeps the whole chat in the raw file and never splits it
        if self.path_manager.layout(group_name) is not Layout.SINGLE:
            self._create_daily_chat_history_from_raw_history(
                group_name, date_from=offset_date
            )
        return group_name, new_messages_count

    def _create_daily_chat_history_from_raw_history(
        self, group_name, date_from: date | None = None, date_to: date | None = None
    ):
        filename = self.path_manager.raw_history_path(group_name)
        if not os.path.exists(filename):
            # a chat with no messages yet has no raw history to split
            return
        messages = []
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                msg = json.loads(line)
                msg_date = datetime.fromisoformat(msg["date"]).date()
                if date_from and msg_date < date_from:
                    continue
                if date_to and msg_date > date_to:
                    break
                messages.append(msg)
        self._create_daily_chat_history(messages, group_name, incomplete_from=today())

    # metadata
    def download_chat_metadata(self, folder_name: str):
        client = self._client
        chat_peers = self.get_chat_peers_from_folder(folder_name)
        group_names = {}
        for chat_peer in chat_peers:
            entity = client.get_entity(chat_peer)
            group_name = self._get_group_name(entity)
            is_new = self._save_chat_metadata(group_name, entity)
            _ = self._save_additional_requirements(group_name, "")
            group_names[group_name] = is_new
        if not group_names:
            # an empty folder is almost always a mistake; refuse to disable
            # every known chat because of it
            logger.warning(
                f"Telegram folder {folder_name!r} is empty, "
                "leaving downloading flags untouched."
            )
            return group_names
        for existing_name, _, _ in self.path_manager.all_groups_list():
            if existing_name not in group_names:
                self.path_manager.set_downloading_enabled(existing_name, False)
        return group_names

    def _save_chat_metadata(self, group_name, entity):
        self.path_manager.create_folders_if_not_exists(group_name)
        filename = self.path_manager.group_metadata_path(group_name)
        link_prefix = self.get_message_link_prefix(entity)
        is_new = True
        existing = {}
        if os.path.exists(filename):
            is_new = False
            with open(filename, encoding="utf-8") as f:
                existing = json.load(f)
        # only downloading_enabled is derived from telegram folder membership,
        # every other key (summarization_enabled included) is kept as is
        legacy_enabled = existing.pop("enabled", None)
        if legacy_enabled is not None:
            existing.setdefault("summarization_enabled", legacy_enabled)
        self.path_manager.write_metadata(
            group_name,
            {
                **existing,
                "id": entity.id,
                "access_hash": getattr(entity, "access_hash", 0),
                "title": self._display_title(entity),
                "username": entity.username,
                "link_prefix": link_prefix,
                "type": type(entity).__name__,
                "downloading_enabled": True,
            },
        )
        return is_new

    def _save_additional_requirements(self, group_name, additional_requirements):
        self.path_manager.create_folders_if_not_exists(group_name)
        filename = self.path_manager.additional_requirements_path(group_name)
        if os.path.exists(filename):
            return
        with open(filename, "w", encoding="utf-8") as f:
            f.write(additional_requirements)
        return

    # WORK WITH FOLDER
    def get_chat_peers_from_folder(self, folder_name: str):
        folder = self._get_folder_by_name(folder_name)
        chat_peers = [ch for ch in folder.include_peers]
        return chat_peers

    def _get_folder_by_name(self, folder_name: str):
        client = self._client
        dialog_filters = client(functions.messages.GetDialogFiltersRequest())
        folders = [
            f for f in dialog_filters.filters if isinstance(f, types.DialogFilter)
        ]
        # find the folder with the matching name
        for dialog_filter in folders:
            if dialog_filter.title.text == folder_name:
                return dialog_filter
        # a missing folder must not look like an empty one: that would disable
        # downloading for every known chat
        known = ", ".join(repr(f.title.text) for f in folders) or "none"
        raise FolderNotFoundError(
            f"Telegram folder {folder_name!r} not found. Available folders: {known}."
        )

    # OTHER
    def get_message_link_prefix(self, entity):
        if isinstance(entity, types.Channel):
            if entity.username:
                # public channel or supergroup
                return f"https://t.me/{entity.username}/"
            else:
                # private channel or supergroup
                return f"https://t.me/c/{entity.id}/"
        elif isinstance(entity, types.Chat):
            # private group
            return f"https://t.me/c/{entity.id}/"
        elif isinstance(entity, types.User):
            if entity.username:
                # user with username
                return f"https://t.me/{entity.username}/"
            else:
                # user without username
                return f"https://t.me/c/{entity.id}/"
        else:
            return "Unknown entity type"
