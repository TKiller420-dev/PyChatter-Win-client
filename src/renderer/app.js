const state = {
  authMode: "login",
  username: "",
  role: "member",
  currentChannel: "general",
  channels: [],
  users: [],
  selectedUser: "",
  isAuthed: false,
  typingTimer: null,
};

const $ = (id) => document.getElementById(id);

const ui = {
  authView: $("authView"),
  appView: $("appView"),
  authTitle: $("authTitle"),
  authSubtitle: $("authSubtitle"),
  showLoginBtn: $("showLoginBtn"),
  showRegisterBtn: $("showRegisterBtn"),
  authForm: $("authForm"),
  usernameInput: $("usernameInput"),
  passwordInput: $("passwordInput"),
  wsUrlInput: $("wsUrlInput"),
  reconnectDelayInput: $("reconnectDelayInput"),
  saveConnectionBtn: $("saveConnectionBtn"),
  authSubmitBtn: $("authSubmitBtn"),
  authStatus: $("authStatus"),
  channels: $("channels"),
  users: $("users"),
  selfUser: $("selfUser"),
  statusText: $("statusText"),
  channelTitle: $("channelTitle"),
  channelMeta: $("channelMeta"),
  roleBadge: $("roleBadge"),
  messages: $("messages"),
  typingIndicator: $("typingIndicator"),
  messageInput: $("messageInput"),
  sendBtn: $("sendBtn"),
  newChannelBtn: $("newChannelBtn"),
  refreshUsersBtn: $("refreshUsersBtn"),
  changeNameBtn: $("changeNameBtn"),
  dmBtn: $("dmBtn"),
  dmHistoryBtn: $("dmHistoryBtn"),
  promoteBtn: $("promoteBtn"),
  restartBridgeBtn: $("restartBridgeBtn"),
};

function setStatus(text) {
  ui.statusText.textContent = text;
}

function setAuthStatus(text, ok = false) {
  ui.authStatus.textContent = text;
  ui.authStatus.style.color = ok ? "#86efac" : "#fda4af";
}

function setMode(mode) {
  state.authMode = mode;
  const isLogin = mode === "login";
  ui.showLoginBtn.classList.toggle("active", isLogin);
  ui.showRegisterBtn.classList.toggle("active", !isLogin);
  ui.authTitle.textContent = isLogin ? "Welcome back" : "Create your account";
  ui.authSubtitle.textContent = isLogin
    ? "Log in to continue chatting with your server."
    : "Register and jump into your channels.";
  ui.authSubmitBtn.textContent = isLogin ? "Sign In" : "Register";
}

function setAppVisible(show) {
  ui.authView.classList.toggle("hidden", show);
  ui.appView.classList.toggle("hidden", !show);
}

function bridgeCommand(command) {
  return window.pychatterBridge.sendCommand(command);
}

async function sendPacket(packet) {
  const ok = await bridgeCommand({ command: "send", packet });
  if (!ok) {
    appendSystem("Bridge not connected. Try restarting bridge.");
  }
}

async function saveConnectionSettings() {
  const wsUrl = ui.wsUrlInput.value.trim();
  const reconnectDelay = Number(ui.reconnectDelayInput.value.trim());

  if (!wsUrl) {
    setAuthStatus("WebSocket URL is required");
    return;
  }

  if (!Number.isFinite(reconnectDelay)) {
    setAuthStatus("Reconnect delay must be a number");
    return;
  }

  await bridgeCommand({
    command: "set_settings",
    settings: {
      ws_url: wsUrl,
      reconnect_delay: Math.max(0.5, Math.min(10, reconnectDelay)),
    },
  });

  setAuthStatus("Connection settings saved", true);
}

async function handleAuthSubmit(event) {
  event.preventDefault();

  const username = ui.usernameInput.value.trim().toLowerCase();
  const password = ui.passwordInput.value;

  if (!username || !password) {
    setAuthStatus("Username and password are required");
    return;
  }

  setAuthStatus("");
  await sendPacket({
    type: "auth",
    action: state.authMode,
    username,
    password,
  });
}

