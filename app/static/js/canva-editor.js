/**
 * canva-editor.js - 小助手寫自傳 Canva 風格編輯器互動模組
 *
 * 功能亮點：
 * 1. 漸進增強：JS 載入後才加上 .has-canva-editor class，無 JS 時保留傳統整頁段落佈局。
 * 2. 桌機（寬度 ≥ 900px）：左側段落目錄、中間單段編輯、右側紙張式整份即時預覽。
 * 3. 手機（寬度 < 900px）：橫向滑動段落小標籤、首屏直接編輯、編輯／預覽切換。
 * 4. 即時同步：輸入文字即時反映到預覽區與各項字數統計。
 * 5. 錨點支援：支援 #paragraph-N 網址直接切換到對應段落。
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-canva-editor]");
  if (!root) {
    return;
  }

  var form = root.querySelector("[data-draft-form]");
  if (!form) {
    return;
  }

  var paragraphs = Array.prototype.slice.call(root.querySelectorAll(".draft__paragraph"));
  if (!paragraphs.length) {
    return;
  }

  // 啟用 Canva 模式
  root.classList.add("has-canva-editor");

  var totalParagraphs = paragraphs.length;
  var currentIndex = 0;

  // 取得控制項與元素
  var tocButtons = Array.prototype.slice.call(root.querySelectorAll(".canva-toc-btn"));
  var mobileChips = Array.prototype.slice.call(root.querySelectorAll(".canva-chip"));
  var previewItems = Array.prototype.slice.call(root.querySelectorAll("[data-preview-index]"));
  var prevBtn = root.querySelector("[data-canva-prev]");
  var nextBtn = root.querySelector("[data-canva-next]");
  var currentLabel = root.querySelector("[data-canva-current-label]");
  var modeToggles = Array.prototype.slice.call(root.querySelectorAll("[data-canva-mode]"));

  // 字數統計函數（排除空白字元，與 components.js refreshDraft 保持一致）
  function countChars(text) {
    return (text || "").replace(/\s/g, "").length;
  }

  function updateTotalCharCount() {
    var total = 0;
    paragraphs.forEach(function (p) {
      var textarea = p.querySelector("textarea");
      total += countChars(textarea ? textarea.value : "");
    });

    var totalBudget = parseInt(root.getAttribute("data-budget-total"), 10);
    if (!totalBudget || totalBudget < 0) {
      totalBudget = 2200;
    }
    var over = total > totalBudget * 1.2;
    var totalText = "全份 " + total + "／" + totalBudget + " 字";

    root.querySelectorAll("[data-char-total]").forEach(function (el) {
      el.textContent = totalText;
      el.classList.toggle("is-over-budget", over);
      el.setAttribute("aria-label", totalText + (over ? "，超過全份字數警戒線" : ""));
    });
  }

  // 更新各處字數統計與即時預覽文字
  function updateCharCount(index, text) {
    var count = countChars(text);
    var paragraph = paragraphs[index];
    var budget = paragraph ? parseInt(paragraph.getAttribute("data-budget"), 10) : 200;
    if (!budget || budget < 0) {
      budget = 200;
    }
    var countStr = count + "／" + budget + " 字";
    var over = count > budget;

    var tocCount = root.querySelector('[data-canva-toc-count="' + index + '"]');
    if (tocCount) {
      tocCount.textContent = countStr;
    }
    var tocButton = tocButtons[index];
    if (tocButton) {
      tocButton.classList.toggle("is-over-budget", over);
      tocButton.setAttribute("aria-label", (tocButton.textContent || "").replace(/\s+/g, " ").trim() + (over ? "，超過建議字數" : ""));
    }

    var chipCount = root.querySelector('[data-canva-chip-count="' + index + '"]');
    if (chipCount) {
      chipCount.textContent = countStr;
    }
    var chip = mobileChips[index];
    if (chip) {
      chip.classList.toggle("is-over-budget", over);
    }

    var fieldCount = root.querySelector('[data-canva-field-count="' + index + '"]');
    if (fieldCount) {
      fieldCount.textContent = countStr;
      fieldCount.classList.toggle("is-over-budget", over);
    }

    var prevCount = root.querySelector('[data-canva-preview-count="' + index + '"]');
    if (prevCount) {
      prevCount.textContent = countStr;
      prevCount.classList.toggle("is-over-budget", over);
    }

    if (paragraph) {
      paragraph.classList.toggle("is-over-budget", over);
    }
    var warning = root.querySelector('[data-canva-budget-warning="' + index + '"]');
    if (warning) {
      if (over) {
        warning.hidden = false;
        warning.textContent = "⚠ 這段超過建議字數 " + (count - budget) + " 字，評審不會有耐心看完，試著精煉一下";
        warning.classList.add("is-over-budget");
      } else {
        warning.hidden = true;
        warning.textContent = "";
        warning.classList.remove("is-over-budget");
      }
    }

    var prevText = root.querySelector('[data-canva-preview-text="' + index + '"]');
    if (prevText) {
      if ((text || "").trim().length > 0) {
        prevText.textContent = text;
        prevText.classList.remove("is-empty");
      } else {
        prevText.textContent = "（此段目前為空）";
        prevText.classList.add("is-empty");
      }
    }
  }

  // 切換至指定段落（索引 0 起算）
  function switchToParagraph(index, options) {
    options = options || {};
    if (index < 0 || index >= totalParagraphs) {
      return;
    }
    currentIndex = index;

    // 1. 切換編輯區段落顯示
    paragraphs.forEach(function (p, i) {
      var active = (i === currentIndex);
      p.classList.toggle("is-active", active);
      p.setAttribute("aria-hidden", active ? "false" : "true");
    });

    // 2. 更新左側目錄項目選取狀態
    tocButtons.forEach(function (btn) {
      var targetIdx = parseInt(btn.getAttribute("data-canva-target"), 10);
      var active = (targetIdx === currentIndex);
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });

    // 3. 更新手機版橫向段落小標籤
    mobileChips.forEach(function (chip) {
      var targetIdx = parseInt(chip.getAttribute("data-canva-target"), 10);
      var active = (targetIdx === currentIndex);
      chip.classList.toggle("is-active", active);
      chip.setAttribute("aria-selected", active ? "true" : "false");
      if (active && typeof chip.scrollIntoView === "function") {
        try {
          chip.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
        } catch (e) {
          chip.scrollIntoView();
        }
      }
    });

    // 4. 更新右側預覽項目醒目提示
    previewItems.forEach(function (item) {
      var targetIdx = parseInt(item.getAttribute("data-preview-index"), 10);
      var active = (targetIdx === currentIndex);
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-current", active ? "true" : "false");
      if (active && typeof item.scrollIntoView === "function") {
        try {
          item.scrollIntoView({ behavior: "smooth", block: "nearest" });
        } catch (e) {
          item.scrollIntoView();
        }
      }
    });

    // 5. 更新頂部工具列上一段／下一段按鈕狀態
    if (prevBtn) {
      prevBtn.disabled = (currentIndex === 0);
      prevBtn.setAttribute("aria-disabled", currentIndex === 0 ? "true" : "false");
    }
    if (nextBtn) {
      nextBtn.disabled = (currentIndex === totalParagraphs - 1);
      nextBtn.setAttribute("aria-disabled", currentIndex === totalParagraphs - 1 ? "true" : "false");
    }

    // 6. 更新工具列目前段落標示
    if (currentLabel) {
      currentLabel.textContent = "第 " + (currentIndex + 1) + " / " + totalParagraphs + " 段";
    }

    // 7. 聚焦到目前段落的輸入框（並通知 bio-pieces.js 更新游標目標）
    var activeTextarea = paragraphs[currentIndex].querySelector("textarea");
    if (activeTextarea) {
      if (options.focus) {
        activeTextarea.focus();
      }
      // 觸發 focus 事件讓 bio-pieces.js 記錄 last focused area
      activeTextarea.dispatchEvent(new Event("focus", { bubbles: true }));
    }

    // 8. 視需要更新網址 hash
    if (options.updateHash && window.history && window.history.replaceState) {
      window.history.replaceState(null, "", "#paragraph-" + currentIndex);
    }
  }

  // 手機版切換檢視模式（edit 或 preview）
  function setViewMode(mode) {
    root.setAttribute("data-canva-view", mode);
    modeToggles.forEach(function (btn) {
      var active = (btn.getAttribute("data-canva-mode") === mode);
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });

    if (mode === "edit") {
      var activeTextarea = paragraphs[currentIndex].querySelector("textarea");
      if (activeTextarea) {
        setTimeout(function () { activeTextarea.focus(); }, 60);
      }
    }
  }

  // 綁定事件監聽
  // 1. 左側目錄點擊
  tocButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var idx = parseInt(btn.getAttribute("data-canva-target"), 10);
      switchToParagraph(idx, { focus: true, updateHash: true });
    });
  });

  // 2. 手機版橫向標籤點擊
  mobileChips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      var idx = parseInt(chip.getAttribute("data-canva-target"), 10);
      switchToParagraph(idx, { focus: true, updateHash: true });
      if (root.getAttribute("data-canva-view") === "preview") {
        setViewMode("edit");
      }
    });
  });

  // 3. 工具列上一段／下一段按鈕
  if (prevBtn) {
    prevBtn.addEventListener("click", function () {
      if (currentIndex > 0) {
        switchToParagraph(currentIndex - 1, { focus: true, updateHash: true });
      }
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener("click", function () {
      if (currentIndex < totalParagraphs - 1) {
        switchToParagraph(currentIndex + 1, { focus: true, updateHash: true });
      }
    });
  }

  // 4. 段落底下的上一段／下一段連結
  root.querySelectorAll("[data-canva-jump]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var idx = parseInt(btn.getAttribute("data-canva-jump"), 10);
      switchToParagraph(idx, { focus: true, updateHash: true });
    });
  });

  // 5. 即時預覽區點擊段落切換
  previewItems.forEach(function (item) {
    function jumpToParagraph() {
      var idx = parseInt(item.getAttribute("data-preview-index"), 10);
      switchToParagraph(idx, { focus: true, updateHash: true });
      if (window.innerWidth < 900) {
        setViewMode("edit");
      }
    }
    item.addEventListener("click", jumpToParagraph);
    item.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        jumpToParagraph();
      }
    });
  });

  // 6. 手機版檢視模式切換按鈕（編輯／預覽）
  modeToggles.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var mode = btn.getAttribute("data-canva-mode");
      setViewMode(mode);
    });
  });

  // 7. 文字輸入即時同步
  paragraphs.forEach(function (p, idx) {
    var textarea = p.querySelector("textarea");
    if (!textarea) {
      return;
    }

    // 初始化字數統計與預覽
    updateCharCount(idx, textarea.value);

    textarea.addEventListener("input", function () {
      updateCharCount(idx, textarea.value);
      updateTotalCharCount();
    });
  });

  updateTotalCharCount();

  // 資料更新提示：關閉後只對目前校系與目前更新筆數記住。
  var dataUpdate = root.querySelector("[data-budget-data-update]");
  if (dataUpdate) {
    var programId = dataUpdate.getAttribute("data-program-id");
    var updateCount = dataUpdate.getAttribute("data-update-count");
    var storageKey = "student-autobiography:data-updated:" + programId + ":" + updateCount;
    try {
      if (window.localStorage.getItem(storageKey) === "closed") {
        dataUpdate.hidden = true;
      }
    } catch (e) {}

    var closeButton = dataUpdate.querySelector("[data-budget-data-update-close]");
    if (closeButton) {
      closeButton.addEventListener("click", function () {
        dataUpdate.hidden = true;
        try {
          window.localStorage.setItem(storageKey, "closed");
        } catch (e) {}
      });
    }
  }

  // 8. 檢查網址 hash（如 #paragraph-3）
  var initialIndex = 0;
  var hashMatch = window.location.hash.match(/#paragraph-(\d+)/);
  if (hashMatch) {
    var target = parseInt(hashMatch[1], 10);
    if (!isNaN(target) && target >= 0 && target < totalParagraphs) {
      initialIndex = target;
    }
  }

  // 9. 素材庫抽屜響應式狀態控制（手機版預設收合避免長頁面，桌機自動展開維持原樣）
  var materialsDetails = root.querySelector("[data-canva-materials]");
  if (materialsDetails && window.matchMedia) {
    var desktopMq = window.matchMedia("(min-width: 900px)");
    function syncMaterialsState(mq) {
      if (mq.matches) {
        materialsDetails.open = true;
      } else {
        materialsDetails.open = false;
      }
    }
    syncMaterialsState(desktopMq);
    if (typeof desktopMq.addEventListener === "function") {
      desktopMq.addEventListener("change", syncMaterialsState);
    } else if (typeof desktopMq.addListener === "function") {
      desktopMq.addListener(syncMaterialsState);
    }
  }

  // 啟動首個段落
  switchToParagraph(initialIndex, { focus: false, updateHash: false });
})();
