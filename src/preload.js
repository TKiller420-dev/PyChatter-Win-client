const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("pychatterBridge", {
  sendCommand: (command) => ipcRenderer.invoke("bridge:command", command),
  restartBridge: () => ipcRenderer.invoke("bridge:restart"),
  onEvent: (callback) => {
    const wrapped = (_event, payload) => callback(payload);
    ipcRenderer.on("bridge:event", wrapped);
    return () => ipcRenderer.removeListener("bridge:event", wrapped);
  },
});
