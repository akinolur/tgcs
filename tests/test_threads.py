import json

from tgcs.threads import build_threads


def _raw(*messages):
    # build the JSONL string that build_threads expects
    return "\n".join(json.dumps(m) for m in messages)


def _msg(message_id, reply_to_message_id, seconds):
    # date is an ISO 8601 string (as produced by the downloader); only the
    # seconds vary so message order is obvious and deterministic
    return {
        "id": message_id,
        "reply_to_message_id": reply_to_message_id,
        "date": f"2020-01-01T00:00:{seconds:02d}+00:00",
        "text": f"m{message_id}",
    }


def test_build_threads_flat():
    # given: three messages, none replying to anything
    raw = _raw(
        _msg(1, None, 1),
        _msg(2, None, 2),
        _msg(3, None, 3),
    )

    # when
    threads = build_threads(raw)

    # then: each message is its own thread
    assert len(threads) == 3
    assert all(len(t.messages) == 1 for t in threads)


def test_build_threads_reply_chain():
    # given: A <- B <- C reply chain
    raw = _raw(
        _msg(1, None, 1),
        _msg(2, 1, 2),
        _msg(3, 2, 3),
    )

    # when
    threads = build_threads(raw)

    # then: one thread rooted at A, holding all three messages
    assert len(threads) == 1
    assert threads[0].thread_starter_id == 1
    assert [m["id"] for m in threads[0].messages] == [1, 2, 3]
