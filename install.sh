#!/usr/bin/env bash
# =============================================================================
# ClawFeeder Agent - User Installer
# =============================================================================
# Run this after receiving the pre-built binary (dist/clawfeeder-agent).
#
# Usage:
#   bash install.sh
#   API_KEY="cf_agt_xxx" MASTER_KEY="password" bash install.sh
#
# Re-running install.sh preserves existing config values by default.
# Press Enter at any prompt to keep the current value.
# =============================================================================

set -e

BINARY_NAME="clawfeeder-agent"
CONFIG_DIR="${HOME}/.clawfeeder"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Read a value from existing config.yaml using grep/sed (no yaml parser needed)
read_config() {
    local key="$1"
    if [[ -f "$CONFIG_FILE" ]]; then
        grep -E "^\s*${key}:" "$CONFIG_FILE" 2>/dev/null | head -1 | sed 's/.*:\s*"\?\([^"]*\)"\?/\1/' | xargs
    fi
}

# Read sync domains list from existing config
read_sync_domains() {
    if [[ -f "$CONFIG_FILE" ]]; then
        awk '/^sync:/{found=1; next} found && /^\s+domains:/{dmn=1; next} dmn && /^\s+-\s+/{gsub(/^\s+-\s+/,""); printf "%s,", $0; next} dmn && /^[^ ]/{exit} !found && /^[^ ]/{found=0}' "$CONFIG_FILE" | sed 's/,$//'
    fi
}

