"""依目前模型中繼資料產生資料字典，不連線資料庫。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.models  # noqa: F401
from app.extensions import db
from docx import Document
from docx.shared import Pt

OUT = ROOT / "docs" / "01_正式規格"
NAMES = {"id": "識別碼", "user_id": "使用者識別碼", "student_id": "學生識別碼", "created_at": "建立時間", "updated_at": "更新時間", "deleted_at": "刪除時間", "name": "名稱", "title": "標題", "status": "狀態", "description": "說明"}

def meaning(column):
    return column.comment or NAMES.get(column.name, "待補")

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tables = sorted(db.metadata.tables.values(), key=lambda t: t.name)
    md = ["# 資料字典（2026-11-19）", "", f"依本工作目錄 app/models 的 SQLAlchemy 模型產生，共 {len(tables)} 張表；不代表任何實際資料庫的現況。未有註解且無法可靠推定的說明標為待補。", ""]
    doc = Document()
    doc.add_heading("資料字典（2026-11-19）", 0)
    doc.add_paragraph(md[2])
    doc.styles["Normal"].font.size = Pt(9)
    headers = ["欄位", "型別", "長度", "可空值", "主鍵", "外鍵", "欄位說明"]
    for table in tables:
        desc = table.comment or "待補"
        title = f"{table.name}（{desc}）"
        md += [f"## {title}", "", "| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        doc.add_heading(title, level=2)
        dt = doc.add_table(rows=1, cols=len(headers))
        dt.style = "Table Grid"
        for cell, value in zip(dt.rows[0].cells, headers):
            cell.text = value
        for c in table.columns:
            length = getattr(c.type, "length", None)
            values = [c.name, str(c.type), str(length) if length is not None else "—", "是" if c.nullable else "否", "是" if c.primary_key else "否", "、".join(sorted(f.target_fullname for f in c.foreign_keys)) or "—", meaning(c)]
            md.append("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in values) + " |")
            for cell, value in zip(dt.add_row().cells, values):
                cell.text = str(value)
        md.append("")
    (OUT / "資料字典_2026-11-19.md").write_text("\n".join(md), encoding="utf-8")
    doc.save(OUT / "資料字典_2026-11-19.docx")
    print(f"已匯出 {len(tables)} 張表")

if __name__ == "__main__":
    main()
