"""
Minimal Proof of Concept (PoC) for Pi Coding Agent in RPC mode with Local Ollama.
Verifies that:
1. Pi Coding Agent launches as a headless subprocess (communicating purely over stdin/stdout JSONL).
2. Uses local Ollama (llama3.2:3b) via OpenAI-compatible endpoint.
3. Sends one harmless prompt, collects the streaming response, enforces timeout, and terminates cleanly.
4. Operates in read-only isolated mode without exposing network ports, tools, or sessions.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path


async def run_pi_rpc_poc():
    base_dir = Path(__file__).resolve().parent
    cli_path = base_dir / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "bundle" / "cli.js"
    agent_dir = base_dir / ".pi-agent"

    if not cli_path.exists():
        print(f"ERROR: Pi CLI not found at {cli_path}")
        return False

    # Configure isolated environment
    env = os.environ.copy()
    env["PI_CODING_AGENT_DIR"] = str(agent_dir)
    # Ensure no cloud API keys are passed
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)

    cmd = [
        "node",
        str(cli_path),
        "--mode", "rpc",
        "--no-session",
        "--no-tools",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-context-files",
        "--provider", "ollama",
        "--model", "llama3.2:3b",
    ]

    print("=" * 60)
    print("PI CODING AGENT RPC PROOF OF CONCEPT (PoC)")
    print(f"Executable: node {cli_path}")
    print(f"Provider: ollama | Model: llama3.2:3b")
    print(f"Agent Dir: {agent_dir}")
    print("=" * 60)

    start_time = time.time()
    trace_events = []
    collected_deltas = []
    stderr_lines = []

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(base_dir),
    )

    # Background reader for stderr
    async def read_stderr():
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded:
                stderr_lines.append(decoded)

    stderr_task = asyncio.create_task(read_stderr())

    test_prompt = {
        "id": "poc-req-001",
        "type": "prompt",
        "message": "Reply with 'Hello from Pi Coding Agent and Ollama!' and nothing else.",
    }

    turn_completed = False
    prompt_accepted = False

    try:
        # Give process 2 seconds to initialize RPC loop
        await asyncio.sleep(1.0)

        # Send test prompt over stdin
        prompt_line = json.dumps(test_prompt) + "\n"
        print(f"\n[CLIENT -> PI stdin]: {prompt_line.strip()}")
        process.stdin.write(prompt_line.encode("utf-8"))
        await process.stdin.drain()

        # Read JSONL records from stdout with 45s overall timeout
        timeout_seconds = 45.0
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            try:
                line_bytes = await asyncio.wait_for(process.stdout.readline(), timeout=min(remaining, 5.0))
            except asyncio.TimeoutError:
                if turn_completed:
                    break
                continue

            if not line_bytes:
                # EOF on stdout
                break

            line_str = line_bytes.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue

            try:
                record = json.loads(line_str)
                trace_events.append(record)
                rec_type = record.get("type")

                if rec_type == "response" and record.get("id") == "poc-req-001":
                    prompt_accepted = record.get("success", False)
                    print(f"[PI stdout RESPONSE]: success={prompt_accepted}, disposition={record.get('data', {}).get('disposition')}")

                elif rec_type == "message_update":
                    evt = record.get("assistantMessageEvent", {})
                    if evt.get("type") == "text_delta":
                        delta = evt.get("delta", "")
                        collected_deltas.append(delta)
                        print(delta, end="", flush=True)

                elif rec_type == "message_end":
                    msg = record.get("message", {})
                    print(f"\n[PI stdout MESSAGE_END]: role={msg.get('role')}")

                elif rec_type in ("turn_end", "agent_end", "agent_settled"):
                    print(f"\n[PI stdout {rec_type.upper()}]: Run finished.")
                    turn_completed = True
                    break

            except json.JSONDecodeError:
                print(f"[NON-JSON stdout]: {line_str}")

    except Exception as exc:
        print(f"\nERROR during RPC execution: {exc}")
    finally:
        # Clean process shutdown
        print("\nCleaning up subprocess...")
        if process.stdin:
            try:
                process.stdin.close()
                await process.stdin.wait_closed()
            except Exception:
                pass

        try:
            await asyncio.wait_for(process.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            print("Force-terminating process...")
            process.terminate()
            await process.wait()

        await stderr_task

    duration = time.time() - start_time
    full_response = "".join(collected_deltas).strip()

    # Save sanitized execution trace
    trace_data = {
        "status": "SUCCESS" if (prompt_accepted and turn_completed) else "FAILURE",
        "duration_seconds": round(duration, 2),
        "prompt_sent": test_prompt["message"],
        "model_selected": "ollama/llama3.2:3b",
        "response_received": full_response,
        "events_count": len(trace_events),
        "events": trace_events,
        "stderr_diagnostics": stderr_lines,
    }

    trace_file = base_dir / "trace.json"
    with open(trace_file, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, indent=2)

    print("\n" + "=" * 60)
    print("PoC EXECUTION SUMMARY")
    print(f"Status: {trace_data['status']}")
    print(f"Duration: {trace_data['duration_seconds']}s")
    print(f"Prompt Accepted: {prompt_accepted}")
    print(f"Turn Completed: {turn_completed}")
    print(f"Response Received: {full_response!r}")
    print(f"Trace saved to: {trace_file}")
    print("=" * 60)

    return prompt_accepted and turn_completed and bool(full_response)


if __name__ == "__main__":
    success = asyncio.run(run_pi_rpc_poc())
    sys.exit(0 if success else 1)
