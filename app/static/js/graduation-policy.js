(() => {
  const summaries = [...document.querySelectorAll("[data-graduation-policy]")];
  if (!summaries.length) return;
  let pending;
  const load = () => {
    if (!pending) {
      const { endpoint, csrf } = summaries[0].dataset;
      pending = fetch(endpoint, {
        method: "POST",
        body: new URLSearchParams({ csrf_token: csrf }),
      }).then((response) => {
        if (!response.ok) throw new Error("Policy summary unavailable");
        return response.json();
      }).then(({ summary, basis, checked_on: checkedOn }) => {
        for (const panel of summaries) {
          panel.querySelector("[data-policy-summary]").textContent = summary;
          panel.querySelector("[data-policy-basis]").textContent = checkedOn ? basis + " · 查核 " + checkedOn : basis;
        }
      }).catch(() => { pending = undefined; });
    }
  };
  if (typeof IntersectionObserver !== "function") {
    load();
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) {
      observer.disconnect();
      load();
    }
  });
  summaries.forEach((panel) => observer.observe(panel));
})();
