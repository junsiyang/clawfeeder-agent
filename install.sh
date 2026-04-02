#!/usr/bin/env bash
# =============================================================================
# ClawFeeder Agent - One-Line Installer
# =============================================================================
# Usage: curl -sSL https://your-domain.com/install.sh | bash
# Or:    bash <(curl -sSL https://your-domain.com/install.sh)
#
# This script:
#   1. Detects OS and architecture
#   2. Downloads the latest binary
#   3. Sets up config directory (~/.clawfeeder/)
#   4. Registers as systemd service (Linux) or launchd (macOS)
#   5. Starts the service
# =============================================================================

set -e

# Configuration
AGENT_NAME="clawfeeder"
INSTALL_DIR="/opt/${AGENT_NAME}"
CONFIG_DIR="${HOME}/.${AGENT_NAME}"
BINARY_NAME="${AGENT_NAME}"
REPO_URL="https://github.com/yourusername/cookie-manager/releases/latest"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v systemctl &> /dev/null; then
            echo "linux-systemd"
        else
            echo "linux-no-systemd"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

# Detect architecture
detect_arch() {
    local arch=$(uname -m)
    case $arch in
        x86_64)
            echo "amd64"
            ;;
        aarch64|arm64)
            echo "arm64"
            ;;
        armv7l)
            echo "arm"
            ;;
        *)
            echo "amd64"
            ;;
    esac
}

# Download binary
download_binary() {
    local os=$1
    local arch=$2
    local version=$3

    log_info "Downloading ${AGENT_NAME} v${version} for ${os}/${arch}..."

    local download_url="${REPO_URL}/download/v${version}/${AGENT_NAME}-${os}-${arch}"
    local tmp_file="/tmp/${BINARY_NAME}"

    if command -v curl &> /dev/null; then
        curl -sSL -o "$tmp_file" "$download_url"
    elif command -v wget &> /dev/null; then
        wget -q -O "$tmp_file" "$download_url"
    else
        log_error "curl or wget is required"
        exit 1
    fi

    chmod +x "$tmp_file"
    mkdir -p "$INSTALL_DIR"
    mv "$tmp_file" "${INSTALL_DIR}/${BINARY_NAME}"

    log_info "Binary installed to ${INSTALL_DIR}/${BINARY_NAME}"
}

# Setup config directory
setup_config() {
    log_info "Setting up config directory: ${CONFIG_DIR}"

    mkdir -p "${CONFIG_DIR}"
    mkdir -p "${CONFIG_DIR}/data"
    mkdir -p "${CONFIG_DIR}/data/expired"
    mkdir -p "${CONFIG_DIR}/logs"

    # Create default config if not exists
    if [[ ! -f "${CONFIG_DIR}/config.yaml" ]]; then
        cat > "${CONFIG_DIR}/config.yaml" << EOF
api:
  base_url: "http://localhost:8000"
  heartbeat_interval: 60

auth:
  email: "your@email.com"
  password: "yourpassword"

storage:
  data_dir: "${CONFIG_DIR}/data"
  expired_dir: "${CONFIG_DIR}/data/expired"

device:
  device_id: "$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid)"
  device_name: "$(hostname)"
EOF
        log_info "Created default config at ${CONFIG_DIR}/config.yaml"
    fi
}

# Register as systemd service (Linux)
register_systemd_service() {
    log_info "Registering systemd service..."

    local service_file="/etc/systemd/system/${AGENT_NAME}.service"

    sudo tee "$service_file" > /dev/null << EOF
[Unit]
Description=ClawFeeder Agent
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=${CONFIG_DIR}
Environment="EMAIL=${EMAIL}" "PASSWORD=${PASSWORD}"
ExecStart=${INSTALL_DIR}/${BINARY_NAME} --config ${CONFIG_DIR}/config.yaml --email \${EMAIL} --password \${PASSWORD}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable "${AGENT_NAME}"

    log_info "Systemd service registered"
}

