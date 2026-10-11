"""
Subprocess client for the genuine Pi Coding Agent running in RPC mode with local Ollama.
Reuses the verified integration approach from proof-of-concept/test_pi_rpc.py.
Handles JSONL streaming, timeouts, clean process termination, Windows Proactor event loop
bridging, and resilient direct Ollama HTTP fallback.
"""

import asyncio
import concurrent.futures
from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Dict, Any, List, Optional, Callable
import uuid

import httpx

from backend.config import get_settings

logger = logging.getLogger("agent.pi_client")

# Default paths relative to workspace root
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CLI_PATH = WORKSPACE_ROOT / "proof-of-concept" / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "bundle" / "cli.js"
DEFAULT_AGENT_DIR = WORKSPACE_ROOT / "proof-of-concept" / ".pi-agent"


@dataclass
class PiAgentConfig:
    """Configuration for Pi Coding Agent RPC subprocess."""
    cli_path: Path = DEFAULT_CLI_PATH
    agent_dir: Path = DEFAULT_AGENT_DIR
    node_binary: str = "node"
    provider: str = "ollama"
    # Env-driven defaults (OLLAMA_MODEL / OLLAMA_BASE_URL / OLLAMA_TIMEOUT_SECONDS / OLLAMA_NUM_CTX):
    # switching the local model never requires a code change.
    model: str = field(default_factory=lambda: get_settings().ollama_model)
    timeout_seconds: float = field(default_factory=lambda: get_settings().ollama_timeout_seconds)
    ollama_base_url: str = field(default_factory=lambda: get_settings().ollama_base_url)
    num_ctx: int = field(default_factory=lambda: get_settings().ollama_num_ctx)


class PiRPCError(Exception):
    """Exception raised for Pi RPC execution failures."""
    pass


