// 學生首頁「散落的紙張」與實習履歷頁的互動（2026-11-17）。
// 拖曳的寫法搬自設計示範 _design-demo/student-v2/drag.js 與 index.html：
// 滑鼠按住移動就拖；手指要長按 0.25 秒才拿起（沒長按就照常捲頁面）；放開帶一點慣性，位置記在這台瀏覽器。
(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function pickUp(el, handlers) {
    let id = null, sx = 0, sy = 0, lx = 0, ly = 0, t = 0, vx = 0, vy = 0, live = false, timer = null, touch = false;
    const start = (event) => { live = true; el.classList.add("is-held"); if (handlers.start) handlers.start(event); };
    el.addEventListener("pointerdown", (event) => {
      if (event.button > 0) return;
      id = event.pointerId; touch = event.pointerType !== "mouse";
      sx = lx = event.clientX; sy = ly = event.clientY; t = performance.now(); vx = vy = 0; live = false;
      if (touch) timer = setTimeout(() => { start(event); try { el.setPointerCapture(id); } catch (e) { /* 抓不到也能拖 */ } }, 250);
      else { try { el.setPointerCapture(id); } catch (e) { /* 同上 */ } }
    });
    el.addEventListener("pointermove", (event) => {
      if (event.pointerId !== id) return;
      if (!live) {
        if (Math.hypot(event.clientX - sx, event.clientY - sy) < 6) return;
        if (touch) { clearTimeout(timer); id = null; return; }  // 手指沒長按就移動：交給頁面捲動
        start(event);
      }
      const now = performance.now(), dt = Math.max(1, now - t);
      vx = vx * 0.6 + (event.clientX - lx) / dt * 16 * 0.4; vy = vy * 0.6 + (event.clientY - ly) / dt * 16 * 0.4;
      lx = event.clientX; ly = event.clientY; t = now;
      if (handlers.move) handlers.move({ dx: event.clientX - sx, dy: event.clientY - sy, vx, vy });
    });
    const end = (event) => {
      if (event.pointerId !== id) return;
      clearTimeout(timer); id = null;
      if (live) { live = false; el.classList.remove("is-held"); el.dataset.dragged = "1"; setTimeout(() => { delete el.dataset.dragged; }, 80); if (handlers.end) handlers.end({ vx, vy }); }
    };
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
    el.addEventListener("touchmove", (event) => { if (live) event.preventDefault(); }, { passive: false });
    el.addEventListener("contextmenu", (event) => { if (touch) event.preventDefault(); });
    // 點（或鍵盤 Enter／空白鍵）＝打開；剛拖完的那一下不算點
    el.addEventListener("click", (event) => {
      if (el.dataset.dragged) { delete el.dataset.dragged; event.preventDefault(); return; }
      if (handlers.tap) handlers.tap(event);
    });
  }

  // ---------- 散落的紙 ----------
  const desk = document.querySelector("[data-desk]");
  if (desk) {
    const sheets = [...desk.querySelectorAll("[data-sheet]")];
    const dialog = document.querySelector("[data-sheet-doc]");
    const reset = desk.querySelector("[data-desk-reset]");
    const storageKey = "home-desk-pos:v2:" + desk.dataset.deskOwner;
    const phone = window.matchMedia("(max-width: 720px)");
    let saved = {};
    try {
      const previous = JSON.parse(localStorage.getItem(storageKey) || "{}") || {};
      for (const sheet of sheets) {
        const key = sheet.dataset.sheet;
        const position = previous[key];
        if (Array.isArray(position) && position.length === 3 && position.every(Number.isFinite)
            && position[0] >= 0 && position[0] <= 100 && position[1] >= 0 && position[1] <= 100) {
          saved[key] = position;
        }
      }
    } catch (e) { /* 讀不到就用原位置 */ }
    const updateReset = () => {
      if (reset) reset.hidden = !sheets.some(sheet =>
        saved[sheet.dataset.sheet] && (!phone.matches || !sheet.classList.contains("dsheet--wide-only")));
    };
    const store = () => {
      try { localStorage.setItem(storageKey, JSON.stringify(saved)); } catch (e) { /* 存不了就不記 */ }
      updateReset();
    };
    let top = 10;

    const open = (sheet) => {
      if (!dialog || !dialog.showModal) { window.location.href = sheet.dataset.href; return; }
      dialog.querySelector("[data-sheet-meta]").textContent = sheet.dataset.kind;
      dialog.querySelector("[data-sheet-title]").textContent = sheet.dataset.title || "（沒有標題）";
      dialog.querySelector("[data-sheet-detail]").textContent = sheet.dataset.detail || "";
      dialog.querySelector("[data-sheet-link]").setAttribute("href", sheet.dataset.href);
      dialog.showModal();
    };
    if (dialog) dialog.addEventListener("click", (event) => {
      if (event.target === dialog || event.target.closest("[data-sheet-close]")) dialog.close();
    });

    sheets.forEach((sheet) => {
      const key = sheet.dataset.sheet;
      const place = (x, y) => {
        // 手機和電腦各用各的變數（CSS 依寬度選一個），拖過的位置兩邊都寫
        sheet.style.setProperty("--x", x); sheet.style.setProperty("--mx", x);
        sheet.style.setProperty("--y", y); sheet.style.setProperty("--my", y);
      };
      if (saved[key]) { place(saved[key][0] + "%", saved[key][1] + "%"); sheet.style.setProperty("--r", saved[key][2] + "deg"); }
      sheet.addEventListener("animationend", () => sheet.classList.add("is-landed"), { once: true });
      if (reduce) sheet.classList.add("is-landed");

      let ox = 0, oy = 0, x = 0, y = 0, W = 0, H = 0, frame = 0, fling = 0;
      const paint = () => { frame = 0; place(x + "px", y + "px"); };
      const clampX = (v) => Math.max(20, Math.min(W - 20, v));
      const clampY = (v) => Math.max(24, Math.min(H - 24, v));
      const keep = () => {
        saved[key] = [+(x / W * 100).toFixed(2), +(y / H * 100).toFixed(2), parseFloat(sheet.style.getPropertyValue("--r")) || 0];
        store();
      };
      pickUp(sheet, {
        start() {
          cancelAnimationFrame(fling);
          sheet.classList.add("is-landed", "is-dragging");
          W = desk.clientWidth; H = desk.clientHeight;
          ox = x = sheet.offsetLeft; oy = y = sheet.offsetTop;
          sheet.style.zIndex = String(++top);
        },
        move(m) {
          x = clampX(ox + m.dx); y = clampY(oy + m.dy);
          sheet.style.setProperty("--tilt", Math.max(-18, Math.min(18, m.vx * 2)) + "deg");
          if (!frame) frame = requestAnimationFrame(paint);
        },
        end(m) {
          sheet.classList.remove("is-dragging");
          sheet.style.setProperty("--tilt", "0deg");
          if (frame) cancelAnimationFrame(frame);
          paint();
          if (x === ox && y === oy) return;
          let vx = m.vx, vy = m.vy;
          const speed = Math.hypot(vx, vy), cap = 24;
          if (speed > cap) { vx *= cap / speed; vy *= cap / speed; }  // 甩太快也只滑一小段
          const turn = (parseFloat(sheet.style.getPropertyValue("--r")) || 0) + Math.max(-8, Math.min(8, vx * 0.5));
          sheet.style.setProperty("--r", Math.max(-30, Math.min(30, turn)).toFixed(1) + "deg");
          keep();
          if (reduce) return;
          const step = () => {
            vx *= 0.9; vy *= 0.9; x += vx; y += vy;
            if (x < 20 || x > W - 20) { vx *= -0.5; x = clampX(x); }
            if (y < 24 || y > H - 24) { vy *= -0.5; y = clampY(y); }
            paint();
            if (Math.hypot(vx, vy) > 0.4) fling = requestAnimationFrame(step); else keep();
          };
          fling = requestAnimationFrame(step);
        },
        tap: () => open(sheet),
      });
    });
    if (reset) {
      updateReset();
      phone.addEventListener("change", updateReset);
      reset.addEventListener("click", () => { saved = {}; store(); window.location.reload(); });
    }

    document.querySelectorAll(".desk-action-locked").forEach((control) => {
      const button = control.querySelector("button");
      const show = () => control.classList.remove("tip-dismissed");
      button.addEventListener("click", () => {
        show();
        button.focus();
      });
      button.addEventListener("keydown", (event) => {
        if (event.key === "Escape") control.classList.add("tip-dismissed");
      });
      button.addEventListener("blur", show);
      control.addEventListener("pointerenter", show);
    });

    // ---------- 拼圖舞台 ----------
    // 拼圖桌平常收起來；按「產生實習履歷」或「生成自傳」：紙往中間收 → 整頁攤開拼圖桌 → 借 components.js 的拼圖動畫拼好 → 去那一頁。
    const puzzle = document.querySelector("[data-year-puzzle]");
    if (puzzle) puzzle.classList.add("is-stowed");
    document.querySelectorAll("[data-stage-go]").forEach((button) => {
      button.addEventListener("click", (event) => {
        const assemble = puzzle && puzzle.querySelector("a[data-assemble]");
        const plain = !(event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button > 0);
        if (reduce || !assemble || !plain) return;
        event.preventDefault();
        if (puzzle.dataset.busy) return;
        puzzle.dataset.busy = "1";
        const href = button.href;
        let requested = false;
        const navigate = () => {
          if (requested) return;
          requested = true;
          clearTimeout(fallback);
          window.location.assign(href);
        };
        const fallback = setTimeout(navigate, 4200);
        window.addEventListener("pagehide", () => clearTimeout(fallback), { once: true });
        try {
          desk.classList.add("is-gathering");
          setTimeout(() => {
            try {
              puzzle.classList.remove("is-stowed");
              puzzle.classList.add("is-stage");
              const animation = new CustomEvent("journey:assemble", {
                cancelable: true, detail: { complete: navigate },
              });
              if (assemble.dispatchEvent(animation)) navigate();
            } catch (error) { navigate(); }
          }, 600);
        } catch (error) { navigate(); }
      });
    });
    // 從別頁按「上一頁」回來：把舞台收掉，不要卡在拼好的畫面
    window.addEventListener("pageshow", (event) => { if (event.persisted) window.location.reload(); });
  }

  // ---------- 實習履歷頁：取消勾選的那一片退出去，下面即時列出會寫進自傳的資料 ----------
  const form = document.querySelector("[data-resume-form]");
  if (form) {
    const boxes = [...form.querySelectorAll("[data-pick-box]")];
    const count = form.querySelector("[data-resume-count]");
    const refresh = () => {
      const lines = {};
      boxes.forEach((box) => {
        const row = box.closest("[data-pick]");
        if (row) row.classList.toggle("is-out", !box.checked);
        if (box.checked) (lines[box.dataset.section] = lines[box.dataset.section] || []).push(box.dataset.line);
      });
      form.querySelectorAll("[data-section-preview]").forEach((preview) => {
        const list = lines[preview.dataset.sectionPreview] || [];
        preview.textContent = list.length ? "會列在這一段後面：\n" + list.join("\n") : "";
      });
      const merged = boxes.filter((box) => box.checked).map((box) => box.dataset.line).filter(Boolean);
      form.querySelectorAll("[data-free-preview]").forEach((preview) => {
        preview.textContent = merged.length ? "會列在自傳後面：\n" + merged.join("\n") : "";
      });
      if (count) count.textContent = `放進履歷 ${boxes.filter((box) => box.checked).length} 筆，不放 ${boxes.filter((box) => !box.checked).length} 筆。`;
    };
    boxes.forEach((box) => box.addEventListener("change", refresh));
    refresh();
  }
})();
