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
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from typing import TYPE_CHECKING, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import (
    Button,
    Collapsible,
    Footer,
    Header,
    Input,
    ListItem,
    ListView,
    Rule,
    Static,
    TabbedContent,
    TabPane,
)

from ninja_common.config_manager import ConfigManager
from ninja_common.defaults import (
    PERPLEXITY_MODELS,
    PROVIDER_MODELS,
)
from ninja_config.config_shared import (
    API_KEYS,
    DAEMON_CONFIG,
    OPERATOR_MAP,
    detect_ides,
    detect_tools,
    mask_key,
    register_claude_mcp,
)
from ninja_config.litellm import (
    read_litellm_config,
    write_litellm_config,
)
from ninja_config.model_selector import PROVIDER_DISPLAY_NAMES
from ninja_config.secrets_store import (
    SecretStore,
    SecretStoreUnavailable,
    default_store,
)
from ninja_config.settings_registry import SETTINGS, SettingDef
from ninja_config.ui.model_autocomplete import ModelRolePicker
from ninja_config.ui.model_cache import (
    cached_discover_providers,
    cached_get_provider_models,
    clear_model_cache,
)
from ninja_config.ui.theme import GRADIENT_FROST, gradient_text


if TYPE_CHECKING:
    from rich.text import Text


def _ninja_version() -> str:
    try:
        return pkg_version("ninja-mcp")
    except PackageNotFoundError:
        return "dev"


def _gradient_logo() -> Text:
    # Large block-letter NINJA (6 rows) — unambiguous brand mark.
    # Pure █ letterforms so it reads as NINJA in any monospace terminal
    # (the previous abstract █-art was misread as "PICO").
    # Colored with the Frost gradient (#88C0D0→#81A1C1→#8FBCBB→#5E81AC).
    lines = [
        "██     ██  █████  ██     ██      ███     ███",
        "███    ██    █    ███    ██       ██    ██ ██",
        "████   ██    █    ████   ██       ██   ██   ██",
        "██ ██  ██    █    ██ ██  ██       ██   █████████",
        "██  ██ ██    █    ██  ██ ██  ██   ██   ██     ██",
        "██   ████  █████  ██   ████   █████    ██     ██",
    ]
    return gradient_text("\n".join(lines), GRADIENT_FROST)


def section_header(title: str) -> Static:
    """Gradient section header (Frost gradient + rule-friendly text)."""
    return Static(gradient_text(f"── {title} ──"), classes="section-header")


class AppNotification(Message):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


def _mask(value: str) -> str:
    """Mask a secret value, showing only the last four characters when useful."""
    return f"••••{value[-4:]}" if len(value) > 4 else "••••"


class SecretsPanel(Vertical):
    """Reusable API-key management panel for the modern Textual configurator."""

    def __init__(self, store: SecretStore | None = None) -> None:
        super().__init__()
        self._store = store if store is not None else default_store()
        self._pending_set: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="secrets-error-banner")
        yield Static("Select a key to set or update.", id="secrets-input-label")
        yield Input(placeholder="API key value...", id="secrets-value-input", password=True)
        yield Button("Save", variant="primary", id="secrets-save-btn")
        for key_def in API_KEYS:
            yield self._make_secret_row(key_def.env_var)

    def _make_secret_row(self, name: str) -> Horizontal:
        try:
            value = self._store.get(name)
        except Exception:
            value = None

        if value:
            marker = "✓"
            action = "Update"
            preview = _mask(value)
        else:
            marker = "·"
            action = "Set"
            preview = "[dim]not set[/dim]"

        children = [
            Static(f"{marker} [bold]{name}[/bold]  {preview}"),
            Button(action, id=f"set-{name}"),
        ]
        if value:
            children.append(Button("Delete", variant="error", id=f"del-{name}"))
        return Horizontal(*children)

    def _error_banner(self) -> Static:
        return self.query_one("#secrets-error-banner", Static)

    def _show_error(self, message: str) -> None:
        banner = self._error_banner()
        banner.renderable = message
        banner.display = True

    def _do_save(self) -> None:
        if not self._pending_set:
            return

        inp = self.query_one("#secrets-value-input", Input)
        value = inp.value.strip()
        if not value:
            self._show_error("Enter a value before saving.")
            return

        try:
            self._store.set(self._pending_set, value)
        except SecretStoreUnavailable as exc:
            self._show_error(f"Secret store unavailable: {exc}")
            return
        except Exception as exc:
            self._show_error(f"Failed to save {self._pending_set}: {exc}")
            return

        saved_name = self._pending_set
        self._pending_set = None
        inp.value = ""
        self._error_banner().display = False
        self.app.notify(f"{saved_name} saved.", timeout=3)

    def _do_delete(self, name: str) -> None:
        banner = self._error_banner()
        confirm = f"CONFIRM_DELETE:{name}"
        if not str(getattr(banner, "renderable", "")).startswith(confirm):
            banner.renderable = f"{confirm} — press again"
            banner.display = True
            return

        try:
            self._store.delete(name)
        except Exception as exc:
            self._show_error(f"Failed to delete {name}: {exc}")
            return

        banner.display = False
        self.app.notify(f"{name} deleted.", timeout=3)


