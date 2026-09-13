#!/usr/bin/env bash
#
# Ninja MCP - Bootstrap Installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash
#   ./install.sh              # TUI installer (default)
#   ./install.sh --auto       # Non-interactive / CI mode
#   ./install.sh --minimal    # Minimal install (coder only)
#
# This script:
#   1. Detects system requirements (Python 3.11+)
#   2. Installs ninja-mcp package into a managed venv
#   3. Launches TUI installer for API keys, models, IDE setup
#

set -euo pipefail

REPO_URL="${NINJA_REPO_URL:-https://github.com/angkira/ninja-cli-mcp.git}"
AUTO_MODE=false
MINIMAL_MODE=false
DOCKER_MODE=false
if [[ "${NINJA_DOCKER_NONINTERACTIVE:-0}" == "1" ]]; then
    DOCKER_MODE=true
fi

for arg in "$@"; do
    case "$arg" in
        --auto|--non-interactive|-y)
            AUTO_MODE=true
            ;;
        --minimal)
            MINIMAL_MODE=true
            ;;
        --help|-h)
            cat <<'HELP'
Ninja MCP installer

Usage: ./install.sh [--auto|--minimal]

The interactive installer asks whether to install natively or use an isolated
Docker deployment. Docker automation is available only through an internal
backend environment, not a public command-line option.
HELP
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n' "$arg" >&2
            printf 'Usage: ./install.sh [--auto|--minimal]\n' >&2
            exit 2
            ;;
    esac
done

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

info()    { echo -e "${BLUE}▸${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠${NC} $1"; }
die()     { echo -e "${RED}✗${NC} $1"; exit 1; }

validate_docker_port() {
    local name="$1" value="$2"
    if ! [[ "$value" =~ ^[0-9]+$ ]] || (( value < 1024 || value > 65535 )); then
        die "$name must be a number from 1024 to 65535 (got '$value')"
    fi
}

