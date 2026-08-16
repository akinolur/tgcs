import json
import logging
import os

from tgcs.layouts import Layout
from tgcs.paths import FilePathManager


def _known_group(path_manager, name, **metadata):
    path_manager.create_folders_if_not_exists(name)
    with open(path_manager.group_metadata_path(name), "w") as f:
        json.dump({"id": name, **metadata}, f)


def test_chat_without_a_layout_key_uses_the_configured_default(tmp_path):
    # given
    path_manager = FilePathManager(
        base_path=str(tmp_path / "data"), default_layout=Layout.SINGLE
    )
    _known_group(path_manager, "group")

    # when / then
    assert path_manager.layout("group") is Layout.SINGLE


def test_default_layout_is_daily(tmp_path):
    # given: a chat saved by the current downloader, which writes no layout key
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    _known_group(path_manager, "group")

    # when / then
    assert path_manager.layout("group") is Layout.DAILY


def test_chat_layout_overrides_the_default(tmp_path):
    # given
    path_manager = FilePathManager(
        base_path=str(tmp_path / "data"), default_layout=Layout.DAILY
    )
    _known_group(path_manager, "group", layout="single")

    # when / then
    assert path_manager.layout("group") is Layout.SINGLE


def test_unknown_layout_falls_back_to_the_default_with_a_warning(tmp_path, caplog):
    # given
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    _known_group(path_manager, "group", layout="weekly")

    # when
    with caplog.at_level(logging.WARNING):
        layout = path_manager.layout("group")

    # then
    assert layout is Layout.DAILY
    assert "unknown layout 'weekly'" in caplog.text


def test_unknown_chat_uses_the_default_layout(tmp_path):
    # given: no metadata at all
    path_manager = FilePathManager(
        base_path=str(tmp_path / "data"), default_layout=Layout.SINGLE
    )

    # when / then
    assert path_manager.layout("missing") is Layout.SINGLE


def test_set_layout_keeps_the_other_metadata_keys(tmp_path):
    # given
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    _known_group(path_manager, "group", link_prefix="https://t.me/g/", enabled=True)

    # when
    assert path_manager.set_layout("group", Layout.SINGLE) is True

    # then
    with open(path_manager.group_metadata_path("group")) as f:
        metadata = json.load(f)
    assert metadata["layout"] == "single"
    assert metadata["link_prefix"] == "https://t.me/g/"
    assert metadata["enabled"] is True


def test_set_layout_on_an_unknown_chat_reports_failure(tmp_path):
    # given
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))

    # when / then: nothing safe to rewrite
    assert path_manager.set_layout("missing", Layout.SINGLE) is False


def test_metadata_is_written_atomically(tmp_path):
    # given
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    _known_group(path_manager, "group")

    # when
    path_manager.write_metadata("group", {"id": "group", "layout": "single"})

    # then: readable, and the tmp sibling is gone
    assert path_manager.read_metadata("group") == {"id": "group", "layout": "single"}
    group_dir = os.path.dirname(path_manager.group_metadata_path("group"))
    assert [f for f in os.listdir(group_dir) if ".tmp" in f] == []
