"""
Anthropic Claude client for cloud-based inference (model selected with ANTHROPIC_MODEL).
Communicates directly with the Anthropic Messages API (https://api.anthropic.com/v1/messages)
using httpx, supporting both non-streaming and streaming tokens (SSE), with rate-limit
handling, timeouts, and error isolation without exposing secrets.
"""

import asyncio
from dataclasses import dataclass, field
import json
import logging
import os
from typing import Dict, Any, Optional, Callable

import httpx

from backend.config import DEFAULT_ANTHROPIC_MODEL, get_settings

logger = logging.getLogger("agent.cloud_client")

# Kept for backwards compatibility; the live default comes from ANTHROPIC_MODEL (see backend/config.py).
DEFAULT_CLAUDE_MODEL = DEFAULT_ANTHROPIC_MODEL
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


class CloudProviderError(Exception):
    """Exception raised for Anthropic API communication or validation errors."""
    pass


@dataclass
class AnthropicClaudeConfig:
    """Configuration for Anthropic Claude client."""
    api_key: Optional[str] = None
    model: str = field(default_factory=lambda: get_settings().anthropic_model)
    max_tokens: int = 4096
    temperature: float = 0.2
    timeout_seconds: float = field(default_factory=lambda: get_settings().cloud_timeout_seconds)
    base_url: str = ANTHROPIC_API_URL


