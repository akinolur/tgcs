import os
from concurrent.futures import ThreadPoolExecutor

from tgcs.paths import FilePathManager
from tgcs.summary_creator import SummaryCreator

DATE = "2025-01-01"


def _creator(tmp_path):
    path_manager = FilePathManager(base_path=str(tmp_path / "data"))
    path_manager.create_folders_if_not_exists("group", DATE)
    return SummaryCreator(path_manager, workflow=None)


def _leftover_lock_file(path_manager):
    """A lock file from a crashed run: present, but nothing holds a flock on it."""
    with open(path_manager.lock_path("group", DATE), "w") as f:
        f.write("4242")


def _race_for_the_lock(creator, attempts=32):
    with ThreadPoolExecutor(max_workers=attempts) as pool:
        return list(
            pool.map(creator._acquire_lock, ["group"] * attempts, [DATE] * attempts)
        )


def test_the_lock_is_exclusive(tmp_path):
    # given
    creator = _creator(tmp_path)
    other = SummaryCreator(creator.path_manager, workflow=None)

    # when
    first = creator._acquire_lock("group", DATE)
    second = other._acquire_lock("group", DATE)

    # then
    assert first is True
    assert second is False


def test_the_lock_can_be_taken_again_after_release(tmp_path):
    # given
    creator = _creator(tmp_path)
    creator._acquire_lock("group", DATE)
    other = SummaryCreator(creator.path_manager, workflow=None)

    # when
    creator._release_lock("group", DATE)

    # then
    assert other._acquire_lock("group", DATE) is True


def test_a_lock_file_left_by_a_crashed_run_is_reclaimed(tmp_path):
    # given
    creator = _creator(tmp_path)
    _leftover_lock_file(creator.path_manager)

    # when / then
    assert creator._acquire_lock("group", DATE) is True


def test_only_one_of_many_concurrent_runs_wins(tmp_path):
    # given
    creator = _creator(tmp_path)

    # when
    acquired = _race_for_the_lock(creator)

    # then
    assert sum(acquired) == 1


def test_only_one_run_wins_when_a_crashed_run_left_a_lock_file(tmp_path):
    # given
    creator = _creator(tmp_path)
    _leftover_lock_file(creator.path_manager)

    # when
    acquired = _race_for_the_lock(creator)

    # then
    assert sum(acquired) == 1


def test_releasing_a_lock_that_was_never_taken_is_a_noop(tmp_path):
    # given
    creator = _creator(tmp_path)

    # when / then
    creator._release_lock("group", DATE)
    assert not os.path.exists(creator.path_manager.lock_path("group", DATE))
