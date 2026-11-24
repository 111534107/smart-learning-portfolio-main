(function () {
  "use strict";
  var form = document.querySelector("[data-draft-form], form[data-steps]");
  var status = document.querySelector("[data-unsaved-status]");
  if (!form || !status) return;
  function snapshot() {
    return JSON.stringify(Array.from(new FormData(form).entries()).filter(function (entry) {
      return entry[0] !== "csrf_token" && entry[0] !== "own_api_key" && typeof entry[1] === "string";
    }));
  }
  var initial = snapshot(), submitting = false;
  function update() {
    var clean = snapshot() === initial;
    status.textContent = clean ? "目前沒有未儲存的修改。" : "有未儲存的修改，離開前請先儲存。";
    status.classList.toggle("muted", clean);
    status.classList.toggle("alert", !clean);
  }
  form.addEventListener("input", update);
  form.addEventListener("change", update);
  new MutationObserver(update).observe(form, {childList: true, subtree: true});
  form.addEventListener("submit", function (event) {
    if (!event.defaultPrevented && (!form.hasAttribute("data-draft-form") || !event.submitter || !event.submitter.hasAttribute("formaction"))) submitting = true;
  });
  window.addEventListener("beforeunload", function (event) {
    if (!submitting && snapshot() !== initial) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
})();
