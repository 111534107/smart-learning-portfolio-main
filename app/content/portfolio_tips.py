"""各校「備審資料怎麼準備」白話建議（2026-11-20）。

只收學校簡章明確寫的規定，改寫成學生看得懂的句子；每條附出處頁碼。
沒有出處的經驗談不放這裡。新學年度簡章公告後要重新核對，並更新 checked 日期。

鍵是志願代碼（admission_rule_versions.program_code）；有設定 admission_year 的建議只套用該學年度。
每條建議：{"text": 白話說明, "page": 出處頁碼（簡章印刷頁碼）}。

其他學校的技優甄審建議由 scripts/build_portfolio_tips.py 從聯招會簡章整理成
portfolio_tips_115_skill.json，以「學校｜科系｜招生類別」對應。
"""
import json
import re
from functools import lru_cache
from pathlib import Path

NUTC_DAY_SOURCE = "國立臺中科技大學 114 學年度二技日間部申請入學簡章"
NUTC_DAY_URL = "https://admission.nutc.edu.tw/var/file/16/1016/img/3447/960023343.pdf"
NUTC_SKILL_SOURCE = "115 學年度二技技優保送及甄審入學招生簡章"
NUTC_SKILL_URL = "https://admission.nutc.edu.tw/var/file/16/1016/img/3572/397031185.pdf"
TCUS_TRANSFER_SOURCE = "臺灣綜合大學系統 115 學年度學士班轉學生聯合招生簡章"
TCUS_TRANSFER_URL = "https://exam-tcustrans.nsysu.edu.tw/static/file/66/1066/img/671805059.pdf"

# 中科大日間部申請入學：全校共同的上傳規定（簡章第 5、6 頁）
_NUTC_DAY_UPLOAD = [
    {"text": "全部用網路上傳，只收 PDF；每一項資料各做成一個 PDF，每個 10MB 以下。", "page": "第5頁"},
    {"text": "在超商掃描的 PDF 可能讀不到，上傳前先用電腦「另存新檔」成 PDF 一次。", "page": "第5頁"},
    {"text": "書面審查資料要照系上列的順序合併成一個 PDF，最前面自己加一頁「目錄」，方便老師評分。", "page": "第6頁"},
    {"text": "按下「確認」之後就不能修改或補傳；確認前逐頁檢查，也別把甲系的資料傳到乙系。", "page": "第6頁"},
]

