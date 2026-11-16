"""產生 ERD 的 Mermaid 原始碼：一張全部資料表的總覽，加上依功能拆開的三張分圖。

資料表太多（29 張）時一張圖會太寬，規格書改用三張分圖（圖 18-1～18-3）；
總覽 D-09-erd-v2.mmd 留在 diagrams.md 當參考。

修改方式：改下面 ENTITIES（欄位）或 RELATIONS（關係），再到 docs/images 執行
    python D-09-erd-build.py
會重新寫出四個 .mmd，接著用 Mermaid CLI 匯出 PNG／SVG（見 diagrams.md 最後一節）。

欄位說明寫「待新增」代表規格已定案、程式還沒有。
"""
from pathlib import Path

HEADER = (
    "%%{init: {'theme':'base','themeVariables': {'fontFamily':'Arial, Microsoft JhengHei, sans-serif',"
    "'fontSize':'14px','primaryColor':'#F3F4F6','primaryTextColor':'#111827','primaryBorderColor':'#9CA3AF',"
    "'lineColor':'#6B7280'},'er':{'minEntityWidth':160,'entityPadding':20}}}%%\nerDiagram\n"
)

# 名稱：(中文標題, [欄位列])
ENTITIES = {
    "USERS": ("使用者", [
        'int id PK', 'string username "學號或帳號"', 'string role "student teacher staff admin"', 'bool is_active']),
    "STUDENT_PROFILES": ("學生資料", [
        'int id PK', 'int user_id FK', 'string student_no', 'string class_name "班級"',
        'int admission_year "入學學年度（管理者匯入）"']),
    "CLASS_ADVISORS": ("導師班級", [
        'int id PK', 'int teacher_id FK', 'string class_name', 'int school_year']),
    "SOURCE_DOCUMENTS": ("上傳原始檔", [
        'int id PK', 'int owner_id FK', 'string document_type "成績單 證照 獎懲記錄等"', 'string file_path', 'string status',
        'string storage_backend "local；drive（個人雲端硬碟測試中）"', 'string drive_file_id "Google Drive 檔案 ID"',
        'string lifecycle_status "active soft_deleted（保存期限待學校政策）"', 'datetime deleted_at "軟刪除時間"']),
    "DOCUMENT_EXTRACTIONS": ("辨識結果", [
        'int id PK', 'int source_document_id FK', 'string status "辨識狀態"', 'json notes "AI 註記（待新增）"',
        'datetime confirmed_at "學生確認時間"']),
    "LEARNING_COURSE_RECORDS": ("成績與學分", [
        'int id PK', 'int student_id FK', 'int source_document_id FK', 'int school_year', 'string semester',
        'string course_code "課號（待新增）"', 'string course_name', 'int credits', 'int score',
        'string source_kind "網頁成績 紙本成績單（待新增）"']),
    "CREDENTIAL_RECORDS": ("證照", [
        'int id PK', 'int student_id FK', 'int source_document_id FK', 'string credential_name', 'string level']),
    "PORTFOLIOS": ("活動競賽服務幹部", [
        'int id PK', 'int student_id FK', 'string category "活動 競賽 服務學習 幹部經歷"', 'string title',
        'string evidence_source "證明來源"', 'string status']),
    "PORTFOLIO_EVIDENCE": ("佐證檔案", [
        'int id PK', 'int portfolio_id FK', 'string file_path', 'string external_url']),
    "ATTENDANCE_SUMMARIES": ("缺曠合計（待新增）", [
        'int id PK', 'int student_id FK', 'int school_year', 'string semester',
        'json leave_totals "各假別合計，不存逐日明細"', 'int one_third_hours "應上課三分之一時數"',
        'int absent_hours "至今缺課總時數"', 'bool include_in_package "放進備審，預設否"',
        'datetime include_confirmed_at "學生看過提醒並確認"']),
    "COURSE_RULES": ("課程規則與修業科目表", [
        'int id PK', 'int school_year "入學年度"', 'string course_name', 'string category "必修 選修等"',
        'string requirement_type', 'int credits']),
    "AWARD_CERTIFICATES": ("電子獎狀", [
        'int id PK', 'int student_id FK', 'int portfolio_id FK', 'string title "證明類別：科上派的服務 TA 社團"',
        'string status "pending approved returned"', 'string verify_code "驗證碼"', 'int reviewed_by_id FK "核准的科辦"']),
    "ADMISSION_RULE_VERSIONS": ("校系與年度", [
        'int id PK', 'string program_code "志願代碼"', 'string school_name "學校"', 'string department_name "科系"',
        'string admission_category "招生類別"', 'int admission_year "學年度"', 'string source_url "資料來源"',
        'string status "candidate published"', 'string data_origin "manual agent"',
        'json details_json "資格 文件 時程 連結 特色（待新增）"', 'date checked_at "最後確認日期"']),
    "ADMISSION_RULE_ITEMS": ("校系備審要求", [
        'int id PK', 'int rule_version_id FK', 'string source_item_name "簡章原始項目名稱"', 'int weight_percent "加權百分比"',
        'string mapped_categories "對應資料類別"', 'string mapping_status "確定 待確認"', 'bool is_required']),
    "STUDENT_TARGETS": ("學生目標校系", [
        'int id PK', 'int student_id FK', 'int rule_version_id FK', 'datetime selected_at']),
    "LEARNING_PROFILE_OUTPUTS": ("自傳版本與備審產出", [
        'int id PK', 'int student_id FK', 'string output_type "自傳 備審資料"', 'int version "第幾版"',
        'int edited_by FK "誰存的"', 'datetime created_at']),
    "PACKAGE_REVIEWS": ("導師確認紀錄", [
        'int id PK', 'int student_id FK', 'int rule_version_id FK "目標校系"', 'int teacher_id FK "確認的導師"',
        'string status "pending confirmed needs_revision"', 'json snapshot_json "送審快照：事實、自傳版本、完成度"',
        'string comment "修改建議"']),
    "AUTOBIOGRAPHY_COMMENTS": ("段落註解（待新增）", [
        'int id PK', 'int output_id FK "寫在哪個自傳版本"', 'int paragraph_index "第幾段"', 'int author_id FK "哪位老師或學生"',
        'int parent_id FK "回覆哪一則"', 'string body', 'datetime created_at', 'datetime resolved_at "已處理"', 'int resolved_by FK']),
    "AI_DAILY_USAGE": ("每日 AI 用量", [
        'int id PK', 'int user_id FK', 'date usage_date', 'string key_kind "school own"', 'int count']),
    "PUBLIC_SOURCES": ("資料來源", [
        'int id PK', 'string name', 'string url', 'string source_type "二技招生 資管科官網 資圖中心 行事曆"',
        'bool is_active', 'string check_status "正常 失效（待新增）"', 'string last_error "失效原因（待新增）"']),
    "PUBLIC_SOURCE_SNAPSHOTS": ("來源檢查紀錄", [
        'int id PK', 'int source_id FK', 'string content_hash "內容雜湊，每次都保留"', 'datetime fetched_at']),
    "AGENT_TASKS": ("AI 代理任務", [
        'int id PK', 'string task_type', 'int requester_id FK', 'string status', 'string error_message']),
    "INFO_ITEMS": ("分類後的學校資訊（待新增）", [
        'int id PK', 'int snapshot_id FK', 'string title', 'string url "原始連結"', 'string topic "主題"',
        'string grades "適用年級"', 'string item_type "公告 規定 時程 比賽"', 'date valid_until "有效期間"',
        'string status "candidate published"', 'int reviewed_by FK "核對的管理員"']),
    "ANNOUNCEMENTS": ("公告（待新增）", [
        'int id PK', 'string title', 'string body', 'string audience "給哪些角色或指定學生"', 'int admission_year "對應學年度"',
        'int published_by FK', 'datetime published_at', 'datetime withdrawn_at "下架（不刪除）"']),
    "ANNOUNCEMENT_READS": ("公告已讀（待新增）", [
        'int id PK', 'int announcement_id FK', 'int user_id FK', 'datetime read_at']),
    "FORM_CATEGORIES": ("表單分類（待新增）", [
        'int id PK', 'string name', 'int sort_order', 'bool is_active']),
    "FORM_ITEMS": ("表單項目（待新增）", [
        'int id PK', 'int category_id FK', 'string name', 'bool open_to_students', 'bool open_to_teachers',
        'bool is_listed "上架中"', 'int created_by FK']),
    "FORM_ITEM_VERSIONS": ("表單版本（待新增）", [
        'int id PK', 'int item_id FK', 'int version "發布後不可覆寫"', 'string file_path', 'string file_hash',
        'int uploaded_by FK', 'datetime uploaded_at']),
    "AUDIT_LOGS": ("操作紀錄", [
        'int id PK', 'int user_id FK', 'string action "動作"', 'string target_type', 'int target_id',
        'json detail_json', 'datetime created_at']),
}

