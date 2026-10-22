// 互動元件：五年資料夾分頁、可編輯表格。

// ---------- 五年資料夾分頁 ----------
document.querySelectorAll("[data-folders]").forEach((root) => {
  const tabs = [...root.querySelectorAll('[role="tab"]')];
  const panels = [...root.querySelectorAll('[role="tabpanel"]')];

  const select = (tab, focus = false) => {
    tabs.forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
    });
    panels.forEach((p) => { p.hidden = p.id !== tab.getAttribute("aria-controls"); });
    if (focus) tab.focus();
  };

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => select(tab));
    tab.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      select(tabs[(index + step + tabs.length) % tabs.length], true);
    });
  });

  const initial = tabs.find((t) => t.dataset.initial === "true") || tabs[0];
  if (initial) select(initial);
});

// ---------- 可編輯表格：送出時轉成 JSON 給後端 ----------
document.querySelectorAll("[data-record-table]").forEach((table) => {
  const body = table.querySelector("tbody");
  const template = table.querySelector("template");
  const fields = JSON.parse(table.dataset.fields);
  const output = document.getElementById(table.dataset.output);
  const form = table.closest("form");
  const emptyRow = body.querySelector(".empty-row");

  const refreshEmpty = () => {
    if (emptyRow) emptyRow.hidden = body.querySelectorAll("tr[data-row]").length > 0;
  };

  const addRow = (values = {}) => {
    const row = template.content.firstElementChild.cloneNode(true);
    fields.forEach((name) => {
      const input = row.querySelector(`[data-field="${name}"]`);
      if (input && values[name] !== undefined && values[name] !== null) input.value = values[name];
    });
    row.querySelector("[data-remove]").addEventListener("click", () => { row.remove(); refreshEmpty(); });
    body.appendChild(row);
    refreshEmpty();
    return row;
  };

  JSON.parse(table.dataset.initial || "[]").forEach((values) => addRow(values));
  refreshEmpty();

  document.querySelectorAll(`[data-add-row="${table.id}"]`).forEach((button) => {
    button.addEventListener("click", () => {
      const row = addRow();
      const first = row.querySelector("input, select");
      if (first) first.focus();
    });
  });

  form.addEventListener("submit", () => {
    const rows = [...body.querySelectorAll("tr[data-row]")].map((row) => {
      const item = {};
      fields.forEach((name) => {
        const input = row.querySelector(`[data-field="${name}"]`);
        item[name] = input ? input.value.trim() : "";
      });
      return item;
    }).filter((item) => Object.values(item).some((value) => value !== ""));
    output.value = JSON.stringify(rows);
  });
});

// ---------- 缺件比對：容器依序裝滿、數字往上跳、點容器看細節 ----------
document.querySelectorAll("[data-gap-board]").forEach((board) => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const vessels = [...board.querySelectorAll(".vessel")];
  vessels.forEach((vessel, index) => vessel.style.setProperty("--delay", reduce ? "0s" : `${index * 0.18}s`));
  requestAnimationFrame(() => vessels.forEach((vessel) => vessel.classList.add("is-filled")));

  const panels = [...document.querySelectorAll("[data-gap-detail]")];
  const open = (vessel) => {
    vessels.forEach((v) => v.setAttribute("aria-expanded", String(v === vessel)));
    panels.forEach((panel) => { panel.hidden = panel.id !== vessel.getAttribute("aria-controls"); });
  };
  vessels.forEach((vessel) => vessel.addEventListener("click", () => open(vessel)));
  // 先打開「最需要補」的那一格：加權最大、還沒滿的項目
  const first = vessels.find((v) => v.dataset.priority === "true") || vessels[0];
  if (first) open(first);
});

document.querySelectorAll("[data-count]").forEach((el) => {
  const target = Number(el.dataset.count);
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || Number.isNaN(target)) { el.textContent = target; return; }
  const start = performance.now();
  const step = (now) => {
    const t = Math.min((now - start) / 1400, 1);
    el.textContent = Math.round(target * (1 - Math.pow(1 - t, 3)));
    if (t < 1) requestAnimationFrame(step);
  };
  el.textContent = "0";
  requestAnimationFrame(step);
});

