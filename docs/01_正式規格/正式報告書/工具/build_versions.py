"""產生報告書完整版／精簡版（.md）與流程圖簡報完整版／精簡版（.pptx）。不覆蓋既有檔案。"""
import copy
import os
import shutil

from pptx import Presentation

ROOT = "D:/democase/ai/docs"
REPORT_DIR = f"{ROOT}/01_正式規格/正式報告書"
DECK_DIR = f"{ROOT}/08_簡報"
BASE_MD = f"{REPORT_DIR}/報告書內容.md"
SRC_DECK = f"{DECK_DIR}/AI_流程圖大全_V2草稿_2026-10-16.pptx"
OUT = {
    "md_full": f"{REPORT_DIR}/資管科智慧學習歷程系統_報告書_完整版_V2_2026-10-16.md",
    "md_lean": f"{REPORT_DIR}/資管科智慧學習歷程系統_報告書_精簡版_V2_2026-10-16.md",
    "deck_full": f"{DECK_DIR}/資管科智慧學習歷程系統_流程圖_完整版_V2_2026-10-16.pptx",
    "deck_lean": f"{DECK_DIR}/資管科智慧學習歷程系統_流程圖_精簡版_V2_2026-10-16.pptx",
}
for p in OUT.values():
    assert not os.path.exists(p), f"已存在，不覆蓋：{p}"

IMG = "../../images/"
# 原圖號：(標題, 圖檔, 類別)
FIGS = {
    "1": ("學生使用案例圖", "D-01-use-case-student", "使用案例"),
    "2": ("班導師使用案例圖", "D-01-use-case-teacher", "使用案例"),
    "3": ("科辦／科助使用案例圖", "D-01-use-case-staff", "使用案例"),
    "4": ("系統管理者使用案例圖", "D-01-use-case-admin", "使用案例"),
    "5": ("登入與角色導頁流程圖", "D-02-login-role-routing", "流程圖"),
    "6": ("學生主線流程圖", "D-10-main-line-flow", "流程圖"),
    "7": ("學校資料匯入流程圖", "D-21-school-data-import-flow", "流程圖"),
    "8": ("導師確認流程圖", "D-16-teacher-confirm-flow", "流程圖"),
    "9": ("科辦核准電子獎狀流程圖", "D-18-staff-service-record-flow", "流程圖"),
    "10": ("科辦表單下載區流程圖", "D-20-form-download-flow", "流程圖"),
    "11": ("招生資料更新流程圖", "D-13-admission-rule-update-flow", "流程圖"),
    "12": ("二技招生公告與 AI 推薦校系流程圖", "D-19-admission-announcement-flow", "流程圖"),
    "13": ("官網資料來源、資料分類與來源維護流程圖", "D-22-info-source-classify-flow", "流程圖"),
    "14": ("系統管理者維護校系備審要求流程圖", "D-17-admin-maintain-requirements", "流程圖"),
    "15": ("角色與責任圖", "D-14-role-responsibility", "架構"),
    "16": ("系統架構圖", "D-05-system-architecture", "架構"),
    "17": ("DFD 資料流程圖", "D-06-dfd", "架構"),
    "18-1": ("ERD－帳號、學習資料與學校資料匯入", "D-09-erd-part1-learning", "ERD"),
    "18-2": ("ERD－校系、目標校系、導師確認與自傳", "D-09-erd-part2-review", "ERD"),
    "18-3": ("ERD－資料來源、公告、表單與操作紀錄", "D-09-erd-part3-sources", "ERD"),
    "19": ("報告用總體流程圖", "D-15-report-overview", "流程圖"),
    "20": ("系統功能架構圖", "D-23-function-architecture", "架構"),
    "21": ("2026 年開發甘特圖", "D-24-gantt-2026", "時程"),
    "22": ("登入與角色導頁細部流程圖", "D-25-login-flow", "細部流程"),
    "23": ("學生資料上傳、擷取與本人確認流程圖", "D-26-student-upload-flow", "流程圖"),
    "24": ("二技目標校系推薦流程圖", "D-27-target-recommendation-flow", "細部流程"),
    "25": ("備審送審與導師確認流程圖", "D-28-review-package-flow", "細部流程"),
    "26": ("電子獎狀、TA 與社團證明流程圖", "D-29-certificate-flow", "細部流程"),
    "27": ("管理員資料來源維護流程圖", "D-30-admin-source-flow", "細部流程"),
    "28": ("學生角色功能架構圖", "D-31-student-role-architecture", "架構"),
    "29": ("教師／導師角色功能架構圖", "D-32-teacher-role-architecture", "架構"),
    "30": ("科辦／行政角色功能架構圖", "D-33-staff-role-architecture", "架構"),
    "31": ("系統管理員角色功能架構圖", "D-34-admin-role-architecture", "架構"),
    "32": ("角色／功能權限表", "D-35-permission-matrix", "架構"),
    "33": ("學生細部功能流程圖", "D-36-student-detailed-flow", "細部流程"),
    "34": ("教師／導師細部功能流程圖", "D-37-teacher-detailed-flow", "細部流程"),
    "35": ("科辦／行政細部功能流程圖", "D-38-staff-detailed-flow", "細部流程"),
    "36": ("管理員細部功能流程圖", "D-39-admin-detailed-flow", "細部流程"),
    "37": ("版本／歷史／下載流程圖", "D-40-version-history-download-flow", "細部流程"),
    "38": ("學生主工作台展示架構", "D-41-student-dashboard-wireframe", "畫面架構"),
    "39": ("學生資料確認頁展示架構", "D-42-data-confirmation-wireframe", "畫面架構"),
    "40": ("導師審查頁展示架構", "D-43-teacher-review-wireframe", "畫面架構"),
    "41": ("管理員維護頁展示架構", "D-44-admin-maintenance-wireframe", "畫面架構"),
}
ORDER = list(FIGS)  # 原順序
LEAN = ["1", "2", "3", "4", "16", "5", "6", "23", "7", "8", "9", "10", "11", "14", "18-1", "18-2", "18-3", "21"]
for k in FIGS:
    assert os.path.exists(f"{ROOT}/images/{FIGS[k][1]}.png"), k

