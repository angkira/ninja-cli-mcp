#!/usr/bin/env python3
"""
Manual test for GeminiStrategy to debug issues.
Run this with: python test_gemini_manual.py
"""

import sys
from pathlib import Path


# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ninja_coder.driver import NinjaConfig
from ninja_coder.strategies.registry import CLIStrategyRegistry


def test_gemini_strategy_initialization():
    """Test that GeminiStrategy can be initialized."""
    print("\n=== Test 1: GeminiStrategy Initialization ===")

    # Create a test config
    config = NinjaConfig(
        bin_path="gemini",  # This should trigger gemini strategy
        openai_api_key="test-key",
        openai_base_url="https://openrouter.ai/api/v1",
        model="google/gemini-2.0-flash-exp",
        timeout_sec=300,
    )

    try:
        strategy = CLIStrategyRegistry.get_strategy(config.bin_path, config)
        print(f"✅ Strategy created: {strategy.name}")
        print(f"✅ Strategy type: {type(strategy).__name__}")
        print(f"✅ Capabilities: {strategy.capabilities}")
        return True
    except Exception as e:
        print(f"❌ Failed to create strategy: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_gemini_command_building():
    """Test that GeminiStrategy can build commands."""
    print("\n=== Test 2: Command Building ===")

    config = NinjaConfig(
        bin_path="gemini",
        openai_api_key="test-key",
        openai_base_url="https://openrouter.ai/api/v1",
        model="google/gemini-2.0-flash-exp",
        timeout_sec=300,
    )

    try:
        strategy = CLIStrategyRegistry.get_strategy(config.bin_path, config)

        # Try to build a command
        result = strategy.build_command(
            prompt="Write a hello world function in Python",
            repo_root="/tmp/test",
            file_paths=["test.py"],
            model=None,
        )

        print("✅ Command built successfully")
        print(f"  Command: {' '.join(result.command)}")
        print(f"  Working dir: {result.working_dir}")
        print(f"  Metadata: {result.metadata}")

        # Check if command looks correct
        if "gemini" not in ' '.join(result.command):
            print("⚠️  Warning: 'gemini' not found in command")
            return False

        if "--model" not in result.command:
            print("⚠️  Warning: '--model' not found in command")
            return False

        if "--message" not in result.command:
            print("⚠️  Warning: '--message' not found in command")
            return False

        return True
    except Exception as e:
        print(f"❌ Failed to build command: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_gemini_output_parsing():
    """Test that GeminiStrategy can parse output."""
    print("\n=== Test 3: Output Parsing ===")

    config = NinjaConfig(
        bin_path="gemini",
        openai_api_key="test-key",
        openai_base_url="https://openrouter.ai/api/v1",
        model="google/gemini-2.0-flash-exp",
        timeout_sec=300,
    )

    try:
        strategy = CLIStrategyRegistry.get_strategy(config.bin_path, config)

        # Test successful output
        stdout = """
        Modified file: test.py
        Successfully updated 1 file
        """
        result = strategy.parse_output(stdout, "", 0)

        print("✅ Parsed success output")
        print(f"  Success: {result.success}")
        print(f"  Summary: {result.summary}")
        print(f"  Touched paths: {result.touched_paths}")

        if not result.success:
            print(f"⚠️  Expected success=True, got {result.success}")
            return False

        # Test error output
        stderr = "Error: API rate limit exceeded"
        result = strategy.parse_output("", stderr, 1)

        print("✅ Parsed error output")
        print(f"  Success: {result.success}")
        print(f"  Retryable: {result.retryable_error}")
        print(f"  Notes: {result.notes}")

        if result.success:
            print(f"⚠️  Expected success=False for error, got {result.success}")
            return False

        return True
    except Exception as e:
        print(f"❌ Failed to parse output: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_driver_uses_strategy():
    """Test that NinjaDriver actually uses the strategy."""
    print("\n=== Test 4: Driver Strategy Integration ===")

    from ninja_coder.driver import NinjaDriver

    config = NinjaConfig(
        bin_path="gemini",
        openai_api_key="test-key",
        openai_base_url="https://openrouter.ai/api/v1",
        model="google/gemini-2.0-flash-exp",
        timeout_sec=300,
    )

    try:
        driver = NinjaDriver(config)

        print("✅ Driver created")
        print(f"  Strategy name: {driver._strategy.name}")

        if driver._strategy.name != "gemini":
            print(f"⚠️  Expected strategy name 'gemini', got '{driver._strategy.name}'")
            return False

        # Check if _detect_cli_type() returns gemini
        cli_type = driver._detect_cli_type()
        print(f"  Detected CLI type: {cli_type}")

        if cli_type != "gemini":
            print(f"⚠️  Expected CLI type 'gemini', got '{cli_type}'")
            return False

        return True
    except Exception as e:
        print(f"❌ Failed to test driver: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Gemini Strategy Manual Test Suite")
    print("=" * 60)

    results = []

    results.append(("Initialization", test_gemini_strategy_initialization()))
    results.append(("Command Building", test_gemini_command_building()))
    results.append(("Output Parsing", test_gemini_output_parsing()))
    results.append(("Driver Integration", test_driver_uses_strategy()))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)

    print("=" * 60)
    if all_passed:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)
