# 開發日誌

## 2026-11-08 學生頂端列合併成 5 項＋帳號選單；首頁第一屏先放「今天先完成哪一步」（Claude）

- **起因**：使用者覺得操作不直覺。學生頂端列有 7～8 個選單（我的五年、成績單、證照、活動與經歷、畢業門檻、目標與備審、我的待辦、通知），旁邊再加導覽、字體大小、怎麼操作、名字、登出。改版前用合成學生（`create_local_demo_app`，5057 預覽站）量：1280px 寬時頁面 scrollWidth 1433，整頁左右捲動；900px 時頂端列折成兩排。首頁一打開是五年路線圖，「今天先完成哪一步」的按鈕在 900×700 視窗要到 719px、375×812 手機要到 1112px，第一屏看不到。
- **頂端列**（`partials/nav.html` 的 `student_masthead`，其他角色的 `masthead` 沒動）：
  - 主選單只留 5 項：我的五年／我的資料／畢業門檻／目標與備審／我的待辦（未完成數、提案小圓點照舊）。
  - 「我的資料」＝成績單＋證照＋活動與經歷（轉學生多一個「抵免進度」，原本放主選單，改放這裡）。這幾頁的頂端列下面多一排分頁標籤（`<nav class="subnav" aria-label="我的資料">`），所在頁 `aria-current="page"` 加底線；主選單的「我的資料」用 `aria-current="true"`。上傳、辨識中、確認頁沿用原本的 `page_label`，也會顯示分頁標籤。
  - 字體大小、看這頁的導覽、怎麼操作、登出收進右邊的帳號選單（頭像＋名字按鈕，`aria-expanded`／`aria-controls`）；「通知」移到選單外面、帳號按鈕左邊，照舊顯示未讀數。
  - 寬度不夠時依序收起帳號名稱（≤1180px）、網站名稱（≤1040px）、縮小間距（≤860px）；≤700px 主選單收成「選單」按鈕，打開後直列在頂端列下面。沒有 JavaScript 時主選單直接攤開。
  - 開合程式在 `components.js`（`[data-menu-toggle]`）：點按鈕開關、同時只開一個、Esc 關閉並把焦點還給按鈕、點外面或 Tab 離開面板就關、面板裡點了連結或導覽就關（字體大小可以連續調，不關）。
  - `design-system.css`：舊的學生頂端列規則（900px 以下主選單整排左右捲動、520px 以下排成五格）換成新規則，放在原位置。
- **首頁第一屏**（`student_home.html`、`design-system.css`）：打招呼標題（`#route-title`，好久不見關掉後仍把焦點放這裡）和「今天先完成哪一步」移到最上面；第一張卡片（最重要的一步＋按鈕）緊接在標題下，概況（五年累積／待處理／最近成果）放卡片下面。萬一沒有引導卡片就顯示原本的 `next_card`（主線下一步）。五年路線圖、小人物、四個地方全部保留，接在下面，最大寬度 60rem；標題字級從 `--fs-hero` 降一級成 `--fs-display`。導覽順序改成先「今天先完成哪一步」再路線圖。
- **瀏覽器驗收**（5057 預覽站，合成學生 student_demo；Playwright 用系統 Edge 跑 1280×800、900×700、768×1024、375×812）：
  - 四種寬度的首頁、成績單、證照、活動與經歷頁 scrollWidth 都等於視窗寬度，沒有左右捲動。
  - 首頁下一步按鈕底部：1280 → 228px、900 → 245px、768 → 240px、375 → 384px，都在第一屏內（改版前 787／719／659／1112）。
  - 原本每個入口都找得到：主選單 5 項；成績單／證照／活動與經歷（與轉學生的抵免進度）在「我的資料」分頁標籤；通知在外面；字體大小、導覽、怎麼操作、登出在帳號選單。
  - 鍵盤：Tab 到帳號按鈕按 Enter → `aria-expanded="true"`、面板出現，再 Tab 進到字體按鈕；Esc → 關閉且焦點回到按鈕；點外面 → 關閉。375px：「選單」按鈕一開始收起，按下展開 5 項、Esc 收回。
  - 前後截圖放在本組共用筆記資料夾 `student-nav-shots/`（before-*／after-*，含帳號選單與手機選單打開的畫面），沒有放進專案。
- **測試**：新增 `tests/test_student_nav.py` 11 項（主選單 5 項、帳號選單內容與 `aria-expanded`、通知在外面、手機選單按鈕、我的資料四個子頁的分頁標籤與所在頁、其他頁沒有分頁標籤、首頁下一步在路線圖前面、CSS 與開合程式的關鍵規則）。改 `test_transcript_credential_split.py`（成績單／證照改在分頁標籤找）與 `test_student_flow.py`（抵免進度改在「我的資料」分頁標籤）。
- **沒有動的**：老師、科辦、管理員與未登入的頂端列；`介面維修清單_2026-11-04.md` 不在這次範圍，沒有勾。


## 2026-11-08 管理員首頁改版：今天要處理什麼（Claude）

- **起因**：管理員首頁還停在舊送審流程，寫著「科辦帳號：可登錄共同審查結論」「教師帳號：可查看指派的審查項目」「全部送件」，「最近送件動態」直接顯示英文狀態 `submitted`；規格「四、管理員」要處理的事（核准 AI 擷取的候選更新、資料來源失效標紅、核對資料分類、指派導師）都沒出現在首頁。選單還有規格要先隱藏的「專題規則」。
- **盤點已存在、需要管理員處理的資料**（只接現有資料，沒有做新功能）：
  - 候選校系待核准：`AdmissionProgram.status = candidate` → 校系資料頁。
  - 候選招生日程待核准：`AdmissionScheduleEvent.status = candidate`，同一管道同一學年度算一組 → 招生資料 Agent 頁的「候選招生日程」。
  - 簡章更新待擷取：`PublicSourceChange.status` 不是 `extracted` → Agent 頁的「偵測到的更新」。
  - 資料來源檢查失敗：網址來源最近一次 `admission_source_check` 任務失敗 → Agent 頁的「官方來源」。
  - 資料分類待核對：簡章評分項目與報考資格 `mapping_status = pending` → 校系資料頁。
  - 班級還沒指派導師：有啟用學生的班級沒有任何 `ClassAdvisor` → 導師班級頁。
  - 近 7 天 OCR 辨識失敗：`DocumentExtraction.status = failed` → OCR 辨識設定頁（失敗紀錄不會自己消失，所以只算近 7 天）。
  - 雲端儲存未連線：設定要存 Google 雲端硬碟但沒連線時才出現 → 檔案存放設定頁。
  - 學生端的 `agent_plan.py` 是學生自己的待辦與提案，不歸管理員處理，沒有放進來。
- **新首頁**（`admin_dashboard.html`、`routes/main.py::admin_dashboard`、新檔 `services/admin_todos.py`）：
  - 一句話說明「今天有 N 類事情要處理」；上方是可以點的待辦數字卡，每張直接連到處理頁，0 件的卡變淡。
  - 下方是帳號人數，職責改成正確的文字：學生「整理成績、證照與學習歷程」、導師「查看本班學生的畢業門檻與備審資料」、科辦「核准電子獎狀、核對畢業缺口」；加上「帳號管理」與「操作紀錄」入口。
  - 拿掉「全部送件」「最近送件動態」與舊審查字樣；首頁不再顯示任何英文狀態。
- **資料來源標紅**：招生資料 Agent 頁的官方來源，最近一次檢查失敗的那一列左側標紅，並顯示「上次檢查失敗，網址可能失效」；三個區塊加上錨點，首頁的卡可以直接捲到。
- **選單**：依規格隱藏「專題規則」，只從「課程與招生」群組拿掉；`/admin/project-types` 路由與資料保留。
- **測試**：新增 `tests/test_admin_dashboard_todos.py`（5 項，全部合成資料：各卡數字、連結可開、來源標紅、雲端未連線、空系統）；`test_work_layer.py` 管理員首頁改成檢查待辦區與舊字樣不存在；`test_auth.py` 改成檢查選單沒有「專題規則」但路由仍可開。
- **瀏覽器驗收**：用 5063 預覽站和合成管理者登入，首頁顯示 4 類待處理（候選校系 1、候選日程 1、來源檢查失敗 1、資料分類 106 來自種子資料）；點「資料來源檢查失敗」進到 Agent 頁官方來源，失效來源有紅標；其他卡的處理頁都能開；畫面沒有「送件」「共同審查」「submitted」；選單沒有「專題規則」。

## 2026-11-08 導師首頁整理：畢業門檻放最上面、整列可點、拿掉舊審查畫面（Claude）

- **起因**：2026-10-10 定案「專題共同審查不在本系統範圍」，導師端畫面還留著選單「我的審查」和首頁最下面的「專題審查指派（後續擴充）」；導師最需要看的畢業門檻提醒要往下捲才看到，名單只有小小的 `G-` 編號能點。
- **拿掉舊審查畫面**（只藏畫面）：導師選單只剩「工作台」（加上原本的「通知」）；首頁拿掉「專題審查指派」區塊與送意見表單。`app/routes/review.py` 的 `/teacher/reviews` 路由與 `SubmissionAssignment` 舊資料都保留；`routes/main.py::teacher_dashboard` 不再查指派資料，用不到的 import 刪掉。
- **畢業門檻提醒移到最上面**：導師一進首頁就先看到四張數字卡、比例條和「需要優先關心的學生」；本班人數／等待你確認／已選目標校系的數字卡與本班學生表放在下面。
- **整列可點**：優先名單（→ 畢業門檻案件頁）和本班學生表（→ 學生頁）每一列右邊都有「查看」按鈕（有待確認備審的學生顯示「確認」，左邊有橘色細線）。按鈕的 `::after` 蓋住整列，點列上任何位置都進到同一頁，不需要 JS；CSS 在 `design-system.css` 最下面 `.data-table--rowlink`。
- **等待你確認 N 份**：N 大於 0 時數字卡變成連結：只有一位學生在等確認，直接連到他的學生頁；多位時捲到本班學生表。
- **測試**：`test_work_layer.py` 改成檢查畫面上沒有「我的審查」「專題審查指派」、選單只剩「工作台」「通知」、`/teacher/reviews` 路由與舊指派資料仍在；`test_graduation_dashboards.py` 新增 1 項（畢業門檻在學生表上面、兩張表每列都有查看按鈕、沒有待確認時數字卡不連結）；`test_main_line_routes.py` 加 1 個斷言（只有一位學生待確認時數字卡連到他的學生頁）。
- **瀏覽器驗收**（5063 預覽站，run_demo 合成資料加兩位合成專五學生「測試甲生／測試乙生」）：合成導師 teacher01 登入，視窗 1024×768 時畢業門檻提醒從 216px 開始、優先名單 4 列都在第一屏；選單是「工作台、通知」；8 列（優先 4＋本班 4）在每一格中央做點擊判定都落在該列自己的連結，實際點王小明那列的資料格進到王小明的學生頁；所有「查看」與「等待你確認 1 份」連結都能開（200，林小美學生頁）；375px 寬時頁面不會左右捲動，整列點擊一樣正確。

## 2026-11-08 科辦電子獎狀補完：TA 證明、社團證明、核准／退回通知學生、審核頁直接對照獎懲（Claude）

- **起因**：規格「三、科辦／行政」寫電子獎狀有三種（科上派的服務、TA 證明、社團證明），系統只有「服務證明」；科辦核准或退回後學生不會收到通知；審核頁只有一顆「對照學生上傳的獎懲記錄」按鈕，要另開分頁才看得到原文。
- **類別與申請條件**（`services/certificate_service.py`）：`KINDS` 加上 `ta`「TA 證明」、`club`「社團證明」，沿用同一套申請與核准流程。**可申請條件是我的判斷**：規格只寫「加 TA 證明、社團證明」，沒寫怎麼認定；TA 與社團在學校系統也都記成嘉獎，所以一樣只接受從學校獎懲記錄匯入的紀錄，再看匯入時的獎懲事由原文：
  - 服務證明：類別是服務學習（和原本一樣）。
  - TA 證明：事由有「TA」（前後不能接英文字母，所以「DATA」不算）、「助教」或「教學助理」。
  - 社團證明：事由有「社團」或「社長」。
  - 看的是 `school_award_records.reason`（匯入時原文），學生之後改經歷標題不會多出可申請的類別；舊資料沒有逐列原文才退回看經歷標題。
  - 同一筆符合多種時（例如「協助資管科麗山國中社團活動」同時是服務學習、也提到社團），學生在經歷頁用單選鈕選一種；只符合一種就直接顯示「可以請科辦開一張『TA 證明』」。科辦審核時仍可改標題。
  - `award_certificates` 加 `kind` 欄位；內文結尾依類別不同（服務「熱心服務、表現認真」、TA「協助課程教學、認真負責」、社團「積極參與社團、表現優良」）。科辦清單多一欄「類別」。
- **通知學生**：核准時寄「科辦已核准你的電子獎狀『TA 證明』，可以查看與列印。」連到獎狀頁；退回時寄「科辦退回……：原因」連到經歷修改頁。沿用 `Notification`，原本 `case_id`、`event_id` 不可空，新增遷移 `b20261108a01`（接在 `b20261105c01` 後面）把兩欄改成可空、加 `link` 欄位；`award_certificates.kind` 也在同一支遷移。SQLite 用 batch 模式重建表，`reflect_kwargs={"resolve_fks": False}`，因為遷移鏈裡沒有建立 `users` 表。降版時會先刪掉非案件的通知（舊表結構放不下）。
- **通知頁**：非案件的通知連到新路由 `/notifications/<id>/open`（只有收件人能開，標為已讀後轉到 `link`；只接受 `/` 開頭、不是 `//` 的站內路徑，避免被拿去轉外站）。頁首說明改成「畢業缺口案件與電子獎狀」。
- **審核頁對照獎懲**（`staff_certificate_review.html`）：新增「對照學校獎懲記錄」區塊，直接顯示匯入時的獎懲事由原文、日期與獎懲名稱；學生後來改過經歷標題會提醒「請以原文為準」。學生上傳的原始檔是圖片就用 `<img>`、PDF 就用 `<iframe>` 直接嵌在頁面（沿用 `certificate.staff_source`），另留「另開視窗」連結；沒有原始檔或不能預覽時寫明原因。
- **沒有動的**：科辦首頁 `dashboard.html` 的「科上派的服務證明」字樣，因為同一個資料夾裡另一個對話正在改這個檔案，沒有一起改，留給之後統一。
- **測試**：新增 `tests/test_certificate_kinds_notices.py` 14 項（三種類別判斷、DATA 不算 TA、改標題不能多出類別、單選鈕、科辦清單類別、核准／退回通知與連結、沒寫退回原因不寄通知、別人不能開我的通知、外站連結不轉址、審核頁顯示原文與圖片預覽、沒有原文與原始檔也能顯示、遷移升降版）。原本 `test_award_certificates.py` 不用改。
- **瀏覽器驗收**（5071 預覽站，`create_local_demo_app` 合成資料，另加一筆合成獎懲紀錄「1141學期擔任資料庫系統課程TA認真負責」與合成獎懲記錄圖片）：合成學生在經歷頁看到「可以請科辦開一張『TA 證明』」→ 申請 → 合成科助在審核頁直接看到獎懲原文、2025/12/30 嘉獎 1 次與原始檔圖片 → 核准（產生驗證碼）→ 合成學生的通知頁出現「科辦已核准你的電子獎狀『TA 證明』」（未讀）→ 點下去開到 TA 證明獎狀頁。

## 2026-11-03 合併校園主題與學校 Google 登入兩個分支

日期：2026-11-03（台灣時間）

開發者：Claude（使用者指示「先合併兩個分支」）

目標：把 `feat/campus-theme`（校園招生風主題、版型系統計畫書）與 `feat/school-google-login`（學校 Google 一鍵登入）合併進主開發分支 `feat/google-docs-autobiography`。

合併：
- `23a1f82` 合併 `feat/campus-theme`：交接文件最上面衝突，兩邊段落都保留。
- `d8ec10e` 合併 `feat/school-google-login`：開發日誌最上面衝突，兩邊段落都保留（11-03 放上面）。
- 資料庫遷移合併後只有一個最新版本 `b20261102e01`（學校登入的 `google_sub`）。

驗證結果：
- 完整測試 1043 通過、2 略過（`logs/test-runs/merge-full-20261103`）；略過的兩項同前：上傳文件刪除與保留政策（M10）待決、組員上傳前預覽旋轉未移入。
- 展示站改由 `D:\democase\.claude\launch.json` 的 `story-merged-5013` 從本資料夾啟動（不帶學號參數、OCR 照預設真實辨識）。檢查：目標校系、招生時程、自傳頁有校園主題與快捷鈕；學生首頁沒有；登入頁有學校 Google 登入按鈕。
- 發現：視窗寬度不足 1360px 時，左下角快捷鈕在捲動中會蓋到卡片第一行；已補進版型計畫 Task 8。

未推送；是否合併到 `main`、推送到哪裡待使用者決定。

## 2026-11-03 整合組員的學校 Google 一鍵登入

日期：2026-11-03（台灣時間）

開發者：Claude（工作資料夾 `D:\democase\_worktrees\ai-wt-school-login`，分支 `feat/school-google-login`，從 `d5f3aff` 開出）

目標：使用者要求把組員 111534107（`smart-learning-portfolio-main` 提交 `3187cb5`）的學校 Google 一鍵登入整合進來：只限 `@stu.ukn.edu.tw`、只限管理員先綁定的既有學生。

修改檔案：
- 用 `git cherry-pick -n 3187cb5` 套用組員的程式與測試：`app/services/school_google_login.py`、`app/routes/main.py`（`/auth/google`、`/auth/google/callback`）、`app/routes/admin.py`（綁定學校信箱）、`app/models/user.py`（`google_sub`）、`login.html`、`admin_accounts.html`、`tests/test_school_google_login.py`（12 項）。`admin.py` 匯入行有衝突，兩邊都保留。
- `migrations/versions/b20261102e01_school_google_login.py`：改接本專案目前的 `a20261022e01`；`users` 表不存在或欄位已存在就跳過，用批次改表才能在 SQLite 降級。
- `.env.example`、`README.md`：範例回呼網址改 `localhost`（和 Google 文件同一個主機名稱，不然登入狀態對不上）。
- `scripts/run_local_demo.py`：帶入 `GOOGLE_LOGIN_REDIRECT_URI`；新增 `--student-no` 把合成學生的學號換成指定號碼（只在記憶體），才能驗收「信箱帳號必須等於學號」的綁定。
- 新增 `docs/03_開發紀錄/01_參考與環境設定/學校Google登入_設定步驟.md`（設定、驗收、安裝了什麼、如何移除）。
- 安裝：`google-auth[requests]==2.62.0`（PyPI 官方）到 `D:\democase\ai\.venv`，連帶 `cryptography`、`cffi`、`pycparser`、`pyasn1`、`pyasn1-modules`。

驗證結果：
- 第一次完整測試 8 項失敗，全是資料庫遷移測試：只用遷移建的空資料庫沒有 `users` 表，組員的遷移沒有檢查。加上檢查後重跑完整測試 1026 通過、9 略過。
- 另外手動確認：有 `users` 表的資料庫升級會加上 `google_sub` 欄位與唯一索引，降級會拿掉。
- 展示站（5013 埠，`--student-no 111534105`）：登入頁出現學校 Google 登入按鈕；`admin_demo` 在帳號管理綁定 `111534105@stu.ukn.edu.tw` 成功。
- 真實 Google 登入：起初 `redirect_uri_mismatch`（使用者把網址加到當天新建的另一個用戶端 `dr67…`，系統用的是 `vq74…`），改到正確用戶端後通過這關；接著回系統驗證失敗，伺服器紀錄為 `Token used too early`（電腦時間比 Google 慢 5 秒，組員程式容許誤差 0 秒），改為容許 10 秒並加測試（提交 `8025794`）。2026-11-03 10:44 使用者用 `111534105@stu.ukn.edu.tw` 登入**通過**，進到綁定的合成學生帳號（專五，因為展示站的合成學生本來就是專五）。

下一步：確認學校 Google Workspace 是否允許外部應用程式；教師要不要也能用 `@ukn.edu.tw` 登入待決定。未推送、未合併。

## 2026-11-02 校園招生風主題（參考臺中科大招生網站，首頁不動）

日期：2026-11-02（台灣時間）

開發者：Claude（工作資料夾 `D:\democase\_worktrees\ai-wt-campus-theme`，分支 `feat/campus-theme`，從 `bfbaa58` 開出；計畫書 `docs/superpowers/plans/2026-11-02-campus-theme.md`）

目標：使用者覺得 https://admission.nutc.edu.tw/ 設計得不錯，選定奶油底。只借配色與版面節奏，不用該校校徽、名稱、插圖。

修改檔案：
- `app/templates/base.html`：載入 `theme-campus.css`；首頁（`student-dashboard`、`public-home`）以外的頁面 `<body>` 加 `data-theme="campus"`；學生的非首頁頁面加入快捷鈕。
- `app/static/css/theme-campus.css`（新）：奶油底 `#fdf3e2`、白卡大圓角；白卡第一個標題變成深藍／焦糖交替的標題帶；區塊標題前加焦糖短橫線；紀錄卡、校系卡圓角陰影（減少動態效果時不上浮）；快捷鈕樣式；列印時不印底色與快捷鈕。
- `app/templates/partials/quick_dock.html`（新）：招生時程、小助手寫自傳、回到頂端。
- `tests/test_theme_campus.py`（新，9 項）：首頁不套主題、其他頁套主題、標題帶規則、白字對比 ≥ 4.5:1、快捷鈕只給學生且首頁不顯示、列印與窄螢幕規則。

驗證結果：
- 主題相關測試 9 項通過；完整測試 1011 通過、9 略過（第一次跑因為新工作資料夾缺少已忽略的 `logs/test-runs` 暫存資料夾而大量出錯，建好後重跑通過）。
- 瀏覽器實測（展示站開在 5029 埠）：招生時程頁深藍標題帶正常；800px 寬時右側快捷鈕會蓋住時程文字，已改成寬度不到 1360px 時移到左下角一排小圓鈕（右下角是資管科小助手）；375px 手機沒有橫向捲動；學生首頁仍是原底色 `rgb(243, 239, 230)`、沒有快捷鈕。
- 原站焦糖色 `#ca9954` 配白字對比只有約 2.6:1，標題帶改用 `#94652a`、`#9c6a2c`。

決定與注意：
- 專題 `AGENTS.md` §9「避開米白背景」：使用者 11-02 明確選奶油底，以最新指示為準；要換底色只改 `--paper` 一行，要整個撤掉只拿掉 `base.html` 的 `data-theme`。
- 快捷鈕只給學生，教師之後再決定。
- 目標校系頁的「我的目標」區塊不是 `.sheet__head` 結構，所以沒有標題帶，只有奶油底與卡片樣式。

下一步：合併回 `feat/google-docs-autobiography` 前要先等 GPT 提交；開發日誌與交接文件最上面會有合併衝突，保留兩邊內容即可。未推送、未合併。

## 2026-11-02 目標校系分開二技與插大

日期：2026-11-02（台灣時間）

開發者：GPT

目標：依使用者回饋，避免二技與插大校系混在同一份清單。

修改檔案：`app/routes/student.py`、`app/services/focus_service.py`、`app/templates/student_targets.html`、`app/templates/partials/target_explorer.html`、`app/templates/student_gap.html`：加入二技／插大切換，已選目標、舊目標、探索清單和聚焦建議依管道顯示；篩選與校系細項返回保留管道。沒有採計資料的插大校系提示查看招生簡章，不假定需要自傳。`tests/test_matching_page.py`：驗證分流及插大文案。

驗證結果：相關測試 92 項通過，文案修正後新增回歸測試通過；完整測試 1009 項通過、2 項略過。右側 5017 展示版實際切換，二技 41 筆、插大 4 筆，皆為現有示範資料，並非全國完整清單。

下一步：備審目錄是系統依加權排序的 Word 草稿章節，並非學校正式目錄；Word 含部分已確認資料，缺項需自行補齊。使用者尚未決定是否修改這兩個區塊。

## 2026-11-02 整合組員招生資格與校系探索

日期：2026-11-02（台灣時間）

開發者：GPT；組員來源 `111534107/smart-learning-portfolio-main` 的 `fd30f15`。

目標：保留現有系統與首頁，整合組員的校系探索、資格條件擷取／人工核對／比對，並修正本機展示站只載入 4 個校系的問題。

修改檔案：`app/routes/student.py`、`app/templates/student_targets.html`、`app/templates/partials/target_explorer.html`、`app/static/css/design-system.css`：整合已選目標、校系篩選與準備度排序，保留不限所數與既有推薦功能。`app/models/admission.py`、`app/models/__init__.py`、`migrations/versions/a20261022e01_add_admission_eligibility_rules.py`：接入資格規則模型與遷移。`app/services/admission_agent_service.py`、`app/routes/admin.py`、`app/templates/admin_programs.html`：擷取候選資格並由管理者核對來源；`app/services/admission_eligibility_service.py`、`app/services/matching_service.py`、`app/templates/student_matching_detail.html`：依已確認資料提供資格比對、理由及來源；已刪除競賽不計入，來源網址須為 HTTP(S)。`app/demo.py`：載入既有二技、日間部及插大示範資料；組員名單 27 筆均已包含於既有二技示範資料。相應測試與任務清單同步更新。

驗證結果：隔離工作樹完整測試 1001 項通過、9 項略過；其中 7 項因隔離工作樹缺離線 OCR 模型，另 2 項是原本標記暫緩的測試。右側 5016 以假資料驗證目標校系畫面及 45 個示範校系（其中插大 4 筆）。`git diff --check` 待提交前再次核對。

下一步：真實 Google、真實 Gemini 擷取、隔離 MySQL 遷移與當年度官方招生資料須個別驗收；示範資料並非全國完整清單。未推送。

## 2026-11-02 取消目標校系數量限制

日期：2026-11-02（台灣時間）

開發者：GPT

目標：使用者確認本來沒有五所規定，目標校系一律不限數量。

修改檔案：`app/config.py`、`app/routes/student.py`、`app/services/student_rules.py`、`app/services/guide_service.py`、`app/templates/student_targets.html`：移除可設定上限、加入與送審限制、縮減提示及上限文案；目標清單顯示已選數量。`tests/test_assistant_confirm_versions.py`、`tests/test_ui01_fixes.py`、`tests/test_student_page_consistency.py`、`tests/test_help_and_tour.py`：更新回歸測試，確認舊設定不再生效、六所可加入及送審。

驗證結果：相關測試 71 項通過；完整測試 976 項通過、2 項略過（`logs/test-runs/gpt-no-limit-full-20261102`）。

下一步：舊版展示站關閉後，以新版重新開啟實際畫面；舊設計文件記載的五所上限已被使用者本次決定取代，招生管道的正式規則仍依當年度簡章。

## 2026-11-02 Drive 文件或資料夾被刪後重建

日期：2026-11-02（台灣時間）

開發者：GPT（分支 `feat/google-docs-autobiography`）

目標：學生在自己的 Drive 刪除系統建立的文件或資料夾後，能依需要重建並保留系統內的自傳版本。

修改檔案：
- `app/services/google_docs_service.py`：區分 404，檢查文件或資料夾是否已刪除或移入垃圾桶（交接已有的修改）。
- `app/routes/google_docs.py`：有權杖時檢查舊文件；失效時重建並更新原紀錄，檢查失敗仍開原連結；取回遇 404 顯示重建提示。資料夾失效時更新原編號。
- `tests/test_autobiography_google_docs.py`：涵蓋文件、資料夾重建、授權後重建、檢查失敗、取回 404 和 HTTP 404／垃圾桶。
- `docs/05_交接與專案管理/handoff.md`、`docs/05_交接與專案管理/Drive重建_任務清單_2026-11-02.md`：記錄本次進度與待驗收事項。

驗證結果：相關測試 32 項通過；完整測試 `--basetemp=logs/test-runs/gpt-drive-full-20261102-01` 為 976 項通過、2 項略過。測試使用假資料與 Google 替身，未連真實 Google。

下一步：由使用者親自登入 Google，實際驗收兩個校系的資料夾及刪除後重建；勿以自動測試取代實機驗收。

## 2026-11-02 多校備審第一期：帶入上一份回答、Google 文件放校系資料夾、導師說明

日期：2026-11-02（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`；計畫書 `rosy-honking-cosmos.md` 第一期第 2～4 步）

目標：一位學生做好幾份備審資料給不同學校，回答只打一次，雲端自動分資料夾。

修改檔案：
- `app/services/autobiography_service.py`：新增 `carried_answers`。已確認 `generate_draft` 會把 4 題回答存進 `content_json["answers"]`；新校系還沒有草稿時，帶入學生最近一份草稿的回答。
- `app/routes/student.py`：自傳頁沒有該校系草稿時改用 `carried_answers` 預填。
- `app/models/google_doc.py`、`app/models/__init__.py`：新增 `StudentDriveFolder`（資料表 `student_drive_folders`，記「備審資料」與各校系資料夾的 Drive 編號）。
- `migrations/versions/c9e1a7d43b58_add_student_drive_folders.py`：新增資料庫遷移，接在 `e5b9d1c3a826` 後面。
- `app/services/google_docs_service.py`：HTTP 用戶端新增 `create_folder`；`create_document` 可指定放進哪個資料夾。
- `app/routes/google_docs.py`：建立 Google 文件前先找或建「備審資料／校名_科系」；資料夾只建一次，之後重用。
- 目標校系的「5 所」殘留文字：`app/templates/student_targets.html`（沒有上限時改寫「不限所數」，有上限時導覽文字用實際上限）、`app/content/help.py`、`app/services/guide_service.py`。使用者在展示站看到「已選 2／5」，原因是 5013 埠上跑的是 10:48 啟動的舊伺服器（在「不限所數」提交之前），但新程式在沒有上限時仍寫「最多保留 5 所」，一併修正。
- 文件：`docs/02_需求與設計/01_目前有效/AI_多校備審理想流程_導師說明_2026-11-02.md`（給導師的一頁說明，11/4 討論用）。
- 測試：`tests/test_autobiography.py` 新增第二所學校帶入回答；`tests/test_autobiography_google_docs.py` 替身加 `create_folder`，新增兩所學校各一個資料夾、根資料夾只建一次；`tests/test_assistant_confirm_versions.py` 檢查目標校系頁不再出現「5 所」。

驗證結果：完整測試 970 通過、2 略過（改「5 所」文字前）；改文字後相關 6 個測試檔 116 通過，完整測試重跑結果見交接文件。

未完成：真實 Google 帳號驗收。5013 埠被舊的展示站佔用，AI 沒有權限停止不是自己啟動的程式，需使用者先關掉舊伺服器，再重開展示站、由使用者自己登入 Google。

已知限制：學生若在 Drive 手動刪掉系統建的資料夾，系統記的編號會失效，建立文件會顯示「Google 暫時無法使用」；之後可改成失效時重建。

## 2026-11-02 目標校系預設不限所數

日期：2026-11-02（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`；多校備審計畫第一期第 1 步）

目標：使用者 11-02 指出「沒有規定只能選五所」。原本依規格 10.7，專五最多 5 所目標校系，超過就不能加入、也不能送導師確認。

修改檔案：
- `app/config.py`：`TARGET_LIMIT` 預設改為 0＝不限；學校日後要限制再在 `.env` 設數字（機制保留）。
- `app/services/student_rules.py`：`target_slots` 在 `TARGET_LIMIT` 為 0 時回傳不限。
- 測試：`tests/test_assistant_confirm_versions.py` 改為「專五預設可以加第六所」；`tests/test_student_page_consistency.py`、`tests/test_ui01_fixes.py` 明確設定 `TARGET_LIMIT=5` 再測上限機制。

驗證結果：相關測試 60 passed；完整測試尚未跑（交給下一個工作階段一起跑）。

待確認：規格 10.7 的「最多 5 所」要不要在正式規格書改掉，請使用者和組員確認。

## 2026-11-02 Google 文件真實驗收與修正：真正的標題、授權完直接開文件、台灣時間

日期：2026-11-02（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`；使用者用自己的測試 Google 帳號登入授權，Claude 不代填帳密）

目標：使用者要求用 `.env` 的 Google 設定實測 Google 文件編輯。展示站 `scripts/run_local_demo.py` 開在 `localhost:5013`（`.env` 的導回網址），合成學生 `student_demo`。

實測流程與結果：
- 真實 Gemini 寫自傳：通過（第 1 版 688～841 字，本機 Word 備份成功）。今天共用了 4 次學校 AI 額度。
- 按「在 Google 文件中編輯」→ Google 登入與授權 → 建立文件：通過，用戶端 ID 與導回網址有效。
- 在 Google 文件加字 → 回系統「從 Google 文件取回」：通過，存成第 2 版，中英文修改都取回，30 個來源編號保留、沒有不存在的來源。

發現並修正的問題：
1. **Google 文件裡出現「## 困難與成長 []」等符號**：原本以純文字上傳。改成用 Markdown 上傳與匯出，「##」在 Google 文件裡變成真正的標題；沒有來源的段落不再加空的「[]」；來源編號改放在標題下一行「（來源 F1 F2）」（AI 引用 30 筆時原本會把標題撐成三行）；說明文字每行之間空一行。取回時能讀新格式、Google 的跳脫符號（`\[`），也仍能讀舊格式。（`app/services/google_docs_service.py`）
2. **授權完還要再按一次才會建立文件**：按「在 Google 文件中編輯」才去授權的話，授權回來直接建立並打開文件；授權失敗會清掉這個記錄；已有文件則直接打開舊的。（`app/routes/google_docs.py`）
3. **建立／取回時間顯示 UTC**（頁面寫 02:44，台灣時間是 10:44）：改用既有的 `taipei_time`。（`app/templates/student_autobiography.html`）
4. **AI 已開啟卻寫「本機展示模式不呼叫外部 AI」**：只在沒有 AI 金鑰時顯示，文字改為「本機展示站目前沒有設定 AI 金鑰…」。

測試：`tests/test_autobiography_google_docs.py` 新增 6 個（Markdown 上傳與匯出、無空方括號、來源行、跳脫符號、台灣時間、授權後自動建立與未按按鈕時不建立）；`tests/test_local_demo.py` 更新提示文字斷言。完整測試 `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=logs/test-runs/gdoc-full`：**968 passed, 2 skipped**，0 失敗。修正 1、2、3、4 都已在真實 Google 帳號上再驗一次。

已知限制與待決定：
- 每次授權都要選帳號（`prompt=select_account`，為了共用電腦），伺服器重啟後要重新授權（權杖只放記憶體，原設計）。使用者問是否有解，已說明三種做法，建議維持現狀。
- 學校端備份到 Google 雲端硬碟要在 5021 埠由管理員連線（`GOOGLE_STORAGE_REDIRECT_URI`），這次沒測。
- 示範學生的資料只有「【測試】競賽1」這類標題、沒有內容，AI 只能把名稱列出來，自傳讀起來像清單；11/4 展示前建議換成像真的假資料並準備示範回答，或請 AI 每段只挑 2～3 筆。

## 2026-11-02 版面統一第一刀：AI 統一叫資管科小助手、設計變數（首頁先不動）

日期：2026-11-02（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`；計畫書 `C:\Users\lisa2\.claude\plans\rosy-honking-cosmos.md`，使用者核准）

目標：使用者與組員覺得版面「像東拼西湊的樂高」。檢查後原因是很多個 AI、很多條分支各自在 CSS 檔尾加區塊，各自決定顏色、字級、圓角（字級 65 種、圓角 19 種、陰影 39 種、斷點 12 種），且同一個 AI 有三個名字、首頁混了多種比喻。使用者決定只留拼圖比喻、AI 統一叫「資管科小助手」；過程中使用者要求**首頁先不動**，首頁的改動已全部還原。

修改檔案：
- 命名（提交 213bda9）：自傳小幫手 → 小助手寫自傳；升學 Agent → 小助手升學規劃（按鈕、提示、失敗訊息、Word 範本、AI 自我介紹）；登出時導覽「五年路徑」→「我的五年」。管理員端「招生資料 Agent」是後台工具，維持原名。
- `app/static/css/design-system.css`：
  - `:root` 新增字級 `--fs-xs`～`--fs-xl` 與標題 `--fs-display`、`--fs-hero`，間距 `--space-1`～`--space-6`，`--radius-pill`、`--shadow-pop`，並註明只用 720px、1040px 兩個斷點。
  - 非首頁的規則：rem 字級與標題 `clamp()` 換成變數、2～10px 與 .4rem 圓角換成 `--radius`、膠囊圓角換成 `--radius-pill`、與 `:root` 相同的色碼換成變數（共約 210 行）。只出現在首頁的 class（路線、拼圖桌、資料夾等）跳過，共 165 行沒動。
  - `.status-chip` 改用 `--ok`／`--warn`／`--muted`，和 `.tag` 同一組顏色。

驗證結果：
- 完整測試 `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=logs/test-runs/tokens-full`：**961 passed, 2 skipped**，0 失敗。
- 瀏覽器（5032 展示站，1280px）：成績單、活動與經歷、推薦排序版面正常，`--fs-sm` 等變數已生效；畫面差異很小（例如導覽列 .92 → .88rem），屬預期。

已知未完成：
- 陰影（39 種）與內外距（110 種）沒有自動換，容易走樣，需逐頁人工處理。
- 斷點仍有 12 種，未合併。
- 學生頁骨架未統一（抵免頁仍用後台骨架、部分頁多個 h1）；首頁依使用者指示未動。
- 組員希望改成類似 iOS 的玻璃透感：可行，但沒有顯示卡的電腦會卡、字的對比要調；有了變數之後可以只改變數試做，待使用者決定。

下一步：使用者決定是否試做玻璃透感；學生頁骨架統一；Google 文件真實測試。

## 2026-10-30 推薦排序改版：準備度有高低、二技／插大分頁、搜尋、學校引導頁

日期：2026-10-30（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`；計畫書 `C:\Users\lisa2\.claude\plans\rosy-honking-cosmos.md`，使用者核准）

目標：10-28 導師建議「排成一張排行、點進去看細節」；使用者指出二技與插大混在一頁、沒有搜尋、只說準備了多少卻沒引導學生怎麼進這所學校；10-27 測試報告準備度幾乎全是 100%、護理等群類也標可報。不做爬錄取名單、不算錄取機率（維持 10-23 決定）。

修改檔案：
- `app/services/gap_service.py`、新增 `app/content/readiness_rules.csv`：準備度改為有高低。成績看平均分（85／75／60 分級）、其他類 1 筆算一半 2 筆算滿、外語項目只認語言檢定、自傳（有草稿＝一半、改過＝滿）與專題列入分母。每個項目算「補滿可加幾 %」與最該先補的類別。新增 `student_evidence()` 讓排行只查一次學生資料。
- `app/services/matching_service.py`：二技招生類別寫明其他群類（不是管理類、不是不限類別）且和學生學群不相關時標「需確認」並寫「請確認你的統測類別能否報考」；插大不看群類。不直接判不可報（使用者：真實資料沒有資管只能選資訊相關）。
- `app/services/student_progress.py`：下一步提示改用最該先補的類別。
- `app/routes/student.py`、`app/templates/student_matching.html`：二技／插大分頁（附數量）、關鍵字搜尋（學校或科系，可多個詞）、先列前 20 間＋「看更多」；排行每列有可報狀態並連到細項；各校理由收進「逐間看理由與細項」；只考筆試的插大顯示「依考試成績，不算準備度」。
- `app/templates/partials/matching_detail.html`、`student_matching_detail.html`：細項頁改為「怎麼進這所學校」：缺少的項目依補滿可加 % 排，第一條「先做這個」、每條「去補 →」；靠考試的項目另外說明；報名時程倒數、招生資訊、設為目標校系。
- `app/static/css/design-system.css`：分頁、排行狀態標籤、手機版排行。
- 測試：`tests/test_admission_services.py`、`tests/test_matching_service.py`、`tests/test_matching_page.py`、`tests/test_transfer_exam.py`（舊規則斷言改為新規則，並新增語言檢定、成績分級、群類需確認、分頁、搜尋、看更多、細項頁測試）。

驗證結果：
- 相關測試：A1 148 passed、A2 37 passed、A3／A4 47 passed。
- 瀏覽器（`scripts/run_demo.py`，埠 5032，示範學生王小明，41 間二技＋4 間插大）：二技準備度分布 42%～90%，沒有一間 100%；27 間可報、14 間需確認（護理、餐旅、電機、設計等類別）；先列 20 間並有「看更多」；搜尋「北商 資訊」剩 3 間；375px 排行、搜尋、細項頁 `scrollWidth` 都是 375；細項頁顯示「先做這個：專業成果…補滿可加 30%」。
- 完整測試 `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=logs/test-runs/a34-full`：**961 passed, 2 skipped**，0 失敗。

已知限制：「補滿可加」只看系統裡的資料，統測、面試等考試項目不在內；語言檢定規則只有一條（外語），其他項目沿用類別判斷，規則可直接改 CSV。

下一步：同學試用問題單；B4 拼圖一學期一片（另開任務卡）；報告書第五章。

## 2026-10-30 科辦示範送件；送件卡片類別改顯示中文

日期：2026-10-30（台灣時間）

開發者：Claude（直接在 `D:\democase\ai-wt-story` 修改；未提交、未推送）

目標：使用者要求「補科辦示範送件」。10-29 驗收時科辦「待處理送件」與「電子獎狀」兩頁都是 0 件，展示時沒有東西可審。

修改檔案：
- `app/demo.py`：`_seed_journey_board()` 改為回傳建立的成果；新增 `_seed_staff_queue()`：用 `create_submission_snapshot()` 送審「【測試】活動5」「【測試】競賽5」兩筆成果（與學生按送審走同一段程式），並把「【測試】服務4」標成從學校獎懲記錄匯入（`source="award_record"`），開一張待核准的服務證明電子獎狀，內文用 `certificate_service.default_body()` 產生。
- `app/routes/main.py`、`app/templates/dashboard.html`：科辦送件卡片與導師審查清單原本直接印出類別代碼（例如 `activity`），改用 `CATEGORY_LABELS` 顯示「活動」「競賽」等中文；科辦工作台補傳 `category_labels`。
- `tests/test_local_demo.py`：新增 `test_local_demo_staff_has_submissions_and_a_certificate_to_review`（2 件待處理、獎狀出現、類別顯示中文）。

驗證結果：
- `tests/test_local_demo.py`：11 passed。
- 完整測試第一次 5 failed（`test_course_grade_level.py` 2 個、`test_student_records.py` 3 個）。原因不是本次改動：`.env` 在 10-29 16:49 被改成 `DOCUMENT_ANALYSIS_PROVIDER=rapidocr`，這 5 個測試沒有自己指定辨識方式，拿 4 個位元組的假檔去真辨識，結果是空的。已在 `tests/conftest.py` 新增 `no_real_ocr`，測試預設用假辨識（寫法同既有的 `no_real_ai`、`no_real_google`）；需要真實 OCR 的測試本來就自己在 `create_app` 指定，不受影響。
- 修正後完整測試 `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=logs/test-runs/full-after-ocr-fix`：**951 passed, 2 skipped**，0 失敗。
- 瀏覽器（展示站 5031、375px）：科辦工作台顯示「2 件待處理」「待核准電子獎狀 1」，兩張卡片類別為「活動」「競賽」；電子獎狀清單有「【測試】服務4」；審核頁回 200，標題「服務證明」、內文與發證單位已預填，有「核准並產出獎狀」「退回」；三頁 `scrollWidth` 皆為 375。沒有按核准，示範資料保留給展示。

已知限制：示範獎狀沒有附獎懲記錄原始檔，所以審核頁不會出現「對照學生上傳的獎懲記錄」按鈕；送件也沒有教師意見，卡片顯示「目前還沒有教師意見」。

下一步：全部改動等使用者決定是否提交。

## 2026-10-29 瀏覽器驗收發現的修正：照片 500、展示站上傳資料夾、示範目標校系

日期：2026-10-29（台灣時間）

開發者：Claude（直接在 `D:\democase\ai-wt-story` 修改；未提交、未推送）

目標：使用者要求做瀏覽器驗收。驗收過程發現 4 個問題並修正；完整驗收結果見 `docs/03_開發紀錄/browser-check-2026-10-29.md` 最上面一節。

修改檔案：
- `app/services/photo_service.py`：`photo_path()` 改回傳絕對路徑。原本相對路徑在 `send_file` 會以 `app\` 為基準而找不到，學期照片回 500；正式版預設設定也會遇到。
- `app/demo.py`：展示站改用自己的暫存上傳資料夾（`tempfile.mkdtemp`），不再共用 `instance\uploads`，以免示範學生（編號 1）拿到磁碟上別人留下的照片或備份；示範資料標題改中文；示範學生預設選一個資管相關目標校系，自傳頁才能直接生成。
- `tests/test_semester_photo.py`：新增相對路徑 `UPLOAD_FOLDER` 的照片測試（先失敗後通過）。
- `tests/test_local_demo.py`：新增展示站上傳資料夾獨立、示範學生能直接生成自傳的測試。

驗證結果：
- 相關測試（`tests/test_local_demo.py`、`tests/test_semester_photo.py`、`tests/test_autobiography_google_docs.py`）：39 passed。
- 完整測試 `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=logs/test-runs/browser-fix-full`：**950 passed, 2 skipped**，0 失敗（上一次 947，新增 3 個測試）。
- 瀏覽器：375px 學生首頁 30 片、生成自傳成功、Tab 順序與焦點框正常、導師導覽正常；科辦工作台與導覽補驗通過（示範資料沒有送件，0 件）；減少動態效果未實測。

下一步：決定要不要處理磁碟上 `instance\uploads\semester-photos\1\` 的舊照片。

## 2026-10-29 示範帳號補拼圖資料：student_demo 可生成自傳

日期：2026-10-29（台灣時間）

開發者：Claude（直接在 `D:\democase\ai-wt-story` 修改；未提交、未推送）

目標：使用者決定「補示範資料」。原本 `student_demo` 是專五但拼圖 0 格，展示時按不了生成自傳。現在展示站與示範用的資料庫啟動時，會替示範學生補滿五年 × 六類的已確認合成資料。

修改檔案：
- `app/demo.py`：新增 `_seed_journey_board()`，為每個已走過的年級補上 1 筆成績（`LearningCourseRecord`）、1 筆證照（`CredentialRecord`）、活動／競賽／服務／幹部各 1 筆（`Portfolio`），狀態皆為 `confirmed`，標題前綴「【測試】」。`create_local_demo_app()` 在建立學生檔案後呼叫它。

驗證結果：
- 啟動展示站的同一套建立流程後，`board_progress` 為 30／30（專五 × 六類全部有資料），`autobiography_block_reason` 為 `None`，自傳頁可生成。
- 完整測試 `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=logs/test-runs/demo-seed`：**947 passed, 2 skipped**，0 失敗（1 個既有的 `cache_dir` 設定警告）。
- 未做瀏覽器實測；展示站的登入後畫面與生成自傳按鈕還沒在瀏覽器確認。

下一步：用瀏覽器確認 `student_demo` 首頁拼圖桌為 30 格全亮、生成自傳可按；若要讓學生首頁的草稿有真實感，可再決定示範自傳內容。

## 2026-10-29 用語改準備度：轉學考與算不出時的說明

日期：2026-10-29（台灣時間）

開發者：Claude（直接在 `D:\democase\ai-wt-story` 修改；未提交、未推送）

目標：使用者規格要求用「準備度」，不用「契合度」。`matching_service.py` 第 46、157 行（轉學考校系的說明、算不出時的說明）仍寫「契合度」，這次一併改掉。算法沒有改。

修改檔案：
- `app/services/matching_service.py`：`NO_FIT_TRANSFER` 改為「依考試成績，不算準備度」；`_fit_reasons` 算不出時的說明改為「……系統還算不出準備度。」
- `tests/test_transfer_exam.py`：三處斷言同步更新（只考筆試的插大、推薦排序頁卡片、AI 推薦工具說明）。

驗證：
- 先改測試，確認 3 個測試失敗（對應舊字樣），再改程式。
- 完整測試 `pytest -q -p no:cacheprovider --basetemp=logs/test-runs/fit-wording`：**947 passed, 2 skipped**，0 失敗。（任務基準寫 927，實際數字是 947；測試數量已多於當時基準，全綠。）

追加修改：`app/services/agent_advisor.py` 第 31、32、140 行（AI 指示與工具說明）的「契合度」改為「準備度」；`tests/` 只剩模組說明文字，沒有斷言。完整測試重跑：**947 passed, 2 skipped**。

已知未處理（不在本次範圍）：
- `app/routes/student.py` 等的註解與文件仍有「契合度」，不影響畫面。
- `docs/05_交接與專案管理/checklist.md` 第 31 行 C4 仍寫「第 46、157 行待處理」，需要改為已完成。

下一步：更新 checklist C4 狀態；使用者確認後再提交。

## 2026-10-28 自傳兩邊都存：學校端 Word 備份＋學生自己的 Google 文件

日期：2026-10-28（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`；子代理實作，另一個子代理審查）

目標：使用者問「自傳要存在雲端上，阿雲端的位置勒」，並選擇「兩邊都存」。原本自傳只存在系統資料庫，Google 文件只是另開一份給學生編輯。

- 新增 `app/services/autobiography_backup.py`：自傳每新增一版就輸出成 Word 檔。
  - 三個建立點都會備份：AI 生成、學生或導師存修改、從 Google 文件取回。
  - 檔案透過 `storage_service.save` 存到學校端，位置記在該版的 `content_json["backup_location"]`。
  - 管理員在「檔案存放設定」連上 Google 時，存到學校的 Google 雲端硬碟；沒連上或 Drive 失敗時改存本機。
  - 備份失敗不會影響生成或存檔。
- 自傳頁與版本頁：每一版顯示「已備份到學校雲端」「已備份到本機（學校雲端未連線）」或「備份失敗」，不顯示內部路徑。
- 自傳頁的 Google 文件區塊加上「在自己的 Google 文件中編輯」標題；學校尚未設定 Google 連線時會顯示說明，不再整塊隱藏。
- `/admin/storage` 加說明：自傳備份也存在這裡。

驗證：
- 新測試 `tests/test_autobiography_backup.py` 8 個，先失敗後通過；相關測試 92 個通過。
- 完整測試 **947 passed, 2 skipped**，0 失敗（子代理在提交 37e9fde 執行）。
- 審查結論為通過，具名風險都查過：檔名安全、例外範圍、JSON 有存進資料庫、導師修改時檔案歸學生、Google 取回也有備份。

已知未完成：
- 這台電腦的 `.env` 沒有 Google OAuth 設定，所以 Drive 路徑只用假的 Drive 測過，沒有真的上傳到 Google；要有人在 Google Cloud Console 建立 OAuth 用戶端並填進 `.env`。
- 備份在請求裡同步執行，Drive 很慢時會拖慢存檔（逾時 20 秒）。
- 備份失敗的那一版不會自動補；每一版都存一份 Word，清理政策還沒訂。
- 審查的小建議（Minor）：`_backup_existing` 查學生的那行在 try 外面；Word 檔沒有標示是導師或學生修改的。

## 2026-10-28 首頁改成亂亂的五年拼圖桌；展示站與正式版預設真實 OCR

日期：2026-10-28（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`；先做試用版給使用者看，使用者決定留下後由子代理審查、修正、複審）

目標：使用者看過固定格子大桌板後表示「跟我想像中差好多」。照使用者描述與參考的線上拼圖遊戲改成：六個做拼圖按鈕、一筆資料一片、散在五年共用的桌子四邊，要生成自傳時由資管科小助手把拼圖拼好。使用者另外要求：草圖不要像兒童繪畫本，要像五專生用的；之後不管啟動展示站或正式版，功能都要真的能用。

- 首頁拼圖區（`student_home.html`、`journey_home.py`、`components.js`、`design-system.css`）：
  - 六個按鈕：＋成績、證照、活動、競賽、服務、幹部。沿用網站按鈕樣式，前面是細線圖示。按下去會有一片拼圖從按鈕彈出飛向桌子，再進入填寫頁。
  - 一筆資料一片：資料來自五年的 `build_journey`。每片是同一張圖的一部分，有學期照片就用照片，沒有就用低飽和的湖景插畫。拼圖有凸耳和凹槽，類別只用片內一條細色線標示。
  - 桌面是深灰毛氈質感，拼圖散在四邊、中間留空。位置和角度依資料庫編號決定（`build_journey` 每筆多了 `id`，例如 `portfolio-12`），改標題也不會換位置。
  - 點一片會顯示類別、年級和標題；新增的片回首頁時從上方落下，整體最多約 1.5 秒。
  - 「請小助手拼好拼圖、生成自傳」：小助手出場，把所有拼圖飛到中央拼成一張完整的圖，再進入自傳頁。這顆按鈕是一般連結，沒有 JS 也能用；年級未到或 0 片時停用並說明原因。
  - 首頁標題加上學生姓名（例如「王小明・專三，你在這裡。」）。使用者反映看畫面時「會不知道誰是誰」。
  - 有尊重「減少動態效果」設定。手機版按鈕排成 3×2，桌子改成直式。
- 拿掉上一節的固定格子桌板與「每格都填滿才能生成自傳」限制（網頁與 AI 小幫手草稿工具都拿掉）。OCR 確認關卡沒動。
- **專五才能生成自傳**：使用者看到沒資料也能按生成，表示應該「時間一到才能開始生成」，時間點選「專五開始」。
  - 新增設定 `AUTOBIOGRAPHY_OPEN_GRADE`（預設 5）與 `student_rules.autobiography_block_reason`。
  - 自傳頁、生成路由、AI 小幫手草稿工具、今日焦點都改用它。
  - 送導師確認仍維持 `MIN_REVIEW_GRADE`（專二）。
  - 專一到專四看到的說明都是「專五才開放」。
  - 既有測試的學生改成專五，沒有 mock 掉檢查。
- 真實 OCR 預設開啟（`scripts/real_ocr.py`、`run_local_demo.py`、`run_demo.py`、`start_local.py`、`.env.example`）：
  - 起因：使用者問「為何展示板還是不能掃描成績單」。原因是 `local-demo` 預設用模擬辨識，要加 `--ocr` 才會真的辨識。
  - 現在三種啟動方式遇到 fake／demo／未設定，都改用本機 RapidOCR。模型缺少時從官方 ModelScope 下載並核對 SHA-256，下載失敗才退回並大聲提示。
  - 正式版只改這次啟動的行程，不寫回 `.env`。展示站可加 `--fake-ocr` 改回模擬辨識。
  - `.env` 填好 Google OAuth 時，展示站自動開放 Google 文件編輯。

驗證：
- 完整測試（`D:\democase\ai\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=logs/test-runs/push-final`，提交 cb093f3）：**939 passed, 2 skipped**，0 失敗；1 個既有的 `cache_dir` 設定警告。
- 瀏覽器（展示站 5013，以及用測試資料產生的 36、54、150 片頁面）：
  - 1280px 與 390px 都沒有水平捲動（390px 時 `scrollWidth` 為 390）。
  - 小助手拼圖動畫正常，拼好後合成整張圖。
  - 生成自傳按鈕是 `<a href="/student/autobiography">`；頁面沒有 emoji。
- 展示站改成預設啟動後，`DOCUMENT_ANALYSIS_PROVIDER` 為 `rapidocr`，加 `--fake-ocr` 時為 `demo`。

已知未完成：
- 成績是一門課一片，五年下來可能有一百多片。是否改成一學期一片，待使用者決定。
- 拼圖區仍在「今天先完成哪一步」與五年資料夾之後，不在頁面最上方。
- 展示站的 AI 仍關閉，用示範草稿；是否接真的金鑰尚未決定。Google 文件編輯要 `.env` 有 OAuth 設定才會開，目前 `.env` 沒有。
- 示範帳號 student_demo 沒有任何資料，桌上是空的。
- 自傳「兩邊都存」（學校 Google 雲端硬碟備份 .docx＋學生自己的 Google 文件）：使用者已決定，下一步做。兩邊都需要 `.env` 填入 Google OAuth 用戶端才會真的連上雲端。

## 2026-10-28 學生首頁大桌板與拼圖完成才能生成自傳（工作流 A）

日期：2026-10-28（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`；子代理逐任務實作與審查，另做一次整個分支的最終審查）

目標：依 `docs/superpowers/plans/2026-10-28-guidance-screens.md` 工作流 A，把首頁「今年六片」拼圖擴成大桌板，並在拼圖完成後才開放生成自傳。B-1、B-3、Q5 使用者沒有定見，只要求手機版也要支援；這次採用 Claude 的建議並經使用者核准（決定寫在計畫檔 Blockers 表下方）。

- A1 桌板資料（`app/services/journey_home.py`）：`journey_home()` 新增 `board`，格數為走過的年級數 × 6 類（專一 6 格、專五 30 格），每格有 `slot_id`（例如 `3-grades`）。建片邏輯抽成 `_year_pieces()`，今年六片與桌板共用。新增 `board_progress()`、`board_block_reason()` 供自傳閘門使用。
- A2 桌板畫面（`student_home.html`、`components.js`、`design-system.css`）：今年那塊保留拖拉托盤，走過的年級另外排在下面。有資料的格亮起，亮起的格也能點，可再上傳一份。全部亮起時顯示「拼圖完成！」與「生成自傳」，否則顯示「還差 N 格」。回訪時新亮起的格會跳一下，並尊重「減少動態」設定。電腦版一列 3 個年級，手機版一個年級一塊、上下排列。
- A3 拼圖完成才能生成自傳（`app/routes/student.py`、`app/services/agent_advisor.py`、`student_autobiography.html`）：網頁生成與 AI 小幫手的草稿工具都會先檢查 `board_block_reason`。未完成時不呼叫 AI、不扣額度、不寫入資料，網頁回 409，學生填的答案保留。審查發現 AI 小幫手原本可以繞過閘門，已補上。
- 最終審查修正：專一學生拼完時改顯示「專二開放生成自傳」，不放用不了的按鈕。判斷沿用 `student_rules` 的 `MIN_REVIEW_GRADE`（新增 `review_open_note`）。含連結的拼圖 SVG 從 `role="img"` 改為 `role="group"`。
- 測試共用的 `tests/board_helpers.py` 提供 `fill_board()`；既有自傳測試補滿拼圖後繼續通過。

驗證：
- 完整測試（`D:\democase\ai\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=logs/test-runs/a-final3`，提交 a39043f）：**939 passed, 2 skipped**，0 失敗；1 個既有的 `cache_dir` 設定警告。上一節為 927 passed。
- 瀏覽器（本機展示站 5013、合成帳號 student_demo）：390px 的 `scrollWidth` 為 390、1280px 為 1265，都沒有水平捲動；手機版每格約 99–116px，電腦版約 120px；首頁 30 格都有 `data-board-slot`。

已知未完成：
- **示範帳號 student_demo（`app/demo.py`）是專五，拼圖 0／30 格，所以示範時無法生成自傳。** seed 沒有改，待使用者決定：補示範資料，或放寬「每一年六類都要有」的規則。
- 只存成草稿的經歷也會讓格子亮起，但 AI 寫自傳只用已確認或已送出的資料。
- 過去年級空格的連結不帶年級，學生補過去年級資料時要自己選學年。
- `PuzzlePiece` 模型仍未使用，沒有整併。

下一步：使用者決定示範帳號的處理方式；Q1（登入後引導）、Q4（C3 排序更新）。

## 2026-10-28 指導討論三畫面：OCR 左圖右表、排行篩選與細項、篩選選項後台

日期：2026-10-28（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`；子代理逐任務實作與審查）

目標：依 `docs/superpowers/plans/2026-10-28-guidance-screens.md` 完成不受待確認事項卡住的任務（G1、G2、B2、B1、C2、C1、D1）。學生首頁大桌板（A1–A3）與排序自動更新（C3）等使用者決定，本次沒做。**沒有提交。**

- G1／G2 篩選選項後台：新增 `MatchFilterOption`（`app/models/match_filter.py`）與遷移 `e5b9d1c3a826`；管理頁 `/admin/match-filters` 可新增、修改顯示名稱與排序、停用。「是否可報」只接受 eligible／needs_check／ineligible；「學制」頁面列出現有校系的招生類別供對照；「地區」標為尚未啟用。
- B2 未確認資料不進 AI：新測試發現 `app/services/agent_file_tool.py` 的 `get_my_document` 會把**未確認的 OCR 草稿**傳給升學 Agent，已改成未確認文件只回狀態與摘要。
- B1 OCR 核對頁（`learning_profile_review.html`）：電腦版左圖右表、隱藏表頭並在每格顯示欄位名稱；只有信心已知且低於 0.85 的科目、學分、成績標橘；顯示「還有 N 列待確認」；手機版一列一張卡片、原圖收合。
- C2／C1 校系排行（`student_matching.html`、新路由 `/student/matching/<id>`）：每校可展開「已符合／缺少」（部分符合標「（部分）」），手機版點入整頁；篩選科系、學制、是否可報（選項來自後台）；橫條／長條切換；百分比改為「準備度 N%（建議值）」。
- D1 準備度人工檢查：`docs/superpowers/plans/2026-10-28-score-check-notes.md`。發現純文件項目（例如備審、自傳）不列入分母，只有成績的學生在文件佔 60% 的校系也會顯示 100%。這是原設計的取捨，本次未改算法。

驗證：
- 完整測試（`D:\democase\ai\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=logs/test-runs/final-sdd-2`）：**927 passed, 2 skipped**，0 失敗；1 個既有的 `cache_dir` 設定警告。修正前為 921 passed。
- 瀏覽器（本機展示站 5013、合成帳號 student_demo、假 OCR）：排行頁與細項頁 390px 無水平捲動、無「契合度」與「錄取保證」；OCR 核對頁 390px 無水平捲動、電腦版 1280px 左右並排且每個欄位有名稱。展示站的篩選列因尚未建選項而未出現（預期）。

已知未完成：
- `app/services/matching_service.py` 第 46、157 行（轉學考校系、算不出時的說明）仍寫「契合度」；改字需同步 `tests/test_transfer_exam.py`。
- 管理頁三個既有的 400 錯誤訊息仍是英文。
- 地區篩選：校系資料沒有地區欄位（B-2）。

下一步：使用者決定 B-1（大桌板格數）、B-3（以哪一套拼圖為準）、Q4、Q5 後做 A1–A3、C3；決定準備度算法是否把文件項目列入分母（D2）；確認後再提交。

## 2026-10-28 指導討論畫面草圖與設計摘要（未改程式）

日期：2026-10-28（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`）

目標：依 superpowers 頭腦風暴流程，把學生首頁、OCR 核對、校系排行三個畫面定出版面與互動，寫成設計摘要，等使用者核准後才進入實作規劃。本次只做草圖與文件，沒有改程式、資料表或權限。

- 草圖（瀏覽器，本機伺服器，閒置 4 小時自動關閉）：學生首頁選 A 大桌板；OCR 核對採左圖右表；校系排行採多校一頁、橫條與長條切換、篩選選單（科系、地區、學制、是否可報）、電腦版點入展開已符合與缺少項目。草圖檔案在 `.superpowers/brainstorm/1952-1793158182/content/`。
- 新增 `docs/superpowers/specs/2026-10-28-guidance-screens-design.md`：設計摘要，含目的、目標、非目標、反目標、三個畫面的決定、管理員維護的篩選選項（獨立工作流 G）、待決定事項與自行決定的部分。
- 使用者已定：拼圖完成後才生成自傳；五年內可隨時追補；篩選選項由管理員維護，不寫死。
- 未決：Q2（主任與科主）、Q3（統計表）、Q4（排序是否自動更新）、Q5（拼圖完成細節）、送出後能否回頭修改 OCR、排行預設圖表。

注意：`.superpowers/` 尚未列入 `.gitignore`，提交前需確認。

下一步：使用者核准設計摘要後，進入實作規劃；工作流 A、B、C、D 可分開進行。

## 2026-10-28 指導討論後續：拆分代辦任務清單與 checklist（規劃，未改程式）

日期：2026-10-28（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`）

目標：把 10/28 指導老師討論的需求拆成可分給多個對話視窗完成的工作流，並先規劃解法；本次只寫文件，沒有改程式。

- 新增 `docs/05_交接與專案管理/代辦任務清單_2026-10-28_指導討論.md`：7 項待確認（Q1–Q7）、6 個工作流（A 引導與完成狀態、B OCR 核對、C 校系總覽、D AI 比分檢查、E 權限與統計、F 文件與待確認）、建議的多視窗分工與新視窗啟動提示詞。
- 新增 `docs/05_交接與專案管理/checklist.md`：對應任務清單的可勾選項目，每項需附證據才能打勾。
- 依據：`docs/06_會議錄音與逐字稿/AI_逐字稿_2026-10-28-指導老師agent和增加主任使用者.txt`（自動辨識，不清楚處標示待確認）與 `AI_會議重點與待辦_2026-10-28.md`。
- 程式盤點（只讀）：拼圖在 `app/static/js/components.js` 約 536–623 行，資料表 `puzzle_pieces` 在 `app/models/p0_workbench.py`；校系比對在 `app/services/matching_service.py`；OCR 核對頁在 `app/templates/ocr_acceptance.html`。

下一步：使用者確認 Q1–Q7 的回聽或詢問方式後，依任務清單開新視窗分工；F4 回聽錄音最適合先做。

## 2026-10-27 新增試用任務單與試用紀錄表

日期：2026-10-27（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`）

目標：「畢業專題驗收與展示策略」對話的結論指出，目前缺「有人實際用過」的證據。準備讓 3～5 位學生、1～2 位老師試用的文件。只改文件，沒有改程式。

- 新增 `docs/05_交接與專案管理/試用任務單_2026-10-27.md`：給試用者看，學生任務 A1～A7（另有選做 A8 升學 Agent），導師任務 B1～B4。題目只寫要做到的事，不寫按哪裡。
- 新增 `docs/05_交接與專案管理/試用紀錄表_2026-10-27.md`：主持人流程（5020 埠固定流程、每人前重啟、三級提示）、逐題紀錄、10 題易用性量表與計分方式、跟現在做法的比較題、彙整表、寫進報告的方式。
- 導師任務依 `app/templates/teacher_student.html` 核對：只有待確認時可以選確認或需要修改，已確認後才可以撤回，所以 B3 寫成確認、B4 寫成撤回。

驗證：任務內容對照 `系統完整測試手冊.md` 的 S-03、S-11、S-22、S-23、S-33a、S-39、S-42、S-44、T-01～T-05a；沒有實際找人試用。

下一步：組員找試用者並照紀錄表進行；結果填進彙整表，再把問題分給 GPT（用詞、小畫面）和 Claude（流程）。

## 2026-10-27 系統完整測試手冊依實測修正

日期：2026-10-27（台灣時間）

開發者：Codex（分支 `feat/google-docs-autobiography`）

目標：依照 Claude 於 2026-10-27 的系統實測報告修正操作手冊，並補上使用者指定的已知限制和例外說明；只改文件，未改程式。

- 更新 `docs/05_交接與專案管理/系統完整測試手冊.md`：修正 X-09、S-10、S-13、S-14、S-24、S-28、S-29、S-31、S-42、T-01、T-05b、T-08、F-03、A-02、A-07、A-10、A-11；補上測試檔案規格及同一瀏覽器測多個埠／角色的注意事項。另補契合度、自傳證據編號限制，以及測試報告問題 13、18 是展示資料情況的說明。
- S-13 註明成績確認頁一開始按鈕顯示「解鎖成績」，按一次即可修改分數；一般辨識成功頁沒有新增／刪除按鈕。
- 完整自動測試：依指定指令執行，`898 passed, 3 failed, 2 skipped`（403.17 秒）。3 個失敗是既有程式測試：`test_extract_without_api_key_gives_chinese_message`、`test_missing_key_raises_chinese_message`、`test_editable_course_fields_save_without_javascript`；本次依要求未改程式，故未修復。另有 pytest `cache_dir` 未知設定警告。（GPT 執行時的結果；這 3 個是測試還在檢查舊行為，Claude 已在 `a966c67`、`3c94bac` 改成新行為，之後完整測試 900 通過、唯一失敗已修正並單獨重跑通過，2026-10-27 已推送 `3c94bac`。）

下一步：回報文件修改和測試數字。三個測試失敗已由 Claude 處理（見上）。本次只提交手冊與本開發日誌，不推送。

## 2026-10-27 從頭到尾的主線自動測試

日期：2026-10-27（台灣時間）

開發者：Claude（分支 `feat/e2e-mainline-test`）

目標：V1 規格的完成定義要「一個假學生帳號從上傳走到導師確認不需要人幫忙」，第 9 節要求從頭到尾的自動測試，之前沒有這條。只新增測試，產品程式沒改。

- 新增 `tests/test_end_to_end_mainline.py`：記憶體 SQLite＋Flask 測試用戶端；成績單用測試內產生的一頁 PDF，OCR 走 fake 擷取（背景佇列在測試中同步執行）；自傳用假的 AI 函式（從提示詞讀 F 編號，每段都引用），不連網路。
- 一位學生依序走 11 步，每步都檢查頁面或資料庫：第一次登入進新生引導 → 我的五年；上傳 → 辨識中 → 確認頁；確認前正式成績是 0 筆，改分數（92→95）、加一門課後按確認才寫入；新增活動並確認、上傳佐證照片；推薦排序頁有校系、設為目標；缺件頁每個評分項目的加權、已有與缺少都列出，下載得到 .docx；自傳 4 題產生草稿、每段有 F 編號、改一段存成第 2 版、版本紀錄有兩版；送導師確認存快照；學生再改成第 3 版，快照與第 2 版內容不變（導師頁顯示「自傳依據第 2 版（目前第 3 版）」）；導師在本班看到待確認 1 份、按「內容合理，確認」，學生端顯示「導師已確認」；另一位學生和非本班導師開這位學生的成績單、經歷、佐證、自傳、備審 Word、導師頁都是 403 或 404。
- 走完沒有發現產品問題，沒有標 xfail。
## 2026-10-27 補扣分風險：自傳「從小」、Agent 中斷、C5 證照期限、規格狀態

日期：2026-10-27（台灣時間）

開發者：Claude（分支 `feat/score-risk-fixes`）

目標：10-28 要交完成度，使用者要求今天把所有可能扣分的地方處理好。同時有三個工作階段在做 M10／M11、主線端到端測試、照手冊實測。

- 自傳逐句檢查（`app/services/autobiography_review.py`）：實測 Gemini 寫「我從小就對電腦應用充滿好奇，在五專期間，特別是參加了全國商業類技藝競賽…」，因為同一句有真的競賽名稱而沒被抓。含「從小、小時候、自幼、一直以來」的子句改成單獨檢查，只有學生回答寫過才算有依據。
- 升學 Agent（`agent_engine.py` 的 `expire_if_stale`、結果頁與進度路由）：網站重開時正在背景執行的那一次會永遠停在「執行中」；超過 5 分鐘改記失敗，畫面顯示「這次執行被中斷了…請再按一次」。
- 報考條件 C5（`matching_service.py` 的 `skill_credential`）：已確認證照的等級（丙＜乙＜甲，看等級欄或證照名稱）與取得日期，對照簡章「等級」「期限」（民國年）。沒有符合的證照或缺日期是「需確認」（可能還沒上傳，D8 不亂判）；證照都在期限後才取得是「不可報」。條件 CSV 多「等級」「期限」兩欄，示範條件加在 208001（標示為示範資料）。王小明（乙級，2025-11-02）可報、林小美（只有丙級）需確認。
- 文件：V1 規格 M1～M14 狀態欄依程式重新核對（原本停在 10-15）；Agent 分工規格 11/4 項目註明進度；系統完整測試手冊新增 S-33a、S-46a、AG-11，更新已知限制與 `--basetemp` 說明（GPT 在沙箱用系統 Temp 會權限錯誤）。
- 測試：新增 2（從小）＋2（中斷）＋7（C5）個；相關 7 個測試檔 130 個通過。
- GPT 測試報告（`docs/05_交接與專案管理/測試報告_GPT_2026-10-27.md`）：沙箱連不到本機展示站，92 條手動測試全部略過，只有自動化測試 867 通過；另開工作階段實際照手冊測。
## 2026-10-27 M10 刪除先標記、送審過不能刪；M11 操作紀錄補齊

日期：2026-10-27（台灣時間）

開發者：Claude（分支 `feat/m10-m11-retention`，從 `614de8d` 開出，工作資料夾 `D:\democase\_worktrees\ai-wt-m10-m11`）

目標：規格第 4 節只剩 M10（刪除與保留）、M11（操作紀錄）是部分完成。10-28 交完成度前補齊。

- 資料表：`portfolios` 與 `portfolio_evidence` 加 `deleted_at`（可為空）。遷移 `migrations/versions/d8f3b6a2c417_add_soft_delete_to_portfolios.py` 接在 `c4e2b7a91d05` 之後；和 `c4a8f1e2d903` 一樣，表不存在（從零升級、基本表由 `db.create_all()` 建）時略過。
- 刪除改成標記：`portfolio_delete`、`evidence_delete` 不再刪資料列，只寫 `deleted_at`；檔案照舊只加刪除標記。刪除經歷時，它的佐證一起標記。
- 集中排除已刪除：`Portfolio.active()` 取代原本的 `Portfolio.query`（學生活動頁、我的五年、首頁、缺件清單、自傳資料、備審 Word、小助手、導師頁、活動適合學校都改用它）；`evidence_items` 關聯本身就排除已刪除的佐證，另有唯讀的 `all_evidence_items`。`owned_portfolio`、學生與導師的佐證檢視、電子獎狀申請遇到已刪除的一律 404。獎懲記錄匯入的「已匯入過」檢查刻意不排除，刪掉的匯入紀錄不會被再匯入冒回來。
- 送審過的不能刪：經歷出現在任何一份送審快照（`PackageReview.snapshot_json` 的 `portfolio:編號`），或舊流程有 `PortfolioSubmission`，刪除經歷或它的佐證都擋下，編輯頁顯示「這筆已經送導師確認，不能刪除；如果內容有誤，請修改後再送一次。」導師看的快照不受影響。編輯頁新增「刪除這筆經歷」按鈕（原本畫面沒有入口）。
- 操作紀錄：新增 `app/services/audit_service.py`（`record` 與中文動作名稱）。新記的動作：教職員登入、確認經歷、確認 OCR 擷取結果、上傳佐證、刪除經歷與佐證（含被擋下的嘗試）、上傳成績單或證照、設定與取消目標校系、送導師確認、自傳產生與儲存、導師修改自傳。只記動作、對象類型與編號；細節只放代碼（文件種類、校系編號、筆數），不記標題、檔名、自傳文字、姓名與學號。
- 管理者「操作紀錄」頁：`/admin/audit-logs`，最近 200 筆，可依動作篩選；只顯示角色與使用者編號，不顯示姓名與學號。管理者導覽列與系統總覽都有連結。
- 測試：新增 `tests/test_retention_audit.py`（14 個：刪除後資料列還在但畫面、自傳資料、我的五年、導師頁都看不到；送審過的經歷與佐證刪除被擋並記錄；快照不變；每種新動作都有紀錄；紀錄裡沒有姓名、學號、標題、檔名、自傳文字；管理者頁篩選與權限）。`tests/test_migration_setup.py` 加一個：SQLite 從零升級、降到 base、再升級；以及模擬舊資料庫（有表沒欄位）升級、降級、再升級。既有測試調整 2 處：`test_cloud_storage_routes.py` 原本檢查「刪除後資料列消失」，改成檢查 `deleted_at` 有值；`test_assistant_confirm_versions.py` 的導師確認紀錄現在前面多一筆 `package_review.request`（送審也有紀錄）。
- 完整測試：**875 通過、9 略過**（`D:\democase\ai\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`）。
- 展示站（5026，`D:\democase\.claude\launch.json` 新增 `m10-m11-5026`）：林小美（111534107，已送審）在「全國商業類技藝競賽 佳作」按刪除，顯示上面那段說明、資料還在；王小明（111534105）刪除「校園黑客松」成功，列表顯示「已刪除這筆經歷。」且不再出現；admin 的操作紀錄頁看得到「刪除經歷被擋下（已送審）」「刪除經歷」「送導師確認」與登入紀錄，篩選只剩該動作，表格裡沒有姓名或學號；手機寬度 375px 都沒有橫向捲動。

MySQL 注意事項（**這次沒有對 MySQL 執行**）：
- 執行 `flask db upgrade` 前一定要先備份正式資料庫（例如 `mysqldump`），並先問過使用者再執行。
- 這次只加兩個可為空的欄位，不改既有資料；`ALTER TABLE ADD COLUMN` 在資料多時會鎖表一小段時間，請挑沒人使用的時間。
- 降級會拿掉 `deleted_at`：已標記刪除的經歷與佐證會重新出現在畫面上（資料列一直都在）。

## 2026-10-27 系統完整測試手冊；三項 DEMO 合併後實測

日期：2026-10-27（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`）

- 合併：DEMO-02（`feat/bio-sentence-check`，合併提交 `bc35d05`）與 DEMO-03（`feat/activity-fit`，合併提交 `3fbdd40`），樣式檔尾與開發日誌的衝突都保留雙方；合併後完整測試 **867 通過、2 略過**。
- 合併後實測（5021，真的 Gemini，學生 111534107）：活動與經歷頁總結「最能用在：國立臺北商業大學」，點學校後對應活動亮起並列出「專業成果」占 30%；自傳加一句「我也主動向老師和同學請教，最後帶領團隊拿到全國第一名。」儲存後疑點顯示「有 1 句找不到資料依據」；升學 Agent 依序亮起三組工具並產生第 3 版草稿；伺服器沒有錯誤紀錄。
- 實測發現的限制（寫進手冊第十節）：Gemini 寫「我從小就對電腦應用充滿好奇，在五專期間，特別是參加了全國商業類技藝競賽…」，因為同一句也有資料裡的競賽名稱，整句算有依據。
- 新增 `docs/05_交接與專案管理/系統完整測試手冊.md`：測試環境（5020 無 AI、5021 Gemini）、帳號、記錄方式、自動化測試、共通與權限（X）、學生（S）、升學 Agent（AG）、導師（T）、科辦（F）、管理者（A）約 90 條測試與預期結果、已知限制、測試報告範本。
- 手冊驗證：用 `run_demo.py` 的種子資料逐角色打開 35 個頁面，除了「未登入開 `/help` 是 401」「沒有目標校系時版本紀錄轉到目標校系頁」兩個預期行為，其餘都是 200；學生開導師與管理者頁是 403。抽查後修正導師確認流程（改成「內容合理，確認」／「需要修改」→「送出」，撤回在確認後才出現）與活動頁說明文字。

## 2026-10-27 升學 Agent 執行過程看得見（DEMO-01）

日期：2026-10-27（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`）

目標：10-28 要交 75% 完成度。老師最在意「Agent 要有分工」；原本按下按鈕要等 30～40 秒，只看到最後結果。改成畫面逐步顯示 Agent 把工作分給哪組工具、每組做出什麼。

- 引擎（`app/services/agent_engine.py`）：新增 `start_task`（先建執行中的紀錄）、`fail_task`、`progress`；`run` 可接已建好的 `task_id`，每次「決定下一步」與「執行工具」前後都把進度存進 `agent_tasks.result_json`（`phase`、`current_tool`、已完成的步驟；每步多記 `ok` 表示工具有沒有失敗）。
- 學生觸發（`app/services/agent_advisor.py`）：`start_advisor` 在背景執行緒跑 Agent，出錯時記成「失敗」，畫面不會一直轉；新增 `TOOL_LINEUP`，四張卡片對應四組工具（媒合排序、學生條件、自傳、雲端檔案），顏色沿用五年色。排序工具的摘要拿掉給 AI 看的「考科與資格見 transfer」。
- 路由（`app/routes/student.py`）：按下按鈕後馬上打開結果頁；新增 `/student/agent/runs/<編號>/progress` 給畫面輪詢（只有本人看得到）。測試與 5013 記憶體展示站（所有請求共用一條 SQLite 連線）照舊同步執行，可用 `AGENT_BACKGROUND` 設定。
- 畫面（`student_agent_run.html`、`design-system.css` 檔尾 DEMO-01 區塊）：上方深色列顯示「Gemini 正在想下一步要用哪個工具…」「正在『準備自傳草稿』…」；四張工具卡依序變成「執行中 → 完成」並顯示結果，沒用到的標「這次沒用到」；完成後自動重新整理顯示建議。之後再打開頁面，卡片會依 Agent 呼叫的順序再亮一次。減少動態效果的設定下不播動畫。
- 測試：`tests/test_agent_engine.py` 新增 7 個（每步存進度、失敗步驟標記、卡片涵蓋全部工具、結果頁顯示工具組、進度只給本人、執行中頁面會輪詢且不能重按、背景執行完成與失敗紀錄），共 33 個通過。
- 瀏覽器確認（5021 埠，真的 Gemini）：學生 111534107 先回答自傳問題，再請 Agent 規劃；畫面依序亮起「排序校系 → 查目標校系 → 準備自傳草稿」，完成後顯示「用了 3 組工具、3 個步驟」與 Gemini 的建議，產生第 2 版自傳草稿；手機寬度 375px 一欄排列、沒有橫向捲動；伺服器沒有錯誤紀錄。
- 平行工作：DEMO-02（自傳逐句檢查，`feat/bio-sentence-check`）與 DEMO-03（活動適合學校，`feat/activity-fit`）交給 GPT，各自的 worktree 已建好並登記在工作佇列。
## 2026-10-27 DEMO-02 自傳小幫手：逐句檢查找不到依據的句子

日期：2026-10-27（台灣時間）

開發者：Claude（分支 `feat/bio-sentence-check`）

目標：10-22 實測發現自傳草稿每段的「疑點」只看有沒有引用 F 編號，Gemini 自己補的句子（「並向老師和同學請教」「我從小就…」）頁面仍顯示「暫未發現資料疑點」。改成逐句比對，只用本機規則、不呼叫 AI。

- 規則（`app/services/autobiography_review.py`）：依「。！？」切句；句子出現具體經驗或行為的詞（請教、擔任、參加、負責、獲得、從小、曾經、帶領等）才檢查，純感想和連接句（「這讓我更確定方向」）不檢查。檢查時，句子含有資料的名稱關鍵詞（課名、證照名、活動標題、分數，例如「資料庫管理實務」「SQL」「85分」），或和任何一筆資料、學生回答有連續 4 個字相同，就算有依據。寧可少抓，不把正常句子標成疑點。
- 每段審查結果多一個 `unsupported`（找不到依據的句子原文）。有這類句子時疑點改成「有 N 句找不到資料依據」、⚠，建議「刪掉或改成你真的做過的事，再補上依據」。原本「引用不存在的來源」「這題還沒回答」「沒有資料佐證」三種情況優先，文字不變。
- 畫面：自傳頁疑點區塊逐條列出這些句子，用「」框起來，左邊黃色細線（`design-system.css` 檔尾 `/* DEMO-02 自傳逐句檢查 */` 區塊）。

修改檔案：
- `app/services/autobiography_review.py`
- `app/templates/student_autobiography.html`（疑點區塊）
- `app/static/css/design-system.css`（檔尾新增區塊）
- `tests/test_autobiography_review.py`
- `docs/03_開發紀錄/development-log.md`

驗證：
- 先寫 5 個新測試並確認失敗，再實作：上面兩句會被抓；「在五專二年級修習『資料庫管理實務(SQL)』這門課時，我獲得了85分的成績」不會被抓；學生回答裡寫過的內容不會被抓；感想句不會被抓；原本三種疑點仍然優先。原有 4 個測試照樣通過。
- 完整測試：847 通過、9 略過。
- 5022 展示站（`D:\democase\.claude\launch.json` 新增 `bio-sentence-5022`，該檔不在 Git 裡）：學生 111534105 設定目標校系、回答 4 題產生示範草稿，四段疑點顯示正常；在第 2 段加上兩句 Gemini 式句子並儲存後，顯示「⚠ 有 2 句找不到資料依據」並逐條列出這兩句，「這讓我更確定方向」沒有被列出。手機寬度 375px 沒有橫向捲動。

下一步：
- 規則是關鍵詞比對，學生換句話說（同義詞）時可能誤判成沒有依據，或句子剛好和回答有 4 個字相同而漏抓；請用真的 Gemini 草稿再多測幾份，視情況調整經驗詞清單。
- 等主對話檢查差異後合併。
## 2026-10-27 DEMO-03 活動與經歷：每筆活動適合哪些學校的甄審

日期：2026-10-27（台灣時間）

開發者：Claude（分支 `feat/activity-fit`，從提交 `69001f0` 分出）

目標：導師 10-21 要求「活動不是只有一筆，要能全部丟進去，分析適合哪間學校的甄審」。10-28 進度報告（75%）要展示。

- 新服務 `app/services/activity_fit.py`（只用本機規則，不呼叫 AI）：對學生每一筆活動與經歷，找出哪些校系的甄審項目會用到這筆的類別，附上項目名稱與占比。
  - 校系範圍：有目標校系只看目標校系；沒有目標時，用推薦排序（`rank_programs`）裡「可報」、學群不是「不相關」的前 10 個。
  - 一個校系有好幾個項目用到同一類別時取占比最高的；每筆最多 3 個校系，依占比由高到低。
  - 項目對應的類別取自缺件比對（`analyze_gap`）的結果，兩邊一定一致；沒有修改 `gap_service.py`、`matching_service.py`。
  - 同一個系可能有不同招生管道（展示資料裡北商資管有二技技優甄審和日間部申請入學兩筆），所以每個校系都標出招生管道。
- 活動與經歷頁（`app/routes/student.py` 的 `portfolio_list` 多傳一個 `fit`；`app/templates/student_portfolio.html`）：
  - 上方總結「你的 N 筆活動，最能用在：A 校、B 校」，下面列前 3 個校系（幫得上幾筆、最高占比）。同一間學校兩個系，標題只寫一次學校名稱。
  - 每筆紀錄下方「對這些學校的甄審有幫助」，列校系、項目名稱與占比（例如「其他」占 20%），附一條占比長條。沒有校系用到的類別寫「目前目標校系的甄審沒有列這一類」（沒有目標時寫「目前推薦的校系甄審沒有列這一類」）。
  - 互動：點一間學校（總結或紀錄裡都可以），用得上它的紀錄亮起來、其他淡出，狀態列寫「某校用得上你 N 筆紀錄」；再點一次或按 Esc 取消。占比長條與標題的螢光底線在捲到畫面時才長出來。
  - 尊重 `prefers-reduced-motion`：不加動畫，長條直接完整顯示；沒有 JavaScript 時也是完整顯示。
  - 樣式加在 `app/static/css/design-system.css` 檔尾，用 `/* DEMO-03 活動適合學校 */` 包起來。
- 測試：新增 `tests/test_activity_fit.py` 6 個（有目標只看目標、沒有目標用推薦前幾名並依占比排序、最多 10 個校系、類別沒被使用時回傳空清單與說明、總結依幫得上的筆數排序、活動與經歷頁看得到校系名稱與占比）。先寫測試確認失敗，再實作。
- 瀏覽器確認（5023 埠，`D:\democase\.claude\launch.json` 新增 `activity-fit-5023`）：
  - 111534105（沒有目標校系）：比對推薦排序前 9 個可報校系（可報且相關的只有 9 個），總結「最能用在：國立臺中科技大學、國立臺北商業大學」；點北商資管（日間部申請入學），3 筆紀錄亮起來。
  - 111534107（有目標校系）：只列目標北商資管（二技技優甄審），競賽「專業成果」占 30%、服務學習「其他」占 10%。
  - 手機寬度 375px 沒有橫向捲動。
- 實測中修掉兩個問題：標題重複同一間學校；長項目名稱（「書面資料審查（簡章未列分項比例）」）把校系名擠成一字一行，改成校系、占比、長條分三行。

下一步：
- 「書面資料審查（簡章未列分項比例）」對應全部類別、占 100%，會排在第一個；之後可以考慮把沒有分項比例的項目排在有分項比例的後面。
- 目前以類別比對，還沒看活動內容本身（例如資訊類活動對資訊系更有幫助）；之後可以讓 AI 補一句理由。

## 2026-10-22 OCR 辨識過程：缺少的欄位不再顯示成「0」

日期：2026-10-22（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`）

- 使用者在成績單確認頁（5020 展示站）指出小錯：「查看 OCR 辨識過程」寫「讀取檔案（大小未記錄 像素）」「抓到 0 個字元」，但下方原始文字明明有「程式設計 3 92」。
- 原因：展示站用固定的示範 OCR（`document_analysis_service.py` 的 `deterministic_demo`），步驟紀錄沒有大小和字數；`app/services/ocr_trace.py` 把缺少的欄位當成「未記錄」接上單位、字數預設成 0。
- 修正：有大小才寫「（寬×高 像素）」；有字數才寫「抓到 N 個字元」；示範模式改寫「讀取檔案（示範模式，沒有真的辨識）」「產生示範文字（示範模式，沒有真的辨識）」。只改說明文字，不改步驟紀錄。
- 測試：`tests/test_ocr_trace.py` 新增 2 個（真的紀錄、缺欄位、示範模式），共 8 個通過。用新程式讀 5020 資料庫裡那份文件的紀錄，三行說明都正確。5020 展示站沒有重啟（重啟會清空使用者剛上傳的資料），所以畫面要等下次重啟才會換成新文字。

## 2026-10-22 登入頁「Demo 快速登入」與合併後實測

日期：2026-10-22（台灣時間）

開發者：Claude（分支 `feat/google-docs-autobiography`）

目標：使用者要求把測試帳號密碼寫在登入頁，參考另一組的招生系統（recruitmentsystem.duckdns.org）的「Demo 快速登入」區塊。

- 參考做法：登入框下方另一張卡片，註明開發測試用，帳號依角色列成按鈕，點了就登入。我們只有 4～5 個帳號，不做搜尋框。
- 修正既有問題：`scripts/run_demo.py` 早就設了 `DEMO_ACCOUNTS: True`（註解寫「登入頁顯示展示帳號」），但登入頁只看 `LOCAL_DEMO_MODE`，所以 5000、5014～5021 的展示站登入頁都看不到帳號表；只有 5013（`app/demo.py`）看得到。
- 改法：`DEMO_ACCOUNTS` 改成帳號清單，由各展示站自己提供（`run_demo.py`：學生 111534105、111534107、導師 teacher01、科辦 staff01、管理者 admin，密碼 demo1234；`app/demo.py`：student_demo 等四個，密碼 demo2026）。登入頁有清單才顯示，`FLASK_ENV=production` 一律不顯示。
- 畫面：便條紙色的「Demo 快速登入」卡片；每個帳號一個按鈕，左邊色條依角色（沿用五年色），顯示姓名、說明、帳號與密碼；按鈕是一個隱藏帳密的登入表單，不需要 JavaScript。
- 測試：`tests/test_student_navigation.py` 原本的測試改成檢查 `DEMO_ACCOUNTS`，並加上正式環境不顯示、快速登入按鈕帶的帳密能登入。
- 瀏覽器確認（5020 埠）：卡片顯示 5 個帳號，按「陳導師」直接進教師工作台；手機寬度 375px 沒有橫向捲動。
- 同一天合併後實測（5020、5021 埠，`launch.json` 新增 `merged-demo-5020`、`merged-demo-ai-5021`）：推薦排序、招生時程、升學 Agent 固定流程與 Gemini 模式（「AI 決定步驟」）都正常；自傳草稿的 Gemini 流程能產生第 1 版草稿。
- **發現但還沒改**：自傳草稿每段的「疑點」只看有沒有引用 F 編號（`app/services/autobiography_review.py`），不逐句比對。實測草稿出現資料和回答都沒有的句子（「向老師和同學請教」「從小就…」），頁面仍顯示「暫未發現資料疑點」。

## 2026-10-22 升學 Agent：T2 擷取招生日程（候選、管理員核准後取代）

日期：2026-10-22（台灣時間）

開發者：Claude（分支 `feat/a3-matching`）

目標：背景巡查的擷取工具也能讀出招生日程；日程先成候選，由管理員核准後才取代目前的招生時程。

- 新資料表 `admission_schedule_events` 與遷移 `c4e2b7a91d05`（接在 `a7c3e9d10f42` 之後）。SQLite 從零升級、降級、再升級都測過。**MySQL 還沒執行這支遷移**，執行前要先備份並問使用者。
- 擷取提示詞加入日程表。候選日程的日期錯誤、或結束早於開始的略過，不寫入。
- 管理員招生資料 Agent 頁：候選日程與目前日程逐項比對，分成「相同」「日期不同」「新增」「目前有但沒擷取到」，整組核准或退回；退回不影響目前日程。核准與退回都寫 `audit_logs`。
- 真的 Gemini 實測 115 學年度官方日程 PDF：
  - 第一版提示詞 19 項，3 項錯（2 項技優保送專用被列入、1 項讀錯欄位日期）。
  - 改提示詞後第二版 17 項，日期全對。報名費「4/23 24:00」被寫成「4/24 00:00」，兩者是同一時刻，屬於可接受的表示差異。
  - 核准後招生時程頁顯示 17 項並附 PDF 出處。
- 測試：`tests/test_schedule_extraction.py` 14 個；相關測試 88 通過。完整測試 **764 通過、9 略過**（交接後於 2026-10-22 補跑，`--basetemp` 指定暫存資料夾）。
- 還沒做：C1～C12 報考條件的擷取；把簡章 PDF 網址（不是入口首頁）登記成來源，才擷取得到校系加權。
## 2026-10-22 升學推薦加入插大（轉學考）示範資料

日期：2026-10-22（台灣時間）

開發者：Claude（分支 `feat/transfer-exam`，worktree `D:\democase\_worktrees\ai-wt-transfer-exam`）

目標：指導老師 10-21 要求升學範圍不要只放二技、插大也要（規格 D4）。北中南各放 1～2 間資訊相關科系的示範資料，接進推薦排序頁。

- 查資料（只用各校官方網域的簡章，2026-10-22 查詢；官網最新是 115 學年度，116 學年度簡章要等明年春天才公告）：
  - 北部：國立臺灣大學資訊工程學系，插二年級。不考筆試，書面審查占 100%（審查成績未達 70 分不錄取），報名費 1,500 元（臺大 115 轉學考簡章第 1、4、37 頁）。
  - 中部：國立中興大學資訊工程學系，插二年級。考微積分Ａ×1、計算機概論×1.5、英文×1，報名費 1,600 元（臺灣綜合大學系統 115 轉學考聯合招生簡章第 1、2、3、23、71 頁）。
  - 嘉義：國立中正大學資訊管理學系，插二年級與插三年級各一筆。考計算機概論×1、英文×1，報名費 1,200 元（同一份聯招簡章第 49、65 頁）。
  - 五專畢業生能插幾年級：聯招簡章寫「專科學校畢業，可報考二或三年級」，專科應屆畢業生可以先報考；臺大只招二年級。
- 資料：新增 `app/content/admission_transfer_demo.csv`，每筆都有插入年級、名額、報考資格、考科、報名費、報名日期、考試日期、招生網址、簡章網址、出處頁碼與查詢日期。沿用 `AdmissionProgram`：招生類別寫「插大（轉學考）」，志願代碼用 `TRF-` 開頭。**沒有新增資料庫遷移**：考科等說明留在 CSV，由程式讀取。
- 匯入：新增 `app/services/transfer_exam.py`（`import_transfer_programs`，做法比照 `import_seed_programs`；只考筆試的不建評分項目，臺大有書審才建一個 100% 的項目）；`scripts/run_demo.py` 也會匯入。
- 推薦排序（`matching_service.py`）：
  - 只考筆試的插大不算契合度，顯示「依考試成績，不算契合度」，理由列出考科、報名費、日期與出處；有書審的臺大照常算契合度。
  - 系統無法判斷插大的報考資格，一律「需確認」，並附簡章原文（D8）。
  - 每張卡片標示招生管道（二技技優甄審、插大（轉學考）、日間部申請入學）；插大卡片另外列出「轉學考招生網站」連結。
  - 沒有動 `is_related` 和 `_relation_reason`。
- 招生時程（`admission_schedule.py`）：插大是自己的管道，不做共用日程；推薦排序頁與時程頁寫「插大（轉學考）時程依各校簡章」並附學校網址。
- 招生連結：`admission_school_links.csv` 補上臺大、中興、中正的官方招生網址。
- 目標校系頁（`student_gap.html`）：只考筆試的插大校系在頁首加一句「只看筆試成績，不收備審資料」，避免學生以為要準備備審。
- 升學 Agent（`agent_advisor.py`）：排序工具原本只把前 10 名交給 AI，插大排在可報的二技後面，AI 根本看不到。改成另外附一份插大清單（插幾年級、考科、需確認、不算契合度的原因），工具摘要寫出插大有幾個；AI 規則加一條「插大依考試成績、不算契合度，要說考科並提醒核對資格」；AI 不能用時的固定版總結也會列出插大。
- 測試（先寫、看到失敗才實作）：新增 `tests/test_transfer_exam.py`，共 17 個（含 Agent 1 個）；完整測試 **767 通過、9 略過**。
- 實際看畫面（5017 埠展示站，`launch.json` 新增 `transfer-exam-5017`）：推薦排序頁有 45 張卡片，其中二技技優 36 張、插大 4 張；插大卡片有管道標籤、考科、資格與出處連結；把中正資管插三年級設成目標後，目標校系頁出現新提示；時程頁顯示「依各校簡章」與兩個官方網址。
- 沒做到或待確認：
  - 臺大簡章沒寫五專應屆畢業生能不能先報考（資料標「待確認」）。
  - 高雄、臺南沒有資訊科系的插大資料：成大、中山 115 沒有資管、資工的轉學名額；高雄大學的簡章 PDF 已下架（404）；臺北大學的招生頁找不到簡章 PDF。南部目前只有嘉義的中正。
  - 管理員的校系頁會把只考筆試的插大校系標成「加權合計不等於 100%」，這次沒有處理。
  - 升學 Agent 這次只用固定流程（不連 AI）測過；接上真的 Gemini 時，AI 會不會照新規則講插大，還沒實測。
- 下一步：明年春天各校公告 116 學年度簡章後更新 CSV；補一間高雄或臺南的資訊科系。
## 2026-10-22 推薦排序改用學群判斷相關科系（A2／T5 最小版）

日期：2026-10-22（台灣時間）；分支 `feat/student-groups`

- 問題：`is_related` 用系名關鍵字，「會計資訊系」「醫護教育暨數位學習系」被當成資管相關排在前面。
- 新增 `app/content/curriculum_groups.csv`：111、113 學年度入學資管科修業科目表（科目 → 學群：資訊／商管／通識／不分學群），每列附出處；名稱看不出學群的科目（微積分、微電影製作、多媒體設計等）標「待確認」，不猜。
- 新增 `app/content/department_groups.csv`：校系 → 學群，依招生類別與系名人工整理並附依據；「創意科技與產品設計系」標待確認。
- 新增 `app/services/eligibility_service.py`：只用已確認、及格的成績；專業科目少於 3 科、兩學群一樣多、或沒有那一屆課綱表時回傳「待確認」；對不到課綱的課名另外列出。不呼叫外部 AI。
- `matching_service.py` 只改 `is_related`／`_relation_reason` 與排序：相關 → 待確認 → 不相關；理由寫出「你修過的資訊類專業科目 N 科，這個系屬資訊學群（依據：…）」。
- 展示資料兩個課名對齊真實課綱（資料庫管理實務(SQL)、系統分析與設計）。
- 驗證：先寫測試看它失敗（4 個排序案例＋模組不存在），實作後完整測試 767 通過、9 略過。
- 展示站（5018，`D:\democase\.claude\launch.json` 新增 `student-groups-5018`）實際看推薦排序頁：
  - 111534105（展示資料）：前 8 名都是資訊學群（北商、中科、雲科資管，中科資工、資訊應用菁英班），理由寫「你修過的資訊類專業科目 4 科，這個系屬資訊學群…（依據：…）」；創意科技與產品設計系居中顯示「學群待確認」；會計資訊系、醫護教育暨數位學習系排在不相關那一組，理由寫明屬商管／醫護學群。
  - 111534107（展示資料，只有「計算機概論」）：每一間都顯示「學群待確認」，並列出對不到課綱的「計算機概論」。
- 待確認時，理由會列出對不到課綱的課名。
- 限制：課綱表只整理 111、113 學年度，其他屆一律待確認；學群分類是人工依科目名稱與招生類別判斷，需科辦確認；不可報、需確認的分組排序不變。
## 2026-10-22 檔案存放可替換：本機／Google 雲端硬碟（StorageService）、Agent 依檔案編號取檔

日期：2026-10-22（台灣時間）

開發者：Claude（分支 `feat/cloud-storage`）

目標：依 V2 架構與 V1 規格「檔案存放要做成可替換的」，上傳檔案改走 StorageService；Agent 只能透過後端依檔案編號取檔。

- 新增 `app/services/storage_service.py`：`LocalStorage`（現有行為，位置仍是原本的路徑）與 `GoogleDriveStorage`（只用 `drive.file`，位置記成 `drive:<檔案 ID>/<存檔名稱>`，沿用 `file_path` 欄位，**沒有新增資料庫遷移**）。`STORAGE_BACKEND` 預設 `local`；沒設定、沒連線或上傳失敗一律存本機。權杖只放伺服器記憶體。
- 上傳流程（成績單／證照、獎懲記錄、佐證檔案）、預覽、下載、裁切、OCR 佇列都改走 StorageService；Drive 檔案讀本機快取 `drive-cache/`，快取不見時由後端取回。
- 刪除改成只標記（本機 `.deleted.json`、Drive `appProperties`），不永久刪除；資料庫沒存進去的孤兒檔才丟掉。送審快照沒有改動。
- 新增管理員「檔案存放設定」頁（`/admin/storage`，連線／中斷 Google，記稽核紀錄）。
- 新增 `app/services/agent_file_tool.py`（「查我的檔案」「取檔案內容」，只讀、檢查擁有者、白名單欄位、不拿原始檔、不碰 Drive）與 `app/services/deidentify.py`（姓名、學號、帳號、電子郵件、證號、電話、8～10 位數編號）；接進升學 Agent 學生觸發的工具。
- 設定文件：`docs/03_開發紀錄/01_參考與環境設定/Google雲端硬碟存放_設定步驟.md`（Google Cloud 設定、`.env`、移除方式）。
- 測試：新增 `test_storage_service.py`、`test_cloud_storage_routes.py`、`test_agent_file_tool.py`（先看失敗再實作）。完整測試 **791 通過、9 略過**（改動前 750 通過、9 略過）。
- **只用假物件測過**：Drive 上傳、下載、標記、垃圾桶、資料夾建立、權杖更新、OAuth 授權碼交換（`HttpDriveClient` 沒有連過真的 Google）。
- **需要使用者設定 OAuth 才能實測**：依設定文件填 `.env`、管理員連線後，實際上傳到個人 Google 雲端硬碟並預覽。
- 本機模式瀏覽器實測（5019 埠展示站，`D:\democase\.claude\launch.json` 新增 `cloud-storage-5019`）：展示學生上傳一張合成的成績單圖片 → 辨識完成（找到 1 筆）→ 「辨識中」縮圖、確認頁原圖預覽都正常；檔案存在 `instance/demo-uploads/learning-profile/1/`，路徑寫法和以前一樣，沒有產生雲端快取資料夾。管理員「檔案存放設定」頁顯示「目前存在：本機」。


## 2026-10-22 升學 Agent：真的 Gemini 實測與修正

日期：2026-10-22（台灣時間）

開發者：Claude（分支 `feat/a3-matching`）

目標：使用者要求用 Gemini 金鑰實測升學 Agent 的 AI 模式（巡查與學生觸發各跑一次）。

- 金鑰來源：`ai-wt-story` 沒有 `.env`（它的 5013 展示站固定關閉 AI），專案的 Gemini 金鑰在 `D:\democase\ai\.env`。新增 `D:\democase\.claude\launch.json` 的 `a3-matching-ai-5016`：啟動時把該檔載入記憶體再跑展示站（SQLite 展示資料庫，不連 MySQL）；沒有複製 `.env`、沒有顯示金鑰。
- 第一次實測失敗並找到原因：AI 決定步驟回 HTTP 400，自動改走固定流程。寫診斷腳本取得 Google 的錯誤訊息「Function call is missing a thought_signature」：新的 Gemini 會在工具呼叫上附 `thoughtSignature`，下一輪必須原封不動送回；引擎原本自己重組工具呼叫，把它弄丟了（小助手直接送回原內容所以沒事）。
- 修正（`app/services/agent_engine.py`）：AI 的決定保留模型原本的工具呼叫內容（含簽章），下一輪原樣送回；一次只送回實際執行的那一個工具呼叫。簽章只在這次執行的記憶體裡，不寫進 `agent_tasks`。
- 實測結果（修正後）：
  - 巡查：模式「AI 決定步驟」、沒有改走固定流程；Gemini 自己依序呼叫「檢查官方來源 → 列出待擷取的更新 → 擷取成候選校系」，再寫總結。技專校院招生委員會聯合會首頁不是簡章，擷取出 0 個候選校系，總結也照實說明並建議管理員檢視原始檔。
  - 學生觸發（展示學生 111534107，假資料）：沒回答自傳問題時，Gemini 排序、查目標校系後**沒有寫草稿**，給 5 點建議與「去回答自傳問題」連結；回答後再請，Gemini 依序「排序 → 查目標校系 → 準備自傳草稿」，產生第 2 版真的 AI 草稿，各段引用 F1～F4（成績、證照、競賽、服務學習）。
- 實測發現的畫面問題並修正：
  - AI 回答有 Markdown 粗體符號（`**`）：提示詞加「不要用 Markdown 符號」，引擎另外把 `**`、`#` 拿掉。
  - 學生觸發要等約 39 秒、按鈕沒有反應：三個 Agent 按鈕加上 `data-busy-text`（沿用全站的「送出後按鈕改成處理中、不能重複按」）。
- 測試：`tests/test_agent_engine.py` 新增 3 個（簽章送回、Markdown、等待文字），共 26 個；完整測試 **749 通過、9 略過**。
- 下一步：T2 擷取日程與 C1～C12；把簡章 PDF 網址（不是入口首頁）登記成來源，才擷取得到校系加權。

## 2026-10-22 升學 Agent 共用引擎最小版（背景巡查、學生觸發）

日期：2026-10-22（台灣時間）

開發者：Claude（分支 `feat/a3-matching`）

目標：依規格第〇節「一個 Agent、多組工具」，做出共用引擎；背景巡查跑通 T1＋T2，學生觸發接上 T6 與 T7。

- 新增 `app/services/agent_engine.py`：工具登記（`Tool`）、`AiDecider`（沿用小助手的 Gemini 工具呼叫，一次執行一個工具、結果交回再決定）、`run()`（最多幾步、AI 不能用時自動改走固定流程、每次寫一筆 `agent_tasks`，只記工具名稱、每步摘要與總結）、`taipei_time` 樣板篩選器（資料庫存 UTC，畫面顯示台灣時間）。
- 新增 `app/services/agent_patrol.py`（背景巡查）：工具「檢查官方來源」「列出待擷取的更新」「擷取成候選校系」；固定流程是檢查 → 列出 → 有 AI 才擷取 → 總結。新增 `flask agent-patrol` 指令，招生資料 Agent 頁新增「讓 Agent 巡查一次」按鈕與執行紀錄。
- 新增 `app/services/agent_advisor.py`（學生觸發）：工具「排序校系」「查目標校系」「準備自傳草稿」；Agent **不替學生選目標校系**、**學生沒回答過自傳問題就不寫**（給「去回答自傳問題」連結）；草稿和自傳頁一樣計次、存成新版本、每段標依據。推薦排序頁新增「請升學 Agent 幫我規劃」，結果頁 `/student/agent/runs/<編號>` 只有本人看得到。送給 AI 的內容不含姓名、學號（有測試）。
- 實測發現並修正兩個既有問題（`app/services/admission_agent_service.py`）：
  - Python 3.13 預設嚴格檢查憑證，技專校院招生委員會聯合會網站的憑證缺少 Subject Key Identifier 被拒；改成照常驗證憑證與網域，只關掉 `VERIFY_X509_STRICT`。
  - 網頁上的「網站人次」每次都變，導致每次巡查都誤報有更新；網頁改比對去掉標籤與計數器後的文字（PDF 仍比原始檔）。學校網頁多為 Big5，`_html_to_text` 改成 UTF-8 失敗時用 cp950 解碼（原本會變亂碼，擷取時 AI 讀不懂）。已存在資料庫的網頁來源，下一次巡查會因比對方式改變而多報一次更新。
  - `check_all` 多一個 `fetch` 參數（測試可換成假的）。
- 測試：`tests/test_agent_engine.py` 23 個（先看它失敗再實作）。完整測試 **746 通過、9 略過**。
- 瀏覽器確認（5015 埠展示站，沒有設定 Gemini，走固定流程）：學生第一次請 Agent → 排序 41 校系、提示先回答自傳問題並給連結；回答後再請 → 產生第 2 版示範草稿並給「打開自傳草稿」連結；時間顯示台灣時間。管理員登記技專校院招生委員會聯合會網址後巡查兩次：第一次「1 個有更新」、第二次「0 個有更新」，擷取因沒有 AI 留給管理員。
- **還沒驗證**：真的 Gemini 決定步驟（AI 模式只用假的 AI 測過）；T2 目前只擷取備審加權，還不會擷取日程與報考條件。
- 下一步：設定 Gemini 金鑰實測 AI 模式；T2 擷取日程與 C1～C12；其他工具組（T3 雲端、T5 學群、T9 科規）陸續接上同一個引擎。

## 2026-10-22 規格改版：一個 Agent、多組工具

日期：2026-10-22（台灣時間）

開發者：Claude（分支 `feat/a3-matching`）

目標：使用者認為五個 Agent 難維護，並補充要能生成自傳、要有雲端；依 V2 架構提案（`資管科學習歷程系統_v2.pdf`，2026-10-16 已同意）把雲端寫清楚。

- 修改 `docs/02_需求與設計/02_設計規格/AI_設計規格_Agent分工規劃_2026-10-22.md`：
  - 新增第〇節：一個「升學 Agent」引擎（沿用小助手的工具呼叫迴圈，抽成共用引擎），兩種啟動方式（背景巡查、使用者觸發）；工具組 T1～T10 表（現況、負責端）。
  - 雲端（T3）：系統把檔案存進 Google Drive，MySQL 記檔案索引；現在用個人帳號測試，正式導入改學校 Workspace 並在學生帳號備份；Agent 不直接瀏覽 Drive，只依檔案編號取這次需要的檔案。學生舊檔用選檔視窗自己挑。
  - 決定 D1 改為 D9（一個引擎）、新增 D10（雲端）、D11（自傳是工具組）；分工改依工具組；11/4 範圍：A3 最小版標為已完成、新增 7b 共用引擎最小版；待確認新增 Q9。
- 架構圖：`ai/docs/images/D-46-agent-engine-tools.*`（圖 43），圖 42 五個 Agent 版作廢（在 `D:\democase\ai`，未提交）。
- 更正：先前在對話裡建議「Agent 讀取學生雲端硬碟的檔案」，與 V2「AI 不直接爬 Drive」不一致，已依 V2 改寫。
- 驗證：只改文件，沒有改程式，沒有執行測試。
- 下一步：使用者確認後，做 7b 共用引擎最小版。

## 2026-10-22 招生時程頁

日期：2026-10-22（台灣時間）

開發者：Claude（分支 `feat/a3-matching`）

目標：使用者選擇先做招生時程；每個校系要看得到報名、截止等日期（規格 C11）。

- 資料 `app/content/admission_schedule.csv`：115 學年度二技技優甄審 13 個學生要注意的日程，逐列對照技專校院招生委員會聯合會官方 `115enterdate.pdf`（2026-10-22 下載核對），每列附出處。116 學年度官網「重要日程」頁目前顯示「尚無資訊」，沒有放任何推測日期。
- 新增 `app/services/admission_schedule.py`：`load_schedule`（同一天依官方表格順序）、`program_channel`（6 位數志願代碼＝技優甄審）、`timeline`（標出已過／進行中／還沒到、下一步；當年度沒有日程時用前一年並標成參考）、`latest_timeline`；`CHECKED_ON` 記錄最近一次查官網的日期。
- 新增頁面 `/student/schedule`：技優甄審日程、這一屆結束時說明下一屆尚未公告與去年簡章下載日、每個目標校系該看哪份時程與連結。推薦排序頁每張卡片加一行時程狀態；目標校系頁加「招生時程」按鈕。
- 日間部申請入學：各校日期不同，這一版只寫「依各校簡章」並附學校招生網站，沒有收各校日期。
- 首頁提醒這次沒做：目前資料都是已結束的 115 學年度，首頁提醒只會顯示「尚未公告」；等 116 日程公告後再加。
- 測試：`tests/test_admission_schedule.py` 13 個（先看它失敗再實作）。完整測試 **723 通過、9 略過**。
- 瀏覽器確認（5015 埠展示站）：招生時程頁 13 個日程依官方順序、全部標「已過」並顯示 116 尚未公告；推薦排序頁技優甄審卡片顯示「115 學年度二技技優甄審時程已結束，116 學年度尚未公告」，申請入學卡片顯示「依各校簡章」。
- 下一步：116 日程公告後（去年是 11/20）加進 CSV 並更新 `CHECKED_ON`；各校申請入學日程；首頁倒數提醒；之後可由 A1 自動抓日程。

## 2026-10-22 各校系加上招生連結

日期：2026-10-22（台灣時間）

開發者：Claude（分支 `feat/a3-matching`）

目標：使用者提出每個校系要能直接連到該校的招生資訊。

- 新增 `app/services/admission_links.py`：每個校系依序列出「簡章原始來源」（Agent 擷取時記下的 `source_url`）、「學校招生網站」、「二技技優甄審報名入口（技專校院招生委員會聯合會 `https://www.jctv.ntut.edu.tw/enter/`，只給 6 位數志願代碼的技優甄審志願）」。查不到的學校不自己猜網址。
- 新增 `app/content/admission_school_links.csv`：目前資料裡的 7 所學校官方招生網址，2026-10-22 逐一開啟確認；臺中科大、北商大、北護、虎尾科大、高科大、高餐的首頁都有二技招生連結，雲科大首頁內容讀不到，網址取自該校簡章。
- 推薦排序頁、目標校系頁的每張卡片都顯示連結（新分頁開啟，`rel="noopener noreferrer"`）。
- 測試：`tests/test_matching_service.py` 新增 9 個（先看它失敗再實作），包括「種子資料裡每一所學校都要有官方網址」。完整測試 **710 通過、9 略過**。
- 瀏覽器確認：5015 埠展示站推薦排序頁 41 個校系全部有連結。
- 順帶查到的事實（給 A1、C10 用）：北商大招生網站有「二技轉學」管道；二技技優甄審規定已透過其他管道錄取報到者不得再報名。
- 下一步：插大（轉學考）資料與管道還沒做；連結目前是學校層級，之後可由 A1 擷取到各系所的簡章頁。

## 2026-10-22 A3 媒合排序最小版（推薦排序頁）

日期：2026-10-22（台灣時間）

開發者：Claude（分支 `feat/a3-matching`，worktree `D:\democase\_worktrees\ai-wt-a3-matching`，從 `feat/google-docs-autobiography` 522e49a 開出）

目標：依 Agent 分工規格的 A3，先用現有二技校系資料與缺件比對公式，做出「全部校系判斷可不可報、排序、每一間寫理由」，並加入應屆檢查（C1）。

- 新增 `app/services/matching_service.py`：
  - `rank_programs`：對全部正式校系算契合度（就是 `analyze_gap` 的準備度，兩邊數字相同）、檢查報考資格條件、排序（可報 → 需確認 → 不可報；同組內資管相關科系在前，再依契合度）；每一間都有理由（條件、相關程度、各評分項目已有或還缺什麼）。
  - C1 應屆：預計畢業學年度＝入學學年度＋5；報考學年度前就已畢業的，在「限應屆」的志願顯示「不可報」，並提醒延畢的人告訴導師更正；沒有入學年度時顯示「需確認」。
  - 看不懂的條件類型一律「需確認」並顯示原文（規格 D8）。
  - 資管相關科系暫用科系名稱關鍵字（`RELATED_KEYWORDS`）判斷，A2 做好後改用學群。
  - `load_conditions`：讀 `app/content/admission_conditions_demo.csv`（**示範資料，非簡章原文**，兩筆）。
- 新增頁面 `/student/matching`（`app/templates/student_matching.html`），目標校系頁加「看全部校系的推薦排序 →」連結；頁尾寫明「契合度不是錄取機率」。
- 測試：`tests/test_matching_service.py` 16 個（先寫、看它失敗再實作）。
- 驗證：完整測試 **702 通過、9 略過**（Python 環境 `D:\democase\ai\.venv`）。用 `scripts/run_demo.py`（5015 埠）以展示帳號實際開啟推薦排序頁：41 個校系全部列出，資管相關科系排在前面，示範的「需確認」條件顯示原文與出處。
- 已知限制：關鍵字會把「會計資訊系」「醫護教育暨數位學習系」當成相關；理由是規則產生的，還沒交給 AI 改寫；只有 C1 與「其他（原文）」兩種條件；展示資料裡沒有已畢業的學生，「不可報」只在測試裡驗證。
- 下一步：A2 學群判斷取代關鍵字；C3 科系群類、C5 技優期限、C11 時程；AI 改寫理由。

## 2026-10-22 規格：五個 Agent 的分工規劃

日期：2026-10-22（台灣時間）

開發者：Claude（逐字稿整理視窗）

目標：依 2026-10-21 指導老師兩份錄音，以及使用者補充的「自動追蹤科上規定」，寫出 Agent 分工、組員分工與 11/4 前的範圍。

- 新增：`docs/02_需求與設計/02_設計規格/AI_設計規格_Agent分工規劃_2026-10-22.md`（草稿，不授權寫程式）。
- 內容：
  - 五個 Agent：A1 校系蒐集（擴充現有招生資料 Agent，加入二技統測分發與插大，多擷取報考資格、報名費、考科）、A2 資格判斷（新做，成績單 OCR 加課綱）、A3 媒合排序（新做，對全部校系判斷可不可報、算契合度並寫理由）、A4 小助手（加一個工具）、A5 科規追蹤（新做，沿用 A1 的偵測更新，追蹤畢業門檻與認可證照，依入學年度分版本）。
  - 組員分工：學校端（A1、A5）、個人端（A2）、使用者負責整合（A3、A4）。
  - 11/4 前的範圍與驗收標準。
- 決策草案：不算「錄取機率」，改叫「契合度」；系統沒有歷年錄取資料，專題規則也不允許 AI 判定錄取。這點待使用者確認，並向老師說明。
- 驗證：對照現有程式（`admission_agent_service.py`、`assistant_tools.py`、`gap_service.py`、`knowledge_service.py`、`scripts/build_knowledge.py`）與 10-10 推薦校系規格、10-09 小助手規格，確認沿用的機制都存在；本次只寫文件，沒有改程式，也沒有執行測試。
- 補充（使用者提醒隱藏的報考條件，例如限應屆畢業）：新增「報考資格條件清單」C1～C12，包括應屆、學歷與同等學力、科系群類、統測考科、技優資格與期限、成績排名、語言、工作年資、身分名額、報名衝突、時程，以及「其他（原文）」。決策 D8：擷取不到類型或缺少學生資料時，一律顯示「需確認」，不當成符合。現況缺口：學生資料有 `admission_year`，但沒有延畢與休學紀錄、統測群類、證照取得日期期限的檢查。
- 下一步：使用者與組員確認第九節待確認事項（D2 契合度、組員 A／B 人選、四技所指、科規官方頁面、應屆定義、身分要不要收）；確認後開工。

## 2026-10-21 修正：縮小的成績單圖片三年級年級變空白

日期：2026-10-21（台灣時間）

開發者：Claude（學年歸類修正視窗，分支 `feat/ocr-grade-level-fix`，從 `feat/ocr-background-queue` cca69d0 開出）

目標：PDF 成績單縮成長邊 1400、1800、2400 像素時，三年級 24 門課的學年學期全錯，拖低完全正確數；修好後不能讓 3507、1600 變差。

- 原因：三年級的年級是空白，不是歸到別的學年。表頭裁切包進了頁首的班級學號列，「第 3 學年」又緊貼表格上緣橫線，縮小後文字偵測整行漏掉；1400、1600 時第二欄上方的頁首大標題還被當成橫線。
- 修正（`app/services/ocr_pipeline.py`）：
  - `detect_transcript_panels` 多記 `header_top`（表格最上緣橫線），各欄偏離中位數就改用中位數；`analyze` 的表頭裁切從這裡開始。
  - 新增 `school_year_from_header`、`resolve_panel_grades`：先讀完所有欄的表頭，讀不到「第 N 學年」的欄位用起訖年月（沒有就用欄位順序）推算，互相矛盾就不猜；推算的課程加核對提示「年級表頭未辨識，依起訖年月推定，請核對。」。
  - `parse_panel_words` 多一個 `grade_note` 參數放這條提示。
- 測試（先寫、看它失敗再修）：`tests/synthetic_transcript.py` 的 `render` 多 `student_line` 選項，在表格正上方印假的班級學號列；`tests/test_transcript_layout_rapidocr.py` 新增 7 個測試（表頭裁切從表格上緣開始、頁首密集字不影響單一欄、起訖年月推算、欄位順序推算（含中間空欄）、矛盾時不猜、整條流程的推算與提示）。這些測試用假的辨識結果，不需要模型檔。
- 驗證：
  - 完整測試 **686 個通過、9 個略過**（Python 環境 `D:\democase\ai\.venv`）。
  - 真實 PDF 成績單（只在本機讀，沒有複製進 repo；腳本放本機暫存資料夾）：1400／1600／1800／2400／3507 像素學年學期都是 85／85；完全正確 2400 由 59 → 81、1800 由 57 → 75、1400 由 37 → 44，3507（85）與 1600（71）不變。使用者要求加測不整齊的尺寸：1700／2050／2600／2900 也都是 85／85（修正前 2050～2900 只剩 31 對）。詳見 `docs/03_開發紀錄/OCR驗收紀錄_2026-10-20.md`「修正後：三年級學年歸類」。
- 下一步：使用者決定是否把解析度提醒門檻從 3000 降到 2400（`upload_quality.py`，本次沒改）。

## 2026-10-21 系統啟動手冊；小組 main 更新到最新

日期：2026-10-21（台灣時間）

開發者：Claude（一鍵啟動視窗）

目標：使用者要一份系統啟動手冊單獨提交，並推到小組 `main` 與兩個 repo 的 `feat/google-docs-autobiography`。

- 新增 `docs/05_交接與專案管理/系統啟動手冊.md`（單獨一個提交）：系統組成、事前準備、一鍵啟動各步驟、正確首頁辨認、登入帳號、展示站與手動啟動、停止與重啟、`.env` 設定、常見問題、不上傳的檔案。之前未提交的手冊檔已不在資料夾，依原稿重建，並改寫 `main` 的敘述。
- `組員開啟說明.md`：`main` 已更新到同一版，把「`main` 是舊版、`-b` 一定要加」改為「目前同版，建議加 `-b` 以免之後落後」，並連到手冊；`README.md` 加手冊連結。
- 推送：小組 `main` 由 `e5204c8` 快轉到本分支最新提交（包含任務 A、B、C 的合併），不 force push。
- 驗證：只改文件，沒有改程式。

## 2026-10-21 研究：成績單圖片解析度門檻能不能放寬

日期：2026-10-21（台灣時間）

開發者：Claude（任務 B 視窗，分支 `feat/ocr-background-queue`）

目標：使用者指定的 PNG 成績單（1024×703）在上傳頁被「長邊小於 1600 像素」擋下，使用者要知道門檻能不能放寬。

- 方法：以 PDF 成績單的辨識結果為標準答案，把 PDF 縮成 1024～2400 像素，再試「整張放大回 3507」與「放大＋銳化」，課名、學年學期、學分成績分開計分；1024 像素 PNG 原圖與放大 2、3、3.4 倍各跑一次。每種尺寸跑兩次，結果相同。腳本與圖檔只在本機暫存資料夾。
- 結果：1024 像素放大後課名只對 3／85，救不回來；整張放大讓學分成績較好讀，但學年學期歸類變差，整體沒有改善。另發現 1400、1800、2400 像素都剛好錯 24 筆學年學期（＝三年級整張表），是表格歸類問題，不是解析度問題。
- 建議：最低門檻維持 1600、提醒門檻維持 3000；低於 1600 改成「收下檔案、跳過辨識、直接進手動輸入並顯示原圖」；另開工作修三年級表格歸類。詳見 `docs/03_開發紀錄/OCR驗收紀錄_2026-10-20.md`「解析度門檻研究」。
- 修改檔案：`docs/03_開發紀錄/OCR驗收紀錄_2026-10-20.md`、本日誌。沒有改程式，所以沒有重跑完整測試。
- 下一步：使用者決定要不要做「低於門檻改手動輸入」與「三年級表格歸類修正」。

## 2026-10-21 任務 C：390px 手機與減少動態效果瀏覽器驗收

日期：2026-10-21（台灣時間）

開發者：Claude（任務 C 視窗，分支 `feat/mobile-a11y-check`）

目標：完成待辦清單第 8 項尚未實測的部分：390px 手機、老師／科辦導覽、`prefers-reduced-motion`。

- 方法：5014 埠啟動 `scripts/run_demo.py`（合成資料），內建瀏覽器 390×844 逐頁量測學生主線與老師、科辦、管理員工作台約 35 頁；減少動態以「套用減少動態 CSS 規則」及「讓 `matchMedia` 回報減少動態後重跑頁面腳本」兩種方式模擬。確認頁用畫布產生的「僅為測試資料」圖片上傳。
- 修改檔案：
  - `app/static/css/design-system.css`：窄螢幕表格表頭與按鈕不換行、儲存格中文詞不拆字；`.table-wrap` 加 `position: relative`（表格內隱藏文字不再撐寬整頁）；老師／科辦／管理員頂端導覽 760px 以下不黏頂；自傳事實清單證據編號排到文字欄、清單只上下捲動；減少動態時 `html` 改 `scroll-behavior: auto`；首頁「轉學生？」連結點擊高度補到 24px 以上。
  - `app/templates/staff_certificates.html`：加視覺隱藏的 `h1`。
  - 新增 `docs/03_開發紀錄/瀏覽器驗收_手機與減少動態_2026-10-21.md`、`docs/05_交接與專案管理/交接_任務C_2026-10-21.md`；更新分工任務檔與待辦清單第 8 項。
- 曾試過但撤回：替浮動小助手在頁尾加留白——捲到底量測修改前也沒有內容被蓋住，沒有證據支持。
- 未修：學生首頁導覽第 1 步說明卡壓到目標上緣約 17px（要改 JavaScript，超出範圍）；實體手機觸控與系統減少動態設定未實測。
- 驗證：完整測試（`-p no:cacheprovider --basetemp`）**665 passed、9 skipped**；`git diff --check` 通過；瀏覽器量測結果見驗收紀錄，1280px 桌機回歸通過。
- 下一步：修 `components.js` 導覽定位；用實體手機開「減少動態效果」再走一次學生主線。

## 2026-10-21 任務 B 續：「辨識中」頁重新排版（掃描台＋時間尺＋完成印章）

日期：2026-10-21（台灣時間）

開發者：Claude（任務 B 視窗，分支 `feat/ocr-background-queue`）

目標：使用者認為第一版辨識中頁沒有排版設計（窄卡片＋灰色示意框，畫面大半空白），要求重新做版面設計。

- 版面：改成全寬兩欄。左邊是深色「掃描台」，放學生自己上傳的第一頁縮圖，掃描光由上往下掃；右邊是襯線大標題、三步驟時間軸（已收到檔案 → 辨識文字／排隊中 → 整理成課程清單）、時間尺（斜線區是平常需要的 10～30 秒，藍色是已經過的秒數，超過 30 秒會說明沒有顯示卡時可能要 1～2 分鐘）。寬度 820px 以下改成單欄。
- 和資料有關的互動：縮圖是真的檔案（背景執行緒先花約 1 秒做好第一頁縮圖，頁面查詢到就淡入）；排隊時顯示「前面還有幾份」；完成時在文件上蓋「找到 85 門課」印章，約 1.5 秒後進確認頁。失敗時文件變灰並蓋「未辨識」印章，手機上先顯示原因與按鈕，並附拍照或下載的建議。
- 辨識套件的英文錯誤（例如 `Failed to load document (PDFium…)`）改成中文說明給學生看，原文留在操作日誌的 `raw_error`。
- 修改檔案：`app/services/ocr_queue.py`（`make_preview`、`preview_path`、`queue_position`、`student_error`）、`app/routes/student.py`（新增 `preview` 路由；`status` 多回 `preview`、`ahead`、`found`）、`app/templates/learning_profile_processing.html`（重寫）、`app/static/css/design-system.css`（新增「辨識中」頁區塊）、`tests/test_ocr_background_queue.py`（新增 4 個測試）。
- PDF 轉圖套件不能跨執行緒同時使用，所以縮圖放在同一條背景執行緒做；做不出縮圖不影響辨識，頁面改用示意圖。
- 驗證：
  - 先寫測試看它失敗再實作（縮圖只限本人、縮圖失敗不影響辨識、排隊位置與找到筆數、英文錯誤轉中文）。完整測試 **679 passed、9 skipped**。
  - 瀏覽器實測（本機展示站、真實 RapidOCR、顯示卡 1）用使用者指定的兩份本機成績單（只在本機讀取，未複製進 repo）：PDF 成績單三次都看到真實第一頁＋掃描光，完成時印章顯示「找到 85 門課」並自動進確認頁（確認頁也是 85 門）；寬 1280 為兩欄、375 為單欄且沒有橫向捲動。PNG 成績單在上傳頁就被既有的解析度檢查擋下（長邊只有 1024 像素，門檻 3000），沒有進到辨識中頁，這是原本的規則，本次沒改。
  - 失敗頁用一個故意損壞的 PDF 實測：顯示中文原因、「未辨識」印章、三個按鈕，手機上原因與按鈕在最上面。
- 下一步：PNG 成績單若要能辨識，需要使用者決定是否放寬 `upload_quality.py` 的解析度門檻（另一個議題）。

## 2026-10-21 任務 B：成績單上傳後背景排隊辨識，先顯示「辨識中」頁

日期：2026-10-21（台灣時間）

開發者：Claude（任務 B 視窗，分支 `feat/ocr-background-queue`）

目標：上傳後要等辨識完才跳頁（PDF 成績單用顯示卡約 7～28 秒、CPU 更久），學生會以為當掉。改成上傳後立刻存檔並跳到「辨識中」頁，辨識在背景跑，完成後自動進確認頁。

- 修改檔案：
  - 新增 `app/services/ocr_queue.py`：本機單一背景執行緒依序辨識（不用 Celery 等外部服務，一次只跑一份，避免顯示卡記憶體不夠）。辨識結果、解析度警告與操作日誌的寫法沿用原本上傳路由；同一份文件重複執行只會真的辨識一次（先把 `queued` 原子改成 `processing` 才開始）；未預期的錯誤也會標成失敗，不會卡在辨識中。
  - `app/routes/student.py`：上傳只存檔、文件標成 `queued` 後跳到新的「辨識中」頁；新增 `processing`（辨識中頁）、`status`（給頁面定時查詢的 JSON，只回狀態不回內容）、`retry`（失敗後重新辨識）三個路由，都只限文件本人；確認頁遇到還在辨識的文件會先帶回辨識中頁；辨識中的文件不能按舊的「重新分析」。
  - 新增 `app/templates/learning_profile_processing.html`：成績單示意圖會一列一列變深、步驟清單與經過秒數；每 2 秒查詢一次，完成時全部點亮再跳確認頁；失敗時顯示原因與「重新辨識」「重新上傳」「改用手動輸入」；沒開 JavaScript 時每 5 秒自動重新整理；尊重「減少動態效果」設定。
  - `app/__init__.py`、`app/config.py`：新增 `OCR_QUEUE_MODE`（`thread` 預設／`inline` 在請求裡跑完／`manual` 只排隊）；自動化測試沒指定時用 `inline`，既有測試不用改。`thread` 模式啟動時把上一次沒跑完（`queued`／`processing`）的文件標成失敗並寫操作日誌，學生按「重新辨識」即可。
  - `app/templates/learning_profile.html`：辨識中的文件顯示「辨識中…」連到辨識中頁；`learning_profile_upload.html` 上傳按鈕忙碌文字改為「上傳中…」。
  - 新增 `tests/test_ocr_background_queue.py`（10 個）；`tests/test_student_flow.py` 兩個測試改成「上傳 → 辨識中頁 → 確認頁」，一個改成檢查按鈕文字「上傳中」。
- 沒有資料庫遷移：沿用 `source_documents.status`（新增 `queued`、`processing` 兩個值，欄位長度 30 足夠），失敗原因放在既有的 `document_extractions.error_message`。
- 驗證：
  - 先寫測試並確認失敗（找不到 `ocr_queue`），再實作；新測試涵蓋成功、失敗與重新辨識、未預期錯誤、重複查詢與重複執行、別人的文件不能查或重試、伺服器重開、背景執行緒真的會跑。
  - 完整測試（`D:\democase\ai\.venv`，加 `--basetemp`）：**675 passed、9 skipped**。第一次跑有 1 個舊測試失敗（它檢查上傳按鈕忙碌文字是「辨識中」），因為按鈕現在只負責上傳，已把該測試改成「上傳中」。
  - 瀏覽器實測（本機展示站、真實 RapidOCR、顯示卡 1，模型唯讀指向 `ai-wt-story\instance\ocr-models`）：上傳合成成績單 PDF（由 `tests/synthetic_transcript.py` 產生，僅為測試資料）後立刻看到「成績單辨識中」頁（辨識文字中、已經過 2 秒），查詢 5 次後約 10 秒自動跳到確認頁，辨識到 19 門課。
- 限制：只適用單一程序的伺服器；若改用多程序部署，啟動時的「中斷工作標成失敗」會誤標其他程序正在跑的工作，要改成記錄工作開始時間或改用資料表排隊。
- 下一步：使用者決定是否合併進 `feat/google-docs-autobiography`；任務 C 的手機驗收可順便看辨識中頁在 390px 的樣子。

## 2026-10-21 組員開啟說明：整合系統啟動手冊，標明最新版分支

日期：2026-10-21（台灣時間）

開發者：Claude

目標：使用者要組員一啟動就是最新版。另一個視窗寫的 `系統啟動手冊.md`（未提交）寫「clone 預設的 main 就是目前版本」，但小組 repo 的 main 停在 e5204c8，沒有任務 A；照它做會一直停在舊版。

- 把手冊中正確、原說明沒有的內容整合進 `docs/05_交接與專案管理/組員開啟說明.md`（README 與 `start_system.bat` 都連到這份）：系統組成表、一鍵啟動每一步做什麼、已 clone 在 main 的人如何切換分支、哪些檔案只在自己電腦、展示站參數（`--ocr`、`--gpu`、`--google`）、手動啟動、`.env` 設定表、常見問題補「無法自動更新」「首頁是舊版」。
- 開頭加醒目提示：最新版在 `feat/google-docs-autobiography`，clone 一定要加 `-b`。
- 腳本名稱、參數、`.env.example` 預設值都已和程式核對。
- `系統啟動手冊.md` 沒有提交、也沒有刪除，留給使用者決定。
- 驗證：只改文件，沒有改程式。
- 下一步：若把 `feat/google-docs-autobiography` 合併進 main，要更新這份說明的 clone 指令。

## 2026-10-21 任務 A：填入本科課程清單，課名校正生效並實測

日期：2026-10-21（台灣時間）

開發者：Claude（任務 A 視窗，分支 `feat/ocr-course-names`）

目標：使用者指定以 `D:\democase\ai\docs\OCR測試資料\` 的成績單作為課程清單來源，讓校正真正生效並實測。

- 修改檔案：
  - `app/services/course_name_correction.py`：`COURSE_CATALOG` 填入 58 門課名（成績單逐筆人工對照原圖抄錄，只取課名）；比對前先轉繁體（沿用 `traditionalize_course_name`）並統一全半形，所以「数位化育料處理」「合计學」「JAVA程式语言」「貢料庫管理實務(SQL）」也能對上。
  - `tests/test_course_name_correction.py`：新增 4 個簡體字／全形括號測試（先看到失敗再實作）。
  - `app/content/ocr_acceptance.py`、`tests/test_ocr_acceptance_page.py`：實測結果頁加入「課程名稱（清單校正後）85／85」與清單來源限制。
  - `docs/03_開發紀錄/OCR驗收紀錄_2026-10-20.md`：新增「課程名稱校正實測」一節。
- 實測（本機 PDF，RapidOCR 伺服器版，約 23 秒）：課程名稱完全正確由 74／85 提高到 **85／85**；共改名 13 筆（11 筆字形錯字＋2 筆只有簡體字），和人工抄錄的 85 列逐一比對沒有多也沒有少。真實檔案只在本機讀取；轉出的圖片與量測腳本放在暫存資料夾，沒有進 repo。
- 限制：清單與驗收是同一份成績單，結果偏樂觀；其他選修課與其他入學年度的課名還沒有。
- 實測時模型讀取主視窗 `D:\democase\ai-wt-story\instance\ocr-models`（唯讀，只在暫存腳本內指定路徑，沒有改主視窗任何檔案）；本 worktree 沒有模型檔。
- 驗證：完整測試 **665 passed、9 skipped**（需加 `--basetemp`）。
- 下一步：補其他選修課與入學年度的課名，用另一份成績單再驗收。

## 2026-10-21 任務 A：成績單課程名稱字形校正（引擎與核對提示）

日期：2026-10-21（台灣時間）

開發者：Claude（任務 A 視窗，分支 `feat/ocr-course-names`）

目標：OCR 讀錯的課名（例如「合計概論」「育料結構」）依本科課程清單改成字形相近的正確課名；學生仍要在確認頁核對。

- 修改檔案：
  - 新增 `app/services/course_name_correction.py`：字形混淆表（10 組，來源是 `OCR驗收紀錄_2026-10-20.md` 的 11 筆錯字）；`correct_course_name` 只在清單上恰好一個候選時才改，差異超過 2 字不改；`apply_name_correction` 改名、保留 `course_name_corrected_from`、設為需確認，並加一則核對提示「課程名稱已依課程清單校正為『…』（OCR 原文『…』），請對照原圖。」
  - `app/services/ocr_pipeline.py`：成績單兩條解析路徑（表格版型、無版型）的輸出都經過校正；辨識邏輯本身沒有改。
  - 新增 `tests/test_course_name_correction.py`：18 個測試，全部使用合成課名（僅為測試資料），涵蓋 10 組錯字、不該被改的例子（已是正確名、清單外的課名、多一個字、少一個字）、清單為空、以及校正後的旗標與提示文字。
- 未完成（阻塞，需要使用者提供資料）：
  - `COURSE_CATALOG` 目前是空的，所以校正還不會生效。`school/public-sources/修業科目表/` 的 PDF 只有英文課名，`im-curriculum-planning.html` 等網頁也沒有中文課名，無法從現有來源建立清單；沒有硬湊課名。
  - 因此沒有用本機 PDF 實測「74／85」能改善到多少，`app/content/ocr_acceptance.py` 與驗收紀錄沒有更新。
  - 提示放在既有的核對提示欄，沒有另外做「已校正自」的獨立標籤。
- 驗證：`D:\democase\ai\.venv` 執行完整測試 **661 passed、9 skipped**（修改前 643 passed、9 skipped，新增 18 個）。直接執行 `pytest` 會因 Windows 暫存資料夾權限出現 302 個 error，需加 `--basetemp`；這是環境問題，不是程式錯誤。
- 下一步：使用者提供本科中文課名（學校正式修業科目表的中文版，或使用者整理的名單）→ 填入 `COURSE_CATALOG` → 用本機 PDF 實測課名正確數 → 更新驗收紀錄與 `ocr_acceptance.py`。

## 2026-10-21 組員一鍵啟動：XAMPP MySQL＋虛擬環境＋資料庫＋瀏覽器

日期：2026-10-21（台灣時間）

開發者：Claude（分支視窗）

目標：組員 clone 後點桌面捷徑就能把資料庫、後端、網頁全部開起來。

- 確認來源：5013 埠目前跑的是本資料夾（`D:\democase\ai-wt-story`）的 `scripts/run_local_demo.py`（記憶體 SQLite 合成資料展示站），分支是 `feat/google-docs-autobiography`，不是交接寫的 `feat/journey-home`。一鍵啟動改走正式路線（MySQL），同樣開在 5013。
- 新增 `start_system.bat`：找 Python（`py -3` 或 `python`）→ 找 XAMPP（`XAMPP_HOME` 或 C:～G: 的 `\xampp`，找不到提示安裝）→ MySQL 沒開就啟動 `mysqld --standalone` 並等 30 秒 → 第一次建 `.venv`、裝 `requirements.txt`（之後只在 `requirements.txt` 變動時重裝）→ 從 `.env.example` 複製 `.env` → 呼叫 `scripts/start_local.py`。全部相對路徑。
- 新增 `scripts/start_local.py`：把 `.env` 中還是範例值的 `SECRET_KEY`、`DB_PASSWORD` 換成隨機值；用 root 建資料庫與帳號（帳號已存在但密碼不符時不改密碼，只提示）；空資料庫先依 Model 建表再把遷移版本標到最新並建 admin，已有遷移紀錄就執行遷移；啟動 Flask（`APP_PORT` 預設 5013，被占用時提示），可連線後開瀏覽器。
- 新增 `create_desktop_shortcut.bat`：在桌面（含 OneDrive 桌面）建立「資管科學習歷程」捷徑指向 `start_system.bat`。
- 新增 `.gitattributes`：`*.bat` 一律 CRLF，避免組員 clone 後批次檔標籤失效。
- `.env.example`：`DB_PORT` 改為 XAMPP 預設 3306，補充一鍵啟動相關說明（`MYSQL_ROOT_PASSWORD`、`APP_PORT`）。
- 新增 `docs/05_交接與專案管理/組員開啟說明.md`（安裝、第一次開啟、常見問題）；`README.md` 加上一鍵啟動入口。
- 驗證（如實記錄）：把目前版本解壓到暫存資料夾模擬組員 clone，用測試用資料庫名稱與帳號 `slp_launch_test`、埠 5015（5013 被展示站占用）實跑：
  - 第一次：建 venv 並裝好全部套件、建 `.env` 並產生隨機值、建資料庫與帳號、建表並標到最新版本 `a7c3e9d10f42`、建 admin、啟動成功；瀏覽器開首頁正常，admin 登入進到系統總覽。
  - 第二次：跳過安裝，執行遷移，自動開瀏覽器（伺服器紀錄有 `GET /` 200）。
  - MySQL 先關閉再執行：腳本自行啟動 XAMPP MariaDB 10.4.27，首頁 HTTP 200。
  - 建立桌面捷徑腳本實跑成功，捷徑指向本資料夾的 `start_system.bat`。
  - 未測：找不到 XAMPP、找不到 Python 的提示路徑（本機兩者都有）。
- 組員看到舊版首頁的原因：舊版（「五年，會留下很多東西。」、選單有「校系資料」）是 `D:\democase\ai` 的 `main`（`d889109`）用 `run.py` 開在 5000 埠，和小組 repo 的 `main`（`9ebea0b`）首頁相同；組員 clone 預設拿到 `main`。新版只在 `feat/google-docs-autobiography`。小組 `main` 是本分支的祖先，可直接快轉。
- 補強：`start_system.bat` 啟動前先 `git pull --ff-only`（失敗就略過）；說明加上新舊版首頁辨認方式與切換分支指令。用 `git clone -b feat/google-docs-autobiography` 全新 clone 小組 repo 實跑（5016 埠），首頁是「把五年，拼成下一站」、藍色資料夾與小人，選單只有「五年路徑」「登入」。
- 注意：本機 XAMPP 已有使用者自己的 `smart_learning_portfolio` 資料庫（遷移版本停在 `a1c8e4d7f902`）與 `smart_learning_app` 帳號，本次沒有動它們。測試留下的 `slp_launch_test` 資料庫與帳號未刪除。

## 2026-10-21 多視窗分工：任務 A～D

日期：2026-10-21（台灣時間）

開發者：Claude（主視窗）

目標：使用者要多開對話視窗分擔工作量，每個視窗都要寫日誌與交接。

- 新增 `docs/05_交接與專案管理/AI_分工任務_多視窗_2026-10-21.md`：共同規則（各開自己的 worktree、先寫測試、完整測試、開發日誌、交接文件、工作佇列回報、只提交自己的檔案、不推送）、四個任務的範圍與完成條件、可直接貼上的開場指令。
  - 任務 A：成績單課程名稱錯字校正（`feat/ocr-course-names`）。
  - 任務 B：OCR 背景排隊處理（`feat/ocr-background-queue`）。
  - 任務 C：手機與減少動態效果瀏覽器驗收（`feat/mobile-a11y-check`，展示站 5014 埠）。
  - 任務 D：11/4 給導師的投影片＋報告書 OCR 段落（正式報告書資料夾，不寫程式）。
- 檔案範圍刻意分開：A 改成績單解析與確認頁課程顯示，B 改上傳路由與新增工作狀態，C 只改 CSS／模板排版，D 只寫報告書資料夾；四條分支都要寫 `development-log.md` 最上面，合併時這個檔案會有容易解決的衝突。
- `D:\democase\ai\docs\AI_代理協作_工作佇列.md` 最下方已追加分派紀錄（共用檔，未提交）。
- 不分派：合併進 main、證照清單相關功能（使用者排在後 30%）。

## 2026-10-21 成績單上傳先檢查解析度；保存並用中文顯示圖片處理方式

日期：2026-10-21（台灣時間）

開發者：Claude

目標：使用者選定下一步「上傳時檢查解析度」；另外要求「保存圖片的處理方式」，讓老師看得到每張圖是怎麼處理的。

- 解析度實測（同一份 PDF 成績單縮成不同寬度，只在本機跑）：3507 像素 85 門有 84 門學分成績齊全；2800、2400 剩 60 門；2000 只有 31 門；1600 有 61 門；1400、1200 分別多出 4、6 筆假課程；1024 抓不到表格。縮小就會漏讀，2000 以下不穩定。
- 修改：
  - 新增 `app/services/upload_quality.py`：成績單圖片長邊小於 1600 像素不存檔、留在成績單上傳頁顯示「解析度太低，請改傳 PDF」（回應 400）；小於 3000 像素照常辨識，加一則「解析度偏低，可能漏讀」提醒。PDF（以 300 DPI 轉圖）與證照不檢查（1005 像素的技術士證實測全對）。`app/routes/student.py` 上傳處理接上檢查，並把結果記成一個處理步驟。
  - 保存處理方式：`app/services/ocr_pipeline.py` 每頁的紀錄多存來源（PDF／圖片）、轉圖 DPI、原始大小、試過的旋轉方向、文件類型、模型等級與 CPU／顯示卡。紀錄存在辨識結果與操作紀錄中。
  - 新增 `app/services/ocr_trace.py`：把處理步驟翻成中文句子；確認頁「查看 OCR 辨識過程」改用它（模板過濾器 `ocr_step`，註冊在 `app/__init__.py`），不再顯示 `page_ocr` 這類程式代號。舊紀錄缺少新欄位時只說明有的部分；沒翻譯的步驟照原名顯示。
  - OCR 實測結果頁與 `OCR驗收紀錄_2026-10-20.md` 加上「圖片怎麼處理」五個步驟與「解析度實測」表。
- 測試：新增 `tests/test_upload_resolution.py`（4 項）、`tests/test_ocr_trace.py`（6 項），`tests/test_ocr_acceptance_page.py` 加 1 項，都先確認失敗再實作。`tests/test_document_ocr_candidates.py` 有兩處上傳 800×200 的合成成績單圖片，會被新規則擋下；那兩項測的是辨識候選流程，改用 3200×800 的合成圖。
- 實際驗證（本機記憶體資料庫、真實 OCR，用使用者提供的測試檔）：乙級證照與 PDF 成績單的確認頁都顯示完整中文處理方式（例如「PDF 以 300 DPI 轉成圖片（3507×2481 像素）；試過 0、270、90、180 度四個方向…；找到 5 個表格…；伺服器版模型、用顯示卡」）；1024 像素的 PNG 成績單直接顯示解析度太低、沒有存檔。
- 完整測試：`650 passed, 2 skipped`。
- 推送：使用者選「跟上次一樣兩個都推」，推到個人與小組 repo 的 `feat/google-docs-autobiography`（接在 `7d2cbf1` 後面，不動 main）。

## 2026-10-20 備份到 GitHub（個人與小組 repo）

日期：2026-10-20（台灣時間）

開發者：Claude

目標：使用者要求先把目前進度推上 GitHub 備份。

- 推送目標（使用者選「兩個都推」，用完整網址，不用預設遠端）：
  - 個人：`https://github.com/LanyuLiu951127/smart-learning-portfolio-solo.git`
  - 小組：`https://github.com/LanyuLiu951127/smart-learning-portfolio.git`
- 推送分支：`feat/google-docs-autobiography`，兩邊都是新分支；沒有動任何一邊的 `main`，也沒有強制推送。
- 內容：從兩邊已有的 `feat/main-line-3`（`9ebea0b`）之後的 73 個提交，再加上本節的提交。包含組員 OCR 合併、RapidOCR 改伺服器版與顯示卡加速、管理員切換 CPU／GPU、證照與成績單辨識修正、成績單與證照分頁與分開上傳、學生動線與頂端列、首頁拼圖與資料夾、自傳 Google 文件示範版、OCR 實測結果頁。
- 推送前檢查：
  - 金鑰：新增內容沒有真的金鑰，只有測試用假值 `public-picker-key`；`.env`、資料庫檔、上傳圖片都沒有被追蹤。
  - 個資：只有證照範例假身分證號 `A123456789`，以及組員 `111534107` 的署名（組員自己的 GitHub 帳號）；OCR 測試用的真實成績單與證照圖片沒有進版本庫。
- 沒有推送：`docs/05_交接與專案管理/handoff.md` 是其他人未提交的修改，不在這次提交內。
- 完整測試（上一節）：`639 passed, 2 skipped`。
- 下一步：`feat/teammate-ocr` 仍停在 `56a74f1`，要不要合併這條分支由使用者決定；兩邊的 `main` 都還沒有這些修改。

## 2026-10-20 OCR 實測結果放進系統（/ocr/acceptance）

日期：2026-10-20（台灣時間）

開發者：Claude

目標：使用者擔心老師看到「OCR 信心幾%」卻沒有真實數據與判斷過程會起疑，要求把驗收紀錄存在系統上，而不只是文件。

- 修改：
  - 新增 `app/content/ocr_acceptance.py`：驗收內容（摘要數字、驗收方法、每張證照逐欄對錯、成績單結果、讀錯的字、信心分數的意思、下一步），只有統計與錯字類型，沒有姓名、學號、身分證號或證號。做法和「怎麼操作」說明頁相同；沒有另外安裝 Markdown 套件。
  - `app/routes/main.py` 新增 `/ocr/acceptance`（學生、老師、科辦、管理員登入後都能看），模板 `app/templates/ocr_acceptance.html`，樣式加在 `design-system.css` 最後。
  - 連結：管理員「OCR 辨識設定」頁；學生證照確認頁「OCR 信心分數不是正確率」後面加「看實測結果」。
- 測試：新增 `tests/test_ocr_acceptance_page.py`（7 項：四種角色都看得到且有關鍵數字與錯字、未登入不能看、內容不含個資、兩處連結），先確認失敗再實作。
- 瀏覽器確認：以合成老師帳號登入，頁面顯示摘要與逐欄表格，784 像素寬沒有左右捲動。
- 完整測試：`639 passed, 2 skipped`。
- 文件版的驗收紀錄仍在 `docs/03_開發紀錄/OCR驗收紀錄_2026-10-20.md`；兩邊內容要一起更新。

## 2026-10-20 技術士證：簡體標籤與被裁切的發證單位也能讀；OCR 驗收紀錄

日期：2026-10-20（台灣時間）

開發者：Claude

目標：使用者回報乙級證照的「職類（項）名稱」顯示未辨識，並請用 `D:\democase\ai\docs\OCR測試資料\` 的檔案測試、誠實驗收。

- 原因（看了整頁辨識到的文字與位置）：
  - 「職類（項）」標籤被讀成簡體「職类（项）」，`technician_regions_from_page_words` 只比對繁體，找不到標籤；職類名稱「電腦軟體應用」其實有讀到。
  - 圖片下緣把「勞動部發」切掉一半，讀成「勞动音」，發證單位也是空的；兩欄都空導致沒有產生證照紀錄。
- 修改（`app/services/credential_analysis.py`）：
  - 依標籤找欄位時，比對前先轉繁體（`traditional_text`）；去掉職類標籤時也先轉繁體。欄位仍保留原始辨識文字。
  - 發證單位多認「勞動」開頭；只讀到「勞動」加殘字時推定為「勞動部」，原因寫「發證單位只讀到「…」，推定為「勞動部」，請對照原圖確認」；其他機關（例如勞工委員會）不會被改成勞動部。
- 測試：`tests/test_technician_certificate_rapidocr.py` 新增 3 項（簡體標籤、被裁切的發證單位、其他機關不被改），先確認 2 項失敗再實作（第 3 項是保護既有行為）。
- 驗收（詳見 `docs/03_開發紀錄/OCR驗收紀錄_2026-10-20.md`，不含個資）：
  - 技術士證 4 張：修正前 24 欄對 22 欄，修正後 24 欄全對（發證單位一欄為推定、請學生核對）。
  - 成績單 PDF：85 門全部找到、學分 85／85、成績 84／85、課程名稱 74／85 完全正確（11 筆字形相近錯字）。
  - 成績單 PNG（1024×703）：解析度太低，抓不到表格，產生亂字；這次沒有修。
- 完整測試：`632 passed, 2 skipped`。
- 下一步：
  - 使用者決定證照清單、OCR 比對證照種類、「找不到證照」、導師審核排到後 30% 開發。
  - 可考慮：上傳時檢查解析度並提醒改傳 PDF；用本科課程名稱清單校正成績單錯字。

## 2026-10-20 成績單和證照分開上傳；首頁年級分頁拿掉上下捲軸

日期：2026-10-20（台灣時間）

開發者：Claude

目標：使用者指出上傳頁同時讓學生選「成績單／證照」，容易傳錯地方；首頁五年資料夾的年級分頁右邊多了一條上下捲軸。

- 捲軸原因：`.folder-tabs` 設了 `overflow-x: auto`，瀏覽器會把上下方向也變成可捲；分頁用 `translateY(6px)` 往下壓住資料夾邊框，多出的 6 像素就冒出上下捲軸。
- 修改：
  - `design-system.css`：`.folder-tabs` 加 `overflow-y: hidden`，並用下方留白 6 像素、負邊距 6 像素保留分頁壓住邊框的樣子；左右仍可捲（手機）。
  - `learning_profile_upload.html`：拿掉類型選項，改成固定的隱藏欄位，上方一行說明這頁要放什麼；真的走錯頁時，下方有「改上傳證照／改上傳成績單」小連結。沒帶類型時視為成績單。
  - 所有上傳成績或證照的連結都帶類型：首頁資料夾與拼圖（`student_home.html`、`journey_home.py`）、缺件頁（`student_gap.html`）、建議卡（`guide_service.py`）、焦點與進度（`focus_service.py`、`student_progress.py`）、確認頁「重新上傳文件」（依該文件類型）。
- 測試：`tests/test_transcript_credential_split.py` 原「上傳頁預選類型」改為「上傳頁固定一種類型、沒有選項」（需求改變），另新增沒帶類型視為成績單、所有連結帶類型、年級分頁沒有上下捲軸，先確認失敗再實作。`test_student_flow.py`、`test_student_page_consistency.py` 各有一處寫死不帶類型的網址，依新網址更新。
- 瀏覽器確認：年級分頁 `scrollHeight` 等於 `clientHeight`（79），沒有捲軸，外觀不變；`?type=credential` 上傳頁只有證照說明與檔案欄位。
- 完整測試：`629 passed, 2 skipped`。

## 2026-10-20 首頁：五年資料夾移到拼圖前面；散落的拼圖片縮小

日期：2026-10-20（台灣時間）

開發者：Claude

目標：使用者反映「打開五年資料夾」要捲很久才看得到，拼圖區太大，滑鼠要滑很久、手機也不方便。

- 原因：散落的拼圖片和圖上的洞一樣大（`components.js` 依整張圖寬度設定 `--size`，桌機每片約 284 像素），六片換行成三排，光放散落片的區塊就約 977 像素高；資料夾放在拼圖與照片之後。
- 修改：
  - `student_home.html`：「五年資料夾」移到「今天先完成哪一步」之後、拼圖之前；網頁導覽順序跟著改為資料夾 3、拼圖 4、照片 5。
  - `design-system.css`：拼圖寬度上限 40rem → 34rem；散落片改成一列六格（520 像素以下三格兩排），每片最大為洞的 45%。
  - `components.js`：按住散落片時，以按下的位置為中心放大到和洞一樣大，吸附判斷照舊；直接點（沒拖）也是先放大再吸到洞裡。
  - `journey_home.py`：成績、證照兩片改開 `?type=transcript`／`?type=credential` 的上傳頁（配合成績單與證照分兩頁）。
  - 手機頂端列：375 像素寬時「活動與經歷」「目標與備審」會折成兩行，改為字級 .82rem、不折行；項目多到放不下（有抵免進度時）可以左右滑。
- 測試：`tests/test_journey_home.py` 新增 3 項（資料夾在拼圖前、兩片連到對應類型、散落片的緊湊排列與拖曳放大），先確認失敗再實作。
- 瀏覽器確認：桌機（963 像素寬）散落片每片 95 像素一列、區塊高約 123 像素，首頁總高約 2016 像素；用滑鼠把「服務」拖到洞裡會吸附並開啟新增服務頁，模擬拖曳「成績」會放大 2.55 倍並開啟上傳成績單頁；手機（375 像素）散落片三格兩排、區塊高 182 像素，頂端導覽一排、沒有左右捲動。
- 完整測試：`626 passed, 2 skipped`。

## 2026-10-20 成績單與證照分成兩頁；學生頂端列不再折行

日期：2026-10-20（台灣時間）

開發者：Claude

目標：使用者反映頂端導覽列很亂，並希望把成績單和證照分開。

- 頂端列問題：寬度大於 900 像素時，導覽項目、網站名稱、右側說明連結都允許折行，在約 930 像素寬時「我的／五年」「成績與／證照」等都斷成兩行，整列約 91 像素高。
- 修改：
  - **成績單與證照分開**：`app/routes/student.py` 拆成 `/student/learning-profile`（成績單：只列成績單文件與課程）與新增的 `/student/learning-profile/credentials`（證照：只列證照文件與證照），共用 `_learning_profile_page()`；上傳頁依 `?type=` 預先選好類型、取消回到對應頁；確認後沒有指定回哪裡時，依文件類型回到成績單或證照頁。`learning_profile.html`、`learning_profile_upload.html`、`learning_profile_review.html` 依類型顯示標題、按鈕、麵包屑與導覽所在頁。導覽列改為「我的五年／成績單／證照／活動與經歷／目標與備審」。
  - **頂端列排版**（`design-system.css`，只影響學生頂端列）：文字一律不折行、縮小間距；1180 像素以下隱藏帳號名稱（仍有登出）；1040 像素以下網站名稱只留「IM」圖示；900 像素以下導覽改到第二排；手機上網站名稱只留圖示，讓說明連結和圖示同一排，導覽依項目數自動平分。
- 測試：新增 `tests/test_transcript_credential_split.py`（6 項），先確認失敗再實作；`tests/test_record_status.py` 原本在同一頁數三種狀態標籤，改為成績單頁＋證照頁合計（需求改變）。
- 瀏覽器確認：947 像素寬頂端列一排、高 65 像素（原 91）；1300 像素一排含帳號名稱；平板兩排不折行；手機兩排、高 143 像素、沒有左右捲動；證照頁只顯示證照，「證照」標示為目前頁面。
- 完整測試：排除另一工作階段做到一半的 `tests/test_autobiography_google_docs.py` 後，`599 passed, 6 failed`；6 項中 5 項（自傳、小助手版本）是對方同時在改自傳造成，單獨重跑已通過，另 1 項為上述 `test_record_status`，已依新需求修改並通過。
- 注意：本次與「自傳改用 Google 文件編輯」工作階段共用同一個資料夾，對方已切到 `feat/google-docs-autobiography` 分支；本次只提交自己的檔案，對方的未提交修改與 handoff.md 都沒有動。

## 2026-10-20 自傳可以在 Google 文件中編輯（示範版）

日期：2026-10-20（台灣時間）

開發者：Claude

目標：使用者與指導老師決議讓自傳可以在 Google 文件中編輯；沒有學校 Workspace，用學生個人 Google 帳號示範。依 V2 提案（D1～D6）：Google 只當編輯工具，自傳版本仍存在 MySQL；只要 `drive.file`；權杖不長期保存。分支 `feat/google-docs-autobiography`（從 `feat/teammate-ocr` 的 `bab0a53` 開出）。

- 後端 Google 授權（OAuth 授權碼流程）：新增 `app/routes/google_docs.py`（獨立 blueprint，沒有改 `student.py`）。`/student/google/connect` 產生隨機 state 後轉到 Google，只要 `https://www.googleapis.com/auth/drive.file`、`access_type=online`（不拿更新權杖）；`/student/google/callback` 核對 state（不符回 400）、拒絕授權時回自傳頁提示。權杖放在伺服器記憶體 `TokenStore`（`app/services/google_docs_service.py`），cookie 只存隨機編號，並綁定使用者 id，最多 1 小時過期；伺服器重啟就要重新授權。
- 設定：`app/config.py` 新增 `GOOGLE_OAUTH_CLIENT_SECRET`、`GOOGLE_OAUTH_REDIRECT_URI`（用戶端 ID 沿用既有 `GOOGLE_OAUTH_CLIENT_ID`），`.env.example` 補說明。三個值缺一個時，自傳頁顯示停用的「Google 尚未設定」按鈕，其他功能照常。本機展示站預設仍完全不連 Google，`scripts/run_local_demo.py --google` 才讀 `.env` 的設定。
- 在 Google 文件中編輯：自傳頁新增 Google 文件區塊。第一次按會把最新版草稿轉成純文字（每段 `## 標題 [來源 F1 F2]`），以 Drive API multipart 上傳並轉成 Google 文件，放在學生自己的 My Drive。新資料表 `autobiography_google_docs`（模型 `app/models/google_doc.py`、遷移 `a7c3e9d10f42`）記下文件 ID、連結、建立時間、對應的自傳版本與最後取回時間；同一位學生同一個校系只有一份，之後再按都開同一份。
- 從 Google 文件取回：用 Drive API 匯出純文字，依 `## 標題` 拆段，存成新的一版（`autobiography_service.save_imported`，舊版不動，`origin` 記為 `google_docs`，導師意見依段落順序沿用）。來源標記重新檢查：只接受這份草稿事實清單裡、有 `evidence_id` 的編號，其他列入 `unknown_sources`，`autobiography_review` 在該段疑點顯示「引用了不存在的來源 F9…」。找不到任何 `## 標題` 時拒絕取回，系統內版本不變。送導師確認照舊用系統內的版本快照。
- 錯誤處理：Google 逾時、5xx、格式不對 → 回自傳頁顯示「Google 暫時無法使用，請先在系統內編輯」；401／403 → 丟掉權杖並提示重新連結。學生隨時可以在系統內編輯與儲存，不卡主線。
- 測試（先寫失敗測試再實作）：新增 `tests/test_autobiography_google_docs.py`（18 項），Google 全部用測試替身或替換 `urlopen`，不連網；涵蓋未設定、只要 drive.file、state 不符、權杖不在 cookie、未授權先轉登入、建立、重開同一份、取回存新版本與標記不存在來源、沒有標題時拒絕、別的學生 403、權杖只屬於授權的那個工作階段、Google 失敗回系統內編輯、授權過期、拒絕授權、文字格式往返、遷移升降級、HTTP 用戶端錯誤對應與文件 ID 檢查、展示站預設不開 Google。`tests/conftest.py` 新增自動擋掉 `.env` 真實 Google 設定。
- 文件：新增 `docs/03_開發紀錄/01_參考與環境設定/Google文件自傳編輯_設定步驟.md`（建立專案、啟用 Drive API、OAuth 同意畫面測試模式加測試使用者、建立網頁用戶端與 localhost 重新導向網址、示範後移除權限）。
- 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/gdocs-full2` → `623 passed, 2 skipped in 254.38s`（含另一方同時提交的 `56a74f1` 成績單與證照分頁；第一次跑時它還在修改中，`test_record_status` 失敗 1 項，提交後重跑通過）。
- 沒做到：沒有用真的 Google 帳號實測（需要使用者先完成 Google Cloud 設定）；也沒有開瀏覽器預覽（共用的 `.claude/launch.json` 修改被權限擋下，頁面行為由測試確認）。

## 2026-10-20 學生主線動線改善五項

日期：2026-10-20（台灣時間）

開發者：Claude

目標：使用者覺得系統動線「用起來卡卡的」。實際走過學生主線後找到卡點，依使用者指示先改五項。

- 走查發現：做完事一律回到列表，要自己找路回校系頁；上傳後要再點一次才進確認頁；首頁「今天先完成哪一步」排在約 1,600 像素高的拼圖後面（約 2,150 像素處）；導覽列「目標校系」「備審資料」在沒選校系時連到同一頁、「抵免進度」所有學生都看得到；上傳辨識 5～10 秒畫面沒有反應。
- 修改：
  1. **做完回原處並顯示更新**：新增 `app/services/flow.py`（`safe_next` 只接受站內路徑、`target_program`、`readiness`、`flash_done`）。上傳、確認、新增經歷都帶 `next`；校系備審頁的「去新增」記住出發頁；回到校系頁時顯示「已儲存 N 門課程。準備度 A% → B%」或「已新增「…」。準備度 A% → B%」。`app/templates/base.html` 新增完成訊息列（樣式在 `design-system.css`）。
  2. **上傳後直接進確認頁**：`learning_profile_document_upload` 改為導向該文件的確認頁。
  3. **首頁下一步移到上方**：`student_home.html` 把「今天先完成哪一步」移到路線圖下、拼圖前（約 559 像素處）。
  4. **導覽列合併與抵免只給轉學生**：「目標校系」「備審資料」合併為「目標與備審」（選了校系進第一個校系的備審頁，沒選就到選校系頁）；「抵免進度」只在已建立抵免紀錄時出現，其他學生在首頁「今天先完成哪一步」下方有「轉學生？填寫抵免進度」小連結。目前資料模型沒有「學生類型」欄位（組員的個人資料頁未搬），所以先以抵免紀錄判斷。
  5. **上傳時顯示辨識中**：上傳按鈕與「重新分析來源檔」加 `data-busy-text`，送出後顯示「辨識中，約 10 秒…」。
- 測試：新增 `tests/test_student_flow.py`（9 項，含外部網址、`//` 開頭、反斜線等不安全跳轉會被忽略），先確認失敗再實作；過程中修正自己測試對網址編碼的錯誤要求（`?next=/student/targets/1` 本來就合法）。
- 瀏覽器確認：首頁導覽列四項、「今天先完成哪一步」在第一個畫面底部；從校系頁「去新增」活動經歷，存檔後回到校系頁並顯示「已新增「合成測試：資訊週志工」。準備度 0% → 7%」。
- 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/flow-full` → `599 passed, 2 skipped in 281.05s`。
- 下一步：使用者與老師決議改用 Google 文件編輯自傳（以個人帳號示範），另行規劃。

## 2026-10-19 整理成績單確認頁版面（課程改成卡片、提示改成標籤、手機版）

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者反映確認頁「很亂很醜」。截圖檢查找到的問題：最右側「核對提示與來源」欄太窄，每個提示被擠成一字一行，一列課程高達約 400 像素；幾乎每列都塗滿黃色底；每格「OCR 信心：未知，請核對」太長、折行；學分與成績欄跟課名一樣寬。

- 修改 `app/templates/learning_profile_review.html`（只改外觀，不改表格列結構、輸入欄名稱與組員腳本依賴的標記）：
  - 每門課改成橫向卡片：上排課名（寬）、學分、成績（窄、數字置中）、學期、年級；下排是提示標籤（不及格紅、已重補修綠、暑寒修藍、需要確認黃），來源與「查看原圖區域」同一行。一列約 110～150 像素。
  - 需要核對的課改成左側細橘線，不再整列塗黃。
  - 信心分數縮短為「信心 87%」「信心 76%・偏低」「信心未知」，完整說明放在滑鼠提示中。
  - 「學期依表格位置推定，請核對表頭。」是整份成績單共通的提醒（組員的設計也已不讓它觸發待核對），改成在課程清單上方說一次；每列只顯示該課自己的問題，沒有自己的問題就不顯示「需要人工確認」。
  - 手機（720px 以下）：課名一行、學分＋成績一行、學期＋年級一行，每格上方顯示欄名；篩選列在手機上不固定在頂端。
  - 「確認並儲存」「重新分析來源檔」改用網站的按鈕樣式。
- 驗證：瀏覽器桌機與 375px 手機寬度實際檢查（真實成績單，經展示站上傳），手機沒有橫向捲動，「第二學期」「3年級」完整顯示；不及格的 JAVA 程式語言同一行顯示「不及格／待確認」與「已重補修：3年級 暑修 85 分（及格）」。
- 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/ui-full` → `590 passed, 2 skipped in 257.34s`；組員 JavaScript 測試 5/5。

## 2026-10-19 不及格課程自動標示「已重補修」與重補修時間

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者建議在確認頁的不及格課程旁標示是否已重補修過、在哪一年級哪一學期（或暑修、寒修）。

- 修改：
  - `app/services/course_review_presentation.py`：`prepare_course_review_rows()` 最後呼叫新增的 `_link_retakes()`。不及格（分數低於 60）的課程，配對**之後**出現、同名（去空白、轉繁體）且及格的那一筆；修課先後依「年級 → 第一學期 → 寒修 → 第二學期 → 暑修」排序，所以之前及格的同名課（例如上學期的另一部分）不會被當成重修；重修又不及格的不算，改找下一次及格。不及格那列加 `retake`，重補修那列加 `retake_of`，只做顯示，不改原始資料。
  - `app/templates/learning_profile_review.html`：不及格列提示「✓ 已重補修：3年級 暑修 85 分（及格）」，重補修列提示「重補修：補 3年級第二學期 58 分」。
  - 新增 `tests/test_course_retake_link.py`（6 項：暑修、之前及格不算、之後學期重修、寒修排在上下學期之間、重修又不及格改找下一次、確認頁顯示）。先確認失敗再實作。
- 實測（使用者提供的成績單，經展示站上傳）：唯一不及格的「JAVA程式語言 58 分（三年級第二學期）」標示「已重補修：3年級 暑修 85 分（及格）」，暑修那列標示「補 3年級第二學期 58 分」；同年級第一學期 91 分的同名課沒有被誤認。
- 限制：配對依課名，課名辨識錯字（例如「會計學」讀成「合计學」）時會配不到，學生修正課名並儲存後重新開啟即可；提示放在最右側「核對提示與來源」欄，欄寬較窄，文字會換行。
- 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/retake-full2` → `590 passed, 2 skipped in 269.47s`。

## 2026-10-19 證照確認頁每個欄位直接顯示原圖預覽；修正展示站同時請求誤判未登入

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者指出證照確認頁的「第 1 頁・原圖位置 1355.0, 1026.0, …」看不懂，要求換成直接顯示該欄位在原圖中的預覽圖片。

- 修改：
  - `app/routes/student.py`：把組員「課程原圖裁切」中讀原圖、裁切、回傳 PNG 的部分抽成共用 `_source_crop_response()`（可加四周留白）；新增證照欄位預覽網址 `/student/learning-profile/documents/<id>/credentials/<分析序號>/fields/<欄位>/source`，同樣檢查擁有者與草稿版本，欄位不存在或位置不完整回 404。
  - `app/templates/learning_profile_review.html`：座標文字換成預覽圖（`credential-field-preview`，有替代文字「原圖中「級別」的位置」，捲到才載入）。
  - 新增 `tests/test_credential_field_preview.py`（4 項：確認頁顯示預覽圖且不再有座標、回傳正確裁切、別的學生看不到、不存在的欄位 404）。先確認失敗再實作；組員的課程原圖測試照常通過。
- 實作時發現並修正：展示站確認頁同時載入 6 張預覽圖時，有 1～2 張隨機失敗。伺服器紀錄顯示是已登入卻被回 401。原因是展示站資料庫在記憶體、所有執行緒共用同一條連線，加上先前把展示站改成多執行緒，同時處理請求時查詢互相干擾；用腳本同時送 36 個請求重現：32 正常、3 個誤回 404、1 個誤回 401。`app/demo.py` 新增 `SerializedWSGI`，讓展示站一次處理一個請求（仍可同時接受連線，不會回到單執行緒卡住的問題）；`tests/test_local_demo.py` 新增 2 項。修正後 36 個同時請求全部正常。正式環境用 MySQL 連線池，沒有這個問題。
- 瀏覽器確認：上傳會計事務證照後，6 個欄位的預覽圖全部顯示（例如「級別」下方是原圖的「丙級」、「技術士證總編號」下方是「149-0685006」）。
- 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/preview3-full` → `584 passed, 2 skipped in 232.08s`。

## 2026-10-19 技術士證改成「整張辨識＋依標籤找欄位」，修正證照讀不到

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者上傳技術士證圖片（會計事務－資訊、電腦軟體應用、電腦硬體裝修，皆為範例資料：身分證號 A123456789、姓名與照片已替換），確認頁顯示「證照類型未辨識」、沒有任何欄位。

- 原因（已驗證）：
  1. 組員流程用**固定比例**切證照欄位（`TECHNICIAN_REGIONS`），使用者圖片的邊界與比例不同，每一區都錯開：證號區切到出生日期、職類區切到證號、日期區只剩零碎字。
  2. 標題被讀成「中華民」「術士證」「國技」三塊，組員的判斷**照辨識順序**接成「中華民術士證國技」，找不到「技術士證」；兩張圖的「國技」被紅色印章蓋住。
  3. 最後的整頁重讀會把整張圖放大 2 倍再辨識，RapidOCR 反而讀爛（顯示卡模式甚至直接失敗）。
  - 對照：同一張圖**整張直接辨識**，每個欄位都讀得到。
- 修改：
  - `app/services/credential_analysis.py`：新增 `technician_regions_from_page_words()`，用整張辨識結果依「標籤＋同一列」找欄位——總編號看「3 碼-7 碼」格式、職類看「職類（項）」右側（或與標籤黏在一起的那段）、級別看「甲乙丙丁級」、生效日期與製發日期各取**同一列右側**的日期（不會誤抓出生日期）、發證單位看「勞動部」；標題被印章蓋住時以左側「技術士證總編號」標籤佐證。`analyze_technician_regions()` 組合文字前先依位置排成閱讀順序，標題也接受簡體「技术」。發證單位「勞動部發」去掉結尾的「發」（先查組員的人工錯讀對照表，例如「勞助部發」，查不到才去掉）。
  - `app/services/ocr_pipeline.py`：引擎為 RapidOCR 時，證照改用整張辨識（不放大）＋上述分欄；Tesseract、PaddleOCR 維持組員原本的固定比例流程。
  - 新增 `tests/synthetic_certificate.py`（合成技術士證，刻意放在邊界、比例不同的畫布上）與 `tests/test_technician_certificate_rapidocr.py`（6 項：標題順序亂、標籤分開、標籤黏在一起、標題被蓋住、發證單位、真實模型讀合成證照）。先確認失敗再修正；過程中曾讓組員 3 項發證單位測試失敗（對照表的鍵含「發」），已改成先查表再處理。
- 實測三張上傳的證照（顯示卡）：每張 0.5 秒，職類、級別、總編號、生效日期、製發日期全部正確，發證單位「勞動部」。經網站上傳後確認頁自動帶入證照名稱、等級、發證單位、製發日期。仍會出現的「請核對」提示是組員的保守規則（標題被印章蓋住、信心低於 85%），不是讀錯。
- 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/cert-full` → `578 passed, 2 skipped in 306.87s`。

## 2026-10-19 首頁拿掉寫死的「校系資料」加權表

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者指出公開首頁的「校系資料」區塊（115 學年度簡章範例的備審加權表）是寫死在前端的，明年簡章一換就又要改程式，要求拿掉。

- 拿掉：`app/templates/index.html` 的 `#agent` 區塊、`app/templates/partials/nav.html` 未登入導覽列的「校系資料」連結、`app/routes/main.py` 首頁不再讀範例校系資料、`app/static/css/design-system.css` 只給這個區塊用的樣式（`agent-board`、`agent-steps`、`program-table`、`weight-bar`、`weight-names`、`public-agent`）。清樣式時曾誤刪一行同時含 `.tickets` 的規則，已補回（首頁仍在用）。
- 保留：系統管理員的「校系資料」管理頁、學生的「目標校系」與其他使用 `load_sample_programs()` 的地方；這些資料存在資料庫，簡章更新時由管理員維護，不用改程式。
- 測試：`tests/test_ui_shell.py` 原本檢查首頁要有 `#agent`，改為新增測試檢查首頁**不再**出現校系區塊、連結、「備審加權」與「簡章範例」；先確認失敗再修改。
- 瀏覽器確認：首頁導覽只剩「五年路徑」「登入」，最後一段「五年，組成一份能出發的資料包」直接接頁尾；伺服器無錯誤。
- 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/home-full` → `572 passed, 2 skipped in 264.98s`。

## 2026-10-19 修正空白格被讀成數字（多出不及格假課程）

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者在確認頁發現「康寧全人教育」多出一筆第二學期、成績「1」（信心 27%）的不及格課程，原件該課只有第一學期 2 學分 86 分，第二學期兩格是空白。

- 原因（已驗證）：第一列緊貼表頭底線，掃描後的淡灰殘影落在第二學期兩格（11、31 個墨水點），超過「空格」門檻 8 點而被送去辨識，模型硬讀出「1」，於是多出一筆假課程。
- 修正：`app/services/ocr_pipeline.py` 的逐格辨識加一道檢查——格子裡的墨水上下要跨過該列文字高度的 40%（至少 6 像素）才當成有字；框線殘影、污點只有 1～3 像素高，真正的字（連「1」）都會跨過。
- 測試：`tests/test_transcript_layout_rapidocr.py` 新增 1 項（合成成績單空白格畫 2 像素高殘影，並讓辨識器一律回答「1」，殘影格不可產生數字）。先確認失敗（多讀 1 筆）再修正。
- 真實成績單重新比對（伺服器版）：多出的列 2 → 1，剩下那筆經查是「會計學」課名被讀成「合计學」（學分 3、成績 75 正確），不是假課程；**假課程 0 筆**，唯一的不及格是 JAVA 程式語言 58 分，與原件一致。學分 84/84、成績 82 筆正確，與修正前相同（沒有誤刪）。跳過殘影格後也更快：顯示卡 4.8 秒、CPU 21.7 秒。
- 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/remnant-full` → `571 passed, 2 skipped in 217.92s`；組員 JavaScript 測試 5/5。
- 提醒：修正前已上傳的文件，辨識結果不會自動更新，要在列表按「重新辨識」。

## 2026-10-19 系統管理員可在網站切換 OCR 用 CPU 或顯示卡

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者要求在系統管理員那裡增加切換，選擇 OCR 要用 CPU 還是顯示卡辨識，並重開系統讓使用者測試。

- 修改檔案：
  - 新增資料表 `system_settings`（鍵／值、修改者、修改時間）：`app/models/system_setting.py`、遷移 `migrations/versions/f3a8c2d61b07_add_system_settings.py`（接在 `e4d7a9c1b602` 之後）。**尚未在 MySQL 執行**，上線前要先備份再升級。
  - 新增 `app/services/ocr_settings.py`：讀取時資料庫設定優先，沒有就用設定檔 `OCR_DEVICE`／`OCR_DML_DEVICE_ID`；OCR 每一格都會讀設定，所以快取 10 秒，管理員儲存時清除本程序快取（其他程序最慢 10 秒後跟上）；資料表不存在（例如離線腳本）時沿用設定檔，不讓 OCR 失敗。寫入時檢查：只接受 CPU／顯示卡、編號 0～15，**這台電腦沒裝顯示卡加速套件時不能切到顯示卡**（避免「看起來開了 GPU、其實悄悄用 CPU」）；每次切換寫入稽核紀錄 `system.ocr_device_changed`。
  - `app/services/ocr_engines.py`：`configured_rapidocr_settings()` 改讀上述設定，切換後不用重開網站。
  - `app/routes/admin.py`、新增 `app/templates/admin_ocr.html`、`app/templates/partials/nav.html`：管理員新頁面「OCR 辨識設定」（`/admin/ocr`），顯示目前裝置、這台電腦能否使用顯示卡加速、切換與顯示卡編號；只有管理員能看與修改。
  - 新增 `tests/test_admin_ocr_device.py`（8 項，先寫失敗測試再實作）。
- 限制：舊的簡易提供者 `offline_ocr` 在網站啟動時就建立引擎，不受這個切換影響；建議使用的 `rapidocr`（組員流程＋RapidOCR）會即時生效。
- 驗證：
  - 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/admin-ocr-full` → `570 passed, 2 skipped in 283.54s`；組員 JavaScript 測試 5/5。
  - 瀏覽器實測（本機展示站）：管理員登入 → 導覽列「OCR 辨識設定」→ 切到 CPU（頁面顯示「目前使用：CPU」）→ 學生上傳合成成績單 9.8 秒、8.8 秒 → 不重開網站切回顯示卡 → 4.1 秒（含載入顯示卡模型）、2.0 秒；四次都辨識到 19 門課，結果相同；伺服器無錯誤。測試時我的上傳小工具曾把 PNG 誤標成 PDF（兩筆辨識失敗），是工具錯誤，修正後重測。
- 下一步：OCR 背景排隊處理；MySQL 實機驗收時一併執行本次遷移。

## 2026-10-19 OCR 改用顯示卡加速（DirectML，RTX 4060），可切回 CPU

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者問「為什麼都用 CPU、沒用 GPU」，並指示改裝 `onnxruntime-directml` 讓 RapidOCR 用 RTX 4060，保留可切回 CPU 的設定，裝完比較速度。

- 安裝：卸除 `onnxruntime`（CPU 版 1.31.0），從 PyPI 安裝 `onnxruntime-directml==1.24.4`（Microsoft 官方，含 CPU 執行）。兩者都提供 `onnxruntime` 模組，不能同時安裝。第一次安裝卡在下載，停掉後加上逾時設定重試成功。現在可用 `DmlExecutionProvider`、`CPUExecutionProvider`。切回方法寫在新增的 `requirements-directml.txt`；`requirements.txt` 仍維持 CPU 版，讓沒有顯示卡的電腦或伺服器照常安裝。
- 發現兩件事：
  1. `rapidocr` 3.10 把顯示卡設定以 OmegaConf 物件交給 onnxruntime，被拒絕後會**悄悄退回 CPU**（時間跟 CPU 一樣、顯示卡記憶體沒變）。已在本專案包一層轉成一般 dict（`_patch_rapidocr_directml_options`）。
  2. 筆電有兩張顯示卡：DirectML 編號 0 是 AMD 內建顯示（只快約 2 倍），編號 1 才是 RTX 4060（`nvidia-smi` 顯示使用率 100%、記憶體 665→5388 MiB）。所以要能指定編號。
- 修改檔案：`app/services/document_analysis_service.py`（`RapidOcrEngine` 新增 `device`、`dml_device_id` 與 `build_params()`）、`app/services/ocr_engines.py`（模型依「等級、裝置、編號」分別快取，新增 `configured_rapidocr_settings()`）、`app/config.py`（`OCR_DEVICE` 預設 `cpu`、`OCR_DML_DEVICE_ID` 預設 0）、`app/__init__.py`、`.env.example`、`scripts/run_local_demo.py`（新增 `--gpu 編號`）、新增 `requirements-directml.txt`、`tests/test_rapidocr_device.py`（6 項，先寫失敗測試再實作）。工作區 `D:\democase\.claude\launch.json` 新增「local-demo-ocr-gpu」（不在版本控制內）。
- **實測（使用者提供的成績單，85 筆，同一套 DirectML 套件內切換）**：

  | 組合 | 第一次（含載入） | 網站已在跑時 | 準確度 |
  | --- | --- | --- | --- |
  | 伺服器版＋CPU | 33.5 秒 | 31.6 秒 | 學分 84/84、成績 82 對 0 錯、年級 84/84 |
  | **伺服器版＋RTX 4060** | **9.4 秒** | **5.9 秒** | **與 CPU 完全相同** |
  | 輕量版＋CPU | 9.2 秒 | 8.5 秒 | 成績讀錯 3 筆、年級 58 |
  | 輕量版＋RTX 4060 | 8.4 秒 | 6.3 秒 | 與輕量版 CPU 相同 |

  伺服器版用 RTX 4060 比 CPU 快約 5.4 倍，結果一字不差；也比輕量版＋CPU 更快更準。經本機展示站實際上傳：9.7 秒完成（含第一次載入模型），顯示卡記憶體 665→3352 MiB，確認有用到 RTX 4060。今天同一份成績單從 467.5 秒（調整前）→ 46.7 秒（逐格辨識）→ 5.9 秒（顯示卡）。
- 注意：顯示卡模式會佔用約 3～5 GB 顯示卡記憶體；正式多人使用時，每個網站服務程序各載一份模型，要依伺服器顯示卡記憶體決定程序數，或改成背景排隊處理。學校伺服器若沒有顯示卡，維持 `OCR_DEVICE=cpu` 即可。
- 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/device-full` → `562 passed, 2 skipped in 267.32s`；組員 JavaScript 測試 5/5。
- 下一步：OCR 背景排隊處理；與組員分享版型調整與顯示卡設定。

## 2026-10-19 依學校成績單版型調整 RapidOCR：修正漏讀、年級失敗，速度 467 秒降到 47 秒

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者指示用上一節的真實成績單版面調整 RapidOCR——先驗證漏讀與年級失敗的原因，再改裁切放大與表頭判斷，比較伺服器版與輕量版，先寫測試。真實成績單只在本機分析，答案表與診斷資料放在對話暫存區，不進專案；本日誌不含個資。

- **驗證到的原因**：
  1. 年級全部失敗：RapidOCR 把表頭「第 1 學年」讀成簡體「第2学年」或形近字「第1举年」，組員的年級規則只認「學年」。
  2. 學分／成績整欄漏讀：窄小的數字欄用文字框偵測時，兩位數成績被拆成兩個框（93 → 「9」「3」）、重複框（87 → 「87」「8」），甚至漏掉一位數（70 → 「0」，會變成**錯誤數值**）；伺服器版模型在又高又窄的欄位裁切上甚至偵測不到任何文字。
  3. 改用逐格辨識後發現：掃描檔的左框線落在偵測到的欄線右側幾個像素，把前六列連成一大塊，造成數值錯位。
  4. 速度：舊方法逐欄、逐區塊重複偵測與放大，每次都跑伺服器版模型。
- **修改**：
  - `app/services/ocr_pipeline.py`：`grade_from_header()` 在「第N_年」固定格式中接受「學／学／举」；RapidOCR 改為**逐列、逐格只做文字辨識**——以墨水投影找出每一列（`_text_row_bands`），先移除直線框線（`_ink_without_rules`，含偏移、較粗的線），空格不辨識，只有標點（掃描污點讀成「.」「−」）的不算文字；輸出格式與原本相同，組員的解析邏輯不變。其他引擎（Tesseract、PaddleOCR）維持原流程。
  - `app/services/ocr_engines.py`：新增 `recognize_rapidocr_line()`（只辨識、不偵測）；一般辨識改為明確開啟偵測（rapidocr 會記住上一次呼叫的設定）。
  - 新增 `tests/synthetic_transcript.py`（產生學校成績單版型的合成圖片，全部假資料）與 `tests/test_transcript_layout_rapidocr.py`（9 項：年級表頭簡體／形近字、不亂猜、合成成績單伺服器版與輕量版逐格全對、偏移粗框線不把列連在一起、污點不算文字）。先寫測試、確認失敗，再修正。
- **真實成績單比對（共 85 筆，人工答案）**：

  | 項目 | 修改前（伺服器版） | 修改後伺服器版 | 修改後輕量版 |
  | --- | --- | --- | --- |
  | 時間 | 467.5 秒 | **46.7 秒** | 12.1 秒 |
  | 對到的課程 | 86（含錯位） | 84 | 81 |
  | 學分正確 | 約 43 | **84（讀錯 0）** | 80（讀錯 0） |
  | 成績正確 | 58 | **82** | 78 |
  | 成績讀錯 | 0 | **0**（比對程式報 1 筆，經查是答案表同課名同學期重複造成的誤判） | **3** |
  | 年級正確 | 0 | **84** | 58 |
  | 課名完全正確 | 64 | 69 | 48 |

  結論：伺服器版在每一項都較好且沒有讀錯數字，維持為預設；輕量版較快但有 3 筆成績讀錯，不建議用於成績單。剩下的問題：1 筆成績讀成「G5」（被數字檢查擋下，留空給學生補）、部分課名有形近字（例如 會計學→合计學），學生確認時要修正。
- 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/layout-full` → `556 passed, 2 skipped in 369.27s`；組員 JavaScript 測試 5/5。
- 使用者提問「為什麼都用 CPU、沒有用 GPU」：本機有 NVIDIA GeForce RTX 4060 Laptop GPU，但目前安裝的 `onnxruntime` 是 CPU 版，只提供 `CPUExecutionProvider`。這次的加速（467 → 47 秒）來自辨識方法的改變，不是 GPU。若要用 GPU，需改裝 `onnxruntime-directml`（約 20 MB，經 DirectX 使用顯示卡）或 `onnxruntime-gpu`（CUDA，需另外約 2～3 GB 的執行檔），兩者都會取代目前的 `onnxruntime`，待使用者決定。
- 下一步：使用者決定是否改用 GPU；與組員分享版型調整結果；OCR 背景排隊處理。

## 2026-10-19 用真實格式成績單示範測試 OCR（組員流程＋RapidOCR 伺服器版）

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者提供一份學校正式格式的「學生歷年成績單」PDF（1～3 年級，1 頁），指示拿來做示範測試。這是使用者本人提供的真實成績單，本日誌**不記錄姓名、學號等個資**，只記錄辨識統計。

- 方式：本機展示站（真實 RapidOCR 模式）的正常上傳流程；辨識全程在本機，未送任何外部服務。答案以人工看原件逐列核對。
- 結果（共約 86 門課）：

  | 項目 | 結果 |
  | --- | --- |
  | 課程列 | 86/86 找到，另多 1 列雜訊 |
  | 分數 | 58/86 有填出，**填出的全部正確**；28 筆漏讀 |
  | 學分 | 約 43/86 有填出（抽查皆正確） |
  | 課名完全正確 | 64/86；其餘為形近字錯誤（如 資訊→查訊、會計學→會計畢、經濟學→經滑學） |
  | 年級 | 0/86（全部「年級待確認」） |
  | 不及格標記 | 58 分課程正確標為不及格 |
  | 速度 | 1 頁 467.5 秒（約 7.8 分鐘） |

- 觀察：漏讀集中在整欄（例如二年級第二學期分數、三年級第一學期分數、多數第一學期學分），不是零星錯字。
- 推測原因（**尚未驗證**）：組員流程對「整行辨識引擎」的數字欄位用原尺寸裁切（原為 PaddleOCR 設計），本次把 RapidOCR 歸入同一類，小字數字可能需要放大；年級由各學年表頭判斷，這一步在 RapidOCR 下沒有成功；速度慢是因為逐欄、逐區塊分別辨識，每次都跑伺服器版模型。
- 本次沒有改程式；這份成績單的辨識結果停在「草稿」未確認（展示站資料庫在記憶體中，停止服務即消失）。上傳的檔案複本存在 `instance/uploads/learning-profile/1/`（不進 Git）。
- 下一步（待使用者決定）：以這份版面調整 RapidOCR 的裁切放大與表頭判斷、比較伺服器版與輕量版的速度與準確度，並把辨識改成背景處理以免使用者等 8 分鐘。

## 2026-10-19 修正年級讀不到：列表與「我的五年」讀取組員確認頁的年級

日期：2026-10-19（台灣時間）

開發者：Claude

目標：瀏覽器實測發現，組員確認頁把學生填的年級存在新欄位 `grade_level`（例如「三年級」），但本分支的列表、「我的五年」、自傳證據、Word 匯出只讀舊欄位 `school_year`，所以列表顯示「—」、課程沒有放進對應年級。依使用者指示先寫測試再修正。

- 修改檔案：
  - `app/models/learning_profile.py`：新增 `grade_number()`（「三年級」「3年級」→ 3，看不懂回傳 None）與課程屬性 `year_for_placement`（先用 `school_year`，沒有才用 `grade_level`；不會自己補寫 `school_year`）。
  - `app/services/journey_service.py`（「我的五年」放置）、`app/services/autobiography_service.py`（自傳證據文字）改用 `year_for_placement`。
  - `app/templates/learning_profile.html`（列表）、`app/services/package_service.py`（Word 匯出）沒有 `school_year` 時顯示年級文字。
  - `app/routes/student.py`：確認時的「不能填比現在高的年級」檢查，原本只看 `school_year`，組員確認頁只填年級時會漏檢；改為沒有 `school_year` 時用 `grade_level` 檢查。
- 新增 `tests/test_course_grade_level.py`（5 項）：年級文字換算、`school_year` 優先、「我的五年」放進專三、列表顯示「三年級」、一年級學生填「五年級」會被擋（400，且不寫入）。先執行為 4 項失敗＋1 項（年級檢查）失敗，修正後全部通過。
- 同日一併記錄（上一輪讓使用者測試時的修改）：`scripts/run_local_demo.py` 新增 `--ocr` 選項改用真實 RapidOCR（預設仍是模擬 OCR）；改成多執行緒（單執行緒時瀏覽器保留的連線會讓整站卡住）。工作區 `D:\democase\.claude\launch.json` 新增「local-demo-ocr」啟動項目（原有兩個項目未動，此檔不在本專案版本控制內）。
- 驗證：
  - 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/grade-full` → `547 passed, 2 skipped in 225.35s`；組員 JavaScript 測試 5/5。
  - 瀏覽器實測（本機展示站、真實 RapidOCR、合成成績單）：確認頁填「三年級」「四年級」→ 列表顯示三年級／四年級；「我的五年」專三有模擬資料結構、專四有模擬網頁設計；伺服器無錯誤。
- 實測時另外觀察到（尚未處理，屬組員介面設計）：確認頁的鎖定按鈕是三段切換——預設只鎖分數，按第一下變成「全部鎖定」，按第二下才全部解鎖；學生想改分數要按兩下，第一下效果相反，容易誤會。
- 下一步：與組員討論鎖定按鈕的操作方式；用真實格式的合成成績單測組員的版面解析。

## 2026-10-19 合併組員的 OCR 部分，並接上本機 RapidOCR

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者指定「只把組員的 OCR 部分拉出來合併到我的系統」；使用者已確認組員 repo（https://github.com/111534107/smart-learning-portfolio.git）的提交 `3301a9b` 全部是組員 111534107 做的。以組員 OCR 流程為主，把本分支的 RapidOCR 接成其中一個引擎。

- 分支：從 `feat/journey-home`（先提交伺服器版變更 `19a1c6b`）開新分支 `feat/teammate-ocr`；沒有合併到 `main`、沒有推送。
- 合併方式：組員提交與本分支的共同祖先是 `056382f`。新檔直接從 `3301a9b` 取出；共用檔用三方合併（我們／共同祖先／組員），衝突逐處判斷。
- **搬入（OCR）**：`ocr_engines.py`、`ocr_pipeline.py`、`credential_analysis.py`（技術士證判讀）、`course_review_presentation.py`、組員版 `document_analysis_service.py`（成績單版面解析、圖片校正、去表格線）、PDF 辨識（最多 10 頁）、簡轉繁、重新辨識、原圖下載與單課原圖裁切、組員的確認頁（分數鎖定、信心值、年級／學期分組、重補修標記）、課程紀錄新增 `grade_level`、`makeup_season` 兩個欄位與遷移、OCR 文件（`docs/ocr-setup.md`、`03_開發紀錄/ocr-development-log.md`、OCR 可靠度計畫）、速度測試腳本、7 個 OCR 測試檔與 1 個 JavaScript 測試。
- **沒搬（非 OCR 或需決策）**：學生個人資料頁與 `user.py` 新欄位及其遷移、首頁五年級判斷、`audit_log` 主鍵型別、作品集與個人資料頁、`.codex` 掛鉤、組員的學習歷程頁改版（保留本分支頁面，只加上「重新辨識」按鈕）；**刪除上傳文件、清空已確認資料兩個功能**依規格 M10（刪除與保留政策待學校決定）暫不搬；`requirements-ocr.txt`、`start-ocr.ps1`（PaddleOCR 需 Python 3.12）不搬。
- **接上 RapidOCR**：`ocr_engines.recognize()` 新增 `rapidocr` 引擎，回傳與組員相同的文字框格式；新增提供者 `DOCUMENT_ANALYSIS_PROVIDER=rapidocr`（組員流程＋RapidOCR，建議使用）；RapidOCR 與 PaddleOCR 同屬整行辨識，流程中原本只給 PaddleOCR 的處理改用 `LINE_LEVEL_ENGINES` 一併套用；模型等級跟隨 `OCR_MODEL_TIER`。Tesseract 不安裝：組員的數字與等級補辨識在沒有 Tesseract 時回傳空結果，已實測不會中斷。
- 衝突處理重點：`student.py` 9 處（課程確認合併組員的嚴格檢查與本分支的年級規則檢查；證照日期採組員版；作品集兩處保留本分支）、確認頁採「本分支外框與原始文件預覽＋組員的確認介面」，辨識失敗時另外顯示本分支的表格手動輸入（M12），避免只剩組員的 JSON 手動輸入；兩個遷移改接在本分支最新遷移 `a920261013tc` 之後，維持單一遷移鏈。
- 合併時修正：組員的上傳稽核紀錄遇到 `courses: None` 會出錯（本分支 demo／offline_ocr 提供者用 None），改為 `or []`；本分支原有錯誤：上傳檔預覽在相對路徑 `UPLOAD_FOLDER` 下 500（`send_file` 以 `app/` 為基準），改用絕對路徑並補測試。
- 測試調整（如實記錄）：本分支 3 個測試檔改為新的確認流程規則（確認時要送回 `draft_revision`；修改 OCR 分數需先解鎖）；組員 1 個遷移測試的 stamp 版本改為新接點；2 個組員測試標為略過並寫明原因（頁面改版未搬、刪除功能待 M10）。
- 新增 `tests/test_rapidocr_pipeline.py`（4 項，先寫失敗測試再實作）。
- 套件：從 PyPI 安裝 `pytesseract==0.3.13`、`opencc-python-reimplemented==0.1.7`、`pypdfium2==4.30.0`，寫入 `requirements.txt`。
- 驗證：
  - 組員流程＋RapidOCR 實跑合成成績單：3 門課（課名、學分、分數）全部正確，5.6 秒。
  - 組員的 JavaScript 測試 `node --test tests/test_review_grade_filter.cjs`：5/5 通過。
  - 瀏覽器實測本機展示站（5013）：上傳合成圖片 → 確認頁（原圖預覽、組員確認介面）→ 確認並儲存 → 課程出現在「成績與學分」且狀態為已確認；修正後伺服器無錯誤。
  - 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/merge-final` → `542 passed, 2 skipped in 227.04s`（2 項略過即上述刻意略過的組員測試）。
- 注意：組員的上傳稽核紀錄會把 OCR 全文（`raw_text`）存進 `audit_logs`；這是組員原設計，只存在本機資料庫，但成績單全文可能含個資，之後做 M14 去識別化時要一併決定是否保留。
- 下一步：決定是否採用組員的學習歷程頁改版（上傳前預覽旋轉）；M10 決定後再評估刪除功能；用真實格式的合成成績單與證照圖片測組員版面解析＋RapidOCR 的準確度；OCR 背景排隊處理。

## 2026-10-19 OCR 預設改用 PP-OCRv5 伺服器版

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者希望直接用伺服器版模型，為之後正式多人使用做準備；先確認使用者電腦跑得動。

- 模型：`scripts/download_ocr_models.py` 新增伺服器版偵測（88 MB）與辨識（85 MB）模型，來源仍是 RapidAI 官方 ModelScope，SHA-256 均相符；輕量版保留作備用。
- 實測（使用者電腦：AMD Ryzen 5 7535HS、6 核 12 執行緒、31 GB 記憶體；全部是合成圖片）：

  | 項目 | 輕量版 | 伺服器版 |
  | --- | --- | --- |
  | 載入模型＋第一張 | 約 3 秒 | 約 12 秒 |
  | A4 清楚整頁（40 行） | 2.2 秒，40/40 | 10.2 秒，40/40 |
  | 模糊、傾斜 5 度、低對比的照片 | 2.2 秒，8/40 | 6.9 秒，20/40 |
  | 記憶體高峰 | 約 0.7 GB | 約 2.0 GB |

  結論：使用者電腦可以跑伺服器版；畫質差時伺服器版明顯較準（20/40 對 8/40），代價是慢約 3～4 倍、記憶體約 3 倍。極度模糊的圖片兩者都讀不出來（0/40），這種情況靠學生手動填寫（M12）。
- 修改檔案：`app/services/document_analysis_service.py`（`OCR_MODEL_TIERS`，`RapidOcrEngine` 預設 `tier="server"`，可設 `mobile`）、`app/config.py`（新增 `OCR_MODEL_TIER`，預設 `server`）、`app/__init__.py`（建立引擎時帶入等級）、`.env.example`、`scripts/download_ocr_models.py`、`tests/test_document_ocr_candidates.py`（新增 4 項，真實辨識測試改用伺服器版模型）。
- TDD：先寫測試，8 項失敗（紅燈）；補實作後 OCR 測試檔 16 項全通過。
- 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/tier-full` → `364 passed in 200.58s`。
- 正式多人使用的注意事項（尚未處理）：每個網站服務程序（worker）各自載入一份模型，伺服器版每份約 2 GB；一張 A4 約 10 秒會佔住一個 worker。正式上線前要決定伺服器規格、worker 數量，以及是否把 OCR 改成背景排隊處理（上傳後先回應、辨識完成再通知），避免多人同時上傳時網頁卡住。
- 下一步：OCR 背景排隊處理的設計（正式多人使用前必做）；合成證照圖片實測；M14 去識別化。

## 2026-10-19 換用 PP-OCRv5 模型，繁體中文辨識通過

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者同意下載支援繁體中文的 RapidOCR 模型；換模型並重跑測試，把上一節的 2 項 xfail 改回正式測試。

- 套件：從 PyPI 安裝 `rapidocr==3.10.0`（RapidAI 官方，與 `rapidocr_onnxruntime` 同一團隊），用 `--no-deps` 安裝以免和現有 `opencv-python` 重複安裝 `cv2`；另裝 `tqdm`、`omegaconf`、`requests`、`colorlog`。`pip check` 只提示缺 `opencv-python-headless`，實際由 `opencv-python` 提供，匯入正常。舊的 `rapidocr_onnxruntime` 仍在虛擬環境中，未移除、程式已不使用。`requirements.txt` 改為 `rapidocr==3.10.0`、`onnxruntime==1.31.0`。
- 模型：新增 `scripts/download_ocr_models.py`，從 RapidAI 官方 ModelScope 下載 PP-OCRv5 偵測、PP-OCRv5 辨識（簡體／繁體／英文／日文共用）、方向分類 3 個模型到 `instance/ocr-models`（已被 `.gitignore` 忽略，不會提交），3 個檔案 SHA-256 全部與 rapidocr 3.10.0 官方清單相符。
- 修改檔案：`app/services/document_analysis_service.py`（`RapidOcrEngine` 改用 rapidocr 3.x 與本機模型路徑，**不會自動下載**，模型不存在時明確失敗並提示執行下載腳本；欄位解析改為遇到空白或下一個標籤就停止）、`tests/test_document_ocr_candidates.py`、`requirements.txt`、`.env.example`（新增 `DOCUMENT_ANALYSIS_PROVIDER`、`DOCUMENT_OCR_ENGINE` 說明）、新增 `scripts/download_ocr_models.py`。
- 實測（合成成績單圖片）：`課程：模擬資料結構`、`課程：模擬網頁設計` 全部正確，信心值 0.94～1.0。新發現：OCR 會把「學分：3  分數：88」黏成「學分：3分數：88」，已先寫失敗測試再修正解析規則。
- 測試：上一節 2 項 xfail 已移除，改為正式斷言（兩門課的課名、學分、分數全部正確）；另新增「黏在一起的標籤」與「缺模型檔不下載、直接失敗」2 項。OCR 測試檔 12 項全通過。
- 完整測試：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/v5-full` → `360 passed in 203.60s`（無 xfail、無略過）。
- 限制：只驗證過電腦字型繪製的合成圖片；拍照、傾斜、掃描品質差的真實樣式尚未測。證照圖片的真實辨識也還沒測（目前證照只有測試替身）。
- 下一步：用合成的證照圖片與手機拍照樣式做實測；接著做 M14 去識別化（送 AI 前移除姓名、學號、證號等）與 M5 欄位規則檢查。

## 2026-10-19 接上 RapidOCR 離線辨識（M4，繁體字辨識待改善）

日期：2026-10-19（台灣時間）

開發者：Claude

目標：使用者選定 RapidOCR 離線辨識；安裝套件、接上 `OCR_ENGINE`，並用合成成績單圖片實測。

- 安裝：從 PyPI 安裝 `rapidocr_onnxruntime==1.2.3`（連同 onnxruntime、opencv-python 等相依套件）到 `D:\democase\ai\.venv`（本專題共用的虛擬環境）；已寫入 `requirements.txt`。
- 修改檔案：`app/services/document_analysis_service.py`（新增 `RapidOcrEngine`：本機執行、模型第一次辨識時才載入，依文字框座標分行、同行由左到右排序）、`app/config.py`（新增 `DOCUMENT_OCR_ENGINE`，空白＝不啟用，`rapidocr`＝啟用）、`app/__init__.py`（啟用時把 `RapidOcrEngine` 放進 `OCR_ENGINE`；若測試已傳入引擎則不覆蓋）、`requirements.txt`、`tests/test_document_ocr_candidates.py`（新增 5 項，其中 2 項標 xfail）。
- 實測結果：合成圖片（繁體中文，系統字型 msjh.ttc 繪製，內容全是假資料）經 RapidOCR 辨識，**數字正確**（88、91、學分），**繁體中文名稱不正確**：`課程`→`程`、`模擬`→`模凝`、`資料結構`→`餐料结构`，`網頁`→`網真`。RapidOCR 1.2.3 預設模型偏簡體，對繁體字辨識不準。
- 因此：兩項「課名應正確辨識」測試標為 `xfail` 並寫明原因，不放寬斷言；候選解析規則仍會把學生需要修正的內容交給學生確認。這是目前最大的品質缺口，不能宣稱 OCR 已可用於真實成績單。
- 規則不變：候選只寫入抽取紀錄；學生確認前 `LearningCourseRecord` 為 0 筆；未啟用 OCR 時上傳標示 `analysis_failed`。
- 測試結果：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/rapid-full` → `356 passed, 2 xfailed in 202.22s`。
- 下一步（需使用者決定）：(1) 換用支援繁體中文的 RapidOCR 辨識模型（需下載模型檔，依規定須先取得你同意）；(2) 或先降低期待，只要求學生確認時逐字修正。完成後再把 2 個 xfail 改回正式測試。
- 未做：M14 去識別化、M5 規則檢查；未接 Gemini。

## 2026-10-19 M3／M4 離線 OCR 候選欄位骨架（合成資料，未接外部服務）

日期：2026-10-19（台灣時間）

開發者：Claude

目標：把上傳證明後的寫死假資料，換成「OCR 文字 → 候選欄位」的真流程骨架；先不選定、不安裝正式 OCR 套件。

- 修改檔案：`app/services/document_analysis_service.py`（新增 `offline_ocr` 提供者、`NotConfiguredOcrEngine`、`parse_candidates`；欄位以「標籤：值」規則解析，查不到就留空）、`app/routes/student.py`（把 `OCR_ENGINE` 設定傳入分析函式）、新增 `tests/test_document_ocr_candidates.py`（6 項）。
- TDD：先寫測試，匯入 `parse_candidates` 失敗（紅燈）；補實作後 10 項相關測試通過（綠燈）。
- 規則驗證：候選只寫進抽取紀錄；上傳後 `LearningCourseRecord` 筆數為 0，學生確認後才寫入正式課程；未設定 OCR 引擎時狀態為 `analysis_failed`，不猜測任何欄位。
- 測試資料全部是合成資料：合成白底 PNG（只為讓檔案是真圖片）＋測試替身 OCR 引擎回傳固定文字。測試不讀像素，因此這**不是**真實 OCR 辨識率驗證。
- 未做：沒有安裝 RapidOCR；沒有接 Gemini；原始圖片仍只存 `UPLOAD_FOLDER`。OCR 套件的選擇需使用者確認（規格 D7 已記載 RapidOCR 離線，但這次任務指示先問）。
- 測試結果：`pytest -q -p no:cacheprovider --basetemp=logs/test-runs/ocr-full` → `354 passed in 205.90s`。
- 注意：`docs/05_交接與專案管理/handoff.md` 有他人留下的未提交修改（21 行新增），本次沒有碰它、沒有提交。
- 下一步：使用者確認 OCR 套件後，安裝並在 `OCR_ENGINE` 接真實 RapidOCR 引擎，用合成證照圖片做實測；再做 M14 去識別化與 M5 欄位規則檢查。

## 2026-10-16 整理 D:\democase 根目錄的測試暫存資料夾

日期：2026-10-16（台灣時間）

開發者：Claude

目標：使用者反映 `D:\democase` 根目錄太亂，要求整理。

- 把根目錄 33 個測試暫存資料夾（`pytest-*`、`ui01-test-temp`）搬到 `D:\democase\_test-temp-archive\`，搬移前後數量核對一致（33 → 0 留在根目錄、33 在歸檔資料夾），清單存在 `_test-temp-archive\_清單_搬移前後.txt`。
- 沒有刪除任何檔案。`ai`、`ai-wt-story`、`ai-meeting-room`、`ai-meeting-room-codex-integration`、`room-test-data`、`room02-browser` 等專案與資料夾未動。
- 還沒處理：`ai-wt-story` 根目錄的 `.pytest-*` 測試暫存（已被 `.gitignore` 忽略，不影響提交）；`docs\02_需求與設計` 裡約 25 份文件的命名與分類；`ai-wt-gpt*`、`ai-wt-award` 等舊的 worktree 是否還要留，需要使用者確認。
- 注意：搬移的資料夾若要還原，依清單搬回原位即可。
- 同日第二批：舊的 worktree 統一搬到 `D:\democase\_worktrees\`。`ai-wt-award` 用 `git worktree move` 搬移，已在 `ai` 的 worktree 清單確認；`ai-wt-gpt`、`ai-wt-gpt4`、`ai-wt-gpt5` 不是 git worktree（沒有 `.git`），是單純的資料夾，也一併搬移。`ai-wt-story` 因為目前分支還在用，先留在原位。
- 還沒做：`ai-personal`、`ai-personal-backup-2026-09-29`、`backup` 的去留，等使用者決定。
- 使用者決定：`ai-personal-backup-2026-09-29` 與 `backup` 留著、不搬不刪。
- `ai-wt-story` 根目錄的 26 個 `.pytest-*` 與 `.requirement-pdf-review` 搬到 `logs\test-runs\`（已被忽略，不影響提交）。
- `docs\02_需求與設計` 重新分類成四個資料夾：`01_目前有效`、`02_設計規格`、`03_審查與檢查`、`04_原始資料與參考`。
  - 搬檔後重寫了文件內的相對連結（37 處）與純文字路徑，並修正移入子資料夾後深一層的連結（12 處）。
  - Markdown 連結檢查：失效連結數與搬檔前相同（9 個，都在 `99_封存` 舊檔裡，搬檔前就已失效）。
  - 修正程式與測試中寫死的路徑：`tests/test_project_consistency.py`、`app/services/guide_service.py`、`app/services/journey_home.py`。
  - 完整測試 `348 passed in 341.29s`。
  - 注意：只改了 `feat/journey-home` 這條分支；主專案 `D:\democase\ai\docs` 的檔案沒有動。
- 同日第三批：依使用者要求整理 `docs\03_開發紀錄` 與 `docs\05_交接與專案管理`。
  - 保留原位（其他文件與使用者習慣都指向這些路徑）：`development-log.md`、`midterm-development-log.md`、`AI_交接_新對話起點_2026-10-08.md`、`handoff.md`、`待辦清單.md`、`AI_操作手冊與角色導覽_本機展示版.md`、`AI_專題任務工作流程_新手版.md`。
  - `docs\03` 新增 `01_參考與環境設定`（environment-check、mysql-setup、database-setup.sql）與 `02_流程與簡報紀錄`（流程圖更新紀錄、簡報製作紀錄）。
  - `docs\05` 新增 `01_舊交接與修正紀錄`（GPT 雲端副本修正清單、10-10 會議室交接）與 `02_任務與檢查`（期中任務清單、系統完整性檢查、組員正式文件草稿）。
  - 更新 18 個檔案的連結與路徑；失效連結數維持 9 個（與搬檔前相同，皆在 `99_封存`）。
- 同日第四批：依使用者要求整理 `docs\04_圖表與介面`、`docs\06_會議錄音與逐字稿`、`docs\09_AI會議室`。
  - `04`：新增 `01_資料模型`、`02_設計規格`、`03_檢查與圖表規範`。
  - `06`：會議紀錄移到 `01_會議紀錄`，逐字稿移到 `02_逐字稿`；總覽「專題開發時間線與錄音整理」留在原位。
  - `09`：新增 `01_實作計畫`、`02_設計規格`、`03_開發紀錄`、`04_驗收與交接`（含交接說明與瀏覽器驗收腳本）。
  - 更新 66 個檔案的連結與路徑（含 `scripts/`、`tests/` 內寫死的圖號與路徑）；失效連結數維持 9 個（皆在 `99_封存`）。
  - 完整測試 `348 passed in 286.10s`。
- 還沒做：`docs\01_正式規格`、`docs\99_封存` 等資料夾未動。

## 2026-10-15 重寫 V1 系統開發規格

日期：2026-10-15（台灣時間）

開發者：Claude

目標：指導老師指示「先把系統做好」，依《V2 架構調整提案》簡報重寫一份精簡的開發規格，取代分散的 V2 診斷與追蹤文件作為開發依據。

- 新增 `docs/02_需求與設計/02_設計規格/AI_設計規格_V1系統開發規格_2026-10-15.md`：主線 M1～M12 與驗收條件、現況、開發預設決定、資安底線、不做清單、10/20～11 月中時程。
- 舊的 V2 診斷、需求追蹤、待辦清單保留不刪，只當參考。
- 本次只改文件，沒有改程式，也沒有執行測試。
- 同日補記使用者拍板：教師端只做班導；同意用 Google Drive／Docs，先用個人雲端驗證；自傳定位為可追溯草稿並要有歷史版本（新增 M13）；AI 先抓欄位、學生只檢查對錯再確認；證照與成績單送外部 AI 前先去識別化（新增 M14 與第 6 節資料流程）。因此 OCR 定為伺服器離線辨識（RapidOCR），原始圖片不送外部服務。
- 使用者要安裝影片介紹的 Jev（TypeSafe 外掛），權限設定擋下，需使用者自己執行安裝指令。

## 2026-10-15 整理未提交改動並分組提交

日期：2026-10-15（台灣時間）

開發者：Claude

目標：把 10/13～10/15 Codex 在 `ai-wt-story` 留下的未提交改動分組提交，方便之後跟老師討論 V2 前確認現況。

- 開工前確認：Codex 對話 `01a135a6` 最後一輪於 10/15 09:13 結束，之後沒有在工作；工作佇列無進行中的同批檔案。
- 驗證：完整測試 `348 passed in 170.42s`（提交前執行）。掃描新檔沒有真實金鑰，`.env.example` 的 Google 設定都是空值。
- 分組提交（本機分支 `feat/journey-home`，未合併、未推送）：
  1. 抵免功能（含遷移檔 `a920261013tc`，**尚未在 MySQL 執行**，要先備份）
  2. 提案展示頁與 Google Drive 單檔預覽（預設關閉）
  3. 證據編號、自傳、送審快照、模擬 OCR
  4. 本機合成資料展示站與四種角色導覽
  5. 文件
- `.gitignore` 加上 `.pytest-*/`、`.requirement-pdf-review/`；這些測試暫存資料夾沒有刪除。
- 注意：各組按檔案分，不保證中間每個提交單獨都能跑測試；最後一個提交的狀態就是測試通過的狀態。
- 下一步：跟老師用 V2 簡報第 13 頁的 6 個問題拍板，再決定 Google Drive 與資料生命週期怎麼改。

## 2026-10-15 本機展示頁瀏覽器與完整套件驗收

日期：2026-10-15（台灣時間）

開發者：Codex

目標：實際驗收 `ai-wt-story` 本機展示頁，重跑完整自動測試並更新交接狀態。

- 修改檔案：`tests/test_student_navigation.py`、`docs/02_需求與設計/01_目前有效/AI_V2需求追蹤與現況對照_2026-10-14.md`、`docs/05_交接與專案管理/AI_操作手冊與角色導覽_本機展示版.md`、`docs/05_交接與專案管理/handoff.md`、`docs/05_交接與專案管理/待辦清單.md`、本開發日誌。
- 瀏覽器實測：Codex 內建瀏覽器實際開啟 `http://127.0.0.1:5013/proposal-preview`，標題與頁面內容均為工作樹的「五年，不只是五個學年」展示頁，畫面明示假資料及「Google Drive 尚未設定」。桌面視窗截圖為 1111×729；鍵盤 `Tab` 依序聚焦略過主要內容、首頁及區塊導覽，按 `Enter` 導到 `#journey`，實際看到四步資料流程。再以四組合成帳號實際登入成功，分別到達學生、教師、科辦、管理員工作台；學生及管理員導覽可啟動、按方向鍵前進、按 `Esc` 關閉。管理員「怎麼操作」的重播按鈕會返回工作台並啟動導覽。未把 5000 埠計入本次驗收。
- 窄版與動態偏好：瀏覽器工具沒有 viewport 模擬介面；因此未實測 390px 手機尺寸或作業系統「減少動態效果」偏好。教師／科辦導覽細節未在瀏覽器逐一手測。靜態檢查確認 `proposal-preview.css` 有 `max-width: 640px` 版面規則及 `prefers-reduced-motion: reduce` 規則；這只能證明有對應樣式，不能代替實機驗收。
- 完整測試第一次得到 `347 passed, 1 failed`。失敗是舊測試仍檢查早期 `DEMO_ACCOUNTS`／`teacher01` 契約；現行展示帳號為 `student_demo`、`teacher_demo`、`staff_demo`、`admin_demo`，並由 `LOCAL_DEMO_MODE` 控制。只更新 `tests/test_student_navigation.py` 使其檢查現行模式契約；針對測試 `1 passed in 1.19s`，完整套件重跑為 `348 passed in 253.24s`。
- 靜態驗證：`python -m compileall -q app scripts tests` exit 0；`git diff --check` exit 0，只有 Git LF／CRLF 提醒。新增測試暫存目錄皆使用新的唯一路徑，未清除既有暫存資料。
- 外部服務：工作樹沒有 `.env`，資料庫及 Google OAuth／Picker 環境變數皆未設定；沒有連接任何資料庫或 Google 帳號。隔離 MySQL 8.0.39、OAuth／Drive／Docs／Gemini 仍未實機驗收。
- 操作：依[本機展示手冊](../05_交接與專案管理/AI_操作手冊與角色導覽_本機展示版.md)執行 `& D:\democase\ai\.venv\Scripts\python.exe scripts\run_local_demo.py`，使用瀏覽器開啟 5013 埠。展示帳密只在非正式本機展示模式列出。
- 下一步：在可切換 390px viewport 與減少動態效果的瀏覽器補做手動驗收；取得隔離 MySQL 及核准的 Google 測試設定後，逐項完成真實服務驗收。V2 仍待組員與老師審查，不代表正式規格已變更。

## 2026-10-14 V2 雲端增補篇整合診斷與開發前準備

日期：2026-10-14
開發者：Codex
目標：檢視 V2 成果報告書後加的雲端提案，整理為可追溯、可決議和可分段驗收的開發準備文件。

- 新增 `docs/02_需求與設計/01_目前有效/AI_V2增補篇整合診斷與開發前規格_2026-10-14.md`，記錄原報告正文後接 15 節增補提案、需求優先級與架構提及不一致、功能編號缺口、現行程式基線、十項待決事項及附件來源首切片建議。
- 新增 `docs/superpowers/plans/2026-10-14-v2-cloud-integration-preparation.md`，依需求校準、領域／資料設計、本機假服務契約、單一 Drive 用例、OCR／證據包接線及分層驗收安排標準流程；標明帳號、老師／組員決議和隔離 MySQL 為外部前置條件。
- 檢查既有 Drive 路由後確認 `/proposal-preview/drive-file` 屬公開展示原型，沒有應用程式登入者或學生資料歸屬；新增 D-10，要求先定帳號連結與附件擁有者檢查，避免把公開展示路由直接改造成學生附件 API。
- 更新 `docs/05_交接與專案管理/handoff.md` 與 `待辦清單.md`，加入本次 V2 整合分析入口、未決決策、執行閘門和後續可開始工作；保留原有交接內容。
- 此次為文件準備，沒有修改功能程式、V2 Word 原檔、學校正式規格或其他專案，也沒有連接外部服務或資料庫。
- 驗證：兩份新增文件的空白檢查與相對連結檢查通過，確認本節位於日誌最上方；`git diff --check` exit 0（只有 Git LF／CRLF 提醒）。本回合不重跑程式測試。既有工作樹修改及未追蹤測試暫存目錄全部保留。
- 下一步：先按整合診斷整理 F 編號及現況資料模型對照；不依賴外部帳號的假服務契約可先做測試設計，Drive schema／OAuth／上傳流程須等相應待決事項有結論後實作。

## 2026-10-14 登入頁展示文案與測試帳密

日期：2026-10-14
開發者：Codex
目標：移除登入頁多餘說明，並在本機展示模式列出目前可用的合成測試帳密。

- 修改檔案：`app/templates/login.html`、`tests/test_auth.py`、`tests/test_local_demo.py`。
- 移除登入標題下方重複解釋登入用途的小字；本機展示模式登入頁列出學生、教師、科辦、管理員四組合成帳號及共用密碼 `demo2026`。一般登入頁不顯示帳密；正式環境即使誤開本機展示旗標也會隱藏。
- 測試先行：新增 3 項測試，先觀察到 2 項失敗、1 項（正式環境隱藏）通過；完成模板後執行 `tests/test_auth.py tests/test_local_demo.py`，結果 `11 passed in 7.21s`。
- 本機展示服務已重啟於 `127.0.0.1:5013` 以載入新模板。畫面截圖指向 `127.0.0.1:5000`，其登入文案與本工作樹模板不同；本次沒有改動其他專案，也未能從內建瀏覽器驗收 5013 的實際畫面。
- 下一步：在 `http://127.0.0.1:5013/login` 看見展示帳密；正式環境部署前確認 `FLASK_ENV=production`，頁面不應顯示帳密。桌機／手機版面仍需於可連 localhost 的瀏覽器驗收。

## 2026-10-14 V2 本機展示流程、證據追溯與角色導覽

日期：2026-10-14
開發者：Codex
目標：依使用者指定的 V2 提案，補成本機可展示的 OCR 修正、證據引用、角色導覽及後續驗收交接。

- 修改程式與測試：`app/demo.py`、`app/services/document_analysis_service.py`、`app/services/autobiography_service.py`、`app/services/autobiography_review.py`、`app/services/package_service.py`、`app/services/review_snapshot_service.py`、`app/routes/main.py`、`app/static/js/components.js`、`app/templates/dashboard.html`、`app/templates/admin_dashboard.html`、`app/templates/help.html`、`app/templates/learning_profile_upload.html`、`app/templates/learning_profile_review.html`、`app/templates/student_autobiography.html`、`scripts/run_local_demo.py`、`tests/test_document_analysis_demo.py`、`tests/test_local_demo.py`、`tests/test_autobiography.py`、`tests/test_autobiography_review.py`、`tests/test_help_and_tour.py`、`tests/test_package_docx.py`。
- 已確認的課程、證照、經歷現在會建立穩定的 `evidence_id`；自傳來源顯示與導師送審快照保存該 ID。備審 Word 只包含已確認的課程、證照與經歷。
- 新增 `DOCUMENT_ANALYSIS_PROVIDER=demo` 本機合成 OCR 範例，清楚標示假資料與不連外；加入只綁 `127.0.0.1:5013`、記憶體 SQLite 的展示啟動程式與四個本機合成角色帳號。停止程序後展示資料消失。
- 「怎麼操作」的重播按鈕已依登入角色回到自己的工作台並啟動導覽；為學生、教師、科辦、管理員主頁補導覽步驟。
- 新增 `docs/02_需求與設計/01_目前有效/AI_V2需求追蹤與現況對照_2026-10-14.md` 及 `docs/05_交接與專案管理/AI_操作手冊與角色導覽_本機展示版.md`；更新本日誌、`handoff.md`、`待辦清單.md`。V2 仍是待老師／組員審查提案。
- 階段測試：OCR 合成範例與確認 2 項通過；四角色本機展示及 OCR 相關 4 項通過；自傳、引用、Word 輸出及四角色導覽的階段套件 33 項通過。修正保留舊 `work-dashboard` 識別名稱後，完整測試 `343 passed in 163.32s`；`git diff --check` 無錯誤（PowerShell 顯示 LF／CRLF 提醒）。
- 本機啟動驗證：`scripts/run_local_demo.py` 修正匯入路徑後可建立合成資料並啟動 Flask，顯示服務位址 `127.0.0.1:5013`；測試用戶端確認展示頁與四角色工作區回應正常。
- 瀏覽器驗收受環境阻擋：沙盒 PowerShell loopback GET 回報「嘗試存取通訊端被拒絕，因為存取權限不足」；Codex 內建瀏覽器開啟 5013 回報 `net::ERR_CONNECTION_TIMED_OUT`。服務沒有連到 `ai-personal`，但桌機／手機版面、鍵盤實際操作與減少動態效果仍未驗收。
- 安全補強：本機展示啟動器強制關閉外部 AI、清空本機設定載入的 AI 金鑰、隱藏並忽略自備金鑰輸入，避免使用者原有 `.env` 使合成資料送出外部。新增回歸測試，針對性套件 17 項通過；完整套件需再跑一次。
- 畫面補強：本機模式把自傳按鈕改為「產生示範草稿」，隱藏金鑰欄位並說明不呼叫外部 AI；本機展示／自傳／導覽針對性測試 32 項通過。最終完整測試 `345 passed in 169.46s`；`git diff --check` 無錯誤（僅 LF／CRLF 提醒）。
- 尚未驗收：隔離 MySQL 8.0.39；真實 OAuth／Drive／Docs／Gemini。SQLite、本機合成 OCR 不代表上述實機驗收。
- 下一步：在可連本機服務的瀏覽器環境執行操作手冊驗收，再安排隔離 MySQL；外部 Google 服務要等測試帳號、雲端設定及審查決議。

## 2026-10-14 驗收重跑

- 依使用者要求重新執行完整自動測試：`python -m pytest -q --basetemp .pytest-live-acceptance-20261014-a`，結果 **345 passed in 175.45s**。
- `git diff --check` 與 `python -m compileall -q app scripts tests` 均以 exit code 0 結束；Git 顯示的 LF／CRLF 訊息是行尾格式提醒。
- 重新啟動本機展示服務，啟動器顯示 `http://127.0.0.1:5013/proposal-preview`；Codex 內建瀏覽器仍回報 `net::ERR_CONNECTION_TIMED_OUT`，PowerShell loopback GET 仍遭通訊端權限拒絕。此次未完成桌機、390px 手機、鍵盤或減少動態效果的實際畫面驗收。
- 下一步：需在能連到此工作樹 localhost 的瀏覽器環境完成畫面驗收；MySQL 8.0.39 與 Google OAuth／Drive／Docs／Gemini 仍須各自實機驗收。

## 2026-10-13 夜間接手：現況盤點與資料模型文件草稿

日期：2026-10-13
開發者：Codex
目標：接續完成可展示、可驗收的畢業專題；整理新對話可直接執行的工作清單。

- 修改文件：`docs/02_需求與設計/01_目前有效/AI_資料字典_現行ORM草稿_2026-10-13.md`、`docs/04_圖表與介面/01_資料模型/AI_ERD_現行ORM模型_2026-10-13.md`、`docs/04_圖表與介面/03_檢查與圖表規範/diagrams.md`、`docs/05_交接與專案管理/handoff.md`、`docs/05_交接與專案管理/待辦清單.md`、`docs/02_需求與設計/01_目前有效/AI_專題審查需求對照與進度盤點_2026-10-13.md`、本開發日誌。
- 資料字典／ERD 草稿由現行 SQLAlchemy ORM 中繼資料產生：42 張表、312 個欄位、60 個明確外鍵欄位。欄位中文用途是暫譯；尚未核對實際 MySQL，也不取代正式規格。規劃型 29 表 ERD 和現行實作 ERD 分開保留。
- 新增估計八小時待辦清單，將瀏覽器實測、字典語意複核、MySQL 整合測試、畢業門檻缺口和展示流程分段排序。12／13 只作 MVP 項目證據，不宣稱整體完成率。
- 完整測試基線（文件整理前執行）：`333 passed in 143.33s`；`git diff --check` 無差異格式錯誤。此次只改 Markdown 文件，沒有更動應用程式程式碼，未重跑完整測試。
- 瀏覽器驗收未完成：Codex 內建瀏覽器的 5000 頁面內容對應 `ai-personal`；從工作樹啟動的 5013 頁面無法由 Codex 瀏覽器連線。未在 `ai-personal` 或其他專案操作，未設定 OAuth，未做 MySQL 遷移。
- 下一步：依 `docs/05_交接與專案管理/待辦清單.md`，先讓正確工作樹的本機預覽能被瀏覽器存取；再複核資料文件及隔離 MySQL 驗收。若正式畢業條件或期中分母沒有依據，交由組員／老師確認，不自行發明。

## 2026-10-13 新對話交接整合

日期：2026-10-13
開發者：Codex
目標：將本輪長對話的專題決策、實作狀態與待驗收事項濃縮到接手文件。

- 修改檔案：`docs/05_交接與專案管理/handoff.md`、本開發日誌。
- 交接文件新增一頁現況、使用者最新優先順序、四種帳號角色與教師關係、正式規格與 Google 新構想的界線、學校審查要求、資料庫版本、目前原型限制、下一步及可直接貼到新對話的起始文字。
- 明確記錄：新構想文件列出的完整 V1 與長篇展示流程仍是提案；目前只驗證單一 Drive 選檔原型。先前 `333` 項完整測試通過屬 2026-10-13 最近一次程式驗證，本次只改文件，沒有重跑程式測試。
- 驗證：核對 `ai-wt-story` 分支為 `feat/journey-home`、HEAD `fcd50a7`；檢查交接內的關鍵來源路徑、設定名稱與待辦，並執行 `git diff --check`。既有未提交變更與測試暫存資料均保留。
- 下一步：新對話先讀 `handoff.md` 並確認最新 Git 狀態，再選定一件優先任務；真實 Drive 授權、MySQL 8.0.39 和瀏覽器展示仍須實測。

## 2026-10-13 期中要求盤點、角色收斂與轉學生抵免進度

日期：2026-10-13
開發者：Codex

- 依學校系統組要求盤點文件和系統：需求、架構圖、ERD、分工、資料字典、資料表數量、使用者角色、正規化與防呆。新增審查需求對照文件，並把商業產品化分析限定為未來參考，不把多租戶、平台管理員或計費加入本期範圍。
- 角色採四種帳號角色：學生、教師、科辦、管理員。「導師／專任教師／指導老師」屬教師工作關係與資料範圍，不另拆帳號角色；目前只實作導師與班級關係。
- 新增學生「轉學生抵免進度」頁，可記錄人工追蹤狀態、日期、待補資料與備註；導師可確認受指派班級的學生。學生更新欄位後會清除舊確認。此功能不判斷校方抵免結果。
- 新增 `transfer_credit_records` 資料模型與 Alembic 遷移 `a920261013tc`，未對既有或正式資料庫執行遷移。
- 資料庫版本盤點：XAMPP 3.3.0 隨附 MariaDB 10.4.27，另有 MySQL 8.0.39 與 8.4.9。依正式專題規格以 MySQL 8.0.39 為標準；保留 XAMPP/MariaDB。隔離資料目錄初始化成功，但 Windows 沙箱拒絕本機 TCP 與命名管道連線，故真實 MySQL 遷移尚未驗收。
- 測試先行：抵免表單、狀態驗證、教師班級權限、更新後清除確認與遷移測試先因功能缺少而失敗，再完成實作。最近局部測試 `26 passed in 21.16s`；完整測試 `333 passed in 150.76s`。Alembic 僅有一個 head：`a920261013tc`。
- 尚待完成：欄位級資料字典、同步目前 ORM 資料表的 ERD、隔離 MySQL 8.0.39 整合驗收、畢業門檻提醒清單或經老師核准移出本期、分工與完成百分比確認、Drive OAuth 真實選檔及桌面／手機瀏覽器驗收。MVP 12/13 只代表所選 MVP 功能清單，不代表整個專題完成百分比。
- 本次新增盤點與任務清單，並更新交接文件；保留 Google Drive 原型和工作樹既有變更，未碰主專案 `ai`、其他版本，未合併或推送。

## 2026-10-13 Google Drive 雲端主線展示原型與新手交接

日期：2026-10-13
開發者：Codex

- 在 `feat/journey-home` 新增公開 `/proposal-preview` 編輯式展示頁，以五年路徑、成果拼圖和數位檔案呈現「目標 → 成果證據 → 缺件 → 下一步」；學生、校系和成果資料皆為假資料，並清楚標示提案原型。
- 加入本機 Google Identity Services、Google Picker 和 Drive `files.get` 中繼資料驗證流程。只在 OAuth 設定完整且非 production 時啟用；只向 Google 查詢使用者選取檔案的 ID、名稱、類型和原始檔連結。程式不下載內容、不呼叫 Drive 寫入、不保存 token 或檔案選取狀態。`drive.file` scope 仍包含 Google 層級的建立／修改能力，提案文件已說明此限制。
- 新增會議用可行性評估、新手任務工作流程與 `handoff.md`，記錄提案界線、OAuth 設定步驟、隱私提醒、目前驗收和接手任務；不改正式規格或其他專案。
- 測試先行：新增 13 項展示路由與 Drive 中繼資料測試，先確認功能缺少時會失敗，再完成實作。目標測試實際輸出：`13 passed in 0.91s`；`node --check app/static/js/proposal-preview-drive.js` 通過。
- 完整 pytest 實際輸出：`322 passed, 6 failed in 156.30s`。6 項均為 Flask-Migrate CLI／migration 測試；目前 Python 環境沒有 `Flask-Migrate`，測試暫用的相容 shim 只略過應用初始化、不支援 migration 指令。安裝專案依賴後需重跑這 6 項及完整測試。
- 視覺驗收限制：Flask 測試伺服器成功啟動於 5055，但沙箱拒絕瀏覽器工具連至本機通訊端；桌面／手機瀏覽器版面、鍵盤與減少動態效果尚未取得實際驗收證據。Google OAuth 尚未設定，真實帳號選檔也未驗證。
- 後續：安裝專案依賴並完成完整測試；在可連本機伺服器的瀏覽器做桌面／手機驗收；由專案擁有人設定 OAuth 後，以無個資測試檔完成真實 Picker 流程，再帶給組員和指導老師決策。原型維持未提交、未合併、未推送。

## 2026-10-11（續 43）第三輪審查（會議 20261011-041330）必修修正（GPT 任務 07，Claude 審查後合併）

- Claude 合併後驗收：完整測試 `315 passed, 1 warning in 299.42s`。瀏覽器（展示版學生 111534105，資料庫放一筆 200 天前的登入，用表單登入）：「好久不見」出現時焦點在「繼續 →」、`aria-modal="true"`；按 3 次 Tab 焦點仍在畫面內；等 5 秒沒有自動消失；Esc 關閉後焦點回到首頁標題 `route-title`；首頁顯示「五年累積 50% 只是累積比例，不是錄取機率」。

日期：2026-10-11
開發者：GPT／Codex

- 照片上傳在完整解碼前檢查尺寸；超過 4,000 萬像素或 Pillow 判定為解壓縮炸彈時回傳指定的 400 訊息。JPEG 先寫入正式檔同資料夾的唯一暫存檔，成功後才取代舊照片，失敗會清除暫存檔並保留舊照片。
- 「好久不見」對話框補上 `aria-modal`、初始焦點、Tab 焦點循環、Esc／按鈕關閉與關閉後標題焦點；鍵盤焦點仍在對話框內時不自動消失。
- 小人物完成初始路線時送出 `journey:walked` 事件並留下完成狀態；首頁首次導覽改等事件，最多等待 6 秒，不再固定等 2.6 秒。
- 學生可見的「做備審」統一為「準備備審資料」；首頁五年累積旁補上「只是累積比例，不是錄取機率」。
- 測試驅動：先新增巨大 PNG、舊照片保留、對話框鍵盤契約、完成事件／逾時備援、統一用語與比例說明測試，確認因功能缺少而失敗後完成最小實作。獨立審查後再補真實執行的 Node 最小 DOM 測試，以及暫存寫入、原子取代失敗與成功取代案例；淡出期間維持焦點限制，並在樣式檔最後補一條規則，讓程式移入焦點的按鈕不受延遲動畫隱藏。
- 規格取捨：`app/routes/main.py` 原本已將 `ValueError` 回成 400，因此不額外修改路由；比例短說明沿用既有小字樣式，只在 `design-system.css` 最後追加焦點按鈕立即可見的規則。`AGENTS.md` 要求更新協作佇列，但任務明定只改指定檔案與 `tests/`，故依最小改動原則不改專案外佇列。
- 測試（實際輸出）：`315 passed, 1 warning in 300.55s (0:05:00)`。

## 2026-10-11（續 42）學生端其餘頁面用語與空狀態一致（GPT 任務 06，Claude 審查後合併）

日期：2026-10-11
開發者：GPT／Codex

- 統一六個學生端頁面的空狀態與錯誤下一步：無法預覽可重新上傳、辨識失敗可直接跳到手動輸入、經歷表單錯誤可回到必填欄位、目標校系空狀態可先整理資料、目標數量超限可跳到已選校系，不能使用時以明確按鈕返回。
- 用語調整（舊說法 → 新說法）：
  - `learning_profile_review.html`：「確認資料」→「確認上傳內容」；「還沒有資料」→「還沒有課程／證照」。
  - `student_portfolio_form.html`：「儲存並確認內容正確」→「確認並儲存」。
  - `student_targets.html`：「設為目標／取消目標／舊學年度的目標／已取消的目標」→「設為目標校系／取消目標校系／舊學年度的目標校系／已取消的目標校系」；「做備審」→「準備備審資料」。
  - `student_welcome.html`：「先看看學校」→「先看目標校系」。
- 文字瘦身：`learning_profile_upload.html` 的上傳說明改為兩句短話；`student_targets.html` 的年級限制與備審說明收斂為一至兩句。
- 新增 `tests/test_student_page_consistency.py` 共 5 項真實路由測試；先確認 5 項因缺少 CTA 與一致用語而失敗，再完成最小範本修改。
- 規格取捨：既有 `.button`、`.record-card__actions`、`.paper-empty` 已能呈現一致狀態，因此沒有在 `design-system.css` 重複新增樣式；`AGENTS.md` 要求更新工作佇列，但任務 06 未列在佇列，且本任務明定修改範圍不含佇列，因此只在本開發日誌留下紀錄。
- 測試（實際輸出）：`306 passed, 1 warning in 294.93s (0:04:54)`。

## 2026-10-11（續 41）第二輪審查（會議 20261011-002400）的修正與瀏覽器驗收紀錄

日期：2026-10-11 凌晨
開發者：Claude Code

- 審查：Gemini 被限流、5 分鐘沒有輸出自動停止；GPT 額度用完未參加；Copilot（#7）與 Claude（獨立審查，#8）的意見全部查證屬實，照改：
  1. 下載前檢查清單「自傳已寫」只要有 AI 草稿就打勾 → 改成「自傳已改成自己的話」，學生自己存過一版（`edited`）才算。新增測試：AI 剛產生沒改過的草稿顯示「! 還沒」，連結到該校系自傳頁。
  2. 自傳每段「沒有資料佐證」的建議不分題目 → 依題目給建議（動機、經驗、困難、未來各一句）。新增測試。
  3. 導覽視窗沒有把 Tab 焦點留在視窗內 → 焦點只在導覽卡片的按鈕之間循環。
  4. 點年級打開資料夾的捲動沒照「減少動態效果」→ 已照設定。
  5. 自傳頁、導師頁、缺件頁的時間軸與檢查清單沒有導覽步驟 → 已補；老師的上方選單也加「導覽」按鈕。
- 主筆決定（組長醒來可改）：「自傳已寫」要學生自己改過才算；首頁第一次自動播導覽維持（小人物走完才開始，可按「結束」或 Esc）。
- 承認：續 39、40 寫了「每項都開瀏覽器看過」，但任務 03、04 的瀏覽器驗收沒有寫進日誌；續 40 也沒寫測試數字（299 是 `7a19b0a` 提交前那次完整測試的輸出「299 passed」）。以下補上，以後每節都寫實際輸出。
- **瀏覽器驗收（本節，展示版學生 111534107 林小美、導師 teacher01）**：
  - 缺件頁（臺北商大資管）：準備度旁「準備度只看你確認過的資料，不是錄取機率」；時間軸「第 1 版 待確認 2026-10-10 最新」；檢查清單四項：✓ 資料都已確認／! 導師已確認最新的一版（連到 `#review`）／! 加權項目都有資料（連到 `#board-title`）／! 自傳已改成自己的話（連到 `/student/autobiography?program_id=3`），兩個頁內錨點都存在。
  - 導覽：缺件頁按「導覽」1／5 開始，按 5 次 Tab 焦點仍在導覽卡片的「結束」；→ 換到 2／5「資料齊了，從這裡請導師確認。」；Esc 關閉。
  - 自傳頁：送出四題（第 3 題空白）產生示範草稿（展示版沒接 AI，不花額度）。四段：動機「沒有資料佐證 → 補上讓你想讀資管的具體契機」；經驗「F3 競賽：全國商業類技藝競賽 佳作，暫未發現疑點」；困難「這題還沒回答 → 補上遇到的困難、你的做法與結果」；未來「沒有資料佐證 → 補上進二技後想學的內容與目標」；上方「🚫 AI 不能做的事」。
  - 導師頁：五年簡圖專一 5、專二 5、專三 2（今年）、專四／專五尚未到。
- 測試（實際輸出）：`301 passed, 1 warning in 253.48s (0:04:13)`。

## 2026-10-11（續 40）GPT 任務 04、05 合併；修兩個瀏覽器才看得到的錯誤

日期：2026-10-11 凌晨
開發者：GPT／Codex（任務 04、05 程式與測試）；Claude Code（驗證、合併、修錯）

- **GPT 額度用完**（5 小時上限，凌晨 3:51 恢復）：任務 04、05 的程式與測試在額度用完前都已寫好，但沒寫到日誌。Claude 跑測試確認後提交並合併。
- 任務 04（自傳草稿，Canva 第 14 頁）：每段顯示引用的資料（短標題）、疑點（沒回答／沒有資料佐證）、建議，以及「AI 不能做的事」；用規則判斷，不呼叫 AI（`app/services/autobiography_review.py`）。
- 任務 05（導師看學生，Canva 第 17 頁）：頁面上方加純靜態的五年簡圖，點有資料的年級捲到下方；不放照片、小人物、拼圖。
- **修正 1：共用樣式檔有合併殘留**。合併任務 03 時留下一行衝突標記，手機版那段少了收尾的大括號，**後面所有樣式整段失效**（缺件頁時間軸、檢查清單、導師簡圖都沒有樣式）。已修正，並新增 `tests/test_css_integrity.py` 檢查衝突標記與大括號成對。
- **修正 2：屬性名稱撞到**。導師簡圖用了 `data-count`，但既有的數字跳動動畫會抓所有 `data-count` 元素並把內容換成數字，結果圓點和年級標籤被清掉。改名為 `data-records`。
- 教訓：伺服器端測試抓不到這兩種錯，一定要開瀏覽器看。
- 測試：全部通過（見提交）。瀏覽器：導師頁五年簡圖顯示正確（專一 5、專二 5、專三 2 今年、專四／專五尚未到）。

## 2026-10-11（續 39）缺件頁：不是錄取機率、送審版本時間軸、下載前檢查清單（GPT 任務 03，Claude 審查後合併）

日期：2026-10-10
開發者：GPT／Codex

- 缺件頁準備度旁新增「準備度只看你確認過的資料，不是錄取機率」；原本導覽屬性已有同句，採最小改動改成較短導覽文字，避免同一句重複出現。
- 「導師確認」新增同一學生、同一校系的歷次送審時間軸，依送審日期列出版本、日期與已確認／退回／待確認狀態，並標示最新版本；沒有送審紀錄時不顯示。
- 「產出備審資料」新增四項下載前提醒：資料確認、最新版本導師確認、準備度 100%、自傳草稿；未完成項目都有補件連結。清單只提醒，既有 Word 下載規則未變。
- 新增 `app/services/gap_checklist.py` 集中整理時間軸與提醒資料，不新增資料表；`target_gap()` 只新增範本所需資料。
- 測試驅動：先新增未送審、退回再送、全部完成三種真實路由案例並確認 3 項皆因功能缺少而失敗，再完成實作。指定完整測試結果：`290 passed, 1 warning in 279.24s`；警告為既有 pytest 設定 `cache_dir` 未被辨識。

## 2026-10-11（續 38）公開首頁依 Canva 視覺改為六幕故事（GPT 任務 01；Claude 審查：修正標語被資料夾層蓋住、手機版標語被切掉，之後合併）

日期：2026-10-10
開發者：GPT／Codex（分支 `feat/gpt-home`）

- 將訪客首頁改成六幕連續故事：藍色資料夾海與小人物、細線成路、專一至專五的低飽和彩色資料夾、升學／實習／就業分岔、相關資料聚焦、半透明漸層資料包；所有圖像均由 HTML、CSS 與內嵌 SVG 繪製，沒有新增外部圖片、字型或套件。
- 首屏標語改成「把五年，拼成下一站」，最後加入「開始我的路徑」登入按鈕；五年文字集中在 `five_year_plan.py`，每年維持一句短話。保留 `data-page="public-home"`、`data-scatter`、`id="route"`、`id="agent"`，校系資料與加權表放在六幕故事後並改成同一套米白／深墨視覺。
- 動效只保留淡入、細線成路、聚焦與資料包組合。系統開啟「減少動態效果」時，十個動效容器皆直接採最終靜態排列、無位移與縮放，只保留 `opacity` 淡入。
- 測試先新增六幕順序、三向分支錨點、登入 CTA、每幕一個主標題加一句主述（五年與下一站卡片為規格明定的短句例外）的契約，確認舊版首頁會失敗後再實作。最終完整 pytest：`285 passed, 1 warning in 247.16s`；警告是既有的 pytest `cache_dir` 未知設定。
- 瀏覽器驗收：以系統既有 Chrome／Playwright 實際載入本工作樹的 5055 埠；桌面 1440px 與手機 375px 都無水平溢出，六幕逐幕捲動後完整顯示；CTA 可取得焦點並顯示 4px 實線焦點環；模擬 `prefers-reduced-motion: reduce` 時所有動效容器的 `transform` 均為 `none`、透明度為 1。另模擬 `IntersectionObserver` 不可用，所有內容仍顯示且聚焦幕維持最終狀態。
- 獨立程式審查發現並修正：`motion-ready` 祖先方向寫反，使成路／聚焦／組合動效沒有生效；五年資料夾改成低飽和粉、橘、藍、芥末、灰藍並重驗文字對比（最低 6.97:1）；第四幕補成真正的三向分岔；恢復招生範例的年度與公告說明。首幕綠字對米白為 4.56:1。
- Claude 於 1280×800 實看後複查修正：首幕由 1212px 收為首屏 735px，標語、人物與資料夾海第一屏可見；六幕收斂為約一個視窗高，分岔線改近白 3px；375px 改五年／聚焦雙欄、票券單欄，一般與減少動態均無水平溢出且文字可讀；完整測試 `285 passed, 1 warning in 276.65s`。
- 規格取捨／環境限制：六幕「字少」規則只套故事段落，需求明定保留的 `id="agent"` 校系表作為故事後的補充資訊，不硬塞成第七幕。電腦使用介面沒有可用瀏覽器，且直接無頭 Edge／Chrome 受沙盒 GPU 程序限制，因此改用環境既有 Playwright 驅動系統 Chrome；本機 5000 埠已有舊版服務，為避免干擾改用 5055 埠驗收，未更動應用程式埠設定。
- 尚未做：沒有產品功能缺口；測試截圖與瀏覽器暫存只供本機驗收，不納入版本控制。未提交、未推送、未合併、未切換分支。
## 2026-10-10（續 37）學習歷程狀態標籤統一（GPT 任務 02，Claude 審查後合併）

日期：2026-10-10
開發者：GPT／Codex

- 新增 `app/services/record_status.py`，集中判斷「已確認／待補來源／草稿」：活動與經歷依確認狀態、資料來源與佐證判斷；成績、證照與來源文件依本人確認或來源文件確認判斷。
- 新增共用 Jinja macro `partials/status.html`，兩頁都使用相同的圖示與短文字；已確認為綠色 `✓`、待補來源為黃色 `!`、草稿為灰色虛線 `—`，不只用顏色表達狀態。
- `learning_profile.html` 的來源文件、課程、證照，以及 `student_portfolio.html` 的新舊活動紀錄均套用共用狀態標籤。經使用者同意，`app/routes/student.py` 僅增加狀態 helper 的匯入與兩個模板參數。
- 測試驅動：先新增 `tests/test_record_status.py` 並確認 5 項因功能缺少而失敗，再完成實作；同步把既有「未確認」頁面測試改為新規格的「草稿」。完整測試結果：`287 passed, 1 warning in 274.99s`；警告為既有 pytest 設定 `cache_dir` 未被辨識。
## 2026-10-10（續 36）夜間開發：Canva 整理、四位 AI 腦力激盪、手冊與導覽、分工給 GPT

日期：2026-10-10 深夜
開發者：Claude Code（主持＋實作）；會議室 `20261010-224756`

- 組長睡前要求：學生端做到 Canva「智慧學習歷程 UX 交接」的樣子，並做系統手冊與網頁導覽；開 AI 會議室讓 Claude、GPT、Gemini、Copilot 一起討論。組長說明 Canva 第 1～5 頁是她親手做的視覺基準，第 6 頁以後是 GPT 網頁版生成、只當想法。
- 會議室加入第四位 AI **Copilot**（GitHub Copilot CLI 1.0.95，組長用學校 GitHub 帳號登入；自訂指令、唯讀：`--deny-tool=write --deny-tool=shell`，實測建立檔案會被擋）。GPT 在會議室原本的模型 `gpt-6.1-sol` 不支援 ChatGPT 帳號的指令列模式，會議室裡的 GPT 改用 `gpt-5.6-sol`（只改會議室設定，不動組長的 Codex 設定）。
- Canva 23 頁整理成 `docs/02_需求與設計/02_設計規格/AI_設計規格_Canva_UX交接整理_2026-10-10.md`。
- 會議結論（#11）：今晚先保證「一條新生走得完的展示流程＋其餘頁面風格一致」；每項附可操作的驗收句。依會議修正：
  - 拼圖鍵盤 Enter 打不開、拖曳被中斷會卡住（獨立審查 #6）→ 已修並實測。
  - 字級（Gemini #4、獨立審查 #6）→ 最外層改 `font-size: 112.5%`，內文 18px；最小標籤約 13px。
  - 照片快取一天（GPT #10）→ `Cache-Control: no-store`。
  - 送給 AI 的指示有學生姓名（GPT #10 問、Claude 查證屬實）→ 小助手與自傳草稿拿掉姓名，新增 `tests/test_ai_privacy.py`。**導師用小助手查全班時，工具仍會把學生姓名傳給 AI（`assistant_tools.py` 第 53 行），改成代號較大，留給組長決定。**
  - 首頁補「今天先完成哪一步」＋五年累積、待處理、最近成果（Canva 第 11 頁）。
- 手機版：五年路線改直的年級列表＋四個功能大按鈕（375px 沒有左右捲動）。
- 系統手冊：新增「❓ 怎麼操作」頁（`/help`，內容在 `app/content/help.py`，13 題，每題一兩句話＋一個按鈕；老師、科辦、管理員各有簡短版）。網頁導覽：頁面上 `data-tour` 的元素就是步驟；首頁第一次自動播，其他頁按上方「導覽」；Esc 結束、← → 換步、焦點在「下一步」；看不到的元素自動略過。
- 額度：Claude 本 5 小時已用約 69%、本週 73%，GPT 本週 27%。依組長指示，之後主要程式交給 GPT 在獨立工作資料夾寫（`ai-wt-gpt` 分支 `feat/gpt-home`：公開首頁；`ai-wt-gpt2` 分支 `feat/gpt-status`：狀態標籤），Claude 審查、測試、瀏覽器驗收後合併。
- 測試：282 項通過（續 36 結束時）。

## 2026-10-10（續 35）拼圖的圖改成「這學期最快樂的照片」；報告準備文件

日期：2026-10-10
開發者：Claude Code（分支 `feat/journey-home`）

- 使用者要讓學生上傳當學期最快樂的照片當拼圖。使用者決定：**每學期一張、只有學生自己看得到、還沒上傳時先用插畫並提示上傳**。
- 新增 `app/services/photo_service.py`：不新增資料表，存成 `UPLOAD_FOLDER/semester-photos/<學生編號>/<年級>-<學期>.jpg`，同學期再傳就覆蓋。一律用 Pillow 重新壓成 JPEG：**去掉 EXIF（含拍攝地點）**、依拍攝方向轉正、從中間裁成拼圖的 3:2、最長邊 1500 像素。看不懂的檔案回 400。上學期＝8 月～1 月，下學期＝2～7 月。
- 路由：`POST /student/photo`（上傳）、`GET /student/photo/<年級>/<學期>`（只能看自己的；別的學生 404、老師 403、未登入 401；`Cache-Control: private`）。
- 首頁拼圖：有照片就用照片切六片，沒有就用插畫；拼圖下方「📷 放上上學期最快樂的照片」，選好檔案直接上傳；「只有你自己看得到。」
- `requirements.txt` 加上 `Pillow==12.3.0`（虛擬環境原本就有，專案腳本也用過）。
- 使用者問「老師問為什麼做拼圖、要現場改程式怎麼辦」：新增 `docs/08_簡報/AI_報告準備_首頁拼圖的設計理由與現場修改指南_2026-10-10.md`（設計理由、可能追問、常見修改要求對應到哪個檔案哪一行、展示順序）。
- 測試：`tests/test_semester_photo.py`（5 項：學期判斷、上傳後裁切且去掉定位資訊、只有本人看得到、拒絕非圖片、沒照片時顯示插畫與提示）；完整測試通過。瀏覽器：上傳一張測試照片後，拼圖的洞與散落的片都換成照片。
- 還沒做：拼圖目前是「一個年級的資料」配「這學期的照片」；要不要改成依學期判斷每一片，待使用者決定。

## 2026-10-10（續 34）今年的拼圖改成「一張圖切六片」，真的拼起來

日期：2026-10-10
開發者：Claude Code（分支 `feat/journey-home`）

- 使用者：原本六片各自獨立「比較像收集拼圖，不能順便拼起來」，要像線上拼圖一樣有圖案、真的拼出一張圖。
- 改成：每個年級一張插畫（學校、太陽、山坡、往前的路、樹、「專三」字樣，屋頂與大字用該年級的顏色；SVG 畫，不用外部圖片），切成 3×2 六片，邊是凹凸咬合的拼圖邊（`journey_home.jigsaw_pieces()` 產生，相鄰兩片共用同一條邊，一凸一凹）。
  - 有資料的類別：那一片拼在圖上，看得到圖案，下方標類別。
  - 沒有的：圖上留下虛線的洞，那一片歪歪地散在圖下方。
  - 把散落的片拖到洞附近：洞會亮起；放開就吸進去拼上，接著打開新增頁。拖到別處放開會彈回。直接點也可以。
  - 回來時新拼上的那片會跳一下、標題「又留下了一塊。」（沿用續 33）。
- 標題改成「還差 N 片，就拼完專三。」／「專三拼完了。」
- 測試：`tests/test_journey_home.py` 加 2 項（六片形狀與位置、有資料的片顯示圖案）；完整測試通過。瀏覽器：看得到拼好的成績、活動兩片與四個洞；程式模擬拖曳把「服務」拖到洞上，洞亮起、放開吸進去並打開新增；新增一筆專三服務後回首頁，服務那片拼進圖裡，標題「又留下了一塊。」
- 已知：用自動化工具實際拖曳時頁面會被捲動、座標跑掉，所以拖曳是用程式送出同樣的拖曳事件驗證；手機寬度的版面還沒調。

## 2026-10-10（續 33）拖拉拼圖：拖進空格就去補，存好回來會拼上

日期：2026-10-10
開發者：Claude Code（分支 `feat/journey-home`）

- 依 img-020（一隻手把拼圖放進去）：今年拼圖的每個空格上方浮著一片同色的拼圖，輕輕上下飄。
  - 拖進空格放開：「啪」一聲拼上，接著打開那一類的新增或上傳頁。
  - 拖到別處放開：彈回原位，不換頁。
  - 不想拖的直接點也可以（新手、鍵盤都能用）。
- 回到首頁時，用瀏覽器分頁暫存比對上次看到哪些拼圖；新拼上的那片會跳一下，標題變成「又留下了一塊。」第一次進來不會出現。不新增資料表。
- 測試：`tests/test_journey_home.py` 加 1 項（空格與可拖的拼圖都有 6 片）；完整測試通過。瀏覽器實際拖曳：拖到別處會彈回、拖進空格打開「上傳文件」；新增一筆專三的競賽後回首頁，競賽那片拼上、標題「又留下了一塊。」
- **發現的問題（還沒修）**：窗格很窄（約手機寬度）時，五年路線整張縮得很小，節點與小島的字看不清楚；浮起來的拼圖也會壓到旁邊。手機版要另外排（例如路線改成直的）。

## 2026-10-10（續 32）首頁加上小人物與路邊四個小島

日期：2026-10-10
開發者：Claude Code（分支 `feat/journey-home`）

- 使用者看完參考圖後同意 Claude 的提議：參考圖幾乎都有「一個小人物站在資訊裡」（img-003、005、008、012、019、020），所以登入後不是捲動閱讀，而是一張可以走的地圖。使用者要的是「動畫互動」，不是儀表板大覽；上方選單保留，方便熟悉的學生直接用。
- 小人物（平面剪影，不畫臉）：登入後沿著路線從專一走到今年停下；同一個分頁只走一次（`sessionStorage`），之後直接站在今年；「好久不見」播放時等它關掉才走；系統設定減少動態效果時不走。
- 路邊四個小島＝四個主要功能：成績與證照、活動與經歷、目標校系、備審資料（有目標校系時連到第一個校系的缺件頁）。點小島，小人物走過去再換頁；按住 Ctrl／Shift 點擊照一般連結開新分頁。
- 修正兩個瀏覽器才看得到的問題：① 公開首頁原本就有 `.walker` 樣式，名稱撞到讓小人物跑出畫面，改名 `.jwalker`；② 小島圖示的動畫用了 `transform`，蓋掉 SVG 的位置，四個圖示疊在左上角（使用者在畫面上指出「這一坨是啥」），改成只做淡入。
- 測試：`tests/test_journey_home.py` 加 1 項（小人物與四個小島、連結）；完整測試通過。瀏覽器：小人物走到專三停在節點上；四個圖示在各自的小島上；點小島會走過去並進入該頁。
- 還沒做：拖拉拼圖、聚焦那一幕加上小人物（使用者說先看第 1、2 項效果）。

## 2026-10-10（續 31）學生首頁改成「我的五年路線」

日期：2026-10-10
開發者：Claude Code（分支 `feat/journey-home`，從 `feat/story-guide` 的 `2aa480c` 開出；未合併、未推送）

- 使用者要「簡潔明瞭，用動畫說故事，少量文字」。依 `chat.md` 第 6、9 輪的設計（我的五年路線、缺漏變成拼圖空格、一年一次的回訪儀式），規格寫在 `docs/02_需求與設計/02_設計規格/AI_設計規格_我的五年路線首頁_2026-10-10.md`。
- 首頁由上到下：
  - 「專三，你在這裡。」＋五年路線：路線從專一畫到今年；走過的年級把當年的資料吸進節點（節點上是筆數）；今年的節點呼吸發光；之後是虛線。點節點會打開那一年的資料夾。
  - 今年的六塊拼圖：有資料的一片片拼上，空白是虛線，點了直接去補。標題只有「還有 N 塊空白。」或「今年六塊都拼上了。」
  - 引導卡片（沿用）；五年資料夾與目標校系收進「打開五年資料夾」。
  - 原本的六格數字與「下一步」卡片拿掉。
- 好久不見：學生登入改記在操作紀錄（`student.login`）；上次登入在 60 天以前時，首頁先播「200 天沒見了。」「專二留下了 5 件。」，數字跳動，約 4.5 秒或點一下就淡出；**同一次登入只播一次**；播放時路線動畫先暫停，關掉才開始。
- 新增 `app/services/journey_home.py`、`tests/test_journey_home.py`（6 項）。聚焦標題改成「先做這 N 件，離下一站更近。」（chat.md 第 9 輪的語氣）。
- 驗證：完整測試通過；瀏覽器實際操作：路線、節點、拼圖動畫依序播放；點節點打開資料夾並切到該年；在展示資料庫放一筆 200 天前的登入後，用表單登入看到回訪畫面，關掉後路線動畫才開始。
- 注意：展示版伺服器關閉偵錯模式時會快取網頁範本，改範本後要重啟才看得到。

## 2026-10-10（續 30）依 GPT 審查（UI-01）修正必修 R1～R6

日期：2026-10-10
開發者：Claude Code（分支 `feat/story-guide`）

- 審查報告：`main` 的 `docs/05_交接與專案管理/AI_檢查報告_UI-01_story-guide分支審查_2026-10-10.md`。Claude 逐條對照程式查證，6 項必修全部屬實，照改。
- R1 沒有推薦≠準備好了：聚焦區沒有推薦時改成「目前沒有可以推薦的補件，專題作品、自傳等文件請看各校的文件清單」，不再說「都準備好了」。
- R2 待確認要標示：聚焦結果帶 `pending`，畫面寫「N 所校系的要求有這項 · 分類待確認」，下方說明「依系統目前的分類估算，不是校方配分」。不再說「都看重」。
- R3 舊學年度目標不參與聚焦：改用 `target_slots()["current"]`，和選校名額同一套。
- R4 內部代碼不能當官方代碼：卡片、缺件頁、導師頁只有數字代碼才寫「志願代碼」；改顯示「學年度 · 招生管道」，日間部加「下面是書審內部比例，另計統測」；目標校系頁頁尾改寫涵蓋兩種管道。
- R5 升五年級超過 5 所：新增 `student_rules.over_limit_reason()`；目標校系頁顯示要取消幾所、首頁出現「整理目標校系」卡片；送導師確認時擋下。**不自動刪除**目標或自傳。
- R6 做完的卡片要消失：看完歡迎流程後不再出現「歡迎」卡（按鈕改連到歡迎流程）；二、四年級的「每學期成果」「實習」在該年級已有經歷時消失；四年級「看各校要求」選了校系就消失；三年級競賽卡改用自己的代號。
- 一起做的建議：聚焦區的要求數改成完整總數（動畫最多 60 張）；歡迎流程第 3 幕改「點一片，看能存什麼」、第 4 幕只留一個校系例子、「記下一件活動」直接到新增表單且不再說「比賽都可以」；首頁第一張卡片放大成主要動作。
- 交接的提交數誤寫為 7 個，實際 6 個（GPT 指出）。
- 測試：新增 `tests/test_ui01_fixes.py`（10 項，逐條重現 R1～R6）；完整測試 **256 項通過**。瀏覽器：展示版王小明選 12 所 → 聚焦顯示「分類待確認」與說明；日間部 5 張卡片都有「另計統測」、頁面沒有「志願代碼 DAY」。
- 未做的建議：`build_national_seed.py` 跨行解析的補強（CSV 本身已核對一致）、同校同系不同招生類別是否去重（待使用者決定）。

## 2026-10-10（續 29）「資料爆多 → 聚焦」；選校上限改依年級

日期：2026-10-10
開發者：Claude Code（分支 `feat/story-guide`）

- 新增 `app/services/focus_service.py` 與 `partials/focus.html`：目標校系選 3 所以上時，「目標校系」頁最上面出現聚焦區。捲到畫面時，所有校系的備審要求一張張堆滿（最多 60 張），約 1.5 秒後淡出模糊，只留下「先做這 N 件」（最多 3 件），每件一個按鈕。可以按「再看一次」；系統設定減少動態效果時直接顯示結果。
- 「先做哪件」的算法：只看學生還沒有的資料類別；每個簡章項目的加權平分給它對應的類別，所有目標校系加總，分數高的先做。「自傳與讀書計畫」在學生還沒替該系寫自傳、而且年級可以寫時也列入。算法寫在檔案開頭，方便報告說明。
- 依 10-10 定案（小助手規格 10.7）：**目標校系一到四年級不限所數，五年級最多 5 所**（`student_rules.target_slots` 的 `limit` 為 `None` 代表不限）。目標校系頁的說明跟著改。既有測試 `test_sixth_target_is_refused` 改成五年級的情況，另加三年級可以超過 5 所的測試。
- 測試：`tests/test_focus_service.py`（5 項）；完整測試 245 項通過。瀏覽器：展示版王小明選 12 所 → 34 項要求堆滿 → 聚焦成「補上競賽（9 所看重）」「寫自傳與讀書計畫（7 所）」兩件（王小明其他資料都有，所以只剩 2 件）。

## 2026-10-10（續 28）下載三校二技日間部簡章，補上國立資管相關系

日期：2026-10-10
開發者：Claude Code（分支 `feat/story-guide`）

- 使用者同意後，從招策會頁面的「招生簡章下載」連結下載雲林科大、臺中科大、臺北商大的 115 學年度二技日間部申請入學簡章（共約 3.3MB），存在 `school/public-sources/二技簡章_115日間部申請入學/`，README 記錄來源網址。
- 日間部和技優甄審不同：**總成績＝統測＋書面審查**。系統只算書審，所以 `app/content/admission_demo_dayapply_115.csv` 存的是書審內部比例，統測與書審的比例寫在「資料來源」欄。
  - 雲科資管（52 名）：統測 30%＋書審 70%；書審＝歷年成績及學習計畫書 50%、相關能力證明 50%。
  - 中科資管（40）：統測 20%＋書審 80%；成績 40%、專題／競賽／證照 60%。資應菁英班（3）：10%＋90%；30%／70%。資工（46）：20%＋80%；40%／60%。
  - 北商資管（31）：統測 25%＋書審 75%；**簡章沒有列書審分項比例**，只列 7 項應繳資料，所以存成一項 100%、標「待確認」。
- 展示版（`scripts/run_demo.py`）多匯入這 5 個系；主種子檔不動。測試加在 `tests/test_national_demo_seed.py`；展示版啟動確認正常。

## 2026-10-10（續 27）二技國立校系：用招策會官網核對 Gemini 的整理

日期：2026-10-10
開發者：Claude Code（分支 `feat/story-guide`）

- 使用者請 Gemini 整理國立二技校系，覺得有漏，請 Claude 查。新增 `scripts/scrape_techadmi_national.py`，從招策會網站抓 6 種二技管道（技優甄審、技優保送、日間部、進修部、五專菁英班、產學攜手）所有國立學校的系名與名額（115 學年度；只讀公開網頁，沒有下載檔案）。
- 結果寫在 `docs/02_需求與設計/03_審查與檢查/AI_檢查報告_二技國立校系官網核對_2026-10-10.md`：Gemini 版本的名額大多不對、列了不存在的系（例如北護高齡健康照護系、技優臺中科大護理），也漏了雲林科大資管（日間部 52 名）、臺中科大資管與資工等。北科大不在任何二技管道名單上。
- 官網沒有備審加權，所以這次**沒有把新校系放進系統**；要放進系統需讀各校簡章（下載前先問使用者）。Gemini 附的加分比率表官網沒有，未核對、不採用。

## 2026-10-10（續 26）展示資料：補上 PDF 裡所有國立校系（為「資料爆多 → 聚焦」鋪路）

日期：2026-10-10
開發者：Claude Code（分支 `feat/story-guide`）

- 使用者要求從 `school/Documents/116二技技優甄審_時程與備審加權_修訂版.pdf` 找國立大學的二技科系，讓示範資料夠多。
- PDF 附錄共 83 個志願代碼，其中國立 36 個（6 校：臺中科大 14、臺北商大 8、臺北護理健康大學 7、虎尾科大 3、高雄科大 3、高雄餐旅 1）。主種子檔已有 4 個，其餘 **32 個**由 `scripts/build_national_seed.py` 讀 PDF 整理成 `app/content/admission_demo_national_116.csv`（105 列，每個志願加權加總 100%）。
- **PDF 裡沒有排名，也沒有北科大**（使用者提到的北科大應用日文系不在這份 PDF）。所以不是「前十名」，而是 PDF 內所有國立校系；沒有自己補學校或加權。要加北科大需要使用者提供該校簡章。
- 「對應資料類別」是依項目名稱關鍵字推測；只有純成績類標「確定」，其餘都標「待確認」，管理者核對後才算數。
- 主種子檔不動（測試仍以 4 個校系為基準）；`scripts/run_demo.py` 展示版會多匯入這份。測試：`tests/test_national_demo_seed.py`。
- 下一步：用這些校系做「選很多校系 → 資料堆滿 → 聚焦在最重要的 3 件」。

## 2026-10-10（續 25）第一次登入的歡迎流程（拼圖版，視覺隱喻待使用者定案）

日期：2026-10-10
開發者：Claude Code（分支 `feat/story-guide`；未合併、未推送）

- 起因：使用者指出新生不知道要按什麼、介面太花會被勸退；要像 Windows 11／蘋果的開機設定，一次一個畫面先教會學弟妹。
- 新增 `GET /student/welcome`（5 個畫面：歡迎、五年五片拼圖、六種成果點一下拼上、二技校系看什麼〔取自 115 簡章種子資料〕、先放第一片）與 `POST /student/welcome/done`（記入操作紀錄 `student.welcome_done`，不新增資料表；去向只接受白名單）。學生第一次登入會先到這裡，之後登入直接進首頁；每一頁都有「跳過」。
- 視覺隱喻先用「拼圖」：依據 `docs/99_封存…/04_視覺參考與聊天紀錄/chat.md` 的結論（母題「把五年，拼成下一站」）。**使用者表示拼圖只是舉例、還有很多張圖，最適合哪一張尚未定案**；畫面的拼圖是 SVG，之後可替換。
- 測試：`tests/test_student_welcome.py`（5 項）；`test_auth` 改為「已看過歡迎」的情況。完整測試 237 項通過；瀏覽器逐頁走過 5 個畫面。
- 沒有編造「學長姐經驗」或升學成功案例；第 4 畫面只放真實簡章資料。

## 2026-10-10（續 24）引導卡片第一版與「一兩句話」文字瘦身

日期：2026-10-10
開發者：Claude Code（分支 `feat/story-guide`，worktree `D:\democase\ai-wt-story`；尚未合併、未推送）

- 起因：使用者說第一版離預期的「用網頁講簡短一兩句話的故事」差太多、字太多；範圍選「都有」（學生頁面、引導卡片、公開首頁、小助手視窗）。
- 新增 `app/services/guide_service.py`：依年級與學生做了什麼決定引導卡片，**一次最多 3 張，每張 40 字內、一個按鈕**；做完自動消失；「稍後再說」存在工作階段、隔 24 小時再出現（不新增資料表）。路由 `POST /student/guide/snooze`（只接受白名單卡片代號）。
- 學生首頁「我的五年」：原本的「下一步」卡片換成三張翻頁動畫的卡片（`partials/nav.html` 的 `guide_deck`、`design-system.css`、`components.js`）。
- 文字瘦身：公開首頁每一幕改成一句話（標題＋一行）、五年路徑與下一站每則 30 字內；小助手歡迎詞與建議問題縮短；目標校系頁說明縮成一行。
- 測試：新增 `tests/test_guide_cards.py`（10 項）、`tests/test_short_copy.py`（字數上限）；`test_student_navigation` 改檢查引導卡片只在首頁出現。完整測試 232 項通過。瀏覽器實際操作：登入一年級示範帳號看到 3 張卡片，按「稍後再說」後卡片淡出，重新載入不再出現。
- 還沒做：「❓ 怎麼操作」說明區與網頁導覽、小助手限定範圍提問的規則、學生其餘頁面的逐頁瘦身；卡片文字等使用者看過再調整。

## 2026-10-10（續 23）報告書定版：使用者手動調整的完整版為準

日期：2026-10-10
開發者：Claude Code（記錄；報告書由使用者在 Word 手動調整）

- 開發工具更正為 **Antigravity IDE**（Claude 之前誤寫成 Visual Studio Code，已改報告書內容、規格書與給 GPT 的修正清單）。
- 依使用者要求另做精簡版（只留 10 張核心圖，49 頁；`--lite`，內容檔 `報告書內容_精簡版.md`），並統計學長姐五份報告書的圖表種類：使用案例圖、系統架構圖、甘特圖、系統畫面截圖五份都有；流程圖四份有；ERD 圖、DFD 五份都沒有（以資料表欄位表呈現）。使用者最後決定**用完整版（43 張圖）**，精簡版保留不用。
- **使用者在 Word 手動調整完整版** `docs/01_正式規格/正式報告書/資管科智慧學習歷程系統_專題報告書.docx`：封面改回原本雲端版樣式、更新目錄頁碼、拿掉圖目錄、上邊界 2 公分、字級改為章 20／節 14／小標 12／內文 11／圖說 10、圖 8 移到說明文字上方。**這份是定版，不要再用 `scripts/build_report_docx.py` 覆蓋**；若要用產生器，先把上述格式寫進產生器並和使用者確認。
- Word 檔未放進 git；使用者調整前的版本可用產生器重新產生。

## 2026-10-10（續 23）SPEC-02 副本深度校稿、重複圖清理與圖片可讀性調整

日期：2026-10-10
開發者：GPT／Codex

- 只修改雲端 GPT 副本 `1hi7GI-x_Ion__nDu4TTOUb8N2uVOqW3Q-Ia_7VGveqw`；原始正式版未修改。
- 依逐處核對清單修回被吃掉或黏住的文字：系統首頁標題、學生資料匯入的缺曠說明、表單下載規則、招生資料第一至三階段、官網資料分類與來源失效處理、圖 3／6／8／11／14 圖說，以及第八、十一節標題。
- 學生使用者需求恢復 1～23 編號；沒有使用 Tab 對齊。開發環境改回 Visual Studio Code，刪除「顯著提升整體開發效率」等宣傳式文字，保留必要的 Google Gemini API 功能說明。
- 讀回檢查確認完整「圖片位置：」、`png】`、`片位置`、`發發布`、`圖圖`、Antigravity 與宣傳句均為 0；主文圖說 1～19（含 18-1～18-3）及附錄保留圖 20、21、23、24、26、28～41，各圖說不重複。
- 清理附錄中與主文重複的圖 22、圖 25、圖 27；圖 7 重複圖片刪除一張，圖 12 標題黏附的多餘圖片刪除一張；補回圖 3、圖 6、圖 8、圖 11、圖 13 的圖片與圖說。
- 圖 19 改為可閱讀的直式流程圖；圖 28～31、圖 38～41 重新輸出可讀版圖片，圖 33 控制在約 683 點高以放入單頁。最新 PDF 匯出成功，檔案大小約 13.6 MB；頁面實際分頁仍應由使用者在 Google 文件中最後檢視。
- 未修改圖 21 甘特圖內容；C 段資料表欄位、使用者需求表格、F-01～F-56 逐項說明與未來展望仍未執行。未推送 Git。

## 2026-10-10（續 22）正式報告書改用程式產生 Word；依學長姐框架與學校目錄重排

日期：2026-10-10
開發者：Claude Code（只改文件與產生報告的程式，沒有改系統程式）

- 起因：續 21 GPT 把圖插進雲端副本時算錯位置，**吃掉、黏住十幾處文字**（例如「一、系統首頁與使用者登入流程圖」只剩「一、系」、「圖圖 13」、「科辦核五、科辦核准…」），還把 Visual Studio Code 換成 Antigravity IDE 並加了宣傳句；清單用 Tab 造成編號跑版；圖片大小不一（有的 23 點高看不清、有的超過一頁）。用文件工具逐字算位置的做法本身就容易出錯。
- 使用者決定：**用程式產生 Word**，47 張圖全部保留；開發用的大表格搬到附件；整份照學長姐報告書框架與學校目錄。SPEC-02 改為暫停，GPT 停止修改雲端副本。
- 新增：
  - `docs/01_正式規格/正式報告書/報告書內容.md`：報告書內容（來源是 Claude 修完、GPT 插圖前的雲端版本，已是正式語氣；另清掉 5 處舊的替換殘留）。之後改內容只改這份。
  - `docs/01_正式規格/正式報告書/開發規格附件內容.md`：從報告書搬出的使用案例清單、功能範圍與後續規劃（MVP 切割）、頁面與路由規劃、資料字典摘要。
  - `scripts/build_report_docx.py`：產生報告書（`--annex` 產生附件）。中文標楷體、英文 Times New Roman；章 26／節 20／小標 18／內文 16／表格與圖說 14；每章換頁；封面；Word 目錄（含頁碼）與圖目錄；頁尾「第 N 頁」（封面不放）；圖依比例縮到一頁內，連續兩張窄長圖並排，太寬的圖放橫式頁；**圖號依出現順序自動編**，內文的圖號參照跟著換；表格欄寬依內容分配、表頭跨頁重複。
- 重排：一、緒論只留三節（專題定位併入附錄一）；三、使用者需求改成「使用者｜功能」表格（115 專題日格式）、使用案例圖只放圖；細部流程、各角色流程、版本流程移到第三節；四、系統架構圖收入功能架構與各角色架構圖，權限與角色移到第四節；介面規劃圖移到七、系統展示；甘特圖移到六、開發時程；原附錄四拆散後，固定內容對照改為附錄四。
- 驗證：用 Word 轉 PDF 量頁數與逐頁內容，報告書 **80 頁**（含 43 張圖、目錄、頁碼），附件 21 頁；用 Word 把封面、目錄、內文、表格、並排圖、橫式頁轉成圖片逐張看過，修正了表格欄寬平均分配的問題。
- 未完成：甘特圖（圖 21）內容仍是 GPT 的舊版，等使用者從 AI 會議室產出；Word 檔可隨時重新產生，未放進 git。

## 2026-10-10（續 21）SPEC-02 雲端副本補圖與舊圖更新

日期：2026-10-10
開發者：GPT／Codex

- 依 SPEC-02 只修改雲端 GPT 副本 `1hi7GI-x_Ion__nDu4TTOUb8N2uVOqW3Q-Ia_7VGveqw`；原始正式版 `1IzswEzb2TA0TzDnb669jFMg1diIskO9dEnhvdZf4gjs` 未修改。
- 重新輸出 `D-29-certificate-flow` 與 `D-35-permission-matrix` PNG，使用本機 `scripts/mermaid-render-config.json`；雲端圖 26、圖 32 已替換為本機圖檔，未公開分享圖片。
- 雲端副本中的圖片佔位已改為本機圖檔，共讀回 47 個內嵌圖片，並確認找不到完整的「【圖片位置：」佔位文字。部分早期佔位文字曾被分段插入，已讀回清理殘留檔名片段與圖說文字。
- 流程圖大全簡報 `AI_流程圖大全_給指導老師_2026-10-10.pptx` 重新產生，圖 1～41 均有中文圖名，佔位圖數為 0；簡報腳本不再把本機路徑寫到投影片。
- 實際匯出雲端副本 PDF 為 93 頁。長流程圖仍會增加頁數，Google Docs API 沒有可直接修改既有內嵌圖片尺寸的請求；目前已將圖 26、圖 32 以 300pt 寬重新插入，其他圖片尚未全部壓縮，需使用者確認是否接受縮小圖面或拆圖。
- C 段尚未執行，待使用者確認範圍：依 `app/models` 實際欄位產生資料表欄位表；把使用者需求轉成三欄表；把 F-01～F-56 改成逐項功能說明；新增只取規格書後續擴充項目的未來展望；改寫開發目的第 3、4 點。開發時程與甘特圖未修改。


## 2026-10-10（續 20）接手 GPT：檢查雲端副本是否符合專案、修正排版與內容、加入歷屆報告書固定內容對照

日期：2026-10-10
開發者：Claude Code（GPT 額度用完後接手；只改文件與圖，沒有改程式）

- **先查證 GPT 做到哪裡**：ChatGPT 分享連結讀不到（403），改讀本機 Codex 對話紀錄（`.codex/sessions/2026/10/10/rollout-…01a1232a….jsonl`）、git 提交與開發日誌。GPT 插入圖片用的是能直接上傳本機圖的工具，**沒有公開分享任何圖片**。
- **符合度檢查**（使用者：模型設錯時 GPT 變笨，要確認內容符合本專案）：雲端每段對照本機規格書。圖 20～41 沒有加入專案以外的功能；不符合的地方：招生資料 Agent 被寫成「後續擴充」（實際第二、三階段已完成）、開發環境與參考資料把 Gemini 寫成「外部模型服務」、去 AI 化時整份取代弄壞句子（「啟動 模組，」「模組 拆解」等 15 處）、甘特圖把已完成的主線排成未來、圖 26 把 TA／社團證明寫成來自獎懲記錄、圖 32 寫成所有老師都能修改與確認、學生能撤回送審。
- **雲端副本修正**（只改 GPT 副本，原始正式版不動；每批寫入前重讀並帶版本編號，寫後讀回驗證）：
  - 照學長姐報告書實測格式：**全文標楷體**（含封面）；章標題 26、節標題 20、小標 18 粗體、內文 16、表格與圖說 14。
  - 目錄、圖目錄與每一章前加分頁，標題設定不與下一段分開；圖片與圖說置中。
  - 135 處手打的「•」改成真正的項目清單；目錄拿掉 13 個「待排頁」並加上附錄五。
  - 修好 15 處被弄壞的句子；Gemini 改回；招生資料更新改為「系統亮點，第二、三階段已完成」。
  - **開發環境改寫成招生平台格式**（第一節標題、類別、工具名稱、一段說明），只列程式實際用到的工具；拿掉程式沒用到的 GitHub REST API 與 Chart.js（參考資料一併換成 Flask-SQLAlchemy、python-docx）。
  - 工作分配表改成「學號｜姓名｜工作內容」。
  - 新增**附錄五「歷屆專題成果報告書固定內容對照」**：五份學長姐報告書（113、114 升學競賽、114 軟丙軟乙、115 招生平台、115 專題日）逐份確認，列出每項出現份數、學長姐寫法、本報告書狀態。5／5 都有而我們還缺的：每張資料表的欄位表、系統畫面截圖；開發時程依使用者指示等 AI 會議室產出。
- **本機**：修正 `D-29-certificate-flow`、`D-35-permission-matrix` 並重新輸出；提交 GPT 留下未提交的圖（標楷體設定、圖 20～41 的 PNG）；流程圖大全簡報重新產生（44 頁，佔位頁 0）。
- **未完成／待使用者決定**：
  - 雲端圖 2～15（使用案例圖 2～4、流程圖 5～14、角色責任圖）仍是「【圖片位置】」文字；Claude 的工具只能插入公開網址圖片，需要使用者手動插入，或同意暫時公開分享後插入再取消分享。
  - 雲端裡的圖 21 甘特圖、圖 26、圖 32 仍是 GPT 的舊版（使用者說甘特圖先不做）。
  - 頁碼目錄要在 Google 文件用「插入 → 目錄」產生。
  - GPT 的排版修訂草稿與 `排版核對` 資料夾未提交（含學長姐 PDF，不放 git）。

## 2026-10-10（續 19）雲端副本正式文件去除工具痕跡、字型與個資處理

日期：2026-10-10
開發者：GPT／Codex

- 只修改 GPT 雲端副本 `1hi7GI-x_Ion__nDu4TTOUb8N2uVOqW3Q-Ia_7VGveqw`，原始正式文件與封面內容維持不動。
- 將正文中的開發工具、代理名稱、提示詞及內部協作說明改成正式文件用語；保留系統功能必要的智慧輔助描述。
- 修復先前文字替換造成的 `AI_` 連結前綴與重複詞，並保留目錄、章節與圖表索引。
- 正文中的組員展示資料改為學生甲／乙／丙、指導教師與測試資料說明；封面專題基本資料未改。補上證照、成績單與測試帳號不得使用真實姓名、學號、身分證字號的去識別化規則。
- 參照使用者提供的學長姐文件，將正文（封面除外）套用標楷體；保留既有標題層級與段落結構。
- Mermaid 圖表新增較大字級與標楷體／楷體優先的輸出設定；目前 Windows 的 Mermaid CLI 仍因 Puppeteer 瀏覽器設定檔鎖定而未完成 PNG 重新輸出，尚未宣稱圖片驗收通過。


## 2026-10-10（續 18）SPEC-01 接手：歷屆報告比對、補圖與雲端副本九章重整

日期：2026-10-10
開發者：GPT／Codex

- 依序讀取 114 升學競賽、115 專題日與招生平台三份報告，整理共同需要的功能架構圖、甘特圖與逐功能流程圖。
- 在 `docs/images/` 新增 D-23～D-30 八份 Mermaid 圖稿，並同步更新本機規格書及 `docs/04_圖表與介面/03_檢查與圖表規範/diagrams.md` 的圖表索引。
- 雲端只更新 GPT 副本（<https://docs.google.com/document/d/1hi7GI-x_Ion__nDu4TTOUb8N2uVOqW3Q-Ia_7VGveqw/edit>）：封面保留，內文依招生平台報告書的九章格式重整；原始正式版未修改。更新後以 Docs API 讀回章節標題與「此處插入圖 N」佔位文字確認成功。
- 使用者檢查後指出前一版雲端正文過短；已重新以本機開發閱讀版完整內容為正文來源，保留九章與附錄、需求表、流程說明、驗收原則、頁面／路由、資料字典與長期規則。正文由約 4,400 個字元擴充至約 52,000 個字元，Docs API 讀回 1,037 個段落並確認附錄與功能表存在。
- 重新找到原本的 `AI_流程圖彙整_2026-10-10.pptx` 與 `scripts/build_diagram_deck.py`；依同一版型產生副本 `AI_流程圖大全_給指導老師_2026-10-10.pptx`。副本共 30 張投影片，圖 1～27 每張都有中文圖名；圖 20～27 因尚無 PNG，先建立標名與貼圖位置的佔位頁，方便貼到雲端與 Canva。
- 依學長姐模板再補圖 28～41：四個角色架構、角色／功能權限表、四角色細部流程、版本／歷史／下載，以及學生主工作台、資料確認、導師審查、管理員維護展示架構。內容只取自本機既有規格與頁面／API／資料表；流程圖大全副本已重新產生為 44 張投影片，新增圖目前以有名稱的佔位頁呈現，未新增程式功能。
- 雲端正式副本已再次同步本機規格與圖 28～41 的補強原則；另建立本機 `docs/10_完成快照_2026-10-10/` 與雲端資料夾「AI會議室開發前_已完成規格與圖表_2026-10-10」，新增獨立的「已完成內容與圖表索引」文件，作為進入 AI 會議室開發的基準。文件以約新臺幣 20 萬元系統價值作為範圍與品質估值基準，不把未定案功能宣稱為已完成。
- 雲端完成內容文件已補入正文並讀回驗證：51 個段落，含 20 萬元價值基準、主線、角色、圖 1～41、硬性規則與待處理事項。
- 完成快照新增「評審差異化與競爭力」章節：先界定教育部高中職學習歷程檔案是正式紀錄來源，再說明本系統在目標校系缺件比對、分散資料整合、版本送審、來源追溯、AI 邊界與導師確認上的差異；以 20 個規格維度估算 16／20＝80% 差異度，並明確註記這不是市場實測，尚需實作與使用者測試驗證。
- Mermaid CLI 可執行，但 Puppeteer 在目前 Windows 環境啟動瀏覽器失敗，因此 D-23～D-30 尚未輸出 PNG／SVG；雲端副本暫留圖片佔位，是否公開分享圖片待使用者決定。
- 本次未推送 Git；完成收尾後需做 `git diff --check`，並將規格、圖稿與文件紀錄分開檢視，避免帶入既有未提交修改。

## 2026-10-10（續 17）本機規格書依 10-10 定案大改、圖號從頭重排、補新流程圖與 ERD 拆圖

日期：2026-10-10
開發者：Claude Code（只改文件與圖，沒有改程式）

- 經過：使用者請 Claude 接手（交接原寫由 GPT 負責）。開工後發現 GPT 同時在做，Claude 先停手並把 GPT 摘要和定案不符的 3 處記進工作佇列；使用者請 GPT 暫停、GPT 還原它的草稿後，Claude 重新開工。
- **規格書** `docs/01_正式規格/…開發閱讀版.md`：
  - 「2026-10-08 功能確認總表」改成 **2026-10-10 版**：六份定案規格一覽；決策表保留原有 31 列並加 17 列 10-10 決定（10-09「拿掉聊天框」加註已被取代）；主線改 11 步；完成狀態表重寫（獎懲、證明來源、電子獎狀、確認與版本、自傳版本、入學學年度、每日用量改為已完成；選校上限、小助手、招生資料 Agent 為「部分完成」）；AI 邊界、設計原則（功能寧可少但不能缺、公告通用、好維修、不刪資料）；新增**第六點「拿掉的功能與原因」**（報告用）、圖號新舊對照、待確認事項、開發順序。
  - 補上新功能：資料分類、資料來源維護、畢業學分檢查、成績／獎懲／缺曠貼上匯入、二技公告與推薦、段落註解、引導卡片、表單下載區、操作紀錄頁（使用者需求、UC-23～UC-30、F-46～F-56、頁面 P23～P31、權限矩陣、驗收第 11～16 條、資料表、附錄）。
  - 拿掉或改正舊說法：科辦「登錄送件審查結果」與專題共同審查、行政表單收件（只留下載區）、Bootstrap（程式沒用）、`/staff/reviews` 路由。
  - 開發動機補上組長親身經驗與佐證；專題定位補上「和學校已有系統的差別」。
- **圖號從頭重排**：圖 1～4 使用案例、5 登入、6 主線、7 學校資料匯入（新）、8 導師確認、9 電子獎狀、10 表單下載區、11 招生資料更新、12 二技公告、13 官網資料來源與分類（新）、14 維護校系、15 角色、16 架構、17 DFD、18-1～18-3 ERD、19 總體流程。各圖裡「見圖 N」的文字一起改。
- **圖**：新增 `D-21-school-data-import-flow`、`D-22-info-source-classify-flow`；主線、DFD（加 9.0～12.0）、系統架構、角色與責任、總體流程、使用案例圖補新功能。ERD 新增 7 張表（缺曠合計、課程規則、資料來源與檢查紀錄、AI 代理任務、分類後的學校資訊、表單三張）共 29 張，新增產生器 `D-09-erd-build.py`，一次寫出總覽與三張分圖。全部用 Mermaid 工具輸出 PNG／SVG 並逐張看過；主線圖第一版因多一條線版面變亂，改成虛線補充框後恢復。
- `diagrams.md` 依新圖號重組（原始碼直接讀 `.mmd`，兩邊一致）；流程圖彙整簡報重新產生（封面＋21 張）。
- **使用者途中更正與決定**：
  - **學校沒有微學分系統**，微學分要寫紙本向教務處申請（續 15 的盤點寫錯，報告已加註更正）；「微學分怎麼放進系統」列為待確認。
  - **拿掉「個人資料」頁，使用者都不能自己改密碼；只有管理員可以改**（例如學生換了身分證字號），管理員也要能停用帳號。目前程式本來就沒有改密碼的功能；規格書 P13 拿掉、P19 改寫，「修改密碼（只有管理員）」列為待開發。
- 未提交前的狀態：雲端正式版還沒改（下一步）。

## 2026-10-10（更正）規格書工作實際進度

日期：2026-10-10
開發者：GPT／Codex

- 更正前面交接與工作佇列可能造成的誤解：**本次沒有完成規格書更新，也沒有完成雲端正式版改版**。
- 實際只做過一小部分草稿操作：本機規格書曾暫改總表標題、加入 10-10 定案摘要、調整少數功能狀態；雲端正式版先建立副本，曾在副本加入補充段落並修正目錄標題。使用者發現範圍不符後，這些規格與雲端副本內容均已還原。
- 原始雲端正式版從未修改；目前尚未完成的工作仍包括整合全部 10-10 規格、資料分類／來源維護／畢業學分、流程圖重排與主線圖／DFD／ERD 更新。
- 本次真正完成的是 AI 會議室兩個小問題：導覽檔案面板步驟先開啟面板，以及通知配對「資料保存／操作紀錄」到張馨羽、「系統測試」到林承諺；已補測試，未提交、未推送。

## 2026-10-10（續 16）驗收 GPT 修好的 AI 會議室（ROOM-02）

日期：2026-10-10
開發者：Claude Code（只驗收，沒有改會議室程式）

- GPT 照修正清單一項一項提交（`a4bad88`～`fe5fbdd`，共 15 個），另外做了資料夾合併、小助手支援資料夾與貼上內容、簡約線條圖示、完整檔案檢視；開發時程改成實際時程（11/4、11/15 前 70%、12/5 前審核準備）。
- 驗證：會議室自動測試 **78 個全部通過**；瀏覽器驗收（測試資料夾＋埠號 8767）ROOM-01 的 32 項通過 31 項、ROOM-02 的 11 項全部通過。驗收腳本配合介面調整更新（資料夾圖示從 12 個精簡成 6 個、收合發言中的確認按鈕看不到），提交 `7a4eac7`。
- 發現 GPT 修完**沒有重啟真的會議室 8765**（仍是舊版，新功能網址回 404；使用者一直在用 GPT 的測試伺服器 8766）。確認沒有 AI 發言後已重啟成新版。
- 交給 GPT 的兩個小問題（寫在工作佇列）：導覽第 23、24 步沒有自動打開檔案面板；通知配對組員時「資料與紀錄」「系統測試」配給了組長，應分別是張馨羽、林承諺。

## 2026-10-10（續 15）學校官網資料盤點

日期：2026-10-10
開發者：Claude Code（只讀網站、寫報告，沒有改程式）

- 使用者請 Claude 逛資管科、學校官網、資圖中心，找出有用的資料。共約 41 個請求（首頁 3、子頁約 20、修業科目表 PDF 18），每次間隔 1～2 秒，只讀公開頁面、不登入、不送表單，原始頁面不存（PDF 除外）。
- 新增 `docs/02_需求與設計/03_審查與檢查/AI_檢查報告_學校官網資料盤點_2026-10-10.md`（提交 `085c938`，未推送）。重點：
  - **學校已經有**學生證照上傳管理、競賽活動報名系統、電子證書發證平台、微學分系統、服務學習課程記錄、實習週記管理系統、資管科畢業專題管理系統 → 本系統不重做，定位是**整合這些資料做備審、對照二技校系、導師確認**（11/4 簡報要說明）。
  - 可用資料：證照地圖（各學年證照與對應課程）、兩個課程模組（資訊軟體開發／資訊軟體應用）、健康照護資訊管理學程、專題與實習時程公告、課程檢核、資訊盃比賽（資管科 1–2 年級低年級組、3–5 年級高年級組，成績可申請 MOCC）、MOCC 認證科目；行事曆是 Google 日曆，頁面文字讀不到。
  - **續**：使用者說明學校首頁內嵌的 Google 行事曆已失效，確定的日期要查教務處行事曆（每學年一份 PDF）。下載 115 學年度一份確認文字讀得出期中、期末考與「成績上網登錄」期間，畢業班另有一段；提醒卡片改用成績上網登錄日期。使用者希望「好維修」→ 規格新增管理員端「資料來源維護」（來源失效標紅、換網址、手動輸入、寫操作紀錄），說明不是把 AI 會議室搬進系統。11/4 簡報「開發動機」補上組長親身經驗（學校各單位系統分散、新生不知道去哪查、茫然的學生容易被落下）。提交 `c2f62e7`。
  - **續（教務處）**：使用者發現教務處網站有表單可下載（讀了五年才知道，之前都花錢請行政單位印）。逛教務處首頁與三個組的表單頁，下載**學生用的 14 種表單**（PDF 與 DOC，38 個檔案、3.2MB）到 `school/public-sources/教務處表單/`，附 README 清單與原始連結；學報投稿與老師用的表單沒有下載；重補修單英文版 PDF 在學校網站上是 404。兩個檔名因括號被截斷，已改回完整名稱。另外查到教務處選單的「**學生學習歷程系統**」轉到舊網域 `portfolio.knjc.edu.tw`，20 秒連不上，**已失效**；寫進盤點報告與 11/4 簡報開發動機的佐證。提交 `05ca940`。
  - 使用者的想法：小助手抓回來後在系統內**重新分類**（主題、適用年級、類型、有效期間、來源），像 Discord 一樣瀏覽與搜尋，並供引導卡片與小助手使用；名單類公告只存標題、日期、連結。

## 2026-10-10（續 14）學校資料匯入與官網資料來源規格

日期：2026-10-10
開發者：Claude Code（只寫規格，沒有改程式）

- 使用者提供學生資訊系統的畫面結構（個人課表、歷年獎懲、本學期選課清單、歷年成績、缺曠記錄）與資管科官網、資圖中心網址。**截圖中的個人成績與請假資料沒有寫進任何文件**（已檢查規格檔）。
- 新增 `docs/02_需求與設計/02_設計規格/AI_設計規格_學校資料匯入與官網資料來源_2026-10-10.md`（提交 `27bd1d0`，未推送）。仍維持 10-06「不得用學生帳號登入或爬學校系統」。
- 使用者決定：成績＝**網頁成績貼上表格**（網路成績只開放約一週，引導卡片提醒）＋**紙本成績單 OCR**（組員完成、待整合），網頁成績標「僅供參考」；獎懲**多一種貼上表格**，和截圖並存；**缺曠記錄要收**（有些二技學校會看出缺勤）；資管科官網、資圖中心**照二技公告機制**，管理員核對後才給學生看；選課清單、個人課表不做。
- Claude 為缺曠記錄加的隱私保護（**待使用者確認**）：只存假別合計不存逐日明細、只有學生與導師看得到、不送給 AI、備審預設不放（學生勾選才放，且不放健康相關假別）。
  - **使用者確認並修改（提交 `e96c995`）**：只有學生與**班導**看得到，AI 和其他人都看不到；備審預設不放，學生勾選才放，**勾選後全部假別合計都放**（含健康相關假別），放之前提醒學生本人會放進哪些內容。只存合計照原案。
- 新增畢業學分檢查（成績對照官網修業科目表，接管理員的課程規則）與說明區「找誰問」分機表。
- 待使用者補充：期中期末網路成績開放時間、修業科目表在官網的位置。
- **續（使用者補充）**：網路成績在期中、期末考後約 1～3 週開放、只開放約一週；學校也會寄紙本成績單到家裡（錯過網路成績可改上傳紙本）。修業科目表在資管科官網，每個入學年度一份 PDF，「○○年度入學」對應學號前三碼。
- 使用者記得 GPT 之前「全部載下來」：查證後 09-17 只下載了列表頁（`school/public-sources/im-curriculum-planning.html`），PDF 沒有下載。依列表頁連結用 Python 補下載 18 份（99～114 年度入學修業科目表＋2 份替代課程對照表，每份間隔 1 秒，確認是 PDF 才寫檔）到 `school/public-sources/修業科目表/`，抽 111 年度第一頁確認是正確內容。README 與規格已更新，提交 `eab25be`，未推送。（第一次的下載指令含刪除失敗檔案的寫法，被安全檢查擋下、沒有執行，改成不需刪除的寫法。）

## 2026-10-10（續 13）流程圖依 10-10 定案更新；流程圖彙整簡報

日期：2026-10-10
開發者：Claude Code（只改圖與文件，沒有改程式）

- 盤點 GPT 之前做的 16 張圖＋4 張使用案例圖，對照 10-10 定案的四份規格：直接沿用圖 4、圖 10；小改圖 1～3、1-1、5、8、11、12、13、15、16；圖 9 換成新版；ERD（圖 14）補上已存在卻沒畫的電子獎狀、操作紀錄、每日 AI 用量，以及新的公告、已讀、段落註解（標「待新增」）；新增圖 17「二技招生公告與 AI 推薦校系」（前半段引用圖 8，避免重複）。
- 圖 6「行政表單」、圖 7「專題共同審查」（都是後續擴充）和定案衝突（收件暫停、科辦不審、專題模板隱藏），**待使用者決定**怎麼處理，這次沒改。
- 所有改過的圖用 Mermaid 工具輸出 PNG／SVG，使用案例圖用 `D-01-use-case-by-role.py` 重新產生；逐張看過圖片，修正兩處（圖 17 老師那格改成「四、五年級學生」、學生使用案例圖補上 TA 與社團證明）。`diagrams.md` 的原始碼與 `.mmd` 同步，加上「2026-10-10 定案後的流程圖基準」與圖 17。
- 簡報：`scripts/build_teacher_presentation.py` 目前只會產生流程圖頁，直接執行會把 10-07 那份 3MB 的完整討論簡報**覆蓋**，所以沒有執行。改成新增 `scripts/build_diagram_deck.py`（沿用同一套版面），輸出 `docs/08_簡報/AI_流程圖彙整_2026-10-10.pptx`：封面＋16 張最新的圖，每頁標規格書圖號，方便使用者抓圖貼到 Canva。10-07 討論簡報保留不動，當作當天紀錄。
- 本機提交 `7257b7c`，未推送。
- **續：圖 6、7 的處理（使用者決定）**：舊圖 6「行政表單數位化與申請追蹤」與圖 7「專題共同審查」從規格書移除，圖檔用 `git mv` 搬到 `docs/99_封存_歷史與待確認/03_舊版流程圖與圖片/`（不刪除），封存 README 寫明原因。使用者要求「**表單下載區也要有流程圖，可以詳細完整，但不能因為簡單不做**」：新增圖 6「科辦表單下載區流程圖」（`docs/images/D-20-form-download-flow.*`），包含科辦分類管理、新增項目、檔案檢查、發布、改版（舊版保留不能覆寫）、下架，學生與老師依開放對象下載、權限檢查（403）、小助手查表單，並註明收件暫停。規格書第三節改成這張圖，`diagrams.md` 與流程圖彙整簡報同步更新；圖號在更新規格書時統一重排。提交 `f44ab57`，未推送。

## 2026-10-10（續 12）引導卡片、科辦與管理員功能清單定案；拿掉舊的科辦審查流程

日期：2026-10-10
開發者：Claude Code（只寫規格，沒有改程式）

- 新增 `docs/02_需求與設計/02_設計規格/AI_設計規格_引導卡片與科辦管理員功能清單_2026-10-10.md`（已定案，提交 `7f40687`，未推送）。
- **使用者原則：功能寧可少，但不能缺。** 做了的功能都要完整可用；沒把握做完整的就不放進範圍並記錄原因。
- 引導卡片：依年級＋時間點＋學生做了什麼出現，首頁一次最多 3 張，做完自動消失；一年級從「歡迎、認識二技、存第一份成果」開始，學期末提醒上傳成績單；各年級方向依規格書附錄三。「怎麼操作」說明區＝每頁網頁導覽＋約 10 題常見問題（不用 AI）。
- 科辦：做＝核准電子獎狀、**TA 證明與社團證明併進電子獎狀（多兩種類別）**、二技公告與寄送備審日期提醒、表單下載區；不做＝表單收件、競賽報名、公假、器材點收；學生自己漏傳的獎狀不處理。
- 管理員：做＝帳號、班級導師、校系資料、招生資料 Agent、課程規則、二技公告核對發布、**操作紀錄查詢頁（新）**；**專題類型與需求模板先隱藏**（程式與資料保留）；一般公告之後再做。
- **拿掉的功能（使用者要求寫進日誌，避免日後報告又說「可以一起做」而變成做一半）**：科辦「登錄送件審查結果」（舊流程 `/staff/reviews/<id>/result`）。原因：2026-10-07 科助電話確認「備審資料導師看過就可以了」，科辦不看備審；留著會讓科辦角色矛盾、評審混淆誰審備審。開發時拿掉頁面與選單，**已存在的資料不刪除**。

## 2026-10-10（續 11）二技招生公告與 AI 推薦校系規格定案

日期：2026-10-10
開發者：Claude Code（只寫規格，沒有改程式）

- 新增 `docs/02_需求與設計/02_設計規格/AI_設計規格_二技公告與AI推薦校系_2026-10-10.md`（已定案）與流程圖草稿 `docs/images/二技公告與AI推薦校系流程圖_草稿_2026-10-10.png`（用 Mermaid 工具實際輸出確認）。
- 內容：AI 代理查資管相關二技校系、只存文字（資格、文件、時程、加權、申請連結、學校特色）→ 候選資料 → 管理員對照官方連結核對 → 核准並發布公告；學生（一～四年級看特色與推薦、想去的學校不限數量；五年級做備審最多 5 所）、老師（看到自己四、五年級學生並可提醒）、科辦（寄送備審日期、處理電子獎狀申請，學生漏傳的獎狀不處理）。接在現有招生資料 Agent 的候選與核准流程上；新增公告與已讀資料表。
- 使用者決定：查詢範圍先做資管相關科系；推薦用「規則算符合程度＋AI 寫理由」；每個來源只留最新一份簡章檔（擷取的文字與雜湊每次都保留）；老師看四、五年級；公告資料表做通用、這次畫面只做二技公告。
- 本機提交 `96d7d61`、`4c28dd7`，未推送。

## 2026-10-10（續 14）主持人圖釘圖示微調

日期：2026-10-10
開發者：GPT／Codex

- 依瀏覽器註解，把主持人區的圖釘改成更接近 Codex 介面的簡潔推針輪廓，保留主持人文字與換人功能。
- 驗證：非平行測試 **65 項通過**；Python 編譯、內嵌 JavaScript 語法與 `git diff --check` 通過。

## 2026-10-10（續 13）檔案目錄收合、圖示精簡與導覽同步

日期：2026-10-10
開發者：GPT／Codex

- 修正完整檔案工作區的操作語意：檔案目錄收合按鈕只控制左側資料夾欄；完整查看另有獨立的放大／縮小按鈕；「返回會議」明確離開完整模式。
- 恢復專案進度小助手的機器人圖示，避免介面過於單調。
- AI 讀過的、AI 讀取位置與預覽空白提示改用一致的簡約文件／讀取線條圖示。
- 資料夾建立的圖示選擇由十二個縮減為六個精選選項，保留創意但降低視覺負擔。
- 系統導覽同步改寫檔案目錄收合、完整查看與「開新會議」文字，避免導覽描述和畫面不一致。
- 通知鈴鐺維持紅色未讀圓點與通知數字；已確認既有通知刷新與已讀清除行為仍保留。
- 驗證：版面測試 **26 項通過**；Python 編譯、內嵌 JavaScript 語法與 `git diff --check` 通過。

## 2026-10-10（續 12）全介面簡約線條圖示與檔案模式切換修正

日期：2026-10-10
開發者：GPT／Codex

- 修正完整查看按鈕原本只會要求進入完整模式的問題，改為真正的切換：一般檢視按一次放大，完整檢視再按一次縮小回標準檔案檢視。
- 將 AI 會議室標題、全部會議、未分類、主持人、導覽、編輯紀錄、編輯、匯出、語音、搜尋條件與資料夾選擇等表情符號，統一改成共用的線條式圖示；保留文字名稱與滑鼠提示。
- 移除「＋ 開新會議」前面的加號，避免和其他新增按鈕混淆。
- 使用同一組 SVG 圖示來源，避免檔案區、工具列和資料夾列各自使用不同風格。
- 驗證：版面測試 **24 項通過**；Python 編譯、內嵌 JavaScript 語法與 `git diff --check` 通過。

## 2026-10-10（續 10）重新檢討小助手、上傳回饋、選校上限、二技公告

日期：2026-10-10
開發者：Claude Code（只寫規格，沒有改程式）

- 查證：10-07 指導老師錄音原話是「檔案格式由 AI 判斷……不是直接丟給他說錯誤、錯誤……確認的時候在旁邊，AI 就會在旁邊註記……因為你一定要本人確認」。使用者記得的「由老師確認再標出來」在現有逐字稿中找不到（可能是沒錄到的討論），已向使用者說明。
- 使用者決定（寫進小助手規格 10.7，提交 `ba8a644`）：
  - 小助手**不整個拿掉提問**：引導卡片＋不用 AI 的「怎麼操作」說明區＋限定範圍的 AI 提問（只答操作、科上規定、個人進度，附出處，算每日次數）。
  - 上傳回饋**照 10-07 錄音**：AI 在學生確認畫面旁註記可能原因與修改建議，學生本人確認；不能只寫「錯誤」、不用整片紅字。
  - 選校上限改成**一到四年級不限、五年級做備審時最多 5 所**，並加上「只是引導方向、隨時可換、五年級換校自傳要重寫」的提醒。
  - 二技招生資料由 AI 代理查詢、**只存文字**（連結、資格、文件、時程、加權），**管理員核對後才公告**給學生、老師、科辦；去年的 116 甄審 PDF 先當示範與比對資料。
- 待決定：AI 代理要查所有二技學校科系，還是先只查資管相關科系。
- 使用案例圖、系統架構圖等功能全部確定後再畫；科辦目前真正能用的功能只有核准電子獎狀，「收到二技公告後補證明」是新功能。

## 2026-10-10（續 11）檔案圖示統一、AI 讀取位置固定與切換檢視模式

日期：2026-10-10
開發者：GPT／Codex

- 依瀏覽器註解，把檔案功能移到主工具列原本匯出的位置；匯出移入「更多」，讓常用的檔案功能更容易找到。
- 檔案圖示統一改用簡潔線條圖示，工具列與檔案工作區的目錄按鈕使用同一個圖示與配色，並補上清楚的「展開／收起檔案目錄」說明。
- 新增固定的「AI 讀取位置」區塊，顯示 AI、檔案路徑與讀取行號；區塊可展開／收起，點檔名可直接開啟對應檔案。原本的檔案目錄仍保留「全部檔案」瀏覽模式。
- 完整查看按鈕改為同一個切換按鈕：一般模式顯示放大圖示，完整模式顯示縮小圖示，並同步更新按鈕說明與無障礙狀態；完整模式可覆蓋會議室與資料夾欄位。
- 驗證：版面測試 **22 項通過**；`git diff --check` 通過；JavaScript 語法檢查待收尾執行。

## 2026-10-10（續 10）會議室標題列、進度小助手與完整檔案工作區

日期：2026-10-10
開發者：GPT／Codex

- 依瀏覽器註解調整 AI 會議室左側標題列：專案進度小助手靠近「AI 會議室」標題左側，專案進度通知鈴鐺靠右，保留收合會議列表按鈕。
- 整理專案進度小助手的輸入區：單一／多文件上傳、整個專案資料夾選取、文件整理，以及貼上內容保存，各自分組並使用不同的按鈕色彩；甘特圖、分工表與關閉按鈕另成一組，降低誤按機會。
- 將檔案面板補成完整檔案工作區：新增像 Codex 的完整查看模式，保留目錄、分頁、搜尋、AI 讀取證據、原始檔下載與新分頁功能；完整模式可用「返回會議」、Esc 或醒目的「× 關閉檔案」離開。
- 更新系統導覽、會議室 README 與操作手冊，說明完整查看模式和離開方式。
- 驗證：版面測試 **19 項通過**；`git diff --check` 通過。完整測試與瀏覽器逐項驗收於本次收尾再執行；瀏覽器驗收若仍無法連線，必須在回報明確記錄，不得宣稱通過。
- 限制：完整查看模式是前端檔案工作區，不會把檔案上傳到外部服務，也不會自動叫 AI 發言或消耗額度。

## 2026-10-10（續 9）第 1 項功能定案：導師確認版本一致、雙版本顯示、段落註解

日期：2026-10-10
開發者：Claude Code（只寫規格，沒有改程式）

- 使用者決定：**先把功能和流程圖確定，再同步雲端正式版，最後才開發**。雲端正式版是 Google 文件「資管科智慧學習歷程系統－系統規格設計書（最終版）」，內容還停在初版（沒有 10-08 功能確認總表、資管科小助手、獎懲記錄、電子獎狀），等全部確定後再一次大改。
- 新增 `docs/02_需求與設計/02_設計規格/AI_設計規格_導師確認版本與段落註解_2026-10-10.md`（已定案）：只能確認送審的那一版（伺服器端檢查，不同版就擋下並請學生重新送審）、確認畫面同時顯示送審版與最新版、導師修改後提醒學生、像 Google 文件的段落註解；10 多條驗收標準。
- 使用者對四題的決定：學生**可以回覆**註解；註解可以按**「已處理」收起來**（不刪除、記錄是誰按的）；導師修改後在**自傳頁＋學生首頁**提醒，先不寄電子郵件；**和學生有關的老師都可以**加註解（顯示姓名與身分）。註解這次只做到段落（照建議）。
- 新版圖 9「導師確認流程圖」草稿：`docs/images/D-16-teacher-confirm-flow_新版草稿_2026-10-10.png`（用 Mermaid 工具實際輸出確認語法與版面；補回舊版「成績單、證照不經導師審核」的說明）。原本的圖 9 還沒覆蓋。
- 本機提交 `f13a73b`、`f09cc3a`，未推送。下一步：其他功能與流程圖逐項確定 → 更新本機規格書與 `diagrams.md` → 同步雲端正式版 → 開發。

## 2026-10-10（續 9）ROOM-02 修正清單與小助手多來源文件

日期：2026-10-10
開發者：GPT／Codex

- 依使用者確認，把 `development_plan.json` 改成實際時程：11/4 交簡報、11 月中完成 70%、12 月初專題審核；不再使用學長姐範例日期。
- 修正會議清單 API：抽出 `list_meetings()`，直接讀取 `*/meta.json`，依建立時間由新到舊排序。修正前錯誤是把已經是 `meta.json` 的路徑再接一次 `meta.json`。
- 專案文件改為保留相對子資料夾路徑；同名文件自動保存為新版本，不覆蓋舊版。操作紀錄移到 `project_documents_history.jsonl`，避免上傳名為 `history.jsonl` 的文件覆蓋紀錄。
- AI 最終功能確認按鈕只出現在真正的 AI 與會者，不再出現在 Claude 主筆或主持人發言上；確認紀錄與編輯紀錄分開，編輯版本不會因確認而增加。
- 搜尋篩選改為頁面內選擇清單，不再使用瀏覽器的輸入／提示跳出框。
- 新增資料夾拖曳合併：來源資料夾保留但清空，會議移到目標資料夾，並在資料夾歷史留下學號與移動清單。
- 專案進度小助手保留單一／多文件上傳，新增整個資料夾選取與文字貼上；資料夾保留相對路徑，貼上內容保存成文字文件。整理只在本機產生草稿，不自動叫 AI 發言、不消耗額度。
- 主要本機提交：`dce8eba`、`7a6d868`、`dc2b38a`、`a5d4803`、`84cacfd`、`45959fe`、`10ca044`；均未推送。
- 自動驗證：排除既有平行程序停止測試後，**54 項通過、13 項未執行**；`python -m py_compile server.py` 與 `git diff --check` 通過。完整測試為 **64 項通過、2 項既有平行程序停止測試失敗**，兩項在本環境約 60 秒後才結束，未列為本次功能回歸失敗。
- 瀏覽器驗收：依指定腳本準備 8767 隔離資料，但本機環境無法保持 8767 伺服器連線，腳本未取得有效結果；不能宣稱瀏覽器驗收通過，待使用者環境補跑。
- 待確認：`project_documents` 若要加入版本控制排除規則，仍需使用者另行決定；本次沒有新增或修改 `.gitignore`。

## 2026-10-10（續 8）11/4 簡報大綱：系統展望與團隊展望分開

日期：2026-10-10
開發者：Claude Code

- 使用者討論 AI 會議室的未來（手機 App、串 Discord、放進管理員後台）後決定：**現在保留本地端版本**，AI 會議室和手機／Discord 遠端開發屬於「我們組的展望」，不放進「系統未來展望」。
- Claude 建議不要放進專題系統的管理員後台：評審會混淆主題、正式系統會有執行 AI 程式的風險、上線後沒有 AI 登入、組員都要拿管理員帳號會打亂權限設計。Discord 串接留到 12 月初審核後再考慮。
- `docs/08_簡報/AI_檢查報告_學長姐專題簡報分析與1104大綱_2026-10-09.md`：第 20 頁「分工與未來展望」拆成第 20 頁「分工」、第 21 頁「系統未來展望」（只寫學習歷程系統）、第 22 頁「團隊展望：AI 輔助協作開發」（AI 會議室與之後的 Discord 構想，註明是開發工具、不屬於系統評分範圍）；全份改成約 22 頁（提交 `3622041`，未推送）。

## 2026-10-10（續 7）Claude 驗收 GPT 續 6 的會議室修改；修正清單交給 GPT（ROOM-02）

日期：2026-10-10
開發者：Claude Code（只檢查，沒有修改會議室程式）

- 檢查範圍：GPT 續 6 在 `ai-meeting-room` 還沒提交的修改（資料夾顏色、專案進度小助手、通知、本場搜尋、搜尋篩選、AI 最終確認、匯出、開發時程），以及 `docs/05_交接與專案管理/02_任務與檢查/AI_檢查報告_系統完整性_2026-10-10.md`。
- 驗證方式：會議室自動測試在使用者電腦上 **56 個全部通過**（GPT 回報的 2 個失敗是它環境的限制）；把 GPT 版本複製到暫存區、修好會議清單那一行後，用測試資料夾＋埠號 8767 跑瀏覽器驗收：ROOM-01 原本 32 項全部通過，新功能（專案進度小助手、通知、本場搜尋）打得開、能用。沒有碰真資料、沒有叫 AI。
- 查到的問題（詳見 `docs/09_AI會議室/01_實作計畫/AI_實作計畫_會議室修正清單_Claude驗收_2026-10-10.md`）：
  1. **會議清單 API 讀成 `meta.json\meta.json`**，重啟成 GPT 版本後左側一場會議都看不到（目前 8765 仍是舊版，正常）。
  2. 同名專案文件再上傳會把舊版蓋掉。
  3. 上傳名為 `history.jsonl` 的檔案會蓋掉操作紀錄。
  4. 「確認」按鈕出現在 Claude（主筆）發言上，按了被拒絕。
  5. AI 確認寫進編輯紀錄同一個檔案：畫面出現空白的修改紀錄，也會讓正在改會議名稱的人被誤擋。
  6. 搜尋篩選改回瀏覽器舊式跳出框。
  7. 專案文件存放位置寫死、會被推上 GitHub。
- 要問使用者：開發時程檔的日期是 GPT 自行編的（不是實際的 11/4、11 月中、12 月初），通知全部提醒田心于；資料夾合併還沒做。
- 系統完整性報告的錯誤：獎懲記錄、證明來源標籤、科辦電子獎狀 10-09 已合併進 `main`（`27f90b8`），報告卻寫「待整合」；漏掉「導師看到最新版、確認卻記成送審版」的已知漏洞。
- 更正 Claude 自己先前的驗收：ROOM-01「不在名單上的學號改不了會議」那一項當時是被 `X-Meeting-Room` 標頭擋下、沒有驗到學號；這次帶標頭補測，學號檢查確實有效。
- 使用者決定：**全部交給 GPT 修**。已在工作佇列登記 ROOM-02，並把瀏覽器驗收腳本放在 `docs/09_AI會議室/瀏覽器驗收腳本/` 讓 GPT 修完自己重跑。

## 2026-10-10（續 6）會議室搜尋與通知圖示、專題完整性只讀檢查

日期：2026-10-10
開發者：GPT／Codex

- `ai-meeting-room/static/index.html`：本場搜尋改為簡潔單色線性放大鏡 SVG；專案進度通知改為簡潔單色線性鈴鐺 SVG，保留 aria-label、通知紅點與原本行為。
- 導覽補上本場搜尋、專案進度小助手、專案進度通知三個入口，並新增 `docs/09_AI會議室/03_開發紀錄/AI_開發紀錄_搜尋通知圖示與導覽補充_2026-10-10.md` 作為本次工程紀錄。
- 資管科小助手本次只讀檢查，沒有修改 `ai` 專案程式碼；確認正式規格要求的引導式 Agent 尚未完全取代現有聊天式介面，列入與主持人討論的風險。
- 新增 `docs/05_交接與專案管理/02_任務與檢查/AI_檢查報告_系統完整性_2026-10-10.md`，記錄功能證據、時程優先順序、測試結果與評審風險。
- 驗證：`ai` 專案 `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=...` 為 **220 passed**；`ai-meeting-room` 重新使用全新暫存目錄測試為 **54 passed、2 failed**，失敗為平行發言無輸出程序未在 15 秒內停止（約 60 秒）。
- 待確認：小助手是否正式拿掉聊天框並改成流程卡片；會議室平行發言逾時問題；本次未推送、未執行 MySQL migration。

## 2026-10-10（續 5）會議室 ROOM-01 收尾：Claude 接手瀏覽器驗收與未完成部分

日期：2026-10-10
開發者：Claude Code（接手 GPT 的 ROOM-01）

### 一、為什麼接手

- GPT 完成第一版（提交 `743e415`）後回報：它的環境連不到本機網頁，**沒有用瀏覽器驗收**；重新下載副本驗收、導覽也沒做，並把工作改成「待使用者確認」。使用者在睡覺，希望睡醒前做好，所以由 Claude 接手。工作佇列已註明「GPT 請先不要動會議室」。
- GPT 說有 4 個平行發言測試失敗；在這台電腦上重跑全部通過，應該是它的沙盒不能強制結束程序，不是程式問題。

### 二、查到並修好的問題

| 問題 | 修正 |
| --- | --- |
| 新會議的專案資料夾其實還是存絕對路徑（`relative_to` 對旁邊的 `ai` 會失敗） | 新增 `repo_for_meta()`：同一層存 `../ai`；相對路徑一律以會議室資料夾為基準（`absolute_repo()`）；舊路徑找不到就找旁邊同名資料夾；系統訊息不再寫本機絕對路徑 |
| 編輯後的系統訊息寫「把title改成…」 | 改成「會議名稱／議題／目標」 |
| 搜尋：關鍵字在會議名稱裡時，整場會議每一則發言都被列出來 | 會議名稱／議題／目標符合只給一筆「會議資訊」，發言內容符合才列發言；片段改成關鍵字前後文；撤回的發言不列 |
| **搜尋一次要 3.5 秒**，結果晚一步才出現 | `speaker_name()` 每次都檢查三家 CLI 有沒有安裝；改成直接讀設定，降到 0.04 秒（也讓組會議紀錄變快）；前端丟掉晚到的舊結果 |
| 編輯視窗按「取消」也會存檔 | 取消直接關閉 |
| 搬會議要**手動輸入資料夾代號**；改名用雙擊＋跳出輸入框；編輯紀錄用 `alert` | 改成對話框點選；資料夾可拖曳搬移；編輯紀錄改前改後左右並排 |
| 右側只多一個小標題，說明文字仍換很多行 | 主持人、AI 與會者各一個框；名字與說明各一行，滑鼠移上去看全文 |
| 網頁導覽沒有更新 | 新增「資料夾」「搜尋」「編輯與編輯紀錄」三步，與會者那步改說明兩區；共 21 步 |
| 資料夾同時新增可能互相覆蓋 | 寫入加鎖 |
| 找不到專案資料夾的提示沒說怎麼辦 | 改成「請把專題資料夾（例如 ai）放在會議室資料夾旁邊」 |

- 資料夾欄改成像 Discord 伺服器列：🗂️ 全部、📥 未分類、各資料夾（圓形圖示、可選 12 種圖示）、最下面「＋」。仍然**沒有任何刪除功能**。
- 使用者截圖裡蓋住「Claude（獨立審查）」的機器人圖示**不是會議室網頁的東西**（網頁程式裡沒有），應該是其他程式（看起來像 Codex 桌面版）的浮動視窗。

### 三、驗證

- 自動測試：新增 6 個（相對路徑、舊路徑改找旁邊資料夾、中文欄位名、搜尋不重複、搜尋結果沒有本機路徑、名字查詢不檢查安裝）；**會議室測試 48 個全部通過**。
- **瀏覽器實際操作**（Playwright，測試用資料夾＋埠號 8767，沒有碰真的會議、沒有叫 AI）：32 項全部通過，包括右側兩框不溢出、說明一行、新增兩個資料夾、拖曳搬移、對話框搬移、切換資料夾與未分類、改名換圖示、歷史紀錄五筆、沒有刪除按鈕、重新整理後還在、取消不存檔、改名稱與目標、編輯紀錄兩筆並排、兩人同時改被擋下且打的字還在、搜尋標亮與跳到發言、`from:`、`in:`、找不到、Esc、窄視窗不溢出、導覽 21 步都指得到、沒學號關不掉進場視窗、不在名單的學號改不了、全程沒有網頁錯誤與舊式跳出視窗。截圖在 Claude 的暫存區。
- **重新下載驗收**：把會議室 `git clone` 到兩個別的位置（都沒有 `workspaces/`），一個旁邊有 `ai`、一個沒有，並把會議的專案路徑改成組員電腦上不存在的位置：旁邊有 `ai` 的自動找到並能開檔；沒有的顯示提示、不會壞掉。兩邊的會議、資料夾、搜尋、編輯紀錄都完整，沒有缺檔。
- 真的會議室伺服器（8765）確認沒有 AI 在發言後已重啟成新版。

### 四、注意與待確認

- 真的資料裡已經有一個資料夾「5」（10-10 04:21 用學號 111534105 在 8765 建立，不是 Claude 的測試）；依「不做刪除」原則保留，使用者要改名可以按 ✏️。
- 本機提交 `8dba7aa`、`31f28b7`、`b494bd5`（拿掉不小心提交的效能分析暫存檔）、`d36725b`，**都沒有推送**。

## 2026-10-10 ROOM-01：資料夾、編輯歷史、搜尋與與會者版面

日期：2026-10-10
開發者：GPT／Codex

- 已先把工作佇列的 ROOM-01 改為「進行中」，範圍只修改 `ai-meeting-room` 與本專案的文件紀錄。
- `server.py` 新增隔離資料目錄環境變數、相對專案路徑解析、資料夾新增／改名／搬移與不可刪除的歷史紀錄、會議名稱／議題／目標編輯、版本衝突阻擋、跨會議搜尋與 `from:`、`in:`、`has:附件`、`before:`、`after:` 篩選。每次修改都檢查組員學號，歷史檔只追加。
- `static/index.html` 新增資料夾列、搬移入口、會議搜尋結果面板、編輯與編輯紀錄入口，並在右側明確分成「主持人（專題組員）」與「AI 與會者」兩區；沒有新增任何刪除會議、資料夾或發言的功能，也沒有改寫既有發言內容。
- 新增測試資料目錄用的 `MEETING_ROOM_DATA`；新增 `meetings/folders.json`，確保資料夾資料會被版本控制追蹤。檔案面板回傳與顯示的來源路徑改為相對表示，不露出本機絕對路徑。
- 測試結果：ROOM-01 新增行為測試 4 項通過；版面與預覽測試 7 項通過，共 11 項；Python 編譯通過；內嵌 JavaScript 語法檢查通過。
- 瀏覽器驗收：已嘗試以隔離測試伺服器 `8766` 開啟本機瀏覽器，但本工作環境的瀏覽器無法連到工作區的本機埠，回報連線逾時；因此尚未取得瀏覽器截圖，也沒有把測試資料寫進真的會議。
- 本次尚未完成：完整瀏覽器實機操作、重新下載副本驗收、README／操作手冊／導覽逐步點驗、最終完整測試、8765 重啟與本機分項提交。暫不宣稱 ROOM-01 完成。

## 2026-10-10（續 4）交給 GPT 的會議室工作 ROOM-01；會議室本機提交

日期：2026-10-10
開發者：Claude Code

- 使用者要睡約 12 小時，請 GPT 接手會議室改版。Claude 依使用者要求整理成約 5 小時的計畫：`docs/09_AI會議室/01_實作計畫/AI_實作計畫_會議室版面整理_資料夾_編輯歷史_搜尋_2026-10-10.md`，並在工作佇列登記為目前工作 ROOM-01。
- 內容：右側與會者分成「主持人」「AI 與會者」兩區、浮動圖示不能蓋住內容；像 Discord 伺服器的會議資料夾與搬移；改會議名稱／議題／目標並記錄是誰改的歷史版本；像 Discord 的搜尋（`from:`、`in:`、`has:附件`、日期）；路徑改成相對路徑並實際用重新下載的副本驗收；更新網頁導覽、操作手冊、README、日誌。
- 使用者規則寫進計畫：不做刪除功能（專題結束後再刪）、只測修改過的地方但要真的開瀏覽器邊測邊修、不推送。Claude 另外加上：不改發言內容、不花 AI 額度、測試用另外的資料夾與埠號、不動 `ai` 專案程式碼。
- 為了讓 GPT 有乾淨的起點、做壞也能對照，先把會議室目前所有變更在本機提交為 `b603025`（GPT 的文件預覽與三欄版面、學號進場、輪流／同時發言、單獨停止、逾時修正、`meetings/` 共同記憶）。提交前掃描金鑰與密碼：只找到一段 PDF 工具說明裡的範例文字，沒有真的金鑰。**沒有推送。**

## 2026-10-10（續 3）AI 會議室：可切換輪流／同時、單獨停止某一位 AI、沒輸出自動停

日期：2026-10-10
開發者：Claude Code

### 一、使用者決定

- 「同時發言」同一圈看不到彼此，要反駁得再輪一圈，太花 token。改成**每場會議可以切換，預設「輪流」**：後面的 AI 看得到前面的發言，同一圈就能反駁；趕時間再切成「同時」。
- 停止按鈕**兩種都要**：每位 AI 自己的「⏹」只停那一位；原本的按鈕改名「⏹ 全部停止」。

### 二、修改內容（`ai-meeting-room`）

- `server.py`：
  - 新增 `speak_mode()`（會議設定 `mode`：`turns` 輪流，預設；`together` 同時）、`update_settings()`（把原本寫在網址處理裡的設定搬出來，換發言方式時在會議裡留系統訊息）。
  - 新增 `stop_one()`：只停掉指定的 AI，還沒輪到的就從隊伍拿掉，其他人照常發言，最後仍由主筆整理。停止的 API 有指定 AI 就只停那一位，沒指定就全部停止。
  - 輪流模式一次只叫一位，每位開始時才讀會議紀錄，所以看得到前面的發言。
- `agents.py`：看門狗改成同時檢查「總時間 15 分鐘」和「超過 5 分鐘完全沒有輸出」（`IDLE_LIMIT = 300`），沒輸出多半是被限流在重試，不用等滿 15 分鐘。只算標準輸出，錯誤輸出裡的重試訊息不算。
- 前端：「＋」選單的設定多了「發言方式」；每位 AI 的「正在輸入」泡泡和右側欄都有自己的「⏹」；頁面導覽、README、操作手冊同步改寫。

### 三、驗證

- 先寫測試再改：新增 6 個測試（預設輪流且後面的 AI 看得到前面的發言、輪流時單獨停掉一位其他人照常並請主筆、同時發言時單獨停掉一位另一位仍在輸入、切換發言方式、沒輸出自動停、持續有輸出不會被停）。修改前 6 個都失敗；修改後**會議室測試 36 個全部通過**。
- JavaScript 語法檢查、Python 編譯檢查通過；已重啟會議室伺服器，頁面有新的設定與按鈕。既有的審查會議沒有設定，自動用「輪流」。
- **還沒做**：在瀏覽器實際按單獨停止、真的三家 AI 輪一圈（會花額度）。
- 注意：5 分鐘沒輸出就停，是假設三家 AI 思考時都會持續輸出事件；若之後發現 GPT 想很久被誤停，可調高 `IDLE_LIMIT`。

## 2026-10-10（續 2）AI 會議室：三位 AI 同時發言；15 分鐘上限真的會生效

日期：2026-10-10
開發者：Claude Code

### 一、同時發言（使用者要求，像 Discord 一樣誰先想完誰先貼）

- 起因：Gemini 被限流時會默默重試，看起來卡住 15 分鐘，排在後面的 AI 都要等。
- `server.py`：輪一圈時，主筆之前的 AI 各開一個執行緒同時開始；全部說完（或逾時、被停止）才換主筆整理。`live`、`processes` 改成依發言者分開記；新增 `speaking_now()`（API 的 `speaking` 改成清單）、`stop_all()`（「⏹ 停止」會停掉全部）。程式剛啟動那一刻按停止也會被停掉。
- 前端：同時顯示多位「正在輸入」的泡泡；下方一行列出所有正在輸入的 AI；右側欄各自顯示「發言中… N 秒」。
- `post.py read` 配合 `speaking` 改成清單。
- 代價（已向使用者說明）：同一圈裡 AI 看不到彼此的發言，要互相反駁就再輪一圈；主筆整理時看得到全部。頁面導覽、README、操作手冊、「AI 正在發言中」的系統提示都改了說法。

### 二、修正：15 分鐘上限沒有生效、錯誤輸出互相卡死（`agents.run()`）

- 以前先把標準輸出讀到結束才 `wait(timeout=900)`，AI 不輸出也不結束時會一直等；錯誤輸出到最後才讀，Gemini 大量寫重試訊息時緩衝區滿了兩邊卡死。
- 改成：錯誤輸出另開執行緒邊讀邊丟（只留最後 20 行，錯誤訊息用最後一行）；計時器時間到呼叫 `kill()`（Windows 用 `taskkill /T` 連子程序一起停），錯誤訊息寫「超過 15 分鐘還沒說完，已強制結束」。

### 三、驗證

- 測試驅動開發：新增 `tests/test_parallel_turns.py` 7 個測試（不輸出的 AI 時間到被停掉、大量錯誤輸出不卡死、錯誤訊息用錯誤輸出的最後一行、一位卡住時其他人的發言先出現、三位同時列在「正在輸入」、停止會停掉全部且不換主筆、全部說完才請主筆）。修改前第一個失敗、錯誤輸出那個直接卡住；修改後 **會議室測試 30 個全部通過**。
- JavaScript 語法檢查、Python 編譯檢查通過；已重啟會議室伺服器，API 回傳新格式。
- **還沒做**：用真的三家 AI 在瀏覽器實際輪一圈（會花額度，等使用者要開會時一起看）。變更還沒提交，依交接和其他會議室變更一起提交、推送。

## 2026-10-10（續）會議室用學號進場；取消目標後仍可看自傳版本

日期：2026-10-10
開發者：Claude Code

### 一、AI 會議室：主持人＝專題組員（使用者要求）

- 新增 `ai-meeting-room/members.json`：111534105 田心于（組長，整合全部內容）、111534107 張馨羽、111534124 林承諺（姓名與分工依正式規格書第 969–977 行）。
- 第一次打開會議室要輸入學號，只接受名單上的組員；主持人發言記下學號（`member`），畫面與 AI 讀的會議紀錄都寫「主持人 ○○○」。以前沒有學號的主持人發言算組長的。
- 右側「與會者」最上面置頂三位主持人，組長排第一；「換人」可以重新輸入學號。
- 後端：`agents.load_members()`、`message_speaker()`；`server.host_say()` 擋下不在名單上的學號。
- 會議室 README 補上說明，並更正「資料」一節：`meetings/` 與 `members.json` 會推上 GitHub（`ai-meeting-room` 是私人儲存庫）。
- 驗證：會議室測試 23 個全部通過（新增 4 個）、JavaScript 語法檢查通過；重啟伺服器後用 API 確認名單讀得到、不在名單上的學號被擋下。

### 二、會議 `20261009-185407` 複查

- 使用者按的「全部輪一圈」沒有送到伺服器（紀錄裡沒有系統訊息），重啟伺服器後由 Claude 代按（#61）。

### 三、取消目標後仍可看自傳版本（使用者決定，提交 `b103585`，已在 `main`）

- 版本頁允許已取消、但留有自傳的校系，顯示「這是已取消的目標校系」（唯讀）；目標校系頁列出「已取消的目標（自傳紀錄保留）」連結。
- 驗證：220 個全部通過。

### 四、推送

- 使用者決定：這些做完再推 `ai` 的 `main` 與會議室（含 `meetings/` 歷史紀錄）。MySQL 資料庫遷移執行前要先備份並再確認。

## 2026-10-10 小助手「確認與版本」審查修正、合併回 main；文件歸位

日期：2026-10-10
開發者：Claude Code

### 一、會議收尾（AI 會議室 `20261009-185407`）

- GPT 的收尾發言（#57）被中止，主持人 #54 的三個回答沒有人整理。Claude 在 #58 補上收尾：解釋「導師看到舊頁面」、對照 `school/Documents/116二技技優甄審_時程與備審加權_修訂版.pdf`（備審寄件是 4/20–4/24，4/30–5/6 是甄審）、列出入學學年度的四種確認方式。
- 主持人決定（#59）：**入學學年度由管理者匯入**，學生不能自己填。修完 4 項才合併（#54）。

### 二、審查必修 4 項（分支 `feat/assistant-confirm-versions`，提交 `b081f8a`）

| 項目 | 修正 |
| --- | --- |
| P0-1 送出後改經歷不用重新確認 | 經歷改過內容一律回到未確認（含舊流程 `submitted`），按「儲存並確認」才算確認 |
| P0-2 導師可能確認到沒看過的內容 | 確認時檢查：送審仍在等待、是最新一筆、導師頁記住的快照時間 `taken_at` 沒變；學生已送新一筆時不能撤回舊的（避免兩筆等待確認） |
| P0-3 舊頁面存檔蓋掉新版本 | 存檔前檢查是不是最新版，否則回 409，顯示最新版並列出剛才沒存到的文字 |
| P0-4 學生自填入學學年度可假裝高年級 | 移除學生自填；管理者在「帳號管理」貼上「學號,入學學年度」匯入，每次變更寫 `audit_logs`；帳號列表顯示誰還沒填 |
| P1 額度用完會把整個資料庫工作階段的變更全部復原 | 改成只丟 `QuotaExceeded`，不影響呼叫端其他變更 |

- 導師頁的提示改用代碼對照，不把網址裡的文字直接顯示在頁面上。
- 驗證：新增 10 個測試；**219 個全部通過**；展示資料走查腳本（含「導師舊頁面按確認被擋下」「舊頁面存自傳被擋下、打的字還在」「管理者匯入」）全部通過。仍**沒有用真的瀏覽器操作**。

### 三、文件整理（GPT 10-10 新增的文件）

- 會議室相關 6 份移到新資料夾 `docs/09_AI會議室/`；審查結論移到 `docs/02_需求與設計/`。
- GPT 的交接摘要併入 `docs/05_交接與專案管理/AI_交接_新對話起點_2026-10-08.md`（改成 10-10 版，只留這一份），原檔封存到 `99_封存_歷史與待確認/01_舊版交接與對話/`。
- 開發日誌：GPT 10-10 的 6 節原本寫在最下面，已移到最上面並改成最新在上；檔案路徑一起更新。
- `docs/README.md` 更新索引。

### 四、待確認

- 學生取消目標校系後，看不到那個校系的自傳版本紀錄（資料保留，導師看得到）。要不要讓學生也看得到，請使用者決定。
- 「專一可以用認識科系的 AI」還沒實作（屬於之後的步驟）。
- 資料庫遷移 `e6c1a3b8f215` 還沒在 MySQL 執行；`main` 還沒推送。

## 2026-10-10 新對話交接準備

- 新增 `AI_交接摘要_新對話起點_2026-10-10.md`（10-10 已併入 `docs/05_交接與專案管理/AI_交接_新對話起點_2026-10-08.md`，原檔封存），集中記錄目前三個專案、AI 會議室、備份（`backup`）分類、已完成功能、驗證證據、未推送項目與下一步。
- 本次只新增交接文件，未建立新的 Git 對話任務、未刪除／移動專案、未提交也未推送。

## 2026-10-10 外部路徑與專題備份整理

- 新增 `D:\democase\backup\專題素材\錄音`，複製 OneDrive 專題錄音資料夾與 「下載」資料夾中的指定錄音；原本位於 `D:\democase` 內的專案、工作樹、備份均未刪除、未移動、未覆寫。
- 新增 `D:\democase\backup\環境清單\外部路徑與備份原則.txt`，區分可備份素材、不可直接複製的個人執行環境，以及 USB／Google Drive／GitHub 的備份界線。
- `scripts/transcribe_project_recordings.py` 與 `scripts/transcribe_meeting_audio.py` 已改用 `D:\democase\backup\專題素材\錄音`，不再依賴 `C:\Users\lisa2` 的 OneDrive／「下載」資料夾路徑。
- 會議室提示與操作手冊的舊範例 `D:\專題\ai` 已統一改成 `D:\democase\ai`。
- 未複製 `C:\Users\lisa2\.codex`、`C:\Users\lisa2\.agents` 或個人 Codex 設定；這些可能含登入狀態、存取權杖、對話、附件或快取。
- 注意：錄音可能含個資，不應直接公開到 GitHub；完整 `D:\democase` 可做 USB／Google Drive 受控或加密備份。

## 2026-10-10 檔案面板來源路徑文字顯示

- 檔案面板來源提示新增實際 `source_path`：歷史快照會顯示 `workspaces/<meeting-id>` 的路徑，沒有快照時會顯示 `meta.json` 指定的專案路徑。
- API 的檔案樹與檔案預覽都回傳來源路徑；前端以「來源類型＋路徑」的純文字提示呈現，讓組員能直覺判斷目前看到的是歷史版本還是目前專案。
- 驗證：相關測試 **10 個全部通過**；完整測試與語法檢查於本次收尾執行。
- README 補充三個儲存庫 依固定 `D:\democase` 結構放置時的跨電腦行為，以及公開 `meetings/` 的人工敏感資料檢查責任。
- 驗證：來源選擇與缺失情境測試 **5 個全部通過**；完整測試 **19 個全部通過**；Python 編譯檢查、內嵌 JavaScript 語法與 `git diff --check` 通過。

## 2026-10-10 會議檔案面板：歷史快照優先與沒有快照時改讀專案路徑

- 新增後端 `preview_root()`：若 `workspaces/<meeting-id>` 存在，檔案樹、文件預覽、原始檔下載與讀取證據都使用歷史快照；若不存在，才驗證會議 `meta.json` 的 `repo` 目錄並讀取目前專案。
- 改讀專案路徑時，API 會回傳 `source: project` 與明確提示；前端檔案面板新增來源提示，區分「歷史程式碼快照」與「目前專案資料夾現況」。找不到兩者時也保留會議文字與原始輸出，並顯示缺失原因。
- AI 實際發言時沒有改讀專案路徑，仍固定傳入 `WORKSPACES/<meeting-id>`，維持 AI 與真正專案根目錄的隔離。
- `.gitignore` 已移除 `meetings/` 忽略規則，讓已確認可公開的完整會議記憶可以被版本控制；本次只調整追蹤規則，沒有推送到 GitHub。

## 2026-10-10 AI 會議室文件預覽與版面改版

- 文件面板現在區分原始預覽與文字抽取：PDF 直接嵌入原始頁面，DOCX／XLSX／PPTX／ODF 顯示帶來源位置的抽取文字，並保留新分頁與原始檔下載。
- 左側會議列表、中央檔案面板、右側與會者欄加入收合與拖曳寬度控制；收合狀態與欄寬保存，中央對話區不再因拖曳被擠壞。
- 新增 `document_extract.py` 與選用的文件解析套件清單；缺少依賴時顯示明確錯誤，OOXML／ODF 有只用標準庫的備援做法；附件可讀文字也會傳給 AI 的提示詞。
- 驗證：11 項直接檢查、內嵌 JavaScript 語法、Python 編譯檢查均通過；PyPI 安裝因 DNS 限制未完成，詳見 `docs/09_AI會議室/03_開發紀錄/AI_開發紀錄_文件預覽與版面改版_2026-10-10.md`。
- 追加修正：補回遺漏的 `#leftResize` DOM 元素；原內容未刪除，是初始化錯誤導致列表與會議未載入。左右收合後保留邊界展開把手。
- 再追加修正：保存在元素上的欄寬曾蓋掉收合 CSS，已改用收合狀態的 `width: 0 !important`，並新增回歸測試；目前 12 項檢查通過。
- 窄視窗修正：右側與會者欄在 `max-width:900px` 預設收合，保留 `>` 把手可打開成浮動欄；檔案面板改為全寬浮層，避免中間對話被擠成直條。
- 實機重整確認資料仍在；內容空白是重整後尚未重新選取會議，不是紀錄遺失。舊後端程序也會讓新版文件預覽看起來像未生效，需重啟會議室後端再重新整理。
- 本次驗證：Python 編譯檢查與文件／布局靜態檢查通過；pytest 因目前環境未安裝 pytest 未能執行。未合併、未推送、未執行資料庫遷移。
- 後續已安裝 `pytest 9.1.1`；指定本專案測試目錄執行後為 **13 個全部通過**。未指定路徑會連同 `workspaces/` 歷史快照收集，造成快照的 `app` 匯入錯誤，因此使用 `python -m pytest tests -q`。
- 已安裝文件預覽依賴 `pypdf`、`python-docx`、`openpyxl`、`python-pptx`、`odfpy`；實測同一快照的 PPTX 可抽出 36 張投影片、PDF 可抽出 36 頁。
- PDF 預覽改為同時呈現原始頁面與 AI 抽取文字／來源位置，避免瀏覽器內嵌 PDF 空白造成無法確認 AI 讀取內容。
- PPTX 預覽改為投影片畫布，依投影片比例放置文字方塊與圖片；抽取文字移到可展開的查核區。實際 36 張簡報均產生投影片畫面資料，測試為 **14 個全部通過**。
- 開啟 PDF／PPTX 時自動收起檔案目錄以增加預覽寬度；按 `🗂` 可恢復目錄，保留檔案切換能力。
- 修正閃爍與誤解：不再於開啟 PDF／PPTX 時自動隱藏檔案目錄，改由 `🗂` 明確切換；AI 讀取證據改為醒目、可展開、限制高度的查核卡。
- `.doc` 增加 pywin32／Microsoft Word 備援做法；若舊式格式仍無法由 Word 開啟，保留原始檔下載與清楚錯誤說明。驗證為 **14 個全部通過**。

## 2026-10-10 AI 會議室導覽與 Gemini 回應診斷

- 導覽新增多模型群組互審、Superpowers 頭腦風暴、會議主題 `ⓘ`、600 秒疑似卡住提示，以及額度提醒 `×` 關閉行為說明。
- 查證 `20261009-230524` 的 Gemini 確實曾被主持人中止；`20261009-185407` 則已在 2026-10-10 00:01:36 完成第 #55 則回答，但因 9 次工具查詢與改用備援模型，耗時約 17.45 分鐘。
- 本次只更新 AI 會議室前端導覽與測試，未修改後端 Gemini 執行策略、未合併、未推送、未執行資料庫遷移。
- 詳細證據與後續風險見 `docs/09_AI會議室/03_開發紀錄/AI_開發紀錄_會議室導覽與Gemini診斷_2026-10-10.md`。

## 2026-10-09（續）完成小組 main 合併；資管科小助手第 1 步「確認與版本」

日期：2026-10-09
開發者：Claude Code

### 一、小組儲存庫合併（使用者同意提交與推送）

- 重跑測試 181 個全部通過，小組 `main` 沒有新提交；合併提交 `acac34e`。
- 推送：小組 `smart-learning-portfolio` 的 `main`（`056382f..acac34e`，快轉）、個人 `smart-learning-portfolio-solo` 的 `feat/main-line-3`。
- 更正交接文件：`feat/award-records` 其實已經合併進 `main`。

### 二、資管科小助手第 1 步（分支 `feat/assistant-confirm-versions`，未推送）

計畫：`docs/02_需求與設計/03_審查與檢查/AI_實作計畫_資管科小助手_確認與版本_2026-10-09.md`。使用者本次決定：**經歷要按「確認」才算學生已確認**。

| 項目 | 做法 |
| --- | --- |
| 只引用已確認資料 | `build_facts()` 只收 `confirmed` 的成績與證照、按過確認的經歷（`confirmed`；舊流程的 `submitted` 也算） |
| 經歷確認 | 經歷卡片「確認內容正確」按鈕；表單「儲存並確認」／「先存成草稿」；修改後回到未確認；獎懲記錄匯入（學生已逐列勾選）直接算確認 |
| 年級限制 | 沒有入學學年度時擋下，學生可自己補一次；不能填比目前年級高的成績與經歷；專一不能送審、不能用 AI 寫自傳（`MIN_REVIEW_GRADE=2`） |
| 目標校系 | 同時最多 5 所（`TARGET_LIMIT`），只算最新學年度；舊學年度目標另列、可刪除 |
| 送審快照 | `PackageReview.snapshot_json`：事實清單、自傳版本、完成度；等待中再送會更新同一筆，確認後再送會新增一筆 |
| 導師確認與撤回 | 確認、請學生修改、撤回都寫 `audit_logs`；撤回要填原因；導師頁顯示和上次確認版本的差異（例：新增乙級證照）與「學生已取消這個目標」 |
| 自傳版本 | 每次 AI 產生、學生儲存、導師修改都新增一版（記錄第幾版、誰、從哪一版改）；版本頁逐字標出新增與刪除；導師可直接改文字、留段落意見 |
| 每日用量 | 新表 `ai_daily_usage`；學生用學校金鑰每天 5 次（自傳、獎懲記錄讀取）；AI 失敗不扣次；用自己的金鑰或示範模式不計次 |

- 新資料庫遷移 `e6c1a3b8f215`（`package_reviews.snapshot_json`、`ai_daily_usage`）：只在 SQLite 測過升降級，**還沒在 MySQL 執行**。
- 順手修正：`AuditLog.id` 是 BIGINT，在 SQLite 不會自動編號（以前從沒寫入過），改成 SQLite 用 INTEGER，MySQL 不變。
- 舊測試調整：3 個測試直接建立草稿經歷又預期進自傳、1 個測試的學生沒有入學學年度，依新規則補上「已確認」與學生資料。
- 展示資料：王小明的「校園黑客松」留成未確認；林小美的送審有快照。
- 驗證：新測試 29 個；用展示資料寫腳本走完「確認經歷 → 第 6 所被擋 → 自傳 → 送審 → 導師確認 → 新增乙級證照 → 再送審看到差異 → 導師改自傳 → 撤回 → 取消目標」，全部符合。**沒有用真的瀏覽器操作過畫面**。

### 三、待確認

- `MIN_REVIEW_GRADE=2`（專二起可送審、用 AI 寫自傳）是暫定值。
- 學生自己補入學學年度只能補一次；管理者修改的介面之後再加。

## 2026-10-09（深夜）推上 GitHub、合併小組 main（已完成，見上一節）

日期：2026-10-09
開發者：Claude Code

### 一、推送（使用者選「會議室＋專題小組＋個人儲存庫」）

- 推之前掃描金鑰、密碼、`.env`、會議紀錄與個人設定：沒有。
- AI 會議室：`ai-meeting-room` 的 `main` 從 `cc70751` 推到 `224186c`。
- 專題：本機 `main`（`d5b711a`）和小組儲存庫的 `main` 已經分岔，所以先推成新分支 `feat/main-line-3`，小組儲存庫和個人 `smart-learning-portfolio-solo` 各一份，沒有動任何 `main`。

### 二、合併小組 main

- 小組 `main` 多出的 2 個提交（09-29：678258b 協作基線、056382f `/health`）是使用者本人（學號 111534105）推的。
- 試合併有 26 個衝突檔，都是同一批功能的兩個版本（例如 `student.py`、`learning_profile.py`、`config.py`），本機版本較新。
- 小組新增的 11 份文件，本機在整理文件時已移到 `99_封存`。比對後內容相同或本機較新（已含 09-29、10-06 需求修正），所以不放回舊位置。
- 只保留小組獨有的 `/health` 健康檢查（`app/routes/main.py`）和 `tests/test_health.py`。
- 驗證：`pytest` 181 個全部通過（原 180 個＋`/health` 測試）。第一次跑出 105 個錯誤，是 pytest 無法寫入系統暫存資料夾（權限），不是程式問題；加上 `-p no:cacheprovider --basetemp=<可寫資料夾>` 後全數通過。
- **合併尚未提交**：自動權限檢查把「提交／推送到小組 `main`」判為修改共用資源而擋下，等使用者同意。下一個對話先處理（見交接文件第四點）。
- 組員 111534107 正用小組舊 `main` 開發成績單 OCR。建議在獨立分支、OCR 邏輯放新檔，之後再合併。

### 三、交接

- 更新 `docs/05_交接與專案管理/AI_交接_新對話起點_2026-10-08.md` 第四到六點：合併待辦、已推送內容、小助手規格全部定案、11/4 簡報、其他待決。

## 2026-10-09（夜 5）AI 會議室：可以換主筆；小助手三題回答

- 使用者看到 Claude 的 5 小時額度剩 55%，要求把主筆交給 GPT。會議室原本「每一圈最後整理」寫死是 VS Code 裡的 Claude，所以新增「換主筆」：
  - 「＋」選單最下面新增「主筆」選單（會議設定 `chair`），可以選 Claude（VS Code）或任何一位已安裝的 AI；換人時會記一則系統訊息。
  - AI 主筆在每一圈不另外發言，只在最後用主筆指示 `CHAIR_TASK` 整理（逐條處理意見、定案表格、最多 3 題待決），字數上限加倍；`@主筆` 會叫到目前的主筆。被禁言或離席時自動退回 Claude（主筆）。
  - 與會者標示「📝 本場主筆」，主筆的發言加「📝 主筆整理」標籤。修正設定 API：只改有送來的欄位（原本只送主筆會把自動回答重設）。
  - 驗證：用假的 AI 模擬：GPT 當主筆時一圈的順序是 Gemini → Claude（獨立審查）→ GPT（主筆）；`@主筆` 叫到 GPT；換回 Claude 後恢復原本流程。用 Playwright 在網頁切換，與會者標示正確，網頁沒有錯誤。已在「資管科小助手計畫・第 2 輪審查」換成 GPT 主筆。
  - 同步更新：操作手冊第九節、README、導覽第 ⑧ 步。
  - **事故**：補導覽第 ⑧ 步文字時，字串裡混進了真的換行，造成 JavaScript 語法錯誤，整個網頁載入失敗（使用者重整後看不到會議、與會者和額度）。資料沒有遺失，修正後恢復。之後每次改網頁都要先用 `node --check` 檢查語法，再用 Playwright 重新載入確認。
- 小助手三題（使用者在 VS Code 回答，寫進規格 10.5）：
  - 專一可以用「認識科系、看學校要求」的 AI，算進每天 5 次，用完提示貼自己的金鑰。
  - 11/4 簡報沒有指定範本，參考學長姐的簡報。
  - 基本檢核是科上的標準，新版在正式規格書第 331 行。

## 2026-10-09（夜 4）讀學長姐專題、11/4 簡報大綱

- 主持人要求讀完所有學長姐專題（不只一份）。用 Google Drive 連接器唯讀讀了 5 個專題的 8 份簡報與報告，其中軟丙軟乙的簡報都是圖片，改讀它的成果報告書。
- 重要發現：114「升學競賽全方位資源網」和我們幾乎同題。它的期中審查委員建議「自動推薦二技科系」「自動產生備審初稿」，他們沒做到，正好是我們小助手的步驟 ② 和 ④。
- 整理出學長姐簡報的共同結構、審查委員在意的事（展示不要出錯、不要把簡單的事複雜化、角色要清楚），以及 113 的「系統基本檢核」表。
- 產出 `docs/08_簡報/AI_檢查報告_學長姐專題簡報分析與1104大綱_2026-10-09.md`，內含約 20 頁的 11/4 簡報大綱。
- 小助手規格新增 10.5：主持人確認 (甲)，以及舊學年度校系不占名額、沒填入學學年度時擋下等補充定案。
- 仍待主持人確認：專一能不能用認識科系的 AI；11/4 簡報範本與頁數；基本檢核表是否為科上標準。

## 2026-10-09（夜 3）小助手第 2 輪審查：主持人回答兩題

- 主持人在會議 #31 回答：導師每個校系分開確認；選校系先限「同時最多 5 所」；11/4 交的是專題報告簡報，請參考雲端資料夾的學長姐作品。
- 三位 AI（#32～#34）回應後，主筆 #36 整理定案，寫進規格 10.4：刪除的目標校系保留送審紀錄、自傳維持一個校系一份、不做依校系各寫一份摘要、年級用既有 `current_grade()`，並列出 4 條可自動測試的驗收。
- 雲端資料夾已用 Google Drive 連接器確認可讀：5 個學長姐專題（含 115 招生平台的「專題進度」簡報與報告書）。
- 仍待主持人確認：「下一年級可以看但不能用」是否指(甲)；11/4 簡報大綱待主筆讀完學長姐簡報後提出。

## 2026-10-09（夜 2）AI 會議室：檔案面板（看 AI 讀了什麼）

日期：2026-10-09
開發者：Claude Code
範圍：`D:\democase\ai-meeting-room`（本機已提交，未推 GitHub）

使用者希望會議室更像開發環境：看得到 AI 讀了哪些檔案和資料夾、點開來看，組員不用再一個一個打開 `docs` 核對。依建議的三步，先做第 1 步「檔案面板」（只讀、只顯示）。第 2 步會議列表升級（搜尋、釘選、改名、封存）、第 3 步 AI 寫入草稿區由使用者審核，尚未開始；第 3 步要放寬「AI 唯讀」原則，需使用者同意。

- 伺服器：
  - 新增 `/tree`（快照檔案清單）和 `/file`（讀檔；文字最多顯示 5MB，圖片和二進位用 `raw=1` 下載）。路徑跳出快照時回 404。
  - `files_touched()` 從「判斷過程」找出 AI 讀過、而且真的在快照裡的檔案或資料夾，並記錄起始行。支援 Gemini 的 JSON、Codex 的 PowerShell 指令、Claude 的絕對路徑；思考內容不算。新發言存成 `reads`，舊發言在讀取時現場算。
- 網頁：
  - 上方「📂 檔案」打開右側面板。左邊可切換「👀 AI 讀過的」（依 AI 分組）或「🗂 全部檔案」（目錄＋搜尋，彩色圓點表示誰讀過），上方是分頁。
  - 程式碼附行號，讀過的那一行標黃。`.md` 文件用新的 `mdDoc()` 排版（標題、清單、引言、表格、分隔線），可以切回原始文字。
  - 每則發言下方有「📂 讀了 N 個」，發言裡的檔名（例如 `teacher.py:80`）可以點；附件也在面板打開。
  - 面板寬度可拖曳調整，目錄可收起；螢幕窄時會暫時收起與會者欄。
- 驗證：用 Playwright 測第 2 輪審查會議：8 則發言有讀檔紀錄，依 AI 分組為 Gemini 5、GPT 11、Claude 16 個；發言中 76 個檔名變成連結。點 `autobiography_service.py:40` 會開分頁並標出第 40 行；`.md` 排版正確（12 個標題、21 個清單項、4 個表格）；搜尋「teacher」有 11 筆；關閉分頁正常；網頁沒有 JS 錯誤。修掉兩個問題：Windows 換行讓文件擠成一段、表格欄位被擠扁。
- 同步更新：操作手冊新增第六節（之後各節順延），附圖 12、13；README；導覽新增第 ⑭ 步（共 16 步）。

## 2026-10-09（夜）AI 會議室：上傳資料夾、取消大小限制

日期：2026-10-09
開發者：Claude Code
範圍：`D:\democase\ai-meeting-room`（本機已提交，未推 GitHub）

- 「＋」選單新增「📁 上傳資料夾」，也可以把資料夾直接拖進輸入框；上傳後保留資料夾結構，AI 從快照的 `_uploads/資料夾/...` 讀得到。
- 自動略過 `node_modules`、`.git`、`.venv`、`__pycache__` 和放密碼的 `.env`，並跳出提示說略過了幾個。
- 發言裡的資料夾顯示成可展開的「📁 名稱（N 個檔案）」，點開可逐一開啟檔案。
- 依使用者指示（本機執行不需要限制）取消每個檔案 20MB、整次 120MB 的上限。
- 下載附件改成可讀子資料夾，並檢查路徑不能跳出 `uploads` 資料夾（`../` 測試回 404）。
- 驗證：Playwright 選資料夾上傳 → 顯示 2 個檔案、略過 2 個；檔案存到會議與快照；子資料夾檔案可下載；網頁無 JS 錯誤。
- 同步更新：README、操作手冊（第四節）、導覽第 ⑥ 步。

## 2026-10-09（晚）AI 會議室、資管科小助手第 2 輪審查、時程更新

日期：2026-10-09
開發者：Claude Code
分支：`main`（`ai` 只改文件；依使用者指示暫不推 GitHub）

### 一、新時程（班導公告，使用者截圖）

11/4 投影片給導師看、11 月中完成 70%、12 月初專題審核。10-15 不是期限。已更新規格書總表、交接文件、小助手規格。

### 二、資管科小助手方向定案

- 依老師 09-23 示範、10-07 錄音、規格書附錄四、09-21 和 GPT 的討論，以及學長姐建議（做成「可以問問題的 AI」出過問題）：**拿掉聊天框**，改成嵌在流程裡、主動幫學生和導師做事的引導式 AI 代理；「查科上規定」改成缺件頁主動提醒。
- 新規格 `docs/02_需求與設計/02_設計規格/AI_設計規格_資管科小助手_引導式Agent_2026-10-09.md`（取代給組員的聊天框版規劃）。
- 第 1 輪由 Gemini CLI 唯讀審查（Pro 失敗改 Flash），4 點意見接受 3 點；紀錄 `AI_審查紀錄_資管科小助手_2026-10-09.md`。
- 第 2 輪在 AI 會議室由 Gemini、GPT、Claude（獨立審查）審查三圈，主筆逐條對照程式碼查證。主持人決定：導師用學校金鑰、學生學校金鑰每人每天 5 次（自己的金鑰先只支援 Gemini）；不貼「已過期」、不刪除，像 Google 文件一樣保留版本；學生確認 → 導師確認（可撤回）才算；導師確認後學生仍可改，改了變新版再送審。定案寫在規格第 10 節。
- 查證發現的**現有程式錯誤**：`build_facts()` 會把「活動與經歷」的草稿引用進自傳；`save_edits()` 直接覆寫不留版本；導師確認不存快照、可來回改不留紀錄。尚未修，列為下一步第 1 項。

### 三、AI 會議室（新工具，獨立儲存庫）

- 位置 `D:\democase\ai-meeting-room`，GitHub `LanyuLiu951127/ai-meeting-room`（使用者在網頁建立空的儲存庫，用完整網址推送 `cc70751`）。只用 Python 內建功能，不需安裝套件與 API 金鑰。
- 功能：多家 AI 群組討論（Gemini／Codex／Claude CLI 唯讀、讀不含 `.env` 的程式碼快照）、@點名、送出後 8 秒可撤回、附件與 Ctrl+V 貼圖、圖片預覽縮放、收合與時間軸、判斷過程、**查證**（到各家 CLI 自己的紀錄資料夾找出同一對話編號，三家實測都找到）、禁言、額度用完自動離席、沒安裝自動跳過、剩餘額度與 20% 警告、換模型與思考強度、新增自訂 AI、語音輸入與朗讀、15 步網頁導覽、操作手冊（附截圖）、好讀版面（💡白話黃框、彩色標籤、```diff 紅綠對照）、閱讀時不被新訊息拉走。
- 安全：Codex 用 `--ignore-user-config` 並關閉應用程式連接、瀏覽器、操作電腦、外掛（使用者的 Codex 設定未修改，備份在 `D:\codex輩分` 與會議室 `備份_codex設定/`）；Claude 用 `--safe-mode` 只開讀檔工具；Gemini 用唯讀模式並關閉擴充。
- 測試：每個功能都用 Playwright 實際操作驗證；模擬組員第一次下載（非 git 專案、`.env` 不被複製）通過。
- 發現並修正的問題：Windows 停止伺服器後舊程序仍占用埠（改成占用時直接報錯）；Codex 額度讀到兩週前舊紀錄；按按鈕叫 AI 沒留紀錄（曾有一次不明的 GPT 發言約 1.4 萬個詞元）；發言時又按「全部輪一圈」會重複輪兩圈。
- 之後再改成 Discord 風格的一行輸入列（左邊「＋」選單收納上傳、語音、請 AI 發言、全部輪一圈、自動回答設定；Enter 送出、Shift+Enter 換行，輸入法選字時不誤送；「停止」只在 AI 發言時出現），手冊與導覽同步更新。
- 本機提交 `84ff183` 之後的幾個提交 尚未推送（推送前先問使用者）。

### 四、開發工具

- 在 `ai\.venv` 安裝 Playwright（只從 PyPI），瀏覽器放 `ai\.playwright-browsers`（707MB，已加入 `.gitignore`，刪除專案資料夾即移除）。

## 2026-10-09 錄音整理、科助採訪與問卷分析

日期：2026-10-09
開發者：Claude Code
分支：`main`（只改文件，沒有改程式；依使用者要求暫不推 GitHub）

### 一、讀了什麼

- `docs/06_會議錄音與逐字稿/`：09-02～10-08 共 9 段錄音的會議紀錄、逐字稿與時間線整理（使用者新增）。
- `docs/07_表單回覆/`：學長姐痛點問卷回覆（4 份）。

### 二、重要發現

- **科助採訪（10-08）**：學生報名比賽、請公假都自己上網，不經科辦 → 競賽報名失去根據；科辦只能補自己開的證明（**TA 證明、社團證明**）；社團對口是老師，科辦不管現場、不收照片；科助真正的困擾是機器人零件歸還後要逐一重新檢查、少了要自己賠（不在學習歷程範圍）。
- **老師的 AI 方法（09-23）**：依序上傳科目 → AI 分類 → 上傳證照 → 證照分類 → 上傳專題 → 最後產出自傳與**未來學習計畫**。不是聊天問答。
- **時程（09-08）**：10-15 要有初步可行版本，11-15 最終驗收。
- **問卷**：4／4 勾選「不知道如何連結升學方向」「不知道如何呈現專題成果」「缺學長姐經驗」「需要重找資料」；沒有任何科辦相關痛點。

### 三、新增文件

- `docs/07_表單回覆/AI_檢查報告_學長姐痛點問卷分析與需求功能對照_2026-10-09.md`：樣本說明、統計、原文節錄、需求→功能對照表（N1～N11）與缺口。

### 四、使用者決定

- 競賽報名**取消**；表單**收件暫停**（下載區保留，10-15 後）；器材點收**只記錄不開發**；10-15 前**先做學生主線**。
- 已更新：規格書功能確認總表（第一點新增 10-08 科助採訪、09-23 老師 AI 方法、10-09 決定；第三點功能狀態；第八點下一步）、表單區規格狀態、交接文件第三～五點。
- 給組員的小助手規劃**尚未重寫**（README 已標示「待重寫，先不要交給組員」）。

### 五、整理 `docs` 資料夾

使用者說專案很亂，交接文件和舊檔案太多。原則：**不刪除，只搬到封存區，並修正連結**。

- 搬到 `99_封存_歷史與待確認/01_舊版交接與對話/`：10-06 交接、09-24 完整對話交接、09-21 專案整理設計規格、系統現況重點摘要、廢棄與待淘汰項目清單。
- 搬到 `99_封存_歷史與待確認/02_舊版規格與規劃/`：`docs` 最上層的 5 份 09-29 文件（三人分工、整合驗收、文件庫索引、產品北極星、雙專案策略）；02 資料夾中 09-21～09-29 的設計規格與實作計畫（核心流程、P0 兩份、單一核心流程重整提案、測試版最終規格、最終版缺漏清單、行政表單規格與計畫）。
- 搬到 `99_封存_歷史與待確認/05_已完成工作計畫/`：AI 自傳小幫手與招生資料代理實作計畫（10-06，已完成）。
- 10-06 指導老師會議紀錄 → `06_會議錄音與逐字稿/`；指導老師討論簡報 → 新資料夾 `08_簡報/`（同步修改 `scripts/build_teacher_presentation.py` 的輸出路徑）。
- 用腳本修正 10 個現行文件中指向被搬移檔案的連結與路徑；另修正 5 個**原本就斷掉**的連結。檢查結果：現行文件（不含封存區）沒有斷掉的相對連結。
- 重寫 `docs/README.md`（先看這 5 份、資料夾說明、02 文件狀態）與封存區 README。
- 留在原地：`AI_代理協作_工作佇列.md`（`AGENTS.md` 指定位置）、`02_需求與設計/system-design-action-plan.md`（測試會檢查路徑）。
- `04_圖表與介面/` 的介面設計文件沒有動，由組員整理。

### 六、合併 `feat/award-records` 回 `main`

- 使用者同意後，先提交文件整理（`00da96d`），再合併 `feat/award-records`（`27f90b8`，無衝突）。獎懲記錄 AI 逐列分類、資料來源標籤、科辦電子獎狀與驗證頁已進入 `main`。
- 合併後 `pytest`：**180 個全部通過**。
- 未提交：`scripts/puppeteer-mermaid.json`（GPT 留下）、`scripts/transcribe_project_recordings.py`（轉錄錄音用，金鑰從 `.env` 讀取），待使用者決定。
- 尚未做：用真的獎懲記錄截圖測 AI 讀取；移除工作樹 `D:\democase\ai-wt-award`；MySQL 資料庫遷移。

## 2026-10-08（晚）排定新想法順序、科辦表單區設計規格

日期：2026-10-08
開發者：Claude Code
分支：`main`（只改文件，沒有改程式）

### 一、使用者的決定

- 組員的 AI 小助手初版是「提問」形式，可以串接 Gemini、GPT、Claude API。使用者提醒：學長姐用「提問」做小助手時，在審查中問題很多（參考 `school/Documents/專題審查學習目標與評量對照表.pdf`）。
- **科辦功能不等科助回覆，直接開發**；要像 Google 表單一樣可以設定，不能寫死。
- 表單下載區：科辦可以新增項目，有「要填的」與「不用填的」兩種，開放給學生和老師。要填的表單選擇**由學生上傳回系統、科辦在系統收件**（含收件清單、誰交誰沒交、退件）；收件清單要**依班級做成可收合的選單**。

### 二、對照學長姐審查意見得到的設計要求

- EV3 教學被說「AI 套件不熟」→ 小助手要說得出用途、限制、資料來源。
- 共同目標 CLO3「不是互不相干的功能」→ 小助手應合併進現有的資管科小助手（有工具、知識庫、權限），組員的多家 API 當作「選哪家 AI」那一層，不另做一套。
- 學會活動管理系統「缺學期屆別、圖表不足」→ 競賽報名與收件都要有學年度學期，統計要能回答管理問題。
- E 化學習平台「班級課程不可自由新增」而沒有通過 → 分類、類型、必附檔案都由科辦設定。

### 三、新增與修改的文件

- 新增 `docs/02_需求與設計/02_設計規格/AI_設計規格_科辦表單區_下載與收件_2026-10-08.md`（草稿，待使用者確認）。
- `AI_設計規格_行政表單數位化與申請追蹤_2026-09-29.md`：開頭加註已被新規格取代的部分。
- 交接文件第三點想法 C：改為「下載＋收件」並連到新規格。

### 三之一、給組員的小助手技能規劃（同日更晚）

使用者說明：組員目前只做了框架，可以把內容送到 AI，還沒有規劃專屬的技能。使用者要先在這裡產生一份規劃範例文件，交給組員的 AI 實作。

- 新增 `docs/02_需求與設計/02_設計規格/AI_設計規格_資管科小助手技能規劃_給組員_2026-10-08.md`：現有小助手架構、必須遵守的規則（只有一個小助手、工具唯讀、帳號決定權限、AI 不做正式決定）、多家 AI 的統一 `chat()` 介面、技能規格格式與兩個範例（查表單、科辦工作進度）、技能優先順序、答辯說法、開發與交付方式。
- 使用者同意表單區規格與合併 `feat/award-records`；合併動作被權限阻擋，**尚未合併**。

### 四、目前建議順序（待使用者確認）

1. 合併 `feat/award-records` 回 `main`。
2. 科辦表單區：先做下載區，再做收件。
3. 競賽報名（自訂欄位）＋統計圖表。
4. 小助手合併組員的多家 API，並加上科辦角色（需要組員的程式位置）。
5. 主線 AI 缺口：OCR 整合、辨識失敗說明、可疑處、推薦校系。
6. MySQL 資料庫遷移、同步、推送。

注意：指導老師 10-06 說先完成主線；把科辦功能排在主線 AI 前面，要在下次見老師時說明理由。

## 2026-10-08 收斂為單一資料夾、合併主線、10-07 會議對照

日期：2026-10-08
開發者：Claude Code
分支：`feat/main-line-2` → 快轉合併到 `main`

### 一、為什麼

使用者覺得專案分成 `ai`、`ai-team`、`ai-personal` 三個資料夾太亂。決定：**之後只在 `ai` 開發**，另外兩個暫時不動、不同步，等功能穩定再一次帶過去（它們各有 65 個未提交的變更，同步前要先檢查）。

### 二、做了什麼

- 提交 10-07 會議錄音整理（`docs/06_會議錄音與逐字稿/`）、指導老師討論簡報、簡報製作紀錄，以及產生它們的兩支腳本（`scripts/transcribe_meeting_audio.py`、`scripts/build_teacher_presentation.py`；已確認不含金鑰）。
- 更正會議紀錄：整理版寫「備審需要科辦或導師確認」，但逐字稿中科助回答「導師看過就可以了」，已加註更正。
- `feat/main-line-2` 快轉合併到 `main`。

### 三、驗證

- 合併前 `pytest`：**151 個全部通過**。

### 四、流程圖依 10-07 會議更新（同日稍晚）

使用者決定：
- 科辦是「科上官方紀錄」的資料來源，用固定 Excel 範本上傳服務、公假、嘉獎名單，不逐筆審核、不審備審資料。
- 競賽證明由主辦方開立（如 AREC），學生自行上傳，不經科辦。
- 學生主動請科辦補登：第一版不做，列為待確認。

處理：
- 更新圖 5、9、11、12、13、15、使用案例圖（新增科辦，圖 1-1），新增圖 16「科辦上傳紀錄流程」（`D-18`）；全部重新匯出 PNG／SVG。
- 同步 `diagrams.md`、規格書（10-08 角色修正節、科辦需求、UC-21、權限矩陣、圖 16）、會議紀錄、指導老師討論簡報。
- 另一個代理在同一時間做了部分修改（`AI_流程圖更新紀錄_2026-10-08.md`），已在其基礎上修正，未覆寫其紀錄。

### 五、規格書新增「2026-10-08 功能確認總表」

使用者要求：把目前討論與更新寫進規格書，功能確認完整、清楚後才做下一步。另告知組員已完成 OCR 成績單智慧判斷（程式尚未在任何遠端分支，未併入 `ai`）。

規格書原「2026-10-08 錄音討論後的角色流程修正」一節擴充為功能確認總表：
- 討論與決定（10-06、10-07、10-08，標明來源）。
- 完整主線 11 步。
- 各功能完成狀態（已完成／組員完成、待整合／待開發／待確認／後續擴充）。
- AI 邊界：證照真偽只能初判，無法保證真假。
- 本次更新的文件、待確認事項（問誰）、下一步。

### 六、參考 GPT 建議後的決定（同日稍晚）

GPT 建議另做「科辦建立競賽 → 學生報名 → 指導老師確認 → 參賽 → 上傳主辦方證明 → 科辦更新公假、嘉獎」的競賽報名流程。它批評的「科辦核准競賽證明」是更早的版本，已經改掉。討論後使用者決定：

| 項目 | 決定 |
| --- | --- |
| 競賽證明的 AI 判斷 | 各主辦方格式不同，AI 容易誤判；競賽證明**只整理欄位、標出可疑處，不判斷真偽**。只有證照（格式固定，有發證單位與證號）做真偽初判 |
| 證明來源 | 每筆資料標示來源：學生上傳／競賽主辦方／科辦提供 |
| 教師端 | 導師、專任教師、指導老師**合併為同一個教師端**（`teacher` 角色），用「與學生的關係」決定能看誰；目前只有「導師 ↔ 班級」，之後加關係即可，不新增角色 |
| 競賽報名 | 先不做。使用者要求「之後再改看看，盡量做成好改、有留後路，不要寫死」 |

規格書新增「設計原則：留後路、不寫死」：
1. 教師範圍用關係決定，權限檢查集中在 `services/teacher_scope.py`。
2. 每筆資料記錄來源，新增來源只要多一個值。
3. 科辦紀錄類別（服務、公假、嘉獎……）放在設定清單，新增類別不必改程式。
4. 未來的競賽報名完成後寫進同一份學生紀錄，缺件比對、自傳與備審不用改。
GPT 的競賽報名流程放在該節當作草稿。

使用者說不知道要問科助什麼，已整理成 7 題放進規格書待確認事項（能拿到範例檔最好，請先遮掉個資）：
1. 科上派學生出去服務（例如帶高中機器人社團），現在是誰記錄？用什麼記（Excel、紙本、其他）？可以給一份範例嗎？
2. 電子證書平台開的證明上有哪些欄位？可以看一張嗎？系統產出的電子證明要跟它長得一樣嗎？
3. 公假和嘉獎的名單，科辦拿得到嗎？多久整理一次？
4. 學生報名比賽現在怎麼走？要經過科辦嗎？指導老師怎麼找？公假和嘉獎怎麼申請？
5. 如果系統可以讓科辦公告比賽、讓學生線上報名，會想用嗎？還是維持現在的方式？
6. 學生發現自己的紀錄漏了，現在怎麼找科辦補？
7. 科辦會有幾個人使用系統？每個人要有自己的帳號嗎？

修改檔案：規格書（功能確認總表、第一節之二教師需求、UC-20、`teacher` 角色說明）、`diagrams.md` 對照表、`D-16-teacher-confirm-flow`（附註，已重新匯出）。

### 七、給 GPT 改簡報、貼流程圖用的清單

使用者會請 GPT 修改 `docs/08_簡報/AI_指導老師討論簡報_2026-10-07.pptx`，並把流程圖貼到 Google 雲端的正式文件。今天所有流程圖已經改好並匯出，可直接使用 `docs/images/` 的 PNG。GPT 也可以修改流程圖，但請同步 `.mmd`、PNG／SVG、`diagrams.md`、規格書，並寫進開發日誌；另外不要和 Claude Code 同時在同一個資料夾工作（10-08 上午兩邊同時匯出圖片，互相覆蓋）。

今天更新過、要換掉舊圖的：

| 圖號 | 圖名 | 檔案（`docs/images/`） | 今天改了什麼 |
| --- | --- | --- | --- |
| 圖 1 | 使用案例－學生 | `D-01-use-case-student.png` | AI 推薦校系、AI 標出可疑處、查看科辦紀錄 |
| 圖 2 | 使用案例－導師 | `D-01-use-case-teacher.png` | 可看原始檔、確認備審內容 |
| 圖 1-1 | 使用案例－科辦／科助（**新增**） | `D-01-use-case-staff.png` | 下載範本、上傳名單、確認匯入、產出電子證明 |
| 圖 3 | 使用案例－系統管理者 | `D-01-use-case-admin.png` | 無內容變更（重新匯出） |
| 參考 | 使用案例總覽 | `D-01-use-case-v2.png` | 加科辦、AI 推薦校系、證照真偽 |
| 圖 4 | 登入與角色導頁 | `D-02-login-role-routing.png` | 科辦工作區改為「上傳服務、公假、嘉獎紀錄」 |
| 圖 5 | 學生主線 | `D-10-main-line-flow.png` | AI 推薦校系、AI 說明錯誤原因、確認前標出可疑處、科辦紀錄自動列入、AI 協助寫自傳 |
| 圖 9 | 導師確認 | `D-16-teacher-confirm-flow.png` | 附註：成績單、證照、競賽證明不經導師 |
| 圖 11 | 角色與責任 | `D-14-role-responsibility.png` | 科辦上傳官方紀錄、不審備審 |
| 圖 12 | 系統架構 | `D-05-system-architecture.png` | 加科辦；Gemini 用途；前端改為「少量原生 JavaScript」 |
| 圖 13 | DFD | `D-06-dfd.png` | 新增 7.0 匯入科辦紀錄、D7 |
| 圖 15 | 報告用總體流程 | `D-15-report-overview.png` | 加 AI 推薦、AI 檢查、科辦紀錄 |
| 圖 16 | 科辦核准電子獎狀流程（**新增**） | `D-18-staff-service-record-flow.png` | 全新（第八節再修改） |

今天沒改、仍可用的：圖 8 `D-13-admission-rule-update-flow.png`、圖 10 `D-17-admin-maintain-requirements.png`、圖 14 `D-09-erd-v2.png`（科辦紀錄的新資料表要等功能設計好再畫）。

**舊圖，不要放進正式文件**：`D-01-use-case.png`、`D-02-student-flow.png`、`D-04-admin-maintenance-flow.png`、`D-08-ai-agent-flow.png`（09-15 版）、`D-09-erd.png`、`D-10-report-overview.png`、`D-10-midterm-core-flow.png`。目前的簡報腳本 `scripts/build_teacher_presentation.py` 仍把部分舊圖放在內文或附錄（例如第 157 行用 `D-08-ai-agent-flow.png`），改簡報時建議拿掉。

簡報文字要跟著改的重點：科辦只替科上派的服務核准電子獎狀（不審備審、不開競賽證明，見第八節）；競賽證明 AI 不判斷真偽；教師端合併三種老師；競賽報名是後續擴充。圖號與說明以規格書「2026-10-08 功能確認總表」為準。

### 八、依學校獎懲記錄與電子證書修正科辦角色（同日稍晚）

使用者提供三張截圖（**含本人姓名學號，未存進專案**，只用文字記下欄位）：
- 學校「獎懲記錄查詢」：學號、姓名、獎懲日期、獎懲名稱、數量、獎懲事由、銷過。科上派的服務（「1141學期協助資管科麗山國中社團活動共1次」）與競賽得獎（「參加2025第36屆AERC…獲得佳作」）都記成嘉獎。使用者說明：這是學校統整的正式紀錄，一行一筆是為了能印成 A4 正式文件。
- 學校「電子證書發證中心」：研習名稱、研習時數、發照單位、證照（可看、可下載 PDF），含服務學習與資訊盃比賽。
- 服務學習證明：校名與校徽、證明類別、內文（學制、科別、姓名、學號、學年度學期、內容、時數）、發證單位、民國日期、驗證碼與 QR code、驗證網址。
- 使用者回答科助問題 1：科辦接到需求 → 找指導老師 → 指導老師找學生組隊，完成後記在獎懲記錄。

決定（使用者同意「甲方案」）：
- 獎懲記錄、電子證書和成績單一樣，由學生從學校系統下載後上傳；AI 逐列讀出並分類到六類。
- 科辦只做一件事：替科上派的服務**核准電子獎狀**。學生從獎懲記錄勾選並申請 → 科辦對照後核准 → 系統產出。電子獎狀是補充個別證明，**不取代學校的獎懲記錄**。
- 電子獎狀：**保留固定的獎狀外框，內文可以編輯**（系統先帶入，科辦核准前可修改），驗證碼連到本系統自己的驗證頁。
- 學校電子證書有驗證碼：AI 讀出後顯示驗證連結，可信度比 AI 初判高；系統是否自動查詢要先確認學校是否允許。
- 科辦用 Excel 上傳名單：改列後續擴充（備用方案）。

修改：
- 規格書：功能確認總表的決定、主線、功能狀態、AI 邊界、設計原則、待確認、下一步；第一節之三科辦需求；UC-21、新增 UC-22；三處權限表；圖 16 名稱。
- 流程圖：圖 4、5、9、11、13、15、使用案例圖（含科辦）、圖 16（改為「科辦核准電子獎狀流程」），重新匯出。
- 同步 `diagrams.md`、會議紀錄、工作佇列 PPT-01。

### 九、程式：獎懲記錄匯入與科辦電子獎狀（同日中午，使用者用餐時）

使用者要求：Claude 寫程式、GPT 改簡報，分開做。為了不和 GPT 互相覆蓋，Claude 在另一個 Git 工作樹（`D:\democase\ai-wt-award`，分支 `feat/award-records`）工作，沒有動 `D:\democase\ai` 的檔案。**尚未合併回 `main`，也沒有推送**，等使用者看過再決定。

#### 1. 獎懲記錄匯入（提交 `c6bf383`）

- 入口：「活動與經歷」頁的「從學校獎懲記錄匯入」→ `/student/award-records`。
- 流程：上傳 PDF 或截圖 → AI 逐列讀出（`services/award_record_service.py`）→ 確認頁對照原始檔，逐列勾選、改類別、改學年度 → 寫進「活動與經歷」。
- 規則：
  - 分類先看 `app/content/award_rules.json` 的關鍵字（科上可以自己改，例如「參加…獲得」→競賽、「協助」→服務學習、「小老師」→幹部經歷），比不到才用 AI 的建議，兩者都沒有就請學生選。
  - 只匯入嘉獎、小功、大功；警告、小過等懲處和已銷過的列一律略過，不存、不顯示。
  - 「1141學期…」讀成 114 學年度第 1 學期；知道入學年度就換成年級（專一～專五），才放得進「我的五年」對的資料夾。
  - 同一個事由不會重複匯入。
- 沒有 AI 金鑰時，確認頁給 3 列空白，請學生對照原始檔自己填。
- 每筆活動與經歷新增「證明來源」（`Portfolio.source`、`source_document_id`，資料庫遷移 `c4a8f1e2d903`）。學生清單、導師學生頁顯示「學校獎懲記錄」標籤；自傳小幫手的事實會註明「來源：學校獎懲記錄」。
- 「成績與證照」頁不再列出獎懲記錄檔案（只列成績單與證照）。
- 獎懲記錄放在獨立的服務層與路由（`routes/award.py`），沒有改 `document_analysis_service.py`，之後整合組員的 OCR 比較不會衝突。

#### 2. 科辦電子獎狀（提交 `096a388`）

- 學生：從獎懲記錄匯入的「服務學習」紀錄，編輯頁出現「申請電子獎狀」；送出後顯示「等科辦核准」，退回時顯示原因並可重新申請，核准後可查看與列印。
- 科辦（新選單「電子獎狀」，科辦工作台也有待核准數量）：`/staff/certificates` 清單 → 審核頁可「對照學生上傳的獎懲記錄」→ 修改標題、內文、發證單位 → 核准或退回（退回必填原因）。
- 獎狀（`templates/certificate.html`）：固定外框（康寧大學 資訊管理科、證明類別、內文、發證單位、民國日期、驗證碼），A4 直式，用瀏覽器「列印／存成 PDF」。內文由系統先帶入，例如「茲證明 本校五專資訊管理科 林小美（學號：111534107）同學，於 114 學年度第一學期參與「協助資管科麗山國中社團活動共1次」，熱心服務、表現認真，特此證明。」
- 驗證：核准時產生 8 碼驗證碼（不用 0、O、1、I）；公開頁 `/verify?code=` 顯示「有效，由資訊管理科於…核發給 林○美 同學」，姓名遮蔽、不顯示學號。
- 誰看得到獎狀：學生本人、科辦、管理者、該生的導師；其他學生和別班導師 403；尚未核准的學生看不到。
- 新資料表 `award_certificates`（資料庫遷移 `d5b9a2c7e104`）。
- 展示網站新增科辦帳號 `staff01`（林科助），林小美有一筆待核准的申請。

#### 3. 順便修正的既有問題

- 「活動與經歷」編輯頁的年級選單只有專一～專五，存成民國學年度（例如 114）的紀錄一按「儲存」學年度就會被清掉。現在選單會保留原本的學年度。

#### 4. 驗證

- `pytest`：**180 個全部通過**（原本 151 個＋新增 29 個：`test_award_records.py` 13 個、`test_award_certificates.py` 14 個、資料庫遷移 1 個、表單保留學年度 1 個）。
- 資料庫遷移：SQLite 上升級／降級測試通過；**尚未在 MySQL 執行**。
- Puppeteer（展示網站 5088 埠）：
  - 王小明上傳獎懲記錄 → 確認頁（沒有 AI，3 列空白）→ 填一列 → 匯入 1 筆，出現「學校獎懲記錄」標籤；再匯入同一筆為 0 筆（不重複）→ 申請電子獎狀，顯示「等科辦核准」。
  - `staff01` 審核林小美的申請 → 修改內文 → 核准，產生驗證碼。
  - 林小美在手機看到「科辦電子獎狀」標籤與獎狀；`teacher01`（本班導師）可以開啟獎狀；公開驗證頁顯示「林○美」且不出現全名。
  - 桌機 1366px、手機 390px 皆無橫向溢出，沒有 JavaScript 錯誤（獎狀頁原本少網站圖示造成一個 404，已補上）。

#### 5. 沒有做、要使用者決定的

- **AI 逐列讀取沒有用真的 Gemini 測**：工作樹沒有 `.env`（金鑰只放在 `ai/.env`），也避免用掉每天 20 次的免費額度。合併後請用一份真的獎懲記錄截圖試一次。
- **QR code**：要另外安裝產生 QR 的套件（例如 `segno`，純 Python），專案規定不隨便加套件，等使用者同意。
- 學校校徽、核准時需要什麼佐證：仍待問科助。
- 合併：使用者看過畫面後，再把 `feat/award-records` 合併回 `main`；MySQL 要先備份再執行兩個新的資料庫遷移。

### 十、下一步（依序）

1. 使用者看過畫面後合併 `feat/award-records`；用真的獎懲記錄測 AI 讀取；決定 QR code 是否加套件。
2. 上傳後 AI 回饋：判斷格式，出錯時說明可能原因與修正方式；確認前由 AI 標出可疑處，最後本人確認。證照與成績單不經導師。
3. AI 推薦校系：依學生條件建議適合的二技校系，可選多個。
4. 待確認：電子獎狀可否放學校校徽；核准時需要什麼佐證；可否自動查驗學校電子證書；科辦是否開放競賽報名（後續擴充）。

## 2026-10-06 主線實作、瀏覽動線簡化與佐證照片預覽

日期：2026-10-06
開發者：Claude Code
分支：`feat/main-line-2`（尚未合併回 `main`）
詳細交接：`docs/99_封存_歷史與待確認/01_舊版交接與對話/AI_交接_主線前後半實作與下一步_2026-10-06.md`

今日目標：依指導老師 10-06 討論完成主線（選校系 → 上傳六類資料 → 缺件比對 → 導師確認 → 產出備審 Word），並依使用者試用回饋整理畫面與動線。

### 一、主線功能（上午～下午，已提交）

- 新設計系統、「我的五年」、成績與證照、活動與經歷（第一批，已合併 `main`）。
- 目標校系、缺件比對與準備度、送導師確認、備審 Word 產出、導師本班名冊與確認、管理者校系資料與導師班級（第二批）。
- 新增 5 張資料表（資料庫遷移 `b7d2e9a41c35`），**尚未在 MySQL 執行**。

### 二、使用者回饋與處理

| 回饋 | 處理 |
| --- | --- |
| 「網頁好亂」 | 拿掉裝飾小標；改用仿臺大教務處的一排主選單＋藍色頁名色塊＋麵包屑（提交 `d849ad8`） |
| 「引導式動線太亂」 | 使用者決定：主選單維持五項；清單頁只放資料，按「＋新增」才到表單頁；「下一步」只放首頁；管理者選單全部保留 |
| 「看不到教師端和管理者」 | 兩端都已做好，只是要換帳號登入；展示網站登入頁現在列出展示帳號（`DEMO_ACCOUNTS`，正式環境不顯示） |
| 「圖片上傳後不能預覽還要下載」「手機也要用」 | 佐證改成縮圖格子，點了放大；PDF 開新分頁；選照片後上傳前先預覽；可刪除；清單卡片顯示第一張照片；手機主選單五格全部看得到 |

### 三、主要修改檔案（動線＋預覽）

- `app/routes/student.py`：新增 `GET /student/learning-profile/upload`、`GET /student/portfolio/new`、`GET /student/evidence/<id>/view`（只開放 PNG／JPG／PDF，加 `nosniff`）、`POST /student/evidence/<id>/delete`；佐證上傳後回到編輯頁。
- `app/models/portfolio.py`：`PortfolioEvidence.extension`、`preview_kind`（不需資料庫遷移）。
- `app/templates/`：`learning_profile.html`、`learning_profile_upload.html`（新）、`student_portfolio.html`、`student_portfolio_form.html`（新增／編輯共用＋佐證區）、`student_home.html`、`partials/nav.html`（`next_card()`）、`login.html`。
- `app/static/js/components.js`：放大檢視（`<dialog>`）、上傳前預覽、刪除前確認。
- `app/static/css/design-system.css`：`.next-card`、`.list-head`、`.evidence-grid`、`.lightbox`、手機主選單。
- `app/services/student_progress.py`：「下一步」連到新的表單頁。
- `scripts/run_demo.py`：開啟 `DEMO_ACCOUNTS`，啟動時印出四個帳號。

### 四、驗證

- `pytest`：**108 個全部通過**（新增 `tests/test_student_navigation.py` 11 個：清單頁無表單、新增頁預選類別、錯誤回表單頁、上傳獨立頁、下一步只在首頁、佐證預覽、文字檔不得內嵌顯示、他人不能看、刪除、展示帳號只在展示模式）。
- 真實瀏覽器（Puppeteer）：上傳照片 → 上傳前預覽出現 → 回編輯頁縮圖載入 → 點縮圖放大 → 刪除後縮圖消失；桌機 1366px 與手機 390px 皆無橫向溢出、無 JavaScript 錯誤；`teacher01`、`admin` 登入後分別進到導師工作台與管理者總覽。

### 五、所有上傳都要預覽、限制 10MB、導師可看佐證（同日稍晚）

使用者回饋：「照片上傳時都該要有預覽，要限制圖片上傳大小，大概 10MB」；導師要能看佐證照片（使用者答「要」）。使用者並提供學校現有「證照登錄」頁截圖作為反例：表格排版、手機跑版。

處理：

- **共用上傳元件** `app/templates/partials/files.html`：
  - `upload_field()`：整塊虛線框可點選或拖入檔案（手機可直接拍照），選好後先預覽；超過上限就清掉並以中文說明大小。
  - `evidence_grid()`：縮圖格子，圖片點了放大，PDF 開新分頁。
  - `lightbox()`：放大檢視視窗。
  - 學生佐證、成績單／證照上傳、導師學生頁都用這三個元件，改樣式只需改這一個檔案。
- **預覽規則集中** `app/services/file_preview.py`：只有 PNG／JPG／PDF 能直接顯示，並加上 `nosniff`。`PortfolioEvidence`、`SourceDocument` 都提供 `preview_kind`。
- **確認頁**：上方顯示學生上傳的原始文件，方便逐筆對照（新路由 `GET /student/learning-profile/documents/<id>/view`）。
- **導師**：學生詳情頁新增「佐證照片」區（新路由 `GET /teacher/evidence/<id>/view`），只看得到 `class_advisors` 指定班級的學生，其他導師一律 403。
- **10MB 上限**：沿用設定 `MAX_CONTENT_LENGTH_MB=10`（`.env` 可改）。瀏覽器端先檢查，伺服器端超過時回 413，並顯示中文說明頁 `upload_too_large.html`，內容包括如何縮小檔案，以及只會連回本站的「回上一頁」。

驗證：

- `pytest`：**113 個全部通過**（新增 `tests/test_file_preview.py` 5 個：導師看本班佐證、他班導師 403、確認頁顯示原始文件、上傳頁帶大小上限、超過上限回中文 413）。
- Puppeteer 手機 390px：
  - 選 11MB 檔案時出現紅框與中文提醒，檔案被清掉。
  - 選照片後出現預覽，上傳後確認頁顯示原始文件。
  - 佐證上傳後顯示縮圖。
  - 無橫向溢出、無 JavaScript 錯誤。
- Puppeteer 桌機：`teacher01` 打開王小明的頁面可看到照片，點了能放大。

### 六、導師看原始檔、旋轉照片（同日稍晚，使用者回答「都要」）

- 導師學生頁新增「成績單與證照原始檔」區，路由為 `GET /teacher/documents/<id>/view`。只顯示學生**已確認**的文件，並且只限本班學生；其他導師會收到 403，未確認的文件回 404。
- `partials/files.html` 的 `evidence_grid()` 新增 `id_arg` 參數，原始文件與佐證共用同一個縮圖格子。
- 上傳框選好照片後，會出現「↺ 向左轉／↻ 向右轉」按鈕。照片在瀏覽器裡用畫布轉正後，換掉要上傳的檔案，伺服器收到的就是轉正後的照片。轉完會重新檢查 10MB 上限。
- 驗證：
  - `pytest`：**116 個全部通過**（新增 3 個測試：本班導師看原始檔、他班導師 403、上傳框有旋轉按鈕）。
  - Puppeteer（手機）：640×420 的照片按「向右轉」後，預覽變成 420×640；上傳後在確認頁顯示也是 420×640。
  - Puppeteer（桌機）：`teacher01` 看得到學生已確認的原始檔。
  - 兩者都沒有 JavaScript 錯誤。

### 七、使用者問「自傳怎麼沒有可以生成的？核心 AI Agent 去哪裡了？」

現況盤點（尚未修改，等使用者決定）：

- 規格書指定 AI 使用 **Google Gemini API**（`services/gemini_client.py`），但程式**從未接上**。`.env` 的 `AI_ENABLED=false`、`AI_PROVIDER=none`，也沒有安裝任何 AI 套件。
- 目前的「自傳草稿」（`services/learning_profile_service.py`）是固定句型套入姓名與證照名稱，不是 AI 生成。備審 Word 的自傳章節只有撰寫提示。
- 系統亮點「二技招生資料代理」目前只完成第一階段：管理者手動匯入種子資料、核准。第二階段（偵測簡章更新）與第三階段（擷取加權成候選版本）尚未開發。
- 文件辨識（`DOCUMENT_ANALYSIS_PROVIDER=fake`）同樣尚未接 AI，學生需手動輸入。

### 八、AI 自傳小幫手＋招生資料代理第二、三階段

使用者的決定：兩個功能一起做；AI 使用 Google Gemini；自傳採「先回答幾題再生成」。計畫書：`docs/99_封存_歷史與待確認/05_已完成工作計畫/AI_實作計畫_AI自傳小幫手與招生資料Agent_2026-10-06.md`。

#### 共用：Gemini 連線

- 新增 `app/services/gemini_client.py`，用 Python 內建的 urllib 呼叫 Gemini REST API，並要求依 `responseSchema` 回傳固定格式的 JSON。可以附上 PDF。各種錯誤都轉成中文訊息。
- 不需要安裝新套件。
- 新增設定：`config.py` 加入 `AI_PROVIDER`、`AI_API_KEY`、`GEMINI_MODEL`、`AGENT_PROGRAM_KEYWORDS`、`AGENT_SOURCE_FOLDER`，並寫進 `.env.example`。**`.env` 未修改，金鑰由使用者自行填入。**

#### AI 自傳小幫手

- 程式：`services/autobiography_service.py`、`templates/student_autobiography.html`。
- 路由：`/student/autobiography`、`/generate`、`/<id>/save`。
- 使用流程：
  1. 學生先選目標校系，再回答 4 題。畫面一次只顯示一題。
  2. 右邊列出「AI 只會用這些資料」：學生資料與校系加權。
  3. AI 依學生的回答、編號事實（F1…）與加權寫 4 段草稿。每段標示「依據」，不存在的事實編號會被濾掉。
  4. 學生逐段修改後儲存，段落輸入框會隨內容長高，並顯示總字數。
- 沒有金鑰時會產生「示範草稿」，並清楚標示「尚未接上 AI」。
- 草稿存在 `learning_profile_outputs`（`autobiography_ai`），**不需要資料庫遷移**。
- 其他頁面的串接：
  - 備審 Word 的「04 自傳」章節改放學生儲存的版本；「05 讀書計畫」改成讀書計畫的撰寫提示。
  - 缺件比對頁新增「自傳」卡片，可直接進入小幫手。
  - 導師的學生頁在每個目標校系下可以展開看自傳。

#### 招生資料代理

- 程式：`services/admission_agent_service.py`、`templates/admin_agent.html`。
- 路由：`/admin/agent`（管理者選單新增「招生資料代理」）。
- 第二階段（偵測更新）：
  - 可以登記網址來源（只接受 http／https）或上傳簡章 PDF。
  - 代理計算 sha256 和上次比對，內容有變就建立變更。檔案存在 `instance/agent-sources/`。
  - 每次執行都記錄在 `agent_tasks`，失敗也會記錄。
  - 可在管理頁按「立即檢查」，也可以排程執行 `flask agent-check`。
- 第三階段（擷取加權）：
  - 把簡章 PDF 交給 Gemini，只擷取科系名稱符合關鍵字的志願。
  - 檢查志願代碼必須是 6 碼、學年度與加權範圍正確，資料類別只保留合法代碼。
  - 建立 `candidate`／`agent` 的候選版本，對應狀態一律為「待確認」，同一志願不會重複建立。
  - 「校系資料」頁顯示代理產生的候選版本和前一年正式版的加權差異。
- 學生端：`published_programs()` 對同一志願代碼只顯示最新學年度的正式版，已選舊版本的目標不受影響。
- 使用既有的 `public_sources`、`public_source_snapshots`、`public_source_changes`、`agent_tasks` 資料表，**不需要資料庫遷移**。

#### 驗證

- `pytest`：**137 個全部通過**。新增的測試：
  - `test_autobiography.py`：7 個。
  - `test_admission_agent.py`：11 個。
  - `test_gemini_client.py`：3 個，檢查送出的格式與錯誤訊息，不會連網路。
- Puppeteer（手機 390px）：林小美依序回答 4 題（畫面一次一題，有「第 n 題，共 4 題」）→ 產生示範草稿 4 段 → 修改後儲存 → 導師頁看得到修改後的文字。無橫向溢出、無 JavaScript 錯誤。
- Puppeteer（桌機）：管理者上傳真實的 `116二技技優甄審_時程與備審加權_修訂版.pdf`（643KB）→ 建立「第一次抓取」變更。因為沒有金鑰，「擷取加權」按鈕停用，並顯示設定說明。
- **尚未用真的 Gemini 金鑰測試**：自傳的實際品質和簡章擷取的準確度，要等使用者填入金鑰後再驗證。

### 九、金鑰位置修正、真實 AI 實測、學生自帶金鑰

#### 金鑰放錯檔案（已處理）

- 使用者把 Gemini 金鑰填在三個資料夾的 `.env.example`。這個檔案會被 git 追蹤，系統真正讀取的 `ai/.env` 反而是空的。
- 已確認三個儲存庫都**還沒提交／推送**，金鑰沒有外流。
- 處理方式（過程中未顯示金鑰內容）：
  - 把金鑰搬進 `ai/.env`（已列入 `.gitignore`），並設定 `AI_ENABLED=true`、`AI_PROVIDER=gemini`。
  - 清空三個 `.env.example` 的 `AI_API_KEY`。
- 防範再犯：
  - 新增測試 `test_env_example_never_contains_a_real_key`，`.env.example` 一出現金鑰就會失敗。
  - 新增 `tests/conftest.py`，所有測試一律關掉真的 AI，不會連網路、不花額度。

#### 真實 Gemini 實測（gemini-2.5-flash）

- 招生代理：上傳 116 簡章 PDF，27 秒擷取完成。208001、208003 的加權和 115 種子資料**完全相同**。
  - 208002（資訊應用菁英班）、299003（資訊工程系）因為不符合關鍵字而被略過。
  - 已把預設關鍵字改為「資訊管理,資管,資訊應用,資訊工程」，和種子資料的範圍一致。
- 自傳小幫手：約 15 秒產生 4 段草稿，引用的事實都是學生真的有的資料（計算機概論 90 分、丙級證照、技藝競賽佳作）。
  - 發現學生跳過「困難」題時，AI 仍會從競賽經驗推想出一段。
  - 已把提示詞改嚴：沒回答的題目只寫「（請補上：…）」。重測確認有效。

#### 學生使用自己的金鑰（使用者要求：不保存、只用一次、提醒刪除）

- 自傳表單新增「用自己的 Gemini 金鑰（選填）」：欄位為 `type=password`、`autocomplete=off`，出錯時也不會回填。
- 金鑰只在 `autobiography_generate()` 的區域變數裡用一次，傳給 `gemini_client.generate_json(api_key=…)`。
  - 不寫入資料庫、登入工作階段或網址。
  - 例外訊息一律 `from None`，不夾帶原始請求內容。
- 產生後頁面顯示紅色提醒：「記得刪除你的金鑰！」，並附上 Google AI Studio 的連結。
- 錯誤訊息改得更清楚：400／401／403 顯示「金鑰無效」，429 顯示「額度用完，可改用自己的金鑰」。
- 測試確認：金鑰有被用到，但資料庫的 `content_json`、`source_snapshot_json`、登入工作階段、轉址網址、頁面內容都找不到它。

#### 其他

- 修正我造成的首頁錯誤：管理者代理頁的 `.agent-steps` 樣式和首頁同名，害首頁步驟 1～4 的字看不見。已把管理者頁的樣式改名為 `.agent-phases`。
- `pytest`：**140 個全部通過**。

### 十、資管科小助手（AI 代理）

使用者決定：四種功能都要做（回答科上規定、查自己的進度、規劃下一步、檢查備審一致性），學生和導師都能使用。

#### 架構（代理會自己決定要查什麼）

1. **知識庫**：`scripts/build_knowledge.py` 用 Gemini 把 `school/` 裡的 9 份科上文件轉寫成 Markdown，存在 `app/content/knowledge/*.md`。
   - 涵蓋：畢業門檻、116 二技時程、專題評量表、重補修、修業科目表、專題繳交、專題表格、轉科、實務專題課程大綱。
   - 每份文件開頭都標明來源。規定改了可以直接改 .md。
   - 超過 14MB 的 PDF（重補修簡報）改用 Gemini 檔案上傳 API。
   - **人工核對**：畢業門檻已逐條對照原始 PDF，數字全部正確。但 AI 把原本三欄獨立的表格逐列合併，會讓人誤解，已改寫成三個清單。其他文件只抽查。
2. **搜尋**：`services/knowledge_service.py` 依「## 小標題」切段，用兩字一組比對，標題命中加倍計分，並有同義詞表（重修→重補修…）。不需要安裝套件。
3. **工具**：`services/assistant_tools.py`，全部唯讀。
   - 學生：查科上規定、查校系加權、查你的資料、缺件比對、自傳一致性檢查。
   - 導師：查科上規定、查校系加權、查本班學生、查學生資料、缺件比對、自傳一致性檢查。
   - 「是誰在問」一律由登入帳號決定。導師查別班學生時，工具會回傳錯誤，不會給資料。
4. **代理迴圈**：`services/assistant_service.py` 用 Gemini 的函式呼叫功能，最多查 5 次後回答，回傳「查了哪些項目」與「引用的文件」。
   - 系統提示詞規定：先查再答、不能編造、不能做正式決定、要用系統的真實頁面名稱、需要志願代碼時自己查。
5. **介面**：`partials/assistant.html`，學生和導師每一頁右下角都有「資管科小助手」，手機上為全螢幕。
   - 提供建議問題、顯示「查了：…」與來源標籤。
   - AI 回答先跳脫 HTML，再轉換粗體與條列，避免被插入程式碼。
6. **隱私**：對話只存在瀏覽器分頁（`sessionStorage`）。伺服器的 `agent_tasks` 只記錄用了哪些工具，不記錄問題與回答。
7. 路由：`POST /assistant/ask`（只限學生、導師）。

#### 額度問題（重要）

- 這把金鑰的免費方案，`gemini-2.5-flash` **每天只有 20 次**。今天的測試已經用完（約 15 小時後恢復）。
- 處理方式：
  - 小助手改用另一個模型 `ASSISTANT_MODEL=gemini-flash-lite-latest`，和自傳、簡章擷取分開計算額度。
  - 遇到「每分鐘次數」限制時，依 Google 建議的秒數自動等待，最多 30 秒，重試一次。
  - 每日額度用完時，顯示中文說明：「明天恢復，急用可改用自己的金鑰」。
- **正式給全班使用時，免費額度一定不夠**，需要和指導老師討論是否申請付費方案或學校帳號。

#### 驗證（小助手）

- `pytest`：**151 個全部通過**。
  - `test_assistant.py` 10 個：工具呼叫流程、學生看不到導師工具、導師查他班被拒、導師只看到本班、對話內容不落地、最多 5 步、沒有金鑰的提示、管理者 403、聊天視窗只出現在學生與導師頁。
  - `test_gemini_client.py` 新增 429 等待後重試的測試。
- 用真的 Gemini 在瀏覽器測 6 題，全部正確：
  - 畢業門檻：查規定＋查個人資料，得出還差 1 張。
  - 先考哪張：依規定建議打字證照，並引導到「目標校系」。
  - 自傳檢查：自己查到目標校系，發現還沒有草稿，引導到自傳小幫手。
  - 二技報名日期：和文件相符，並註明以正式簡章為準。
  - 導師問「誰在等確認」：找到林小美，說明準備度 90% 和缺少的項目。
  - 導師查他班學號：拒絕。
- 第一輪實測發現 AI 會叫錯頁面名稱、會要學生自己提供志願代碼，已修改提示詞後重測改善。
- 手機 390px 與桌機截圖正常，沒有 JavaScript 錯誤。

### 十一、待確認／下一步

- AI 額度：全班使用時需要付費方案或學校帳號（和指導老師討論）。
- 知識庫其餘 8 份文件，請組員對照原始文件核對一次（特別是表格）。
- 使用者看過畫面後再提交，並合併 `feat/main-line-2` 回 `main`。
- 讀書計畫是否也要做成小幫手（可沿用同一套流程）。
- 學生已選的舊學年度目標，是否要提示「升級到新年度版本」。
- 導師與管理者頁尚未改成學生頁的「頁名色塊＋麵包屑」版面。
- MySQL 資料庫遷移（需先備份並取得同意）、同步到 `ai-team`／`ai-personal`、首頁驚訝感與互動、代理第二三階段。

## 2026-09-29 教師端需求漏洞修正：行政表單數位化與申請追蹤

日期：2026-09-29
開發者：Codex
今日目標：依多位指導老師回饋，修正原教師端一般性學習歷程審閱需求不足的問題，並同步團隊版與個人版文件。

需求決策：

- 不刪除或重新定義 P0 學生學習歷程核心。
- 教師逐份查看作品集與 AI 報告降為支援功能，不再作為教師端唯一需求或主要展示論據。
- P1 改為「教師發布年度行政表單 → 學生下載填寫並電子回傳 → 系統／AI 提示缺件 → 教師初檢 → 科辦追蹤與登錄正式行政狀態」。
- AI 只提供缺件、疑似空白與版本疑義候選提示，不得核定抵免、學分、通過或退件。
- 一般檔案上下載或作業傳繳不算差異；必須保留年度／版本、指定對象、附件、補件、狀態與稽核紀錄。

主要修改文件：

- `docs/01_正式規格/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md`
- `docs/99_封存_歷史與待確認/02_舊版規格與規劃/AI_設計規格_行政表單數位化與申請追蹤_2026-09-29.md`
- `docs/99_封存_歷史與待確認/02_舊版規格與規劃/AI_實作計畫_行政表單數位化與申請追蹤_2026-09-29.md`
- `docs/02_需求與設計/04_原始資料與參考/AI_需求基準_檔案分析與學習歷程產出_2026-09-23.md`
- `docs/02_需求與設計/04_原始資料與參考/期中開發補充.md`
- `docs/02_需求與設計/04_原始資料與參考/需求資料蒐集與規則補充表.md`
- `docs/04_圖表與介面/03_檢查與圖表規範/diagrams.md`
- `docs/99_封存_歷史與待確認/01_舊版交接與對話/AI_系統現況重點摘要.md`
- `docs/03_開發紀錄/01_參考與環境設定/environment-check.md`
- 文件索引、產品北極星與三人分工契約。

環境與驗證：

- 兩個新專案皆無自己的 `.venv` 與 `.env`；使用 `D:\democase\ai\.venv` 執行驗證。
- 團隊版：`60 passed in 23.83s`。
- 個人版：`59 passed in 21.94s`。
- 15 份主要修改文件的本機相對連結檢查通過，並修正正式規格書既有圖片相對路徑。
- Mermaid CLI 成功渲染 `diagrams.md` 的 9 張圖及正式規格書的 7 張圖；本次未覆寫 `docs/images/` 正式圖檔。
- 本次未修改 Python、套件、資料庫遷移或資料庫；行政表單功能仍為待實作規格。

下一步：

1. 先完成 P0 非空檔案擷取與可編輯確認。
2. 再依新實作計畫完成不依賴 AI 的表單發布、下載、提交、補件與科辦狀態流程。
3. 人工流程驗收後才加入 AI 完整性候選提示。

## 2026-09-29 基礎系統健康檢查與資料庫就緒驗證

日期：2026-09-29
開發者：Codex
今日目標：在既有登入、角色與 P0 骨架上，補上供開發與部署使用的後端健康檢查。

修改檔案：

- `app/routes/main.py`
- `tests/test_health.py`
- `docs/03_開發紀錄/development-log.md`

完成內容：

- 新增不需登入的 `GET /health`。
- 以 `SELECT 1` 驗證資料庫連線，不回傳主機、帳號或例外細節。
- 資料庫可用時回傳 `200` 與 `{status: ok, database: ok}`。
- 資料庫不可用時回傳 `503` 與安全的錯誤狀態。

測試驅動開發的測試結果：

- 先執行新增測試，確認缺少路由時得到 `404`。
- 完成最小實作後，`tests/test_health.py`：`1 passed`。
- 完整回歸測試：`60 passed`。

已知限制：

- 此健康檢查只驗證 Flask 與資料庫就緒，不代表 P0 檔案分析已完成。

## 2026-09-29 文件庫整理、個人備份與三人協作基準

日期：2026-09-29
開發者：Codex
今日目標：整理現行／歷史文件，建立三人開發與個人完整線的協作基準，並保留可回復的完整備份。

修改檔案／目錄：

- `docs/99_封存_歷史與待確認/02_舊版規格與規劃/AI_產品北極星與垂直切片_2026-09-29.md`
- `docs/99_封存_歷史與待確認/02_舊版規格與規劃/AI_三人開發分工與功能契約_2026-09-29.md`
- `docs/99_封存_歷史與待確認/02_舊版規格與規劃/AI_雙專案與分支整合策略_2026-09-29.md`
- `docs/99_封存_歷史與待確認/02_舊版規格與規劃/AI_整合驗收與失敗回收規則_2026-09-29.md`
- `docs/99_封存_歷史與待確認/02_舊版規格與規劃/AI_文件庫現行版與封存索引_2026-09-29.md`
- `docs/README.md`
- `docs/99_封存_歷史與待確認/`
- `docs/03_開發紀錄/01_參考與環境設定/environment-check.md`
- `docs/99_封存_歷史與待確認/01_舊版交接與對話/AI_系統現況重點摘要.md`
- `docs/99_封存_歷史與待確認/01_舊版交接與對話/廢棄與待淘汰項目清單.md`
- `D:\democase\ai-personal-backup-2026-09-29`

完成內容：

- 建立產品北極星：先讓匿名成績單／證照完成「輸入 → 確認 → 規則 → 摘要 → Word」垂直切片。
- 建立組員 A、組員 B 與整合者的功能契約，限制跨模組修改與 AI 正式判定責任。
- 建立團隊協作線、個人完整線、快照與失敗回收規則。
- 將舊交接、聊天／視覺參考、已完成流程修正計畫與明確淘汰圖片移至 `docs/99_封存_歷史與待確認/`。
- 建立個人完整備份專案，包含程式、文件、資料庫遷移、測試與 Git 歷史；排除虛擬環境、執行資料、快取與測試暫存目錄。

驗證結果：

- 備份已建立：630 個檔案，約 47 MB；確認包含 `.git`、`app`、`docs` 與測試。
- 目前 pytest：排除 `tests/tmp` 後 `59 passed`；完整收集仍被 `tests/tmp` Windows 權限阻擋。
- 尚未建立新的 Git 工作樹；目前工作區仍有未提交變更，待使用者確認基準快照後再建立團隊分支。

## 2026-09-29 流程圖補入 AI 初檢與人工責任鏈

日期：2026-09-29
開發者：Codex
今日目標：依老師回饋修正流程圖，補足目前展示版的 AI 初檢位置與學生／教師端責任邊界。

修改檔案：

- `docs/04_圖表與介面/03_檢查與圖表規範/diagrams.md`
- `docs/04_圖表與介面/03_檢查與圖表規範/diagram-style-guide.md`
- `docs/03_開發紀錄/development-log.md`

完成內容：

- 在學生送出審查快照後加入 AI 初檢節點。
- 明確標示目前 AI 只檢查 GitHub、README 與佐證的缺漏／不一致問題。
- 加入學生查看問題並補正、教師查看 AI 報告與提供回饋的流程。
- 保留科辦／行政登錄正式共同結論；AI 不直接形成通過、退件、分數或正式資格判定。
- 在 DFD 與系統架構圖補上 AI 分析紀錄與非正式候選提示的資料流。
- 修正圖表規範中的圖號重複與 AI 初檢責任說明。

驗證結果：

- `diagrams.md` 共檢查 9 個 Mermaid 區塊。
- 已補齊新增 `ai` 樣式定義，流程圖使用的樣式均有對應宣告。
- 本次未修改應用程式程式碼、資料庫或既有核心流程。
- 尚未重新匯出 `docs/images/` 下的 PNG／SVG；需在具 Mermaid CLI 或 VS Code Mermaid 預覽的環境進行視覺渲染確認。

下一步：

- 以 Mermaid 預覽或 CLI 匯出新版報告圖片，目視確認節點文字與箭頭布局。

## 2026-09-23 協作工作佇列與最終規格收斂

- 使用者確認：P0 必須交付可操作的 8 塊互鎖拼圖；P2 僅深化校園插畫與動畫，不能延後拼圖本體。
- 使用者確認：既有 Flask 登入工作階段為目前身份驗證基礎；JWT、`.enc` 與 Celery 改列為安全目標的可替換實作，不假稱測試版已具備。
- 建立 `AI_代理協作_工作佇列.md` 作為 Codex 與 IDE 內 BMAD 的共享交接媒介；需由使用者在 IDE 手動啟動 BMB，系統不會自動喚醒 BMAD。
- 建立 `AI_設計規格_測試版最終可實作規格_2026-09-23.md`，收錄單一工作檯、去識別化／逐次同意、本機規則加人工確認、雙模式「自備金鑰」、公開資料覆核發布與 Flask 相容邊界。
- 本次僅更新規格、協作規則與開發日誌，未修改應用程式程式碼或資料庫。

## 使用方式

每次開發都新增一筆紀錄。重點不是寫很多，而是讓老師看到你有規劃、有測試、有修正。

## 日誌格式

```text
日期：
開發者：
今日目標：
修改檔案：
完成內容：
遇到問題：
解決方式：
測試結果：
下一步：
```

## 2026-09-15

日期：2026-09-15
開發者：田心于
今日目標：建立 BMAD 開發文件、Flask 專案骨架與環境設定。
修改檔案：

- docs/project-brief.md
- docs/prd.md
- docs/architecture.md
- docs/database-design.md
- docs/development-plan.md
- docs/development-log.md
完成內容：
- 建立專案需求與架構文件草案。
- 規劃大型系統開發流程。
- 加入系統管理者維護功能需求。
遇到問題：
- 尚未正式開始撰寫功能程式。
解決方式：
- 先完成規格、架構、資料庫與開發流程。
測試結果：
- 文件已建立，後續可交給 BMAD 產生使用者故事。
下一步：
- 建立 Flask 最小可啟動程式。

## 2026-09-15 MySQL 環境設定

日期：2026-09-15
開發者：liu
今日目標：設定 MySQL 開發資料庫，讓 Flask 專案可以連線。
修改檔案：
- .env
- .env.example
- docs/mysql-setup.md
- docs/database-setup.sql
- scripts/check_db.py
完成內容：
- 確認 MySQL 伺服器 8.0 正在執行。
- 確認 MySQL 實際埠號為 3307。
- 建立 `smart_learning_portfolio` 資料庫。
- 建立 `smart_learning_app` 專案帳號。
- Flask 使用 .env 成功連線 MySQL。
- 建立並推動專案遠端儲存庫備份：
  - GitHub 儲存庫： `https://github.com/LanyuLiu951127/smart-learning-portfolio.git` (`origin/main`)
  - GitLab 儲存庫： `https://gitlab.com/LanyuLiu951127/smart-learning-portfolio.git` (`gitlab/main`)
- 驗證兩端儲存庫內容同步完成，具備雙備份與組員協作能力。
遇到問題：
- `mysql` 指令不在系統路徑（`PATH`）。
- `root` 不可空密碼登入。
- PyMySQL 連線時遇到 MySQL 8 預設驗證方式需要 cryptography 套件。
解決方式：
- 使用 mysql.exe 完整路徑操作。
- 使用 `root` 密碼建立專案帳號。
- 將 `smart_learning_app` 帳號驗證方式調整為 `mysql_native_password`。
測試結果：
- `scripts/check_db.py` 顯示已連上 MySQL，版本 8.0.39。
下一步：
- 建立資料表結構，或導入 Flask-SQLAlchemy 的資料庫遷移。

## 2026-09-15 第一批資料表與資料模型

日期：2026-09-15
開發者：liu
今日目標：建立第一批 Flask-SQLAlchemy 資料模型，並在 MySQL 建立資料表。
修改檔案：
- app/__init__.py
- app/extensions.py
- app/models/__init__.py
- app/models/user.py
- app/models/portfolio.py
- app/models/agent_task.py
- app/models/audit_log.py
- scripts/init_db.py
- tests/test_models.py
- pytest.ini
- docs/database-design.md
完成內容：
- 加入 SQLAlchemy 擴充初始化。
- 建立 `users`、`student_profiles`、`portfolios`、`portfolio_evidence`、`agent_tasks`、`audit_logs`。
- 建立 init_db.py，可初始化資料表與管理者測試帳號。
- 建立 `admin` 測試帳號。
- 新增資料模型測試。
遇到問題：
- 第一次測試時測試資料誤寫入真實 MySQL。
- 刪除測試使用者時被 `portfolios` 外鍵保護擋住。
解決方式：
- 調整 `create_app` 支援 `config_overrides`，讓測試使用 `sqlite:///:memory:`。
- 先刪除測試學習歷程，再刪除測試使用者。
測試結果：
- pytest 通過：3 個全部通過。
- MySQL 目前資料表：`agent_tasks`、`audit_logs`、`portfolio_evidence`、`portfolios`、`student_profiles`、`users`。
- `users` 目前保留 `admin` 管理者帳號。
下一步：
- 實作登入頁與管理者登入流程。

## 2026-09-15 BMAD 規格書圖表與目錄整合

日期：2026-09-15
開發者：田心于
今日目標：整合 BMAD 圖表清單至規格設計書，並標明對應目錄與分工權責。
修改檔案：
- docs/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md
- docs/development-log.md
完成內容：
- 檢查 `docs/diagrams.md` 中收錄的 Mermaid 圖表（系統架構圖、案例圖、流程圖、DFD、ERD、權限矩陣、管理者維護流程圖等）。
- 在 `資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md` 目錄及內文中補充視覺化圖表位置指引與備註。
- 完善工作分配章節，明確標示成員專題權責與單人獨立全端開發運作模式。
遇到問題：
- 規格書中部分圖表原本留空或預留於附錄，導致閱讀與導覽不便。
解決方式：
- 在目錄明確標註圖示位置（附錄五與各章小節），並完成對應章節的文字與圖示結構整合。
測試結果：
- 規格書目錄、工作分配與圖表導引已同步完成，內容結構完整。
下一步：
- 進入第 1 輪衝刺：實作登入驗證、登入工作階段管理與角色權限控制。

## 2026-09-15 BMAD 團隊協同完成內文圖表融合

日期：2026-09-15
開發者：田心于
今日目標：呼叫 BMAD 團隊（分析師、產品經理、架構師、開發者、審查者、品管測試）將視覺化 Mermaid 圖表直接融合至規格書對應章節內文。
修改檔案：
- docs/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md
- docs/development-log.md
完成內容：
- **分析師（Mary）**：確認使用者案例（UC01-UC14）與流程細節。
- **產品經理（John）**：補強功能性與非功能性需求層級。
- **架構師（Winston）**：將系統架構圖、DFD、AI 代理任務流程圖與 ERD 圖直接嵌至第 4、5 章對應小節。
- **開發者（Amelia）**：重構 Markdown，清理尾端重複之附錄區塊。
- **審查者與品管測試**：驗證文件格式、Mermaid 語法正確性與章節對應關係。
遇到問題：
- 附錄五預留區塊與內文圖表有重複，且圖表原本分散在附錄。
解決方式：
- 將圖表全面提升融入第 3 章、第 4 章、第 5 章與第 7 章正文中，並移除冗餘尾端附錄。
測試結果：
- Markdown 手冊預覽正常，所有 Mermaid 流程圖、案例圖、架構圖、DFD 與 ERD 均能在對應章節直接閱讀。
下一步：
- 開始第 1 輪衝刺的功能實作（登入 / 登出及認證路由）。

## 2026-09-15 規格書高解析度實體流程圖與架構圖嵌入

日期：2026-09-15
開發者：田心于
今日目標：產出符合專題報告規範之高解析度實體流程圖、案例圖、架構圖與 ERD 圖，並直接嵌入規格設計書。
修改檔案：
- docs/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md
- docs/images/portfolio_login_flowchart.jpg
- docs/images/portfolio_usecase_diagram.jpg
- docs/images/portfolio_system_architecture.jpg
- docs/images/portfolio_erd_diagram.jpg
- docs/development-log.md
完成內容：
- 生成並嵌入「系統首頁與使用者登入流程圖」（含訪客、學生、教師、管理者權限分流與判斷條件）。
- 生成並嵌入「使用者案例圖」。
- 生成並嵌入「系統總架構圖」4 層分層圖。
- 生成並嵌入「實體關聯圖（ERD）」6 大核心資料表實體關聯圖。
- 更新規格書目錄與章節圖檔連結。
遇到問題：
- 原文字版 Mermaid 流程圖在報告書排版中缺乏視覺化實體質感。
解決方式：
- 採用高解析度教育報告風格圖檔渲染，並統一集中保存在 `docs/images/`，直接以標準 Markdown 圖檔語法引用。
測試結果：
- 規格書中所有圖表均呈現標準圖檔，格式清爽，可直接複製至專題報告書或簡報。
下一步：
- 進入第 1 輪衝刺：撰寫登入畫面、驗證機制與依角色導向的路由。

## 2026-09-15 Mermaid 圖表與規格書完整目錄重整

日期：2026-09-15
開發者：田心于
今日目標：依 `docs/diagram-style-guide.md` 重整 Mermaid 圖表、匯出圖片，並補全規格設計書之詳細目錄與子章節。
修改檔案：
- docs/diagrams.md
- docs/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md
- generate_images.py
- docs/images/
- docs/development-log.md
完成內容：
- 依規範優化所有 Mermaid 圖表（加入系統邊界、適當 node 樣式與清晰節點命名）。
- 使用 Python 腳本整合 Kroki API，將 10 張 Mermaid 圖表完整渲染並匯出至 `docs/images/` 目錄。
- 重構規格設計書（`資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md`）之目錄，全面包含母節（H2）、子節（H3）及孫節（H4）之完整目錄與超連結導覽。
遇到問題：
- 原始規格書目錄僅列至母節與第一層子節，未能反映完整章節架構與流程小節。
- 直接對 Kroki 發送 GET 請求時若缺少瀏覽器識別標頭（`User-Agent`）會回傳 HTTP 403。
解決方式：
- 自行解析全文 Markdown 標題階層，重構具備完整縮排與錨點連結的 Markdown 目錄。
- 在 Python 匯出腳本中加上標準的 `User-Agent` 標頭，並用 Base64＋Zlib 壓縮。
測試結果：
- 規格書目錄點擊跳轉正常，完整展現包含需求分析、AI 代理限制、資料字典及附錄規範等所有小節。
- `docs/images/` 內 10 張 PNG 圖檔全數產生且無遺漏。
下一步：
- 展開第 1 輪衝刺的前端與後端登入驗證實作。


## 2026-09-15 專案檔案結構整理與冗餘清理

日期：2026-09-15
開發者：田心于 / DMS
今日目標：清理專案中重複的舊版草案文件、備份腳本與測試圖檔，維持目錄乾淨清晰。
修改檔案：
- 刪除：`docs/prd.md`
- 刪除：`docs/architecture.md`
- 刪除：`docs/database-design.md`
- 刪除：`docs/project-brief.md`
- 刪除：`docs/development-plan.md`
- 刪除：`docs/admin-maintenance.md`
- 刪除：`scripts/generate_diagram_png.js`
- 刪除：`docs/images/demo_flowchart.png`
- 刪除：`docs/images/demo_flowchart_hd.jpg`
- 搬移：`docs/generate_images.py` -> `scripts/generate_images.py`
完成內容：
- 清理已無作用的舊草案檔（內容已全面併入主規格書）。
- 將腳本統一歸納至 `scripts/` 資料夾，使 `docs/` 資料夾專注於存放文件與圖檔。
- 清除未使用的圖片測試檔。
測試結果：
- `docs/` 及 `scripts/` 結構清爽有序，主要規格書及圖片引用均保持正常。
下一步：
- 展開第 1 輪衝刺的前端與後端登入驗證實作。

## 2026-09-15 專案設定與程式碼細節修正

日期：2026-09-15
開發者：田心于 / GDS / DMS
今日目標：修復 README 舊文件引用、.env.example 設定、MySQL 指南狀態、管理者密碼讀取及 Flask 安全性與上傳限制設定。
修改檔案：
- `README.md`
- `.env.example`
- `docs/mysql-setup.md`
- `scripts/init_db.py`
- `run.py`
- `app/config.py`
- `docs/development-log.md`
完成內容：
1. **README.md**：修正「文件位置」列表，移除已被清理的 6 個舊檔案，替換為現有的 5 個核心文件與圖表檔。
2. **.env.example**：將 `DB_USER` 預設值修正為專案帳號 `smart_learning_app`，並新增 `ADMIN_DEFAULT_PASSWORD`。
3. **docs/mysql-setup.md**：重構為「已完成設定狀態」、「新環境初始化步驟」與「歷史檢測與除錯紀錄」，消除前後不一致問題。
4. **scripts/init_db.py**：支援從 `.env` 讀取 `ADMIN_DEFAULT_PASSWORD`，並於印出訊息時提供警示提醒。
5. **run.py**：改由 `FLASK_DEBUG` 環境變數動態控制 `debug` 模式。
6. **app/config.py**：新增正式環境無 `SECRET_KEY` 時拋出錯誤機制；讀取 `MAX_CONTENT_LENGTH_MB` 並自動轉換為 Flask `MAX_CONTENT_LENGTH`（單位：位元組）。
測試結果：
- 執行 `.\.venv\Scripts\python.exe -m pytest -q` 順利通過（3 個全部通過）。
下一步：
- 展開第 1 輪衝刺的前端與後端登入驗證實作。

## 2026-09-16 系統設計文件同步與 UI/UX 規格補強

日期：2026-09-16
開發者：田心于 / Codex
今日目標：依 Google 文件最終版與 ChatGPT 分享對話內容，將新版系統設計、角色同步、MVP 切分與 介面與使用體驗方向整合回本地開發文件。
修改檔案：
- `docs/system-design-action-plan.md`
- `docs/diagrams.md`
- `docs/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md`
- `docs/development-log.md`
完成內容：
- 新增 `docs/system-design-action-plan.md`，整理系統設計更新行動計畫。
- 補上角色同步檢查，統一 `student`, `teacher`, `reviewer`, `staff`, `admin` 等角色方向。
- 補上 MVP／第二階段／未來功能的切割，避免開發範圍失控。
- 在 `docs/diagrams.md` 新增文件與開發同步流程圖、角色權限同步流程圖、MVP 主流程圖與 UI/UX 視覺概念流程圖。
- 在主規格書新增「第零節 系統設計版本同步原則」。
- 在主規格書補上科辦／行政角色、批次分派與通知使用者案例、權限矩陣、`Users.role` 允許值。
- 新增「附錄五、網頁視覺與使用體驗設計原則」，正式寫入「把五年，拼成下一站」與「互動式編輯風格學習旅程」設計方向。
遇到問題：
- 一開始未同步更新 `development-log.md`，造成文件更新紀錄缺漏。
- 舊的 `environment-check.md` 與後續 `mysql-setup.md` / `development-log.md` 狀態不一致，需要以實測結果為準。
解決方式：
- 補寫本次同步紀錄。
- 將後續開發流程調整為：每次修改文件或程式後，必須同步補 `docs/development-log.md`。
測試結果：
- 執行 `.\.venv\Scripts\pytest.exe -q` 通過，結果為 `3 passed`。
下一步：
- 開始第 1 輪衝刺前，先整理 Git 狀態與 `.gitignore`，再實作登入、登入工作階段與角色權限控制。

## 2026-09-16 開發前總檢查

日期：2026-09-16
開發者：田心于 / Codex
今日目標：檢視整份專案大綱、文件、環境、資料庫與測試狀態，判斷是否可以開始正式開發系統。
檢查檔案與項目：
- `README.md`
- `docs/environment-check.md`
- `docs/mysql-setup.md`
- `docs/system-design-action-plan.md`
- `docs/diagrams.md`
- `docs/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md`
- `app/`
- `tests/`
- `scripts/check_db.py`
- Git 狀態
完成內容：
- 確認 Flask 應用程式可載入。
- 確認目前測試通過。
- 確認 MySQL 可連線，版本為 `8.0.39`。
- 確認目前資料庫已存在第一批資料表：`users`, `student_profiles`, `portfolios`, `portfolio_evidence`, `agent_tasks`, `audit_logs`。
- 確認主規格書已具備角色、流程、ERD、DFD、MVP 切分、AI 限制與 UI/UX 附錄。
目前仍需處理：
- 專案沒有 `.gitignore`，且 Git 狀態中出現 `__pycache__` 與 `.pyc` 快取檔被加入追蹤/暫存。
- 登入、登出、登入工作階段與角色權限尚未實作。
- 規格書列出的完整核心資料表尚未全部實作，目前僅完成 MVP 第一批模型。
- API 規格仍未獨立整理成完整端點清單。
- 資料字典目前仍是摘要，尚未列出所有欄位型別、必填、預設值與狀態允許值。
- 介面線框圖尚未正式建立。
測試結果：
- `.\.venv\Scripts\pytest.exe -q` 通過，結果為 `3 passed`。
- `.\.venv\Scripts\python.exe scripts\check_db.py` 通過，顯示 `MySQL connected: 8.0.39`。
結論：
- 目前專案已可進入第 1 輪衝刺開發，但不能視為整個系統 100% 完成或完全沒有重大風險。
- 建議先完成 Git 清理、`.gitignore`、登入驗證、登入工作階段、角色導頁與基礎權限測試，再進入學生歷程的新增、查詢、修改、刪除。
下一步：
- 建立 `.gitignore`。
- 移除不應追蹤的 `__pycache__` / `.pyc` 快取檔。
- 實作第 1 輪衝刺：登入驗證、登入工作階段管理、角色權限控制。

## 2026-09-17 期中核心第一階段開發與完整軌跡

日期：2026-09-17
開發者：Codex
今日目標：依正式規格書與 `期中開發補充.md` 開始期中核心開發，先完成登入、登入工作階段與角色權限基礎，並建立可持續追加的完整開發軌跡。
修改檔案：
- `app/routes/main.py`
- `app/templates/login.html`
- `app/templates/dashboard.html`
- `tests/test_auth.py`
- `docs/期中開發補充.md`
- `docs/midterm-development-log.md`
- `docs/development-log.md`
完成內容：
- 新增共用登入與登出流程。
- 新增學生、教師／評審、管理員的角色導頁與後端依角色控管權限。
- 新增學生／教師第一版工作區頁面。
- 依測試驅動開發先建立 4 項登入與權限測試；功能不存在時先得到 4 個失敗，完成最小實作後得到 4 個全部通過。
- 建立完整期中開發軌跡，區分已完成、進行中、未開始與不可宣稱完成項目。
遇到問題：
- 原本只有首頁與管理員佔位頁，沒有登入、登入工作階段或權限保護，無法開始期中端到端流程。
解決方式：
- 先完成核心流程所需的最小認證基礎，並把後續成果提交、AI 初檢、教師覆核與 V2 版本拆成獨立階段。
測試結果：
- `pytest -q tests/test_auth.py`：4 個全部通過。
- 尚未宣稱完整期中核心流程完成；成果提交、快照、AI、教師覆核與版本管理仍待開發。
下一步：
- 依 M-01 至 M-10 順序建立學習目標、提交版本、目標快照與學生提交測試。

## 2026-09-21 目前系統進度重新評估

日期：2026-09-21
開發者：Codex
今日目標：依最新程式、測試、規格與公開來源快照，重新區分規劃成熟度與實際程式完成度。
完成內容：
- 重新執行專案測試，於 `D:\democase\ai` 執行 `pytest -q`，結果為 `7 passed`。
- 確認目前已實作登入、登出、登入工作階段、角色導頁與後端依角色控管權限。
- 確認目前只有第一批六類資料表，尚未建立專題類型、成果要求模板、學生套用、目標快照、教師覆核與 AI 分析資料表。
- 將規格成熟度與實際程式完成度分開記錄，避免用文件規劃百分比代表功能已完成。
目前評估：
- 正式規格書約 85%。
- 學校需求整合約 70%。
- 教師端規劃約 75%。
- 學生端規劃約 82%。
- 管理端規劃約 78%。
- 期中核心實際程式約 20% 左右，尚未形成完整端到端流程。
下一步：
- 先依 114 學年度「專題審查學習目標與評量對照表」建立資訊軟體開發組與商務網站經營組的成果要求範本。
- 建立 `project_types`、`requirement_templates`、`requirement_items`、`student_project_assignments`。
- 以 `admin` 建立安全的專題類型與成果要求維護頁。
- 再進入學生提交與目標快照，之後才做公開來源 AI 代理。

## 2026-09-21 需求規則修正：專題時程與證照／競賽抵免

完成內容：
- 修正學生歷程階段規劃：三年級以累積作品、證照與競賽為主，專題方向、分組與指導教師改為五年級專題正式啟動前。
- 修正抵免規則：抵免來源為學校及各科系認證的證照與競賽／比賽成果，合計至多 6 學分；不再把實習本身列為此項抵免來源。
- 將認證清單、適用年度、證明文件與審核結果列為需版本化管理的資料。
測試結果：
- 本次為規格文件修正，未修改程式碼。
- 修正內容已寫入 `需求資料蒐集與規則補充表.md` 與 `midterm-development-log.md`。
下一步：
- 依修正後的抵免規則設計證照／競賽資料模型與管理員維護欄位。

## 2026-09-17 正式規格書與期中核心範圍對照

日期：2026-09-17
開發者：Codex
今日目標：以正式專題規格設計書為基準，整理完整系統願景與期中核心開發範圍的關係。
修改檔案：
- `docs/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md`
- `docs/期中開發補充.md`
- `docs/development-log.md`
完成內容：
- 保留五專一年級至五年級學習、證照、專題、實習、升學／就業整合的完整產品定位。
- 在正式規格書加入「正式規格與期中核心」閱讀指引，並連結期中對照文件。
- 建立期中核心範圍對照表，整理系統分層、章節對應、M-01 至 M-10 驗收項目及科方交付要求。
- 明確區分長期願景、期中核心、期中支援、期末擴充與未來功能，避免把規劃功能誤認為已完成。
遇到問題：
- 正式規格書同時包含完整產品願景與多階段功能，若沒有另外標示，容易與期中交件範圍混淆。
解決方式：
- 不取代或刪除正式規格書，新增獨立的 `期中開發補充.md` 作為開發與交付管理文件。
測試結果：
- 已檢查正式規格書新增閱讀指引、對照文件連結與期中驗收表內容。
- 未修改程式碼或資料庫，尚未宣稱任何期中功能已完成。
下一步：
- 依對照文件補齊 API 規格、資料字典 與期中測試案例，再開始核心流程實作。

## 2026-09-17 公開校方來源瀏覽與本機快照

日期：2026-09-17
開發者：Codex
今日目標：重新瀏覽需求補充表提供的公開校方網址，下載可公開取得的頁面與附件，供規格核對與後續 AI 代理來源管理使用。
修改檔案：
- `school/public-sources/README.md`
- `school/public-sources/*.html`
- `school/public-sources/*.doc`
- `school/public-sources/*.odt`
- `school/public-sources/*.pdf`
- `docs/development-log.md`
完成內容：
- 保存康寧大學官網首頁、課表查詢、抵免系統公開登入頁、校內轉科公告及資管科公開頁面。
- 保存資管科專題書面繳交公告及附件：著作授權書、成果報告封面／書背格式的 Word、ODT、PDF 版本。
- 保存 1151 學期五專資訊管理科五年級 A 班教學計畫與實務專題課程綱要頁面。
- 建立 `school/public-sources/README.md`，記錄來源網址、抓取日期、初步可用線索與尚待確認項目。
- 未登入抵免系統、未讀取私人資料，也未下載 Google Drive 未確認公開權限的內容。
核對結果：
- 公開教學計畫頁顯示五專資訊管理科五年級 A 班的 1151 學期課程資料。
- 公開課程綱要頁顯示「實務專題」為 1 學分、專題課，並描述分組實作與專題流程。
- 114 學年度專題繳交公告包含每組三本紙本、每本附光碟、PDF 上傳與光碟電子檔要求；這些規則仍需依適用年度確認。
限制：
- 部分資管科頁面無法由瀏覽工具直接解析，但已用公開 HTTP 頁面下載保存。
- 111 級實務專題規定、114 學年度公告與 115 學期課程資料不可直接視為同一年度規則。
下一步：
- 將已核對來源轉成正式規格的年度化規則與成果要求模板；後續由 `admin` 管理假帳號與專題資料，不另設 `Administrator` 網站使用者。

## 2026-09-21 專題成果評量範本與角色收斂

日期：2026-09-21
開發者：Codex
今日目標：依去年度專題審查學習目標與評量對照表，將專題功能收斂為學習歷程中的小組成果，不另做專題行政系統。
修改檔案：
- `docs/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md`
- `docs/需求資料蒐集與規則補充表.md`
- `docs/midterm-development-log.md`
- `docs/專題成果評量範本-第一版.md`
完成內容：
- 確認專題由小組共用成果、個人分工與答詢紀錄組成；不延伸為場地、委員會或網站公告系統。
- 移除正式規格中的獨立 `reviewer` 登入角色設計；教師共同討論，科主任或科助登錄共同結論。
- 建立資訊軟體開發組、商務網站經營組，以及期中／兩次複評的第一版成果要求範本。
- 將 111 級實施計畫與 114 學年度評量對照表標示為年度化參考，不視為永久固定規則。
限制：
- 本次只更新規格與開發軌跡，未修改 Python 程式、資料庫或期中核心實作完成度。
下一步：
- 以成果要求範本為依據，設計並測試 `project_types`、`requirement_templates`、`requirement_items`、`student_project_assignments`。

## 2026-09-21 核心流程第一版實作

日期：2026-09-21
開發者：Codex
今日目標：依 AI 交接摘要完成角色、模板、學生提交、審查版本與 AI 初檢第一版。
修改檔案：
- `app/models/project.py`
- `app/models/submission.py`
- `app/models/review.py`
- `app/services/portfolio_service.py`
- `app/services/review_service.py`
- `app/services/ai_service.py`
- `app/routes/student.py`、`app/routes/review.py`、`app/routes/staff.py`
- `app/security.py`、`app/config.py`
- `tests/` 新增角色、模型、提交、審查、AI 與安全測試
完成內容：
- 統一正式角色為 `student`、`teacher`、`staff`、`admin`，拒絕 `reviewer` 登入導頁。
- 新增專題類型、年度模板、成果要求、小組、成員與學生模板分派模型。
- 完成學生作品新增／編輯、提交版本、要求快照與私有證據下載／上傳。
- 完成教師分派、科辦／管理者共同結論、補件版本與 V1 歷程保留。
- 完成規則式 AI 證據初檢；AI 只能保存候選結果，不會修改正式審查結論。
- 加入 CSRF 驗證碼基礎檢查、上傳檔名／副檔名檢查及管理者密碼不輸出的初始化行為。
測試結果：
- `pytest -q`：22 個全部通過。
已知限制：
- 尚未接外部 LLM、病毒掃描、學校主資料庫或正式的資料庫遷移管理。
- 管理端模板的新增、修改、刪除與完整介面 仍是最小可驗收頁面，需下一階段補齊。
下一步：
- 補齊科辦模板／小組管理表單、檔案掃描策略與 Alembic 資料庫遷移。

## 2026-09-21 AI 代理工具與產物目錄整理

日期：2026-09-21
開發者：Codex
今日目標：整理 BMAD、Codex 與 AI 工具設定，降低專案檔案瀏覽的混亂程度，同時保留工具相容性。
修改檔案／目錄：
- `agent/README.md`
- `.vscode/settings.json`
- `agent/codex/`：由 `ai/codex/` 搬移
- `agent/bmad/`：由 `ai/_bmad/` 搬移
- `ai/_bmad/`：建立指向 `agent/bmad/` 的 Windows 目錄連結
- `agent/codex` 內報告腳本的舊路徑
完成內容：
- Codex 報告、工作腳本與歷史產物集中至 `D:\democase\agent\codex`。
- BMAD 實體資料集中至 `D:\democase\agent\bmad`，保留 `ai/_bmad` 相容路徑，避免 BMAD 專案根目錄解析失效。
- VS Code 以 `files.exclude` 與 `search.exclude` 隱藏 AI 工具設定、虛擬環境、快取、執行資料與相容用的目錄連結；未刪除這些資料。
- 後續 AI 產生的 Markdown 仍統一放在 `D:\democase\ai\docs`。
驗證結果：
- Flask 測試：`22 passed`。
- BMAD 新位置與相容路徑均可讀取。
- Codex 內沒有殘留 `D:\democase\ai\codex` 舊路徑。
恢復方式：
- 編輯 `.vscode/settings.json`，刪除或將對應 `files.exclude`／`search.exclude` 項目設為 `false`，即可在 VS Code 顯示。
- 這些設定只影響 VS Code 顯示與搜尋，不會刪除檔案；PowerShell 使用 `Get-ChildItem -Force` 仍可查看。

## 2026-09-21 UI/UX 設計與動畫規格收斂

日期：2026-09-21
開發者：Codex
今日目標：依參考圖片、既有 UI/UX 對話稿與使用者回饋，定稿首頁與學生端的版面、文案與動畫方向。
修改檔案：
- `docs/UI_UX_設計與動畫規格_2026-09-21.md`
- `docs/system-design-action-plan.md`
- `docs/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md`
- `docs/AI_交接摘要_2026-09-21.md`
完成內容：
- 將介面定位為「資訊豐富的編輯式學習歷程介面」，不再以大量空白作為主要風格。
- 定義 `Experience Layer` 與 `Work Layer`，分離展示感與工作效率。
- 定義文字密度、受控不對稱、台灣口語文案、色彩、字體、版面、元件、響應式與動畫的設計變數。
- 規劃首頁與學生端的資料漂浮、捲動路徑、節點亮起、拼圖填入、成果卡進場與目標分岔動畫。
- 加入 `prefers-reduced-motion`、動畫時間上限與表單／審查頁低動畫規則。
驗證結果：
- 已讀取並對照 UI/UX 對話稿中的 20 張參考圖與既有設計討論。
- 已確認完整規格文件可在 `D:\democase\ai\docs` 找到。
下一步：
- 建立 `base.html`、共用 CSS 設計變數、`JourneyPath`、`PieceCard`、`StatusChip`、`AdviceCard` 與 `DataTable`，再實作公開首頁與學生首頁動畫。

## 2026-09-21 介面共用骨架與學生端第一版完成

日期：2026-09-21  
開發者：Codex  
今日目標：將已定稿的 UI/UX 規格落成可操作的公開首頁、學生首頁與成果管理流程。

修改檔案：

- `app/templates/base.html`
- `app/static/css/design-system.css`
- `app/static/js/motion.js`
- `app/templates/index.html`
- `app/templates/dashboard.html`
- `app/templates/login.html`
- `app/templates/student_portfolio.html`
- `app/templates/student_portfolio_form.html`
- `app/routes/main.py`
- `tests/test_ui_shell.py`

完成內容：

- 建立共用 `base.html`，統一語系、響應式設計的可視區域設定、設計系統 CSS、動畫腳本與鍵盤使用者的跳到主要內容連結。
- 公開首頁改為「把五年，拼成下一站」的資訊豐富敘事版面，包含浮動成果卡、五年路徑、未來分岔與台灣常見網路服務語氣的文案。
- 學生首頁改為個人化學習路徑，會顯示實際已建立的成果數量、五段路徑、可補上的拼圖與下一步提醒。
- 學生的成果清單、成果編輯與登入頁接入同一套視覺語言，避免操作流程在不同頁面出現斷裂感。
- 使用 CSS 動畫與 `IntersectionObserver` 實作卡片漂浮、捲動進場與路徑亮起；並支援 `prefers-reduced-motion`，使用者選擇減少動態時不會被強制播放動畫。
- 先新增介面行為測試，再完成模板與路由實作，涵蓋公開首頁、學生首頁與成果清單是否使用共用介面外殼。

驗證結果：

- `pytest -q tests/test_ui_shell.py`：3 個全部通過。
- `pytest -q`：25 個全部通過。
- `git diff --check`：無多餘空白與修補檔格式錯誤。

下一步：

- 以相同的「工作層」規則，整理教師、科辦與系統管理者的待辦清單、篩選列與資料表格畫面。

## 2026-09-21 「工作層」後台工作介面第一版完成

日期：2026-09-21  
開發者：Codex  
今日目標：把教師、科辦／行政與系統管理者從通用提示頁，改為可讀取既有資料的低動畫工作介面。

修改檔案：

- `app/routes/main.py`
- `app/routes/review.py`
- `app/templates/dashboard.html`
- `app/templates/review_queue.html`
- `app/templates/admin_dashboard.html`
- `app/static/css/design-system.css`
- `tests/test_work_layer.py`

完成內容：

- 教師工作台顯示實際被指派的審查數、最近指派項目與「我的審查」入口；教師只能閱讀與提供意見，共同結論仍由科辦登錄。
- 科辦／行政工作台顯示資料庫中狀態為 `submitted` 的送件，並直接使用既有路由登錄核可、需要補正或退件的共同結論。
- 系統管理總覽顯示啟用學生、教師、科辦帳號、送件總數、待處理送件與最近送件動態。
- 審查清單改用共用版型，讓教師從工作台進入清單時維持一致的導覽與資料層級。
- 「工作層」保持資訊密度與操作優先，僅使用必要的按鈕互動，不加入學生端的漂浮或捲動敘事動畫。
- 新增資料驅動的端到端測試，確認三種角色會收到對應的工作畫面與既有功能入口。

驗證結果：

- `pytest -q tests/test_work_layer.py`：3 個全部通過。
- 完整回歸與程式編譯檢查會在本次收尾後重新執行。

下一步：

- 補上教師可提交建議、科辦可查看既有審查意見與管理者帳號／規則維護頁面，再完成工作流程的細節串接。

## 2026-09-21 教師意見與共同結論流程完成

日期：2026-09-21  
開發者：Codex  
今日目標：讓教師意見能安全地交給科辦參考，再由科辦登錄共同審查結論。

修改檔案：

- `app/models/review.py`
- `app/models/__init__.py`
- `app/services/review_service.py`
- `app/routes/main.py`
- `app/routes/review.py`
- `app/templates/dashboard.html`
- `app/templates/review_queue.html`
- `app/static/css/design-system.css`
- `tests/test_teacher_feedback_flow.py`

完成內容：

- 新增 `TeacherReviewFeedback`，把教師的個別意見與科辦的共同結論分開保存，避免角色責任混在同一筆資料中。
- 教師只能對自己被指派的送件提交非空白意見；未被指派的教師會收到 `403`。
- 教師工作台與「我的審查」清單都可送出意見，且會保留已送出的內容。
- 科辦工作台會在每一筆已送審成果中顯示教師意見，再使用既有的核可／補正／退件功能登錄共同結論。
- 科辦登錄結論後，送件狀態會由既有服務更新；教師無法直接改變共同結論。

驗證結果：

- `tests/test_teacher_feedback_flow.py`：4 個全部通過，涵蓋教師提交、未指派拒絕、空白意見拒絕，以及科辦登錄後狀態更新。
- `pytest -q`：32 個全部通過。

下一步：

- 建立資料庫遷移，讓新的教師意見資料表可安全套用到既有 MySQL 開發資料庫；再補上管理者的帳號與規則維護功能。

## 2026-09-21 教師意見資料表的資料庫遷移完成

日期：2026-09-21  
開發者：Codex  
今日目標：讓教師意見資料表可安全、可追蹤地套用至既有 MySQL 開發資料庫。

修改檔案：

- `app/extensions.py`
- `app/__init__.py`
- `migrations/`
- `migrations/versions/52b9ba9ea108_add_teacher_review_feedback.py`
- `tests/test_migration_setup.py`
- `docs/03_開發紀錄/01_參考與環境設定/mysql-setup.md`

完成內容：

- 啟用已列在相依套件中的 Flask-Migrate，Flask CLI 現可使用 `db` 資料庫遷移指令。
- 建立第一份增量資料庫遷移，僅新增 `teacher_review_feedback`、送件索引與教師索引，不會改動既有送件內容。
- 提供 `downgrade()`，可在確認不需保留教師意見時移除這份資料庫遷移所建立的資料表。
- 更新 MySQL 文件，列出套用前檢查、`db current`、`db upgrade` 與回復操作的安全提醒。

驗證結果：

- Flask `db` 指令註冊測試通過。
- SQLite 實際執行 `db upgrade` 後，已驗證資料表與五個必要欄位存在。
- SQLite 實際執行 `db downgrade base` 後，已驗證資料表被移除。

下一步：

- 由使用者在確認的 MySQL 開發資料庫執行 `db upgrade`；接著建立管理者帳號與規則維護功能。

## 2026-09-21 管理者帳號與年度規則維護第一版完成

日期：2026-09-21  
開發者：Codex  
今日目標：提供系統管理者安全的帳號狀態控制，以及專題類型、成果模板與要求項目的年度化設定介面。

修改檔案：

- `app/routes/admin.py`
- `app/__init__.py`
- `app/templates/admin_dashboard.html`
- `app/templates/admin_accounts.html`
- `app/templates/admin_rules.html`
- `app/static/css/design-system.css`
- `tests/test_admin_management.py`

完成內容：

- 新增只限 `admin` 使用的帳號管理頁；可啟用／停用其他帳號，但不可停用目前登入的管理者，也不提供刪除帳號。
- 新增年度規則管理頁，可依序建立專題類型、成果模板與要求項目，並可啟用／停用類型與模板。
- 要求項目可設定階段、排序、說明，以及必填或選填；預設為必填，避免漏填規則被意外放寬。
- 管理頁不提供刪除已使用規則，也不自行填入未經學校確認的正式規定。
- 補齊桌面與行動版表單排列，維持「工作層」的資料優先與低動畫原則。

驗證結果：

- `tests/test_admin_management.py`：3 個全部通過，涵蓋帳號停用保護、規則階層建立、必填／選填與非管理者拒絕存取。
- `pytest -q`：38 個全部通過。

下一步：

- 在確認的 MySQL 開發資料庫執行資料庫遷移；之後可補上管理者帳號建立／密碼重設，以及已使用規則的版本化編輯流程。

## 2026-09-21 完整對話與開發交接文件建立

日期：2026-09-21  
開發者：Codex  
今日目標：讓使用者可開啟新的 AI 對話，同時保留本次合作的需求、決策、程式狀態與待辦。

修改檔案：

- `docs/99_封存_歷史與待確認/01_舊版交接與對話/AI_完整對話與開發交接_2026-09-21.md`
- `docs/README.md`
- `docs/03_開發紀錄/development-log.md`

完成內容：

- 整理使用者的資料夾、文件、介面與使用體驗、角色流程、資料庫遷移 與管理端需求。
- 記錄已完成功能、重要檔案地圖、測試命令、MySQL 寫入限制與目前進度。
- 提供可直接貼到新 AI 對話的接手指令。

下一步：

- 使用者可將此文件附加或貼到新對話；新 AI 應先依文件完成 MySQL 資料庫遷移前的檢查與展示驗收規劃。

## 2026-09-23 BMAD 架構協作與核心流程定稿前紀錄

日期：2026-09-23  
協作角色：使用者、IDE 內 BMAD 團隊（@BMB、@BMM、@WDS、@TEA、@QAS、@DMS）、Codex  
狀態：需求與架構收斂中；尚未依本節決策開始新的程式實作。

已確認事項：

- IDE 內 BMAD 已完成並寫入 [單一核心流程重整提案](../99_封存_歷史與待確認/02_舊版規格與規劃/AI_設計規格_單一核心流程重整提案_2026-09-23.md)，包含使用者故事、互鎖拼圖規範、最小安全架構與端到端驗收矩陣。
- 測試版採「先做根，再向外延伸」：以學生單一工作檯的「上傳 → 校正 → 拼圖 → 一鍵自傳」為核心；公開招生與科系資料更新只能經科辦覆核後，才影響學生下一站提示。
- Gemini 僅處理本機去識別化後的最小結構化文字；本機規則解析與學生人工確認才可寫入正式資料。
- 學生可選系統共用額度或自備 Gemini API 金鑰；測試版支援暫存使用與學生明確同意後的伺服器端加密保存，均不得寫入日誌或 Git。
- 二技招生與資管科公開資料更新列入測試版；官方來源包含技專校院招生策略委員會與康寧資管科網站 `https://im.ukn.edu.tw/`。未覆核時，學生端僅顯示「偵測到新資料，科辦確認中」。

協作注意事項：

- IDE 內的 BMAD／Gemini 代理 與本對話的桌面控制通道尚未連接；使用者貼回的 BMAD 回報與專案內已寫入文件是目前可驗證的協作證據。
- 終端機啟動的 OpenAI Codex CLI 為另一個獨立代理工作階段；其通用架構草案尚未採納為本專案最終規格，後續不得覆蓋已確認的學生核心流程與文件輸出位置規則。

下一步：

- 先將 BMAD 提案中「P0 必須交付可操作互鎖拼圖」及「技術目標不硬綁未落地 JWT／`.enc`／Celery」兩項收斂後，請使用者確認最終設計規格；確認後再建立實作計畫並開始測試驅動開發。

## 2026-09-24 問卷方向修正與新對話交接

日期：2026-09-24
開發者：Codex
今日目標：將近期問卷協作與正式規格重新對齊，建立新對話可直接接手的交接文件。
修改檔案：

- `docs/99_封存_歷史與待確認/01_舊版交接與對話/AI_完整對話與開發交接_2026-09-24.md`
- `docs/03_開發紀錄/development-log.md`
- Google 試算表「學生學習歷程需求問卷_第一版」：`https://docs.google.com/spreadsheets/d/16NRFWVo27Z68l-VAawpl9nxL1nUMZ0HEHs7UBpHaXPk/edit?gid=2043727304`

完成內容：

- 重新閱讀 `AI_需求基準_檔案分析與學習歷程產出_2026-09-23.md`、`02_需求與設計/期中開發補充.md`、`AI_系統現況重點摘要.md`，確認正式 P0 仍是「成績單／證照與其他資料輸入 → 分析整理 → 學生確認 → 課程／證照分類 → 學習摘要、待補項目、自傳／學習計畫草稿 → Word 匯出」。
- 確認完整產品願景仍包含五年學習歷程、競賽／專題／實習、教師／科辦協助，以及 P2 的五年地圖、互鎖拼圖與公開首頁；期中先收斂一條可驗收的端到端流程，不是刪除願景。
- 修正先前把「避免和學長姐專題衝突」誤解成「把產品縮減成資料保存與老師回饋工具」的錯誤方向。
- 將問卷恢復為正式核心對應版本：保留成績單、證照、作品、分類、待補資料、文件草稿、學生確認、教師協助與資料安全，但以學生能理解的白話呈現，不要求填答者知道系統專有名詞。
- 將差異化重新定義為：避開舊專題的學校／科系資料庫、志願序管理、競賽公告網站與班級志願統計；不刪除本專案自己的 P0／P1／P2 功能。
- 建立 `AI_完整對話與開發交接_2026-09-24.md`，記錄新對話先讀文件、不可誤做事項、Google 試算表狀態與後續確認步驟。

遇到問題：

- 初版問卷依系統內部概念設計，學生可能不理解「AI、拼圖、系統流程、學習歷程區塊」等詞。
- 為了避開學長姐專題，曾將問卷與建議方向縮得過窄，錯誤地弱化了正式規格中的檔案分析、文件草稿、Word 匯出與 P2 體驗層。

解決方式：

- 保留正式規格的功能邊界，只將問卷語言改成學生的生活用語。
- 將「問卷調查什麼」與「系統最後要做什麼」分開；問卷用來驗證需求優先順序，不用來覆蓋已確認的 P0／P1／P2 規格。
- 以新的交接文件固定這次修正，要求後續 AI 在提出大幅產品定位變更前先列出影響並取得使用者確認。

測試／驗證結果：

- 已讀回 Google 試算表 `問卷題目!A1:H11`，確認目前為 10 題，包含成績單／證照、分析結果、文件草稿、學生確認、教師協助與資料安全。
- 已讀回 Google 試算表 `訪談分析對照!A1:F9`，確認已標示正式核心階段、P0／P1／P2 與舊專題邊界。
- 本次未修改應用程式程式碼、資料庫、資料庫遷移或 MySQL。
- 未執行完整 Python 測試，因本次只修改文件與 Google 試算表。

下一步：

- 新對話先閱讀 `AI_完整對話與開發交接_2026-09-24.md` 與正式需求基準。
- 待使用者確認交接內容後，再建立「本專案／學長姐專題／保留或避開／P0-P2」功能對照表，作為流程圖修正與實作計畫的邊界。

## 2026-09-24 流程圖與檢核責任修正

日期：2026-09-24
開發者：Codex
今日目標：修正流程圖未呈現 P0 檔案分析根流程與人工檢核責任的問題，並統一報告用圖表視覺。

修改檔案：

- `docs/04_圖表與介面/03_檢查與圖表規範/diagrams.md`
- `docs/04_圖表與介面/03_檢查與圖表規範/diagram-style-guide.md`
- `docs/images/D-01-use-case-v2.mmd`
- `docs/images/D-02-login-role-routing.mmd`
- `docs/images/D-03-group-project-review-flow.mmd`
- `docs/images/D-10-midterm-core-flow.mmd`
- `docs/01_正式規格/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md`
- `docs/02_需求與設計/04_原始資料與參考/system-design-action-plan.md`
- `docs/99_封存_歷史與待確認/05_已完成工作計畫/specs/2026-09-24-flow-diagram-correction-design.md`
- `docs/99_封存_歷史與待確認/05_已完成工作計畫/plans/2026-09-24-flow-diagram-correction.md`

完成內容：

- 將 P0 主流程統一為「上傳成績單、證照與其他資料 → 系統擷取 → 學生校正確認 → 套用年度規則 → 教師回饋／科辦確認 → 摘要、待補清單、文件草稿與 Word 產出」。
- 新增人工檢核與補件流程，明確區分學生資料確認、教師／導師回饋、科辦／行政正式結論與管理者規則維護。
- 確認登入角色仍只有 `student`、`teacher`、`staff`、`admin`；「檢核」是既有角色的責任，不建立 `reviewer` 帳號。
- 將小組專題標示為 P1，五年地圖與互鎖拼圖定位為 P2，招生資料更新與進階備審檢核定位為未來功能。
- 統一 Mermaid 圖表為白底、細灰框、深灰箭頭、低飽和角色色彩與 `Microsoft JhengHei, Noto Sans TC, Arial, sans-serif` 字型設定。

驗證結果：

- 已掃描 `docs` 下所有 Mermaid 區塊，確認正式規格、設計計畫與集中圖表文件都已改用統一的流程與視覺規範。
- 環境未安裝 Node.js／Mermaid CLI，因此未能執行 CLI 圖片渲染；已進行 Mermaid 區塊、起訖標記、角色名稱與 P0 關鍵節點的結構檢查。匯出 PNG／SVG 前仍應在具 Mermaid CLI 或 VS Code Mermaid 預覽的環境中目視確認。

## 2026-09-24 流程圖範圍補正：目標、送審與科辦管理

使用者確認保留學生設定升學／就業／實習目標、五年學習地圖、AI 差距分析與送審功能；同時保留科辦建立審查專案、批次分派教師／委員、全局進度追蹤、名單／公文匯出、共同結論、成果鎖定與歸檔功能。

修正原則：

- 學生、教師／導師、科辦／行政三條流程共用同一份學生資料，避免學生送審後由科辦重新蒐集或建立另一份資料。
- 審查委員由被科辦指派的教師／導師承擔，不新增獨立登入帳號。
- 學生端的成績單／證照／作品整理、目標差距與五年地圖是提升可用性的核心；送審與科辦管理接在該資料之後。

## 2026-10-11 新對話交接準備

日期：2026-10-11
開發者：Codex／Claude 夜間協作
目的：使用者休息後即將開新對話，整理目前成果、驗證證據與未決事項，避免新代理重做或誤動主分支。

完成內容：

- 確認 `feat/journey-home`（`D:\democase\ai-wt-story`）工作樹乾淨，最新提交為 `f4f39b7`。
- 確認學生端五年路線、首次引導、拼圖、聚焦動畫、短文案、系統手冊、各頁導覽、導師五年簡圖與照片安全處理均已在分支中。
- 確認三輪 AI 審查的必修問題均已修正；完整測試紀錄為 `315 passed, 1 warning`。
- 將新對話起點、展示帳號、分支狀態、設計基準、未決定事項與不可自行變更事項寫入 `docs/05_交接與專案管理/AI_交接_新對話起點_2026-10-08.md` 最上方。

驗證結果：

- `D:\democase\ai-wt-story`：`git status --short` 無輸出。
- `D:\democase\ai`：仍保留原有使用者／其他代理未提交檔案，未修改、未提交、未清除。
- 交接文件已明確標示目前尚未合併 `main`、尚未推送，以及導師 AI 是否匿名化等需要使用者決定的事項。

下一步：

- 新對話先依交接文件檢視展示版，再由使用者決定是否合併與推送。

## 2026-11-02 GPT：系統組驗收與確認資料採計

- 先以回歸測試重現，再修正準備度、推薦排序、缺項與自傳事實僅採計學生已確認的成績、證照及經歷；小助手的資料摘要與佐證清單同步只使用已確認資料。舊經歷的 `submitted` 不證明學生有確認，需學生重新確認；送出導師時保留原確認狀態。舊格式非經歷分類不再被當作成績或證照加計。
- 建立五組僅為測試資料的假學生，手算與系統計算對照見 `docs/05_交接與專案管理/準備度合理性_五組假學生對照_2026-11-02.md`；結果僅涵蓋指定測試案例，並非錄取機率。
- 主任角色與統計留待後續；本次招生範圍為 115 學年度二技及插大，官方來源及完整性仍待核實。Google 文件真實驗收排入，由使用者親自登入操作。
- 可見功能展示範圍草案待使用者確認，故逐項人工驗收、10-27 兩項失敗複測、正式 Word 簽名表及真實 Google 驗收尚未完成。不得把自動測試當作人工或外部服務驗收。
- 測試、交接狀態及歷史數字差異見同目錄的系統組驗收任務清單及 handoff；首頁未改，不推送、不合併。
- 完整測試：`1021 passed, 2 skipped in 539.40s`；命令 `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q --basetemp=logs/test-runs/gpt-school-full-20261102-02`。
- 兩項略過：上傳原始文件的刪除及保留政策（M10）待決；組員上傳前預覽旋轉介面未移入此分支。
