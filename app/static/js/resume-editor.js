/* 實習履歷編輯頁（2026-11-18）：左邊像文件的頁面，右邊「我的資料」卡片與圖片收納匣。
   - 卡片（證照、經歷）可以拖到左邊的格子；也可以用卡片上的選單與勾選（取消勾選＝不放）。
   - 圖片：貼上（Ctrl+V）、拖進來、選檔案，先進收納匣；點一張選起來，再按格子的「放選好的圖」，或直接拖到格子。
   - 所有放進去的東西都是表單欄位，按「儲存草稿」或「下載」才算數。 */
(function () {
  "use strict";
  var form = document.querySelector("[data-resume-form]");
  if (!form) return;
  var uploadUrl = form.getAttribute("data-upload-url");
  var viewTemplate = form.getAttribute("data-view-url");
  var token = function () { return form.querySelector("[name=csrf_token]").value; };
  var tray = form.querySelector("[data-tray]");
  var trayStatus = form.querySelector("[data-tray-status]");
  var selected = null;     // 收納匣裡選起來的圖 {id, url}
  var activeSlot = null;   // 最後點過的格子（貼上時直接放進去）

  function say(text) { if (trayStatus) trayStatus.textContent = text || ""; }
  function viewUrl(id) { return viewTemplate.replace("IMAGE_ID", id); }

  // ---------- 卡片：拖到格子 ----------
  var dragging = null;
  form.querySelectorAll("[data-card]").forEach(function (card) {
    card.addEventListener("dragstart", function (event) {
      dragging = { type: "card", kind: card.getAttribute("data-card"), el: card };
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("text/plain", card.getAttribute("data-label") || "");
    });
    card.addEventListener("dragend", function () { dragging = null; });
  });

  function appendText(section, text) {
    var area = form.querySelector("#text-" + section);
    if (!area || !text) return;
    if (area.value.indexOf(text) >= 0) return;  // 同一段不重複放
    area.value = area.value.trim() ? area.value.replace(/\s+$/, "") + "\n" + text : text;
    area.dispatchEvent(new Event("input", { bubbles: true }));
    area.style.height = "auto"; area.style.height = area.scrollHeight + "px";
  }
  form.addEventListener("click", function (event) {
    var put = event.target.closest("[data-para-put]");
    if (!put) return;
    var card = put.closest("[data-card=para]");
    appendText(card.querySelector("[data-para-select]").value, card.getAttribute("data-text") || "");
  });
  form.querySelectorAll("[data-bio-area]").forEach(function (area) {  // 自傳格子依內容長高，不出現捲軸
    var grow = function () { area.style.height = "auto"; area.style.height = area.scrollHeight + "px"; };
    area.addEventListener("input", grow); grow();
  });

  function place(zone, card) {
    var key = zone.getAttribute("data-zone");
    var box = card.querySelector("[data-pick-box]");
    if (!box && card.getAttribute("data-card") !== "para") return;
    if (key.indexOf("col:") === 0 && card.getAttribute("data-card") === "cred") {
      var select = card.querySelector("[data-col-select]");
      select.value = key.slice(4);
      box.checked = true;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    } else if (key.indexOf("sec:") === 0 && card.getAttribute("data-card") !== "para") {
      var sec = card.querySelector("[data-sec-select]");
      if (sec) { sec.value = key.slice(4); sec.dispatchEvent(new Event("change", { bubbles: true })); }
      box.checked = true;
      box.dispatchEvent(new Event("change", { bubbles: true }));
    } else if (key.indexOf("sec:") === 0 && card.getAttribute("data-card") === "para") {
      appendText(key.slice(4), card.getAttribute("data-text") || "");
    } else if (key === "name") {
      var input = zone.querySelector("[data-name-input]");
      if (input) { input.value = card.getAttribute("data-label") || ""; input.dispatchEvent(new Event("input", { bubbles: true })); }
    }
    renderColumns();
  }

  function bindZone(zone) {
    zone.addEventListener("dragover", function (event) {
      if (dragging || (event.dataTransfer && Array.prototype.indexOf.call(event.dataTransfer.types, "Files") >= 0)) {
        event.preventDefault(); zone.classList.add("is-over");
      }
    });
    zone.addEventListener("dragleave", function () { zone.classList.remove("is-over"); });
    zone.addEventListener("drop", function (event) {
      zone.classList.remove("is-over");
      if (dragging && dragging.type === "card") { event.preventDefault(); place(zone, dragging.el); }
    });
  }
  form.querySelectorAll("[data-zone]").forEach(bindZone);

  // 相關證照：每一格都是輸入框（學生可以自己打字，例如國際證照）；右邊的證照卡勾選或拖進來時，把名稱填進該欄第一個空格
  function cellInputs(column) {
    return Array.prototype.slice.call(form.querySelectorAll('[data-cert-cell^="' + column + ':"] [data-cert-input]'));
  }
  function syncCard(card) {
    var id = card.getAttribute("data-cred-id");
    var box = card.querySelector("[data-pick-box]");
    var select = card.querySelector("[data-col-select]");
    var name = card.getAttribute("data-label");
    form.querySelectorAll('[data-from-card="' + id + '"]').forEach(function (input) { input.value = ""; input.removeAttribute("data-from-card"); });
    if (!box.checked) return;
    var inputs = cellInputs(select.value);
    if (inputs.some(function (input) { return input.value.trim() === name; })) return;
    var target = inputs.filter(function (input) { return !input.value.trim(); })[0];
    if (target) { target.value = name; target.setAttribute("data-from-card", id); }
    else if (inputs.length) { var last = inputs[inputs.length - 1]; last.value = last.value + "、" + name; }  // 超過 6 格併在最後一格
  }
  function renderColumns() { /* 舊名稱保留：格子現在是輸入框，不再重畫 */ }
  form.querySelectorAll("[data-card='cred']").forEach(function (card) {  // 頁面一載入，預填的格子對上哪張卡就記起來，取消勾選才清得掉
    var box = card.querySelector("[data-pick-box]"), select = card.querySelector("[data-col-select]");
    if (!box.checked) return;
    cellInputs(select.value).forEach(function (input) {
      if (input.value.trim() === card.getAttribute("data-label") && !input.hasAttribute("data-from-card")) input.setAttribute("data-from-card", card.getAttribute("data-cred-id"));
    });
  });
  form.addEventListener("change", function (event) {
    var sec = event.target.closest("[data-sec-select]");
    if (sec) {  // 讓舊的「會列在這一段後面」預覽跟著新選的段落
      var box = sec.closest("[data-card]").querySelector("[data-pick-box]");
      box.setAttribute("data-section", sec.value);
      box.dispatchEvent(new Event("change", { bubbles: true }));
    }
    var credCard = event.target.closest("[data-card='cred']");
    if (credCard) syncCard(credCard);
  });

  // ---------- 自傳：把系統裡的自傳放進最後點過的格子 ----------
  var lastArea = null;
  form.querySelectorAll("[data-bio-area]").forEach(function (area) {
    area.addEventListener("focus", function () { lastArea = area; });
  });
  form.addEventListener("click", function (event) {
    var put = event.target.closest("[data-bio-put]");
    if (!put) return;
    var area = lastArea || form.querySelector("[data-bio-area]");
    var text = put.getAttribute("data-bio-text") || "";
    area.value = area.value ? area.value + "\n" + text : text;
    area.dispatchEvent(new Event("input", { bubbles: true }));
    area.focus();
  });

  // ---------- 圖片 ----------
  function upload(file) {
    var data = new FormData();
    data.append("csrf_token", token());
    data.append("image", file, file.name || "貼上的圖片.png");
    say("上傳中…");
    return fetch(uploadUrl, { method: "POST", body: data, credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) { say(res.body.error || "上傳失敗，請再試一次。"); return null; }
        say("已加到收納匣。");
        return { id: res.body.id, url: res.body.url, width: res.body.width, height: res.body.height };
      })
      .catch(function () { say("網路不穩，上傳失敗，請再試一次。"); return null; });
  }

  function addToTray(info) {
    var button = document.createElement("button");
    button.type = "button"; button.className = "rz-tray__item"; button.draggable = true;
    button.setAttribute("data-image-id", info.id);
    var img = document.createElement("img"); img.src = info.url; img.alt = "收納匣的圖片";
    button.appendChild(img);
    button.addEventListener("click", function () { select(info, button); });
    button.addEventListener("dragstart", function (event) {
      dragging = { type: "image", info: info };
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("text/plain", info.id);
    });
    button.addEventListener("dragend", function () { dragging = null; });
    tray.appendChild(button);
    select(info, button);
  }
  function select(info, button) {
    selected = info;
    tray.querySelectorAll(".is-selected").forEach(function (el) { el.classList.remove("is-selected"); });
    button.classList.add("is-selected");
  }

  function fillSlot(slot, info) {
    slot.querySelector("[data-slot-input]").value = info ? info.id : "";
    var view = slot.querySelector("[data-slot-view]");
    view.innerHTML = "";
    if (info) { var img = document.createElement("img"); img.src = info.url || viewUrl(info.id); img.alt = "已放進格子的圖片"; view.appendChild(img); }
    else { var span = document.createElement("span"); span.className = "small muted"; span.textContent = "（不放）"; view.appendChild(span); }
  }

  async function handleFiles(files, then, pdfMode) {
    for (var file of Array.from(files)) {
      if (pdfMode && (file.type === "application/pdf" || /\.pdf$/i.test(file.name))) {
        var data = new FormData();
        data.append("csrf_token", token());
        data.append("pdf", file);
        say("正在讀取 PDF…");
        try {
          var response = await fetch(form.dataset.pdfUrl, { method: "POST", body: data, credentials: "same-origin" });
          if (response.status === 413) { say("PDF 檔案不可超過 6 MB。"); continue; }
          var result = await response.json();
          if (!response.ok) { say(result.error || "PDF 上傳失敗。"); continue; }
          result.pages.forEach(addToTray);
          say("已將 " + result.pages.length + " 頁 PDF 加入收納匣。");
          if (then && pdfMode === "single") {
            await then(result.pages[0]);
            if (result.pages.length > 1) say("已放入第一頁，其餘頁面可從收納匣選用。");
          } else if (then) {
            for (var page of result.pages) await then(page);
          }
        } catch (error) { say("PDF 上傳失敗，請再試一次。"); }
      } else if (file.type.indexOf("image/") === 0) {
        var info = await upload(file);
        if (info) { addToTray(info); if (then) await then(info); }
      } else {
        say(pdfMode ? "請選擇圖片或 PDF。" : "請選擇 JPG、PNG 或 WEBP 圖片。");
      }
    }
  }

  if (tray) {
    form.querySelector("[data-tray-file]").addEventListener("change", function (event) {
      handleFiles(event.target.files); event.target.value = "";
    });
    tray.addEventListener("dragover", function (event) { event.preventDefault(); tray.classList.add("is-over"); });
    tray.addEventListener("dragleave", function () { tray.classList.remove("is-over"); });
    tray.addEventListener("drop", function (event) {
      tray.classList.remove("is-over");
      if (event.dataTransfer.files && event.dataTransfer.files.length) { event.preventDefault(); handleFiles(event.dataTransfer.files); }
    });
  }

  function bindSlot(slot) {
    var pdfMode = slot.querySelector("[data-slot-file]").accept.includes("application/pdf") ? "single" : null;
    slot.addEventListener("click", function () { activeSlot = slot; form.querySelectorAll(".is-active-slot").forEach(function (el) { el.classList.remove("is-active-slot"); }); slot.classList.add("is-active-slot"); });
    slot.addEventListener("dragover", function (event) { event.preventDefault(); slot.classList.add("is-over"); });
    slot.addEventListener("dragleave", function () { slot.classList.remove("is-over"); });
    slot.addEventListener("drop", function (event) {
      slot.classList.remove("is-over");
      event.preventDefault(); event.stopPropagation();
      if (dragging && dragging.type === "image") { fillSlot(slot, dragging.info); return; }
      if (event.dataTransfer.files && event.dataTransfer.files.length) { handleFiles([event.dataTransfer.files[0]], function (info) { fillSlot(slot, info); }, pdfMode); }
    });
    slot.querySelector("[data-slot-put]").addEventListener("click", function () {
      if (!selected) { say("先在右邊的收納匣點一張圖。"); return; }
      fillSlot(slot, selected);
    });
    slot.querySelector("[data-slot-file]").addEventListener("change", function (event) {
      handleFiles([event.target.files[0]].filter(Boolean), function (info) { fillSlot(slot, info); }, pdfMode); event.target.value = "";
    });
    slot.querySelector("[data-slot-clear]").addEventListener("click", function () { fillSlot(slot, null); });
  }
  form.querySelectorAll("[data-image-slot]").forEach(bindSlot);
  var bioMode = form.querySelector("[data-bio-mode]");
  if (bioMode) {
    function updateBioMode() {
      form.querySelectorAll("[data-bio-format]").forEach(function (panel) {
        panel.hidden = panel.dataset.bioFormat !== bioMode.value;
      });
    }
    bioMode.addEventListener("change", updateBioMode);
    updateBioMode();
  }

  // 貼上截圖：文字框裡貼文字照常；貼的是圖片就進收納匣，並放進最後點過的格子
  document.addEventListener("paste", function (event) {
    var items = (event.clipboardData && event.clipboardData.items) || [];
    var files = [];
    Array.prototype.forEach.call(items, function (item) { if (item.kind === "file" && item.type.indexOf("image/") === 0) files.push(item.getAsFile()); });
    if (!files.length || !form.contains(event.target)) return;
    event.preventDefault();
    handleFiles(files, function (info) { if (activeSlot) fillSlot(activeSlot, info); });
  });



  // ---------- 小助手：說給它聽，整理成「家庭生活」那一段 ----------
  var familyGo = form.querySelector("[data-family-go]");
  if (familyGo) {
    familyGo.addEventListener("click", function () {
      var raw = form.querySelector("[data-family-raw]");
      var status = form.querySelector("[data-family-status]");
      if (!raw.value.trim()) { status.textContent = "先說說你的家庭生活。"; raw.focus(); return; }
      var data = new FormData(); data.append("csrf_token", token()); data.append("raw", raw.value);
      status.textContent = "小助手整理中…"; familyGo.disabled = true;
      fetch(form.getAttribute("data-family-url"), { method: "POST", body: data, credentials: "same-origin" })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
        .then(function (res) {
          if (!res.ok) { status.textContent = res.body.error || "整理失敗，請再試一次。"; return; }
          var area = form.querySelector("#text-family");
          area.value = area.value.trim() ? area.value.replace(/\s+$/, "") + "\n" + res.body.text : res.body.text;
          area.dispatchEvent(new Event("input", { bubbles: true }));
          area.scrollIntoView({ block: "center", behavior: "smooth" });
          status.textContent = res.body.note;
        })
        .catch(function () { status.textContent = "網路不穩，請再試一次。"; })
        .then(function () { familyGo.disabled = false; });
    });
  }

  // 資管科小助手（右下角對話）整理好家庭生活時，直接填進格子
  window.addEventListener("assistant-fill", function (event) {
    var fill = event.detail || {};
    if (fill.target !== "family" || !fill.text) return;
    var area = form.querySelector("#text-family");
    if (!area) return;
    area.value = area.value.trim() ? area.value.replace(/\s+$/, "") + "\n" + fill.text : fill.text;
    area.dispatchEvent(new Event("input", { bubbles: true }));
    var status = form.querySelector("[data-family-status]");
    if (status) status.textContent = "小助手已把整理好的家庭生活放進格子，按「儲存草稿」才會存檔。";
    area.classList.add("rz-flash");
    setTimeout(function () { area.classList.remove("rz-flash"); }, 1800);
  });


  // ---------- 我上傳的原始檔：轉成圖片放進收納匣；證照卡可以一鍵放進證照圖片 ----------
  var importUrl = form.getAttribute("data-import-url") || "";
  function importDoc(id) {
    var data = new FormData(); data.append("csrf_token", token());
    say("轉成圖片中…");
    return fetch(importUrl.replace(/\/0$/, "/" + id), { method: "POST", body: data, credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) { say(res.body.error || "轉換失敗，請改用截圖貼上。"); return null; }
        say("已加到收納匣。");
        return { id: res.body.id, url: res.body.url, width: res.body.width, height: res.body.height };
      })
      .catch(function () { say("網路不穩，請再試一次。"); return null; });
  }
  form.addEventListener("click", function (event) {
    var docButton = event.target.closest("[data-doc-import]");
    if (docButton) { importDoc(docButton.getAttribute("data-doc-import")).then(function (info) { if (info) addToTray(info); }); return; }
    var credButton = event.target.closest("[data-cred-doc]");
    if (!credButton) return;
    var card = credButton.closest("[data-card='cred']");
    importDoc(credButton.getAttribute("data-cred-doc")).then(function (info) {
      if (!info) return;
      addToTray(info);
      var grid = form.querySelector("[data-grid=certimg]");
      var slotFree = function () {
        return Array.prototype.slice.call(grid.querySelectorAll("[data-image-slot]")).filter(function (slot) { return !slot.querySelector("[data-slot-input]").value; })[0];
      };
      var slot = slotFree();
      if (!slot) { grid.querySelector("[data-grid-add='1']").click(); slot = slotFree(); }
      if (!slot) return;
      fillSlot(slot, info);
      var nameInput = slot.closest("[data-zone=name]").querySelector("[data-name-input]");
      if (nameInput && !nameInput.value.trim()) nameInput.value = card.getAttribute("data-label") || "";
      say("已把「" + (card.getAttribute("data-label") || "證照") + "」的原檔放進證照圖片。");
    });
  });
  form.querySelectorAll("[data-include]").forEach(function (box) {  // 「這一頁放進履歷」：取消勾選就收起來，下載時整頁拿掉
    var wrap = box.closest(".rz-pagewrap");
    var apply = function () { wrap.classList.toggle("is-excluded", !box.checked); };
    box.addEventListener("change", apply); apply();
  });


  // ---------- 拿掉不需要的格子（沒有那麼多證照或競賽）：證照圖片、競賽一格一格拿，相關證照一列一列調 ----------
  function renumberGrid(grid) {
    var kind = grid.getAttribute("data-grid");
    var body = grid.querySelector("[data-grid-body]");
    var cells = Array.prototype.slice.call(body.querySelectorAll("td"));
    cells.forEach(function (cell, i) {
      var hidden = cell.querySelector("[data-slot-input]");
      if (hidden) hidden.name = kind + "_image_" + i;
      var text = cell.querySelector("[data-name-input]");
      if (text) text.name = kind === "certimg" ? "certimg_name_" + i : "contest_caption_" + i;
      var label = (kind === "certimg" ? "證照圖片 " : "競賽圖片 ") + (i + 1);
      var span = cell.querySelector("[data-slot-view] span"); if (span) span.textContent = label;
    });
    body.innerHTML = "";
    cells.forEach(function (cell, i) {
      var row = body.lastElementChild;
      if (!row || row.children.length >= 2) { row = document.createElement("tr"); body.appendChild(row); }
      row.appendChild(cell);
    });
    grid.querySelector("[data-grid-count]").value = cells.length;
  }
  form.addEventListener("click", function (event) {
    var remove = event.target.closest("[data-grid-remove]");
    if (!remove) return;
    var grid = remove.closest("[data-grid]");
    remove.closest("td").remove();
    renumberGrid(grid);
    say("已拿掉這一格；全部拿光，下載時這張表就不會出現在履歷。");
  });

  var certRowsInput = form.querySelector("[data-certrows]");
  if (certRowsInput) {
    var certBody = form.querySelector("[data-cert-cell]").closest("tbody") || form.querySelector("[data-cert-cell]").closest("table");
    var certColumns = [];
    form.querySelectorAll("[data-cert-cell$=':0']").forEach(function (cell) { certColumns.push(cell.getAttribute("data-cert-cell").split(":")[0]); });
    var certLabels = {};
    form.querySelectorAll("[data-cert-cell$=':0'] [data-cert-input]").forEach(function (input) { certLabels[input.name.split("_")[1]] = input.getAttribute("aria-label").replace(/ 第 .*$/, ""); });
    form.querySelector("[data-certrow-add]").addEventListener("click", function () {
      var n = parseInt(certRowsInput.value, 10);
      if (n >= 9) { say("相關證照最多 9 列（再多履歷表會擠到第二頁）；更多的請併在最後一格。"); return; }
      var tr = document.createElement("tr");
      certColumns.forEach(function (col) {
        var td = document.createElement("td");
        td.className = "rz-zone rz-certcell"; td.setAttribute("data-zone", "col:" + col); td.setAttribute("data-cert-cell", col + ":" + n);
        var input = document.createElement("input");
        input.className = "rz-input rz-cellinput"; input.name = "cert_" + col + "_" + n; input.maxLength = 120;
        input.setAttribute("data-cert-input", ""); input.setAttribute("aria-label", (certLabels[col] || col) + " 第 " + (n + 1) + " 格");
        td.appendChild(input); tr.appendChild(td); bindZone(td);
      });
      var lastCell = form.querySelector("[data-cert-cell$=':" + (n - 1) + "']");
      lastCell.closest("tr").insertAdjacentElement("afterend", tr);
      certRowsInput.value = n + 1;
    });
    form.querySelector("[data-certrow-remove]").addEventListener("click", function () {
      var n = parseInt(certRowsInput.value, 10);
      if (n <= 1) { say("至少留一列。"); return; }
      var row = form.querySelector("[data-cert-cell$=':" + (n - 1) + "']").closest("tr");
      var filled = Array.prototype.some.call(row.querySelectorAll("[data-cert-input]"), function (i) { return i.value.trim(); });
      if (filled && !window.confirm("最後一列有填東西，確定拿掉？")) return;
      row.remove(); certRowsInput.value = n - 1;
    });
  }


  // ---------- 手機：「我的資料」收成底部抽屜，捲到哪一頁就顯示那一頁用得到的卡片 ----------
  var side = form.querySelector("[data-side]");
  var sideToggle = side && side.querySelector("[data-side-toggle]");
  if (side && sideToggle) {
    var PAGE_NAMES = { basic: "履歷表", bio: "自傳", transcript: "成績單", cert: "證照", contest: "競賽", absence: "缺曠記錄" };
    var hint = side.querySelector("[data-side-hint]");
    var setFocus = function (key) {
      side.setAttribute("data-focus", key);
      if (hint) hint.textContent = PAGE_NAMES[key] ? "・" + PAGE_NAMES[key] : "";
    };
    sideToggle.addEventListener("click", function () {
      var open = !side.classList.contains("is-open");
      side.classList.toggle("is-open", open);
      sideToggle.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && side.classList.contains("is-open") && window.matchMedia("(max-width: 1100px)").matches) {
        side.classList.remove("is-open"); sideToggle.setAttribute("aria-expanded", "false");
      }
    });
    // 捲到哪一頁：看每一頁在畫面中露出多少（以畫面高度計），露最多的就是目前這一頁；用捲動事件算，比觀察器穩定
    var pages = Array.prototype.slice.call(form.querySelectorAll("[data-focus-page]"));
    var ticking = false;
    var measure = function () {
      ticking = false;
      var viewport = window.innerHeight, best = null, bestVisible = 0;
      pages.forEach(function (page) {
        var rect = page.getBoundingClientRect();
        var visible = Math.max(0, Math.min(rect.bottom, viewport) - Math.max(rect.top, 0));
        if (visible > bestVisible) { bestVisible = visible; best = page.getAttribute("data-focus-page"); }
      });
      if (best) setFocus(best);
    };
    var schedule = function () { if (!ticking) { ticking = true; window.setTimeout(measure, 80); } };
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    measure();
  }

  // ---------- 證照、競賽：格子不夠就新增（一格或一列兩格） ----------
  form.querySelectorAll("[data-grid]").forEach(function (grid) {
    var kind = grid.getAttribute("data-grid");
    var body = grid.querySelector("[data-grid-body]");
    var count = grid.querySelector("[data-grid-count]");
    var template = grid.querySelector("[data-grid-template]");
    var MAX = 40;
    function addCell() {
      var index = parseInt(count.value, 10);
      if (index >= MAX) { say("最多 " + MAX + " 格。"); return false; }
      var html = template.innerHTML.replace(/99999/g, String(index)).replace(/ 100000/g, " " + (index + 1));
      var holder = document.createElement("tr"); holder.innerHTML = html;
      var cell = holder.querySelector("td");
      var label = (kind === "certimg" ? "證照圖片 " : "競賽圖片 ") + (index + 1);
      var view = cell.querySelector("[data-slot-view] span"); if (view) view.textContent = label;
      var row = body.lastElementChild;
      if (!row || row.children.length >= 2) { row = document.createElement("tr"); body.appendChild(row); }
      row.appendChild(cell);
      count.value = index + 1;
      bindSlot(cell.querySelector("[data-image-slot]"));
      bindZone(cell);
      return true;
    }
    grid.querySelectorAll("[data-grid-add]").forEach(function (button) {
      button.addEventListener("click", function () {
        var n = parseInt(button.getAttribute("data-grid-add"), 10);
        for (var k = 0; k < n; k++) { if (!addCell()) break; }
      });
    });
  });

  // ---------- 成績單：多張圖（學校的成績單是橫的，放進直式 A4 要轉直） ----------
  function rotateRemote(box, id) {
    var url = (box.getAttribute("data-rotate-url") || "").replace("IMAGE_ID", id);
    var data = new FormData(); data.append("csrf_token", token());
    return fetch(url, { method: "POST", body: data, credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) { if (!res.ok) { say(res.body.error || "轉向失敗。"); return null; } return res.body; })
      .catch(function () { say("網路不穩，轉向失敗。"); return null; });
  }
  form.querySelectorAll("[data-multi]").forEach(function (box) {
    var name = box.getAttribute("data-multi"), max = parseInt(box.getAttribute("data-max"), 10) || 4;
    function addFigure(info) {
      var figure = document.createElement("figure"); figure.className = "rz-multi__item";
      var img = document.createElement("img"); img.src = info.url || viewUrl(info.id); img.alt = "成績單";
      var input = document.createElement("input"); input.type = "hidden"; input.name = name; input.value = info.id;
      var tools = document.createElement("span"); tools.className = "rz-multi__tools";
      var rotate = document.createElement("button"); rotate.type = "button"; rotate.className = "button button--small button--line";
      rotate.setAttribute("data-multi-rotate", ""); rotate.textContent = "轉 90 度";
      var remove = document.createElement("button"); remove.type = "button"; remove.className = "button button--small button--quiet";
      remove.setAttribute("data-multi-remove", ""); remove.textContent = "不放";
      tools.appendChild(rotate); tools.appendChild(remove);
      figure.appendChild(img); figure.appendChild(input); figure.appendChild(tools); box.appendChild(figure);
    }
    var pending = 0;
    async function add(info) {
      if (box.querySelectorAll(".rz-multi__item").length + pending >= max) {
        say("成績單最多 " + max + " 頁，其餘頁面留在收納匣。"); return;
      }
      pending += 1;
      try {
        var turned = info.width > info.height ? await rotateRemote(box, info.id) : null;
        addFigure(turned || info);
      } finally {
        pending -= 1;
      }
    }
    form.querySelector("[data-multi-put='" + name + "']").addEventListener("click", function () {
      if (!selected) { say("先在右邊的收納匣點一張圖。"); return; } add(selected);
    });
    form.querySelector("[data-multi-file='" + name + "']").addEventListener("change", function (event) {
      handleFiles(event.target.files, add, "multiple"); event.target.value = "";
    });
    box.addEventListener("click", function (event) {
      var r = event.target.closest("[data-multi-remove]");
      if (r) { r.closest(".rz-multi__item").remove(); return; }
      var t = event.target.closest("[data-multi-rotate]");
      if (!t) return;
      var figure = t.closest(".rz-multi__item");
      rotateRemote(box, figure.querySelector("input").value).then(function (turned) {
        if (!turned) return;
        figure.querySelector("input").value = turned.id;
        figure.querySelector("img").src = turned.url;
      });
    });
  });

  // ---------- 缺曠記錄：自動填入與格式化 ---------- 
  var absencePage = form.querySelector("[data-focus-page='absence']");
  if (absencePage) {
    var absenceStatus = absencePage.querySelector("[data-absence-status]");
    var absenceSuccess = absencePage.querySelector("[data-absence-success]");
    var absenceRange = absencePage.querySelector("[name='abs_range']");
    var absenceHours = absencePage.querySelectorAll("[data-absence-hour]");

    function formatHours(value) {
      var digits = String(value == null ? "" : value).replace(/[^\d]/g, "");
      return digits ? digits + "節" : "";
    }
    absenceHours.forEach(function (input) {
      input.addEventListener("input", function () {
        input.value = input.value.replace(/[^\d]/g, "");
      });
      input.addEventListener("blur", function () {
        input.value = formatHours(input.value);
      });
    });

    function setAbsenceStatus(text) {
      if (absenceStatus) absenceStatus.textContent = text || "";
      if (absenceSuccess) absenceSuccess.textContent = "";
    }
    function applyAbsence(body) {
      if (!body || !Array.isArray(body.rows) || body.rows.length !== 8) {
        setAbsenceStatus("回應格式不完整，請再試一次。");
        return false;
      }
      for (var i = 0; i < 8; i++) {
        var input = form.querySelector("[name='abs_" + i + "']");
        if (input) input.value = formatHours(body.rows[i]);
      }
      if (body.range) {
        var currentRange = absenceRange ? absenceRange.value.trim() : "";
        if (!currentRange) {
          absenceRange.value = body.range;
        } else if (currentRange !== body.range && !window.confirm("查詢區間已有值，要覆蓋成「" + body.range + "」嗎？")) {
          // 保留原本的查詢區間
        } else if (currentRange !== body.range) {
          absenceRange.value = body.range;
        }
      }
      if (absenceStatus) absenceStatus.textContent = "";
      if (absenceSuccess) absenceSuccess.textContent = "已自動填入，請對照截圖確認，讀錯的格子直接修改";
      return true;
    }
    function readResponse(response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        return { ok: response.ok, status: response.status, body: body };
      });
    }

    var fileInput = absencePage.querySelector("[data-absence-file]");
    if (fileInput) {
      fileInput.addEventListener("change", async function () {
        var file = fileInput.files && fileInput.files[0];
        if (!file) return;
        var data = new FormData();
        data.append("file", file);
        data.append("csrf_token", token());
        setAbsenceStatus("正在讀取缺曠資料…");
        try {
          var response = await fetch("/student/internship-resume/absence/read", {
            method: "POST", body: data, credentials: "same-origin"
          });
          var result = await readResponse(response);
          if (!result.ok) {
            setAbsenceStatus(result.body.error || "讀取失敗，請再試一次。");
          } else {
            applyAbsence(result.body);

            //沿用既有 abs_image 圖片／PDF slot 上傳機制，檔案不另傳到其他網址。
            var slotFile = absencePage.querySelector("[data-slot-file]");
            if (slotFile && typeof DataTransfer !== "undefined") {
              try {
                var transfer = new DataTransfer();
                transfer.items.add(file);
                slotFile.files = transfer.files;
                slotFile.dispatchEvent(new Event("change", { bubbles: true }));
              } catch (error) {
                setAbsenceStatus("資料已讀取，但圖片／PDF 未能放進截圖欄位，請使用下方「選圖片或 PDF」。");
              }
            }
          }
        } catch (error) {
          setAbsenceStatus("網路不穩或讀取失敗，原本的值不變。");
        } finally {
          fileInput.value = "";
        }
      });
    }

    var savedButton = absencePage.querySelector("[data-absence-saved]");
    if (savedButton) {
      savedButton.addEventListener("click", async function () {
        setAbsenceStatus("正在讀取已登錄合計…");
        try {
          var response = await fetch("/student/internship-resume/absence/saved", {
            method: "GET", credentials: "same-origin"
          });
          var result = await readResponse(response);
          if (!result.ok) {
            setAbsenceStatus(result.body.error || (result.status === 404 ? "找不到已登錄的缺曠資料。" : "讀取失敗，請再試一次。"));
            return;
          }
          applyAbsence(result.body);
        } catch (error) {
          setAbsenceStatus("網路不穩或讀取失敗，原本的值不變。");
        }
      });
    }

    var totalHelp = absencePage.querySelector(".rz-abs-total-help");
    if (totalHelp) {
      totalHelp.addEventListener("click", function () {
        var tip = absencePage.querySelector(".rz-abs-total-tip");
        if (tip) tip.classList.toggle("is-visible");
      });
    }
  }

  // ---------- 自傳：一鍵請小助手依勾選資料生成四段 ----------
  var bioGenerate = form.querySelector("[data-bio-generate]");
  if (bioGenerate) {
    var bioStatus = form.querySelector("[data-bio-status]");
    var bioNote = form.querySelector("[data-bio-note]");
    var bioSuccess = form.querySelector("[data-bio-success]");
    bioGenerate.addEventListener("click", function () {
      if (!bioStatus || !bioNote || !bioSuccess) return;
      var generateUrl = form.getAttribute("data-bio-generate-url");
      bioStatus.textContent = "小助手整理中…";
      bioNote.textContent = "";
      bioSuccess.textContent = "";
      bioGenerate.disabled = true;
      var data = new FormData(form);
      fetch(generateUrl, { method: "POST", body: data, credentials: "same-origin" })
        .then(function (response) {
          return response.json().catch(function () { return {}; }).then(function (body) {
            return { ok: response.ok, body: body };
          });
        })
        .then(function (result) {
          if (!result.ok) {
            bioStatus.textContent = result.body.error || "小助手暫時整理失敗，請稍後再試一次。";
            return;
          }
          var body = result.body || {};
          var sections = body.sections || {};
          var hints = body.hints || {};
          var mode = form.querySelector("[data-bio-mode]");
          if (mode && mode.value === "guided") {
            ["family", "study", "skill", "future"].forEach(function (key) {
              var area = form.querySelector('[name="text_' + key + '"]');
              var text = (sections[key] || "").trim();
              if (!area || !text) return;
              if (area.value.trim() && !window.confirm("要用小助手整理的內容取代「" + (key === "family" ? "家庭生活" : key === "study" ? "求學經過及社團活動" : key === "skill" ? "個人專長及簡要經歷" : "未來生涯規劃") + "」原有的內容嗎？")) return;
              area.value = text;
              area.dispatchEvent(new Event("input", { bubbles: true }));
            });
          } else {
            var free = form.querySelector('[name="text_free"]');
            var merged = ["family", "study", "skill", "future"].map(function (key) {
              return (sections[key] || "").trim();
            }).filter(Boolean).join("\n\n");
            if (free && merged) {
              if (free.value.trim() && !window.confirm("要用小助手整理的內容取代自由撰寫原有的內容嗎？")) {
                bioStatus.textContent = "已保留原有自由撰寫內容。";
              } else {
                free.value = merged;
                free.dispatchEvent(new Event("input", { bubbles: true }));
              }
            }
          }
          form.querySelectorAll("[data-bio-hint]").forEach(function (hint) {
            hint.textContent = hints[hint.getAttribute("data-bio-hint")] || "";
          });
          bioNote.textContent = body.note || "";
          bioStatus.textContent = "";
          bioSuccess.textContent = "已整理，請逐段看過再改成你自己的話，改好按「儲存草稿」。";
          bioGenerate.setAttribute("aria-describedby", "rz-bio-assist-result");
        })
        .catch(function () {
          bioStatus.textContent = "網路不穩或小助手暫時無法使用，請再試一次。";
        })
        .finally(function () {
          bioGenerate.disabled = false;
        });
    });
  }
})();