# 分圖裡只當「被參照」的資料表，只畫主鍵與一兩個辨識欄位
SHORT = {
    "USERS": ['int id PK', 'string role'],
    "ADMISSION_RULE_VERSIONS": ['int id PK', 'string program_code "志願代碼"', 'string status'],
    "LEARNING_COURSE_RECORDS": ['int id PK', 'string course_name'],
}

# (左, 關係, 右, 說明, 屬於哪幾張分圖)
RELATIONS = [
    ("USERS", "||--o|", "STUDENT_PROFILES", "學生基本資料", {1}),
    ("USERS", "||--o{", "CLASS_ADVISORS", "擔任導師", {1}),
    ("USERS", "||--o{", "SOURCE_DOCUMENTS", "上傳", {1}),
    ("SOURCE_DOCUMENTS", "||--o|", "DOCUMENT_EXTRACTIONS", "辨識結果", {1}),
    ("USERS", "||--o{", "LEARNING_COURSE_RECORDS", "成績與學分", {1}),
    ("SOURCE_DOCUMENTS", "|o--o{", "LEARNING_COURSE_RECORDS", "來源檔", {1}),
    ("COURSE_RULES", "}o..o{", "LEARNING_COURSE_RECORDS", "畢業學分檢查對照", {1}),
    ("USERS", "||--o{", "CREDENTIAL_RECORDS", "證照", {1}),
    ("SOURCE_DOCUMENTS", "|o--o{", "CREDENTIAL_RECORDS", "來源檔", {1}),
    ("USERS", "||--o{", "PORTFOLIOS", "活動競賽服務幹部", {1}),
    ("PORTFOLIOS", "||--o{", "PORTFOLIO_EVIDENCE", "佐證", {1}),
    ("USERS", "||--o{", "ATTENDANCE_SUMMARIES", "缺曠合計", {1}),
    ("USERS", "||--o{", "AWARD_CERTIFICATES", "申請電子獎狀", {1}),
    ("PORTFOLIOS", "|o--o|", "AWARD_CERTIFICATES", "列入學習資料", {1}),
    ("ADMISSION_RULE_VERSIONS", "||--o{", "ADMISSION_RULE_ITEMS", "備審要求", {2}),
    ("USERS", "||--o{", "STUDENT_TARGETS", "選擇校系", {2}),
    ("ADMISSION_RULE_VERSIONS", "||--o{", "STUDENT_TARGETS", "被選擇", {2}),
    ("USERS", "||--o{", "LEARNING_PROFILE_OUTPUTS", "自傳與備審", {2}),
    ("USERS", "||--o{", "PACKAGE_REVIEWS", "送審與確認", {2}),
    ("ADMISSION_RULE_VERSIONS", "||--o{", "PACKAGE_REVIEWS", "針對校系", {2}),
    ("LEARNING_PROFILE_OUTPUTS", "||--o{", "AUTOBIOGRAPHY_COMMENTS", "段落註解", {2}),
    ("USERS", "||--o{", "AUTOBIOGRAPHY_COMMENTS", "老師或學生寫", {2}),
    ("AUTOBIOGRAPHY_COMMENTS", "|o--o{", "AUTOBIOGRAPHY_COMMENTS", "回覆", {2}),
    ("USERS", "||--o{", "AI_DAILY_USAGE", "每日 AI 用量", {2}),
    ("PUBLIC_SOURCES", "||--o{", "PUBLIC_SOURCE_SNAPSHOTS", "每次檢查", {3}),
    ("PUBLIC_SOURCE_SNAPSHOTS", "|o--o{", "ADMISSION_RULE_VERSIONS", "擷取候選校系", {3}),
    ("PUBLIC_SOURCE_SNAPSHOTS", "||--o{", "INFO_ITEMS", "擷取並分類", {3}),
    ("USERS", "||--o{", "AGENT_TASKS", "啟動 AI 代理", {3}),
    ("USERS", "||--o{", "ANNOUNCEMENTS", "發布公告", {3}),
    ("ANNOUNCEMENTS", "||--o{", "ANNOUNCEMENT_READS", "已讀", {3}),
    ("USERS", "||--o{", "ANNOUNCEMENT_READS", "讀過", {3}),
    ("FORM_CATEGORIES", "||--o{", "FORM_ITEMS", "分類", {3}),
    ("FORM_ITEMS", "||--o{", "FORM_ITEM_VERSIONS", "版本", {3}),
    ("USERS", "||--o{", "FORM_ITEM_VERSIONS", "科辦上傳", {3}),
    ("USERS", "||--o{", "AUDIT_LOGS", "操作紀錄", {3}),
]

