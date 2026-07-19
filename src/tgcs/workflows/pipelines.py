from tgcs.app_config import default_config_path
from tgcs.container import container
from tgcs.workflows.base import WorkflowExecutor
from tgcs.workflows.steps.generate_threads_name import GenerateThreadsNameStep
from tgcs.workflows.steps.postprocess import PostProcessStep
from tgcs.workflows.steps.prepare_threads import PrepareThreadsStep
from tgcs.workflows.steps.repair_json import RepairJsonStep


def thread_workflow():
    return WorkflowExecutor(
        steps=[
            PrepareThreadsStep(),
            GenerateThreadsNameStep(
                container.path_manager,
                model=container.cfg.llm_model,
                client=container.llm_client,
            ),
            RepairJsonStep(),
            PostProcessStep(
                template_path=container.cfg.summary_template_path,
                bot_username=container.cfg.bot_username or "",
            ),
        ]
    )


def thread_workflow_tg_notify():
    from tgcs.telegram.notifier import Notificator
    from tgcs.workflows.steps.tg_notification import TgNotificationStep

    if not container.cfg.tg_users:
        raise SystemExit(
            f"telegram_bot.tg_users is not set. Edit {default_config_path()}."
        )
    return WorkflowExecutor(
        steps=[
            PrepareThreadsStep(),
            GenerateThreadsNameStep(
                container.path_manager,
                model=container.cfg.llm_model,
                client=container.llm_client,
            ),
            RepairJsonStep(),
            PostProcessStep(
                template_path=container.cfg.summary_template_path,
                bot_username=container.cfg.bot_username or "",
            ),
            TgNotificationStep(
                Notificator(container.bot_client, container.path_manager),
                users=container.cfg.tg_users,
            ),
        ]
    )
