"""自傳小助手「幫我改」服務（A4 規格）。

功能與安全規範：
1. 學生或導師選取一段自傳文字，由小助手提供改寫建議。
2. 送往 AI 前進行個資去識別化（學生姓名、學號等換為通用代號），回傳後再行還原。
3. AI 改寫結果以「建議修改」（AutobiographySuggestion，狀態為 pending）呈現，絕不直接覆蓋原文。
4. 防造假檢查（Anti-Fabrication Check）：嚴禁新增原文未出現的新數字或未經確認的經歷。
5. 支援離線規則／模擬降級，確保在無外部 AI 金鑰環境下穩定運作。
"""

import re
from datetime import datetime, timezone
from unicodedata import normalize

from flask import current_app

from app.extensions import db
from app.models import AutobiographySuggestion, Notification
from app.services import audit_service, deidentify
from app.services.autobiography_suggestion_service import MAX_REPLACEMENT, MAX_SELECTION, SuggestionError

CN_DIGITS = {
    "零": "0", "〇": "0",
    "一": "1", "壹": "1",
    "二": "2", "貳": "2", "兩": "2",
    "三": "3", "參": "3",
    "四": "4", "肆": "4",
    "五": "5", "伍": "5",
    "六": "6", "陸": "6",
    "七": "7", "柒": "7",
    "八": "8", "捌": "8",
    "九": "9", "玖": "9",
    "十": "10", "拾": "10",
    "百": "100", "佰": "100",
    "千": "1000", "仟": "1000",
    "萬": "10000",
}

CLAIM_CLAUSES = re.compile(r"[，,。！？!?；;：:\n]")
SENTENCE_SPANS = re.compile(r"[^。！？!?；;\n]+")
ATTENDANCE_TERMS = re.compile(
    r"缺[曠旷勤課课席]|[曠旷][課课]|出缺勤|翹[課课]|[遲迟]到|早退|[請请]假|"
    r"事假|病假|生理假|公假|[喪丧]假|出席率|(?:出席|到[課课])(?:紀錄|記錄|记录)"
)
UNASSERTED_CLAIM = re.compile(r"(?:尚未|沒有|還沒|從未|未曾|未能|希望|計畫|打算|預計|想要|目標是)")
CLAIM_NAME_MARKS = re.compile(r"[\s「」『』“”\"']")
CLAIM_NAME_PREFIX = re.compile(r"^(?:以及|及|與|和|並)")
GENERIC_CLUB = re.compile(r"(?:各類|各項|各種|多元|不同|相關|多個|各個|校內|學校|學生)?社團")
CLUB_NAME = r"[^、，,:：]{0,60}?(?:學生會|社團|協會|學會|社(?![會區交流群長員]))"
OFFICE_ACTION = r"(?:擔任|出任|曾任|現任|當過|當上|兼任)"
OFFICE_TITLE = r"(?:社長助理|會長助理|副社長|副會長|副組長|社長|會長|活動長|負責人|幹部|組長|總務|文書)"
CLUB_ROLE_CLAIM = re.compile(
    rf"(?:加入|參加|參與|(?<!現)在|於)\s*[了過]?\s*(?P<club_first>{CLUB_NAME})"
    rf"[\s」』”\"']*(?:中|裡)?\s*[,，]?\s*(?:並|且|也|後)?\s*(?:曾)?"
    rf"(?:{OFFICE_ACTION}|當|是)\s*[了過]?\s*(?:社團)?(?P<office_last>{OFFICE_TITLE})"
    rf"|(?:{OFFICE_ACTION}|我是|曾是|身為)\s*[了過]?\s*(?P<club_last>{CLUB_NAME})"
    rf"[\s」』”\"']*(?:的)?\s*(?P<office_first>{OFFICE_TITLE})"
)
CLAIM_RULES = (
    ("獎項", re.compile(r"獲頒|榮獲|獲得|贏得|拿下|拿到|得到|得過|獲"),
     re.compile(r"[^、]{0,60}?(?:獎學金|獎項|獎牌|獎章|獎(?!勵)|特優|優勝(?!獎)|佳作|金牌|銀牌|銅牌|冠軍|亞軍|季軍)")),
    ("證照", re.compile(r"考取|考到|取得|通過|持有|拿到|獲得|獲頒"),
     re.compile(r"[^、]{0,60}?(?:合格證明|證照|證書|執照|認證|[甲乙丙丁]級(?:技術士)?)")),
    ("社團名稱", re.compile(r"加入|參加|參與|投入|隸屬於|我是|身為|曾是"), re.compile(CLUB_NAME)),
)


class FabricationError(SuggestionError):
    """防造假檢查未通過：新增了未經確認的數字或經歷。"""


