import json
import os
from enum import StrEnum
from typing import TYPE_CHECKING, Optional, assert_never

import typer

from tgcs.dates import cutoff
from tgcs.layouts import SINGLE_SLICE, Layout
from tgcs.threads import build_threads

if TYPE_CHECKING:
    from tgcs.container import Container
    from tgcs.paths import FilePathManager

app = typer.Typer(no_args_is_help=True)


class SortBy(StrEnum):
    date = "date"
    count = "count"


def _get_dates_for_group(path_manager: "FilePathManager", group_name: str) -> list[str]:
    history_path = path_manager.history_folder_path(group_name)
    if not os.path.isdir(history_path):
        return []
    return sorted(
        d
        for d in os.listdir(history_path)
        if os.path.isdir(os.path.join(history_path, d)) and not d.startswith(".")
    )


def _history_slices(
    path_manager: "FilePathManager", group_name: str
) -> list[tuple[str, str]]:
    """(key, history file) pairs of one chat, oldest first.

    The single layout has exactly one slice holding the whole chat; the daily
    layout has one per date folder. The key is what names files under threads/.
    """
    layout = path_manager.layout(group_name)
    if layout is Layout.SINGLE:
        raw_path = path_manager.raw_history_path(group_name)
        return [(SINGLE_SLICE, raw_path)] if os.path.exists(raw_path) else []
    elif layout is Layout.DAILY:
        return [
            (d, path_manager.date_history_path(group_name, d))
            for d in _get_dates_for_group(path_manager, group_name)
        ]
    else:
        assert_never(layout)


def _resolve_group_name(name: str) -> str:
    return name


def _load_link_prefix(path_manager: "FilePathManager", group_name: str) -> str:
    metadata_path = path_manager.group_metadata_path(group_name)
    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)
    return metadata.get("link_prefix", "")


def _load_history_raw(history_path: str) -> str:
    if not os.path.exists(history_path):
        return ""
    with open(history_path, encoding="utf-8") as f:
        return f.read()


def _build_threads(history_raw: str, link_prefix: str, min_msgs: int):
    threads = build_threads(history_raw)
    threads = [t for t in threads if len(t.messages) >= min_msgs]
    threads.sort(key=lambda t: len(t.messages), reverse=True)
    for t in threads:
        t.link_prefix = link_prefix
    return threads


@app.command(name="ls")
def list_threads(
    ctx: typer.Context,
    name: str = typer.Option(..., "--chat", "-g", help="group name or number"),
    date_str: Optional[str] = typer.Option(
        None, "--date", help="single date YYYY-MM-DD"
    ),
    from_date: Optional[str] = typer.Option(
        None, "--from", help="range start YYYY-MM-DD"
    ),
    to_date: Optional[str] = typer.Option(None, "--to", help="range end YYYY-MM-DD"),
    days: Optional[int] = typer.Option(
        None, "--days", min=1, help="last N calendar days, ending today"
    ),
    min_msgs: int = typer.Option(4, "--min-msgs", help="minimum messages per thread"),
    sort_by: SortBy = typer.Option(
        SortBy.date, "--sort", help="sort rows by date or count"
    ),
):
    """List threads for a chat, optionally filtered by date."""
    container: "Container" = ctx.obj
    _list_threads(
        path_manager=container.path_manager,
        name=name,
        date_str=date_str,
        from_date=from_date,
        to_date=to_date,
        days=days,
        min_msgs=min_msgs,
        sort_by=sort_by,
    )


def _list_threads(
    path_manager: "FilePathManager",
    name: str,
    date_str: Optional[str],
    from_date: Optional[str],
    to_date: Optional[str],
    days: Optional[int],
    min_msgs: int,
    sort_by: SortBy,
) -> None:
    selectors_used = sum(
        [
            date_str is not None,
            from_date is not None or to_date is not None,
            days is not None,
        ]
    )
    if selectors_used > 1:
        typer.echo("Error: --date, --from/--to, and --days are mutually exclusive.")
        raise typer.Exit(code=1)
    if (from_date is None) != (to_date is None):
        typer.echo("Error: --from and --to must be used together.")
        raise typer.Exit(code=1)

    group_name = _resolve_group_name(name)
    single_layout = path_manager.layout(group_name) is Layout.SINGLE
    if single_layout and selectors_used:
        typer.echo(
            f"Error: {group_name} uses the single layout, "
            "which has no dates. Drop --date/--from/--to/--days."
        )
        raise typer.Exit(code=1)

    slices = _history_slices(path_manager, group_name)
    if not slices:
        typer.echo("No history found.")
        raise typer.Exit(code=1)

    all_dates = [key for key, _ in slices]
    if date_str is not None:
        selected = [s for s in slices if s[0] == date_str]
    elif from_date is not None:
        selected = [s for s in slices if from_date <= s[0] <= to_date]
    elif days is not None:
        selected = [s for s in slices if s[0] >= cutoff(days)]
    elif single_layout:
        selected = slices
    else:
        selected = [s for s in slices if s[0] == all_dates[-1]]

    if not selected:
        typer.echo("No data for the specified date range.")
        raise typer.Exit(code=1)

    link_prefix = _load_link_prefix(path_manager, group_name)

    rows = []
    for d, history_path in selected:
        history_raw = _load_history_raw(history_path)
        if not history_raw.strip():
            continue
        threads = _build_threads(history_raw, link_prefix, min_msgs)
        for t in threads:
            rows.append((d, str(len(t.messages)), str(t.thread_starter_id), t.url))

    if not rows:
        typer.echo("No threads found.")
        return

    if sort_by == SortBy.count:
        rows.sort(key=lambda r: int(r[1]), reverse=True)

    col_date = max(len("DATE"), *(len(r[0]) for r in rows))
    col_msgs = max(len("MESSAGES"), *(len(r[1]) for r in rows))
    col_root = max(len("ROOT_ID"), *(len(r[2]) for r in rows))
    print(
        f"{'DATE':<{col_date}}  {'MESSAGES':>{col_msgs}}  {'ROOT_ID':>{col_root}}  URL"
    )
    for d, msgs, root_id, url in rows:
        print(f"{d:<{col_date}}  {msgs:>{col_msgs}}  {root_id:>{col_root}}  {url}")


