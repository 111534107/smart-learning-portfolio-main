import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "file:///C:/Users/lisa2/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const outDir = "D:/democase/ai/docs/08_簡報/NAPAI_競賽_2026";
const buildDir = "C:/Users/lisa2/.codex/visualizations/2026/10/12/01a13044-0d7b-7b73-b563-c1f897d16b7d/napai-build";
const W = 1280, H = 720;
const C = { navy: "#17345C", blue: "#2850A5", cyan: "#4C91B8", ink: "#1B2736", gray: "#5D6B7D", pale: "#EEF3F8", line: "#D6E0EA", white: "#FFFFFF", gold: "#D9A441", green: "#3B8068", red: "#A8504F" };
const FONT = "Microsoft JhengHei";

function rect(slide, x, y, w, h, fill, lineFill = "none", lineWidth = 0) {
  return slide.shapes.add({ geometry: "rect", position: { left: x, top: y, width: w, height: h }, fill, line: { style: "solid", fill: lineFill, width: lineWidth } });
}
function txt(slide, text, x, y, w, h, size = 24, color = C.ink, bold = false, align = "left") {
  const s = slide.shapes.add({ geometry: "textbox", position: { left: x, top: y, width: w, height: h }, fill: "none", line: { style: "solid", fill: "none", width: 0 } });
  s.text = text;
  s.text.style = { typeface: FONT, fontSize: size, color, bold, alignment: align, verticalAlignment: "middle", autoFit: "shrinkText", lineSpacing: 1.05 };
  return s;
}
function base(title, n, kicker = "NAPAI Agentic AI 校園落地創新應用競賽") {
  const slide = p.slides.add(); slide.background.fill = C.white;
  rect(slide, 0, 0, 14, H, C.blue);
  txt(slide, kicker, 62, 32, 800, 28, 15, C.gray, true);
  txt(slide, title, 62, 76, 1120, 58, 36, C.navy, true);
  rect(slide, 62, 150, 1156, 2, C.line);
  txt(slide, String(n).padStart(2, "0"), 1160, 670, 58, 24, 15, C.gray, true, "right");
  return slide;
}
function label(slide, value, x, y, w = 280, color = C.blue) {
  rect(slide, x, y + 9, 6, 28, color);
  txt(slide, value, x + 18, y, w, 46, 22, color, true);
}
function bullets(slide, items, x, y, w, size = 23, color = C.ink, gap = 58) {
  items.forEach((t, i) => {
    rect(slide, x, y + i * gap + 16, 8, 8, C.cyan);
    txt(slide, t, x + 24, y + i * gap, w - 24, gap - 4, size, color, false);
  });
}

const p = Presentation.create({ slideSize: { width: W, height: H } });

// 1 Cover
{
  const s = p.slides.add(); s.background.fill = C.navy;
  rect(s, 0, 0, 20, H, C.cyan);
  txt(s, "NAPAI Agentic AI 校園落地創新應用競賽", 82, 72, 1050, 38, 18, "#D5E4F4", true);
  txt(s, "五專升學備審導航 Agent", 82, 188, 1080, 84, 52, C.white, true);
  txt(s, "五年級二技校系要求比對與補件引導", 84, 286, 1040, 52, 29, "#D5E4F4", false);
  rect(s, 84, 384, 96, 5, C.gold);
  txt(s, "校園自主命題組｜智慧教務與學習支援", 84, 416, 900, 40, 21, C.white, true);
  txt(s, "整合五專在校成果，先協助五年級準備二技備審", 84, 478, 1080, 62, 24, "#D5E4F4");
  txt(s, "競賽原型提案｜資料使用去識別化或合成測試資料", 84, 642, 1050, 26, 16, "#B9CBE0");
}

// 2 Problem
{
  const s = base("五專學生需把在校成果接上升學準備", 2);
  label(s, "五年級升二技情境", 72, 182, 340);
  bullets(s, ["五年在校累積的成績、證照、活動、競賽與專題資料分散", "準備二技時須逐校核對招生要求與備審項目", "不確定哪些資料已備妥、還缺什麼，以及如何呈現個人貢獻"], 82, 242, 650, 25, C.ink, 78);
  rect(s, 820, 214, 2, 368, C.line);
  txt(s, "需要的協助", 866, 228, 300, 42, 26, C.blue, true);
  txt(s, "把二技校系要求\n和五專在校成果\n接成一條準備流程", 866, 292, 315, 182, 30, C.navy, true);
  txt(s, "系統提供下一步引導；正式資料仍由學生或教師確認。", 866, 500, 310, 70, 20, C.gray);
}

