/* 學生端 v2：成績單核對頁「下一筆要核對」（2026-11-11）
   - 依序跳到畫面上還看得到、標成要核對（data-attention="true"）的課程，捲到中間、亮一下，游標放到第一個待確認欄位。
   - 只負責移動與標示，不改任何欄位值；篩選（要核對／不及格／全部、年級）變了就重新計算。 */
(function () {
  "use strict";
  var button = document.querySelector("[data-sv2-next]");
  if (!button) { return; }
  var count = button.querySelector("[data-sv2-next-count]");
  var index = -1;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function visible(row) {
    for (var el = row; el; el = el.parentElement) { if (el.hidden) { return false; } }
    return true;
  }
  function targets() {
    return Array.prototype.filter.call(document.querySelectorAll('tr[data-course-index][data-attention="true"]'), visible);
  }
  function refresh() {
    var list = targets();
    button.hidden = list.length === 0;
    if (index >= list.length) { index = -1; }
    count.textContent = index < 0 ? "共 " + list.length + " 筆" : (index + 1) + "／" + list.length;
  }
  button.addEventListener("click", function () {
    var list = targets();
    if (!list.length) { refresh(); return; }
    index = (index + 1) % list.length;
    var row = list[index];
    for (var el = row.parentElement; el; el = el.parentElement) { if (el.tagName === "DETAILS") { el.open = true; } }
    row.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
    document.querySelectorAll("tr.sv2-focus").forEach(function (r) { r.classList.remove("sv2-focus"); });
    row.classList.add("sv2-focus");
    // 先找待確認、看不清楚的欄位；手機不自動聚焦（會跳出鍵盤擋住原圖）
    var field = row.querySelector("input.value-pending") || row.querySelector("td.field-low input") || row.querySelector("input:not([readonly])");
    var finePointer = window.matchMedia && window.matchMedia("(pointer: fine)").matches;
    if (field && finePointer) { setTimeout(function () { field.focus({ preventScroll: true }); }, reduce ? 0 : 350); }
    refresh();
  });
  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-review-view], [data-review-show-all]")) { index = -1; setTimeout(refresh, 0); }
  });
  document.addEventListener("change", function (event) {
    if (event.target.id === "review-grade-filter") { index = -1; setTimeout(refresh, 0); }
  });
  refresh();
})();
