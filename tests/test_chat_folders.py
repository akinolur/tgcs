import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from telethon.tl import types
from telethon.tl.custom.message import Message
from typer.testing import CliRunner

from tgcs.cli import create_app
from tgcs.commands.chats import _download_one
from tgcs.paths import FilePathManager
from tgcs.telegram.downloader import (
    DuplicateChatFolderError,
    PeerKind,
    TelegramChatHistoryDownloader,
    peer_kind,
)


class FakeClient:
    def __init__(self, *entities):
        self.entities = list(entities)

    def __call__(self, request):
        folder = types.DialogFilter(
            id=1,
            title=types.TextWithEntities(text="Chats", entities=[]),
            pinned_peers=[],
            include_peers=[_input_peer(entity) for entity in self.entities],
            exclude_peers=[],
        )
        return SimpleNamespace(filters=[folder])

    def get_entity(self, peer):
        return next(e for e in self.entities if _input_peer(e) == peer)

    def iter_messages(self, entity, **kwargs):
        return [
            Message(
                id=1,
                peer_id=types.PeerChannel(entity.id),
                date=datetime(2025, 3, 1, tzinfo=timezone.utc),
                message=f"from {entity.id}",
            )
        ]


def _tree(path_manager):
    files = {}
    for folder, _, names in os.walk(path_manager.base_path):
        files[folder] = None
        for name in names:
            path = os.path.join(folder, name)
            with open(path) as f:
                files[path] = f.read()
    return files


def _input_peer(entity):
    if isinstance(entity, types.User):
        return types.InputPeerUser(entity.id, entity.access_hash)
    if isinstance(entity, types.Chat):
        return types.InputPeerChat(entity.id)
    return types.InputPeerChannel(entity.id, entity.access_hash)


def _channel(chat_id, title="Team", username=None):
    return types.Channel(
        id=chat_id,
        title=title,
        photo=None,
        date=None,
        access_hash=chat_id * 10,
        username=username,
    )


def _user(user_id, name="Team"):
    return types.User(id=user_id, access_hash=user_id * 10, first_name=name)


def _chat(chat_id, title="Team"):
    return types.Chat(
        id=chat_id,
        title=title,
        photo=None,
        participants_count=2,
        date=None,
        version=1,
    )


@pytest.fixture
def path_manager(tmp_path):
    return FilePathManager(base_path=str(tmp_path / "data"))


def _update(path_manager, *entities):
    downloader = TelegramChatHistoryDownloader(FakeClient(*entities), path_manager)
    return downloader.download_chat_metadata("Chats")


def _known(path_manager, name, **metadata):
    path_manager.create_folders_if_not_exists(name)
    path_manager.write_metadata(name, metadata)


def _write_raw(path_manager, name):
    path_manager.create_folders_if_not_exists(name)
    with open(path_manager.raw_history_path(name), "w") as f:
        f.write("{}\n")


def test_chats_with_the_same_title_get_their_own_stable_folders(path_manager):
    # given
    chats = [_channel(1), _channel(3, "team_2"), _channel(2)]

    # when
    names = [list(_update(path_manager, *chats)) for _ in range(2)]

    # then
    assert names == [["team", "team_2", "team_2_2"]] * 2
    ids = [path_manager.read_metadata(name)["id"] for name in names[0]]
    assert ids == [1, 3, 2]


def test_same_id_of_another_peer_type_is_another_chat(path_manager):
    # when
    names = _update(path_manager, _channel(7), _user(7), _chat(7))

    # then
    assert list(names) == ["team", "team_7", "team_7_2"]
    types_by_name = [path_manager.read_metadata(name)["type"] for name in names]
    assert types_by_name == ["Channel", "User", "Chat"]


def test_renamed_chat_keeps_its_folder_and_stays_enabled(path_manager):
    # given
    _update(path_manager, _channel(1))

    # when
    names = _update(path_manager, _channel(1, "New name", "new_name"))

    # then
    assert names == {"team": False}
    metadata = path_manager.read_metadata("team")
    assert metadata["title"] == "New name"
    assert metadata["downloading_enabled"] is True


def test_suffixed_folder_keeps_its_name_when_the_plain_name_is_free(path_manager):
    # given
    _update(path_manager, _channel(1), _channel(2))
    os.remove(path_manager.group_metadata_path("team"))

    # when / then
    assert _update(path_manager, _channel(2)) == {"team_2": False}


def test_update_disables_chats_by_the_resolved_folder(path_manager):
    # given
    _update(path_manager, _channel(1), _channel(2))

    # when
    _update(path_manager, _channel(2))

    # then
    assert not path_manager.is_downloading_enabled("team")
    assert path_manager.is_downloading_enabled("team_2")


def test_chat_with_two_folders_stops_the_update_before_any_change(path_manager):
    # given
    _known(path_manager, "first", id=1, access_hash=10, type="Channel")
    _known(path_manager, "second", id=1, access_hash=10)
    _known(path_manager, "gone", id=3, access_hash=30, type="Channel")
    before = _tree(path_manager)

    # when
    with pytest.raises(DuplicateChatFolderError) as ex:
        _update(path_manager, _channel(2), _channel(1))

    # then
    assert str(ex.value) == "Chat 'Team' has more than one folder: 'first', 'second'."
    assert _tree(path_manager) == before


def test_two_folders_of_a_chat_outside_the_telegram_folder_are_ignored(path_manager):
    # given
    _known(path_manager, "first", id=1, access_hash=10, type="Channel")
    _known(path_manager, "second", id=1, access_hash=10, type="Channel")

    # when / then
    assert list(_update(path_manager, _channel(2))) == ["team"]