@app.command(name="dump")
def dump_threads(
    ctx: typer.Context,
    name: str = typer.Option(..., "--chat", help="chat name"),
    min_msgs: int = typer.Option(4, "--min-msgs", help="minimum messages per thread"),
    force: bool = typer.Option(False, "--force", help="overwrite existing files"),
):
    """Write threads to individual files on disk."""
    container: "Container" = ctx.obj
    _dump_threads(
        path_manager=container.path_manager,
        name=name,
        min_msgs=min_msgs,
        force=force,
    )


def _dump_threads(
    path_manager: "FilePathManager", name: str, min_msgs: int, force: bool
) -> None:
    group_name = _resolve_group_name(name)
    slices = _history_slices(path_manager, group_name)
    if not slices:
        typer.echo("No history found.")
        raise typer.Exit(code=1)

    link_prefix = _load_link_prefix(path_manager, group_name)
    threads_dir = path_manager.threads_folder_path(group_name)
    os.makedirs(threads_dir, exist_ok=True)

    written = skipped = 0
    for d, history_path in slices:
        history_raw = _load_history_raw(history_path)
        if not history_raw.strip():
            continue
        threads = _build_threads(history_raw, link_prefix, min_msgs)
        for t in threads:
            out_path = path_manager.thread_file_path(group_name, d, t.thread_starter_id)
            if not force and os.path.exists(out_path):
                skipped += 1
                continue
            with open(out_path, "w", encoding="utf-8") as f:
                for msg in t.messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            written += 1

    typer.echo(f"Done: {written} written, {skipped} skipped.")


@app.command(name="show")
def show_thread(
    ctx: typer.Context,
    name: str = typer.Option(..., "--chat", "-g", help="group name or number"),
    root_id: int = typer.Argument(..., help="root/starter message ID"),
):
    """Print all messages in a thread across dates."""
    container: "Container" = ctx.obj
    _show_thread(
        path_manager=container.path_manager,
        name=name,
        root_id=root_id,
    )


def _show_thread(path_manager: "FilePathManager", name: str, root_id: int) -> None:
    group_name = _resolve_group_name(name)
    slices = _history_slices(path_manager, group_name)
    if not slices:
        typer.echo("No history found.")
        raise typer.Exit(code=1)

    root_date_idx = None
    for i, (_, history_path) in enumerate(slices):
        if not os.path.exists(history_path):
            continue
        with open(history_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                msg = json.loads(line)
                if msg["id"] == root_id:
                    root_date_idx = i
                    break
        if root_date_idx is not None:
            break

    if root_date_idx is None:
        typer.echo(f"Message {root_id} not found.")
        raise typer.Exit(code=1)

    history_raw = _load_history_raw(slices[root_date_idx][1])
    threads = build_threads(history_raw)
    root_thread = next((t for t in threads if t.thread_starter_id == root_id), None)
    if root_thread is None:
        typer.echo(f"Thread with root {root_id} not found.")
        raise typer.Exit(code=1)

    thread_message_ids = {m["id"] for m in root_thread.messages}
    all_messages = list(root_thread.messages)

    for _, history_path in slices[root_date_idx + 1 :]:
        if not os.path.exists(history_path):
            continue
        with open(history_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                msg = json.loads(line)
                if msg.get("reply_to_message_id") in thread_message_ids:
                    all_messages.append(msg)
                    thread_message_ids.add(msg["id"])

    all_messages.sort(key=lambda m: m["date"])
    for msg in all_messages:
        sender = msg.get("from_username") or str(msg.get("from_id", "unknown"))
        print(f"[{msg['id']}] {sender}: {msg.get('text', '')}")
