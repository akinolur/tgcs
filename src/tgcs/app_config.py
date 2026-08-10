import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_NAME = "tgcs"
DEFAULT_GROUP_FOLDER = PACKAGE_NAME


@dataclass
class AppConfig:
    data_dir: Path
    api_id: int | None = None
    api_hash: str | None = None
    group_folder: str = DEFAULT_GROUP_FOLDER
    bot_token: str | None = None
    tg_users: list[str] = field(default_factory=list)
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_url: str | None = None
    previous_days: int = 0
    summary_template_path: Path | None = None


def _xdg_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) / PACKAGE_NAME if xdg else Path.home() / ".config" / PACKAGE_NAME


def _xdg_data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    return (
        Path(xdg) / PACKAGE_NAME
        if xdg
        else Path.home() / ".local" / "share" / PACKAGE_NAME
    )


def default_config_path() -> Path:
    return _xdg_config_dir() / "config.toml"


def default_summary_template_path() -> Path:
    return _xdg_config_dir() / "summary.mustache"


def default_prompts_dir() -> Path:
    return _xdg_config_dir() / "prompts"


def write_default_prompts(prompts_dir: Path | None = None) -> Path:
    if prompts_dir is None:
        prompts_dir = default_prompts_dir()
    prompts_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    src = Path(__file__).parent / "prompts" / "summary.toml"
    dest = prompts_dir / "summary.toml"
    dest.write_bytes(src.read_bytes())
    return prompts_dir


DEFAULT_SUMMARY_TEMPLATE = (
    "#{{group_name}}\n"
    "Date: {{date}}\n"
    "\n"
    "{{#threads}}- {{name}} ([{{count}}]({{url}}))\n{{/threads}}"
)


_DEFAULT_CONFIG_TEMPLATE = """\
# {package} configuration

# Data storage directory (default: {data_dir})
# data_dir = "{data_dir}"

[telegram]
# api_id =
# api_hash = ""
# group_folder = "{group_folder}"

[telegram_bot]
# bot_token =
# tg_users = []

[llm]
# api_key = "gsk_..."
# model = ""
# url = "https://api.groq.com/openai/v1"

[settings]
# previous_days = 5
summary_template = "{summary_template}"
"""


def default_config_text() -> str:
    # rendered at write time so the paths match this machine's XDG settings
    return _DEFAULT_CONFIG_TEMPLATE.format(
        package=PACKAGE_NAME,
        data_dir=_xdg_data_dir(),
        group_folder=DEFAULT_GROUP_FOLDER,
        summary_template=default_summary_template_path(),
    )


def load_config(config_path: Path | None = None) -> AppConfig:
    if config_path is None:
        config_path = default_config_path()

    data_dir = _xdg_data_dir()
    kwargs: dict = {}

    if config_path.exists():
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)

        if "data_dir" in raw:
            data_dir = Path(raw["data_dir"]).expanduser()

        tg = raw.get("telegram", {})
        if "api_id" in tg:
            kwargs["api_id"] = int(tg["api_id"])
        kwargs["api_hash"] = tg.get("api_hash")
        kwargs["group_folder"] = tg.get("group_folder", DEFAULT_GROUP_FOLDER)
        tg_bot = raw.get("telegram_bot", {})
        kwargs["bot_token"] = tg_bot.get("bot_token")
        kwargs["tg_users"] = tg_bot.get("tg_users", [])

        llm = raw.get("llm", {})
        kwargs["llm_api_key"] = llm.get("api_key")
        kwargs["llm_model"] = llm.get("model")
        kwargs["llm_url"] = llm.get("url")

        settings = raw.get("settings", {})
        kwargs["previous_days"] = int(settings.get("previous_days", 0))
        if "summary_template" in settings:
            kwargs["summary_template_path"] = Path(
                settings["summary_template"]
            ).expanduser()

    if "summary_template_path" not in kwargs:
        kwargs["summary_template_path"] = default_summary_template_path()

    return AppConfig(data_dir=data_dir, **kwargs)


def write_default_summary_template(template_path: Path | None = None) -> Path:
    if template_path is None:
        template_path = default_summary_template_path()
    template_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    template_path.write_text(DEFAULT_SUMMARY_TEMPLATE, encoding="utf-8")
    return template_path


def write_default_config(config_path: Path | None = None) -> Path:
    if config_path is None:
        config_path = default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    old_umask = os.umask(0o177)
    try:
        config_path.write_text(default_config_text(), encoding="utf-8")
    finally:
        os.umask(old_umask)
    return config_path