PORTFOLIO_TIPS = {
    "NIGHT-CSU-IM": {
        "school": "正修科技大學 資訊管理系",
        "channel": "進修部單獨招生",
        "admission_year": 115,
        "source": "正修科技大學 115 學年度二技進修部申請入學招生簡章",
        "source_url": "https://visit.csu.edu.tw/var/file/72/1072/img/349/266273927.pdf",
        "checked": "2026-11-23",
        "summary": "由報考的科系看書面資料評分，滿分 100 分。",
        "tips": [
            {"text": "報名清單列有一份書審資料。自傳或讀書計畫、推薦函及其他佐證，簡章都列為選繳。", "page": "第10至11頁"},
            {"text": "可以選附和資管相關的證照、競賽成果、社團或幹部證明、作品或工作成果。要交推薦函時，可用簡章附表二。", "page": "第11頁"},
            {"text": "網路報名後，依簡章把紙本裝入貼有 B4 封面的信封，寄出或到招生處現場交件。", "page": "第10至11頁"},
        ],
    },
    "NIGHT-KSU-IM": {
        "school": "崑山科技大學 資訊管理系",
        "channel": "進修部單獨招生",
        "admission_year": 115,
        "source": "崑山科技大學 115 學年度二年制進修部招生簡章",
        "source_url": "https://recruit.ksu.edu.tw/sites/all/files/recruit.ksu.edu.tw/recruit-info/205/1f5397c2319f72d906e3e69d8b8d5bfd-205.pdf",
        "checked": "2026-11-23",
        "summary": "在校學業平均成績和書面審查各占總成績 50%。",
        "tips": [
            {"text": "準備有學校註冊單位章戳的歷年成績單正本，依附件三繳交。缺交、非正本或資料不全時，學業平均成績按 60 分計。", "page": "第7頁"},
            {"text": "填寫附件五的書面審查資料表。可選附證照、職務表現、獲獎、作品、自傳、讀書計畫或其他專業工作成果。", "page": "第9頁"},
            {"text": "依報名方式，以掛號寄交或現場交紙本。郵寄以校方收到的時間為準。證明文件依報名方式在現場或入學時查驗正本。", "page": "第7至8頁"},
        ],
    },
    "NIGHT-MUST-IM": {
        "school": "明新科技大學 資訊管理系",
        "channel": "進修部單獨招生",
        "admission_year": 115,
        "source": "明新科技大學 115 學年度二技進修部單獨招生簡章",
        "source_url": "https://acade.must.edu.tw/files/115%E4%BA%8C%E6%8A%80%E7%B0%A1%E7%AB%A0_%E6%9C%80%E7%B5%82%E7%89%88_20260203083149_20260310210933.pdf",
        "checked": "2026-11-23",
        "summary": "學業成績和書審各滿分 100 分，加起來是總成績。同分時先比學業成績。",
        "tips": [
            {"text": "歷年成績單列為選繳，可交核章的影本。缺交、平均未達 60 分，或以同等學力報考時，學業成績按簡章以 60 分計。", "page": "第9至11頁"},
            {"text": "書審佐證也列為選繳。可挑證照、社團或幹部證明、競賽成果、語文能力、作品、工作成果、自傳或推薦信。", "page": "第9頁"},
            {"text": "網路報名後，把文件裝入 B4 信封，以限時掛號寄出（看郵戳）或親自送去。現場報名可當場交件。", "page": "第8至9頁"},
        ],
    },
    "NIGHT-UCH-IM": {
        "school": "健行科技大學 資訊管理系",
        "channel": "進修部單獨招生",
        "admission_year": 115,
        "source": "健行科技大學 115 學年度進修部二技學士班單獨招生簡章",
        "source_url": "https://oce.uch.edu.tw/var/file/13/1013/img/69/814957930.pdf",
        "checked": "2026-11-23",
        "summary": "簡章把學業成績、佐證及年資的分數相加，各項上限依序是 100、100、30 分。",
        "tips": [
            {"text": "報名要交簽名的報名表、身分證正反面及學歷證明。可線上填表後用掛號寄紙本，也可現場辦理。郵寄文件須在截止前送達。", "page": "第17頁"},
            {"text": "專科成績單影本列為選繳，缺交按 60 分計。有利審查資料最多採認 5 件，可選證照、競賽、志工或幹部證明、自傳或工作成果等。", "page": "第17至18頁"},
            {"text": "年資由系統每滿一年加 3 分，最多 30 分，這項分數免另附年資證明。", "page": "第18頁"},
        ],
    },
    "NIGHT-HDUT-CSIE": {
        "school": "宏國德霖科技大學 資訊工程系",
        "channel": "進修部單獨招生",
        "admission_year": 115,
        "source": "宏國德霖科技大學 115 學年度二技進修部單獨招生簡章",
        "source_url": "https://registry.hdut.edu.tw/ezfiles/18/1018/img/328/813045114.pdf",
        "checked": "2026-11-23",
        "summary": "在校學業平均成績占 40%，學習知能與綜合表現占 60%。",
        "tips": [
            {"text": "備妥官方歷年成績單和學習計畫。成績單缺交時，學業平均按 60 分計。學習計畫可參照簡章範例。", "page": "第6至7頁"},
            {"text": "有就附上證照、在職或年資證明、得獎、相關修課或職訓證明，以及其他技能或作品佐證。", "page": "第6至7頁"},
            {"text": "線上報名時，學習計畫上傳 PDF，其餘文件分項上傳清楚的圖片檔。", "page": "第4頁"},
        ],
    },
    "NIGHT-CUST-HSH-CSIE": {
        "school": "中國科技大學 資訊工程系（新竹校區）",
        "channel": "進修部單獨招生",
        "admission_year": 115,
        "source": "中國科技大學 115 學年度新竹校區進修部二技單獨招生簡章",
        "source_url": "https://recruit.cute.edu.tw/115_hsh_two-years-technical_application-guide/",
        "checked": "2026-11-23",
        "summary": "新竹校區以書面審查評分，滿分 200 分。",
        "tips": [
            {"text": "填新竹校區的附表三，說明學習歷程與工作成果。有證照、進修或研習等證明時可附上。", "page": "第6、19頁"},
            {"text": "線上報名時上傳 5 MB 以內的書審 PDF。郵寄或現場交件時，備妥報名表、證件黏貼表和書審資料，紙本佐證依順序裝訂。", "page": "第4至8頁"},
            {"text": "缺交書審資料或書審得 0 分，均不予錄取。同分由書審委員會重評。", "page": "第8頁"},
        ],
    },
    "NIGHT-CUST-TPE-IM": {
        "school": "中國科技大學 資訊管理系（臺北校區）",
        "channel": "進修部單獨招生",
        "admission_year": 115,
        "source": "中國科技大學 115 學年度臺北校區進修部二技單獨招生簡章",
        "source_url": "https://recruit.cute.edu.tw/115_tpe_two-years-technical_application-guide/",
        "checked": "2026-11-23",
        "summary": "臺北校區以書面審查評分，滿分 200 分。",
        "tips": [
            {"text": "填臺北校區的附表三，說明學習歷程與工作成果。有佐證可一併附上，表格寫不下可以加頁。", "page": "第21頁"},
            {"text": "線上報名時上傳 5 MB 以內的書審 PDF。郵寄或現場交件時，備妥報名表、證件黏貼表和書審資料，紙本佐證依順序裝訂。", "page": "第5至8頁"},
            {"text": "缺交書審資料或書審得 0 分，均不予錄取。同分由書審委員會重評。", "page": "第9頁"},
        ],
    },
    "NIGHT-JWU-ICOM": {
        "school": "景文科技大學 資訊與通訊系",
        "channel": "進修部單獨招生",
        "admission_year": 115,
        "source": "景文科技大學 115 學年度二技進修部單獨招生簡章",
        "source_url": "https://rec.just.edu.tw/var/file/16/1016/attach/43/pta_91001_1682808_93612.pdf",
        "checked": "2026-11-23",
        "notice": "115 學年度資訊與通訊系進修部二技已公告停止開班。",
        "notice_url": "https://rec.just.edu.tw/p/406-1016-71556,r26.php?Lang=zh-tw",
        "summary": "原簡章的書面審查滿分為 100 分。下列是停開前公告的準備方式。",
        "tips": [
            {"text": "原定採線上報名，學歷或同等學力證明依報考資格上傳影本，書面審查資料列為選繳。", "page": "第7頁"},
            {"text": "可選附自傳和讀書計畫（以 1000 字以內為原則）、歷年成績單、證照或獎狀等佐證。", "page": "第7頁"},
            {"text": "書審會綜合看就讀動機、學習計畫、生涯規劃，以及社團、幹部、競賽或作品等佐證。", "page": "第10頁"},
        ],
    },
    "TRF-NTU-CSIE-2": {
        "school": "國立臺灣大學 資訊工程學系（二年級）",
        "channel": "插大（轉學考）",
        "admission_year": 115,
        "source": "國立臺灣大學 115 學年度轉學生招生簡章",
        "source_url": "https://exam.aca.ntu.edu.tw/trans/brochure/115/pdf/P37.pdf",
        "checked": "2026-11-23",
        "summary": "資工系二年級只採書面審查，占總成績 100%。審查未達 70 分不予錄取。",
        "tips": [
            {"text": "下載報名表，備妥原校截至 114 學年度第 1 學期的歷年成績單，成績單要有名次和百分比。", "page": "第37頁"},
            {"text": "自傳要寫報考動機與未來規劃，最多 2 頁 A4。個人資料表到資工系網站下載，填好後上傳。", "page": "第37頁"},
            {"text": "其他有利資料附上入學考試成績單。有優良事蹟或特殊表現可挑最多 5 項，同一類資料合成一個 PDF，最多 10 頁 A4。", "page": "第37頁"},
            {"text": "書審資料依校方規定，在期限內上傳到轉學生招生報名系統。", "page": "第37頁"},
        ],
    },
    "TRF-NCHU-CSIE-2": {
        "school": "國立中興大學 資訊工程學系（二年級）",
        "channel": "插大（轉學考）",
        "admission_year": 115,
        "heading": "筆試準備",
        "source": TCUS_TRANSFER_SOURCE,
        "source_url": TCUS_TRANSFER_URL,
        "checked": "2026-11-23",
        "summary": "二年級 A06 聯招，只採計筆試成績。",
        "tips": [
            {"text": "考微積分 A（權重 1）、計算機概論（權重 1.5）和英文（權重 1）。", "page": "第23頁"},
            {"text": "總成績相同時，依序比較計算機概論、微積分 A、英文。", "page": "第23頁"},
        ],
    },
    "TRF-CCU-IM-2": {
        "school": "國立中正大學 資訊管理學系（二年級）",
        "channel": "插大（轉學考）",
        "admission_year": 115,
        "heading": "筆試準備",
        "source": TCUS_TRANSFER_SOURCE,
        "source_url": TCUS_TRANSFER_URL,
        "checked": "2026-11-23",
        "summary": "二年級 B30 單招，只採計筆試成績。",
        "tips": [
            {"text": "考計算機概論和英文，權重各為 1。", "page": "第49頁"},
            {"text": "總成績相同時，先比計算機概論，再比英文。", "page": "第49頁"},
        ],
    },
    "TRF-CCU-IM-3": {
        "school": "國立中正大學 資訊管理學系（三年級）",
        "channel": "插大（轉學考）",
        "admission_year": 115,
        "heading": "筆試準備",
        "source": TCUS_TRANSFER_SOURCE,
        "source_url": TCUS_TRANSFER_URL,
        "checked": "2026-11-23",
        "summary": "三年級 D33 單招，只採計筆試成績。",
        "tips": [
            {"text": "考計算機概論和英文，權重各為 1。", "page": "第65頁"},
            {"text": "總成績相同時，先比計算機概論，再比英文。", "page": "第65頁"},
        ],
    },
    "DAY-NTUB-11507": {
        "school": "國立臺北商業大學 資訊管理系（臺北）",
        "channel": "日間部申請入學",
        "admission_year": 115,
        "source": "國立臺北商業大學 115 學年度二技日間部申請入學簡章",
        "source_url": "https://admis.ntub.edu.tw/p/406-1028-116119,r139.php",
        "checked": "2026-11-23",
        "summary": "總成績中，書面審查占 75%，二技統測占 25%。簡章沒有公布書審各項的個別配分。",
        "tips": [
            {"text": "履歷自傳要附上自我推薦摘要表（表 A）和課程學習成果工作內容與貢獻度表（表 B）。兩張表可到資管系網站的招生相關表單下載。", "page": "第25頁"},
            {"text": "成績單要請學校核章，並確認上面有歷年成績、總平均和排名百分比。", "page": "第25頁"},
            {"text": "另外要上傳社團參與或學校幹部的證明、專業證照、競賽獎狀或成果，以及專題成果。有實習、打工或課外活動資料，也可以附上。", "page": "第25頁"},
            {"text": "專題要用專科期間完成的作品。團隊作品請寫清楚自己負責哪些部分。", "page": "第25頁"},
            {"text": "PDF 檔要清楚可讀。單一檔案以 50 MB 為原則，所有書審檔案合計不得超過 200 MB。", "page": "第25頁"},
            {"text": "每個項目各自存成 PDF，再逐項上傳。上傳後，請在期限內下載系統合併的 PDF，檢查是否完整並留存。", "page": "第VIII頁"},
        ],
    },
    "DAY-YT-IM": {
        "school": "國立雲林科技大學 資訊管理系",
        "channel": "日間部申請入學",
        "admission_year": 115,
        "source": "國立雲林科技大學 115 學年度二技申請入學招生簡章",
        "source_url": "https://examweb.yuntech.edu.tw/Exams/Docs/Exam_2/115/GenlReg.pdf",
        "checked": "2026-11-23",
        "summary": "總成績中，書面審查占 70%，二技統測占 30%。",
        "tips": [
            {"text": "書審分成兩部分：歷年成績與學習計畫書合計占 50%，相關能力證明占 50%。", "page": "第6頁"},
            {"text": "書審必交自傳和學習計畫書。自傳可以寫想讀這個系的原因、學過什麼和心得。學習計畫書可以寫入學後想學什麼、未來想往哪個方向發展。", "page": "第5頁"},
            {"text": "能力證明可選交，例如作品集、工作經驗證明、證照、競賽成果或社團表現。", "page": "第5頁"},
            {"text": "報名資格資料要附原就讀學校教務處核章的歷年成績單，並備妥排名資料。", "page": "第5頁"},
            {"text": "把書審資料合成 1 個 PDF，上限 55 MB。需要審查的內容請放在檔案裡，只貼網址不會採計。報名資格資料另合成 1 個 PDF，上限 10 MB。", "page": "第4頁"},
            {"text": "書審資料沒有補件機會，請在上傳期限前檢查資料是否齊全。", "page": "第5頁"},
        ],
    },
    # 中科大資管系，二技技優甄審（管理類四），簡章第 64 頁
    "208001": {
        "school": "國立臺中科技大學 資訊管理系",
        "channel": "技優甄審",
        "source": NUTC_SKILL_SOURCE,
        "source_url": NUTC_SKILL_URL,
        "checked": "2026-11-20",
        "summary": "這個管道只看書面資料（占 100%），沒有筆試，備審就是全部。",
        "tips": [
            {"text": "要交五樣：歷年成績單（含排名）、專題作品、專業與語文證照、簡歷自傳讀書計畫、其他有幫助的資料（如競賽、社團）。", "page": "第64頁"},
            {"text": "配分：成績 30%、個人特質與專業技能 50%（自傳＋專業與語文證照）、其他 20%。自傳和證照合起來最重，先把這兩樣做好。", "page": "第64頁"},
            {"text": "同分時先比「其他有助於審查之資料」，所以競賽、社團、服務這些不要漏放。", "page": "第64頁"},
            {"text": "系上說課程是進階資管，要有程式設計或資料庫的基礎；在自傳或專題裡具體寫出你寫過什麼程式、做過什麼資料庫。", "page": "第64頁"},
            {"text": "交出去的資料不會退還，自己留一份。", "page": "第64頁"},
        ],
    },
    # 中科大資訊應用菁英班，二技技優甄審（管理類四），簡章第 64～65 頁
    "208002": {
        "school": "國立臺中科技大學 資訊應用菁英班",
        "channel": "技優甄審",
        "source": NUTC_SKILL_SOURCE,
        "source_url": NUTC_SKILL_URL,
        "checked": "2026-11-20",
        "summary": "這個管道只看書面資料（占 100%），沒有筆試，備審就是全部。",
        "tips": [
            {"text": "要交的五樣和資管系相同：成績單（含排名）、專題作品、專業與語文證照、簡歷自傳讀書計畫、其他有幫助的資料。", "page": "第65頁"},
            {"text": "配分：成績 25%、個人特質與專業技能 50%（自傳＋證照）、其他 25%；「其他」比資管系多，競賽和社團更值得整理。", "page": "第65頁"},
            {"text": "同分時先比「其他有助於審查之資料」。", "page": "第65頁"},
            {"text": "要有程式設計或資料庫的基礎，在自傳或專題裡寫出具體例子。", "page": "第65頁"},
        ],
    },
    # 中科大資管系，二技日間部申請入學（114 學年度簡章第 24 頁；新學年度公告後要再核對）
    "DAY-NUTC-IM": {
        "school": "國立臺中科技大學 資訊管理系",
        "channel": "日間部申請入學",
        "source": NUTC_DAY_SOURCE,
        "source_url": NUTC_DAY_URL,
        "checked": "2026-11-20",
        "summary": "總成績是統測 20%＋書面審查 80%，備審資料比統測重要得多。",
        "tips": [
            {"text": "書審裡成績單占 40%；專題作品、競賽成果、證照與其他能力證明合起來占 60%。把力氣放在專題、競賽和證照。", "page": "第24頁"},
            {"text": "這個管道的應繳資料沒有列自傳；與其寫長自傳，不如把專題和證照整理清楚、附上說明。", "page": "第24頁"},
            {"text": "系上要求要有程式設計或資料庫的基礎，專題說明裡寫出你用了什麼語言、做了哪些資料表。", "page": "第24頁"},
            {"text": "同分時先比書面資料審查成績，再比統測。", "page": "第24頁"},
            *_NUTC_DAY_UPLOAD,
        ],
    },
    # 中科大資訊應用菁英班，二技日間部申請入學（114 學年度簡章第 25 頁）
    "DAY-NUTC-IAE": {
        "school": "國立臺中科技大學 資訊應用菁英班",
        "channel": "日間部申請入學",
        "source": NUTC_DAY_SOURCE,
        "source_url": NUTC_DAY_URL,
        "checked": "2026-11-20",
        "summary": "總成績是統測 10%＋書面審查 90%，幾乎全看備審資料。",
        "tips": [
            {"text": "書審裡成績單占 30%；專題作品、競賽成果、證照與其他能力證明合起來占 70%。", "page": "第25頁"},
            {"text": "這個管道的應繳資料沒有列自傳；把專題、競賽和證照整理清楚、附上說明更重要。", "page": "第25頁"},
            {"text": "系上要求要有程式設計或資料庫的基礎，專題說明裡寫出具體做了什麼。", "page": "第25頁"},
            *_NUTC_DAY_UPLOAD,
        ],
    },
    # 中科大資訊工程系，二技日間部申請入學（114 學年度簡章第 27 頁）
    "DAY-NUTC-CSIE": {
        "school": "國立臺中科技大學 資訊工程系",
        "channel": "日間部申請入學",
        "source": NUTC_DAY_SOURCE,
        "source_url": NUTC_DAY_URL,
        "checked": "2026-11-20",
        "summary": "總成績是統測 20%＋書面審查 80%，備審資料比統測重要得多。",
        "tips": [
            {"text": "書審裡成績單占 40%；專題作品、競賽成果、證照與其他能力證明合起來占 60%。", "page": "第27頁"},
            {"text": "這個管道的應繳資料沒有列自傳；重點放在專題、競賽和證照。", "page": "第27頁"},
            {"text": "系上說課程是進階資訊工程，要有程式設計或資料庫的基礎。", "page": "第27頁"},
            {"text": "同分時先比書面資料審查成績，再比統測。", "page": "第27頁"},
            *_NUTC_DAY_UPLOAD,
        ],
    },
}


