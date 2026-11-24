// 小助手置中視窗：背景暫停互動與焦點返回（assistant-window.js）
// 執行：node --test tests/test_assistant_window.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'js', 'assistant-window.js'), 'utf8',
);

function element(tagName, extra = {}) {
  const listeners = {};
  const classes = new Set();
  const el = {
    tagName, dataset: {}, style: { setProperty() {} }, hidden: false, inert: false,
    attributes: {}, children: [], parent: null, isConnected: true, offsetWidth: 52, offsetHeight: 52,
    classList: {
      toggle(name, on) { const v = on === undefined ? !classes.has(name) : on; if (v) classes.add(name); else classes.delete(name); return v; },
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); },
    },
    addEventListener(type, handler) { (listeners[type] ||= []).push(handler); },
    dispatchEvent(event) { (listeners[event.type] || []).forEach((h) => h(event)); return true; },
    setAttribute(key, value) { this.attributes[key] = value; },
    getAttribute(key) { return this.attributes[key] ?? null; },
    getBoundingClientRect() { return { left: 0, top: 0, bottom: 0, width: 52, height: 52 }; },
    getClientRects() { return [1]; },
    setPointerCapture() {},
    contains(other) { for (let n = other; n; n = n.parent) if (n === this) return true; return false; },
    focus() { doc.activeElement = this; },
    ...extra,
  };
  return el;
}

let doc;

function setup() {
  const body = element('BODY');
  doc = {
    body, activeElement: body,
    querySelector: () => null,
    querySelectorAll: (sel) => (sel === '[data-assistant]' ? [root] : []),
  };
  const add = (parent, child) => { child.parent = parent; parent.children.push(child); return child; };
  const main = add(body, element('MAIN'));
  const header = add(body, element('HEADER'));
  const root = add(body, element('DIV'));
  root.dataset.user = '7';
  const launcher = add(root, element('BUTTON'));
  const overlay = add(root, element('DIV'));
  const panel = add(overlay, element('SECTION'));
  const textarea = add(panel, element('TEXTAREA'));
  const reset = add(panel, element('BUTTON'));
  const expand = add(panel, element('BUTTON'));
  const map = {
    '.assistant__toggle': launcher, '.assistant__panel': panel, '[data-assistant-overlay]': overlay,
    '[data-assistant-reset]': reset, '[data-assistant-expand]': expand, textarea,
  };
  root.querySelector = (sel) => map[sel] || null;
  panel.querySelectorAll = () => [textarea];
  const context = {
    document: doc, window: {}, innerWidth: 1024, innerHeight: 768,
    localStorage: { getItem: () => null, setItem() {} },
    getComputedStyle: () => ({ display: 'block' }),
    addEventListener() {}, setTimeout,
    CustomEvent: class { constructor(type, init = {}) { this.type = type; this.detail = init.detail; } },
    Number, Math, JSON, Object, String,
  };
  vm.runInNewContext(script, context);
  const show = (open) => {
    root.classList.toggle('is-open', open);
    root.dispatchEvent(new context.CustomEvent('assistant-visibility', { detail: open }));
  };
  return { root, main, header, launcher, textarea, show };
}

test('開啟中再次觸發開啟（點建議問題），關閉後背景仍可操作', () => {
  const { main, header, show } = setup();
  show(true);
  assert.equal(main.inert, true);
  show(true);
  show(false);
  assert.equal(main.inert, false);
  assert.equal(header.inert, false);
});

test('關閉時焦點在視窗內或頁面本體，都回到入口按鈕', () => {
  const { launcher, textarea, show } = setup();
  show(true);
  assert.equal(doc.activeElement, textarea);
  doc.activeElement = doc.body; // Safari 點按鈕不會給按鈕焦點；關閉按鈕隱藏後焦點也會掉到本體
  show(false);
  assert.equal(doc.activeElement, launcher);
});
