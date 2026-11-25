// Компонент шахової дошки: малювання, перетягування, «клік–клік», перетворення пішака.
const FILES = 'abcdefgh';
const NAMES = { p: 'пішак', n: 'кінь', b: 'слон', r: 'тура', q: 'ферзь', k: 'король' };

export function parseFen(fen) {
  const map = {};
  fen.split(' ')[0].split('/').forEach((row, r) => {
    let c = 0;
    for (const ch of row) {
      if (+ch) { c += +ch; continue; }
      map[FILES[c] + (8 - r)] = (ch === ch.toLowerCase() ? 'b' : 'w') + ch.toLowerCase();
      c++;
    }
  });
  return map;
}

export class Board {
  /** onMove(uci) викликається, коли користувач зробив хід на дошці. */
  constructor(root, onMove) {
    this.root = root;
    this.onMove = onMove;
    this.flipped = false;
    this.pieces = {};       // поле -> код фігури
    this.nodes = {};        // поле -> DOM-елемент фігури
    this.legal = {};
    this.selected = null;
    this.drag = null;
    root.classList.add('board');
    root.innerHTML = '<div class="squares"></div><svg class="arrows" viewBox="0 0 8 8"></svg><div class="pieces"></div>';
    [this.squaresEl, this.arrowsEl, this.piecesEl] = root.children;
    root.addEventListener('pointerdown', e => this.down(e));
    root.addEventListener('pointermove', e => this.move(e));
    root.addEventListener('pointerup', e => this.up(e));
    root.addEventListener('pointercancel', () => this.cancel());
    root.addEventListener('contextmenu', e => { e.preventDefault(); this.cancel(); });
    this.buildSquares();
  }

