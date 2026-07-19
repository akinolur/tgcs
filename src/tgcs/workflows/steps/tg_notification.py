import logging
from typing import TYPE_CHECKING, Any

from tgcs.workflows.base import Step

if TYPE_CHECKING:
    from tgcs.telegram.notifier import Notificator


logger = logging.getLogger(__name__)


class TgNotificationStep(Step):
    def __init__(self, notificator: "Notificator", users):
        self._notificator = notificator
        self._users = users

    def process(self, data: Any, context: Any) -> Any:
        logger.debug("TgNotificationStep")
        if not data:
            return None
        results = []
        for user in self._users:
            logger.info(f"Sending message to {user}")
            results.append(self._notificator.send_summary(user, data))
        # mark as notified only when every send succeeded,
        # so the notification command can retry failed dates
        if results and all(results):
            self._notificator.mark_notified(context["group_name"], context["date"])
        return data
