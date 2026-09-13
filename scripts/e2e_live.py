"""
Live battle E2E: sequential plan, parallel plan, agent delegation.

Boots real MCP servers (ninja-coder, ninja-agent) over stdio, connects an
MCP client, and drives real tool calls against a temp git repo using the
host's configured CLI + OPENROUTER key. These are REAL model runs.

Run via ``scripts/e2e_live.sh`` (or directly: ``uv run python scripts/e2e_live.py``).
Set ``E2E_SCOPE`` to ``sequential`` / ``parallel`` / ``delegate`` / ``all`` and
``REPO_PATH`` to choose the target repo.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


REPO = Path(os.environ.get("REPO_PATH", "/tmp/opencode/e2e_battle_repo"))
SCOPE = os.environ.get("E2E_SCOPE", "all")


def _setup_repo() -> None:
    shutil.rmtree(REPO, ignore_errors=True)
    REPO.mkdir(parents=True)
    (REPO / "greet.py").write_text('def greet(name: str) -> str:\n    return f"Hello, {name}"\n')
    subprocess.run(["git", "init"], cwd=REPO, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "e2e@test"], cwd=REPO, check=True, capture_output=True
    )
    subprocess.run(["git", "config", "user.name", "E2E"], cwd=REPO, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=REPO, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=REPO, check=True, capture_output=True)


def _extract_json(result) -> dict:
    """Pull the structured result from an MCP tool call.

    Prefers ``structuredContent``; falls back to parsing the JSON embedded in
    ``content[].text`` (which is what the ninja servers return).
    """
    structured = getattr(result, "structuredContent", None) or {}
    if structured:
        return structured

    text = ""
    for c in result.content:
        text += (getattr(c, "text", "") or "") + "\n"
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Some servers return a plain message; wrap it so callers see text.
        return {"_text": text}


async def _tool_call(session: ClientSession, name: str, args: dict) -> dict:
    print(f"\n>>> calling {name}")
    t0 = time.time()
    result = await session.call_tool(name, args)
    dt = time.time() - t0
    print(f"    [took {dt:.1f}s]")
    data = _extract_json(result)
    # Compact dump of the structured payload for visibility.
    print("    " + json.dumps(data, ensure_ascii=False)[:1200])
    return data


async def _coder_sequential(session: ClientSession) -> dict:
    return await _tool_call(
        session,
        "coder_execute_plan_sequential",
        {
            "repo_root": str(REPO),
            "mode": "quick",
            "steps": [
                {
                    "id": "s1",
                    "title": "Add goodbye",
                    "task": (
                        "Add a goodbye(name) function to greet.py "
                        'returning f"Goodbye, {name}". Keep greet unchanged.'
                    ),
                    "allowed_globs": ["greet.py"],
                },
                {
                    "id": "s2",
                    "title": "Add CLI entry",
                    "task": (
                        "Add a __main__ block to greet.py that calls "
                        'both greet() and goodbye() with name="World".'
                    ),
                    "allowed_globs": ["greet.py"],
                },
            ],
        },
    )


async def _coder_parallel(session: ClientSession) -> dict:
    return await _tool_call(
        session,
        "coder_execute_plan_parallel",
        {
            "repo_root": str(REPO),
            "complexity": "simple",
            "fanout": 2,
            "steps": [
                {
                    "id": "p1",
                    "title": "Add math add",
                    "task": "Create math_ops.py with an add(a, b) function returning a + b.",
                    "allowed_globs": ["math_ops.py"],
                },
                {
                    "id": "p2",
                    "title": "Add math mul",
                    "task": "Create calc_ops.py with a multiply(a, b) function returning a * b.",
                    "allowed_globs": ["calc_ops.py"],
                },
            ],
        },
    )


async def _agent_delegate(session: ClientSession) -> dict:
    return await _tool_call(
        session,
        "agent_delegate",
        {
            "delegate_to": "coder",
            "subtask": (
                "Create utils.py in the repo with an is_even(n) function returning n % 2 == 0."
            ),
            "repo_root": str(REPO),
        },
    )


async def main() -> None:
    _setup_repo()
    print(f"repo: {REPO} | scope: {SCOPE}")
    print("NINJA_CODE_BIN:", os.environ.get("NINJA_CODE_BIN", "opencode"))
    print("model:", os.environ.get("NINJA_MODEL", "default"))

    coder_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ninja_coder.server"],
        env={**os.environ},
    )
    agent_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ninja_agent.server"],
        env={**os.environ},
    )

    results: dict[str, dict] = {}

    if SCOPE in ("sequential", "all"):
        print("\n" + "=" * 70)
        print("E2E 1: coder_execute_plan_sequential")
        print("=" * 70)
        async with stdio_client(coder_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                results["sequential"] = await _coder_sequential(session)
        seq = results["sequential"]
        print("\nSEQUENTIAL overall_status:", seq.get("overall_status"))
        print("SEQUENTIAL steps:", [(s.get("id"), s.get("status")) for s in seq.get("steps", [])])

    if SCOPE in ("parallel", "all"):
        print("\n" + "=" * 70)
        print("E2E 2: coder_execute_plan_parallel")
        print("=" * 70)
        async with stdio_client(coder_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                results["parallel"] = await _coder_parallel(session)
        par = results["parallel"]
        print("\nPARALLEL overall_status:", par.get("overall_status"))
        print("PARALLEL steps:", [(s.get("id"), s.get("status")) for s in par.get("steps", [])])

    if SCOPE in ("delegate", "all"):
        print("\n" + "=" * 70)
        print("E2E 3: agent_delegate -> coder")
        print("=" * 70)
        async with stdio_client(agent_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                results["delegate"] = await _agent_delegate(session)
        dele = results["delegate"]
        print("\nDELEGATE success:", dele.get("success"))
        print("DELEGATE delegate_to:", dele.get("delegate_to"))

    print("\n" + "=" * 70)
    print("VERIFY files")
    print("=" * 70)
    expected = ["greet.py"]
    if SCOPE in ("parallel", "all"):
        expected += ["math_ops.py", "calc_ops.py"]
    if SCOPE in ("delegate", "all"):
        expected += ["utils.py"]
    for f in expected:
        p = REPO / f
        ok = p.exists()
        print(f"  {f}: {'OK' if ok else 'MISSING'}")
        if ok:
            print("    " + p.read_text().splitlines()[0])

    print("\nALL LIVE E2E CALLS COMPLETED")


if __name__ == "__main__":
    asyncio.run(main())