  buildSquares() {
    this.squares = {};
    this.squaresEl.innerHTML = '';
    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
      const sq = this.flipped ? FILES[7 - c] + (r + 1) : FILES[c] + (8 - r);
      const el = document.createElement('div');
      el.className = 'sq ' + ((r + c) % 2 ? 'dark' : 'light');
      if (c === 0) el.insertAdjacentHTML('beforeend', `<i class="rank">${sq[1]}</i>`);
      if (r === 7) el.insertAdjacentHTML('beforeend', `<i class="file">${sq[0]}</i>`);
      this.squares[sq] = el;
      this.squaresEl.append(el);
    }
  }

  xy(sq) {
    const f = FILES.indexOf(sq[0]), r = 8 - +sq[1];
    return this.flipped ? [7 - f, 7 - r] : [f, r];
  }

  place(node, sq) {
    const [x, y] = this.xy(sq);
    node.style.transform = `translate(${x * 100}%, ${y * 100}%)`;
  }

  setFlipped(v) {
    if (this.flipped === v) return;
    this.flipped = v;
    this.buildSquares();
    for (const sq in this.nodes) this.place(this.nodes[sq], sq);
    this.paint();
  }

  /** Показати позицію. last – хід uci, check – поле короля під шахом, legal – дозволені ходи. */
  set({ fen, legal = {}, last = null, check = null, badge = null }) {
    this.cancel();
    this.legal = legal; this.last = last; this.check = check; this.badge = badge;
    const next = parseFen(fen), keep = {}, free = [];
    for (const sq in this.nodes) {
      if (next[sq] === this.pieces[sq]) keep[sq] = this.nodes[sq]; else free.push(sq);
    }
    const need = Object.keys(next).filter(sq => !keep[sq]);
    // Спершу пара «звідки–куди» останнього ходу, щоб анімувалася саме та фігура.
    if (last) need.sort((a, b) => (b === last.slice(2, 4)) - (a === last.slice(2, 4)));
    for (const sq of need) {
      const from = (last && sq === last.slice(2, 4) && free.includes(last.slice(0, 2)) && this.pieces[last.slice(0, 2)] === next[sq])
        ? last.slice(0, 2) : free.find(f => this.pieces[f] === next[sq]);
      let node;
      if (from) { node = this.nodes[from]; free.splice(free.indexOf(from), 1); }
      else {
        node = document.createElement('img');
        node.className = 'piece'; node.draggable = false;
        node.src = `/pieces/${next[sq]}.svg`; node.alt = NAMES[next[sq][1]];
        this.piecesEl.append(node);
      }
      keep[sq] = node;
      this.place(node, sq);
    }
    free.forEach(sq => this.nodes[sq].remove());
    this.nodes = keep; this.pieces = next;
    this.paint();
  }

  paint() {
    for (const sq in this.squares) {
      const c = this.squares[sq].classList;
      c.toggle('last', !!this.last && (sq === this.last.slice(0, 2) || sq === this.last.slice(2, 4)));
      c.toggle('check', sq === this.check);
      c.toggle('selected', sq === this.selected);
      const target = this.selected && (this.legal[this.selected] || []).includes(sq);
      c.toggle('target', !!target && !this.pieces[sq]);
      c.toggle('capture', !!target && !!this.pieces[sq]);
      c.toggle('movable', !!this.legal[sq]);
    }
    this.root.querySelector('.badge')?.remove();
    if (this.badge && this.last) {
      const b = document.createElement('div');
      b.className = 'badge ' + this.badge.cls; b.textContent = this.badge.text;
      const [x, y] = this.xy(this.last.slice(2, 4));
      b.style.left = `${(x + 1) * 12.5}%`; b.style.top = `${y * 12.5}%`;
      this.root.append(b);
    }
    this.drawArrows();
  }

  setArrows(list) { this.arrows = list; this.drawArrows(); }

  drawArrows() {
    this.arrowsEl.innerHTML = (this.arrows || []).map(({ uci, cls }) => {
      const [x1, y1] = this.xy(uci.slice(0, 2)), [x2, y2] = this.xy(uci.slice(2, 4));
      const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy), ux = dx / len, uy = dy / len;
      const ex = x2 + .5 - ux * .22, ey = y2 + .5 - uy * .22, bx = ex - ux * .34, by = ey - uy * .34;
      return `<g class="${cls}"><line x1="${x1 + .5 + ux * .3}" y1="${y1 + .5 + uy * .3}" x2="${bx}" y2="${by}"/>` +
        `<polygon points="${ex},${ey} ${bx - uy * .22},${by + ux * .22} ${bx + uy * .22},${by - ux * .22}"/></g>`;
    }).join('');
  }

  squareAt(e) {
    const b = this.squaresEl.getBoundingClientRect();
    const x = Math.floor((e.clientX - b.left) / b.width * 8), y = Math.floor((e.clientY - b.top) / b.height * 8);
    if (x < 0 || x > 7 || y < 0 || y > 7) return null;
    return this.flipped ? FILES[7 - x] + (y + 1) : FILES[x] + (8 - y);
  }

  down(e) {
    if (e.button !== 0 || e.target.closest('.promo')) return;
    if (this.root.querySelector('.promo')) { this.cancel(); return; }
    const sq = this.squareAt(e);
    if (!sq) return;
    if (this.selected && (this.legal[this.selected] || []).includes(sq)) { this.tryMove(this.selected, sq); return; }
    if (!this.legal[sq]) { this.cancel(); return; }
    const wasSelected = this.selected === sq;
    this.selected = sq;
    this.drag = { sq, node: this.nodes[sq], x: e.clientX, y: e.clientY, moved: false, wasSelected };
    this.root.setPointerCapture(e.pointerId);
    this.paint();
  }

  move(e) {
    const d = this.drag;
    if (!d) return;
    if (!d.moved && Math.hypot(e.clientX - d.x, e.clientY - d.y) < 4) return;
    d.moved = true;
    const b = this.squaresEl.getBoundingClientRect(), s = b.width / 8;
    d.node.classList.add('dragging');
    d.node.style.transform = `translate(${e.clientX - b.left - s / 2}px, ${e.clientY - b.top - s / 2}px)`;
    const over = this.squareAt(e);
    for (const q in this.squares) this.squares[q].classList.toggle('hover', q === over && (this.legal[d.sq] || []).includes(q));
  }

  up(e) {
    const d = this.drag;
    if (!d) return;
    this.drag = null;
    d.node.classList.remove('dragging');
    this.clearHover();
    const sq = this.squareAt(e);
    if (!d.moved) { if (d.wasSelected) this.cancel(); return; }
    if (sq && (this.legal[d.sq] || []).includes(sq)) this.tryMove(d.sq, sq);
    else { this.place(d.node, d.sq); this.selected = null; this.paint(); }
  }

  clearHover() { for (const q in this.squares) this.squares[q].classList.remove('hover'); }

  cancel() {
    this.root.querySelector('.promo')?.remove();
    if (this.drag) { this.drag.node.classList.remove('dragging'); this.drag = null; this.clearHover(); }
    for (const sq in this.nodes) this.place(this.nodes[sq], sq);
    if (this.selected) { this.selected = null; this.paint(); }
  }

  tryMove(from, to) {
    const p = this.pieces[from];
    this.selected = null; this.paint();
    if (p[1] === 'p' && (to[1] === '8' || to[1] === '1')) { this.place(this.nodes[from], to); this.askPromotion(from, to, p[0]); }
    else { this.place(this.nodes[from], to); this.onMove(from + to); }
  }

  askPromotion(from, to, color) {
    const box = document.createElement('div');
    box.className = 'promo';
    const [x, y] = this.xy(to);
    box.style.left = `${x * 12.5}%`;
    box.style[y === 0 ? 'top' : 'bottom'] = '0';
    for (const k of y === 0 ? 'qrbn' : 'nbrq') {
      const btn = document.createElement('button');
      btn.type = 'button'; btn.title = NAMES[k]; btn.dataset.piece = k;
      btn.innerHTML = `<img src="/pieces/${color}${k}.svg" alt="${NAMES[k]}">`;
      btn.onclick = () => { box.remove(); this.onMove(from + to + k); };
      box.append(btn);
    }
    this.root.append(box);
  }
}
