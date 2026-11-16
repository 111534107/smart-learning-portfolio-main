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

/* 學生端 v2：上傳進度（2026-11-13）
   - 送出時改用 XMLHttpRequest 送同一個表單到同一個路由，才能拿到上傳百分比；不改後端。
   - 上傳框的位置換成進度區（不跳出視窗）：上方進度條＋三個步驟（上傳檔案／交給 OCR／開始辨識）。
   - 伺服器回轉址就照著走；沒有轉址（例如檔案不合格）就用原本的表單再送一次，顯示原本的錯誤頁。
   - 瀏覽器不支援或連線失敗時，退回原本的表單送出。 */
(function () {
  "use strict";
  var form = document.querySelector("form[data-sv2-drop-form]");
  if (!form || !window.XMLHttpRequest || !window.FormData) { return; }
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function build(fileName) {
    var box = document.createElement("div");
    box.className = "sv2-progress";
    box.setAttribute("role", "status");
    box.setAttribute("aria-live", "polite");
    box.innerHTML =
      '<div class="sv2-progress__card">' +
      '<p class="sv2-progress__title">正在上傳<span class="sv2-progress__file"></span></p>' +
      '<div class="sv2-progress__bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" aria-label="上傳進度"><i></i></div>' +
      '<p class="sv2-progress__pct">0%</p>' +
      '<ol class="sv2-progress__steps">' +
      '<li data-step="1" class="is-now"><b>1</b><span>上傳檔案</span><em>進行中</em></li>' +
      '<li data-step="2"><b>2</b><span>交給 OCR</span><em>等待</em></li>' +
      '<li data-step="3"><b>3</b><span>開始辨識</span><em>等待</em></li>' +
      '</ol>' +
      '<p class="sv2-progress__hint">請不要關閉這一頁。</p>' +
      '</div>';
    box.querySelector(".sv2-progress__file").textContent = fileName ? "：" + fileName : "";
    // 直接放在上傳框的位置（不跳出視窗）；列表頁沒有上傳框，就放在主內容最上面
    var zone = form.querySelector(".dropzone");
    if (zone) {
      zone.parentElement.insertBefore(box, zone);
      // 上傳框有自己的 display 樣式，hidden 蓋不過，直接用行內樣式收起
      [zone].concat(Array.prototype.slice.call(form.querySelectorAll(".dropzone__status, .dropzone__tools"))).forEach(function (el) { el.style.display = "none"; });
      box.scrollIntoView({ block: "center" });
    } else {
      var main = document.querySelector("main") || document.body;
      main.insertBefore(box, main.firstChild);
      box.scrollIntoView({ block: "center" });
    }
    return box;
  }

  function step(box, n) {
    box.querySelectorAll("[data-step]").forEach(function (li) {
      var k = Number(li.dataset.step);
      li.className = k < n ? "is-done" : (k === n ? "is-now" : "");
      li.querySelector("em").textContent = k < n ? "完成" : (k === n ? "進行中" : "等待");
    });
  }

  function setPct(box, pct) {
    box.querySelector(".sv2-progress__bar i").style.width = pct + "%";
    box.querySelector(".sv2-progress__bar").setAttribute("aria-valuenow", String(pct));
    box.querySelector(".sv2-progress__pct").textContent = pct + "%";
  }

  form.addEventListener("submit", function (event) {
    if (event.defaultPrevented || form.dataset.sv2Sending) { return; }
    var input = form.querySelector('input[type="file"]');
    var file = input && input.files && input.files[0];
    if (!file) { return; }
    event.preventDefault();
    form.dataset.sv2Sending = "1";
    form.querySelectorAll('button[type="submit"]').forEach(function (b) { b.disabled = true; });
    var box = build(file.name);
    var xhr = new XMLHttpRequest();
    xhr.open((form.getAttribute("method") || "post").toUpperCase(), form.action);
    xhr.upload.addEventListener("progress", function (e) {
      if (e.lengthComputable) { setPct(box, Math.min(99, Math.round(e.loaded / e.total * 100))); }
    });
    xhr.upload.addEventListener("load", function () {
      setPct(box, 100);
      step(box, 2);
      box.querySelector(".sv2-progress__title").firstChild.textContent = "上傳完成，交給 OCR";
      box.classList.add("is-waiting");
    });
    xhr.addEventListener("load", function () {
      step(box, 3);
      var target = xhr.responseURL || "";
      if (target && target !== form.action && xhr.status < 400) {
        window.location.assign(target);
        return;
      }
      // 沒有轉址（例如檔案不合格要回上傳頁顯示錯誤）：改用原本的表單送一次，讓瀏覽器正常顯示那一頁
      // （不用 document.write：會讓頁面腳本重複執行而出錯）
      form.submit();
    });
    xhr.addEventListener("error", function () {
      box.remove();
      var zone = form.querySelector(".dropzone");
      if (zone) { zone.style.display = ""; }
      delete form.dataset.sv2Sending;
      form.submit();
    });
    if (reduce) { box.classList.add("is-reduced"); }
    xhr.send(new FormData(form));
  });
})();
