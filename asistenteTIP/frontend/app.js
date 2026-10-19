(function () {
  'use strict';

  const API = '';
  const $ = (id) => document.getElementById(id);
  const hologram = $('hologram');
  let recognition = null;
  let isListening = false;
  let currentAudio = null;
  let currentController = null;
  let finalTranscript = '';
  let micDenied = false;
  let turnBusy = false;      // hay una consulta en curso (procesando o hablando)
  let afterTurn = null;      // la atención por presencia lo usa para volver a escuchar

  let sessionId = sessionStorage.getItem('session_id');
  if (!sessionId) {
    sessionId = window.crypto?.randomUUID?.() || `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    sessionStorage.setItem('session_id', sessionId);
  }

  function setStatus(text, pulse = false) {
    const status = $('status-bar');
    status.textContent = text;
    status.classList.toggle('pulse', pulse);
  }

  function setHologram(state) {
    hologram.classList.remove('inactive', 'listening', 'thinking', 'speaking');
    hologram.classList.add(state);
  }

  function addMessage(text, type) {
    const article = document.createElement('article');
    article.className = `message ${type}`;
    if (type === 'assistant') {
      const avatar = document.createElement('div');
      avatar.className = 'assistant-avatar';
      const image = document.createElement('img');
      image.src = '/static/img/logo-utec.jpg';
      image.alt = '';
      avatar.append(image);
      article.append(avatar);
    }
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    // Text-only rendering prevents document/model output from becoming HTML.
    bubble.textContent = text;
    article.append(bubble);
    $('chat-messages').append(article);
    $('chat-messages').scrollTop = $('chat-messages').scrollHeight;
  }

  function cleanForSpeech(text) {
    return text.replace(/```[\s\S]*?```/g, 'código').replace(/[*_#>`]/g, ' ')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/\s+/g, ' ').trim();
  }

  let speakController = null;

  function finishSpeaking() {
    currentAudio = null; speakController = null; turnBusy = false;
    setHologram('inactive'); setStatus('Sistema listo · Escribe o pulsa el micrófono');
    $('stop-btn').hidden = true;
    if (afterTurn) afterTurn();
  }

  function cancelSpeech() {
    if (speakController) { speakController.abort(); speakController = null; }
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }

  // Voz de respaldo del navegador, usada si el servicio de voz del servidor no responde.
  function speakWithBrowser(text) {
    if (!window.speechSynthesis) { finishSpeaking(); return; }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'es-UY';
    const voice = window.speechSynthesis.getVoices().find((v) => v.lang.toLowerCase().startsWith('es'));
    if (voice) utterance.voice = voice;
    utterance.onstart = () => setHologram('speaking');
    utterance.onend = finishSpeaking;
    utterance.onerror = finishSpeaking;
    window.speechSynthesis.speak(utterance);
  }

  async function speak(text) {
    const clean = cleanForSpeech(text);
    if (!clean) { finishSpeaking(); return; }
    cancelSpeech();
    speakController = new AbortController();
    const signal = speakController.signal;
    try {
      const response = await fetch(`${API}/speak`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: clean }), signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      if (!blob.size) throw new Error('audio vacío');
      const url = URL.createObjectURL(blob);
      currentAudio = new Audio(url);
      currentAudio.onplay = () => setHologram('speaking');
      currentAudio.onended = () => { URL.revokeObjectURL(url); finishSpeaking(); };
      currentAudio.onerror = () => {
        URL.revokeObjectURL(url); currentAudio = null;
        if (!signal.aborted) speakWithBrowser(clean); else finishSpeaking();
      };
      await currentAudio.play();
    } catch (error) {
      if (signal.aborted) return;
      console.warn('Voz del servidor no disponible; uso la voz del navegador:', error);
      speakWithBrowser(clean);
    }
  }

  async function sendQuestion(question) {
    const cleanQuestion = question.trim();
    if (!cleanQuestion) return;
    if (currentController) currentController.abort();
    cancelSpeech();
    turnBusy = true;

    setHologram('thinking'); setStatus('Procesando la consulta…', true);
    $('stop-btn').hidden = false;
    currentController = new AbortController();
    let fullText = '';
    let doneReceived = false;
    try {
      const response = await fetch(`${API}/ask`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: cleanQuestion, session_id: sessionId }),
        signal: currentController.signal,
      });
      if (!response.ok) throw new Error(`El servidor respondió HTTP ${response.status}`);
      if (!response.body) throw new Error('El servidor no inició la respuesta en streaming.');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';
        for (const event of events) {
          const line = event.split('\n').find((item) => item.startsWith('data:'));
          if (!line) continue;
          const payload = JSON.parse(line.slice(5).trim());
          if (payload.type === 'chunk') fullText += payload.text || '';
          if (payload.type === 'error') throw new Error(payload.text || 'Error del asistente.');
          if (payload.type === 'done') doneReceived = true;
        }
      }
      if (!fullText.trim()) throw new Error(doneReceived ? 'El asistente devolvió una respuesta vacía.' : 'La conexión terminó antes de recibir respuesta.');
      addMessage(fullText, 'assistant');
      setStatus('Respuesta lista · reproduciendo voz');
      await speak(fullText);
    } catch (error) {
      if (error.name !== 'AbortError') {
        console.error(error);
        addMessage(`No pude completar la consulta: ${error.message}`, 'assistant');
        setStatus('No se pudo completar la consulta');
        setHologram('inactive'); $('stop-btn').hidden = true;
        turnBusy = false; if (afterTurn) afterTurn();
      }
    } finally {
      currentController = null;
    }
  }

  function stopResponse() {
    if (currentController) { currentController.abort(); currentController = null; }
    cancelSpeech();
    if (isListening && recognition) recognition.stop();
    setHologram('inactive'); setStatus('Respuesta detenida'); $('stop-btn').hidden = true;
    turnBusy = false; if (afterTurn) afterTurn();
  }

  $('composer').addEventListener('submit', (event) => {
    event.preventDefault();
    const input = $('text-input');
    const question = input.value.trim();
    if (!question) return;
    addMessage(question, 'user'); input.value = ''; $('transcript').textContent = '';
    sendQuestion(question);
  });
  $('stop-btn').addEventListener('click', stopResponse);
  document.querySelectorAll('[data-question]').forEach((button) => {
    button.addEventListener('click', () => {
      const question = button.dataset.question;
      addMessage(question, 'user'); sendQuestion(question);
    });
  });

  function setMicButton(listening) {
    isListening = listening;
    $('mic-btn').classList.toggle('active', listening);
    $('mic-btn').setAttribute('aria-pressed', String(listening));
    $('mic-label').textContent = listening ? 'Escuchando…' : 'Hablar';
    $('mic-icon').textContent = listening ? '⏹' : '🎤';
  }

  function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      $('mic-btn').disabled = true;
      $('voice-hint').textContent = 'Este navegador no ofrece reconocimiento de voz. Puedes escribir tu consulta.';
      $('mic-btn').title = 'Reconocimiento de voz no disponible';
      return;
    }
    recognition = new SpeechRecognition();
    recognition.lang = 'es-UY';
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.onstart = () => {
      finalTranscript = ''; setMicButton(true); setStatus('Escuchando… habla ahora', true); setHologram('listening');
    };
    recognition.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalTranscript += `${transcript} `;
        else interim += transcript;
      }
      $('transcript').textContent = `${finalTranscript}${interim}`.trim();
      if (finalTranscript.trim()) {
        const question = finalTranscript.trim(); finalTranscript = '';
        addMessage(question, 'user'); $('transcript').textContent = '';
        recognition.stop(); sendQuestion(question);
      }
    };
    recognition.onerror = (event) => {
      setMicButton(false); setHologram('inactive');
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        micDenied = true;
        setStatus('Permite el uso del micrófono en el navegador para hablar.');
      } else if (event.error !== 'no-speech' && event.error !== 'aborted') {
        setStatus('No se pudo usar el micrófono; puedes escribir la consulta.');
      }
    };
    recognition.onend = () => {
      setMicButton(false);
      if (!turnBusy) setHologram('inactive');
      if ($('status-bar').textContent.startsWith('Escuchando')) setStatus('Sistema listo · Escribe o pulsa el micrófono');
      if (afterTurn && !turnBusy) afterTurn();   // presencia: sigue escuchando mientras haya alguien
    };
  }

  $('mic-btn').addEventListener('click', () => {
    if (!recognition) return;
    if (isListening) recognition.stop();
    else {
      $('transcript').textContent = '';
      try { recognition.start(); }
      catch (error) { console.warn('No se pudo activar el micrófono:', error); }
    }
  });
  initSpeechRecognition();

  // ── Atención por presencia ─────────────────────────────────────────────────────────────
  // La cámara solo detecta si hay una persona delante (MediaPipe, en el navegador). Cuando
  // alguien se acerca, saluda y abre el micrófono; al alejarse, reinicia la conversación.
  // Está activo en la página principal; con ?presencia=0 se usa solo el chat.
  const params = new URLSearchParams(window.location.search);
  if (params.get('presencia') !== '0') initKiosk();
  else $('kiosk-overlay').hidden = true;

  function initKiosk() {
    const PRESENT_AFTER_MS = Number(params.get('presente')) || 1200;  // cara estable antes de saludar
    const ABSENT_AFTER_MS = Number(params.get('ausente')) || 10000;   // sin cara antes de cerrar la sesión
    const MIN_FACE = Number(params.get('cara')) || 0.12;               // ancho mínimo de la cara (fracción del cuadro)
    const MIN_SCORE = 0.6;
    const CHECK_MS = 250;
    const GREETING = 'Hola, soy el asistente virtual de la carrera. Puedes preguntarme por materias, horarios, parciales o docentes. Te escucho.';

    const overlay = $('kiosk-overlay');
    const message = $('kiosk-message');
    const startButton = $('kiosk-start');
    const textOnlyButton = $('kiosk-text-only');
    const video = $('kiosk-video');
    let detector = null;
    let timer = null;
    let active = false;        // hay una persona atendida
    let firstSeen = 0;
    let lastSeen = 0;
    let listenTimer = null;

    overlay.hidden = false;

    // Sin cámara (o si la persona prefiere escribir) queda el chat normal, sin bloquear la pantalla.
    function textOnly(note) {
      if (timer) { clearInterval(timer); timer = null; }
      video.srcObject?.getTracks().forEach((track) => track.stop());
      active = false; afterTurn = null;
      overlay.hidden = true; $('kiosk-badge').hidden = true;
      setStatus(note || 'Sistema listo · Escribe o pulsa el micrófono');
    }

    function showOverlay(text, waiting) {
      message.textContent = text;
      overlay.classList.toggle('waiting', Boolean(waiting));
      overlay.hidden = false;
    }

    function startListening() {
      listenTimer = null;
      if (!active || turnBusy || isListening || micDenied || !recognition) return;
      $('transcript').textContent = '';
      try { recognition.start(); } catch (error) { /* ya estaba escuchando */ }
    }

    // Después de cada respuesta (o de un silencio) vuelve a abrir el micrófono.
    afterTurn = () => {
      if (!active || listenTimer) return;
      listenTimer = setTimeout(startListening, 600);
    };

    function newVisitor() {
      sessionId = window.crypto?.randomUUID?.() || `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      sessionStorage.setItem('session_id', sessionId);
      $('chat-messages').replaceChildren();
    }

    function beginSession() {
      active = true;
      newVisitor();
      overlay.hidden = true;
      addMessage(GREETING, 'assistant');
      turnBusy = true;               // el micrófono espera a que termine el saludo
      setStatus('Respuesta lista · reproduciendo voz');
      speak(GREETING);
    }

    function endSession() {
      active = false;
      if (listenTimer) { clearTimeout(listenTimer); listenTimer = null; }
      if (currentController) { currentController.abort(); currentController = null; }
      cancelSpeech();
      if (isListening && recognition) recognition.stop();
      turnBusy = false;
      newVisitor();
      setHologram('inactive'); setStatus('Sistema listo · Acércate para consultar');
      $('stop-btn').hidden = true;
      showOverlay('Acércate para consultar. Te escucharé cuando estés frente a la pantalla.', true);
    }

    function check() {
      if (!detector || video.readyState < 2 || !video.videoWidth) return;
      const now = performance.now();
      let seen = false;
      try {
        const { detections } = detector.detectForVideo(video, now);
        seen = detections.some((d) => d.boundingBox
          && d.boundingBox.width / video.videoWidth >= MIN_FACE
          && (d.categories?.[0]?.score ?? 1) >= MIN_SCORE);
      } catch (error) {
        console.warn('Error en la detección de presencia:', error);
        return;
      }
      if (seen) {
        if (!firstSeen) firstSeen = now;
        lastSeen = now;
        if (!active && now - firstSeen >= PRESENT_AFTER_MS) beginSession();
      } else {
        if (now - lastSeen > 600) firstSeen = 0;   // tolera pérdidas muy breves de la cara
        if (active && now - lastSeen >= ABSENT_AFTER_MS) endSession();
      }
    }

    async function start() {
      startButton.hidden = true; textOnlyButton.hidden = true;
      showOverlay('Iniciando la cámara…', false);
      try {
        video.srcObject = await navigator.mediaDevices.getUserMedia({
          video: { width: 640, height: 480, facingMode: 'user' }, audio: false,
        });
        await video.play();
        const vision = await import('/static/vendor/mediapipe/vision_bundle.mjs');
        const files = await vision.FilesetResolver.forVisionTasks('/static/vendor/mediapipe/wasm');
        const options = (delegate) => ({
          baseOptions: { modelAssetPath: '/static/vendor/mediapipe/blaze_face_short_range.tflite', delegate },
          runningMode: 'VIDEO',
          minDetectionConfidence: MIN_SCORE,
        });
        try { detector = await vision.FaceDetector.createFromOptions(files, options('GPU')); }
        catch (error) { detector = await vision.FaceDetector.createFromOptions(files, options('CPU')); }
      } catch (error) {
        console.error('No se pudo iniciar la atención por presencia:', error);
        textOnly('Cámara no disponible · Escribe o pulsa el micrófono');
        return;
      }
      $('kiosk-badge').hidden = false;
      setStatus('Sistema listo · Acércate para consultar');
      showOverlay('Acércate para consultar. Te escucharé cuando estés frente a la pantalla.', true);
      timer = setInterval(check, CHECK_MS);
    }

    startButton.addEventListener('click', start);
    textOnlyButton.addEventListener('click', () => textOnly());
    window.addEventListener('beforeunload', () => {
      if (timer) clearInterval(timer);
      video.srcObject?.getTracks().forEach((track) => track.stop());
    });
  }
})();
