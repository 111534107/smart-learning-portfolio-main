from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(r"D:\democase\ai\docs\08_簡報\NAPAI_競賽_2026\五專升學備審_Agent_場域需求與驗證資料.pdf")
FONT_PATH = Path(r"C:\Windows\Fonts\msjh.ttc")
FONT_BOLD_PATH = Path(r"C:\Windows\Fonts\msjhbd.ttc")

pdfmetrics.registerFont(TTFont("JhengHei", str(FONT_PATH), subfontIndex=0))
pdfmetrics.registerFont(TTFont("JhengHei-Bold", str(FONT_BOLD_PATH), subfontIndex=0))

NAVY = colors.HexColor("#17345C")
BLUE = colors.HexColor("#2850A5")
CYAN = colors.HexColor("#4C91B8")
INK = colors.HexColor("#1B2736")
GRAY = colors.HexColor("#5D6B7D")
PALE = colors.HexColor("#EEF3F8")
LINE = colors.HexColor("#D6E0EA")
GOLD = colors.HexColor("#D9A441")
WHITE = colors.white

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="DocTitle", fontName="JhengHei-Bold", fontSize=22, leading=30, textColor=NAVY, spaceAfter=8))
styles.add(ParagraphStyle(name="SubTitle", fontName="JhengHei", fontSize=10, leading=16, textColor=GRAY, spaceAfter=14))
styles.add(ParagraphStyle(name="H1tc", fontName="JhengHei-Bold", fontSize=15, leading=22, textColor=NAVY, spaceBefore=8, spaceAfter=7))
styles.add(ParagraphStyle(name="H2tc", fontName="JhengHei-Bold", fontSize=11, leading=17, textColor=BLUE, spaceBefore=4, spaceAfter=4))
styles.add(ParagraphStyle(name="Bodytc", fontName="JhengHei", fontSize=9.5, leading=16, textColor=INK, spaceAfter=6))
styles.add(ParagraphStyle(name="Smalltc", fontName="JhengHei", fontSize=8, leading=12, textColor=GRAY, spaceAfter=4))
styles.add(ParagraphStyle(name="Tabletc", fontName="JhengHei", fontSize=8.7, leading=13, textColor=INK))
styles.add(ParagraphStyle(name="TableHead", fontName="JhengHei-Bold", fontSize=8.7, leading=13, textColor=WHITE))
styles.add(ParagraphStyle(name="Callouttc", fontName="JhengHei-Bold", fontSize=10, leading=16, textColor=NAVY, backColor=PALE, borderColor=LINE, borderWidth=0.7, borderPadding=8, spaceBefore=5, spaceAfter=9))
styles.add(ParagraphStyle(name="CenterSmall", fontName="JhengHei", fontSize=8.2, leading=12, textColor=GRAY, alignment=TA_CENTER))

def P(text, style="Bodytc"):
    return Paragraph(text, styles[style])

def make_table(rows, widths, header=True):
    converted = []
    for ri, row in enumerate(rows):
        converted.append([P(str(cell), "TableHead" if header and ri == 0 else "Tabletc") for cell in row])
    tbl = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [WHITE, PALE]),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    tbl.setStyle(TableStyle(commands))
    return tbl