main() {
    echo ""
    echo "=============================================="
    echo "  ClawFeeder Agent Installer"
    echo "=============================================="
    echo ""

    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local binary="${script_dir}/${BINARY_NAME}"

    # ── Check binary ───────────────────────────────────────────────────────
    if [[ ! -f "$binary" ]]; then
        log_error "Binary not found: ${binary}"
        log_error "Please place the pre-built '${BINARY_NAME}' binary next to install.sh"
        exit 1
    fi

    # ── Load existing config values ────────────────────────────────────────
    local existing_api_key=""
    local existing_master_key=""
    local existing_device_name=""
    local existing_device_id=""
    local existing_data_dir=""
    local existing_expired_dir=""
    local existing_domains=""

    if [[ -f "$CONFIG_FILE" ]]; then
        log_info "Found existing config: ${CONFIG_FILE}"
        existing_api_key=$(read_config "api_key")
        existing_master_key=$(read_config "master_key")
        existing_device_name=$(read_config "device_name")
        existing_device_id=$(read_config "device_id")
        existing_data_dir=$(read_config "data_dir")
        existing_expired_dir=$(read_config "expired_dir")
        existing_domains=$(read_sync_domains)
        echo ""
    fi

    # ── Required: API Key ──────────────────────────────────────────────────
    if [[ -z "${API_KEY}" ]]; then
        if [[ -n "$existing_api_key" ]]; then
            local masked="${existing_api_key:0:10}...${existing_api_key: -4}"
            echo -n "Agent API Key [${masked}]: "
        else
            echo -n "Agent API Key (cf_agt_...): "
        fi
        read API_KEY
        echo ""
    fi

    if [[ -z "${API_KEY}" ]]; then
        API_KEY="${existing_api_key}"
    fi

    if [[ -z "${API_KEY}" ]]; then
        log_error "API key is required"
        exit 1
    fi

    if [[ ! "${API_KEY}" =~ ^cf_agt_ ]]; then
        log_error "Invalid API key format. Should start with 'cf_agt_'"
        exit 1
    fi

    # ── Required: Master Password ──────────────────────────────────────────
    if [[ -z "${MASTER_KEY}" ]]; then
        if [[ -n "$existing_master_key" ]]; then
            echo -n "Master Password [****]: "
        else
            echo -n "Master Password: "
        fi
        read -s MASTER_KEY
        echo ""
    fi

    if [[ -z "${MASTER_KEY}" ]]; then
        MASTER_KEY="${existing_master_key}"
    fi

    if [[ -z "${MASTER_KEY}" ]]; then
        log_error "Master password is required"
        exit 1
    fi

    # ── Optional: Device Name (default: hostname) ──────────────────────────
    local default_device_name
    default_device_name="${existing_device_name:-$(hostname)}"

    if [[ -z "${DEVICE_NAME}" ]]; then
        echo -n "Device Name [${default_device_name}]: "
        read DEVICE_NAME
        echo ""
    fi

    if [[ -z "${DEVICE_NAME}" ]]; then
        DEVICE_NAME="${default_device_name}"
    fi

    # ── Auto-generated: Device ID (preserve existing) ─────────────────────
    local device_id
    if [[ -n "$existing_device_id" ]]; then
        device_id="$existing_device_id"
    else
        device_id=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || uuidgen 2>/dev/null || echo "device-$$")
    fi

    # ── Optional: Sync Domains ─────────────────────────────────────────────
    if [[ -z "${SYNC_DOMAINS}" ]]; then
        if [[ -n "$existing_domains" ]]; then
            echo -e "Sync Domains (comma-separated, ${CYAN}Enter${NC} to keep [${existing_domains}], ${CYAN}all${NC} for all): "
        else
            echo -e "Sync Domains (comma-separated, ${CYAN}Enter${NC} for all): "
        fi
        echo -n "> "
        read SYNC_DOMAINS
        echo ""
    fi

    if [[ -z "${SYNC_DOMAINS}" ]]; then
        SYNC_DOMAINS="${existing_domains}"
    fi

    if [[ "${SYNC_DOMAINS}" == "all" ]]; then
        SYNC_DOMAINS=""
    fi

    # ── Preserve storage paths ─────────────────────────────────────────────
    local data_dir="${existing_data_dir:-${CONFIG_DIR}/data}"
    local expired_dir="${existing_expired_dir:-${CONFIG_DIR}/data/expired}"

    # ── Write user config ──────────────────────────────────────────────────
    log_info "Creating config directory: ${CONFIG_DIR}"
    mkdir -p "${CONFIG_DIR}" "${data_dir}" "${CONFIG_DIR}/logs"

    log_info "Writing ~/.clawfeeder/config.yaml..."

    # Build sync.domains YAML block
    local sync_block=""
    if [[ -n "${SYNC_DOMAINS}" ]]; then
        sync_block=$'\n'"sync:"$'\n'"  domains:"
        IFS=',' read -ra DOMAIN_ARRAY <<< "${SYNC_DOMAINS}"
        for d in "${DOMAIN_ARRAY[@]}"; do
            d=$(echo "$d" | xargs)  # trim whitespace
            if [[ -n "$d" ]]; then
                sync_block="${sync_block}"$'\n'"    - ${d}"
            fi
        done
    fi

    cat > "${CONFIG_FILE}" << EOF
# User config — edit this file to update your personal settings.
# Changes take effect on agent restart. No need to re-run install.sh.

auth:
  api_key: "${API_KEY}"

storage:
  data_dir: "${data_dir}"
  expired_dir: "${expired_dir}"

device:
  device_id: "${device_id}"
  device_name: "${DEVICE_NAME}"

master_key: "${MASTER_KEY}"${sync_block}
EOF

    # ── Install binary ─────────────────────────────────────────────────────
    local installed="${CONFIG_DIR}/${BINARY_NAME}"
    cp "$binary" "$installed"
    chmod +x "$installed"

    echo ""
    echo "=============================================="
    echo "  Installation Complete!"
    echo "=============================================="
    echo ""
    log_info "Config:  ${CONFIG_FILE}"
    log_info "Binary:  ${installed}"
    if [[ -n "${SYNC_DOMAINS}" ]]; then
        log_info "Sync:    ${SYNC_DOMAINS}"
    else
        log_info "Sync:    all domains"
    fi
    echo ""
    echo "Start:"
    echo "  ${installed} --config ${CONFIG_FILE}"
    echo ""
    echo "To update settings, edit config.yaml and restart."
    echo ""
}

main
