// Tema claro/oscuro: se aplica antes de pintar la página para evitar un destello y se recuerda en este navegador.
(function () {
  'use strict';
  const KEY = 'tema_interfaz';
  const root = document.documentElement;

  function guardado() {
    try { return localStorage.getItem(KEY); } catch (error) { return null; }
  }

  function inicial() {
    const valor = guardado();
    if (valor === 'claro' || valor === 'oscuro') return valor;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro';
  }

  function aplicar(tema) {
    root.dataset.tema = tema;
    document.querySelectorAll('.theme-toggle button[data-tema]').forEach((boton) => {
      boton.setAttribute('aria-pressed', String(boton.dataset.tema === tema));
    });
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', tema === 'oscuro' ? '#262624' : '#F7F7F5');
  }

  aplicar(inicial());

  document.addEventListener('DOMContentLoaded', () => {
    aplicar(root.dataset.tema || inicial());
    document.querySelectorAll('.theme-toggle button[data-tema]').forEach((boton) => {
      boton.addEventListener('click', () => {
        aplicar(boton.dataset.tema);
        try { localStorage.setItem(KEY, boton.dataset.tema); } catch (error) { /* sin almacenamiento: solo dura esta visita */ }
      });
    });
  });
})();
