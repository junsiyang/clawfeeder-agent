"""Interactive setup wizard — replaces install.sh."""

import getpass
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import yaml


CONFIG_DIR = Path.home() / ".clawfeeder"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
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


SERVICE_NAME = "clawfeeder-agent"
SYSTEM_SERVICE_PATH = Path(f"/etc/systemd/system/{SERVICE_NAME}.service")
USER_SERVICE_DIR = Path.home() / ".config" / "systemd" / "user"
USER_SERVICE_PATH = USER_SERVICE_DIR / f"{SERVICE_NAME}.service"

LAUNCHD_LABEL = "com.clawfeeder.agent"
LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def _stop_existing_agent():
    """Stop any running clawfeeder-agent process before re-setup."""
    system = platform.system()

    if system == "Linux":
        subprocess.run(
            ["systemctl", "stop", SERVICE_NAME],
            capture_output=True,
        )
        subprocess.run(
            ["systemctl", "--user", "stop", SERVICE_NAME],
            capture_output=True,
        )
        subprocess.run(
            ["pkill", "-f", "clawfeeder-agent --config"],
            capture_output=True,
        )

    elif system == "Darwin":
        if LAUNCHD_PLIST.exists():
            subprocess.run(
                ["launchctl", "unload", str(LAUNCHD_PLIST)],
                capture_output=True,
            )
        subprocess.run(
            ["pkill", "-f", "clawfeeder-agent --config"],
            capture_output=True,
        )

    time.sleep(1)


def run_setup():
    print()
    print("==============================================")
    print("  ClawFeeder Agent Setup")
    print("==============================================")
    print()

    _stop_existing_agent()

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

    # Offer background service installation
    if platform.system() == "Linux":
        _offer_systemd_service()
    elif platform.system() == "Darwin":
        _offer_launchd_service()
    else:
        print("Start:")
        print(f"  clawfeeder-agent --config {CONFIG_FILE}")
        print()


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


def _has_user_dbus():
    """Check if D-Bus user session is available."""
    uid = os.getuid()
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    if os.path.isdir(runtime_dir):
        os.environ.setdefault("XDG_RUNTIME_DIR", runtime_dir)
        bus_path = f"{runtime_dir}/bus"
        if os.path.exists(bus_path):
            os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={bus_path}")
            return True
    return False


CRONTAB_TAG = "# clawfeeder-agent"


def _install_crontab(binary):
    """Install or update @reboot crontab entry."""
    entry = f"@reboot {binary} --config {CONFIG_FILE} {CRONTAB_TAG}"

    # Read existing crontab
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""

    lines = existing.splitlines()
    has_existing = any(CRONTAB_TAG in line for line in lines)

    if has_existing:
        # Replace existing entry
        lines = [entry if CRONTAB_TAG in line else line for line in lines]
        print(f"{GREEN}[INFO]{NC} Updating existing crontab entry.")
    else:
        lines.append(entry)

    new_crontab = "\n".join(lines).strip() + "\n"
    proc = subprocess.run(
        ["crontab", "-"], input=new_crontab, text=True, capture_output=True,
    )
    if proc.returncode != 0:
        print(f"{RED}[ERROR]{NC} Failed to install crontab: {proc.stderr.strip()}")
        return

    # Start the process now with nohup
    log_file = CONFIG_DIR / "logs" / "agent.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_fd = open(log_file, "a")
    proc = subprocess.Popen(
        ["nohup", binary, "--config", str(CONFIG_FILE)],
        stdout=log_fd,
        stderr=log_fd,
        start_new_session=True,
    )
    log_fd.close()

    time.sleep(2)
    if proc.poll() is not None:
        print(f"{RED}[ERROR]{NC} Agent exited immediately (code {proc.returncode}).")
        print(f"  Check logs: tail -20 {log_file}")
        print()
        return

    print()
    print(f"{GREEN}[OK]{NC} Crontab @reboot installed and agent started (PID {proc.pid}).")
    print()
    print(f"  View crontab:  crontab -l")
    print(f"  View logs:     tail -f {log_file}")
    print(f"  Check process: ps aux | grep clawfeeder")
    print(f"  Stop:          pkill -f clawfeeder-agent")
    print(f"  Uninstall:     crontab -l | grep -v '{CRONTAB_TAG}' | crontab -")
    print()


