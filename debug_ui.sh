#!/usr/bin/env bash
#
# Проверяет ЧТО РЕАЛЬНО запускается когда ты вызываешь ninja-config
#

echo "======================================================================"
echo "  🔍 DEBUGGING NINJA-CONFIG UI"
echo "======================================================================"
echo ""

echo "1. Checking which ninja-config is being used:"
which ninja-config
echo ""

echo "2. Checking real path:"
ls -la $(which ninja-config)
echo ""

echo "3. Checking Python interpreter:"
head -1 $(readlink -f $(which ninja-config) 2>/dev/null || readlink $(which ninja-config) 2>/dev/null || which ninja-config)
echo ""

echo "4. Testing show_welcome() directly:"
~/.local/share/uv/tools/ninja-mcp/bin/python3 -c "
from ninja_config.ui.main_menu import show_welcome
print('===== OUTPUT FROM show_welcome(): =====')
show_welcome()
print('===== END OF OUTPUT =====')
"
echo ""

echo "5. Checking what's in interactive_configurator:"
grep -A 3 "def run_power_configurator" ~/.local/share/uv/tools/ninja-mcp/lib/python3.12/site-packages/ninja_config/interactive_configurator.py | head -5
echo ""

echo "6. Checking for any other ninja-config installations:"
find /usr/local/bin ~/.local -name "ninja-config" 2>/dev/null
echo ""

echo "7. Checking for running ninja processes:"
ps aux | grep -i ninja | grep -v grep || echo "No ninja processes running"
echo ""

echo "======================================================================"
echo "  ℹ️  NOW RUN THIS IN YOUR TERMINAL:"
echo "======================================================================"
echo ""
echo "  ninja-config configure"
echo ""
echo "And tell me EXACTLY what you see in the first 5 lines."
echo ""
