import json

from tgcs.commands.chats import _last_dt


def _write(tmp_path, records):
    path = tmp_path / "history.jsonl"
    with open(path, "wb") as f:
        for record in records:
            f.write(json.dumps(record).encode() + b"\n")
    return str(path)


def test_last_dt_of_empty_history_is_none(tmp_path):
    # given
    path = _write(tmp_path, [])

    # then
    assert _last_dt([path]) is None


def test_last_dt_reads_last_record(tmp_path):
    # given
    path = _write(
        tmp_path,
        [
            {"date": "2026-08-24T10:00:00+00:00"},
            {"date": "2026-08-25T12:30:00+00:00"},
        ],
    )

    # then
    assert _last_dt([path]) == "2026-08-25 12:30"


def test_last_dt_of_record_longer_than_tail_scan_window(tmp_path):
    # given: last record's text alone exceeds the initial 4096-byte scan window
    long_text = "x" * 5000
    path = _write(
        tmp_path,
        [
            {"date": "2026-08-24T10:00:00+00:00", "text": "short"},
            {"date": "2026-08-25T12:30:00+00:00", "text": long_text},
        ],
    )

    # then
    assert _last_dt([path]) == "2026-08-25 12:30"


def test_last_dt_of_single_record_longer_than_file(tmp_path):
    # given: the whole file is one record bigger than the initial scan window
    long_text = "x" * 5000
    path = _write(tmp_path, [{"date": "2026-08-25T12:30:00+00:00", "text": long_text}])

    # then
    assert _last_dt([path]) == "2026-08-25 12:30"
