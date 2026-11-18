from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from tgcs.paths import FilePathManager


def require_known_chat(path_manager: "FilePathManager", name: str) -> None:
    is_segment = "/" not in name and "\\" not in name and name.strip(".") != ""
    if not is_segment or path_manager.read_metadata(name) is None:
        typer.echo(f"{name}: unknown chat. Run 'tgcs chats ls' to see chat names.")
        raise typer.Exit(code=1)
