"""將報告用流程圖標示改為中文；不修改程式行為。"""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
replacements = {
    '候選版本 status=candidate<br/>校系與年度、校系備審要求': '待確認的招生資料<br/>學校、科系、招生年度與備審要求',
    '正式版本 status=published': '已核准的招生資料',
    '建立 PackageReview 快照': '保存這次送審的資料版本',
    'AI Agent 輔助模組': '資料整理與推薦功能',
    'AI Agent 讀取已核准校系規則': '讀取已核准的校系要求',
    '招生資料 Agent 候選內容': '待確認的招生資料',
    'Agent 擷取文字與候選分類': '整理網站文字與建議分類',
    '查詢操作紀錄與 Agent 任務': '查詢操作紀錄與資料更新進度',
    '建立候選版本並保留雜湊': '保存待確認資料與內容比對紀錄',
    'AI 代理每年更新（亮點）': '每年檢查招生資料',
    'AI 代理抓取來源並比對內容雜湊': '系統讀取官方資料並比對內容',
    'AI 代理擷取文字': '系統整理招生資料',
    'AI 不得直接發布；舊年度資料保留不覆蓋；<br/>每次擷取的文字與雜湊都保留': '資料須經管理員確認後發布<br/>保留歷年資料及每次更新紀錄',
    '拒絕存取（403）': '顯示沒有使用權限',
    '記錄上傳者、時間、檔案雜湊': '記錄上傳者、時間與檔案比對資訊',
    '（組員完成、待整合）': '（辨識後由學生確認）',
    '候選欄位': '待確認欄位',
    '送審快照': '送審版本',
    '建立送審快照': '保存送審版本',
    '關係範圍內學生清單': '有指導關係的學生清單',
    '關係內學生': '有指導關係的學生',
    '工作台載入關係範圍': '顯示可查看的學生',
    '學生基本資料與關係範圍': '學生資料與指導關係',
    '信心／疑點／分類': '辨識結果、待確認處與分類',
}
changed=[]
for p in sorted((root/'docs/images').glob('D-*.mmd')):
    old=p.read_text(encoding='utf-8-sig'); new=old
    if p.name.startswith('D-09-'): continue  # ERD 保留必要欄位名稱
    for a,b in replacements.items(): new=new.replace(a,b)
    new=new.replace('Microsoft JhengHei, Noto Sans TC, Arial, sans-serif','DFKai-SB, BiauKai, serif')
    new=new.replace("'themeVariables': {", "'themeVariables': {'fontSize':'18px',",1) if "'fontSize'" not in new and "'themeVariables': {" in new else new
    if new!=old:
        p.write_text(new,encoding='utf-8'); changed.append(p.name)
print('\n'.join(changed))
