import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import typer
from telethon.tl import types

from tgcs.commands.chats import _get_chats
from tgcs.commands.threads import SortBy, _dump_threads, _list_threads
from tgcs.dates import today
from tgcs.layouts import Layout
from tgcs.paths import FilePathManager
from tgcs.telegram.downloader import TelegramChatHistoryDownloader


class FakeMessage:
    """The subset of a telethon message that `_prepare_message` reads."""

    def __init__(self, msg_id, text, reply_to=None, at=None):
        self.id = msg_id
        self.message = text
        self.reply_to_msg_id = reply_to
        self.date = at or datetime.now(timezone.utc)
        self.from_id = types.PeerUser(user_id=7)
        self.sender_id = 7
        self.sender = SimpleNamespace(username="someone")
        self.reactions = None


class FakeClient:
    """Serves one fixed batch of messages, honouring `min_id`."""

    def __init__(self, messages, entity):
        self.messages = messages
        self._entity = entity

    def get_entity(self, peer):
        return self._entity

    def iter_messages(self, entity, limit, offset_date, reverse, **kwargs):
        min_id = kwargs.get("min_id") or 0
        offset_id = kwargs.get("offset_id") or 0
        return [m for m in self.messages if m.id > min_id and m.id > offset_id]


def _entity():
    return SimpleNamespace(
        id=42, access_hash=1, title="Quiet chat", username="quiet_chat"
    )


def _downloader(tmp_path, messages):
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    client = FakeClient(messages, _entity())
    return TelegramChatHistoryDownloader(client, path_manager, download_limit=1000)


def _make_single_layout(path_manager, group="quiet_chat"):
    path_manager.create_folders_if_not_exists(group)
    with open(path_manager.group_metadata_path(group), "w") as f:
        json.dump(
            {"id": 42, "link_prefix": "https://t.me/quiet_chat/", "layout": "single"}, f
        )


def _raw_ids(path_manager, group="quiet_chat"):
    with open(path_manager.raw_history_path(group)) as f:
        return [json.loads(line)["id"] for line in f if line.strip()]


def test_download_writes_only_the_raw_file_and_no_date_folders(tmp_path):
    # given: a single-layout chat whose newest messages are from today
    downloader = _downloader(tmp_path, [FakeMessage(1, "hi"), FakeMessage(2, "there")])
    path_manager = downloader.path_manager
    _make_single_layout(path_manager)

    # when
    group_name, count = downloader.download_chat_history("quiet_chat")

    # then: today's messages are kept, and nothing was split by date
    assert (group_name, count) == ("quiet_chat", 2)
    assert _raw_ids(path_manager) == [1, 2]
    history_dir = path_manager.history_folder_path("quiet_chat")
    assert os.listdir(history_dir) == ["raw_chat_history.jsonl"]
    assert not os.path.exists(
        path_manager.date_history_folder_path("quiet_chat", today().isoformat())
    )


def test_daily_layout_still_splits_by_date(tmp_path):
    # given: the same chat left on the default layout
    yesterday = datetime.now(timezone.utc).replace(hour=12) - timedelta(days=1)
    downloader = _downloader(tmp_path, [FakeMessage(1, "hi", at=yesterday)])
    path_manager = downloader.path_manager
    path_manager.create_folders_if_not_exists("quiet_chat")

    # when
    downloader.download_chat_history("quiet_chat")

    # then
    day = yesterday.date().isoformat()
    assert os.path.exists(path_manager.date_history_path("quiet_chat", day))


def test_second_download_appends_only_new_messages(tmp_path):
    # given: a chat already downloaded once
    downloader = _downloader(tmp_path, [FakeMessage(1, "hi"), FakeMessage(2, "there")])
    path_manager = downloader.path_manager
    _make_single_layout(path_manager)
    downloader.download_chat_history("quiet_chat")

    # when: one more message arrives
    downloader._client.messages.append(FakeMessage(3, "later"))
    _, count = downloader.download_chat_history("quiet_chat")

    # then
    assert count == 1
    assert _raw_ids(path_manager) == [1, 2, 3]


