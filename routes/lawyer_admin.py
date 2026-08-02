import os
import uuid
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from extensions import db
from models import Category, Consultation, ConsultationAnswer, LawyerPost, LawyerProfile
from routes.decorators import role_required
from routes.profile_form import apply_profile_form, profile_form_context

bp = Blueprint("lawyer_admin", __name__)

PHOTO_EXTENSIONS = {"jpg", "jpeg", "png"}

POST_TYPES = [
    ("case", "해결사례"),
    ("guide", "법률가이드"),
    ("video", "법률동영상"),
    ("essay", "변호사에세이"),
]
POST_TYPE_LABELS = dict(POST_TYPES)
POST_STATUS_LABELS = {
    "pending": "검수 대기",
    "published": "게시중",
    "rejected": "반려",
    "hidden": "숨김",
}


def _matched_category_ids():
    """내 분야 + 그 부모/자식 분야 id 집합 (피드 매칭용)."""
    prof = g.user.lawyer_profile
    if prof is None or not prof.categories:
        return set()
    ids = set()
    for c in prof.categories:
        ids.add(c.id)
        if c.parent_id:
            ids.add(c.parent_id)
        else:
            ids.update(
                cid for (cid,) in db.session.query(Category.id).filter_by(parent_id=c.id)
            )
    return ids


def _pending_feed_query(cat_ids=None):
    """내 분야 매칭 + 아직 내가 답변하지 않은 상담글 쿼리 (§9 피드)."""
    if cat_ids is None:
        cat_ids = _matched_category_ids()
    answered_ids = [
        cid
        for (cid,) in db.session.query(ConsultationAnswer.consultation_id).filter(
            ConsultationAnswer.lawyer_id == g.user.id,
            ConsultationAnswer.deleted_at.is_(None),
        )
    ]
    q = Consultation.query.filter_by(status="open").filter(
        Consultation.deleted_at.is_(None)
    )
    if answered_ids:
        q = q.filter(~Consultation.id.in_(answered_ids))
    if cat_ids:
        q = q.filter(Consultation.category_id.in_(cat_ids))
    return q.order_by(Consultation.created_at.desc())


@bp.route("/")
@role_required("lawyer")
def dashboard():
    profile = g.user.lawyer_profile
    month_start = datetime.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    stats = {
        "view_count": profile.view_count if profile else 0,
        "contact_click_count": profile.contact_click_count if profile else 0,
        "answer_count": ConsultationAnswer.query.filter(
            ConsultationAnswer.lawyer_id == g.user.id,
            ConsultationAnswer.deleted_at.is_(None),
            ConsultationAnswer.created_at >= month_start,
        ).count(),
        "published_posts": LawyerPost.query.filter_by(
            lawyer_id=g.user.id, status="published"
        ).filter(LawyerPost.deleted_at.is_(None)).count(),
    }

    # 답변 대기 피드 미리보기 (§9 대시보드)
    feed = _pending_feed_query().limit(5).all() if profile else []

    # 내 포스트 상태 미리보기
    my_posts = (
        LawyerPost.query.filter_by(lawyer_id=g.user.id)
        .filter(LawyerPost.deleted_at.is_(None))
        .order_by(LawyerPost.created_at.desc())
        .limit(5)
        .all()
    )
    return render_template(
        "lawyer_admin/dashboard.html",
        stats=stats,
        profile=profile,
        feed=feed,
        my_posts=my_posts,
        status_labels=POST_STATUS_LABELS,
        type_labels=POST_TYPE_LABELS,
    )


@bp.route("/profile", methods=["GET", "POST"])
@role_required("lawyer")
def profile():
    """프로필 관리 — 저장 즉시 /lawyers/:id 공개 페이지 생성/갱신 (§4-3)."""
    prof = g.user.lawyer_profile
    if prof is None:
        prof = LawyerProfile(user_id=g.user.id, license_no="")
        db.session.add(prof)

    if request.method == "POST":
        errors = apply_profile_form(prof, request.form, request.files, g.user.id)
        if errors:
            db.session.rollback()
            for e in errors:
                flash(e, "error")
        else:
            db.session.commit()
            from utils import invalidate_page_cache

            invalidate_page_cache()
            flash("프로필이 저장되었습니다. 공개 페이지에 즉시 반영됩니다.", "success")
            return redirect(url_for("lawyer_admin.profile"))

    return render_template(
        "lawyer_admin/profile.html", profile=prof, **profile_form_context(prof)
    )


