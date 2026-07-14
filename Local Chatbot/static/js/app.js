const state = {
  conversations: [],
  activeConversationId: null,
  currentMessages: [],
  models: [],
  isStreaming: false,
  settings: {
    systemPrompt: "You are a helpful assistant",
    temperature: 0.7,
    maxTokens: 512,
    topP: 0.9,
    topK: 40,
    model: "llama3.2"
  }
};

const els = {
  conversationList: document.getElementById("conversationList"),
  messageInput: document.getElementById("messageInput"),
  sendBtn: document.getElementById("sendBtn"),
  messages: document.getElementById("messages"),
  newChatBtn: document.getElementById("newChatBtn"),
  conversationSearch: document.getElementById("conversationSearch"),
  chatTitle: document.getElementById("chatTitle"),
  chatMeta: document.getElementById("chatMeta"),
  settingsToggle: document.getElementById("settingsToggle"),
  settingsPanel: document.getElementById("settingsPanel"),
  systemPromptInput: document.getElementById("systemPromptInput"),
  temperatureInput: document.getElementById("temperatureInput"),
  temperatureValue: document.getElementById("temperatureValue"),
  maxTokensInput: document.getElementById("maxTokensInput"),
  topPInput: document.getElementById("topPInput"),
  topPValue: document.getElementById("topPValue"),
  topKInput: document.getElementById("topKInput"),
  modelSelect: document.getElementById("modelSelect"),
  themeToggle: document.getElementById("themeToggle"),
  exportBtn: document.getElementById("exportBtn"),
  pullModelInput: document.getElementById("pullModelInput"),
  pullModelBtn: document.getElementById("pullModelBtn"),
  modelInfo: document.getElementById("modelInfo")
};

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[char]);
}

function renderMessage(message) {
  const bubble = document.createElement("div");
  bubble.className = `message ${message.role}`;
  bubble.innerHTML = `
    <div class="message-content">${renderMarkdown(message.content || "")}</div>
    <div class="message-actions">
      <button data-action="copy">Copy</button>
      ${message.role === "assistant" ? '<button data-action="regenerate">Regenerate</button>' : ""}
      ${message.role === "user" ? '<button data-action="edit">Edit</button>' : ""}
    </div>
  `;
  if (window.hljs) {
    bubble.querySelector(".message-content").querySelectorAll("pre code").forEach((block) => window.hljs.highlightElement(block));
  }
  bubble.querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => handleMessageAction(message, btn.dataset.action);
  });
  els.messages.appendChild(bubble);
}

function renderMarkdown(content) {
  if (!window.marked) return escapeHtml(content).replace(/\n/g, "<br>");
  const renderer = new marked.Renderer();
  renderer.html = (html) => escapeHtml(html);
  return marked.parse(content, { renderer });
}

function renderConversationList() {
  els.conversationList.innerHTML = "";
  const query = els.conversationSearch.value.trim().toLowerCase();
  const filtered = state.conversations.filter((c) => `${c.title}`.toLowerCase().includes(query));
  filtered.forEach((conv) => {
    const item = document.createElement("button");
    item.className = `conversation-item ${conv.id === state.activeConversationId ? "active" : ""}`;
    item.innerHTML = `
      <span class="conversation-title">${escapeHtml(conv.title || "Untitled")}</span>
      <span class="conversation-actions">
        <button data-action="rename" title="Rename">✏️</button>
        <button data-action="delete" title="Delete">🗑️</button>
      </span>
    `;
    item.onclick = () => loadConversation(conv.id);
    item.querySelectorAll("button").forEach((btn) => {
      btn.onclick = (event) => {
        event.stopPropagation();
        handleConversationAction(conv.id, btn.dataset.action);
      };
    });
    els.conversationList.appendChild(item);
  });
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || response.statusText || "Request failed");
  }
  return response.json();
}

async function loadConversations() {
  const conversations = await fetchJson("/api/conversations");
  state.conversations = conversations;
  if (!state.activeConversationId && conversations.length) {
    await loadConversation(conversations[0].id);
  } else {
    renderConversationList();
  }
}

