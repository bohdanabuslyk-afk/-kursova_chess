import { open, sleep } from './shot.mjs';

const p = await open('http://127.0.0.1:8000/', { width: 900, height: 960 });
const D = 'screenshots/03_v0.3_rushii_skladnist_kolir/';
await p.shot(D + '01_vybir_koloru_ta_skladnosti.png');
const mine = `/\\(ви\\)|Кінець/.test(document.getElementById('status').textContent)`;
const play = async m => {
  await p.js(`document.getElementById('m').value='${m}';document.getElementById('f').requestSubmit()`);
  await sleep(400); await p.until(mine);
};
await p.js(`document.getElementById('level').value='5'`); await p.click('#new button'); await sleep(600);
for (const m of ['e2e4', 'g1f3', 'd2d4']) await play(m);
await sleep(300);
await p.shot(D + '02_hra_bilymy_ekspert.png');
await p.js(`document.getElementById('color').value='black';document.getElementById('level').value='4'`);
await p.click('#new button'); await sleep(600); await p.until(mine); await sleep(400);
await p.shot(D + '03_hra_chornymy_kompiuter_pershyi.png');
console.log('помилки JS:', p.errors);
await p.close();
