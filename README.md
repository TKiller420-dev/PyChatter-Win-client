# PyChatter Windows Client (Electron + Python Bridge)

Electron desktop client for PyChatter on Windows, with a Python bridge process for WebSocket transport.

## Features

- Login/Register auth flow
- Channel list and switching
- Real-time chat messages
- Member list and user actions
- Direct messages and DM history
- Admin role management
- Reconnect handling and saved WebSocket settings

## Requirements

- Node.js 18+
- Python 3.10+
- Running PyChatter backend + web bridge (WebSocket endpoint)

## Setup

```bash
npm install
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

## Run

```bash
npm start
```

By default, it connects to:

```text
ws://127.0.0.1:9011/ws
```

You can change the WebSocket URL and reconnect delay in the login screen and save it.

## Build EXE (Windows)

```bash
npm run dist:win
```

Output executable:

```text
dist\\
```
