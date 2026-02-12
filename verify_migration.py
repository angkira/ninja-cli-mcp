#!/usr/bin/env python3
"""
Pre-migration verification script for ninja-mcp.

Run this BEFORE updating on your other machine to verify what will be migrated.
This script is READ-ONLY and makes no changes to your system.

Usage:
    python3 verify_migration.py
"""

import os
import sys
from pathlib import Path


def main():
    print("\n" + "=" * 70)
    print("  NINJA-MCP PRE-MIGRATION VERIFICATION")
    print("=" * 70)
    print("\nThis script checks what will be migrated. NO CHANGES will be made.\n")

    # Check for old .env file
    old_env = Path.home() / ".ninja-mcp.env"
    print(f"📁 Checking for old config: {old_env}")

    if not old_env.exists():
        print("   ✗ Old config file NOT found")
        print("   ℹ️  Migration not needed - you may be starting fresh\n")
        return

    print(f"   ✓ Found (size: {old_env.stat().st_size} bytes)")
    print(f"   ℹ️  Last modified: {Path(old_env).stat().st_mtime}")

    # Parse and show what will be migrated
    print("\n📋 Parsing configuration...")

    credentials_found = []
    settings_found = []

    with open(old_env, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Remove 'export ' prefix if present
            line = line.replace('export ', '', 1).strip()

            # Split on first '=' only
            if '=' not in line:
                continue

            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            # Skip if value is empty
            if not value:
                continue

            # Check if it's a credential
            credential_indicators = ["API_KEY", "_KEY", "PASSWORD", "SECRET", "TOKEN"]
            is_credential = any(indicator in key for indicator in credential_indicators)

            if is_credential:
                credentials_found.append((key, len(value)))
            else:
                settings_found.append((key, value))

    # Report findings
    print("\n" + "=" * 70)
    print("  MIGRATION PREVIEW")
    print("=" * 70)

    print(f"\n🔑 CREDENTIALS (will be encrypted in database):")
    if credentials_found:
        for cred_name, cred_len in credentials_found:
            print(f"   ✓ {cred_name} ({cred_len} characters)")
    else:
        print("   ⚠️  No credentials found")

    print(f"\n⚙️  SETTINGS (will be in JSON config):")
    if settings_found:
        for setting_name, setting_value in settings_found:
            # Truncate long values
            display_value = setting_value[:50] + '...' if len(setting_value) > 50 else setting_value
            print(f"   • {setting_name}: {display_value}")
    else:
        print("   ℹ️  No additional settings found")

    # Check what already exists
    print(f"\n📂 Checking existing new-format files:")

    new_config = Path.home() / ".ninja" / "config.json"
    creds_db = Path.home() / ".ninja" / "credentials.db"

    print(f"   Config: {new_config}")
    if new_config.exists():
        print(f"      ⚠️  ALREADY EXISTS (size: {new_config.stat().st_size} bytes)")
        print(f"      Migration will be SKIPPED (config already migrated)")
    else:
        print(f"      ✓ Does not exist (migration will proceed)")

    print(f"   Credentials: {creds_db}")
    if creds_db.exists():
        print(f"      ℹ️  Exists (size: {creds_db.stat().st_size} bytes)")
        print(f"      Migration will add to existing database")
    else:
        print(f"      ✓ Does not exist (will be created)")

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    print(f"\n✓ Found {len(credentials_found)} credential(s) to migrate")
    print(f"✓ Found {len(settings_found)} setting(s) to migrate")

    if new_config.exists():
        print("\n⚠️  WARNING: New config already exists!")
        print("   Migration will be SKIPPED because:")
        print("   - ConfigMigrator.needs_migration() checks for existing config")
        print("   - It only migrates if old exists AND new doesn't exist")
        print("\n   If you need to re-migrate:")
        print(f"   1. Backup: cp {new_config} {new_config}.backup")
        print(f"   2. Remove: rm {new_config}")
        print("   3. Update ninja-mcp (migration will auto-run)")
    else:
        print("\n✓ Migration will proceed automatically when you update")
        print("\nWhat will happen:")
        print("   1. Old .env backed up to ~/.ninja/config.backup/")
        print("   2. Credentials encrypted and stored in SQLite")
        print("   3. Settings saved to ~/.ninja/config.json")
        print("   4. Old .env renamed to .env.migrated")

    # Create backup recommendation
    print("\n" + "=" * 70)
    print("  RECOMMENDED ACTIONS BEFORE UPDATE")
    print("=" * 70)
    print("\n1. Manually backup your credentials:")
    print(f"   cp {old_env} {old_env}.manual-backup")
    print("\n2. Update ninja-mcp:")
    print("   cd /path/to/ninja-cli-mcp")
    print("   git pull")
    print("   uv tool install --reinstall --force .")
    print("\n3. Verify migration succeeded:")
    print("   python3 -c \"")
    print("   import sys")
    print("   sys.path.insert(0, 'src')")
    print("   from ninja_config.credentials import CredentialManager")
    print("   m = CredentialManager()")
    for cred_name, _ in credentials_found:
        print(f"   assert m.get('{cred_name}'), '{cred_name} not found!'")
    print("   print('✓ All credentials verified')")
    print("   \"")

    print("\n" + "=" * 70)
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
