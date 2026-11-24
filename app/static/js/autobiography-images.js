/* 自傳段落貼上圖片：選檔案或在文字框 Ctrl+V 貼上截圖 → 傳到伺服器 → 縮圖放進該段，按「儲存」才存進這一版。 */
(function () {
  "use strict";
  var form = document.querySelector("[data-draft-form]");
  if (!form) return;
  var token = function () { var f = form.querySelector("[name=csrf_token]"); return f ? f.value : ""; };

  function say(box, text) { var s = box.querySelector("[data-image-status]"); if (s) s.textContent = text || ""; }

  function addFigure(box, info) {
    var figure = document.createElement("figure");
    figure.className = "bio-images__item";
    figure.setAttribute("data-image", "");
    var img = document.createElement("img"); img.src = info.url; img.alt = "自傳附圖";
    var hidden = document.createElement("input"); hidden.type = "hidden";
    hidden.name = "paragraph_" + box.getAttribute("data-index") + "_image"; hidden.value = info.id;
    var remove = document.createElement("button"); remove.type = "button";
    remove.className = "button button--small button--quiet"; remove.setAttribute("data-image-remove", ""); remove.textContent = "移除";
    figure.appendChild(img); figure.appendChild(hidden); figure.appendChild(remove);
    var label = box.querySelector("label");
    box.insertBefore(figure, label);
  }

  function upload(box, file) {
    if (box.querySelectorAll("[data-image]").length >= 6) { say(box, "每段最多 6 張圖片。"); return; }
    var data = new FormData();
    data.append("csrf_token", token());
    data.append("image", file, file.name || "貼上的圖片.png");
    say(box, "上傳中…");
    fetch(box.getAttribute("data-upload-url"), { method: "POST", body: data, credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) { say(box, res.body.error || "上傳失敗，請再試一次。"); return; }
        addFigure(box, res.body);
        say(box, "已加入，按「儲存」後才會存進這一版。");
      })
      .catch(function () { say(box, "網路不穩，上傳失敗，請再試一次。"); });
  }

  form.addEventListener("change", function (event) {
    var input = event.target.closest("[data-image-file]");
    if (!input) return;
    var box = input.closest("[data-image-box]");
    Array.prototype.forEach.call(input.files, function (file) { upload(box, file); });
    input.value = "";
  });

  form.addEventListener("click", function (event) {
    var button = event.target.closest("[data-image-remove]");
    if (!button) return;
    var figure = button.closest("[data-image]");
    var box = figure.closest("[data-image-box]");
    figure.remove();
    say(box, "已移除，按「儲存」後生效（舊版本仍保留這張圖）。");
  });

  form.addEventListener("paste", function (event) {
    var area = event.target.closest && event.target.closest("textarea");
    if (!area) return;
    var section = area.closest(".draft__paragraph");
    var box = section && section.querySelector("[data-image-box]");
    var items = (event.clipboardData && event.clipboardData.items) || [];
    var found = false;
    Array.prototype.forEach.call(items, function (item) {
      if (item.kind === "file" && item.type.indexOf("image/") === 0) {
        var file = item.getAsFile();
        if (file && box) { upload(box, file); found = true; }
      }
    });
    if (found) event.preventDefault();  // 貼的是圖片時不要再貼進文字；純文字照常貼上
  });
})();
