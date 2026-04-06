#!/usr/bin/env bash
# =============================================================================
# ClawFeeder Agent - Local Installer
# =============================================================================
# Usage:
#   bash install.sh
#   API_KEY="cf_agt_xxx" MASTER_KEY="password" bash install.sh
#
# This script:
#   1. Creates config directory (~/.clawfeeder/)
#   2. Generates config.yaml
#   3. Creates launcher script
# =============================================================================

set -e

# Configuration
AGENT_NAME="clawfeeder"
CONFIG_DIR="${HOME}/.${AGENT_NAME}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Main
main() {
    echo ""
    echo "=============================================="
    echo "  ${AGENT_NAME} Agent Installer"
    echo "=============================================="
    echo ""

    # Get project directory (where this script is)
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local venv_python="${script_dir}/.venv/bin/python"

    if [[ ! -f "$venv_python" ]]; then
        log_error "Virtual environment not found at ${script_dir}/.venv/"
        log_error "Please run: cd ${script_dir} && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi

    # Check for API key
    if [[ -z "${API_KEY}" ]]; then
        log_warn "API_KEY not set"
        echo -n "Enter your Agent API Key (cf_agt_...): "
        read API_KEY
        echo ""
    fi

    if [[ -z "${API_KEY}" ]]; then
        log_error "API key is required"
        exit 1
    fi

    if [[ ! "${API_KEY}" =~ ^cf_agt_ ]]; then
        log_error "Invalid API key format. Should start with 'cf_agt_'"
        exit 1
    fi

    # Check for master key
    if [[ -z "${MASTER_KEY}" ]]; then
        log_warn "MASTER_KEY not set"
        echo -n "Enter your Master Password: "
        read -s MASTER_KEY
        echo ""
    fi

    if [[ -z "${MASTER_KEY}" ]]; then
        log_error "Master password is required"
        exit 1
    fi

    # Setup config directory
    log_info "Creating config directory: ${CONFIG_DIR}"
    mkdir -p "${CONFIG_DIR}"
    mkdir -p "${CONFIG_DIR}/data"
    mkdir -p "${CONFIG_DIR}/logs"

    # Generate device ID
    local device_id=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || uuidgen 2>/dev/null || echo "device-$$")

    # Create config
    log_info "Creating config.yaml..."
    cat > "${CONFIG_DIR}/config.yaml" << EOF
api:
  base_url: "http://localhost:8000"
  heartbeat_interval: 60

auth:
  api_key: "${API_KEY}"

storage:
  data_dir: "${CONFIG_DIR}/data"
  expired_dir: "${CONFIG_DIR}/data/expired"

device:
  device_id: "${device_id}"
  device_name: "$(hostname)"

master_key: "${MASTER_KEY}"
EOF

    # Create launcher
    log_info "Creating launcher..."
    local launcher="${CONFIG_DIR}/${AGENT_NAME}"
    cat > "$launcher" << LAUNCHER
#!/usr/bin/env bash
# ClawFeeder Agent Launcher
cd "${script_dir}"
exec "${script_dir}/.venv/bin/python" -m src.main --config "${CONFIG_DIR}/config.yaml" "\$@"
LAUNCHER
    chmod +x "$launcher"
    log_info "Launcher created at ${launcher}"

    echo ""
    echo "=============================================="
    echo "  Installation Complete!"
    echo "=============================================="
    echo ""
    log_info "Config: ${CONFIG_DIR}/config.yaml"
    log_info "Launcher: ${launcher}"
    echo ""
    echo "Usage:"
    echo "  ${launcher} --config ${CONFIG_DIR}/config.yaml"
    echo ""
    echo "Or with environment variables:"
    echo "  MASTER_KEY='your_password' ${launcher} --api-key '${API_KEY}'"
    echo ""
}

main