PARTS = {
    1: ("D-09-erd-part1-learning.mmd", [
        "USERS", "STUDENT_PROFILES", "CLASS_ADVISORS", "SOURCE_DOCUMENTS", "DOCUMENT_EXTRACTIONS",
        "LEARNING_COURSE_RECORDS", "COURSE_RULES", "CREDENTIAL_RECORDS", "PORTFOLIOS", "PORTFOLIO_EVIDENCE",
        "ATTENDANCE_SUMMARIES", "AWARD_CERTIFICATES"]),
    2: ("D-09-erd-part2-review.mmd", [
        "USERS", "ADMISSION_RULE_VERSIONS", "ADMISSION_RULE_ITEMS", "STUDENT_TARGETS",
        "LEARNING_PROFILE_OUTPUTS", "PACKAGE_REVIEWS", "AUTOBIOGRAPHY_COMMENTS", "AI_DAILY_USAGE"]),
    3: ("D-09-erd-part3-sources.mmd", [
        "USERS", "PUBLIC_SOURCES", "PUBLIC_SOURCE_SNAPSHOTS", "ADMISSION_RULE_VERSIONS", "AGENT_TASKS",
        "INFO_ITEMS", "ANNOUNCEMENTS", "ANNOUNCEMENT_READS", "FORM_CATEGORIES", "FORM_ITEMS",
        "FORM_ITEM_VERSIONS", "AUDIT_LOGS"]),
}
# 分圖中只畫簡短欄位的資料表（主要欄位在別張分圖）
SHORT_IN_PART = {2: {"USERS"}, 3: {"USERS", "ADMISSION_RULE_VERSIONS"}}


