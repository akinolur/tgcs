import os
from contextlib import ExitStack
from functools import cached_property
from pathlib import Path

from tgcs.app_config import (
    PACKAGE_NAME,
    AppConfig,
    default_prompts_dir,
    load_config,
)
from tgcs.paths import FilePathManager


class Container:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self._exit_stack = ExitStack()

    def close(self) -> None:
        self._exit_stack.close()

    @cached_property
    def cfg(self) -> AppConfig:
        return load_config(self.config_path)

    @cached_property
    def path_manager(self):
        return FilePathManager(
            base_path=str(self.cfg.data_dir),
            prompt_dir=str(default_prompts_dir()),
        )

    @cached_property
    def llm_client(self):
        from openai import OpenAI  # lazy: openai adds ~450ms to startup

        if not self.cfg.llm_api_key:
            raise SystemExit(f"llm.api_key is not set. Edit {self.config_path}.")
        if not self.cfg.llm_model:
            raise SystemExit(f"llm.model is not set. Edit {self.config_path}.")
        client = OpenAI(
            api_key=self.cfg.llm_api_key,
            base_url=self.cfg.llm_url,
        )
        self._exit_stack.callback(client.close)
        return client

    @cached_property
    def user_client(self):
        from telethon.sync import (
            TelegramClient,  # lazy: telethon adds ~120ms to startup
        )

        if not self.cfg.api_id or not self.cfg.api_hash:
            raise SystemExit(
                f"api_id and api_hash are not set. Edit {self.config_path}."
            )
        session_file = Path(self.path_manager.user_session_path() + ".session")
        if not session_file.exists():
            raise SystemExit(
                f"No Telegram session found. Run '{PACKAGE_NAME} auth login' first."
            )

        # 0o177 masks out group+others entirely: 666 & ~177 = 600 (owner rw only)
        old_umask = os.umask(0o177)
        try:
            client = TelegramClient(
                self.path_manager.user_session_path(),
                self.cfg.api_id,
                self.cfg.api_hash,
            )
            client.connect()
            self._exit_stack.callback(client.disconnect)
        finally:
            os.umask(old_umask)

        if client.get_me() is None:
            raise SystemExit(
                f"Telegram session expired or revoked. "
                f"Run '{PACKAGE_NAME} auth login' again."
            )

        return client

    @cached_property
    def tg_client(self):
        from telethon.sync import (
            TelegramClient,  # lazy: telethon adds ~120ms to startup
        )

        if not self.cfg.api_id or not self.cfg.api_hash:
            raise SystemExit(
                f"api_id and api_hash are not set. Edit {self.config_path}."
            )

        # 0o177 masks out group+others entirely: 666 & ~177 = 600 (owner rw only)
        old_umask = os.umask(0o177)
        try:
            client = TelegramClient(
                self.path_manager.user_session_path(),
                self.cfg.api_id,
                self.cfg.api_hash,
            )
            client.connect()
            self._exit_stack.callback(client.disconnect)
        finally:
            os.umask(old_umask)

        return client

    @cached_property
    def tg_bot(self):
        from telethon.sync import (
            TelegramClient,
        )  # lazy: telethon adds ~120ms to startup

        if not self.cfg.bot_token:
            raise SystemExit(
                f"telegram_bot.bot_token is not set. Edit {self.config_path}."
            )
        # 0o177 masks out group+others entirely: 666 & ~177 = 600 (owner rw only)
        old_umask = os.umask(0o177)
        try:
            client = TelegramClient(
                self.path_manager.bot_session_path(),
                self.cfg.api_id,
                self.cfg.api_hash,
            )
            self._exit_stack.callback(client.disconnect)
            client.start(bot_token=self.cfg.bot_token)
        finally:
            os.umask(old_umask)  # restore original mask (typically 0o022 → 644)
        return client
