# PyChatter Windows Client (Python)

Python desktop client for PyChatter on Windows 10.

## Features

- Login/Register auth flow
- Channel list and switching
- Real-time chat messages
- Member list and user actions
- Direct messages and DM history
- Admin role management
- Reconnect handling and saved WebSocket settings

## Requirements

- Python 3.10+
- Running PyChatter backend + web bridge (WebSocket endpoint)

## Setup

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

By default, it connects to:

```text
ws://127.0.0.1:9011/ws
```

You can change the WebSocket URL and reconnect delay in the login screen and save it.

## Build EXE (Windows)

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name PyChatter app.py
```

Output executable:

```text
dist\\PyChatter\\PyChatter.exe
```
