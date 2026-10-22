"""產生「中華民國技術士證」版型的合成圖片（全部假資料），供證照 OCR 測試使用。

刻意把卡片放在有留白、比例不同的畫布上，模擬學生拍照或截圖時邊界不一的情況；
組員原本用固定比例切欄位，這種圖片的欄位位置會整個錯開。
"""
from PIL import Image, ImageDraw, ImageFont

MSJH_FONT = "C:/Windows/Fonts/msjh.ttc"

SYNTHETIC_CERTIFICATE = {
    "occupation": "會計事務－資訊",
    "level": "丙級",
    "certificate_number": "999-0000001",
    "birth_date": "民國96年01月01日",
    "effective_date": "民國113年11月13日",
    "issue_date": "民國113年11月20日",
}


def render(path, margin=(160, 260)):
    """畫出合成技術士證並存檔；margin 是卡片左上角離畫布邊界的距離（像素）。"""
    left, top = margin
    title = ImageFont.truetype(MSJH_FONT, 96)
    label = ImageFont.truetype(MSJH_FONT, 44)
    value = ImageFont.truetype(MSJH_FONT, 58)
    image = Image.new("RGB", (left + 1700, top + 1150), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([left, top, left + 1620, top + 1080], fill=(222, 238, 205))
    draw.text((left + 280, top + 90), "中華民國技術士證", fill="black", font=title)
    draw.rectangle([left + 1150, top + 280, left + 1450, top + 600], fill="white", outline="black", width=3)
    draw.text((left + 1220, top + 420), "照片", fill="black", font=label)
    rows = [
        (300, "身分證統一編號", "（合成測試）"),
        (440, "出生日期", SYNTHETIC_CERTIFICATE["birth_date"]),
        (560, "技術士證總編號", SYNTHETIC_CERTIFICATE["certificate_number"]),
        (690, "職類（項）", SYNTHETIC_CERTIFICATE["occupation"]),
    ]
    for y, label_text, value_text in rows:
        draw.text((left + 40, top + y + 10), label_text, fill="black", font=label)
        draw.text((left + 420, top + y), value_text, fill="black", font=value)
    draw.text((left + 40, top + 780), "名稱", fill="black", font=label)
    draw.text((left + 1050, top + 790), "級別", fill="black", font=label)
    draw.text((left + 1220, top + 780), SYNTHETIC_CERTIFICATE["level"], fill="black", font=value)
    draw.text((left + 40, top + 930), "生效日期", fill="black", font=label)
    draw.text((left + 260, top + 920), SYNTHETIC_CERTIFICATE["effective_date"], fill="black", font=value)
    draw.text((left + 820, top + 930), "製發日期", fill="black", font=label)
    draw.text((left + 1040, top + 920), SYNTHETIC_CERTIFICATE["issue_date"], fill="black", font=value)
    draw.text((left + 1360, top + 1020), "勞動部發", fill="black", font=label)
    image.save(path)
    return SYNTHETIC_CERTIFICATE
