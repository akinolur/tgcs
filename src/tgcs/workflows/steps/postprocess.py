import logging
from pathlib import Path
from typing import Any

import chevron

from tgcs.app_config import DEFAULT_SUMMARY_TEMPLATE
from tgcs.models import Thread
from tgcs.workflows.base import Step

logger = logging.getLogger(__name__)


class PostProcessStep(Step):
    def __init__(self, template_path: Path | None = None, bot_username: str = ""):
        if template_path is not None and template_path.exists():
            self.template = template_path.read_text()
        else:
            self.template = DEFAULT_SUMMARY_TEMPLATE
        self.bot_username = bot_username

    def _get_threads(self, data: Any, context: Any) -> list[Thread]:
        threads: list[Thread] = context["threads"]
        assert len(threads) == len(data["threads"]), (
            f"PostProcessStep: length of threads [{len(threads)}] != length of threads summaries [{len(data['threads'])}]."  # noqa: E501
            f"\nTry to remove summary of {context['group_name']} {context['date']}\n"
        )
        try:
            thread_names_map = {
                thread["id"]: thread["name"] for thread in data["threads"]
            }
        except KeyError as ex:
            logger.error(f"KeyError: {ex}")
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
            "bot_username": self.bot_username,
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
