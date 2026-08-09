import json
import os
from datetime import timedelta

from tgcs.dates import today
from tgcs.paths import FilePathManager
from tgcs.telegram.downloader import TelegramChatHistoryDownloader


def _message(msg_id: int, day: str):
    return {
        "id": msg_id,
        "type": "message",
        "date": f"{day}T12:00:00+00:00",
        "from_username": "someone",
        "from_id": "user1",
        "text": "hi",
        "reply_to_message_id": None,
        "reactions": {},
    }


def _downloader(tmp_path):
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    return TelegramChatHistoryDownloader(client=None, path_manager=path_manager)


def _day_file(path_manager, group, day):
    return path_manager.date_history_path(group, day)


def test_last_day_is_written_when_the_chat_went_quiet(tmp_path):
    # given: the newest messages are two days old, nothing since
    utc_today = today()
    quiet_day = (utc_today - timedelta(days=2)).isoformat()
    downloader = _downloader(tmp_path)
    downloader.path_manager.create_folders_if_not_exists("group")

    # when
    downloader._create_daily_chat_history(
        [_message(1, quiet_day), _message(2, quiet_day)],
        "group",
        incomplete_from=utc_today,
    )

    # then
    written = _day_file(downloader.path_manager, "group", quiet_day)
    assert os.path.exists(written)
    with open(written) as f:
        assert [json.loads(line)["id"] for line in f] == [1, 2]


def test_today_is_skipped_because_it_can_still_receive_messages(tmp_path):
    # given
    utc_today = today()
    yesterday = (utc_today - timedelta(days=1)).isoformat()
    downloader = _downloader(tmp_path)
    downloader.path_manager.create_folders_if_not_exists("group")

    # when
    downloader._create_daily_chat_history(
        [_message(1, yesterday), _message(2, utc_today.isoformat())],
        "group",
        incomplete_from=utc_today,
    )

    # then
    assert os.path.exists(_day_file(downloader.path_manager, "group", yesterday))
    assert not os.path.exists(
        _day_file(downloader.path_manager, "group", utc_today.isoformat())
    )


def test_existing_day_file_is_not_overwritten(tmp_path):
    # given
    utc_today = today()
    day = (utc_today - timedelta(days=1)).isoformat()
    downloader = _downloader(tmp_path)
    downloader.path_manager.create_folders_if_not_exists("group", day)
    existing = _day_file(downloader.path_manager, "group", day)
    with open(existing, "w") as f:
        f.write("kept\n")

    # when
    downloader._create_daily_chat_history(
        [_message(1, day)], "group", incomplete_from=utc_today
    )

    # then
    with open(existing) as f:
        assert f.read() == "kept\n"


def test_splitting_a_chat_with_no_raw_history_is_a_noop(tmp_path):
    # given: a known chat that has never received a message
    downloader = _downloader(tmp_path)
    downloader.path_manager.create_folders_if_not_exists("group")

    # when / then: no exception
    downloader._create_daily_chat_history_from_raw_history("group")
