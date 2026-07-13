import logging
from importlib.metadata import version as _pkg_version
from pathlib import Path

import typer

from tgcs.app_config import (
    PACKAGE_NAME,
    default_config_path,
    load_config,
    write_default_config,
)
from tgcs.commands import auth, chats
from tgcs.container import container
from tgcs.logging_setup import setup_logging

logger = logging.getLogger(__name__)

app = typer.Typer(
    no_args_is_help=True, pretty_exceptions_enable=False, rich_markup_mode=None
)
app.add_typer(auth.app, name="auth", help="Manage Telegram authentication.")
app.add_typer(chats.app, name="chats", help="Manage chat groups and download history.")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"{PACKAGE_NAME} {_pkg_version(PACKAGE_NAME)}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
        is_flag=True,
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help=f"Path to config file (default: ~/.config/{PACKAGE_NAME}/config.toml)",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose output."
    ),
):
    setup_logging(verbose)
    if config is not None:
        cfg = load_config(config)
        container.path_manager.base_path = str(cfg.data_dir)


def _get_groups():
    return container.path_manager.groups_list()


def _get_group_name_by_number(number: int):
    group_names = _get_groups()
    return group_names[number - 1]


@app.command()
def notification(
    name: str = typer.Option(None, "--chat", "-g", help="name or number of chat"),
    all: bool = typer.Option(
        False, "--all", "-a", help="Download history for all groups."
    ),
    days: int | None = typer.Option(
        None, "--days", "-d", help="Only notify for last N days"
    ),
):
    """Send saved summaries as Telegram notifications."""
    if name.isnumeric():
        name = _get_group_name_by_number(int(name))

    from tgcs.telegram.notifier import Notificator

    notificator = Notificator(container.bot_client, container.path_manager)
    user_id = container.cfg.tg_users[0]
    notificator.notify(name, user_id, last_days=days)


@app.command()
def init(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing config"
    ),
):
    """Create default config and summary template if they don't exist."""
    from tgcs.app_config import (
        default_prompts_dir,
        default_summary_template_path,
        write_default_prompts,
        write_default_summary_template,
    )

    config_path = default_config_path()
    if config_path.exists() and not force:
        typer.echo(f"Config already exists: {config_path}")
    else:
        write_default_config(config_path)
        typer.echo(f"Config created: {config_path}")

    template_path = default_summary_template_path()
    if template_path.exists() and not force:
        typer.echo(f"Summary template already exists: {template_path}")
    else:
        write_default_summary_template(template_path)
        typer.echo(f"Summary template created: {template_path}")

    prompt_path = default_prompts_dir() / "summary.toml"
    if prompt_path.exists() and not force:
        typer.echo(f"Prompt template already exists: {prompt_path}")
    else:
        write_default_prompts()
        typer.echo(f"Prompt template created: {prompt_path}")


if __name__ == "__main__":
    app()
