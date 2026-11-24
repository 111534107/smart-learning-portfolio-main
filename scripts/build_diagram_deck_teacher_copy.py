"""產生給指導老師與 Canva 使用的流程圖大全副本。

沿用既有流程圖彙整簡報的版面與圖號；新增圖稿若尚未有 PNG，仍建立
有清楚圖名的佔位頁，方便後續貼入圖檔，不覆蓋原本的簡報。
"""
from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches

from build_teacher_presentation import IMG, ROOT, WHITE, NAVY, MUTED, add_text, base_slide, diagram_slide

OUT = ROOT / "docs" / "08_簡報" / "AI_流程圖大全_給指導老師_2026-10-10.pptx"

from build_diagram_deck import DIAGRAMS as ORIGINAL_DIAGRAMS

DIAGRAMS = ORIGINAL_DIAGRAMS + [
    ("D-23-function-architecture.png", "圖 20｜系統功能架構圖（系統→角色→功能）"),
    ("D-24-gantt-2026.png", "圖 21｜2026 年開發甘特圖"),
    ("D-25-login-flow.png", "圖 22｜登入與角色導頁細部流程圖"),
    ("D-26-student-upload-flow.png", "圖 23｜學生資料上傳、AI 擷取與本人確認流程圖"),
    ("D-27-target-recommendation-flow.png", "圖 24｜二技目標校系推薦流程圖"),
    ("D-28-review-package-flow.png", "圖 25｜備審送審與導師確認流程圖"),
    ("D-29-certificate-flow.png", "圖 26｜電子獎狀、TA 與社團證明流程圖"),
    ("D-30-admin-source-flow.png", "圖 27｜管理員資料來源維護流程圖"),
    ("D-31-student-role-architecture.png", "圖 28｜學生角色功能架構圖"),
    ("D-32-teacher-role-architecture.png", "圖 29｜教師／導師角色功能架構圖"),
    ("D-33-staff-role-architecture.png", "圖 30｜科辦／行政角色功能架構圖"),
    ("D-34-admin-role-architecture.png", "圖 31｜系統管理員角色功能架構圖"),
    ("D-35-permission-matrix.png", "圖 32｜角色／功能權限表"),
    ("D-36-student-detailed-flow.png", "圖 33｜學生細部功能流程圖"),
    ("D-37-teacher-detailed-flow.png", "圖 34｜教師／導師細部功能流程圖"),
    ("D-38-staff-detailed-flow.png", "圖 35｜科辦／行政細部功能流程圖"),
    ("D-39-admin-detailed-flow.png", "圖 36｜管理員細部功能流程圖"),
    ("D-40-version-history-download-flow.png", "圖 37｜版本／歷史／下載流程圖"),
    ("D-41-student-dashboard-wireframe.png", "圖 38｜學生主工作台展示架構"),
    ("D-42-data-confirmation-wireframe.png", "圖 39｜學生資料確認頁展示架構"),
    ("D-43-teacher-review-wireframe.png", "圖 40｜導師審查頁展示架構"),
    ("D-44-admin-maintenance-wireframe.png", "圖 41｜管理員維護頁展示架構"),
]


def placeholder_slide(prs, filename, title):
    slide = base_slide(prs, title, "流程圖附錄")
    add_text(slide, "此頁保留圖名與貼圖位置", 0.8, 1.7, 11.7, 0.5, 28, NAVY, True, PP_ALIGN.CENTER)
    add_text(slide, f"圖稿原始碼：docs/images/{filename.removesuffix('.png')}.mmd", 0.8, 2.55, 11.7, 0.35, 17, MUTED, False, PP_ALIGN.CENTER)
    add_text(slide, "目前環境尚未輸出 PNG；可將對應圖檔貼到此頁後，再上傳雲端或 Canva。", 0.8, 3.25, 11.7, 0.45, 17, MUTED, False, PP_ALIGN.CENTER)
    return slide


def make_deck():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    cover = base_slide(prs, "資管科智慧學習歷程系統", dark=True)
    add_text(cover, "流程圖大全（給指導老師／Canva 貼圖用）", 0.82, 1.55, 11, 0.7, 32, WHITE, True)
    add_text(cover, "圖 1～41；沿用原流程圖彙整簡報格式，新增角色架構、權限、細部流程與介面展示圖。", 0.86, 4.95, 11.5, 0.45, 16, WHITE)
    missing = []
    for filename, title in DIAGRAMS:
        path = IMG / filename
        if path.exists():
            diagram_slide(prs, filename, title, "原圖：docs/images/" + filename)
        else:
            missing.append(filename)
            placeholder_slide(prs, filename, title)
    prs.save(OUT)
    print(f"{OUT}\n佔位圖檔：{len(missing)}")


if __name__ == "__main__":
    make_deck()
