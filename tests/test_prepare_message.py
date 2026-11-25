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
