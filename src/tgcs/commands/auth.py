import asyncio
import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from tgcs.app_config import PACKAGE_NAME

if TYPE_CHECKING:
    from tgcs.container import Container

app = typer.Typer(no_args_is_help=True, rich_markup_mode=None)


def _print_qr(url: str, expires_in: float) -> None:
    import qrcode

    qr = qrcode.QRCode()
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    typer.echo(f"\nOr open this URL in a browser / QR generator:\n{url}")
    typer.echo(f"\nBoth expire in ~{round(expires_in)} seconds - scan now.\n")


@app.command()
def status(ctx: typer.Context):
    """Show current Telegram authentication status."""
    container: "Container" = ctx.obj
    if not container.cfg.api_id or not container.cfg.api_hash:
        typer.echo(f"api_id and api_hash are not set. Edit {container.config_path}.")
        raise typer.Exit(code=1)

    session_file = Path(container.path_manager.user_session_path() + ".session")
    if not session_file.exists():
        typer.echo(f"Not logged in. Run '{PACKAGE_NAME} auth login'.")
        raise typer.Exit(code=1)

    client = container.user_client
    me = client.get_me()
    typer.echo(f"Logged in as @{me.username} (id: {me.id})")


@app.command()
def login(ctx: typer.Context):
    """Authenticate via Telegram QR code (no phone number required)."""
    container: "Container" = ctx.obj
    from telethon.errors import SessionPasswordNeededError

    if not container.cfg.api_id or not container.cfg.api_hash:
        typer.echo(f"api_id and api_hash are not set. Edit {container.config_path}.")
        raise typer.Exit(code=1)

    client = container.auth_client

    if client.is_user_authorized():
        me = client.get_me()
        typer.echo(f"Already logged in as @{me.username} (id: {me.id}).")
        return

    qr_login = client.qr_login()
    expires_in = _seconds_until(qr_login.expires)

    typer.echo(
        "Scan this QR code with your Telegram app (Settings → Devices → Scan QR):\n"
    )
    _print_qr(qr_login.url, expires_in)
    typer.echo("Waiting for scan... (Ctrl+C to cancel)")

    try:
        client.loop.run_until_complete(qr_login.wait(expires_in))
    except (asyncio.TimeoutError, TimeoutError):
        typer.echo(
            f"\nThe QR code and link expired after {round(expires_in)} seconds "
            "without being scanned.\n"
            f"Run '{PACKAGE_NAME} auth login' again to get a fresh one."
        )
        raise typer.Exit(code=1) from None
    except SessionPasswordNeededError:
        password = typer.prompt("2FA password", hide_input=True)
        client.sign_in(password=password)

    me = client.get_me()
    typer.echo(f"Authenticated as @{me.username} (id: {me.id})")


def _seconds_until(expires: datetime.datetime) -> float:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    return (expires - now).total_seconds()