// 佐證照片：點縮圖放大（用瀏覽器內建的 <dialog>，按 Esc、× 或點旁邊都能關）
const lightbox = document.querySelector("[data-lightbox-dialog]");
if (lightbox) {
  document.querySelectorAll("[data-lightbox]").forEach((button) => {
    button.addEventListener("click", () => {
      const img = lightbox.querySelector("img");
      img.src = button.dataset.lightbox;
      img.alt = button.getAttribute("aria-label") || "";
      lightbox.showModal();
    });
  });
  lightbox.addEventListener("click", (event) => { if (event.target === lightbox) lightbox.close(); });
}

// 上傳框（partials/files.html 的 upload_field）：選好檔案先預覽；超過大小就清掉並提醒；照片可以旋轉
document.querySelectorAll("[data-upload]").forEach((zone) => {
  const field = zone.parentElement;
  const input = zone.querySelector("input[type=file]");
  const preview = zone.querySelector(".dropzone__preview");
  const tools = field.querySelector(".dropzone__tools");
  const status = field.querySelector(".dropzone__status");
  const maxBytes = Number(zone.dataset.maxBytes);
  const toMB = (bytes) => (bytes / 1024 / 1024).toFixed(1) + "MB";

  const show = () => {
    const file = input.files[0];
    if (preview.src) URL.revokeObjectURL(preview.src);
    preview.removeAttribute("src");
    preview.hidden = true;
    tools.hidden = true;
    zone.classList.remove("is-chosen", "is-error");
    status.textContent = "";
    if (!file) return;
    if (maxBytes && file.size > maxBytes) {
      input.value = "";
      zone.classList.add("is-error");
      status.textContent = `「${file.name}」有 ${toMB(file.size)}，超過上限 ${toMB(maxBytes)}。請裁切或壓縮後再選一次。`;
      return;
    }
    zone.classList.add("is-chosen");
    status.textContent = `已選擇：${file.name}（${toMB(file.size)}）`;
    if (file.type.startsWith("image/")) {
      preview.src = URL.createObjectURL(file);
      preview.hidden = false;
      tools.hidden = false;
    }
  };

  // 旋轉：把照片畫到畫布上轉 90 度，再換掉要上傳的檔案（上傳的就是轉正後的照片）
  const rotate = (degrees) => {
    const file = input.files[0];
    if (!file || !preview.src) return;
    const canvas = document.createElement("canvas");
    const sideways = Math.abs(degrees) === 90;
    canvas.width = sideways ? preview.naturalHeight : preview.naturalWidth;
    canvas.height = sideways ? preview.naturalWidth : preview.naturalHeight;
    const ctx = canvas.getContext("2d");
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.rotate((degrees * Math.PI) / 180);
    ctx.drawImage(preview, -preview.naturalWidth / 2, -preview.naturalHeight / 2);
    const type = file.type === "image/png" ? "image/png" : "image/jpeg";
    canvas.toBlob((blob) => {
      const files = new DataTransfer();
      files.items.add(new File([blob], file.name, { type }));
      input.files = files.files;
      show();
    }, type, 0.92);
  };
  tools.querySelectorAll("[data-rotate]").forEach((button) => {
    button.addEventListener("click", () => rotate(Number(button.dataset.rotate)));
  });

  input.addEventListener("change", show);
  // 拖檔案進來時框變色（真正接收檔案的是蓋在上面的 input）
  input.addEventListener("dragenter", () => zone.classList.add("is-dragging"));
  ["dragleave", "drop"].forEach((type) => input.addEventListener(type, () => zone.classList.remove("is-dragging")));
});

// 刪除前先問一次
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