// 3 Needs evidence
{
  const s = base("畢業學長姐回顧指出升學方向與成果呈現痛點", 3);
  txt(s, "匿名問卷｜近一年畢業學長姐｜2026/09/24｜n = 4", 74, 176, 980, 34, 18, C.gray, true);
  const rows = [
    ["不知道如何連結升學方向", "4 / 4"],
    ["不知道如何呈現專題成果", "4 / 4"],
    ["準備時曾需要重找資料", "4 / 4"],
    ["不清楚應準備哪些資料", "3 / 4"],
  ];
  rows.forEach((r, i) => {
    const y = 242 + i * 76;
    txt(s, r[0], 84, y, 600, 42, 24, C.ink, i === 0);
    rect(s, 720, y + 11, 270, 22, C.pale);
    rect(s, 720, y + 11, i < 3 ? 270 : 202, 22, i < 3 ? C.blue : C.cyan);
    txt(s, r[1], 1020, y, 128, 42, 23, C.navy, true);
  });
  txt(s, "樣本僅 4 位近一年畢業者，屬回顧性線索；尚未直接調查目前專四、專五學生。提交前須核對訪談摘要。", 82, 570, 1090, 54, 17, C.gray);
  txt(s, "資料來源：學長姐痛點問卷分析與需求功能對照（2026/10/09）", 82, 637, 980, 24, 14, C.gray);
}

// 4 Solution
{
  const s = base("競賽原型先驗證五年級升二技備審流程", 4);
  txt(s, "使用情境：五專五年級學生整理目標二技校系備審", 80, 182, 1060, 42, 24, C.navy, true);
  const steps = ["選擇\n目標二技", "讀取\n招生要求", "比對已確認\n五專學習資料", "整理缺項\n與下一步", "學生／教師\n確認結果"];
  const x0 = 80, y = 300, bw = 198, gap = 45;
  steps.forEach((t, i) => {
    const x = x0 + i * (bw + gap);
    rect(s, x, y, bw, 112, i === 4 ? C.navy : C.pale, i === 4 ? C.navy : C.line, 1);
    txt(s, String(i + 1).padStart(2, "0"), x + 18, y + 12, 46, 26, 17, i === 4 ? "#D5E4F4" : C.blue, true);
    txt(s, t, x + 18, y + 42, bw - 36, 60, 22, i === 4 ? C.white : C.ink, true, "center");
    if (i < steps.length - 1) txt(s, "→", x + bw + 5, y + 34, 38, 38, 27, C.cyan, true, "center");
  });
  txt(s, "資料不足或規則不明時停止自動推進，提示補件或人工確認。", 82, 468, 1030, 46, 22, C.gray);
}

// 5 Agentic method
{
  const s = base("Agent 為五專五年級拆解二技備審任務", 5);
  const cols = [
    ["任務分解", "讀取目標二技校系要求\n整理五年在校已確認資料\n逐項比對備審項目"],
    ["工具與資料", "二技招生要求資料\n五專學生學習資料\n缺件比對服務"],
    ["狀態與調整", "已完成／待補／待確認\n資料不足時要求補充\n錯誤時保留人工流程"],
  ];
  cols.forEach((c, i) => {
    const x = 78 + i * 390;
    rect(s, x, 218, 340, 5, i === 1 ? C.cyan : C.blue);
    txt(s, c[0], x, 242, 330, 46, 26, C.navy, true);
    txt(s, c[1], x, 308, 330, 142, 22, C.ink, false);
  });
  rect(s, 78, 496, 1120, 1, C.line);
  txt(s, "Agent 的輸出是可追溯的待確認建議，不是錄取判斷或正式審查結論。", 80, 528, 1090, 60, 23, C.blue, true);
}

