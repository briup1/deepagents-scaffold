/**
 * DeepAgents Scaffold - Chat Frontend
 * Pure vanilla JS, no build step required.
 */

const API_BASE = window.location.origin + '/api';

// --- State ---
let currentThreadId = null;
let streamingEnabled = true;
let isLoading = false;
let messageHistory = []; // { role, content, tool_calls? }

// --- DOM refs ---
const els = {
  messages: document.getElementById('messages'),
  input: document.getElementById('message-input'),
  sendBtn: document.getElementById('send-btn'),
  agentSelect: document.getElementById('agent-select'),
  modelSelect: document.getElementById('model-select'),
  newThreadBtn: document.getElementById('new-thread-btn'),
  threadList: document.getElementById('thread-list'),
  currentThreadLabel: document.getElementById('current-thread'),
  status: document.getElementById('status-indicator'),
  clearBtn: document.getElementById('clear-chat'),
  streamToggle: document.getElementById('toggle-stream'),
};

// --- Init ---
async function init() {
  await loadAgents();
  await loadModels();
  await checkHealth();
  createNewThread();

  // Event listeners
  els.sendBtn.addEventListener('click', sendMessage);
  els.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  els.input.addEventListener('input', autoResize);
  els.newThreadBtn.addEventListener('click', createNewThread);
  els.clearBtn.addEventListener('click', clearChat);
  els.streamToggle.addEventListener('click', toggleStream);
}

// --- API ---
async function apiGet(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res;
}

async function checkHealth() {
  try {
    const res = await fetch(window.location.origin + '/health');
    if (!res.ok) throw new Error();
    setStatus('已连接', 'connected');
  } catch {
    setStatus('未连接', 'disconnected');
  }
}

async function loadAgents() {
  try {
    const data = await apiGet('/agents/');
    els.agentSelect.innerHTML = '';
    const agents = data.agents || [];
    if (agents.length === 0) {
      const opt = document.createElement('option');
      opt.value = 'default';
      opt.textContent = 'default';
      els.agentSelect.appendChild(opt);
    } else {
      agents.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.name;
        opt.textContent = a.name;
        els.agentSelect.appendChild(opt);
      });
    }
  } catch (e) {
    console.warn('Failed to load agents:', e);
  }
}

async function loadModels() {
  try {
    // Fetch from config via a simple heuristic: models are in config
    // We don't have a direct /models endpoint, so we'll skip dynamic loading
    // and let the user configure if needed.
    const models = []; // Could be populated from a future /config endpoint
    els.modelSelect.innerHTML = '<option value="">默认</option>';
    models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      els.modelSelect.appendChild(opt);
    });
  } catch (e) {
    console.warn('Failed to load models:', e);
  }
}

// --- Thread management ---
function createNewThread() {
  currentThreadId = generateId();
  messageHistory = [];
  els.messages.innerHTML = '';
  updateThreadLabel();
  addThreadToList(currentThreadId);
  addSystemMessage('新会话已开始');
}

function generateId() {
  return 'thread-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 7);
}

function updateThreadLabel() {
  els.currentThreadLabel.textContent = currentThreadId
    ? `会话: ${currentThreadId.slice(0, 20)}...`
    : '新会话';
}

function addThreadToList(threadId) {
  const li = document.createElement('li');
  li.textContent = threadId;
  li.dataset.id = threadId;
  li.addEventListener('click', () => switchThread(threadId));
  els.threadList.prepend(li);
  highlightThread(threadId);
}

function switchThread(threadId) {
  currentThreadId = threadId;
  updateThreadLabel();
  highlightThread(threadId);
  // In a real app, we'd fetch messages from the server here
}

function highlightThread(threadId) {
  Array.from(els.threadList.children).forEach(li => {
    li.classList.toggle('active', li.dataset.id === threadId);
  });
}

// --- Messaging ---
function autoResize() {
  els.input.style.height = 'auto';
  els.input.style.height = Math.min(els.input.scrollHeight, 200) + 'px';
}

