#!/usr/bin/env bash
#
# Диагностика установки ninja-mcp
# Проверяет что именно не обновилось и почему
#

set -e

echo ""
echo "========================================================================"
echo "  🔍 NINJA-MCP INSTALLATION DIAGNOSTICS"
echo "========================================================================"
echo ""

# 1. Проверяем где установлены бинарники
echo "📍 Step 1: Checking binary locations..."
echo ""

NINJA_CONFIG_PATH=$(which ninja-config 2>/dev/null || echo "NOT FOUND")
echo "  ninja-config binary: $NINJA_CONFIG_PATH"

if [ "$NINJA_CONFIG_PATH" != "NOT FOUND" ]; then
    NINJA_CONFIG_REAL=$(readlink -f "$NINJA_CONFIG_PATH" 2>/dev/null || readlink "$NINJA_CONFIG_PATH" 2>/dev/null || echo "$NINJA_CONFIG_PATH")
    echo "  Real path: $NINJA_CONFIG_REAL"
fi
echo ""

# 2. Проверяем версию установленного пакета
echo "📦 Step 2: Checking installed package version..."
echo ""

uv tool list 2>&1 | grep -A 3 ninja-mcp || echo "  ⚠️  ninja-mcp not installed via uv tool"
echo ""

# 3. Проверяем где находятся Python модули
echo "🐍 Step 3: Checking Python module locations..."
echo ""

SITE_PACKAGES=$(find ~/.local/share/uv/tools/ninja-mcp/lib/python*/site-packages -type d -name "ninja_config" 2>/dev/null | head -1)

if [ -n "$SITE_PACKAGES" ]; then
    echo "  Python modules: $SITE_PACKAGES"

    # Проверяем есть ли новый UI
    if [ -d "$SITE_PACKAGES/ui" ]; then
        echo "  ✓ UI module exists: $SITE_PACKAGES/ui"

        # Проверяем содержимое main_menu.py
        if [ -f "$SITE_PACKAGES/ui/main_menu.py" ]; then
            if grep -q "NINJA MCP POWER CONFIGURATOR" "$SITE_PACKAGES/ui/main_menu.py"; then
                echo "  ✓ New UI code detected (POWER CONFIGURATOR message found)"
            else
                echo "  ✗ OLD UI code detected (no POWER CONFIGURATOR message)"
            fi
        else
            echo "  ✗ main_menu.py not found"
        fi
    else
        echo "  ✗ UI module NOT found - OLD installation!"
    fi
else
    echo "  ⚠️  No ninja_config module found in uv tools"
fi
echo ""

# 4. Проверяем откуда запускается ninja-config
echo "🔎 Step 4: Testing which Python environment is used..."
echo ""

if [ "$NINJA_CONFIG_PATH" != "NOT FOUND" ]; then
    # Запускаем ninja-config и смотрим откуда импортируется модуль
    python_path=$(head -1 "$NINJA_CONFIG_REAL" | sed 's/#!//')
    echo "  Python interpreter: $python_path"

    # Проверяем sys.path
    "$python_path" -c "import sys; print('  sys.path:'); [print(f'    - {p}') for p in sys.path if 'ninja' in p.lower()]" 2>/dev/null || true
fi
echo ""

# 5. Проверяем credentials и config
echo "💾 Step 5: Checking credentials and config..."
echo ""

if [ -f ~/.ninja/credentials.db ]; then
    echo "  ✓ Credentials database: ~/.ninja/credentials.db"
    echo "    Size: $(ls -lh ~/.ninja/credentials.db | awk '{print $5}')"
else
    echo "  ✗ No credentials.db found"
fi

if [ -f ~/.ninja/config.json ]; then
    echo "  ✓ Config file: ~/.ninja/config.json"
else
    echo "  ℹ️  No config.json (using .ninja-mcp.env)"
fi

if [ -f ~/.ninja-mcp.env ]; then
    echo "  ✓ Old config file: ~/.ninja-mcp.env (should be migrated)"
fi
echo ""

# 6. Проверяем git репозиторий
echo "📂 Step 6: Checking repository..."
echo ""

if [ -d .git ]; then
    echo "  ✓ Git repository found"
    echo "  Current directory: $(pwd)"
    echo "  Current branch: $(git branch --show-current)"
    echo "  Latest commit: $(git log -1 --oneline)"

    # Проверяем есть ли uncommitted changes
    if [ -n "$(git status --porcelain)" ]; then
        echo "  ⚠️  You have uncommitted changes"
    fi
else
    echo "  ⚠️  Not in git repository!"
    echo "  Current directory: $(pwd)"
    echo ""
    echo "  🚨 YOU MUST RUN THIS FROM THE REPOSITORY DIRECTORY!"
fi
echo ""

# 7. РЕКОМЕНДАЦИИ
echo "========================================================================"
echo "  📋 RECOMMENDATIONS"
echo "========================================================================"
echo ""

if [ ! -d .git ]; then
    echo "❌ ERROR: You are NOT in the ninja-cli-mcp repository directory!"
    echo ""
    echo "You MUST cd to the repository first:"
    echo "  cd /path/to/ninja-cli-mcp"
    echo ""
    echo "Then run this diagnostic script again."
    exit 1
fi

if [ ! -d "$SITE_PACKAGES/ui" ] || ! grep -q "POWER CONFIGURATOR" "$SITE_PACKAGES/ui/main_menu.py" 2>/dev/null; then
    echo "🔄 SOLUTION: Your installation is OUTDATED. Update it:"
    echo ""
    echo "  # Make sure you're in the repo directory"
    echo "  cd $(pwd)"
    echo ""
    echo "  # Update the repository"
    echo "  git pull"
    echo ""
    echo "  # FORCE reinstall from THIS directory"
    echo "  uv tool install --reinstall --force ."
    echo ""
    echo "  # Restart daemons"
    echo "  ninja-daemon restart"
    echo ""
else
    echo "✅ Your installation looks CORRECT!"
    echo ""
    echo "If you still see old UI, try:"
    echo "  1. Kill all ninja processes: pkill -9 -f ninja"
    echo "  2. Clear cache: rm -rf ~/.cache/ninja-mcp"
    echo "  3. Restart daemons: ninja-daemon restart"
    echo "  4. Run: ninja-config configure"
fi

echo ""
echo "========================================================================"
