// Вкладка «Тренер»: запитання до мовної моделі про поточну позицію.
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const QUICK = ['Який у мене план?', 'Чи є загрози?', 'Оціни позицію', 'Що то за дебют?'];

export class Coach {
  constructor(root, { api, game, status }) {
    Object.assign(this, { root, api, game, status, log: [], id: null, wait: false });
    root.addEventListener('submit', e => { e.preventDefault(); this.send(e.target.elements.q.value); });
    root.addEventListener('click', e => { const b = e.target.closest('[data-q]'); if (b) this.send(b.dataset.q); });
  }

  open(id) { if (id !== this.id) { this.id = id; this.log = []; this.wait = false; this.render(); } }

  render() {
    if (!this.status().ready) {
      this.root.innerHTML = `<div class="note"><p><b>Мовну модель не підключено.</b></p>
        <p>Скопіюйте <code>.env.example</code> у <code>.env</code>, впишіть адресу, ключ і назву моделі та перезапустіть сервер. Без інтернету підійде локальна Ollama.</p>
        <p>Гра, рушій, запис і аналіз ходів працюють і без моделі; пояснення ходів формуються за шаблоном.</p></div>`;
      return;
    }
    const msgs = this.log.map(m => `<div class="bubble ${m.role}">${esc(m.content)}</div>`).join('');
    this.root.innerHTML = `<div class="chatlog">${msgs || '<p class="note">Запитайте тренера про поточну позицію.</p>'}${this.wait ? '<div class="bubble assistant dim">Думаю…</div>' : ''}</div>
      <div class="chips pad">${QUICK.map(q => `<button class="chip plain" data-q="${q}">${q}</button>`).join('')}</div>
      <form class="entry"><input name="q" placeholder="Ваше запитання" autocomplete="off" maxlength="500" aria-label="Запитання тренеру"><button class="btn primary" ${this.wait ? 'disabled' : ''}>Надіслати</button></form>
      <p class="modelname">Модель: ${esc(this.status().model)}. Вона може помилятися.</p>`;
    const box = this.root.querySelector('.chatlog');
    box.scrollTop = box.scrollHeight;
  }

  async send(question) {
    question = question.trim();
    if (!question || this.wait) return;
    const id = this.id;
    this.log.push({ role: 'user', content: question });
    this.wait = true; this.render();
    let msg;
    try { msg = { role: 'assistant', content: (await this.api(`/api/games/${id}/chat`, { question })).answer }; }
    catch (e) { msg = { role: 'error', content: e.message }; }
    if (id !== this.id) return;
    this.wait = false; this.log.push(msg); this.render();
    this.root.querySelector('input')?.focus();
  }
}