def test_overlapping_batch_merges_without_duplicates_or_leftovers(tmp_path):
    # given: a raw file whose ids the next batch repeats
    downloader = _downloader(tmp_path, [])
    path_manager = downloader.path_manager
    _make_single_layout(path_manager)
    raw_path = path_manager.raw_history_path("quiet_chat")
    downloader._update_raw_chat_history(
        [downloader._prepare_message(FakeMessage(i, f"m{i}")) for i in (1, 2, 3)],
        "quiet_chat",
    )

    # when: ids 2 and 3 come back alongside a new id 4
    added = downloader._update_raw_chat_history(
        [downloader._prepare_message(FakeMessage(i, f"m{i}")) for i in (2, 3, 4)],
        "quiet_chat",
    )

    # then: merged in place, no tmp file survives the atomic rewrite
    assert added == 1
    assert _raw_ids(path_manager) == [1, 2, 3, 4]
    history_dir = os.path.dirname(raw_path)
    assert [f for f in os.listdir(history_dir) if ".tmp" in f] == []


def test_partial_last_record_is_repaired_instead_of_blocking_downloads(tmp_path):
    # given: an append was killed halfway, leaving an unterminated record
    downloader = _downloader(tmp_path, [])
    path_manager = downloader.path_manager
    _make_single_layout(path_manager)
    downloader._update_raw_chat_history(
        [downloader._prepare_message(FakeMessage(i, f"m{i}")) for i in (1, 2)],
        "quiet_chat",
    )
    raw_path = path_manager.raw_history_path("quiet_chat")
    with open(raw_path, "a") as f:
        f.write('{"id":3,"te')

    # when: without the repair this would raise JSONDecodeError forever
    added = downloader._update_raw_chat_history(
        [downloader._prepare_message(FakeMessage(3, "m3"))], "quiet_chat"
    )

    # then
    assert added == 1
    assert _raw_ids(path_manager) == [1, 2, 3]


def test_a_wholly_partial_raw_file_is_repaired(tmp_path):
    # given: the very first append was killed before any newline landed
    downloader = _downloader(tmp_path, [])
    path_manager = downloader.path_manager
    _make_single_layout(path_manager)
    raw_path = path_manager.raw_history_path("quiet_chat")
    with open(raw_path, "w") as f:
        f.write('{"id":1,"te')

    # when
    added = downloader._update_raw_chat_history(
        [downloader._prepare_message(FakeMessage(1, "m1"))], "quiet_chat"
    )

    # then
    assert added == 1
    assert _raw_ids(path_manager) == [1]


def test_stale_date_folders_are_not_summarized_after_switching_to_single(tmp_path):
    # given: a chat downloaded as daily, then switched to single
    from tgcs.summary_creator import SummaryCreator

    downloader = _downloader(tmp_path, [])
    path_manager = downloader.path_manager
    path_manager.create_folders_if_not_exists("quiet_chat", "2025-03-01")
    with open(path_manager.date_history_path("quiet_chat", "2025-03-01"), "w") as f:
        f.write("{}\n")
    _make_single_layout(path_manager)

    # when / then: the leftover date folder must not be summarized
    creator = SummaryCreator(path_manager, workflow=None)
    assert creator.get_unprocessed_dates("quiet_chat") == []


def test_chats_ls_counts_messages_from_the_raw_file(tmp_path, capsys):
    # given
    at = datetime(2025, 3, 4, 9, 30, tzinfo=timezone.utc)
    downloader = _downloader(
        tmp_path, [FakeMessage(1, "hi", at=at), FakeMessage(2, "there", at=at)]
    )
    path_manager = downloader.path_manager
    _make_single_layout(path_manager)
    downloader.download_chat_history("quiet_chat")

    # when
    _get_chats(path_manager)

    # then: the layout is visible and the count is not zero
    out = capsys.readouterr().out
    assert "LAYOUT" in out
    assert "single" in out
    assert "2025-03-04 09:30" in out
    assert out.strip().splitlines()[-1].split()[-1] == "2"


def test_threads_ls_builds_threads_from_the_whole_file(tmp_path, capsys):
    # given: one thread of four messages spread over two days
    old = datetime(2025, 3, 1, 9, 0, tzinfo=timezone.utc)
    new = datetime(2025, 3, 8, 9, 0, tzinfo=timezone.utc)
    messages = [
        FakeMessage(1, "root", at=old),
        FakeMessage(2, "a", reply_to=1, at=old),
        FakeMessage(3, "b", reply_to=1, at=new),
        FakeMessage(4, "c", reply_to=1, at=new),
    ]
    downloader = _downloader(tmp_path, messages)
    path_manager = downloader.path_manager
    _make_single_layout(path_manager)
    downloader.download_chat_history("quiet_chat")

    # when
    _list_threads(
        path_manager=path_manager,
        name="quiet_chat",
        date_str=None,
        from_date=None,
        to_date=None,
        days=None,
        min_msgs=4,
        sort_by=SortBy.date,
    )

    # then: a per-day layout would have split this thread below the threshold
    out = capsys.readouterr().out
    row = out.strip().splitlines()[-1].split()
    assert row[:3] == ["all", "4", "1"]


