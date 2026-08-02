from types import SimpleNamespace

from tgcs.commands.summarize import summarize


def test_summarize_all_with_no_groups_does_not_create_clients():
    # given
    client_requests = []

    class EmptyPathManager:
        def groups_list(self):
            return []

    class FakeContainer:
        path_manager = EmptyPathManager()

        @property
        def llm_client(self):
            client_requests.append("llm")

        @property
        def tg_bot(self):
            client_requests.append("telegram bot")

    ctx = SimpleNamespace(invoked_subcommand=None, obj=FakeContainer())

    # when
    summarize(
        ctx,
        name=None,
        all=True,
        tg_notification=True,
        limit=None,
        days=None,
    )

    # then
    assert client_requests == []
