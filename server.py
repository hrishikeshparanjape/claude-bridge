import asyncio
import json
import os
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import Optional

app = FastAPI()

USER_PASSWORD = os.environ.get("USER_PASSWORD", "change-me-password")

bridge_ws: Optional[WebSocket] = None
browser_clients: dict[str, WebSocket] = {}

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Claude Chat</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #f5f5f5;
    --surface: #fff;
    --border: #e0e0e0;
    --user-bubble: #0a84ff;
    --claude-bubble: #e9e9eb;
    --text: #1c1c1e;
    --text-light: #6e6e73;
    --header-bg: #fff;
    --input-bg: #f5f5f5;
    --send-bg: #0a84ff;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #000;
      --surface: #1c1c1e;
      --border: #2c2c2e;
      --claude-bubble: #2c2c2e;
      --text: #fff;
      --text-light: #8e8e93;
      --header-bg: #1c1c1e;
      --input-bg: #2c2c2e;
    }
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', sans-serif;
    background: var(--bg);
    height: 100dvh;
    display: flex;
    flex-direction: column;
    color: var(--text);
  }

  /* Login */
  #login {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 24px;
    gap: 16px;
  }
  #login h1 { font-size: 28px; font-weight: 700; }
  #login p { color: var(--text-light); font-size: 15px; text-align: center; }
  #login input {
    width: 100%;
    max-width: 320px;
    padding: 14px 16px;
    border: 1.5px solid var(--border);
    border-radius: 12px;
    font-size: 16px;
    background: var(--surface);
    color: var(--text);
    outline: none;
  }
  #login input:focus { border-color: #0a84ff; }
  #login button {
    width: 100%;
    max-width: 320px;
    padding: 14px;
    background: #0a84ff;
    color: white;
    border: none;
    border-radius: 12px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
  }
  #login button:active { opacity: 0.85; }
  #login-error { color: #ff3b30; font-size: 14px; display: none; }

  /* Chat */
  #chat { flex: 1; display: none; flex-direction: column; }
  header {
    padding: 14px 20px;
    padding-top: calc(14px + env(safe-area-inset-top));
    background: var(--header-bg);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #34c759;
    flex-shrink: 0;
  }
  .status-dot.offline { background: #ff3b30; }
  header h1 { font-size: 17px; font-weight: 600; }

  #messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    overscroll-behavior: contain;
  }

  .bubble-row {
    display: flex;
    max-width: 100%;
  }
  .bubble-row.user { justify-content: flex-end; }
  .bubble-row.claude { justify-content: flex-start; }

  .bubble {
    max-width: 80%;
    padding: 10px 14px;
    border-radius: 18px;
    font-size: 16px;
    line-height: 1.45;
    word-break: break-word;
    white-space: pre-wrap;
  }
  .bubble-row.user .bubble {
    background: var(--user-bubble);
    color: white;
    border-bottom-right-radius: 4px;
  }
  .bubble-row.claude .bubble {
    background: var(--claude-bubble);
    color: var(--text);
    border-bottom-left-radius: 4px;
  }

  .typing {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 12px 14px;
    background: var(--claude-bubble);
    border-radius: 18px;
    border-bottom-left-radius: 4px;
    width: fit-content;
  }
  .typing span {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--text-light);
    animation: bounce 1.2s infinite;
  }
  .typing span:nth-child(2) { animation-delay: 0.2s; }
  .typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes bounce {
    0%, 60%, 100% { transform: translateY(0); }
    30% { transform: translateY(-5px); }
  }

  .error-bubble {
    align-self: center;
    padding: 8px 14px;
    background: #ff3b301a;
    color: #ff3b30;
    border-radius: 10px;
    font-size: 14px;
  }

  #input-area {
    padding: 10px 12px;
    padding-bottom: calc(10px + env(safe-area-inset-bottom));
    background: var(--header-bg);
    border-top: 1px solid var(--border);
    display: flex;
    align-items: flex-end;
    gap: 8px;
  }
  #input {
    flex: 1;
    padding: 10px 14px;
    background: var(--input-bg);
    border: none;
    border-radius: 20px;
    font-size: 16px;
    color: var(--text);
    resize: none;
    outline: none;
    max-height: 120px;
    min-height: 40px;
    line-height: 1.4;
    font-family: inherit;
    overflow-y: auto;
  }
  #send {
    width: 36px; height: 36px;
    border-radius: 50%;
    background: var(--send-bg);
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: opacity 0.1s;
  }
  #send:disabled { background: var(--border); cursor: default; }
  #send svg { fill: white; }
</style>
</head>
<body>

<div id="login">
  <h1>Claude Chat</h1>
  <p>Enter your password to continue</p>
  <input type="password" id="password-input" placeholder="Password" autocomplete="current-password">
  <div id="login-error">Incorrect password</div>
  <button onclick="login()">Continue</button>
