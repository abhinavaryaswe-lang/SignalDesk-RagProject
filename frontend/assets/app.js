const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
let allDocs = [];
let toastTimer;

function toast(message, error = false) {
  const node = $('#toast');
  node.textContent = message;
  node.classList.toggle('error', error);
  node.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove('show'), 3600);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

function go(view) {
  $$('.view').forEach(node => node.classList.remove('active'));
  $(`#view-${view}`)?.classList.add('active');
  $$('.nav-item').forEach(node => node.classList.toggle('active', node.dataset.view === view));
  const names = { overview: 'Overview', research: 'Research assistant', library: 'Knowledge library' };
  $('#crumb').textContent = names[view] || 'Overview';
  if (view === 'research') setTimeout(() => $('#question').focus(), 50);
}

$$('[data-view]').forEach(button => button.addEventListener('click', () => go(button.dataset.view)));

function niceDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? 'Just now' : new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date);
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

function renderDocs() {
  const count = allDocs.length;
  $('#nav-doc-count').textContent = count;
  $('#stat-documents').textContent = count;
  $('#stat-chunks').textContent = allDocs.reduce((sum, d) => sum + Number(d.chunks || 0), 0);
  $('#library-count').innerHTML = `<strong>${count} ${count === 1 ? 'source' : 'sources'}</strong><span> are powering your market view</span>`;

  const recent = $('#recent-list');
  if (!count) {
    recent.innerHTML = `<div class="empty-state"><div class="empty-icon">▤</div><strong>Your research starts here</strong><p>Add reports, customer interviews, or market notes to build your source library.</p><button class="button primary small" data-action="upload">Add your first source <span>＋</span></button></div>`;
  } else {
    recent.innerHTML = allDocs.slice(0, 4).map(d => `<div class="doc-row"><div class="doc-name"><span class="file-icon">${esc(d.file_type)}</span><span><strong>${esc(d.name)}</strong><small>${formatBytes(d.size_bytes)}</small></span></div><span class="file-type">${esc(d.file_type)}</span><span class="segments">${Number(d.chunks)} passages</span><span class="doc-date">${niceDate(d.created_at)}</span><span></span></div>`).join('');
  }
  renderLibrary();
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function renderLibrary() {
  const filter = ($('#filter-docs')?.value || '').toLowerCase();
  const docs = allDocs.filter(d => d.name.toLowerCase().includes(filter));
  const body = $('#document-list');
  if (!allDocs.length) {
    body.innerHTML = `<div class="empty-library"><div class="empty-icon">▤</div><h3>A clearer view starts with good sources.</h3><p>Add a market report, customer feedback, or research notes to get started.</p><button class="button primary small" data-action="upload">Add your first source <span>＋</span></button></div>`;
  } else if (!docs.length) {
    body.innerHTML = `<div class="empty-library"><h3>No matching sources</h3><p>Try another search term.</p></div>`;
  } else {
    body.innerHTML = docs.map(d => `<div class="doc-row"><div class="doc-name"><span class="file-icon">${esc(d.file_type)}</span><span><strong title="${esc(d.name)}">${esc(d.name)}</strong><small>${formatBytes(d.size_bytes)}</small></span></div><span class="file-type">${esc(d.file_type)}</span><span class="segments">${Number(d.chunks)} passages</span><span class="doc-date">${niceDate(d.created_at)}</span><button class="delete-doc" title="Remove ${esc(d.name)}" aria-label="Remove ${esc(d.name)}" data-delete="${esc(d.id)}">×</button></div>`).join('');
  }
}

async function refresh() {
  try {
    const [docs, stats] = await Promise.all([api('/api/documents'), api('/api/stats')]);
    allDocs = docs;
    renderDocs();
    const providerNames = { ollama: 'Local models', cloudflare: 'Cloudflare AI', huggingface: 'Hugging Face' };
    $('#provider-name').textContent = providerNames[stats.provider] || stats.provider;
    $('#stat-model').textContent = stats.ready ? stats.model : stats.provider_status;
    $('#connection-label').textContent = stats.ready ? `${providerNames[stats.provider] || stats.provider} ready` : stats.provider_status;
    $('#connection-dot').className = `status-dot ${stats.ready ? 'online' : 'offline'}`;
  } catch (error) {
    $('#connection-label').textContent = 'Offline';
    $('#connection-dot').className = 'status-dot offline';
  }
}

document.addEventListener('click', async event => {
  const upload = event.target.closest('[data-action="upload"]');
  if (upload) $('#file-input').click();
  const remove = event.target.closest('[data-delete]');
  if (remove) {
    remove.disabled = true;
    try {
      await api(`/api/documents/${encodeURIComponent(remove.dataset.delete)}`, { method: 'DELETE' });
      toast('Source removed from your library.');
      await refresh();
    } catch (error) { toast(error.message, true); remove.disabled = false; }
  }
  const promptButton = event.target.closest('[data-prompt]');
  if (promptButton) {
    go('research');
    $('#question').value = promptButton.dataset.prompt;
    $('#question').focus();
    $('#question').dispatchEvent(new Event('input'));
  }
});

$('#file-input').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  const submitButtons = $$('[data-action="upload"]');
  submitButtons.forEach(b => b.disabled = true);
  toast(`Reading ${file.name} and creating search embeddings…`);
  const form = new FormData();
  form.append('file', file);
  try {
    const result = await api('/api/documents', { method: 'POST', body: form });
    toast(`${result.name} added · ${result.chunks} searchable passages`);
    await refresh();
  } catch (error) { toast(error.message, true); }
  finally { submitButtons.forEach(b => b.disabled = false); event.target.value = ''; }
});