# ---------- 報告書 ----------
base = open(BASE_MD, encoding="utf-8").read()
s2 = base.index("### 第二節 主要流程")
s3 = base.index("### 第三節 資料與檔案生命週期")
a1 = base.index("## 附錄一　流程圖索引")
a2 = base.index("## 附錄二　版本紀錄")

GROUP_TITLES = [("使用案例", "一、使用案例圖"), ("架構", "二、系統架構"), ("流程圖", "三、流程圖"),
                ("ERD", "四、資料庫關聯圖（ERD）"), ("細部流程", "五、細部流程圖"), ("畫面架構", "六、畫面展示架構"),
                ("時程", "七、開發時程")]


def figure_section(keys, numbering):
    out = ["### 第二節 系統圖表\n",
           "圖檔統一放在 `docs/images/`，索引見 `docs/04_圖表與介面/diagrams.md`。虛線框表示待組員與指導老師決議（D1～D6）。\n"]
    for cat, title in GROUP_TITLES:
        ks = [k for k in keys if FIGS[k][2] == cat]
        if not ks:
            continue
        out.append(f"#### {title}\n")
        for k in ks:
            name, f, _ = FIGS[k]
            out.append(f"**圖 {numbering[k]}　{name}**\n\n![圖 {numbering[k]} {name}]({IMG}{f}.png)\n")
    return "\n".join(out) + "\n"


def appendix(keys, numbering, note):
    rows = "\n".join(f"| 圖 {numbering[k]} | {FIGS[k][0]} | `docs/images/{FIGS[k][1]}.png` | 圖 {k} |" for k in keys)
    return (f"## 附錄一　圖表索引\n\n{note}\n\n| 本文圖號 | 名稱 | 圖檔 | 流程圖大全原圖號 |\n| --- | --- | --- | --- |\n{rows}\n\n")


PERMISSION_TABLE = """
**表 3-1　登入者權限**

| 登入者 | 可以做的事 | 不能做的事 |
| --- | --- | --- |
| 學生 | 讀寫與確認自己的資料；建立與重新送審；讀取公告、資訊、表單 | 看別人的資料；確認自己的送審版本 |
| 班導師 | 讀取本班學生資料；送審版本段落註解；修改自傳；確認送審版本；查看本班缺曠合計 | 看別班學生；審核成績單、證照與競賽證明 |
| 科辦／行政 | 電子獎狀核准或退回；表單下載區上架、改版、下架；讀取公告 | 審查備審內容 |
| 系統管理員 | 維護帳號、角色、班級；核對與發布規則、來源、分類、公告；查詢操作紀錄 | 代替學生或教師確認內容 |
"""


