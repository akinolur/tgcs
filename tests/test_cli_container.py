from pathlib import Path

from typer.testing import CliRunner

import tgcs.cli
from tgcs.container import Container


class FakePathManager:
    def all_groups_list(self):
        return []


class FakeContainer:
    config_path: Path | None = None

    def __init__(self, config_path: Path) -> None:
        FakeContainer.config_path = config_path
        self.path_manager = FakePathManager()


def test_config_path_is_passed_to_container(monkeypatch, tmp_path):
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(tgcs.cli, "Container", FakeContainer)

    result = CliRunner().invoke(
        tgcs.cli.app, ["--config", str(config_path), "chats", "ls"]
    )

    assert result.exit_code == 0
    assert FakeContainer.config_path == config_path


def test_container_loads_the_given_config_path(tmp_path):
    data_dir = tmp_path / "data"
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{data_dir}"')

    container = Container(config_path)

    assert container.config_path == config_path
    assert container.cfg.data_dir == data_dir
