from flask import Blueprint, jsonify, request

from extensions import db
from models import LawyerProfile

# 경량 AJAX 전용 (/api/*)
bp = Blueprint("api", __name__)


@bp.route("/lawyers/<int:user_id>/contact-click", methods=["POST"])
def contact_click(user_id):
    """전화/카톡 클릭 수만 기록 — 사이트 내 중개 없음 (§4-1)."""
    click_type = (request.get_json(silent=True) or {}).get("type")
    if click_type not in ("phone", "kakao"):
        return jsonify({"error": {"code": "INVALID_TYPE", "message": "type은 phone|kakao"}}), 400
    profile = db.session.get(LawyerProfile, user_id)
    if profile is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "프로필 없음"}}), 404
    profile.contact_click_count = (profile.contact_click_count or 0) + 1
    db.session.commit()
    return jsonify({"ok": True})
