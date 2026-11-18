import logging
import os
from typing import Any

from openai import OpenAI, RateLimitError

from tgcs.paths import FilePathManager
from tgcs.prompt_loader import PromptLoader
from tgcs.workflows.base import ResumableStep

logger = logging.getLogger(__name__)


def _rate_limit_message(error: RateLimitError) -> str:
    retry_after = error.response.headers.get("retry-after")
    hint = f" (retry-after={retry_after}s)" if retry_after else ""
    return f"LLM rate limit, giving up{hint}: {error}"


class GenerateThreadsNameStep(ResumableStep):
    def __init__(self, path_manager: FilePathManager, model: str, client: OpenAI):
        self._path_manager = path_manager
        self._model = model
        self._client = client
        prompt_path = self._path_manager.prompt_path("summary.toml")
        self._prompt_loader = PromptLoader(prompt_path)

    def _get_additional_requirements(self, group_name: str) -> str:
        additional_requirements_path = self._path_manager.additional_requirements_path(
            group_name
        )
        with open(additional_requirements_path, "r") as f:
            return f.read()

    def _call_llm(self, system_prompt, user_prompt, schema):
        """Make LLM API call with retry logic for rate limits"""
        logger.info("Calling LLM API...")
        response_format = None
        if schema:
            response_format = {"type": "json_object"}
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_format,
        )
        return response

    def _process(self, data: Any, context: Any) -> Any:
        logger.debug("GenerateThreadsNameStep")
        if not data:
            return "No messages"  # TODO: handle this case better
        group_name = context["group_name"]
        additional_requirements = self._get_additional_requirements(group_name)

        # Use the new prompt loader
        system_prompt = self._prompt_loader.get_system_prompt()
        prompt_context = {
            "additional_requirements": additional_requirements,
            "messages": data,
        }
        user_prompt = self._prompt_loader.build_user_prompt(prompt_context)
        schema = self._prompt_loader.get_schema()
        try:
            response = self._call_llm(system_prompt, user_prompt, schema)
            result = response.choices[0].message.content
            logger.debug(result)
        except RateLimitError as e:
            logger.error(_rate_limit_message(e))
            result = ""
        except Exception as e:
            logger.error(f"Error during LLM call: {e}")
            result = ""
        return result

    def is_already_completed(self, data: Any, context: Any) -> bool:
        result_path = self._get_result_path(context)
        return os.path.exists(result_path)

    def load_result(self, data: Any, context: Any) -> Any:
        result_path = self._get_result_path(context)
        with open(result_path, "r") as f:
            return f.read()

    def save_result(self, data: Any, context: Any, result) -> None:
        if not result:
            return
        result_path = self._get_result_path(context)
        with open(result_path, "w") as f:
            f.write(result)

    def _get_result_path(self, context: Any):
        group_name = context["group_name"]
        date = context["date"]
        return self._path_manager.thread_names_raw_path(group_name, date)
