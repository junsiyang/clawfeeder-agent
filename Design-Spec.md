# ClawFeeder Agent - Technical Design

**Version:** 1.0
**Date:** 2026-04-04
**Module:** Headless Worker Agent

---

## 1. Overview

**Purpose:** Headless worker that polls backend for keep-alive tasks, decrypts payloads locally, executes HTTP requests, and persists decrypted cookies to local filesystem.

**Core Principle:** "Client executes (Worker)." The agent polls for tasks, decrypts locally using the master key, executes HTTP requests from the user's real local IP, reports results, and persists cookies for other tools (AI agents, crawlers).

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ClawFeeder Agent                           │
│                                                             │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐ │
│  │ Heartbeat      │  │ Task           │  │ Keep-Alive   │ │
│  │ Poller         │  │ Executor       │  │ Executor     │ │
│  │ - POST        │  │ - Claim tasks  │  │ - Decrypt    │ │
│  │   /heartbeat  │  │ - Acquire lock │  │ - HTTP req   │ │
│  │ - Parse tasks │  │                │  │ - Detect     │ │
│  │               │  │                │  │   result     │ │
│  └────────────────┘  └────────────────┘  └──────────────┘ │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐ │
│  │ Status         │  │ Local File     │  │ Master Key   │ │
│  │ Reporter       │  │ Persister      │  │ Store        │ │
│  │ - PATCH status │  │ - Write JSON  │  │ - Config     │ │
│  │ - Release lock │  │ - Netscape    │  │   file       │ │
│  │                │  │   format       │  │ - Args       │ │
│  └────────────────┘  └────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Local filesystem
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ ~/.clawfeeder/                                             │
│ ├── data/                                                  │
│ │   ├── weibo.com.json       # Decrypted cookies (JSON)    │
│ │   ├── weibo.com.txt        # Decrypted cookies (Netscape)│
│ │   └── expired/              # Expired cookie files       │
│ ├── logs/                        # Agent logs               │
│ │   ├── agent.log             │
│ │   └── agent.err             │
│ └── config.yaml                 # Agent configuration       │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Technology Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.9+ |
| Async | asyncio |
| HTTP Client | httpx |
| Crypto | cryptography (PyNaCl) |
| YAML | PyYAML |
| Config | argparse + YAML |
| Deployment | systemd / launchd |

---

## 4. Data Flow

### 4.1 Heartbeat Loop

```
Every ~60 seconds:
        │
        ▼
Agent: POST /api/v1/agent/heartbeat { device_id, device_name }
        │
        ▼
Server: Returns available task IDs + encrypted payloads
        │
        ▼
For each task:
        │
        ├── Agent decrypts encrypted_data in memory
        │       (master key from config/args)
        │
        ├── Agent executes HTTP request from LOCAL IP
        │       │
        │       ├─── Success (2xx)?
        │       │       └─── PATCH /cookies/{id}/status { status: 'active' }
        │       │
        │       ├─── Auth failure (401/403)?
        │       │       └─── PATCH /cookies/{id}/status { status: 'expired' }
        │       │
        │       └─── Server error (5xx)?
        │               └─── Retry 3x with exponential backoff
        │
        ├── Agent writes decrypted cookies to local files:
        │       ~/.clawfeeder/data/{domain}.json
        │       ~/.clawfeeder/data/{domain}.txt (Netscape format)
        │
        └── Agent releases lock (via PATCH status)

        │
        ▼
After processing tasks, Agent runs Local File GC:
        │
        ▼
Agent: GET /api/v1/cookies?status=active
        │
        ▼
Agent: Compare cloud domains vs local files
        │
        ├─── Local file exists but domain NOT in cloud?
        │       └─── DELETE local file
        │
        ├─── Local file exists but status = 'expired'?
        │       └─── MOVE to expired/
        │
        └─── Keep active files in place
```

---

## 5. Decryption Flow

### 5.1 Key Derivation (mirrors extension)

```
Master Password (from config/args)
      │
      ├── PBKDF2 (100,000 iterations, SHA-256)
      │   Salt: "cookie-manager-salt-v1" (fixed, must match extension)
      │
      ▼
   256-bit AES Key
      │
      ▼
   AES-256-GCM Decrypt
```

### 5.2 Crypto Implementation

