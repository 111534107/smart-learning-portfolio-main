(() => {
  const dialog = document.getElementById("student-search-dialog");
  if (!dialog || typeof dialog.showModal !== "function") return;
  const form = dialog.querySelector("form");
  const status = dialog.querySelector("[data-search-status]");
  const results = dialog.querySelector("[data-search-results]");
  let opener, pending, position, drag;
  const moveHandle = dialog.querySelector("[data-search-move]");
  const reset = dialog.querySelector("[data-search-reset]");

  const place = (left, top) => {
    const box = dialog.getBoundingClientRect();
    const maxX = Math.max(8, document.documentElement.clientWidth - box.width - 8);
    const maxY = Math.max(8, window.innerHeight - box.height - 8);
    position = { left: Math.max(8, Math.min(maxX, left)), top: Math.max(8, Math.min(maxY, top)) };
    dialog.style.left = position.left + "px";
    dialog.style.top = position.top + "px";
    dialog.classList.add("is-positioned");
  };
  const fit = () => {
    if (position && dialog.open) place(position.left, position.top);
  };
  reset.addEventListener("click", () => {
    position = undefined;
    dialog.classList.remove("is-positioned");
    dialog.style.removeProperty("left");
    dialog.style.removeProperty("top");
  });
  moveHandle.addEventListener("pointerdown", (event) => {
    if (!event.isPrimary || event.button !== 0) return;
    const box = dialog.getBoundingClientRect();
    drag = { id: event.pointerId, x: event.clientX - box.left, y: event.clientY - box.top };
    moveHandle.setPointerCapture(event.pointerId);
  });
  moveHandle.addEventListener("pointermove", (event) => {
    if (drag?.id === event.pointerId) place(event.clientX - drag.x, event.clientY - drag.y);
  });
  moveHandle.addEventListener("lostpointercapture", () => { drag = undefined; });
  moveHandle.addEventListener("keydown", (event) => {
    const step = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] }[event.key];
    if (!step) return;
    event.preventDefault();
    const box = dialog.getBoundingClientRect();
    place(box.left + step[0], box.top + step[1]);
  });
  window.addEventListener("resize", fit);
  if (typeof ResizeObserver === "function") new ResizeObserver(fit).observe(dialog);
  dialog.querySelector("[data-search-example]").addEventListener("click", () => {
    form.elements.q.value = "畢業門檻";
    form.elements.kind.value = "功能";
    form.requestSubmit();
  });
  document.querySelectorAll("[data-student-search-open]").forEach((link) => {
    link.setAttribute("aria-haspopup", "dialog");
    link.addEventListener("click", (event) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      opener = link;
      if (!dialog.open) dialog.showModal();
      fit();
    });
  });
  dialog.querySelector("[data-student-search-close]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  });
  dialog.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    dialog.close();
  });
  dialog.addEventListener("close", () => {
    pending?.abort();
    opener?.focus({ preventScroll: true });
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    pending?.abort();
    const request = new AbortController();
    pending = request;
    const params = new URLSearchParams(new FormData(form));
    params.set("format", "json");
    status.hidden = false;
    status.textContent = "搜尋中…";
    results.hidden = true;
    results.replaceChildren();
    try {
      const response = await fetch(form.action + "?" + params, { signal: request.signal });
      if (!response.ok) throw new Error("Search failed");
      const data = await response.json();
      if (request.signal.aborted) return;
      for (const [kind, title, href] of data.results) {
        const row = document.createElement("li");
        const link = document.createElement("a");
        link.href = href;
        link.textContent = title;
        const tag = document.createElement("small");
        tag.textContent = kind;
        row.append(tag, link);
        results.append(row);
      }
      results.hidden = !data.results.length;
      status.textContent = data.results.length ? `找到 ${data.results.length} 筆` : "沒有找到符合的資料。";
    } catch (error) {
      if (error.name !== "AbortError") status.textContent = "暫時無法搜尋，請再試一次。";
    }
  });
  form.elements.kind.addEventListener("change", () => {
    if (form.elements.q.value.trim()) form.requestSubmit();
  });
})();
