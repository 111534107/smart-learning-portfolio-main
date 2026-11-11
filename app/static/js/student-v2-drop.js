/* 學生端 v2：把檔案拖進整個頁面就上傳（成績單、證照頁；2026-11-11）
   - 拖進來時整頁出現「放開就上傳，系統會用 OCR 辨識」。
   - 放開後把檔案放進頁面上原本的上傳表單（form[data-sv2-drop-form]），照原本路由送出，不另寫 API。
   - 一次只收一個檔案（原本的上傳欄位就是單檔）。選檔按鈕照舊可用。 */
(function () {
  "use strict";
  var root = document.documentElement;
  var form = document.querySelector("form[data-sv2-drop-form]");
  if (!form) { return; }
  var input = form.querySelector('input[type="file"]');
  if (!input) {
    // 列表頁的隱藏表單沒有放檔案欄位，這裡補上（名稱與上傳頁相同：file）
    input = document.createElement("input");
    input.type = "file"; input.name = "file"; input.hidden = true; input.tabIndex = -1;
    form.appendChild(input);
  }
  var depth = 0;

  function hasFiles(event) {
    var types = event.dataTransfer && event.dataTransfer.types;
    return !!types && Array.prototype.indexOf.call(types, "Files") !== -1;
  }
  function stop() { depth = 0; root.classList.remove("sv2-dropping"); }

  window.addEventListener("dragenter", function (event) {
    if (!hasFiles(event)) { return; }
    depth += 1;
    root.classList.add("sv2-dropping");
  });
  window.addEventListener("dragleave", function () {
    depth -= 1;
    if (depth <= 0) { stop(); }
  });
  window.addEventListener("dragover", function (event) {
    if (hasFiles(event)) { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }
  });
  window.addEventListener("drop", function (event) {
    if (!hasFiles(event)) { return; }
    event.preventDefault();
    stop();
    var files = event.dataTransfer.files;
    if (!files || !files.length) { return; }
    var holder = new DataTransfer();
    holder.items.add(files[0]);
    input.files = holder.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    var status = form.querySelector(".dropzone__status");
    if (files.length > 1 && status) { status.textContent = "一次上傳一個檔案，先送出「" + files[0].name + "」。"; }
    // 原本的上傳框會檢查大小；超過上限時它會標成錯誤，就不要送出
    var zone = form.querySelector(".dropzone");
    setTimeout(function () {
      if (zone && zone.classList.contains("is-error")) { return; }
      if (form.requestSubmit) { form.requestSubmit(); } else { form.submit(); }
    }, 60);
  });
})();