// 6 Architecture
{
  const s = base("原型串接在校資料、二技要求與人工確認", 6);
  const nodes = [
    ["學生端", "選目標二技校系\n檢視缺件\n確認資料", 78, 230, 240],
    ["資料來源", "已核對二技要求\n學生已確認的在校資料", 382, 230, 260],
    ["比對與 Agent 流程", "任務狀態\n條件比對\n下一步建議", 706, 230, 270],
    ["人工確認", "學生／教師\n確認、修正或補件", 1032, 230, 180],
  ];
  nodes.forEach(([title, body, x, y, w], i) => {
    rect(s, x, y, w, 184, i === 2 ? "#E6EEF9" : C.pale, C.line, 1);
    rect(s, x, y, w, 8, i === 2 ? C.blue : C.cyan);
    txt(s, title, x + 18, y + 24, w - 36, 40, 22, C.navy, true);
    txt(s, body, x + 18, y + 78, w - 36, 84, 18, C.ink, false);
    if (i < nodes.length - 1) txt(s, "→", x + w + 10, y + 72, 32, 38, 24, C.cyan, true, "center");
  });
  txt(s, "系統不登入或爬取校務系統；需要外部 AI 時遵守告知與資料遮蔽規則。", 80, 476, 1100, 52, 21, C.gray);
}

// 7 Safety
{
  const s = base("人工確認與資料保護是流程的一部分", 7);
  const items = [
    ["資料來源", "只讀取已核對的校系要求與學生已確認資料。"],
    ["人員權限", "登入身分決定可檢視資料；教師只看授權範圍。"],
    ["敏感資料", "缺曠只存合計、不送外部 AI，備審預設不放。"],
    ["AI 邊界", "AI 不核定資格、不給錄取判斷、不自行發布。"],
    ["可追溯性", "保留來源、版本、任務狀態及人工確認紀錄。"],
  ];
  items.forEach((it, i) => {
    const y = 184 + i * 86;
    txt(s, it[0], 82, y, 180, 38, 21, C.blue, true);
    rect(s, 272, y + 16, 18, 3, C.cyan);
    txt(s, it[1], 318, y - 2, 810, 48, 21, C.ink);
  });
  txt(s, "展示資料使用去識別化或合成測試資料。", 82, 632, 1000, 30, 17, C.gray, true);
}

// 8 Status / scope
{
  const s = base("先驗證五專五年級備審主線，不把規劃寫成完成", 8);
  label(s, "既有專題基礎", 82, 190, 430, C.green);
  bullets(s, ["目標校系與學習資料管理", "缺件比對與備審產出骨架", "教師確認與版本紀錄"], 92, 246, 500, 22, C.ink, 66);
  rect(s, 630, 192, 2, 350, C.line);
  label(s, "競賽展示範圍", 694, 190, 450, C.blue);
  bullets(s, ["單一二技校系、固定測試學生", "展示五專成果比對、缺件與人工確認", "AI OCR／推薦等尚未完成項目不列為既有成果"], 704, 246, 482, 21, C.ink, 82);
  txt(s, "依 2026/10/10 系統完整性檢查；錄製前請再確認目前可操作版本。", 82, 605, 1100, 32, 15, C.gray);
}

// 9 Test plan
{
  const s = base("以固定測試案例檢查比對結果與失敗處理", 9);
  const rows = [
    ["案例 A", "所需資料齊全", "所有項目正確標示完成"],
    ["案例 B", "缺少一項證明", "指出缺項並提供下一步"],
    ["案例 C", "資料內容不確定", "標示待確認，不寫入正式資料"],
    ["案例 D", "校系規則查無來源", "停止推論並提示人工核對"],
  ];
  const xs = [82, 252, 572, 930], widths = [150, 300, 264];
  txt(s, "案例", xs[0], 196, widths[0], 36, 18, C.gray, true);
  txt(s, "輸入情境", xs[1], 196, widths[1], 36, 18, C.gray, true);
  txt(s, "預期結果", xs[2], 196, 520, 36, 18, C.gray, true);
  rect(s, 82, 234, 1080, 2, C.blue);
  rows.forEach((r, i) => {
    const y = 254 + i * 72;
    txt(s, r[0], xs[0], y, widths[0], 40, 20, C.blue, true);
    txt(s, r[1], xs[1], y, widths[1], 46, 20, C.ink);
    txt(s, r[2], xs[2], y, 540, 46, 20, C.ink);
    rect(s, 82, y + 54, 1080, 1, C.line);
  });
  txt(s, "實測前不填入正確率、處理時間或成功案例數；完成後附操作紀錄與錯誤類型。", 82, 574, 1070, 52, 20, C.gray);
}

