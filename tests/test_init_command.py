import stat

from typer.testing import CliRunner

from tgcs.app_config import (
    DEFAULT_GROUP_FOLDER,
    default_config_text,
    default_summary_template_path,
)
from tgcs.cli import app
from tgcs.layouts import Layout


def _isolated(tmp_path):
    """Keep XDG lookups inside tmp_path so init never touches the real ~/.config."""
    return {
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
    }


def test_init_creates_the_default_layout(tmp_path):
    # when
    result = CliRunner().invoke(app, ["init"], env=_isolated(tmp_path))

    # then
    assert result.exit_code == 0, result.output
    config_dir = tmp_path / "config" / "tgcs"
    assert (config_dir / "config.toml").exists()
    assert (config_dir / "summary.mustache").exists()
    assert (config_dir / "prompts" / "summary.toml").exists()
    assert stat.S_IMODE(config_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((config_dir / "config.toml").stat().st_mode) == 0o600


def test_init_rejects_a_custom_config_path(tmp_path):
    # given
    custom = tmp_path / "elsewhere" / "config.toml"

    # when
    result = CliRunner().invoke(
        app, ["--config", str(custom), "init"], env=_isolated(tmp_path)
    )

    # then
    assert result.exit_code == 1
    assert "always creates the default config" in result.output
    assert not custom.exists()


def test_init_does_not_overwrite_an_existing_config(tmp_path):
    # given
    config_path = tmp_path / "config" / "tgcs" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("# mine\n", encoding="utf-8")
    config_path.chmod(0o644)

    # when
    result = CliRunner().invoke(app, ["init"], env=_isolated(tmp_path))

    # then
    assert result.exit_code == 0, result.output
    assert config_path.read_text() == "# mine\n"
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o644
    assert "already exists" in result.output


def test_generated_config_points_at_the_real_template_path():
    # when
    text = default_config_text()

    # then
    assert f'summary_template = "{default_summary_template_path()}"' in text
    assert f'# group_folder = "{DEFAULT_GROUP_FOLDER}"' in text
    assert f'# layout = "{Layout.DAILY}"' in text
    assert "{" not in text, "no unrendered placeholders left"
