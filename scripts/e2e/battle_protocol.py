#!/usr/bin/env python3
"""Live protocol conformance suite for running ninja-mcp daemons (MCP 2026-07-28).

Read-only by construction: the only tools invoked are read-only ones
(jobs list / logs query / branches list / processes / analyze / file search).
Nothing in this file mutates a repository, spawns a coding CLI, deletes a
branch, or restarts a daemon.

The suite is opt-in: it needs four running daemons and is intentionally not
wired into the default pytest run. Exit code is 0 only when every check passed.

Usage:
    python scripts/e2e/battle_protocol.py
    python scripts/e2e/battle_protocol.py --json /tmp/protocol.json
    python scripts/e2e/battle_protocol.py --ports coder=8100,agent=8106

Ports come from ``NINJA_<MODULE>_PORT`` (coder, researcher, agent, secretary)
and can be overridden with ``--ports module=port,...``.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp import Client, types
from mcp.client.extension import advertise
from pydantic import TypeAdapter

# The tasks extension needs a claim resolver, not just an ad: a client that
# merely advertises gets `resultType: "task"` back and cannot shape it into a
# CallToolResult. This is the repo's own companion client.
from ninja_common.mcp_ext.tasks_client import TasksClient


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

SKILLS_EXT = "io.modelcontextprotocol/skills"
TASKS_EXT = "io.modelcontextprotocol/tasks"
MODERN = "2026-07-28"
CALL_TIMEOUT = 30.0

EXTENSIONS = [advertise(SKILLS_EXT, {}), TasksClient(timeout_seconds=120, poll_interval_ms=250)]

#: Deployed defaults; every value is overridable through the environment or
#: ``--ports`` so the suite is not tied to one machine's layout.
DEFAULT_PORTS: dict[str, int] = {
    "coder": 8100,
    "researcher": 8101,
    "agent": 8106,
    "secretary": 8107,
}
PORT_ENV: dict[str, str] = {
    "coder": "NINJA_CODER_PORT",
    "researcher": "NINJA_RESEARCHER_PORT",
    "agent": "NINJA_AGENT_PORT",
    "secretary": "NINJA_SECRETARY_PORT",
}


def resolve_ports(override: str | None) -> dict[str, int]:
    """Resolve module ports: CLI override > environment > deployed default."""
    ports = {}
    for key, default in DEFAULT_PORTS.items():
        raw = os.environ.get(PORT_ENV[key], "").strip()
        try:
            ports[key] = int(raw) if raw else default
        except ValueError:
            raise SystemExit(f"{PORT_ENV[key]} must be an integer, got {raw!r}") from None
    if override:
        for item in override.split(","):
            if not item.strip():
                continue
            try:
                key, value = item.split("=", 1)
            except ValueError:
                raise SystemExit(f"--ports expects module=port pairs, got {item!r}") from None
            key = key.strip().lower()
            if key not in ports:
                raise SystemExit(f"unknown module {key!r}; expected one of {sorted(ports)}")
            try:
                ports[key] = int(value)
            except ValueError:
                raise SystemExit(f"port for {key!r} must be an integer, got {value!r}") from None
    return ports


@dataclass(frozen=True)
class ServerSpec:
    key: str
    port: int
    server_name: str
    tool_count: int
    skill_count: int
    #: a no-argument (or trivially safe) read-only tool used as the health probe
    probe_tool: str
    probe_args: dict[str, Any]
    #: read-only tool with required args, used for the missing/wrong-arg paths
    strict_tool: str


#: Static expectations per daemon; only the port is resolved at runtime.
SERVER_TEMPLATES: tuple[ServerSpec, ...] = (
    ServerSpec("coder", 0, "ninja-coder", 16, 4, "coder_jobs_list", {}, "coder_job_status"),
    ServerSpec(
        "researcher",
        0,
        "ninja-researcher",
        8,
        3,
        "researcher_arxiv_search",
        {"query": "model context protocol"},
        "researcher_arxiv_search",
    ),
    ServerSpec("agent", 0, "ninja-agent", 9, 2, "agent_processes", {}, "agent_analyze"),
    ServerSpec(
        "secretary",
        0,
        "ninja-secretary",
        6,
        2,
        "secretary_session_report",
        {},
        "secretary_file_search",
    ),
)


def build_servers(ports: dict[str, int]) -> tuple[ServerSpec, ...]:
    return tuple(
        ServerSpec(
            key=spec.key,
            port=ports[spec.key],
            server_name=spec.server_name,
            tool_count=spec.tool_count,
            skill_count=spec.skill_count,
            probe_tool=spec.probe_tool,
            probe_args=spec.probe_args,
            strict_tool=spec.strict_tool,
        )
        for spec in SERVER_TEMPLATES
    )


SERVERS: tuple[ServerSpec, ...] = build_servers(resolve_ports(None))
BY_KEY: dict[str, ServerSpec] = {s.key: s for s in SERVERS}

#: Scratch directory handed to tools that require an existing repo_root.
WORK_ROOT = Path(tempfile.mkdtemp(prefix="ninja-e2e-protocol-"))


# --------------------------------------------------------------------------- #
# Result bookkeeping
# --------------------------------------------------------------------------- #


@dataclass
class Check:
    section: str
    server: str
    title: str
    ok: bool
    observed: str = ""
    failure: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    timings: list[tuple[str, float]] = field(default_factory=list)
    skills: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    digest_mismatches: list[str] = field(default_factory=list)
    path_hits: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def record(self, section, server, title, ok, observed="", failure=""):
        self.checks.append(Check(section, server, title, ok, observed, failure))
        return ok

    def fail(self, section, server, title, observed, failure=""):
        return self.record(section, server, title, False, observed, failure or observed)


REPORT = Report()


def timed(label: str, started: float) -> None:
    REPORT.timings.append((label, time.monotonic() - started))


async def call(label: str, coro, timeout: float = CALL_TIMEOUT):
    started = time.monotonic()
    try:
        return await asyncio.wait_for(coro, timeout)
    finally:
        timed(label, started)


def meta_of(obj: Any) -> dict[str, Any]:
    meta = getattr(obj, "meta", None)
    return meta if isinstance(meta, dict) else {}


def has_server_info(obj: Any) -> bool:
    info = meta_of(obj).get("io.modelcontextprotocol/serverInfo")
    return isinstance(info, dict) and bool(info.get("name"))


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #


async def raw_request(client: Client, method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Send an extension method the typed client does not model."""
    return await client.session.send_request(
        types.Request[dict, str](method=method, params=params),  # type: ignore[arg-type]
        result_type=TypeAdapter(dict),
    )


