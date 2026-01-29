#!/usr/bin/env bash
#
# install_daemon.sh - Install ninja-cli-mcp as a system daemon/service
#
# This script detects the init system and installs the appropriate service:
#   - systemd (Linux) - User service
#   - launchd (macOS) - Launch agent
#   - sysvinit/other - Simple background process with monitoring
#
# Usage: ./scripts/install_daemon.sh [start|stop|restart|status|uninstall]
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_NAME="ninja-cli-mcp"

# Detect init system
detect_init_system() {
    if command -v systemctl &>/dev/null && systemctl --version &>/dev/null; then
        echo "systemd"
    elif [[ "$OSTYPE" == "darwin"* ]] && command -v launchctl &>/dev/null; then
        echo "launchd"
    else
        echo "other"
    fi
}

# Install systemd user service
install_systemd() {
    info "Installing systemd user service..."
    
    # Create user systemd directory
    mkdir -p ~/.config/systemd/user
    
    # Generate service file with actual paths
    cat > ~/.config/systemd/user/${SERVICE_NAME}.service << EOF
[Unit]
Description=ninja-cli-mcp MCP Server
Documentation=https://github.com/angkira/ninja-cli-mcp
After=network.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_ROOT}
Environment="PATH=${HOME}/.local/bin:${HOME}/.nvm/versions/node/v25.0.0/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=-${HOME}/.ninja-cli-mcp.env
ExecStart=${PROJECT_ROOT}/scripts/run_server.sh
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${HOME}/.cache/ninja-cli-mcp

[Install]
WantedBy=default.target
EOF

    success "Service file created: ~/.config/systemd/user/${SERVICE_NAME}.service"
    
    # Reload systemd
    systemctl --user daemon-reload
    
    success "systemd user service installed"
    info "To enable on boot: systemctl --user enable ${SERVICE_NAME}"
}

# Install macOS launchd agent
install_launchd() {
    info "Installing macOS Launch Agent..."
    
    mkdir -p ~/Library/LaunchAgents
    
    # Generate plist
    cat > ~/Library/LaunchAgents/com.angkira.${SERVICE_NAME}.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.angkira.${SERVICE_NAME}</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>${PROJECT_ROOT}/scripts/run_server.sh</string>
    </array>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    
    <key>StandardOutPath</key>
    <string>${HOME}/Library/Logs/${SERVICE_NAME}.log</string>
    
    <key>StandardErrorPath</key>
    <string>${HOME}/Library/Logs/${SERVICE_NAME}.error.log</string>
    
    <key>WorkingDirectory</key>
    <string>${PROJECT_ROOT}</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

    success "Launch Agent created: ~/Library/LaunchAgents/com.angkira.${SERVICE_NAME}.plist"
    info "Logs will be in ~/Library/Logs/${SERVICE_NAME}.log"
}

# Install generic daemon (for systems without systemd/launchd)
install_generic() {
    warn "No systemd or launchd detected"
    info "Creating basic daemon script..."
    
    # Create a simple daemon wrapper
    cat > ~/.local/bin/${SERVICE_NAME}-daemon << 'EOF'
#!/usr/bin/env bash
# Simple daemon wrapper for ninja-cli-mcp

PIDFILE="$HOME/.cache/ninja-cli-mcp/daemon.pid"
LOGFILE="$HOME/.cache/ninja-cli-mcp/daemon.log"

mkdir -p "$(dirname "$PIDFILE")"
mkdir -p "$(dirname "$LOGFILE")"

case "${1:-start}" in
    start)
        if [[ -f "$PIDFILE" ]] && kill -0 $(cat "$PIDFILE") 2>/dev/null; then
            echo "Daemon already running (PID: $(cat "$PIDFILE"))"
            exit 1
        fi
        
        echo "Starting ninja-cli-mcp daemon..."
        nohup bash PROJECT_ROOT/scripts/run_server.sh >> "$LOGFILE" 2>&1 &
        echo $! > "$PIDFILE"
        echo "Started (PID: $(cat "$PIDFILE"))"
        echo "Logs: $LOGFILE"
        ;;
    
    stop)
        if [[ ! -f "$PIDFILE" ]]; then
            echo "Daemon not running"
            exit 1
        fi
        
        PID=$(cat "$PIDFILE")
        echo "Stopping ninja-cli-mcp daemon (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
        rm -f "$PIDFILE"
        echo "Stopped"
        ;;
    
    restart)
        "$0" stop
        sleep 2
        "$0" start
        ;;
    
    status)
        if [[ -f "$PIDFILE" ]] && kill -0 $(cat "$PIDFILE") 2>/dev/null; then
            echo "Daemon running (PID: $(cat "$PIDFILE"))"
        else
            echo "Daemon not running"
            exit 1
        fi
        ;;
    
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
EOF
    
    sed -i "s|PROJECT_ROOT|${PROJECT_ROOT}|g" ~/.local/bin/${SERVICE_NAME}-daemon
    chmod +x ~/.local/bin/${SERVICE_NAME}-daemon
    
    success "Daemon script created: ~/.local/bin/${SERVICE_NAME}-daemon"
    info "Usage: ${SERVICE_NAME}-daemon {start|stop|restart|status}"
}

