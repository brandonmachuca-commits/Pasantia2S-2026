(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const TOKEN_KEY = 'tip_admin_token';
  let token = sessionStorage.getItem(TOKEN_KEY) || '';
  let documentData = {};
  const headers = () => token ? { Authorization: `Bearer ${token}` } : {};

  function notice(id, message, type = '') {
    const el = $(id); el.textContent = message; el.className = `notice ${type}`.trim();
  }
  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { ...headers(), ...(options.headers || {}) },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    return data;
  }
  function showDashboard() {
    $('login-view').hidden = true; $('dashboard').hidden = false;
  }
  function showLogin() {
    token = ''; sessionStorage.removeItem(TOKEN_KEY);
    $('dashboard').hidden = true; $('login-view').hidden = false;
  }
  function fillCategories(data) {
    documentData = data.categorias || {};
    const categorySelect = $('category');
    const current = categorySelect.value;
    categorySelect.replaceChildren();
    Object.keys(documentData).sort((a, b) => a.localeCompare(b, 'es')).forEach((name) => {
      const option = document.createElement('option'); option.value = name; option.textContent = name;
      categorySelect.append(option);
    });
    if (documentData[current]) categorySelect.value = current;
    updateTargets();
  }
  function updateTargets() {
    const category = $('category').value;
    const target = $('replace-target');
    target.replaceChildren(new Option('Agregar como archivo nuevo', ''));
    for (const path of (documentData[category]?.archivos || [])) {
      target.add(new Option(`Reemplazar: ${path}`, path));
    }
  }
  async function refresh() {
    const [docs, status] = await Promise.all([api('/admin/documents'), api('/admin/status')]);
    fillCategories(docs);
    const list = $('status-list'); list.replaceChildren();
    const categories = status.categorias || {};
    const names = Object.keys(categories).sort((a, b) => a.localeCompare(b, 'es'));
    if (!names.length) list.innerHTML = '<div class="empty">No hay agentes cargados.</div>';
    names.forEach((name) => {
      const item = document.createElement('div'); item.className = 'status-item';
      const label = document.createElement('div');
      const title = document.createElement('strong'); title.textContent = name;
      const detail = document.createElement('small');
      const info = categories[name];
      detail.textContent = `${info.archivos ?? 0} archivo(s) · ${info.fragmentos ?? info.chunks ?? 0} fragmentos`;
      label.append(title, detail);
      const count = document.createElement('span'); count.className = 'count';
      count.textContent = info.activo === false || (info.fragmentos ?? info.chunks ?? 0) === 0 ? 'Vacío' : 'Activo';
      item.append(label, count); list.append(item);
    });
  }
  $('login-form').addEventListener('submit', async (event) => {
    event.preventDefault(); notice('login-message', 'Verificando acceso…');
    try {
      const result = await fetch('/admin/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: $('admin-password').value }),
      });
      const data = await result.json().catch(() => ({}));
      if (!result.ok) throw new Error(data.detail || `HTTP ${result.status}`);
      token = data.token; sessionStorage.setItem(TOKEN_KEY, token); $('admin-password').value = '';
      showDashboard(); await refresh(); notice('status-message', 'Acceso concedido.', 'success');
    } catch (error) { notice('login-message', error.message, 'error'); }
  });
  $('category').addEventListener('change', updateTargets);
  $('file-input').addEventListener('change', () => {
    const file = $('file-input').files[0];
    $('file-label').textContent = file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB` : 'Selecciona un archivo';
  });
  const dropZone = $('drop-zone');
  dropZone.addEventListener('dragover', (event) => { event.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', (event) => {
    event.preventDefault(); dropZone.classList.remove('dragover');
    if (event.dataTransfer.files.length) {
      $('file-input').files = event.dataTransfer.files;
      $('file-input').dispatchEvent(new Event('change'));
    }
  });
  $('upload-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const file = $('file-input').files[0];
    if (!file) return;
    $('upload-submit').disabled = true; notice('upload-message', 'Validando y subiendo el archivo…');
    try {
      const form = new FormData();
      form.append('categoria', $('category').value);
      form.append('reemplazar', $('replace-target').value);
      form.append('archivo', file);
      const result = await api('/admin/upload', { method: 'POST', body: form });
      notice('upload-message', result.mensaje || 'Archivo subido y agente actualizado.', 'success');
      $('upload-form').reset(); $('file-label').textContent = 'Selecciona un archivo';
      await refresh();
    } catch (error) {
      notice('upload-message', error.message, 'error');
      if (error.message.includes('401')) showLogin();
    } finally { $('upload-submit').disabled = false; }
  });
  $('reload-btn').addEventListener('click', async () => {
    $('reload-btn').disabled = true; notice('status-message', 'Recargando agentes…');
    try {
      const result = await api('/admin/reload', { method: 'POST' });
      await refresh(); notice('status-message', result.mensaje || 'Agentes recargados.', 'success');
    } catch (error) { notice('status-message', error.message, 'error'); }
    finally { $('reload-btn').disabled = false; }
  });
  $('logout-btn').addEventListener('click', async () => {
    try { await api('/admin/logout', { method: 'POST' }); } catch (_) { /* token may have expired */ }
    showLogin(); notice('login-message', 'Sesión cerrada.');
  });

  if (token) {
    showDashboard();
    refresh().catch((error) => { showLogin(); notice('login-message', error.message, 'error'); });
  }
})();
