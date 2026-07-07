from flask import Blueprint, jsonify, request

from extensions import db
from models import FirmAd, FirmInquiry, LawyerProfile

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


@bp.route("/firms/<int:firm_id>/inquiry", methods=["POST"])
def firm_inquiry(firm_id):
    """로펌 간편 문의 — 비회원 가능, 관리자 접수함으로 (§4-1)."""
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    content = (data.get("content") or "").strip()
    if not (name and phone and content):
        return jsonify(
            {"error": {"code": "MISSING_FIELDS", "message": "이름/연락처/내용은 필수입니다."}}
        ), 400
    if db.session.get(FirmAd, firm_id) is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "로펌 광고 없음"}}), 404
    db.session.add(
        FirmInquiry(firm_ad_id=firm_id, name=name[:50], phone=phone[:20], content=content[:1000])
    )
    db.session.commit()
    return jsonify({"ok": True})
