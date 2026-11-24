# Copilot 自傳頁配色修改說明

## 修改內容

- 自傳 Canva 編輯頁的外層工作區沿用學生端既有的 `--sheet`、`--ink`、`--line` 與 `--accent` token，工具列、目錄、卡片與提示區不再混用深白淺白底色。
- 中間段落編輯區與右側即時預覽統一成白底黑字、細灰邊、標楷體與輕微陰影，兩處紙面外觀一致。
- 段落標題改為一般文字色加粗；目前段落以青綠／藍綠 `--accent` 左色條或底線標示，不再使用鮭魚紅／橘紅標題。
- 超過字數預算時，只將字數文字與 `⚠` 圖示標成警示色；目錄與手機小標籤最多保留左側 3px 警示色條，不再整塊填紅底紅框。
- 手機 375px 結構與段落切換、編輯／預覽模式維持不變。

## 色彩對應表

| 用途 | 淺色外觀 | 深色外觀 |
|---|---|---|
| 外層卡片／工具列 | `--sheet`、`--ink`、`--line` | `--sheet`、`--ink`、`--line` |
| 強調色與目前段落 | `--accent`（既有深灰藍綠） | `--accent`（既有淺藍綠） |
| 編輯紙／預覽紙 | 白色 `#ffffff`、黑字 `#000000`例外 | 白色 `#ffffff`、黑字 `#000000`例外 |
| 超標警示文字／圖示 | `--bio-warn`（深紅 `#9b3d36`） | `--bio-warn`（粉紅 `#e8a39b`） |
| 一般次要文字 | `--muted`／`--ink-soft` | `--muted`／`--ink-soft` |

淺色與深色外觀主要文字都使用既有對應 token；編輯紙與預覽紙固定黑字白底，屬於紙面例外。

## 第二輪：深色外觀統一

| 區塊 | 淺色外觀底色／文字色／邊框色 | 深色外觀底色／文字色／邊框色 |
|---|---|---|
| `.paragraph-review` 及證據／疑點／建議三區 | `--sheet`／`--ink`／`--line` | `--sheet`／`--ink`／`--line` |
| `.evidence-item` | `--sheet`／`--ink`／`--line` | `--sheet`／`--ink`／`--line` |
| `.unsupported-list` | 透明底／`--ink`／左邊 `--warn` 3px 色條 | 透明底／`--ink`／左邊 `--warn` 3px 色條 |
| `.review-line` | `--ink` | `--ink` |
| `.teacher-comment`、段落留言 | `--sheet`／`--ink`／`--line`；警示只用左邊 `--warn` 3px 色條 | `--sheet`／`--ink`／`--line`；警示只用左邊 `--warn` 3px 色條 |
| 素材區 `.bio-pieces`、`.bio-piece`、`.canva-aux-drawer` | `--sheet`／`--ink`／`--line` | `--sheet`／`--ink`／`--line` |
| `.alert`、`.alert--soft`、`.notice`、`.notice--warn` | 透明底／文字用 `--ink`；左邊 3px 分別為 `--danger`／`--ok`／`--warn` | 透明底／文字用 `--ink`；左邊 3px 分別為 `--danger`／`--ok`／`--warn` |
| `.draft__budget-warning` | 透明底／`--ink`／左邊 `--warn` 3px 色條 | 透明底／`--ink`／左邊 `--warn` 3px 色條 |
| `.budget-data-update`／資料更新提示 | `--sheet` 或透明提示底／`--ink`／`--line`，警示保留左邊 3px 色條 | `--sheet` 或透明提示底／`--ink`／`--line`，警示保留左邊 3px 色條 |
| `.canva-paragraph-nav` 按鈕 | `--sheet`／`--ink`／`--line` | `--sheet`／`--ink`／`--line` |
| `.bio-images` | `--sheet`／`--ink`／`--line` | `--sheet`／`--ink`／`--line` |
| 中間編輯框／右側預覽紙／導師中間編輯內容 | 白色 `#ffffff`／黑字 `#000000`例外／淺灰邊框例外 | 白色 `#ffffff`／黑字 `#000000`例外／淺灰邊框例外 |
