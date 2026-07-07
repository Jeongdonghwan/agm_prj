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


@bp.route("/me/nickname/check")
def nickname_check():
    """닉네임 중복/금칙어 확인 (실시간)."""
    from utils import validate_nickname

    value = (request.args.get("value") or "").strip()
    ok, reason = validate_nickname(value)
    if not ok:
        return jsonify({"available": False, "reason": reason})
    from models import User

    if User.query.filter_by(nickname=value).first():
        return jsonify({"available": False, "reason": "이미 사용 중인 닉네임입니다."})
    return jsonify({"available": True, "reason": ""})


@bp.route("/me/nickname", methods=["PUT", "POST"])
def nickname_set():
    """닉네임 설정/변경 — 변경은 30일 1회 (§4-2)."""
    from datetime import datetime, timedelta

    from flask import g

    from utils import validate_nickname

    if g.user is None:
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": "로그인이 필요합니다."}}), 401
    value = ((request.get_json(silent=True) or request.form).get("value") or "").strip()
    ok, reason = validate_nickname(value)
    if not ok:
        return jsonify({"error": {"code": "INVALID_NICKNAME", "message": reason}}), 400
    from models import User

    dup = User.query.filter(User.nickname == value, User.id != g.user.id).first()
    if dup:
        return jsonify({"error": {"code": "DUPLICATED", "message": "이미 사용 중인 닉네임입니다."}}), 409
    if g.user.nickname and g.user.nickname_changed_at:
        if datetime.now() - g.user.nickname_changed_at < timedelta(days=30):
            return jsonify(
                {"error": {"code": "TOO_SOON", "message": "닉네임은 30일에 1회만 변경할 수 있습니다."}}
            ), 429
    g.user.nickname = value
    g.user.nickname_changed_at = datetime.now()
    db.session.commit()
    return jsonify({"ok": True, "nickname": value})


@bp.route("/community/posts/<int:post_id>/like", methods=["POST"])
def community_like(post_id):
    """추천 — 글당 1회 (§4-2). 변호사는 커뮤니티 열람만."""
    from flask import g

    from models import CommunityPost
    from models.community import community_likes

    if g.user is None:
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": "로그인이 필요합니다."}}), 401
    if g.user.role not in ("user", "admin"):
        return jsonify({"error": {"code": "FORBIDDEN", "message": "추천 권한이 없습니다."}}), 403
    post = CommunityPost.query.filter_by(id=post_id, status="open").filter(
        CommunityPost.deleted_at.is_(None)
    ).first()
    if post is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "글 없음"}}), 404
    exists = db.session.execute(
        community_likes.select().where(
            community_likes.c.post_id == post_id,
            community_likes.c.user_id == g.user.id,
        )
    ).first()
    if exists:
        return jsonify({"error": {"code": "ALREADY_LIKED", "message": "이미 추천한 글입니다."}}), 409
    db.session.execute(
        community_likes.insert().values(post_id=post_id, user_id=g.user.id)
    )
    post.likes = (post.likes or 0) + 1
    db.session.commit()
    return jsonify({"ok": True, "likes": post.likes})


@bp.route("/reports", methods=["POST"])
def report():
    """신고 — 로그인 회원."""
    from flask import g

    from models import Report

    if g.user is None:
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": "로그인이 필요합니다."}}), 401
    data = request.get_json(silent=True) or request.form
    target_type = data.get("target_type")
    target_id = data.get("target_id")
    reason = (data.get("reason") or "").strip()
    if target_type not in ("community_post", "community_comment", "consultation", "answer"):
        return jsonify({"error": {"code": "INVALID_TARGET", "message": "잘못된 신고 대상입니다."}}), 400
    if not target_id or not reason:
        return jsonify({"error": {"code": "MISSING_FIELDS", "message": "대상과 사유는 필수입니다."}}), 400
    db.session.add(
        Report(
            reporter_id=g.user.id,
            target_type=target_type,
            target_id=int(target_id),
            reason=reason[:300],
        )
    )
    db.session.commit()
    return jsonify({"ok": True})
