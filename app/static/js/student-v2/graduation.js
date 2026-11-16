// 學生端 v2：畢業門檻工作台（2026-11-11 建立，2026-11-16 改成工作台）
// 1. 十格學期條：點格子只顯示那一學期的細節（沒有 JS 時，所有有不及格的學期細節都直接列出）
// 2. 總覽：總學分環與四條量表從 0 長到實際值，數字跟著跳；系統設定「減少動態」時直接顯示
// 3. 點量表 → 打開並捲到那一個門檻區塊；第一次打開已達成的區塊會畫勾
// 4. 「問導師」「請科辦確認」這類下一步：把內容先填進下方詢問框
(function () {
  const root = document.querySelector(".g2grad");
  if (!root) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const strip = root.querySelector("[data-term-strip]");
  if (strip) {
    const cells = [...strip.querySelectorAll(".g2-term")];
    const panels = [...root.querySelectorAll(".g2-detail")];
    const show = (cell) => {
      cells.forEach((c) => c.setAttribute("aria-pressed", String(c === cell)));
      const id = cell.getAttribute("aria-controls");
      panels.forEach((p) => { p.hidden = p.id !== id; });
    };
    cells.forEach((cell) => cell.addEventListener("click", () => show(cell)));
    // 預設打開：最近一個有不及格的學期；沒有的話，打開最近結束的學期
    const ended = cells.filter((c) => !c.classList.contains("future"));
    const first = [...ended].reverse().find((c) => c.classList.contains("warn")) || ended[ended.length - 1];
    if (first) show(first);
    if (!reduce) strip.classList.add("is-animated");
  }

  // ---- 總覽動畫：環、量表、數字 ----
  const top = root.querySelector("[data-gd-top]");
  const grow = [...root.querySelectorAll("[data-credit-bars], [data-gd-ring]")];
  const counters = [...root.querySelectorAll("[data-count]")];
  const countUp = (el) => {
    const end = Number(el.dataset.count);
    if (!Number.isFinite(end) || end <= 0) return;
    const start = performance.now();
    const dur = 1300;
    const tick = (now) => {
      const t = Math.min((now - start) / dur, 1);
      el.textContent = String(Math.round(end * (1 - Math.pow(1 - t, 3))));
      if (t < 1) requestAnimationFrame(tick);
    };
    el.textContent = "0";
    requestAnimationFrame(tick);
  };
  if (top && !reduce && "IntersectionObserver" in window) {
    grow.forEach((el) => el.classList.add("is-waiting"));
    let started = false;
    const go = () => {
      if (started) return;
      started = true;
      setTimeout(() => grow.forEach((el) => el.classList.remove("is-waiting")), 40);
      counters.forEach(countUp);
    };
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { go(); io.disconnect(); }
    }, { threshold: 0.25 });
    io.observe(top);
    // 保底：分頁在背景、觀察器沒觸發時，幾秒後也一定顯示實際值，不能停在 0
    setTimeout(() => { io.disconnect(); if (!started) { started = true; grow.forEach((el) => el.classList.remove("is-waiting")); } }, 4000);
  }

  // ---- 門檻區塊：已達成的第一次打開時畫勾 ----
  const blocks = [...root.querySelectorAll("[data-gd-block]")];
  blocks.forEach((block) => {
    block.addEventListener("toggle", () => {
      if (block.open && block.dataset.result === "met" && !block.dataset.seen && !reduce) {
        block.dataset.seen = "1";
        block.classList.remove("is-new-met");
        void block.offsetWidth;
        block.classList.add("is-new-met");
      }
    });
  });

  // 點量表：打開對應區塊並捲過去
  root.querySelectorAll("[data-open-block]").forEach((link) => {
    link.addEventListener("click", (event) => {
      const block = root.querySelector(`[data-gd-block="${link.dataset.openBlock}"]`);
      if (!block) return;
      event.preventDefault();
      block.open = true;
      block.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      const summary = block.querySelector("summary");
      if (summary) summary.focus({ preventScroll: true });
    });
  });

  // ---- 下一步：要問人的，先把內容填進詢問框 ----
  const ask = root.querySelector("#gd-ask");
  const note = ask ? ask.querySelector("textarea[name=note]") : null;
  root.querySelectorAll("[data-prefill]").forEach((button) => {
    button.addEventListener("click", (event) => {
      if (!note) return;
      event.preventDefault();
      if (!note.value.trim() || note.dataset.filled === "1") {
        note.value = button.dataset.prefill;
        note.dataset.filled = "1";
      }
      ask.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
      ask.classList.remove("is-flash");
      void ask.offsetWidth;
      ask.classList.add("is-flash");
      note.focus({ preventScroll: true });
    });
  });
  if (note) note.addEventListener("input", () => { note.dataset.filled = "0"; });
})();
