import json
import os
from pathlib import Path


class FilePathManager:
    def __init__(self, base_path: str = "data", prompt_dir: str = "prompts"):
        self.base_path = base_path  # triggers setter which creates the dir
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

    @property
    def base_path(self) -> str:
        return self._base_path

    @base_path.setter
    def base_path(self, value: str) -> None:
        self._base_path = value
        os.makedirs(value, exist_ok=True)

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

    def is_enabled(self, group_name: str) -> bool:
        metadata_path = self.group_metadata_path(group_name)
        if not os.path.exists(metadata_path):
            return False
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)
        return metadata.get("enabled", True)

    def set_enabled(self, group_name: str, enabled: bool) -> None:
        metadata_path = self.group_metadata_path(group_name)
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)
        metadata["enabled"] = enabled
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)

    def groups_list(self) -> list[str]:
        groups = []
        for group_name in os.listdir(self.base_path):
            metadata_path = self.group_metadata_path(group_name)
            if os.path.exists(metadata_path) and self.is_enabled(group_name):
                groups.append(group_name)
        return groups

    def all_groups_list(self) -> list[tuple[str, bool]]:
        groups = []
        for group_name in os.listdir(self.base_path):
            metadata_path = self.group_metadata_path(group_name)
            if os.path.exists(metadata_path):
                groups.append((group_name, self.is_enabled(group_name)))
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
