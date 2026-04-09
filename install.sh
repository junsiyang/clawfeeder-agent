#!/usr/bin/env bash
# =============================================================================
# ClawFeeder Agent - Local Installer
# =============================================================================
# Usage:
#   bash install.sh
#   API_KEY="cf_agt_xxx" MASTER_KEY="password" bash install.sh
#
# Build-time config (base_url etc.) is read from config.build.yaml.
# User config (api_key, master_key, device info) is written to ~/.clawfeeder/config.yaml.
#
# Setup:
#   cp config.build.yaml.example config.build.yaml
#   # Edit config.build.yaml with your base_url
#   bash install.sh
# =============================================================================

set -e

AGENT_NAME="clawfeeder"
CONFIG_DIR="${HOME}/.${AGENT_NAME}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

main() {
    echo ""
    echo "=============================================="
    echo "  ${AGENT_NAME} Agent Installer"
    echo "=============================================="
    echo ""

    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local venv_python="${script_dir}/.venv/bin/python"
    local build_config="${script_dir}/config.build.yaml"

    if [[ ! -f "$venv_python" ]]; then
        log_error "Virtual environment not found at ${script_dir}/.venv/"
        log_error "Please run: cd ${script_dir} && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi

    # ── Build-time config ──────────────────────────────────────────────────
    if [[ ! -f "$build_config" ]]; then
        log_error "config.build.yaml not found."
        log_error "Run: cp config.build.yaml.example config.build.yaml"
        log_error "Then set base_url in config.build.yaml"
        exit 1
    fi

    if grep -q '__BASE_URL__' "$build_config"; then
        log_error "config.build.yaml still contains placeholder '__BASE_URL__'."
        log_error "Edit config.build.yaml and set the real base_url."
        exit 1
    fi

    # Read build-time values from config.build.yaml
    local base_url
    base_url=$("${venv_python}" -c \
        "import yaml; d=yaml.safe_load(open('${build_config}')); print(d['api']['base_url'])")
    local heartbeat_interval
    heartbeat_interval=$("${venv_python}" -c \
        "import yaml; d=yaml.safe_load(open('${build_config}')); print(d['api'].get('heartbeat_interval', 60))")

    log_info "Backend: ${base_url}"

    # ── User config ────────────────────────────────────────────────────────
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

    # ── Write user config ─────────────────────────────────────────────────
    log_info "Creating config directory: ${CONFIG_DIR}"
    mkdir -p "${CONFIG_DIR}" "${CONFIG_DIR}/data" "${CONFIG_DIR}/logs"

    local device_id
    device_id=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || uuidgen 2>/dev/null || echo "device-$$")

    log_info "Writing ~/.clawfeeder/config.yaml..."
    cat > "${CONFIG_DIR}/config.yaml" << EOF
# User config — edit this file to update your personal settings.
# Build-time settings (base_url etc.) are embedded in the launcher.

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

    # ── Launcher (build-time config embedded here) ─────────────────────────
    log_info "Creating launcher..."
    local launcher="${CONFIG_DIR}/${AGENT_NAME}"
    cat > "$launcher" << LAUNCHER
#!/usr/bin/env bash
# ClawFeeder Agent Launcher
# Build-time config embedded by install.sh — do not edit manually.
# To update base_url or heartbeat_interval, re-run install.sh.
export CLAWFEEDER_BASE_URL="${base_url}"
export CLAWFEEDER_HEARTBEAT_INTERVAL="${heartbeat_interval}"

cd "${script_dir}"
exec "${script_dir}/.venv/bin/python" -m src.main --config "${CONFIG_DIR}/config.yaml" "\$@"
LAUNCHER
    chmod +x "$launcher"

    echo ""
    echo "=============================================="
    echo "  Installation Complete!"
    echo "=============================================="
    echo ""
    log_info "User config:  ${CONFIG_DIR}/config.yaml"
    log_info "Build config: ${build_config}"
    log_info "Launcher:     ${launcher}"
    echo ""
    echo "Start:"
    echo "  ${launcher}"
    echo ""
}

main
