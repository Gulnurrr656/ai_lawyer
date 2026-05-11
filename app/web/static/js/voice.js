// ZangerPro AI — multi-turn voice chat (WhatsApp-style).
//
// Design goals:
//
// * The user can record voice messages **back-to-back** within the same
//   chat — there is no one-shot lock.
// * After every recording the transcribed text is shown inline next to the
//   voice button and the user confirms with one click. Confirmation lets
//   us avoid sending raw, unverified facts to the legal pipeline.
// * Falls back to ``<input type="file" accept="audio/*">`` on browsers
//   without ``MediaRecorder`` (e.g. some iOS Safari versions). Multiple
//   consecutive uploads are allowed.
//
// The chat container surface is expected to expose:
//   - #voice-btn        — toggle record button
//   - #chat-input       — textarea where the transcript lands
//   - (optional) #chat-panel[data-session-id]
//
// The script uses ``/api/voice/upload`` (transcribe-only). When a session
// id is present on ``#chat-panel``, ``/api/chat/{session_id}/voice`` is
// preferred so each voice note is appended to the conversation in the
// same turn.

(function () {
  const btn = document.getElementById('voice-btn');
  const input = document.getElementById('chat-input');
  if (!btn || !input) return;

  const panel = document.getElementById('chat-panel');
  const sessionId = panel && panel.dataset ? panel.dataset.sessionId : null;
  const chatLog = document.getElementById('chat-log');

  let mediaRecorder = null;
  let chunks = [];
  let recording = false;
  let stream = null;

  // --- in-DOM status ribbon ---------------------------------------------
  const status = document.createElement('div');
  status.id = 'voice-status';
  status.style.cssText =
    'display:none;font-size:0.75rem;color:#5B6B8C;margin-top:6px;';
  if (btn.parentNode) btn.parentNode.appendChild(status);

  function setStatus(text) {
    if (!text) {
      status.style.display = 'none';
      status.textContent = '';
      return;
    }
    status.textContent = text;
    status.style.display = 'block';
  }

  // --- availability check ----------------------------------------------
  async function checkAvailability() {
    try {
      const res = await fetch('/voice/status');
      const data = await res.json();
      if (!data.available) {
        btn.title = data.message || 'Voice unavailable';
      }
    } catch (_) { /* ignore */ }
  }
  checkAvailability();

  // --- recording lifecycle ---------------------------------------------
  async function startRecording() {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      fallbackFilePicker();
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        await sendVoice(blob, 'voice.webm');
        if (stream) {
          stream.getTracks().forEach((t) => t.stop());
          stream = null;
        }
      };
      mediaRecorder.start();
      recording = true;
      btn.textContent = '⏺';
      btn.classList.add('animate-pulse');
      setStatus('Жазылып жатыр… / Идёт запись…');
    } catch (_) {
      fallbackFilePicker();
    }
  }

  function stopRecording() {
    if (mediaRecorder && recording) {
      try { mediaRecorder.stop(); } catch (_) { /* ignore */ }
      recording = false;
      btn.textContent = '🎙';
      btn.classList.remove('animate-pulse');
      setStatus('Өңделуде… / Обрабатываем…');
    }
  }

  function fallbackFilePicker() {
    const fp = document.createElement('input');
    fp.type = 'file';
    fp.accept = 'audio/*';
    fp.style.display = 'none';
    fp.onchange = async () => {
      const f = fp.files && fp.files[0];
      if (f) await sendVoice(f, f.name || 'voice.m4a');
      fp.remove();
    };
    document.body.appendChild(fp);
    fp.click();
  }

  // --- send + confirm ---------------------------------------------------
  function appendVoiceBubble(text) {
    if (!chatLog) return;
    const div = document.createElement('div');
    div.className = 'self-end ml-12 bg-zp-blue/10 border border-zp-blue/30 text-zp-deep rounded-md p-3 text-sm';
    div.style.whiteSpace = 'pre-wrap';
    div.textContent = '🎙 ' + text;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function appendAssistantBubble(text) {
    if (!chatLog) return;
    const div = document.createElement('div');
    div.className = 'mr-12 bg-zp-bg border border-zp-line rounded-md p-3 text-sm text-zp-deep';
    div.style.whiteSpace = 'pre-wrap';
    div.textContent = text;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  async function sendVoice(blob, filename) {
    const fd = new FormData();
    fd.append('audio', blob, filename);
    setStatus('Тану / Распознаём…');

    // Prefer the multi-turn endpoint when we have a session id.
    if (sessionId) {
      try {
        const res = await fetch('/api/chat/' + sessionId + '/voice', {
          method: 'POST', body: fd,
        });
        const data = await res.json();
        if (!data.ok) {
          setStatus(data.message || 'Қате / Ошибка');
          return;
        }
        // Show the transcript next to the input for confirmation.
        if (data.transcript) {
          appendVoiceBubble(data.transcript);
          input.value = (input.value ? input.value + '\n' : '') + data.transcript;
          input.dispatchEvent(new Event('input', { bubbles: true }));
        }
        if (data.assistant_text) appendAssistantBubble(data.assistant_text);
        setStatus('Дайын / Готово');
        setTimeout(() => setStatus(''), 1500);
        return;
      } catch (e) {
        setStatus('Қате / Ошибка');
        return;
      }
    }

    // Transcribe-only fallback.
    try {
      const res = await fetch('/api/voice/upload', { method: 'POST', body: fd });
      const data = await res.json();
      if (!data.ok) {
        setStatus(data.message || 'Қате / Ошибка');
        return;
      }
      input.value = (input.value ? input.value + '\n' : '') + data.text;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.focus();
      appendVoiceBubble(data.text);
      setStatus('Растаңыз да жіберіңіз / Подтвердите и отправьте');
    } catch (e) {
      setStatus('Қате / Ошибка');
    }
  }

  btn.addEventListener('click', () => {
    if (recording) stopRecording();
    else startRecording();
  });
})();