# Start the service
start_service() {
    local init_system=$(detect_init_system)
    
    case "$init_system" in
        systemd)
            info "Starting systemd user service..."
            systemctl --user start ${SERVICE_NAME}
            systemctl --user status ${SERVICE_NAME} --no-pager || true
            success "Service started"
            ;;
        
        launchd)
            info "Loading Launch Agent..."
            launchctl load ~/Library/LaunchAgents/com.angkira.${SERVICE_NAME}.plist
            success "Service started"
            ;;
        
        other)
            ${SERVICE_NAME}-daemon start
            ;;
    esac
}

# Stop the service
stop_service() {
    local init_system=$(detect_init_system)
    
    case "$init_system" in
        systemd)
            info "Stopping systemd user service..."
            systemctl --user stop ${SERVICE_NAME}
            success "Service stopped"
            ;;
        
        launchd)
            info "Unloading Launch Agent..."
            launchctl unload ~/Library/LaunchAgents/com.angkira.${SERVICE_NAME}.plist 2>/dev/null || true
            success "Service stopped"
            ;;
        
        other)
            ${SERVICE_NAME}-daemon stop
            ;;
    esac
}

# Check service status
status_service() {
    local init_system=$(detect_init_system)
    
    case "$init_system" in
        systemd)
            systemctl --user status ${SERVICE_NAME} --no-pager
            ;;
        
        launchd)
            if launchctl list | grep -q "com.angkira.${SERVICE_NAME}"; then
                success "Service is running"
                launchctl list com.angkira.${SERVICE_NAME}
            else
                warn "Service is not running"
                exit 1
            fi
            ;;
        
        other)
            ${SERVICE_NAME}-daemon status
            ;;
    esac
}

# Uninstall the service
uninstall_service() {
    local init_system=$(detect_init_system)
    
    # Stop first
    stop_service 2>/dev/null || true
    
    case "$init_system" in
        systemd)
            info "Uninstalling systemd user service..."
            systemctl --user disable ${SERVICE_NAME} 2>/dev/null || true
            rm -f ~/.config/systemd/user/${SERVICE_NAME}.service
            systemctl --user daemon-reload
            success "Service uninstalled"
            ;;
        
        launchd)
            info "Uninstalling Launch Agent..."
            rm -f ~/Library/LaunchAgents/com.angkira.${SERVICE_NAME}.plist
            success "Service uninstalled"
            ;;
        
        other)
            info "Removing daemon script..."
            rm -f ~/.local/bin/${SERVICE_NAME}-daemon
            success "Daemon script removed"
            ;;
    esac
}

# Main
main() {
    local action="${1:-install}"
    local init_system=$(detect_init_system)
    
    echo ""
    echo "=========================================="
    echo "  ninja-cli-mcp Daemon Installer"
    echo "=========================================="
    echo ""
    
    info "Detected init system: $init_system"
    info "Project root: $PROJECT_ROOT"
    echo ""
    
    case "$action" in
        install)
            # Install based on system
            case "$init_system" in
                systemd)
                    install_systemd
                    echo ""
                    info "To start the service:"
                    echo "  systemctl --user start ${SERVICE_NAME}"
                    echo ""
                    info "To enable on boot:"
                    echo "  systemctl --user enable ${SERVICE_NAME}"
                    echo ""
                    info "To view logs:"
                    echo "  journalctl --user -u ${SERVICE_NAME} -f"
                    ;;
                
                launchd)
                    install_launchd
                    echo ""
                    info "To start the service:"
                    echo "  launchctl load ~/Library/LaunchAgents/com.angkira.${SERVICE_NAME}.plist"
                    echo ""
                    info "To view logs:"
                    echo "  tail -f ~/Library/Logs/${SERVICE_NAME}.log"
                    ;;
                
                other)
                    install_generic
                    echo ""
                    info "To start the daemon:"
                    echo "  ${SERVICE_NAME}-daemon start"
                    ;;
            esac
            ;;
        
        start)
            start_service
            ;;
        
        stop)
            stop_service
            ;;
        
        restart)
            stop_service
            sleep 2
            start_service
            ;;
        
        status)
            status_service
            ;;
        
        uninstall)
            uninstall_service
            ;;
        
        *)
            error "Unknown action: $action"
            echo ""
            echo "Usage: $0 [install|start|stop|restart|status|uninstall]"
            echo ""
            echo "Actions:"
            echo "  install    - Install the service (default)"
            echo "  start      - Start the service"
            echo "  stop       - Stop the service"
            echo "  restart    - Restart the service"
            echo "  status     - Check service status"
            echo "  uninstall  - Remove the service"
            exit 1
            ;;
    esac
    
    echo ""
}

main "$@"
