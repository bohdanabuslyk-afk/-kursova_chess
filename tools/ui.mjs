// Спільні дії для сценаріїв знімків: ходи мишкою, нова партія.
import { open, sleep } from './shot.mjs';
export { sleep };

export async function start(opts) {
  const p = await open('http://127.0.0.1:8000/', opts);
  const sq = async s => {
    const [x, y, w, f] = await p.js(`(()=>{const r=document.querySelector('.squares').getBoundingClientRect();return [r.x,r.y,r.width,document.querySelector('.sq .rank').textContent==='1']})()`);
    const c = 'abcdefgh'.indexOf(s[0]), r = 8 - +s[1], u = w / 8;
    return [x + ((f ? 7 - c : c) + .5) * u, y + ((f ? 7 - r : r) + .5) * u];
  };
  const idle = async () => { await sleep(350); await p.until(`!document.querySelector('.think')`, 90000); await sleep(350); };
  return {
    ...p, sq, idle,
    move: async (a, b) => { await p.drag(await sq(a), await sq(b)); await idle(); },
    clickSq: async s => p.clickAt(...await sq(s)),
    newGame: async ({ color = 'white', opponent = 'engine', level = 3 }, shot) => {
      await p.click('#btn-new'); await sleep(250);
      for (const [n, v] of Object.entries({ opponent, color, level })) {
        await p.js(`(()=>{const e=document.querySelector('[name=${n}][value="${v}"]');e.checked=true;e.dispatchEvent(new Event('change',{bubbles:true}))})()`);
      }
      await sleep(200);
      if (shot) await p.shot(shot);
      await p.click('#form-new .primary'); await idle();
    },
    importPgn: async pgn => {
      await p.click('#btn-archive'); await sleep(500);
      await p.js(`document.getElementById('pgn-text').value=${JSON.stringify(pgn)}`);
      await p.click('#do-import'); await sleep(700);
    },
    sans: () => p.js(`[...document.querySelectorAll('.moves [data-ply]')].map(b=>b.textContent.trim()).join(' ')`),
  };
}

// «Вічнозелена партія» (Андерсен – Дюфрен, 1852): суспільне надбання, зручний приклад для аналізу.
export const EVERGREEN = '1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. b4 Bxb4 5. c3 Ba5 6. d4 exd4 7. O-O d3 8. Qb3 Qf6 9. e5 Qg6 10. Re1 Nge7 11. Ba3 b5 12. Qxb5 Rb8 13. Qa4 Bb6 14. Nbd2 Bb7 15. Ne4 Qf5 16. Bxd3 Qh5 17. Nf6+ gxf6 18. exf6 Rg8 19. Rad1 Qxf3 20. Rxe7+ Nxe7 21. Qxd7+ Kxd7 22. Bf5+ Ke8 23. Bd7+ Kf8 24. Bxe7# 1-0';
