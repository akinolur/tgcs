import logging

import typer

from tgcs.container import container

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
        _summarize_all(tg_notification, limit, days)
    elif name:
        if name.isnumeric():
            name = _get_group_name_by_number(int(name))  # noqa: PLW2901
        logger.info(f"Summarizing group: {name}")
        _summarize_group(name, tg_notification, limit, days)
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


def _summarize_group(group_name: str, tg_notification, limit, days=None):
    from tgcs.summary_creator import SummaryCreator
    from tgcs.workflows.pipelines import thread_workflow, thread_workflow_tg_notify

    workflow = thread_workflow()
    if tg_notification:
        workflow = thread_workflow_tg_notify()
    SummaryCreator(container.path_manager, workflow).process_unprocessed_dates(
        group_name, limit, last_days=days
    )


def _get_group_name_by_number(number: int) -> str:
    return container.path_manager.groups_list()[number - 1]


def _summarize_all(tg_notification, limit, days=None):
    for group_name in container.path_manager.groups_list():
        _summarize_group(group_name, tg_notification, limit, days)
