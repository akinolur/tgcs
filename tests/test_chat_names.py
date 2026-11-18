import os
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import tgcs.commands.summarize as summarize_module
import tgcs.telegram.notifier as notifier_module
from tgcs.cli import create_app
from tgcs.paths import FilePathManager


class FakeContainer:
    def __init__(self, path_manager) -> None:
        self.path_manager = path_manager
        self.cfg = SimpleNamespace(
            llm_model="model", summary_template_path=None, tg_users=["someone"]
        )
        self.config_path = "config.toml"
        self.llm_client = None
        self.bot_client = None

    def close(self) -> None:
        pass


def _container(tmp_path, chats=()):
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    for chat in chats:
        path_manager.create_folders_if_not_exists(chat)
        path_manager.write_metadata(chat, {"id": 1})
    return FakeContainer(path_manager)


def _invoke(container, args):
    return CliRunner().invoke(create_app(lambda _: container), args)


@pytest.mark.parametrize("command", ["summarize", "notification"])
@pytest.mark.parametrize("name", ["missing", "1", ".."])
def test_unknown_chat_exits_with_an_error(tmp_path, command, name):
    # given
    container = _container(tmp_path, chats=["alpha"])

    # when
    result = _invoke(container, [command, "--chat", name])

    # then
    assert result.exit_code == 1
    assert f"{name}: unknown chat" in result.output


@pytest.mark.parametrize("command", ["summarize", "notification"])
def test_a_path_to_another_data_dir_is_not_a_chat(tmp_path, command):
    # given
    other = _container(tmp_path / "other", chats=["alpha"])
    other_chat = os.path.dirname(other.path_manager.group_metadata_path("alpha"))
    container = _container(tmp_path, chats=["beta"])

    # when
    result = _invoke(container, [command, "--chat", os.path.abspath(other_chat)])

    # then
    assert result.exit_code == 1
    assert "unknown chat" in result.output


def test_summarize_treats_a_numeric_chat_name_as_a_name(tmp_path, monkeypatch):
    # given
    container = _container(tmp_path, chats=["alpha", "1"])
    summarized = []
    monkeypatch.setattr(
        summarize_module,
        "_summarize_group",
        lambda **kwargs: summarized.append(kwargs["group_name"]),
    )

    # when
    result = _invoke(container, ["summarize", "--chat", "1"])

    # then
    assert result.exit_code == 0, result.output
    assert summarized == ["1"]


def test_notification_treats_a_numeric_chat_name_as_a_name(tmp_path, monkeypatch):
    # given
    container = _container(tmp_path, chats=["alpha", "1"])
    notified = []

    class FakeNotificator:
        def __init__(self, bot_client, path_manager) -> None:
            pass

        def notify(self, group_name, users, last_days=None):
            notified.append(group_name)
            return 1

    monkeypatch.setattr(notifier_module, "Notificator", FakeNotificator)

    # when
    result = _invoke(container, ["notification", "--chat", "1"])

    # then
    assert result.exit_code == 0, result.output
    assert notified == ["1"]
