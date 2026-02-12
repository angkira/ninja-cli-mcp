# Migration Guide for Other Machine

**Date:** 2026-02-12
**Status:** Ready for deployment
**Target:** Machine with 100% sequential task failure rate

## What Happened on This Machine

The migration system **exists** and **works correctly** when run, but was **not triggered automatically** during the update. This caused credentials to be "lost" (actually just not migrated).

After manually running the migration:
- ✅ All credentials recovered
- ✅ Properly encrypted in database
- ✅ System working correctly

## Migration System Details

### How It Works

The `ConfigMigrator` class in `src/ninja_config/config_migrator.py`:

1. **Detection**: Checks if `~/.ninja-mcp.env` exists AND `~/.ninja/config.json` doesn't
2. **Backup**: Copies `.env` to `~/.ninja/config.backup/ninja-mcp.env.TIMESTAMP`
3. **Parse**: Reads old `.env` file (handles `export KEY=value` and `KEY=value`)
4. **Extract Credentials**: Identifies keys containing:
   - `API_KEY`
   - `_KEY`
   - `PASSWORD`
   - `SECRET`
   - `TOKEN`
5. **Encrypt & Store**: Saves credentials to `~/.ninja/credentials.db` (encrypted)
6. **Save Config**: Saves settings to `~/.ninja/config.json`
7. **Mark Migrated**: Renames `.env` to `.env.migrated`

### What Gets Migrated

**Credentials** (encrypted in SQLite):
- `OPENROUTER_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `PERPLEXITY_API_KEY`
- `SERPER_API_KEY`
- Any other `*_KEY`, `*_TOKEN`, `*_SECRET`, `*_PASSWORD`

**Settings** (in JSON):
- `NINJA_CODE_BIN`
- `NINJA_PERPLEXITY_MODEL`
- Port configurations
- Daemon settings
- Everything else

### Safety Mechanisms

1. **Backup First**: Old config always backed up before migration
2. **Atomic Operations**: Uses SQLite transactions
3. **Encryption**: AES-256-GCM with machine-specific key derivation
4. **No Deletion**: Original file renamed, not deleted
5. **Migration Log**: Creates detailed log in `~/.ninja/migrations/`

## Pre-Migration Checklist for Other Machine

### Step 1: Verify What Will Be Migrated

**BEFORE pulling updates**, run the verification script:

```bash
cd /path/to/ninja-cli-mcp
python3 verify_migration.py
```

This will show:
- What credentials will be migrated
- What settings will be migrated
- If migration will run or be skipped
- What backups will be created

### Step 2: Manual Backup (CRITICAL)

```bash
# Backup your credentials
cp ~/.ninja-mcp.env ~/.ninja-mcp.env.manual-backup-$(date +%Y%m%d)

# Make it secure
chmod 600 ~/.ninja-mcp.env.manual-backup-*

# Verify backup
cat ~/.ninja-mcp.env.manual-backup-* | grep API_KEY
```

### Step 3: Check Current State

```bash
# Check what's in your current .env
cat ~/.ninja-mcp.env | grep -E "KEY|TOKEN|SECRET"

# Count credentials
cat ~/.ninja-mcp.env | grep -E "KEY|TOKEN|SECRET" | grep -v "^#" | wc -l

# Check if new config already exists
ls -la ~/.ninja/config.json ~/.ninja/credentials.db
```

### Step 4: Update Ninja-MCP

```bash
cd /path/to/ninja-cli-mcp
git pull
uv tool install --reinstall --force .
```

**IMPORTANT**: Watch the output! If you see:
```
NINJA CONFIGURATION MIGRATION
===============================
Migrating from legacy .env to new JSON+SQLite format...
```

The migration is running. ✅

If you DON'T see this, the migration was skipped (probably because config already exists).

### Step 5: Verify Migration

```bash
# Check credentials were migrated
python3 <<'EOF'
import sys
from pathlib import Path
sys.path.insert(0, 'src')
from ninja_config.credentials import CredentialManager

manager = CredentialManager()

# List expected credentials
expected_keys = [
    'OPENROUTER_API_KEY',
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'PERPLEXITY_API_KEY',
]

print("Verifying migrated credentials:\n")
for key_name in expected_keys:
    try:
        value = manager.get(key_name)
        if value:
            print(f"✓ {key_name}: Found ({len(value)} chars)")
        else:
            print(f"✗ {key_name}: Not found")
    except Exception as e:
        print(f"✗ {key_name}: Error - {e}")
EOF
```

### Step 6: Update MCP Config

The MCP config (`~/.claude.json`) needs to be updated with the migrated credentials:

```bash
python3 <<'EOF'
import json
import sys
from pathlib import Path

sys.path.insert(0, 'src')
from ninja_config.credentials import CredentialManager

config_path = Path.home() / '.claude.json'
backup_path = Path.home() / '.claude.json.backup-pre-migration'

