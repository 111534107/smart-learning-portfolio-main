"""升學 Agent 依檔案編號取檔（規格 AI_設計規格_Agent分工規劃_2026-10-22.md 第〇節「雲端（T3）」）。

原則：
- AI 不直接瀏覽 Google 雲端硬碟，也不拿原始檔（原始照片不送外部 AI）：工具只讀系統資料庫裡
  OCR／學生確認流程留下的欄位，依檔案編號、經後端檢查擁有者後才回傳。
- 只回這次需要的欄位（白名單）；不回檔名、檔案位置、OCR 原文與座標。
- 回傳前一律去識別化（姓名、學號、證號等），因為結果會交回給外部 AI 判斷下一步。
- 別人的檔案和不存在的檔案回同一句話，不透露檔案存不存在。
"""

from app.models import SourceDocument
from app.services import deidentify
from app.services.agent_engine import Tool, ToolError

NOT_FOUND = "找不到這份檔案，或你沒有權限查看。"
PENDING = ("queued", "processing")
TYPE_LABELS = {"transcript": "成績單", "credential": "證照", "award_record": "獎懲記錄"}
STATUS_LABELS = {"queued": "排隊辨識中", "processing": "辨識中", "extracted": "待學生確認",
                 "confirmed": "學生已確認", "analysis_failed": "辨識失敗"}
# 各類檔案交給 AI 的欄位（白名單）；其他欄位一律不回
FIELDS = {
    "courses": ("school_year", "semester", "grade_level", "course_name", "credits", "score"),
    "credentials": ("credential_name", "level", "issuing_organization", "issue_date"),
    "rows": ("reason", "category", "school_year", "semester"),
}
MAX_ITEMS = 80


def _pick(items, keys):
    return [{key: item[key] for key in keys if item.get(key) not in (None, "")}
            for item in (items or [])[:MAX_ITEMS] if isinstance(item, dict)]


def document_tools(student):
    """這位學生自己的檔案清單與單一檔案內容；兩個工具都只讀。"""

    def known():
        return deidentify.known_values_for(student)

    def list_documents():
        documents = SourceDocument.query.filter_by(owner_id=student.id).order_by(SourceDocument.id).all()
        items = [{"document_id": str(d.id), "document_type": d.document_type,
                  "type_label": TYPE_LABELS.get(d.document_type, d.document_type),
                  "status": d.status, "uploaded_on": d.created_at.date().isoformat() if d.created_at else ""}
                 for d in documents]
        return {"summary": f"你上傳了 {len(items)} 份檔案。", "documents": items}

    def get_document(document_id=""):
        text = str(document_id).strip()
        if not text.isdigit():
            raise ToolError("檔案編號要是數字（從檔案清單取得）。")
        document = SourceDocument.query.filter_by(id=int(text), owner_id=student.id).first()
        if document is None:
            raise ToolError(NOT_FOUND)
        if document.status in PENDING:
            raise ToolError("這份檔案還在辨識，請等辨識完成再查。")
        # 未經學生確認的 OCR 資料不得進入 AI 分析：還沒確認就不回任何欄位內容
        confirmed = document.status == "confirmed"
        result = ((document.extraction.result_json if document.extraction else None) or {}) if confirmed else {}
        payload = {
            "document_id": str(document.id),
            "document_type": document.document_type,
            "status": document.status,
            "uploaded_on": document.created_at.date().isoformat() if document.created_at else "",
        }
        counts = []
        for key, keys in FIELDS.items():
            if result.get(key):
                payload[key] = _pick(result[key], keys)
                counts.append(f"{len(payload[key])} 筆")
        label = TYPE_LABELS.get(document.document_type, document.document_type)
        if confirmed:
            payload["summary"] = (f"{label}（{STATUS_LABELS.get(document.status, document.status)}）"
                                  + (f"：{'、'.join(counts)}資料。" if counts else "：沒有辨識出資料。"))
        else:
            payload["summary"] = f"{label}（{STATUS_LABELS.get(document.status, document.status)}）：學生還沒確認，內容不提供。"
            payload["note"] = "學生還沒確認這份資料，請提醒學生先到學習檔案確認，確認後才能使用。"
        return deidentify.redact(payload, known())

    return [
        Tool("list_my_documents", "查我的檔案", "列出學生自己上傳的檔案編號、類別、狀態與上傳日期（不含檔名）。", list_documents),
        Tool("get_my_document", "取檔案內容",
             "依檔案編號取學生自己的一份檔案中，學生已確認的內容（課程、證照、獎懲事由），已去識別化；不含原始檔。尚未確認的檔案只回傳狀態與摘要。",
             get_document, params={"document_id": "檔案編號（從檔案清單取得）"}),
    ]