def footer(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.line(18 * mm, 15 * mm, w - 18 * mm, 15 * mm)
    canvas.setFont("JhengHei", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(18 * mm, 9.5 * mm, "五專升學備審 Agent｜初賽場域需求與驗證資料")
    canvas.drawRightString(w - 18 * mm, 9.5 * mm, f"{doc.page}")
    canvas.restoreState()

story = []

# Page 1: need and user evidence
story += [
    P("五專升學備審 Agent｜場域需求與驗證資料", "DocTitle"),
    P("五專在校成果整合｜先驗證五年級二技備審流程｜匿名初賽版", "SubTitle"),
    P("場域與作品", "H1tc"),
    P("本作品服務五專學生，讓學生從在校期間逐年累積成績、證照、活動、競賽、服務與專題等資料；競賽原型先聚焦五年級準備升二技時，依目標校系要求核對備審項目，整理已完成、待補及需要人工確認的內容，提供下一步引導。", "Bodytc"),
    P("問題發想來自五專五年級準備二技備審的第一手情境；個人經驗只作為問題脈絡，不當作獨立訪談或原型測試證據。", "Callouttc"),
    P("需求調查摘要", "H1tc"),
    P("匿名問卷於 2026 年 9 月 24 日收到 4 份近一年畢業學長姐回覆；3 人升學、1 人就業。此為回顧性需求線索，不是目前專四、專五在校生的直接驗證；樣本數少，不推論為全體學生。", "Bodytc"),
    make_table([
        ["回覆內容", "人數", "對應設計"],
        ["不知道如何連結升學方向", "4 / 4", "提供目標校系要求與準備進度比對"],
        ["不知道如何呈現專題成果", "4 / 4", "協助整理成果資料；不自動評分"],
        ["準備時曾需要重找資料", "4 / 4", "集中呈現已確認資料及佐證"],
        ["不清楚應準備哪些資料", "3 / 4", "列出校系要求、已完成與待補項目"],
    ], [47 * mm, 24 * mm, 103 * mm]),
    Spacer(1, 5 * mm),
    P("調查限制", "H2tc"),
    P("這 4 份回覆來自近一年畢業學長姐，並非目前正在準備二技備審的專四、專五學生；下一步應補做在校生需求確認。", "Callouttc"),
    PageBreak(),
]

# Page 2: field engagement and level
story += [
    P("場域接觸與驗證等級", "DocTitle"),
    P("服務對象：五專學生；優先原型對象：五年級二技備審使用者。", "SubTitle"),
    P("目前可佐證的場域接觸", "H1tc"),
    make_table([
        ["紀錄日期／來源", "資料內容", "使用方式與限制"],
        ["2026/10/07 教師討論紀錄", "討論學生選校、資料上傳及小助手流程。", "教師流程觀點；摘要須對照原始錄音確認。"],
        ["2026/10/08 科助採訪紀錄 1、2", "討論校內行政流程、學生自行申請及服務紀錄管理。", "科辦流程負責人觀點；不等同五年級學生需求訪談。"],
        ["2026/09/24 匿名問卷 n=4", "畢業生回顧備審準備困難、資料遺漏與資訊需求。", "補充需求線索；小樣本，不作群體推論。"],
    ], [43 * mm, 61 * mm, 70 * mm]),
    Spacer(1, 4 * mm),
    P("Level 1 選擇依據", "H1tc"),
    P("競賽所列 Level 1 為需求訪談。現有材料包括教師討論、科辦流程採訪及 4 份畢業學長姐問卷；它們可提供利害關係人流程觀點與回顧性需求線索，但尚未直接涵蓋目前的五年級目標使用者。訪談摘要由 AI 初步整理且待對照錄音覆核；提交前須確認訪談確實包含需求內容，並補上四、五年級學生回饋，不能把設計者本人的經驗算成獨立訪談。", "Bodytc"),
    P("若無法從原始錄音核實訪談對象、需求內容與日期，或競賽規則要求目前目標使用者訪談，請先訪談五專四、五年級學生並保留紀錄；未完成前不要把個人經驗或畢業生問卷單獨描述成需求訪談。", "Callouttc"),
    P("本稿不主張 Level 2 以上", "H2tc"),
    P("目前未附上五專四、五年級目標使用者實際操作競賽原型的回饋紀錄或真實場域試辦結果。即使系統已有流程文件與程式測試，也不應寫成已完成的場域試用。", "Bodytc"),
    PageBreak(),
]

# Page 3: validation plan and governance
story += [
    P("原型驗證計畫與資料保護", "DocTitle"),
    P("初賽以固定測試案例檢查流程；結果欄待團隊實測後補入。", "SubTitle"),
    P("測試案例", "H1tc"),
    make_table([
        ["測試情境", "檢查內容", "紀錄指標"],
        ["要求與資料齊全", "每項要求是否正確比對為已備妥。", "測試項目數、正確比對數"],
        ["缺少一項佐證", "是否指出缺項並提供可理解的下一步。", "缺件漏判數、提醒正確數"],
        ["欄位或資料不確定", "是否要求學生／教師確認，不直接改正式資料。", "人工確認案例數、錯誤類型"],
        ["規則找不到來源", "是否停止推論並提示人工核對。", "來源缺失案例數、錯誤處理方式"],
    ], [48 * mm, 75 * mm, 51 * mm]),
    Spacer(1, 4 * mm),
    P("結果紀錄欄（完成測試後填寫）", "H1tc"),
    make_table([
        ["測試案例總數", "正確比對數", "缺件漏判數", "誤提醒數", "完成時間"],
        ["實測後填入", "實測後填入", "實測後填入", "實測後填入", "實測後填入"],
    ], [35 * mm, 35 * mm, 35 * mm, 35 * mm, 34 * mm]),
    Spacer(1, 4 * mm),
    P("資料保護與 AI 邊界", "H1tc"),
    P("展示使用去識別化或合成測試資料。系統不登入或爬取學校核心系統；缺曠只存假別合計、只有學生本人與班導可見，不送外部 AI，備審預設不包含。AI 產生的分類或提醒是待確認建議，不核定資格、錄取或正式審查結果。", "Bodytc"),
    P("提交前核對清單", "H1tc"),
    P("□ 覆核 10/07 與 10/08 訪談摘要　 □ 補做／補附四、五年級學生回饋　 □ 確認受訪者身分以角色描述且已去識別　 □ 補上原型操作紀錄　 □ 填入實測數字　 □ 確認展示資料不含個資", "Bodytc"),
    P("資料來源：學長姐痛點問卷分析與需求功能對照（2026/10/09）；教師與科辦會議紀錄（2026/10/07、2026/10/08）；系統完整性檢查（2026/10/10）。", "Smalltc"),
]

doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=21 * mm, title="場域需求與驗證資料")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
