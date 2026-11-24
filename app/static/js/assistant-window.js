/* 小助手入口位置、置中視窗與鍵盤操作；不改提問及待辦資料流程。 */
document.querySelectorAll('[data-assistant]').forEach((root) => {
  const launcher = root.querySelector('.assistant__toggle');
  const panel = root.querySelector('.assistant__panel');
  const overlay = root.querySelector('[data-assistant-overlay]');
  if (!launcher || !panel || !overlay) return;
  const key = `assistant-position:${root.dataset.user || ''}`;
  let position = { side: 'right', y: 1 }, drag = null, suppressClick = false;
  let inertBefore = [], shown = false;
  try {
    const saved = JSON.parse(localStorage.getItem(key) || 'null');
    if (saved && ['left', 'right'].includes(saved.side) && Number.isFinite(saved.y)) {
      position = { side: saved.side, y: Math.min(1, Math.max(0, saved.y)) };
    }
  } catch (_) { /* 儲存不可用時保留預設位置。 */ }
  const save = () => { try { localStorage.setItem(key, JSON.stringify(position)); } catch (_) {} };
  const bounds = () => {
    const header = document.querySelector('.masthead');
    const tabs = document.querySelector('.sv2-tabbar');
    const tabRect = tabs && tabs.getBoundingClientRect();
    const sidebar = header?.classList.contains('masthead--admin') && matchMedia('(min-width: 961px)').matches;
    const bottom = tabRect && getComputedStyle(tabs).display !== 'none' ? tabRect.top - 12 : innerHeight - 16;
    const max = Math.max(12, bottom - launcher.offsetHeight);
    const headerBottom = header && !sidebar ? header.getBoundingClientRect().bottom + 12 : 12;
    const top = Math.min(max, Math.max(12, headerBottom));
    return { top, max, width: launcher.offsetWidth };
  };
  const place = () => {
    const b = bounds();
    const left = position.side === 'left' ? 12 : Math.max(12, innerWidth - b.width - 12);
    Object.assign(launcher.style, { left: `${left}px`, right: 'auto', top: `${b.top + position.y * (b.max - b.top)}px`, bottom: 'auto' });
  };
  const viewport = () => {
    const v = window.visualViewport;
    overlay.style.setProperty('--as-vh', `${v ? v.height : innerHeight}px`);
    overlay.style.setProperty('--as-vw', `${v ? v.width : innerWidth}px`);
    overlay.style.setProperty('--as-top', `${v ? v.offsetTop : 0}px`);
    overlay.style.setProperty('--as-left', `${v ? v.offsetLeft : 0}px`);
    if (!drag && !root.classList.contains('is-open')) place();
  };
  launcher.style.touchAction = 'none';
  launcher.addEventListener('pointerdown', (event) => {
    if (!event.isPrimary || event.button > 0) return;
    const rect = launcher.getBoundingClientRect();
    drag = { id: event.pointerId, sx: event.clientX, sy: event.clientY, x: rect.left, y: rect.top, moved: false };
    launcher.setPointerCapture(event.pointerId);
  });
  launcher.addEventListener('pointermove', (event) => {
    if (!drag || drag.id !== event.pointerId) return;
    const dx = event.clientX - drag.sx, dy = event.clientY - drag.sy;
    if (!drag.moved && Math.hypot(dx, dy) < 8) return;
    drag.moved = true;
    const b = bounds();
    launcher.style.left = `${Math.max(12, Math.min(innerWidth - b.width - 12, drag.x + dx))}px`;
    launcher.style.top = `${Math.max(b.top, Math.min(b.max, drag.y + dy))}px`;
  });
  const release = (event) => {
    if (!drag || drag.id !== event.pointerId) return;
    if (drag.moved) {
      suppressClick = true;
      const b = bounds(), rect = launcher.getBoundingClientRect();
      position = { side: rect.left + rect.width / 2 < innerWidth / 2 ? 'left' : 'right', y: (rect.top - b.top) / Math.max(1, b.max - b.top) };
      save(); place();
      setTimeout(() => { suppressClick = false; }, 0);
    }
    drag = null;
  };
  launcher.addEventListener('pointerup', release);
  launcher.addEventListener('pointercancel', release);
  launcher.addEventListener('click', (event) => {
    if (suppressClick) { event.preventDefault(); event.stopImmediatePropagation(); suppressClick = false; }
  }, true);
  root.querySelector('[data-assistant-reset]').addEventListener('click', () => {
    position = { side: 'right', y: 1 }; save();
    root.dispatchEvent(new CustomEvent('assistant-set-open', { detail: false }));
  });
  const expand = root.querySelector('[data-assistant-expand]');
  expand.addEventListener('click', () => {
    const enlarged = root.classList.toggle('is-enlarged');
    expand.setAttribute('aria-pressed', String(enlarged));
    expand.setAttribute('aria-label', enlarged ? '還原視窗' : '放大視窗');
    expand.title = enlarged ? '還原視窗' : '放大視窗';
  });
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) root.dispatchEvent(new CustomEvent('assistant-set-open', { detail: false }));
  });
  root.addEventListener('assistant-visibility', (event) => {
    const open = Boolean(event.detail);
    // 已開啟時再收到開啟（例如點建議問題）不可重記背景狀態，否則關閉後整頁會一直無法操作。
    if (open === shown) return;
    shown = open;
    overlay.hidden = !open;
    if (open) {
      inertBefore = [...document.body.children].filter(e => e !== root && !e.contains(root) && !['SCRIPT', 'STYLE', 'LINK'].includes(e.tagName)).map(e => [e, e.inert]);
      inertBefore.forEach(([e]) => { e.inert = true; });
      viewport();
      root.querySelector('textarea').focus({ preventScroll: true });
    } else {
      inertBefore.forEach(([e, value]) => { e.inert = value; }); inertBefore = [];
      place();
      // Safari 點按鈕不會給焦點；只要焦點留在視窗內或掉到頁面本體，就交回入口。
      const active = document.activeElement;
      if (!active || active === document.body || root.contains(active)) launcher.focus({ preventScroll: true });
    }
  });
  panel.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab') return;
    const items = [...panel.querySelectorAll('a[href], button, summary, textarea, input:not([type=hidden])')].filter(e => !e.disabled && e.getClientRects().length);
    if (!items.length) { event.preventDefault(); panel.focus(); return; }
    const first = items[0], last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  addEventListener('resize', viewport);
  // 學生端手機底部導覽由 student-v2.js 產生，它比這支晚執行；頁面載完再放一次，入口才不會蓋住「我的待辦」（2026-11-18）
  document.addEventListener('DOMContentLoaded', viewport);
  addEventListener('load', viewport);
  if (window.visualViewport) { window.visualViewport.addEventListener('resize', viewport); window.visualViewport.addEventListener('scroll', viewport); }
  viewport();
});
