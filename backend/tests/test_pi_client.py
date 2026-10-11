"""
Unit tests for PiAgentClient subprocess configuration, argument safety, and error handling.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from backend.agent.pi_client import (
    PiAgentClient,
    PiAgentConfig,
    PiRPCError,
    DEFAULT_CLI_PATH,
    DEFAULT_AGENT_DIR,
)


def test_pi_client_config_defaults():
    """Verify default configuration uses local Ollama and points to PoC."""
    cfg = PiAgentConfig()
    assert cfg.provider == "ollama"
    assert cfg.model == "llama3.2:3b"
    assert cfg.timeout_seconds > 0
    assert cfg.cli_path == DEFAULT_CLI_PATH
    assert cfg.agent_dir == DEFAULT_AGENT_DIR


def test_pi_client_env_isolation(monkeypatch):
    """Verify that cloud keys are stripped from subprocess environment."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai-key")

    client = PiAgentClient()
    env = client._build_env()

    assert "ANTHROPIC_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    # A runtime copy of the agent dir is used so models.json follows OLLAMA_BASE_URL / OLLAMA_MODEL.
    import json
    models = json.loads((Path(env["PI_CODING_AGENT_DIR"]) / "models.json").read_text())
    assert models["providers"]["ollama"]["baseUrl"].endswith("/v1")
    assert models["providers"]["ollama"]["models"][0]["id"] == client.config.model


def test_pi_client_command_safety_flags():
    """Verify restricted arguments matching the PoC."""
    client = PiAgentClient()
    cmd = client._build_cmd()

    assert "--mode" in cmd and cmd[cmd.index("--mode") + 1] == "rpc"
    assert "--no-session" in cmd
    assert "--no-tools" in cmd
    assert "--no-extensions" in cmd
    assert "--no-skills" in cmd
    assert "--no-prompt-templates" in cmd
    assert "--no-context-files" in cmd
    assert "--provider" in cmd and cmd[cmd.index("--provider") + 1] == "ollama"
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "llama3.2:3b"


@pytest.mark.asyncio
async def test_pi_client_raises_when_binary_missing():
    """Verify clean error when CLI path does not exist."""
    bad_config = PiAgentConfig(cli_path=Path("nonexistent/path/cli.js"))
    client = PiAgentClient(bad_config)

    with pytest.raises(PiRPCError, match="Pi CLI binary not found"):
        await client.run_prompt("Hello")
