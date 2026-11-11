// 學生端 v2：畢業門檻頁（2026-11-11）
// 1. 十格學期條：點格子只顯示那一學期的細節（沒有 JS 時，所有有不及格的學期細節都直接列出）
// 2. 學分進度條：捲到畫面內才從 0 長到目前比例；系統設定「減少動態」時直接顯示
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

  const bars = root.querySelector("[data-credit-bars]");
  if (bars && !reduce && "IntersectionObserver" in window) {
    bars.classList.add("is-waiting");
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setTimeout(() => bars.classList.remove("is-waiting"), 30);
        io.disconnect();
      }
    }, { threshold: 0.3 });
    io.observe(bars);
    // 保底：分頁在背景、觀察器沒觸發時，幾秒後也一定顯示，不能停在 0
    setTimeout(() => { io.disconnect(); bars.classList.remove("is-waiting"); }, 4000);
  }
})();
