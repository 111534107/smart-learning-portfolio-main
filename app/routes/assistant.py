"""資管科小助手的對話介面（右下角聊天視窗呼叫這裡）。"""

import json

from flask import Blueprint, jsonify, request

from app.routes.main import get_current_user, role_required
from app.services.assistant_service import ask

assistant_bp = Blueprint("assistant", __name__)


@assistant_bp.post("/assistant/ask")
@role_required("student", "teacher")
def assistant_ask():
    try:
        history = json.loads(request.form.get("history") or "[]")
    except ValueError:
        history = []
    if not isinstance(history, list):
        history = []
    result = ask(get_current_user(), request.form.get("message", ""), history=history,
                 page=request.form.get("page", ""))
    return jsonify(result)
