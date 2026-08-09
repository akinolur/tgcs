import json
from types import SimpleNamespace

import pytest
from telethon.tl import types

from tgcs.paths import FilePathManager
from tgcs.telegram.downloader import FolderNotFoundError, TelegramChatHistoryDownloader


class FakeClient:
    """Answers GetDialogFiltersRequest with the folders it was built with."""

    def __init__(self, folders):
        self._folders = folders

    def __call__(self, request):
        return SimpleNamespace(filters=self._folders)


def _folder(title, include_peers=()):
    folder = types.DialogFilter(
        id=1,
        title=types.TextWithEntities(text=title, entities=[]),
        pinned_peers=[],
        include_peers=list(include_peers),
        exclude_peers=[],
    )
    return folder


def _known_group(path_manager, name):
    path_manager.create_folders_if_not_exists(name)
    with open(path_manager.group_metadata_path(name), "w") as f:
        json.dump({"id": 1, "downloading_enabled": True}, f)


def test_missing_folder_raises_and_keeps_downloading_enabled(tmp_path):
    # given
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    _known_group(path_manager, "group")
    client = FakeClient([_folder("Other")])
    downloader = TelegramChatHistoryDownloader(client, path_manager)

    # when
    with pytest.raises(FolderNotFoundError) as ex:
        downloader.download_chat_metadata("Typo")

    # then
    assert "'Other'" in str(ex.value)
    assert path_manager.is_downloading_enabled("group")


def test_empty_folder_does_not_disable_known_chats(tmp_path):
    # given
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    _known_group(path_manager, "group")
    client = FakeClient([_folder("Chats")])
    downloader = TelegramChatHistoryDownloader(client, path_manager)

    # when
    result = downloader.download_chat_metadata("Chats")

    # then
    assert result == {}
    assert path_manager.is_downloading_enabled("group")