class ModelCard(ListItem):
    """Card-style model row: bordered, padded, with a current-model badge.

    Keeps the ``model_id`` / ``role`` / ``env_var`` attributes that
    ``on_list_view_selected`` relies on.
    """

    def __init__(
        self,
        name: str,
        model_id: str,
        description: str,
        role: str,
        env_var: str,
        current: bool = False,
    ) -> None:
        self.model_id = model_id
        self.role = role
        self.env_var = env_var
        badge = "[#a3be8c]✓ current[/#a3be8c]" if current else "[dim]○[/dim]"
        super().__init__(
            Static(f"[bold]{name}[/bold]  {badge}\n[dim]{model_id} — {description}[/dim]"),
            classes="model-card current" if current else "model-card",
        )


class NinjaConfigApp(App):
    TITLE = "Ninja MCP"
    SUB_TITLE = f"v{_ninja_version()} — Configuration"

    CSS_PATH = "ui/theme.tcss"

    BINDINGS: ClassVar[list] = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+r", "refresh", "Refresh"),
        Binding("/", "focus_search", "Search"),
        Binding("s", "save_current", "Save"),
        Binding("1", "goto_tab(0)", "Overview"),
        Binding("2", "goto_tab(1)", "Keys"),
        Binding("3", "goto_tab(2)", "Models"),
        Binding("4", "goto_tab(3)", "Daemon"),
        Binding("5", "goto_tab(4)", "IDE"),
        Binding("6", "goto_tab(5)", "Settings"),
        Binding("escape", "escape_focus", "Back", show=False),
    ]

    ROLE_MAP: ClassVar[dict[str, tuple[str, str]]] = {
        "quick": ("NINJA_MODEL_QUICK", "opencode/glm-4.7-free"),
        "sequential": ("NINJA_MODEL_SEQUENTIAL", "zai-coding-plan/glm-4.7"),
        "parallel": ("NINJA_MODEL_PARALLEL", "opencode/glm-4.7-free"),
        "researcher": ("NINJA_RESEARCHER_MODEL", "sonar"),
        "secretary": ("NINJA_SECRETARY_MODEL", "opencode/glm-4.7-free"),
    }

    TAB_ORDER: ClassVar[list[str]] = [
        "tab-overview",
        "tab-keys",
        "tab-models",
        "tab-daemon",
        "tab-ide",
        "tab-settings",
    ]

    def __init__(self, config_path: str | None = None) -> None:
        super().__init__()
        self.config_manager = ConfigManager(config_path)
        self._models_loaded = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with TabbedContent(id="main-tabs"):
            with TabPane("Overview", id="tab-overview"):
                with VerticalScroll():
                    yield Static(_gradient_logo())
                    yield Static("")
                    yield Static(
                        f"[bold #eceff4]Ninja MCP[/bold #eceff4]  [dim]v{_ninja_version()}[/dim]"
                    )
                    yield Static("")
                    yield section_header("System")
                    yield Rule()
                    yield Static(self._system_status())
                    yield section_header("Configuration")
                    yield Rule()
                    yield Static(self._config_summary())
                    yield section_header("Quick Actions")
                    yield Rule()
                    yield Horizontal(
                        Button("Check Updates", variant="primary", id="btn-update"),
                        Button("Run Doctor", id="btn-doctor"),
                        Button("Show Config", id="btn-show-config"),
                    )

            with TabPane("API Keys", id="tab-keys"):
                with VerticalScroll():
                    yield section_header("API Key Management")
                    yield Rule()
                    yield Static("[dim]Keys are stored via OS keyring → encrypted SQLite.[/dim]")
                    yield Static("")
                    yield ListView(id="api-key-list")
                    yield Static("")
                    yield Static("[bold]Set / Update Key[/bold]")
                    yield Input(
                        placeholder="Select key above, then enter value...",
                        id="api-key-input",
                        password=True,
                    )
                    yield Horizontal(
                        Button("Save", variant="primary", id="btn-save-key"),
                        Button("Delete", variant="error", id="btn-delete-key"),
                    )

            with TabPane("Models", id="tab-models"):
                with VerticalScroll():
                    yield section_header("Model Selection")
                    yield Rule()
                    yield Static(
                        "[dim]Pick a provider, type 2+ chars to search. "
                        "↓/↑ + Enter picks, Enter on raw text saves custom.[/dim]"
                    )
                    with Collapsible(title="Coder · Quick (fast, simple tasks)", collapsed=False):
                        yield ModelRolePicker(
                            role="quick",
                            env_var="NINJA_MODEL_QUICK",
                            default="opencode/glm-4.7-free",
                            config=self.config_manager,
                        )
                    with Collapsible(
                        title="Coder · Sequential (complex, multi-step)", collapsed=True
                    ):
                        yield ModelRolePicker(
                            role="sequential",
                            env_var="NINJA_MODEL_SEQUENTIAL",
                            default="zai-coding-plan/glm-4.7",
                            config=self.config_manager,
                        )
                    with Collapsible(title="Coder · Parallel (high concurrency)", collapsed=True):
                        yield ModelRolePicker(
                            role="parallel",
                            env_var="NINJA_MODEL_PARALLEL",
                            default="opencode/glm-4.7-free",
                            config=self.config_manager,
                        )
                    with Collapsible(title="Researcher", collapsed=True):
                        yield ModelRolePicker(
                            role="researcher",
                            env_var="NINJA_RESEARCHER_MODEL",
                            default="sonar",
                            config=self.config_manager,
                        )
                    with Collapsible(title="Secretary", collapsed=True):
                        yield ModelRolePicker(
                            role="secretary",
                            env_var="NINJA_SECRETARY_MODEL",
                            default="opencode/glm-4.7-free",
                            config=self.config_manager,
                        )
                    yield Static("[bold]Custom Model ID[/bold]")
                    yield Input(
                        placeholder="e.g. openrouter/qwen/qwen3-32b", id="custom-model-input"
                    )
                    yield Horizontal(
                        Button("Set Coder Quick", id="set-quick"),
                        Button("Set Coder Seq", id="set-seq"),
                        Button("Set Coder Par", id="set-par"),
                        Button("Set Researcher", id="set-res"),
                        Button("Set Secretary", id="set-sec"),
                    )

            with TabPane("Daemon", id="tab-daemon"):
                with VerticalScroll():
                    yield section_header("Daemon Configuration")
                    yield Rule()
                    yield Static(self._daemon_status())
                    yield Static("")
                    yield Horizontal(
                        Button("Toggle Daemon", variant="primary", id="btn-toggle-daemon"),
                        Button("Restart Daemon", id="btn-restart-daemon"),
                    )
                    yield Static("")
                    yield Static("[bold]Ports[/bold]")
                    yield Static(self._daemon_ports())
                    yield Static("")
                    yield Static("[dim]Changes require daemon restart.[/dim]")

            with TabPane("IDE", id="tab-ide"):
                with VerticalScroll():
                    yield section_header("IDE Integration")
                    yield Rule()
                    yield Static(self._ide_status())
                    yield Static("")
                    yield Static("[bold]Actions[/bold]")
                    yield Button("Register Claude Code MCP", variant="primary", id="btn-claude-mcp")
                    yield Button("Register OpenCode MCP", id="btn-opencode-mcp")

            with TabPane("Settings", id="tab-settings"):
                with VerticalScroll():
                    yield section_header("Settings")
                    yield Rule()
                    yield Static("[bold]Operator[/bold]")
                    yield Static(self._operator_status())
                    yield Static("")
                    yield Static("[bold]Detected Operators[/bold]")
                    yield Static(self._operator_buttons())
                    yield Static("")
                    yield Static("[bold]Search Provider[/bold]")
                    yield Static(self._search_status())
                    yield Horizontal(
                        Button("DuckDuckGo", id="search-duckduckgo"),
                        Button("Serper", id="search-serper"),
                        Button("Perplexity", id="search-perplexity"),
                    )
                    yield section_header("LiteLLM Proxy")
                    yield Rule()
                    yield Static("Self-hosted OpenAI-compatible proxy. Configure the")
                    yield Static("base URL + key here; models then appear in the picker.")
                    yield Static(self._litellm_status(), id="lbl-litellm")
                    yield Input(
                        placeholder="Base URL (e.g. http://localhost:4000/v1)", id="litellm-url"
                    )
                    yield Input(placeholder="API key", id="litellm-key", password=True)
                    yield Input(
                        placeholder="Models (comma-separated: gpt-4o, deepseek-chat)",
                        id="litellm-models",
                    )
                    yield Horizontal(
                        Button("Save LiteLLM", variant="primary", id="btn-save-litellm"),
                        Button("Clear LiteLLM", id="btn-clear-litellm"),
                    )
                    yield Static("")
                    yield section_header("Runtime Constants")
                    yield Rule()
                    yield Static(
                        "All tunable runtime settings (timeouts, safety, retries, serve pool)."
                    )
                    yield Static("Select a setting, edit the value, then press Save.")
                    yield ListView(id="settings-list")
                    yield Static("")
                    yield Input(
                        placeholder="Edit selected setting value...",
                        id="settings-input",
                    )
                    yield Horizontal(
                        Button("Save", variant="primary", id="btn-save-setting"),
                        Button("Reset to Default", id="btn-reset-setting"),
                    )
                    yield Static("")
                    yield Static("[bold #88c0d0]About[/bold #88c0d0]")
                    yield Static(f"Version: {_ninja_version()}")
                    yield Static("Config: ~/.ninja-mcp.env")
                    yield Static("Secrets: OS keyring → encrypted SQLite")
                    yield Static("")
                    yield Button("Check for Updates", variant="primary", id="btn-update-settings")

        yield Footer()

    def on_mount(self) -> None:
        # Light mount only: Header/Tabs/Footer + skeleton. Heavy provider/model
        # discovery runs in background workers after the Models tab opens, so
        # the first frame paints in <0.5s instead of ~14s of empty screen.
        self._refresh_api_keys()
        self._refresh_settings_list()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        pane = getattr(event, "pane", None)
        if (getattr(pane, "id", "") or "") != "tab-models":
            return
        if self._models_loaded:
            return
        self._models_loaded = True
        for picker in self.query(ModelRolePicker):
            try:
                picker.load_providers()
            except Exception:
                continue

    def _provider_buttons_for_role(self, role: str) -> list[tuple[str, str]]:
        """Return (provider_id, display_name) buttons for a role.

        Uses cached dynamic discovery via ``opencode models`` (one subprocess
        per process lifetime, shared across roles); falls back to the
        static provider list if the CLI is unavailable.
        """
        discovered = cached_discover_providers()
        if role == "researcher":
            # Researcher uses Perplexity directly, plus OpenRouter for models.
            if any(p == "openrouter" for p, _, _ in discovered):
                return [("openrouter", "OpenRouter")]
            return [("openrouter", "OpenRouter")]
        providers = []
        for pid, _display, _desc in discovered:
            display = PROVIDER_DISPLAY_NAMES.get(pid, _display)
            if pid == "anthropic":
                continue
            providers.append((pid, display))
        return providers

    def _populate_provider_buttons(self) -> None:
        for role in self.ROLE_MAP:
            prov_row_id = f"prov-{role}"
            try:
                row = self.query_one(f"#{prov_row_id}", Horizontal)
            except Exception:
                continue
            wanted = list(self._provider_buttons_for_role(role))
            wanted_ids = [f"prov-{role}-{pid}" for pid, _ in wanted]
            current_ids = [c.id for c in row.children]
            if current_ids == wanted_ids:
                continue  # Already populated — skip (mount is not idempotent).
            # Providers changed mid-session: drop stale buttons and mount only
            # genuinely new ids. Child removal is async, so re-mounting a
            # still-registered id would raise DuplicateIds.
            row.remove_children([c for c in row.children if c.id not in wanted_ids])
            for bid, (_pid, display) in zip(wanted_ids, wanted):
                if bid not in current_ids:
                    row.mount(Button(display, id=bid))

    def _models_for_role(self, role: str, provider: str) -> list[tuple[str, str, str]]:
        # Cached dynamic discovery first — query the actual operator.
        operator = self.config_manager.get("NINJA_CODE_BIN", "opencode") or "opencode"
        try:
            models = cached_get_provider_models(operator, provider)
        except Exception:
            models = []
        if models:
            return [(m.id, m.name, m.description) for m in models]
        # Static fallback lists.
        if provider == "perplexity":
            return list(PERPLEXITY_MODELS)
        if provider in PROVIDER_MODELS:
            return list(PROVIDER_MODELS[provider])
        return list(PROVIDER_MODELS.get("openrouter", []))

    def _populate_role_lists(self) -> None:
        self._populate_provider_buttons()
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
                lv.append(ModelCard(name, mid, desc, role, env_var, current=(mid == cur)))
        for picker in self.query(ModelRolePicker):
            try:
                picker.refresh_label()
            except Exception:
                continue

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
            lv.append(ModelCard(name, mid, desc, role, env_var, current=(mid == cur)))

    def _guess_provider(self, model_id: str) -> str:
        if not model_id:
            return "openrouter"
        m = model_id.lower()
        if m.startswith("sonar") or "perplexity" in m:
            return "perplexity"
        if m.startswith("opencode-go/"):
            return "opencode-go"
        if m.startswith("zai-coding-plan/"):
            return "zai-coding-plan"
        if m.startswith("zai/"):
            return "zai"
        if m.startswith("opencode/"):
            return "opencode"
        if m.startswith("gemini") or "google/" in m:
            return "google"
        if m.startswith("claude") or "anthropic/" in m:
            return "anthropic"
        if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or "openai/" in m:
            return "openai"
        return "openrouter"

    # ── helpers ──────────────────────────────────────────────────────────

    def _system_status(self) -> str:
        tools = detect_tools()
        ides = detect_ides()
        return (
            f"Tools: {', '.join(tools.keys()) if tools else '[dim]none[/dim]'}\n"
            f"IDEs:  {', '.join(ides.keys()) if ides else '[dim]none[/dim]'}\n"
            f"OS:    {os.uname().sysname} {os.uname().machine}"
        )

    def _config_summary(self) -> str:
        cfg = self.config_manager.list_all()
        op = cfg.get("NINJA_CODE_BIN", "not set")
        daemon = cfg.get("NINJA_ENABLE_DAEMON", "true")
        keys = sum(1 for k in API_KEYS if cfg.get(k.env_var) or os.environ.get(k.env_var))
        return (
            f"Operator: {op}\n"
            f"Daemon:   {'enabled' if daemon == 'true' else 'disabled'}\n"
            f"API Keys: {keys}/{len(API_KEYS)} configured"
        )

    def _current_model(self, env_var: str, default: str) -> str:
        cfg = self.config_manager.list_all()
        cur = cfg.get(env_var, default)
        return f"Current: [#a3be8c]{cur}[/#a3be8c]"

    def _daemon_status(self) -> str:
        cfg = self.config_manager.list_all()
        on = cfg.get("NINJA_ENABLE_DAEMON", "true") == "true"
        return f"Status: {'[#a3be8c]enabled[/#a3be8c]' if on else '[#ebcb8b]disabled[/#ebcb8b]'}"

    def _daemon_ports(self) -> str:
        cfg = self.config_manager.list_all()
        skip = {"NINJA_ENABLE_DAEMON", "NINJA_PROMPTS_PORT", "NINJA_RESOURCES_PORT"}
        lines = []
        for key, val in DAEMON_CONFIG.items():
            if key in skip:
                continue
            cur = cfg.get(key, val)
            name = key.replace("NINJA_", "").replace("_PORT", "").title()
            lines.append(f"{name:12} {cur}")
        return "\n".join(lines)

    def _ide_status(self) -> str:
        from ninja_config.config_shared import IDES as IDE_DEFS

        ides = detect_ides()
        if not ides:
            return "[dim]No IDE configurations detected.[/dim]"
        lines = []
        for ide_id, path in ides.items():
            name = ide_id.title()
            for d in IDE_DEFS:
                if d.id == ide_id:
                    name = d.display_name
                    break
            lines.append(f"[#a3be8c]✓[/#a3be8c] {name}: {path}")
        return "\n".join(lines)

    def _operator_status(self) -> str:
        cfg = self.config_manager.list_all()
        return f"Current: [bold]{cfg.get('NINJA_CODE_BIN', 'not set')}[/bold]"

    def _operator_buttons(self) -> str:
        tools = detect_tools()
        if not tools:
            return "[dim]No operators detected.[/dim]"
        lines = []
        for tid in tools:
            op = OPERATOR_MAP.get(tid)
            if op:
                lines.append(f"[bold]{op.display_name}[/bold] — {op.description}")
        return "\n".join(lines)

    def _search_status(self) -> str:
        cfg = self.config_manager.list_all()
        return f"Current: [bold]{cfg.get('NINJA_SEARCH_PROVIDER', 'duckduckgo')}[/bold]"

    # ── LiteLLM ─────────────────────────────────────────────────────────

    def _litellm_status(self) -> str:
        cfg = read_litellm_config()
        if not cfg or not cfg["base_url"]:
            return "[dim]LiteLLM not configured[/dim]"
        models = ", ".join(cfg["models"]) or "none"
        return (
            f"[bold #a3be8c]Configured:[/bold #a3be8c] {cfg['base_url']}\n"
            f"[bold]Models:[/bold] {models}"
        )

    def _save_litellm(self) -> None:
        url = self.query_one("#litellm-url", Input).value.strip()
        key = self.query_one("#litellm-key", Input).value.strip()
        models_raw = self.query_one("#litellm-models", Input).value.strip()
        if not url:
            self.notify("Enter a LiteLLM base URL first.", timeout=3)
            return
        models = [m.strip() for m in models_raw.split(",") if m.strip()]
        if write_litellm_config(url, key, models):
            try:
                lbl = self.query_one("#lbl-litellm", Static)
                lbl.update(self._litellm_status())
            except Exception:
                pass
            for wid in ("litellm-url", "litellm-key", "litellm-models"):
                try:
                    self.query_one(f"#{wid}", Input).value = ""
                except Exception:
                    pass
            self.config_manager.set("NINJA_CODER_PROVIDER", "litellm")
            self.notify("LiteLLM saved. Models appear in the picker.", timeout=4)
        else:
            self.notify("Failed to write LiteLLM config.", timeout=3)

    def _clear_litellm(self) -> None:
        from ninja_config.litellm import remove_litellm_config

        if remove_litellm_config():
            try:
                lbl = self.query_one("#lbl-litellm", Static)
                lbl.update(self._litellm_status())
            except Exception:
                pass
            self.notify("LiteLLM config removed.", timeout=3)
        else:
            self.notify("Failed to remove LiteLLM config.", timeout=3)

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
        sel = getattr(lv, "highlighted_child", None)
        if sel is None and getattr(lv, "index", None) is not None:
            try:
                sel = lv.children[lv.index]
            except Exception:
                sel = None
        if sel and hasattr(sel, "env_var"):
            return sel.env_var, sel.display_name
        return None

    # ── Runtime constants settings ─────────────────────────────────────

    def _refresh_settings_list(self) -> None:
        lv = self.query_one("#settings-list", ListView)
        lv.clear()
        cfg = self.config_manager.list_all()
        for sd in SETTINGS:
            cur = cfg.get(sd.env_var, sd.default) or sd.default
            if sd.value_type == "bool":
                shown = "true" if cur in ("true", "1", "yes") else "false"
            elif sd.value_type == "choice":
                shown = cur
            else:
                shown = cur or sd.default
            item = ListItem(
                Static(
                    f"[bold]{sd.label}[/bold]  [#a3be8c]{shown}[/#a3be8c]\n"
                    f"  [dim]{sd.env_var} — {sd.description}[/dim]"
                )
            )
            item.setting_env_var = sd.env_var
            item.setting_def = sd
            lv.append(item)

    def _selected_setting(self) -> SettingDef | None:
        lv = self.query_one("#settings-list", ListView)
        sel = getattr(lv, "highlighted_child", None)
        if sel is None and getattr(lv, "index", None) is not None:
            try:
                sel = lv.children[lv.index]
            except Exception:
                sel = None
        if sel and hasattr(sel, "setting_def"):
            return sel.setting_def
        return None

    def _save_setting(self) -> None:
        sd = self._selected_setting()
        if not sd:
            self.notify("Select a setting from the list first.", timeout=3)
            return
        inp = self.query_one("#settings-input", Input)
        value = inp.value.strip()
        if not value:
            self.notify("Enter a value before saving.", timeout=3)
            return
        if sd.value_type == "choice" and value not in sd.options:
            self.notify(
                f"Invalid value for {sd.label}. Options: {', '.join(sd.options)}",
                timeout=5,
            )
            return
        self.config_manager.set(sd.env_var, value)
        self.notify(f"{sd.label} set to {value}.", timeout=3)
        inp.value = ""
        self._refresh_settings_list()

    def _reset_setting(self) -> None:
        sd = self._selected_setting()
        if not sd:
            self.notify("Select a setting from the list first.", timeout=3)
            return
        self.config_manager.set(sd.env_var, sd.default)
        self.notify(f"{sd.label} reset to default ({sd.default}).", timeout=3)
        self._refresh_settings_list()

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
        elif bid == "btn-save-setting":
            self._save_setting()
        elif bid == "btn-reset-setting":
            self._reset_setting()
        elif bid == "btn-save-litellm":
            self._save_litellm()
        elif bid == "btn-clear-litellm":
            self._clear_litellm()
        elif bid == "btn-toggle-daemon":
            self._toggle_daemon()
        elif bid == "btn-restart-daemon":
            self.notify("Run 'ninja-mcp daemon restart' to restart.", timeout=3)
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
        if hasattr(event.item, "setting_env_var") and hasattr(event.item, "setting_def"):
            inp = self.query_one("#settings-input", Input)
            inp.value = self.config_manager.get(event.item.setting_env_var) or ""
            inp.placeholder = f"Edit {event.item.setting_env_var}..."
            return
        if hasattr(event.item, "env_var") and hasattr(event.item, "model_id"):
            env_var = event.item.env_var
            model_id = event.item.model_id
            role = getattr(event.item, "role", "")
            self.config_manager.set(env_var, model_id)
            lbl_id = f"lbl-{role}"
            try:
                lbl = self.query_one(f"#{lbl_id}", Static)
                lbl.update(f"Current: [#a3be8c]{model_id}[/#a3be8c]")
            except Exception:
                pass
            self._populate_role_lists()
            self.notify(f"Model set: {model_id}", timeout=3)
        elif hasattr(event.item, "env_var"):
            inp = self.query_one("#api-key-input", Input)
            inp.placeholder = f"Enter {event.item.display_name} key..."

    def _handle_provider_button(self, bid: str) -> None:
        # Button IDs are prov-{role}-{provider} where provider may contain dashes.
        # Strip the known role prefixes to find the role, then the provider is the rest.
        ROLE_PREFIXES = {
            "prov-quick-": "quick",
            "prov-sequential-": "sequential",
            "prov-parallel-": "parallel",
            "prov-researcher-": "researcher",
            "prov-secretary-": "secretary",
        }
        for prefix, role in ROLE_PREFIXES.items():
            if bid.startswith(prefix):
                provider = bid[len(prefix) :]
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
            lbl.update(f"Current: [#a3be8c]{inp.value}[/#a3be8c]")
        except Exception:
            pass
        self._populate_role_lists()
        self.notify(f"{role.title()} model set: {inp.value}", timeout=3)
        inp.value = ""

    def on_app_notification(self, event: AppNotification) -> None:
        self.notify(event.text, timeout=4)

    # ── Actions ──────────────────────────────────────────────────────────

    def _check_update(self) -> None:
        self.notify("Update with: ninja-mcp update", timeout=5)

    def _show_config(self) -> None:
        cfg = self.config_manager.list_all()
        lines = [f"{k} = {mask_key(v) if 'KEY' in k else v}" for k, v in sorted(cfg.items())]
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
        self.notify(
            f"Daemon {'enabled' if new == 'true' else 'disabled'}. Restart to apply.", timeout=3
        )

    def action_refresh(self) -> None:
        clear_model_cache()
        self._refresh_api_keys()
        self._refresh_settings_list()
        for picker in self.query(ModelRolePicker):
            try:
                picker.refresh_label()
                if self._models_loaded:
                    picker.refresh_providers()
            except Exception:
                continue
        self.notify("Refreshed.", timeout=2)

    # ── Keyboard-first navigation (all actions wired to BINDINGS above) ──

    def action_goto_tab(self, index: int) -> None:
        """Jump to tab by number (``1``-``6``)."""
        try:
            tabs = self.query_one("#main-tabs", TabbedContent)
            tabs.active = self.TAB_ORDER[int(index)]
        except Exception:
            pass

    def _active_tab_id(self) -> str:
        try:
            return str(self.query_one("#main-tabs", TabbedContent).active or "")
        except Exception:
            return ""

    def action_focus_search(self) -> None:
        """``/`` — focus the search/autocomplete input of the active tab."""
        active = self._active_tab_id()
        candidates: list[str] = []
        if active == "tab-models":
            candidates = [f"#model-input-{role}" for role in self.ROLE_MAP]
        elif active == "tab-keys":
            candidates = ["#api-key-input"]
        elif active == "tab-settings":
            candidates = ["#settings-input"]
        else:
            candidates = ["#api-key-input", "#settings-input", "#model-input-quick"]
        for selector in candidates:
            try:
                self.query_one(selector, Input).focus()
                return
            except Exception:
                continue

    def action_save_current(self) -> None:
        """``s`` — save from wherever the focus is (model input/API key/setting)."""
        focused = self.focused
        fid = str(getattr(focused, "id", "") or "")
        if fid.startswith("model-input-"):
            role = fid[len("model-input-") :]
            for picker in self.query(ModelRolePicker):
                if picker.role == role:
                    try:
                        picker.save_current_input()
                    except Exception:
                        pass
                    return
            return
        if fid == "api-key-input" or self._active_tab_id() == "tab-keys":
            self._save_key()
            return
        if fid in ("settings-input", "settings-list") or self._active_tab_id() == "tab-settings":
            self._save_setting()
            return
        self.notify("Focus a model/key/setting input, then press s to save.", timeout=3)

    def action_escape_focus(self) -> None:
        """``Esc`` fallback — drop focus when no dropdown/input consumes it."""
        try:
            self.set_focus(None)
        except Exception:
            pass


def run_modern_tui(config_path: str | None = None) -> int:
    app = NinjaConfigApp(config_path)
    app.run()
    return 0