// 10 Metrics
{
  const s = base("評測記錄可量化比對品質與人工介入", 10);
  const metrics = [
    ["要求比對正確率", "正確比對項目 ÷ 全部測試項目"],
    ["缺件漏判數", "存在缺件但未提示的案例數"],
    ["錯誤提醒數", "無缺件卻被標為待補的項目數"],
    ["人工確認比例", "需要人工確認的案例 ÷ 全部案例"],
    ["完成時間", "從開始比對到顯示結果的實測時間"],
  ];
  metrics.forEach((m, i) => {
    const y = 184 + i * 78;
    txt(s, m[0], 84, y, 360, 42, 22, C.navy, true);
    rect(s, 464, y + 18, 52, 3, C.cyan);
    txt(s, m[1], 546, y, 580, 42, 20, C.ink);
  });
  rect(s, 82, 598, 1080, 1, C.line);
  txt(s, "本頁為評測方法；所有數值須由團隊完成測試後再填入。", 84, 618, 1080, 30, 17, C.red, true);
}

// 11 Implementation
{
  const s = base("從五年級二技原型擴展到五專全學程服務", 11);
  label(s, "近期原型", 82, 190, 300);
  bullets(s, ["先以五年級單一二技校系與合成資料驗證", "由管理者核對來源與招生要求，再提供學生使用", "採人工確認處理資料錯誤與規則變更"], 92, 246, 500, 22, C.ink, 72);
  rect(s, 630, 192, 2, 342, C.line);
  label(s, "後續擴展", 694, 190, 300, C.cyan);
  bullets(s, ["延伸至一至五年級的學習資料累積", "加入專四、專五學生試用與回饋", "追蹤招生資料更新、錯誤修正與維護成本"], 704, 246, 480, 22, C.ink, 72);
  txt(s, "正式導入需取得場域授權，並依校方資安與個資規範另行審查。", 82, 604, 1100, 42, 18, C.gray);
}

// 12 Team and disclosures
{
  const s = base("三人團隊以需求、系統與驗證協作", 12);
  const roles = [
    ["需求與場域", "整理訪談與問卷\n核對校系要求來源"],
    ["系統與 Agent", "維護比對流程\n呈現任務狀態與結果"],
    ["評測與展示", "建立測試案例\n記錄結果並製作 Demo"],
  ];
  roles.forEach((r, i) => {
    const x = 82 + i * 370;
    rect(s, x, 214, 322, 4, i === 1 ? C.cyan : C.blue);
    txt(s, r[0], x, 238, 320, 46, 24, C.navy, true);
    txt(s, r[1], x, 306, 318, 86, 20, C.ink);
  });
  rect(s, 82, 448, 1080, 1, C.line);
  txt(s, "技術與資源", 84, 474, 220, 36, 20, C.blue, true);
  txt(s, "Flask／Python、關聯式資料庫、Google Gemini API（僅用於已告知且允許的功能）；測試使用合成或去識別化資料。", 316, 470, 830, 72, 18, C.ink);
  txt(s, "作品以團隊既有學習歷程系統為基礎；競賽提案聚焦備審導航 Agent 的流程驗證，並如實揭露尚未完成項目。", 84, 576, 1060, 62, 18, C.gray);
}

await fs.mkdir(buildDir, { recursive: true });
await fs.mkdir(outDir, { recursive: true });
for (const [i, slide] of p.slides.items.entries()) {
  const blob = await p.export({ slide, format: "png", scale: 2 });
  await fs.writeFile(path.join(buildDir, `slide-${String(i + 1).padStart(2, "0")}.png`), new Uint8Array(await blob.arrayBuffer()));
}
const pptx = await PresentationFile.exportPptx(p);
await pptx.save(path.join(buildDir, "proposal-draft.pptx"));
console.log(JSON.stringify({ slides: p.slides.items.length, draftPptx: path.join(buildDir, "proposal-draft.pptx") }));
