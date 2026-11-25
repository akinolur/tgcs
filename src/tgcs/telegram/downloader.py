import json
import logging
import os
from datetime import timedelta
from enum import StrEnum
from itertools import count
from typing import TYPE_CHECKING

from telethon import functions
from telethon.tl import types

from tgcs.dates import today
from tgcs.history_files import (
    raw_history_bounds,
    repair_raw_history_tail,
    split_raw_history,
    update_raw_history,
)
from tgcs.layouts import Layout

# from telethon.errors import ChatsIdInvalidError

if TYPE_CHECKING:
    from telethon.sync import TelegramClient
    from telethon.tl.custom.message import Message

    from tgcs.paths import FilePathManager

logger = logging.getLogger(__name__)


class FolderNotFoundError(Exception):
    """The configured telegram folder does not exist."""


class DuplicateChatFolderError(Exception):
    pass


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
    if (
        isinstance(message.peer_id, types.PeerUser)
        and message.peer_id.user_id == message.sender_id
    ):
        return f"user{message.sender_id}"
    return f"channel{message.sender_id}"


class PeerKind(StrEnum):
    USER = "user"
    CHAT = "chat"
    CHANNEL = "channel"


_KIND_BY_TYPE = {
    "User": PeerKind.USER,
    "UserEmpty": PeerKind.USER,
    "Chat": PeerKind.CHAT,
    "ChatEmpty": PeerKind.CHAT,
    "ChatForbidden": PeerKind.CHAT,
    "Channel": PeerKind.CHANNEL,
    "ChannelForbidden": PeerKind.CHANNEL,
    "Community": PeerKind.CHANNEL,
    "CommunityForbidden": PeerKind.CHANNEL,
}


def peer_kind(type_name: str | None, access_hash: int | None) -> PeerKind:
    guessed = PeerKind.CHANNEL if access_hash else PeerKind.CHAT
    return _KIND_BY_TYPE.get(type_name, guessed)


def _is_same_peer(metadata: dict, entity) -> bool:
    return metadata.get("id") == entity.id and peer_kind(
        metadata.get("type"), metadata.get("access_hash")
    ) == peer_kind(type(entity).__name__, getattr(entity, "access_hash", None))


def _local_reply_id(message: "Message") -> int | None:
    reply_peer = getattr(message.reply_to, "reply_to_peer_id", None)
    if reply_peer is not None and reply_peer != message.peer_id:
        return None
    return message.reply_to_msg_id


def _peer_key(peer) -> tuple[str, int | None]:
    for field in ("user_id", "chat_id", "channel_id"):
        peer_id = getattr(peer, field, None)
        if peer_id is not None:
            return field, peer_id
    return type(peer).__name__, None


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
            "reply_to_message_id": _local_reply_id(message),
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
        group_name = getattr(entity, "username", None)
        if not group_name:
            title = self._display_title(entity)
            group_name = str(title).lower().strip().replace(" ", "_")
            # titles are free text: keep the name a single path segment
            group_name = group_name.replace("/", "_").replace("\\", "_")
            if group_name.strip(".") == "":
                group_name = f"chat_{entity.id}"
        return group_name

    def _get_entity(self, peer):
        entity = self._client.get_entity(peer)
        if getattr(entity, "access_hash", 0) is None:
            entity.access_hash = getattr(peer, "access_hash", None)
        return entity

    def _known_group_name(self, entity) -> str | None:
        known = sorted(
            group_name
            for group_name, _, _ in self.path_manager.all_groups_list()
            if _is_same_peer(self.path_manager.read_metadata(group_name) or {}, entity)
        )
        if len(known) > 1:
            folders = ", ".join(repr(group_name) for group_name in known)
            raise DuplicateChatFolderError(
                f"Chat {self._display_title(entity)!r} has more than one folder: "
                f"{folders}."
            )
        return known[0] if known else None

    def _resolve_group_name(self, entity) -> str:
        known = self._known_group_name(entity)
        if known is not None:
            return known
        name = self._get_group_name(entity)
        if self.path_manager.is_group_name_free(name):
            return name
        name_with_id = f"{name}_{entity.id}"
        if self.path_manager.is_group_name_free(name_with_id):
            return name_with_id
        for n in count(2):
            candidate = f"{name_with_id}_{n}"
            if self.path_manager.is_group_name_free(candidate):
                return candidate

    def download_chat_history(
        self, group_name, chat_peer, previous_days=0, start_from_yesterday=True
    ):
        client = self._client
        entity = self._get_entity(chat_peer)
        self._save_chat_metadata(group_name, entity, enable_downloading=False)

        messages = []
        # utc: telegram timestamps and the date-named folders are both utc
        offset_date = today() - timedelta(days=previous_days)
        if start_from_yesterday:
            offset_date = offset_date - timedelta(days=1)
        repair_raw_history_tail(self.path_manager, group_name)
        _, first_message_date, last_message_id, _ = raw_history_bounds(
            self.path_manager, group_name
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
        new_messages_count = update_raw_history(self.path_manager, messages, group_name)
        logger.debug(f"new messages: {new_messages_count}")
        # the single layout keeps the whole chat in the raw file and never splits it
        if self.path_manager.layout(group_name) is not Layout.SINGLE:
            split_raw_history(self.path_manager, group_name, date_from=offset_date)
        return new_messages_count

    # metadata
    def download_chat_metadata(self, folder_name: str):
        chat_peers = self.get_chat_peers_from_folder(folder_name)
        entities = [self._get_entity(chat_peer) for chat_peer in chat_peers]
        for entity in entities:
            self._known_group_name(entity)
        group_names = {}
        for entity in entities:
            group_name = self._resolve_group_name(entity)
            is_new = self._save_chat_metadata(
                group_name, entity, enable_downloading=True
            )
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

    def _save_chat_metadata(self, group_name, entity, *, enable_downloading: bool):
        self.path_manager.create_folders_if_not_exists(group_name)
        filename = self.path_manager.group_metadata_path(group_name)
        link_prefix = self.get_message_link_prefix(entity)
        is_new = True
        existing = {}
        if os.path.exists(filename):
            is_new = False
            with open(filename, encoding="utf-8") as f:
                existing = json.load(f)
        downloading_enabled = enable_downloading or existing.get(
            "downloading_enabled", existing.get("enabled", True)
        )
        access_hash = getattr(entity, "access_hash", 0)
        if access_hash is None and _is_same_peer(existing, entity):
            access_hash = existing.get("access_hash")
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
                "access_hash": access_hash,
                "title": self._display_title(entity),
                "username": getattr(entity, "username", None),
                "link_prefix": link_prefix,
                "type": type(entity).__name__,
                "downloading_enabled": downloading_enabled,
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
        chat_peers = {}
        for peer in [*folder.pinned_peers, *folder.include_peers]:
            chat_peers.setdefault(_peer_key(peer), peer)
        return list(chat_peers.values())

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
