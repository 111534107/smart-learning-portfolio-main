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

    if app.config["OCR_QUEUE_MODE"] == "thread":
        from app.services.ocr_queue import recover_on_startup
        recover_on_startup(app)

    @app.errorhandler(413)
    def file_too_large(_error):
        from flask import render_template, request
        from app.routes.main import get_current_user
        limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        back = request.referrer if request.referrer and request.referrer.startswith(request.host_url) else None
        return render_template("upload_too_large.html", user=get_current_user(), limit_mb=limit_mb, back=back), 413

    return app
