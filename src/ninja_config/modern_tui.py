"""Modern TUI configurator with collapsible tree and model search.

Features:
- Collapsible tree navigation (expand/collapse branches)
- Right panel for model search with autocomplete
- Input fields for API keys and settings
- Dynamic panels based on selection
"""

from __future__ import annotations

import os
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header,
    Footer,
    Static,
    Tree,
    Button,
    Input,
    Label,
    ListView,
    ListItem,
    Checkbox,
)
from textual.binding import Binding
from textual.widget import Widget
from rich.text import Text
from pathlib import Path

from ninja_common.config_manager import ConfigManager


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
            component = self.context.get('component', '')
            model_type = self.context.get('model_type', '')
            config = self.config_manager.list_all()
            key = f"NINJA_{component.upper()}_MODEL_{model_type.upper()}"
            current_model = config.get(key, "")
            if current_model:
                yield Label(f"[green]Current: {current_model}[/green]", id="current-model")
            else:
                yield Label("[dim]Current: Not set[/dim]", id="current-model")

        yield Input(placeholder="Search models...", id="model-search-input")

        # Custom model ID input
        yield Label("[dim]Or enter custom model ID (e.g., openrouter/qwen/qwen3-coder-next):[/dim]", classes="field-label")
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
                    info_item = ListItem(Static(f"[yellow]No models available for {operator}/{provider}[/yellow]\n[dim]Try configuring operator first[/dim]"))
                    list_view.append(info_item)
                    return

                # Convert Model objects to (model_id, name, description) tuples
                all_models = [
                    (model.id, model.name, model.description)
                    for model in models_data
                ]
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

        component = self.context.get('component', '')
        model_type = self.context.get('model_type', '')

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


