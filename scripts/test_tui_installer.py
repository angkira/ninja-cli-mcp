#!/usr/bin/env python3
"""
Test script for the TUI installer.
"""

import sys
from pathlib import Path


# Add src to path so we can import ninja_config modules
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

try:
    from ninja_config.tui_installer import run_tui_installer

    print("✅ TUI Installer imported successfully")

    # Run a basic test (this will exit the script)
    print("🏃 Running TUI installer test...")
    result = run_tui_installer()
    print(f"🏁 TUI installer finished with result: {result}")

except ImportError as e:
    print(f"❌ Failed to import TUI installer: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error running TUI installer: {e}")
    sys.exit(1)