install_docker() {
    command -v docker >/dev/null 2>&1 || die "Docker is required for the isolated deployment"
    local compose_cmd=()
    if docker compose version >/dev/null 2>&1; then
        compose_cmd=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
        compose_cmd=(docker-compose)
    else
        die "Docker Compose v2 (docker compose) is required for the isolated deployment"
    fi

    local workspace="${NINJA_DOCKER_WORKSPACE:-$PWD}"
    [[ "$workspace" = /* && -d "$workspace" ]] || die "NINJA_DOCKER_WORKSPACE must be an existing absolute directory"
    local ports=("${NINJA_DOCKER_CODER_PORT:-8100}" "${NINJA_DOCKER_RESEARCHER_PORT:-8101}" "${NINJA_DOCKER_SECRETARY_PORT:-8102}" "${NINJA_DOCKER_AGENT_PORT:-8103}")
    local names=(NINJA_DOCKER_CODER_PORT NINJA_DOCKER_RESEARCHER_PORT NINJA_DOCKER_SECRETARY_PORT NINJA_DOCKER_AGENT_PORT)
    local i j
    for i in "${!ports[@]}"; do validate_docker_port "${names[$i]}" "${ports[$i]}"; done
    for i in "${!ports[@]}"; do
        for j in "${!ports[@]}"; do
            [[ "$i" -ge "$j" ]] && continue
            [[ "${ports[$i]}" != "${ports[$j]}" ]] || die "Docker host ports must be unique (${ports[$i]})"
        done
    done
    local profiles="${NINJA_DOCKER_PROFILES:-coder}"
    [[ "$profiles" =~ ^(coder|researcher|secretary|agent)(,(coder|researcher|secretary|agent))*$ ]] || die "NINJA_DOCKER_PROFILES must be a comma-separated list of supported profiles"

    local source_dir
    source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local temp_dir=""
    if [[ ! -f "$source_dir/docker-compose.yml" ]]; then
        temp_dir=$(mktemp -d)
        trap 'rm -rf "$temp_dir"' EXIT
        git clone --depth 1 "$REPO_URL" "$temp_dir/ninja-mcp" >/dev/null 2>&1 || die "Could not download Ninja MCP source"
        source_dir="$temp_dir/ninja-mcp"
    fi

    local config_dir="${NINJA_DOCKER_CONFIG_DIR:-$HOME/.config/ninja-mcp/docker}"
    mkdir -p "$config_dir"
    if [[ -n "$temp_dir" ]]; then
        rm -rf "$config_dir/source"
        cp -R "$source_dir" "$config_dir/source"
        source_dir="$config_dir/source"
    fi
    cat > "$config_dir/.env" <<EOF
# Ninja MCP Docker configuration. No API secrets are stored here.
NINJA_DOCKER_IMAGE=ninja-mcp:local-1.0.3
NINJA_DOCKER_WORKSPACE=$workspace
NINJA_DOCKER_CODER_PORT=${ports[0]}
NINJA_DOCKER_RESEARCHER_PORT=${ports[1]}
NINJA_DOCKER_SECRETARY_PORT=${ports[2]}
NINJA_DOCKER_AGENT_PORT=${ports[3]}
NINJA_DOCKER_PROFILES=$profiles
NINJA_DOCKER_AGENT_ACCESS=${NINJA_DOCKER_AGENT_ACCESS:-rw}
EOF
    if [[ -n "${NINJA_DOCKER_RUNTIME_ENV_FILE:-}" ]]; then
        printf 'NINJA_DOCKER_RUNTIME_ENV_FILE=%s\n' "$NINJA_DOCKER_RUNTIME_ENV_FILE" >> "$config_dir/.env"
    fi
    cat > "$config_dir/ninja-mcp-docker" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
CONFIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a
. "$CONFIG_DIR/.env"
set +a
PROJECT_DIR="@PROJECT_DIR@"
compose_cmd=()
if docker compose version >/dev/null 2>&1; then
  compose_cmd=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose_cmd=(docker-compose)
else
  printf 'Docker Compose v2 (docker compose) is required\n' >&2
  exit 1
fi
compose() {
  args=("${compose_cmd[@]}" --project-name ninja-mcp --env-file "$CONFIG_DIR/.env")
  if [[ -n "${NINJA_DOCKER_RUNTIME_ENV_FILE:-}" ]]; then
    [[ -f "$NINJA_DOCKER_RUNTIME_ENV_FILE" ]] || {
      printf 'Runtime env file does not exist: %s\n' "$NINJA_DOCKER_RUNTIME_ENV_FILE" >&2
      exit 1
    }
    args+=(--env-file "$NINJA_DOCKER_RUNTIME_ENV_FILE")
  fi
  args+=(-f "$PROJECT_DIR/docker-compose.yml")
  "${args[@]}" "$@"
}
profile_args=()
IFS=',' read -r -a profiles <<< "${NINJA_DOCKER_PROFILES:-coder}"
for profile in "${profiles[@]}"; do profile_args+=(--profile "$profile"); done
case "${1:-}" in
  start) shift; compose "${profile_args[@]}" up -d "$@" ;;
  stop) shift; compose "${profile_args[@]}" down "$@" ;;
  status) compose "${profile_args[@]}" ps ;;
  logs) shift; compose "${profile_args[@]}" logs -f "$@" ;;
  config) compose "${profile_args[@]}" config ;;
  *) printf 'Usage: %s {start|stop|status|logs|config}\n' "$0" >&2; exit 2 ;;
esac
WRAPPER
    local escaped_source
    escaped_source=$(printf '%s' "$source_dir" | sed 's/[&|]/\\&/g')
    sed -i.bak "s|@PROJECT_DIR@|$escaped_source|" "$config_dir/ninja-mcp-docker"
    rm -f "$config_dir/ninja-mcp-docker.bak"
    chmod 700 "$config_dir/ninja-mcp-docker"
    if [[ ! -e "$HOME/.local/bin/ninja-mcp-docker" ]]; then
        mkdir -p "$HOME/.local/bin"
        ln -s "$config_dir/ninja-mcp-docker" "$HOME/.local/bin/ninja-mcp-docker"
    else
        warn "$HOME/.local/bin/ninja-mcp-docker exists; wrapper was not overwritten"
    fi
    local profile_args=()
    IFS=',' read -r -a selected_profiles <<< "$profiles"
    local profile
    for profile in "${selected_profiles[@]}"; do profile_args+=(--profile "$profile"); done
    if [[ "${NINJA_DOCKER_BUILD:-1}" == "1" ]]; then
        (cd "$source_dir" && "${compose_cmd[@]}" --project-name ninja-mcp --env-file "$config_dir/.env" "${profile_args[@]}" build)
    fi
    if [[ "${NINJA_DOCKER_START:-0}" == "1" ]]; then
        "$config_dir/ninja-mcp-docker" start
    fi
    success "Docker setup ready: $config_dir"
    info "Use $HOME/.local/bin/ninja-mcp-docker {start|stop|status|logs|config}"
}

if [[ "$DOCKER_MODE" == "true" ]]; then
    docker_override=false
    for key in NINJA_DOCKER_WORKSPACE NINJA_DOCKER_PROFILES NINJA_DOCKER_CODER_PORT \
               NINJA_DOCKER_RESEARCHER_PORT NINJA_DOCKER_SECRETARY_PORT NINJA_DOCKER_AGENT_PORT; do
        [[ -n "${!key:-}" ]] && docker_override=true
    done
    if [[ "$docker_override" != "true" ]]; then
        if command -v ninja-config >/dev/null 2>&1; then
            exec ninja-config install
        fi
        source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        if [[ -f "$source_dir/src/ninja_config/docker_installer.py" ]]; then
            export PYTHONPATH="$source_dir/src${PYTHONPATH:+:$PYTHONPATH}"
            exec python3 -m ninja_config.docker_installer
        fi
        bootstrap_dir=$(mktemp -d)
        trap 'rm -rf "$bootstrap_dir"' EXIT
        if git clone --depth 1 "$REPO_URL" "$bootstrap_dir/ninja-mcp" >/dev/null 2>&1; then
            python3 -m pip install --quiet --target "$bootstrap_dir/python" InquirerPy
            export PYTHONPATH="$bootstrap_dir/ninja-mcp/src:$bootstrap_dir/python${PYTHONPATH:+:$PYTHONPATH}"
            export NINJA_DOCKER_SOURCE_DIR="$bootstrap_dir/ninja-mcp"
            exec python3 -m ninja_config.docker_installer
        fi
    fi
    install_docker
    exit 0
fi

# ============================================================================
# Banner
# ============================================================================
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}                                                          ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}              🥷 ${BOLD}NINJA MCP INSTALLER${NC}                      ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}                                                          ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================================
# STEP 1: System Detection
# ============================================================================
info "Detecting system..."

OS="unknown"
ARCH=$(uname -m)

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
fi

info "OS: $OS | Arch: $ARCH"

if ! command -v python3 &> /dev/null; then
    die "Python 3.11+ required. Install: https://python.org"
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 11) else 1)'; then
    success "Python $PYTHON_VERSION"
else
    die "Python 3.11+ required (you have $PYTHON_VERSION)"
fi

# ============================================================================
# STEP 3: Install ninja-mcp
# ============================================================================
info "Installing ninja-mcp..."

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    info "Deactivating virtual environment..."
    deactivate 2>/dev/null || true
    unset VIRTUAL_ENV
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "$SCRIPT_DIR/.venv/bin" ]]; then
    PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "$SCRIPT_DIR/.venv/bin" | tr '\n' ':' | sed 's/:$//')
    export PATH
fi

export PATH="$HOME/.local/bin:$PATH"

INSTALL_SUCCESS=false
INSTALL_EXTRAS="[runtime]"
if [[ "$MINIMAL_MODE" == "true" ]]; then
    INSTALL_EXTRAS="[coder]"
fi

INSTALL_PREFIX="${NINJA_INSTALL_PREFIX:-$HOME/.local/share/ninja-mcp}"
VENV_DIR="$INSTALL_PREFIX/venv"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$INSTALL_PREFIX" "$BIN_DIR"

info "Preparing managed Python environment: $VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip

if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    info "Detected dev directory, installing from local source..."
    if "$VENV_DIR/bin/python" -m pip install --upgrade "${SCRIPT_DIR}${INSTALL_EXTRAS}" 2>&1; then
        INSTALL_SUCCESS=true
        success "Installed from local dev directory"
    else
        warn "Local install failed, falling back to remote..."
    fi
fi

if [[ "$INSTALL_SUCCESS" != "true" ]]; then
    if "$VENV_DIR/bin/python" -m pip install --upgrade "ninja-mcp${INSTALL_EXTRAS}" 2>/dev/null; then
        INSTALL_SUCCESS=true
        success "Installed from PyPI"
    elif "$VENV_DIR/bin/python" -m pip install --upgrade "ninja-mcp${INSTALL_EXTRAS} @ git+${REPO_URL}" 2>&1; then
        INSTALL_SUCCESS=true
        success "Installed from GitHub"
    else
        warn "Direct install failed, trying local build..."
        TEMP_DIR=$(mktemp -d)
        trap 'rm -rf "$TEMP_DIR"' EXIT

         git clone --depth 1 "$REPO_URL" "$TEMP_DIR/ninja-mcp" 2>/dev/null || \
             (curl -sL "${REPO_URL%.git}/archive/main.tar.gz" | tar xz -C "$TEMP_DIR" && \
              extracted_dir="" && \
              for candidate in "$TEMP_DIR"/*; do
                  if [[ -d "$candidate" && "$candidate" != "$TEMP_DIR/ninja-mcp" ]]; then
                      extracted_dir="$candidate"
                      break
                  fi
              done && \
              [[ -n "$extracted_dir" ]] && mv "$extracted_dir" "$TEMP_DIR/ninja-mcp")

        if "$VENV_DIR/bin/python" -m pip install --upgrade "$TEMP_DIR/ninja-mcp${INSTALL_EXTRAS}"; then
            INSTALL_SUCCESS=true
            success "Installed from local build"
        fi
    fi
fi

[[ "$INSTALL_SUCCESS" != "true" ]] && die "Installation failed"

for cmd in ninja-mcp ninja-coder ninja-researcher ninja-secretary ninja-agent ninja-config ninja-daemon; do
    if [[ -x "$VENV_DIR/bin/$cmd" ]]; then
        ln -sf "$VENV_DIR/bin/$cmd" "$BIN_DIR/$cmd"
    fi
done

for cmd in ninja-mcp ninja-coder ninja-researcher ninja-secretary ninja-agent ninja-config ninja-daemon; do
    cmd_path=$(command -v "$cmd" 2>/dev/null || echo "not found")
    if [[ "$cmd_path" == *"/.local/"* ]]; then
        success "$cmd: $cmd_path"
    elif [[ "$cmd_path" == "not found" ]]; then
        warn "$cmd: not found in PATH"
    else
        warn "$cmd: $cmd_path"
    fi
done

LOCAL_BIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    export PATH="$LOCAL_BIN:$PATH"
    SHELL_RC="$HOME/.bashrc"
    [[ "$(basename "$SHELL")" == "zsh" ]] && SHELL_RC="$HOME/.zshrc"
    if ! grep -q '.local/bin' "$SHELL_RC" 2>/dev/null; then
        printf "\n# Ninja MCP\nexport PATH=\"\$HOME/.local/bin:\$PATH\"\n" >> "$SHELL_RC"
        info "Added to $SHELL_RC"
    fi
fi

# ============================================================================
# STEP 4: Launch TUI Installer
# ============================================================================
if [[ "$AUTO_MODE" == "true" ]]; then
    echo ""
    info "Auto mode: writing minimal config..."

    NINJA_CONFIG="$HOME/.ninja-mcp.env"
    {
        echo "# Ninja MCP Configuration"
        echo "# Generated on $(date)"
        echo ""
        echo "NINJA_CODE_BIN=aider"
        echo "NINJA_SEARCH_PROVIDER=duckduckgo"
        echo "NINJA_ENABLE_DAEMON=true"
        echo "NINJA_ENABLED_MODULES=coder,researcher"
        echo "# To enable agent orchestrator: ninja-daemon module enable agent"
        echo "NINJA_CODER_PORT=8100"
        echo "NINJA_RESEARCHER_PORT=8101"
        echo "NINJA_SECRETARY_PORT=8102"
        echo "NINJA_AGENT_PORT=8103"
        echo ""
        echo "# Set your API keys:"
        echo "# OPENROUTER_API_KEY=sk-or-..."
        echo "# NINJA_CODER_MODEL=opencode/glm-4.7-free"
        echo "# NINJA_RESEARCHER_MODEL=sonar"
        echo "# NINJA_SECRETARY_MODEL=opencode/glm-4.7-free"
    } > "$NINJA_CONFIG"

    if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
        echo "OPENROUTER_API_KEY=${OPENROUTER_API_KEY}" >> "$NINJA_CONFIG"
        success "OpenRouter API key from environment"
    else
        warn "No OPENROUTER_API_KEY set. Run 'ninja-config install' to configure."
    fi

    if command -v aider &> /dev/null; then
        success "aider already installed"
    elif command -v pipx &> /dev/null; then
        info "Installing aider..."
            if pipx install aider-chat 2>&1; then
                success "aider installed"
            else
                warn "Could not install aider"
            fi
    else
        warn "aider not found. Install manually: pipx install aider-chat"
    fi

    success "Auto-mode installation complete"
else
    echo ""
    info "Launching TUI installer..."
    echo ""

    if command -v ninja-config &> /dev/null; then
        exec ninja-config install
    else
        die "ninja-config not found. Installation may have failed."
    fi
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}           ${BOLD}🥷 INSTALLATION COMPLETE!${NC}                      ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}Next steps:${NC}"
echo "  ninja-config configure     # Reconfigure any time"
echo "  ninja-config doctor        # Verify installation"
echo "  ninja-config select-model  # Change AI models"
echo ""
echo -e "${DIM}Documentation: https://github.com/angkira/ninja-cli-mcp${NC}"
echo ""
