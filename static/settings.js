// Оформлення та звук: зберігаються в браузері.
const KEY = 'settings';
const defaults = { theme: 'auto', board: 'sage', sound: true };
export const settings = { ...defaults, ...JSON.parse(localStorage.getItem(KEY) || '{}') };

export function apply() {
  const dark = settings.theme === 'dark' || (settings.theme === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.documentElement.dataset.board = settings.board;
}
export function set(name, value) {
  settings[name] = value;
  localStorage.setItem(KEY, JSON.stringify(settings));
  apply();
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', apply);
apply();

let ctx;
function tone(freq, at, len, gain) {
  const o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime + at;
  o.type = 'triangle'; o.frequency.value = freq;
  g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(.001, t + len);
  o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + len);
}
/** Короткий звук ходу, синтезований у браузері – без звукових файлів. */
export function sound(kind) {
  if (!settings.sound) return;
  try {
    ctx ??= new AudioContext();
    if (ctx.state === 'suspended') return void ctx.resume();
    if (kind === 'end') { tone(392, 0, .25, .2); tone(523, .14, .4, .2); }
    else if (kind === 'check') { tone(660, 0, .12, .2); tone(880, .07, .14, .15); }
    else if (kind === 'capture') { tone(170, 0, .1, .4); tone(120, .03, .12, .3); }
    else tone(240, 0, .09, .3);
  } catch { /* без звуку гра працює так само */ }
}
