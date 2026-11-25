import { start, sleep, EVERGREEN } from './ui.mjs';

const D = 'screenshots/07_v1.0_finalnyi_interfeis/';
const u = await start();
const set = async (n, v) => { await u.click('#btn-settings'); await sleep(300); await u.js(`document.querySelector('#settings-box [name=${n}][value=${v}]').click()`); await sleep(200); };
const done = async () => { await u.click('#dlg-settings [data-close]'); await sleep(300); };
await u.newGame({ color: 'black', level: 3 });
await u.move('e7', 'e5');
await u.shot(D + '01_hra_chornymy.png');

await u.importPgn(EVERGREEN);
await u.click('#finish-analyse');
await u.until(`!!document.querySelector('.accs')`, 180000); await sleep(400);
await u.click('[data-tab=game]'); await u.js(`document.querySelector('.moves [data-ply="33"]').click()`); await sleep(500);
await u.shot(D + '02_svitla_tema_zapys_z_otsinkamy.png');
await u.click('[data-tab=analysis]'); await sleep(400);
await u.shot(D + '03_svitla_tema_analiz.png');
await set('theme', 'dark');
await u.shot(D + '04_vikno_oformlennia.png');
await done();
await u.shot(D + '05_temna_tema_analiz.png');
await set('theme', 'light'); await set('board', 'walnut'); await done();
await u.click('[data-tab=game]'); await sleep(300);
await u.shot(D + '06_doshka_horikh.png');
await set('board', 'lake'); await done();
await u.shot(D + '07_doshka_ozero.png');
await set('board', 'sage'); await done();
console.log('прокрутка сторінки 1440x900:', await u.js(`document.documentElement.scrollHeight > innerHeight`));

// мат: «дитячий» мат двома гравцями
await u.newGame({ opponent: 'human' });
for (const [a, b] of [['e2', 'e4'], ['e7', 'e5'], ['f1', 'c4'], ['b8', 'c6'], ['d1', 'h5'], ['g8', 'f6'], ['h5', 'f7']]) await u.move(a, b);
await sleep(300);
await u.shot(D + '08_mat_kinets_partii.png');
console.log('фінал:', await u.js(`document.getElementById('status').textContent`));

for (const [w, h, name] of [[1920, 1080, '09_full_hd'], [1280, 720, '10_noutbuk_1280'], [820, 1180, '11_planshet'], [390, 844, '12_telefon']]) {
  await u.resize(w, h); await sleep(700);
  await u.shot(`${D}${name}.png`);
  console.log(name, 'горизонтальна прокрутка:', await u.js(`document.documentElement.scrollWidth > innerWidth`));
}
console.log('помилки JS:', u.errors);
await u.close();