def split_frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip().strip("'\"")
    return out


def resource_bytes(contents: Any) -> bytes:
    if getattr(contents, "blob", None) is not None:
        return base64.b64decode(contents.blob)
    return (contents.text or "").encode("utf-8")


# --------------------------------------------------------------------------- #
# A. Discovery & capability conformance
# --------------------------------------------------------------------------- #


async def section_a(client: Client, spec: ServerSpec) -> None:
    s = spec.key

    REPORT.record(
        "A1",
        s,
        "protocol_version == 2026-07-28",
        client.protocol_version == MODERN,
        observed=client.protocol_version,
    )

    caps = client.server_capabilities
    ext = getattr(caps, "extensions", None) or {}
    ok = SKILLS_EXT in ext and TASKS_EXT in ext
    REPORT.record("A2", s, "extensions advertise skills+tasks", ok, observed=str(sorted(ext)))

    has_tools = caps.tools is not None
    has_resources = caps.resources is not None
    has_prompts = getattr(caps, "prompts", None) is not None
    ok = has_tools and has_resources and not has_prompts
    REPORT.record(
        "A3",
        s,
        "tools+resources present, prompts absent",
        ok,
        observed=f"tools={has_tools} resources={has_resources} prompts={has_prompts}",
    )

    info = client.server_info
    name = getattr(info, "name", None) if info else None
    REPORT.record("A4", s, "server_info.name non-empty", bool(name), observed=repr(name))

    tools1 = await call(f"{s} tools/list#1", client.list_tools())
    tools2 = await call(f"{s} tools/list#2", client.list_tools())
    n1 = [t.name for t in tools1.tools]
    n2 = [t.name for t in tools2.tools]
    j1 = [json.dumps(t.input_schema, sort_keys=False) for t in tools1.tools]
    j2 = [json.dumps(t.input_schema, sort_keys=False) for t in tools2.tools]
    ok = n1 == n2 and j1 == j2
    detail = "identical"
    if not ok:
        detail = f"order_equal={n1 == n2} schema_equal={j1 == j2}"
    REPORT.record("A5", s, "tools/list deterministic", ok, observed=detail)

    bad = []
    for t in tools1.tools:
        schema = t.input_schema or {}
        out_schema = t.output_schema or {}
        hints = []
        if t.annotations is not None:
            hints = [
                k
                for k, v in t.annotations.model_dump(exclude_none=True).items()
                if k != "title" and v is not None
            ]
        problems = []
        if schema.get("type") != "object":
            problems.append(f"input_schema.type={schema.get('type')!r}")
        if not (t.title or "").strip():
            problems.append("title empty")
        if not hints:
            problems.append("no annotation hint")
        if out_schema.get("type") != "object":
            problems.append(f"output_schema root type={out_schema.get('type')!r}")
        if problems:
            bad.append(f"{t.name}: {', '.join(problems)}")
    REPORT.record(
        "A6",
        s,
        "every tool schema/title/hints/object output",
        not bad,
        observed="all conform" if not bad else "; ".join(bad),
    )

    REPORT.record(
        "A7",
        s,
        f"tool count == {spec.tool_count}",
        len(tools1.tools) == spec.tool_count,
        observed=str(len(tools1.tools)),
    )

    if spec.key == "secretary":
        # Regression: the advertised schema must require repo_root, matching runtime
        # validation (2.0.2). Report the observed list so drift is visible.
        search = next(t for t in tools1.tools if t.name == "secretary_file_search")
        required = (search.input_schema or {}).get("required") or []
        ok = "pattern" in required and "repo_root" in required
        REPORT.record(
            "A8",
            s,
            "secretary_file_search requires pattern+repo_root",
            ok,
            observed=f"required={required}",
        )

    # E1: modern responses carry _meta serverInfo
    missing = []
    if not has_server_info(tools1):
        missing.append("tools/list")
    REPORT.record(
        "E1",
        s,
        "_meta.serverInfo on every modern response",
        not missing,
        observed="present" if not missing else f"missing on {missing}",
    )
    REPORT_STATE["tools"].update({s: len(tools1.tools)})
    collect_text(f"{s} instructions", client.instructions or "")
    for t in tools1.tools:
        collect_text(
            f"{s} tool-description {t.name}",
            f"{t.title or ''}\n{t.description or ''}\n{json.dumps(t.input_schema)}",
        )


