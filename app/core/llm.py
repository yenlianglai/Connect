import json
import logging
from typing import TypeVar

from google import genai
from google.genai.types import (
    AutomaticFunctionCallingConfig,
    FunctionCallingConfig,
    GenerateContentConfig,
    ToolConfig,
)
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

# Type variable for Pydantic models
T = TypeVar("T", bound=BaseModel)


__all__ = ["invoke_llm", "invoke_llm_structured"]


def _convert_messages_to_gemini_format(messages: list[dict]) -> tuple[list[dict], str | None]:
    """Convert OpenAI-style messages to Gemini format."""
    system_instruction = next((m["content"] for m in messages if m["role"] == "system"), None)
    contents = [
        {"role": "model" if m["role"] in ["assistant", "model"] else "user", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] != "system"
    ]
    return contents, system_instruction


async def invoke_llm(messages: list[dict], max_tokens: int = 600, temperature: float = 0.9) -> str:
    """
    Invoke LLM with messages (async)
    """
    if settings.LLM_PROVIDER == "gemini":
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)

        contents, system_instruction = _convert_messages_to_gemini_format(messages)

        config = GenerateContentConfig(
            automatic_function_calling=AutomaticFunctionCallingConfig(disable=True),
            tool_config=ToolConfig(function_calling_config=FunctionCallingConfig(mode="NONE")),
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        if system_instruction:
            config.system_instruction = system_instruction

        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=config,
        )

        return response.text if response is not None else ""

    elif settings.LLM_PROVIDER == "openai":
        if not settings.OPENAI_API_KEY:
            raise Exception("OpenAI 需要 OPENAI_API_KEY")

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL, messages=messages, max_tokens=max_tokens, temperature=temperature
        )
        result = response.choices[0].message.content
        return result if result else ""

    else:
        raise Exception("沒有可用的 LLM Provider，請檢查 API Key 設定")


async def invoke_llm_structured(
    messages: list[dict], response_schema: type[T], max_tokens: int = 3000, temperature: float = 0.9
) -> T:
    """
    Invoke LLM with structured output (async version)
    """
    logger.debug(f"Structured LLM call with schema: {response_schema.__name__}")

    if settings.LLM_PROVIDER == "gemini":
        if settings.GOOGLE_GENAI_USE_VERTEXAI:
            client = genai.Client(vertexai=settings.GOOGLE_GENAI_USE_VERTEXAI)
        elif hasattr(settings, "GOOGLE_API_KEY") and settings.GOOGLE_API_KEY:
            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        else:
            raise Exception("Gemini 需要 GOOGLE_GENAI_USE_VERTEXAI 或 GOOGLE_API_KEY")

        contents, system_instruction = _convert_messages_to_gemini_format(messages)
        # Log prompt details only at DEBUG level to keep the console clean
        logger.debug(f"Gemini System Instruction: {system_instruction}")
        logger.debug(f"Gemini Contents: {contents}")

        config = GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_schema,
            automatic_function_calling=AutomaticFunctionCallingConfig(disable=True),
            tool_config=ToolConfig(function_calling_config=FunctionCallingConfig(mode="NONE")),
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=config,
        )

        if not response.parsed:
            logger.warning("Empty parsed response from Gemini structured output")
            logger.debug(f"Raw Gemini text response: {response.text}")
            try:
                return response_schema()
            except Exception:
                raise Exception(f"Gemini failed to parse structured output. Raw text: {response.text}")

        result = response.parsed
        logger.debug(f"✅ Structured response received: {result.model_dump_json(ensure_ascii=False)}")
        return result

    elif settings.LLM_PROVIDER == "openai":
        if not settings.OPENAI_API_KEY:
            raise Exception("OpenAI 需要 OPENAI_API_KEY")

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

        result_text = response.choices[0].message.content
        if not result_text:
            return response_schema()

        result_dict = json.loads(result_text)
        result = response_schema(**result_dict)
        return result

    else:
        raise Exception("No available LLM Provider, please check API Key settings")
