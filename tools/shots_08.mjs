// Справжня мовна модель із .env. Витрачає приблизно 8–15 запитів.
import { start, sleep } from './ui.mjs';

const D = 'screenshots/08_spravzhnia_movna_model/';
const u = await start();
console.log('модель:', await u.js(`document.getElementById('chip-model').textContent`));
await u.newGame({ color: 'white', opponent: 'llm', level: 3 }, D + '01_vybir_movnoi_modeli.png');
// Хід гравця – найкраща відповідь рушія, щоб партія була легальною за будь-якої гри моделі.
const info = () => u.js(`document.getElementById('info').innerText`);
for (let i = 0; i < 5; i++) {
  const id = await u.js(`localStorage.getItem('game')`);
  const h = await u.js(`fetch('/api/games/${id}/hint',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.json())`);
  if (h.error) break;
  await u.move(h.uci.slice(0, 2), h.uci.slice(2, 4));
  await u.until(`!document.querySelector('.think')`, 180000);
  console.log(await u.sans(), '|', (await info()).replace(/\n/g, ' / '));
  if (i === 0) await u.shot(D + '02_pershyi_khid_modeli.png');
  await sleep(4000); // щоб не перевищити ліміт запитів за хвилину
}
await u.shot(D + '03_partiia_proty_modeli.png');

await u.click('[data-tab=coach]'); await sleep(300);
await u.click('[data-q]');
await u.until(`document.querySelectorAll('.bubble').length>1 && !document.querySelector('.bubble.dim')`, 150000); await sleep(400);
await u.shot(D + '04_trener.png');
console.log('тренер:', await u.js(`[...document.querySelectorAll('.bubble')].at(-1).className+': '+[...document.querySelectorAll('.bubble')].at(-1).textContent`));

await u.click('[data-tab=analysis]'); await sleep(300);
await u.click('[data-speed=fast]'); await u.until(`!!document.querySelector('.accs')`, 120000);
const ply = await u.js(`fetch('/api/games/'+localStorage.getItem('game')+'/analysis').then(r=>r.json()).then(d=>d.rows.slice().sort((a,b)=>b.loss-a.loss)[0].ply)`);
await u.js(`document.querySelector('.moves [data-ply="${ply}"]').click()`); await sleep(400);
await u.click('[data-explain]'); await u.until(`!!document.querySelector('blockquote')`, 150000); await sleep(300);
await u.js(`document.querySelector('blockquote').scrollIntoView({block:'end'})`); await sleep(300);
await u.shot(D + '05_poiasnennia_khodu.png');
console.log('пояснення:', await u.js(`document.querySelector('.explain').innerText`));
console.log('помилки JS:', u.errors);
await u.close();
