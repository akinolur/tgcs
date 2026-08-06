import os
from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager
from functools import cached_property
from pathlib import Path
from typing import Any

from tgcs.app_config import (
    PACKAGE_NAME,
    AppConfig,
    default_prompts_dir,
    load_config,
)
from tgcs.paths import FilePathManager


def _require(value: Any, missing: str, config_path: Path) -> None:
    if not value:
        raise SystemExit(f"{missing}. Edit {config_path}.")


def new_telegram_client(session_path: str, api_id: int, api_hash: str) -> Any:
    from telethon.sync import TelegramClient  # lazy: telethon adds ~120ms to startup

    # 0o177 masks out group+others entirely: 666 & ~177 = 600 (owner rw only)
    old_umask = os.umask(0o177)
    try:
        return TelegramClient(session_path, api_id, api_hash)
    finally:
        os.umask(old_umask)  # restore original mask (typically 0o022 → 644)


def new_llm_client(api_key: str, base_url: str | None) -> Any:
    from openai import OpenAI  # lazy: openai adds ~450ms to startup

    return OpenAI(api_key=api_key, base_url=base_url)


@contextmanager
def create_user_client(
    cfg: AppConfig,
    config_path: Path,
    path_manager: FilePathManager,
    make_telegram_client: Callable[..., Any] = new_telegram_client,
    *,
    verify_session: bool = True,
) -> Generator[Any]:
    """`auth login` passes verify_session=False: it runs before a session exists."""
    _require(
        cfg.api_id and cfg.api_hash, "api_id and api_hash are not set", config_path
    )
    session_path = path_manager.user_session_path()
    if verify_session and not Path(session_path + ".session").exists():
        raise SystemExit(
            f"No Telegram session found. Run '{PACKAGE_NAME} auth login' first."
        )
    client = make_telegram_client(session_path, cfg.api_id, cfg.api_hash)
    try:
        client.connect()
        if verify_session and client.get_me() is None:
            raise SystemExit(
                f"Telegram session expired or revoked. "
                f"Run '{PACKAGE_NAME} auth login' again."
            )
        yield client
    finally:
        client.disconnect()


@contextmanager
def create_bot_client(
    cfg: AppConfig,
    config_path: Path,
    path_manager: FilePathManager,
    make_telegram_client: Callable[..., Any] = new_telegram_client,
) -> Generator[Any]:
    _require(cfg.bot_token, "telegram_bot.bot_token is not set", config_path)
    _require(
        cfg.api_id and cfg.api_hash, "api_id and api_hash are not set", config_path
    )
    client = make_telegram_client(
        path_manager.bot_session_path(), cfg.api_id, cfg.api_hash
    )
    try:
        client.start(bot_token=cfg.bot_token)
        yield client
    finally:
        client.disconnect()


@contextmanager
def create_llm_client(
    cfg: AppConfig,
    config_path: Path,
    make_llm_client: Callable[..., Any] = new_llm_client,
) -> Generator[Any]:
    _require(cfg.llm_api_key, "llm.api_key is not set", config_path)
    _require(cfg.llm_model, "llm.model is not set", config_path)
    client = make_llm_client(cfg.llm_api_key, cfg.llm_url)
    try:
        yield client
    finally:
        client.close()


class Container:
    """
    Each client is built on first use and released in reverse order by close().
    """

    def __init__(
        self,
        config_path: Path,
        *,
        make_telegram_client: Callable[..., Any] = new_telegram_client,
        make_llm_client: Callable[..., Any] = new_llm_client,
    ) -> None:
        self.config_path = config_path
        self._make_telegram_client = make_telegram_client
        self._make_llm_client = make_llm_client
        self._exit_stack = ExitStack()

    def close(self) -> None:
        self._exit_stack.close()

    @cached_property
    def cfg(self) -> AppConfig:
        return load_config(self.config_path)

    @cached_property
    def path_manager(self) -> FilePathManager:
        return FilePathManager(
            base_path=str(self.cfg.data_dir),
            prompt_dir=str(default_prompts_dir()),
        )

    @cached_property
    def user_client(self) -> Any:
        return self._exit_stack.enter_context(
            create_user_client(
                self.cfg,
                self.config_path,
                self.path_manager,
                self._make_telegram_client,
            )
        )

    @cached_property
    def auth_client(self) -> Any:
        return self._exit_stack.enter_context(
            create_user_client(
                self.cfg,
                self.config_path,
                self.path_manager,
                self._make_telegram_client,
                verify_session=False,
            )
        )

    @cached_property
    def bot_client(self) -> Any:
        return self._exit_stack.enter_context(
            create_bot_client(
                self.cfg,
                self.config_path,
                self.path_manager,
                self._make_telegram_client,
            )
        )

    @cached_property
    def llm_client(self) -> Any:
        return self._exit_stack.enter_context(
            create_llm_client(self.cfg, self.config_path, self._make_llm_client)
        )
