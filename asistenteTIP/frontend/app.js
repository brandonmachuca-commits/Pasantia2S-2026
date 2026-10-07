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

  async function speak(text) {
    const clean = cleanForSpeech(text);
    if (!clean) return;
    try {
      const response = await fetch(`${API}/speak`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: clean }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const url = URL.createObjectURL(await response.blob());
      currentAudio = new Audio(url);
      currentAudio.onplay = () => setHologram('speaking');
      currentAudio.onended = () => {
        URL.revokeObjectURL(url); currentAudio = null;
        setHologram('inactive'); setStatus('Sistema listo · Escribe o pulsa el micrófono');
        $('stop-btn').hidden = true;
      };
      currentAudio.onerror = () => {
        URL.revokeObjectURL(url); currentAudio = null; setHologram('inactive');
        $('stop-btn').hidden = true;
      };
      await currentAudio.play();
    } catch (error) {
      console.warn('No se pudo reproducir la respuesta en voz:', error);
      setHologram('inactive'); $('stop-btn').hidden = true;
    }
  }

  async function sendQuestion(question) {
    const cleanQuestion = question.trim();
    if (!cleanQuestion) return;
    if (currentController) currentController.abort();
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }

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
      }
    } finally {
      currentController = null;
    }
  }

  function stopResponse() {
    if (currentController) { currentController.abort(); currentController = null; }
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
    if (isListening && recognition) recognition.stop();
    setHologram('inactive'); setStatus('Respuesta detenida'); $('stop-btn').hidden = true;
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
        setStatus('Permite el uso del micrófono en el navegador para hablar.');
      } else if (event.error !== 'no-speech' && event.error !== 'aborted') {
        setStatus('No se pudo usar el micrófono; puedes escribir la consulta.');
      }
    };
    recognition.onend = () => {
      setMicButton(false); setHologram('inactive');
      if ($('status-bar').textContent.startsWith('Escuchando')) setStatus('Sistema listo · Escribe o pulsa el micrófono');
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
})();
