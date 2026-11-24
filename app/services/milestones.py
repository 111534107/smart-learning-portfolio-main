"""里程碑：學生做到某件事時，小助手頒獎（彩蛋）。只讀取資料，不改任何東西；看過與否存在瀏覽器。"""

from app.models import CredentialRecord, LearningProfileOutput, StudentTarget
from app.services import autobiography_service

CREDENTIAL_GOAL = 3


def reached(student):
    """回傳學生已達成的里程碑列表（每項 {key, title, text}）。"""
    if student is None or student.role != "student":
        return []
    items = []
    outputs = (LearningProfileOutput.query
               .filter_by(student_id=student.id, output_type=autobiography_service.OUTPUT_TYPE).all())
    drafted = {(o.content_json or {}).get("program_id") for o in outputs}
    if outputs:
        items.append({"key": "first_autobiography", "title": "第一份自傳完成",
                      "text": "你的第一份自傳草稿完成了，改成自己的話就更棒。"})
    programs = [t.program.id for t in StudentTarget.query.filter_by(student_id=student.id).all()]
    if len(programs) >= 2 and all(pid in drafted for pid in programs):
        items.append({"key": "all_targets_drafted", "title": "所有目標校系都有自傳了",
                      "text": f"{len(programs)} 所校系都有自傳草稿，可以逐份檢查再送導師。"})
    credentials = CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").count()
    if credentials >= CREDENTIAL_GOAL:
        items.append({"key": "credentials_3", "title": f"證照滿 {CREDENTIAL_GOAL} 張",
                      "text": f"你已經確認了 {credentials} 張證照，備審的硬實力很扎實。"})
    return items
