import { open, sleep } from './shot.mjs';

const p = await open('http://127.0.0.1:8000/', { width: 800, height: 860 });
const D = 'screenshots/02_v0.2_khody_myshkoiu/';
const sq = async s => {
  const [x, y, w, f] = await p.js(`(()=>{const r=document.querySelector('.squares').getBoundingClientRect();return [r.x,r.y,r.width,document.querySelector('.sq .rank').textContent==='1']})()`);
  const c = 'abcdefgh'.indexOf(s[0]), r = 8 - +s[1], u = w / 8;
  return [x + ((f ? 7 - c : c) + .5) * u, y + ((f ? 7 - r : r) + .5) * u];
};
const click = async s => p.clickAt(...await sq(s));
const drag = async (a, b, hold) => p.drag(await sq(a), await sq(b), hold);
const moves = () => p.js(`document.getElementById('moves').textContent`);

await drag('e2', 'e4'); await sleep(400);
await click('d7'); await click('d5'); await sleep(400);
console.log('після перетягування та кліків:', await moves());
await click('e4'); await sleep(200);
await p.shot(D + '01_pidkazky_khodiv.png');
await drag('g1', 'f3', true); await sleep(200);
await p.shot(D + '02_peretiahuvannia.png');
await p.mouse('mouseReleased', ...await sq('g5')); await sleep(400); // нелегально: має повернутися
console.log('після нелегального кидка:', await moves());
for (const [a, b] of [['e4', 'd5'], ['c7', 'c6'], ['d5', 'c6'], ['g7', 'g6'], ['c6', 'b7'], ['f8', 'g7'], ['b7', 'a8']]) { await drag(a, b); await sleep(350); }
await sleep(300);
await p.shot(D + '03_vybir_figury_peretvorennia.png');
await p.click('[data-piece=n]'); await sleep(500);
console.log('після перетворення:', await moves());
await p.click('#flip'); await sleep(400);
await drag('d8', 'd2'); await sleep(400);
await p.shot(D + '04_perevernuta_doshka_shakh.png');
console.log('після шаху з перевернутої дошки:', await moves());
console.log('помилки JS:', p.errors);
await p.close();
