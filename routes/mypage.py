from datetime import datetime

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from extensions import db
from models import CommunityComment, CommunityPost, Consultation
from models.community import community_bookmarks
from routes.decorators import login_required

bp = Blueprint("mypage", __name__, url_prefix="/mypage")


@bp.route("/")
@login_required
def home():
    my_consults = (
        Consultation.query.filter_by(user_id=g.user.id)
        .filter(Consultation.deleted_at.is_(None))
        .order_by(Consultation.created_at.desc())
        .limit(20)
        .all()
    )
    my_posts = (
        CommunityPost.query.filter_by(user_id=g.user.id)
        .filter(CommunityPost.deleted_at.is_(None))
        .order_by(CommunityPost.created_at.desc())
        .limit(20)
        .all()
    )
    my_comments = (
        CommunityComment.query.filter_by(user_id=g.user.id)
        .filter(CommunityComment.deleted_at.is_(None))
        .order_by(CommunityComment.created_at.desc())
        .limit(20)
        .all()
    )
    my_bookmarks = (
        CommunityPost.query.join(
            community_bookmarks, CommunityPost.id == community_bookmarks.c.post_id
        )
        .filter(
            community_bookmarks.c.user_id == g.user.id,
            CommunityPost.status == "open",
            CommunityPost.deleted_at.is_(None),
        )
        .order_by(CommunityPost.created_at.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "mypage/home.html",
        active_menu=None,
        my_consults=my_consults,
        my_posts=my_posts,
        my_comments=my_comments,
        my_bookmarks=my_bookmarks,
    )


@bp.route("/update", methods=["POST"])
@login_required
def update():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    g.user.name = name or g.user.name
    g.user.phone = phone or g.user.phone
    db.session.commit()
    flash("회원 정보가 수정되었습니다.", "success")
    return redirect(url_for("mypage.home"))


@bp.route("/visit-proof", methods=["POST"])
@login_required
def visit_proof():
    """커뮤니티 인증 — 접견예약확인 캡처 제출/재제출."""
    from routes.auth import save_visit_proof

    if g.user.role != "user":
        flash("일반회원만 제출할 수 있습니다.", "error")
        return redirect(url_for("mypage.home"))
    if g.user.approved_at:
        flash("이미 커뮤니티 이용이 승인된 계정입니다.", "success")
        return redirect(url_for("mypage.home"))
    f = request.files.get("visit_proof")
    if not f or not f.filename:
        flash("접견예약확인 이미지를 선택해주세요.", "error")
    else:
        err = save_visit_proof(g.user, f)
        if err:
            flash(err, "error")
        else:
            db.session.commit()
            flash("접수되었습니다. 관리자 승인 후 커뮤니티를 이용할 수 있습니다.", "success")
    return redirect(request.form.get("next") or url_for("mypage.home"))


@bp.route("/password", methods=["POST"])
@login_required
def password():
    current = request.form.get("current_password", "")
    new = request.form.get("new_password", "")
    if not g.user.check_password(current):
        flash("현재 비밀번호가 올바르지 않습니다.", "error")
    elif len(new) < 8:
        flash("새 비밀번호는 8자 이상이어야 합니다.", "error")
    else:
        g.user.set_password(new)
        db.session.commit()
        flash("비밀번호가 변경되었습니다.", "success")
    return redirect(url_for("mypage.home"))


@bp.route("/withdraw", methods=["POST"])
@login_required
def withdraw():
    if not g.user.check_password(request.form.get("password", "")):
        flash("비밀번호가 올바르지 않습니다.", "error")
        return redirect(url_for("mypage.home"))
    g.user.status = "withdrawn"
    g.user.deleted_at = datetime.now()  # soft delete (§11)
    db.session.commit()
    session.clear()
    flash("탈퇴가 완료되었습니다. 이용해주셔서 감사합니다.", "success")
    return redirect(url_for("main.index"))
