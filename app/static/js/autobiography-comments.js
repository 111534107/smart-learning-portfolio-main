// 自傳段落註解：送出註解、回覆或標記時會離開頁面；自傳文字還沒儲存就先提醒（組員 46531f2）。
(function () {
  var draft = document.querySelector("[data-draft-form]");
  if (!draft) return;
  function changed() {
    return Array.prototype.some.call(
      document.querySelectorAll('textarea[name^="paragraph_"], textarea[name^="comment_"]'),
      function (field) { return field.value !== field.defaultValue; }
    );
  }
  document.querySelectorAll("[data-comment-form]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (changed() && !window.confirm("自傳文字還沒儲存。現在送出會重新整理頁面，剛才改的字會不見。\n\n要先儲存自傳，請按「取消」；仍要送出請按「確定」。")) {
        event.preventDefault();
      }
    });
  });
})();
