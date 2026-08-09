import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import chevron

from tgcs.app_config import DEFAULT_SUMMARY_TEMPLATE
from tgcs.models import Thread
from tgcs.workflows.base import Step

if TYPE_CHECKING:
    from tgcs.paths import FilePathManager

logger = logging.getLogger(__name__)


class PostProcessStep(Step):
    def __init__(
        self,
        template_path: Path | None = None,
        path_manager: "FilePathManager | None" = None,
    ):
        if template_path is not None and template_path.exists():
            self.template = template_path.read_text()
        else:
            self.template = DEFAULT_SUMMARY_TEMPLATE
        self._path_manager = path_manager

    def _discard_cached_answer(self, context: Any) -> None:
        """Drop the stored llm answer so the next run asks the model again.

        GenerateThreadsNameStep replays its saved answer from disk, so an
        unusable one would otherwise be reused forever and the date could
        never be summarized.
        """
        if self._path_manager is None:
            return
        path = self._path_manager.thread_names_raw_path(
            context["group_name"], context["date"]
        )
        if os.path.exists(path):
            os.remove(path)
            logger.warning(f"Discarded unusable llm answer: {path}")

    def _get_threads(self, data: Any, context: Any) -> list[Thread]:
        threads: list[Thread] = context["threads"]
        where = f"{context['group_name']} {context['date']}"
        answers = data.get("threads") if isinstance(data, dict) else None
        if not isinstance(answers, list):
            logger.error(f"[{where}] llm answer has no 'threads' list")
            self._discard_cached_answer(context)
            return []
        try:
            thread_names_map = {thread["id"]: thread["name"] for thread in answers}
        except (KeyError, TypeError) as ex:
            logger.error(f"[{where}] malformed thread in llm answer: {ex}")
            self._discard_cached_answer(context)
            return []
        missing = [t.id for t in threads if t.id not in thread_names_map]
        if missing:
            logger.error(
                f"[{where}] llm named {len(thread_names_map)} of {len(threads)} "
                f"threads, missing ids: {missing}"
            )
            self._discard_cached_answer(context)
            return []
        for thread in threads:
            thread.name = thread_names_map[thread.id]
        return threads

    def process(self, data: Any, context: Any) -> str | None:
        logger.debug("PostProcessStep")
        if not data:
            return None
        threads = self._get_threads(data, context)
        if not threads:
            return None
        ctx = {
            "group_name": context["group_name"],
            "date": context["date"],
            "threads": [
                {
                    "name": t.name,
                    "count": t.len,
                    "url": t.url,
                    "thread_id": t.thread_starter_id,
                }
                for t in threads
            ],
        }
        return chevron.render(self.template, ctx)
