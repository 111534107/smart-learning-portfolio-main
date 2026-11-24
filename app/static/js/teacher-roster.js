/**
 * 導師班級總覽表：純前端排序與即時篩選。
 * - 依欄位排序（桌機點表頭切換升冪／降冪，手機使用下拉選單與升降冪按鈕）
 * - 即時篩選（搜尋學號／姓名、「只看有待確認」勾選）
 */
(function () {
  function initTeacherRoster() {
    var table = document.getElementById("teacher-roster-table");
    if (!table) return;

    var tbody = table.querySelector("tbody");
    if (!tbody) return;

    var searchInput = document.getElementById("roster-search");
    var pendingFilter = document.getElementById("roster-filter-pending");
    var headers = table.querySelectorAll("th.sortable");

    var sortSelect = document.getElementById("roster-sort-select");
    var sortOrderBtn = document.getElementById("roster-sort-order-btn");

    var currentSortKey = null;
    var currentSortDir = "asc";

    function getRows() {
      return Array.prototype.slice.call(tbody.querySelectorAll("tr:not(#roster-empty-row)"));
    }

    // 篩選功能：同時考量文字搜尋與「只看有待確認」
    function applyFilter() {
      var query = searchInput ? searchInput.value.trim().toLowerCase() : "";
      var onlyPending = pendingFilter ? pendingFilter.checked : false;
      var rows = getRows();
      var visibleCount = 0;

      rows.forEach(function (row) {
        var studentNoCell = row.querySelector(".cell-student-no");
        var studentNameCell = row.querySelector(".cell-student-name");
        var pendingCell = row.querySelector(".cell-pending");

        var studentNo = studentNoCell ? studentNoCell.textContent.trim().toLowerCase() : "";
        var studentName = "";
        if (studentNameCell) {
          var nameAttr = studentNameCell.getAttribute("data-name");
          if (nameAttr) {
            studentName = nameAttr.trim().toLowerCase();
          } else {
            var boldEl = studentNameCell.querySelector(".cell-student-name__text") || studentNameCell.querySelector("b");
            studentName = (boldEl ? boldEl.textContent : studentNameCell.textContent).trim().toLowerCase();
          }
        }
        var pendingVal = pendingCell ? parseFloat(pendingCell.getAttribute("data-num") || "0") : 0;

        var textMatch = !query || studentNo.indexOf(query) !== -1 || studentName.indexOf(query) !== -1;
        var pendingMatch = !onlyPending || pendingVal > 0;

        row.hidden = !(textMatch && pendingMatch);
        if (!row.hidden) visibleCount++;
      });

      var emptyRow = document.getElementById("roster-empty-row");
      if (visibleCount === 0) {
        if (!emptyRow) {
          emptyRow = document.createElement("tr");
          emptyRow.id = "roster-empty-row";
          var td = document.createElement("td");
          td.colSpan = 10;
          td.className = "muted text-center py-3";
          td.style.textAlign = "center";
          td.style.padding = "1.5rem";
          td.textContent = "沒有符合篩選條件的學生。";
          emptyRow.appendChild(td);
          tbody.appendChild(emptyRow);
        }
        emptyRow.style.display = "";
      } else if (emptyRow) {
        emptyRow.style.display = "none";
      }
    }

    if (searchInput) {
      searchInput.addEventListener("input", applyFilter);
    }
    if (pendingFilter) {
      pendingFilter.addEventListener("change", applyFilter);
      // 從工作台點「等你確認」進來（?pending=1）時，勾選框一開始就是勾的，名單也要一開始就只剩待確認
      if (pendingFilter.checked) {
        applyFilter();
      }
    }

    // 取得儲存格用以排序的數值或文字
    function getCellValue(row, sortKey, sortType) {
      var cellClass = "cell-" + sortKey.replace(/([A-Z])/g, "-$1").toLowerCase();
      var cell = row.querySelector("." + cellClass);
      if (!cell) return sortType === "number" ? 0 : "";

      if (sortKey === "studentName") {
        var nameAttr = cell.getAttribute("data-name");
        if (nameAttr) return nameAttr.trim();
        var boldEl = cell.querySelector(".cell-student-name__text") || cell.querySelector("b");
        if (boldEl) return boldEl.textContent.trim();
      }

      if (sortType === "number") {
        var numAttr = cell.getAttribute("data-num");
        if (numAttr !== null && numAttr !== "") {
          return parseFloat(numAttr) || 0;
        }
        var clean = cell.textContent.replace(/[^\d.-]/g, "");
        return parseFloat(clean) || 0;
      }
      return cell.textContent.trim();
    }

    // 執行排序並同步更新桌機表頭與手機選單／按鈕
    function executeSort(sortKey, sortType, sortDir) {
      currentSortKey = sortKey;
      currentSortDir = sortDir;

      // 更新桌機表頭指標
      headers.forEach(function (h) {
        var key = h.getAttribute("data-sort-key");
        var ind = h.querySelector(".sort-indicator");
        if (key === sortKey) {
          h.setAttribute("aria-sort", sortDir === "asc" ? "ascending" : "descending");
          if (ind) ind.textContent = sortDir === "asc" ? "▲" : "▼";
        } else {
          h.setAttribute("aria-sort", "none");
          if (ind) ind.textContent = "↕";
        }
      });

      // 更新手機排序 UI
      if (sortSelect && sortSelect.value !== sortKey) {
        sortSelect.value = sortKey;
      }
      if (sortOrderBtn) {
        sortOrderBtn.setAttribute("data-order", sortDir);
        var labelEl = sortOrderBtn.querySelector(".sort-order-label");
        var iconEl = sortOrderBtn.querySelector(".sort-order-icon");
        if (labelEl) labelEl.textContent = sortDir === "asc" ? "升冪" : "降冪";
        if (iconEl) iconEl.textContent = sortDir === "asc" ? "▲" : "▼";
      }

      var rows = getRows();
      rows.sort(function (a, b) {
        var valA = getCellValue(a, sortKey, sortType);
        var valB = getCellValue(b, sortKey, sortType);

        var cmp = 0;
        if (sortType === "number") {
          cmp = valA - valB;
        } else {
          cmp = String(valA).localeCompare(String(valB), "zh-Hant");
        }
        return sortDir === "asc" ? cmp : -cmp;
      });

      // 重新依排序順序掛載列
      rows.forEach(function (row) {
        tbody.appendChild(row);
      });

      var emptyRow = document.getElementById("roster-empty-row");
      if (emptyRow) {
        tbody.appendChild(emptyRow);
      }
    }

    // 桌機：點擊表頭排序
    headers.forEach(function (th) {
      var btn = th.querySelector(".table-sort-btn") || th;
      btn.addEventListener("click", function () {
        var sortKey = th.getAttribute("data-sort-key");
        var sortType = th.getAttribute("data-sort-type") || "string";
        var nextDir = "asc";

        if (currentSortKey === sortKey) {
          nextDir = currentSortDir === "asc" ? "desc" : "asc";
        }
        executeSort(sortKey, sortType, nextDir);
      });
    });

    // 手機：下拉選單變更排序欄位
    if (sortSelect) {
      sortSelect.addEventListener("change", function () {
        var sortKey = sortSelect.value;
        var opt = sortSelect.options[sortSelect.selectedIndex];
        var sortType = (opt && opt.getAttribute("data-type")) || "string";
        executeSort(sortKey, sortType, currentSortDir);
      });
    }

    // 手機：按鈕切換升冪／降冪
    if (sortOrderBtn) {
      sortOrderBtn.addEventListener("click", function () {
        var sortKey = sortSelect ? sortSelect.value : (currentSortKey || "studentNo");
        var sortType = "string";
        if (sortSelect) {
          var opt = sortSelect.options[sortSelect.selectedIndex];
          if (opt && opt.getAttribute("data-type")) {
            sortType = opt.getAttribute("data-type");
          }
        }
        var nextDir = currentSortDir === "asc" ? "desc" : "asc";
        executeSort(sortKey, sortType, nextDir);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTeacherRoster);
  } else {
    initTeacherRoster();
  }
})();
