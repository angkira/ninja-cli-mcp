"""
TUI installer for ninja-mcp — uses shared config code with configurator.

Reuses: config_shared (API keys, tool/IDE detection), ConfigManager (saves),
        defaults (models, ports), secrets_store (API key storage).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any


try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator
except ImportError:
    print("InquirerPy required. Install with: pip install InquirerPy")
    sys.exit(1)

from ninja_common.config_manager import ConfigManager
from ninja_common.defaults import (
    OPENROUTER_MODELS,
    PERPLEXITY_MODELS,
    ZAI_MODELS,
)
from ninja_config.config_shared import (
    CODER_API_KEYS,
    DAEMON_CONFIG,
    RESEARCHER_API_KEYS,
    APIKeyDef,
    check_python,
    check_uv,
    detect_ides,
    detect_tools,
    get_secret,
    install_uv,
    mask_key,
    register_claude_mcp,
    save_secret,
)


def _exec(result: Any) -> Any:
    return result.execute() if hasattr(result, "execute") else result


class TUIInstaller:
    def __init__(self) -> None:
        self.config_mgr = ConfigManager()
        self.config = self.config_mgr.list_all()
        self.modules: list[str] = []
        self.tools = detect_tools()
        self.ides = detect_ides()

    def _save(self, key: str, value: str) -> None:
        self.config_mgr.set(key, value)
        self.config[key] = value

    def _save_batch(self, updates: dict[str, str]) -> None:
        self.config_mgr.update(updates)
        self.config.update(updates)

    # ── System checks ────────────────────────────────────────────────

    def run(self) -> int:
        self._header()

        if not check_python():
            return 1
        print(f"  ✓ Python {sys.version_info.major}.{sys.version_info.minor}")

        if not check_uv():
            print("  uv not found. Installing...")
            if not install_uv():
                print("  ✗ Failed to install uv")
                return 1
        print(f"  ✓ uv {shutil.which('uv')}")

        if self.tools:
            print(f"  Tools: {', '.join(self.tools.keys())}")
        if self.ides:
            print(f"  IDEs:  {', '.join(self.ides.keys())}")

        self._select_modules()

        if not self._install_package():
            return 1

        if "coder" in self.modules:
            self._configure_coder()

        if "researcher" in self.modules:
            self._configure_researcher()

        self._configure_models()
        self._configure_daemon()
        selected_ides = self._configure_ide()
        self._register_ides(selected_ides)
        self._verify()
        self._summary(selected_ides)
        return 0

    def _header(self) -> None:
        print("\n" + "═" * 60)
        print("  🥷 NINJA MCP — TUI INSTALLER")
        print("═" * 60)

    # ── Modules ──────────────────────────────────────────────────────

    def _select_modules(self) -> None:
        result = inquirer.select(
            message="📦 Installation type:",
            choices=[
                Choice(value="full", name="Full  •  All modules"),
                Choice(value="minimal", name="Minimal  •  Coder + resources"),
                Choice(value="custom", name="Custom  •  Pick modules"),
            ],
            pointer="►",
        )
        install_type = _exec(result)

        if install_type == "full":
            self.modules = ["coder", "researcher", "secretary", "resources", "prompts"]
        elif install_type == "minimal":
            self.modules = ["coder", "resources"]
        else:
            all_mods = [
                ("coder", "AI code assistant"),
                ("researcher", "Web research & search"),
                ("secretary", "File ops & analysis"),
                ("resources", "Resource templates"),
                ("prompts", "Prompt management"),
            ]
            choices = [
                Choice(value=n, name=f"{n.title()}  •  {d}", enabled=True)
                for n, d in all_mods
            ]
            result = inquirer.checkbox(
                message="🎯 Modules:", choices=choices,
                pointer="►", instruction="Space to toggle, Enter to confirm",
            )
            self.modules = _exec(result) or ["coder", "resources"]

        print(f"  Modules: {', '.join(self.modules)}")

    # ── Install package ──────────────────────────────────────────────

    def _install_package(self) -> bool:
        print("\n🔄 Installing ninja-mcp...")
        extras = f"[{','.join(self.modules)}]"

        from pathlib import Path
        cwd = Path.cwd()
        if (cwd / "pyproject.toml").exists():
            cmd = ["uv", "tool", "install", "--force", f"{cwd}{extras}"]
        else:
            cmd = ["uv", "tool", "install", "--force", f"ninja-mcp{extras}"]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print("  ✓ ninja-mcp installed")
            return True
        print(f"  ✗ Install failed: {result.stderr}")
        return False

    # ── Coder config ─────────────────────────────────────────────────

    def _configure_coder(self) -> None:
        print("\n" + "─" * 50)
        print("  💻 CODER MODULE")
        print("─" * 50)

        tool_choices: list[Any] = []
        for name, path in self.tools.items():
            tool_choices.append(Choice(value=name, name=f"{name.title()}  (detected: {path})"))
        for name, desc in [
            ("aider", "Aider Chat  •  OpenRouter"),
            ("opencode", "OpenCode  •  Multi-provider CLI"),
            ("gemini", "Gemini CLI  •  Google models"),
            ("cursor", "Cursor  •  AI-powered IDE"),
        ]:
            if name not in self.tools:
                tool_choices.append(Choice(value=name, name=desc))
        tool_choices.append(Separator())
        tool_choices.append(Choice(value="__custom", name="Custom path"))

        result = inquirer.select(message="Code CLI:", choices=tool_choices, pointer="►")
        selected = _exec(result)

        if selected == "__custom":
            result = inquirer.text(message="Path to code CLI:")
            code_cli = _exec(result)
        else:
            code_cli = selected

        self._save("NINJA_CODE_BIN", code_cli)

        if code_cli == "aider" and not shutil.which("aider"):
            print("  Installing aider...")
            subprocess.run(
                ["pipx", "install", "aider-chat"],
                capture_output=True, text=True, check=False,
            )

        print("\n  🔑 Coder API Keys")
        for key_def in CODER_API_KEYS:
            self._ask_key(key_def)

    def _ask_key(self, key_def: APIKeyDef) -> None:
        existing = get_secret(key_def.env_var)
        if existing:
            masked = mask_key(existing)
            result = inquirer.confirm(
                message=f"  Use existing {key_def.display_name} ({masked})?",
                default=True,
            )
            if _exec(result):
                return

        result = inquirer.secret(
            message=f"  {key_def.display_name} API key (for {key_def.module}):",
            instruction=f"Get from {key_def.url}  •  Enter to skip",
        )
        val = _exec(result)
        if val:
            save_secret(key_def.env_var, val)

    # ── Researcher config ────────────────────────────────────────────

    def _configure_researcher(self) -> None:
        print("\n" + "─" * 50)
        print("  🔬 RESEARCHER MODULE")
        print("─" * 50)

        result = inquirer.select(
            message="  Search provider:",
            choices=[
                Choice(value="duckduckgo", name="DuckDuckGo  •  Free, no key needed"),
                Choice(value="serper", name="Serper.dev  •  Google Search API"),
                Choice(value="perplexity", name="Perplexity AI  •  AI-powered research"),
            ],
            pointer="►",
        )
        provider = _exec(result)
        self._save("NINJA_SEARCH_PROVIDER", provider)

        for key_def in RESEARCHER_API_KEYS:
            needed = (
                (provider == "serper" and key_def.env_var == "SERPER_API_KEY")
                or (provider == "perplexity" and key_def.env_var == "PERPLEXITY_API_KEY")
            )
            if needed:
                self._ask_key(key_def)

    # ── Models ───────────────────────────────────────────────────────

    def _configure_models(self) -> None:
        print("\n" + "─" * 50)
        print("  🤖 MODEL SELECTION")
        print("─" * 50)

        for module in self.modules:
            if module not in ("coder", "researcher", "secretary"):
                continue

            key = f"NINJA_{module.upper()}_MODEL"

            if module == "researcher":
                model_list = PERPLEXITY_MODELS
            else:
                model_list = OPENROUTER_MODELS

            choices: list[Any] = [
                Choice(
                    value=mid,
                    name=f"{mname:25} • {mdesc}",
                )
                for mid, mname, mdesc in model_list
            ]

            if module == "coder":
                choices.append(Separator("── Z.AI / GLM ──"))
                for mid, mname, mdesc in ZAI_MODELS:
                    choices.append(Choice(value=mid, name=f"{mname:25} • {mdesc}"))

            choices.append(Separator())
            choices.append(Choice(value="__custom", name="Custom model"))

            result = inquirer.select(
                message=f"  {module.title()} model:",
                choices=choices,
                pointer="►",
            )
            selected = _exec(result)

            if selected == "__custom":
                result = inquirer.text(
                    message=f"  Custom model for {module}:",
                    instruction="e.g. anthropic/claude-opus-4",
                )
                selected = _exec(result)

            if selected:
                self._save(key, selected)

    # ── Daemon ───────────────────────────────────────────────────────

    def _configure_daemon(self) -> None:
        print("\n" + "─" * 50)
        print("  ⚙️  DAEMON MODE")
        print("─" * 50)

        result = inquirer.confirm(
            message="  Enable daemon mode? (recommended)",
            default=True,
        )
        if _exec(result):
            self._save_batch(DAEMON_CONFIG)
        else:
            self._save("NINJA_ENABLE_DAEMON", "false")

    # ── IDE ───────────────────────────────────────────────────────────

    def _configure_ide(self) -> list[str]:
        if not self.ides:
            return []

        print("\n" + "─" * 50)
        print("  🖥️  IDE INTEGRATION")
        print("─" * 50)

        choices = [
            Choice(value=ide_id, name=f"{ide_id.title()}  •  {path}")
            for ide_id, path in self.ides.items()
        ]
        result = inquirer.checkbox(
            message="  Select IDEs to configure:",
            choices=choices, pointer="►",
        )
        selected = _exec(result)
        return selected if selected else []

    def _register_ides(self, ides: list[str]) -> None:
        for ide in ides:
            if ide == "claude":
                count = register_claude_mcp()
                print(f"  ✓ Claude Code: {count}/3 servers registered")
            else:
                print(f"  ⚠ {ide}: use ninja-config configure for setup")

    # ── Verify & Summary ─────────────────────────────────────────────

    def _verify(self) -> None:
        print("\n🔍 Verifying...")
        for cmd in ("ninja-config", "ninja-coder", "ninja-researcher", "ninja-secretary"):
            if shutil.which(cmd):
                print(f"  ✓ {cmd}")
            else:
                print(f"  ✗ {cmd} not found")

    def _summary(self, ides: list[str]) -> None:
        print("\n" + "═" * 60)
        print("  🎉 INSTALLATION COMPLETE!")
        print("═" * 60)

        cli = self.config.get("NINJA_CODE_BIN", "")
        search = self.config.get("NINJA_SEARCH_PROVIDER", "")
        if cli:
            print(f"  Code CLI:     {cli}")
        if search:
            print(f"  Search:       {search}")
        for m in self.modules:
            if m in ("coder", "researcher", "secretary"):
                model = self.config.get(f"NINJA_{m.upper()}_MODEL", "")
                if model:
                    print(f"  {m:14s}{model}")
        if ides:
            print(f"  IDEs:         {', '.join(ides)}")

        print(f"\n  Config: {self.config_mgr.config_file}")
        print("  Next: ninja-config configure  |  ninja-config doctor\n")


def _get_env(key: str) -> str:
    import os
    return os.environ.get(key, "")


def run_tui_installer() -> int:
    return TUIInstaller().run()


if __name__ == "__main__":
    sys.exit(run_tui_installer())
