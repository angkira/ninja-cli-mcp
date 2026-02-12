#!/usr/bin/env bash
#
# Убивает все зависшие ninja-config процессы и запускает заново
#

echo "======================================================================"
echo "  🔪 KILLING OLD PROCESSES"
echo "======================================================================"
echo ""

# Найти и убить все ninja-config процессы
echo "Looking for ninja-config processes..."
PIDS=$(ps aux | grep "ninja-config" | grep -v grep | grep -v kill_and_restart | awk '{print $2}')

if [ -n "$PIDS" ]; then
    echo "Found processes: $PIDS"
    for PID in $PIDS; do
        echo "Killing PID $PID..."
        kill -9 $PID 2>/dev/null || true
    done
    echo "✓ Killed all old processes"
else
    echo "✓ No old processes found"
fi

echo ""
echo "======================================================================"
echo "  ✅ NOW RUN IN YOUR TERMINAL:"
echo "======================================================================"
echo ""
echo "  ninja-config configure"
echo ""
echo "You should see the NEW interface with POWER CONFIGURATOR!"
echo ""
