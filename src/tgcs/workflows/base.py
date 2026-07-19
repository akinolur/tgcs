from abc import ABC, abstractmethod
from typing import Any


class Step(ABC):
    @abstractmethod
    def process(self, data: Any, context: Any) -> Any:
        pass

    def get_context(self) -> dict["str", Any] | None:
        return None


class ResumableStep(Step):
    def process(self, data: Any, context: Any) -> Any:
        if self.is_already_completed(data, context):
            return self.load_result(data, context)
        result = self._process(data, context)
        self.save_result(data, context, result)
        return result

    @abstractmethod
    def _process(self, data: Any, context: Any) -> Any:
        pass

    @abstractmethod
    def is_already_completed(self, data: Any, context: Any) -> bool:
        pass

    @abstractmethod
    def load_result(self, data: Any, context: Any) -> Any:
        pass

    @abstractmethod
    def save_result(self, data: Any, context: Any, result) -> None:
        pass


class WorkflowExecutor:
    def __init__(self, steps: list[Step], context: Any = None):
        self.steps = steps
        self.context = context or {}

    def run(self, initial_data: Any = None):
        data = initial_data
        context = self.context
        for step in self.steps:
            data = step.process(data, context)
            if step.get_context() is not None:
                context = step.get_context()
        return data
