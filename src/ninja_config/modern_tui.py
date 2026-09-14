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

from textual import on, work
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
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from ninja_common.config_manager import ConfigManager
from ninja_common.daemon import DaemonManager
from ninja_common.defaults import (
    AVAILABLE_MODULES,
    DEFAULT_ENABLED_MODULES,
    DEFAULT_PORTS,
    PERPLEXITY_MODELS,
    PROVIDER_MODELS,
)
from ninja_config.config_shared import (
    API_KEYS,
    detect_ides,
    detect_tools,
    get_secret,
    mask_key,
    register_claude_mcp,
)
from ninja_config.litellm import (
    read_litellm_config,
    write_litellm_config,
)
from ninja_config.model_selector import (
    OPERATORS,
    PROVIDER_DISPLAY_NAMES,
    check_operator_auth,
    detect_operators,
    native_provider_for_operator,
    normalize_operator,
)
from ninja_config.secrets_store import (
    SecretStore,
    SecretStoreUnavailable,
    default_store,
    rekey_and_set_password,
    reset_encrypted_store,
    store_password_source,
)
from ninja_config.settings_registry import SETTINGS, SettingDef
from ninja_config.ui.model_autocomplete import ModelRolePicker
from ninja_config.ui.model_autocomplete import guess_provider as model_guess_provider
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


def _set_toggle(button: Button, on: bool) -> None:
    """Paint a leading toggle-indicator button (light blue when on)."""
    button.label = "●" if on else "○"
    button.set_class(on, "tog-on")
    button.set_class(not on, "tog-off")


class ModuleRow(Horizontal):
    """One module as a borderless table row: [●] Module  daemon  port  binary.

    The leading toggle button (light blue when on) is keyboard-focusable and
    enables + starts (on) or disables + stops (off) the module's daemon.
    """

    def __init__(self, module: str) -> None:
        super().__init__(classes="module-row")
        self.module_name = module

    def compose(self) -> ComposeResult:
        yield Button("○", id=f"module-toggle-{self.module_name}", classes="tog module-toggle")
        yield Static(self.module_name.title(), classes="m-name")
        yield Static("", id=f"module-daemon-{self.module_name}", classes="m-state")
        yield Static("", id=f"module-port-{self.module_name}", classes="m-port")
        yield Static("", id=f"module-binary-{self.module_name}", classes="m-binary")
        yield Button(
            "Install",
            id=f"module-install-{self.module_name}",
            classes="module-install",
        )

    def set_state(self, *, enabled: bool, running: bool, installed: bool, port: int | None) -> None:
        """Sync the row with the persisted enabled flag and live daemon state."""
        _set_toggle(self.query_one(".module-toggle", Button), enabled)
        self.query_one(f"#module-daemon-{self.module_name}", Static).update(
            "[#a3be8c]running[/#a3be8c]" if running else "[dim]stopped[/dim]"
        )
        self.query_one(f"#module-port-{self.module_name}", Static).update(str(port))
        self.query_one(f"#module-binary-{self.module_name}", Static).update(
            "[#a3be8c]✓[/#a3be8c]" if installed else "[#ebcb8b]✗[/#ebcb8b]"
        )
        self.query_one(".module-install", Button).display = not installed


class DaemonRow(Horizontal):
    """One module daemon as a borderless table row with a start/stop toggle."""

    def __init__(self, module: str) -> None:
        super().__init__(classes="daemon-row")
        self.module_name = module

    def compose(self) -> ComposeResult:
        yield Button("○", id=f"daemon-toggle-{self.module_name}", classes="tog daemon-toggle")
        yield Static(self.module_name.title(), classes="m-name")
        yield Static("", id=f"daemon-state-{self.module_name}", classes="m-state")
        yield Static("", id=f"daemon-port-{self.module_name}", classes="m-port")

    def set_state(self, *, running: bool, port: int | None) -> None:
        """Sync the row with the live daemon state."""
        _set_toggle(self.query_one(".daemon-toggle", Button), running)
        self.query_one(f"#daemon-state-{self.module_name}", Static).update(
            "[#a3be8c]running[/#a3be8c]" if running else "[dim]stopped[/dim]"
        )
        self.query_one(f"#daemon-port-{self.module_name}", Static).update(str(port))


