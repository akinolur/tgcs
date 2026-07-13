import os
from functools import cached_property
from pathlib import Path

from tgcs.app_config import (
    PACKAGE_NAME,
    default_config_path,
    default_prompts_dir,
    load_config,
)
from tgcs.paths import FilePathManager


class Container:
    @cached_property
    def cfg(self):
        return load_config()

    @cached_property
    def path_manager(self):
        return FilePathManager(
            base_path=str(self.cfg.data_dir),
            prompt_dir=str(default_prompts_dir()),
        )

    @cached_property
    def user_client(self):
        from telethon.sync import (
            TelegramClient,  # lazy: telethon adds ~120ms to startup
        )

        if not self.cfg.api_id or not self.cfg.api_hash:
            raise SystemExit(
                f"api_id and api_hash are not set. Edit {default_config_path()}."
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
        finally:
            os.umask(old_umask)

        if client.get_me() is None:
            raise SystemExit(
                f"Telegram session expired or revoked. "
                f"Run '{PACKAGE_NAME} auth login' again."
            )

        return client

    @cached_property
    def bot_client(self):
        from telethon.sync import (
            TelegramClient,
        )  # lazy: telethon adds ~120ms to startup

        if not self.cfg.bot_token:
            raise SystemExit(
                f"telegram_bot.bot_token is not set. Edit {default_config_path()}."
            )
        # 0o177 masks out group+others entirely: 666 & ~177 = 600 (owner rw only)
        old_umask = os.umask(0o177)
        try:
            client = TelegramClient(
                self.path_manager.bot_session_path(),
                self.cfg.api_id,
                self.cfg.api_hash,
            )
            client.start(bot_token=self.cfg.bot_token)
        finally:
            os.umask(old_umask)  # restore original mask (typically 0o022 → 644)
        return client


container = Container()
