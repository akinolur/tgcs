import stat
from pathlib import Path

import pytest

from tgcs.app_config import AppConfig
from tgcs.container import (
    Container,
    create_bot_client,
    create_llm_client,
    create_user_client,
)
from tgcs.paths import FilePathManager

CONFIG_PATH = Path("/etc/tgcs.toml")
FULL_CONFIG = """\
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


class FakePaths:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def user_session_path(self) -> str:
        return str(self.data_dir / "user")

    def bot_session_path(self) -> str:
        return str(self.data_dir / "bot")


class FakeTelegramClient:
    def __init__(self, events: list, name: str, me=object(), start_error=None) -> None:
        self._events, self._name = events, name
        self._me, self._start_error = me, start_error

    def connect(self):
        self._events.append(f"{self._name}:connect")

    def start(self, bot_token):
        self._events.append(f"{self._name}:start")
        if self._start_error:
            raise self._start_error

    def get_me(self):
        return self._me

    def disconnect(self):
        self._events.append(f"{self._name}:disconnect")


def telegram_factory(events: list, **kwargs):
    def make(session_path, api_id, api_hash):
        return FakeTelegramClient(events, Path(session_path).name, **kwargs)

    return make


def llm_factory(events: list):
    class FakeLlmClient:
        def close(self):
            events.append("llm:close")

    def make(api_key, base_url):
        events.append("llm:create")
        return FakeLlmClient()

    return make


def container(tmp_path: Path, events: list, **kwargs) -> Container:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "user.session").touch()
    config_path = tmp_path / "config.toml"
    config_path.write_text(FULL_CONFIG.format(data_dir=tmp_path / "data"))
    return Container(
        config_path,
        make_telegram_client=telegram_factory(events, **kwargs),
        make_llm_client=llm_factory(events),
    )


def test_missing_credentials_point_at_the_config_file(tmp_path):
    # then
    with pytest.raises(SystemExit, match="api_id and api_hash are not set"):
        with create_user_client(AppConfig(tmp_path), CONFIG_PATH, FakePaths(tmp_path)):
            pass


def test_user_client_requires_an_existing_session(tmp_path):
    # given
    cfg = AppConfig(tmp_path, api_id=1, api_hash="hash")

    # then
    with pytest.raises(SystemExit, match="No Telegram session found"):
        with create_user_client(cfg, CONFIG_PATH, FakePaths(tmp_path)):
            pass


def test_missing_bot_token_points_at_the_config_file(tmp_path):
    # then
    with pytest.raises(SystemExit, match="telegram_bot.bot_token is not set"):
        with create_bot_client(AppConfig(tmp_path), CONFIG_PATH, FakePaths(tmp_path)):
            pass


def test_missing_llm_settings_point_at_the_config_file(tmp_path):
    # then
    with pytest.raises(SystemExit, match="llm.api_key is not set. Edit /etc/tgcs.toml"):
        with create_llm_client(AppConfig(tmp_path), CONFIG_PATH):
            pass


def test_unauthorized_user_client_is_disconnected(tmp_path):
    # given
    events = []
    c = container(tmp_path, events, me=None)

    # when
    with pytest.raises(SystemExit, match="session expired or revoked"):
        c.user_client
    c.close()

    # then
    assert events == ["user:connect", "user:disconnect"]


def test_bot_is_disconnected_when_start_fails(tmp_path):
    # given
    events = []
    c = container(tmp_path, events, start_error=RuntimeError("authorization failed"))

    # when
    with pytest.raises(RuntimeError, match="authorization failed"):
        c.bot_client
    c.close()

    # then
    assert events == ["bot:start", "bot:disconnect"]


def test_clients_are_cached_and_closed_in_reverse_order(tmp_path):
    # given
    events = []
    c = container(tmp_path, events)

    # when
    user_client = c.user_client
    c.bot_client
    c.auth_client
    c.llm_client
    c.close()

    # then
    assert c.user_client is user_client
    assert events == [
        "user:connect",
        "bot:start",
        "user:connect",  # auth client: same session, no session/get_me checks
        "llm:create",
        "llm:close",
        "user:disconnect",
        "bot:disconnect",
        "user:disconnect",
    ]


def test_path_manager_creates_private_data_directory(tmp_path):
    data_dir = tmp_path / "data"

    FilePathManager(str(data_dir))

    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o700
