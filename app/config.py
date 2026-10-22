import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY")

    if not SECRET_KEY:
        if FLASK_ENV == "production":
            raise ValueError("SECRET_KEY must be set in production environment!")
        SECRET_KEY = "dev-secret-key"

    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_NAME = os.getenv("DB_NAME", "smart_learning_portfolio")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "instance/uploads")
    
    max_mb = int(os.getenv("MAX_CONTENT_LENGTH_MB", "10"))
    MAX_CONTENT_LENGTH = max_mb * 1024 * 1024
    
    AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"
    AI_PROVIDER = os.getenv("AI_PROVIDER", "none").lower()
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    # Google Drive 原型只在本機明確啟用，且 OAuth 與 Picker 設定齊全時開放。
    GOOGLE_DRIVE_PREVIEW_ENABLED = os.getenv("GOOGLE_DRIVE_PREVIEW_ENABLED", "false").lower() == "true"
    GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    # 自傳在 Google 文件中編輯（後端 OAuth，只要 drive.file）：三個值都填了才會開放；權杖只放伺服器記憶體
    GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")
    GOOGLE_PICKER_API_KEY = os.getenv("GOOGLE_PICKER_API_KEY", "")
    GOOGLE_CLOUD_PROJECT_NUMBER = os.getenv("GOOGLE_CLOUD_PROJECT_NUMBER", "")
    # 小助手對話次數多，用較輕量的模型，和自傳、簡章擷取分開計算每日額度
    ASSISTANT_MODEL = os.getenv("ASSISTANT_MODEL", "gemini-flash-lite-latest")
    # 招生資料 Agent 只擷取科系名稱含這些字的校系（逗號分隔）
    AGENT_PROGRAM_KEYWORDS = [k.strip() for k in os.getenv("AGENT_PROGRAM_KEYWORDS", "資訊管理,資管,資訊應用,資訊工程").split(",") if k.strip()]
    AGENT_SOURCE_FOLDER = os.getenv("AGENT_SOURCE_FOLDER", "instance/agent-sources")
    # 資管科小助手（規格第 10 節）：目標校系同時最多幾所、學校金鑰每人每天幾次、幾年級起可以送審
    TARGET_LIMIT = int(os.getenv("TARGET_LIMIT", "5"))
    SCHOOL_AI_DAILY_LIMIT = int(os.getenv("SCHOOL_AI_DAILY_LIMIT", "5"))
    MIN_REVIEW_GRADE = int(os.getenv("MIN_REVIEW_GRADE", "2"))
    DOCUMENT_ANALYSIS_PROVIDER = os.getenv("DOCUMENT_ANALYSIS_PROVIDER", "fake")
    # 離線 OCR 引擎：空白＝不啟用（上傳會標示 analysis_failed）；rapidocr＝本機 RapidOCR
    DOCUMENT_OCR_ENGINE = os.getenv("DOCUMENT_OCR_ENGINE", "")
    # 模型等級：server＝伺服器版（預設，較準、較慢）；mobile＝輕量版（較快、記憶體較少）
    OCR_MODEL_TIER = os.getenv("OCR_MODEL_TIER", "server")
    # 執行裝置：cpu＝一般處理器（預設）；dml＝Windows DirectML 顯示卡加速（需安裝 onnxruntime-directml）
    OCR_DEVICE = os.getenv("OCR_DEVICE", "cpu")
    # DirectML 顯示卡編號：筆電的 0 多半是內建顯示，獨立顯示卡常是 1（開發用筆電的 RTX 4060 是 1）
    OCR_DML_DEVICE_ID = int(os.getenv("OCR_DML_DEVICE_ID", "0"))
    # 上傳後的辨識方式：thread＝背景執行緒排隊（預設，學生先看到「辨識中」頁）；inline＝在上傳請求裡跑完
    OCR_QUEUE_MODE = os.getenv("OCR_QUEUE_MODE", "thread")
    CSRF_ENABLED = os.getenv("CSRF_ENABLED", "true").lower() == "true"
    ALLOWED_UPLOAD_EXTENSIONS = {
        value.strip().lower()
        for value in os.getenv("ALLOWED_UPLOAD_EXTENSIONS", "pdf,png,jpg,jpeg,doc,docx,odt,txt").split(",")
        if value.strip()
    }
    LEARNING_PROFILE_ALLOWED_EXTENSIONS = {
        value.strip().lower()
        for value in os.getenv("LEARNING_PROFILE_ALLOWED_EXTENSIONS", "pdf,png,jpg,jpeg").split(",")
        if value.strip()
    }
