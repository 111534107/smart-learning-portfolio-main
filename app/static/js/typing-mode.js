(function () {
  "use strict";

  var MOBILE_QUERY = "(max-width: 899px)";
  var mobile = window.matchMedia(MOBILE_QUERY);
  var blurTimer = null;
  var activeTyping = false;

  function isTextControl(element) {
    if (!element) return false;
    if (element.isContentEditable) return true;
    if (element.matches && element.matches("textarea")) return true;
    if (!element.matches || !element.matches("input")) return false;
    var type = (element.getAttribute("type") || "text").toLowerCase();
    return !["checkbox", "radio", "button", "submit", "reset", "file", "image", "hidden"].includes(type);
  }

  function setTyping(value) {
    activeTyping = Boolean(value);
    document.body.classList.toggle("is-typing", activeTyping);
  }

  function keyboardLikelyOpen() {
    if (!mobile.matches || !window.visualViewport) return false;
    return window.innerHeight - window.visualViewport.height > 120;
  }

  function updateTyping() {
    if (keyboardLikelyOpen()) setTyping(true);
  }

  function markBottomBars() {
    if (!mobile.matches) {
      document.querySelectorAll("[data-typing-bottom]").forEach(function (element) {
        element.removeAttribute("data-typing-bottom");
      });
      return;
    }
    Array.from(document.querySelectorAll("body *")).forEach(function (element) {
      if (element.matches(".sv2-tabbar, .assistant__toggle, .tour-invite")) return;
      var style = window.getComputedStyle(element);
      if (style.position !== "fixed" && style.position !== "sticky") return;
      var rect = element.getBoundingClientRect();
      var viewportHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
      var horizontal = rect.width >= window.innerWidth * 0.45;
      var atBottom = rect.bottom >= viewportHeight - 16 && rect.top >= 0;
      if (horizontal && atBottom) element.setAttribute("data-typing-bottom", "");
    });
  }

  document.addEventListener("focusin", function (event) {
    if (!mobile.matches || !isTextControl(event.target)) return;
    if (blurTimer) window.clearTimeout(blurTimer);
    setTyping(true);
    var target = event.target;
    window.setTimeout(function () {
      if (mobile.matches && target) {
        var page = document.body.getAttribute("data-page") || "";
        if (page === "student-internship-resume") {
          var rect = target.getBoundingClientRect();
          var absTop = window.scrollY + rect.top;
          window.scrollTo({ top: Math.max(0, absTop - 90), behavior: "instant" });
        } else {
          target.scrollIntoView({ block: "center", behavior: "auto" });
        }
      }
    }, 100);
  });

  document.addEventListener("focusout", function () {
    if (!mobile.matches) return;
    if (blurTimer) window.clearTimeout(blurTimer);
    blurTimer = window.setTimeout(function () {
      var active = document.activeElement;
      if (!isTextControl(active) && !keyboardLikelyOpen()) setTyping(false);
    }, 250);
  });

  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", function () {
      updateTyping();
      markBottomBars();
      if (!keyboardLikelyOpen()) {
        window.setTimeout(function () {
          if (!isTextControl(document.activeElement) && !keyboardLikelyOpen()) setTyping(false);
        }, 250);
      }
    });
  }
  window.addEventListener("resize", markBottomBars);

  var readingPages = ["student-autobiography", "student-internship-resume"];
  var bodyPage = document.body.getAttribute("data-page") || "";
  var lastScrollY = window.scrollY;

  function updateReadingMode() {
    if (!readingPages.includes(bodyPage)) return;
    var scrollY = window.scrollY;
    var maxScroll = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    var atTop = scrollY <= 80;
    var atBottom = maxScroll - scrollY <= 80;
    var upwardDistance = lastScrollY - scrollY;

    if (atTop || atBottom) {
      document.body.classList.remove("is-reading");
    } else if (upwardDistance > 40) {
      document.body.classList.add("is-reading");
    } else {
      document.body.classList.add("is-reading");
    }
    lastScrollY = scrollY;
  }

  window.addEventListener("scroll", function () {
    updateReadingMode();
  }, { passive: true });

  document.addEventListener("DOMContentLoaded", function () {
    markBottomBars();
    updateReadingMode();
  });

  markBottomBars();
  updateReadingMode();
  updateTyping();
})();
