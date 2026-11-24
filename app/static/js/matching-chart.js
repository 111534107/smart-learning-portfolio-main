// 排行頁圖表切換：只改顯示（橫條／長條），沒有 JS 時按鈕仍是帶 ?chart= 的連結。
(function () {
  var chart = document.querySelector("[data-match-chart]");
  var buttons = document.querySelectorAll("[data-chart-mode]");
  if (!chart || !buttons.length) return;
  buttons.forEach(function (button) {
    button.addEventListener("click", function (event) {
      event.preventDefault();
      var mode = button.getAttribute("data-chart-mode");
      chart.classList.remove("match-chart--bar", "match-chart--column");
      chart.classList.add("match-chart--" + mode);
      buttons.forEach(function (other) {
        var on = other === button;
        other.setAttribute("aria-pressed", on ? "true" : "false");
        other.classList.toggle("button--line", !on);
      });
      var form = document.querySelector(".match-filter input[name=chart]");
      if (form) form.value = mode;
      if (window.history && history.replaceState) history.replaceState(null, "", button.getAttribute("href"));
    });
  });
})();