async function sendMessage() {
  const text = els.input.value.trim();
  if (!text || isLoading) return;

  // Add user message
  addMessage('user', text);
  messageHistory.push({ role: 'user', content: text });
  els.input.value = '';
  autoResize();

  if (streamingEnabled) {
    await sendStream(text);
  } else {
    await sendWait(text);
  }
}

async function sendStream(text) {
  setLoading(true);
  const assistantMsgId = addMessage('assistant', '');
  const bubble = document.querySelector(`[data-msg-id="${assistantMsgId}"] .bubble`);

  let fullContent = '';
  let reasoning = '';
  let toolCalls = [];

  try {
    const body = {
      assistant_id: els.agentSelect.value || 'default',
      input: { messages: messageHistory },
      config: {
        configurable: { thread_id: currentThreadId },
      },
    };

    const res = await apiPost('/runs/stream', body);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete line

      for (const line of lines) {
        if (!line.trim()) continue;
        // SSE format: "data: {...}" or "event: end\ndata: {...}"
        if (line.startsWith('data:')) {
          const jsonStr = line.slice(5).trim();
          if (jsonStr) {
            try {
              const data = JSON.parse(jsonStr);
              processStreamEvent(data, bubble, () => {
                fullContent = accumulateContent(data, fullContent);
                reasoning = accumulateReasoning(data, reasoning);
                toolCalls = accumulateToolCalls(data, toolCalls);
              });
            } catch {
              // ignore parse errors for partial data
            }
          }
        }
      }
    }

    // Save to history
    messageHistory.push({ role: 'assistant', content: fullContent });
  } catch (err) {
    bubble.innerHTML = `<span style="color:var(--error)">错误: ${escapeHtml(err.message)}</span>`;
  } finally {
    setLoading(false);
  }
}

async function sendWait(text) {
  setLoading(true);
  const loadingId = addLoading();

  try {
    const body = {
      assistant_id: els.agentSelect.value || 'default',
      input: { messages: messageHistory },
      config: {
        configurable: { thread_id: currentThreadId },
      },
    };

    const res = await apiPost('/runs/wait', body);
    const data = await res.json();
    removeLoading(loadingId);

    const output = data.output || {};
    const content = extractContent(output);
    const reasoning = extractReasoning(output);
    const toolCalls = extractToolCalls(output);

    addMessage('assistant', content, { reasoning, toolCalls });
    messageHistory.push({ role: 'assistant', content });
  } catch (err) {
    removeLoading(loadingId);
    addMessage('assistant', `错误: ${err.message}`);
  } finally {
    setLoading(false);
  }
}

// --- Event processing ---
function processStreamEvent(data, bubble, accumulator) {
  accumulator();

  // Rebuild bubble content from accumulated state
  // For streaming, we process the raw event and render incrementally
  const content = extractContent(data);
  const reasoning = extractReasoning(data);
  const toolCalls = extractToolCalls(data);

  let html = '';
  if (reasoning) {
    html += renderReasoning(reasoning);
  }
  if (content) {
    html += escapeHtml(content);
  }
  if (toolCalls.length > 0) {
    html += toolCalls.map(tc => renderToolCall(tc)).join('');
  }

  if (html) {
    bubble.innerHTML = html;
    scrollToBottom();
  }
}

function accumulateContent(data, current) {
  const c = extractContent(data);
  return c || current;
}

function accumulateReasoning(data, current) {
  const r = extractReasoning(data);
  return r || current;
}

function accumulateToolCalls(data, current) {
  const tcs = extractToolCalls(data);
  if (tcs.length > 0) {
    return [...current, ...tcs];
  }
  return current;
}

function extractLastAssistantMessage(data) {
  if (data && data.messages && Array.isArray(data.messages)) {
    for (let i = data.messages.length - 1; i >= 0; i--) {
      const m = data.messages[i];
      const t = m.type || m.role;
      if (t === 'ai' || t === 'assistant') {
        return m;
      }
    }
  }
  return null;
}

