# ClawFeeder Agent

Headless worker that polls for tasks, decrypts cookie data locally, and executes keep-alive HTTP requests.

## Features

- **Heartbeat Polling** — polls backend every ~60s for available tasks
- **Distributed Locking** — claims tasks atomically to prevent duplicate execution
- **E2EE Decryption** — decrypts payload locally using master key (PBKDF2 + AES-256-GCM)
- **Keep-Alive Execution** — executes HTTP requests from user's real local IP
- **Local File Storage** — persists decrypted cookies to filesystem
- **Domain Filtering** — optionally sync only specified domains
- **Garbage Collection** — removes local files no longer present in cloud

## Authentication

The agent uses an API key (`cf_agt_...`) for backend authentication. The master key is separate and used only for local E2EE decryption — it is never sent to the backend.

## Configuration

`~/.clawfeeder/config.yaml`:

```yaml
auth:
  api_key: "cf_agt_..."

storage:
  data_dir: "~/.clawfeeder/data"
  expired_dir: "~/.clawfeeder/data/expired"

device:
  device_id: "auto-generated-uuid"
  device_name: "my-server"

master_key: "your-master-password"

# Optional: sync only specific domains (omit for all)
sync:
  domains:
    - weibo.com
    - twitter.com
```

## CLI Options

```
python -m src.main [options]

  --config PATH        Config file path (default: config.yaml)
  --device-id ID       Override device ID
  --device-name NAME   Override device name
  --api-key KEY        API key for authentication (cf_agt_...)
```

## Local File Storage

```
~/.clawfeeder/
├── config.yaml
├── clawfeeder-agent        # Binary (after install)
├── data/
│   ├── weibo.com.json      # Active cookies
│   └── expired/            # Expired cookies
└── logs/
    └── agent.log
```

## Architecture

```
┌────────────────────────────────────────────────────┐
│                 ClawFeeder Agent                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │  Heartbeat   │  │    Task      │  │  Crypto  │ │
│  │   Poller     │──▶│  Executor   │──▶│ (E2EE)  │ │
│  └──────────────┘  └──────────────┘  └──────────┘ │
│  ┌──────────────┐  ┌──────────────┐               │
│  │   Storage    │  │   Config     │               │
│  │  (local fs)  │  │  (YAML)     │               │
│  └──────────────┘  └──────────────┘               │
└────────────────────────────────────────────────────┘
```

## Deployment

See [../docs/deployment.md](../docs/deployment.md) for build, install, and service management instructions.

## License

MIT