class PiAgentClient:
    """
    Client for interacting with Pi Coding Agent in headless RPC mode.
    Communicates strictly over stdin/stdout JSONL pipes.
    Includes Windows Proactor event loop bridging and direct Ollama HTTP fallback.
    """

    def __init__(self, config: Optional[PiAgentConfig] = None):
        self.config = config or PiAgentConfig()

    def _runtime_agent_dir(self) -> Path:
        """
        Pi reads its provider list from `<agent_dir>/models.json`. The committed template hard-codes
        http://localhost:11434, which is wrong inside Docker (where Ollama is reached through
        host.docker.internal). We therefore materialise a runtime copy of the agent dir whose
        models.json points at the configured OLLAMA_BASE_URL / OLLAMA_MODEL.
        """
        key = hashlib.sha1(f"{self.config.ollama_base_url}|{self.config.model}".encode()).hexdigest()[:10]
        runtime_dir = Path(tempfile.gettempdir()) / "lenny-pi-agent" / key
        try:
            runtime_dir.mkdir(parents=True, exist_ok=True)
            template = self.config.agent_dir
            if template.exists():
                for item in template.iterdir():
                    if item.is_file() and item.name != "models.json":
                        shutil.copy2(item, runtime_dir / item.name)
            models = {
                "providers": {
                    "ollama": {
                        "baseUrl": f"{self.config.ollama_base_url.rstrip('/')}/v1",
                        "api": "openai-completions",
                        "apiKey": "ollama",
                        "models": [{"id": self.config.model}],
                    }
                }
            }
            (runtime_dir / "models.json").write_text(json.dumps(models, indent=2), encoding="utf-8")
            return runtime_dir
        except OSError as exc:
            logger.warning("pi_runtime_dir_failed", extra={"error": str(exc)})
            return self.config.agent_dir

    def _build_env(self) -> Dict[str, str]:
        """Constructs an isolated environment without cloud credentials."""
        env = os.environ.copy()
        env["PI_CODING_AGENT_DIR"] = str(self._runtime_agent_dir())
        # Prevent any ambient cloud keys from being accessed by the agent
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
        return env

    def _build_cmd(self) -> List[str]:
        """Builds command-line arguments restricting tools and extensions."""
        return [
            self.config.node_binary,
            str(self.config.cli_path),
            "--mode", "rpc",
            "--no-session",
            "--no-tools",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-context-files",
            "--provider", self.config.provider,
            "--model", self.config.model,
        ]

    async def _run_subprocess_internal(
        self,
        prompt: str,
        timeout_sec: float,
        on_delta: Optional[Callable[[str], Any]] = None,
    ) -> str:
        """Executes the Pi RPC subprocess directly in the active asyncio event loop."""
        req_id = f"req-{uuid.uuid4().hex[:12]}"
        cmd = self._build_cmd()
        env = self._build_env()

        logger.info(f"Spawning Pi RPC subprocess: {' '.join(cmd[:4])} (provider={self.config.provider}, model={self.config.model})")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(self.config.cli_path.parent.parent.parent.parent.parent),
            )
        except NotImplementedError:
            raise NotImplementedError("Subprocess execution not supported on current asyncio event loop")
        except Exception as spawn_err:
            raise PiRPCError(f"Failed to spawn Pi RPC subprocess ({type(spawn_err).__name__}): {spawn_err}")

        stderr_lines: List[str] = []

        async def _drain_stderr():
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    stderr_lines.append(decoded)
                    logger.debug(f"[Pi stderr] {decoded}")

        stderr_task = asyncio.create_task(_drain_stderr())

        collected_deltas: List[str] = []
        turn_completed = False
        prompt_accepted = False
        error_msg = None
        fallback_text: Optional[str] = None

        try:
            # Short stabilization delay
            await asyncio.sleep(0.5)

            # Send prompt over stdin
            payload = {
                "id": req_id,
                "type": "prompt",
                "message": prompt,
            }
            line = json.dumps(payload) + "\n"
            process.stdin.write(line.encode("utf-8"))
            await process.stdin.drain()

            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break

                try:
                    line_bytes = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=min(remaining, 5.0),
                    )
                except asyncio.TimeoutError:
                    if turn_completed:
                        break
                    continue

                if not line_bytes:
                    break

                line_str = line_bytes.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    record = json.loads(line_str)
                except json.JSONDecodeError:
                    logger.warning(f"Malformed JSON from Pi RPC stdout: {line_str[:120]}")
                    continue

                rec_type = record.get("type")

                # Robust fallback: capture full text from assistant message payload if present
                if rec_type in ("message_start", "message_update", "message_end", "turn_end"):
                    msg = record.get("message")
                    if isinstance(msg, dict) and msg.get("role") == "assistant":
                        content = msg.get("content")
                        if isinstance(content, str) and content.strip():
                            fallback_text = content.strip()
                        elif isinstance(content, list):
                            parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                            if parts:
                                fallback_text = "".join(parts).strip()

                if rec_type == "response" and record.get("id") == req_id:
                    prompt_accepted = record.get("success", False)
                    if not prompt_accepted:
                        error_msg = record.get("error", "Prompt rejected by Pi RPC")
                        logger.error(f"Pi RPC prompt rejected: {error_msg}")

                elif rec_type == "message_update":
                    evt = record.get("assistantMessageEvent", {})
                    if evt.get("type") == "text_delta":
                        delta = evt.get("delta", "")
                        collected_deltas.append(delta)
                        if on_delta:
                            res = on_delta(delta)
                            if asyncio.iscoroutine(res):
                                await res

                elif rec_type in ("turn_end", "agent_end", "agent_settled"):
                    turn_completed = True
                    break

        except asyncio.TimeoutError:
            raise PiRPCError(f"Pi RPC timed out after {timeout_sec} seconds")
        except Exception as exc:
            raise PiRPCError(f"Pi RPC communication error ({type(exc).__name__}): {exc}")
        finally:
            if process.stdin:
                try:
                    process.stdin.close()
                    await process.stdin.wait_closed()
                except Exception:
                    pass

            try:
                await asyncio.wait_for(process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                logger.warning("Terminating Pi RPC subprocess...")
                process.terminate()
                await process.wait()

            await stderr_task

        if error_msg:
            raise PiRPCError(f"Pi RPC error: {error_msg}. Diagnostics: {'; '.join(stderr_lines[-3:])}")

        full_text = "".join(collected_deltas).strip()
        if not full_text and fallback_text:
            full_text = fallback_text
            if on_delta:
                try:
                    res = on_delta(full_text)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass

        if not full_text and stderr_lines:
            stderr_joined = " ".join(stderr_lines)
            if "ECONNREFUSED" in stderr_joined or "fetch failed" in stderr_joined:
                raise PiRPCError(f"Ollama connection refused at {self.config.ollama_base_url}. Stderr: {stderr_joined}")
            raise PiRPCError(f"Pi completed with empty output. Stderr: {stderr_joined}")

        return full_text

    async def _run_in_proactor_thread(
        self,
        prompt: str,
        timeout_sec: float,
        on_delta: Optional[Callable[[str], Any]] = None,
        caller_loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> str:
        """
        Runs Pi RPC in a dedicated worker thread with a Windows ProactorEventLoop.
        This resolves the Windows Uvicorn SelectorEventLoop limitation where
        create_subprocess_exec raises NotImplementedError.
        """
        caller_loop = caller_loop or asyncio.get_running_loop()

        def _worker() -> str:
            # Create isolated Proactor event loop for this worker thread
            worker_loop = asyncio.WindowsProactorEventLoopPolicy().new_event_loop()
            asyncio.set_event_loop(worker_loop)

            def _thread_safe_delta(delta: str):
                if not on_delta:
                    return
                try:
                    if asyncio.iscoroutinefunction(on_delta):
                        caller_loop.call_soon_threadsafe(caller_loop.create_task, on_delta(delta))
                    else:
                        caller_loop.call_soon_threadsafe(on_delta, delta)
                except Exception as err:
                    logger.debug(f"Error dispatching token delta: {err}")

            try:
                return worker_loop.run_until_complete(
                    self._run_subprocess_internal(
                        prompt=prompt,
                        timeout_sec=timeout_sec,
                        on_delta=_thread_safe_delta if on_delta else None,
                    )
                )
            finally:
                worker_loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return await caller_loop.run_in_executor(pool, _worker)

    async def _fallback_ollama_http(
        self,
        prompt: str,
        timeout_sec: float,
        on_delta: Optional[Callable[[str], Any]] = None,
    ) -> str:
        """Direct HTTP fallback to local Ollama API if subprocess cannot run."""
        url = f"{self.config.ollama_base_url.rstrip('/')}/api/generate"
        logger.info(f"Invoking Ollama HTTP fallback: {url} (model={self.config.model})")
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": True,
            # Ollama silently truncates prompts beyond num_ctx; retrieval + history prompts are long.
            "options": {"num_ctx": self.config.num_ctx},
        }
        collected_tokens: List[str] = []
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        token = record.get("response", "")
                        if token:
                            collected_tokens.append(token)
                            if on_delta:
                                res = on_delta(token)
                                if asyncio.iscoroutine(res):
                                    await res

                        if record.get("done", False):
                            break

            return "".join(collected_tokens).strip()
        except Exception as http_err:
            raise PiRPCError(f"Ollama HTTP fallback failure ({type(http_err).__name__}): {http_err}")

    async def run_prompt(
        self,
        prompt: str,
        timeout: Optional[float] = None,
        on_delta: Optional[Callable[[str], Any]] = None,
    ) -> str:
        """
        Executes a prompt via Pi Coding Agent RPC and returns the full assistant response.
        Falls back seamlessly to direct Ollama HTTP if subprocess execution is blocked.
        """
        timeout_sec = timeout or self.config.timeout_seconds
        pi_error: Optional[Exception] = None

        if not self.config.cli_path.exists():
            # Resilience: without the Pi CLI (e.g. `npm ci` not run) we still serve answers via Ollama's HTTP API.
            logger.warning("pi_cli_missing_using_http_fallback", extra={"cli_path": str(self.config.cli_path)})
            try:
                return await self._fallback_ollama_http(prompt=prompt, timeout_sec=timeout_sec, on_delta=on_delta)
            except PiRPCError as fb_err:
                raise PiRPCError(f"Pi CLI binary not found at {self.config.cli_path} and Ollama HTTP fallback failed: {fb_err}")

        current_loop = asyncio.get_running_loop()
        is_win = sys.platform == "win32"
        is_selector = is_win and "Selector" in type(current_loop).__name__

        try:
            if is_selector:
                logger.info("Current loop is SelectorEventLoop on Windows. Using Proactor thread bridge for Pi RPC.")
                return await self._run_in_proactor_thread(
                    prompt=prompt,
                    timeout_sec=timeout_sec,
                    on_delta=on_delta,
                    caller_loop=current_loop,
                )
            else:
                return await self._run_subprocess_internal(
                    prompt=prompt,
                    timeout_sec=timeout_sec,
                    on_delta=on_delta,
                )
        except NotImplementedError:
            if is_win:
                logger.info("Caught NotImplementedError on subprocess. Retrying via Proactor thread bridge...")
                try:
                    return await self._run_in_proactor_thread(
                        prompt=prompt,
                        timeout_sec=timeout_sec,
                        on_delta=on_delta,
                        caller_loop=current_loop,
                    )
                except Exception as bridge_err:
                    pi_error = bridge_err
            else:
                pi_error = NotImplementedError("Subprocess not supported on active loop")
        except Exception as rpc_err:
            logger.warning(f"Pi RPC subprocess execution failed ({type(rpc_err).__name__}): {rpc_err}")
            pi_error = rpc_err

        # Fallback to direct Ollama HTTP if Pi RPC failed or is unavailable
        logger.info(f"Initiating Ollama HTTP API fallback due to: {pi_error}")
        try:
            return await self._fallback_ollama_http(
                prompt=prompt,
                timeout_sec=timeout_sec,
                on_delta=on_delta,
            )
        except Exception as fb_err:
            raise PiRPCError(f"Both Pi RPC and Ollama HTTP fallback failed. Pi: {pi_error} | Fallback: {fb_err}")
