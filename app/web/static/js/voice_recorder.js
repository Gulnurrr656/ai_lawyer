// ZangerPro AI — reusable voice recorder widget.
//
// Drops onto any page that includes ``_voice_recorder.html``. Supports
// repeated record -> transcribe -> confirm -> send cycles without page
// reload (WhatsApp-style). Designed to never leave a stale microphone
// stream or MediaRecorder behind. Sequential recordings are explicitly
// guaranteed via resetRecorderState().
//
// Endpoints used (first one available wins):
//   * POST /api/chat/{session_id}/voice      multi-turn (preferred when
//                                             ``data-session-id`` is set)
//   * POST /api/voice/transcribe             generic transcribe-only
//   * POST /api/voice/upload                 legacy fallback
//
// Response shape expected:
//   { ok: true,  text: "...", language: "kk|ru|en|unknown", model: "..." }
//   { ok: false, error_code: "...", message: "..." }

(function () {
  'use strict';

  // Pick the most browser-friendly recording MIME type that the OpenAI
  // audio transcription endpoint understands.
  function getBestAudioMimeType() {
    var candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/mp4',
      'audio/mpeg'
    ];
    if (!window.MediaRecorder) return '';
    for (var i = 0; i < candidates.length; i++) {
      try {
        if (MediaRecorder.isTypeSupported(candidates[i])) return candidates[i];
      } catch (_) { /* keep scanning */ }
    }
    return '';
  }

  function extensionFor(mime) {
    if (!mime) return 'webm';
    if (mime.indexOf('webm') !== -1) return 'webm';
    if (mime.indexOf('mp4') !== -1) return 'm4a';
    if (mime.indexOf('mpeg') !== -1) return 'mp3';
    if (mime.indexOf('ogg') !== -1) return 'ogg';
    if (mime.indexOf('wav') !== -1) return 'wav';
    return 'webm';
  }

  function init(root) {
    if (!root || root._zpVoiceReady) return;
    root._zpVoiceReady = true;

    var targetInputSel = root.getAttribute('data-target-input') || '#chat-input';
    var targetSendSel = root.getAttribute('data-target-send') || '';
    var sessionId = root.getAttribute('data-session-id') || '';
    var transcribeUrl = root.getAttribute('data-transcribe-url') || '/api/voice/transcribe';
    var autosend = root.getAttribute('data-autosend') === '1';

    var btnRecord = root.querySelector('[data-voice-record]');
    var btnStop = root.querySelector('[data-voice-stop]');
    var btnCancel = root.querySelector('[data-voice-cancel]');
    var btnSend = root.querySelector('[data-voice-send]');
    var fallbackLabel = root.querySelector('[data-voice-fallback]');
    var fallbackInput = root.querySelector('[data-voice-file]');
    var transcriptBox = root.querySelector('[data-voice-transcript]');
    var statusEl = root.querySelector('[data-voice-status]');
    var timerEl = root.querySelector('[data-voice-timer]');

    var labelsRaw = root.querySelector('[data-voice-labels]');
    var L = {};
    try { L = JSON.parse((labelsRaw && labelsRaw.textContent) || '{}'); } catch (_) { L = {}; }

    // ----- internal recorder state ---------------------------------------
    var mediaRecorder = null;
    var stream = null;
    var chunks = [];
    var audioBlob = null;
    var recording = false;
    var startedAt = 0;
    var timerHandle = null;
    var lastTranscript = '';
    var selectedMime = getBestAudioMimeType();

    function setStatus(msg) {
      if (!statusEl) return;
      statusEl.textContent = msg || '';
    }

    function show(el, on) {
      if (!el) return;
      if (on) el.classList.remove('hidden');
      else el.classList.add('hidden');
    }

    function setUiState(state) {
      // states: idle | recording | ready | error
      if (state === 'recording') {
        show(btnRecord, false);
        show(btnStop, true);
        show(btnCancel, true);
        show(btnSend, false);
        show(transcriptBox, false);
      } else if (state === 'ready') {
        show(btnRecord, true);
        show(btnStop, false);
        show(btnCancel, true);
        show(btnSend, true);
        show(transcriptBox, true);
      } else { // idle / error -> idle
        show(btnRecord, true);
        show(btnStop, false);
        show(btnCancel, false);
        show(btnSend, false);
        show(transcriptBox, false);
      }
    }

    // Hard-reset the recorder, microphone stream and chunks after every
    // recording so a second click works without a page reload. This is
    // the canonical fix for the "voice works once, then dies" bug.
    function resetRecorderState() {
      try {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
          mediaRecorder.stop();
        }
      } catch (_) { /* ignore */ }
      if (stream) {
        try {
          stream.getTracks().forEach(function (t) { t.stop(); });
        } catch (_) { /* ignore */ }
      }
      mediaRecorder = null;
      stream = null;
      chunks = [];
      audioBlob = null;
      recording = false;
      if (timerHandle) { clearInterval(timerHandle); timerHandle = null; }
      if (timerEl) timerEl.textContent = '0:00';
      setUiState('idle');
    }
    // Expose for tests / external callers.
    root.zpVoiceReset = resetRecorderState;
    root.zpGetBestMime = getBestAudioMimeType;

    function fmt(secs) {
      var s = Math.max(0, Math.floor(secs));
      var m = Math.floor(s / 60);
      var r = s % 60;
      return m + ':' + (r < 10 ? '0' + r : r);
    }

    function startTimer() {
      startedAt = Date.now();
      if (timerEl) timerEl.textContent = '0:00';
      timerHandle = setInterval(function () {
        if (timerEl) timerEl.textContent = fmt((Date.now() - startedAt) / 1000);
      }, 250);
    }

    // ----- recording -----------------------------------------------------
    function startRecording() {
      // Always start clean — see resetRecorderState above.
      resetRecorderState();

      if (!navigator.mediaDevices || !window.MediaRecorder) {
        showFallback();
        if (fallbackInput) { try { fallbackInput.click(); } catch (_) {} }
        return;
      }

      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
        stream = s;
        chunks = [];
        var opts = selectedMime ? { mimeType: selectedMime } : undefined;
        try {
          mediaRecorder = new MediaRecorder(stream, opts);
        } catch (e) {
          try { mediaRecorder = new MediaRecorder(stream); }
          catch (_) {
            setStatus(L.error || L.unavailable || '');
            resetRecorderState();
            return;
          }
        }
        mediaRecorder.ondataavailable = function (e) {
          if (e.data && e.data.size > 0) chunks.push(e.data);
        };
        mediaRecorder.onstop = function () {
          var mime = (mediaRecorder && mediaRecorder.mimeType) || selectedMime || 'audio/webm';
          audioBlob = chunks.length ? new Blob(chunks, { type: mime }) : null;
          // Release the mic stream immediately after stop, even if the
          // user cancels before send.
          if (stream) {
            try { stream.getTracks().forEach(function (t) { t.stop(); }); } catch (_) {}
            stream = null;
          }
          if (timerHandle) { clearInterval(timerHandle); timerHandle = null; }
          recording = false;
          show(btnStop, false);
          transcribeBlob(audioBlob);
        };
        try { mediaRecorder.start(); } catch (_) {
          setStatus(L.error || L.unavailable || '');
          resetRecorderState();
          return;
        }
        recording = true;
        setUiState('recording');
        setStatus(L.recording || '');
        startTimer();
      }).catch(function () {
        setStatus(L.error || L.unavailable || '');
        showFallback();
      });
    }

    function stopRecording() {
      if (!recording || !mediaRecorder) return;
      try { mediaRecorder.stop(); } catch (_) { /* ignore */ }
      setStatus(L.transcribing || '');
    }

    function cancelRecording() {
      resetRecorderState();
      lastTranscript = '';
      if (transcriptBox) transcriptBox.value = '';
      setStatus('');
    }

    function showFallback() {
      if (fallbackLabel) show(fallbackLabel, true);
    }

    // ----- transcription -------------------------------------------------
    function buildFormData(blob, filename) {
      var fd = new FormData();
      fd.append('audio', blob, filename || ('voice.' + extensionFor(blob && blob.type)));
      return fd;
    }

    function transcribeBlob(blob) {
      if (!blob || blob.size === 0) {
        setStatus(L.error || L.unavailable || '');
        // Important: clear chunks + state so a second attempt works.
        chunks = [];
        audioBlob = null;
        setUiState('idle');
        return;
      }
      setStatus(L.transcribing || '');
      var url = sessionId
        ? ('/api/chat/' + encodeURIComponent(sessionId) + '/voice')
        : transcribeUrl;
      var fd = buildFormData(blob, 'voice.' + extensionFor(blob.type));
      fetch(url, { method: 'POST', body: fd, credentials: 'same-origin' })
        .then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (data) {
          // If session-scoped endpoint failed, retry the generic upload alias
          // so the widget still works on pre-auth/dev pages.
          if ((!data || !data.ok) && sessionId) {
            return fetch('/api/voice/upload', { method: 'POST', body: fd, credentials: 'same-origin' })
              .then(function (r) { return r.json().catch(function () { return {}; }); });
          }
          return data || {};
        })
        .then(function (data) {
          if (!data || !data.ok) {
            var msg = (data && (data.message || data.error_code)) || L.unavailable || L.error || '';
            setStatus(msg);
            // Clear chunks even on failure so the next recording starts fresh.
            chunks = [];
            audioBlob = null;
            setUiState('idle');
            return;
          }
          var text = data.text || data.transcript || '';
          lastTranscript = String(text || '').trim();
          if (transcriptBox) transcriptBox.value = lastTranscript;
          setUiState('ready');
          setStatus(L.ready || '');
          if (autosend) sendTranscript();
        })
        .catch(function () {
          setStatus(L.error || L.unavailable || '');
          chunks = [];
          audioBlob = null;
          setUiState('idle');
        });
    }

    // ----- send to chat --------------------------------------------------
    function sendTranscript() {
      var text = ((transcriptBox && transcriptBox.value) || lastTranscript || '').trim();
      if (!text) return;
      var input = targetInputSel ? document.querySelector(targetInputSel) : null;
      if (input) {
        input.value = (input.value ? input.value + '\n' : '') + text;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.focus();
      }
      var sendBtn = targetSendSel ? document.querySelector(targetSendSel) : null;
      if (sendBtn) {
        try { sendBtn.click(); } catch (_) { /* ignore */ }
      }
      lastTranscript = '';
      if (transcriptBox) transcriptBox.value = '';
      // After insertion, fully reset so chunks are clean for the next recording.
      resetRecorderState();
      setStatus('');
    }

    // ----- fallback file picker (iOS / unsupported MediaRecorder) -------
    function handleFallbackFile() {
      var f = fallbackInput && fallbackInput.files && fallbackInput.files[0];
      if (!f) return;
      audioBlob = f;
      show(transcriptBox, true);
      transcribeBlob(f);
      try { fallbackInput.value = ''; } catch (_) {}
    }

    // ----- wire-up -------------------------------------------------------
    if (btnRecord) btnRecord.addEventListener('click', startRecording);
    if (btnStop) btnStop.addEventListener('click', stopRecording);
    if (btnCancel) btnCancel.addEventListener('click', cancelRecording);
    if (btnSend) btnSend.addEventListener('click', sendTranscript);
    if (fallbackInput) fallbackInput.addEventListener('change', handleFallbackFile);

    // Always show the fallback label when MediaRecorder is missing.
    if (!(navigator.mediaDevices && window.MediaRecorder)) {
      showFallback();
    }

    // Informational availability check — never hides the record button,
    // only updates the tooltip and status hint.
    if (window.fetch) {
      fetch('/voice/status', { credentials: 'same-origin' })
        .then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (d) {
          if (!d) return;
          if (d.voice_enabled === false) {
            if (btnRecord) {
              btnRecord.disabled = true;
              btnRecord.title = (d.message) || L.unavailable || '';
            }
            setStatus((d.message) || L.unavailable || '');
            return;
          }
          if (!d.available && btnRecord) {
            btnRecord.title = d.message || L.unavailable || '';
          }
        })
        .catch(function () { /* leave UI alone */ });
    }

    setUiState('idle');
  }

  function bootAll() {
    var roots = document.querySelectorAll('[data-voice-recorder]');
    for (var i = 0; i < roots.length; i++) init(roots[i]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootAll);
  } else {
    bootAll();
  }
})();
