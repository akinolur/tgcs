import logging
from typing import Any

from tgcs.threads import build_threads
from tgcs.workflows.base import Step

logger = logging.getLogger(__name__)


class PrepareThreadsStep(Step):
    _context = None

    def _choose_threads(self, threads, number_of_threads=5, min_length=4):
        """
        Choose threads to summarize
        """
        sorted_threads = sorted(threads, key=lambda t: len(t.messages), reverse=True)
        sorted_threads = [t for t in sorted_threads if len(t.messages) >= min_length]
        return sorted_threads[:number_of_threads]

    def _prepare_threads(self, threads):
        """
        Prepare the threads to be summarized
        """
        data = []
        for i, thread in enumerate(threads):
            messages = thread.messages
            messages = [m["message"] for m in messages]
            # messages = [f'{m["sender_id"]}: {m["message"]}' for m in messages]
            data.append({"thread_id": thread.id, "messages": messages})
        return data

    def process(self, data: Any, context: Any) -> Any:
        logger.debug("PrepareThreadsStep")
        self._context = context
        # data: raw daily tg history json string
        threads = build_threads(data)
        chosen_threads = self._choose_threads(threads)
        for i, thread in enumerate(chosen_threads):
            thread.id = i + 1
            thread.link_prefix = context["link_prefix"]
        self._context["threads"] = chosen_threads
        data = self._prepare_threads(chosen_threads)
        return data
        # data_json = json.dumps(data, ensure_ascii=False, indent=4)
        # return data_json

    def get_context(self):
        return self._context
