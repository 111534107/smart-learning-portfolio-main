(() => {
  const dialog = document.getElementById("student-search-dialog");
  if (!dialog || typeof dialog.showModal !== "function") return;
  const form = dialog.querySelector("form");
  const status = dialog.querySelector("[data-search-status]");
  const results = dialog.querySelector("[data-search-results]");
  let opener, pending;
  document.querySelectorAll("[data-student-search-open]").forEach((link) => {
    link.setAttribute("aria-haspopup", "dialog");
    link.addEventListener("click", (event) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      opener = link;
      dialog.showModal();
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
  dialog.addEventListener("close", () => opener?.focus({ preventScroll: true }));
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
