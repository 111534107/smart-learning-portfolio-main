// 學生端 v2：缺件檢查頁（2026-11-11）
// 方塊填滿、準備度往上數、點方塊看細節都由 components.js 處理；這裡只讓備審目錄的加權長條捲到畫面內才依序長出來。
(function () {
  const toc = document.querySelector(".g2gap [data-toc-bars]");
  if (!toc || window.matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) return;
  toc.querySelectorAll(".toc__bar i").forEach((bar, i) => bar.style.setProperty("--delay", `${i * 0.08}s`));
  toc.classList.add("is-waiting");
  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) {
      setTimeout(() => toc.classList.remove("is-waiting"), 30);
      io.disconnect();
    }
  }, { threshold: 0.2 });
  io.observe(toc);
  // 保底：分頁在背景、觀察器沒觸發時，幾秒後也一定顯示，不能停在 0
  setTimeout(() => { io.disconnect(); toc.classList.remove("is-waiting"); }, 4000);
})();
