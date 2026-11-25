from datetime import datetime, timezone

import pytest
from telethon.tl import types
from telethon.tl.custom.message import Message

from tgcs.paths import FilePathManager
from tgcs.telegram.downloader import TelegramChatHistoryDownloader


def _prepare(tmp_path, peer_id, **kwargs):
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    downloader = TelegramChatHistoryDownloader(None, path_manager)
    message = Message(
        id=10,
        peer_id=peer_id,
        date=datetime(2025, 3, 1, tzinfo=timezone.utc),
        message="hi",
        **kwargs,
    )
    return downloader._prepare_message(message)


@pytest.mark.parametrize(
    ("peer_id", "kwargs", "expected"),
    [
        (types.PeerUser(5), {}, "user5"),
        (types.PeerUser(5), {"out": True}, None),
        (types.PeerUser(5), {"out": True, "from_id": types.PeerUser(6)}, "user6"),
        (types.PeerChannel(5), {"post": True}, "channel-1000000000005"),
        (types.PeerChat(5), {}, None),
    ],
)
def test_from_id_has_the_prefix_of_the_sender(tmp_path, peer_id, kwargs, expected):
    # when
    prepared = _prepare(tmp_path, peer_id, **kwargs)

    # then
    assert prepared["from_id"] == expected


@pytest.mark.parametrize(
    ("reply_to", "expected"),
    [
        (None, None),
        (types.MessageReplyHeader(reply_to_msg_id=3), 3),
        (
            types.MessageReplyHeader(
                reply_to_msg_id=3, reply_to_peer_id=types.PeerChannel(1)
            ),
            3,
        ),
        (
            types.MessageReplyHeader(
                reply_to_msg_id=3, reply_to_peer_id=types.PeerChannel(2)
            ),
            None,
        ),
        (
            types.MessageReplyHeader(
                reply_to_msg_id=3, reply_to_peer_id=types.PeerUser(1)
            ),
            None,
        ),
        (types.MessageReplyStoryHeader(peer=types.PeerUser(1), story_id=3), None),
    ],
)
def test_reply_is_kept_only_for_this_chat(tmp_path, reply_to, expected):
    # when
    prepared = _prepare(tmp_path, types.PeerChannel(1), reply_to=reply_to)

    # then
    assert prepared["reply_to_message_id"] == expected
