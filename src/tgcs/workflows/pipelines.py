from typing import TYPE_CHECKING

from tgcs.workflows.base import WorkflowExecutor
from tgcs.workflows.steps.generate_threads_name import GenerateThreadsNameStep
from tgcs.workflows.steps.postprocess import PostProcessStep
from tgcs.workflows.steps.prepare_threads import PrepareThreadsStep
from tgcs.workflows.steps.repair_json import RepairJsonStep

if TYPE_CHECKING:
    from pathlib import Path

    from openai import OpenAI

    from tgcs.paths import FilePathManager
    from tgcs.telegram.notifier import Notificator


def thread_workflow(
    path_manager: "FilePathManager",
    model: str | None,
    llm_client: "OpenAI",
    template_path: "Path | None",
) -> WorkflowExecutor:
    return WorkflowExecutor(
        steps=[
            PrepareThreadsStep(),
            GenerateThreadsNameStep(
                path_manager,
                model=model,
                client=llm_client,
            ),
            RepairJsonStep(),
            PostProcessStep(
                template_path=template_path,
            ),
        ]
    )


def thread_workflow_tg_notify(
    path_manager: "FilePathManager",
    model: str | None,
    llm_client: "OpenAI",
    template_path: "Path | None",
    notificator: "Notificator",
    users: list[str],
) -> WorkflowExecutor:
    from tgcs.workflows.steps.tg_notification import TgNotificationStep

    return WorkflowExecutor(
        steps=[
            PrepareThreadsStep(),
            GenerateThreadsNameStep(
                path_manager,
                model=model,
                client=llm_client,
            ),
            RepairJsonStep(),
            PostProcessStep(
                template_path=template_path,
            ),
            TgNotificationStep(
                notificator,
                users=users,
            ),
        ]
    )