def test_threads_ls_rejects_date_selectors(tmp_path):
    # given
    downloader = _downloader(tmp_path, [FakeMessage(1, "hi")])
    path_manager = downloader.path_manager
    _make_single_layout(path_manager)
    downloader.download_chat_history("quiet_chat")

    # when / then
    with pytest.raises(typer.Exit) as ex:
        _list_threads(
            path_manager=path_manager,
            name="quiet_chat",
            date_str=None,
            from_date=None,
            to_date=None,
            days=7,
            min_msgs=4,
            sort_by=SortBy.date,
        )
    assert ex.value.exit_code == 1


def test_threads_dump_names_files_after_the_single_slice(tmp_path):
    # given
    at = datetime(2025, 3, 1, 9, 0, tzinfo=timezone.utc)
    messages = [FakeMessage(1, "root", at=at)] + [
        FakeMessage(i, "x", reply_to=1, at=at) for i in (2, 3, 4)
    ]
    downloader = _downloader(tmp_path, messages)
    path_manager = downloader.path_manager
    _make_single_layout(path_manager)
    downloader.download_chat_history("quiet_chat")

    # when
    _dump_threads(path_manager, name="quiet_chat", min_msgs=4, force=False)

    # then
    assert os.listdir(path_manager.threads_folder_path("quiet_chat")) == ["all-1.jsonl"]


def test_switching_back_to_daily_backfills_every_date_folder(tmp_path):
    # given: a single-layout chat with history older than any download window
    from tgcs.commands.chats import chat_layout

    old = datetime(2025, 3, 1, 9, 0, tzinfo=timezone.utc)
    downloader = _downloader(
        tmp_path, [FakeMessage(1, "hi", at=old), FakeMessage(2, "there", at=old)]
    )
    path_manager = downloader.path_manager
    _make_single_layout(path_manager)
    downloader.download_chat_history("quiet_chat")
    assert not os.path.exists(
        path_manager.date_history_folder_path("quiet_chat", "2025-03-01")
    )

    # when
    ctx = SimpleNamespace(obj=SimpleNamespace(path_manager=path_manager))
    chat_layout(ctx, name="quiet_chat", value=Layout.DAILY)

    # then: the whole raw file is split, not just the recent window
    with open(path_manager.date_history_path("quiet_chat", "2025-03-01")) as f:
        assert [json.loads(line)["id"] for line in f] == [1, 2]


def test_summarization_skips_a_single_layout_chat(tmp_path):
    # given: a downloaded single-layout chat has no date folders to summarize
    from tgcs.summary_creator import SummaryCreator

    downloader = _downloader(tmp_path, [FakeMessage(1, "hi")])
    path_manager = downloader.path_manager
    _make_single_layout(path_manager)
    downloader.download_chat_history("quiet_chat")

    # when: workflow is None, so touching it would raise
    creator = SummaryCreator(path_manager, workflow=None)
    creator.process_unprocessed_dates("quiet_chat")

    # then
    assert creator.get_unprocessed_dates("quiet_chat") == []
    assert path_manager.layout("quiet_chat") is Layout.SINGLE


def test_count_lines_matches_wc_and_handles_a_torn_tail(tmp_path):
    # given: a well-formed file, one with no trailing newline, and an empty one
    from tgcs.commands.chats import _count_lines

    clean = tmp_path / "clean.jsonl"
    clean.write_bytes(b'{"id":1}\n{"id":2}\n{"id":3}\n')
    torn = tmp_path / "torn.jsonl"
    torn.write_bytes(b'{"id":1}\n{"id":2}\n{"id":3')
    empty = tmp_path / "empty.jsonl"
    empty.write_bytes(b"")

    # when / then: newline count for complete records, plus the unterminated one
    assert _count_lines(str(clean)) == 3
    assert _count_lines(str(torn)) == 3
    assert _count_lines(str(empty)) == 0


def test_count_lines_spans_chunk_boundaries(tmp_path):
    # given: a file several read-chunks long, so counting cannot rely on one read
    from tgcs.commands.chats import _COUNT_CHUNK, _count_lines

    record = b'{"id":1,"text":"' + b"x" * 200 + b'"}\n'
    count = (_COUNT_CHUNK * 3) // len(record)
    big = tmp_path / "big.jsonl"
    big.write_bytes(record * count)

    # when / then
    assert big.stat().st_size > _COUNT_CHUNK * 2
    assert _count_lines(str(big)) == count
