from datetime import datetime

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from extensions import db
from models import CommunityComment, CommunityPost, Consultation
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
    return render_template(
        "mypage/home.html",
        active_menu=None,
        my_consults=my_consults,
        my_posts=my_posts,
        my_comments=my_comments,
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
