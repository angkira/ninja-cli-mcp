"""Modern TUI configurator with collapsible tree and model search.

Features:
- Collapsible tree navigation (expand/collapse branches)
- Right panel for model search with autocomplete
- Input fields for API keys and settings
- Dynamic panels based on selection
"""

from __future__ import annotations

import logging
import os
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
    Tree,
)

from ninja_common.config_manager import ConfigManager
from ninja_config.secrets_store import (
    KNOWN_SECRET_NAMES,
    SecretStore,
    SecretStoreUnavailable,
    default_store,
)


log = logging.getLogger(__name__)


# Import model fetching from model_selector
try:
    from ninja_config.model_selector import get_provider_models

    HAS_MODEL_FETCHER = True
except ImportError:
    HAS_MODEL_FETCHER = False


class ModelSearchPanel(Widget):
    """Panel for searching and selecting models."""

    def __init__(self, context: dict, config_manager: ConfigManager | None = None) -> None:
        super().__init__()
        self.context = context
        self.config_manager = config_manager
        self.filtered_models = []

    def compose(self) -> ComposeResult:
        """Compose the search panel."""
        yield Label("[bold cyan]Model Search[/bold cyan]", id="search-title")
        yield Label(
            f"[dim]Component: {self.context.get('component', 'N/A')}[/dim]",
            id="search-context",
        )
        yield Label(
            f"[dim]Type: {self.context.get('model_type', 'N/A')}[/dim]",
            id="search-type",
        )

        # Show current model if config_manager available
        if self.config_manager:
            component = self.context.get("component", "")
            model_type = self.context.get("model_type", "")
            config = self.config_manager.list_all()
            key = f"NINJA_{component.upper()}_MODEL_{model_type.upper()}"
            current_model = config.get(key, "")
            if current_model:
                yield Label(f"[green]Current: {current_model}[/green]", id="current-model")
            else:
                yield Label("[dim]Current: Not set[/dim]", id="current-model")

        yield Input(placeholder="Search models...", id="model-search-input")

        # Custom model ID input
        yield Label(
            "[dim]Or enter custom model ID (e.g., openrouter/qwen/qwen3-coder-next):[/dim]",
            classes="field-label",
        )
        yield Input(placeholder="Custom model ID...", id="custom-model-input")
        yield Button("Use Custom Model", variant="primary", id="use-custom-model-btn")

        with ScrollableContainer(id="model-results"):
            yield ListView(id="model-list")

    def on_mount(self) -> None:
        """Initialize with all models."""
        self._update_model_list("")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "model-search-input":
            self._update_model_list(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key on custom model input."""
        if event.input.id == "custom-model-input" and event.value:
            self._save_model(event.value)
            event.input.value = ""  # Clear input

    def _update_model_list(self, query: str) -> None:
        """Update model list based on search query."""
        # Get models from appropriate provider using real API
        provider = self.context.get("provider", "openrouter")

        # Fetch real models from API
        if HAS_MODEL_FETCHER:
            try:
                # Determine operator based on component config
                operator = "aider"  # Default
                if self.config_manager:
                    component = self.context.get("component", "")
                    config = self.config_manager.list_all()
                    operator = config.get(f"NINJA_{component.upper()}_OPERATOR", "aider")

                # Fetch models (returns list of Model objects)
                models_data = get_provider_models(operator, provider)

                if not models_data:
                    # Show info message if no models available
                    list_view = self.query_one("#model-list", ListView)
                    list_view.clear()
                    info_item = ListItem(
                        Static(
                            f"[yellow]No models available for {operator}/{provider}[/yellow]\n[dim]Try configuring operator first[/dim]"
                        )
                    )
                    list_view.append(info_item)
                    return

                # Convert Model objects to (model_id, name, description) tuples
                all_models = [(model.id, model.name, model.description) for model in models_data]
            except Exception as e:
                # Fallback to empty list if fetch fails
                all_models = []
                # Show error in UI
                list_view = self.query_one("#model-list", ListView)
                list_view.clear()
                error_item = ListItem(Static(f"[red]Failed to fetch models: {e}[/red]"))
                list_view.append(error_item)
                return
        else:
            all_models = []

        # Filter models
        query_lower = query.lower()
        if query:
            self.filtered_models = [
                (model_id, name, desc)
                for model_id, name, desc in all_models
                if query_lower in model_id.lower()
                or query_lower in name.lower()
                or query_lower in desc.lower()
            ]
        else:
            self.filtered_models = all_models

        # Update list view
        list_view = self.query_one("#model-list", ListView)
        list_view.clear()

        for model_id, name, desc in self.filtered_models:
            content = f"[bold]{name}[/bold]\n[dim]{model_id}\n{desc}[/dim]"
            item = ListItem(Static(content))
            item.model_id = model_id
            list_view.append(item)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle custom model button."""
        if event.button.id == "use-custom-model-btn":
            try:
                custom_input = self.query_one("#custom-model-input", Input)
                if custom_input.value:
                    self._save_model(custom_input.value)
                    custom_input.value = ""  # Clear input
            except Exception:
                pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle model selection from list."""
        if hasattr(event.item, "model_id") and self.config_manager:
            self._save_model(event.item.model_id)

    def _save_model(self, model_id: str) -> None:
        """Save selected model to config."""
        if not self.config_manager:
            return

        component = self.context.get("component", "")
        model_type = self.context.get("model_type", "")

        # Save to config
        key = f"NINJA_{component.upper()}_MODEL_{model_type.upper()}"
        self.config_manager.set(key, model_id)

        # Update current model display
        if self.is_mounted:
            try:
                current_label = self.query_one("#current-model", Label)
                current_label.update(f"[green]Current: {model_id}[/green]")
            except Exception:
                pass

        # Show success notification
        self.app.notify(f"✓ Model saved: {model_id}", severity="information", timeout=2)
        self.app.bell()


class APIKeyPanel(Widget):
    """Panel for configuring a single API key."""

    API_KEY_INFO: ClassVar[dict[str, tuple[str, str]]] = {
        "OPENROUTER_API_KEY": ("OpenRouter", "Used by: Coder, Secretary, Prompts"),
        "ANTHROPIC_API_KEY": ("Anthropic", "Used by: Coder (OpenCode)"),
        "OPENAI_API_KEY": ("OpenAI", "Used by: Coder (OpenCode)"),
        "GOOGLE_API_KEY": ("Google", "Used by: Coder (OpenCode)"),
        "AZURE_OPENAI_API_KEY": ("Azure OpenAI", "Used by: Coder (OpenCode)"),
        "OLLAMA_API_KEY": ("Ollama", "Used by: Coder (OpenCode, optional)"),
        "LMSTUDIO_API_KEY": ("LM Studio", "Used by: Coder (OpenCode, optional)"),
        "ZAI_API_KEY": ("Z.ai", "Used by: Coder (OpenCode)"),
        "PERPLEXITY_API_KEY": ("Perplexity", "Used by: Researcher"),
        "SERPER_API_KEY": ("Serper", "Used by: Researcher"),
    }

    def __init__(self, env_var: str, config_manager: ConfigManager) -> None:
        super().__init__()
        self.env_var = env_var
        self.config_manager = config_manager

    def compose(self) -> ComposeResult:
        """Compose the API key panel."""
        config = self.config_manager.list_all()
        name, usage = self.API_KEY_INFO.get(self.env_var, (self.env_var, ""))
        api_key = config.get(self.env_var, "") or os.environ.get(self.env_var, "")

        yield Label(f"[bold cyan]🔑 {name}[/bold cyan]", id="settings-title")
        yield Label(f"[dim]{usage}[/dim]", id="settings-context")
        yield Label(f"[dim]Environment Variable: {self.env_var}[/dim]", classes="field-label")

        if api_key:
            yield Label("[green]Current Key:[/green]", classes="field-label")
            with Horizontal(classes="key-display-container"):
                yield Input(
                    value=api_key,
                    password=True,
                    id="current-key-display",
                    disabled=True,
                )
                yield Checkbox("Show", id="show-key-checkbox")
        else:
            yield Label("[yellow]No key configured[/yellow]", classes="field-label")

        yield Label("[bold]Update Key:[/bold]", classes="field-label")
        yield Input(
            placeholder=f"Enter new {name} API key...",
            password=True,
            id="api-key-input",
        )
        yield Button("Save Key", variant="primary", id="save-key-btn")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle show/hide checkbox toggle."""
        try:
            key_input = self.query_one("#current-key-display", Input)
            key_input.password = not event.value
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Auto-save on Enter key."""
        if event.input.id == "api-key-input" and event.value:
            self._save_key()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle save button press."""
        if event.button.id == "save-key-btn":
            self._save_key()

    def _save_key(self) -> None:
        """Save the API key."""
        try:
            key_input = self.query_one("#api-key-input", Input)
            if key_input.value:
                self.config_manager.set(self.env_var, key_input.value)
                key_input.value = ""
                self.app.notify(f"✓ {self.env_var} saved!", severity="information", timeout=2)
                self.app.bell()
                # Refresh to show new key
                self.app.query_one(RightPanel).show_api_key(self.env_var, self.config_manager)
        except Exception:
            pass


def _mask(value: str) -> str:
    """Return a masked representation of a secret value.

    Shows only the last 4 characters preceded by bullet dots.
    Never exposes the raw value.

    Examples:
        "sk-abc1234" -> "••••234"  (last 4 of 10-char string is "1234" — wait, corrected below)
        Actually: last 4 chars appended to "••••".
        "abc" -> "••••"   (too short, no preview)
        ""    -> "••••"
    """
    if len(value) > 4:
        return f"••••{value[-4:]}"
    return "••••"


# Canonical display order for known secrets — stable across refreshes.
_KNOWN_SECRET_NAMES_ORDERED: list[str] = sorted(KNOWN_SECRET_NAMES)


class SecretsPanel(Widget):
    """Panel for managing all known API secrets via the SecretStore backend.

    Displays each KNOWN_SECRET_NAME with its set/unset status and a masked
    preview when set.  Provides Set/Update and Delete actions per row.
    Errors from the store (e.g. SecretStoreUnavailable) are surfaced inline;
    the TUI never crashes.
    """

    # ID used for the error banner Static widget.
    _ERROR_BANNER_ID = "secrets-error-banner"

    def __init__(self, store: SecretStore | None = None) -> None:
        super().__init__()
        # Allow injecting a custom store for testing; otherwise use the singleton.
        self._store: SecretStore = store if store is not None else default_store()
        # Tracks which secret is pending a Set/Update operation (name or None).
        self._pending_set: str | None = None

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        """Render the secrets management panel."""
        yield Label("[bold cyan]\U0001f511 API Key Secrets[/bold cyan]", id="secrets-title")
        try:
            backend = self._store.backend_name()
        except Exception:
            backend = "unknown"
        yield Label(f"[dim]Backend: {backend}[/dim]", id="secrets-backend")

        # Error banner — hidden by default; shown on store errors.
        yield Static("", id=self._ERROR_BANNER_ID, classes="secrets-error")

        # One row per known secret.
        for name in _KNOWN_SECRET_NAMES_ORDERED:
            yield self._make_secret_row(name)

        # Input area for setting a value — always rendered, toggled visible.
        yield Label("", id="secrets-input-label", classes="field-label")
        yield Input(
            placeholder="Enter new value...",
            password=True,
            id="secrets-value-input",
        )
        yield Button("Save", variant="primary", id="secrets-save-btn")

        # Hide the input area until a Set/Update action is triggered.
        self._set_input_visible(False)

    def on_mount(self) -> None:
        """Ensure input area is hidden on mount."""
        self._set_input_visible(False)
        self._clear_error()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_secret_row(self, name: str) -> Widget:
        """Build a horizontal row widget for a single secret."""
        try:
            value = self._store.get(name)
        except Exception as exc:
            log.warning("secrets panel: get(%s) error: %s", name, type(exc).__name__)
            value = None

        is_set = value is not None
        status = "[green]✓[/green]" if is_set else "[dim]·[/dim]"
        preview = f" [dim]{_mask(value)}[/dim]" if is_set else ""
        row_label = f"{status} {name}{preview}"

        row = Horizontal(classes="secret-row")
        row.compose_add_child(Label(row_label, classes="secret-name-label"))
        set_btn = Button(
            "Update" if is_set else "Set",
            variant="default",
            id=f"set-{name}",
            classes="secret-set-btn",
        )
        row.compose_add_child(set_btn)
        if is_set:
            del_btn = Button(
                "Delete",
                variant="error",
                id=f"del-{name}",
                classes="secret-del-btn",
            )
            row.compose_add_child(del_btn)
        return row

    def _set_input_visible(self, visible: bool) -> None:
        """Show or hide the value-entry input area."""
        if not self.is_mounted:
            return
        try:
            label = self.query_one("#secrets-input-label", Label)
            inp = self.query_one("#secrets-value-input", Input)
            btn = self.query_one("#secrets-save-btn", Button)
            label.display = visible
            inp.display = visible
            btn.display = visible
        except Exception:
            pass

    def _show_error(self, message: str) -> None:
        """Display an error message in the error banner."""
        if not self.is_mounted:
            return
        try:
            banner = self.query_one(f"#{self._ERROR_BANNER_ID}", Static)
            banner.update(f"[bold red]Error:[/bold red] {message}")
            banner.display = True
        except Exception:
            pass

    def _clear_error(self) -> None:
        """Hide the error banner."""
        if not self.is_mounted:
            return
        try:
            banner = self.query_one(f"#{self._ERROR_BANNER_ID}", Static)
            banner.update("")
            banner.display = False
        except Exception:
            pass

    def refresh_secrets(self) -> None:
        """Re-render secret rows to reflect current store state.

        Called after a set or delete operation to keep the display consistent
        with the store.  Uses the same store instance to ensure consistency.
        """
        # Remove all existing secret-row Horizontals and re-add them.
        for row in list(self.query(".secret-row")):
            row.remove()

        # Re-insert rows before the input label — find the anchor widget.
        try:
            anchor = self.query_one("#secrets-input-label", Label)
        except Exception:
            return

        for name in reversed(_KNOWN_SECRET_NAMES_ORDERED):
            anchor.before(self._make_secret_row(name))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dispatch Set/Update and Delete actions."""
        btn_id = event.button.id or ""

        if btn_id.startswith("set-"):
            name = btn_id[4:]
            self._pending_set = name
            self._clear_error()
            try:
                label = self.query_one("#secrets-input-label", Label)
                label.update(f"[bold]New value for {name}:[/bold]")
            except Exception:
                pass
            self._set_input_visible(True)
            try:
                self.query_one("#secrets-value-input", Input).focus()
            except Exception:
                pass

        elif btn_id.startswith("del-"):
            name = btn_id[4:]
            self._do_delete(name)

        elif btn_id == "secrets-save-btn":
            self._do_save()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Save value when Enter is pressed in the value input."""
        if event.input.id == "secrets-value-input":
            self._do_save()

    def _do_save(self) -> None:
        """Persist the entered value for the pending secret."""
        name = self._pending_set
        if not name:
            return
        try:
            inp = self.query_one("#secrets-value-input", Input)
            value = inp.value.strip()
        except Exception:
            return
        if not value:
            self._show_error("Value cannot be empty.")
            return
        try:
            self._store.set(name, value)
        except SecretStoreUnavailable as exc:
            log.warning("secrets panel: set(%s) unavailable: %s", name, exc)
            self._show_error(
                f"Backend unavailable: {exc}. "
                "Set NINJA_CREDENTIAL_PASSWORD env var or use a keyring daemon."
            )
            return
        except Exception as exc:
            log.warning("secrets panel: set(%s) error: %s", name, type(exc).__name__)
            self._show_error(f"Failed to save {name}: {exc}")
            return

        log.debug("secrets panel: set(%s) ok", name)
        inp.value = ""
        self._pending_set = None
        self._set_input_visible(False)
        self._clear_error()
        self.refresh_secrets()
        self.app.notify(f"✓ {name} saved!", severity="information", timeout=2)

    def _do_delete(self, name: str) -> None:
        """Delete the named secret after inline confirmation."""
        # Inline confirm: reuse the error banner area for a confirm prompt.
        # If a previous delete was already armed for this key, execute it;
        # otherwise arm the prompt.
        banner_id = f"#{self._ERROR_BANNER_ID}"
        try:
            banner = self.query_one(banner_id, Static)
            current_text = str(banner.renderable)
        except Exception:
            current_text = ""

        confirm_marker = f"CONFIRM_DELETE:{name}"
        if confirm_marker in current_text:
            # Second press — execute the delete.
            self._clear_error()
            try:
                self._store.delete(name)
            except Exception as exc:
                log.warning("secrets panel: delete(%s) error: %s", name, type(exc).__name__)
                self._show_error(f"Failed to delete {name}: {exc}")
                return
            log.debug("secrets panel: delete(%s) ok", name)
            self.refresh_secrets()
            self.app.notify(f"✓ {name} deleted.", severity="information", timeout=2)
        else:
            # First press — show confirm prompt.
            try:
                banner = self.query_one(banner_id, Static)
                banner.update(
                    f"[yellow]{confirm_marker}[/yellow]\n"
                    f"Press Delete again to confirm removing [bold]{name}[/bold]."
                )
                banner.display = True
            except Exception:
                pass


class SettingsPanel(Widget):
    """Panel for configuring component-specific settings."""

    def __init__(self, context: dict, config_manager: ConfigManager) -> None:
        super().__init__()
        self.context = context
        self.config_manager = config_manager

    def compose(self) -> ComposeResult:
        """Compose the settings panel."""
        component = self.context.get("component", "")
        config = self.config_manager.list_all()

        yield Label("[bold cyan]Settings & Credentials[/bold cyan]", id="settings-title")

        # Component-specific settings
        yield Label(
            f"[dim]Component: {component.title() if component else 'N/A'}[/dim]",
            id="settings-context",
        )

        # Check operator and provider
        operator = config.get(f"NINJA_{component.upper()}_OPERATOR", "")
        provider = (
            config.get(f"NINJA_{component.upper()}_{operator.upper()}_PROVIDER", "")
            if operator == "opencode"
            else ""
        )

        # Show operator and provider
        if operator:
            operator_text = f"Current Operator: {operator.title()}"
            if provider:
                operator_text += f" ({provider.title()})"
            yield Label(operator_text, classes="field-label")

            # Show which keys this component uses
            if component == "coder":
                if operator == "opencode" and provider:
                    yield Label(
                        f"[dim]Uses: {provider.upper()}_API_KEY (see Global Settings)[/dim]",
                        classes="field-label",
                    )
                else:
                    yield Label(
                        "[dim]Uses: OPENROUTER_API_KEY (see Global Settings)[/dim]",
                        classes="field-label",
                    )
            elif component == "researcher":
                if operator:
                    yield Label(
                        f"[dim]Uses: {operator.upper()}_API_KEY (see Global Settings)[/dim]",
                        classes="field-label",
                    )
            elif component in ["secretary", "prompts"]:
                yield Label(
                    "[dim]Uses: OPENROUTER_API_KEY (see Global Settings)[/dim]",
                    classes="field-label",
                )

            yield Label(
                "[dim]→ Manage all API keys in [bold cyan]Global Settings → API Keys[/bold cyan][/dim]",
                classes="field-label",
            )

        # Base URL (for OpenCode providers) - optional component-specific setting
        if component == "coder" and operator == "opencode":
            yield Label("Base URL (optional):", classes="field-label")
            base_url = config.get(f"NINJA_{component.upper()}_{operator.upper()}_BASE_URL", "")
            yield Input(
                placeholder="Custom base URL...",
                value=base_url,
                id="base-url-input",
            )

        # Save button
        yield Button("Save Settings", variant="primary", id="save-settings-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle save button press."""
        if event.button.id == "save-settings-btn":
            self._save_settings()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Auto-save on Enter key."""
        input_id = event.input.id
        if input_id == "base-url-input":
            self._save_settings()

    def _save_settings(self) -> None:
        """Save settings to config."""
        component = self.context.get("component", "")
        saved_count = 0

        # Try to get base URL input (only exists for OpenCode in component settings)
        try:
            base_url_input = self.query_one("#base-url-input", Input)
            if base_url_input.value:
                self.config_manager.set(f"NINJA_{component.upper()}_BASE_URL", base_url_input.value)
                saved_count += 1
        except Exception:
            pass

        # Show success message
        self.app.bell()
        if saved_count > 0:
            self.app.notify(f"✓ Saved {saved_count} setting(s)!", severity="information", timeout=2)
        else:
            self.app.notify("No changes to save", severity="warning", timeout=2)


class InfoPanel(Widget):
    """Panel showing information about selected item."""

    def __init__(self, info: str = "[dim]Select an item from the tree[/dim]") -> None:
        super().__init__()
        self.current_info = info

    def compose(self) -> ComposeResult:
        """Compose the info panel."""
        yield Static(
            self.current_info,
            id="info-content",
        )

    def update_info(self, info: str) -> None:
        """Update panel content."""
        self.current_info = info
        if self.is_mounted:
            self.query_one("#info-content", Static).update(info)


class ConfigTree(Tree):
    """Configuration tree with collapsible branches."""

    def __init__(self, config_manager: ConfigManager) -> None:
        super().__init__("Ninja MCP Configuration")
        self.config_manager = config_manager
        self.config = config_manager.list_all()
        self.root.expand()
        self._build_tree()

    def _get_current_operator(self, component: str) -> str:
        """Get currently selected operator for component."""
        key = f"NINJA_{component.upper()}_OPERATOR"
        return self.config.get(key, "")

    def _get_current_model(self, component: str, model_type: str) -> str:
        """Get currently selected model for component/type."""
        key = f"NINJA_{component.upper()}_MODEL_{model_type.upper()}"
        return self.config.get(key, "")

    def _build_tree(self) -> None:
        """Build the configuration tree."""
        # Global Settings at the top
        global_settings = self.root.add(
            "🌐 Global Settings", expand=False, data={"type": "global_settings", "id": "global"}
        )

        # API Keys sub-branch with individual keys — status pulled from SecretStore.
        api_keys_branch = global_settings.add(
            "\U0001f511 API Keys", expand=False, data={"type": "api_keys_branch"}
        )

        # Collect names known to the store so we can mark them set/unset.
        try:
            _store = default_store()
            _store_set: set[str] = set(_store.list_names())
        except Exception:
            _store_set = set()

        # Ordered list of all display entries (name, env_var).
        # Includes KNOWN_SECRET_NAMES plus legacy non-standard keys still
        # present in the old APIKeyPanel.API_KEY_INFO dict.
        _all_key_entries: list[tuple[str, str]] = [
            ("OpenRouter", "OPENROUTER_API_KEY"),
            ("Anthropic", "ANTHROPIC_API_KEY"),
            ("OpenAI", "OPENAI_API_KEY"),
            ("Google", "GOOGLE_API_KEY"),
            ("Azure OpenAI", "AZURE_OPENAI_API_KEY"),
            ("Ollama", "OLLAMA_API_KEY"),
            ("LM Studio", "LMSTUDIO_API_KEY"),
            ("Z.ai", "ZAI_API_KEY"),
            ("Perplexity", "PERPLEXITY_API_KEY"),
            ("Serper", "SERPER_API_KEY"),
            ("Groq", "GROQ_API_KEY"),
            ("DeepSeek", "DEEPSEEK_API_KEY"),
            ("Mistral", "MISTRAL_API_KEY"),
        ]

        for name, env_var in _all_key_entries:
            # For KNOWN_SECRET_NAMES prefer the store status; for others fall
            # back to config/env.
            if env_var in KNOWN_SECRET_NAMES:
                is_set = env_var in _store_set
            else:
                is_set = bool(self.config.get(env_var, "") or os.environ.get(env_var, ""))
            status = "✓" if is_set else "·"
            api_keys_branch.add(
                f"{status} {name}",
                data={"type": "api_key", "env_var": env_var, "name": name},
                allow_expand=False,
            )

        # Coder component
        coder = self.root.add("Coder", expand=False, data={"type": "component", "id": "coder"})

        # Default Operator branch
        current_op = self._get_current_operator("coder")
        op_branch = coder.add(
            "Default Operator", expand=False, data={"type": "operator_branch", "component": "coder"}
        )

        # Show current selection with [*]
        aider_label = "[*] Aider" if current_op == "aider" else "[ ] Aider"
        opencode_label = "[*] OpenCode" if current_op == "opencode" else "[ ] OpenCode"

        op_branch.add(
            aider_label,
            data={"type": "operator", "component": "coder", "operator": "aider"},
            allow_expand=False,
        )
        op_branch.add(
            opencode_label,
            data={"type": "operator", "component": "coder", "operator": "opencode"},
            allow_expand=False,
        )

        # Settings branch (for default operator)
        settings = coder.add(
            "Settings", expand=False, data={"type": "settings_branch", "component": "coder"}
        )

        # If OpenCode is selected, show provider selection
        if current_op == "opencode":
            provider_branch = settings.add(
                "OpenCode Provider",
                expand=False,
                data={"type": "provider_branch", "component": "coder"},
            )

            current_provider = self.config.get("NINJA_CODER_OPENCODE_PROVIDER", "")

            # OpenCode providers from https://opencode.ai/docs/providers/
            providers = [
                ("openrouter", "OpenRouter"),
                ("anthropic", "Anthropic"),
                ("openai", "OpenAI"),
                ("google", "Google (Gemini)"),
                ("azure", "Azure OpenAI"),
                ("ollama", "Ollama"),
                ("lmstudio", "LM Studio"),
                ("zai", "Z.ai Coding Plan"),
            ]

            for provider_id, provider_name in providers:
                label = (
                    f"[*] {provider_name}"
                    if current_provider == provider_id
                    else f"[ ] {provider_name}"
                )
                provider_branch.add(
                    label,
                    data={
                        "type": "provider",
                        "component": "coder",
                        "operator": "opencode",
                        "provider": provider_id,
                    },
                    allow_expand=False,
                )

        # General settings (API keys, etc)
        settings.add(
            "Credentials", data={"type": "settings", "component": "coder"}, allow_expand=False
        )

        # Models branch - each model type can have its own operator
        models = coder.add(
            "Models", expand=False, data={"type": "models_branch", "component": "coder"}
        )

        # Quick Tasks
        quick = models.add(
            "Quick Tasks",
            expand=False,
            data={"type": "model_group", "component": "coder", "model_type": "quick"},
        )
        quick_op = quick.add(
            "Operator Override",
            expand=False,
            data={"type": "operator_branch", "component": "coder", "model_type": "quick"},
        )

        # Check if there's a per-model override
        quick_override = self.config.get("NINJA_CODER_OPERATOR_QUICK", "")
        default_label = "[*] Use Default" if not quick_override else "[ ] Use Default"
        aider_label = "[*] Aider" if quick_override == "aider" else "[ ] Aider"
        opencode_label = "[*] OpenCode" if quick_override == "opencode" else "[ ] OpenCode"

        quick_op.add(
            default_label,
            data={
                "type": "operator",
                "component": "coder",
                "operator": "default",
                "model_type": "quick",
            },
            allow_expand=False,
        )
        quick_op.add(
            aider_label,
            data={
                "type": "operator",
                "component": "coder",
                "operator": "aider",
                "model_type": "quick",
            },
            allow_expand=False,
        )
        quick_op.add(
            opencode_label,
            data={
                "type": "operator",
                "component": "coder",
                "operator": "opencode",
                "model_type": "quick",
            },
            allow_expand=False,
        )
        quick.add(
            "Model Selection",
            data={"type": "model", "component": "coder", "model_type": "quick"},
            allow_expand=False,
        )

        # Sequential Tasks
        seq = models.add(
            "Sequential Tasks",
            expand=False,
            data={"type": "model_group", "component": "coder", "model_type": "sequential"},
        )
        seq_op = seq.add(
            "Operator Override",
            expand=False,
            data={"type": "operator_branch", "component": "coder", "model_type": "sequential"},
        )

        seq_override = self.config.get("NINJA_CODER_OPERATOR_SEQUENTIAL", "")
        seq_default_label = "[*] Use Default" if not seq_override else "[ ] Use Default"
        seq_aider_label = "[*] Aider" if seq_override == "aider" else "[ ] Aider"
        seq_opencode_label = "[*] OpenCode" if seq_override == "opencode" else "[ ] OpenCode"

        seq_op.add(
            seq_default_label,
            data={
                "type": "operator",
                "component": "coder",
                "operator": "default",
                "model_type": "sequential",
            },
            allow_expand=False,
        )
        seq_op.add(
            seq_aider_label,
            data={
                "type": "operator",
                "component": "coder",
                "operator": "aider",
                "model_type": "sequential",
            },
            allow_expand=False,
        )
        seq_op.add(
            seq_opencode_label,
            data={
                "type": "operator",
                "component": "coder",
                "operator": "opencode",
                "model_type": "sequential",
            },
            allow_expand=False,
        )
        seq.add(
            "Model Selection",
            data={"type": "model", "component": "coder", "model_type": "sequential"},
            allow_expand=False,
        )

        # Parallel Tasks
        par = models.add(
            "Parallel Tasks",
            expand=False,
            data={"type": "model_group", "component": "coder", "model_type": "parallel"},
        )
        par_op = par.add(
            "Operator Override",
            expand=False,
            data={"type": "operator_branch", "component": "coder", "model_type": "parallel"},
        )

        par_override = self.config.get("NINJA_CODER_OPERATOR_PARALLEL", "")
        par_default_label = "[*] Use Default" if not par_override else "[ ] Use Default"
        par_aider_label = "[*] Aider" if par_override == "aider" else "[ ] Aider"
        par_opencode_label = "[*] OpenCode" if par_override == "opencode" else "[ ] OpenCode"

        par_op.add(
            par_default_label,
            data={
                "type": "operator",
                "component": "coder",
                "operator": "default",
                "model_type": "parallel",
            },
            allow_expand=False,
        )
        par_op.add(
            par_aider_label,
            data={
                "type": "operator",
                "component": "coder",
                "operator": "aider",
                "model_type": "parallel",
            },
            allow_expand=False,
        )
        par_op.add(
            par_opencode_label,
            data={
                "type": "operator",
                "component": "coder",
                "operator": "opencode",
                "model_type": "parallel",
            },
            allow_expand=False,
        )
        par.add(
            "Model Selection",
            data={"type": "model", "component": "coder", "model_type": "parallel"},
            allow_expand=False,
        )

        # Researcher component
        researcher = self.root.add(
            "Researcher", expand=False, data={"type": "component", "id": "researcher"}
        )

        current_op = self._get_current_operator("researcher")
        op_branch = researcher.add(
            "Default Operator",
            expand=False,
            data={"type": "operator_branch", "component": "researcher"},
        )

        perplexity_label = "[*] Perplexity" if current_op == "perplexity" else "[ ] Perplexity"
        serper_label = "[*] Serper" if current_op == "serper" else "[ ] Serper"
        duckduckgo_label = "[*] DuckDuckGo" if current_op == "duckduckgo" else "[ ] DuckDuckGo"

        op_branch.add(
            perplexity_label,
            data={"type": "operator", "component": "researcher", "operator": "perplexity"},
            allow_expand=False,
        )
        op_branch.add(
            serper_label,
            data={"type": "operator", "component": "researcher", "operator": "serper"},
            allow_expand=False,
        )
        op_branch.add(
            duckduckgo_label,
            data={"type": "operator", "component": "researcher", "operator": "duckduckgo"},
            allow_expand=False,
        )

        researcher.add("Settings", data={"type": "settings", "component": "researcher"})

        models = researcher.add(
            "Models", expand=False, data={"type": "models_branch", "component": "researcher"}
        )
        research = models.add(
            "Research Model",
            expand=False,
            data={"type": "model_group", "component": "researcher", "model_type": "research"},
        )
        research_op = research.add(
            "Operator Override",
            expand=False,
            data={"type": "operator_branch", "component": "researcher", "model_type": "research"},
        )

        # Check for research model operator override
        research_override = self.config.get("NINJA_RESEARCHER_OPERATOR_RESEARCH", "")
        research_default_label = "[*] Use Default" if not research_override else "[ ] Use Default"
        research_perplexity_label = (
            "[*] Perplexity" if research_override == "perplexity" else "[ ] Perplexity"
        )
        research_serper_label = "[*] Serper" if research_override == "serper" else "[ ] Serper"
        research_duckduckgo_label = (
            "[*] DuckDuckGo" if research_override == "duckduckgo" else "[ ] DuckDuckGo"
        )

        research_op.add(
            research_default_label,
            data={
                "type": "operator",
                "component": "researcher",
                "operator": "default",
                "model_type": "research",
            },
            allow_expand=False,
        )
        research_op.add(
            research_perplexity_label,
            data={
                "type": "operator",
                "component": "researcher",
                "operator": "perplexity",
                "model_type": "research",
            },
            allow_expand=False,
        )
        research_op.add(
            research_serper_label,
            data={
                "type": "operator",
                "component": "researcher",
                "operator": "serper",
                "model_type": "research",
            },
            allow_expand=False,
        )
        research_op.add(
            research_duckduckgo_label,
            data={
                "type": "operator",
                "component": "researcher",
                "operator": "duckduckgo",
                "model_type": "research",
            },
            allow_expand=False,
        )
        research.add(
            "Model Selection",
            data={"type": "model", "component": "researcher", "model_type": "research"},
            allow_expand=False,
        )

        # Secretary component
        secretary = self.root.add(
            "Secretary", expand=False, data={"type": "component", "id": "secretary"}
        )
        secretary.add("Settings", data={"type": "settings", "component": "secretary"})
        models = secretary.add(
            "Models", expand=False, data={"type": "models_branch", "component": "secretary"}
        )
        analysis = models.add(
            "Analysis Model",
            expand=False,
            data={"type": "model_group", "component": "secretary", "model_type": "analysis"},
        )
        analysis.add(
            "Model Selection",
            data={"type": "model", "component": "secretary", "model_type": "analysis"},
            allow_expand=False,
        )

        # Prompts component
        prompts = self.root.add(
            "Prompts", expand=False, data={"type": "component", "id": "prompts"}
        )
        prompts.add("Settings", data={"type": "settings", "component": "prompts"})
        models = prompts.add(
            "Models", expand=False, data={"type": "models_branch", "component": "prompts"}
        )
        generation = models.add(
            "Generation Model",
            expand=False,
            data={"type": "model_group", "component": "prompts", "model_type": "generation"},
        )
        generation.add(
            "Model Selection",
            data={"type": "model", "component": "prompts", "model_type": "generation"},
            allow_expand=False,
        )


class RightPanel(Container):
    """Dynamic right panel that changes based on tree selection."""

    def __init__(self, config_manager: ConfigManager) -> None:
        super().__init__(id="right-panel")
        self.config_manager = config_manager
        self.current_panel = None

    def show_model_search(self, context: dict) -> None:
        """Show model search panel."""
        self.remove_children()
        self.mount(ModelSearchPanel(context, self.config_manager))

    def show_settings(self, context: dict) -> None:
        """Show settings panel."""
        self.remove_children()
        self.mount(SettingsPanel(context, self.config_manager))

    def show_api_key(self, env_var: str, config_manager: ConfigManager | None = None) -> None:
        """Show API key configuration panel."""
        self.remove_children()
        self.mount(APIKeyPanel(env_var, config_manager or self.config_manager))

    def show_info(self, info: str) -> None:
        """Show info panel."""
        self.remove_children()
        self.mount(InfoPanel(info))

    def show_secrets(self) -> None:
        """Show the secrets management panel."""
        self.remove_children()
        self.mount(SecretsPanel())


class ModernConfigApp(App):
    """Modern TUI configurator."""

    CSS = """
    Screen {
        background: $surface;
    }

    #logo {
        height: 6;
        content-align: center middle;
        margin-bottom: 1;
        text-style: bold;
        border-bottom: solid cyan;
        padding-bottom: 1;
    }

    #main-container {
        layout: horizontal;
        height: 100%;
    }

    #left-panel {
        width: 45%;
        height: 100%;
        border: solid cyan;
        padding: 1;
    }

    #right-panel {
        width: 55%;
        height: 100%;
        border: solid green;
        padding: 1;
        overflow-y: auto;
    }

    Tree {
        background: $surface;
    }

    Tree:focus {
        border: solid yellow;
    }

    #search-title, #settings-title {
        height: 1;
        margin-bottom: 1;
    }

    #search-context, #search-type, #settings-context {
        height: 1;
        margin-bottom: 1;
    }

    .field-label {
        height: 1;
        margin-top: 1;
        margin-bottom: 1;
    }

    .key-display-container {
        height: auto;
        margin-bottom: 1;
    }

    #current-key-display {
        width: 80%;
    }

    #show-key-checkbox {
        width: 20%;
        margin-left: 1;
    }

    #model-search-input, #api-key-input, #base-url-input {
        margin-bottom: 1;
    }

    #model-results {
        height: 1fr;
        border: solid $primary;
        padding: 1;
    }

    #model-list {
        background: $surface;
    }

    ListView > ListItem {
        padding: 1;
        height: auto;
    }

    ListView > ListItem:hover {
        background: $boost;
    }

    ListView > ListItem.-active {
        background: $primary;
    }

    #save-settings-btn {
        margin-top: 1;
    }

    /* SecretsPanel styles */
    #secrets-title {
        height: 1;
        margin-bottom: 1;
    }

    #secrets-backend {
        height: 1;
        margin-bottom: 1;
    }

    .secrets-error {
        color: $error;
        margin-bottom: 1;
        display: none;
    }

    .secret-row {
        height: auto;
        margin-bottom: 1;
    }

    .secret-name-label {
        width: 1fr;
    }

    .secret-set-btn {
        width: auto;
        margin-left: 1;
    }

    .secret-del-btn {
        width: auto;
        margin-left: 1;
    }

    #secrets-value-input {
        margin-top: 1;
        margin-bottom: 1;
    }

    #secrets-save-btn {
        margin-bottom: 1;
    }
    """

    BINDINGS: ClassVar[list] = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, config_path: str | None = None):
        super().__init__()
        self.config_manager = ConfigManager(config_path)
        self.title = "Ninja MCP Configurator"
        self.sub_title = "Modern Tree-Based Configuration"

    def _create_logo(self) -> str:
        """Create gradient logo text with teal-blue gradient."""
        # NINJA-MCP with gradient from turquoise to blue
        # Using bright colors for visibility
        return (
            "[bold cyan]███[/bold cyan]   [bold blue]███[/bold blue] [bold]████████[/bold] [bold cyan]████████[/bold cyan]\n"
            "[bold cyan]█[/bold cyan]   [bold blue]█[/bold blue] [bold]█[/bold]   [bold cyan]█[/bold cyan] [bold bright_cyan]█[/bold bright_cyan]     [bold]█[/bold]\n"
            "[bold blue]█[/bold blue]   [bold]█[/bold] [bold cyan]████████[/bold cyan] [bold bright_blue]████████[/bold bright_blue]\n"
            "[bold]█[/bold]   [bold cyan]█[/bold cyan] [bold bright_cyan]█[/bold bright_cyan]     [bold]█[/bold]     [bold bright_cyan]█[/bold bright_cyan]\n"
            "[bold cyan]███[/bold cyan]   [bold bright_cyan]███[/bold bright_cyan] [bold]█[/bold]     [bold bright_cyan]████████[/bold bright_cyan]"
        )

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()

        with Horizontal(id="main-container"):
            # Left: Collapsible tree with logo
            with Container(id="left-panel"):
                # Logo with gradient
                yield Static(self._create_logo(), id="logo")
                yield ConfigTree(self.config_manager)

            # Right: Dynamic panel
            yield RightPanel(self.config_manager)

        yield Footer()

    def on_mount(self) -> None:
        """Initialize right panel."""
        right_panel = self.query_one(RightPanel)
        right_panel.show_info("[dim]Select an item from the tree to configure[/dim]")

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """Handle tree node highlighting (navigation with arrows)."""
        if not event.node.data:
            return

        right_panel = self.query_one(RightPanel)
        node_type = event.node.data.get("type")

        if node_type == "model":
            # Show model search panel
            context = {
                "component": event.node.data.get("component"),
                "model_type": event.node.data.get("model_type"),
                "provider": "openrouter",  # TODO: Get from config
            }
            right_panel.show_model_search(context)

        elif node_type == "settings":
            # Show settings panel
            context = {
                "component": event.node.data.get("component"),
            }
            right_panel.show_settings(context)

        elif node_type == "api_key":
            # Route to the unified SecretsPanel for all secrets management.
            right_panel.show_secrets()

        elif node_type == "api_keys_branch":
            # Show the unified secrets management panel.
            right_panel.show_secrets()

        elif node_type == "operator":
            # Show operator info
            comp = event.node.data.get("component", "").title()
            op = event.node.data.get("operator", "").title()
            info = f"[bold cyan]{op} Operator[/bold cyan]\n\n"
            info += f"Component: {comp}\n\n"
            info += "[dim]Press Enter to select this operator[/dim]"
            right_panel.show_info(info)

        elif node_type == "component":
            # Show component info
            comp_id = event.node.data.get("id", "")
            info = f"[bold cyan]{comp_id.title()} Component[/bold cyan]\n\n"
            info += "[dim]Expand to configure operator, settings, and models[/dim]"
            right_panel.show_info(info)

        else:
            # Show generic info
            right_panel.show_info(f"[dim]{node_type}[/dim]")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection (Enter key press)."""
        if not event.node.data:
            return

        node_type = event.node.data.get("type")

        if node_type == "operator":
            # Save operator selection
            component = event.node.data.get("component")
            operator = event.node.data.get("operator")
            model_type = event.node.data.get("model_type")  # Optional, for per-model operators

            if operator == "default":
                # Clear per-model operator override
                if model_type:
                    key = f"NINJA_{component.upper()}_OPERATOR_{model_type.upper()}"
                    # Remove the override key
                    config = self.config_manager.list_all()
                    if key in config:
                        # TODO: Add delete method to ConfigManager
                        pass
            else:
                # Save operator selection
                if model_type:
                    # Per-model operator
                    key = f"NINJA_{component.upper()}_OPERATOR_{model_type.upper()}"
                else:
                    # Default operator
                    key = f"NINJA_{component.upper()}_OPERATOR"

                self.config_manager.set(key, operator)

            # Refresh tree to show new selection
            self._refresh_tree()
            self.bell()

        elif node_type == "provider":
            # Save OpenCode provider selection
            component = event.node.data.get("component")
            operator = event.node.data.get("operator")
            provider = event.node.data.get("provider")

            # Save provider
            key = f"NINJA_{component.upper()}_{operator.upper()}_PROVIDER"
            self.config_manager.set(key, provider)

            # Refresh tree to show new selection
            self._refresh_tree()
            self.bell()

        elif node_type == "model":
            # For model selection, the right panel already handles it
            pass

    def _refresh_tree(self) -> None:
        """Refresh tree to show updated selections without collapsing branches."""
        tree = self.query_one(ConfigTree)

        # Save expanded state before rebuilding
        expanded_paths = self._get_expanded_paths(tree.root, [])

        # Rebuild tree with updated config
        tree.clear()
        tree.config = tree.config_manager.list_all()  # Reload config
        tree._build_tree()

        # Restore expanded state
        self._restore_expanded_state(tree.root, expanded_paths, [])

        # Show notification
        self.notify("Selection saved!", severity="information", timeout=2)

    def _get_expanded_paths(self, node, current_path: list) -> list[tuple]:
        """Recursively get paths of all expanded nodes."""
        expanded = []

        if node.is_expanded and node.data:
            # Store the path as a tuple of data dictionaries
            expanded.append((*current_path, node.data))

        for child in node.children:
            expanded.extend(
                self._get_expanded_paths(child, [*current_path, node.data] if node.data else [])
            )

        return expanded

    def _restore_expanded_state(
        self, node, expanded_paths: list[tuple], current_path: list
    ) -> None:
        """Recursively restore expanded state to matching nodes."""
        if node.data:
            current_tuple = (*current_path, node.data)
            # Check if this node's path was expanded
            if current_tuple in expanded_paths:
                node.expand()

        for child in node.children:
            self._restore_expanded_state(
                child, expanded_paths, [*current_path, node.data] if node.data else []
            )

    def action_refresh(self) -> None:
        """Refresh configuration."""
        # TODO: Reload config from file
        pass


def run_modern_tui(config_path: str | None = None) -> int:
    """Run the modern TUI configurator.

    Args:
        config_path: Optional path to config file

    Returns:
        Exit code
    """
    app = ModernConfigApp(config_path)
    app.run()
    return 0