class SettingsPanel(Widget):
    """Panel for configuring settings and API keys."""

    def __init__(self, context: dict, config_manager: ConfigManager) -> None:
        super().__init__()
        self.context = context
        self.config_manager = config_manager
        self.api_key_env_var = ""  # Will be set during compose

    def compose(self) -> ComposeResult:
        """Compose the settings panel."""
        component = self.context.get("component", "")
        config = self.config_manager.list_all()

        yield Label("[bold cyan]Settings & Credentials[/bold cyan]", id="settings-title")

        # Global credentials panel - show ALL API keys
        if component == "global":
            yield Label(
                "[dim]Global API Keys (shared across all components)[/dim]",
                id="settings-context",
            )

            # All possible API keys grouped by category
            yield Label("[bold yellow]AI Providers[/bold yellow]", classes="field-label")

            all_keys = [
                ("OpenRouter", "OPENROUTER_API_KEY", "Used by: Coder, Secretary, Prompts"),
                ("Anthropic", "ANTHROPIC_API_KEY", "Used by: Coder (OpenCode)"),
                ("OpenAI", "OPENAI_API_KEY", "Used by: Coder (OpenCode)"),
                ("Google", "GOOGLE_API_KEY", "Used by: Coder (OpenCode)"),
                ("Azure OpenAI", "AZURE_OPENAI_API_KEY", "Used by: Coder (OpenCode)"),
                ("Ollama", "OLLAMA_API_KEY", "Used by: Coder (OpenCode, optional)"),
                ("LM Studio", "LMSTUDIO_API_KEY", "Used by: Coder (OpenCode, optional)"),
                ("Z.ai", "ZAI_API_KEY", "Used by: Coder (OpenCode)"),
            ]

            for label, env_var, usage in all_keys:
                api_key = config.get(env_var, "") or os.environ.get(env_var, "")

                yield Label(f"[bold]{label}[/bold] [dim]{usage}[/dim]", classes="field-label")

                if api_key:
                    with Horizontal(classes="key-display-container"):
                        yield Input(
                            value=api_key,
                            password=True,
                            id=f"current-{env_var.lower()}",
                            disabled=True,
                        )
                        yield Checkbox("Show", id=f"show-{env_var.lower()}")
                else:
                    yield Label("[dim]Not set[/dim]", classes="field-label")

                yield Input(
                    placeholder=f"Update {label}...",
                    password=True,
                    id=f"update-{env_var.lower()}",
                )

            yield Label("[bold yellow]Research Providers[/bold yellow]", classes="field-label")

            research_keys = [
                ("Perplexity", "PERPLEXITY_API_KEY", "Used by: Researcher"),
                ("Serper", "SERPER_API_KEY", "Used by: Researcher"),
            ]

            for label, env_var, usage in research_keys:
                api_key = config.get(env_var, "") or os.environ.get(env_var, "")

                yield Label(f"[bold]{label}[/bold] [dim]{usage}[/dim]", classes="field-label")

                if api_key:
                    with Horizontal(classes="key-display-container"):
                        yield Input(
                            value=api_key,
                            password=True,
                            id=f"current-{env_var.lower()}",
                            disabled=True,
                        )
                        yield Checkbox("Show", id=f"show-{env_var.lower()}")
                else:
                    yield Label("[dim]Not set[/dim]", classes="field-label")

                yield Input(
                    placeholder=f"Update {label}...",
                    password=True,
                    id=f"update-{env_var.lower()}",
                )

        else:
            # Component-specific settings
            yield Label(
                f"[dim]Component: {component.title() if component else 'N/A'}[/dim]",
                id="settings-context",
            )

            # Check operator and provider
            operator = config.get(f"NINJA_{component.upper()}_OPERATOR", "")
            provider = config.get(f"NINJA_{component.upper()}_{operator.upper()}_PROVIDER", "") if operator == "opencode" else ""

            # Show operator and provider
            if operator:
                operator_text = f"Current Operator: {operator.title()}"
                if provider:
                    operator_text += f" ({provider.title()})"
                yield Label(operator_text, classes="field-label")

            # Show which keys this component uses
            if component == "coder":
                if operator == "opencode" and provider:
                    yield Label(f"[dim]Uses: {provider.upper()}_API_KEY (see Global Settings)[/dim]", classes="field-label")
                else:
                    yield Label("[dim]Uses: OPENROUTER_API_KEY (see Global Settings)[/dim]", classes="field-label")
            elif component == "researcher":
                if operator:
                    yield Label(f"[dim]Uses: {operator.upper()}_API_KEY (see Global Settings)[/dim]", classes="field-label")
            elif component in ["secretary", "prompts"]:
                yield Label("[dim]Uses: OPENROUTER_API_KEY (see Global Settings)[/dim]", classes="field-label")

            yield Label("[dim]→ Manage all API keys in [bold cyan]Global Settings → API Keys[/bold cyan][/dim]", classes="field-label")

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

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle show/hide checkbox toggle."""
        checkbox_id = event.checkbox.id
        if checkbox_id and checkbox_id.startswith("show-"):
            # Extract the key identifier from checkbox ID
            key_id = checkbox_id.replace("show-", "")

            # Try different ID formats (component-specific and global)
            for prefix in ["current-key-", "current-"]:
                try:
                    key_input = self.query_one(f"#{prefix}{key_id}", Input)
                    key_input.password = not event.value
                    break
                except Exception:
                    continue

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Auto-save on Enter key."""
        input_id = event.input.id
        if input_id and (input_id.startswith("update-key-") or input_id == "api-key-input"):
            self._save_settings()

    def _save_settings(self) -> None:
        """Save settings to config."""
        component = self.context.get("component", "")
        config = self.config_manager.list_all()
        operator = config.get(f"NINJA_{component.upper()}_OPERATOR", "") if component != "global" else ""

        saved_count = 0

        # Global settings - save all API keys
        if component == "global":
            all_env_vars = [
                "OPENROUTER_API_KEY",
                "ANTHROPIC_API_KEY",
                "OPENAI_API_KEY",
                "GOOGLE_API_KEY",
                "AZURE_OPENAI_API_KEY",
                "OLLAMA_API_KEY",
                "LMSTUDIO_API_KEY",
                "ZAI_API_KEY",
                "PERPLEXITY_API_KEY",
                "SERPER_API_KEY",
            ]

            for env_var in all_env_vars:
                try:
                    update_input = self.query_one(f"#update-{env_var.lower()}", Input)
                    if update_input.value:
                        self.config_manager.set(env_var, update_input.value)
                        saved_count += 1
                except Exception:
                    pass

        # Try to get base URL input (only exists for OpenCode in component settings)
        try:
            base_url_input = self.query_one("#base-url-input", Input)
            if base_url_input.value:
                self.config_manager.set(f"NINJA_{component.upper()}_BASE_URL", base_url_input.value)
                saved_count += 1
        except Exception:
            pass

        # Clear all update input fields after saving
        if saved_count > 0:
            # Find all update-key inputs and clear them
            for widget in self.query("Input"):
                if widget.id and widget.id.startswith("update-key-"):
                    widget.value = ""

        # Show success message
        self.app.bell()
        if saved_count > 0:
            self.app.notify(f"✓ Saved {saved_count} credential(s)!", severity="information", timeout=2)
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
        global_settings = self.root.add("🌐 Global Settings", expand=False, data={"type": "global_settings", "id": "global"})
        global_settings.add("API Keys", data={"type": "global_credentials"}, allow_expand=False)

        # Coder component
        coder = self.root.add("Coder", expand=False, data={"type": "component", "id": "coder"})

        # Default Operator branch
        current_op = self._get_current_operator("coder")
        op_branch = coder.add("Default Operator", expand=False, data={"type": "operator_branch", "component": "coder"})

        # Show current selection with [*]
        aider_label = "[*] Aider" if current_op == "aider" else "[ ] Aider"
        opencode_label = "[*] OpenCode" if current_op == "opencode" else "[ ] OpenCode"

        op_branch.add(aider_label, data={"type": "operator", "component": "coder", "operator": "aider"}, allow_expand=False)
        op_branch.add(opencode_label, data={"type": "operator", "component": "coder", "operator": "opencode"}, allow_expand=False)

        # Settings branch (for default operator)
        settings = coder.add("Settings", expand=False, data={"type": "settings_branch", "component": "coder"})

        # If OpenCode is selected, show provider selection
        if current_op == "opencode":
            provider_branch = settings.add("OpenCode Provider", expand=False, data={"type": "provider_branch", "component": "coder"})

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
                label = f"[*] {provider_name}" if current_provider == provider_id else f"[ ] {provider_name}"
                provider_branch.add(label, data={"type": "provider", "component": "coder", "operator": "opencode", "provider": provider_id}, allow_expand=False)

        # General settings (API keys, etc)
        settings.add("Credentials", data={"type": "settings", "component": "coder"}, allow_expand=False)

        # Models branch - each model type can have its own operator
        models = coder.add("Models", expand=False, data={"type": "models_branch", "component": "coder"})

        # Quick Tasks
        quick = models.add("Quick Tasks", expand=False, data={"type": "model_group", "component": "coder", "model_type": "quick"})
        quick_op = quick.add("Operator Override", expand=False, data={"type": "operator_branch", "component": "coder", "model_type": "quick"})

        # Check if there's a per-model override
        quick_override = self.config.get("NINJA_CODER_OPERATOR_QUICK", "")
        default_label = "[*] Use Default" if not quick_override else "[ ] Use Default"
        aider_label = "[*] Aider" if quick_override == "aider" else "[ ] Aider"
        opencode_label = "[*] OpenCode" if quick_override == "opencode" else "[ ] OpenCode"

        quick_op.add(default_label, data={"type": "operator", "component": "coder", "operator": "default", "model_type": "quick"}, allow_expand=False)
        quick_op.add(aider_label, data={"type": "operator", "component": "coder", "operator": "aider", "model_type": "quick"}, allow_expand=False)
        quick_op.add(opencode_label, data={"type": "operator", "component": "coder", "operator": "opencode", "model_type": "quick"}, allow_expand=False)
        quick.add("Model Selection", data={"type": "model", "component": "coder", "model_type": "quick"}, allow_expand=False)

        # Sequential Tasks
        seq = models.add("Sequential Tasks", expand=False, data={"type": "model_group", "component": "coder", "model_type": "sequential"})
        seq_op = seq.add("Operator Override", expand=False, data={"type": "operator_branch", "component": "coder", "model_type": "sequential"})

        seq_override = self.config.get("NINJA_CODER_OPERATOR_SEQUENTIAL", "")
        seq_default_label = "[*] Use Default" if not seq_override else "[ ] Use Default"
        seq_aider_label = "[*] Aider" if seq_override == "aider" else "[ ] Aider"
        seq_opencode_label = "[*] OpenCode" if seq_override == "opencode" else "[ ] OpenCode"

        seq_op.add(seq_default_label, data={"type": "operator", "component": "coder", "operator": "default", "model_type": "sequential"}, allow_expand=False)
        seq_op.add(seq_aider_label, data={"type": "operator", "component": "coder", "operator": "aider", "model_type": "sequential"}, allow_expand=False)
        seq_op.add(seq_opencode_label, data={"type": "operator", "component": "coder", "operator": "opencode", "model_type": "sequential"}, allow_expand=False)
        seq.add("Model Selection", data={"type": "model", "component": "coder", "model_type": "sequential"}, allow_expand=False)

        # Parallel Tasks
        par = models.add("Parallel Tasks", expand=False, data={"type": "model_group", "component": "coder", "model_type": "parallel"})
        par_op = par.add("Operator Override", expand=False, data={"type": "operator_branch", "component": "coder", "model_type": "parallel"})

        par_override = self.config.get("NINJA_CODER_OPERATOR_PARALLEL", "")
        par_default_label = "[*] Use Default" if not par_override else "[ ] Use Default"
        par_aider_label = "[*] Aider" if par_override == "aider" else "[ ] Aider"
        par_opencode_label = "[*] OpenCode" if par_override == "opencode" else "[ ] OpenCode"

        par_op.add(par_default_label, data={"type": "operator", "component": "coder", "operator": "default", "model_type": "parallel"}, allow_expand=False)
        par_op.add(par_aider_label, data={"type": "operator", "component": "coder", "operator": "aider", "model_type": "parallel"}, allow_expand=False)
        par_op.add(par_opencode_label, data={"type": "operator", "component": "coder", "operator": "opencode", "model_type": "parallel"}, allow_expand=False)
        par.add("Model Selection", data={"type": "model", "component": "coder", "model_type": "parallel"}, allow_expand=False)

        # Researcher component
        researcher = self.root.add("Researcher", expand=False, data={"type": "component", "id": "researcher"})

        current_op = self._get_current_operator("researcher")
        op_branch = researcher.add("Default Operator", expand=False, data={"type": "operator_branch", "component": "researcher"})

        perplexity_label = "[*] Perplexity" if current_op == "perplexity" else "[ ] Perplexity"
        serper_label = "[*] Serper" if current_op == "serper" else "[ ] Serper"
        duckduckgo_label = "[*] DuckDuckGo" if current_op == "duckduckgo" else "[ ] DuckDuckGo"

        op_branch.add(perplexity_label, data={"type": "operator", "component": "researcher", "operator": "perplexity"}, allow_expand=False)
        op_branch.add(serper_label, data={"type": "operator", "component": "researcher", "operator": "serper"}, allow_expand=False)
        op_branch.add(duckduckgo_label, data={"type": "operator", "component": "researcher", "operator": "duckduckgo"}, allow_expand=False)

        researcher.add("Settings", data={"type": "settings", "component": "researcher"})

        models = researcher.add("Models", expand=False, data={"type": "models_branch", "component": "researcher"})
        research = models.add("Research Model", expand=False, data={"type": "model_group", "component": "researcher", "model_type": "research"})
        research_op = research.add("Operator Override", expand=False, data={"type": "operator_branch", "component": "researcher", "model_type": "research"})

        # Check for research model operator override
        research_override = self.config.get("NINJA_RESEARCHER_OPERATOR_RESEARCH", "")
        research_default_label = "[*] Use Default" if not research_override else "[ ] Use Default"
        research_perplexity_label = "[*] Perplexity" if research_override == "perplexity" else "[ ] Perplexity"
        research_serper_label = "[*] Serper" if research_override == "serper" else "[ ] Serper"
        research_duckduckgo_label = "[*] DuckDuckGo" if research_override == "duckduckgo" else "[ ] DuckDuckGo"

        research_op.add(research_default_label, data={"type": "operator", "component": "researcher", "operator": "default", "model_type": "research"}, allow_expand=False)
        research_op.add(research_perplexity_label, data={"type": "operator", "component": "researcher", "operator": "perplexity", "model_type": "research"}, allow_expand=False)
        research_op.add(research_serper_label, data={"type": "operator", "component": "researcher", "operator": "serper", "model_type": "research"}, allow_expand=False)
        research_op.add(research_duckduckgo_label, data={"type": "operator", "component": "researcher", "operator": "duckduckgo", "model_type": "research"}, allow_expand=False)
        research.add("Model Selection", data={"type": "model", "component": "researcher", "model_type": "research"}, allow_expand=False)

        # Secretary component
        secretary = self.root.add("Secretary", expand=False, data={"type": "component", "id": "secretary"})
        secretary.add("Settings", data={"type": "settings", "component": "secretary"})
        models = secretary.add("Models", expand=False, data={"type": "models_branch", "component": "secretary"})
        analysis = models.add("Analysis Model", expand=False, data={"type": "model_group", "component": "secretary", "model_type": "analysis"})
        analysis.add("Model Selection", data={"type": "model", "component": "secretary", "model_type": "analysis"}, allow_expand=False)

        # Prompts component
        prompts = self.root.add("Prompts", expand=False, data={"type": "component", "id": "prompts"})
        prompts.add("Settings", data={"type": "settings", "component": "prompts"})
        models = prompts.add("Models", expand=False, data={"type": "models_branch", "component": "prompts"})
        generation = models.add("Generation Model", expand=False, data={"type": "model_group", "component": "prompts", "model_type": "generation"})
        generation.add("Model Selection", data={"type": "model", "component": "prompts", "model_type": "generation"}, allow_expand=False)


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

    def show_info(self, info: str) -> None:
        """Show info panel."""
        self.remove_children()
        self.mount(InfoPanel(info))


