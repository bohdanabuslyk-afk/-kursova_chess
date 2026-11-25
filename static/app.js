import { Board, parseFen } from '/static/board.js';
import { AnalysisView } from '/static/analysis.js';
import { Coach } from '/static/coach.js';
import { settings, set as setSetting, sound } from '/static/settings.js';

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
let st = null;        // стан партії з сервера
let view = null;      // номер півходу, який переглядаємо; null – поточна позиція
let busy = false;     // суперник думає
let levels = [];
let model = { ready: false };

export async function api(url, body) {
  const r = await fetch(url, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || 'Помилка сервера');
  return data;
}
const say = (text = '', info = false) => { $('msg').textContent = text; $('msg').classList.toggle('info', info); };
const guard = fn => async (...a) => { say(); try { await fn(...a); } catch (e) { say(e.message); } };

// ---------- партія ----------
const board = new Board($('board'), move => play(move));

async function play(move) {
  say();
  try {
    st = await api(`/api/games/${st.id}/move`, { move });
    $('move-input').value = '';
  } catch (e) { say(e.message); }
  view = null; board.setArrows([]);
  render();
  reply();
}

async function reply() {
  if (busy || st.result || st.playersTurn) return;
  const id = st.id;
  busy = true; render();
  try {
    const next = await api(`/api/games/${id}/reply`, {});
    if (st.id === id) st = next;
  } catch (e) { say(e.message); }
  busy = false;
  render();
  if (st.id !== id) reply();
}

// ---------- аналіз ----------
let rows = null;      // розбір ходів, якщо він є
const analysis = new AnalysisView($('tab-analysis'), {
  api, go: n => go(n),
  onData: d => { rows = d?.rows || null; if (st) render(); },
  explain: (ply, btn) => explainMove(ply, btn),
});
const explained = new Map();   // партія:хід -> пояснення
analysis.explained = ply => {
  const key = `${st.id}:${st.history.length}:${ply}`, e = explained.get(key);
  if (!e) return model.ready ? `<button class="btn small" data-explain="${ply}">Пояснити мовною моделлю</button>` : '<p class="dim">Підключіть мовну модель, щоб отримати пояснення словами.</p>';
  if (e.wait) return '<p class="dim">Готую пояснення…</p>';
  return `<blockquote>${esc(e.text)}<footer>${e.by === 'llm' ? `Мовна модель ${esc(e.model)}` : 'Пояснення за шаблоном, без мовної моделі'}</footer></blockquote>${e.warning ? `<p class="warn">${esc(e.warning)}</p>` : ''}`;
};
async function explainMove(ply) {
  const key = `${st.id}:${st.history.length}:${ply}`;
  explained.set(key, { wait: true }); analysis.render();
  try { explained.set(key, await api(`/api/games/${st.id}/explain`, { ply })); }
  catch (e) { explained.delete(key); say(e.message); }
  analysis.render();
}
const coach = new Coach($('tab-coach'), { api, status: () => model });
document.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => showTab(b.dataset.tab));
function showTab(name) {
  document.querySelectorAll('[data-tab]').forEach(b => {
    b.setAttribute('aria-selected', b.dataset.tab === name);
    $('tab-' + b.dataset.tab).hidden = b.dataset.tab !== name;
  });
}

let heard = 0;
function playSound() {
  const n = st.history.length;
  if (n > heard) {
    const h = st.history.at(-1);
    sound(st.result ? 'end' : h.check ? 'check' : h.san.includes('x') ? 'capture' : 'move');
  }
  heard = n;
}

function open(state) {
  heard = state.history.length;
  st = state; view = null;
  localStorage.setItem('game', st.id);
  board.setArrows([]);
  coach.open(st.id);
  board.setFlipped(st.color === 'black');
  render(); reply();
}

// ---------- малювання ----------
const position = () => {
  const n = view ?? st.history.length;
  const h = n ? st.history[n - 1] : null;
  return { n, fen: h ? h.fen : st.startFen, last: h?.uci, check: h?.check };
};

function render() {
  const p = position(), live = view === null || view === st.history.length;
  const row = rows?.[p.n - 1];
  board.set({
    fen: p.fen, last: p.last, check: p.check, legal: live && !busy ? st.legal : {},
    badge: row && { cls: row.class, text: row.mark },
  });
  // Стрілка показує, що варто було зіграти замість помилкового ходу.
  if (row) board.setArrows(['inacc', 'mistake', 'blunder'].includes(row.class) ? [{ uci: row.bestUci, cls: 'best' }] : []);
  renderEval(row);
  if (analysis.ply !== p.n) analysis.setPly(p.n);
  analysis.load(st);
  playSound();
  renderPlayers(p);
  renderStatus();
  $('finish').hidden = !st.result && !st.imported;
  renderMoves(p.n);
  $('pgn').href = `/api/games/${st.id}/pgn`;
  $('undo').disabled = st.imported || !st.history.length;
  $('hint').disabled = !!st.result || st.imported || busy || !live;
  $('resign').disabled = !!st.result || st.imported;
}

