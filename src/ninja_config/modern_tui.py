"""Modern TUI configurator with collapsible tree and model search.

Features:
- Collapsible tree navigation (expand/collapse branches)
- Right panel for model search with autocomplete
- Input fields for API keys and settings
- Dynamic panels based on selection
"""

from __future__ import annotations

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
)
from textual.binding import Binding
from textual.widget import Widget
from rich.text import Text
from pathlib import Path

from ninja_common.config_manager import ConfigManager


# Mock model data (in real implementation, fetch from APIs)
AVAILABLE_MODELS = {
    "openrouter": [
        ("anthropic/claude-4", "Claude 4", "Most capable model"),
        ("anthropic/claude-3.5-sonnet", "Claude 3.5 Sonnet", "Fast and intelligent"),
        ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5", "Fast and affordable"),
        ("openai/gpt-4-turbo", "GPT-4 Turbo", "OpenAI's latest"),
        ("openai/gpt-4", "GPT-4", "Powerful reasoning"),
        ("google/gemini-2.0-flash-exp", "Gemini 2.0 Flash", "Fast and multimodal"),
        ("google/gemini-pro", "Gemini Pro", "Google's best"),
        ("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B", "Open source"),
        ("qwen/qwen-2.5-72b-instruct", "Qwen 2.5 72B", "Multilingual"),
    ],
    "perplexity": [
        ("sonar", "Sonar", "Online model with search"),
        ("sonar-pro", "Sonar Pro", "Advanced online model"),
    ],
}


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
                yield Label(f"Current: {current_model}", id="current-model")

        yield Input(placeholder="Search models...", id="model-search-input")

        with ScrollableContainer(id="model-results"):
            yield ListView(id="model-list")

    def on_mount(self) -> None:
        """Initialize with all models."""
        self._update_model_list("")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "model-search-input":
            self._update_model_list(event.value)

    def _update_model_list(self, query: str) -> None:
        """Update model list based on search query."""
        # Get models from appropriate provider
        provider = self.context.get("provider", "openrouter")
        all_models = AVAILABLE_MODELS.get(provider, [])

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

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle model selection."""
        if hasattr(event.item, "model_id") and self.config_manager:
            model_id = event.item.model_id
            component = self.context.get('component', '')
            model_type = self.context.get('model_type', '')

            # Save to config
            key = f"NINJA_{component.upper()}_MODEL_{model_type.upper()}"
            self.config_manager.set(key, model_id)

            # Show success
            self.app.bell()

            # Update current model display
            if self.is_mounted:
                try:
                    current_label = self.query_one("#current-model", Label)
                    current_label.update(f"Current: {model_id}")
                except Exception:
                    pass


class SettingsPanel(Widget):
    """Panel for configuring settings and API keys."""

    def __init__(self, context: dict, config_manager: ConfigManager) -> None:
        super().__init__()
        self.context = context
        self.config_manager = config_manager

    def compose(self) -> ComposeResult:
        """Compose the settings panel."""
        component = self.context.get("component", "")
        config = self.config_manager.list_all()

        # Check operator and provider
        operator = config.get(f"NINJA_{component.upper()}_OPERATOR", "")
        provider = config.get(f"NINJA_{component.upper()}_{operator.upper()}_PROVIDER", "") if operator == "opencode" else ""

        yield Label("[bold cyan]Settings & Credentials[/bold cyan]", id="settings-title")
        yield Label(
            f"[dim]Component: {component.title() if component else 'N/A'}[/dim]",
            id="settings-context",
        )

        # Show operator and provider
        if operator:
            operator_text = f"Operator: {operator.title()}"
            if provider:
                operator_text += f" ({provider.title()})"
            yield Label(operator_text, classes="field-label")

        # Get current API key based on operator/provider
        api_key = ""
        api_key_label = "API Key"

        if component == "coder" and operator == "opencode":
            # OpenCode uses provider-specific keys
            if provider == "openrouter":
                api_key = config.get("OPENROUTER_API_KEY", "")
                api_key_label = "OpenRouter API Key"
            elif provider == "anthropic":
                api_key = config.get("ANTHROPIC_API_KEY", "")
                api_key_label = "Anthropic API Key"
            elif provider == "openai":
                api_key = config.get("OPENAI_API_KEY", "")
                api_key_label = "OpenAI API Key"
            elif provider == "google":
                api_key = config.get("GOOGLE_API_KEY", "")
                api_key_label = "Google API Key"
        elif component == "coder":
            api_key = config.get("OPENROUTER_API_KEY", "")
        elif component == "researcher":
            api_key = config.get("PERPLEXITY_API_KEY", "") or config.get("SERPER_API_KEY", "")

        # Show masked current value
        if api_key:
            masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
            yield Label(f"Current: {masked}", classes="field-label")

        # API Key input
        yield Label(f"{api_key_label}:", classes="field-label")
        yield Input(
            placeholder="Enter new API key or leave blank to keep current...",
            password=True,
            id="api-key-input",
        )

        # Base URL (for OpenCode providers)
        if operator == "opencode":
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

    def _save_settings(self) -> None:
        """Save settings to config."""
        component = self.context.get("component", "")
        api_key_input = self.query_one("#api-key-input", Input)
        base_url_input = self.query_one("#base-url-input", Input)

        # Save API key if provided
        if api_key_input.value:
            if component == "coder":
                self.config_manager.set("OPENROUTER_API_KEY", api_key_input.value)
            elif component == "researcher":
                self.config_manager.set("PERPLEXITY_API_KEY", api_key_input.value)

        # Save base URL
        if base_url_input.value:
            self.config_manager.set(f"NINJA_{component.upper()}_BASE_URL", base_url_input.value)

        # Show success message
        self.app.bell()
        # TODO: Show notification


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
        research_op.add("Use Default", data={"type": "operator", "component": "researcher", "operator": "default", "model_type": "research"}, allow_expand=False)
        research_op.add("Perplexity", data={"type": "operator", "component": "researcher", "operator": "perplexity", "model_type": "research"}, allow_expand=False)
        research_op.add("Serper", data={"type": "operator", "component": "researcher", "operator": "serper", "model_type": "research"}, allow_expand=False)
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

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()

        with Horizontal(id="main-container"):
            # Left: Collapsible tree
            with Container(id="left-panel"):
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
        """Refresh tree to show updated selections."""
        tree = self.query_one(ConfigTree)

        # Rebuild tree with updated config
        tree.clear()
        tree.config = tree.config_manager.list_all()  # Reload config
        tree._build_tree()
        tree.root.expand()

        # Show notification
        self.notify("Selection saved!", severity="information", timeout=2)

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
