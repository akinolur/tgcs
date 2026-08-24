import json

from telethon.tl.types import InputPeerChannel, InputPeerUser

from tgcs.commands.chats import _chat_peer_from_metadata, _download_all, _download_one
from tgcs.paths import FilePathManager


class FakeDownloader:
    """Fails for the chats named in `failing`, records the rest."""

    def __init__(self, failing=()):
        self.failing = set(failing)
        self.downloaded = []

    def download_chat_history(self, chat_peer, days):
        if chat_peer in self.failing:
            raise RuntimeError("boom")
        self.downloaded.append(chat_peer)
        return chat_peer, 1


def _known_group(path_manager, name, downloading=True):
    path_manager.create_folders_if_not_exists(name)
    with open(path_manager.group_metadata_path(name), "w") as f:
        json.dump({"id": name, "downloading_enabled": downloading}, f)


def test_one_failing_chat_does_not_stop_the_others(tmp_path):
    # given
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    for name in ("a", "b", "c"):
        _known_group(path_manager, name)
    downloader = FakeDownloader(failing={"b"})

    # when
    failed = 0
    for name in sorted(path_manager.download_groups_list()):
        if not _download_one(downloader, path_manager, name, days=1):
            failed += 1

    # then
    assert downloader.downloaded == ["a", "c"]
    assert failed == 1


def test_unknown_chat_is_reported_as_a_failure(tmp_path):
    # given
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    downloader = FakeDownloader()

    # when
    ok = _download_one(downloader, path_manager, "missing", days=1)

    # then
    assert ok is False
    assert downloader.downloaded == []


def test_download_all_with_no_enabled_chats_is_not_a_failure(tmp_path):
    # given
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    _known_group(path_manager, "a", downloading=False)

    # when
    failed = _download_all(
        user_client=None, path_manager=path_manager, default_previous_days=1
    )

    # then
    assert failed == 0


def test_chat_peer_from_metadata_builds_input_peer_user_for_a_private_dialog():
    # given
    metadata = {"id": 1, "access_hash": 42, "type": "User"}

    # when
    peer = _chat_peer_from_metadata(metadata)

    # then
    assert peer == InputPeerUser(1, 42)


def test_chat_peer_from_metadata_without_type_still_builds_channel_peer():
    # given
    metadata = {"id": 1, "access_hash": 42}

    # when
    peer = _chat_peer_from_metadata(metadata)

    # then
    assert peer == InputPeerChannel(1, 42)
