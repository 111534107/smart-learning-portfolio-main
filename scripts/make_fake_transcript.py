"""產生假成績單圖片（僅為測試資料）：照學校成績單版型，兩個學年各一欄，每欄是 科目｜上學分｜上成績｜下學分｜下成績。

用法：python scripts/make_fake_transcript.py 輸出.png
同時寫出 輸出.png.json（正確答案：年級、學期、課名、學分、成績），驗收腳本用它比對 OCR 結果。
學號、姓名都是展示用假資料；不要改成真實學生的資料。
課名都要在 111、113 學年度入學的修業科目表裡（2026-11-16 B26：原本「計算機概論」「資訊管理導論」「資料庫管理」對不到，
畢業門檻三項學分都變「待人工確認」）；示範學生 113534901 原有的課和這張成績單同名、同年級學期、同分數。
"""
import json
import sys

from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1]
FONT = "C:/Windows/Fonts/msjh.ttc"  # Windows 微軟正黑體；其他系統請改成可用的中文字型
f_big, f, f_small = ImageFont.truetype(FONT, 44), ImageFont.truetype(FONT, 30), ImageFont.truetype(FONT, 26)

YEARS = [
    ("第1學年", "113年8月至114年6月", [
        ("資訊科技", 3, 86, 0, None), ("程式設計", 3, 91, 3, 88), ("國文", 2, 80, 2, 83),
        ("英文", 2, 77, 2, 79), ("數學", 3, 72, 3, 68), ("網頁設計", 0, None, 3, 93),
        ("體育", 1, 85, 1, 87), ("管理學", 2, 89, 0, None)]),
    ("第2學年", "114年8月至115年6月", [
        ("商業套裝軟體", 3, 90, 0, None), ("管理資訊系統", 0, None, 3, 84), ("統計學", 3, 75, 3, 78),
        ("會計學", 3, 81, 3, 79), ("英文", 2, 82, 2, 85), ("資料結構", 0, None, 3, 87),
        ("體育", 1, 88, 1, 90), ("物件導向程式設計", 3, 92, 0, None)]),
]
W, H = 2400, 1700
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
d.text((W // 2, 60), "康寧大學五專部 學生歷年成績表（僅為測試資料）", font=f_big, fill="black", anchor="mm")
d.text((120, 115), "科別：資訊管理科　班級：資管科三甲　學號：113534901　姓名：王小明（假資料）", font=f, fill="black")

panel_w, left0, top, row_h, rows = 1080, 100, 300, 68, 12
cols = [0, 70, 560, 690, 820, 950, panel_w]  # 標記｜科目｜上學分｜上成績｜下學分｜下成績
expected = []
for p, (header, period, courses) in enumerate(YEARS):
    x0 = left0 + p * (panel_w + 60)
    # 學年表頭在表格框內最上面一列（和學校成績單一樣），下面才是欄位名稱列
    y_top = top - row_h
    d.text((x0 + panel_w // 2, y_top + row_h // 2), f"{header}　{period}", font=f, fill="black", anchor="mm")
    d.line([(x0, y_top), (x0, top)], fill="black", width=3)
    d.line([(x0 + panel_w, y_top), (x0 + panel_w, top)], fill="black", width=3)
    y_head, y_body = top, top + row_h
    y_end = y_body + rows * row_h
    for c in cols:  # 直線
        d.line([(x0 + c, y_head), (x0 + c, y_end)], fill="black", width=3)
    for y in (y_top, y_head, y_body, y_end):  # 表頭與表身外框的橫線
        d.line([(x0, y), (x0 + panel_w, y)], fill="black", width=3)
    for label, (a, b) in zip(["", "科目名稱", "學分", "成績", "學分", "成績"], zip(cols, cols[1:])):
        d.text((x0 + (a + b) // 2, y_head + row_h // 2), label, font=f_small, fill="black", anchor="mm")
    for r, (name, c1, s1, c2, s2) in enumerate(courses):
        y = y_body + r * row_h + row_h // 2
        d.text((x0 + cols[1] + 14, y), name, font=f, fill="black", anchor="lm")
        for value, (a, b) in ((c1 or "", cols[2:4]), (s1 or "", cols[3:5]), (c2 or "", cols[4:6]), (s2 or "", cols[5:7])):
            if value != "":
                d.text((x0 + (a + b) // 2, y), str(value), font=f, fill="black", anchor="mm")
        for sem, credit, score in (("上", c1, s1), ("下", c2, s2)):
            if credit:
                expected.append({"grade": p + 1, "semester": sem, "name": name, "credits": credit, "score": score})
d.text((120, H - 80), "本成績表為系統測試用合成資料，非真實學生成績。", font=f_small, fill="black")
img.save(OUT)
open(OUT + ".json", "w", encoding="utf-8").write(json.dumps(expected, ensure_ascii=False))
