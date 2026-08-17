// cdp-run.mjs <file.html> <out.png> [--keys] — load a page in headless Chrome via CDP,
// run in real time, optionally simulate a key sequence, collect console errors, screenshot.
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { writeFile } from 'node:fs/promises';

const [,, htmlPath, outPng, ...flags] = process.argv;
const doKeys = flags.includes('--keys'); const soak = flags.includes('--soak'); const observe = flags.includes('--observe'); const clear = flags.includes('--clear');
const wait = ms => new Promise(r => setTimeout(r, ms));
const port = 9300 + Math.floor(Math.random() * 500);
const chrome = spawn('google-chrome', ['--headless=new', '--disable-gpu', '--no-sandbox', '--allow-file-access-from-files',
  '--hide-scrollbars', '--window-size=500,580', `--remote-debugging-port=${port}`, '--user-data-dir=/tmp/validate/chrome-profile-' + port, 'about:blank'],
  { stdio: 'ignore' });
let wsUrl;
for (let i = 0; i < 50 && !wsUrl; i++) {
  try { const r = await fetch(`http://127.0.0.1:${port}/json`); const t = await r.json(); wsUrl = t.find(x => x.type === 'page')?.webSocketDebuggerUrl; } catch { await wait(200); }
}
if (!wsUrl) { console.log('RESULT: could not attach to chrome'); chrome.kill(); process.exit(1); }
const ws = new WebSocket(wsUrl);
await new Promise(r => ws.onopen = r);
let id = 0; const pending = new Map(); const errors = []; const logs = [];
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === 'Runtime.exceptionThrown') errors.push((m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text).split('\n').slice(0,2).join(' ').replace(/file:\/\/\S*\//g,''));
  if (m.method === 'Runtime.consoleAPICalled' && (m.params.type === 'error' || m.params.type === 'warning')) errors.push(m.params.args.map(a => a.value ?? a.description).join(' '));
  if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'log') logs.push(m.params.args.map(a => a.value ?? a.description).join(' '));
};
const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
await send('Runtime.enable'); await send('Page.enable'); await send('Emulation.setDeviceMetricsOverride', { width: 500, height: 580, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: 'file://' + htmlPath });
await wait(800);
const key = async (k, code, kc, type) => {
  const base = { key: k, code, windowsVirtualKeyCode: kc, nativeVirtualKeyCode: kc };
  if (type !== 'up') await send('Input.dispatchKeyEvent', { type: k.length === 1 ? 'keyDown' : 'rawKeyDown', ...base, text: k.length === 1 ? k : undefined });
  if (!type) await wait(90);
  if (type !== 'down') await send('Input.dispatchKeyEvent', { type: 'keyUp', ...base });
};
const sample = async () => (await send('Runtime.evaluate', { returnByValue: true, expression: `(() => { const c = document.querySelector('canvas'); if (!c) return null;
  const ctx = c.getContext('2d'); const d = ctx.getImageData(0,0,c.width,c.height).data; let n=0,sx=0,sy=0; const top = Math.floor(c.height*0.6);
  for (let y=40;y<top;y++) for (let x=0;x<c.width;x++){ const i=(y*c.width+x)*4; if (d[i]+d[i+1]+d[i+2]>60){n++;sx+=x;sy+=y;} }
  return {upperLit:n, cx: n?Math.round(sx/n):null, cy: n?Math.round(sy/n):null}; })()` })).result?.result?.value;
const killAll = async () => (await send('Runtime.evaluate', { returnByValue: true, expression: `(() => { let n=0; const seen=new Set();
  const walk = (o,depth) => { if (!o||typeof o!=='object'||seen.has(o)||depth>4) return; seen.add(o);
    if (Array.isArray(o)) { for (const e of o) { if (e&&typeof e==='object'&&'alive' in e&&e.alive) { e.alive=false; n++; } else walk(e,depth+1); } }
    else for (const k of Object.keys(o)) { if (['alive','live','aliveCount','liveCount','remaining','invadersLeft','count'].includes(k) && typeof o[k]==='number' && o[k]>0) { o[k]=0; n+=1000; } else walk(o[k],depth+1); } };
  for (const name of ['state','game','G','invaders','aliens','enemies']) { try { walk(window[name]??eval(name),0); } catch(e){} }
  return n; })()` })).result?.result?.value;
let observations = {};
if (observe) {
  const a = await sample(); await wait(1200); const b = await sample(); await wait(1200); const c = await sample();
  observations = { onLoad: a, t2: b, t3: c };
} else if (clear) {
  await key('Enter','Enter',13); await wait(800); const before = await sample(); const killed = await killAll(); await wait(7000); const after = await sample();
  observations = { before, killed, after };
} else if (doKeys) {
  await key('Enter', 'Enter', 13); await wait(300);
  await key('ArrowRight', 'ArrowRight', 39, 'down'); await wait(900); await key('ArrowRight', 'ArrowRight', 39, 'up');
  await key(' ', 'Space', 32); await wait(100);
  await key('ArrowLeft', 'ArrowLeft', 37, 'down'); await wait(400); await key('ArrowLeft', 'ArrowLeft', 37, 'up');
  await wait(50);
} else if (soak) {
  await key('Enter', 'Enter', 13); await wait(200);
  const t0 = Date.now(); let dir = 1;
  while (Date.now() - t0 < 15000) {
    const k = dir > 0 ? ['ArrowRight','ArrowRight',39] : ['ArrowLeft','ArrowLeft',37];
    await key(...k, 'down'); await wait(350); await key(...k, 'up');
    await key(' ', 'Space', 32); await wait(120);
    if (Math.random() < 0.35) dir = -dir;
  }
} else { await wait(1500); }
// pixel-level check: how much of the canvas is non-black
const probe = await send('Runtime.evaluate', { returnByValue: true, expression: `(() => { const c = document.querySelector('canvas'); if (!c) return {canvas:false};
  const ctx = c.getContext('2d'); const d = ctx.getImageData(0,0,c.width,c.height).data; let lit = 0, colors = new Set();
  for (let i = 0; i < d.length; i += 4) { if (d[i]+d[i+1]+d[i+2] > 60) { lit++; if (colors.size < 12) colors.add(d[i]+','+d[i+1]+','+d[i+2]); } }
  return {canvas:true, w:c.width, h:c.height, litPixels: lit, colors:[...colors]}; })()` });
const shot = await send('Page.captureScreenshot', { format: 'png' });
await writeFile(outPng, Buffer.from(shot.result.data, 'base64'));
console.log('RESULT:', JSON.stringify({ observations, probe: probe.result?.result?.value ?? probe.result?.exceptionDetails?.exception?.description, errors: [...new Set(errors)].slice(0, 6), logs: logs.slice(0, 4) }));
ws.close(); chrome.kill('SIGKILL');
