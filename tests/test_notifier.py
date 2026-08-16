import json
import os

from tgcs.paths import FilePathManager
from tgcs.telegram.notifier import Notificator


class FakeTgClient:
    """Records sends; raises for the recipients listed in `failing`."""

    def __init__(self, failing=()):
        self.failing = set(failing)
        self.sent = []

    def send_message(self, user_id, text, link_preview=False):
        if str(user_id) in self.failing:
            raise RuntimeError("blocked")
        self.sent.append((user_id, text))


def _summary(path_manager, date_str, text="summary"):
    path_manager.create_folders_if_not_exists("group", date_str)
    with open(path_manager.summary_path("group", date_str), "w") as f:
        f.write(text)


def test_single_layout_chat_is_not_notified_about_stale_dates(tmp_path):
    # given: a chat switched to single keeps the summaries it made while daily
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    _summary(path_manager, "2025-01-01")
    with open(path_manager.group_metadata_path("group"), "w") as f:
        json.dump({"id": 1, "layout": "single"}, f)
    client = FakeTgClient()

    # when
    sent = Notificator(client, path_manager).notify("group", ["111"])

    # then
    assert sent == 0
    assert client.sent == []
    assert not os.path.exists(path_manager.notified_path("group", "2025-01-01"))


def test_every_configured_user_receives_the_summary(tmp_path):
    # given
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    _summary(path_manager, "2025-01-01")
    client = FakeTgClient()

    # when
    notificator = Notificator(client, path_manager)
    notificator.notify("group", ["111", "222"])

    # then
    assert [user_id for user_id, _ in client.sent] == [111, 222]
    assert os.path.exists(path_manager.notified_path("group", "2025-01-01"))


def test_a_failed_recipient_keeps_the_date_pending(tmp_path):
    # given
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    _summary(path_manager, "2025-01-01")
    client = FakeTgClient(failing={"222"})

    # when
    notificator = Notificator(client, path_manager)
    notificator.notify("group", ["111", "222"])

    # then
    assert not os.path.exists(path_manager.notified_path("group", "2025-01-01"))
