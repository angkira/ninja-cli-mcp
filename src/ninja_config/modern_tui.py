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

    def __init__(self, context: dict) -> None:
        super().__init__()
        self.context = context
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
            content = f"[bold]{name}[/bold]\n[dim]{model_id}[/dim]\n[dim italic]{desc}[/dim]"
            item = ListItem(Static(content))
            item.model_id = model_id
            list_view.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle model selection."""
        if hasattr(event.item, "model_id"):
            # TODO: Save selected model to config
            self.app.bell()


class SettingsPanel(Widget):
    """Panel for configuring settings and API keys."""

    def __init__(self, context: dict) -> None:
        super().__init__()
        self.context = context

    def compose(self) -> ComposeResult:
        """Compose the settings panel."""
        component = self.context.get("component", "")
        operator = self.context.get("operator", "")

        yield Label("[bold cyan]Settings & Credentials[/bold cyan]", id="settings-title")
        yield Label(
            f"[dim]Component: {component.title() if component else 'N/A'}[/dim]",
            id="settings-context",
        )

        # API Key input
        yield Label("API Key:", classes="field-label")
        yield Input(
            placeholder="Enter API key...",
            password=True,
            id="api-key-input",
        )

        # Operator-specific settings
        yield Label("Operator Settings:", classes="field-label")
        yield Input(
            placeholder="Base URL (optional)...",
            id="base-url-input",
        )

        # Save button
        yield Button("Save Settings", variant="primary", id="save-settings-btn")


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

    def __init__(self) -> None:
        super().__init__("Ninja MCP Configuration")
        self.root.expand()
        self._build_tree()

    def _build_tree(self) -> None:
        """Build the configuration tree."""
        # Coder component
        coder = self.root.add("Coder", expand=False, data={"type": "component", "id": "coder"})

        # Operator branch
        op_branch = coder.add("Operator", expand=False, data={"type": "operator_branch", "component": "coder"})
        op_branch.add("Aider", data={"type": "operator", "component": "coder", "operator": "aider"})
        op_branch.add("OpenCode", data={"type": "operator", "component": "coder", "operator": "opencode"})

        # Settings branch
        coder.add("Settings", data={"type": "settings", "component": "coder"})

        # Models branch
        models = coder.add("Models", expand=False, data={"type": "models_branch", "component": "coder"})
        models.add("Quick Tasks", data={"type": "model", "component": "coder", "model_type": "quick"})
        models.add("Sequential Tasks", data={"type": "model", "component": "coder", "model_type": "sequential"})
        models.add("Parallel Tasks", data={"type": "model", "component": "coder", "model_type": "parallel"})

        # Researcher component
        researcher = self.root.add("Researcher", expand=False, data={"type": "component", "id": "researcher"})

        op_branch = researcher.add("Operator", expand=False, data={"type": "operator_branch", "component": "researcher"})
        op_branch.add("Perplexity", data={"type": "operator", "component": "researcher", "operator": "perplexity"})
        op_branch.add("Serper", data={"type": "operator", "component": "researcher", "operator": "serper"})
        op_branch.add("DuckDuckGo", data={"type": "operator", "component": "researcher", "operator": "duckduckgo"})

        researcher.add("Settings", data={"type": "settings", "component": "researcher"})

        models = researcher.add("Models", expand=False, data={"type": "models_branch", "component": "researcher"})
        models.add("Research Model", data={"type": "model", "component": "researcher", "model_type": "research"})

        # Secretary component
        secretary = self.root.add("Secretary", expand=False, data={"type": "component", "id": "secretary"})
        secretary.add("Settings", data={"type": "settings", "component": "secretary"})
        models = secretary.add("Models", expand=False, data={"type": "models_branch", "component": "secretary"})
        models.add("Analysis Model", data={"type": "model", "component": "secretary", "model_type": "analysis"})

        # Prompts component
        prompts = self.root.add("Prompts", expand=False, data={"type": "component", "id": "prompts"})
        prompts.add("Settings", data={"type": "settings", "component": "prompts"})
        models = prompts.add("Models", expand=False, data={"type": "models_branch", "component": "prompts"})
        models.add("Generation Model", data={"type": "model", "component": "prompts", "model_type": "generation"})


class RightPanel(Container):
    """Dynamic right panel that changes based on tree selection."""

    def __init__(self) -> None:
        super().__init__(id="right-panel")
        self.current_panel = None

    def show_model_search(self, context: dict) -> None:
        """Show model search panel."""
        self.remove_children()
        self.mount(ModelSearchPanel(context))

    def show_settings(self, context: dict) -> None:
        """Show settings panel."""
        self.remove_children()
        self.mount(SettingsPanel(context))

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
                yield ConfigTree()

            # Right: Dynamic panel
            yield RightPanel()

        yield Footer()

    def on_mount(self) -> None:
        """Initialize right panel."""
        right_panel = self.query_one(RightPanel)
        right_panel.show_info("[dim]Select an item from the tree to configure[/dim]")

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """Handle tree node selection."""
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
