"""Modern TUI configurator using Textual framework.

Provides tree-based navigation:
- Component selection (coder, researcher, secretary, prompts)
- Per-component operator configuration
- Per-operator model selection
- Hierarchical settings management
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, Tree, Button, Input, Select, Label
from textual.binding import Binding
from textual.screen import Screen
from rich.panel import Panel
from rich.text import Text
from rich.style import Style
from pathlib import Path
import json

from ninja_common.config_manager import ConfigManager


# Component configuration structure
COMPONENTS = {
    "coder": {
        "display_name": "Coder",
        "description": "AI-powered code generation and modification",
        "operators": {
            "aider": {
                "display_name": "Aider",
                "requires_api_key": True,
                "models": ["quick", "sequential", "parallel"],
            },
            "opencode": {
                "display_name": "OpenCode",
                "requires_api_key": True,
                "models": ["default"],
            },
        },
        "model_types": {
            "quick": "Fast operations (syntax fixes, simple changes)",
            "sequential": "Complex multi-step tasks",
            "parallel": "Independent parallel operations",
        },
    },
    "researcher": {
        "display_name": "Researcher",
        "description": "Web search and research capabilities",
        "operators": {
            "perplexity": {
                "display_name": "Perplexity AI",
                "requires_api_key": True,
                "models": ["research"],
            },
            "serper": {
                "display_name": "Serper (Google)",
                "requires_api_key": True,
                "models": ["research"],
            },
            "duckduckgo": {
                "display_name": "DuckDuckGo",
                "requires_api_key": False,
                "models": ["research"],
            },
        },
        "model_types": {
            "research": "Research and web search model",
        },
    },
    "secretary": {
        "display_name": "Secretary",
        "description": "File operations and codebase analysis",
        "operators": {
            "default": {
                "display_name": "Default",
                "requires_api_key": False,
                "models": ["analysis"],
            },
        },
        "model_types": {
            "analysis": "Code analysis and file operations",
        },
    },
    "prompts": {
        "display_name": "Prompts",
        "description": "Prompt templates and management",
        "operators": {
            "default": {
                "display_name": "Default",
                "requires_api_key": False,
                "models": ["generation"],
            },
        },
        "model_types": {
            "generation": "Prompt generation model",
        },
    },
}


class ConfigPanel(Static):
    """Panel showing current configuration status."""

    def __init__(self, config_manager: ConfigManager) -> None:
        super().__init__()
        self.config_manager = config_manager

    def compose(self) -> ComposeResult:
        config = self.config_manager.list_all()

        status_lines = []
        status_lines.append("[bold cyan]Current Configuration[/bold cyan]")
        status_lines.append("")

        # API Keys status
        api_keys = {k: v for k, v in config.items() if "API_KEY" in k}
        if api_keys:
            status_lines.append("[bold]API Keys:[/bold]")
            for key in api_keys:
                status_lines.append(f"  {key}: [green]Set[/green]")
        else:
            status_lines.append("[bold]API Keys:[/bold] [yellow]Not configured[/yellow]")

        status_lines.append("")

        # Component status
        for comp_id, comp_data in COMPONENTS.items():
            status_lines.append(f"[bold]{comp_data['display_name']}:[/bold]")
            operator = config.get(f"NINJA_{comp_id.upper()}_OPERATOR", "Not set")
            status_lines.append(f"  Operator: {operator}")

        yield Static("\n".join(status_lines))


class ComponentTree(Tree):
    """Tree widget for hierarchical component navigation."""

    def __init__(self) -> None:
        super().__init__("Ninja Components")
        self.root.expand()
        self._build_tree()

    def _build_tree(self) -> None:
        """Build component tree structure."""
        for comp_id, comp_data in COMPONENTS.items():
            # Add component node
            comp_node = self.root.add(
                f"[bold cyan]{comp_data['display_name']}[/bold cyan]",
                data={"type": "component", "id": comp_id},
            )
            comp_node.expand()

            # Add operator selection node
            op_node = comp_node.add(
                "[bold]Operator Selection[/bold]",
                data={"type": "operator_select", "component": comp_id},
            )

            # Add operators
            for op_id, op_data in comp_data["operators"].items():
                op_node.add(
                    f"{op_data['display_name']}",
                    data={
                        "type": "operator",
                        "component": comp_id,
                        "operator": op_id,
                    },
                )

            # Add settings node
            comp_node.add(
                "[bold]Settings & Credentials[/bold]",
                data={"type": "settings", "component": comp_id},
            )

            # Add models node
            models_node = comp_node.add(
                "[bold]Model Configuration[/bold]",
                data={"type": "models", "component": comp_id},
            )

            # Add model types
            for model_type, description in comp_data["model_types"].items():
                models_node.add(
                    f"{model_type.replace('_', ' ').title()}: {description}",
                    data={
                        "type": "model_type",
                        "component": comp_id,
                        "model_type": model_type,
                    },
                )


class DetailPanel(Static):
    """Panel showing details for selected tree item."""

    def __init__(self) -> None:
        super().__init__()
        self.current_selection = None

    def update_selection(self, node_data: dict | None) -> None:
        """Update panel content based on selected node."""
        if not node_data:
            self.update("[dim]Select an item from the tree[/dim]")
            return

        self.current_selection = node_data

        if node_data["type"] == "component":
            comp_data = COMPONENTS[node_data["id"]]
            content = f"""[bold cyan]{comp_data['display_name']}[/bold cyan]

