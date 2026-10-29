from flask import Flask

from app.config import Config
from app.extensions import db, migrate
from app.security import init_security


def create_app(config_overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    # 自動化測試沒指定時在請求裡直接辨識，既有測試上傳後就能拿到辨識結果
    if app.config.get("TESTING") and "OCR_QUEUE_MODE" not in (config_overrides or {}):
        app.config["OCR_QUEUE_MODE"] = "inline"
    if app.config.get("DOCUMENT_OCR_ENGINE") == "rapidocr" and app.config.get("OCR_ENGINE") is None:
        from app.services.document_analysis_service import RapidOcrEngine

        app.config["OCR_ENGINE"] = RapidOcrEngine(
            tier=app.config.get("OCR_MODEL_TIER", "server"),
            device=app.config.get("OCR_DEVICE", "cpu"),
            dml_device_id=app.config.get("OCR_DML_DEVICE_ID", 0),
        )

    db.init_app(app)
    migrate.init_app(app, db)
    init_security(app)

    from app.services.credential_analysis import traditional_text
    app.add_template_filter(traditional_text, "traditional_text")
    from app.services.ocr_trace import describe_step
    app.add_template_filter(describe_step, "ocr_step")
    from app.services.agent_engine import taipei_time
    app.add_template_filter(taipei_time, "taipei_time")

    from app.routes.main import main_bp
    from app.routes.admin import admin_bp
    from app.routes.student import student_bp
    from app.routes.review import review_bp
    from app.routes.staff import staff_bp
    from app.routes.teacher import teacher_bp
    from app.routes.assistant import assistant_bp
    from app.routes.award import award_bp
    from app.routes.certificate import certificate_bp
    from app.routes.proposal_preview import proposal_preview_bp
    from app.routes.transfer_credit import transfer_credit_bp
    from app.routes.google_docs import google_docs_bp
    from app.routes.storage import storage_bp
    from app import models

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(award_bp)
    app.register_blueprint(certificate_bp)
    app.register_blueprint(proposal_preview_bp)
    app.register_blueprint(transfer_credit_bp)
    app.register_blueprint(google_docs_bp)
    app.register_blueprint(storage_bp)

    @app.cli.command("agent-check")
    def agent_check_command():
        """招生資料 Agent：檢查所有官方來源有沒有更新（給排程用）。"""
        from app.models import User
        from app.services.admission_agent_service import check_all
        admin = User.query.filter_by(role="admin").order_by(User.id).first()
        if not admin:
            print("找不到管理者帳號，無法記錄執行者。")
            return
        for task in check_all(admin):
            result = task.error_message or ("有更新" if task.result_json.get("changed") else "沒有更新")
            print(f"來源 {task.target_id}：{result}")

    @app.cli.command("agent-patrol")
    def agent_patrol_command():
        """升學 Agent 背景巡查：檢查官方來源、把更新擷取成候選校系（給排程用）。"""
        from app.models import User
        from app.services.agent_patrol import run_patrol
        admin = User.query.filter_by(role="admin").order_by(User.id).first()
        if not admin:
            print("找不到管理者帳號，無法記錄執行者。")
            return
        result = run_patrol(admin)
        mode = "AI 決定步驟" if result["mode"] == "ai" else "固定流程"
        print(f"升學 Agent 巡查（{mode}）：{result['summary']}")

    if app.config["OCR_QUEUE_MODE"] == "thread":
        from app.services.ocr_queue import recover_on_startup
        recover_on_startup(app)

    error_texts = {
        401: ("請先登入", "這一頁要登入後才能看。可能是還沒登入，或太久沒操作被登出了。"),
        403: ("沒有權限", "你的帳號不能看這一頁。如果你覺得應該可以，請洽導師或系統管理員。"),
        404: ("找不到這一頁", "網址可能打錯了，或這筆資料不是你的、已經不存在。"),
    }

    def friendly_error(error):
        """401、403、404 改成中文頁面（10-27 實測問題 5）；狀態碼不變，給程式讀的請求照樣回 JSON。"""
        from flask import jsonify, render_template, request
        from app.routes.main import get_current_user
        title, message = error_texts[error.code]
        if request.accept_mimetypes.best == "application/json":
            return jsonify(error=title, message=message), error.code
        next_path = request.full_path.rstrip("?") if error.code == 401 and request.method == "GET" else None
        return render_template("error_page.html", user=get_current_user(), code=error.code, title=title,
                               message=message, next_path=next_path), error.code

    for code in error_texts:
        app.register_error_handler(code, friendly_error)

    @app.errorhandler(413)
    def file_too_large(_error):
        from flask import render_template, request
        from app.routes.main import get_current_user
        limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        back = request.referrer if request.referrer and request.referrer.startswith(request.host_url) else None
        return render_template("upload_too_large.html", user=get_current_user(), limit_mb=limit_mb, back=back), 413

    return app
