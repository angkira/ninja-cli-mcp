#!/usr/bin/env python3
"""
Utility script to register ninja MCP servers with configuration files.
"""

import json
import os
import sys
from pathlib import Path


def update_mcp_config(config_path, server_name):
    """Update MCP configuration file with server registration."""

    config_file = Path(config_path)

    # Load existing config or create new one
    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {config_file}: {e}", file=sys.stderr)
            return False
    else:
        config = {}

    # Ensure mcpServers exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Add default environment variables based on server type
    env_vars = {}
    if server_name == "ninja-coder":
        env_vars = {
            "NINJA_CODER_MODEL": "google/gemini-2.0-flash-exp",
            "NINJA_CONFIG_NAME": "ninja-coder",
            "NINJA_CONFIG_PATH": str(config_path),
            "NINJA_CONFIG_VERSION": "1.0",
            "NINJA_CODE_BIN": "gemini",
            "NINJA_CODER_TIMEOUT": "300",
        }
    elif server_name == "ninja-researcher":
        env_vars = {
            "NINJA_RESEARCHER_MODEL": "google/gemini-2.0-flash-exp",
            "NINJA_RESEARCHER_MAX_SOURCES": "20",
            "NINJA_RESEARCHER_PARALLEL_AGENTS": "4",
        }
    elif server_name == "ninja-secretary":
        env_vars = {
            "NINJA_SECRETARY_MODEL": "google/gemini-2.0-flash-exp",
            "NINJA_SECRETARY_MAX_FILE_SIZE": "1048576",
        }
    elif server_name == "ninja-resources":
        env_vars = {
            "NINJA_RESOURCES_CACHE_TTL": "3600",
            "NINJA_RESOURCES_MAX_FILES": "1000",
        }
    elif server_name == "ninja-prompts":
        env_vars = {
            "NINJA_PROMPTS_MAX_SUGGESTIONS": "5",
            "NINJA_PROMPTS_CACHE_TTL": "3600",
        }

    # Get actual API key from environment
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")

    # Add API key if available
    if api_key:
        env_vars["OPENROUTER_API_KEY"] = api_key

    # Add or update server config
    server_config = {"command": "ninja-coder" if server_name == "ninja-coder" else server_name}

    if env_vars:
        server_config["env"] = env_vars

    config["mcpServers"][server_name] = server_config

    # Write with proper formatting
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        print(f"Updated {config_file} with {server_name}")
        return True
    except Exception as e:
        print(f"Error writing to {config_file}: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 update_mcp_config.py <config_path> <server_name>")
        sys.exit(1)

    config_path = sys.argv[1]
    server_name = sys.argv[2]

    success = update_mcp_config(config_path, server_name)
    sys.exit(0 if success else 1)