# Register as launchd service (macOS)
register_launchd_service() {
    log_info "Registering launchd service..."

    local plist_dir="${HOME}/Library/LaunchAgents"
    local plist_file="${plist_dir}/io.${AGENT_NAME}.plist"

    mkdir -p "$plist_dir"

    cat > "$plist_file" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.${AGENT_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${INSTALL_DIR}/${BINARY_NAME}</string>
        <string>--config</string>
        <string>${CONFIG_DIR}/config.yaml</string>
        <string>--email</string>
        <string>${EMAIL}</string>
        <string>--password</string>
        <string>${PASSWORD}</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>EMAIL</key>
        <string>${EMAIL}</string>
        <key>PASSWORD</key>
        <string>${PASSWORD}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${CONFIG_DIR}/logs/agent.log</string>
    <key>StandardErrorPath</key>
    <string>${CONFIG_DIR}/logs/agent.err</string>
</dict>
</plist>
EOF

    log_info "Launchd plist created at ${plist_file}"
}

# Start service
start_service() {
    local os=$1

    log_info "Starting ${AGENT_NAME}..."

    if [[ "$os" == "linux-systemd" ]]; then
        sudo systemctl start "${AGENT_NAME}"
        sudo systemctl status "${AGENT_NAME}" --no-pager
    elif [[ "$os" == "macos" ]]; then
        launchctl load "$plist_file"
    else
        log_warn "Auto-start not available for ${os}, starting manually..."
        nohup "${INSTALL_DIR}/${BINARY_NAME}" --config "${CONFIG_DIR}/config.yaml" --email "${EMAIL}" --password "${PASSWORD}" > "${CONFIG_DIR}/logs/agent.log" 2>&1 &
    fi
}

# Main
main() {
    echo ""
    echo "=============================================="
    echo "  ${AGENT_NAME} One-Line Installer"
    echo "=============================================="
    echo ""

    # Check for email and password
    if [[ -z "${EMAIL}" ]]; then
        log_warn "EMAIL not set in environment"
        echo -n "Enter your email: "
        read EMAIL
        echo ""
    fi

    if [[ -z "${PASSWORD}" ]]; then
        log_warn "PASSWORD not set in environment"
        echo -n "Enter your password: "
        read -s PASSWORD
        echo ""
    fi

    if [[ -z "${EMAIL}" ]] || [[ -z "${PASSWORD}" ]]; then
        log_error "Email and password are required"
        exit 1
    fi

    local os=$(detect_os)
    local arch=$(detect_arch)

    log_info "Detected: ${os}/${arch}"

    if [[ "$os" == "unknown" ]]; then
        log_error "Unsupported OS: $OSTYPE"
        exit 1
    fi

    # For demo, we'll create a placeholder for the binary
    # In production, this would download from GitHub releases
    log_info "Setting up directory structure..."

    setup_config

    # Download or create placeholder binary
    # Note: In production, download actual binary
    mkdir -p "$INSTALL_DIR"

    # Create a simple launcher script as placeholder
    cat > "${INSTALL_DIR}/${BINARY_NAME}" << 'LAUNCHER'
#!/usr/bin/env bash
# Launcher placeholder - replace with actual binary
exec python3 "$(dirname "$0")/../../../clawfeeder/src/main.py" "$@"
LAUNCHER
    chmod +x "${INSTALL_DIR}/${BINARY_NAME}"

    # Register service
    if [[ "$os" == "linux-systemd" ]]; then
        register_systemd_service
    elif [[ "$os" == "macos" ]]; then
        register_launchd_service
    fi

    echo ""
    log_info "=============================================="
    log_info "  Installation Complete!"
    log_info "=============================================="
    echo ""
    log_info "Config: ${CONFIG_DIR}/config.yaml"
    log_info "Logs:   ${CONFIG_DIR}/logs/"
    echo ""
    log_info "To start manually:"
    echo "  ${INSTALL_DIR}/${BINARY_NAME} --config ${CONFIG_DIR}/config.yaml --email '${EMAIL}' --password '${PASSWORD}'"
    echo ""
    log_info "To uninstall:"
    echo "  sudo systemctl stop ${AGENT_NAME}  # Linux"
    echo "  launchctl unload ~/Library/LaunchAgents/io.${AGENT_NAME}.plist  # macOS"
    echo "  rm -rf ${INSTALL_DIR} ${CONFIG_DIR}"
    echo ""
}

main "$@"