def build_md(keys, out_path, version_label, note):
    numbering = {k: str(i) for i, k in enumerate(keys, 1)}
    body = base[:s2] + figure_section([k for k in keys if FIGS[k][2] != "時程"], numbering) + base[s3:a1]
    body += appendix(keys, numbering, note) + base[a2:]
    body = body.replace("# 資管科智慧學習歷程系統－專題成果報告書（重寫版草稿）",
                        f"# 資管科智慧學習歷程系統－專題成果報告書（{version_label}）", 1)
    # 甘特圖放到第八章時程
    gk = [k for k in keys if FIGS[k][2] == "時程"][0]
    body = body.replace("時程以指導老師的回饋為準，必要時調整。",
                        f"時程以指導老師的回饋為準，必要時調整。\n\n**圖 {numbering[gk]}　{FIGS[gk][0]}**\n\n![圖 {numbering[gk]}]({IMG}{FIGS[gk][1]}.png)", 1)
    # 權限表
    anchor = "3. 資料是否屬於該使用者，或該使用者是否為指派班級的導師。\n"
    assert anchor in body
    body = body.replace(anchor, anchor + PERMISSION_TABLE, 1)
    body = body.replace("| 重寫版草稿 | 2026-10-16 | 依 V2 提案與現況重寫，尚未審查 |",
                        f"| 重寫版草稿 | 2026-10-16 | 依 V2 提案與現況重寫，尚未審查 |\n| {version_label} | 2026-10-16 | 由重寫版草稿產生，圖表共 {len(keys)} 張 |")
    open(out_path, "w", encoding="utf-8").write(body)


build_md(ORDER, OUT["md_full"], "完整版 V2",
         "完整版收錄流程圖大全全部 43 張圖（圖 18 為三張 ERD），供附錄與口試備查。")
build_md(LEAN, OUT["md_lean"], "精簡版 V2",
         "精簡版依學長姐報告書的圖數（約 16 張）收錄 18 張；其餘圖表見完整版，權限改用表 3-1 呈現。")

# ---------- 簡報 ----------
shutil.copyfile(SRC_DECK, OUT["deck_full"])


def set_cover(prs, line1, line2):
    for sh in prs.slides[0].shapes:
        if not sh.has_text_frame or not sh.text_frame.paragraphs[0].runs:
            continue
        txt = sh.text_frame.text
        runs = sh.text_frame.paragraphs[0].runs
        if "流程圖大全" in txt:
            runs[0].text = line1
        elif txt.startswith("依 V2"):
            runs[0].text = line2
        else:
            continue
        for r in runs[1:]:
            r.text = ""


full = Presentation(OUT["deck_full"])
set_cover(full, "流程圖完整版（V2，2026-10-16）", "依 V2 架構提案更新，收錄全部 43 張圖；虛線框＝待決議（D1～D6）。")
full.save(OUT["deck_full"])

# 精簡版：投影片 1 為封面，原圖號 k 的投影片位置 = ORDER.index(k) + 2
lean = Presentation(SRC_DECK)
set_cover(lean, "流程圖精簡版（V2，2026-10-16）", "正式報告書使用的 18 張圖；完整 43 張見完整版。虛線框＝待決議。")
sld_list = lean.slides._sldIdLst
ids = list(sld_list)
keep = [ids[0]] + [ids[ORDER.index(k) + 1] for k in LEAN]
for el in ids:
    if el not in keep:
        rid = el.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        lean.part.drop_rel(rid)
        sld_list.remove(el)
for el in keep:  # 依精簡版順序重新排列
    sld_list.remove(el)
    sld_list.append(el)
for i, k in enumerate(LEAN, 1):
    slide = lean.slides[i]
    for sh in slide.shapes:
        if sh.has_text_frame and sh.text_frame.text.startswith(f"圖 {k}｜"):
            runs = [r for p in sh.text_frame.paragraphs for r in p.runs]
            whole = "".join(r.text for r in runs)
            new = f"圖 {i}｜" + whole.split("｜", 1)[1]
            runs[0].text = new
            for r in runs[1:]:
                r.text = ""
lean.save(OUT["deck_lean"])

for p in OUT.values():
    print(os.path.getsize(p), p)
print("lean slides:", len(Presentation(OUT["deck_lean"]).slides), "full slides:", len(Presentation(OUT["deck_full"]).slides))
