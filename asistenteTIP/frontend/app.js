(function () {
  'use strict';

  const API = '';

  let recognition = null;
  let isListening = false;

  // Generar ID de sesión
  let sessionId = sessionStorage.getItem("session_id");
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    sessionStorage.setItem("session_id", sessionId);
  }

  // Elementos del DOM 
  const $status = () => document.getElementById('status-bar');
  const $transcript = () => document.getElementById('transcript');
  const $response = () => document.getElementById('response-box');
  const $source = () => document.getElementById('source-tag');
  const $mic = () => document.getElementById('mic-btn');
  const $textInput = () => document.getElementById('text-input');
  const hologram = document.getElementById('hologram');

  // Helpers 
  function setStatus(txt, pulse = false) {
    const el = $status();
    if (el) {
      el.textContent = txt;
      el.classList.toggle('pulse', pulse);
    }
  }

  function sourceLabel(src) {
    return src === 'document' ? '[ fuente: documento ]'
      : src === 'web' ? '[ fuente: búsqueda web ]'
        : src === 'training' ? '[ fuente: conocimiento del modelo ]'
          : '';
  }

  function showStopButton() {
    const btn = document.getElementById('stop-btn');
    if (btn) btn.style.display = 'flex';
  }

  function hideStopButton() {
      const btn = document.getElementById('stop-btn');
      if (btn) btn.style.display = 'none';
  }

  window.stopResponse = function () {
    if (currentController) {
      currentController.abort();
      currentController = null;
    }
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    onSpeakingEnd();
    setStatus('Respuesta detenida');
    hideStopButton();
  };

  // Holograma 
  function setHologramState(state) {
    if (!hologram) return;
    hologram.classList.remove('listening', 'thinking', 'speaking', 'inactive');
    hologram.classList.add(state);
  }

  function onSpeakingStart() {
    setHologramState('speaking');
  }

  function onSpeakingEnd() {
    setHologramState('inactive');
  }

  function onListeningStart() {
    setHologramState('listening');
  }

  function onListeningEnd() {
    setHologramState('inactive');
  }

  // Limpieza de texto para voz 
  function cleanForSpeech(text) {
    return text
      .replace(/```[\s\S]*?```/g, 'código')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/\*([^*]+)\*/g, '$1')
      .replace(/__([^_]+)__/g, '$1')
      .replace(/_([^_]+)_/g, '$1')
      .replace(/#{1,6}\s+/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/^\s*[-*+•]\s+/gm, '')
      .replace(/^\s*\d+\.\s+/gm, '')
      .replace(/^>\s*/gm, '')
      .replace(/---+/g, ', ')
      .replace(/\n{2,}/g, '. ')
      .replace(/\n/g, ' ')
      .replace(/\s{2,}/g, ' ')
      .trim();
  }

  // Síntesis de voz 
  let currentAudio = null;
  let currentController = null;

  async function speak(text) {
    const clean = cleanForSpeech(text);
    if (!clean) return;

    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }

    try {
      const res = await fetch(`${API}/speak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: clean }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      currentAudio = new Audio(url);

      currentAudio.onplay = () => onSpeakingStart();
      currentAudio.onended = () => {
        onSpeakingEnd();
        URL.revokeObjectURL(url);
        currentAudio = null;
        setStatus('Sistema listo · Habla o escribe');
      };
      currentAudio.onerror = () => {
        onSpeakingEnd();
        URL.revokeObjectURL(url);
        currentAudio = null;
         hideStopButton(); // NUEVO
      };

      await currentAudio.play();
    } catch (err) {
      console.error('TTS error:', err);
      onSpeakingEnd();
    }
  }

  // Pregunta al asistente (streaming) 
  async function sendQuestion(question) {
    if (!question.trim()) return;

    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }

    onSpeakingEnd();
    onListeningEnd();
    setHologramState('thinking');

    setStatus('Procesando…', true);
    showStopButton(); // NUEVO

    let fullText = '';
    let source = '';

    currentController = new AbortController(); // NUEVO

    try {
      const res = await fetch(`${API}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, session_id: sessionId }),
        signal: currentController.signal, // NUEVO
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data:')) continue;
          const data = JSON.parse(line.slice(5).trim());

          if (data.type === 'chunk') {
            fullText += data.text;
            source = data.source;
          } else if (data.type === 'done') {
            agregarMensaje(fullText, 'assistant');
            setStatus('Respondiendo…');
            speak(fullText);
          } else if (data.type === 'error') {
            throw new Error(data.text);
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {  // NUEVO: no mostrar esto como error real
        setStatus('Sistema listo · Habla o escribe');
        onSpeakingEnd();
        hideStopButton();
        return;
      }
      console.error(err);
      agregarMensaje(`Error: ${err.message}. ¿Está el servidor corriendo en localhost:9000?`, 'assistant');
      setStatus('Error de conexión');
      onSpeakingEnd();
      hideStopButton(); // NUEVO
    }
}

  // Entrada por teclado 
  window.sendText = function () {
    const el = $textInput();
    if (!el) return;
    const txt = el.value.trim();
    if (!txt) return;

    agregarMensaje(txt, 'user');

    $transcript().textContent = txt;
    el.value = '';
    sendQuestion(txt);
  };

  const textInput = $textInput();
  if (textInput) {
    textInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') window.sendText();
    });
  }

  function agregarMensaje(texto, tipo) {
    let container = document.getElementById('chat-messages');

    // Si no existe, lo creamos y lo agregamos al DOM
    if (!container) {
      console.warn('No se encontró #chat-messages, creando contenedor...');
      container = document.createElement('div');
      container.id = 'chat-messages';
      // Lo insertamos en algún lugar, por ejemplo dentro de #ui-panel o antes de #controls
      const panel = document.getElementById('ui-panel');
      if (panel) {
        panel.insertBefore(container, document.getElementById('controls'));
      } else {
        // Si no hay #ui-panel, lo agregamos al body
        document.body.appendChild(container);
      }
    }

    const div = document.createElement('div');
    div.className = `message ${tipo}`;
    div.innerHTML = `<div class="bubble">${texto}</div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }


  // DETECCIÓN DE PRESENCIA CON MEDIAPIPE.JS

  let presenceTimer = null;
  let personPresent = false;
  let camera = null;

  function startFaceDetection() {
    // Verificar que las clases globales de MediaPipe existan
    if (typeof FaceDetection === 'undefined' || typeof Camera === 'undefined') {
      console.warn('MediaPipe no cargado correctamente. Se omite detección facial.');
      setStatus('Cámara no disponible (scripts no cargados).', false);
      return;
    }

    const videoElement = document.createElement('video');
    videoElement.style.display = 'none';
    document.body.appendChild(videoElement);

    const faceDetection = new FaceDetection({
      locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_detection/${file}`,
    });

    faceDetection.setOptions({
      model: 'short',
      minDetectionConfidence: 0.5,
    });

    faceDetection.onResults(onFaceResults);

    const cameraInstance = new Camera(videoElement, {
      onFrame: async () => {
        try {
          await faceDetection.send({ image: videoElement });
        } catch (err) {
          console.warn('Error en frame de detección:', err);
        }
      },
      width: 640,
      height: 480,
    });

    // Iniciar cámara con manejo de errores y timeout
    cameraInstance.start()
      .then(() => {
        console.log('Cámara iniciada correctamente');
        setStatus('Cámara activa · Detección de presencia', false);
      })
      .catch((err) => {
        console.error('Error al iniciar cámara:', err);
        setStatus('Cámara no disponible. Usá texto o voz.', false);
      });
  }


  function quickQuestion(question) {

    document.getElementById("text-input").value = question;

    sendText();
  }

  function onFaceResults(results) {

    if (results.detections.length > 0) {

      if (!personPresent) {

        personPresent = true;

        console.log('✅ Persona detectada');

        // reiniciar memoria
        fetch(`${API}/reset-memory`, {
          method: 'POST'
        }).catch(console.error);

        // iniciar micrófono
        if (recognition && !isListening) {
          recognition.start();
        }
      }

      clearTimeout(presenceTimer);
      presenceTimer = null;

    } else {

      if (personPresent && !presenceTimer) {

        presenceTimer = setTimeout(() => {

          personPresent = false;

          console.log("❌ Persona ausente");

          if (recognition && isListening) {
            recognition.stop();
          }

          onListeningEnd();

        }, 5000);
      }
    }
  }

  // Esperar a que el DOM esté listo y luego iniciar detección
  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
      startFaceDetection();
    }, 500);
  });

  // Reconocimiento de voz 
  function initSpeech() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
      const micBtn = $mic();
      if (micBtn) {
        micBtn.title = 'Voz no disponible en este navegador. Usa Chrome o Chromium.';
        micBtn.style.opacity = '0.4';
        micBtn.addEventListener('click', () =>
          alert('Tu navegador no soporta reconocimiento de voz.\nUsa Google Chrome o Chromium para activar el micrófono.')
        );
      }
      return;
    }

    recognition = new SpeechRec();
    recognition.lang = 'es-ES';
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.onstart = () => {
      isListening = true;
      const micBtn = $mic();
      if (micBtn) micBtn.classList.add('active');
      const lbl = document.getElementById('mic-label');
      if (lbl) lbl.textContent = 'Escuchando…';
      setStatus('Escuchando… habla ahora', true);
      onListeningStart();
    };

    recognition.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        interim += e.results[i][0].transcript;
      }
      if ($transcript()) $transcript().textContent = interim;
      if (e.results[e.results.length - 1].isFinal) {
        agregarMensaje(interim, 'user');
        sendQuestion(interim);
      }
    };

    recognition.onerror = () => stopListening();
    recognition.onend = () => stopListening();
  }

  function stopListening() {
    isListening = false;
    const micBtn = $mic();
    if (micBtn) micBtn.classList.remove('active');
    const lbl = document.getElementById('mic-label');
    if (lbl) lbl.textContent = 'Hablar';
    setStatus('Sistema listo · Habla o escribe');
    onListeningEnd();
  }

  window.toggleMic = function () {
    if (!recognition) {
      alert('Reconocimiento de voz no disponible en este navegador.');
      return;
    }
    if (isListening) {
      recognition.stop();
    } else {
      if ($transcript()) $transcript().textContent = '';
      recognition.start();
    }
  };

  const micBtn = $mic();
  if (micBtn) micBtn.addEventListener('click', window.toggleMic);

  initSpeech();
})();