function extractContent(data) {
  if (typeof data === 'string') return data;
  if (data && typeof data.content === 'string') return data.content;
  if (data && typeof data.text === 'string') return data.text;
  const last = extractLastAssistantMessage(data);
  if (last && typeof last.content === 'string') return last.content;
  if (data && data.output && typeof data.output.content === 'string') {
    return data.output.content;
  }
  return '';
}

function extractReasoning(data) {
  if (data && data.reasoning_content) return data.reasoning_content;
  if (data && data.additional_kwargs && data.additional_kwargs.reasoning_content) {
    return data.additional_kwargs.reasoning_content;
  }
  const last = extractLastAssistantMessage(data);
  if (last && last.additional_kwargs && last.additional_kwargs.reasoning_content) {
    return last.additional_kwargs.reasoning_content;
  }
  return '';
}

function extractToolCalls(data) {
  if (data && data.tool_calls && Array.isArray(data.tool_calls)) {
    return data.tool_calls;
  }
  if (data && data.additional_kwargs && data.additional_kwargs.tool_calls) {
    return data.additional_kwargs.tool_calls;
  }
  const last = extractLastAssistantMessage(data);
  if (last && last.tool_calls) return last.tool_calls;
  return [];
}

// --- Rendering ---
function addMessage(role, content, opts = {}) {
  const id = 'msg-' + generateId();
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.dataset.msgId = id;

  const avatarText = role === 'user' ? '我' : role === 'assistant' ? 'AI' : '•';
  const avatar = `<div class="avatar">${avatarText}</div>`;

  let body = '';
  if (opts.reasoning) body += renderReasoning(opts.reasoning);
  if (content) body += escapeHtml(content);
  if (opts.toolCalls && opts.toolCalls.length) {
    body += opts.toolCalls.map(tc => renderToolCall(tc)).join('');
  }

  div.innerHTML = `${avatar}<div class="bubble">${body || ''}</div>`;
  els.messages.appendChild(div);
  scrollToBottom();
  return id;
}

function addSystemMessage(text) {
  return addMessage('system', text);
}

function addLoading() {
  const id = 'loading-' + generateId();
  const div = document.createElement('div');
  div.className = 'message assistant';
  div.dataset.loadingId = id;
  div.innerHTML = `
    <div class="avatar">AI</div>
    <div class="bubble loading">
      <div class="loading-dot"></div>
      <div class="loading-dot"></div>
      <div class="loading-dot"></div>
    </div>
  `;
  els.messages.appendChild(div);
  scrollToBottom();
  return id;
}

function removeLoading(id) {
  const el = document.querySelector(`[data-loading-id="${id}"]`);
  if (el) el.remove();
}

function renderReasoning(text) {
  return `
    <div class="reasoning">
      <div class="reasoning-label">思考过程</div>
      <div class="reasoning-content">${escapeHtml(text)}</div>
    </div>
  `;
}

function renderToolCall(tc) {
  const name = tc.name || tc.function?.name || 'unknown';
  const args = tc.args || tc.function?.arguments || tc.arguments || '{}';
  const argsStr = typeof args === 'string' ? args : JSON.stringify(args, null, 2);
  return `
    <div class="tool-call">
      <div class="tool-call-header">
        <span>工具调用</span>
        <span class="tool-call-name">${escapeHtml(name)}</span>
      </div>
      <div class="tool-call-args">${escapeHtml(argsStr)}</div>
    </div>
  `;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

function setStatus(text, cls) {
  els.status.textContent = text;
  els.status.className = `status ${cls}`;
}

function setLoading(loading) {
  isLoading = loading;
  els.sendBtn.disabled = loading;
  els.sendBtn.textContent = loading ? '发送中...' : '发送';
}

function clearChat() {
  els.messages.innerHTML = '';
  messageHistory = [];
  addSystemMessage('聊天已清空');
}

function toggleStream() {
  streamingEnabled = !streamingEnabled;
  els.streamToggle.classList.toggle('active', streamingEnabled);
  els.streamToggle.textContent = streamingEnabled ? '流式' : '非流式';
}

// --- Start ---
init();