// 自傳小幫手：一次只顯示一題（沒有 JavaScript 時全部題目都會顯示）
document.querySelectorAll("[data-steps]").forEach((form) => {
  const steps = [...form.querySelectorAll("[data-step]")];
  const progress = form.querySelector("[data-step-progress]");
  const prev = form.querySelector("[data-step-prev]");
  const next = form.querySelector("[data-step-next]");
  const submit = form.querySelector("[data-step-submit]");
  let current = 0;
  const go = (index) => {
    current = Math.max(0, Math.min(index, steps.length - 1));
    steps.forEach((step, i) => { step.hidden = i !== current; });
    progress.textContent = `第 ${current + 1} 題，共 ${steps.length} 題`;
    prev.hidden = current === 0;
    next.hidden = current === steps.length - 1;
    submit.hidden = current !== steps.length - 1;
    steps[current].querySelector("textarea").focus();
  };
  prev.addEventListener("click", () => go(current - 1));
  next.addEventListener("click", () => go(current + 1));
  go(0);
});

// 送出後按鈕改成「處理中」，避免重複按（AI 需要一點時間）
document.querySelectorAll("[data-busy-text]").forEach((button) => {
  button.form.addEventListener("submit", () => {
    button.disabled = true;
    button.textContent = button.dataset.busyText;
  });
});

// 草稿段落：輸入框隨內容長高，並顯示總字數
const charTotal = document.querySelector("[data-char-total]");
const paragraphs = [...document.querySelectorAll("textarea[data-char]")];
const refreshDraft = () => {
  paragraphs.forEach((area) => { area.style.height = "auto"; area.style.height = area.scrollHeight + 4 + "px"; });
  if (charTotal) charTotal.textContent = `　目前共 ${paragraphs.reduce((sum, area) => sum + area.value.replace(/\s/g, "").length, 0)} 字`;
};
paragraphs.forEach((area) => area.addEventListener("input", refreshDraft));
refreshDraft();

// 資管科小助手：右下角聊天視窗（partials/assistant.html）
document.querySelectorAll("[data-assistant]").forEach((root) => {
  const panel = root.querySelector(".assistant__panel");
  const log = root.querySelector("[data-assistant-log]");
  const form = root.querySelector("[data-assistant-form]");
  const input = form.querySelector("textarea");
  const send = form.querySelector("button[type=submit]");
  const toggles = root.querySelectorAll("[data-assistant-toggle]");
  const KEY = "assistant-history";
  let history = [];
  try { history = JSON.parse(sessionStorage.getItem(KEY) || "[]"); } catch (e) { history = []; }

  // 把 AI 回答的簡單 Markdown（粗體、條列）轉成畫面；先跳脫 HTML，避免被插入程式碼
  const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" };
  const escape = (text) => text.replace(/[&<>"']/g, (c) => ESCAPES[c]);
  const render = (text) => {
    let html = "";
    let inList = false;
    escape(text).split("\n").forEach((line) => {
      const item = line.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)$/);
      if (item && !inList) { html += "<ul>"; inList = true; }
      if (!item && inList) { html += "</ul>"; inList = false; }
      if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) return; // 分隔線不顯示
      const body = (item ? item[1] : line).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\*(.+?)\*/g, "<i>$1</i>").replace(/^#+\s*/, "");
      if (item) html += `<li>${body}</li>`;
      else if (body.trim()) html += `<p>${body}</p>`;
    });
    return html + (inList ? "</ul>" : "");
  };

  const add = (role, text, extra = {}) => {
    const box = document.createElement("div");
    box.className = `assistant__msg assistant__msg--${role === "user" ? "me" : "bot"}`;
    if (role === "user") box.textContent = text;
    else box.innerHTML = render(text);
    if (extra.steps && extra.steps.length) {
      const steps = document.createElement("p");
      steps.className = "assistant__steps";
      steps.textContent = "查了：" + extra.steps.join("、");
      box.prepend(steps);
    }
    if (extra.sources && extra.sources.length) {
      const list = document.createElement("p");
      list.className = "assistant__sources";
      list.textContent = "來源：";
      extra.sources.forEach((source) => {
        const tag = document.createElement(source.url ? "a" : "span");
        tag.className = "tag";
        tag.textContent = source.title;
        if (source.url) { tag.href = source.url; tag.target = "_blank"; tag.rel = "noopener noreferrer"; }
        list.append(tag);
      });
      box.append(list);
    }
    log.append(box);
    log.scrollTop = log.scrollHeight;
    return box;
  };

  history.forEach((turn) => add(turn.role, turn.text));

  const setOpen = (open) => {
    panel.hidden = !open;
    toggles[0].setAttribute("aria-expanded", String(open));
    root.classList.toggle("is-open", open);
    if (open) input.focus();
  };
  toggles.forEach((button) => button.addEventListener("click", () => setOpen(panel.hidden)));
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !panel.hidden) setOpen(false); });

  const submit = async (raw) => {
    const text = raw.trim();
    if (!text) return;
    add("user", text);
    input.value = "";
    send.disabled = true;
    const waiting = add("bot", "正在查資料…");
    waiting.classList.add("is-waiting");
    const data = new FormData();
    data.append("csrf_token", form.querySelector("[name=csrf_token]").value);
    data.append("message", text);
    data.append("history", JSON.stringify(history.slice(-8)));
    data.append("page", document.title);
    try {
      const response = await fetch(root.dataset.endpoint, { method: "POST", body: data, credentials: "same-origin" });
      if (!response.ok) throw new Error(String(response.status));
      const result = await response.json();
      waiting.remove();
      add("bot", result.answer, result);
      history.push({ role: "user", text }, { role: "assistant", text: result.answer });
      try { sessionStorage.setItem(KEY, JSON.stringify(history.slice(-20))); } catch (e) { /* 存不了也沒關係 */ }
    } catch (error) {
      waiting.remove();
      add("bot", "小助手暫時連不上，請稍後再試。");
    } finally {
      send.disabled = false;
      input.focus();
    }
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); submit(input.value); });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); submit(input.value); }
  });
  root.querySelectorAll("[data-assistant-suggest]").forEach((chip) => {
    chip.addEventListener("click", () => { setOpen(true); submit(chip.textContent); });
  });
});