REPORT_STATE: dict[str, dict[str, Any]] = {"tools": {}, "skills": {}, "manifests": {}, "text": []}


def collect_text(label: str, text: str, *, skill_text: bool = False) -> None:
    """Keep a payload for the end-of-run host-path scan."""
    REPORT_STATE["text"].append((label, text or "", skill_text))


# --------------------------------------------------------------------------- #
# B. Skills
# --------------------------------------------------------------------------- #


async def section_b(client: Client, spec: ServerSpec) -> None:
    s = spec.key
    listing = await call(f"{s} skills/list", raw_request(client, "skills/list", {}))
    skills = listing.get("skills") or []
    REPORT_STATE["skills"][s] = [sk.get("frontmatter", {}).get("name") for sk in skills]
    REPORT.skills[s] = skills

    if not has_server_info_raw(listing):
        REPORT.record("E1", s, "_meta.serverInfo on skills/list", False, observed="missing")

    ok = len(skills) == spec.skill_count
    REPORT.record("B1", s, f"skill count == {spec.skill_count}", ok, observed=str(len(skills)))

    entry_problems: list[str] = []
    for sk in skills:
        uri = sk.get("uri") or ""
        fm = sk.get("frontmatter") or {}
        res = sk.get("resources")
        name = fm.get("name") or ""
        problems = []
        if not uri:
            problems.append("uri missing")
        if not name:
            problems.append("frontmatter.name missing")
        if not (fm.get("description") or "").strip():
            problems.append("frontmatter.description missing")
        if not isinstance(res, list) or not any(r.get("uri") == uri for r in res):
            problems.append("manifest lacks its SKILL.md")
        if not uri.startswith("skill://") or not uri.endswith("/SKILL.md"):
            problems.append(f"bad skill uri {uri!r}")
        if problems:
            entry_problems.append(f"{uri or '<no uri>'}: {', '.join(problems)}")
    REPORT.record(
        "B2",
        s,
        "skill manifest entries complete",
        not entry_problems,
        observed="all complete" if not entry_problems else "; ".join(entry_problems),
    )

    # B3 + B4: read every listed file, verify frontmatter and digest/size
    fm_problems: list[str] = []
    digest_problems: list[str] = []
    files_checked = 0
    for sk in skills:
        name = (sk.get("frontmatter") or {}).get("name") or ""
        res = sk.get("resources")
        if not isinstance(res, list):
            digest_problems.append(f"{name}: manifest is not a static list")
            continue
        for entry in res:
            uri = entry.get("uri") or ""
            try:
                read = await call(f"{s} read {uri}", client.read_resource(uri))
                body = resource_bytes(read.contents[0])
            except Exception as exc:
                digest_problems.append(f"{uri}: read failed: {type(exc).__name__}: {exc}")
                continue
            files_checked += 1
            if uri.endswith("/SKILL.md"):
                collect_text(f"{s} skill {uri}", body.decode("utf-8", "replace"), skill_text=True)
            if not has_server_info(read):
                REPORT.record("E1", s, f"_meta.serverInfo on read {uri}", False, observed="missing")
            if uri.endswith("/SKILL.md"):
                text = body.decode("utf-8", "replace")
                fm = split_frontmatter(text)
                if fm is None:
                    fm_problems.append(f"{uri}: no leading YAML frontmatter")
                elif fm.get("name") != name:
                    fm_problems.append(f"{uri}: frontmatter name {fm.get('name')!r} != {name!r}")
            digest = entry.get("digest") or ""
            expected_digest = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
            actual = hashlib.sha256(body).hexdigest()
            if not expected_digest or actual != expected_digest:
                digest_problems.append(f"{uri}: digest advertised={digest} actual=sha256:{actual}")
            if int(entry.get("size", -1)) != len(body):
                digest_problems.append(
                    f"{uri}: size advertised={entry.get('size')} actual={len(body)}"
                )
    REPORT.record(
        "B3",
        s,
        "SKILL.md frontmatter name matches skill",
        not fm_problems,
        observed=f"{files_checked} files read" if not fm_problems else "; ".join(fm_problems),
    )
    REPORT.record(
        "B4",
        s,
        "manifest digest+size match served bytes",
        not digest_problems,
        observed=f"{files_checked} files verified"
        if not digest_problems
        else "; ".join(digest_problems),
    )
    if digest_problems:
        REPORT.digest_mismatches.extend(f"{s}: {p}" for p in digest_problems)
    REPORT_STATE["manifests"][s] = files_checked

    # B5: skills/get parity
    parity: list[str] = []
    for sk in skills:
        uri = sk.get("uri") or ""
        got = await call(f"{s} skills/get {uri}", raw_request(client, "skills/get", {"uri": uri}))
        if not has_server_info_raw(got):
            REPORT.record(
                "E1", s, f"_meta.serverInfo on skills/get {uri}", False, observed="missing"
            )
        if got.get("skill") != sk:
            parity.append(uri)
    REPORT.record(
        "B5",
        s,
        "skills/get equals skills/list entry",
        not parity,
        observed="identical" if not parity else f"differs: {parity}",
    )

    # B6: bogus skills/get -> -32602
    try:
        await call(
            f"{s} skills/get bogus",
            raw_request(client, "skills/get", {"uri": "skill://nope/SKILL.md"}),
        )
        REPORT.fail("B6", s, "skills/get bogus -> -32602", "no error raised")
    except Exception as exc:
        code = getattr(exc, "code", None)
        REPORT.record(
            "B6",
            s,
            "skills/get bogus -> -32602",
            code == types.INVALID_PARAMS,
            observed=f"code={code} msg={str(exc)[:120]}",
        )

    # B7: bogus resources/read -> -32602 and the connection survives
    try:
        await call(f"{s} read bogus", client.read_resource("skill://nope/SKILL.md"))
        REPORT.fail("B7", s, "resources/read bogus -> -32602", "no error raised")
    except Exception as exc:
        code = getattr(exc, "code", None)
        REPORT.record(
            "B7",
            s,
            "resources/read bogus -> -32602",
            code == types.INVALID_PARAMS,
            observed=f"code={code} msg={str(exc)[:120]}",
        )
    health = await call(f"{s} tools/list after bogus reads", client.list_tools())
    REPORT.record(
        "B7b",
        s,
        "session healthy after bogus reads",
        len(health.tools) == spec.tool_count,
        observed=str(len(health.tools)),
    )


