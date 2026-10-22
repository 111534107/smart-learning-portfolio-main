"""「❓ 怎麼操作」說明頁的內容（系統手冊的網頁版）。

規則：每個答案一兩句話（測試限 70 字內），附一個按鈕帶到要做的地方。
link 是 url_for 的端點名稱；參數放在 args。改文字只要改這個檔案。
"""

HELP = {
    "student": [
        {
            "title": "開始",
            "items": [
                {"q": "這個系統是做什麼的？", "a": "把五年的成績、證照、活動收在一起，五年級準備備審資料時不用到處找。", "link": "main.student_welcome", "label": "再看一次歡迎介紹"},
                {"q": "首頁的小人物和拼圖是什麼？", "a": "小人物站在你現在的年級；拼圖缺的片就是今年還沒留下的資料，拖回洞裡就能補。", "link": "main.student_dashboard", "label": "回首頁"},
                {"q": "不知道先做什麼？", "a": "看首頁「今天先完成哪一步」，最多三件事，照順序點就好。", "link": "main.student_dashboard", "label": "回首頁"},
            ],
        },
        {
            "title": "留下資料",
            "items": [
                {"q": "怎麼上傳成績單或證照？", "a": "從學校系統下載成績單（或拍下證照），按「上傳成績單或證照」，再確認內容。", "link": "student.learning_profile_upload_page", "label": "去上傳"},
                {"q": "活動、競賽、服務、幹部怎麼新增？", "a": "到「活動與經歷」按「新增一筆」，填年級和說明，可以附照片或證明。", "link": "student.portfolio_new", "label": "新增一筆"},
                {"q": "上傳後的 AI 註記是什麼？", "a": "AI 讀不清楚的地方會在旁邊提醒可能原因，最後由你本人確認，不會自己改。", "link": "student.learning_profile", "label": "看我的文件"},
                {"q": "「確認」是什麼意思？", "a": "你核對過內容沒錯，資料才會算進五年資料夾和備審準備度。", "link": "student.learning_profile", "label": "看我的文件"},
            ],
        },
        {
            "title": "目標校系與備審",
            "items": [
                {"q": "目標校系可以選幾所？", "a": "一到四年級不限，找方向用；五年級準備備審資料時最多 5 所。", "link": "student.target_list", "label": "看學校"},
                {"q": "怎麼換學校？", "a": "在目標校系按「取消目標」再選新的；五年級換學校，寫好的自傳要重寫。", "link": "student.target_list", "label": "看學校"},
                {"q": "準備度是錄取機率嗎？", "a": "不是。準備度只看你已確認的資料符合簡章幾成，正式規定以各校簡章為準。", "link": "student.target_list", "label": "看學校"},
                {"q": "怎麼送導師確認？", "a": "在目標校系的頁面最下面按「請導師確認內容」，導師確認後才能下載正式版。", "link": "student.target_list", "label": "看學校"},
                {"q": "AI 額度用完怎麼辦？", "a": "學校的 AI 每人每天有次數上限，隔天會恢復；也可以用自己的金鑰。", "link": "student.target_list", "label": "看學校"},
            ],
        },
        {
            "title": "隱私",
            "items": [
                {"q": "我的資料誰看得到？", "a": "你自己和你的導師；科辦只看到你申請的證明。缺曠只有你和班導看得到。", "link": "main.student_dashboard", "label": "回首頁"},
                {"q": "拼圖的照片誰看得到？", "a": "只有你自己。不會放進備審、不會給 AI，照片裡的拍攝地點也會先拿掉。", "link": "main.student_dashboard", "label": "回首頁"},
            ],
        },
    ],
}

# 老師、科辦、管理員先共用一份簡短說明
HELP["teacher"] = [{"title": "導師", "items": [
    {"q": "怎麼確認學生的備審？", "a": "在工作台點學生，確認畫面會同時顯示送審版和最新版；只能確認送審的那一版。", "link": "main.teacher_dashboard", "label": "回工作台"},
    {"q": "學生改了資料怎麼辦？", "a": "學生要重新送審，舊的確認不會沿用到新版本。", "link": "main.teacher_dashboard", "label": "回工作台"},
]}]
HELP["staff"] = [{"title": "科辦", "items": [
    {"q": "怎麼核准電子獎狀？", "a": "到「電子獎狀」看學生的申請，核准後會產生帶驗證碼的證明。", "link": "certificate.staff_list", "label": "去電子獎狀"},
]}]
HELP["admin"] = [{"title": "管理員", "items": [
    {"q": "招生資料怎麼更新？", "a": "招生資料 Agent 抓到的是候選版本，比對差異、人工核准後才會發布。", "link": "admin.agent_home", "label": "去招生資料"},
]}]
