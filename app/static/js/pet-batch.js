/**
 * 批次生成頁：沿用既有 API 流程，只以真正的 assistant__toggle 為主角。
 */
(() => {
  'use strict';

  const container = document.querySelector('[data-batch-container]');
  if (!container) return;

  const startUrl = container.dataset.startUrl;
  const statusUrlTemplate = container.dataset.statusUrl;
  const retryUrl = container.dataset.retryUrl;
  const csrfToken = container.dataset.csrfToken;
  const papers = Array.from(container.querySelectorAll('.batch-paper'));
  const headlineEl = container.querySelector('[data-batch-headline]');
  const statusTextEl = container.querySelector('[data-batch-status-text]');
  const progressFill = container.querySelector('[data-batch-progress-fill]');
  const doneCountEl = container.querySelector('[data-batch-done-count]');
  const completionBox = container.querySelector('[data-batch-completion]');
  const startPanel = container.querySelector('[data-batch-start-panel]');
  const startBtn = container.querySelector('[data-batch-start-btn]');
  const startNote = container.querySelector('[data-batch-start-note]');
  const launcher = document.querySelector('[data-assistant] .assistant__toggle');
  const originalIcon = launcher && launcher.querySelector('.as-icon');

  let currentJobId = null;
  let pollTimer = null;
  let isPolling = false;
  let activePaper = null;
  let bubbleTimer = null;
  let cialloTimer = null;
  let moveTimer = null;
  let originalStyle = null;
  const itemStates = new Map();
  let backendAllDone = false;
  let presentationStarted = false;
  let presentationFinished = false;
  let failedEncountered = false;

  const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
    || document.body.classList.contains('reduced-motion')
    || document.documentElement.classList.contains('reduced-motion');

  let bubble = null;
  let face = null;
  let leftMuscle = null;
  let rightMuscle = null;
  const ensureAssistantEffects = () => {
    if (!launcher) return;
    if (!bubble) {
      bubble = document.createElement('div');
      bubble.className = 'batch-assistant-bubble';
      bubble.setAttribute('role', 'status');
      bubble.setAttribute('aria-live', 'polite');
      launcher.appendChild(bubble);
    }
    if (!face) {
      face = document.createElement('span');
      face.className = 'batch-assistant-face';
      face.setAttribute('aria-hidden', 'true');
      launcher.appendChild(face);
    }
    if (!leftMuscle) {
      leftMuscle = document.createElement('span');
      leftMuscle.className = 'batch-assistant-muscle batch-assistant-muscle--left';
      leftMuscle.textContent = 'ᕦ';
      leftMuscle.setAttribute('aria-hidden', 'true');
      launcher.appendChild(leftMuscle);
    }
    if (!rightMuscle) {
      rightMuscle = document.createElement('span');
      rightMuscle.className = 'batch-assistant-muscle batch-assistant-muscle--right';
      rightMuscle.textContent = 'ᕤ';
      rightMuscle.setAttribute('aria-hidden', 'true');
      launcher.appendChild(rightMuscle);
    }
  };

  const positionBubble = () => {
    if (!launcher || !bubble || !bubble.classList.contains('is-visible')) return;
    const iconRect = launcher.getBoundingClientRect();
    const bubbleRect = bubble.getBoundingClientRect();
    const bubbleWidth = bubbleRect.width;
    const bubbleHeight = bubbleRect.height;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const iconCenter = iconRect.left + iconRect.width / 2;
    const iconOnRight = iconCenter >= viewportWidth / 2;

    let left = iconOnRight
      ? iconRect.right - bubbleWidth
      : iconRect.left;
    left = Math.max(12, Math.min(viewportWidth - 12 - bubbleWidth, left));

    let top = iconRect.top - bubbleHeight - 10;
    bubble.classList.remove('is-below');
    if (top < 12) {
      top = iconRect.bottom + 10;
      bubble.classList.add('is-below');
    }
    if (top + bubbleHeight > viewportHeight - 12) {
      top = Math.max(12, viewportHeight - 12 - bubbleHeight);
    }

    bubble.classList.toggle('is-right-aligned', iconOnRight);
    bubble.classList.toggle('is-left-aligned', !iconOnRight);
    bubble.style.left = `${left}px`;
    bubble.style.top = `${top}px`;
    bubble.style.right = 'auto';
    bubble.style.bottom = 'auto';
  };

  const setBubble = (text, duration = 3000) => {
    ensureAssistantEffects();
    clearTimeout(bubbleTimer);
    bubble.textContent = text || '';
    bubble.classList.toggle('is-visible', Boolean(text));
    if (text) {
      requestAnimationFrame(positionBubble);
      if (duration) bubbleTimer = setTimeout(() => bubble.classList.remove('is-visible'), duration);
    }
  };

  const setFace = (expression = '') => {
    ensureAssistantEffects();
    face.textContent = expression;
    face.classList.toggle('is-casting-face', expression === '(｀・ω・´)');
    face.classList.toggle('is-all-completed', expression === 'ヽ(>∀<☆)ノ');
    if (originalIcon) originalIcon.style.display = expression ? 'none' : '';
  };

  const setCasting = (casting) => {
    if (!launcher) return;
    launcher.classList.toggle('is-batch-casting', casting);
    document.body.classList.toggle('is-batch-casting', casting);
  };

  if (launcher) {
    launcher.addEventListener('click', (event) => {
      if (launcher.classList.contains('is-batch-casting')) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, true);
    launcher.addEventListener('pointerdown', (event) => {
      if (launcher.classList.contains('is-batch-casting')) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, true);
  }

  const captureOriginalStyle = () => {
    if (!launcher || originalStyle) return;
    originalStyle = {
      left: launcher.style.left,
      right: launcher.style.right,
      top: launcher.style.top,
      bottom: launcher.style.bottom,
      transform: launcher.style.transform
    };
  };

  const restoreAssistant = () => {
    if (!launcher || !originalStyle) return;
    clearTimeout(moveTimer);
    setCasting(false);
    setFace('');
    setBubble('');
    if (bubble) bubble.className = 'batch-assistant-bubble';
    launcher.style.left = originalStyle.left;
    launcher.style.right = originalStyle.right;
    launcher.style.top = originalStyle.top;
    launcher.style.bottom = originalStyle.bottom;
    launcher.style.transform = originalStyle.transform;
  };

  const moveAssistantToPaper = (paper, callback) => {
    if (!launcher || !paper) {
      if (callback) callback();
      return;
    }
    captureOriginalStyle();
    const rectBeforeMove = paper.getBoundingClientRect();
    const paperOutOfView = rectBeforeMove.top < 0
      || rectBeforeMove.bottom > innerHeight
      || rectBeforeMove.left < 0
      || rectBeforeMove.right > innerWidth;
    if (paperOutOfView) {
      paper.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'center', inline: 'center' });
    }
    clearTimeout(moveTimer);
    const apply = () => {
      if (reducedMotion()) {
        launcher.style.transition = 'none';
        const rect = paper.getBoundingClientRect();
        const size = launcher.getBoundingClientRect();
        const targetLeft = Math.max(12, Math.min(innerWidth - size.width - 12, rect.right + 8));
        const targetTop = Math.max(12, Math.min(innerHeight - size.height - 12, rect.top - 10));
        launcher.style.position = 'fixed';
        launcher.style.left = `${targetLeft}px`;
        launcher.style.right = 'auto';
        launcher.style.top = `${targetTop}px`;
        launcher.style.bottom = 'auto';
        launcher.style.transform = 'none';
        if (callback) callback();
        return;
      } else {
        launcher.style.transition = 'left 0.75s cubic-bezier(.25,1,.5,1), top 0.75s cubic-bezier(.25,1,.5,1), transform 0.75s cubic-bezier(.25,1,.5,1)';
      }
      const rect = paper.getBoundingClientRect();
      const size = launcher.getBoundingClientRect();
      const targetLeft = Math.max(12, Math.min(innerWidth - size.width - 12, rect.right + 8));
      const targetTop = Math.max(12, Math.min(innerHeight - size.height - 12, rect.top - 10));
      launcher.style.position = 'fixed';
      launcher.style.left = `${targetLeft}px`;
      launcher.style.right = 'auto';
      launcher.style.top = `${targetTop}px`;
      launcher.style.bottom = 'auto';
      launcher.style.transform = reducedMotion() ? 'none' : 'translateY(0)';
      if (callback) moveTimer = setTimeout(callback, reducedMotion() ? 0 : 760);
    };
    setTimeout(apply, reducedMotion() ? 0 : 80);
  };

  const updateProgress = () => {
    const doneTotal = Array.from(itemStates.values()).filter(status => status === 'done').length;
    if (doneCountEl) doneCountEl.textContent = doneTotal;
    if (progressFill) progressFill.style.width = `${papers.length ? Math.round(doneTotal / papers.length * 100) : 0}%`;
  };

  const startBatch = async () => {
    if (!startUrl) {
      statusTextEl.textContent = '缺少啟動網址，請重新整理頁面。';
      setFace('(；´Д｀)');
      setBubble('啟動網址不見了');
      if (startBtn) startBtn.disabled = false;
      if (startBtn) startBtn.textContent = '請小助手開始';
      if (startNote) startNote.textContent = '點擊後將開始排隊生成，不點擊不會消耗你的 AI 額度。';
      return;
    }
    startBtn.disabled = true;
    startBtn.textContent = '小助手施法中';
    if (startNote) startNote.textContent = '正在依序生成，請保持頁面開啟';
    setFace('(｀・ω・´)');
    setBubble('正在啟動批次生成...');
    headlineEl.textContent = '小助手準備中';
    statusTextEl.textContent = '小助手正在向科辦登記批次生成自傳任務...';
    try {
      const form = new FormData();
      if (csrfToken) form.append('csrf_token', csrfToken);
      const resp = await fetch(startUrl, { method: 'POST', body: form, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!resp.ok) throw new Error(`伺服器回應異常 (${resp.status})`);
      const data = await resp.json();
      if (!data.job_id) throw new Error('未取得有效的任務代號');
      currentJobId = data.job_id;
      statusTextEl.textContent = `任務已啟動 (代號: ${String(currentJobId).slice(0, 8)}...)，小助手即將大顯身手！`;
      startPolling();
    } catch (err) {
      setFace('(；´Д｀)');
      setBubble('啟動批次時連線稍微卡住');
      statusTextEl.textContent = `啟動失敗：${err.message || '連線錯誤'}。請點擊按鈕再試一次。`;
      startBtn.disabled = false;
      startBtn.textContent = '請小助手開始';
      if (startNote) startNote.textContent = '點擊後將開始排隊生成，不點擊不會消耗你的 AI 額度。';
    }
  };

  const stopPolling = () => {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    isPolling = false;
  };

  const pollStatus = async () => {
    if (!currentJobId || !statusUrlTemplate) return;
    const url = statusUrlTemplate.replace('__JOB__', encodeURIComponent(currentJobId));
    try {
      const resp = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!resp.ok) throw new Error(`輪詢失敗 (${resp.status})`);
      handleStatusResponse(await resp.json());
    } catch (err) {
      console.warn('輪詢狀態遇到暫時性問題：', err);
    }
  };

  const startPolling = () => {
    if (pollTimer) clearInterval(pollTimer);
    isPolling = true;
    pollStatus();
    pollTimer = setInterval(pollStatus, 1500);
  };

  const handleStatusResponse = (data) => {
    if (!data || !Array.isArray(data.items)) return;
    let running = null;
    let failed = null;

    data.items.forEach(item => {
      const programId = String(item.program_id);
      const paper = container.querySelector(`.batch-paper[data-program-id="${programId}"]`);
      if (!paper) return;
      const statusText = paper.querySelector('[data-paper-status-text]');
      const failBox = paper.querySelector('.batch-paper__fail-box');
      const failNote = paper.querySelector('[data-fail-note]');
      const retryBtn = paper.querySelector('[data-retry-btn]');
      const guideLink = paper.querySelector('[data-guide-link]');

      if (item.status === 'done') {
        if (paper.dataset.status !== 'done') statusText.textContent = '排隊等待小助手蓋章';
        failBox.hidden = true;
      } else if (item.status === 'running') {
        running = { item, paper };
        if (paper.dataset.status !== 'running') statusText.textContent = '排隊等待輪到施法';
        failBox.hidden = true;
      } else if (item.status === 'failed') {
        failed = { item, paper };
        failedEncountered = true;
        paper.dataset.status = 'failed';
        statusText.textContent = '⚠️ 生成暫時中斷';
        failBox.hidden = false;
        const message = (item.message || '').trim();
        failNote.textContent = message || '這所學校的重點分析暫時中斷，點擊重試讓小助手再試一次！';
        const needsGuidance = message.includes('自己的話') || message.includes('回答');
        retryBtn.hidden = needsGuidance;
        guideLink.hidden = !needsGuidance;
        if (needsGuidance) guideLink.href = `/student/autobiography?program_id=${encodeURIComponent(programId)}&redo=1`;
      } else {
        if (paper.dataset.status !== 'running' && paper.dataset.status !== 'done') {
          paper.dataset.status = 'pending';
          statusText.textContent = '排隊等待中';
        }
        failBox.hidden = true;
      }
      itemStates.set(programId, item.status);
    });

    updateProgress();

    if (failed && !running) {
      headlineEl.textContent = '生成遭遇小波折';
      statusTextEl.textContent = '部分校系需要補填引導題或連線暫時不順，請檢視紙張上的提示。';
    }

    const allDone = papers.every(p => p.dataset.status === 'done');
    backendAllDone = allDone || (data.status === 'done' && Array.from(itemStates.values()).every(status => status === 'done'));
    if (backendAllDone) {
      stopPolling();
    }
    if (!presentationStarted) startPresentationQueue();
  };

  const wait = milliseconds => new Promise(resolve => setTimeout(resolve, reducedMotion() ? 0 : milliseconds));

  const startPresentationQueue = async () => {
    if (presentationStarted) return;
    presentationStarted = true;

    for (const paper of papers) {
      if (presentationFinished) break;
      const programId = String(paper.dataset.programId);
      const statusText = paper.querySelector('[data-paper-status-text]');

      headlineEl.textContent = `小助手正在前往：${paper.dataset.school || ''}`;
      statusTextEl.textContent = `小助手正在移動到 ${paper.dataset.school || ''} ${paper.dataset.department || ''} 的紙張旁。`;
      setFace('(｀・ω・´)');
      setBubble(`正在前往 ${paper.dataset.school || ''} 的紙張旁`, 0);
      await new Promise(resolve => moveAssistantToPaper(paper, resolve));

      paper.dataset.status = 'running';
      statusText.textContent = '✨ 小助手施法撰寫中...';
      headlineEl.textContent = `正在生成：${paper.dataset.school || ''}`;
      statusTextEl.textContent = `小助手正對 ${paper.dataset.school || ''} ${paper.dataset.department || ''} 的紙張施法撰寫中...`;
      setCasting(true);
      setFace('(｀・ω・´)');
      setBubble(`正在為 ${paper.dataset.school || ''} 撰寫自傳中...`, 0);

      await wait(1400);

      while (['pending', 'running'].includes(itemStates.get(programId))) {
        setCasting(true);
        setFace('(｀・ω・´)');
        setBubble(`等待 ${paper.dataset.school || ''} 的後端完成施法中...`, 0);
        statusText.textContent = '⏳ 後端仍在處理，等待小助手完成';
        await wait(250);
      }

      const finalStatus = itemStates.get(programId);
      if (finalStatus === 'done') {
        paper.dataset.status = 'done';
        statusText.textContent = '✓ 自傳初稿生成完畢';
        setCasting(false);
        setFace('(≧▽≦)');
        setBubble('Ciallo～(∠・ω<)⌒★', 3000);
        await wait(400);
      } else if (finalStatus === 'failed') {
        paper.dataset.status = 'failed';
        statusText.textContent = '⚠️ 生成暫時中斷';
        setCasting(false);
        setFace('(；´Д｀)');
        setBubble('這所學校卡住了，點紙上的重試', 3000);
        await wait(400);
      } else {
        paper.dataset.status = 'pending';
      }

      activePaper = paper;
      updateProgress();
    }

    presentationFinished = true;
    if (backendAllDone && papers.length && Array.from(itemStates.values()).every(status => status === 'done')) {
      handleAllCompleted();
    } else if (failedEncountered) {
      setCasting(false);
      setFace('(；´Д｀)');
      setBubble('部分校系需要補填引導題或重試');
    }
  };

  const handleAllCompleted = () => {
    stopPolling();
    setCasting(false);
    setFace('ヽ(>∀<☆)ノ');
    setBubble('資管小助手很高興為你服務', 3000);
    restoreAssistant();
    setFace('ヽ(>∀<☆)ノ');
    setBubble('資管小助手很高興為你服務', 3000);
    headlineEl.textContent = '🎉 全數校系自傳已生成完畢！';
    statusTextEl.textContent = '恭喜！所有目標校系的自傳初稿均已妥善準備好。';
    if (startPanel) startPanel.hidden = true;
    if (completionBox) {
      completionBox.hidden = false;
      completionBox.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'nearest' });
    }
  };

  const retryProgram = async (programId, btn) => {
    if (!retryUrl || !currentJobId) return;
    btn.disabled = true;
    btn.textContent = '重試請求中...';
    const paper = container.querySelector(`.batch-paper[data-program-id="${programId}"]`);
    if (paper) {
      paper.dataset.status = 'pending';
      paper.querySelector('[data-paper-status-text]').textContent = '準備重新生成...';
      paper.querySelector('.batch-paper__fail-box').hidden = true;
    }
    setFace('(・ω・)');
    setBubble('小助手重新整備出發！');
    try {
      const form = new FormData();
      if (csrfToken) form.append('csrf_token', csrfToken);
      form.append('program_id', programId);
      form.append('job_id', currentJobId);
      const resp = await fetch(retryUrl, { method: 'POST', body: form, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!resp.ok) throw new Error(`重試失敗 (${resp.status})`);
      if (!isPolling) startPolling();
    } catch (err) {
      alert(`重試失敗：${err.message || '連線錯誤'}，請稍候再試。`);
      if (paper) {
        paper.dataset.status = 'failed';
        paper.querySelector('.batch-paper__fail-box').hidden = false;
      }
      setFace('(；´Д｀)');
      setBubble('這所學校卡住了，點紙上的重試');
    } finally {
      btn.disabled = false;
      btn.textContent = '重試此校';
    }
  };

  if (startBtn) startBtn.addEventListener('click', startBatch);
  container.addEventListener('click', event => {
    const retryBtn = event.target.closest('[data-retry-btn]');
    if (retryBtn && retryBtn.dataset.programId) retryProgram(retryBtn.dataset.programId, retryBtn);
  });

  window.addEventListener('resize', positionBubble);
  window.addEventListener('scroll', positionBubble, true);

  window.addEventListener('DOMContentLoaded', () => {
    papers.forEach(paper => {
      paper.dataset.status = 'pending';
      paper.querySelector('[data-paper-status-text]').textContent = '等待小助手開始';
      paper.querySelector('.batch-paper__fail-box').hidden = true;
    });
    ensureAssistantEffects();
    setFace('(・ω・)');
    setBubble(papers.length ? '請點「請小助手開始」' : '尚未加入目標校系');
  });

  window.addEventListener('pagehide', restoreAssistant);
})();
