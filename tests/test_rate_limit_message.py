from types import SimpleNamespace

from tgcs.workflows.steps.generate_threads_name import _rate_limit_message


class FakeRateLimitError(Exception):
    def __init__(self, headers) -> None:
        super().__init__("Error code: 429")
        self.response = SimpleNamespace(headers=headers)


def test_message_shows_retry_after_when_the_server_sent_it():
    # given
    error = FakeRateLimitError({"retry-after": "3600"})

    # when
    message = _rate_limit_message(error)

    # then
    assert message == "LLM rate limit, giving up (retry-after=3600s): Error code: 429"


def test_message_omits_retry_after_when_absent():
    # given
    error = FakeRateLimitError({})

    # when
    message = _rate_limit_message(error)

    # then
    assert message == "LLM rate limit, giving up: Error code: 429"
