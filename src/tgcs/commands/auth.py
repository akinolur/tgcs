import os
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from tgcs.app_config import PACKAGE_NAME

if TYPE_CHECKING:
    from tgcs.container import Container

app = typer.Typer(no_args_is_help=True, rich_markup_mode=None)


@app.command()
def status(ctx: typer.Context):
    """Show current Telegram authentication status."""
    container: "Container" = ctx.obj
    from telethon.sync import TelegramClient  # lazy: telethon adds ~120ms to startup

    if not container.cfg.api_id or not container.cfg.api_hash:
        typer.echo(f"api_id and api_hash are not set. Edit {container.config_path}.")
        raise typer.Exit(code=1)

    session_file = Path(container.path_manager.user_session_path() + ".session")
    if not session_file.exists():
        typer.echo(f"Not logged in. Run '{PACKAGE_NAME} auth login'.")
        raise typer.Exit(code=1)

    client = TelegramClient(
        container.path_manager.user_session_path(),
        container.cfg.api_id,
        container.cfg.api_hash,
    )
    client.connect()
    me = client.get_me()
    client.disconnect()
    typer.echo(f"Logged in as @{me.username} (id: {me.id})")


@app.command()
def login(ctx: typer.Context):
    """Authenticate via Telegram QR code (no phone number required)."""
    container: "Container" = ctx.obj
    import qrcode
    from telethon.errors import SessionPasswordNeededError
    from telethon.sync import TelegramClient  # lazy: telethon adds ~120ms to startup

    if not container.cfg.api_id or not container.cfg.api_hash:
        typer.echo(f"api_id and api_hash are not set. Edit {container.config_path}.")
        raise typer.Exit(code=1)

    session_path = container.path_manager.user_session_path()
    old_umask = os.umask(0o177)
    try:
        client = TelegramClient(
            session_path, container.cfg.api_id, container.cfg.api_hash
        )
        client.connect()
    finally:
        os.umask(old_umask)

    if client.is_user_authorized():
        me = client.get_me()
        typer.echo(f"Already logged in as @{me.username} (id: {me.id}).")
        client.disconnect()
        return

    qr_login = client.qr_login()

    qr = qrcode.QRCode()
    qr.add_data(qr_login.url)
    qr.make(fit=True)
    typer.echo(
        "Scan this QR code with your Telegram app (Settings → Devices → Scan QR):\n"
    )
    qr.print_ascii(invert=True)
    typer.echo(f"\nOr open this URL in a browser / QR generator:\n{qr_login.url}\n")
    typer.echo("Waiting for scan... (Ctrl+C to cancel)")

    try:
        client.loop.run_until_complete(qr_login.wait(None))
    except SessionPasswordNeededError:
        password = typer.prompt("2FA password", hide_input=True)
        client.sign_in(password=password)

    me = client.get_me()
    client.disconnect()
    typer.echo(f"Authenticated as @{me.username} (id: {me.id})")
