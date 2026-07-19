import json
import tomllib
from pathlib import Path
from typing import Any


class PromptLoader:
    def __init__(self, toml_path: str):
        self.toml_path = Path(toml_path)
        self._config = self._load_toml()

    def _load_toml(self) -> dict[str, Any]:
        with open(self.toml_path, "rb") as f:
            return tomllib.load(f)

    def get_system_prompt(self) -> str:
        instruction = self._config["prompt"]["system"]["content"]
        schema_instruction = self._config["prompt"]["system"].get(
            "schema_instruction", ""
        )
        try:
            schema_content = self._config["prompt"]["schema"]["content"]
        except KeyError:
            schema_content = None

        schema_section = "\n\n---\n\n"
        if schema_instruction:
            schema_section += schema_instruction + "\n"
        if schema_content:
            schema_section += f"```\n{json.dumps(schema_content, indent=2)}\n```"

        return instruction.strip() + schema_section

    def get_user_prompt_template(self) -> str:
        return self._config["prompt"]["user"]["template"]

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        template = self.get_user_prompt_template()
        return template.format(**context)

    def get_schema(self) -> dict[str, Any] | None:
        try:
            schema_string = self._config["prompt"]["schema"]["content"]
            return json.loads(schema_string)
        except KeyError:
            return None