{comp_data['description']}

[bold]Available Operators:[/bold]
{chr(10).join(f"  - {op['display_name']}" for op in comp_data['operators'].values())}

[bold]Model Types:[/bold]
{chr(10).join(f"  - {name.replace('_', ' ').title()}: {desc}" for name, desc in comp_data['model_types'].items())}
"""
            self.update(content)

        elif node_data["type"] == "operator":
            comp_data = COMPONENTS[node_data["component"]]
            op_data = comp_data["operators"][node_data["operator"]]
            content = f"""[bold]{op_data['display_name']}[/bold]

Component: {comp_data['display_name']}

API Key Required: {'Yes' if op_data['requires_api_key'] else 'No'}

Available Models:
{chr(10).join(f"  - {m.replace('_', ' ').title()}" for m in op_data['models'])}

[dim]Press Enter to configure[/dim]
"""
            self.update(content)

        elif node_data["type"] == "model_type":
            comp_data = COMPONENTS[node_data["component"]]
            model_desc = comp_data["model_types"][node_data["model_type"]]
            content = f"""[bold]{node_data['model_type'].replace('_', ' ').title()} Model[/bold]

Component: {comp_data['display_name']}
Purpose: {model_desc}

[dim]Press Enter to select model[/dim]
"""
            self.update(content)

        else:
            self.update(f"[dim]{node_data['type']}[/dim]")


class NinjaConfigApp(App):
    """Modern TUI configurator for Ninja MCP."""

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        layout: horizontal;
        height: 100%;
    }

    #left-panel {
        width: 40%;
        height: 100%;
        border: solid cyan;
        padding: 1;
    }

    #right-panel {
        width: 60%;
        height: 100%;
        layout: vertical;
    }

    #status-panel {
        height: 12;
        border: solid green;
        padding: 1;
        margin-bottom: 1;
    }

    #detail-panel {
        height: 1fr;
        border: solid blue;
        padding: 1;
    }

    Tree {
        background: $surface;
        color: $text;
    }

    Tree:focus {
        border: solid yellow;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("r", "refresh", "Refresh"),
        ("enter", "select", "Select"),
    ]

    def __init__(self, config_path: str | None = None):
        super().__init__()
        self.config_manager = ConfigManager(config_path)
        self.title = "Ninja MCP Configurator"
        self.sub_title = "Modern TUI Configuration Interface"

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()

        with Container(id="main-container"):
            # Left panel: Tree navigation
            with Vertical(id="left-panel"):
                yield ComponentTree()

            # Right panel: Status + Details
            with Vertical(id="right-panel"):
                with Container(id="status-panel"):
                    yield ConfigPanel(self.config_manager)

                with Container(id="detail-panel"):
                    yield DetailPanel()

        yield Footer()

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """Handle tree node selection."""
        detail_panel = self.query_one(DetailPanel)
        if event.node.data:
            detail_panel.update_selection(event.node.data)

    def action_select(self) -> None:
        """Handle Enter key on selected node."""
        tree = self.query_one(ComponentTree)
        if tree.cursor_node and tree.cursor_node.data:
            # TODO: Open configuration dialog based on node type
            pass

    def action_refresh(self) -> None:
        """Refresh configuration display."""
        config_panel = self.query_one(ConfigPanel)
        config_panel.refresh()


def run_modern_tui(config_path: str | None = None) -> int:
    """Run the modern TUI configurator.

    Args:
        config_path: Optional path to config file

    Returns:
        Exit code
    """
    app = NinjaConfigApp(config_path)
    app.run()
    return 0
