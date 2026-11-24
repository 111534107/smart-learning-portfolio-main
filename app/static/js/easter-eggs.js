(() => {
  const reduced = document.documentElement.classList.contains("reduced-motion") || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const assistant = document.querySelector("[data-assistant]");
  const userId = assistant ? assistant.dataset.user : (document.body.dataset.user || "unknown");
  const get = (key) => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const set = (key, value) => { try { localStorage.setItem(key, value); } catch (_) {} };

  function closeAfter(card, ms) {
    const removeCard = () => {
      card.remove();
      if (card.classList.contains("egg-milestone")) {
        milestoneCardVisible = false;
        setTimeout(releaseNextMilestone, 50);
      }
    };
    const timer = setTimeout(removeCard, ms);
    card.querySelectorAll("[data-egg-close],[data-egg-skip]").forEach((button) => button.addEventListener("click", () => { clearTimeout(timer); removeCard(); }, { once: true }));
  }
  function staticToast(text) { const card = document.createElement("div"); card.className = "egg-toast"; card.setAttribute("role", "status"); card.innerHTML = `<span></span><button type="button" class="egg-close" data-egg-close aria-label="關閉提示">×</button>`; card.querySelector("span").textContent = text; document.body.appendChild(card); closeAfter(card, 3800); }

  // 畢業門檻量表進展
  if (document.body.dataset.page === "student-graduation-check") {
    const meters = [...document.querySelectorAll("[data-meter-key]")];
    let allFull = true;
    meters.forEach((meter) => {
      const key = meter.dataset.meterKey;
      const value = Number(meter.dataset.meterValue);
      const storageKey = `grad-meter:${userId}:${key}`;
      const previousText = get(storageKey);
      const previous = previousText === null ? value : Number(previousText);
      if (previousText !== null && Number.isFinite(value) && value > previous) {
        if (reduced) staticToast(`${meter.dataset.meterName || "量表"}已補進 1；目前 ${value}/${meter.dataset.meterNeed || "門檻"}`);
        else {
          const rect = meter.getBoundingClientRect();
          const piece = document.createElement("div"); piece.className = "egg-puzzle-piece";
          piece.style.setProperty("--egg-x", "calc(100vw - 70px)"); piece.style.setProperty("--egg-y", "calc(100vh - 70px)");
          piece.innerHTML = '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M6 6h14v8c6-5 12 5 6 9h16v19H24v-8c-7 5-13-5-7-9H6z" fill="#2448c9" stroke="#1c2230" stroke-width="2"/></svg>'; document.body.appendChild(piece);
          const pr = piece.getBoundingClientRect(); piece.style.setProperty("--egg-dx", `${rect.left + rect.width/2 - pr.left - 24}px`); piece.style.setProperty("--egg-dy", `${rect.top + rect.height/2 - pr.top - 24}px`);
          requestAnimationFrame(() => piece.classList.add("is-flying")); setTimeout(() => piece.remove(), 1250);
        }
      }
      set(storageKey, String(value));
      if (Number(meter.dataset.meterPct) < 100) allFull = false;
    });
    if (meters.length && allFull) {
      const fireKey = `grad-fireworks:${userId}`;
      if (!get(fireKey)) {
        set(fireKey, "1");
        if (reduced) staticToast("畢業門檻四項量表已全滿。");
        else { const box = document.createElement("div"); box.className = "egg-fireworks"; box.setAttribute("aria-hidden","true"); for (let i=0;i<18;i++){ const p=document.createElement("i"); p.style.setProperty("--egg-angle",`${i*20}deg`); p.style.setProperty("--egg-color",i%2?"#d9961f":"#2448c9"); box.appendChild(p); } document.body.appendChild(box); setTimeout(()=>box.remove(),2000); }
      }
    }
  }

  // 打包下載／寄送信封
  if (document.body.dataset.page === "student-gap") {
    const checklist = [...document.querySelectorAll("[data-package-bundle]").flatMap(() => [])];
    const items = [...document.querySelectorAll(".download-checklist__item")];
    const missing = items.filter((item) => item.classList.contains("is-open")).map((item) => item.textContent.replace(/! 還沒|去補.*$/g, "").trim()).filter(Boolean);
    const complete = missing.length === 0 && items.length > 0;
    const showEnvelope = () => {
      if (reduced) { staticToast(complete ? "資料已打包，章戳：可以寄出。" : `章戳無法蓋下：請先完成檢核表，缺少 ${missing.join("、")}`); return; }
      const card = document.createElement("div"); card.className = "egg-envelope"; card.setAttribute("role","dialog"); card.setAttribute("aria-label","打包進度提示");
      card.innerHTML = `<div class="egg-envelope__art" aria-hidden="true"><div class="egg-document"></div><div class="egg-envelope__back"></div><div class="egg-envelope__flap"></div><div class="egg-envelope__stamp"></div></div><p class="egg-envelope__text"></p><button type="button" class="egg-skip" data-egg-skip>跳過動畫</button>`;
      card.querySelector(".egg-envelope__text").textContent = complete ? "檢核表已全部完成，可以寄出。" : `請先完成檢核表：${missing.join("、") || "資料完整度尚未達成"}`;
      card.querySelector(".egg-envelope__stamp").textContent = complete ? "可以寄出" : "請先完成檢核表";
      document.body.appendChild(card); closeAfter(card, 3600);
    };
    document.querySelectorAll('a[href*="target_package"], [data-package-bundle] form').forEach((control) => control.addEventListener("submit", showEnvelope));
    document.querySelectorAll('a[href*="target_package"]').forEach((link) => link.addEventListener("click", showEnvelope));
    if (["sent","link","logged","failed"].includes(new URLSearchParams(location.search).get("mailed"))) showEnvelope();
  }

  let pendingMilestones = [];
  let milestoneInviteTimer = null;
  let milestoneCardVisible = false;
  const topForMasthead = () => {
    const masthead = document.querySelector(".masthead");
    const top = masthead ? Math.ceil(masthead.getBoundingClientRect().bottom + 12) : 76;
    document.documentElement.style.setProperty("--egg-milestone-top", `${top}px`);
  };
  const hasTourInvite = () => !!document.querySelector(".tour-invite");
  const renderMilestone = (item) => {
    if (!item || !item.title || milestoneCardVisible || hasTourInvite()) {
      if (item) pendingMilestones.push(item);
      return;
    }
    milestoneCardVisible = true;
    const key = `milestone-seen:${userId}:${item.key || item.title}`;
    set(key, "1");
    topForMasthead();
    const card = document.createElement("section");
    card.className = "egg-milestone";
    card.setAttribute("role", "status");
    card.innerHTML = '<svg class="egg-milestone__svg" viewBox="0 0 68 68" aria-hidden="true"><circle cx="34" cy="38" r="20" fill="#2448c9"/><path d="M34 8l12 8-12 8-12-8z" fill="#d9961f"/><path d="M22 16v12c7 6 17 6 24 0V16" fill="#d9961f"/><path d="M34 24v14" stroke="#1c2230" stroke-width="3"/><circle cx="34" cy="40" r="8" fill="#fffdf8"/><path d="M30 40l3 3 6-7" fill="none" stroke="#1f8a7a" stroke-width="3"/></svg><div><h3></h3><p></p></div><button type="button" class="egg-close" data-egg-close aria-label="關閉頒獎卡片">×</button>';
    card.querySelector("h3").textContent = item.title;
    card.querySelector("p").textContent = item.text || "里程碑已達成";
    document.body.appendChild(card);
    closeAfter(card, 3800);
    card.addEventListener("eggcardremoved", () => { milestoneCardVisible = false; }, { once: true });
  };
  const releaseNextMilestone = () => {
    if (milestoneInviteTimer) clearTimeout(milestoneInviteTimer);
    milestoneInviteTimer = null;
    if (!pendingMilestones.length) return;
    if (hasTourInvite()) return;
    const item = pendingMilestones.shift();
    renderMilestone(item);
  };
  window.showMilestone = (item) => {
    if (!item || !item.title) return;
    if (milestoneCardVisible || hasTourInvite()) {
      pendingMilestones.push(item);
      return;
    }
    renderMilestone(item);
  };

  // 觀察 components.js 建立的 .tour-invite；導覽邀請存在時頒獎卡片一律等待。
  const inviteObserver = new MutationObserver(() => {
    const invite = document.querySelector(".tour-invite");
    if (invite) {
      if (!milestoneInviteTimer) {
        milestoneInviteTimer = setTimeout(() => {
          const activeInvite = document.querySelector(".tour-invite");
          if (activeInvite) activeInvite.remove();
          releaseNextMilestone();
        }, 8000);
      }
    } else {
      setTimeout(releaseNextMilestone, 50);
    }
  });
  inviteObserver.observe(document.body, { childList: true, subtree: true });
  window.addEventListener("resize", topForMasthead);
  const milestoneNode = document.getElementById("milestones-data");
  // 2026-11-21 使用者要求拿掉「第一份自傳完成」這類里程碑彈跳視窗（用處不大、蓋住畫面）：
  // 不再讀取頁面上的 milestones-data 來跳卡片。後端的里程碑資料與 window.showMilestone 都保留，要恢復就把下一行的註解拿掉。
  // if (milestoneNode) { try { JSON.parse(milestoneNode.textContent||"[]").forEach((item)=>{ if(!get(`milestone-seen:${userId}:${item.key}`)) window.showMilestone(item); }); } catch (_) {} }

  // 隱藏彩蛋：校徽連點三下
  const creditsNode = document.getElementById("credits-data");
  let credits = []; if (creditsNode) { try { credits=JSON.parse(creditsNode.textContent||"[]"); } catch (_) {} }
  const dialog = document.getElementById("egg-credits-dialog");
  if (dialog) {
    const list = dialog.querySelector("[data-credits-list]"); credits.forEach((person)=>{ const li=document.createElement("li"); const role=document.createElement("b"); role.textContent=person.role; const name=document.createElement("span"); name.textContent=person.name; li.append(role,name); list.appendChild(li); });
    dialog.querySelector("[data-egg-close]").addEventListener("click",()=>dialog.close());
  }
  const brand = document.querySelector(".masthead__inner .brand");
  if (brand && dialog) { let taps=[]; let navTimer=null; brand.addEventListener("click",(event)=>{ event.preventDefault(); const now=Date.now(); taps=taps.filter((time)=>now-time<=600); taps.push(now); if(navTimer) clearTimeout(navTimer); if(taps.length>=3){ taps=[]; if(typeof dialog.showModal==="function") dialog.showModal(); dialog.querySelector("[data-egg-close]").focus(); } else { navTimer=setTimeout(()=>{ if(taps.length===1) window.location.href=brand.href; taps=[]; },650); } }); }
})();