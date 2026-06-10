"""Advanced TUI configurator for Ninja MCP.

Features:
- Gradient NINJA logo with ANSI art
- Tabbed interface: Overview, API Keys, Models, Daemons, IDE, Settings
- Lazy model loading with debounce (no subprocess-per-keystroke)
- Version display and update check
- Secure key storage via SecretStore

Built with Textual + Rich.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    ListItem,
    ListView,
    Static,
    TabbedContent,
    TabPane,
)

from ninja_common.config_manager import ConfigManager
from ninja_config.config_shared import (
    API_KEYS,
    DAEMON_CONFIG,
    OPERATOR_MAP,
    detect_ides,
    detect_tools,
    mask_key,
    register_claude_mcp,
)
from ninja_config.secrets_store import (
    SecretStoreUnavailable,
    default_store,
)

from ninja_common.defaults import (
    PERPLEXITY_MODELS,
    PROVIDER_MODELS,
)


def _ninja_version() -> str:
    try:
        return pkg_version("ninja-mcp")
    except PackageNotFoundError:
        return "dev"


def _gradient_logo() -> Text:
    colors = [
        "#88c0d0", "#81a1c1", "#8fbcbb", "#5e81ac",
        "#88c0d0", "#81a1c1", "#8fbcbb", "#5e81ac",
        "#88c0d0", "#81a1c1", "#8fbcbb", "#5e81ac",
    ]
    lines = [
        " ███▀▀███  ▀███▀  ▀████▀  ████▀▀████",
        " █▀    ▀█    █      █     █▀      ▀█",
        " █      █    █      █     █        █",
        " █     ▄▀    █      █     █▄      ▄█",
        " ███▀▀▀     ▄█▄    ▄████▄  ███▀▀████",
    ]
    logo = Text()
    for row_idx, line in enumerate(lines):
        col = 0
        for ch in line:
            if ch != " ":
                ci = min(col * len(colors) // max(len(line), 1), len(colors) - 1)
                logo.append(ch, style=colors[ci])
            else:
                logo.append(" ")
            col += 1
        if row_idx < len(lines) - 1:
            logo.append("\n")
    return logo


class AppNotification(Message):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class NinjaConfigApp(App):
    TITLE = "Ninja MCP"
    SUB_TITLE = f"v{_ninja_version()} — Configuration"

    CSS = """
    Screen { background: #2e3440; }
    Header { background: #3b4252; color: #eceff4; }
    Footer { background: #3b4252; color: #d8dee9; }
    TabbedContent { height: 1fr; }
    TabbedContent Tabs { background: #3b4252; }
    TabbedContent Tabs Tab { background: #3b4252; color: #d8dee9; }
    TabbedContent Tabs Tab.-active { background: #434c5e; color: #88c0d0; text-style: bold; }
    TabPane { padding: 1 2; background: #2e3440; }
    VerticalScroll { height: 1fr; }
    ListView { height: auto; max-height: 12; }
    Horizontal { height: auto; }
    Static { color: #d8dee9; }
    Label { color: #d8dee9; }
    Input { background: #3b4252; color: #eceff4; border: tall #434c5e; }
    Input:focus { border: tall #88c0d0; }
    Button { margin: 0 1; height: 3; min-height: 3; max-height: 3; padding: 0 2; }
    Button.-primary { background: #5e81ac; color: #eceff4; }
    Button.-primary:hover { background: #88c0d0; color: #2e3440; }
    Button.-default { background: #434c5e; color: #d8dee9; }
    Button.-default:hover { background: #4c566a; color: #eceff4; }
    Button.-error { background: #bf616a; color: #eceff4; }
    Button.-error:hover { background: #d08770; color: #2e3440; }
    Button.-success { background: #a3be8c; color: #2e3440; }
    Button.-success:hover { background: #8fbcbb; color: #2e3440; }
    #main-tabs { height: 1fr; }
    """

    BINDINGS: ClassVar[list] = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+r", "refresh", "Refresh"),
    ]

    def __init__(self, config_path: str | None = None) -> None:
        super().__init__()
        self.config_manager = ConfigManager(config_path)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with TabbedContent(id="main-tabs"):
            with TabPane("Overview"):
                with VerticalScroll():
                    yield Static(_gradient_logo())
                    yield Static("")
                    yield Static(f"  [bold #eceff4]Ninja MCP[/bold #eceff4]  [dim]v{_ninja_version()}[/dim]")
                    yield Static("")
                    yield Static("  [bold #88c0d0]── System ──────────────────────────[/bold #88c0d0]")
                    yield Static(self._system_status())
                    yield Static("")
                    yield Static("  [bold #88c0d0]── Configuration ────────────────────[/bold #88c0d0]")
                    yield Static(self._config_summary())
                    yield Static("")
                    yield Static("  [bold #88c0d0]── Quick Actions ───────────────────[/bold #88c0d0]")
                    yield Horizontal(
                        Button("Check Updates", variant="primary", id="btn-update"),
                        Button("Run Doctor", id="btn-doctor"),
                        Button("Show Config", id="btn-show-config"),
                    )

            with TabPane("API Keys"):
                with VerticalScroll():
                    yield Static("  [bold #88c0d0]API Key Management[/bold #88c0d0]")
                    yield Static("  [dim]Keys are stored via OS keyring → encrypted SQLite.[/dim]")
                    yield Static("")
                    yield ListView(id="api-key-list")
                    yield Static("")
                    yield Static("  [bold]Set / Update Key[/bold]")
                    yield Input(
                        placeholder="Select key above, then enter value...",
                        id="api-key-input",
                        password=True,
                    )
                    yield Horizontal(
                        Button("Save", variant="primary", id="btn-save-key"),
                        Button("Delete", variant="error", id="btn-delete-key"),
                    )

            with TabPane("Models"):
                with VerticalScroll():
                    yield Static("  [bold #88c0d0]Model Selection[/bold #88c0d0]")
                    yield Static("")
                    yield Static("  [bold #88c0d0]── Coder ────────────────────────────[/bold #88c0d0]")
                    yield Static("  Select model for each coder task type.")
                    yield Static("")
                    yield Static("  [bold]Quick[/bold] [dim](fast, simple tasks)[/dim]")
                    yield Static(self._current_model("NINJA_MODEL_QUICK", "opencode/glm-4.7-free"), id="lbl-quick")
                    yield Horizontal(
                        Button("OpenRouter", id="prov-quick-openrouter"),
                        Button("Z.ai", id="prov-quick-zai"),
                        Button("Google", id="prov-quick-google"),
                        Button("Anthropic", id="prov-quick-anthropic"),
                    )
                    yield ListView(id="list-quick")
                    yield Static("")
                    yield Static("  [bold]Sequential[/bold] [dim](complex, multi-step)[/dim]")
                    yield Static(self._current_model("NINJA_MODEL_SEQUENTIAL", "zai-coding-plan/glm-4.7"), id="lbl-sequential")
                    yield Horizontal(
                        Button("OpenRouter", id="prov-seq-openrouter"),
                        Button("Z.ai", id="prov-seq-zai"),
                        Button("Google", id="prov-seq-google"),
                        Button("Anthropic", id="prov-seq-anthropic"),
                    )
                    yield ListView(id="list-sequential")
                    yield Static("")
                    yield Static("  [bold]Parallel[/bold] [dim](high concurrency)[/dim]")
                    yield Static(self._current_model("NINJA_MODEL_PARALLEL", "opencode/glm-4.7-free"), id="lbl-parallel")
                    yield Horizontal(
                        Button("OpenRouter", id="prov-par-openrouter"),
                        Button("Z.ai", id="prov-par-zai"),
                        Button("Google", id="prov-par-google"),
                        Button("Anthropic", id="prov-par-anthropic"),
                    )
                    yield ListView(id="list-parallel")
                    yield Static("")
                    yield Static("  [bold #88c0d0]── Researcher ──────────────────────[/bold #88c0d0]")
                    yield Static(self._current_model("NINJA_RESEARCHER_MODEL", "sonar"), id="lbl-researcher")
                    yield Horizontal(
                        Button("Perplexity", id="prov-res-perplexity"),
                        Button("OpenRouter", id="prov-res-openrouter"),
                    )
                    yield ListView(id="list-researcher")
                    yield Static("")
                    yield Static("  [bold #88c0d0]── Secretary ──────────────────────[/bold #88c0d0]")
                    yield Static(self._current_model("NINJA_SECRETARY_MODEL", "opencode/glm-4.7-free"), id="lbl-secretary")
                    yield Horizontal(
                        Button("OpenRouter", id="prov-sec-openrouter"),
                        Button("Z.ai", id="prov-sec-zai"),
                        Button("Google", id="prov-sec-google"),
                        Button("Anthropic", id="prov-sec-anthropic"),
                    )
                    yield ListView(id="list-secretary")
                    yield Static("")
                    yield Static("  [bold]Custom Model ID[/bold]")
                    yield Input(placeholder="e.g. openrouter/qwen/qwen3-32b", id="custom-model-input")
                    yield Horizontal(
                        Button("Set Coder Quick", id="set-quick"),
                        Button("Set Coder Seq", id="set-seq"),
                        Button("Set Coder Par", id="set-par"),
                        Button("Set Researcher", id="set-res"),
                        Button("Set Secretary", id="set-sec"),
                    )

            with TabPane("Daemon"):
                with VerticalScroll():
                    yield Static("  [bold #88c0d0]Daemon Configuration[/bold #88c0d0]")
                    yield Static(self._daemon_status())
                    yield Static("")
                    yield Horizontal(
                        Button("Toggle Daemon", variant="primary", id="btn-toggle-daemon"),
                        Button("Restart Daemon", id="btn-restart-daemon"),
                    )
                    yield Static("")
                    yield Static("  [bold]Ports[/bold]")
                    yield Static(self._daemon_ports())
                    yield Static("")
                    yield Static("  [dim]Changes require daemon restart.[/dim]")

            with TabPane("IDE"):
                with VerticalScroll():
                    yield Static("  [bold #88c0d0]IDE Integration[/bold #88c0d0]")
                    yield Static("")
                    yield Static(self._ide_status())
                    yield Static("")
                    yield Static("  [bold]Actions[/bold]")
                    yield Button("Register Claude Code MCP", variant="primary", id="btn-claude-mcp")
                    yield Button("Register OpenCode MCP", id="btn-opencode-mcp")

            with TabPane("Settings"):
                with VerticalScroll():
                    yield Static("  [bold #88c0d0]Settings[/bold #88c0d0]")
                    yield Static("")
                    yield Static("  [bold]Operator[/bold]")
                    yield Static(self._operator_status())
                    yield Static("")
                    yield Static("  [bold]Detected Operators[/bold]")
                    yield Static(self._operator_buttons())
                    yield Static("")
                    yield Static("  [bold]Search Provider[/bold]")
                    yield Static(self._search_status())
                    yield Horizontal(
                        Button("DuckDuckGo", id="search-duckduckgo"),
                        Button("Serper", id="search-serper"),
                        Button("Perplexity", id="search-perplexity"),
                    )
                    yield Static("")
                    yield Static("  [bold #88c0d0]About[/bold #88c0d0]")
                    yield Static(f"  Version: {_ninja_version()}")
                    yield Static("  Config: ~/.ninja-mcp.env")
                    yield Static("  Secrets: OS keyring → encrypted SQLite")
                    yield Static("")
                    yield Button("Check for Updates", variant="primary", id="btn-update-settings")

        yield Footer()

    def on_mount(self) -> None:
        self._refresh_api_keys()
        self._populate_role_lists()

    ROLE_MAP: ClassVar[dict[str, tuple[str, str]]] = {
        "quick": ("NINJA_MODEL_QUICK", "opencode/glm-4.7-free"),
        "sequential": ("NINJA_MODEL_SEQUENTIAL", "zai-coding-plan/glm-4.7"),
        "parallel": ("NINJA_MODEL_PARALLEL", "opencode/glm-4.7-free"),
        "researcher": ("NINJA_RESEARCHER_MODEL", "sonar"),
        "secretary": ("NINJA_SECRETARY_MODEL", "opencode/glm-4.7-free"),
    }

    def _models_for_role(self, role: str, provider: str) -> list[tuple[str, str, str]]:
        if provider == "perplexity":
            return list(PERPLEXITY_MODELS)
        if provider in PROVIDER_MODELS:
            return list(PROVIDER_MODELS[provider])
        return list(PROVIDER_MODELS.get("openrouter", []))

    def _populate_role_lists(self) -> None:
        cfg = self.config_manager.list_all()
        for role, (env_var, default) in self.ROLE_MAP.items():
            lv_id = f"list-{role}"
            try:
                lv = self.query_one(f"#{lv_id}", ListView)
            except Exception:
                continue
            lv.clear()
            cur = cfg.get(env_var, default)
            provider = self._guess_provider(cur)
            models = self._models_for_role(role, provider)
            for mid, name, desc in models:
                marker = " ◄" if mid == cur else ""
                item = ListItem(Static(f"[bold]{name}[/bold]{marker}\n  [dim]{mid} — {desc}[/dim]"))
                item.model_id = mid
                item.role = role
                item.env_var = env_var
                lv.append(item)

    def _populate_role_for_provider(self, role: str, provider: str) -> None:
        cfg = self.config_manager.list_all()
        env_var, default = self.ROLE_MAP[role]
        lv_id = f"list-{role}"
        try:
            lv = self.query_one(f"#{lv_id}", ListView)
        except Exception:
            return
        lv.clear()
        cur = cfg.get(env_var, default)
        models = self._models_for_role(role, provider)
        for mid, name, desc in models:
            marker = " ◄" if mid == cur else ""
            item = ListItem(Static(f"[bold]{name}[/bold]{marker}\n  [dim]{mid} — {desc}[/dim]"))
            item.model_id = mid
            item.role = role
            item.env_var = env_var
            lv.append(item)

    def _guess_provider(self, model_id: str) -> str:
        if not model_id:
            return "openrouter"
        m = model_id.lower()
        if m.startswith("sonar") or "perplexity" in m:
            return "perplexity"
        if m.startswith("gemini") or "google/" in m:
            return "google"
        if m.startswith("claude") or "anthropic/" in m:
            return "anthropic"
        if "zai" in m or "glm" in m:
            return "zai"
        return "openrouter"

    # ── helpers ──────────────────────────────────────────────────────────

    def _system_status(self) -> str:
        tools = detect_tools()
        ides = detect_ides()
        return (
            f"  Tools: {', '.join(tools.keys()) if tools else '[dim]none[/dim]'}\n"
            f"  IDEs:  {', '.join(ides.keys()) if ides else '[dim]none[/dim]'}\n"
            f"  OS:    {os.uname().sysname} {os.uname().machine}"
        )

    def _config_summary(self) -> str:
        cfg = self.config_manager.list_all()
        op = cfg.get("NINJA_CODE_BIN", "not set")
        daemon = cfg.get("NINJA_ENABLE_DAEMON", "true")
        keys = sum(1 for k in API_KEYS if cfg.get(k.env_var) or os.environ.get(k.env_var))
        return (
            f"  Operator: {op}\n"
            f"  Daemon:   {'enabled' if daemon == 'true' else 'disabled'}\n"
            f"  API Keys: {keys}/{len(API_KEYS)} configured"
        )

    def _current_model(self, env_var: str, default: str) -> str:
        cfg = self.config_manager.list_all()
        cur = cfg.get(env_var, default)
        return f"  Current: [#a3be8c]{cur}[/#a3be8c]"

    def _daemon_status(self) -> str:
        cfg = self.config_manager.list_all()
        on = cfg.get("NINJA_ENABLE_DAEMON", "true") == "true"
        return f"  Status: {'[#a3be8c]enabled[/#a3be8c]' if on else '[#ebcb8b]disabled[/#ebcb8b]'}"

    def _daemon_ports(self) -> str:
        cfg = self.config_manager.list_all()
        skip = {"NINJA_ENABLE_DAEMON", "NINJA_PROMPTS_PORT", "NINJA_RESOURCES_PORT"}
        lines = []
        for key, val in DAEMON_CONFIG.items():
            if key in skip:
                continue
            cur = cfg.get(key, val)
            name = key.replace("NINJA_", "").replace("_PORT", "").title()
            lines.append(f"  {name:12} {cur}")
        return "\n".join(lines)

    def _ide_status(self) -> str:
        from ninja_config.config_shared import IDES as IDE_DEFS
        ides = detect_ides()
        if not ides:
            return "  [dim]No IDE configurations detected.[/dim]"
        lines = []
        for ide_id, path in ides.items():
            name = ide_id.title()
            for d in IDE_DEFS:
                if d.id == ide_id:
                    name = d.display_name
                    break
            lines.append(f"  [#a3be8c]✓[/#a3be8c] {name}: {path}")
        return "\n".join(lines)

    def _operator_status(self) -> str:
        cfg = self.config_manager.list_all()
        return f"  Current: [bold]{cfg.get('NINJA_CODE_BIN', 'not set')}[/bold]"

    def _operator_buttons(self) -> str:
        tools = detect_tools()
        if not tools:
            return "  [dim]No operators detected.[/dim]"
        lines = []
        for tid in tools:
            op = OPERATOR_MAP.get(tid)
            if op:
                lines.append(f"  [bold]{op.display_name}[/bold] — {op.description}")
        return "\n".join(lines)

    def _search_status(self) -> str:
        cfg = self.config_manager.list_all()
        return f"  Current: [bold]{cfg.get('NINJA_SEARCH_PROVIDER', 'duckduckgo')}[/bold]"

    # ── API Keys ─────────────────────────────────────────────────────────

    def _refresh_api_keys(self) -> None:
        lv = self.query_one("#api-key-list", ListView)
        lv.clear()
        cfg = self.config_manager.list_all()
        for k in API_KEYS:
            val = cfg.get(k.env_var) or os.environ.get(k.env_var, "")
            icon = "[#a3be8c]✓[/#a3be8c]" if val else "[dim]○[/dim]"
            masked = mask_key(val) if val else "[dim]not set[/dim]"
            item = ListItem(
                Static(f"{icon} [bold]{k.display_name}[/bold]  {masked}  [dim]({k.module})[/dim]")
            )
            item.env_var = k.env_var
            item.display_name = k.display_name
            lv.append(item)

    def _selected_api_key(self) -> tuple[str, str] | None:
        lv = self.query_one("#api-key-list", ListView)
        sel = lv.highlighted_item
        if sel and hasattr(sel, "env_var"):
            return sel.env_var, sel.display_name
        return None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if hasattr(event.item, "env_var"):
            inp = self.query_one("#api-key-input", Input)
            inp.placeholder = f"Enter {event.item.display_name} key..."

    # ── Event handlers ───────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""

        if bid in ("btn-update", "btn-update-settings"):
            self._check_update()
        elif bid == "btn-doctor":
            self.notify("Run 'ninja-config doctor' for diagnostics.", timeout=3)
        elif bid == "btn-show-config":
            self._show_config()
        elif bid == "btn-save-key":
            self._save_key()
        elif bid == "btn-delete-key":
            self._delete_key()
        elif bid == "btn-toggle-daemon":
            self._toggle_daemon()
        elif bid == "btn-restart-daemon":
            self.notify("Run 'ninja-daemon restart' to restart.", timeout=3)
        elif bid == "btn-claude-mcp":
            count = register_claude_mcp()
            self.notify(f"Claude Code MCP: {count}/3 servers registered.", timeout=3)
        elif bid == "btn-opencode-mcp":
            if shutil.which("opencode"):
                self.notify("OpenCode: use 'ninja-config configure' for setup.", timeout=3)
            else:
                self.notify("OpenCode CLI not found.", timeout=3)
        elif bid.startswith("set-"):
            self._set_custom_model(bid[4:])
        elif bid.startswith("prov-"):
            self._handle_provider_button(bid)
        elif bid.startswith("op-"):
            op_id = bid[3:]
            self.config_manager.set("NINJA_CODE_BIN", op_id)
            self.notify(f"Operator set to {op_id}.", timeout=3)
        elif bid == "search-duckduckgo":
            self.config_manager.set("NINJA_SEARCH_PROVIDER", "duckduckgo")
            self.notify("Search: DuckDuckGo", timeout=3)
        elif bid == "search-serper":
            self.config_manager.set("NINJA_SEARCH_PROVIDER", "serper")
            self.notify("Search: Serper", timeout=3)
        elif bid == "search-perplexity":
            self.config_manager.set("NINJA_SEARCH_PROVIDER", "perplexity")
            self.notify("Search: Perplexity", timeout=3)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if hasattr(event.item, "env_var") and hasattr(event.item, "model_id"):
            env_var = event.item.env_var
            model_id = event.item.model_id
            role = getattr(event.item, "role", "")
            self.config_manager.set(env_var, model_id)
            lbl_id = f"lbl-{role}"
            try:
                lbl = self.query_one(f"#{lbl_id}", Static)
                lbl.update(f"  Current: [#a3be8c]{model_id}[/#a3be8c]")
            except Exception:
                pass
            self._populate_role_lists()
            self.notify(f"Model set: {model_id}", timeout=3)
        elif hasattr(event.item, "env_var"):
            inp = self.query_one("#api-key-input", Input)
            inp.placeholder = f"Enter {event.item.display_name} key..."

    def _handle_provider_button(self, bid: str) -> None:
        ROLE_PREFIXES = {
            "prov-quick-": "quick",
            "prov-seq-": "sequential",
            "prov-par-": "parallel",
            "prov-res-": "researcher",
            "prov-sec-": "secretary",
        }
        for prefix, role in ROLE_PREFIXES.items():
            if bid.startswith(prefix):
                provider = bid[len(prefix):]
                self._populate_role_for_provider(role, provider)
                return

    def _set_custom_model(self, role_key: str) -> None:
        ROLE_KEY_MAP = {
            "quick": ("NINJA_MODEL_QUICK", "quick"),
            "seq": ("NINJA_MODEL_SEQUENTIAL", "sequential"),
            "par": ("NINJA_MODEL_PARALLEL", "parallel"),
            "res": ("NINJA_RESEARCHER_MODEL", "researcher"),
            "sec": ("NINJA_SECRETARY_MODEL", "secretary"),
        }
        if role_key not in ROLE_KEY_MAP:
            return
        env_var, role = ROLE_KEY_MAP[role_key]
        inp = self.query_one("#custom-model-input", Input)
        if not inp.value:
            self.notify("Enter a custom model ID first.", timeout=3)
            return
        self.config_manager.set(env_var, inp.value)
        try:
            lbl = self.query_one(f"#lbl-{role}", Static)
            lbl.update(f"  Current: [#a3be8c]{inp.value}[/#a3be8c]")
        except Exception:
            pass
        self._populate_role_lists()
        self.notify(f"{role.title()} model set: {inp.value}", timeout=3)
        inp.value = ""

    def on_app_notification(self, event: AppNotification) -> None:
        self.notify(event.text, timeout=4)

    # ── Actions ──────────────────────────────────────────────────────────

    def _check_update(self) -> None:
        try:
            result = subprocess.run(
                ["uv", "tool", "upgrade", "ninja-mcp", "--dry-run"],
                capture_output=True, text=True, check=False, timeout=15,
            )
            if "Would upgrade" in result.stdout or "upgraded" in result.stdout.lower():
                self.notify("Update available! Run: uv tool upgrade ninja-mcp", timeout=5)
            else:
                self.notify("Already up to date.", timeout=3)
        except Exception as e:
            self.notify(f"Check failed: {e}", timeout=4)

    def _show_config(self) -> None:
        cfg = self.config_manager.list_all()
        lines = [f"  {k} = {mask_key(v) if 'KEY' in k else v}" for k, v in sorted(cfg.items())]
        self.notify("\n".join(lines[:25]), timeout=8)

    def _save_key(self) -> None:
        inp = self.query_one("#api-key-input", Input)
        if not inp.value:
            return
        sel = self._selected_api_key()
        if not sel:
            self.notify("Select a key from the list first.", timeout=3)
            return
        env_var, display_name = sel
        try:
            store = default_store()
            store.set(env_var, inp.value)
            self.notify(f"✓ {display_name} saved to secure store.", timeout=3)
        except SecretStoreUnavailable:
            self.config_manager.set(env_var, inp.value)
            self.notify(f"✓ {display_name} saved (keyring unavailable).", timeout=3)
        except Exception as e:
            self.config_manager.set(env_var, inp.value)
            self.notify(f"⚠ {display_name} saved to config ({e}).", timeout=3)
        inp.value = ""
        self._refresh_api_keys()

    def _delete_key(self) -> None:
        sel = self._selected_api_key()
        if not sel:
            return
        env_var, display_name = sel
        try:
            store = default_store()
            store.delete(env_var)
        except Exception:
            pass
        self.config_manager.set(env_var, "")
        self.notify(f"✓ {display_name} removed.", timeout=3)
        self._refresh_api_keys()

    def _toggle_daemon(self) -> None:
        cfg = self.config_manager.list_all()
        cur = cfg.get("NINJA_ENABLE_DAEMON", "true")
        new = "false" if cur == "true" else "true"
        self.config_manager.set("NINJA_ENABLE_DAEMON", new)
        self.notify(f"Daemon {'enabled' if new == 'true' else 'disabled'}. Restart to apply.", timeout=3)

    def action_refresh(self) -> None:
        self._refresh_api_keys()
        self._populate_role_lists()
        self.notify("Refreshed.", timeout=2)


def run_modern_tui(config_path: str | None = None) -> int:
    app = NinjaConfigApp(config_path)
    app.run()
    return 0
