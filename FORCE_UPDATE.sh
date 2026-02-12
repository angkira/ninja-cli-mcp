#!/usr/bin/env bash
#
# ПОЛНАЯ ПЕРЕУСТАНОВКА ninja-mcp с сохранением credentials
# Используй ЭТОТ скрипт на другой машине
#

set -e

echo ""
echo "========================================================================"
echo "  🔄 NINJA-MCP FORCE UPDATE"
echo "========================================================================"
echo ""

# Проверяем что мы в репозитории
if [ ! -f "pyproject.toml" ] || ! grep -q "ninja-mcp" pyproject.toml; then
    echo "❌ ERROR: This script must be run from ninja-cli-mcp repository root!"
    echo ""
    echo "Current directory: $(pwd)"
    echo ""
    echo "Please cd to the repository first:"
    echo "  cd /path/to/ninja-cli-mcp"
    echo "  ./FORCE_UPDATE.sh"
    exit 1
fi

echo "✓ Running from repository: $(pwd)"
echo ""

# Шаг 1: Backup credentials
echo "📥 Step 1: Backing up credentials..."
if [ -f ~/.ninja/credentials.db ]; then
    TIMESTAMP=$(date +%s)
    cp ~/.ninja/credentials.db ~/.ninja/credentials.db.backup-${TIMESTAMP}
    echo "  ✓ Backed up to ~/.ninja/credentials.db.backup-${TIMESTAMP}"
elif [ -f ~/.ninja-mcp.env ]; then
    TIMESTAMP=$(date +%s)
    cp ~/.ninja-mcp.env ~/.ninja-mcp.env.backup-${TIMESTAMP}
    echo "  ✓ Backed up to ~/.ninja-mcp.env.backup-${TIMESTAMP}"
else
    echo "  ℹ️  No credentials found to backup"
fi
echo ""

# Шаг 2: Git pull
echo "📥 Step 2: Pulling latest code..."
git fetch origin
git pull origin main
echo "  ✓ Code updated"
echo ""

# Шаг 3: Полностью удаляем старую установку
echo "🗑️  Step 3: Removing old installation..."
uv tool uninstall ninja-mcp 2>/dev/null || echo "  ℹ️  Package wasn't installed"
echo "  ✓ Old installation removed"
echo ""

# Шаг 4: Чистим кеш
echo "🧹 Step 4: Cleaning cache..."
rm -rf ~/.cache/ninja-mcp 2>/dev/null || true
echo "  ✓ Cache cleaned"
echo ""

# Шаг 5: Устанавливаем заново ИЗ ТЕКУЩЕЙ ДИРЕКТОРИИ
echo "📦 Step 5: Installing from current directory..."
echo "  Installing from: $(pwd)"
uv tool install --force .
echo "  ✓ Package installed"
echo ""

# Шаг 6: Проверяем что установилось
echo "🔍 Step 6: Verifying installation..."
SITE_PACKAGES=$(find ~/.local/share/uv/tools/ninja-mcp/lib/python*/site-packages -type d -name "ninja_config" 2>/dev/null | head -1)

if [ -n "$SITE_PACKAGES" ] && [ -d "$SITE_PACKAGES/ui" ]; then
    if grep -q "POWER CONFIGURATOR" "$SITE_PACKAGES/ui/main_menu.py" 2>/dev/null; then
        echo "  ✅ NEW UI code installed correctly!"
    else
        echo "  ⚠️  Warning: UI code might be old"
    fi
else
    echo "  ⚠️  Warning: UI module not found"
fi
echo ""

# Шаг 7: Мигрируем credentials если нужно
echo "🔄 Step 7: Checking credential migration..."
if [ -f ~/.ninja-mcp.env ] && [ ! -f ~/.ninja/credentials.db ]; then
    echo "  Running migration..."
    python3 -c "
from ninja_config.config_migrator import ConfigMigrator
migrator = ConfigMigrator()
if migrator.needs_migration():
    result = migrator.migrate()
    print(f'  ✓ Migrated {result[\"credentials_count\"]} credentials')
else:
    print('  ℹ️  No migration needed')
" 2>/dev/null || echo "  ℹ️  Migration skipped (run ninja-config configure to complete)"
else
    echo "  ℹ️  No migration needed"
fi
echo ""

# Шаг 8: Обновляем MCP config
echo "⚙️  Step 8: Updating MCP configuration..."
if [ -f ~/.claude.json ]; then
    cp ~/.claude.json ~/.claude.json.backup-$(date +%s)
    echo "  ℹ️  MCP config backed up"
    echo "  ℹ️  Run 'ninja-config configure' to update MCP settings"
else
    echo "  ℹ️  No .claude.json found"
fi
echo ""

# Шаг 9: Перезапускаем daemons
echo "🔄 Step 9: Restarting daemons..."
ninja-daemon restart
echo "  ✓ Daemons restarted"
echo ""

# Шаг 10: Финальная проверка
echo "✅ Step 10: Final verification..."
ninja-daemon status || echo "  ⚠️  Check daemon status manually"
echo ""

echo "========================================================================"
echo "  ✅ UPDATE COMPLETE!"
echo "========================================================================"
echo ""
echo "NOW RUN:"
echo "  ninja-config configure"
echo ""
echo "You should see the NEW modular interface with:"
echo "  • 📋 Configuration Overview"
echo "  • 🎯 Coder Setup flow"
echo "  • 🤖 Dynamic model selection"
echo "  • And more..."
echo ""
echo "If you STILL see old interface, send me the output of:"
echo "  ./diagnose_installation.sh"
echo ""
