第一階段：點火啟動 (指揮官開場) (完成)
在任何操作之前，先建立專案地基。
/bmad-init：初始化專案環境。
/bmad-generate-project-context：生成專案上下文檔案，這能幫 AI 記住你的專案開發準則。

📝 第二階段：需求深挖 (BA 階段) (完成)
對象： /bmad-agent-analyst (Mary)
動作： 跟 Mary 對話，把你的點子丟給她。
關鍵： 如果她給的建議太普通，直接補一個 /bmad-advanced-elicitation，逼她挖出你沒想到的商業邏輯或潛在問題。
成果： 釐清後的「需求草案」。

📋 第三階段：規格定稿 (PM 階段)
對象： /bmad-agent-pm (Josh)
/bmad-market-research：叫 Josh 去查查競爭對手怎麼做的（如果你有聯網模式）。
/bmad-create-prd：將 Mary 的草案轉化為標準的 PRD (產品需求文件)。
/bmad-validate-prd：（重要！） 讓系統檢查 PRD 是否夠細、有沒有邏輯漏洞。

🏗️ 第四階段：技術藍圖 (SA/SD 階段)
對象： /bmad-agent-architect (Winston)
/bmad-create-architecture：叫 Winston 決定要用什麼語言（React? Python?）、資料庫怎麼設計、API 怎麼寫。
/bmad-create-ux-design：如果需要畫面，找 Sally (/bmad-agent-ux-designer) 把頁面流程畫出來。

✂️ 第五階段：
對象： /bmad-agent-sm (Bob)
/bmad-create-epics-and-stories：把龐大的架構拆成一格一格的 User Story。
/bmad-check-implementation-readiness：問系統：「我現在的文件夠不夠讓工程師開工了？」

💻 第六階段：工廠生產 (Dev & QA 階段)
對象： /bmad-agent-dev & /bmad-agent-qa (Quinn)
/bmad-dev-story：進入 Cursor，從 001-setup.md 開始，一次餵一個 Story 給 AI 寫程式。
/bmad-code-review：寫完一部分，就叫 AI 做「敵對式審查」。
/bmad-qa-generate-e2e-tests：叫 Quinn 寫測試，確保功能沒壞。
