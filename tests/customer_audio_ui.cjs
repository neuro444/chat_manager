// Run: node tests/customer_audio_ui.cjs
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.isConnected = true; }
  appendChild(x) { this.children.push(x); return x; }
  append(...xs) { this.children.push(...xs); }
  setAttribute() {}
  remove() { this.removed = true; }
}
const source = fs.readFileSync(require('node:path').join(__dirname, '../web/app.js'), 'utf8');
const start = source.indexOf('function addCustomerAudio(');
const end = source.indexOf('function bubble(', start);
let requestPath;
const context = {
  document: { createElement: (tag) => new Element(tag) }, state: {session:'call-one'},
  customerAudioUrls: [], URL: { createObjectURL: () => 'blob:test' },
  api: async (path) => { requestPath = path; return {blob:async () => ({})}; },
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
(async () => {
  const node = new Element('div');
  context.addCustomerAudio(node, {id:'clip-one',duration_seconds:1.2,complete:true,expires_at:Date.now()/1000+60}, 'call-one');
  const panel = node.children[0];
  const button = panel.children[1];
  await button.onclick();
  assert.equal(requestPath, '/sessions/call-one/audio/clip-one');
  const player = panel.children.find(x => x.tag === 'audio');
  assert.equal(player.controls, true);
  assert.equal(player.src, 'blob:test');
  assert.equal(panel.children.find(x => x.tag === 'a').download, 'clip-one.wav');
  assert.equal(button.removed, true);
  const old = new Element('div');
  context.addCustomerAudio(old, null, 'call-one');
  assert.equal(old.children[0].children[0].textContent, 'Customer audio: not recorded');
  const expired = new Element('div');
  context.addCustomerAudio(expired, {id:'old',expires_at:0}, 'call-one');
  assert.equal(expired.children[0].children[0].textContent, 'Customer audio: expired');
  console.log('Customer audio UI interaction checks passed');
})().catch(error => { console.error(error); process.exit(1); });