def has_server_info_raw(payload: dict[str, Any]) -> bool:
    meta = payload.get("_meta") or {}
    info = meta.get("io.modelcontextprotocol/serverInfo")
    return isinstance(info, dict) and bool(info.get("name"))


# --------------------------------------------------------------------------- #
# C. Error paths / robustness
# --------------------------------------------------------------------------- #


async def section_c(spec: ServerSpec) -> None:
    s = spec.key
    url = f"http://127.0.0.1:{spec.port}/mcp"
    async with Client(
        url, mode="auto", extensions=EXTENSIONS, read_timeout_seconds=CALL_TIMEOUT
    ) as client:
        # C1 unknown tool -> tool-level error, never a successful result.
        try:
            res = await call(
                f"{s} call unknown tool", client.call_tool("this_tool_does_not_exist", {})
            )
            text = " ".join(c.text for c in res.content if isinstance(c, types.TextContent))
            REPORT.record(
                "C1",
                s,
                "unknown tool -> is_error=True",
                res.is_error is True,
                observed=f"is_error={res.is_error} text={text[:160]!r}",
            )
        except Exception as exc:
            REPORT.fail(
                "C1",
                s,
                "unknown tool -> is_error=True",
                f"raised {type(exc).__name__}: {str(exc)[:160]}",
            )

        # C2 missing required args -> is_error=True.
        try:
            res = await call(f"{s} call missing args", client.call_tool(spec.strict_tool, {}))
            text = " ".join(c.text for c in res.content if isinstance(c, types.TextContent))
            REPORT.record(
                "C2",
                s,
                "missing required args -> is_error=True",
                res.is_error is True,
                observed=f"is_error={res.is_error} text={text[:200]!r}",
            )
        except Exception as exc:
            REPORT.fail(
                "C2",
                s,
                "missing required args -> is_error=True",
                f"raised {type(exc).__name__}: {str(exc)[:160]}",
            )

        # C3 wrong-typed arg -> is_error=True; coder must name the offending field.
        wrong = {"job_id": 12345} if s == "coder" else {"repo_root": ["not", "a", "path"]}
        try:
            res = await call(f"{s} call wrong type", client.call_tool(spec.strict_tool, wrong))
            text = " ".join(c.text for c in res.content if isinstance(c, types.TextContent))
            ok = res.is_error is True
            if s == "coder":
                ok = ok and "job_id must be a string" in text
            title = (
                "wrong-typed job_id -> is_error=True naming the field"
                if s == "coder"
                else "wrong-typed arg -> is_error=True"
            )
            REPORT.record(
                "C3", s, title, ok, observed=f"is_error={res.is_error} text={text[:200]!r}"
            )
        except Exception as exc:
            REPORT.fail(
                "C3",
                s,
                "wrong-typed arg -> is_error=True",
                f"raised {type(exc).__name__}: {str(exc)[:160]}",
            )

        # C4 health probe after the three error paths
        try:
            res = await call(
                f"{s} probe {spec.probe_tool}", client.call_tool(spec.probe_tool, spec.probe_args)
            )
            ok = not res.is_error
            REPORT.record(
                "C4",
                s,
                "session healthy after error paths",
                ok,
                observed=f"is_error={res.is_error} structured={res.structured_content is not None}",
            )
            REPORT_STATE.setdefault("structured", {})[s] = res.structured_content is not None
            text = " ".join(c.text for c in res.content if isinstance(c, types.TextContent))
            REPORT_STATE.setdefault("tool_text", []).append((s, spec.probe_tool, text))
        except Exception as exc:
            REPORT.record(
                "C4",
                s,
                "session healthy after error paths",
                False,
                observed=f"{type(exc).__name__}: {str(exc)[:200]}",
            )