// 引導卡片「稍後再說」：不換頁，卡片淡出後移除
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-guide-snooze]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const card = form.closest("[data-guide-card]");
      try {
        const response = await fetch(form.action, {
          method: "POST", body: new FormData(form), credentials: "same-origin",
          headers: { "X-Requested-With": "fetch" },
        });
        if (!response.ok) throw new Error(String(response.status));
        card.classList.add("is-leaving");
        setTimeout(() => card.remove(), 300);
      } catch (error) {
        form.submit();
      }
    });
  });
});

// 聚焦：捲到畫面時，先讓校系要求一張張堆滿，再淡出，只留最重要的 3 件
document.querySelectorAll("[data-focus]").forEach((root) => {
  const pieces = root.querySelectorAll(".focus__piece").length;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let timer;
  const play = () => {
    clearTimeout(timer);
    root.classList.remove("is-focused", "is-flood");
    if (reduce) { root.classList.add("is-focused"); return; }
    void root.offsetWidth; // 重新開始動畫
    root.classList.add("is-flood");
    timer = setTimeout(() => root.classList.add("is-focused"), pieces * 28 + 1400);
  };
  if ("IntersectionObserver" in window) {
    const watch = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { play(); watch.disconnect(); }
    }, { threshold: 0.35 });
    watch.observe(root);
  } else {
    root.classList.add("is-focused");
  }
  root.querySelector("[data-focus-replay]")?.addEventListener("click", play);
});

// 我的五年路線：點節點打開那一年的資料夾
document.querySelectorAll("[data-open-year]").forEach((node) => {
  node.addEventListener("click", (event) => {
    const drawer = document.querySelector("[data-folders-drawer]");
    const tab = document.getElementById(`tab-${node.dataset.openYear}`);
    if (!drawer || !tab) return;
    event.preventDefault();
    drawer.open = true;
    tab.click();
    drawer.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  });
});