```python
# src/crypto.py

import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SALT = "cookie-manager-salt-v1"
ITERATIONS = 100_000

def derive_key(password: str) -> bytes:
    """Derive AES key from password using PBKDF2."""
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        SALT.encode('utf-8'),
        ITERATIONS,
        dklen=32
    )
    return key

def decrypt_payload(payload: dict, password: str) -> dict:
    """Decrypt encrypted payload."""
    key = derive_key(password)
    aesgcm = AESGCM(key)

    salt = base64.b64decode(payload['salt'])
    iv = base64.b64decode(payload['iv'])
    ciphertext = base64.b64decode(payload['ciphertext'])

    # The salt is prepended for JS compatibility
    decrypted = aesgcm.decrypt(iv, ciphertext, salt)
    return json.loads(decrypted.decode('utf-8'))
```

---

## 6. Configuration

### 6.1 config.yaml

```yaml
api:
  base_url: "http://localhost:8000"
  heartbeat_interval: 60  # seconds

auth:
  email: "user@example.com"
  password: "masterpassword"  # Also used for E2EE decryption

storage:
  data_dir: "~/.clawfeeder/data"
  expired_dir: "~/.clawfeeder/data/expired"

device:
  device_id: "local-agent-001"
  device_name: "Local Agent"
```

### 6.2 Command Line Arguments

```bash
python -m src.main [options]

Options:
  --config PATH       Config file path (default: config.yaml)
  --device-id ID     Override device ID
  --device-name NAME  Override device name
  --email EMAIL       Email for authentication
  --password PASSWORD Password for authentication (also used for E2EE)
```

---

## 7. Local File Storage

### 7.1 Directory Structure

```
~/.clawfeeder/
├── config.yaml           # Agent configuration
├── data/
│   ├── weibo.com.json    # Active cookies (JSON format)
│   ├── weibo.com.txt     # Active cookies (Netscape format)
│   └── expired/
│       ├── twitter.com.json  # Expired cookies
│       └── old-domain.json
└── logs/
    ├── agent.log         # Info logs
    └── agent.err         # Error logs
```

### 7.2 JSON Format

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
  "updatedAt": "2026-03-28T10:00:00Z"
}
```

### 7.3 Netscape Format

```
# Netscape HTTP Cookie File
# This file was generated by ClawFeeder Agent

.weibo.com	TRUE	/	TRUE	1735689600	SESSIONID	abc123...
```

---

## 8. API Integration

### 8.1 Endpoints Used

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/login` | Authenticate, get API key |
| POST | `/api/v1/agent/heartbeat` | Poll for tasks |
| GET | `/api/v1/cookies` | List cookies (for GC) |
| GET | `/api/v1/cookies/{id}` | Get specific blob |
| PATCH | `/api/v1/cookies/{id}/status` | Report task result |

### 8.2 Authentication Flow

```
1. Call POST /api/v1/login with email + password
2. Backend returns { user_id, api_key, registered }
3. Store api_key for subsequent API calls
4. Use password for E2EE decryption (never sent after login)
```

---

## 9. Project Structure

```
clawfeeder-agent/
├── src/
│   ├── __init__.py
│   ├── main.py           # Entry point, orchestrates components
│   ├── config.py         # Config loader
│   ├── api.py            # API client (httpx)
│   ├── crypto.py         # E2EE decryption
│   ├── heartbeat.py      # Heartbeat poller
│   ├── executor.py        # Keep-alive HTTP executor
│   └── storage.py         # Local file persistence
├── config.yaml           # Default configuration
├── requirements.txt
├── install.sh            # One-line installer
└── README.md
```

---

## 10. Implemented Features

| Feature | Status |
|---------|--------|
| Heartbeat polling (~60s interval) | ✅ |
| Distributed locking | ✅ |
| E2EE decryption (PBKDF2 + AES-GCM) | ✅ |
| Keep-alive HTTP execution | ✅ |
| Status reporting (active/expired) | ✅ |
| Local file persistence (JSON) | ✅ |
| Netscape format export | ✅ |
| Local file GC | ✅ |
| Command line arguments | ✅ |
| Config file support | ✅ |
| Service installation (systemd/launchd) | ✅ |

---

## 11. Not Implemented (Future)

| Feature | Description |
|---------|-------------|
| Cookie rotation detection | Detect Set-Cookie in response, update blob |
| OS Keychain integration | Store master key in macOS Keychain |
| Master key caching | Keep key in memory, reload from keychain on restart |
| Exponential backoff retry | Retry failed requests with backoff |
| Config hot reload | Reload config without restart |
| TLS client cert | mTLS for agent-backend communication |
| Proxy support | Route through proxy |

---

## 12. Security Considerations

- Master password stored in config file or passed as argument
- Consider using OS keychain for production deployments
- API key used for all backend communication
- Decrypted cookies written to local filesystem
- No cloud sync of decrypted data
- Network traffic should use HTTPS in production
