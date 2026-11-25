// Потрібні: сервер без моделі на 8000, сервер із заглушкою на 8001 (див. tools/demo.sh).
import { start, sleep } from './ui.mjs';

const D = 'screenshots/06_v0.6_movna_model/';
let u = await start();
await u.newGame({ color: 'white', level: 3 }, D + '01_bez_modeli_vybir_supernyka.png');
for (const [a, b] of [['e2', 'e4'], ['d1', 'h5'], ['h5', 'f7']]) await u.move(a, b);
await u.click('[data-tab=coach]'); await sleep(300);
await u.shot(D + '02_bez_modeli_trener.png');
await u.click('[data-tab=analysis]'); await sleep(300);
await u.click('[data-speed=fast]'); await u.until(`!!document.querySelector('.accs')`, 60000);
await u.js(`document.querySelector('.moves [data-ply="5"]').click()`); await sleep(400);
await u.click('[data-explain]'); await u.until(`!!document.querySelector('blockquote')`); await sleep(300);
await u.shot(D + '03_bez_modeli_shablonne_poiasnennia.png');
console.log('помилки JS (без моделі):', u.errors); await u.close();

u = await start({ port: 8001 });
await u.newGame({ color: 'white', opponent: 'llm', level: 2 }, D + '04_zahlushka_vybir_supernyka.png');
for (const [a, b] of [['e2', 'e4'], ['g1', 'f3']]) await u.move(a, b);
await u.shot(D + '05_zahlushka_vidkhylenyi_khid_i_povtor.png');
console.log('інфо:', await u.js(`document.getElementById('info').textContent`));
await u.click('[data-tab=coach]'); await sleep(300);
await u.click('[data-q]'); await u.until(`document.querySelectorAll('.bubble').length>1 && !document.querySelector('.bubble.dim')`, 30000); await sleep(300);
await u.shot(D + '06_zahlushka_trener_chat.png');
await u.click('[data-tab=analysis]'); await sleep(300);
await u.click('[data-speed=fast]'); await u.until(`!!document.querySelector('.accs')`, 60000);
await u.js(`document.querySelector('.moves [data-ply="4"]').click()`); await sleep(400);
await u.click('[data-explain]'); await u.until(`!!document.querySelector('blockquote')`); await sleep(300);
await u.shot(D + '07_zahlushka_poiasnennia.png');
console.log('помилки JS (заглушка):', u.errors); await u.close();
