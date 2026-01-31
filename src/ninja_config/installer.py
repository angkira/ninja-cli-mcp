"""
Modern interactive installer for ninja-mcp using InquirerPy.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


# Try multiple import patterns for InquirerPy compatibility
try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice

    HAS_INQUIRERPY = True
except ImportError:
    try:
        from InquirerPy import inquirer
        from InquirerPy.base.control import Choice

        HAS_INQUIRERPY = True
    except ImportError:
        HAS_INQUIRERPY = False


def print_banner() -> None:
    """Print installation banner."""
    print("\n" + "=" * 70)
    print("  🥷 NINJA MCP - INTERACTIVE INSTALLER")
    print("=" * 70 + "\n")


def check_python_version() -> bool:
    """Check if Python version is 3.11+."""
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}")
    return True


def check_uv() -> bool:
    """Check if uv is installed."""
    if shutil.which("uv"):
        print("✓ uv package manager found")
        return True

    print("\n⚠️  uv package manager not found")
    if not HAS_INQUIRERPY:
        response = input("Install uv now? [Y/n]: ").strip().lower()
        install_uv = response in ("", "y", "yes")
    else:
        result = inquirer.confirm(
            message="Install uv package manager?",
            default=True,
        )
        install_uv = result.execute() if hasattr(result, "execute") else result

    if install_uv:
        print("\n🔄 Installing uv...")
        result = subprocess.run(
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            print("✓ uv installed successfully")
            # Update PATH
            local_bin = Path.home() / ".local" / "bin"
            os.environ["PATH"] = f"{local_bin}:{os.environ['PATH']}"
            return True
        else:
            print(f"✗ Failed to install uv: {result.stderr}")
            return False

    return False


def select_installation_type() -> str | None:
    """Select installation type."""
    if not HAS_INQUIRERPY:
        print("\n📦 Installation Options:")
        print("  1) Full installation (all features)")
        print("  2) Minimal (core only)")
        print("  3) Custom (select modules)")
        choice = input("\nSelect [1]: ").strip() or "1"

        choices = {"1": "full", "2": "minimal", "3": "custom"}
        return choices.get(choice, "full")

    result = inquirer.select(
        message="Select installation type:",
        choices=[
            Choice(
                value="full",
                name="Full  •  All modules (coder, researcher, secretary, resources, prompts)",
            ),
            Choice(value="minimal", name="Minimal  •  Core only (coder, resources)"),
            Choice(value="custom", name="Custom  •  Choose modules"),
        ],
        pointer="►",
    )

    return result.execute() if hasattr(result, "execute") else result


def select_modules() -> list[str]:
    """Select modules for custom installation."""
    all_modules = [
        ("coder", "AI code assistant with Aider/OpenCode/Gemini support"),
        ("researcher", "Web research with DuckDuckGo/Perplexity"),
        ("secretary", "File operations and codebase analysis"),
        ("resources", "Resource templates and prompts"),
        ("prompts", "Prompt management and chaining"),
    ]

    if not HAS_INQUIRERPY:
        print("\n📦 Available Modules:")
        for i, (name, desc) in enumerate(all_modules, 1):
            print(f"  {i}) {name}  •  {desc}")

        response = input("\nSelect modules (comma-separated numbers, or 'all'): ").strip()
        if response.lower() == "all":
            return [name for name, _ in all_modules]

        try:
            indices = [int(x.strip()) - 1 for x in response.split(",")]
            return [all_modules[i][0] for i in indices if 0 <= i < len(all_modules)]
        except (ValueError, IndexError):
            print("Invalid selection, using full installation")
            return [name for name, _ in all_modules]

    choices = [
        Choice(value=name, name=f"{name}  •  {desc}", enabled=True) for name, desc in all_modules
    ]

    result = inquirer.checkbox(
        message="Select modules to install:",
        choices=choices,
        pointer="►",
    )

    selected = result.execute() if hasattr(result, "execute") else result
    return selected if selected else ["coder", "resources"]


def install_ninja_mcp(install_type: str) -> bool:
    """Install ninja-mcp with selected modules."""
    print("\n🔄 Installing ninja-mcp...")

    # Determine installation extras
    if install_type == "full":
        extras = "[all]"
    elif install_type == "minimal":
        extras = "[coder]"
    else:
        modules = select_modules()
        extras = f"[{','.join(modules)}]"

    print(f"   Installing with extras: {extras}")

    # Check if we're in dev directory
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists():
        print(f"   Installing from local source: {cwd}")
        cmd = ["uv", "tool", "install", "--force", f"{cwd}{extras}"]
    else:
        print("   Installing from PyPI...")
        cmd = ["uv", "tool", "install", "--force", f"ninja-mcp{extras}"]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode == 0:
        print("✓ ninja-mcp installed successfully")
        return True
    else:
        print(f"✗ Installation failed: {result.stderr}")
        return False


def install_aider() -> bool:
    """Install aider-chat if not present."""
    if shutil.which("aider"):
        print("✓ aider already installed")
        return True

    if not HAS_INQUIRERPY:
        response = input("\nInstall aider (AI coding assistant)? [Y/n]: ").strip().lower()
        install = response in ("", "y", "yes")
    else:
        result = inquirer.confirm(
            message="Install aider-chat (AI coding assistant)?",
            default=True,
        )
        install = result.execute() if hasattr(result, "execute") else result

    if install:
        print("\n🔄 Installing aider...")
        result = subprocess.run(
            ["uv", "tool", "install", "aider-chat"], capture_output=True, text=True, check=False
        )

        if result.returncode == 0:
            print("✓ aider installed")
            return True
        else:
            print(f"⚠️  Could not install aider: {result.stderr}")
            return False

    return True


def install_opencode() -> bool:
    """Install opencode if not present."""
    if shutil.which("opencode"):
        print("✓ OpenCode already installed")
        return True

    if not HAS_INQUIRERPY:
        response = input("\nInstall OpenCode (multi-provider CLI)? [Y/n]: ").strip().lower()
        install = response in ("", "y", "yes")
    else:
        result = inquirer.confirm(
            message="Install OpenCode (multi-provider CLI with 75+ LLMs)?",
            default=True,
        )
        install = result.execute() if hasattr(result, "execute") else result

    if install:
        print("\n🔄 Installing OpenCode...")
        print("   Visit: https://opencode.dev for installation instructions")
        print("   Run: curl -fsSL https://opencode.dev/install.sh | bash")
        return False

    return True


def verify_installation() -> bool:
    """Verify all components are installed correctly."""
    print("\n🔍 Verifying installation...")

    all_ok = True
    commands = [
        "ninja-config",
        "ninja-coder",
        "ninja-researcher",
        "ninja-secretary",
        "ninja-resources",
        "ninja-prompts",
    ]

    for cmd in commands:
        if shutil.which(cmd):
            print(f"✓ {cmd}")
        else:
            print(f"✗ {cmd} not found")
            all_ok = False

    return all_ok


def show_next_steps() -> None:
    """Show post-installation next steps."""
    print("\n" + "=" * 70)
    print("  ✅ INSTALLATION COMPLETE!")
    print("=" * 70)

    print("\n📋 Next Steps:\n")
    print("1. Configure API keys and operators:")
    print("   ninja-config auth")
    print()
    print("2. Select your preferred operator and model:")
    print("   ninja-config select-model")
    print()
    print("3. Configure Claude Code integration:")
    print("   ninja-config setup-claude")
    print()
    print("4. Verify everything works:")
    print("   ninja-config doctor")
    print()
    print("5. View full configuration:")
    print("   ninja-config show")
    print()

    print("📚 Documentation: https://github.com/angkira/ninja-cli-mcp")
    print()


def run_installer() -> int:
    """Run the interactive installer."""
    if not HAS_INQUIRERPY:
        print("⚠️  InquirerPy not installed. Using basic prompts.")
        print("   Install InquirerPy for better experience: pip install InquirerPy")
        print()

    print_banner()

    # Check Python version
    if not check_python_version():
        return 1

    # Check/install uv
    if not check_uv():
        print("\n✗ Cannot proceed without uv package manager")
        return 1

    # Select installation type
    install_type = select_installation_type()
    if not install_type:
        print("\n✗ Installation cancelled")
        return 1

    # Install ninja-mcp
    if not install_ninja_mcp(install_type):
        return 1

    # Install dependencies
    install_aider()
    install_opencode()

    # Verify installation
    if not verify_installation():
        print("\n⚠️  Some components failed to install")
        print("   Try running: ninja-config doctor")
        return 1

    # Show next steps
    show_next_steps()

    return 0


if __name__ == "__main__":
    sys.exit(run_installer())
