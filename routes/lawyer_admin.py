import os
import uuid
from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from extensions import db
from models import Category, ConsultationAnswer, LawyerPost, LawyerProfile, Region
from routes.decorators import role_required

bp = Blueprint("lawyer_admin", __name__)

MAX_CATEGORIES = 7  # §4-3-1: 분야 최대 7개

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


def _completion_percent(profile: LawyerProfile) -> int:
    """프로필 완성도 % — 필수 4항목(각 20) + 부가 4항목(각 5)."""
    score = 0
    if profile.photo_url:
        score += 20
    if profile.headline:
        score += 20
    if profile.categories:
        score += 20
    if profile.office_phone or profile.kakao_url:
        score += 20
    if profile.address:
        score += 5
    if profile.intro_full:
        score += 5
    if profile.career:
        score += 5
    if profile.region_id:
        score += 5
    return score


@bp.route("/")
@role_required("lawyer")
def dashboard():
    profile = g.user.lawyer_profile
    stats = {
        "view_count": profile.view_count if profile else 0,
        "contact_click_count": profile.contact_click_count if profile else 0,
        "answer_count": ConsultationAnswer.query.filter_by(lawyer_id=g.user.id).count(),
        "published_posts": LawyerPost.query.filter_by(
            lawyer_id=g.user.id, status="published"
        ).count(),
    }
    return render_template(
        "lawyer_admin/dashboard.html",
        stats=stats,
        profile=profile,
        completion=_completion_percent(profile) if profile else 0,
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
        errors = []
        form = request.form

        headline = form.get("headline", "").strip()
        office_phone = form.get("office_phone", "").strip()
        kakao_url = form.get("kakao_url", "").strip()
        if kakao_url and not kakao_url.startswith(("http://", "https://")):
            errors.append("카카오톡 채널 URL은 http(s)://로 시작해야 합니다.")
        if not office_phone and not kakao_url:
            errors.append("사무실 전화와 카카오톡 채널 중 하나는 반드시 입력해야 합니다.")

        category_ids = [int(v) for v in form.getlist("categories") if v.isdigit()]
        if len(category_ids) > MAX_CATEGORIES:
            errors.append(f"분야는 최대 {MAX_CATEGORIES}개까지 선택할 수 있습니다.")

        # 경력: career_year[] + career_text[] 쌍
        career = []
        for year, text in zip(form.getlist("career_year"), form.getlist("career_text")):
            year, text = year.strip(), text.strip()
            if year or text:
                career.append({"year": year, "text": text})

        photo = request.files.get("photo")
        photo_url = prof.photo_url
        if photo and photo.filename:
            ext = photo.filename.rsplit(".", 1)[-1].lower() if "." in photo.filename else ""
            if ext not in PHOTO_EXTENSIONS:
                errors.append("프로필 사진은 jpg, jpeg, png만 업로드할 수 있습니다.")
            else:
                photo_dir = os.path.join(
                    current_app.config["UPLOAD_FOLDER"], "profiles", str(g.user.id)
                )
                os.makedirs(photo_dir, exist_ok=True)
                fname = f"{uuid.uuid4().hex}.{ext}"
                photo.save(os.path.join(photo_dir, fname))
                photo_url = url_for(
                    "main.uploads", filename=f"profiles/{g.user.id}/{fname}"
                )

        if errors:
            db.session.rollback()
            for e in errors:
                flash(e, "error")
        else:
            prof.headline = headline or None
            prof.firm_name = form.get("firm_name", "").strip() or None
            prof.bar_association = form.get("bar_association", "").strip() or None
            prof.office_phone = office_phone or None
            prof.kakao_url = kakao_url or None
            prof.address = form.get("address", "").strip() or None
            prof.intro_full = form.get("intro_full", "").strip() or None
            prof.career = career or None
            prof.region_id = form.get("region_id", type=int) or None
            prof.photo_url = photo_url
            prof.categories = (
                Category.query.filter(Category.id.in_(category_ids)).all()
                if category_ids
                else []
            )
            db.session.commit()
            flash("프로필이 저장되었습니다. 공개 페이지에 즉시 반영됩니다.", "success")
            return redirect(url_for("lawyer_admin.profile"))

    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    children_by_parent = {}
    for c in Category.query.filter(Category.parent_id.isnot(None)).order_by(
        Category.sort_order
    ):
        children_by_parent.setdefault(c.parent_id, []).append(c)
    regions = Region.query.order_by(Region.sort_order).all()
    selected_ids = {c.id for c in prof.categories} if prof.categories else set()

    return render_template(
        "lawyer_admin/profile.html",
        profile=prof,
        parents=parents,
        children_by_parent=children_by_parent,
        regions=regions,
        selected_ids=selected_ids,
        completion=_completion_percent(prof),
        max_categories=MAX_CATEGORIES,
    )


@bp.route("/posts")
@role_required("lawyer")
def posts():
    """내 포스트 목록: 게시중 / 검수 대기 / 반려(+사유)."""
    items = (
        LawyerPost.query.filter_by(lawyer_id=g.user.id)
        .filter(LawyerPost.deleted_at.is_(None))
        .order_by(LawyerPost.created_at.desc())
        .all()
    )
    return render_template(
        "lawyer_admin/posts.html",
        items=items,
        post_types=POST_TYPES,
        type_labels=POST_TYPE_LABELS,
        status_labels=POST_STATUS_LABELS,
    )


@bp.route("/posts/new", methods=["GET", "POST"])
@role_required("lawyer")
def post_new():
    """포스트 작성 → 저장 시 pending → 관리자 검수 후 게시 (§4-3)."""
    if request.method == "POST":
        form = request.form
        ptype = form.get("type")
        title = form.get("title", "").strip()
        content = form.get("content", "").strip()
        errors = []
        if ptype not in POST_TYPE_LABELS:
            errors.append("포스트 타입을 선택해주세요.")
        if not title:
            errors.append("제목을 입력해주세요.")
        if not content:
            errors.append("본문을 입력해주세요.")

        thumbnail_url = None
        thumb = request.files.get("thumbnail")
        if thumb and thumb.filename:
            ext = thumb.filename.rsplit(".", 1)[-1].lower() if "." in thumb.filename else ""
            if ext not in PHOTO_EXTENSIONS:
                errors.append("썸네일은 jpg, jpeg, png만 업로드할 수 있습니다.")
            else:
                tdir = os.path.join(
                    current_app.config["UPLOAD_FOLDER"], "posts", str(g.user.id)
                )
                os.makedirs(tdir, exist_ok=True)
                fname = f"{uuid.uuid4().hex}.{ext}"
                thumb.save(os.path.join(tdir, fname))
                thumbnail_url = url_for(
                    "main.uploads", filename=f"posts/{g.user.id}/{fname}"
                )

        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db.session.add(
                LawyerPost(
                    lawyer_id=g.user.id,
                    type=ptype,
                    title=title[:200],
                    content=content,
                    thumbnail_url=thumbnail_url,
                    result_badge=form.get("result_badge", "").strip()[:30] or None,
                    category_id=form.get("category_id", type=int) or None,
                    status="pending",
                )
            )
            db.session.commit()
            flash("포스트가 제출되었습니다. 관리자 검수 후 게시됩니다.", "success")
            return redirect(url_for("lawyer_admin.posts"))

    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    return render_template(
        "lawyer_admin/post_form.html", post_types=POST_TYPES, parents=parents
    )


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