class APIKeyRow(Vertical):
    """A provider API-key row with an inline editor revealed on focus.

    Tabbing onto the row (or clicking it) shows a password input plus Save /
    Delete right under that provider — no shared input at the bottom of the tab.
    """

    can_focus = True

    BINDINGS: ClassVar[list] = [
        Binding("down", "next_provider", "Next provider", show=False),
        Binding("up", "prev_provider", "Previous provider", show=False),
    ]

    def __init__(self, env_var: str, display_name: str, module: str, value: str) -> None:
        super().__init__(classes="api-key-row")
        self.env_var = env_var
        self.display_name = display_name
        self.module = module
        self._value = value

    def action_next_provider(self) -> None:
        """Move focus to the next provider row (``↓``)."""
        self._focus_sibling_row(1)

    def action_prev_provider(self) -> None:
        """Move focus to the previous provider row (``↑``)."""
        self._focus_sibling_row(-1)

    def _focus_sibling_row(self, step: int) -> None:
        parent = self.parent
        if parent is None:
            return
        rows = [child for child in parent.children if isinstance(child, APIKeyRow)]
        try:
            index = rows.index(self)
        except ValueError:
            return
        target = index + step
        if 0 <= target < len(rows):
            rows[target].focus()

    def compose(self) -> ComposeResult:
        yield Static(self._head_text(), classes="key-head")
        yield Input(
            placeholder=f"New value for {self.display_name}",
            password=True,
            id=f"key-input-{self.env_var}",
            classes="key-editor",
        )
        yield Horizontal(
            Button("Save", variant="primary", id=f"key-save-{self.env_var}"),
            Button("Delete", variant="error", id=f"key-delete-{self.env_var}"),
            classes="key-editor key-actions",
        )

    def _head_text(self) -> str:
        icon = "[#a3be8c]✓[/#a3be8c]" if self._value else "[dim]○[/dim]"
        masked = mask_key(self._value) if self._value else "[dim]not set[/dim]"
        return f"{icon} [bold]{self.display_name}[/bold]  {masked}  [dim]({self.module})[/dim]"

    def set_value(self, value: str) -> None:
        """Refresh the masked value shown in the row header."""
        self._value = value
        self.query_one(".key-head", Static).update(self._head_text())

    def input_value(self) -> str:
        return self.query_one(f"#key-input-{self.env_var}", Input).value

    def clear_input(self) -> None:
        self.query_one(f"#key-input-{self.env_var}", Input).value = ""


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
        Binding("7", "goto_tab(6)", "Modules"),
        Binding("escape", "escape_focus", "Back", show=False),
        # ── RU (ЙЦУКЕН) duplicates: same physical keys, hidden from Footer ──
        # Textual matches BINDINGS by character (event.key), not scancode,
        # so RU layout yields different characters: q→й, s→ы, /→.
        # Digits 1-6, Tab/Esc/arrows are layout-independent (no dups needed).
        # ctrl+r is normally layout-independent, ctrl+к covers terminals
        # that localize Ctrl combos.
        Binding("й", "quit", "Quit", show=False, priority=True),
        Binding("Й", "quit", "Quit", show=False, priority=True),
        Binding("ы", "save_current", "Save", show=False),
        Binding("Ы", "save_current", "Save", show=False),
        Binding(".", "focus_search", "Search", show=False),
        Binding("ctrl+к", "refresh", "Refresh", show=False),
        # U+041A CYRILLIC CAPITAL KA as escape (RUF001 flags the literal).
        Binding("ctrl+\u041a", "refresh", "Refresh", show=False),
    ]

    ROLE_MAP: ClassVar[dict[str, tuple[str, str]]] = {
        "quick": ("NINJA_MODEL_QUICK", "opencode/glm-4.7-free"),
        "sequential": ("NINJA_MODEL_SEQUENTIAL", "zai-coding-plan/glm-4.7"),
        "parallel": ("NINJA_MODEL_PARALLEL", "opencode/glm-4.7-free"),
        "researcher": ("NINJA_RESEARCHER_MODEL", "sonar"),
        "secretary": ("NINJA_SECRETARY_MODEL", "opencode/glm-4.7-free"),
        "agent": ("NINJA_AGENT_MODEL", "opencode/glm-4.7-free"),
    }

    TAB_ORDER: ClassVar[list[str]] = [
        "tab-overview",
        "tab-keys",
        "tab-models",
        "tab-daemon",
        "tab-ide",
        "tab-settings",
        "tab-modules",
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
                    yield Static(
                        "[dim]Keys are stored via OS keyring → encrypted SQLite. "
                        "Focus a provider to edit its key inline.[/dim]"
                    )
                    yield Static("")
                    with Vertical(id="api-key-rows"):
                        for _k in API_KEYS:
                            yield APIKeyRow(
                                _k.env_var,
                                _k.display_name,
                                _k.module,
                                get_secret(_k.env_var) or "",
                            )
                    yield Static("")
                    yield section_header("Encrypted store")
                    yield Rule()
                    yield Static(self._store_status(), id="lbl-store")
                    yield Static(
                        "[dim]Password for ~/.ninja/credentials.db — kept in the OS "
                        "keyring (falls back to the config file if unavailable).[/dim]"
                    )
                    yield Input(
                        placeholder="New store password",
                        password=True,
                        id="store-pw",
                    )
                    yield Input(
                        placeholder="Confirm store password",
                        password=True,
                        id="store-pw2",
                    )
                    yield Horizontal(
                        Button("Set / Change", variant="primary", id="btn-store-set"),
                        Button("Reset store", variant="error", id="btn-store-reset"),
                    )
                    yield Input(
                        placeholder="Type DELETE to confirm reset", id="store-reset-confirm"
                    )

            with TabPane("Models", id="tab-models"):
                with VerticalScroll():
                    yield section_header("Model Selection")
                    yield Rule()
                    yield Static(
                        "[dim]Pick a provider, type 2+ chars to search. "
                        "↓/↑ + Enter picks, Enter on raw text saves custom.[/dim]"
                    )
                    yield Static(
                        "[bold]Operator[/bold] [dim](coding CLI: opencode / codex / claude / aider / …)[/dim]"
                    )
                    yield Static(self._operator_status(), id="lbl-operator-models")
                    yield Select(
                        self._operator_select_options(),
                        prompt="Operator…",
                        value=self._current_operator_id(),
                        id="operator-select",
                    )
                    yield Static("")
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
                    with Collapsible(title="Agent (orchestrator)", collapsed=True):
                        yield ModelRolePicker(
                            role="agent",
                            env_var="NINJA_AGENT_MODEL",
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
                        Button("Set Agent", id="set-agent"),
                    )

            with TabPane("Daemon", id="tab-daemon"):
                with VerticalScroll():
                    yield section_header("Daemon Configuration")
                    yield Rule()
                    yield Static(self._daemon_status())
                    yield Static("")
                    yield Horizontal(
                        Static("", classes="m-toggle-spacer"),
                        Static("[dim]Daemon[/dim]", classes="m-name"),
                        Static("[dim]State[/dim]", classes="m-state"),
                        Static("[dim]Port[/dim]", classes="m-port"),
                        classes="table-head",
                    )
                    with Vertical(id="daemon-rows"):
                        for module in AVAILABLE_MODULES:
                            yield DaemonRow(module)
                    yield Static("")
                    yield Static("[dim]Toggle a row to start/stop that daemon.[/dim]")

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
                    yield Static(self._operator_status(), id="lbl-operator-status")
                    yield Static("")
                    yield Static("[bold]Detected Operators[/bold]")
                    yield Static(self._operator_buttons(), id="lbl-operators")
                    yield Horizontal(id="operator-buttons")
                    yield Static("[dim]Checking availability…[/dim]", id="lbl-operator-avail")
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

            with TabPane("Modules", id="tab-modules"):
                with VerticalScroll():
                    yield section_header("Module Management")
                    yield Rule()
                    yield Static(
                        "[dim]Toggle a module on/off — that enables it and starts/stops "
                        "its daemon. Missing binaries show an Install button.[/dim]"
                    )
                    yield Horizontal(
                        Static("", classes="m-toggle-spacer"),
                        Static("[dim]Module[/dim]", classes="m-name"),
                        Static("[dim]Daemon[/dim]", classes="m-state"),
                        Static("[dim]Port[/dim]", classes="m-port"),
                        Static("[dim]Binary[/dim]", classes="m-binary"),
                        classes="table-head",
                    )
                    with Vertical(id="module-rows"):
                        for module in AVAILABLE_MODULES:
                            yield ModuleRow(module)
                    yield Static("")
                    yield Static(self._modules_help(), id="modules-help")

        yield Footer()

    def on_mount(self) -> None:
        # Light mount only: Header/Tabs/Footer + skeleton. Heavy provider/model
        # discovery runs in background workers after the Models tab opens, so
        # the first frame paints in <0.5s instead of ~14s of empty screen.
        self._refresh_api_keys()
        self._refresh_settings_list()
        self._refresh_modules()
        self._refresh_daemons()
        self._populate_operator_buttons()
        self._check_operator_availability()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        pane = getattr(event, "pane", None)
        pane_id = getattr(pane, "id", "") or ""
        if pane_id == "tab-modules":
            self._refresh_modules()
            return
        if pane_id == "tab-daemon":
            self._refresh_daemons()
            return
        if pane_id != "tab-models":
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
        # Native operators (codex/junie/…) expose only their own provider —
        # `opencode models` discovery never lists it.
        native = native_provider_for_operator(self.config_manager.get("NINJA_CODE_BIN"))
        if native:
            return [(native, PROVIDER_DISPLAY_NAMES.get(native, native.replace("-", " ").title()))]
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
        operator = normalize_operator(self.config_manager.get("NINJA_CODE_BIN"))
        return model_guess_provider(model_id, operator)

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
        raw = self.config_manager.get("NINJA_CODE_BIN") or "not set"
        op_id = normalize_operator(raw)
        op = next((o for o in OPERATORS if o.id == op_id), None)
        name = op.name if op else op_id
        return f"Current: [bold]{name}[/bold] [dim]({raw})[/dim]"

    def _installed_operators(self) -> list:
        """Detected (installed) operators — cheap ``shutil.which`` probe only."""
        try:
            return detect_operators()
        except Exception:
            return []

    def _current_operator_id(self) -> str:
        """The configured operator id (``NINJA_CODE_BIN``), normalized."""
        return normalize_operator(self.config_manager.get("NINJA_CODE_BIN"))

    def _operator_select_options(self) -> list[tuple[str, str]]:
        """(label, id) options for the Models-tab operator picker."""
        options = [(op.name, op.id) for op in self._installed_operators()]
        current = self._current_operator_id()
        if all(value != current for _, value in options):
            op = next((o for o in OPERATORS if o.id == current), None)
            options.append((op.name if op else current, current))
        return options or [("opencode", "opencode")]

    def _operator_buttons(self) -> str:
        installed = {op.id for op in self._installed_operators()}
        current = normalize_operator(self.config_manager.get("NINJA_CODE_BIN"))
        lines = []
        for op in OPERATORS:
            if op.id in installed:
                mark = "[#a3be8c]✓ installed[/#a3be8c]"
                auth = "host-auth" if op.id in ("codex", "junie") else "API key"
            else:
                mark = "[dim]✗ not installed[/dim]"
                auth = "[dim]—[/dim]"
            cur = " [bold #a3be8c]← current[/bold #a3be8c]" if op.id == current else ""
            lines.append(f"{mark} [bold]{op.name}[/bold] ({auth}){cur}")
        return "\n".join(lines) if lines else "[dim]No operators detected.[/dim]"

    def _populate_operator_buttons(self) -> None:
        """Mount one select button per installed operator (current highlighted).

        Idempotent: existing buttons are relabelled in place and stale ones
        removed, so re-entrant calls never raise ``DuplicateIds`` (child
        removal is async in Textual).
        """
        try:
            row = self.query_one("#operator-buttons", Horizontal)
        except Exception:
            return
        current = normalize_operator(self.config_manager.get("NINJA_CODE_BIN"))
        wanted = self._installed_operators()
        wanted_ids = [f"op-{op.id}" for op in wanted]
        current_ids = [c.id for c in row.children]
        row.remove_children([c for c in row.children if c.id not in wanted_ids])
        for op, bid in zip(wanted, wanted_ids):
            label = f"{op.name}{' ✓' if op.id == current else ''}"
            variant = "primary" if op.id == current else "default"
            if bid in current_ids:
                try:
                    btn = row.query_one(f"#{bid}", Button)
                    btn.label = label
                    btn.variant = variant
                except Exception:
                    pass
            else:
                row.mount(Button(label, id=bid, variant=variant))

    @work(thread=True, exclusive=True)
    def _check_operator_availability(self) -> None:
        """Probe installed operators for usable auth (background, non-blocking)."""
        lines = []
        for op in self._installed_operators():
            try:
                auth = check_operator_auth(op)
            except Exception:
                auth = {}
            providers = ", ".join(p for p, ok in auth.items() if ok)
            host = op.id in ("codex", "junie")
            usable = bool(providers) or host
            status = "[#a3be8c]available[/#a3be8c]" if usable else "[#ebcb8b]unavailable[/#ebcb8b]"
            detail = providers or ("host-auth" if host else "no credentials")
            lines.append(f"{op.name}: {status} [dim]({detail})[/dim]")
        self.app.call_from_thread(
            self._set_operator_avail,
            "\n".join(lines) if lines else "[dim]No operators installed.[/dim]",
        )

    def _set_operator_avail(self, text: str) -> None:
        try:
            self.query_one("#lbl-operator-avail", Static).update(text)
        except Exception:
            pass

    def _select_operator(self, op_id: str) -> None:
        """Switch the active operator, guarding against uninstalled ones.

        Rebuilds the model pickers' provider lists so the new operator's native
        provider (e.g. Codex) appears immediately.
        """
        installed = {op.id for op in self._installed_operators()}
        if op_id not in installed:
            self.notify(f"{op_id} is not installed.", timeout=4, severity="warning")
            return
        self.config_manager.set("NINJA_CODE_BIN", op_id)
        try:
            self.query_one("#lbl-operator-status", Static).update(self._operator_status())
            self.query_one("#lbl-operators", Static).update(self._operator_buttons())
        except Exception:
            pass
        self._populate_operator_buttons()
        for picker in self.query(ModelRolePicker):
            try:
                picker.on_operator_changed()
            except Exception:
                continue
        self.notify(f"Operator set to {op_id}. Model providers refreshed.", timeout=3)

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
        # Resolve the effective value (SecretStore -> env -> .env) so the row
        # preview reflects a key just saved to the keyring.
        for row in self.query(APIKeyRow):
            row.set_value(get_secret(row.env_var) or "")

    def _api_key_row(self, env_var: str) -> APIKeyRow | None:
        """Return the API-key row for ``env_var``, if mounted."""
        for row in self.query(APIKeyRow):
            if row.env_var == env_var:
                return row
        return None

    def _store_status(self) -> str:
        """One-line status of the encrypted store password source."""
        source = store_password_source()
        label = {
            "memory": "held in this process (memory)",
            "passwordless": "passwordless (machine-bound)",
            "fd": "inherited fd (daemon start)",
            "systemd": "systemd credential",
            "file": "password file",
            "keyring": "OS keychain",
            "env": "env var (NINJA_CREDENTIAL_PASSWORD)",
            "unset": "unset — prompts on first use",
        }.get(source, source)
        colour = "#ebcb8b" if source == "unset" else "#a3be8c"
        return f"Password: [{colour}]{label}[/{colour}]  ·  ~/.ninja/credentials.db"

    def _set_store_password(self) -> None:
        """Set or change the encrypted-store password (re-encrypts credentials)."""
        password = self.query_one("#store-pw", Input).value
        confirm = self.query_one("#store-pw2", Input).value
        if not password or password != confirm:
            self.notify("Passwords are empty or do not match.", timeout=4)
            return
        try:
            # persist=True keeps it in the OS keychain (macOS Keychain / Secret
            # Service) so headless launches can unlock the store without a TTY.
            count = rekey_and_set_password(password, persist=True)
        except Exception as e:
            self.notify(
                f"Failed to change store password ({e}). Use Reset to start over.",
                timeout=6,
            )
            return
        for wid in ("store-pw", "store-pw2"):
            self.query_one(f"#{wid}", Input).value = ""
        self.query_one("#lbl-store", Static).update(self._store_status())
        self._refresh_api_keys()
        self.notify(
            f"Store password set (keychain); {count} credential(s) re-encrypted.",
            timeout=5,
        )

    def _reset_store(self) -> None:
        """Delete the encrypted store (requires typing DELETE to confirm)."""
        confirm = self.query_one("#store-reset-confirm", Input).value.strip()
        if confirm != "DELETE":
            self.notify("Type DELETE in the confirm field to reset the store.", timeout=4)
            return
        if reset_encrypted_store():
            self.query_one("#store-reset-confirm", Input).value = ""
            self.query_one("#lbl-store", Static).update(self._store_status())
            self._refresh_api_keys()
            self.notify("Encrypted store reset (credentials.db removed).", timeout=5)
        else:
            self.notify("Could not remove credentials.db.", timeout=4)

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

    # ── Modules ──────────────────────────────────────────────────────────

    def _enabled_modules(self) -> list[str]:
        """Return the enabled modules parsed from ``NINJA_ENABLED_MODULES``.

        A present-but-empty value means "none enabled"; only an *absent* key
        falls back to :data:`DEFAULT_ENABLED_MODULES`, so toggling the last
        module off sticks.
        """
        raw = self.config_manager.get("NINJA_ENABLED_MODULES")
        if raw is None:
            return list(DEFAULT_ENABLED_MODULES)
        return [m.strip() for m in raw.split(",") if m.strip()]

    def _set_enabled_modules(self, modules: list[str]) -> None:
        """Persist the enabled module list to ``NINJA_ENABLED_MODULES``."""
        self.config_manager.set("NINJA_ENABLED_MODULES", ",".join(modules))

    def _modules_help(self) -> str:
        """Return one help line per available module with its default port."""
        return "\n".join(
            f"{module:12} port {DEFAULT_PORTS.get(module, 8100)}" for module in AVAILABLE_MODULES
        )

    def _refresh_modules(self) -> None:
        """Sync every module row with the persisted enabled flag + live state."""
        try:
            rows = self.query_one("#module-rows", Vertical)
        except Exception:
            return
        dm = DaemonManager()
        enabled = self._enabled_modules()
        by_name = {r.module_name: r for r in rows.query(ModuleRow)}
        for module in AVAILABLE_MODULES:
            row = by_name.get(module)
            if row is None:
                continue
            try:
                st = dm.status(module)
            except Exception:
                st = {}
            row.set_state(
                enabled=module in enabled,
                running=bool(st.get("running")),
                installed=shutil.which(f"ninja-{module}") is not None,
                port=st.get("port"),
            )

    def _refresh_daemons(self) -> None:
        """Sync every daemon row with the live daemon state."""
        try:
            rows = self.query_one("#daemon-rows", Vertical)
        except Exception:
            return
        dm = DaemonManager()
        by_name = {r.module_name: r for r in rows.query(DaemonRow)}
        for module in AVAILABLE_MODULES:
            row = by_name.get(module)
            if row is None:
                continue
            try:
                st = dm.status(module)
            except Exception:
                st = {}
            row.set_state(running=bool(st.get("running")), port=st.get("port"))

    def _toggle_module_daemon(self, module: str) -> None:
        """Start or stop ``module``'s daemon (running state only)."""
        dm = DaemonManager()
        try:
            running = bool(dm.status(module).get("running"))
            if running:
                ok = dm.stop(module)
                action = "stopped"
            else:
                ok = dm.start(module)
                action = "started"
        except Exception as e:
            self.notify(f"{module}: daemon toggle failed ({e}).", timeout=8)
            self._refresh_daemons()
            self._refresh_modules()
            return
        self._refresh_daemons()
        self._refresh_modules()
        if ok:
            self.notify(f"{module} daemon {action}.", timeout=3)
        else:
            self.notify(
                f"{module} daemon did not {action[:-1]} — see ~/.cache/ninja-mcp/logs/{module}.log",
                timeout=7,
            )

    def _enable_module(self, module: str) -> None:
        """Enable ``module`` in config and start its daemon."""
        enabled = self._enabled_modules()
        if module in enabled:
            self._refresh_modules()
            return
        if shutil.which(f"ninja-{module}") is None:
            self.notify(f"{module} binary missing — press Install.", timeout=4)
            self._refresh_modules()
            return
        enabled.append(module)
        self._set_enabled_modules(enabled)
        try:
            started = DaemonManager().start(module)
        except Exception as e:
            self.notify(f"{module}: could not start daemon ({e}).", timeout=8)
            self._refresh_modules()
            return
        self._refresh_modules()
        if started:
            self.notify(f"{module} enabled; daemon started.", timeout=3)
        else:
            self.notify(
                f"{module} enabled, but the daemon did not start — check "
                f"~/.cache/ninja-mcp/logs/{module}.log",
                timeout=7,
            )

    def _disable_module(self, module: str) -> None:
        """Remove ``module`` from config and stop its daemon."""
        enabled = self._enabled_modules()
        if module in enabled:
            enabled.remove(module)
            self._set_enabled_modules(enabled)
        try:
            DaemonManager().stop(module)
        except Exception as e:
            self.notify(f"{module}: could not stop daemon ({e}).", timeout=8)
            self._refresh_modules()
            return
        self._refresh_modules()
        self.notify(f"{module} disabled; daemon stopped.", timeout=3)

    def _install_module(self, module: str) -> None:
        """Install the missing binary for ``module``."""
        if shutil.which(f"ninja-{module}") is not None:
            self.notify(f"{module} already installed.", timeout=3)
            return
        self._install_worker(module)

    @work(thread=True, group="module-install")
    def _install_worker(self, module: str) -> None:
        """Install one module via ``uv tool install`` in a background thread."""
        import subprocess
        from pathlib import Path

        cwd = Path.cwd()
        if (cwd / "pyproject.toml").exists():
            cmd = ["uv", "tool", "install", "--force", f"{cwd}[{module}]"]
        else:
            cmd = ["uv", "tool", "install", "--force", f"ninja-mcp[{module}]"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        self.call_from_thread(self._finish_install, module, result.returncode == 0)

    def _finish_install(self, module: str, ok: bool) -> None:
        """Handle install completion: enable and start the module on success."""
        if not ok:
            self.notify(f"Install of {module} failed.", timeout=3)
            return
        enabled = self._enabled_modules()
        if module not in enabled:
            enabled.append(module)
            self._set_enabled_modules(enabled)
        DaemonManager().start(module)
        self._refresh_modules()
        self.notify(f"{module} installed, enabled, and started.", timeout=3)

    # ── Event handlers ───────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""

        if bid in ("btn-update", "btn-update-settings"):
            self._check_update()
        elif bid == "btn-doctor":
            self.notify("Run 'ninja-config doctor' for diagnostics.", timeout=3)
        elif bid == "btn-show-config":
            self._show_config()
        elif bid.startswith("key-save-"):
            row = self._api_key_row(bid[len("key-save-") :])
            if row is not None:
                self._save_key(row)
        elif bid.startswith("key-delete-"):
            row = self._api_key_row(bid[len("key-delete-") :])
            if row is not None:
                self._delete_key(row)
        elif bid == "btn-store-set":
            self._set_store_password()
        elif bid == "btn-store-reset":
            self._reset_store()
        elif bid == "btn-save-setting":
            self._save_setting()
        elif bid == "btn-reset-setting":
            self._reset_setting()
        elif bid == "btn-save-litellm":
            self._save_litellm()
        elif bid == "btn-clear-litellm":
            self._clear_litellm()
        elif bid == "btn-claude-mcp":
            count = register_claude_mcp()
            self.notify(f"Claude Code MCP: {count}/3 servers registered.", timeout=3)
        elif bid == "btn-opencode-mcp":
            if shutil.which("opencode"):
                self.notify("OpenCode: use 'ninja-config configure' for setup.", timeout=3)
            else:
                self.notify("OpenCode CLI not found.", timeout=3)
        elif bid.startswith("module-toggle-"):
            module = bid[len("module-toggle-") :]
            if module in self._enabled_modules():
                self._disable_module(module)
            else:
                self._enable_module(module)
        elif bid.startswith("daemon-toggle-"):
            self._toggle_module_daemon(bid[len("daemon-toggle-") :])
        elif bid.startswith("module-install-"):
            self._install_module(bid[len("module-install-") :])
        elif bid.startswith("set-"):
            self._set_custom_model(bid[4:])
        elif bid.startswith("prov-"):
            self._handle_provider_button(bid)
        elif bid.startswith("op-"):
            self._select_operator(bid[3:])
        elif bid == "search-duckduckgo":
            self.config_manager.set("NINJA_SEARCH_PROVIDER", "duckduckgo")
            self.notify("Search: DuckDuckGo", timeout=3)
        elif bid == "search-serper":
            self.config_manager.set("NINJA_SEARCH_PROVIDER", "serper")
            self.notify("Search: Serper", timeout=3)
        elif bid == "search-perplexity":
            self.config_manager.set("NINJA_SEARCH_PROVIDER", "perplexity")
            self.notify("Search: Perplexity", timeout=3)

    @on(Select.Changed)
    def on_operator_selected(self, event: Select.Changed) -> None:
        """Operator picker in the Models tab (global coding CLI)."""
        if event.select.id != "operator-select":
            return
        value = event.value
        if value is None or value == Select.BLANK:
            return
        self._select_operator(str(value))
        try:
            self.query_one("#lbl-operator-models", Static).update(self._operator_status())
        except Exception:
            pass

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

    def _handle_provider_button(self, bid: str) -> None:
        # Button IDs are prov-{role}-{provider} where provider may contain dashes.
        # Strip the known role prefixes to find the role, then the provider is the rest.
        ROLE_PREFIXES = {
            "prov-quick-": "quick",
            "prov-sequential-": "sequential",
            "prov-parallel-": "parallel",
            "prov-researcher-": "researcher",
            "prov-secretary-": "secretary",
            "prov-agent-": "agent",
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
            "agent": ("NINJA_AGENT_MODEL", "agent"),
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

    def _save_key(self, row: APIKeyRow) -> None:
        value = row.input_value()
        if not value:
            self.notify(f"Enter a value for {row.display_name} first.", timeout=3)
            return
        try:
            default_store().set(row.env_var, value)
        except SecretStoreUnavailable:
            self.notify(
                f"⚠ {row.display_name}: encrypted store locked — set the store "
                f"password below, then save again.",
                timeout=7,
            )
        except Exception as e:
            self.notify(f"⚠ {row.display_name}: save failed ({e}).", timeout=7)
        else:
            row.clear_input()
            self.notify(f"✓ {row.display_name} saved to encrypted store.", timeout=3)
        self._refresh_api_keys()

    def _delete_key(self, row: APIKeyRow) -> None:
        try:
            store = default_store()
            store.delete(row.env_var)
        except Exception:
            pass
        self.config_manager.set(row.env_var, "")
        self.notify(f"✓ {row.display_name} removed.", timeout=3)
        self._refresh_api_keys()

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
        if active == "tab-keys":
            # Focus the inline editor of the first API-key row.
            for row in self.query(APIKeyRow):
                try:
                    row.query_one(Input).focus()
                    return
                except Exception:
                    continue
            return
        if active == "tab-models":
            candidates = [f"#model-input-{role}" for role in self.ROLE_MAP]
        elif active == "tab-settings":
            candidates = ["#settings-input"]
        else:
            candidates = ["#settings-input", "#model-input-quick"]
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
        if fid.startswith("key-input-"):
            row = self._api_key_row(fid[len("key-input-") :])
            if row is not None:
                self._save_key(row)
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
