// 學生端版面量測（2026-11-03）：在展示站登入學生後，貼到瀏覽器主控台執行。
// 每頁量：高度（幾個 800px 螢幕）、按鈕數、實心主要按鈕數、首屏按鈕數、標題數、字級種類、字數、標籤與灰字數。
(async () => {
  const pages = ['/student/dashboard', '/student/learning-profile', '/student/learning-profile/upload',
    '/student/learning-profile/credentials', '/student/portfolio', '/student/portfolio/new',
    '/student/targets', '/student/matching', '/student/schedule', '/student/autobiography'];
  const audit = async (path) => {
    const html = await (await fetch(path)).text();
    const frame = document.createElement('iframe');
    frame.style.cssText = 'position:fixed;left:-2000px;top:0;width:1280px;height:800px;';
    document.body.appendChild(frame);
    await new Promise((resolve) => { frame.onload = resolve; frame.srcdoc = html.replace('<head>', `<head><base href="${location.origin}/">`); });
    await new Promise((resolve) => setTimeout(resolve, 400));
    const doc = frame.contentDocument, win = frame.contentWindow;
    const visible = (el) => { const r = el.getBoundingClientRect(); const s = win.getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
    const main = doc.querySelector('main') || doc.body;
    const actions = [...main.querySelectorAll('a.button, button, input[type=submit]')].filter(visible);
    const filled = actions.filter((el) => ['rgb(28, 34, 48)', 'rgb(36, 72, 201)'].includes(win.getComputedStyle(el).backgroundColor));
    const sizes = new Set([...main.querySelectorAll('*')]
      .filter((el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()))
      .map((el) => win.getComputedStyle(el).fontSize));
    const result = {
      path,
      heightScreens: +(doc.documentElement.scrollHeight / 800).toFixed(1),
      actions: actions.length,
      filledPrimary: filled.length,
      actionsAboveFold: actions.filter((el) => el.getBoundingClientRect().top < 800).length,
      headings: main.querySelectorAll('h1,h2,h3').length,
      fontSizes: sizes.size,
      chars: main.innerText.replace(/\s/g, '').length,
      notices: main.querySelectorAll('.notice,.tag,.small.muted,.muted').length,
    };
    frame.remove();
    return result;
  };
  const rows = [];
  for (const path of pages) rows.push(await audit(path));
  console.table(rows);
})();
