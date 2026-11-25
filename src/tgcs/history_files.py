import json
import logging
import os
from collections import OrderedDict
from datetime import date, datetime
from typing import TYPE_CHECKING

from tgcs.dates import today
from tgcs.paths import write_text_atomic

if TYPE_CHECKING:
    from tgcs.paths import FilePathManager

logger = logging.getLogger(__name__)

_LAST_LINE_CHUNK = 4096


def read_last_line(path: str) -> bytes:
    """Return the last line of a JSONL file without reading the whole file.

    Seeks backward in chunks from EOF, stops at the newline that precedes the
    last record
    """
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        if end == 0:
            return b""

        # lines end with \n; skip the trailing newline of the last line
        # so rfind below locates the *preceding* newline (= start of last record).
        f.seek(end - 1)
        pos = end - 1 if f.read(1) == b"\n" else end

        while pos > 0:
            chunk = min(_LAST_LINE_CHUNK, pos)
            pos -= chunk
            f.seek(pos)
            data = f.read(chunk)
            idx = data.rfind(b"\n")
            if idx != -1:
                f.seek(pos + idx + 1)
                return f.readline()

        # no newline found - the whole file is a single line
        f.seek(0)
        return f.readline()


def truncate_partial_tail(path: str) -> bool:
    """Drop a trailing partial record left behind by an interrupted append.

    An append can only ever land as a prefix of what it meant to write, so the
    damage is confined to the bytes after the last newline. Without this repair
    one killed run would leave an unparseable last line and `read_last_line`
    would raise on every later download of the chat - fatal under the single
    layout, where this file is the only copy of the history.
    """
    with open(path, "rb+") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        if end == 0:
            return False
        f.seek(end - 1)
        if f.read(1) == b"\n":
            return False

        pos = end
        while pos > 0:
            chunk = min(_LAST_LINE_CHUNK, pos)
            pos -= chunk
            f.seek(pos)
            idx = f.read(chunk).rfind(b"\n")
            if idx != -1:
                f.truncate(pos + idx + 1)
                return True

        # no newline anywhere - the whole file is one partial record
        f.truncate(0)
        return True


def _dump_jsonl(messages) -> str:
    return "".join(json.dumps(msg, ensure_ascii=False) + "\n" for msg in messages)


def _append_jsonl(path: str, messages) -> None:
    """Append records in one write, then fsync so they are actually on disk."""
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(_dump_jsonl(messages))
        f.flush()
        os.fsync(f.fileno())


def _rewrite_jsonl(path: str, messages) -> None:
    write_text_atomic(path, _dump_jsonl(messages))


def update_raw_history(path_manager: "FilePathManager", messages, group_name):
    filename = path_manager.raw_history_path(group_name)
    if not messages:
        return 0
    if not os.path.exists(filename):
        _rewrite_jsonl(filename, messages)
        return len(messages)

    repair_raw_history_tail(path_manager, group_name)
    last_line = read_last_line(filename)
    if not last_line.strip():
        # empty, or emptied by the repair above
        _rewrite_jsonl(filename, messages)
        return len(messages)
    last_known_id = json.loads(last_line)["id"]

    new_messages = [m for m in messages if m["id"] > last_known_id]

    # fall back to full dedup/rewrite if there are overlapping IDs
    has_overlap = len(new_messages) < len(messages)
    if has_overlap:
        with open(filename, "r", encoding="utf-8") as f:
            existing = {json.loads(line)["id"]: json.loads(line) for line in f}
        original_count = len(existing)
        for msg in messages:
            existing[msg["id"]] = msg
        merged = sorted(existing.values(), key=lambda x: x["id"])
        _rewrite_jsonl(filename, merged)
        return len(merged) - original_count

    if new_messages:
        _append_jsonl(filename, new_messages)
    return len(new_messages)


def write_daily_history(
    path_manager: "FilePathManager",
    messages,
    group_name,
    incomplete_from: date | None = None,
):
    """Write one history file per day.

    `incomplete_from` (today) is the first day that can still receive
    messages; it and anything after it are skipped so a partial day is
    never written. Every earlier day is written even when it is the newest
    data we have - a chat that went quiet must not lose its last day.
    """
    # group messages by date
    messages_by_date = OrderedDict()
    for message in messages:
        date_str = message["date"].split("T")[0]
        if date_str not in messages_by_date:
            messages_by_date[date_str] = []
        messages_by_date[date_str].append(message)

    cutoff = incomplete_from.isoformat() if incomplete_from else None
    for date_str, day_messages in messages_by_date.items():
        if cutoff and date_str >= cutoff:
            continue
        filename = path_manager.date_history_path(group_name, date_str)
        # assumption: if the file exists, its history is complete
        if os.path.exists(filename):
            continue
        path_manager.create_folders_if_not_exists(group_name, date_str)
        # atomic: a day file is never rewritten once it exists, so a crash
        # mid-write would leave a truncated day forever
        _rewrite_jsonl(filename, day_messages)


def repair_raw_history_tail(path_manager: "FilePathManager", group_name) -> None:
    filename = path_manager.raw_history_path(group_name)
    if os.path.exists(filename) and truncate_partial_tail(filename):
        logger.warning(f"{group_name}: dropped a partial record from {filename}")


def raw_history_bounds(path_manager: "FilePathManager", group_name):
    """Return (first_id, first_date, last_id, last_date) of the raw history."""
    filename = path_manager.raw_history_path(group_name)
    if not os.path.exists(filename):
        return None, None, None, None
    with open(filename, "rb") as f:
        first_line = f.readline()
    if not first_line.strip():
        return None, None, None, None
    first = json.loads(first_line)
    last = json.loads(read_last_line(filename))
    return (
        first["id"],
        datetime.fromisoformat(first["date"]),
        last["id"],
        datetime.fromisoformat(last["date"]),
    )


def split_raw_history(
    path_manager: "FilePathManager",
    group_name,
    date_from: date | None = None,
    date_to: date | None = None,
):
    filename = path_manager.raw_history_path(group_name)
    if not os.path.exists(filename):
        # a chat with no messages yet has no raw history to split
        return
    messages = []
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            msg = json.loads(line)
            msg_date = datetime.fromisoformat(msg["date"]).date()
            if date_from and msg_date < date_from:
                continue
            if date_to and msg_date > date_to:
                break
            messages.append(msg)
    write_daily_history(path_manager, messages, group_name, incomplete_from=today())
