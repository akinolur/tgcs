import logging
from typing import TYPE_CHECKING

import typer

from tgcs.container import container

if TYPE_CHECKING:
    from pathlib import Path

    from openai import OpenAI

    from tgcs.paths import FilePathManager
    from tgcs.telegram.notifier import Notificator

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)


@app.callback(invoke_without_command=True)
def summarize(
    ctx: typer.Context,
    name: str = typer.Option(None, "--chat", "-g", help="name or number of chat"),
    all: bool = typer.Option(False, "--all", "-a", help="Summarize all groups."),
    tg_notification: bool = typer.Option(False, "--tg"),
    limit: int | None = None,
    days: int | None = typer.Option(
        None, "--days", "-d", help="Only summarize last N days"
    ),
):
    """Generate LLM summaries for unprocessed dates."""
    if ctx.invoked_subcommand is not None:
        return
    if all and name:
        typer.echo("You can't specify both --all and --name.")
        raise typer.Exit(code=1)
    elif all:
        logger.info("Summarizing all groups")
        llm_client = container.llm_client
        notificator = None
        if tg_notification:
            from tgcs.app_config import default_config_path
            from tgcs.telegram.notifier import Notificator

            if not container.cfg.tg_users:
                raise SystemExit(
                    f"telegram_bot.tg_users is not set. Edit {default_config_path()}."
                )
            notificator = Notificator(container.bot_client, container.path_manager)
        _summarize_all(
            path_manager=container.path_manager,
            notificator=notificator,
            model=container.cfg.llm_model,
            llm_client=llm_client,
            template_path=container.cfg.summary_template_path,
            users=container.cfg.tg_users,
            limit=limit,
            days=days,
        )
    elif name:
        if name.isnumeric():
            name = _get_group_name_by_number(  # noqa: PLW2901
                container.path_manager, int(name)
            )
        logger.info(f"Summarizing group: {name}")
        llm_client = container.llm_client
        notificator = None
        if tg_notification:
            from tgcs.app_config import default_config_path
            from tgcs.telegram.notifier import Notificator

            if not container.cfg.tg_users:
                raise SystemExit(
                    f"telegram_bot.tg_users is not set. Edit {default_config_path()}."
                )
            notificator = Notificator(container.bot_client, container.path_manager)
        _summarize_group(
            path_manager=container.path_manager,
            notificator=notificator,
            model=container.cfg.llm_model,
            llm_client=llm_client,
            template_path=container.cfg.summary_template_path,
            users=container.cfg.tg_users,
            group_name=name,
            limit=limit,
            days=days,
        )
    else:
        typer.echo("You must specify either --chat or --all.")
        raise typer.Exit(code=1)


@app.command()
def preview():
    """Render the summary template with sample data.

    Useful for testing custom templates.
    """
    import chevron

    from tgcs.app_config import DEFAULT_SUMMARY_TEMPLATE

    path = container.cfg.summary_template_path
    if path and path.exists():
        template = path.read_text()
        typer.echo(f"Template: {path}\n")
    else:
        template = DEFAULT_SUMMARY_TEMPLATE
        typer.echo("Template: built-in default\n")

    sample = {
        "group_name": "my_group",
        "date": "2025-01-01",
        "threads": [
            {
                "name": "First topic",
                "count": 12,
                "url": "https://t.me/my_group/100/",
                "thread_id": 100,
            },
            {
                "name": "Second topic",
                "count": 5,
                "url": "https://t.me/my_group/200/",
                "thread_id": 200,
            },
            {
                "name": "Third topic",
                "count": 3,
                "url": "https://t.me/my_group/300/",
                "thread_id": 300,
            },
        ],
    }
    try:
        typer.echo(chevron.render(template, sample))
    except Exception as e:
        typer.echo(f"Error rendering template: {e}", err=True)
        raise typer.Exit(code=1)


def _summarize_group(
    path_manager: "FilePathManager",
    notificator: "Notificator | None",
    model: str | None,
    llm_client: "OpenAI",
    template_path: "Path | None",
    users: list[str],
    group_name: str,
    limit: int | None,
    days: int | None = None,
) -> None:
    from tgcs.summary_creator import SummaryCreator
    from tgcs.workflows.pipelines import thread_workflow, thread_workflow_tg_notify

    workflow = thread_workflow(
        path_manager=path_manager,
        model=model,
        llm_client=llm_client,
        template_path=template_path,
    )
    if notificator is not None:
        workflow = thread_workflow_tg_notify(
            path_manager=path_manager,
            model=model,
            llm_client=llm_client,
            template_path=template_path,
            notificator=notificator,
            users=users,
        )
    SummaryCreator(path_manager, workflow).process_unprocessed_dates(
        group_name, limit, last_days=days
    )


def _get_group_name_by_number(path_manager: "FilePathManager", number: int) -> str:
    return path_manager.groups_list()[number - 1]


def _summarize_all(
    path_manager: "FilePathManager",
    notificator: "Notificator | None",
    model: str | None,
    llm_client: "OpenAI",
    template_path: "Path | None",
    users: list[str],
    limit: int | None,
    days: int | None = None,
) -> None:
    for group_name in path_manager.groups_list():
        _summarize_group(
            path_manager=path_manager,
            notificator=notificator,
            model=model,
            llm_client=llm_client,
            template_path=template_path,
            users=users,
            group_name=group_name,
            limit=limit,
            days=days,
        )
