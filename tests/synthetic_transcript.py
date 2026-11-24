"""產生「學生歷年成績單」版型的合成圖片（全部假資料），供 OCR 版面測試使用。

版型仿照學校正式成績單：五個學年欄位並排，每欄有「第 N 學年」表頭、起訖年月、
第一／第二學期的學分與成績欄，以及表格框線。內容不是任何真實學生的資料。
"""
from PIL import Image, ImageDraw, ImageFont

MSJH_FONT = "C:/Windows/Fonts/msjh.ttc"
PAGE = (3508, 2480)  # A4 橫向 300 DPI
MARKER, NAME, NUMBER = 50, 330, 62
PANEL = MARKER + NAME + NUMBER * 4
TOP_RULE, HEADER_RULE, BODY_RULE, SUMMARY_RULE, BOTTOM_RULE = 300, 470, 520, 1950, 2300
ROW = 46

# 每學年的合成課程：(課名, 第一學期(學分, 成績) 或 None, 第二學期(學分, 成績) 或 None)
SYNTHETIC_YEARS = [
    [("模擬程式設計", (3, 93), (3, 85)), ("模擬一年國文", (2, 87), (2, 78)),
     ("模擬管理學", (2, 70), (2, 61)), ("模擬音樂", (2, 74), None)],
    [("模擬網頁設計", (2, 94), (2, 92)), ("模擬會計學", (3, 75), (3, 77)),
     ("模擬統計學", (3, 74), None), ("模擬行銷管理", (2, 87), (2, 85))],
    [("模擬資料結構", (3, 77), None), ("模擬作業系統", (2, 85), None),
     ("模擬計算機網路", None, (2, 91)), ("模擬經濟學", (3, 75), (3, 82))],
]


def _right(draw, x_right, y, text, font):
    width = draw.textlength(text, font=font)
    draw.text((x_right - width - 8, y), text, fill="black", font=font)


def render(path, years=SYNTHETIC_YEARS, *, student_line=False):
    """畫出合成成績單並存檔；回傳期望的課程列表（年級、學期、課名、學分、成績）。

    student_line：仿照正式成績單在表格正上方印一行班級與學號（假資料），
    這行文字緊貼各學年表頭，用來檢查年級表頭不會被頁首文字干擾。
    """
    big = ImageFont.truetype(MSJH_FONT, 34)
    font = ImageFont.truetype(MSJH_FONT, 30)
    small = ImageFont.truetype(MSJH_FONT, 22)
    image = Image.new("RGB", PAGE, "white")
    draw = ImageDraw.Draw(image)
    draw.text((900, 120), "合成測試學校　學生歷年成績單（假資料）", fill="black", font=big)
    if student_line:
        draw.text((700, TOP_RULE - 50), "四年忠班　　學號：000000000　　姓名：測試學生", fill="black", font=font)
    expected = []
    for panel_index in range(5):
        left = 120 + panel_index * (PANEL + 30)
        edges = [left, left + MARKER, left + MARKER + NAME] + [left + MARKER + NAME + NUMBER * i for i in range(1, 5)]
        for x in edges:
            draw.line([(x, TOP_RULE), (x, BOTTOM_RULE)], fill="black", width=3)
        for y in (TOP_RULE, HEADER_RULE, BODY_RULE, SUMMARY_RULE, BOTTOM_RULE):
            draw.line([(left, y), (edges[-1], y)], fill="black", width=3)
        year_no = panel_index + 1
        draw.text((left + PANEL // 2 - 70, TOP_RULE + 12), f"第 {year_no} 學年", fill="black", font=font)
        if panel_index < len(years):
            draw.text((left + 110, TOP_RULE + 58), f"{110 + year_no} 年 8 月至 {111 + year_no} 年 6 月", fill="black", font=small)
        draw.text((left + MARKER + NAME + 10, TOP_RULE + 100), "第一學期", fill="black", font=small)
        draw.text((left + MARKER + NAME + NUMBER * 2 + 10, TOP_RULE + 100), "第二學期", fill="black", font=small)
        draw.text((left + MARKER + 120, TOP_RULE + 125), "科　目", fill="black", font=font)
        if panel_index >= len(years):
            continue
        for row, (name, first, second) in enumerate(years[panel_index]):
            y = BODY_RULE + 14 + row * ROW
            draw.text((left + 10, y), "必", fill="black", font=small)
            draw.text((left + MARKER + 10, y), name, fill="black", font=font)
            for semester, values in enumerate((first, second)):
                if values is None:
                    continue
                credits, score = values
                base = left + MARKER + NAME + NUMBER * semester * 2
                _right(draw, base + NUMBER, y, str(credits), font)
                _right(draw, base + NUMBER * 2, y, str(score), font)
                expected.append({"grade_level": f"{year_no}年級", "semester": ("第一學期", "第二學期")[semester],
                                 "course_name": name, "credits": credits, "score": score})
    image.save(path)
    return expected
