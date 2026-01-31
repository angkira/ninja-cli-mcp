#!/usr/bin/env python3
"""
Integration test for GeminiStrategy with NinjaDriver.
"""

import sys
from pathlib import Path


# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ninja_coder.driver import NinjaConfig, NinjaDriver


def test_driver_with_gemini():
    """Test that NinjaDriver correctly uses GeminiStrategy."""
    print("\n=== Testing NinjaDriver with Gemini ===")

    config = NinjaConfig(
        bin_path="gemini",
        openai_api_key="test-key",
        openai_base_url="https://openrouter.ai/api/v1",
        model="google/gemini-2.0-flash-exp",
        timeout_sec=300,
    )

    driver = NinjaDriver(config)

    print(f"✅ Driver created with strategy: {driver._strategy.name}")
    print(f"  Strategy capabilities: {driver._strategy.capabilities}")

    # Test that strategy is used in command building
    instruction = {
        "type": "task",
        "description": "Write a hello world function",
        "file_scope": {"context_paths": ["test.py"]},
    }

    # Test prompt building
    prompt = driver._build_prompt_text(instruction, "/tmp/test")
    print("✅ Prompt built successfully")
    print(f"  Prompt length: {len(prompt)} chars")

    # Test strategy command building
    cli_result = driver._strategy.build_command(
        prompt=prompt,
        repo_root="/tmp/test",
        file_paths=["test.py"],
        model=config.model,
    )

    print("✅ Strategy command built successfully")
    print(f"  Command: {' '.join(cli_result.command)}")
    print(f"  Working dir: {cli_result.working_dir}")
    print(f"  Has env vars: {len(cli_result.env)} vars")

    # Verify command uses gemini binary
    assert "gemini" in cli_result.command[0], "Command should use gemini binary"
    assert "--model" in cli_result.command, "Command should have --model flag"
    assert config.model in cli_result.command, "Command should have model name"
    assert "--message" in cli_result.command, "Command should have --message flag"

    print("✅ All assertions passed!")

    return True


if __name__ == "__main__":
    try:
        if test_driver_with_gemini():
            print("\n✅ Integration test passed!")
            sys.exit(0)
        else:
            print("\n❌ Integration test failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Integration test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