def _offer_systemd_service():
    """Ask the user whether to install a systemd service (system-level or user-level)."""
    is_root = os.geteuid() == 0

    if is_root:
        user_mode = False
    elif _has_user_dbus():
        user_mode = True
    else:
        binary = _find_binary() or "clawfeeder-agent"
        print()
        print(f"{YELLOW}[WARN]{NC} No D-Bus user session detected (common in SSH).")
        print(f"  User-level systemd service won't work in this environment.")
        print()
        print(f"  Options:")
        print(f"    1. Use system-level service:  sudo {binary} --setup")
        print(f"    2. Use crontab @reboot (no sudo needed)")
        print()
        answer = input("Install via crontab @reboot? [Y/n]: ").strip().lower()
        if answer in ("n", "no"):
            print()
            return
        _install_crontab(binary)
        return

    if user_mode:
        service_path = USER_SERVICE_PATH
        ctl = ["systemctl", "--user"]
    else:
        service_path = SYSTEM_SERVICE_PATH
        ctl = ["systemctl"]

    already_installed = service_path.exists()

    if already_installed:
        result = subprocess.run(
            ctl + ["is-active", SERVICE_NAME],
            capture_output=True, text=True,
        )
        is_running = result.stdout.strip() == "active"

        if is_running:
            print(f"{GREEN}[INFO]{NC} systemd service is already running.")
            answer = input("Restart service to apply new config? [Y/n]: ").strip().lower()
            if answer in ("n", "no"):
                print()
                return
            subprocess.run(ctl + ["restart", SERVICE_NAME], check=True)
            print(f"{GREEN}[OK]{NC} Service restarted.")
            print()
            return
        else:
            answer = input("Reinstall and start systemd service? [Y/n]: ").strip().lower()
    else:
        mode_hint = "user-level, no sudo needed" if user_mode else "system-level"
        answer = input(f"Install as systemd service ({mode_hint})? [Y/n]: ").strip().lower()

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

    if user_mode:
        unit = f"""[Unit]
Description=ClawFeeder Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={binary} --config {CONFIG_FILE}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""
        USER_SERVICE_DIR.mkdir(parents=True, exist_ok=True)
        service_path.write_text(unit)

        subprocess.run(ctl + ["daemon-reload"], check=True)
        subprocess.run(ctl + ["enable", SERVICE_NAME], check=True)
        subprocess.run(ctl + ["restart", SERVICE_NAME], check=True)

        # enable-linger so user services survive logout
        user = os.environ.get("USER", "")
        if user:
            subprocess.run(["loginctl", "enable-linger", user], capture_output=True)

        print()
        print(f"{GREEN}[OK]{NC} User service installed and started.")
        print()
        print(f"  Check status:  systemctl --user status {SERVICE_NAME}")
        print(f"  View logs:     journalctl --user -u {SERVICE_NAME} -f")
        print(f"  Stop:          systemctl --user stop {SERVICE_NAME}")
        print(f"  Disable:       systemctl --user disable {SERVICE_NAME}")
        print()

    else:
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
            service_path.write_text(unit)
        except PermissionError:
            print(f"{RED}[ERROR]{NC} Permission denied writing {service_path}")
            print(f"  Re-run with sudo: sudo {binary} --setup")
            return

        subprocess.run(ctl + ["daemon-reload"], check=True)
        subprocess.run(ctl + ["enable", SERVICE_NAME], check=True)
        subprocess.run(ctl + ["restart", SERVICE_NAME], check=True)

        print()
        print(f"{GREEN}[OK]{NC} System service installed and started.")
        print()
        print(f"  Check status:  systemctl status {SERVICE_NAME}")
        print(f"  View logs:     journalctl -u {SERVICE_NAME} -f")
        print(f"  Stop:          sudo systemctl stop {SERVICE_NAME}")
        print(f"  Disable:       sudo systemctl disable {SERVICE_NAME}")
        print()


def _is_launchd_loaded() -> bool:
    result = subprocess.run(
        ["launchctl", "list", LAUNCHD_LABEL],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _offer_launchd_service():
    """Ask the user whether to install a macOS launchd service."""
    already_installed = LAUNCHD_PLIST.exists()

    if already_installed:
        is_loaded = _is_launchd_loaded()

        if is_loaded:
            print(f"{GREEN}[INFO]{NC} launchd service is already running.")
            answer = input("Restart service to apply new config? [Y/n]: ").strip().lower()
            if answer in ("n", "no"):
                print()
                return
            subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)], capture_output=True)
            subprocess.run(["launchctl", "load", str(LAUNCHD_PLIST)], check=True)
            print(f"{GREEN}[OK]{NC} Service restarted.")
            print()
            return
        else:
            answer = input("Reinstall and start launchd service? [Y/n]: ").strip().lower()
    else:
        answer = input("Install as background service (auto-start on login)? [Y/n]: ").strip().lower()

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

    log_dir = CONFIG_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{binary}</string>
        <string>--config</string>
        <string>{CONFIG_FILE}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>{log_dir}/agent.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/agent.log</string>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
"""

    LAUNCHD_PLIST.parent.mkdir(parents=True, exist_ok=True)
    LAUNCHD_PLIST.write_text(plist)

    subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)], capture_output=True)
    subprocess.run(["launchctl", "load", str(LAUNCHD_PLIST)], check=True)

    print()
    print(f"{GREEN}[OK]{NC} Service installed and started.")
    print()
    print(f"  Check status:  launchctl list {LAUNCHD_LABEL}")
    print(f"  View logs:     tail -f {log_dir}/agent.log")
    print(f"  Stop:          launchctl unload {LAUNCHD_PLIST}")
    print(f"  Remove:        rm {LAUNCHD_PLIST}")
    print()