async function loadConversation(id) {
  state.activeConversationId = id;
  const conversation = await fetchJson(`/api/conversations/${id}`);
  state.currentMessages = conversation.messages || [];
  state.settings = {
    systemPrompt: conversation.system_prompt || "You are a helpful assistant",
    temperature: conversation.temperature || 0.7,
    maxTokens: conversation.max_tokens || 512,
    topP: conversation.top_p || 0.9,
    topK: conversation.top_k || 40,
    model: conversation.model || state.settings.model
  };
  syncFormFromSettings();
  els.chatTitle.textContent = conversation.title || "New conversation";
  els.chatMeta.textContent = `Model: ${conversation.model}`;
  renderMessages();
  renderConversationList();
}

function syncFormFromSettings() {
  els.systemPromptInput.value = state.settings.systemPrompt;
  els.temperatureInput.value = state.settings.temperature;
  els.temperatureValue.textContent = state.settings.temperature;
  els.maxTokensInput.value = state.settings.maxTokens;
  els.topPInput.value = state.settings.topP;
  els.topPValue.textContent = state.settings.topP;
  els.topKInput.value = state.settings.topK;
  els.modelSelect.value = state.settings.model;
}

function renderMessages() {
  els.messages.innerHTML = "";
  state.currentMessages.forEach(renderMessage);
  scrollToBottom();
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

function setStreaming(isStreaming) {
  state.isStreaming = isStreaming;
  els.sendBtn.disabled = isStreaming;
  els.sendBtn.textContent = isStreaming ? "Thinking..." : "Send";
  els.messageInput.disabled = isStreaming;
}

async function createConversation() {
  const payload = {
    title: "New conversation",
    system_prompt: state.settings.systemPrompt,
    model: state.settings.model,
    temperature: state.settings.temperature,
    maxTokens: state.settings.maxTokens,
    topP: state.settings.topP,
    topK: state.settings.topK
  };
  const result = await fetchJson("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  state.activeConversationId = result.id;
  state.currentMessages = [];
  els.chatTitle.textContent = "New conversation";
  els.chatMeta.textContent = `Model: ${state.settings.model}`;
  renderMessages();
  await loadConversations();
}

async function saveSettings() {
  if (!state.activeConversationId) return;
  await fetchJson(`/api/conversations/${state.activeConversationId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      system_prompt: state.settings.systemPrompt,
      model: state.settings.model,
      temperature: state.settings.temperature,
      max_tokens: state.settings.maxTokens,
      top_p: state.settings.topP,
      top_k: state.settings.topK
    })
  });
  await loadConversations();
}

async function loadModels() {
  let models = [];
  try {
    models = await fetchJson("/api/models");
  } catch (error) {
    els.modelInfo.textContent = `Ollama is unavailable: ${error.message}`;
  }
  state.models = models;
  els.modelSelect.innerHTML = "";
  if (!models.some((model) => model.name === state.settings.model)) {
    models.unshift({ name: state.settings.model });
  }
  models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model.name;
    option.textContent = model.name;
    els.modelSelect.appendChild(option);
  });
  if (state.settings.model) {
    els.modelSelect.value = state.settings.model;
  }
}

async function sendMessage(contentOverride = null, persistUserMessage = true) {
  if (state.isStreaming) return;
  if (!state.activeConversationId) await createConversation();
  const content = (contentOverride ?? els.messageInput.value).trim();
  if (!content || !state.activeConversationId) return;
  if (contentOverride === null) els.messageInput.value = "";
  setStreaming(true);

  if (persistUserMessage) {
    const userMessage = { role: "user", content };
    state.currentMessages.push(userMessage);
    renderMessages();
  }

  const assistantPlaceholder = document.createElement("div");
  assistantPlaceholder.className = "message assistant typing-indicator";
  assistantPlaceholder.textContent = "Thinking...";
  els.messages.appendChild(assistantPlaceholder);
  scrollToBottom();

  try {
    if (persistUserMessage) {
      const savedMessage = await fetchJson(`/api/conversations/${state.activeConversationId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "user", content })
      });
      state.currentMessages.at(-1).id = savedMessage.id;
    }

  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: state.activeConversationId })
  });

    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to contact Ollama");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let streamed = "";
    let buffer = "";
    let streamError = "";
    while (true) {
    const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";
      events.filter(Boolean).forEach((piece) => {
      if (piece.startsWith("data:")) {
        const payload = piece.slice(5).trim();
        if (payload === "[DONE]") {
          return;
        }
        const event = JSON.parse(payload);
        if (event.error) {
          streamError = event.error;
          return;
        }
        streamed += event.delta || "";
        assistantPlaceholder.textContent = streamed;
        scrollToBottom();
      }
      });
      if (streamError) throw new Error(streamError);
    }

    if (!streamed) throw new Error("The model returned an empty response.");
    state.currentMessages.push({ role: "assistant", content: streamed });
    assistantPlaceholder.remove();
    renderMessages();
    await loadConversations();
  } catch (error) {
    assistantPlaceholder.classList.remove("typing-indicator");
    assistantPlaceholder.textContent = `Error: ${error.message}`;
  } finally {
    setStreaming(false);
  }
}