def norm_school(name):
    """「長庚學校財團法人長庚科技大學」→「長庚科技大學」；臺／台視為相同。"""
    name = re.sub(r"^.*學校財團法人", "", name or "")
    return name.replace("臺", "台").strip()


def norm_dept(name):
    """「資訊管理系(臺北校區)」「護理系（嘉義分部）」「資訊管理系（臺北）」對到同一個寫法。"""
    name = re.sub(r"[（(]([^）)]*?)(校區|分部)?[）)]", r"\1", name or "")
    return re.sub(r"\s", "", name).replace("臺", "台")


def norm_category(name):
    """「08管理類（四）」與「管理類四」相同。"""
    return re.sub(r"^\d+|[（）()\s]", "", name or "")


def key_of(school, dept, category):
    return f"{norm_school(school)}|{norm_dept(dept)}|{norm_category(category)}"


@lru_cache(maxsize=1)
def _skill_tips():
    """聯招會技優甄審簡章整理出的各校系建議（scripts/build_portfolio_tips.py 產生）。"""
    path = Path(__file__).with_name("portfolio_tips_115_skill.json")
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def tips_for(program):
    """回傳這個志願的白話建議；沒有資料就回傳 None。

    先找人工整理的（以志願代碼），再找技優甄審簡章整理的（以學校＋科系＋招生類別）。
    日間部申請入學、進修部的規定和技優甄審不同，招生類別對不上就不會套用。
    """
    if program is None:
        return None
    manual = PORTFOLIO_TIPS.get(str(program.program_code))
    if manual:
        if "admission_year" in manual and program.admission_year != manual["admission_year"]:
            return None
        return manual
    return _skill_tips().get(key_of(program.school_name, program.department_name, program.admission_category))
