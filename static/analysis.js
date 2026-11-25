// Вкладка «Аналіз»: запуск, підсумок, графік шансів, розбір вибраного ходу.
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const ORDER = ['best', 'book', 'good', 'forced', 'inacc', 'mistake', 'blunder'];

export class AnalysisView {
  constructor(root, { api, go, onData, explain }) {
    Object.assign(this, { root, api, go, onData, explain, data: null, gameId: null, timer: null });
    root.addEventListener('click', e => {
      const t = e.target.closest('[data-speed],[data-go],[data-explain]');
      if (!t) return;
      if (t.dataset.speed) this.run(t.dataset.speed);
      if (t.dataset.go) this.go(+t.dataset.go);
      if (t.dataset.explain) this.explain(+t.dataset.explain, t);
    });
    root.addEventListener('pointermove', e => this.hover(e));
    root.addEventListener('pointerleave', () => this.tip(null));
  }

  async load(game) {
    const key = game.id + ':' + game.history.length;
    if (key === this.key) return;
    this.key = key; this.game = game; this.gameId = game.id; this.data = null; this.error = null;
    clearTimeout(this.timer);
    this.onData(null); this.render();
    await this.poll(key);
  }

  async run(speed) {
    this.error = null;
    try { this.data = await this.api(`/api/games/${this.gameId}/analysis`, { speed }); } catch (e) { this.error = e.message; }
    this.render();
    this.poll(this.key);
  }

  async poll(key) {
    let d;
    try { d = await this.api(`/api/games/${this.gameId}/analysis`); } catch (e) { this.error = e.message; this.render(); return; }
    if (key !== this.key) return;                     // поки чекали, відкрили іншу партію або зробили хід
    this.data = d.started === false ? null : d;
    this.onData(this.data);
    this.render();
    if (this.data && !this.data.summary && !this.data.error) this.timer = setTimeout(() => this.poll(key), 600);
  }

  setPly(n) { this.ply = n; this.render(); }
  row(n) { return this.data?.rows[n - 1]; }

  render() {
    const g = this.game, d = this.data;
    if (!g) return;
    const top = this.root.scrollTop;
    const buttons = `<div class="actions pad"><button class="btn primary" data-speed="fast">Швидкий аналіз</button><button class="btn" data-speed="deep">Глибокий аналіз</button></div>`;
    if (this.error || d?.error) { this.root.innerHTML = `<p class="note bad">${esc(this.error || d.error)}</p>${buttons}`; return; }
    if (!g.history.length) { this.root.innerHTML = '<p class="note">Зробіть хоча б один хід, щоб було що аналізувати.</p>'; return; }
    if (!d) { this.root.innerHTML = `<p class="note">Рушій оцінить кожен хід партії, знайде помилки та покаже кращі варіанти. Швидкий – близько 0,6 с на хід, глибокий – до 2 с.</p>${buttons}`; return; }
    let html = '';
    if (!d.summary) html += `<div class="progress"><span>Аналізую хід ${d.done} з ${d.total}</span><progress max="${d.total}" value="${d.done}"></progress></div>`;
    else html += this.summary(d);
    html += this.chart(d) + this.detail(d);
    if (d.summary) html += buttons.replace('primary', '').replace('Швидкий аналіз', 'Повторити швидкий').replace('Глибокий аналіз', 'Глибокий аналіз');
    this.root.innerHTML = html;
    this.root.scrollTop = top;
  }

  summary(d) {
    const s = d.summary, acc = c => s[c].accuracy === null ? '–' : s[c].accuracy.toFixed(1).replace('.', ',') + '%';
    const card = (c, name) => `<div class="acc"><span class="dot ${c[0]}"></span><div><b>${acc(c)}</b><small>${name} · точність</small><small>середня втрата ${s[c].acpl ?? '–'} сп</small></div></div>`;
    const rows = ORDER.filter(k => s.white.counts[k] + s.black.counts[k]).map(k =>
      `<tr><td>${s.white.counts[k]}</td><th><i class="mk ${k}">${d.classes[k].mark}</i>${d.classes[k].name}</th><td>${s.black.counts[k]}</td></tr>`).join('');
    return `<div class="accs">${card('white', 'білі')}${card('black', 'чорні')}</div>
      <table class="counts"><thead><tr><td>білі</td><th></th><td>чорні</td></tr></thead><tbody>${rows}</tbody></table>`;
  }

