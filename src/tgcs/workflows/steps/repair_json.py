from typing import Any

import json_repair

from tgcs.workflows.base import Step


class RepairJsonStep(Step):
    def process(self, data: Any, context: Any) -> Any:
        decoded_object = json_repair.loads(data)
        return decoded_object