</div>

<div id="chat">
  <header>
    <div class="status-dot offline" id="status-dot"></div>
    <h1>Claude</h1>
  </header>
  <div id="messages"></div>
  <div id="input-area">
    <textarea id="input" placeholder="Message" rows="1"></textarea>
    <button id="send" onclick="sendMessage()" disabled>
      <svg width="16" height="16" viewBox="0 0 16 16"><path d="M8 1l7 7-7 7V9.5H1v-3h7V1z"/></svg>
    </button>
  </div>
</div>

<script>
  let ws = null;
  let clientId = null;
  let waiting = false;
  let typingEl = null;

  const passwordInput = document.getElementById('password-input');
  passwordInput.addEventListener('keydown', e => { if (e.key === 'Enter') login(); });

  function login() {
    const pw = passwordInput.value.trim();
    if (!pw) return;
    connect(pw);
  }

  function connect(password) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/chat`);

    ws.onopen = () => {
      clientId = crypto.randomUUID();
      ws.send(JSON.stringify({ password, client_id: clientId }));
    };

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.error) {
        document.getElementById('login-error').style.display = 'block';
        ws.close();
        return;
      }
      if (msg.type === 'connected') {
        showChat();
        return;
      }
      if (msg.type === 'error') {
        removeTyping();
        addError(msg.text);
        setWaiting(false);
        return;
      }
      if (msg.type === 'message' && msg.role === 'assistant') {
        removeTyping();
        addBubble('claude', msg.text);
        setWaiting(false);
      }
    };

    ws.onclose = () => {
      document.getElementById('status-dot').classList.add('offline');
      document.getElementById('send').disabled = true;
    };

    ws.onerror = () => ws.close();
  }

  function showChat() {
    document.getElementById('login').style.display = 'none';
    const chat = document.getElementById('chat');
    chat.style.display = 'flex';
    document.getElementById('status-dot').classList.remove('offline');
    document.getElementById('send').disabled = false;
    document.getElementById('input').focus();
  }

  const input = document.getElementById('input');
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  function sendMessage() {
    if (waiting) return;
    const text = input.value.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    addBubble('user', text);
    ws.send(JSON.stringify({ text, type: 'message' }));
    input.value = '';
    input.style.height = 'auto';
    setWaiting(true);
    addTyping();
    scrollToBottom();
  }

  function setWaiting(val) {
    waiting = val;
    document.getElementById('send').disabled = val;
  }

  function addBubble(role, text) {
    const row = document.createElement('div');
    row.className = `bubble-row ${role}`;
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;
    row.appendChild(bubble);
    document.getElementById('messages').appendChild(row);
    scrollToBottom();
  }

  function addError(text) {
    const el = document.createElement('div');
    el.className = 'error-bubble';
    el.textContent = text;
    document.getElementById('messages').appendChild(el);
    scrollToBottom();
  }

  function addTyping() {
    const row = document.createElement('div');
    row.className = 'bubble-row claude';
    row.id = 'typing-row';
    row.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
    document.getElementById('messages').appendChild(row);
    scrollToBottom();
  }

  function removeTyping() {
    const el = document.getElementById('typing-row');
    if (el) el.remove();
  }

  function scrollToBottom() {
    const msgs = document.getElementById('messages');
    msgs.scrollTop = msgs.scrollHeight;
  }
</script>
</body>
</html>"""


@app.get("/")
async def get_ui():
    return HTMLResponse(HTML)


@app.websocket("/bridge")
async def bridge_endpoint(websocket: WebSocket):
    global bridge_ws
    await websocket.accept()

    bridge_ws = websocket
    print("Bridge connected.")
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            client_ws = browser_clients.get(msg.get("client_id"))
            if client_ws:
                try:
                    await client_ws.send_text(data)
                except Exception:
                    pass
    except WebSocketDisconnect:
        bridge_ws = None
        print("Bridge disconnected.")


@app.websocket("/chat")
async def chat_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        auth_data = await websocket.receive_text()
        auth = json.loads(auth_data)
    except Exception:
        await websocket.close(code=4002)
        return

    if auth.get("password") != USER_PASSWORD:
        await websocket.send_text(json.dumps({"error": "Invalid password"}))
        await websocket.close(code=4001)
        return

    client_id = auth.get("client_id") or str(uuid.uuid4())
    browser_clients[client_id] = websocket
    await websocket.send_text(json.dumps({"type": "connected", "client_id": client_id}))

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg["client_id"] = client_id

            if bridge_ws:
                try:
                    await bridge_ws.send_text(json.dumps(msg))
                except Exception:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "text": "Bridge disconnected. Restart bridge.py on your local machine."
                    }))
            else:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "text": "Bridge not connected. Run bridge.py on your local machine."
                }))
    except WebSocketDisconnect:
        browser_clients.pop(client_id, None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