function renderEval(row) {
  const bar = $('evalbar');
  bar.hidden = !rows;
  if (!rows) return;
  bar.classList.toggle('flipped', board.flipped);
  bar.firstElementChild.style.height = `${row ? row.win : 50}%`;
  bar.lastElementChild.textContent = row ? row.scoreText : '0';
}

const VAL = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 }, START = { p: 8, n: 2, b: 2, r: 2, q: 1 };
function renderPlayers(p) {
  const pieces = Object.values(parseFen(p.fen));
  const count = c => pieces.filter(x => x === c).length;
  const sum = c => pieces.filter(x => x[0] === c).reduce((s, x) => s + VAL[x[1]], 0);
  const diff = sum('w') - sum('b');
  const bot = { engine: `Рушій · ${st.levelName}`, llm: `Мовна модель · ${st.levelName}`, human: 'Гравець 2' }[st.opponent];
  const draw = (el, c) => {
    const color = c === 'w' ? 'white' : 'black', me = st.color === color;
    const enemy = c === 'w' ? 'b' : 'w', adv = c === 'w' ? diff : -diff;
    let cap = '';
    for (const t of 'qrbnp') for (let i = 0, k = START[t] - count(enemy + t); i < k; i++) cap += `<img class="${i ? '' : 'gap'}" src="/pieces/${enemy}${t}.svg" alt="">`;
    const thinking = busy && !me ? '<span class="think">думає…</span>' : '';
    el.innerHTML = `<span class="dot ${c}"></span><b>${st.imported ? (c === 'w' ? 'Білі' : 'Чорні') : me ? 'Ви' : bot}</b>${thinking}<span class="cap">${cap}${adv > 0 ? `<span>+${adv}</span>` : ''}</span>`;
  };
  draw($('p-top'), board.flipped ? 'w' : 'b');
  draw($('p-bottom'), board.flipped ? 'b' : 'w');
}

function renderStatus() {
  const side = st.turn === 'white' ? 'білих' : 'чорних';
  $('status').textContent = st.result ? `${st.result.replace('1/2-1/2', '½–½').replace('-', '–')} · ${st.reason}`
    : st.imported ? 'Перегляд партії' : `Хід ${side}${st.opponent === 'human' ? '' : st.playersTurn ? ' – ваш' : ''}`;
  $('opening').textContent = st.opening || '';
  const i = st.info;
  if (i?.llm) {
    const bad = i.errors.length ? `<br>Відхилено: ${i.errors.map(esc).join('; ')}` : '';
    $('info').innerHTML = `${i.comment ? `<q>${esc(i.comment)}</q><br>` : ''}${i.fallback ? 'Модель не дала правильного ходу – зіграв рушій' : `${esc(i.model)} · ${i.mode} · спроб: ${i.attempts}`} · ${i.seconds} с${bad}`;
  } else $('info').textContent = i?.by === 'book' ? 'хід із дебютної книги' : i?.by === 'engine' && i.nodes ? `глибина ${i.depth} · ${i.nodes.toLocaleString('uk')} позицій · ${i.seconds} с` : '';
}

const mark = ply => { const r = rows?.[ply - 1]; return r && r.class !== 'good' ? `<i class="mk ${r.class}" title="${r.className}">${r.mark}</i>` : ''; };
function renderMoves(current) {
  const box = $('moves');
  if (!st.history.length) { box.innerHTML = '<div class="empty">Ходів ще немає. Перетягніть фігуру, клацніть її або введіть хід текстом.</div>'; return; }
  box.innerHTML = st.history.map((h, i) =>
    (i % 2 ? '' : `<span class="n">${i / 2 + 1}.</span>`) +
    `<button data-ply="${h.ply}" class="${h.ply === current ? 'on' : ''}">${esc(h.san)}${mark(h.ply)}</button>`).join('');
  box.querySelector('.on')?.scrollIntoView({ block: 'nearest' });
}

function go(n) {
  view = Math.max(0, Math.min(st.history.length, n));
  if (view === st.history.length) view = null;
  board.setArrows([]);
  render();
}

