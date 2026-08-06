import json
from types import SimpleNamespace

from tgcs.commands import summarize as summarize_module
from tgcs.paths import FilePathManager
from tgcs.telegram.downloader import TelegramChatHistoryDownloader


def _make_group(base_path, group_name: str, **metadata) -> None:
    group_path = base_path / group_name
    group_path.mkdir(parents=True, exist_ok=True)
    (group_path / "metadata.json").write_text(
        json.dumps({"id": 1, "title": group_name, **metadata})
    )


def test_summarize_groups_list_skips_summarization_disabled(tmp_path):
    # given
    _make_group(tmp_path, "kept")
    _make_group(tmp_path, "no_summary", summarization_enabled=False)
    path_manager = FilePathManager(base_path=str(tmp_path))

    # when / then
    assert path_manager.summarize_groups_list() == ["kept"]
    assert sorted(path_manager.download_groups_list()) == ["kept", "no_summary"]


def test_download_groups_list_skips_downloading_disabled(tmp_path):
    # given
    _make_group(tmp_path, "kept")
    _make_group(tmp_path, "no_download", downloading_enabled=False)
    path_manager = FilePathManager(base_path=str(tmp_path))

    # when / then
    assert path_manager.download_groups_list() == ["kept"]
    assert sorted(path_manager.summarize_groups_list()) == ["kept", "no_download"]


def test_flags_default_to_true_when_keys_missing(tmp_path):
    # given
    _make_group(tmp_path, "plain")
    path_manager = FilePathManager(base_path=str(tmp_path))

    # when / then
    assert path_manager.is_downloading_enabled("plain") is True
    assert path_manager.is_summarization_enabled("plain") is True
    assert path_manager.all_groups_list() == [("plain", True, True)]


def test_legacy_enabled_key_is_honoured_for_both_flags(tmp_path):
    # given
    _make_group(tmp_path, "legacy", enabled=False)
    path_manager = FilePathManager(base_path=str(tmp_path))

    # when / then
    assert path_manager.is_downloading_enabled("legacy") is False
    assert path_manager.is_summarization_enabled("legacy") is False


def test_flags_are_false_when_metadata_is_missing(tmp_path):
    # given
    path_manager = FilePathManager(base_path=str(tmp_path))

    # when / then
    assert path_manager.is_downloading_enabled("unknown") is False
    assert path_manager.is_summarization_enabled("unknown") is False


def test_chats_update_preserves_summarization_flag(tmp_path):
    # given: a group the user disabled summarization for
    _make_group(tmp_path, "muted", summarization_enabled=False, enabled=False)
    path_manager = FilePathManager(base_path=str(tmp_path))
    downloader = TelegramChatHistoryDownloader(client=None, path_manager=path_manager)
    entity = SimpleNamespace(
        id=1, access_hash=2, title="muted", username="muted", usernames=None
    )

    # when: the chat is still in the telegram folder
    downloader._save_chat_metadata("muted", entity)

    # then
    metadata = json.loads((tmp_path / "muted" / "metadata.json").read_text())
    assert metadata["summarization_enabled"] is False
    assert metadata["downloading_enabled"] is True
    assert "enabled" not in metadata


def test_summarize_all_skips_summarization_disabled_group(tmp_path, monkeypatch):
    # given
    _make_group(tmp_path, "kept")
    _make_group(tmp_path, "muted", summarization_enabled=False)
    summarized = []
    monkeypatch.setattr(
        summarize_module,
        "_summarize_group",
        lambda **kwargs: summarized.append(kwargs["group_name"]),
    )

    class FakeContainer:
        path_manager = FilePathManager(base_path=str(tmp_path))
        cfg = SimpleNamespace(llm_model=None, summary_template_path=None, tg_users=[])
        llm_client = None

    ctx = SimpleNamespace(invoked_subcommand=None, obj=FakeContainer())

    # when
    summarize_module.summarize(
        ctx, name=None, all=True, tg_notification=False, limit=None, days=None
    )

    # then
    assert summarized == ["kept"]


def test_set_downloading_enabled_writes_only_that_flag(tmp_path):
    # given
    _make_group(tmp_path, "gone", summarization_enabled=False)
    path_manager = FilePathManager(base_path=str(tmp_path))

    # when
    path_manager.set_downloading_enabled("gone", False)

    # then
    metadata = json.loads((tmp_path / "gone" / "metadata.json").read_text())
    assert metadata["downloading_enabled"] is False
    assert metadata["summarization_enabled"] is False