def test_update_command_reports_a_chat_with_two_folders(path_manager):
    # given
    _known(path_manager, "first", id=1, access_hash=10, type="Channel")
    _known(path_manager, "second", id=1, access_hash=10, type="Channel")
    container = SimpleNamespace(
        cfg=SimpleNamespace(group_folder="Chats"),
        config_path="config.toml",
        user_client=FakeClient(_channel(1)),
        path_manager=path_manager,
        close=lambda: None,
    )

    # when
    result = CliRunner().invoke(create_app(lambda _: container), ["chats", "update"])

    # then
    assert result.exit_code == 1
    assert "'first', 'second'" in result.output
    assert "group_folder" not in result.output


def test_update_writes_the_type_to_an_old_folder(path_manager):
    # given
    _known(path_manager, "old", id=7, access_hash=70, enabled=False)

    # when
    names = _update(path_manager, _channel(7))

    # then
    assert names == {"old": False}
    metadata = path_manager.read_metadata("old")
    assert metadata["type"] == "Channel"
    assert metadata["summarization_enabled"] is False


def test_missing_access_hash_does_not_replace_the_known_one(path_manager):
    # given
    _update(path_manager, _channel(1))
    incomplete = _channel(1)
    incomplete.access_hash = None

    downloader = TelegramChatHistoryDownloader(FakeClient(), path_manager)

    # when
    downloader._save_chat_metadata("team", incomplete, enable_downloading=True)

    # then
    assert path_manager.read_metadata("team")["access_hash"] == 10


def test_access_hash_of_the_request_fills_a_missing_one(path_manager):
    # given
    class HashlessClient(FakeClient):
        def get_entity(self, peer):
            entity = _channel(peer.channel_id)
            entity.access_hash = None
            return entity

    downloader = TelegramChatHistoryDownloader(
        HashlessClient(_channel(1)), path_manager
    )

    # when
    downloader.download_chat_metadata("Chats")

    # then
    assert path_manager.read_metadata("team")["access_hash"] == 10


@pytest.mark.parametrize("type_name", ["Community", "CommunityForbidden"])
def test_community_is_a_channel_without_an_access_hash(type_name):
    # when / then
    assert peer_kind(type_name, None) is PeerKind.CHANNEL


@pytest.mark.parametrize(
    ("metadata", "entity", "expected"),
    [
        ({"access_hash": 70}, _channel(7), "old"),
        ({"access_hash": 70}, _chat(7), "team"),
        ({"access_hash": 0}, _chat(7), "old"),
        ({"type": "ChannelForbidden", "access_hash": 0}, _channel(7), "old"),
        ({"type": "ChatForbidden", "access_hash": 0}, _chat(7), "old"),
    ],
)
def test_peer_type_of_old_metadata(path_manager, metadata, entity, expected):
    # given
    _known(path_manager, "old", id=7, **metadata)

    # when / then
    assert list(_update(path_manager, entity)) == [expected]


def test_regular_file_with_the_chat_name_is_skipped(path_manager):
    # given
    for name in ("team", "team_1"):
        with open(os.path.join(path_manager.base_path, name), "w"):
            pass

    # when / then
    assert list(_update(path_manager, _channel(1))) == ["team_1_2"]


@pytest.mark.parametrize("metadata", [None, {}, {"id": None}])
def test_folder_with_history_but_no_id_is_skipped(path_manager, metadata):
    # given
    _write_raw(path_manager, "team")
    if metadata is not None:
        path_manager.write_metadata("team", metadata)

    # when / then
    assert list(_update(path_manager, _channel(1))) == ["team_1"]


@pytest.mark.parametrize("metadata", [None, {"layout": "single"}])
def test_folder_without_history_and_id_is_reused(path_manager, metadata):
    # given
    path_manager.create_folders_if_not_exists("team")
    if metadata is not None:
        path_manager.write_metadata("team", metadata)

    # when / then
    assert list(_update(path_manager, _channel(1))) == ["team"]


@pytest.mark.parametrize("content", [b"{not json", b"[]", b"\xff\xfe"])
def test_folder_with_unreadable_metadata_is_in_use(path_manager, content):
    # given
    path_manager.create_folders_if_not_exists("team")
    with open(path_manager.group_metadata_path("team"), "wb") as f:
        f.write(content)

    # when
    names = _update(path_manager, _channel(1))

    # then
    assert list(names) == ["team_1"]
    with open(path_manager.group_metadata_path("team"), "rb") as f:
        assert f.read() == content


@pytest.mark.parametrize("name", ["team", "team_2", "custom"])
def test_download_writes_to_the_named_folder(path_manager, name):
    # given
    _known(path_manager, "team", id=1, access_hash=10, type="Channel")
    _known(path_manager, "team_2", id=2, access_hash=20, type="Channel")
    _known(path_manager, "custom", id=2, access_hash=20, type="Channel")
    client = FakeClient(_channel(1), _channel(2))
    downloader = TelegramChatHistoryDownloader(client, path_manager)
    chat_id = path_manager.read_metadata(name)["id"]

    # when
    ok = _download_one(downloader, path_manager, name, days=1)

    # then
    assert ok
    with open(path_manager.raw_history_path(name)) as f:
        assert [json.loads(line)["text"] for line in f] == [f"from {chat_id}"]
    assert path_manager.read_metadata(name)["id"] == chat_id
    for other in {"team", "team_2", "custom"} - {name}:
        assert not os.path.exists(path_manager.raw_history_path(other))