class ModernConfigApp(App):
    """Modern TUI configurator."""

    CSS = """
    Screen {
        background: $surface;
    }

    #logo {
        height: 2;
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
        width: 50%;
        height: 100%;
        border: solid cyan;
        padding: 1;
    }

    #right-panel {
        width: 50%;
        height: 100%;
        border: solid green;
        padding: 1;
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
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, config_path: str | None = None):
        super().__init__()
        self.config_manager = ConfigManager(config_path)
        self.title = "Ninja MCP Configurator"
        self.sub_title = "Modern Tree-Based Configuration"

    def _create_logo(self) -> str:
        """Create gradient logo text."""
        # NINJA-MCP with gradient from turquoise to lilac using Rich markup
        # Using color codes that work well in terminals
        return "[bold cyan]N[/bold cyan][bold bright_cyan]I[/bold bright_cyan][bold blue]N[/bold blue][bold bright_blue]J[/bold bright_blue][bold magenta]A[/bold magenta][bold bright_magenta]-[/bold bright_magenta][bold magenta]M[/bold magenta][bold bright_magenta]C[/bold bright_magenta][bold magenta]P[/bold magenta]"

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

        elif node_type == "global_credentials":
            # Show global credentials panel
            context = {
                "component": "global",
            }
            right_panel.show_settings(context)

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
            expanded.append(tuple(current_path + [node.data]))

        for child in node.children:
            expanded.extend(self._get_expanded_paths(child, current_path + [node.data] if node.data else []))

        return expanded

    def _restore_expanded_state(self, node, expanded_paths: list[tuple], current_path: list) -> None:
        """Recursively restore expanded state to matching nodes."""
        if node.data:
            current_tuple = tuple(current_path + [node.data])
            # Check if this node's path was expanded
            if current_tuple in expanded_paths:
                node.expand()

        for child in node.children:
            self._restore_expanded_state(
                child,
                expanded_paths,
                current_path + [node.data] if node.data else []
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
