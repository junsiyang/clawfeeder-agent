#!/usr/bin/env bash
# =============================================================================
# ClawFeeder Agent - User Installer
# =============================================================================
# Run this after receiving the pre-built binary (dist/clawfeeder).
#
# Usage:
#   bash install.sh
#   API_KEY="cf_agt_xxx" MASTER_KEY="password" bash install.sh
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
    local binary="${script_dir}/clawfeeder"

    # ── Check binary ───────────────────────────────────────────────────────
    if [[ ! -f "$binary" ]]; then
        log_error "Binary not found: ${binary}"
        log_error "Please place the pre-built 'clawfeeder' binary next to install.sh"
        exit 1
    fi

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

    # ── Write user config ──────────────────────────────────────────────────
    log_info "Creating config directory: ${CONFIG_DIR}"
    mkdir -p "${CONFIG_DIR}" "${CONFIG_DIR}/data" "${CONFIG_DIR}/logs"

    local device_id
    device_id=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || uuidgen 2>/dev/null || echo "device-$$")

    log_info "Writing ~/.clawfeeder/config.yaml..."
    cat > "${CONFIG_DIR}/config.yaml" << EOF
# User config — edit this file to update your personal settings.

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

    # ── Install binary ─────────────────────────────────────────────────────
    local installed="${CONFIG_DIR}/${AGENT_NAME}"
    cp "$binary" "$installed"
    chmod +x "$installed"
    log_info "Installed binary: ${installed}"

    echo ""
    echo "=============================================="
    echo "  Installation Complete!"
    echo "=============================================="
    echo ""
    log_info "Config:  ${CONFIG_DIR}/config.yaml"
    log_info "Binary:  ${installed}"
    echo ""
    echo "Start:"
    echo "  ${installed} --config ${CONFIG_DIR}/config.yaml"
    echo ""
}

main
