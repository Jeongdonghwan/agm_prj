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
    """로펌 간편 상담 — 휴대폰 + 개인정보 동의만 (YK식), 비회원 가능, 관리자 접수함으로."""
    data = request.get_json(silent=True) or request.form
    phone = (data.get("phone") or "").strip()
    if not phone:
        return jsonify(
            {"error": {"code": "MISSING_FIELDS", "message": "휴대폰 번호를 입력해주세요."}}
        ), 400
    if not data.get("agree"):
        return jsonify(
            {"error": {"code": "CONSENT_REQUIRED", "message": "개인정보 수집·제공에 동의해주세요."}}
        ), 400
    if db.session.get(FirmAd, firm_id) is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "로펌 광고 없음"}}), 404
    db.session.add(
        FirmInquiry(
            firm_ad_id=firm_id,
            name=(data.get("name") or "").strip()[:50] or None,
            phone=phone[:20],
            content=(data.get("content") or "").strip()[:1000] or "간편상담 신청 (개인정보 동의 완료)",
        )
    )
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/search-suggest")
def search_suggest():
    """헤더 검색 자동완성 — 분야명(#해시태그) + 변호사명 상위 8건."""
    from models import Category, LawyerProfile, User

    q = (request.args.get("q") or "").strip().lstrip("#")
    if len(q) < 1:
        return jsonify({"suggestions": []})
    like = f"%{q}%"
    out = []
    for c in (
        Category.query.filter(Category.name.like(like))
        .order_by(Category.parent_id.isnot(None), Category.sort_order)
        .limit(5)
    ):
        out.append({"type": "category", "id": c.id, "label": f"#{c.name}"})
    for p in (
        LawyerProfile.query.join(User, LawyerProfile.user_id == User.id)
        .filter(
            User.status == "active",
            User.deleted_at.is_(None),
            LawyerProfile.is_visible.is_(True),
            db.or_(User.name.like(like), LawyerProfile.firm_name.like(like)),
        )
        .limit(5)
    ):
        out.append({
            "type": "lawyer",
            "id": p.user_id,
            "label": f"{p.user.name} 변호사" + (f" · {p.firm_name}" if p.firm_name else ""),
        })
    return jsonify({"suggestions": out[:8]})


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
    if not g.user.community_approved:
        return jsonify({"error": {"code": "APPROVAL_REQUIRED", "message": "커뮤니티 인증 후 이용할 수 있습니다."}}), 403
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