def extract_numbers(text: str) -> set[str]:
    """擷取文字中的所有數字（包含阿拉伯數字與中文字數字），轉換為可比對字串集合。"""
    if not text:
        return set()
    nums = set(re.findall(r"\d+", text))
    # 「參加／參與」的「參」是動詞的一部分，單獨當數字使用時仍須比對。
    text = re.sub(r"參(?=[加與])", "", text)
    for cn_char, val in CN_DIGITS.items():
        if cn_char in text:
            nums.add(val)
            nums.add(cn_char)
    return nums


def _club_office_claims(text: str) -> set[tuple[str, str]]:
    """將已擔任的職務和社團名稱配對，避免把某個社團或職務換成另一個。"""
    claims = set()
    for span in SENTENCE_SPANS.finditer(text):
        sentence = span.group()
        for match in CLUB_ROLE_CLAIM.finditer(sentence):
            prefix = sentence[:match.start()].rsplit(",", 1)[-1].rstrip()
            if UNASSERTED_CLAIM.search(prefix) or prefix.endswith(("想", "未", "不")):
                continue
            club = CLAIM_NAME_MARKS.sub("", match["club_first"] or match["club_last"]).casefold()
            office = match["office_last"] or match["office_first"]
            if GENERIC_CLUB.fullmatch(club):
                club = "社團"
            else:
                claims.add(("社團名稱", club))
            claims.add(("社團職務", f"{club}：{office}"))
    return claims


def _experience_claims(text: str) -> set[tuple[str, str]]:
    """找出具名、已發生的獎項、證照和社團經歷，讓潤飾可保留同一名稱。"""
    text = normalize("NFKC", text)
    claims = _club_office_claims(text)
    for clause in CLAIM_CLAUSES.split(text):
        for category, verbs, names in CLAIM_RULES:
            verb = verbs.search(clause)
            if not verb or UNASSERTED_CLAIM.search(clause[:verb.start()]):
                continue
            tail = re.sub(r"^\s*[了過]", "", clause[verb.end():])
            for index, match in enumerate(names.finditer(tail)):
                name = CLAIM_NAME_MARKS.sub("", match.group()).casefold()
                if index:
                    name = CLAIM_NAME_PREFIX.sub("", name)
                if category != "社團名稱" or not GENERIC_CLUB.fullmatch(name):
                    claims.add((category, name))
    return claims


def check_fabrication(original_text: str, revised_text: str) -> None:
    """拒絕選取原文中沒有的新數字或可辨識的具體經歷。"""
    orig_nums = extract_numbers(original_text)
    rev_nums = extract_numbers(revised_text)
    new_nums = rev_nums - orig_nums
    if new_nums:
        # 濾出可讀的新增數字清單
        display_diff = sorted(new_nums)
        raise FabricationError(
            f"小助手偵測到修改文字新增了原文未提及的數字「{', '.join(display_diff)}」，為維護自傳真實性，禁止新增未經確認的數字。"
        )

    added_claims = _experience_claims(revised_text) - _experience_claims(original_text)
    if added_claims:
        categories = "、".join(sorted({category for category, _ in added_claims}))
        raise FabricationError(f"小助手偵測到修改文字新增了選取原文未確認的{categories}，無法建立這則建議。")


def _selection_overlaps_attendance(text: str, start: int, end: int) -> bool:
    """同一句內的節數等片段也可能是缺曠資料，須比對選取範圍的上下文。"""
    return any(
        sentence.start() < end and start < sentence.end()
        and ATTENDANCE_TERMS.search(re.sub(r"\s+", "", sentence.group()))
        for sentence in SENTENCE_SPANS.finditer(text)
    )


def redact_personal_info(text: str, student) -> str:
    """送 AI 前遮蔽個資：姓名、學號等。"""
    if not text:
        return ""
    known = []
    if student.display_name and len(student.display_name.strip()) >= 2:
        known.append((student.display_name.strip(), "[學生姓名]"))
    profile = getattr(student, "student_profile", None)
    student_no = getattr(profile, "student_no", None) if profile else None
    if student_no and len(str(student_no).strip()) >= 2:
        known.append((str(student_no).strip(), "[學號]"))
    elif student.username and len(student.username.strip()) >= 2:
        known.append((student.username.strip(), "[學號]"))

    return deidentify.redact(text, known=known)


def unredact_personal_info(text: str, student) -> str:
    """回傳後將代號換回學生真實個資。"""
    if not text:
        return ""
    res = text
    if student.display_name:
        res = res.replace("[學生姓名]", student.display_name)
        res = res.replace("[姓名]", student.display_name)
    profile = getattr(student, "student_profile", None)
    student_no = getattr(profile, "student_no", None) if profile else None
    target_no = str(student_no) if student_no else student.username
    if target_no:
        res = res.replace("[學號]", target_no)
        res = res.replace("[帳號]", target_no)
    return res