class AnthropicClaudeClient:
    """
    Client for interacting with Anthropic Claude (configurable model).
    Matches the PiAgentClient interface:
    `run_prompt(prompt, timeout=None, on_delta=None) -> str`
    """

    def __init__(self, config: Optional[AnthropicClaudeConfig] = None):
        self.config = config or AnthropicClaudeConfig()
        # Resolve API key from config or environment
        self.api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY", "").strip()

    def is_configured(self) -> bool:
        """Returns True if a valid Anthropic API key is available."""
        return bool(
            self.api_key
            and not self.api_key.startswith("your_")
            and len(self.api_key) > 10
        )

    def _build_headers(self) -> Dict[str, str]:
        """Constructs headers for Anthropic API request."""
        if not self.is_configured():
            raise CloudProviderError(
                "ANTHROPIC_API_KEY is not configured in the environment or config. "
                "Please configure ANTHROPIC_API_KEY to use Cloud Claude."
            )
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }

    async def run_prompt(
        self,
        prompt: str,
        timeout: Optional[float] = None,
        on_delta: Optional[Callable[[str], Any]] = None,
    ) -> str:
        """
        Executes a prompt against Anthropic Messages API.
        If on_delta is provided, streams tokens via SSE.
        Returns the complete response text.
        """
        headers = self._build_headers()
        timeout_sec = timeout or self.config.timeout_seconds
        stream_mode = bool(on_delta)

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream_mode,
        }

        logger.info(
            f"Invoking Cloud Claude: model={self.config.model}, stream={stream_mode}, timeout={timeout_sec}s"
        )

        if not stream_mode:
            # Non-streaming request
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                try:
                    resp = await client.post(
                        self.config.base_url,
                        headers=headers,
                        json=payload,
                    )
                except httpx.TimeoutException:
                    raise CloudProviderError(f"Anthropic Claude API timed out after {timeout_sec}s")
                except Exception as exc:
                    raise CloudProviderError(f"Network error connecting to Anthropic API: {exc}")

                if resp.status_code == 401:
                    raise CloudProviderError("Authentication failed: Invalid ANTHROPIC_API_KEY.")
                elif resp.status_code == 429:
                    raise CloudProviderError("Anthropic API rate limit exceeded. Please retry later.")
                elif resp.status_code >= 400:
                    try:
                        err_json = resp.json()
                        err_msg = err_json.get("error", {}).get("message", resp.text)
                    except Exception:
                        err_msg = resp.text
                    raise CloudProviderError(f"Anthropic API error ({resp.status_code}): {err_msg}")

                data = resp.json()
                content_blocks = data.get("content", [])
                full_text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
                return full_text

        # Streaming request (SSE)
        collected_tokens: list[str] = []
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            try:
                async with client.stream(
                    "POST",
                    self.config.base_url,
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code == 401:
                        raise CloudProviderError("Authentication failed: Invalid ANTHROPIC_API_KEY.")
                    elif response.status_code == 429:
                        raise CloudProviderError("Anthropic API rate limit exceeded.")
                    elif response.status_code >= 400:
                        body = await response.aread()
                        raise CloudProviderError(f"Anthropic API error ({response.status_code}): {body.decode('utf-8', errors='replace')}")

                    async for raw_line in response.aiter_lines():
                        for line in raw_line.split("\n"):
                            line = line.strip()
                            if not line or not line.startswith("data: "):
                                continue
                            
                            data_str = line[len("data: "):].strip()
                            if data_str == "[DONE]":
                                break

                            try:
                                event_data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            etype = event_data.get("type")
                            if etype == "content_block_delta":
                                delta_obj = event_data.get("delta", {})
                                if delta_obj.get("type") == "text_delta":
                                    token_text = delta_obj.get("text", "")
                                    if token_text:
                                        collected_tokens.append(token_text)
                                        if on_delta:
                                            res = on_delta(token_text)
                                            if asyncio.iscoroutine(res):
                                                await res

                            elif etype == "message_stop":
                                break

            except httpx.TimeoutException:
                raise CloudProviderError(f"Anthropic streaming timed out after {timeout_sec}s")
            except CloudProviderError:
                raise
            except Exception as exc:
                raise CloudProviderError(f"Error during Anthropic streaming: {exc}")

        return "".join(collected_tokens)


DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


@dataclass
class GoogleGeminiConfig:
    """Configuration for Google Gemini client."""
    api_key: Optional[str] = None
    model: str = field(default_factory=lambda: getattr(get_settings(), "gemini_model", DEFAULT_GEMINI_MODEL))
    temperature: float = 0.2
    timeout_seconds: float = field(default_factory=lambda: get_settings().cloud_timeout_seconds)


class GoogleGeminiClient:
    """
    Client for interacting with Google Gemini API (gemini-2.5-flash / gemini-1.5-flash).
    Supports 100% free API keys from Google AI Studio (https://aistudio.google.com/app/apikey).
    Matches the PiAgentClient / AnthropicClaudeClient interface:
    `run_prompt(prompt, timeout=None, on_delta=None) -> str`
    """

    def __init__(self, config: Optional[GoogleGeminiConfig] = None):
        self.config = config or GoogleGeminiConfig()
        self.api_key = (
            self.config.api_key
            or os.getenv("GEMINI_API_KEY", "").strip()
            or os.getenv("GOOGLE_API_KEY", "").strip()
            or getattr(get_settings(), "gemini_api_key", "").strip()
        )

    def is_configured(self) -> bool:
        """Returns True if a valid Google Gemini API key is configured."""
        return bool(
            self.api_key
            and not self.api_key.startswith("your_")
            and len(self.api_key) > 10
        )

    async def run_prompt(
        self,
        prompt: str,
        timeout: Optional[float] = None,
        on_delta: Optional[Callable[[str], Any]] = None,
    ) -> str:
        """Executes prompt against Google Gemini API with streaming support."""
        if not self.is_configured():
            raise CloudProviderError(
                "GEMINI_API_KEY is not configured in the environment. "
                "Get a 100% free API key at https://aistudio.google.com/app/apikey"
            )

        timeout_sec = timeout or self.config.timeout_seconds
        stream_mode = bool(on_delta)
        model = self.config.model

        payload: Dict[str, Any] = {
            "contents": [
                {"parts": [{"text": prompt}]}
            ],
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": 4096,
            },
        }

        candidate_models = [model]
        for fallback_m in ("gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"):
            if fallback_m not in candidate_models:
                candidate_models.append(fallback_m)

        last_error = None
        for current_model in candidate_models:
            logger.info(
                f"Invoking Google Gemini: model={current_model}, stream={stream_mode}, timeout={timeout_sec}s"
            )

            if not stream_mode:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={self.api_key}"
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    try:
                        resp = await client.post(url, json=payload)
                        if resp.status_code in (429, 503):
                            logger.warning(f"Google Gemini model {current_model} returned {resp.status_code}. Trying next model...")
                            continue
                        if resp.status_code == 400 or resp.status_code == 403:
                            raise CloudProviderError(f"Google Gemini authentication/request failed ({resp.status_code}): {resp.text}")
                        elif resp.status_code >= 400:
                            raise CloudProviderError(f"Google Gemini API error ({resp.status_code}): {resp.text}")

                        data = resp.json()
                        text = ""
                        for cand in data.get("candidates", []):
                            for part in cand.get("content", {}).get("parts", []):
                                text += part.get("text", "")
                        return text
                    except httpx.TimeoutException:
                        raise CloudProviderError(f"Google Gemini API timed out after {timeout_sec}s")
                    except CloudProviderError:
                        raise
                    except Exception as exc:
                        logger.warning(f"Error on model {current_model}: {exc}. Trying next model...")
                        last_error = exc
                        continue

            # Streaming request via SSE
            collected = []
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:streamGenerateContent?alt=sse&key={self.api_key}"
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                try:
                    async with client.stream("POST", url, json=payload) as response:
                        if response.status_code in (429, 503):
                            logger.warning(f"Google Gemini model {current_model} returned {response.status_code}. Trying next model...")
                            continue
                        if response.status_code != 200:
                            body = await response.aread()
                            raise CloudProviderError(f"Google Gemini API error ({response.status_code}): {body.decode('utf-8', errors='replace')}")

                        async for raw_line in response.aiter_lines():
                            line = raw_line.strip()
                            if not line or not line.startswith("data: "):
                                continue
                            data_str = line[len("data: "):].strip()
                            try:
                                event_data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            for cand in event_data.get("candidates", []):
                                for part in cand.get("content", {}).get("parts", []):
                                    token = part.get("text", "")
                                    if token:
                                        collected.append(token)
                                        if on_delta:
                                            res = on_delta(token)
                                            if asyncio.iscoroutine(res):
                                                await res
                    return "".join(collected)
                except httpx.TimeoutException:
                    raise CloudProviderError(f"Google Gemini streaming timed out after {timeout_sec}s")
                except CloudProviderError:
                    raise
                except Exception as exc:
                    logger.warning(f"Error streaming on model {current_model}: {exc}. Trying next model...")
                    last_error = exc
                    continue

        raise last_error or CloudProviderError("Google Gemini failed across all fallback models")