# --------------------------------------------------------------------------- #
# D. Legacy era
# --------------------------------------------------------------------------- #


async def section_d_legacy(spec: ServerSpec) -> None:
    s = spec.key
    url = f"http://127.0.0.1:{spec.port}/mcp"
    try:
        async with Client(url, mode="legacy", read_timeout_seconds=CALL_TIMEOUT) as client:
            ver = client.protocol_version
            ok_ver = isinstance(ver, str) and ver.startswith("2025-")
            REPORT.record("D1", s, "legacy protocol version (2025-era)", ok_ver, observed=ver)

            tools = await call(f"{s} legacy tools/list", client.list_tools())
            ok_tools = len(tools.tools) == spec.tool_count
            REPORT.record(
                "D1b", s, "legacy tools/list works", ok_tools, observed=str(len(tools.tools))
            )

            res = await call(
                f"{s} legacy call {spec.probe_tool}",
                client.call_tool(spec.probe_tool, spec.probe_args),
            )
            ok_call = not res.is_error
            REPORT.record(
                "D1c",
                s,
                "legacy read-only tool call works",
                ok_call,
                observed=f"is_error={res.is_error}",
            )
            REPORT_STATE.setdefault("structured_legacy", {})[s] = res.structured_content is not None

            try:
                await call(f"{s} legacy skills/list", raw_request(client, "skills/list", {}))
                REPORT.fail("D2", s, "legacy skills/list -> -32601", "succeeded unexpectedly")
            except Exception as exc:
                code = getattr(exc, "code", None)
                REPORT.record(
                    "D2",
                    s,
                    "legacy skills/list -> -32601",
                    code == types.METHOD_NOT_FOUND,
                    observed=f"code={code} msg={str(exc)[:120]}",
                )
    except Exception as exc:
        REPORT.record(
            "D1", s, "legacy connection", False, observed=f"{type(exc).__name__}: {str(exc)[:240]}"
        )


# --------------------------------------------------------------------------- #
# D3. Concurrency
# --------------------------------------------------------------------------- #


async def concurrent_client(spec: ServerSpec, idx: int) -> dict[str, Any]:
    url = f"http://127.0.0.1:{spec.port}/mcp"
    async with Client(
        url, mode="auto", extensions=EXTENSIONS, read_timeout_seconds=CALL_TIMEOUT
    ) as client:
        tools = await call(f"{spec.key}#{idx} tools/list", client.list_tools(), CALL_TIMEOUT)
        resources = await call(
            f"{spec.key}#{idx} resources/list", client.list_resources(), CALL_TIMEOUT
        )
        listing = await call(
            f"{spec.key}#{idx} skills/list", raw_request(client, "skills/list", {}), CALL_TIMEOUT
        )
        return {
            "port": spec.port,
            "server": getattr(client.server_info, "name", None),
            "tools": [t.name for t in tools.tools],
            "resources": [r.uri for r in resources.resources],
            "skills": [sk.get("uri") for sk in listing.get("skills") or []],
        }