# Backup
with open(config_path) as f:
    config = json.load(f)
with open(backup_path, 'w') as f:
    json.dump(config, f, indent=2)
print(f'✓ Backed up to {backup_path}')

# Get credentials
manager = CredentialManager()
openrouter_key = manager.get('OPENROUTER_API_KEY')

if not openrouter_key:
    print('✗ ERROR: OPENROUTER_API_KEY not found!')
    sys.exit(1)

# Update servers
mcpServers = config.get('mcpServers', {})
for server_name in ['ninja-coder', 'ninja-researcher', 'ninja-secretary', 'ninja-prompts']:
    if server_name in mcpServers:
        if 'env' not in mcpServers[server_name]:
            mcpServers[server_name]['env'] = {}
        mcpServers[server_name]['env']['OPENROUTER_API_KEY'] = openrouter_key
        mcpServers[server_name]['env']['OPENAI_API_KEY'] = openrouter_key
        mcpServers[server_name]['env']['OPENAI_BASE_URL'] = 'https://openrouter.ai/api/v1'
        print(f'✓ Updated {server_name}')

# Save
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
print(f'\n✓ Updated {config_path}')
EOF
```

### Step 7: Restart Daemons

```bash
ninja-daemon restart
sleep 2
ninja-daemon status
```

### Step 8: Verify Everything Works

```bash
# Test that sequential tasks work now
# (they should no longer hang with the timeout fixes)
```

## If Migration Fails

### Recovery Steps

1. **Check Backup**:
   ```bash
   ls -la ~/.ninja/config.backup/
   cat ~/.ninja/config.backup/ninja-mcp.env.* | grep API_KEY
   ```

2. **Check Manual Backup**:
   ```bash
   cat ~/.ninja-mcp.env.manual-backup-* | grep API_KEY
   ```

3. **Manually Add Credentials**:
   ```bash
   python3 <<'EOF'
   import sys
   sys.path.insert(0, 'src')
   from ninja_config.credentials import CredentialManager

   manager = CredentialManager()

   # Add your credentials
   manager.set('OPENROUTER_API_KEY', 'sk-or-v1-...your-key...')
   # manager.set('OTHER_API_KEY', '...')

   print('✓ Credentials stored')
   EOF
   ```

4. **Verify**:
   ```bash
   # Check database directly
   sqlite3 ~/.ninja/credentials.db "SELECT name FROM credentials"
   ```

## Expected Results

### Before Migration
- ❌ Sequential tasks: 100% failure rate
- ❌ Tasks timeout after 120s of no output
- ❌ Dialogue mode always fails
- ✓ Credentials in `~/.ninja-mcp.env`

### After Migration
- ✅ Sequential tasks: Complete successfully (timeout fixes)
- ✅ Proper timeouts (900s for sequential)
- ✅ Dialogue mode works
- ✅ Credentials in encrypted database
- ✅ Old config backed up

## Files to Check

### Before Update
- `~/.ninja-mcp.env` - Your credentials (should exist)
- `~/.claude.json` - MCP config

### After Update
- `~/.ninja/credentials.db` - Encrypted credentials (created)
- `~/.ninja/config.json` - Configuration (created)
- `~/.ninja/config.backup/ninja-mcp.env.TIMESTAMP` - Backup (created)
- `~/.ninja-mcp.env.migrated` - Old config (renamed)
- `~/.ninja/migrations/migration_*.json` - Migration log (created)

## Troubleshooting

### "Migration not running"

**Symptom**: No migration output during installation

**Cause**: `~/.ninja/config.json` already exists

**Fix**:
```bash
# If you're sure you want to re-migrate:
mv ~/.ninja/config.json ~/.ninja/config.json.old
# Then reinstall
uv tool install --reinstall --force .
```

### "Credentials not found after migration"

**Symptom**: MCP doctor shows no credentials

**Cause 1**: Migration didn't run
**Fix**: See "Migration not running" above

**Cause 2**: MCP config not updated
**Fix**: Run Step 6 above to update `.claude.json`

**Cause 3**: Credentials weren't in old .env
**Fix**: Check manual backup and add manually (Step 3 in "If Migration Fails")

### "Permission denied on credentials.db"

**Symptom**: Can't read/write credentials

**Fix**:
```bash
chmod 600 ~/.ninja/credentials.db
chown $USER ~/.ninja/credentials.db
```

## Summary

The migration system **DOES work correctly** but has one failure mode:
- ❌ Not automatically triggered during installation
- ✅ Works perfectly when run manually
- ✅ Creates backups
- ✅ Encrypts credentials
- ✅ Preserves all data

**For the other machine:**
1. ✅ Run `verify_migration.py` FIRST
2. ✅ Create manual backup
3. ✅ Pull updates
4. ✅ Verify migration ran
5. ✅ Update MCP config
6. ✅ Restart daemons
7. ✅ Test sequential tasks

**If you follow these steps, all credentials will be safely migrated.**
