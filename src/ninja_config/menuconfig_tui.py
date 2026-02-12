"""MenuConfig-style TUI for Ninja MCP configuration.

Hierarchical menu navigation similar to Linux kernel menuconfig:
- Screen-based navigation (not tree)
- Enter to go deeper
- Esc/Back to go up
- Breadcrumbs showing current path
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, VerticalScroll
from textual.widgets import Header, Footer, Static, Button, Label, ListItem, ListView
from textual.binding import Binding
from textual.screen import Screen
from rich.text import Text
from rich.panel import Panel
from rich.align import Align
from pathlib import Path

from ninja_common.config_manager import ConfigManager


# Configuration structure
COMPONENTS = {
    "coder": {
        "name": "Coder Configuration",
        "description": "AI-powered code generation and modification",
        "operators": ["aider", "opencode", "custom"],
        "models": ["quick", "sequential", "parallel"],
    },
    "researcher": {
        "name": "Researcher Configuration",
        "description": "Web search and research capabilities",
        "operators": ["perplexity", "serper", "duckduckgo"],
        "models": ["research"],
    },
    "secretary": {
        "name": "Secretary Configuration",
        "description": "File operations and codebase analysis",
        "operators": ["default"],
        "models": ["analysis"],
    },
    "prompts": {
        "name": "Prompts Configuration",
        "description": "Prompt templates and management",
        "operators": ["default"],
        "models": ["generation"],
    },
}


class MenuItem:
    """Represents a menu item."""

    def __init__(
        self,
        label: str,
        description: str = "",
        action: str | None = None,
        submenu: str | None = None,
        data: dict | None = None,
    ):
        self.label = label
        self.description = description
        self.action = action  # Action to perform when selected
        self.submenu = submenu  # Submenu to navigate to
        self.data = data or {}


class MenuScreen(Screen):
    """Base screen for menu navigation."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", priority=True),
        Binding("q", "quit_app", "Quit", priority=True),
    ]

    def __init__(
        self,
        title: str,
        items: list[MenuItem],
        breadcrumb: str = "",
        config_manager: ConfigManager | None = None,
    ):
        super().__init__()
        self.title = title
        self.items = items
        self.breadcrumb = breadcrumb
        self.config_manager = config_manager

    def compose(self) -> ComposeResult:
        """Compose the menu screen."""
        # Breadcrumb
        if self.breadcrumb:
            yield Static(
                f"[dim]Ninja MCP[/dim] [cyan]>[/cyan] {self.breadcrumb}",
                id="breadcrumb",
            )

        # Title
        yield Static(f"[bold cyan]{self.title}[/bold cyan]", id="menu-title")

        # Menu items
        with VerticalScroll(id="menu-container"):
            list_view = ListView(id="menu-list")
            for item in self.items:
                # Create list item with description
                if item.description:
                    content = f"[bold]{item.label}[/bold]\n[dim]{item.description}[/dim]"
                else:
                    content = f"[bold]{item.label}[/bold]"

                list_item = ListItem(Static(content))
                list_item.item_data = item  # Store item data
                list_view.append(list_item)

            yield list_view

        # Status bar
        yield Static("[dim]Use arrows to navigate, Enter to select, Esc to go back[/dim]", id="status-bar")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle menu item selection."""
        item: MenuItem = event.item.item_data

        if item.submenu:
            # Navigate to submenu
            self._navigate_to_submenu(item)
        elif item.action:
            # Perform action
            self._perform_action(item)

    def _navigate_to_submenu(self, item: MenuItem) -> None:
        """Navigate to a submenu."""
        submenu_type = item.submenu
        new_breadcrumb = f"{self.breadcrumb} > {item.label}" if self.breadcrumb else item.label

        if submenu_type == "component_menu":
            # Component submenu (operator, settings, models)
            component_id = item.data["component_id"]
            screen = self._create_component_menu(component_id, new_breadcrumb)
            self.app.push_screen(screen)

        elif submenu_type == "operator_select":
            # Operator selection submenu
            component_id = item.data["component_id"]
            screen = self._create_operator_menu(component_id, new_breadcrumb)
            self.app.push_screen(screen)

        elif submenu_type == "model_select":
            # Model selection submenu
            component_id = item.data["component_id"]
            screen = self._create_model_menu(component_id, new_breadcrumb)
            self.app.push_screen(screen)

    def _create_component_menu(self, component_id: str, breadcrumb: str) -> MenuScreen:
        """Create component configuration menu."""
        comp_data = COMPONENTS[component_id]

        items = [
            MenuItem(
                "Operator Selection",
                f"Choose operator for {comp_data['name'].lower()}",
                submenu="operator_select",
                data={"component_id": component_id},
            ),
            MenuItem(
                "Operator Settings",
                "Configure operator-specific settings and credentials",
                action="configure_operator_settings",
                data={"component_id": component_id},
            ),
            MenuItem(
                "Model Configuration",
                "Configure models for different task types",
                submenu="model_select",
                data={"component_id": component_id},
            ),
        ]

        return MenuScreen(
            comp_data["name"],
            items,
            breadcrumb,
            self.config_manager,
        )

    def _create_operator_menu(self, component_id: str, breadcrumb: str) -> MenuScreen:
        """Create operator selection menu."""
        comp_data = COMPONENTS[component_id]

        items = [
            MenuItem(
                op.title(),
                f"Use {op} as operator",
                action="select_operator",
                data={"component_id": component_id, "operator": op},
            )
            for op in comp_data["operators"]
        ]

        return MenuScreen(
            "Select Operator",
            items,
            breadcrumb,
            self.config_manager,
        )

    def _create_model_menu(self, component_id: str, breadcrumb: str) -> MenuScreen:
        """Create model configuration menu."""
        comp_data = COMPONENTS[component_id]

        model_descriptions = {
            "quick": "Fast operations (syntax fixes, simple changes)",
            "sequential": "Complex multi-step tasks",
            "parallel": "Independent parallel operations",
            "research": "Web search and research",
            "analysis": "Code analysis and understanding",
            "generation": "Prompt generation",
        }

        items = [
            MenuItem(
                f"{model_type.replace('_', ' ').title()} Model",
                model_descriptions.get(model_type, f"Model for {model_type}"),
                action="configure_model",
                data={"component_id": component_id, "model_type": model_type},
            )
            for model_type in comp_data["models"]
        ]

        return MenuScreen(
            "Model Configuration",
            items,
            breadcrumb,
            self.config_manager,
        )

    def _perform_action(self, item: MenuItem) -> None:
        """Perform an action."""
        if item.action == "select_operator":
            # TODO: Implement operator selection dialog
            self.app.bell()
        elif item.action == "configure_operator_settings":
            # TODO: Implement settings dialog
            self.app.bell()
        elif item.action == "configure_model":
            # TODO: Implement model selection dialog
            self.app.bell()

    def action_quit_app(self) -> None:
        """Quit the application."""
        self.app.exit()


class MainMenuScreen(MenuScreen):
    """Main menu screen."""

    def __init__(self, config_manager: ConfigManager):
        items = [
            MenuItem(
                comp_data["name"],
                comp_data["description"],
                submenu="component_menu",
                data={"component_id": comp_id},
            )
            for comp_id, comp_data in COMPONENTS.items()
        ]

        # Add separator and global settings
        items.append(
            MenuItem(
                "────────────────────────────",
                "",
            )
        )
        items.append(
            MenuItem(
                "Global Settings",
                "System-wide configuration options",
                action="global_settings",
            )
        )

        super().__init__(
            "Ninja MCP Configuration",
            items,
            "",
            config_manager,
        )


class MenuConfigApp(App):
    """MenuConfig-style TUI application."""

    CSS = """
    Screen {
        background: $surface;
        padding: 1 2;
    }

    #breadcrumb {
        height: 1;
        margin-bottom: 1;
        color: $text-muted;
    }

    #menu-title {
        height: 3;
        content-align: center middle;
        text-style: bold;
    }

    #menu-container {
        height: 1fr;
        border: solid cyan;
        padding: 1;
    }

    #menu-list {
        background: $surface;
    }

    ListView > ListItem {
        padding: 1 2;
        height: auto;
    }

    ListView > ListItem:hover {
        background: $boost;
    }

    ListView > ListItem.-active {
        background: $primary;
    }

    #status-bar {
        height: 1;
        margin-top: 1;
        content-align: center middle;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
    ]

    def __init__(self, config_path: str | None = None):
        super().__init__()
        self.config_manager = ConfigManager(config_path)
        self.title = "Ninja MCP Configurator"

    def on_mount(self) -> None:
        """Mount the main menu screen."""
        self.push_screen(MainMenuScreen(self.config_manager))


def run_menuconfig_tui(config_path: str | None = None) -> int:
    """Run the menuconfig-style TUI.

    Args:
        config_path: Optional path to config file

    Returns:
        Exit code
    """
    app = MenuConfigApp(config_path)
    app.run()
    return 0
