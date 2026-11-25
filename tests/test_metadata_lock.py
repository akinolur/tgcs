import os
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from telethon.tl import types

from tgcs.fs import locker
from tgcs.layouts import Layout
from tgcs.paths import FilePathManager
from tgcs.telegram.downloader import TelegramChatHistoryDownloader


class FakeClient:
    def __init__(self, entity):
        self.entity = entity
        self.peer = types.InputPeerChannel(entity.id, entity.access_hash)

    def __call__(self, request):
        folder = types.DialogFilter(
            id=1,
            title=types.TextWithEntities(text="Chats", entities=[]),
            pinned_peers=[],
            include_peers=[self.peer],
            exclude_peers=[],
        )
        return SimpleNamespace(filters=[folder])

    def get_entity(self, peer):
        return self.entity

    def iter_messages(self, entity, **kwargs):
        return []


def _channel(chat_id):
    return types.Channel(
        id=chat_id, title="Team", photo=None, date=None, access_hash=chat_id * 10
    )


def _metadata(chat_id, **extra):
    return {"id": chat_id, "access_hash": chat_id * 10, "type": "Channel", **extra}


@pytest.fixture
def path_manager(tmp_path):
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    path_manager.create_folders_if_not_exists("team")
    return path_manager


def _open_lock_file(path_manager):
    path = os.path.join(path_manager.base_path, ".metadata.lock")
    return os.open(path, os.O_CREAT | os.O_RDWR, 0o644)


@contextmanager
def _another_process_holds_the_lock(path_manager, action):
    fd = _open_lock_file(path_manager)
    thread = threading.Thread(target=action, daemon=True)
    try:
        locker.lock(fd)
        thread.start()
        thread.join(0.2)
        assert thread.is_alive()
        yield
    finally:
        os.close(fd)
        thread.join(5)
    assert not thread.is_alive()


def test_set_layout_keeps_a_flag_changed_by_another_process(path_manager):
    # given
    path_manager.write_metadata("team", _metadata(1, downloading_enabled=True))

    # when
    with _another_process_holds_the_lock(
        path_manager, lambda: path_manager.set_layout("team", Layout.SINGLE)
    ):
        path_manager.write_metadata("team", _metadata(1, downloading_enabled=False))

    # then
    assert path_manager.layout("team") is Layout.SINGLE
    assert path_manager.is_downloading_enabled("team") is False


def test_set_downloading_enabled_keeps_a_layout_of_another_process(path_manager):
    # given
    path_manager.write_metadata("team", _metadata(1))

    # when
    with _another_process_holds_the_lock(
        path_manager, lambda: path_manager.set_downloading_enabled("team", False)
    ):
        path_manager.write_metadata("team", _metadata(1, layout="single"))

    # then
    assert path_manager.layout("team") is Layout.SINGLE
    assert path_manager.is_downloading_enabled("team") is False


def test_download_keeps_a_flag_changed_by_another_process(path_manager):
    # given
    path_manager.write_metadata("team", _metadata(1, downloading_enabled=False))
    client = FakeClient(_channel(1))
    downloader = TelegramChatHistoryDownloader(client, path_manager)

    # when
    with _another_process_holds_the_lock(
        path_manager, lambda: downloader.download_chat_history("team", client.peer)
    ):
        path_manager.write_metadata("team", _metadata(1, downloading_enabled=True))

    # then
    assert path_manager.is_downloading_enabled("team") is True


def test_update_does_not_take_a_folder_claimed_by_another_process(path_manager):
    # given
    client = FakeClient(_channel(2))
    downloader = TelegramChatHistoryDownloader(client, path_manager)

    # when
    with _another_process_holds_the_lock(
        path_manager, lambda: downloader.download_chat_metadata("Chats")
    ):
        path_manager.write_metadata("team", _metadata(1))

    # then
    assert path_manager.read_metadata("team")["id"] == 1
    assert path_manager.read_metadata("team_2")["id"] == 2


def test_lock_is_released_after_an_error(path_manager):
    # when
    with pytest.raises(RuntimeError):
        with path_manager.lock_metadata():
            raise RuntimeError("boom")

    # then
    fd = _open_lock_file(path_manager)
    try:
        assert locker.try_lock(fd)
    finally:
        os.close(fd)


def test_lock_file_is_kept_and_is_not_a_chat(path_manager):
    # when
    with path_manager.lock_metadata():
        pass

    # then
    path = os.path.join(path_manager.base_path, ".metadata.lock")
    assert os.path.isfile(path)
    assert path_manager.all_groups_list() == []