def entity_block(name, short=False):
    title, cols = ENTITIES[name]
    cols = SHORT[name] if short else cols
    body = "\n".join(f"        {c}" for c in cols)
    # 標題後面的全形空白是為了讓 Mermaid 留出足夠寬度，避免中文標題被截斷
    return f'    {name}["{name} {title}　　　"] {{\n{body}\n    }}'


def build(names, relations, short_set=frozenset()):
    rel_lines = [f'    {a} {r} {b} : "{label}"' for a, r, b, label in relations]
    blocks = [entity_block(n, n in short_set) for n in names]
    return HEADER + "\n".join(rel_lines) + "\n\n" + "\n".join(blocks) + "\n"


def main():
    here = Path(__file__).resolve().parent
    all_rel = [(a, r, b, label) for a, r, b, label, _ in RELATIONS]
    (here / "D-09-erd-v2.mmd").write_text(build(list(ENTITIES), all_rel), encoding="utf-8", newline="\n")
    for part, (filename, names) in PARTS.items():
        rels = [(a, r, b, label) for a, r, b, label, parts in RELATIONS if part in parts]
        missing = {x for a, _, b, _ in rels for x in (a, b)} - set(names)
        if missing:
            raise SystemExit(f"分圖 {part} 缺少資料表：{missing}")
        text = build(names, rels, SHORT_IN_PART.get(part, set()))
        (here / filename).write_text(text, encoding="utf-8", newline="\n")
    print(f"已寫出 D-09-erd-v2.mmd（{len(ENTITIES)} 張資料表）與 {len(PARTS)} 張分圖")


if __name__ == "__main__":
    main()
