import logging
import os
from typing import TYPE_CHECKING

from tgcs.dates import cutoff

if TYPE_CHECKING:
    from telethon.sync import TelegramClient

    from tgcs.paths import FilePathManager


logger = logging.getLogger(__name__)


class Notificator:
    def __init__(self, client: "TelegramClient", path_manager: "FilePathManager"):
        self._client = client
        self._path_manager = path_manager

    def load_unnotified_summaries(self, group_name, last_days=None):
        history_path = self._path_manager.history_folder_path(group_name)
        all_dates = sorted(
            [
                d
                for d in os.listdir(history_path)
                if os.path.isdir(os.path.join(history_path, d))
            ]
        )

        if last_days is not None:
            all_dates = [d for d in all_dates if d >= cutoff(last_days)]

        result = []
        for date in all_dates:
            summary_path = self._path_manager.summary_path(group_name, date)
            notified_path = self._path_manager.notified_path(group_name, date)
            if os.path.exists(summary_path) and not os.path.exists(notified_path):
                with open(summary_path, "r") as f:
                    result.append((date, f.read()))
        return result

    def mark_notified(self, group_name, date):
        notified_path = self._path_manager.notified_path(group_name, date)
        open(notified_path, "w").close()

    def send_summary(self, user_id, text) -> bool:
        try:
            self._client.send_message(int(user_id), text, link_preview=False)
            logger.info(f"Message sent to {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {user_id}: {e}")
            return False

    def notify(self, group_name, user_ids, last_days=None):
        entries = self.load_unnotified_summaries(group_name, last_days)
        for date, summary in entries:
            results = [self.send_summary(user_id, summary) for user_id in user_ids]
            # mark notified only when every recipient got it, so a failed send
            # can be retried on the next run
            if results and all(results):
                self.mark_notified(group_name, date)
        return len(entries)