def _generate_rule_based_rewrite(redacted_text: str) -> str:
    """無 AI 服務可用時的精簡順暢改寫降級方案。"""
    cleaned = redacted_text.strip()
    replacements = [
        ("我覺得", ""),
        ("我認為", ""),
        ("非常非常", "十分"),
        ("很大的一個", "重大"),
        ("很多很多", "許多"),
        ("有參加過", "曾參與"),
    ]
    for old, new in replacements:
        cleaned = cleaned.replace(old, new)
    return cleaned.strip() or redacted_text


def generate_rewrite(redacted_text: str, style_hint: str = "concise", callers=None) -> str:
    """呼叫 AI 進行語句改寫與潤飾。"""
    from app.services import ai_gateway

    prompt = (
        "你是升學自傳寫作小助手。請將下列這段由學生自傳中選取的文字進行語句精修與潤飾，使其語氣更加真誠、具體、精煉且專業。\n"
        "【嚴格規定】\n"
        "1. 絕對不可新增原文中沒有出現過的任何數字、經歷、獎項、名次、證照、社團名稱、社團職務或專案。\n"
        "2. 保留第一人稱視角與原始事件核心脈絡。\n"
        "3. 若文字包含 [學生姓名] 或 [學號] 代號，必須原樣保留。\n"
        "4. 僅回傳 JSON 格式：{\"rewritten\": \"修改後的文字\"}。\n\n"
        f"待修改文字：\n{redacted_text}"
    )
    schema = {
        "type": "object",
        "properties": {
            "rewritten": {"type": "string", "description": "改寫後的句子"}
        },
        "required": ["rewritten"]
    }

    try:
        result, _used = ai_gateway.generate_json(prompt, schema, callers=callers)
        rewritten = result.get("rewritten", "").strip()
        if rewritten:
            return rewritten
    except Exception:
        pass
    return _generate_rule_based_rewrite(redacted_text)


def rewrite_selection(
    actor,
    student,
    output,
    paragraph: int,
    start: int,
    end: int,
    replacement_override: str | None = None,
    callers=None
) -> AutobiographySuggestion:
    """選取文字後呼叫小助手幫我改，建立一筆 AutobiographySuggestion（pending）。"""
    paragraphs = (output.content_json or {}).get("paragraphs", [])
    if paragraph is None or not (0 <= paragraph < len(paragraphs)):
        raise SuggestionError("找不到這一段，請重新整理頁面。")
    text = paragraphs[paragraph].get("text", "")
    if start is None or end is None or not (0 <= start < end <= len(text)):
        raise SuggestionError("請先選取要請小助手修改的文字範圍。")
    if end - start > MAX_SELECTION:
        raise SuggestionError(f"一次最多選取 {MAX_SELECTION} 字。")
    if _selection_overlaps_attendance(text, start, end):
        raise SuggestionError("選取範圍包含缺曠或請假資料，請重新選取不含這些紀錄的句子。")

    original_selection = text[start:end]

    if replacement_override is not None:
        raw_revised = replacement_override
    else:
        # 1. 遮蔽個資
        redacted = redact_personal_info(original_selection, student)
        # 2. 送 AI 改寫
        raw_revised = generate_rewrite(redacted, callers=callers)

    # 3. 還原個資
    unredacted = unredact_personal_info(raw_revised, student).strip()
    if not unredacted:
        raise SuggestionError("小助手未回傳有效的修改建議。")
    if len(unredacted) > MAX_REPLACEMENT:
        unredacted = unredacted[:MAX_REPLACEMENT]

    # 4. 防造假檢查
    check_fabrication(original_selection, unredacted)

    # 5. 建立建議修改（以建議修改呈現，不覆蓋原文）
    program_id = output.content_json.get("program_id")
    suggestion = AutobiographySuggestion(
        student_id=student.id,
        program_id=program_id,
        output_id=output.id,
        paragraph=paragraph,
        start=start,
        end=end,
        original=original_selection,
        replacement=unredacted,
        author_id=actor.id,
        status="pending"
    )
    db.session.add(suggestion)
    db.session.flush()

    # 記錄審計日誌
    audit_service.record(
        actor,
        "autobiography.assistant_rewrite",
        "autobiography_suggestion",
        suggestion.id,
        detail={
            "student_id": student.id,
            "program_id": program_id,
            "paragraph": paragraph,
            "chars": end - start,
            "replacement_len": len(unredacted)
        }
    )
    db.session.commit()
    return suggestion
