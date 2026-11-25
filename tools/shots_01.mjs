import { open, sleep } from './shot.mjs';

const p = await open('http://127.0.0.1:8000/', { width: 800, height: 800 });
const D = 'screenshots/01_v0.1_yadro_tekstovyi_vvid/';
await p.shot(D + '01_pochatkova_pozytsiia.png');
for (const m of ['e2e4', 'e5', 'Nf3']) { await p.click('#m'); await p.type(m); await p.enter(); await sleep(400); }
await p.shot(D + '02_khody_tekstom.png');
await p.click('#m'); await p.type('Ke7e5'); await p.enter(); await sleep(400);
await p.shot(D + '03_nelehalnyi_khid.png');
console.log('помилки JS:', p.errors);
await p.close();