// 好久不見：焦點留在對話框內；沒有鍵盤焦點在裡面時才自動淡出
document.querySelectorAll("[data-return]").forEach((root) => {
  const closeButton = root.querySelector("[data-return-close]");
  let closing = false;
  let autoClose = null;
  const close = () => {
    if (closing) return;
    closing = true;
    clearTimeout(autoClose);
    root.classList.add("is-leaving");
    document.querySelector("[data-journey-home]")?.classList.remove("is-waiting");
    setTimeout(() => {
      document.removeEventListener("keydown", onKey);
      root.remove();
      document.getElementById("route-title")?.focus();
    }, 600);
  };
  function onKey(event) {
    if (event.key === "Escape") { event.preventDefault(); close(); return; }
    if (event.key === "Tab") {
      const focusable = [...root.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")]
        .filter((node) => !node.hidden && !node.disabled);
      if (!focusable.length) return;
      const at = focusable.indexOf(document.activeElement);
      event.preventDefault();
      const next = event.shiftKey ? (at <= 0 ? focusable.length - 1 : at - 1) : (at + 1) % focusable.length;
      focusable[next].focus();
    }
  }
  const scheduleAutoClose = () => {
    autoClose = setTimeout(() => {
      if (root.contains(document.activeElement)) scheduleAutoClose();
      else close();
    }, 4500);
  };
  const number = root.querySelector("[data-count-to]");
  const target = Number(number.dataset.countTo) || 0;
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const start = performance.now();
    const tick = (time) => {
      const t = Math.min(1, (time - start) / 1000);
      number.textContent = Math.round(target * (1 - Math.pow(1 - t, 3)));
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  closeButton.addEventListener("click", close);
  document.addEventListener("keydown", onKey);
  root.querySelector("[data-return-close]").focus();
  scheduleAutoClose();
});

// 小人物：沿著路線從專一走到今年；點路邊的地方，走過去再進入
document.querySelectorAll("[data-walker]").forEach((walker) => {
  const svg = walker.ownerSVGElement;
  const notifyWalked = () => {
    document.documentElement.dataset.journeyWalked = "true";
    document.dispatchEvent(new CustomEvent("journey:walked"));
  };
  if (!svg) return;
  if (svg.getBoundingClientRect().width === 0) { notifyWalked(); return; }  // 手機版不顯示這張圖
  const route = svg.querySelector(".route-map__walked");
  const home = walker.closest("[data-journey-home]");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const grade = Number(walker.dataset.grade) || 1;
  const stops = [100, 300, 500, 700, 900];
  const total = route.getTotalLength();
  // 路線上 x 最接近某個值的位置（二分搜尋）
  const lengthAtX = (x) => {
    let lo = 0, hi = total;
    for (let i = 0; i < 30; i += 1) { const mid = (lo + hi) / 2; if (route.getPointAtLength(mid).x < x) lo = mid; else hi = mid; }
    return lo;
  };
  const place = (point) => walker.setAttribute("transform", `translate(${point.x} ${point.y - 24})`);
  let current = { x: 100, y: 140 };
  place(current);

  const end = lengthAtX(stops[grade - 1]);
  let seen = false;
  try { seen = sessionStorage.getItem("journey-walked") === "1"; } catch (e) { /* 讀不到就當沒看過 */ }
  const finish = () => {
    walker.classList.remove("is-walking");
    current = route.getPointAtLength(end);
    place(current);
    notifyWalked();
  };
  const walk = () => {
    if (reduce || seen || grade === 1) { finish(); return; }
    walker.classList.add("is-walking");
    const start = performance.now();
    const duration = 900 + (grade - 1) * 450;
    const step = (time) => {
      const t = Math.min(1, (time - start) / duration);
      const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      current = route.getPointAtLength(end * eased);
      place(current);
      if (t < 1) requestAnimationFrame(step); else finish();
    };
    requestAnimationFrame(step);
    try { sessionStorage.setItem("journey-walked", "1"); } catch (e) { /* 存不了也沒關係 */ }
  };
  // 「好久不見」播放中就等它關掉再走
  if (home && home.classList.contains("is-waiting")) {
    const watch = new MutationObserver(() => { if (!home.classList.contains("is-waiting")) { watch.disconnect(); setTimeout(walk, 300); } });
    watch.observe(home, { attributes: true, attributeFilter: ["class"] });
  } else {
    setTimeout(walk, 300);
  }

  svg.querySelectorAll("[data-place]").forEach((spot) => {
    spot.addEventListener("click", (event) => {
      if (reduce || event.metaKey || event.ctrlKey || event.shiftKey) return;
      event.preventDefault();
      spot.classList.add("is-target");
      walker.classList.add("is-walking");
      // 從現在的位置走到小島上（直線補間），到了再換頁
      const from = { ...current };
      const to = { x: Number(spot.dataset.x), y: Number(spot.dataset.y) };
      const start = performance.now();
      const step = (time) => {
        const t = Math.min(1, (time - start) / 650);
        const e = 1 - Math.pow(1 - t, 2);
        current = { x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e };
        place(current);
        if (t < 1) requestAnimationFrame(step); else setTimeout(() => { window.location.href = spot.getAttribute("href"); }, 150);
      };
      requestAnimationFrame(step);
    });
  });
});

// 拼圖：把旁邊散落的那片拖回圖上的洞裡（或直接點），拼上後打開新增
document.querySelectorAll("[data-board]").forEach((board) => {
  const boardSvg = board.querySelector(".jig__board");
  // 洞在畫面上的寬度：整張圖 viewBox 寬 660，每片的 viewBox 寬 260。
  // 散落的片平常只有洞的四成多（區塊才不會很長），拖起來再放大到和洞一樣
  const holeWidth = () => (boardSvg ? boardSvg.getBoundingClientRect().width / 660 * 260 : 0);
  const resize = () => {
    if (!boardSvg) return;
    board.querySelectorAll("[data-loose]").forEach((loose) => loose.style.setProperty("--size", `${holeWidth() * 0.45}px`));
  };
  resize();
  window.addEventListener("resize", resize);

  board.querySelectorAll("[data-loose]").forEach((loose) => {
    const piece = loose.querySelector("[data-drag-piece]");
    const hole = board.querySelector(`[data-hole="${loose.dataset.loose}"]`);
    let start = null;
    let moved = false;
    let grow = 1;  // 拖曳時放大幾倍才和洞一樣大
    const measureGrow = () => { grow = holeWidth() / (loose.getBoundingClientRect().width || 1); };
    // 這片在畫面上應該到的位置（洞的左上角，含拼圖凸出的留白）
    const target = () => {
      const box = boardSvg.getBoundingClientRect();
      const scale = box.width / 660;
      return { x: box.left + (Number(loose.dataset.x) + 30 - 30) * scale, y: box.top + (Number(loose.dataset.y) + 30 - 30) * scale };
    };
    const snap = () => {
      measureGrow();
      // 直接點（沒拖）時先放大，量到放大後的位置再移過去
      if (!piece.classList.contains("is-dragging")) piece.classList.add("is-dragging");
      if (!/scale\(/.test(piece.style.transform)) piece.style.transform = `translate(0px, 0px) scale(${grow})`;
      const now = piece.getBoundingClientRect();
      const goal = target();
      const base = piece.style.transform.match(/translate\(([-\d.]+)px, ([-\d.]+)px\)/);
      const bx = base ? Number(base[1]) : 0;
      const by = base ? Number(base[2]) : 0;
      piece.classList.remove("is-dragging");
      piece.classList.add("is-snapped");
      piece.style.transform = `translate(${bx + goal.x - now.left}px, ${by + goal.y - now.top}px) scale(${grow})`;
      setTimeout(() => { window.location.href = loose.getAttribute("href"); }, 320);
    };
    piece.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      piece.setPointerCapture(event.pointerId);
      start = { x: event.clientX, y: event.clientY };
      moved = false;
      measureGrow();
      // 以按下的那一點為中心放大，片才會一直在手指下面
      const box = piece.getBoundingClientRect();
      piece.style.transformOrigin = `${event.clientX - box.left}px ${event.clientY - box.top}px`;
      piece.classList.add("is-dragging");
    });
    piece.addEventListener("pointermove", (event) => {
      if (!start) return;
      const dx = event.clientX - start.x;
      const dy = event.clientY - start.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
      piece.style.transform = `translate(${dx}px, ${dy}px) scale(${grow})`;
      if (hole) {
        const a = piece.getBoundingClientRect();
        const goal = target();
        hole.classList.toggle("is-near", Math.hypot(a.left - goal.x, a.top - goal.y) < a.width * 0.35);
      }
    });
    piece.addEventListener("pointerup", () => {
      if (!start) return;
      start = null;
      if (hole) hole.classList.remove("is-near");
      const a = piece.getBoundingClientRect();
      const goal = target();
      if (!moved || Math.hypot(a.left - goal.x, a.top - goal.y) < a.width * 0.35) { snap(); return; }
      piece.classList.remove("is-dragging");
      piece.style.transform = "";
      piece.style.transformOrigin = "";
    });
    // 拖到一半被系統打斷（來電、手勢）：放回原位
    piece.addEventListener("pointercancel", () => {
      start = null;
      if (hole) hole.classList.remove("is-near");
      piece.classList.remove("is-dragging");
      piece.style.transform = "";
      piece.style.transformOrigin = "";
    });
    // 滑鼠或手指放開後瀏覽器還會送一次 click，交給上面處理；鍵盤 Enter 的 click（detail 為 0）照常換頁
    loose.addEventListener("click", (event) => { if (event.detail !== 0) event.preventDefault(); });
  });

  // 回到首頁時：比對上次看到的拼圖，新拼上的那片跳一下，標題變成「又留下了一塊。」
  const key = `journey-pieces-${board.dataset.grade}`;
  const filled = [...board.querySelectorAll("[data-filled]")].map((el) => el.dataset.piece);
  let before = null;
  try { before = JSON.parse(sessionStorage.getItem(key) || "null"); } catch (e) { before = null; }
  if (Array.isArray(before)) {
    const fresh = filled.filter((piece) => !before.includes(piece));
    if (fresh.length) {
      fresh.forEach((piece) => board.querySelector(`[data-piece="${piece}"]`)?.classList.add("is-new"));
      const title = document.querySelector("[data-board-title]");
      if (title) title.textContent = "又留下了一塊。";
    }
  }
  try { sessionStorage.setItem(key, JSON.stringify(filled)); } catch (e) { /* 存不了也沒關係 */ }
});

// 學期照片：選好檔案就直接上傳
document.querySelectorAll("[data-photo-form]").forEach((form) => {
  const input = form.querySelector("[data-photo-input]");
  form.querySelector("[data-photo-submit]").hidden = true;
  input.addEventListener("change", () => { if (input.files.length) form.submit(); });
});

// ---------- 網頁導覽：一步一步指出畫面上的功能 ----------
// 頁面上有 data-tour="一句話" data-tour-order="1" 的元素就是步驟；看不到的元素（例如手機版隱藏）自動略過。
// 首頁第一次來會自動播一次（瀏覽器記住），其他頁按上方「導覽」才播；Esc 結束、← → 換步。
(() => {
  const page = document.body.dataset.page || "page";
  const steps = () => [...document.querySelectorAll("[data-tour]")]
    .filter((el) => el.getClientRects().length && el.getBoundingClientRect().width > 0)
    .sort((a, b) => (Number(a.dataset.tourOrder) || 99) - (Number(b.dataset.tourOrder) || 99));
  const startButton = document.querySelector("[data-tour-start]");
  if (startButton && steps().length) startButton.hidden = false;

  let layer = null;
  let index = 0;
  let list = [];
  let returnFocus = null;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const place = () => {
    if (!layer) return;
    const rect = list[index].getBoundingClientRect();
    const pad = 8;
    const spot = layer.querySelector(".tour__spot");
    spot.style.top = `${rect.top - pad}px`;
    spot.style.left = `${rect.left - pad}px`;
    spot.style.width = `${rect.width + pad * 2}px`;
    spot.style.height = `${rect.height + pad * 2}px`;
    const card = layer.querySelector(".tour__card");
    const below = rect.bottom + 14 + card.offsetHeight < window.innerHeight;
    const top = below ? rect.bottom + 14 : rect.top - card.offsetHeight - 14;
    card.style.top = `${Math.min(Math.max(12, top), window.innerHeight - card.offsetHeight - 12)}px`;
    card.style.left = `${Math.min(Math.max(12, rect.left), window.innerWidth - card.offsetWidth - 12)}px`;
  };
  const close = () => {
    if (!layer) return;
    layer.remove();
    layer = null;
    document.removeEventListener("keydown", onKey);
    window.removeEventListener("resize", place);
    window.removeEventListener("scroll", place);
    if (returnFocus && returnFocus.focus) returnFocus.focus();
  };
  const go = (next) => {
    if (next < 0) return;
    if (next >= list.length) { close(); return; }
    index = next;
    const target = list[index];
    target.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
    layer.querySelector(".tour__text").textContent = target.dataset.tour;
    layer.querySelector(".tour__count").textContent = `${index + 1}／${list.length}`;
    layer.querySelector("[data-tour-prev]").hidden = index === 0;
    layer.querySelector("[data-tour-next]").textContent = index === list.length - 1 ? "完成" : "下一步 →";
    place();
    setTimeout(place, 400);
    layer.querySelector("[data-tour-next]").focus();
  };
  function onKey(event) {
    if (event.key === "Tab" && layer) {
      // 焦點只在導覽卡片的按鈕之間循環，不會跑到被遮住的頁面
      const buttons = [...layer.querySelectorAll("button")].filter((b) => !b.hidden);
      const at = buttons.indexOf(document.activeElement);
      event.preventDefault();
      const next = event.shiftKey ? (at <= 0 ? buttons.length - 1 : at - 1) : (at + 1) % buttons.length;
      buttons[next].focus();
      return;
    }
    if (event.key === "Escape") close();
    if (event.key === "ArrowRight") go(index + 1);
    if (event.key === "ArrowLeft") go(index - 1);
  }
  const start = () => {
    list = steps();
    if (!list.length) return;
    close();
    returnFocus = document.activeElement;
    layer = document.createElement("div");
    layer.className = "tour";
    layer.setAttribute("role", "dialog");
    layer.setAttribute("aria-modal", "true");
    layer.setAttribute("aria-label", "網頁導覽");
    layer.innerHTML = '<div class="tour__spot"></div>'
      + '<div class="tour__card"><p class="tour__text" aria-live="polite"></p>'
      + '<div class="tour__actions"><span class="tour__count"></span>'
      + '<button type="button" class="tour__skip" data-tour-close>結束</button>'
      + '<button type="button" class="button button--small button--line" data-tour-prev>← 上一步</button>'
      + '<button type="button" class="button button--small" data-tour-next>下一步 →</button></div></div>';
    document.body.appendChild(layer);
    layer.querySelector("[data-tour-close]").addEventListener("click", close);
    layer.querySelector("[data-tour-prev]").addEventListener("click", () => go(index - 1));
    layer.querySelector("[data-tour-next]").addEventListener("click", () => go(index + 1));
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, { passive: true });
    go(0);
    try { localStorage.setItem(`tour-seen-${page}`, "1"); } catch (e) { /* 存不了也沒關係 */ }
  };
  if (startButton) startButton.addEventListener("click", start);
  document.querySelectorAll("[data-tour-replay]").forEach((button) => button.addEventListener("click", () => {
    try { localStorage.removeItem(`tour-seen-${button.dataset.tourReplay}`); } catch (e) { /* 沒關係 */ }
    window.location.href = button.dataset.tourReplayUrl || "/student/dashboard";
  }));
  // 首頁第一次來自動播；「好久不見」那一幕還在的話等它關掉，也等小人物走完
  if (new URLSearchParams(window.location.search || "").get("tour") === "1") {
    start();
  } else if (page === "student-dashboard") {
    let seen = false;
    try { seen = localStorage.getItem(`tour-seen-${page}`) === "1"; } catch (e) { seen = true; }
    if (!seen) {
      const waitForWalker = () => {
        if (document.documentElement.dataset.journeyWalked === "true") { start(); return; }
        let started = false;
        let fallback = null;
        const begin = () => {
          if (started) return;
          started = true;
          clearTimeout(fallback);
          document.removeEventListener("journey:walked", begin);
          start();
        };
        document.addEventListener("journey:walked", begin, { once: true });
        fallback = setTimeout(begin, 6000);
      };
      const wait = () => {
        if (document.querySelector("[data-return]")) setTimeout(wait, 500);
        else waitForWalker();
      };
      wait();
    }
  }
})();