async def section_d_concurrency() -> None:
    jobs = [concurrent_client(spec, i) for spec in SERVERS for i in range(3)]
    results = await asyncio.gather(*jobs, return_exceptions=True)
    failures: list[str] = []
    by_port: dict[int, list[dict[str, Any]]] = {}
    for spec, res in zip([s for s in SERVERS for _ in range(3)], results, strict=True):
        if isinstance(res, BaseException):
            failures.append(f"{spec.key}: {type(res).__name__}: {res}")
            continue
        by_port.setdefault(spec.port, []).append(res)
        if res["server"] != spec.server_name:
            failures.append(f"{spec.key}: serverInfo {res['server']!r} != {spec.server_name!r}")
        if len(res["tools"]) != spec.tool_count:
            failures.append(f"{spec.key}: {len(res['tools'])} tools")
        expected_skills = sorted(REPORT_STATE.get("skills", {}).get(spec.key, []))
        got_skills = sorted((u or "").split("/")[2] for u in res["skills"] if u)
        if got_skills != expected_skills:
            failures.append(f"{spec.key}: skill set {got_skills} != {expected_skills}")
        expected_uris = sorted((u or "") for u in res["resources"])
        if not expected_uris:
            failures.append(f"{spec.key}: resources/list empty")
        # cross-talk: every resource URI must belong to a skill this server serves
        for uri in expected_uris:
            if uri.split("/")[2] not in expected_skills:
                failures.append(f"{spec.key}: foreign resource {uri}")

    for spec in SERVERS:
        conns = by_port.get(spec.port, [])
        ok = len(conns) == 3 and not [f for f in failures if f.startswith(spec.key)]
        REPORT.record(
            "D3",
            spec.key,
            "3 concurrent modern clients, no cross-talk",
            ok,
            observed=f"{len(conns)}/3 ok"
            if ok
            else "; ".join(f for f in failures if f.startswith(spec.key))[:400],
        )


# --------------------------------------------------------------------------- #
# E. Output hygiene
# --------------------------------------------------------------------------- #

ABSOLUTE_PATH = re.compile(r"/home/[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]*")


def scan_paths(label: str, text: str, *, skill_text: bool) -> None:
    for match in ABSOLUTE_PATH.findall(text or ""):
        REPORT.path_hits.append(
            {"where": label, "path": match, "kind": "skill-text" if skill_text else "payload"}
        )


async def section_e(spec: ServerSpec) -> None:
    s = spec.key
    # E1 coverage on resources/list
    url = f"http://127.0.0.1:{spec.port}/mcp"
    async with Client(
        url, mode="auto", extensions=EXTENSIONS, read_timeout_seconds=CALL_TIMEOUT
    ) as client:
        res = await call(f"{s} resources/list", client.list_resources())
        REPORT.record(
            "E1b",
            s,
            "_meta.serverInfo on resources/list",
            has_server_info(res),
            observed=str(list(meta_of(res).keys())),
        )
        for r in res.resources:
            scan_paths(
                f"{s} resource-meta",
                json.dumps(r.model_dump(mode="json"), default=str),
                skill_text=False,
            )

        # E2: at least one tool on this server returns structured content (modern era)
        probe = await call(
            f"{s} probe {spec.probe_tool}", client.call_tool(spec.probe_tool, spec.probe_args)
        )
        REPORT_STATE.setdefault("structured", {})[s] = probe.structured_content is not None
        REPORT.record(
            "E2",
            s,
            "structured_content non-null on one tool",
            probe.structured_content is not None,
            observed=f"tool={spec.probe_tool} is_error={probe.is_error}",
        )
        REPORT.record(
            "E1c",
            s,
            "_meta.serverInfo on tools/call",
            has_server_info(probe),
            observed=str(list(meta_of(probe).keys())),
        )
        collect_text(
            f"{s} tool-result {spec.probe_tool}",
            json.dumps(
                {
                    "content": [c.model_dump(mode="json") for c in probe.content],
                    "structured": probe.structured_content,
                },
                default=str,
            ),
        )


# --------------------------------------------------------------------------- #
# Tasks extension round trip (task-enabled tools only on secretary)
# --------------------------------------------------------------------------- #