function appendMessage(author, content, system = false) {
  const row = document.createElement("article");
  row.className = `msg${system ? " system" : ""}`;

  const who = document.createElement("div");
  who.className = "who";
  who.textContent = author;

  const text = document.createElement("div");
  text.className = "text";
  text.textContent = content;

  row.append(who, text);
  ui.messages.appendChild(row);
  ui.messages.scrollTop = ui.messages.scrollHeight;
}

function appendSystem(text) {
  appendMessage("System", text, true);
}

function renderChannels() {
  ui.channels.innerHTML = "";
  state.channels.forEach((channel) => {
    const li = document.createElement("li");
    li.textContent = `#${channel}`;
    li.classList.toggle("active", channel === state.currentChannel);
    li.addEventListener("click", () => {
      if (channel !== state.currentChannel) {
        sendPacket({ type: "switch_channel", channel });
      }
    });
    ui.channels.appendChild(li);
  });
}

function renderUsers() {
  ui.users.innerHTML = "";
  state.users.forEach((user) => {
    const li = document.createElement("li");
    li.textContent = user;
    li.classList.toggle("active", user === state.selectedUser);
    li.addEventListener("click", () => {
      state.selectedUser = user;
      renderUsers();
    });
    ui.users.appendChild(li);
  });
}

function renderHistory(history) {
  ui.messages.innerHTML = "";
  history.forEach((item) => {
    const deleted = Boolean(item.deleted);
    appendMessage(item.author || "?", deleted ? "[deleted]" : item.content || "");
  });
}

function updateRole(role) {
  state.role = role;
  ui.roleBadge.textContent = role;
}

function requireSelectedUser() {
  if (!state.selectedUser) {
    appendSystem("Select a user first");
    return null;
  }
  return state.selectedUser;
}

async function sendMessage() {
  if (!state.isAuthed) {
    appendSystem("Authenticate first");
    return;
  }

  const content = ui.messageInput.value.trim();
  if (!content) {
    return;
  }

  await sendPacket({ type: "message", content });
  ui.messageInput.value = "";
}

function sendTypingSignal() {
  if (!state.isAuthed) {
    return;
  }
  sendPacket({ type: "typing" });
}

function handlePacket(packet) {
  const packetType = packet.type || "";

  if (packetType === "auth_ok") {
    state.username = packet.username || state.username;
    state.isAuthed = true;
    updateRole(packet.role || "member");
    ui.selfUser.textContent = state.username || "guest";
    appendSystem(`Logged in as ${state.username}`);
    setAppVisible(true);
    sendPacket({ type: "who" });
    return;
  }

  if (packetType === "auth_error") {
    setAuthStatus(packet.message || "Authentication failed");
    return;
  }

  if (packetType === "welcome" || packetType === "channel_switched") {
    state.currentChannel = packet.channel || "general";
    state.channels = Array.isArray(packet.channels) ? packet.channels : ["general"];
    ui.channelTitle.textContent = `#${state.currentChannel}`;
    ui.messageInput.placeholder = `Message #${state.currentChannel}`;
    renderChannels();
    renderHistory(Array.isArray(packet.history) ? packet.history : []);
    return;
  }

  if (packetType === "user_list") {
    state.users = Array.isArray(packet.users) ? packet.users : [];
    if (!state.users.includes(state.selectedUser)) {
      state.selectedUser = "";
    }
    renderUsers();
    return;
  }

  if (packetType === "message") {
    appendMessage(packet.author || "?", packet.content || "");
    return;
  }

  if (packetType === "typing") {
    const user = packet.username || "";
    const channel = packet.channel || "";
    if (user && user !== state.username && channel === state.currentChannel) {
      ui.typingIndicator.textContent = `${user} is typing...`;
      window.clearTimeout(state.typingTimer);
      state.typingTimer = window.setTimeout(() => {
        ui.typingIndicator.textContent = "";
      }, 2000);
    }
    return;
  }

  if (packetType === "dm") {
    const sender = packet.sender || "";
    const recipient = packet.recipient || "";
    const peer = sender === state.username ? recipient : sender;
    appendSystem(`DM with ${peer}: ${packet.content || ""}`);
    return;
  }

  if (packetType === "dm_history") {
    appendSystem(`--- DM history with ${packet.with || "?"} ---`);
    const history = Array.isArray(packet.history) ? packet.history : [];
    history.forEach((item) => {
      appendSystem(`${item.sender || "?"}: ${item.content || ""}`);
    });
    return;
  }

  if (packetType === "role_update") {
    updateRole(packet.role || state.role);
    appendSystem(`Role updated to ${state.role}`);
    return;
  }

  if (packetType === "username_changed") {
    state.username = packet.username || state.username;
    ui.selfUser.textContent = state.username;
    appendSystem(`Username changed to ${state.username}`);
    return;
  }

  if (packetType === "action_error" || packetType === "system") {
    appendSystem(packet.message || "Action failed");
  }
}

