import urllib.request
import os
import base64
import zlib

mermaid_blocks = [
    ("D-05-system-architecture.png", """flowchart LR
    classDef frontend fill:#fff,stroke:#333;
    classDef backend fill:#E0F2FE,stroke:#333;
    classDef db fill:#F3F4F6,stroke:#333;
    classDef ai fill:#FFEDD5,stroke:#333;
    classDef external fill:#FEF9C3,stroke:#333;
    classDef student fill:#DBEAFE,stroke:#333;
    classDef teacher fill:#DCFCE7,stroke:#333;
    classDef admin fill:#EDE9FE,stroke:#333;

    U[前端介面]:::frontend
    R[Flask 後端]:::backend
    M[(MySQL 資料庫)]:::db
    AI[AI Agent 模組]:::ai
    Gemini[Gemini API]:::external
    GH[GitHub REST API]:::external
    
    Student[學生]:::student --> U
    Teacher[教師 / 評審]:::teacher --> U
    Admin[系統管理者]:::admin --> U
    
    U --> R
    R --> M
    R --> AI
    AI --> Gemini
    AI --> GH"""),
    
    ("D-01-use-case.png", """flowchart TD
    classDef student fill:#DBEAFE,stroke:#333;
    classDef teacher fill:#DCFCE7,stroke:#333;
    classDef admin fill:#EDE9FE,stroke:#333;
    classDef ai fill:#FFEDD5,stroke:#333;
    classDef backend fill:#E0F2FE,stroke:#333;

    System[前端介面與後端]:::backend

    System --> Student[學生]:::student
    System --> Teacher[教師 / 評審]:::teacher
    System --> Admin[系統管理者]:::admin
    System --> Agent[AI Agent]:::ai

    Student --> S1[學習歷程管理]:::student
    Student --> S2[上傳佐證資料]:::student
    Student --> S3[任務地圖解鎖]:::student
    Student --> S4[提交備審與成績]:::student
    Student --> S5[查看 AI 檢核報告]:::student

    Teacher --> T1[查看被分派學生]:::teacher
    Teacher --> T2[評分與回饋留言]:::teacher
    Teacher --> T3[人工覆核 AI 提示]:::teacher
    Teacher --> T4[提供補件建議]:::teacher

    Admin --> A1[帳號與權限管理]:::admin
    Admin --> A2[系統設定維護]:::admin
    Admin --> A3[操作與錯誤日誌]:::admin
    Admin --> A4[監控 AI 任務狀態]:::admin
    Admin --> A5[審核並發布招生規則]:::admin

    Agent --> G1[成績單文字擷取]:::ai
    Agent --> G2[備審主張證據檢核]:::ai
    Agent --> G3[分析任務地圖進度]:::ai
    Agent --> G4[擷取官方招生資料]:::ai"""),
    
    ("D-02-student-flow.png", """flowchart TD
    classDef student fill:#DBEAFE,stroke:#333;
    classDef backend fill:#E0F2FE,stroke:#333;

    Start([開始]) --> Login[學生登入]:::student
    Login --> Profile[維護個人基本資料]:::student
    Profile --> Portfolio[新增學習歷程]:::student
    Portfolio --> Classify[填寫學年度與類型]:::student
    Classify --> Evidence[上傳佐證資料]:::student
    Evidence --> Draft{是否存草稿?}
    Draft -- 是 --> SaveDraft[儲存草稿]:::backend
    SaveDraft --> Edit[修改資料]:::student
    Edit --> Submit[正式提交]:::backend
    Draft -- 否 --> Submit
    Submit --> Milestone[更新任務地圖]:::backend
    Milestone --> End([完成])"""),
    
    ("D-08-ai-agent-flow.png", """flowchart TD
    classDef student fill:#DBEAFE,stroke:#333;
    classDef teacher fill:#DCFCE7,stroke:#333;
    classDef ai fill:#FFEDD5,stroke:#333;
    classDef backend fill:#E0F2FE,stroke:#333;
    classDef alert fill:#FEE2E2,stroke:#333;

    Start([開始]) --> Upload[上傳備審資料]:::student
    Upload --> CreateTask[建立檢核任務]:::backend
    CreateTask --> Extract[擷取文字內容]:::ai
    Extract --> Claims[拆解可驗證主張]:::ai
    Claims --> SearchEvidence[搜尋佐證資料]:::ai
    SearchEvidence --> Matrix[建立主張證據矩陣]:::ai
    Matrix --> Status[標示支持程度]:::ai
    Status --> Report[產生檢核報告]:::ai
    Report --> StudentReview[學生查看並補件]:::student
    StudentReview --> TeacherReview[教師人工覆核]:::teacher
    TeacherReview --> Decision{教師決定}
    Decision -- 採納 --> Accepted[保存採納紀錄]:::backend
    Decision -- 駁回 --> Rejected[保存駁回理由]:::alert
    Decision -- 待確認 --> Pending[列入面試追問]:::alert
    Accepted --> End([完成])
    Rejected --> End
    Pending --> End"""),
    
    ("D-05-transcript-flow.png", """flowchart TD
    classDef student fill:#DBEAFE,stroke:#333;
    classDef ai fill:#FFEDD5,stroke:#333;
    classDef backend fill:#E0F2FE,stroke:#333;
    classDef alert fill:#FEE2E2,stroke:#333;

    Start([開始]) --> Login[學生登入]:::student
    Login --> Upload[上傳成績單圖片]:::student
    Upload --> Validate[檢查檔案格式]:::backend
    Validate --> Valid{格式正確?}
    Valid -- 否 --> Error[顯示錯誤訊息]:::alert
    Valid -- 是 --> Task[建立 Agent 任務]:::backend
    Task --> OCR[擷取影像文字]:::ai
    OCR --> AI[提取課程與成績]:::ai
    AI --> Schema[驗證結構化資料]:::ai
    Schema --> OK{結果完整?}
    OK -- 否 --> Pending[標示擷取失敗]:::alert
    OK -- 是 --> Draft[產生成績草稿]:::backend
    Draft --> Confirm[學生確認修正]:::student
    Confirm --> Save[寫入資料庫]:::backend
    Save --> End([完成])"""),
    
    ("D-04-admin-maintenance-flow.png", """flowchart TD
    classDef admin fill:#EDE9FE,stroke:#333;
    classDef ai fill:#FFEDD5,stroke:#333;
    classDef backend fill:#E0F2FE,stroke:#333;
    classDef alert fill:#FEE2E2,stroke:#333;

    Start([開始]) --> Source[設定官方來源]:::admin
    Source --> Check[檢查來源更新]:::ai
    Check --> Extract[擷取招生規則]:::ai
    Extract --> Compare[比對現行版本]:::ai
    Compare --> Candidate[建立候選更新]:::ai
    Candidate --> Review[管理者查看差異]:::admin
    Review --> Approve{是否核准?}
    Approve -- 否 --> Reject[駁回並紀錄]:::alert
    Approve -- 是 --> Publish[發布新規則版本]:::backend
    Publish --> Log[寫入操作紀錄]:::backend
    Reject --> Log
    Log --> End([完成])"""),
    
    ("D-04-system-maintenance-flow.png", """flowchart TD
    classDef admin fill:#EDE9FE,stroke:#333;
    classDef backend fill:#E0F2FE,stroke:#333;

    Admin[系統管理者登入]:::admin --> Dashboard[進入管理者維護模組]:::backend
    Dashboard --> Users[帳號與權限管理]:::admin
    Dashboard --> Settings[系統設定維護]:::admin
    Dashboard --> Logs[操作與錯誤日誌]:::admin
    Dashboard --> Tasks[監控 AI 任務狀態]:::admin
    Dashboard --> Backup[備份匯出與報表]:::admin

    Settings --> UploadLimit[設定檔案大小限制]:::backend
    Settings --> AIFlag[切換 AI 功能開關]:::backend
    Tasks --> Retry[重新執行失敗任務]:::backend"""),
    
    ("D-09-erd.png", """erDiagram
    USERS ||--o| STUDENT_PROFILES : "has"
    USERS ||--o{ PORTFOLIOS : "owns"
    USERS ||--o{ AGENT_TASKS : "requests"
    USERS ||--o{ HUMAN_REVIEWS : "reviews"

    PORTFOLIOS ||--o{ PORTFOLIO_EVIDENCE : "contains"
    PORTFOLIOS ||--o{ PORTFOLIO_CLAIMS : "includes"
    PORTFOLIOS ||--o{ AI_AUDIT_REPORTS : "audited_by"

    PORTFOLIO_CLAIMS ||--o{ CLAIM_EVIDENCE_LINKS : "maps"
    PORTFOLIO_EVIDENCE ||--o{ CLAIM_EVIDENCE_LINKS : "supports"

    AGENT_TASKS ||--o{ AI_AUDIT_REPORTS : "produces"
    AI_AUDIT_REPORTS ||--o{ HUMAN_REVIEWS : "reviewed_by"

    OFFICIAL_SOURCES ||--o{ ADMISSION_RULE_VERSIONS : "provides"
    ADMISSION_RULE_VERSIONS ||--o{ ADMISSION_RULE_ITEMS : "contains"
    ADMISSION_RULE_VERSIONS ||--o{ SIMULATION_RESULTS : "used_by"
    STUDENT_PROFILES ||--o{ SIMULATION_RESULTS : "calculates"

    USERS {
        int user_id PK
        string username
        string password_hash
        string role
        string status
    }

    PORTFOLIOS {
        int portfolio_id PK
        int student_id FK
        string title
        string category
        string status
    }

    AGENT_TASKS {
        int task_id PK
        string task_type
        int requested_by FK
        string status
        string error_message
    }"""),
    
    ("D-06-dfd.png", """flowchart LR
    classDef student fill:#DBEAFE,stroke:#333;
    classDef teacher fill:#DCFCE7,stroke:#333;
    classDef admin fill:#EDE9FE,stroke:#333;
    classDef ai fill:#FFEDD5,stroke:#333;
    classDef db fill:#F3F4F6,stroke:#333;

    Student[學生]:::student --> P1[學習歷程模組]
    P1 --> D1[(學習歷程資料)]:::db
    Student --> P2[佐證資料模組]
    P2 --> D2[(檔案與草稿資料)]:::db
    P2 --> P3[AI Agent 模組]:::ai
    P3 --> D3[(任務與檢核報告)]:::db
    Teacher[教師 / 評審]:::teacher --> P4[人工覆核流程]
    P4 --> D4[(評分與覆核紀錄)]:::db
    Admin[系統管理者]:::admin --> P5[管理者維護模組]
    P5 --> D5[(帳號規則日誌)]:::db"""),
    
    ("D-10-report-overview.png", """flowchart LR
    classDef student fill:#DBEAFE,stroke:#333;
    classDef teacher fill:#DCFCE7,stroke:#333;
    classDef admin fill:#EDE9FE,stroke:#333;
    classDef ai fill:#FFEDD5,stroke:#333;
    classDef backend fill:#E0F2FE,stroke:#333;

    Input[學生資料與佐證]:::student --> Core[Flask 後端與資料庫]:::backend
    Core --> AI[AI Agent 模組]:::ai
    AI --> Review[教師人工覆核]:::teacher
    Review --> Output[給予回饋與補件建議]:::teacher
    Admin[系統管理者]:::admin -.->|管理參數與規則| Core
    Admin -.->|排程檢查| AI""")
]

os.makedirs('d:/democase/ai/docs/images', exist_ok=True)

def kroki_payload(text):
    compressed = zlib.compress(text.encode('utf-8'))
    return base64.urlsafe_b64encode(compressed).decode('ascii')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

for filename, text in mermaid_blocks:
    try:
        payload = kroki_payload(text)
        url = f'https://kroki.io/mermaid/png/{payload}'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                with open(f'd:/democase/ai/docs/images/{filename}', 'wb') as f:
                    f.write(response.read())
                print(f"Saved {filename}")
            else:
                print(f"Failed to generate {filename}: {response.status}")
    except Exception as e:
        print(f"Error {filename}: {e}")
