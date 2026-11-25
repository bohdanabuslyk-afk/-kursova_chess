// Керування Microsoft Edge (headless) через DevTools Protocol без сторонніх пакетів.
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
export const sleep = ms => new Promise(r => setTimeout(r, ms));

export async function open(url, { width = 1440, height = 900, scale = 1 } = {}) {
  const port = 9300 + Math.floor(Math.random() * 500);
  const proc = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${port}`, '--no-first-run', '--disable-gpu',
    `--user-data-dir=${mkdtempSync(join(tmpdir(), 'edge-'))}`, 'about:blank'], { stdio: 'ignore' });
  let target;
  for (let i = 0; i < 60 && !target; i++) {
    await sleep(250);
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(t => t.type === 'page'); } catch {}
  }
  if (!target) { proc.kill(); throw new Error('Edge не запустився'); }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  let id = 0;
  const wait = new Map(), errors = [];
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id) { wait.get(m.id)?.(m); wait.delete(m.id); }
    if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
    if (m.method === 'Page.javascriptDialogOpening') cdp('Page.handleJavaScriptDialog', { accept: true });
  };
  const cdp = (method, params = {}) => new Promise((res, rej) => {
    const i = ++id;
    wait.set(i, m => m.error ? rej(new Error(`${method}: ${m.error.message}`)) : res(m.result));
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  await cdp('Page.enable');
  await cdp('Runtime.enable');
  await cdp('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: scale, mobile: false });
  await cdp('Page.navigate', { url });
  await sleep(1500);

  const js = async expression => {
    const r = await cdp('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description);
    return r.result.value;
  };
  const until = async (expr, ms = 60000) => {
    for (let t = 0; t < ms; t += 200) { if (await js(expr)) return; await sleep(200); }
    throw new Error('Не дочекалися: ' + expr);
  };
  const mouse = (type, x, y, buttons = 0) => cdp('Input.dispatchMouseEvent',
    { type, x, y, button: type === 'mouseMoved' ? 'none' : 'left', buttons, clickCount: type === 'mouseMoved' ? 0 : 1 });
  const center = sel => js(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});if(!e)throw Error('no element '+${JSON.stringify(sel)});const r=e.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()`);
  const clickAt = async (x, y) => {
    await mouse('mouseMoved', x, y); await mouse('mousePressed', x, y, 1); await mouse('mouseReleased', x, y); await sleep(120);
  };
  return {
    cdp, js, until, errors, mouse, center, clickAt,
    click: async sel => {
      await js(`document.querySelector(${JSON.stringify(sel)})?.scrollIntoView({block:'nearest'})`);
      await clickAt(...await center(sel));
    },
    drag: async ([x1, y1], [x2, y2], hold) => {
      await mouse('mouseMoved', x1, y1); await mouse('mousePressed', x1, y1, 1);
      for (let i = 1; i <= 8; i++) { await mouse('mouseMoved', x1 + (x2 - x1) * i / 8, y1 + (y2 - y1) * i / 8, 1); await sleep(20); }
      if (!hold) { await mouse('mouseReleased', x2, y2); await sleep(250); }
    },
    type: text => cdp('Input.insertText', { text }),
    enter: async () => {
      const k = { key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 };
      await cdp('Input.dispatchKeyEvent', { type: 'keyDown', text: '\r', ...k });
      await cdp('Input.dispatchKeyEvent', { type: 'keyUp', ...k });
      await sleep(300);
    },
    resize: (w, h) => cdp('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: scale, mobile: w < 600 }),
    shot: async file => {
      const { data } = await cdp('Page.captureScreenshot', { format: 'png' });
      mkdirSync(dirname(file), { recursive: true });
      writeFileSync(file, Buffer.from(data, 'base64'));
      console.log('знімок', file);
    },
    close: async () => { try { await cdp('Browser.close'); } catch {} ws.close(); proc.kill(); },
  };
}
