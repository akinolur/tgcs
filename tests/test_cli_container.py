from typer.testing import CliRunner

import tgcs.cli
from tgcs.cli import create_app


class FakeContainer:
    def __init__(self, path_manager) -> None:
        self.path_manager = path_manager
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def test_config_path_is_passed_to_container(tmp_path):
    # given
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{tmp_path / "data"}"')

    # when
    result = CliRunner().invoke(
        tgcs.cli.app, ["--config", str(config_path), "chats", "ls"]
    )

    # then: the container was built from that file, so its data dir now exists
    assert result.exit_code == 0
    assert (tmp_path / "data").is_dir()


def test_container_is_closed_after_a_command():
    # given
    class EmptyPathManager:
        def all_groups_list(self):
            return []

    container = FakeContainer(EmptyPathManager())

    # when
    result = CliRunner().invoke(create_app(lambda _: container), ["chats", "ls"])

    # then
    assert result.exit_code == 0
    assert container.close_calls == 1


def test_container_is_closed_after_cli_error():
    # given
    class FailingPathManager:
        def all_groups_list(self):
            raise RuntimeError("command failed")

    container = FakeContainer(FailingPathManager())

    # when
    result = CliRunner().invoke(create_app(lambda _: container), ["chats", "ls"])

    # then
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert container.close_calls == 1
