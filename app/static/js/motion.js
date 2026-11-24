// 公開首頁六幕：一般模式依序成路、聚焦、組合；減少動態時只淡入。
(() => {
  document.documentElement.classList.remove("no-js");
  document.documentElement.classList.add("js");

  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const motionItems = document.querySelectorAll("[data-motion]");

  if (reduce) {
    document.documentElement.classList.add("reduced-motion");
    window.requestAnimationFrame(() => motionItems.forEach((el) => el.classList.add("is-visible")));
    return;
  }

  document.documentElement.classList.add("motion-ready");

  if (typeof window.IntersectionObserver !== "function") {
    motionItems.forEach((el) => el.classList.add("is-visible"));
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-visible");
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.2, rootMargin: "0px 0px -40px" });

  motionItems.forEach((el) => observer.observe(el));
})();
