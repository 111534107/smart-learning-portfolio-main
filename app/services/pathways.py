"""升學路線比較（B19 二技與插大比較、B20 統測進四技）。

內容只寫有官方出處的規定，出處與查詢日期一起顯示；查證紀錄見
docs/05_交接與專案管理/B17-B20_插大與統測四技_官方資料查證_2026-11-13.md（主專案 ai\\docs）。
學生選「我現在是」之後，畫面依 open_when / soon_when 標出哪條路現在能走。
"""

from datetime import date

CHECKED_ON = "2026-11-13"

LAW_URL = "https://law.moj.gov.tw/LawClass/LawAll.aspx?PCode=H0030032"
TCTE_ORDER_URL = "https://www.tcte.edu.tw/NetServer/116Order/"
TCTE_SELECT_URL = "https://www.tcte.edu.tw/index.php?mod=TVETest%2FSelfSelectSubject"
TCTE_RANGE_URL = "https://www.tcte.edu.tw/doc/116Range_4y/"
TCTE_SCHEDULE_URL = "https://tcvs.tc.edu.tw/p/406-1084-620610,r2327.php"

# 116 學年度統測（重要日程表；簡章正式下載後要再對一次）
TCTE_116_APPLY_START = date(2026, 12, 9)
TCTE_116_APPLY_END = date(2026, 12, 21)
TCTE_116_EXAM = date(2027, 4, 24)

STATUS_BY_GRADE = {1: "y1to3", 2: "y1to3", 3: "y1to3", 4: "y4", 5: "y5"}


def default_status(grade):
    return STATUS_BY_GRADE.get(grade, "y1to3")


def build_pathways(target_url_twotech, target_url_transfer):
    return [
        {
            "key": "twotech",
            "title": "二技",
            "open_when": ["grad"],
            "soon_when": ["y5"],
            "facts": [
                ("讀幾年", "兩年，畢業拿學士學位。"),
                ("誰能考", "五專畢業；五專肄業要符合同等學力第 3 條（例如已修畢畢業應修學分 220 學分以上）。"),
                ("怎麼考", "各校簡章規定，多數看書面審查（備審資料）與各項加權。系統的目標校系、準備度就是為這條路做的。"),
            ],
            "dates": [],
            "warning": "",
            "sources": [("入學大學同等學力認定標準第 3 條", LAW_URL)],
            "link": ("看二技目標校系", target_url_twotech),
        },
        {
            "key": "transfer",
            "title": "插大（轉學考）",
            "open_when": ["grad"],
            "soon_when": ["y5"],
            "facts": [
                ("讀幾年", "插入大學二年級或三年級，讀完剩下的年級；插三年級通常再讀兩年。"),
                ("誰能考", "取得專科畢業證書，或修滿規定修業年限（五專為五年）並附成績單。"),
                ("怎麼考", "各校自辦轉學考，筆試、書面審查或面試，每校每系不同；要看考科、考期，自己排準備進度。"),
                ("什麼時候", "暑假轉學考多在 5–7 月報名、6–7 月考試（依 115 學年度範例校）；部分學校另有寒假轉學考。"),
            ],
            "dates": [],
            "warning": "",
            "sources": [("入學大學同等學力認定標準第 4 條", LAW_URL)],
            "link": ("看插大目標校系", target_url_transfer),
        },
        {
            "key": "fouryear",
            "title": "統測進四技",
            "open_when": ["leave"],
            "soon_when": [],
            "facts": [
                ("讀幾年", "從大學一年級讀起，四年。"),
                ("誰能考", "五專修滿三年級下學期後，休學或退學一年以上，才有大學一年級同等學力。"),
                ("考什麼", "統測。商業與管理群：國文、英文、數學、專業科目(一)（商業概論、數位科技概論、數位科技應用）、專業科目(二)（會計學、經濟學）。"),
                ("116 起", "自主選考：單群類至少選考 2 科，其中至少 1 科是專業科目。"),
            ],
            "dates": [
                ("116 統測報名開始", TCTE_116_APPLY_START),
                ("116 統測報名截止", TCTE_116_APPLY_END),
                ("116 統測考試", TCTE_116_EXAM),
            ],
            "warning": "在學中讀完三年不能直接去考：要先休學或退學滿一年才有報考資格。休學、退學會影響五專學籍，決定前請先和導師、家人討論。",
            "sources": [
                ("入學大學同等學力認定標準第 2 條", LAW_URL),
                ("測驗中心 116 簡章", TCTE_ORDER_URL),
                ("自主選考說明", TCTE_SELECT_URL),
                ("116 考試大綱", TCTE_RANGE_URL),
                ("116 重要日程表（學校轉貼）", TCTE_SCHEDULE_URL),
            ],
            "link": None,
        },
    ]
