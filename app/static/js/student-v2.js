/* 學生端 v2 共用外殼（2026-11-11，邏輯參考設計示範 _design-demo/student-v2/common.js）
   - 帳號選單：字體大小滑桿（14–24px）、外觀（淺色／深色／跟系統）、玻璃效果滑桿、折射開關。
   - 手機（≤720px）：主選單改成底部浮動分頁列，往下捲縮成一顆。
   - 設定只存在這台瀏覽器的 localStorage；全部包在函式裡，不留全域變數。
   - 只在學生頁載入（base.html 判斷 user.role == "student"）。 */
(function () {
  "use strict";
  var root = document.documentElement;
  if (root.getAttribute("data-ui") !== "student-v2") { return; }
  root.classList.add("sv2-js");

  function get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* 私密視窗等情況存不了，畫面照常 */ } }

  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  var isChromium = !!(navigator.userAgentData && navigator.userAgentData.brands &&
    navigator.userAgentData.brands.some(function (b) { return /Chromium/.test(b.brand); }));
  var FS_DEFAULT = 16;
  var GLASS_DEFAULT = 40;

  function applyTheme() {
    var t = get("ui-theme") || "auto";
    root.setAttribute("data-theme", t === "auto" ? (mq && mq.matches ? "dark" : "light") : t);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) { meta.setAttribute("content", root.getAttribute("data-theme") === "dark" ? "#1f1b17" : "#f1ebe2"); }
  }
  function applySize() {
    var v = parseFloat(get("ui-fs"));
    if (v >= 14 && v <= 24) { root.style.fontSize = v + "px"; } else { root.style.removeProperty("font-size"); }
  }
  function applyGlass() {
    var g = get("ui-glass-v");
    var v = g === null ? GLASS_DEFAULT : +g;
    root.style.setProperty("--galpha", (0.2 + 0.8 * v / 100).toFixed(2));
    root.style.setProperty("--gblur", (v >= 100 ? 0 : 8 + v * 0.36).toFixed(0) + "px");
    root.setAttribute("data-glass", v >= 100 ? "solid" : v <= 15 ? "clear" : "std");
    root.classList.toggle("lens", isChromium && get("ui-lens") !== "off");
  }
  applyTheme(); applySize(); applyGlass();
  if (mq) {
    if (mq.addEventListener) { mq.addEventListener("change", applyTheme); } else if (mq.addListener) { mq.addListener(applyTheme); }
  }

  /* 折射濾鏡：玻璃邊緣把背後內容稍微扭曲（只有 Chromium 會用到） */
  if (isChromium) {
    var ns = "http://www.w3.org/2000/svg";
    var fsvg = document.createElementNS(ns, "svg");
    fsvg.setAttribute("width", "0"); fsvg.setAttribute("height", "0"); fsvg.setAttribute("aria-hidden", "true");
    fsvg.style.position = "absolute";
    fsvg.innerHTML = '<filter id="sv2-lens" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.008 0.012" numOctaves="2" seed="3" result="n"/><feGaussianBlur in="n" stdDeviation="2" result="nb"/><feDisplacementMap in="SourceGraphic" in2="nb" scale="38" xChannelSelector="R" yChannelSelector="G"/></filter>';
    document.body.appendChild(fsvg);
  }

  /* ---------- 帳號選單裡的外觀設定 ---------- */
  function svg(path) { return '<svg viewBox="0 0 24 24" aria-hidden="true">' + path + "</svg>"; }
  var ICON = {
    sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
    moon: svg('<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>'),
    auto: svg('<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/>'),
    lens: svg('<circle cx="12" cy="12" r="8"/><path d="M7.5 10a5 5 0 0 1 4-3.5"/>'),
    flat: svg('<rect x="4" y="4" width="16" height="16" rx="5"/><path d="M4 20L20 4"/>')
  };
  var SLIDERS = {
    "ui-fs": { min: 14, max: 24, step: 0.5, def: FS_DEFAULT, label: "字體大小",
      ticks: [[14, "14px"], [16, "標準"], [18, "18px"], [20, "20px"], [24, "24px"]],
      fmt: function (v) { return v + "px"; }, apply: applySize },
    "ui-glass-v": { min: 0, max: 100, step: 1, def: GLASS_DEFAULT, label: "玻璃效果",
      ticks: [[0, "清透"], [40, "標準"], [75, "霧面"], [100, "不透明"]],
      fmt: function (v) { return v >= 100 ? "不透明" : v + "%"; }, apply: applyGlass }
  };
  function sliderHtml(key) {
    var s = SLIDERS[key];
    var stored = get(key);
    var cur = stored === null || isNaN(+stored) ? s.def : +stored;
    var ticks = s.ticks.map(function (t) {
      return '<button type="button" data-v="' + t[0] + '" style="left:' + ((t[0] - s.min) / (s.max - s.min) * 100) + '%"' +
        (t[0] === s.def ? ' class="is-default"' : "") + ' tabindex="-1">' + t[1] + "</button>";
    }).join("");
    return '<div class="sv2-sld" data-k="' + key + '"><div class="sv2-sld__ticks">' + ticks + "</div>" +
      '<input type="range" min="' + s.min + '" max="' + s.max + '" step="' + s.step + '" value="' + cur + '" aria-label="' + s.label + '" aria-valuetext="' + s.fmt(cur) + '"></div>';
  }
  function segHtml(key, items, disabled) {
    return '<div class="sv2-seg" role="group" data-k="' + key + '">' + items.map(function (it) {
      return '<button type="button" data-v="' + it[0] + '" aria-label="' + it[1] + '" title="' + (disabled ? "這個瀏覽器不支援折射" : it[1]) + '" aria-pressed="false"' + (disabled ? " disabled" : "") + ">" + it[2] + "</button>";
    }).join("") + "</div>";
  }

  var panel = document.getElementById("account-menu-panel");
  if (panel && document.querySelector(".masthead--student")) {
    var prefs = document.createElement("div");
    prefs.className = "sv2-prefs";
    prefs.innerHTML =
      '<h4 id="sv2-fs-title">字體大小</h4>' + sliderHtml("ui-fs") +
      '<div class="sv2-row"><div><h4>外觀</h4>' +
      segHtml("ui-theme", [["light", "淺色", ICON.sun], ["dark", "深色", ICON.moon], ["auto", "跟系統", ICON.auto]], false) +
      "</div><div><h4>折射</h4>" +
      segHtml("ui-lens", [["on", "折射開", ICON.lens], ["off", "折射關", ICON.flat]], !isChromium) +
      "</div></div><h4>玻璃效果</h4>" + sliderHtml("ui-glass-v");
    var who = panel.querySelector(".account-menu__who");
    if (who && who.nextSibling) { panel.insertBefore(prefs, who.nextSibling); } else { panel.insertBefore(prefs, panel.firstChild); }

    function sync() {
      prefs.querySelectorAll(".sv2-seg").forEach(function (seg) {
        var cur = get(seg.dataset.k) || (seg.dataset.k === "ui-theme" ? "auto" : "on");
        seg.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.v === cur)); });
      });
    }
    function paint(sl) {
      var r = sl.querySelector("input");
      var s = SLIDERS[sl.dataset.k];
      r.style.setProperty("--p", ((r.value - r.min) / (r.max - r.min) * 100) + "%");
      r.setAttribute("aria-valuetext", s.fmt(+r.value));
      sl.querySelectorAll(".sv2-sld__ticks button").forEach(function (b) { b.classList.toggle("is-on", +b.dataset.v === +r.value); });
    }
    prefs.addEventListener("click", function (event) {
      event.stopPropagation(); // 不要讓 components.js 以為點到外面而關掉選單
      var b = event.target.closest(".sv2-seg button");
      if (!b || b.disabled) { return; }
      var key = b.parentElement.dataset.k;
      set(key, b.dataset.v);
      if (key === "ui-theme") { applyTheme(); } else { applyGlass(); }
      sync();
    });
    prefs.querySelectorAll(".sv2-sld").forEach(function (sl) {
      var r = sl.querySelector("input");
      var key = sl.dataset.k;
      var s = SLIDERS[key];
      paint(sl);
      r.addEventListener("input", function () {
        var range = s.max - s.min;
        for (var i = 0; i < s.ticks.length; i += 1) {
          if (Math.abs(s.ticks[i][0] - r.value) <= range * 0.025) { r.value = s.ticks[i][0]; break; }
        }
        set(key, r.value);
        s.apply();
        paint(sl);
      });
      sl.querySelectorAll(".sv2-sld__ticks button").forEach(function (b) {
        b.addEventListener("click", function () { r.value = b.dataset.v; r.dispatchEvent(new Event("input")); });
      });
    });
    sync();
  }

  /* ---------- 手機底部分頁列：從頂端主選單產生，連結與目前頁完全相同 ---------- */
  var ICONS = {
    "我的五年": '<path d="M4 18c3-8 6 2 9-6s5-4 7-6"/><circle cx="4" cy="18" r="1.6"/><circle cx="20" cy="6" r="1.6"/>',
    "我的資料": '<path d="M3 7h6l2 2h10v10H3z"/>',
    "畢業門檻": '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2 9 2 12 0v-5"/>',
    "目標與備審": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1"/>',
    "我的待辦": '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2"/>'
  };
  var nav = document.getElementById("student-mainnav");
  if (nav) {
    var bar = document.createElement("nav");
    bar.className = "sv2-tabbar sv2-glass";
    bar.setAttribute("aria-label", "主要導覽（手機）");
    nav.querySelectorAll("a").forEach(function (a) {
      var label = (a.childNodes[0] && a.childNodes[0].nodeType === 3 ? a.childNodes[0].textContent : a.textContent).trim();
      var tab = document.createElement("a");
      tab.className = "sv2-tab";
      tab.href = a.getAttribute("href");
      if (a.hasAttribute("aria-current")) { tab.setAttribute("aria-current", a.getAttribute("aria-current")); }
      tab.innerHTML = svg(ICONS[label] || "") + "<span></span>";
      tab.querySelector("span").textContent = label;
      var count = a.querySelector(".mainnav__count");
      if (count) {
        var dot = document.createElement("i");
        dot.className = "sv2-dot";
        dot.textContent = count.textContent.trim();
        dot.setAttribute("aria-label", count.getAttribute("aria-label") || "");
        tab.appendChild(dot);
      }
      bar.appendChild(tab);
    });
    document.body.appendChild(bar);
    var last = window.scrollY;
    window.addEventListener("scroll", function () {
      var y = window.scrollY;
      if (Math.abs(y - last) < 6) { return; }
      bar.classList.toggle("is-min", y > last && y > 120);
      last = y;
    }, { passive: true });
    bar.addEventListener("click", function (event) {
      if (bar.classList.contains("is-min") && event.target.closest("[aria-current]")) {
        event.preventDefault();
        bar.classList.remove("is-min");
      }
    });
  }
})();