async function handleConversationAction(id, action) {
  if (action === "delete") {
    await fetchJson(`/api/conversations/${id}`, { method: "DELETE" });
    if (state.activeConversationId === id) {
      state.activeConversationId = null;
    }
    await loadConversations();
    if (!state.activeConversationId) await createConversation();
    return;
  }
  if (action === "rename") {
    const newTitle = window.prompt("Enter a new title", "Untitled conversation");
    if (!newTitle) return;
    await fetchJson(`/api/conversations/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: newTitle }) });
    await loadConversations();
  }
}

async function handleMessageAction(message, action) {
  if (action === "copy") {
    navigator.clipboard.writeText(message.content);
  }
  if (action === "edit") {
    const next = window.prompt("Edit message", message.content);
    if (next !== null) {
      const content = next.trim();
      if (!content) return;
      await fetchJson(`/api/messages/${message.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content })
      });
      message.content = content;
      renderMessages();
      await loadConversations();
    }
  }
  if (action === "regenerate") {
    const messageIndex = state.currentMessages.indexOf(message);
    const previousMessages = state.currentMessages.slice(0, messageIndex);
    const lastUserMessage = [...previousMessages].reverse().find((item) => item.role === "user");
    if (!lastUserMessage || !message.id) return;
    await fetchJson(`/api/messages/${message.id}`, { method: "DELETE" });
    state.currentMessages = state.currentMessages.filter((item) => item.id !== message.id);
    renderMessages();
    await sendMessage(lastUserMessage.content, false);
  }
}

async function exportConversation() {
  if (!state.activeConversationId) return;
  const type = window.prompt("Export as json, markdown, or pdf", "json");
  const format = (type || "json").toLowerCase();
  const url = `/api/conversations/${state.activeConversationId}/export?format=${format}`;
  window.open(url, "_blank");
}

async function pullModel() {
  const name = els.pullModelInput.value.trim();
  if (!name) return;
  els.pullModelBtn.disabled = true;
  els.modelInfo.textContent = `Downloading ${name}...`;
  try {
    await fetchJson("/api/models/pull", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
    els.modelInfo.textContent = `${name} is ready.`;
    await loadModels();
  } catch (error) {
    els.modelInfo.textContent = `Could not pull model: ${error.message}`;
  } finally {
    els.pullModelBtn.disabled = false;
  }
}

function bindEvents() {
  els.sendBtn.onclick = sendMessage;
  els.messageInput.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.key === "Enter") {
      event.preventDefault();
      sendMessage();
    }
  });
  els.newChatBtn.onclick = createConversation;
  els.conversationSearch.addEventListener("input", renderConversationList);
  els.settingsToggle.onclick = () => els.settingsPanel.classList.toggle("hidden");
  els.exportBtn.onclick = exportConversation;
  els.pullModelBtn.onclick = pullModel;
  els.themeToggle.onclick = () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
  };
  els.systemPromptInput.addEventListener("input", (event) => {
    state.settings.systemPrompt = event.target.value;
    saveSettings();
  });
  els.temperatureInput.addEventListener("input", (event) => {
    state.settings.temperature = Number(event.target.value);
    els.temperatureValue.textContent = state.settings.temperature;
    saveSettings();
  });
  els.maxTokensInput.addEventListener("input", (event) => {
    state.settings.maxTokens = Number(event.target.value);
    saveSettings();
  });
  els.topPInput.addEventListener("input", (event) => {
    state.settings.topP = Number(event.target.value);
    els.topPValue.textContent = state.settings.topP;
    saveSettings();
  });
  els.topKInput.addEventListener("input", (event) => {
    state.settings.topK = Number(event.target.value);
    saveSettings();
  });
  els.modelSelect.addEventListener("change", (event) => {
    state.settings.model = event.target.value;
    saveSettings();
  });
}

async function boot() {
  bindEvents();
  document.documentElement.setAttribute("data-theme", localStorage.getItem("theme") || "dark");
  await loadModels();
  await loadConversations();
  if (!state.activeConversationId) await createConversation();
}

boot();
