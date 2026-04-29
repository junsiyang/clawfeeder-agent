"""Interactive setup wizard — replaces install.sh."""

import getpass
import os
import platform
import shutil
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import yaml


CONFIG_DIR = Path.home() / ".clawfeeder"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
NC = "\033[0m"


def _load_existing() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f) or {}


def _prompt(label: str, existing: str = "", secret: bool = False, required: bool = True) -> str:
    if existing:
        if secret:
            hint = "[****]"
        else:
            hint = f"[{existing}]"
        prompt_text = f"{label} {hint}: "
    else:
        prompt_text = f"{label}: "

    if secret:
        value = getpass.getpass(prompt_text)
    else:
        value = input(prompt_text)

    value = value.strip()
    if not value:
        value = existing

    if required and not value:
        print(f"{RED}[ERROR]{NC} {label} is required")
        raise SystemExit(1)

    return value


def run_setup():
    print()
    print("==============================================")
    print("  ClawFeeder Agent Setup")
    print("==============================================")
    print()

    existing = _load_existing()
    if existing:
        print(f"{GREEN}[INFO]{NC} Found existing config: {CONFIG_FILE}")
        print()

    ex_auth = existing.get("auth", {})
    ex_device = existing.get("device", {})
    ex_storage = existing.get("storage", {})
    ex_sync = existing.get("sync", {})

    # API Key
    ex_api_key = ex_auth.get("api_key", "")
    if ex_api_key:
        masked = ex_api_key[:10] + "..." + ex_api_key[-4:]
        api_key = _prompt("Agent API Key", masked)
        if api_key == masked:
            api_key = ex_api_key
    else:
        api_key = _prompt("Agent API Key (cf_agt_...)")

    if not api_key.startswith("cf_agt_"):
        print(f"{RED}[ERROR]{NC} Invalid API key format. Should start with 'cf_agt_'")
        raise SystemExit(1)

    # Master Key
    master_key = _prompt("Master Password", existing.get("master_key", ""), secret=True)

    # Device Name
    default_name = ex_device.get("device_name", "") or socket.gethostname()
    device_name = _prompt("Device Name", default_name, required=False) or default_name

    # Device ID (auto-generated, preserved)
    device_id = ex_device.get("device_id", "") or str(uuid.uuid4())

    # Sync Domains
    ex_domains = ex_sync.get("domains") or []
    ex_domains_str = ", ".join(ex_domains) if ex_domains else ""

    if ex_domains_str:
        print(f"Sync Domains (comma-separated, {CYAN}Enter{NC} to keep [{ex_domains_str}], {CYAN}all{NC} for all):")
    else:
        print(f"Sync Domains (comma-separated, {CYAN}Enter{NC} for all):")
    domains_input = input("> ").strip()
    print()

    if domains_input.lower() == "all":
        sync_domains = []
    elif domains_input:
        sync_domains = [d.strip() for d in domains_input.split(",") if d.strip()]
    else:
        sync_domains = [d.strip() for d in ex_domains if d and d.strip()]

    # Storage paths
    data_dir = ex_storage.get("data_dir", str(CONFIG_DIR / "data"))
    expired_dir = ex_storage.get("expired_dir", str(CONFIG_DIR / "data" / "expired"))

    # Create directories
    print(f"{GREEN}[INFO]{NC} Creating directories...")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    Path(data_dir).expanduser().mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "logs").mkdir(parents=True, exist_ok=True)

    # Build config
    config_data = {
        "auth": {"api_key": api_key},
        "storage": {"data_dir": data_dir, "expired_dir": expired_dir},
        "device": {"device_id": device_id, "device_name": device_name},
        "master_key": master_key,
    }
    if sync_domains:
        config_data["sync"] = {"domains": sync_domains}

    # Write config
    print(f"{GREEN}[INFO]{NC} Writing {CONFIG_FILE}...")
    header = (
        "# User config — edit this file to update your personal settings.\n"
        "# Changes take effect on agent restart.\n\n"
    )
    with open(CONFIG_FILE, "w") as f:
        f.write(header)
        yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print()
    print("==============================================")
    print("  Setup Complete!")
    print("==============================================")
    print()
    print(f"{GREEN}[INFO]{NC} Config: {CONFIG_FILE}")
    if sync_domains:
        print(f"{GREEN}[INFO]{NC} Sync:   {', '.join(sync_domains)}")
    else:
        print(f"{GREEN}[INFO]{NC} Sync:   all domains")
    print()

    # Offer systemd service installation on Linux
    if platform.system() == "Linux":
        _offer_systemd_service()
    else:
        print("Start:")
        print(f"  clawfeeder-agent --config {CONFIG_FILE}")
        print()


SERVICE_NAME = "clawfeeder-agent"
SERVICE_PATH = Path(f"/etc/systemd/system/{SERVICE_NAME}.service")


def _find_binary() -> str:
    """Find the clawfeeder-agent binary path."""
    # PyInstaller frozen binary
    if getattr(sys, "frozen", False):
        return sys.executable
    # Installed via pip / in PATH
    found = shutil.which("clawfeeder-agent")
    if found:
        return found
    return ""


def _offer_systemd_service():
    """Ask the user whether to install a systemd service."""
    answer = input(f"Install as systemd service (auto-start on boot)? [Y/n]: ").strip().lower()
    if answer in ("n", "no"):
        print()
        print("Start manually:")
        print(f"  clawfeeder-agent --config {CONFIG_FILE}")
        print()
        return

    binary = _find_binary()
    if not binary:
        print(f"{RED}[ERROR]{NC} Cannot find clawfeeder-agent binary.")
        print("  Copy the binary to /usr/local/bin/ first, then re-run --setup.")
        return

    user = os.environ.get("SUDO_USER") or os.environ.get("USER") or "root"
    home = Path(f"~{user}").expanduser() if user != "root" else Path.home()

    unit = f"""[Unit]
Description=ClawFeeder Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
ExecStart={binary} --config {home}/.clawfeeder/config.yaml
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
"""

    try:
        SERVICE_PATH.write_text(unit)
    except PermissionError:
        print(f"{RED}[ERROR]{NC} Permission denied writing {SERVICE_PATH}")
        print(f"  Re-run with sudo: sudo {binary} --setup")
        return

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", SERVICE_NAME], check=True)
    subprocess.run(["systemctl", "restart", SERVICE_NAME], check=True)

    print()
    print(f"{GREEN}[OK]{NC} Service installed and started.")
    print()
    print("  Check status:  systemctl status clawfeeder-agent")
    print("  View logs:     journalctl -u clawfeeder-agent -f")
    print("  Stop:          sudo systemctl stop clawfeeder-agent")
    print("  Disable:       sudo systemctl disable clawfeeder-agent")
    print()
