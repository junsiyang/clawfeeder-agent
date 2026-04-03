# ClawFeeder Agent

Headless worker that polls for tasks, executes keep-alive requests, and persists decrypted cookies locally.

## Features

- **Heartbeat Polling** - Poll backend every ~60s for available tasks
- **Distributed Locking** - Claim tasks atomically to prevent duplicate execution
- **E2EE Decryption** - Decrypt payload locally using master key
- **Keep-Alive Execution** - Execute HTTP requests from user's real local IP
- **Local File Storage** - Persist decrypted cookies to filesystem
- **Garbage Collection** - Sync local files with cloud state

## Installation

### One-Line Installation (Recommended)

```bash
curl -sSL https://your-domain.com/install.sh | bash
```

The installer will:
1. Detect your OS (Linux/macOS) and architecture
2. Download the latest binary
3. Set up config directory at `~/.clawfeeder/`
4. Register as a systemd service (Linux) or launchd daemon (macOS)
5. Start the service automatically

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/junsiyang/clawfeeder-agent.git
cd clawfeeder-agent

# Install dependencies
pip install -r requirements.txt

# Create config directory
mkdir -p ~/.clawfeeder
cp config.yaml ~/.clawfeeder/

# Run directly
python -m src.main --config ~/.clawfeeder/config.yaml --email "you@example.com" --password "yourpassword"
```

## Configuration

Edit `~/.clawfeeder/config.yaml`:

```yaml
api:
  base_url: "http://localhost:8000"
  heartbeat_interval: 60  # seconds

auth:
  email: "your@email.com"
  password: "yourpassword"

storage:
  data_dir: "~/.clawfeeder/data"
  expired_dir: "~/.clawfeeder/data/expired"

device:
  device_id: "auto-generated-uuid"
  device_name: "my-server"
```

## Usage

### Command Line Options

```bash
python -m src.main [options]

Options:
  --config PATH       Config file path (default: config.yaml)
  --device-id ID     Override device ID
  --device-name NAME  Override device name
  --email EMAIL       Email for authentication
  --password PASSWORD Password for authentication (also used for E2EE)
```

### Authentication Flow

The agent authenticates using email + password:

1. Agent calls `POST /api/v1/login` with email and password
2. Backend returns `api_key`
3. Agent uses `api_key` for all subsequent API calls (heartbeat, status updates, etc.)
4. Password is also used locally for E2EE decryption of cookie data (never sent to backend)

### Running as Service

#### Linux (systemd)

```bash
sudo systemctl start clawfeeder
sudo systemctl status clawfeeder
sudo systemctl enable clawfeeder  # Auto-start on boot
```

#### macOS (launchd)

```bash
launchctl load ~/Library/LaunchAgents/io.clawfeeder.plist
launchctl unload ~/Library/LaunchAgents/io.clawfeeder.plist
```

## Local File Storage

Decrypted cookies are saved to:

```
~/.clawfeeder/
├── data/
│   ├── weibo.com.json       # Active cookies
│   └── twitter.com.json
├── data/expired/
│   └── old-domain.json      # Expired cookies
└── logs/
    ├── agent.log
    └── agent.err
```

Cookie file format:

```json
{
  "domain": "weibo.com",
  "cookies": [
    {
      "name": "SESSIONID",
      "value": "abc123...",
      "domain": ".weibo.com",
      "path": "/",
      "expires": 1735689600,
      "httpOnly": true,
      "secure": true
    }
  ],
  "capturedAt": "2026-03-28T10:00:00Z",
  "keepAlive": {
    "url": "https://api.weibo.com/heartbeat",
    "method": "GET",
    "headers": {}
  }
}
```

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    ClawFeeder Agent                         │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐ │
│  │ Heartbeat      │  │ Task           │  │ Keep-Alive   │ │
│  │ Poller         │  │ Executor       │  │ Executor     │ │
│  └────────────────┘  └────────────────┘  └──────────────┘ │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐ │
│  │ Status         │  │ Local File     │  │ Master Key   │ │
│  │ Reporter       │  │ Persister      │  │ Store        │ │
│  └────────────────┘  └────────────────┘  └──────────────┘ │
└────────────────────────────────────────────────────────────┘
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/agent/heartbeat` | POST | Poll for available tasks |
| `/api/v1/cookies` | GET | List cookie sets |
| `/api/v1/cookies/{id}` | GET | Get specific cookie set |
| `/api/v1/cookies/{id}/status` | PATCH | Update task status |

## License

MIT
