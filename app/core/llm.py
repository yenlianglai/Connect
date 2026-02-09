# Standard library imports
import json
import logging
from collections.abc import AsyncIterator
from typing import TypeVar

# Third-party imports
import httpx
from google import genai
from google.genai.types import (
    AutomaticFunctionCallingConfig,
    FunctionCallingConfig,
    GenerateContentConfig,
    ToolConfig,
)
from openai import AsyncOpenAI
from pydantic import BaseModel

# Local imports
from app.core.config import settings

logger = logging.getLogger(__name__)

# Type variable for Pydantic models
T = TypeVar("T", bound=BaseModel)


__all__ = ["invoke_llm", "invoke_llm_structured", "invoke_llm_stream"]


def _convert_messages_to_gemini_format(messages: list[dict]) -> tuple[list[dict], str | None]:
    """Convert OpenAI-style messages to Gemini format."""
    system_instruction = next((m["content"] for m in messages if m["role"] == "system"), None)
    contents = [
        {"role": "model" if m["role"] in ["assistant", "model"] else "user", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] != "system"
    ]
    return contents, system_instruction


def _convert_messages_to_ollama_format(messages: list[dict]) -> list[dict]:
    """Convert OpenAI-style messages to Ollama format."""
    ollama_messages = []
    for m in messages:
        role = m["role"]
        # Ollama uses "assistant" instead of "model"
        if role == "model":
            role = "assistant"
        ollama_messages.append({"role": role, "content": m["content"]})
    return ollama_messages


def _get_pydantic_json_schema(model: type[BaseModel]) -> dict:
    """Get JSON schema from Pydantic model."""
    return model.model_json_schema()


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

        result = response.text if response is not None else ""
        logger.debug(
            "LLM result (gemini) len=%d: %s", len(result), result[:500] + "..." if len(result) > 500 else result
        )
        return result

    elif settings.LLM_PROVIDER == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError("OpenAI requires OPENAI_API_KEY to be set")

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL, messages=messages, max_tokens=max_tokens, temperature=temperature
        )
        result = response.choices[0].message.content or ""
        logger.debug(
            "LLM result (openai) len=%d: %s", len(result), result[:500] + "..." if len(result) > 500 else result
        )
        return result

    elif settings.LLM_PROVIDER == "ollama":
        ollama_messages = _convert_messages_to_ollama_format(messages)

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
            )
            response.raise_for_status()
            result = response.json()
            text = result.get("message", {}).get("content", "")
            logger.debug("LLM result (ollama) len=%d: %s", len(text), text[:500] + "..." if len(text) > 500 else text)
            return text

    else:
        raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}. Please check API key settings.")


async def invoke_llm_stream(
    messages: list[dict], max_tokens: int = 600, temperature: float = 0.9
) -> AsyncIterator[str]:
    """
    Invoke LLM with streaming response (async generator)
    Yields text chunks as they are generated.
    """
    logger.debug("LLM stream started (provider=%s)", settings.LLM_PROVIDER)
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

        stream = await client.aio.models.generate_content_stream(
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=config,
        )
        async for chunk in stream:
            if chunk.text:
                yield chunk.text

    elif settings.LLM_PROVIDER == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError("OpenAI requires OPENAI_API_KEY to be set")

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        stream = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    elif settings.LLM_PROVIDER == "ollama":
        ollama_messages = _convert_messages_to_ollama_format(messages)

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "messages": ollama_messages,
                    "stream": True,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        try:
                            chunk_data = json.loads(line)
                            if "message" in chunk_data and "content" in chunk_data["message"]:
                                content = chunk_data["message"]["content"]
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue

    else:
        raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}. Please check API key settings.")


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
            raise ValueError("Gemini requires either GOOGLE_GENAI_USE_VERTEXAI or GOOGLE_API_KEY to be set")

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
            logger.warning("Empty parsed response from Gemini structured output (often due to truncated JSON)")
            logger.debug(f"Raw Gemini text response: {response.text[:1500]}...")
            # Fallback: try parsing raw text in case response was valid but parser failed (e.g. truncation)
            if response.text and response.text.strip():
                try:
                    result_dict = json.loads(response.text)
                    result = response_schema(**result_dict)
                    logger.info("Recovered structured output from raw text (partial or full)")
                    return result
                except (json.JSONDecodeError, Exception) as e:
                    logger.debug("Could not recover from raw text: %s", e)
            try:
                return response_schema()
            except Exception as e:
                raise ValueError(f"Gemini failed to parse structured output. Raw text: {response.text[:500]}") from e

        result = response.parsed
        logger.debug(f"✅ Structured response received: {result.model_dump_json(ensure_ascii=False)}")
        return result

    elif settings.LLM_PROVIDER == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError("OpenAI requires OPENAI_API_KEY to be set")

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
        logger.debug("LLM structured result (openai): %s", result.model_dump_json(ensure_ascii=False)[:1000])
        return result

    elif settings.LLM_PROVIDER == "ollama":
        ollama_messages = _convert_messages_to_ollama_format(messages)

        # Get JSON schema from Pydantic model
        json_schema = _get_pydantic_json_schema(response_schema)

        # Add schema to the prompt for better grounding (as recommended in Ollama docs)
        # Enhance the last user message with schema information
        enhanced_messages = ollama_messages.copy()
        if enhanced_messages and enhanced_messages[-1]["role"] == "user":
            schema_str = json.dumps(json_schema, indent=2)
            enhanced_messages[-1]["content"] += (
                f"\n\nPlease respond with valid JSON matching this schema:\n{schema_str}"
            )

        # Extraction can be slow: large prompt + structured JSON; use 5 min read timeout
        timeout = httpx.Timeout(300.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "messages": enhanced_messages,
                    "stream": False,
                    "format": json_schema,  # Pass schema to format parameter
                    "options": {
                        "temperature": temperature,  # Lower temperature for more deterministic outputs
                        "num_predict": max_tokens,
                    },
                },
            )
            response.raise_for_status()
            result_data = response.json()
            result_text = result_data.get("message", {}).get("content", "")
            logger.debug(
                "LLM structured raw (ollama) len=%d: %s",
                len(result_text),
                result_text[:1000] + "..." if len(result_text) > 1000 else result_text,
            )

            if not result_text:
                logger.warning("Empty response from Ollama structured output")
                try:
                    return response_schema()
                except Exception as e:
                    raise ValueError("Ollama returned empty response and schema has no defaults") from e

            # Parse and validate the JSON response
            try:
                result_dict = json.loads(result_text)
                result = response_schema(**result_dict)
                # Log when extraction returns empty nodes so we can diagnose
                if hasattr(result, "knowledge_nodes") and len(getattr(result, "knowledge_nodes", [])) == 0:
                    logger.warning(
                        "Ollama structured output returned 0 knowledge_nodes. Raw response (first 500 chars): %s",
                        result_text[:500] if result_text else "(empty)",
                    )
                logger.debug(f"✅ Structured response received: {result.model_dump_json(ensure_ascii=False)}")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from Ollama: {result_text[:500]}")
                raise ValueError(f"Ollama returned invalid JSON: {e}") from e
            except Exception as e:
                logger.error(f"Failed to validate response against schema: {e}")
                logger.debug(f"Response text: {result_text[:500]}")
                raise ValueError(f"Response validation failed: {e}") from e

    else:
        raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}. Please check API key settings.")
