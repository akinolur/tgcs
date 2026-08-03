import sys
from pathlib import Path
from types import ModuleType

import pytest
from typer.testing import CliRunner

import tgcs.cli
from tgcs.container import Container


class FakePathManager:
    def all_groups_list(self):
        return []


class FakeContainer:
    instances = []

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.close_calls = 0
        self.path_manager = FakePathManager()
        FakeContainer.instances.append(self)

    def close(self) -> None:
        self.close_calls += 1


def test_config_path_is_passed_to_container(monkeypatch, tmp_path):
    # given
    config_path = tmp_path / "config.toml"
    FakeContainer.instances.clear()
    monkeypatch.setattr(tgcs.cli, "Container", FakeContainer)

    # when
    result = CliRunner().invoke(
        tgcs.cli.app, ["--config", str(config_path), "chats", "ls"]
    )

    # then
    assert result.exit_code == 0
    assert FakeContainer.instances[0].config_path == config_path
    assert FakeContainer.instances[0].close_calls == 1


def test_container_is_closed_after_cli_error(monkeypatch):
    # given
    class FailingPathManager:
        def all_groups_list(self):
            raise RuntimeError("command failed")

    class FailingContainer(FakeContainer):
        def __init__(self, config_path: Path) -> None:
            super().__init__(config_path)
            self.path_manager = FailingPathManager()

    FakeContainer.instances.clear()
    monkeypatch.setattr(tgcs.cli, "Container", FailingContainer)

    # when
    result = CliRunner().invoke(tgcs.cli.app, ["chats", "ls"])

    # then
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert FakeContainer.instances[0].close_calls == 1


def test_container_loads_the_given_config_path(tmp_path):
    # given
    data_dir = tmp_path / "data"
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{data_dir}"')

    # when
    container = Container(config_path)

    # then
    assert container.config_path == config_path
    assert container.cfg.data_dir == data_dir


def test_user_client_is_disconnected_when_container_closes(monkeypatch, tmp_path):
    # given
    events = []

    class FakeTelegramClient:
        def __init__(self, session_path, api_id, api_hash):
            events.append(("create", session_path, api_id, api_hash))

        def connect(self):
            events.append("connect")

        def get_me(self):
            events.append("get_me")
            return object()

        def disconnect(self):
            events.append("disconnect")

    data_dir = tmp_path / "data"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[telegram]\napi_id = 123\napi_hash = "hash"'
    )
    data_dir.mkdir()
    (data_dir / "user.session").touch()
    monkeypatch.setattr("telethon.sync.TelegramClient", FakeTelegramClient)
    container = Container(config_path)

    # when
    container.user_client
    container.close()

    # then
    assert events == [
        ("create", str(data_dir / "user"), 123, "hash"),
        "connect",
        "get_me",
        "disconnect",
    ]


def test_unauthorized_user_client_is_disconnected(monkeypatch, tmp_path):
    # given
    events = []

    class FakeTelegramClient:
        def __init__(self, session_path, api_id, api_hash):
            pass

        def connect(self):
            events.append("connect")

        def get_me(self):
            events.append("get_me")
            return None

        def disconnect(self):
            events.append("disconnect")

    data_dir = tmp_path / "data"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[telegram]\napi_id = 123\napi_hash = "hash"'
    )
    data_dir.mkdir()
    (data_dir / "user.session").touch()
    monkeypatch.setattr("telethon.sync.TelegramClient", FakeTelegramClient)
    container = Container(config_path)

    # when
    with pytest.raises(SystemExit):
        container.user_client
    container.close()

    # then
    assert events == ["connect", "get_me", "disconnect"]


def test_bot_is_disconnected_when_start_fails(monkeypatch, tmp_path):
    # given
    events = []

    class FakeTelegramClient:
        def __init__(self, session_path, api_id, api_hash):
            events.append("create")

        def start(self, bot_token):
            events.append("start")
            raise RuntimeError("authorization failed")

        def disconnect(self):
            events.append("disconnect")

    data_dir = tmp_path / "data"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[telegram_bot]\nbot_token = "token"'
    )
    monkeypatch.setattr("telethon.sync.TelegramClient", FakeTelegramClient)
    container = Container(config_path)

    # when
    with pytest.raises(RuntimeError, match="authorization failed"):
        container.tg_bot
    container.close()

    # then
    assert events == ["create", "start", "disconnect"]


def test_container_closes_all_clients_in_reverse_creation_order(monkeypatch, tmp_path):
    # given
    events = []
    telegram_clients = []

    class FakeTelegramClient:
        def __init__(self, session_path, api_id, api_hash):
            self.number = len(telegram_clients) + 1
            telegram_clients.append(self)

        def connect(self):
            events.append(f"telegram-{self.number}:connect")

        def start(self, bot_token):
            events.append(f"telegram-{self.number}:start")

        def get_me(self):
            return object()

        def disconnect(self):
            events.append(f"telegram-{self.number}:disconnect")

    class FakeOpenAI:
        def __init__(self, api_key, base_url):
            events.append("llm:create")

        def close(self):
            events.append("llm:close")

    data_dir = tmp_path / "data"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""\
data_dir = "{data_dir}"
[telegram]
api_id = 123
api_hash = "hash"
[telegram_bot]
bot_token = "token"
[llm]
api_key = "key"
model = "model"
"""
    )
    data_dir.mkdir()
    (data_dir / "user.session").touch()
    monkeypatch.setattr("telethon.sync.TelegramClient", FakeTelegramClient)
    openai = ModuleType("openai")
    openai.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", openai)
    container = Container(config_path)

    # when
    user_client = container.user_client
    container.tg_bot
    container.tg_client
    container.llm_client
    container.close()

    # then
    assert container.user_client is user_client
    assert events == [
        "telegram-1:connect",
        "telegram-2:start",
        "telegram-3:connect",
        "llm:create",
        "llm:close",
        "telegram-3:disconnect",
        "telegram-2:disconnect",
        "telegram-1:disconnect",
    ]