async def section_tasks() -> None:
    spec = BY_KEY["secretary"]
    url = f"http://127.0.0.1:{spec.port}/mcp"
    args = {"repo_root": str(WORK_ROOT)}
    async with Client(
        url, mode="auto", extensions=EXTENSIONS, read_timeout_seconds=CALL_TIMEOUT
    ) as client:
        res = await call(
            "secretary task-call secretary_codebase_report",
            client.call_tool("secretary_codebase_report", args),
        )
        REPORT.record(
            "T1",
            "secretary",
            "task-enabled tool resolves via tasks/get",
            res.structured_content is not None and not res.is_error,
            observed=f"is_error={res.is_error} structured={res.structured_content is not None}",
        )

        # Wire-level view: the task handle itself must still carry _meta.serverInfo.
        raw = await call(
            "secretary raw tools/call task handle",
            raw_request(
                client, "tools/call", {"name": "secretary_codebase_report", "arguments": args}
            ),
        )
        REPORT.record(
            "T1b",
            "secretary",
            "task handle carries _meta.serverInfo",
            has_server_info_raw(raw),
            observed=f"resultType={raw.get('resultType')!r} "
            f"meta={list((raw.get('_meta') or {}).keys())}",
        )
        if not (res.meta or {}).get("io.modelcontextprotocol/serverInfo"):
            REPORT.notes.append(
                "TasksClient (client side) rebuilds the resolved CallToolResult from the "
                "stored payload, dropping _meta.io.modelcontextprotocol/serverInfo; the "
                "server's tools/call handle and synchronous path both carry it, so this "
                "is a client-companion limitation, not a server violation."
            )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


async def run_modern(spec: ServerSpec) -> None:
    url = f"http://127.0.0.1:{spec.port}/mcp"
    try:
        async with Client(
            url, mode="auto", extensions=EXTENSIONS, read_timeout_seconds=CALL_TIMEOUT
        ) as client:
            await section_a(client, spec)
            await section_b(client, spec)
    except Exception:
        REPORT.record(
            "A0",
            spec.key,
            "modern connection",
            False,
            observed=traceback.format_exc(limit=3)[-800:],
        )


async def guarded(section: str, spec_key: str, coro) -> None:
    """Run one matrix section; a crash is a recorded failure, never an abort."""
    try:
        await coro
    except Exception:
        REPORT.record(
            section,
            spec_key,
            "section crashed",
            False,
            observed=traceback.format_exc(limit=5)[-700:],
        )


def report_payload(exit_code: int) -> dict[str, Any]:
    """Machine-readable rendering of everything the suite observed."""
    passed = sum(1 for c in REPORT.checks if c.ok)
    return {
        "suite": "protocol",
        "generated_at": datetime.now(UTC).isoformat(),
        "mcp_protocol": MODERN,
        "work_root": str(WORK_ROOT),
        "servers": {
            s.key: {"port": s.port, "url": f"http://127.0.0.1:{s.port}/mcp"} for s in SERVERS
        },
        "summary": {
            "total": len(REPORT.checks),
            "passed": passed,
            "failed": len(REPORT.checks) - passed,
            "exit_code": exit_code,
        },
        "checks": [asdict(c) for c in REPORT.checks],
        "timings": [{"label": label, "seconds": round(secs, 3)} for label, secs in REPORT.timings],
        "skills": REPORT.skills,
        "digest_mismatches": REPORT.digest_mismatches,
        "path_hits": REPORT.path_hits,
        "notes": REPORT.notes,
    }


