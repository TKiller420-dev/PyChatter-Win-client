const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

let win = null;
let pyProc = null;
let pyBuffer = "";

function bridgePath() {
  return path.join(__dirname, "..", "python", "bridge.py");
}

function getPythonCommand() {
  if (process.env.PYCHATTER_PYTHON) {
    return { cmd: process.env.PYCHATTER_PYTHON, args: [bridgePath()] };
  }
  return { cmd: process.platform === "win32" ? "py" : "python3", args: process.platform === "win32" ? ["-3", bridgePath()] : [bridgePath()] };
}

function sendToRenderer(event) {
  if (win && !win.isDestroyed()) {
    win.webContents.send("bridge:event", event);
  }
}

function startPythonBridge() {
  const bridgeFile = bridgePath();
  if (!fs.existsSync(bridgeFile)) {
    sendToRenderer({ event: "status", value: "Python bridge missing" });
    return;
  }

  const py = getPythonCommand();
  pyProc = spawn(py.cmd, py.args, {
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });

  pyProc.stdout.on("data", (chunk) => {
    pyBuffer += chunk.toString("utf-8");
    let idx = pyBuffer.indexOf("\n");
    while (idx !== -1) {
      const line = pyBuffer.slice(0, idx).trim();
      pyBuffer = pyBuffer.slice(idx + 1);
      if (line) {
        try {
          const event = JSON.parse(line);
          sendToRenderer(event);
        } catch {
          sendToRenderer({ event: "status", value: `Bridge output parse error: ${line}` });
        }
      }
      idx = pyBuffer.indexOf("\n");
    }
  });

  pyProc.stderr.on("data", (chunk) => {
    sendToRenderer({ event: "status", value: `Bridge error: ${chunk.toString("utf-8").trim()}` });
  });

  pyProc.on("close", (code) => {
    sendToRenderer({ event: "status", value: `Bridge exited (${code ?? "?"})` });
    pyProc = null;
  });

  sendToRenderer({ event: "status", value: "Python bridge started" });
}

function sendBridgeCommand(command) {
  if (!pyProc || pyProc.killed || !pyProc.stdin.writable) {
    return false;
  }
  pyProc.stdin.write(`${JSON.stringify(command)}\n`);
  return true;
}

function createWindow() {
  win = new BrowserWindow({
    width: 1340,
    height: 860,
    minWidth: 1000,
    minHeight: 680,
    title: "PyChatter",
    autoHideMenuBar: true,
    backgroundColor: "#1e1f22",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

app.whenReady().then(() => {
  createWindow();
  startPythonBridge();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

ipcMain.handle("bridge:command", (_event, command) => {
  return sendBridgeCommand(command);
});

ipcMain.handle("bridge:restart", () => {
  if (pyProc) {
    pyProc.kill();
    pyProc = null;
  }
  pyBuffer = "";
  startPythonBridge();
  return true;
});

app.on("before-quit", () => {
  if (pyProc) {
    pyProc.kill();
  }
});
