import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class FilePathManager:
    def __init__(self, base_path: str = "data", prompt_dir: str = "prompts"):
        self.base_path = base_path
        os.makedirs(base_path, mode=0o700, exist_ok=True)
        self.prompt_dir = prompt_dir
        self.history_folder_name = "history"
        self.threads_folder_name = "threads"
        self.date_history_filename = "history.jsonl"
        self.raw_history_filename = "raw_chat_history.jsonl"
        self.summary_filename = "summary.md"
        self.lock_filename = "processing.lock"
        self.group_metadata_filename = "metadata.json"
        self.additional_requirements_filename = "additional_requirements.md"
        self.thread_names_filename_raw = "thread_names_raw.txt"
        self.notified_filename = "notified"

    def threads_folder_path(self, group_name: str) -> str:
        return os.path.join(self.base_path, group_name, self.threads_folder_name)

    def thread_file_path(self, group_name: str, date_str: str, root_id: int) -> str:
        return os.path.join(
            self.threads_folder_path(group_name), f"{date_str}-{root_id}.jsonl"
        )

    def group_metadata_path(self, group_name):
        return os.path.join(self.base_path, group_name, self.group_metadata_filename)

    def summary_path(self, group_name, date_str):
        date_history_path = self.date_history_folder_path(group_name, date_str)
        return os.path.join(date_history_path, self.summary_filename)

    def history_folder_path(self, group_name):
        path = os.path.join(self.base_path, group_name, self.history_folder_name)
        return path

    def date_history_folder_path(self, group_name, date_str):
        history_folder_path = self.history_folder_path(group_name)
        return os.path.join(history_folder_path, date_str)

    def date_history_path(self, group_name, date_str):
        date_history_path = self.date_history_folder_path(group_name, date_str)
        return os.path.join(date_history_path, self.date_history_filename)

    def raw_history_path(self, group_name):
        date_history_path = self.history_folder_path(group_name)
        return os.path.join(date_history_path, self.raw_history_filename)

    def lock_path(self, group_name, date_str):
        date_history_path = self.date_history_folder_path(group_name, date_str)
        return os.path.join(date_history_path, self.lock_filename)

    def create_folders_if_not_exists(
        self, group_name: str, date_str: str | None = None
    ):
        history_folder_path = self.history_folder_path(group_name)
        os.makedirs(history_folder_path, exist_ok=True)
        if date_str:
            date_history_folder_path = self.date_history_folder_path(
                group_name, date_str
            )
            os.makedirs(date_history_folder_path, exist_ok=True)

    def read_metadata(self, group_name: str) -> dict | None:
        """Metadata of one chat, or None if it is missing or unreadable.

        One corrupt file must not take down commands that walk every chat.
        """
        metadata_path = self.group_metadata_path(group_name)
        if not os.path.exists(metadata_path):
            return None
        try:
            with open(metadata_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as ex:
            logger.warning(f"Skipping {group_name}: cannot read {metadata_path}: {ex}")
            return None

    def _flag(self, metadata: dict, flag_name: str) -> bool:
        # "enabled" is the legacy flag that used to gate both actions
        return metadata.get(flag_name, metadata.get("enabled", True))

    def is_downloading_enabled(self, group_name: str) -> bool:
        metadata = self.read_metadata(group_name)
        # an unknown or unreadable chat is not enabled for anything
        return self._flag(metadata, "downloading_enabled") if metadata else False

    def is_summarization_enabled(self, group_name: str) -> bool:
        metadata = self.read_metadata(group_name)
        return self._flag(metadata, "summarization_enabled") if metadata else False

    def set_downloading_enabled(self, group_name: str, enabled: bool) -> None:
        metadata_path = self.group_metadata_path(group_name)
        metadata = self.read_metadata(group_name)
        if metadata is None:
            # nothing safe to rewrite; the warning is already logged
            return
        legacy_enabled = metadata.pop("enabled", None)
        if legacy_enabled is not None:
            metadata.setdefault("summarization_enabled", legacy_enabled)
        metadata["downloading_enabled"] = enabled
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)

    def download_groups_list(self) -> list[str]:
        return [name for name, downloading, _ in self.all_groups_list() if downloading]

    def summarize_groups_list(self) -> list[str]:
        return [
            name for name, _, summarization in self.all_groups_list() if summarization
        ]

    def all_groups_list(self) -> list[tuple[str, bool, bool]]:
        if not os.path.isdir(self.base_path):
            return []
        groups = []
        for group_name in os.listdir(self.base_path):
            metadata = self.read_metadata(group_name)
            if metadata is None:
                continue
            groups.append(
                (
                    group_name,
                    self._flag(metadata, "downloading_enabled"),
                    self._flag(metadata, "summarization_enabled"),
                )
            )
        return groups

    def additional_requirements_path(self, group_name: str) -> str:
        additional_requirements_path = os.path.join(
            self.base_path,
            group_name,
            self.additional_requirements_filename,
        )
        return additional_requirements_path

    def notified_path(self, group_name: str, date_str: str) -> str:
        return os.path.join(
            self.date_history_folder_path(group_name, date_str), self.notified_filename
        )

    def thread_names_raw_path(self, group_name: str, date_str: str) -> str:
        date_folder = self.date_history_folder_path(group_name, date_str)
        return os.path.join(date_folder, self.thread_names_filename_raw)

    def prompt_path(self, prompt_name: str) -> str:
        user_path = Path(self.prompt_dir) / prompt_name
        if user_path.exists():
            return str(user_path)
        return str(Path(__file__).parent / "prompts" / prompt_name)

    def bot_session_path(self) -> str:
        return os.path.join(self.base_path, "bot")

    def user_session_path(self) -> str:
        return os.path.join(self.base_path, "user")