async def main(ports: dict[str, int], json_path: str | None) -> int:
    global SERVERS, BY_KEY
    SERVERS = build_servers(ports)
    BY_KEY = {s.key: s for s in SERVERS}

    print("=" * 78)
    print("ninja-mcp live MCP protocol battle suite")
    print(f"protocol={MODERN}  " + "  ".join(f"{s.key}:{s.port}" for s in SERVERS))
    print("=" * 78)

    await asyncio.gather(*(guarded("A", s.key, run_modern(s)) for s in SERVERS))
    await asyncio.gather(*(guarded("E", s.key, section_e(s)) for s in SERVERS))
    await asyncio.gather(*(guarded("C", k, section_c(BY_KEY[k])) for k in ("coder", "agent")))
    await asyncio.gather(*(guarded("D", s.key, section_d_legacy(s)) for s in SERVERS))
    await guarded("D3", "all", section_d_concurrency())
    await guarded("T1", "secretary", section_tasks())

    # ---------------- per-assertion output ---------------- #
    print("\n--- ASSERTIONS (verbatim) ---")
    for check in REPORT.checks:
        status = "PASS" if check.ok else "FAIL"
        line = f"[{status}] {check.section:<3} {check.server:<10} {check.title}"
        if check.ok:
            line += f"  (observed: {check.observed})"
        else:
            line += f"\n        observed: {check.observed}"
            if check.failure:
                line += f"\n        failure:  {check.failure}"
        print(line)

    # ---------------- summary table ---------------- #
    print("\n--- SUMMARY MATRIX ---")
    sections = [
        "A1",
        "A2",
        "A3",
        "A4",
        "A5",
        "A6",
        "A7",
        "A8",
        "B1",
        "B2",
        "B3",
        "B4",
        "B5",
        "B6",
        "B7",
        "B7b",
        "C1",
        "C2",
        "C3",
        "C4",
        "D1",
        "D1b",
        "D1c",
        "D2",
        "D3",
        "E1",
        "E1b",
        "E1c",
        "E2",
        "T1",
    ]
    header = f"{'check':<6}" + "".join(f"{s.key:^13}" for s in SERVERS)
    print(header)
    print("-" * len(header))
    for sec in sections:
        cells = []
        for srv in SERVERS:
            rel = [c for c in REPORT.checks if c.section == sec and c.server == srv.key]
            if not rel:
                cells.append(
                    "n/a" if sec.startswith("C") and srv.key not in ("coder", "agent") else "—"
                )
            elif all(c.ok for c in rel):
                cells.append("PASS")
            else:
                cells.append(f"FAIL({sum(not c.ok for c in rel)})")
        print(f"{sec:<6}" + "".join(f"{c:^13}" for c in cells))

    # ---------------- failures verbatim ---------------- #
    fails = [c for c in REPORT.checks if not c.ok]
    print(f"\n--- FAILURES (n={len(fails)}) ---")
    if not fails:
        print("none")
    for c in fails:
        print(f"{c.section} {c.server}: {c.title}")
        print(f"  observed: {c.observed}")
        if c.failure:
            print(f"  failure:  {c.failure}")

    # ---------------- slowest calls ---------------- #
    print("\n--- SLOWEST 5 CALLS ---")
    for label, secs in sorted(REPORT.timings, key=lambda kv: kv[1], reverse=True)[:5]:
        print(f"{secs:8.3f}s  {label}")

    # ---------------- skill inventory ---------------- #
    print("\n--- SKILL INVENTORY ---")
    for spec in SERVERS:
        skills = REPORT.skills.get(spec.key, [])
        print(
            f"{spec.key} ({spec.server_name}): {len(skills)} skills, "
            f"{REPORT_STATE['manifests'].get(spec.key, 0)} files digest-verified"
        )
        for sk in skills:
            fm = sk.get("frontmatter") or {}
            res = sk.get("resources") or []
            size = sum(int(r.get("size", 0)) for r in res)
            print(f"  - {fm.get('name')}  uri={sk.get('uri')}  files={len(res)}  bytes={size}")
    print("digest mismatches:", "none" if not REPORT.digest_mismatches else "")
    for m in REPORT.digest_mismatches:
        print("  !", m)

    # ---------------- path leakage ---------------- #
    print("\n--- PATH LEAKAGE SCAN ---")
    for label, text, skill_text in REPORT_STATE["text"]:
        scan_paths(label, text, skill_text=skill_text)
    skill_hits = [h for h in REPORT.path_hits if h["kind"] == "skill-text"]
    payload_hits = [h for h in REPORT.path_hits if h["kind"] != "skill-text"]
    print(f"skill text hits: {len(skill_hits)} (informational)")
    for h in sorted({(x["where"], x["path"]) for x in skill_hits})[:20]:
        print("  ", h[0], "->", h[1])
    print(f"non-skill payload hits: {len(payload_hits)}")
    for h in payload_hits[:10]:
        print("  !", h["where"], "->", h["path"])

    # ---------------- structured content ---------------- #
    print("\n--- STRUCTURED CONTENT ---")
    for spec in SERVERS:
        print(
            f"{spec.key}: modern={REPORT_STATE.get('structured', {}).get(spec.key)} "
            f"legacy={REPORT_STATE.get('structured_legacy', {}).get(spec.key)}"
        )

    error_checks = [c for c in REPORT.checks if c.section in {"C1", "C2", "C3"}]
    honored = sum(1 for c in error_checks if c.ok)
    REPORT.notes.append(
        "Tool-level validation failures (unknown tool, missing required args, wrong-typed "
        f"args): {honored}/{len(error_checks)} probes reported is_error=True."
    )
    REPORT.notes.append(
        "Every check above reports the value observed on this run; nothing in the suite "
        "asserts a package version."
    )

    print("\n--- NOTES ---")
    for n in REPORT.notes:
        print(" -", n)
    passed = len(REPORT.checks) - len(fails)
    print(f"\nTotal checks: {len(REPORT.checks)}  passed: {passed}  failed: {len(fails)}")

    exit_code = 0 if not fails else 1
    if json_path:
        payload = report_payload(exit_code)
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"JSON report written to {json_path}")
    return exit_code


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Live protocol conformance suite for running ninja-mcp daemons.",
    )
    parser.add_argument(
        "--ports",
        metavar="MODULE=PORT,...",
        help="Override daemon ports, e.g. coder=8100,agent=8106 "
        "(defaults: NINJA_CODER_PORT etc., then 8100/8101/8106/8107)",
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        help="Write a machine-readable JSON report to PATH",
    )
    args = parser.parse_args(argv)
    return asyncio.run(main(resolve_ports(args.ports), args.json))


if __name__ == "__main__":
    sys.exit(cli())
