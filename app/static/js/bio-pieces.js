/* 自傳素材拖放（2026-11-13，B1）
   - [data-bio-piece] 可以拖到頁面上的 textarea；放開時插在游標位置（拖放是複製，來源不會消失）。
   - 「放進去」按鈕：插在最後點過的 textarea（手機、鍵盤可用）；還沒點過就放進第一個。
   - 插入後觸發 input 事件，讓字數統計、自動長高照常運作。 */
(function () {
  "use strict";
  var box = document.querySelector("[data-bio-pieces]");
  if (!box) { return; }
  var status = box.querySelector("[data-bio-status]");
  var areas = Array.prototype.slice.call(document.querySelectorAll("form textarea"));
  if (!areas.length) { return; }
  var last = null;
  areas.forEach(function (area) {
    area.addEventListener("focus", function () { last = area; });
  });

  function insert(area, text, at) {
    var pos = typeof at === "number" ? at : (area === last ? area.selectionEnd : area.value.length);
    var before = area.value.slice(0, pos), after = area.value.slice(pos);
    var gap = before && !/\s$/.test(before) ? "\n" : "";
    area.value = before + gap + text + after;
    var end = (before + gap + text).length;
    area.focus();
    area.setSelectionRange(end, end);
    area.dispatchEvent(new Event("input", { bubbles: true }));
    area.classList.add("bio-target--flash");
    setTimeout(function () { area.classList.remove("bio-target--flash"); }, 700);
    var question = area.closest("label") && area.closest("label").querySelector(".ask__question");
    var tag = question && question.querySelector(".tag");
    var label = area.getAttribute("aria-label") ||
      (question ? question.textContent.replace(tag ? tag.textContent : "", "") : "文字框");
    if (status) { status.textContent = "已放進「" + label.trim().slice(0, 20) + "」，可以再改成你自己的話。"; }
  }

  box.addEventListener("click", function (event) {
    var button = event.target.closest("[data-bio-put]");
    if (!button) { return; }
    insert(last || areas[0], button.closest("[data-bio-piece]").getAttribute("data-bio-piece"));
  });

  box.addEventListener("dragstart", function (event) {
    var piece = event.target.closest && event.target.closest("[data-bio-piece]");
    if (!piece) { return; }
    event.dataTransfer.effectAllowed = "copy";
    event.dataTransfer.setData("text/plain", piece.getAttribute("data-bio-piece"));
    event.dataTransfer.setData("application/x-bio-piece", "1");
    document.documentElement.classList.add("bio-dragging");
  });
  box.addEventListener("dragend", function () { document.documentElement.classList.remove("bio-dragging"); });

  areas.forEach(function (area) {
    area.addEventListener("dragover", function (event) {
      if (Array.prototype.indexOf.call(event.dataTransfer.types, "application/x-bio-piece") === -1) { return; }
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      area.classList.add("bio-target--over");
    });
    area.addEventListener("dragleave", function () { area.classList.remove("bio-target--over"); });
    area.addEventListener("drop", function (event) {
      if (Array.prototype.indexOf.call(event.dataTransfer.types, "application/x-bio-piece") === -1) { return; }
      event.preventDefault();
      area.classList.remove("bio-target--over");
      document.documentElement.classList.remove("bio-dragging");
      last = area;
      insert(area, event.dataTransfer.getData("text/plain"), area.selectionEnd);
    });
  });
})();