  chart(d) {
    const W = 420, H = 110, n = Math.max(d.total - 1, 1);
    const x = i => (i / n) * W, y = w => H - (w / 100) * H;
    const pts = [[0, 50], ...d.rows.map(r => [r.ply, r.win])];
    const line = pts.map(([i, w], k) => `${k ? 'L' : 'M'}${x(i).toFixed(1)},${y(w).toFixed(1)}`).join('');
    const last = pts.at(-1)[0];
    const dots = d.rows.filter(r => r.class === 'mistake' || r.class === 'blunder')
      .map(r => `<circle class="${r.class}" cx="${x(r.ply).toFixed(1)}" cy="${y(r.win).toFixed(1)}" r="4.5"/>`).join('');
    return `<figure class="chart"><figcaption>Шанси білих на перемогу, %</figcaption>
      <div class="plot" data-n="${n}"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Графік шансів білих за ходами">
      <rect class="blackside" width="${W}" height="${H}"/><path class="whiteside" d="${line}L${x(last)},${H}L0,${H}Z"/>
      <line class="mid" x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}"/><path class="line" d="${line}"/>
      ${this.ply ? `<line class="cur" x1="${x(this.ply)}" x2="${x(this.ply)}" y1="0" y2="${H}"/>` : ''}${dots}</svg>
      <span class="ax t">100</span><span class="ax m">50</span><span class="ax b">0</span><div class="tip" hidden></div></div>
      <div class="legend"><span><i class="mk mistake">?</i>помилка</span><span><i class="mk blunder">??</i>груба помилка</span></div></figure>`;
  }

  hover(e) {
    const plot = e.target.closest?.('.plot');
    if (!plot) return this.tip(null);
    const r = plot.getBoundingClientRect(), n = +plot.dataset.n;
    const ply = Math.round((e.clientX - r.left) / r.width * n), row = this.row(ply);
    plot.onclick = row ? () => this.go(ply) : null;
    this.tip(row, (ply / n) * 100, plot);
  }

  tip(row, pct, plot) {
    const tip = this.root.querySelector('.tip');
    if (!tip) return;
    tip.hidden = !row;
    if (!row) return;
    tip.textContent = `${Math.ceil(row.ply / 2)}${row.color === 'white' ? '.' : '…'} ${row.san} · ${row.scoreText} · білі ${Math.round(row.win)}% · ${row.className}`;
    tip.style.left = `${Math.max(22, Math.min(78, pct))}%`;
  }

  detail(d) {
    const r = this.row(this.ply);
    if (!r) {
      const m = d.summary?.moments || [];
      if (!d.summary) return '';
      return `<div class="detail"><h3>Ключові моменти</h3>${m.length ? `<div class="chips">${m.map(p => { const q = this.row(p); return `<button class="chip" data-go="${p}"><i class="mk ${q.class}">${q.mark}</i>${Math.ceil(p / 2)}${p % 2 ? '.' : '…'} ${esc(q.san)}</button>`; }).join('')}</div>` : '<p>Серйозних помилок немає.</p>'}<p class="dim">Виберіть хід у списку або на графіку, щоб побачити розбір.</p></div>`;
    }
    const bestDiffers = r.uci !== r.bestUci;
    return `<div class="detail"><h3><i class="mk ${r.class}">${r.mark}</i>${Math.ceil(r.ply / 2)}${r.ply % 2 ? '.' : '…'} ${esc(r.san)} – ${r.className}<span class="score">${r.scoreText}</span></h3>
      ${bestDiffers ? `<p>Найкраще: <b>${esc(r.best)}</b> (${r.bestScoreText}) <span class="pv">${esc(r.bestLine)}</span></p>` : ''}
      <ul>${r.facts.map(f => `<li>${esc(f)}</li>`).join('')}</ul>
      <div class="explain" id="explain-${r.ply}">${this.explained?.(r.ply) ?? ''}</div>
      <p class="dim">Глибина оцінки: ${r.depth} півходів.${d.summary ? ' <button class="link" data-go="0">До ключових моментів</button>' : ''}</p></div>`;
  }
}
