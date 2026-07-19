import json
import logging
import os
from datetime import datetime, timedelta

from tgcs.paths import FilePathManager
from tgcs.workflows.base import WorkflowExecutor

logger = logging.getLogger(__name__)


class SummaryCreator:
    def __init__(self, path_manager: FilePathManager, workflow: WorkflowExecutor):
        self.path_manager = path_manager
        self.workflow = workflow

    def _is_date_processed(self, group_name, date):
        """
        Check if the date has been processed (i.e., summary.md exists)
        """
        summary_file_path = self.path_manager.summary_path(group_name, date)
        return os.path.exists(summary_file_path)

    def _get_all_dates(self, group_name):
        """
        Get all dates for which there are messages
        """
        group_path = self.path_manager.history_folder_path(group_name)
        # Assuming messages are stored in directories named by date
        return sorted(
            [
                d
                for d in os.listdir(group_path)
                if os.path.isdir(os.path.join(group_path, d))
                and not d.startswith(".")  # for claude
            ]
        )

    def get_unprocessed_dates(self, group_name, last_days=None):
        """
        Get dates that have not been processed yet
        """
        group_path = self.path_manager.history_folder_path(group_name)
        if not os.path.exists(group_path):
            return []

        all_dates = self._get_all_dates(group_name)
        unprocessed_dates = [
            date for date in all_dates if not self._is_date_processed(group_name, date)
        ]
        if last_days is not None:
            cutoff = (datetime.today() - timedelta(days=last_days)).strftime("%Y-%m-%d")
            unprocessed_dates = [d for d in unprocessed_dates if d >= cutoff]
        return unprocessed_dates

    def _acquire_lock(self, group_name, date):
        """
        Acquire a lock for processing the date
        """
        lock_file_path = self.path_manager.lock_path(group_name, date)
        if os.path.exists(lock_file_path):
            return False
        with open(lock_file_path, "w") as lock_file:
            lock_file.write(str(os.getpid()))
        return True

    def _release_lock(self, group_name, date):
        """
        Release the lock for processing the date
        """
        lock_file_path = self.path_manager.lock_path(group_name, date)
        if os.path.exists(lock_file_path):
            os.remove(lock_file_path)

    def process_unprocessed_dates(self, group_name, n=None, last_days=None):
        """
        Process all unprocessed dates
        """
        unprocessed_dates = self.get_unprocessed_dates(group_name, last_days)
        if n is not None:
            unprocessed_dates = unprocessed_dates[:n]
        for date in unprocessed_dates:
            if self._acquire_lock(group_name, date):
                # print(f"Acquire lock {date}")
                try:
                    logger.info(f"[{date}] {group_name}")
                    self._process_date(group_name, date)
                finally:
                    self._release_lock(group_name, date)
                    # print(f"Release lock {date}\n")

    def _process_date(self, group_name, date):
        """
        Process the date
        """
        date_history_path = self.path_manager.date_history_path(group_name, date)
        with open(date_history_path, "r") as f:
            history_raw = f.read()
        metadata_path = self.path_manager.group_metadata_path(group_name)
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        context = {
            "link_prefix": metadata["link_prefix"],
            "group_name": group_name,
            "date": date,
        }
        self.workflow.context = context
        summary = self.workflow.run(history_raw)
        if summary:
            self._save_summary(group_name, date, summary)
        return summary

    def _save_summary(self, group_name, date, summary):
        """
        Save the summary
        """
        summary_path = self.path_manager.summary_path(group_name, date)
        with open(summary_path, "w") as f:
            f.write(summary)