// ---------- події ----------
$('moves').onclick = e => { const b = e.target.closest('[data-ply]'); if (b) go(+b.dataset.ply); };
const NAV = { start: () => 0, prev: n => n - 1, next: n => n + 1, end: () => Infinity };
document.querySelectorAll('[data-nav]').forEach(b => b.onclick = () => go(NAV[b.dataset.nav](position().n)));
document.addEventListener('keydown', e => {
  if (e.target.matches('input, textarea, select') || document.querySelector('dialog[open]')) return;
  const k = { ArrowLeft: 'prev', ArrowRight: 'next', Home: 'start', End: 'end' }[e.key];
  if (k) { e.preventDefault(); go(NAV[k](position().n)); }
  if (e.key === 'f' || e.key === 'а') $('flip').click();
});
$('entry').onsubmit = e => { e.preventDefault(); play($('move-input').value); };
$('flip').onclick = () => { board.setFlipped(!board.flipped); render(); };
$('undo').onclick = guard(async () => { st = await api(`/api/games/${st.id}/undo`, {}); view = null; board.setArrows([]); render(); });
$('resign').onclick = guard(async () => { if (confirm('Здатися?')) { st = await api(`/api/games/${st.id}/resign`, {}); render(); } });
$('hint').onclick = guard(async () => {
  $('hint').disabled = true; say('Шукаю хід…', true);
  const id = st.id, n = st.history.length, h = await api(`/api/games/${id}/hint`, {});
  $('hint').disabled = false;
  if (st.id !== id || st.history.length !== n) return say();
  board.setArrows([{ uci: h.uci, cls: 'hint' }]); say(`Підказка: ${h.pv}`, true);
});

$('finish-analyse').onclick = () => { showTab('analysis'); if (!analysis.data) analysis.run('fast'); };
$('finish-new').onclick = () => $('btn-new').click();

// ---------- діалоги ----------
$('btn-settings').onclick = () => {
  for (const i of $('settings-box').querySelectorAll('input')) i.type === 'checkbox' ? i.checked = settings[i.name] : i.checked = settings[i.name] === i.value;
  $('dlg-settings').showModal();
};
$('settings-box').onchange = e => setSetting(e.target.name, e.target.type === 'checkbox' ? e.target.checked : e.target.value);
document.querySelectorAll('[data-close]').forEach(b => b.onclick = () => b.closest('dialog').close());
const form = $('form-new');
const syncForm = () => {
  $('fs-level').hidden = form.opponent.value === 'human';
  const llmOpt = form.querySelector('[value=llm]');
  llmOpt.disabled = !model.ready;
  llmOpt.closest('label').title = model.ready ? model.model : 'Заповніть файл .env';
  if (!model.ready) $('llm-note').textContent = 'Мовну модель не підключено: заповніть файл .env і перезапустіть сервер.';
  else $('llm-note').textContent = form.opponent.value === 'llm' ? `${model.model}. Рівні 1–3: модель обирає сама; 4–5: із найкращих ходів рушія.` : '';
  $('level-desc').textContent = form.opponent.value === 'llm' ? '' : levels.find(l => l.id === +form.level.value)?.description || '';
};
form.onchange = syncForm;
form.onsubmit = guard(async () => {
  open(await api('/api/games', { color: form.color.value, opponent: form.opponent.value, level: +form.level.value }));
});
$('btn-new').onclick = () => { syncForm(); $('dlg-new').showModal(); };
$('btn-archive').onclick = async () => {
  $('import-msg').textContent = '';
  const list = await api('/api/games');
  $('games').innerHTML = list.map(g => `<button data-id="${g.id}"><span>${esc(g.white)} – ${esc(g.black)}</span><b>${esc(g.result)}</b><small>${esc(g.time)} · ходів: ${g.moves}</small><small>${esc(g.reason || '')}</small></button>`).join('') || '<small>Збережених партій ще немає.</small>';
  $('dlg-archive').showModal();
};
$('games').onclick = guard(async e => {
  const b = e.target.closest('[data-id]');
  if (b) { const s = await api(`/api/games/${b.dataset.id}`); $('dlg-archive').close(); open(s); }
});
$('do-import').onclick = async () => {
  try { const s = await api('/api/import', { pgn: $('pgn-text').value }); $('dlg-archive').close(); open(s); go(0); }
  catch (e) { $('import-msg').textContent = e.message; }
};

// ---------- старт ----------
[levels, model] = await Promise.all([api('/api/levels'), api('/api/llm')]);
$('level-cards').innerHTML = levels.map(l => `<label><input type="radio" name="level" value="${l.id}" ${l.id === 3 ? 'checked' : ''}>${esc(l.name)}</label>`).join('');
$('chip-model').textContent = model.ready ? model.model : 'без моделі';
$('chip-model').title = model.ready ? 'Підключена мовна модель' : 'Заповніть .env, щоб підключити мовну модель';
$('chip-model').classList.toggle('on', model.ready);
const old = localStorage.getItem('game');
try { open(old ? await api(`/api/games/${old}`) : await api('/api/games', { color: 'white', level: 3 })); }
catch { open(await api('/api/games', { color: 'white', level: 3 })); }