$('#filter-docs').addEventListener('input', renderLibrary);

function markdown(text) {
  let html = esc(text);
  html = html.replace(/\[([0-9]+)\]/g, '<span data-cite>[$1]</span>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  return html.split(/\n\n+/).map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
}

function appendQuestion(text) {
  const stage = $('#chat-stage');
  const welcome = $('.chat-welcome', stage);
  if (welcome) welcome.remove();
  let messages = $('.chat-messages', stage);
  if (!messages) {
    messages = document.createElement('div');
    messages.className = 'chat-messages';
    stage.append(messages);
  }
  const user = document.createElement('div');
  user.className = 'message user';
  user.textContent = text;
  messages.append(user);
  const pending = document.createElement('div');
  pending.className = 'message assistant';
  pending.innerHTML = '<div class="assistant-badge">✳</div><div class="typing" aria-label="Searching sources"><i></i><i></i><i></i></div>';
  messages.append(pending);
  stage.scrollTop = stage.scrollHeight;
  pending.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  return pending;
}

$('#chat-form').addEventListener('submit', async event => {
  event.preventDefault();
  const input = $('#question');
  const question = input.value.trim();
  if (!question) return;
  input.value = '';
  input.style.height = 'auto';
  const pending = appendQuestion(question);
  $('#send-button').disabled = true;
  try {
    const result = await api('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) });
    const citations = result.sources?.length ? `<details class="source-drawer"><summary>Evidence · ${result.sources.length} ${result.sources.length === 1 ? 'source passage' : 'source passages'}</summary>${result.sources.map(s => `<div class="citation"><span class="citation-num">${s.index}</span><span><strong>${esc(s.name)}${s.page ? ` · page ${s.page}` : ''}</strong><p>${esc(s.excerpt)}${s.excerpt.length >= 300 ? '…' : ''}</p></span></div>`).join('')}</details>` : '';
    pending.innerHTML = `<div class="assistant-badge">✳</div><div class="answer-body">${markdown(result.answer)}${citations}</div>`;
  } catch (error) {
    const selectedProvider = $('#provider-name').textContent;
    const hint = selectedProvider === 'Local models' ? 'Make sure Ollama is running and both models are installed.' : selectedProvider === 'Cloudflare AI' ? 'Check your Cloudflare credentials and daily Workers AI usage.' : 'Check your Hugging Face token, inference provider settings, and remaining credits.';
    pending.innerHTML = `<div class="assistant-badge">✳</div><div class="answer-body"><p>${esc(error.message)}</p><p>${esc(hint)}</p></div>`;
  } finally { $('#send-button').disabled = false; pending.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
});

$('#question').addEventListener('input', event => {
  event.target.style.height = 'auto';
  event.target.style.height = `${Math.min(event.target.scrollHeight, 110)}px`;
});
$('#question').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); $('#chat-form').requestSubmit(); }
});

refresh();