function handleBridgeEvent(event) {
  if (!event || typeof event !== "object") {
    return;
  }

  if (event.event === "status") {
    setStatus(event.value || "Status updated");
    return;
  }

  if (event.event === "settings") {
    const wsUrl = event.settings?.ws_url || "ws://127.0.0.1:9011/ws";
    const reconnectDelay = String(event.settings?.reconnect_delay ?? 2);
    ui.wsUrlInput.value = wsUrl;
    ui.reconnectDelayInput.value = reconnectDelay;
    return;
  }

  if (event.event === "packet") {
    handlePacket(event.packet || {});
  }
}

function initActions() {
  ui.showLoginBtn.addEventListener("click", () => setMode("login"));
  ui.showRegisterBtn.addEventListener("click", () => setMode("register"));
  ui.authForm.addEventListener("submit", handleAuthSubmit);
  ui.saveConnectionBtn.addEventListener("click", saveConnectionSettings);

  ui.sendBtn.addEventListener("click", sendMessage);
  ui.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      sendMessage();
    }
  });
  ui.messageInput.addEventListener("input", sendTypingSignal);

  ui.newChannelBtn.addEventListener("click", () => {
    const raw = window.prompt("Channel name:");
    if (!raw) {
      return;
    }
    const channel = raw.trim().toLowerCase().replace(/\s+/g, "-");
    if (!channel) {
      return;
    }
    sendPacket({ type: "switch_channel", channel });
  });

  ui.refreshUsersBtn.addEventListener("click", () => sendPacket({ type: "who" }));

  ui.changeNameBtn.addEventListener("click", () => {
    const raw = window.prompt("New username:");
    if (!raw) {
      return;
    }
    const normalized = raw.trim().toLowerCase();
    if (!normalized) {
      return;
    }
    sendPacket({ type: "change_username", new_username: normalized });
  });

  ui.dmBtn.addEventListener("click", () => {
    const target = requireSelectedUser();
    if (!target) {
      return;
    }
    const text = window.prompt(`Send to ${target}:`);
    if (!text || !text.trim()) {
      return;
    }
    sendPacket({ type: "dm", to: target.toLowerCase(), content: text.trim() });
  });

  ui.dmHistoryBtn.addEventListener("click", () => {
    const target = requireSelectedUser();
    if (!target) {
      return;
    }
    sendPacket({ type: "dm_history", with: target.toLowerCase() });
  });

  ui.promoteBtn.addEventListener("click", () => {
    if (state.role !== "admin") {
      appendSystem("Only admins can set roles");
      return;
    }

    const target = requireSelectedUser();
    if (!target) {
      return;
    }

    const role = window.prompt("Role: member | mod | admin");
    const normalized = (role || "").trim().toLowerCase();
    if (!["member", "mod", "admin"].includes(normalized)) {
      appendSystem("Invalid role");
      return;
    }

    sendPacket({ type: "promote", username: target.toLowerCase(), role: normalized });
  });

  ui.restartBridgeBtn.addEventListener("click", async () => {
    await window.pychatterBridge.restartBridge();
    appendSystem("Bridge restart requested");
  });
}

function init() {
  setMode("login");
  setStatus("Connecting...");
  setAppVisible(false);
  initActions();
  window.pychatterBridge.onEvent(handleBridgeEvent);
}

init();
