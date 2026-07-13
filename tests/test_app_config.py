from textwrap import dedent

import pytest

from tgcs.app_config import load_config


def test_load_config_partial_sections(tmp_path):
    # given: TOML with only [telegram] (no [llm], no [settings])
    path = tmp_path / "config.toml"
    path.write_text('[telegram]\napi_id = 12345\napi_hash = "abc"\n', encoding="utf-8")

    # when: missing sections don't blow up (raw.get("llm", {}))
    cfg = load_config(path)

    # then
    assert cfg.api_id == 12345
    assert cfg.llm_api_key is None
    assert cfg.llm_model is None
    assert cfg.llm_url is None
    assert cfg.previous_days == 0


def test_load_config_full_file(tmp_path):
    # given: TOML with every section filled in (api_id as a number)
    path = tmp_path / "config.toml"
    path.write_text(
        dedent(
            """\
            [telegram]
            api_id = 12345
            api_hash = "hash"
            group_folder = "My Folder"

            [telegram_bot]
            bot_token = "token"
            bot_username = "mybot"
            tg_users = ["1", "2"]

            [llm]
            api_key = "gsk_x"
            model = "some-model"
            url = "https://llm.example/v1"

            [settings]
            previous_days = 5
            """
        ),
        encoding="utf-8",
    )

    # when
    cfg = load_config(path)

    # then
    assert cfg.api_id == 12345 and isinstance(cfg.api_id, int)
    assert cfg.api_hash == "hash"
    assert cfg.group_folder == "My Folder"
    assert cfg.bot_token == "token"
    assert cfg.bot_username == "mybot"
    assert cfg.tg_users == ["1", "2"]
    assert cfg.llm_api_key == "gsk_x"
    assert cfg.llm_model == "some-model"
    assert cfg.llm_url == "https://llm.example/v1"
    assert cfg.previous_days == 5


@pytest.mark.parametrize("value, expected", [("5", 5), ('"5"', 5)])
def test_load_config_previous_days_coercion(tmp_path, value, expected):
    # given: previous_days as a number and as a numeric string
    path = tmp_path / "config.toml"
    path.write_text(f"[settings]\nprevious_days = {value}\n", encoding="utf-8")

    # when
    cfg = load_config(path)

    # then: always coerced to int
    assert cfg.previous_days == expected
    assert isinstance(cfg.previous_days, int)


def test_load_config_previous_days_invalid_raises(tmp_path):
    # given: a non-numeric previous_days
    path = tmp_path / "config.toml"
    path.write_text('[settings]\nprevious_days = "abc"\n', encoding="utf-8")

    # when / then: int("abc") raises
    with pytest.raises(ValueError):
        load_config(path)
