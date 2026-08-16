import fcntl
import json
import logging
import os

from tgcs.dates import cutoff
from tgcs.layouts import Layout
from tgcs.paths import FilePathManager
from tgcs.workflows.base import WorkflowExecutor

logger = logging.getLogger(__name__)


class SummaryCreator:
    def __init__(self, path_manager: FilePathManager, workflow: WorkflowExecutor):
        self.path_manager = path_manager
        self.workflow = workflow
        # open lock descriptors by (group, date); the flock lives as long as
        # the descriptor does
        self._lock_fds: dict[tuple[str, str], int] = {}

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
        if self.path_manager.layout(group_name) is Layout.SINGLE:
            # a chat switched over from the daily layout keeps its old date
            # folders; summarizing them again would burn llm calls and notify
            # about history the user already saw
            return []

        group_path = self.path_manager.history_folder_path(group_name)
        if not os.path.exists(group_path):
            return []

        all_dates = self._get_all_dates(group_name)
        unprocessed_dates = [
            date for date in all_dates if not self._is_date_processed(group_name, date)
        ]
        if last_days is not None:
            unprocessed_dates = [d for d in unprocessed_dates if d >= cutoff(last_days)]
        return unprocessed_dates

    def _acquire_lock(self, group_name, date):
        """
        Acquire a lock for processing the date
        """
        lock_file_path = self.path_manager.lock_path(group_name, date)
        fd = os.open(lock_file_path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            # the kernel drops this when the holder exits or is killed, so a
            # crashed run cannot leave a lock that blocks the date forever
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            logger.info(f"[{date}] {group_name}: locked by another run, skipping")
            return False
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        self._lock_fds[(group_name, date)] = fd
        return True

    def _release_lock(self, group_name, date):
        """
        Release the lock for processing the date
        """
        fd = self._lock_fds.pop((group_name, date), None)
        if fd is None:
            return
        # the file itself is kept: unlinking it while another run has the same
        # inode open would let that run lock an orphaned inode and process the
        # date in parallel. closing the descriptor releases the flock, which is
        # what actually guards the date
        os.ftruncate(fd, 0)
        os.close(fd)

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
