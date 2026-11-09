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
    if (!response.ok) {
      const detail = data.detail && typeof data.detail === 'object' ? data.detail : null;
      const error = new Error(detail?.mensaje || data.detail || data.error || `HTTP ${response.status}`);
      error.detail = detail;
      throw error;
    }
    return data;
  }
  function folderOf(path) {
    const parts = path.split('/');
    return parts.length > 1 ? parts.slice(0, -1).join('/') : '';
  }
  function groupByFolder(paths) {
    const groups = new Map();
    for (const path of paths) {
      const folder = folderOf(path);
      if (!groups.has(folder)) groups.set(folder, []);
      groups.get(folder).push(path);
    }
    return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0], 'es'));
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
    for (const [folder, paths] of groupByFolder(documentData[category]?.archivos || [])) {
      const group = document.createElement('optgroup');
      group.label = folder ? `Carpeta ${folder}` : 'Raíz de la categoría';
      for (const path of paths) group.append(new Option(`Reemplazar: ${path}`, path));
      target.append(group);
    }
    renderFiles();
  }
  function renderFiles() {
    const category = $('category').value;
    const list = $('files-list');
    list.replaceChildren();
    const paths = documentData[category]?.archivos || [];
    if (!paths.length) {
      list.innerHTML = '<div class="empty">Esta categoría todavía no tiene archivos.</div>';
      return;
    }
    for (const [folder, items] of groupByFolder(paths)) {
      const group = document.createElement('div'); group.className = 'folder-group';
      const title = document.createElement('h3'); title.textContent = folder ? `Carpeta ${folder}` : 'Raíz de la categoría';
      group.append(title);
      for (const path of items) {
        const row = document.createElement('div'); row.className = 'file-row';
        const name = document.createElement('span'); name.textContent = path.split('/').pop();
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'btn btn-danger'; remove.textContent = 'Eliminar';
        remove.addEventListener('click', () => deleteFile(category, path));
        row.append(name, remove); group.append(row);
      }
      list.append(group);
    }
  }
  async function deleteFile(category, path) {
    if (!window.confirm(`¿Eliminar ${category}/${path}? Esta acción no se puede deshacer.`)) return;
    notice('files-message', 'Eliminando…');
    try {
      const form = new FormData();
      form.append('categoria', category); form.append('archivo', path);
      const result = await api('/admin/delete', { method: 'POST', body: form });
      notice('files-message', result.mensaje || 'Archivo eliminado.', 'success');
      await refresh();
    } catch (error) { notice('files-message', error.message, 'error'); }
  }
  async function refresh() {
    const [docs, status] = await Promise.all([api('/admin/documents'), api('/admin/status')]);
    fillCategories(docs);
    const list = $('status-list'); list.replaceChildren();
    const categories = status.categorias || {};
    const names = Object.keys(categories).sort((a, b) => a.localeCompare(b, 'es'));
    if (!names.length) list.innerHTML = '<div class="empty">No hay agentes cargados.</div>';
    names.forEach((name) => {
      const info = categories[name];
      const chunks = info.fragmentos ?? info.chunks ?? 0;
      const empty = info.activo === false || chunks === 0;
      const row = document.createElement('div'); row.className = 'status-item'; row.setAttribute('role', 'row');
      const cells = [
        ['name', name, 'rowheader'],
        ['num', String(info.archivos ?? 0), 'cell'],
        ['num', String(chunks), 'cell'],
      ];
      cells.forEach(([kind, text, role]) => {
        const cell = document.createElement('span'); cell.className = kind; cell.textContent = text; cell.setAttribute('role', role);
        row.append(cell);
      });
      const state = document.createElement('span'); state.setAttribute('role', 'cell'); state.className = 'num';
      const badge = document.createElement('span'); badge.className = `badge ${empty ? 'empty-badge' : 'ok-badge'}`;
      badge.textContent = empty ? 'Vacío' : 'Activo';
      state.append(badge); row.append(state); list.append(row);
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
      showDashboard(); await refresh();
    } catch (error) { notice('login-message', error.message, 'error'); }
  });
  $('category').addEventListener('change', updateTargets);
  $('file-input').addEventListener('change', () => {
    const file = $('file-input').files[0];
    $('file-label').textContent = file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB` : 'Selecciona o arrastra un archivo';
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
  function hideDup() { $('dup-box').hidden = true; $('dup-actions').replaceChildren(); }
  function showDup(detail) {
    $('dup-text').textContent = detail.mensaje;
    const actions = $('dup-actions'); actions.replaceChildren();
    const add = (label, handler, kind = 'btn-secondary') => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = `btn ${kind}`; button.textContent = label;
      button.addEventListener('click', handler); actions.append(button);
    };
    if (detail.codigo === 'similares') {
      for (const path of detail.archivos) {
        add(`Reemplazar ${path}`, () => { $('replace-target').value = path; hideDup(); upload(); }, 'btn-primary');
      }
      add('Subir como archivo nuevo', () => { hideDup(); upload({ confirmar: '1' }); });
    }
    add('Cancelar', hideDup);
    $('dup-box').hidden = false;
  }
  async function upload(extra = {}) {
    const file = $('file-input').files[0];
    if (!file) return;
    $('upload-submit').disabled = true; notice('upload-message', 'Validando y subiendo el archivo…');
    try {
      const form = new FormData();
      form.append('categoria', $('category').value);
      form.append('reemplazar', $('replace-target').value);
      form.append('archivo', file);
      for (const [key, value] of Object.entries(extra)) form.append(key, value);
      const result = await api('/admin/upload', { method: 'POST', body: form });
      notice('upload-message', result.mensaje || 'Archivo subido y agente actualizado.', 'success');
      const category = $('category').value;
      $('upload-form').reset(); $('category').value = category;
      $('file-label').textContent = 'Selecciona o arrastra un archivo';
      await refresh();
    } catch (error) {
      if (error.detail?.codigo === 'similares' || error.detail?.codigo === 'identico') {
        notice('upload-message', 'No se subió todavía: revisa el aviso.', 'error');
        showDup(error.detail);
      } else {
        notice('upload-message', error.message, 'error');
        if (error.message.includes('401')) showLogin();
      }
    } finally { $('upload-submit').disabled = false; }
  }
  $('upload-form').addEventListener('submit', (event) => { event.preventDefault(); hideDup(); upload(); });
  $('file-input').addEventListener('change', hideDup);
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
