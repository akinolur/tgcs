import os

from tgcs.models import Thread
from tgcs.paths import FilePathManager
from tgcs.workflows.steps.postprocess import PostProcessStep


def _thread(thread_id: int) -> Thread:
    thread = Thread(messages=[{"id": thread_id}], thread_starter_id=thread_id)
    thread.id = thread_id
    thread.link_prefix = "https://t.me/g/"
    return thread


def _context():
    return {
        "group_name": "group",
        "date": "2025-01-01",
        "threads": [_thread(1), _thread(2)],
    }


def _step_with_cached_answer(tmp_path):
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    path_manager.create_folders_if_not_exists("group", "2025-01-01")
    cached = path_manager.thread_names_raw_path("group", "2025-01-01")
    with open(cached, "w") as f:
        f.write("stale llm answer")
    return PostProcessStep(path_manager=path_manager), cached


def test_short_llm_answer_returns_none_instead_of_raising(tmp_path):
    # given: the llm named only one of the two threads
    step, cached = _step_with_cached_answer(tmp_path)

    # when
    result = step.process({"threads": [{"id": 1, "name": "one"}]}, _context())

    # then
    assert result is None
    assert not os.path.exists(cached), "stale answer must be dropped so a retry works"


def test_malformed_llm_answer_returns_none(tmp_path):
    # given
    step, cached = _step_with_cached_answer(tmp_path)

    # when
    result = step.process({"threads": [{"id": 1}, {"id": 2}]}, _context())

    # then
    assert result is None
    assert not os.path.exists(cached)


def test_non_dict_llm_answer_returns_none(tmp_path):
    # given
    step, cached = _step_with_cached_answer(tmp_path)

    # when
    result = step.process("not json at all", _context())

    # then
    assert result is None
    assert not os.path.exists(cached)


def test_complete_llm_answer_renders_the_summary(tmp_path):
    # given
    step, cached = _step_with_cached_answer(tmp_path)
    answer = {"threads": [{"id": 1, "name": "one"}, {"id": 2, "name": "two"}]}

    # when
    result = step.process(answer, _context())

    # then
    assert "one" in result and "two" in result
    assert os.path.exists(cached), "a usable answer must stay cached"