@bp.route("/posts")
@role_required("lawyer")
def posts():
    """내 포스트 목록: 게시중 / 검수 대기 / 반려(+사유)."""
    status = request.args.get("status", "all")
    q = LawyerPost.query.filter_by(lawyer_id=g.user.id).filter(
        LawyerPost.deleted_at.is_(None)
    )
    if status in POST_STATUS_LABELS:
        q = q.filter_by(status=status)
    items = q.order_by(LawyerPost.created_at.desc()).all()
    counts = {
        st: LawyerPost.query.filter_by(lawyer_id=g.user.id, status=st)
        .filter(LawyerPost.deleted_at.is_(None))
        .count()
        for st in ("published", "pending", "rejected")
    }
    return render_template(
        "lawyer_admin/posts.html",
        items=items,
        status=status,
        counts=counts,
        type_labels=POST_TYPE_LABELS,
        status_labels=POST_STATUS_LABELS,
    )


def _save_thumbnail(thumb):
    """포스트 썸네일 저장 → (url, error)."""
    ext = thumb.filename.rsplit(".", 1)[-1].lower() if "." in thumb.filename else ""
    if ext not in PHOTO_EXTENSIONS:
        return None, "썸네일은 jpg, jpeg, png만 업로드할 수 있습니다."
    tdir = os.path.join(current_app.config["UPLOAD_FOLDER"], "posts", str(g.user.id))
    os.makedirs(tdir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    thumb.save(os.path.join(tdir, fname))
    return url_for("main.uploads", filename=f"posts/{g.user.id}/{fname}"), None


def _post_form_errors(form):
    errors = []
    if form.get("type") not in POST_TYPE_LABELS:
        errors.append("포스트 타입을 선택해주세요.")
    if not form.get("title", "").strip():
        errors.append("제목을 입력해주세요.")
    if not form.get("content", "").strip():
        errors.append("본문을 입력해주세요.")
    # 분야는 유저 화면 필터·해결사례 광고 매칭 기준이므로 필수
    if not form.get("category_id", type=int):
        errors.append("분야를 선택해주세요.")
    return errors


def _render_post_form(post=None):
    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    return render_template(
        "lawyer_admin/post_form.html",
        post_types=POST_TYPES,
        parents=parents,
        post=post,
        form=request.form,
    )


@bp.route("/posts/new", methods=["GET", "POST"])
@role_required("lawyer")
def post_new():
    """포스트 작성 → 저장 시 pending → 관리자 검수 후 게시 (§4-3)."""
    if request.method == "POST":
        form = request.form
        errors = _post_form_errors(form)
        thumbnail_url = None
        thumb = request.files.get("thumbnail")
        if thumb and thumb.filename:
            thumbnail_url, err = _save_thumbnail(thumb)
            if err:
                errors.append(err)

        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db.session.add(
                LawyerPost(
                    lawyer_id=g.user.id,
                    type=form.get("type"),
                    title=form["title"].strip()[:200],
                    content=form["content"].strip(),
                    thumbnail_url=thumbnail_url,
                    result_badge=form.get("result_badge", "").strip()[:30] or None,
                    category_id=form.get("category_id", type=int) or None,
                    status="pending",
                )
            )
            db.session.commit()
            from utils import invalidate_page_cache

            invalidate_page_cache()
            flash("포스트가 제출되었습니다. 관리자 검수 후 게시됩니다.", "success")
            return redirect(url_for("lawyer_admin.posts"))

    return _render_post_form()


@bp.route("/posts/<int:post_id>/edit", methods=["GET", "POST"])
@role_required("lawyer")
def post_edit(post_id):
    """내 포스트 수정 — 저장 시 다시 검수 대기로(반려 → 수정 → 재검수)."""
    post = LawyerPost.query.filter_by(id=post_id, lawyer_id=g.user.id).filter(
        LawyerPost.deleted_at.is_(None)
    ).first()
    if post is None:
        abort(404)

    if request.method == "POST":
        form = request.form
        errors = _post_form_errors(form)
        thumbnail_url = post.thumbnail_url
        thumb = request.files.get("thumbnail")
        if thumb and thumb.filename:
            saved, err = _save_thumbnail(thumb)
            if err:
                errors.append(err)
            else:
                thumbnail_url = saved

        if errors:
            for e in errors:
                flash(e, "error")
        else:
            post.type = form.get("type")
            post.title = form["title"].strip()[:200]
            post.content = form["content"].strip()
            post.thumbnail_url = thumbnail_url
            post.result_badge = form.get("result_badge", "").strip()[:30] or None
            post.category_id = form.get("category_id", type=int) or None
            post.status = "pending"  # 수정하면 다시 검수 대기
            post.reject_reason = None
            post.published_at = None
            db.session.commit()
            from utils import invalidate_page_cache

            invalidate_page_cache()
            flash("포스트를 수정했습니다. 관리자 재검수 후 게시됩니다.", "success")
            return redirect(url_for("lawyer_admin.posts"))

    return _render_post_form(post)


@bp.route("/posts/<int:post_id>/delete", methods=["POST"])
@role_required("lawyer")
def post_delete(post_id):
    post = LawyerPost.query.filter_by(id=post_id, lawyer_id=g.user.id).first()
    if post is None:
        flash("포스트를 찾을 수 없습니다.", "error")
    else:
        post.deleted_at = datetime.now()  # soft delete (§11)
        db.session.commit()
        flash("포스트가 삭제되었습니다.", "success")
    return redirect(url_for("lawyer_admin.posts"))


@bp.route("/answers")
@role_required("lawyer")
def answers():
    """분야 매칭 답변 대기 피드 + 내 답변 목록 (§9)."""
    cat_ids = _matched_category_ids()
    feed = _pending_feed_query(cat_ids).limit(20).all()

    my_answers = (
        ConsultationAnswer.query.filter_by(lawyer_id=g.user.id)
        .filter(ConsultationAnswer.deleted_at.is_(None))
        .order_by(ConsultationAnswer.created_at.desc())
        .limit(20)
        .all()
    )
    consult_map = {
        c.id: c
        for c in Consultation.query.filter(
            Consultation.id.in_([a.consultation_id for a in my_answers] or [0])
        )
    }
    return render_template(
        "lawyer_admin/answers.html",
        feed=feed,
        my_answers=my_answers,
        consult_map=consult_map,
        has_categories=bool(cat_ids),
    )


@bp.route("/answers", methods=["POST"])
@role_required("lawyer")
def answer_create():
    """답변 작성 — 상담글당 변호사 1인 1답변 (uq_one_answer)."""
    consultation_id = request.form.get("consultation_id", type=int)
    content = request.form.get("content", "").strip()
    c = Consultation.query.filter_by(id=consultation_id, status="open").filter(
        Consultation.deleted_at.is_(None)
    ).first()
    if c is None:
        flash("상담글을 찾을 수 없습니다.", "error")
        return redirect(url_for("lawyer_admin.answers"))
    if not content:
        flash("답변 내용을 입력해주세요.", "error")
        return redirect(url_for("lawyer_admin.answers"))
    exists = ConsultationAnswer.query.filter_by(
        consultation_id=consultation_id, lawyer_id=g.user.id
    ).first()
    if exists and exists.deleted_at is None:
        flash("이미 이 상담글에 답변했습니다. (상담글당 1답변)", "error")
        return redirect(url_for("lawyer_admin.answers"))
    if exists:  # 삭제했던 답변이면 되살려 재작성 (uq_one_answer 제약 회피)
        exists.content = content
        exists.deleted_at = None
        exists.created_at = datetime.now()
    else:
        db.session.add(
            ConsultationAnswer(
                consultation_id=consultation_id, lawyer_id=g.user.id, content=content
            )
        )
    db.session.commit()
    flash("답변이 등록되었습니다.", "success")
    return redirect(url_for("lawyer_admin.answers"))


def _my_answer(answer_id):
    a = ConsultationAnswer.query.filter_by(id=answer_id, lawyer_id=g.user.id).filter(
        ConsultationAnswer.deleted_at.is_(None)
    ).first()
    if a is None:
        abort(404)
    return a


@bp.route("/answers/<int:answer_id>/edit", methods=["POST"])
@role_required("lawyer")
def answer_edit(answer_id):
    """내 답변 수정 (§7 PUT /api/lawyer-admin/answers)."""
    a = _my_answer(answer_id)
    content = request.form.get("content", "").strip()
    if not content:
        flash("답변 내용을 입력해주세요.", "error")
    else:
        a.content = content
        db.session.commit()
        flash("답변을 수정했습니다.", "success")
    return redirect(url_for("lawyer_admin.answers"))


@bp.route("/answers/<int:answer_id>/delete", methods=["POST"])
@role_required("lawyer")
def answer_delete(answer_id):
    """내 답변 삭제 — soft delete (§11). 삭제 후 해당 상담글이 피드에 다시 뜬다."""
    a = _my_answer(answer_id)
    a.deleted_at = datetime.now()
    db.session.commit()
    flash("답변을 삭제했습니다.", "success")
    return redirect(url_for("lawyer_admin.answers"))


@bp.route("/settings", methods=["GET", "POST"])
@role_required("lawyer")
def settings():
    """계정 설정 — 비밀번호 변경, 소속 변경 (§9)."""
    prof = g.user.lawyer_profile
    if request.method == "POST":
        action = request.form.get("action")
        if action == "password":
            if not g.user.check_password(request.form.get("current_password", "")):
                flash("현재 비밀번호가 올바르지 않습니다.", "error")
            elif len(request.form.get("new_password", "")) < 8:
                flash("새 비밀번호는 8자 이상이어야 합니다.", "error")
            else:
                g.user.set_password(request.form["new_password"])
                db.session.commit()
                flash("비밀번호가 변경되었습니다.", "success")
        elif action == "firm":
            firm_name = request.form.get("firm_name", "").strip()
            if prof and firm_name:
                prof.firm_name = firm_name
                db.session.commit()
                flash("소속이 변경되었습니다.", "success")
            else:
                flash("소속명을 입력해주세요.", "error")
        return redirect(url_for("lawyer_admin.settings"))
    return render_template("lawyer_admin/settings.html", profile=prof)
