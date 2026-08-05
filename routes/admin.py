import os
import re
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
    send_from_directory,
    url_for,
)
from sqlalchemy.orm import joinedload

from extensions import db
from models import (
    AdminLog,
    Banner,
    Category,
    Consultation,
    FirmAd,
    FirmInquiry,
    LawyerPost,
    LawyerProfile,
    LawyerVerificationFile,
    LegalCase,
    News,
    Report,
    User,
)
from routes.decorators import role_required

bp = Blueprint("admin", __name__)

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}

POST_TYPE_LABELS = {"case": "해결사례", "guide": "법률가이드", "video": "법률동영상", "essay": "변호사에세이"}
CASE_TYPES = [
    ("criminal", "형사"), ("civil", "민사"), ("administrative", "행정"),
    ("constitutional", "헌법"), ("patent", "특허"),
]


def _log(action, target, detail=None):
    """관리자 액션 admin_logs 자동 기록 (§11) + 페이지 캐시 무효화."""
    from utils import invalidate_page_cache

    invalidate_page_cache()
    db.session.add(
        AdminLog(admin_id=g.user.id, action=action, target=str(target), detail=detail)
    )


def _save_image(file, subdir):
    """이미지 업로드 → /uploads 공개 URL 반환. 확장자 불일치 시 None."""
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in IMAGE_EXTENSIONS:
        return None
    d = os.path.join(current_app.config["UPLOAD_FOLDER"], subdir)
    os.makedirs(d, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(d, fname))
    return url_for("main.uploads", filename=f"{subdir}/{fname}")


# ─────────────────────────── 대시보드 ───────────────────────────
@bp.route("/")
@role_required("admin")
def dashboard():
    pending_lawyers = (
        User.query.filter_by(role="lawyer", status="pending")
        .order_by(User.created_at.desc())
        .limit(5)
        .all()
    )
    pending_posts = (
        LawyerPost.query.filter_by(status="pending")
        .filter(LawyerPost.deleted_at.is_(None))
        .options(joinedload(LawyerPost.lawyer))
        .order_by(LawyerPost.created_at.desc())
        .limit(5)
        .all()
    )
    stats = {
        "total_users": User.query.filter_by(role="user").count(),
        "total_lawyers": User.query.filter_by(role="lawyer", status="active").count(),
        "today_consultations": Consultation.query.filter(
            db.func.date(Consultation.created_at) == db.func.curdate()
        ).count(),
        "pending_lawyers": User.query.filter_by(role="lawyer", status="pending").count(),
        "pending_posts": LawyerPost.query.filter_by(status="pending").count(),
        "new_reports": Report.query.filter_by(status="new").count(),
    }
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        pending_lawyers=pending_lawyers,
        pending_posts=pending_posts,
        type_labels=POST_TYPE_LABELS,
    )


# ─────────────────────────── 회원 관리 (§4-4) ───────────────────────────
@bp.route("/users")
@role_required("admin")
def users():
    status = request.args.get("status", "all")
    keyword = request.args.get("q", "").strip()
    q = User.query.filter_by(role="user")
    if status in ("active", "suspended", "withdrawn"):
        q = q.filter_by(status=status)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            db.or_(User.email.like(like), User.name.like(like), User.nickname.like(like))
        )
    total = q.count()
    items = q.order_by(User.created_at.desc()).limit(50).all()
    return render_template(
        "admin/users.html", items=items, total=total, status=status, keyword=keyword
    )


def _get_plain_user(user_id):
    user = db.session.get(User, user_id)
    if user is None or user.role != "user":
        abort(404)
    return user


@bp.route("/users/<int:user_id>/suspend", methods=["POST"])
@role_required("admin")
def user_suspend(user_id):
    user = _get_plain_user(user_id)
    reason = request.form.get("reason", "").strip()
    user.status = "suspended"
    user.status_reason = reason[:300] or "운영 정책 위반"
    _log("user_suspend", f"user:{user_id}", {"reason": user.status_reason})
    db.session.commit()
    flash(f"{user.display_name} 회원을 정지했습니다.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/activate", methods=["POST"])
@role_required("admin")
def user_activate(user_id):
    user = _get_plain_user(user_id)
    user.status = "active"
    user.status_reason = None
    _log("user_activate", f"user:{user_id}")
    db.session.commit()
    flash(f"{user.display_name} 회원의 정지를 해제했습니다.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/withdraw", methods=["POST"])
@role_required("admin")
def user_withdraw(user_id):
    user = _get_plain_user(user_id)
    user.status = "withdrawn"
    user.deleted_at = datetime.now()  # soft delete (§11)
    _log("user_withdraw", f"user:{user_id}")
    db.session.commit()
    flash(f"{user.display_name} 회원을 탈퇴 처리했습니다.", "success")
    return redirect(url_for("admin.users"))


# ─────────────────────────── 변호사 관리 ───────────────────────────
@bp.route("/lawyers")
@role_required("admin")
def lawyers():
    status = request.args.get("status", "pending")
    keyword = request.args.get("q", "").strip()
    q = User.query.filter_by(role="lawyer").filter(User.deleted_at.is_(None))
    if status == "pending":
        q = q.filter(User.status.in_(["pending", "rejected"]))
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            db.or_(
                User.name.like(like),
                User.email.like(like),
                User.lawyer_profile.has(
                    db.or_(
                        LawyerProfile.license_no.like(like),
                        LawyerProfile.firm_name.like(like),
                    )
                ),
            )
        )
    q = q.options(joinedload(User.lawyer_profile)).order_by(User.created_at.desc())
    total = q.count()
    users = q.limit(50).all()
    files_by_user = {}
    for f in LawyerVerificationFile.query.filter(
        LawyerVerificationFile.user_id.in_([u.id for u in users] or [0])
    ):
        files_by_user.setdefault(f.user_id, []).append(f)
    pending_count = User.query.filter_by(role="lawyer").filter(
        User.deleted_at.is_(None), User.status.in_(["pending", "rejected"])
    ).count()
    return render_template(
        "admin/lawyers.html",
        users=users,
        status=status,
        keyword=keyword,
        total=total,
        files_by_user=files_by_user,
        pending_count=pending_count,
    )


@bp.route("/lawyers/<int:user_id>", methods=["GET", "POST"])
@role_required("admin")
def lawyer_detail(user_id):
    """변호사 상세 + 프로필 강제 수정 (§4-4)."""
    from models import ConsultationAnswer, LawyerAd
    from routes.profile_form import apply_profile_form, profile_form_context

    user = db.session.get(User, user_id)
    if user is None or user.role != "lawyer":
        abort(404)
    prof = user.lawyer_profile
    if prof is None:
        prof = LawyerProfile(user_id=user.id, license_no="")
        db.session.add(prof)
        db.session.commit()

    if request.method == "POST":
        errors = apply_profile_form(prof, request.form, request.files, user.id)
        if errors:
            db.session.rollback()
            for e in errors:
                flash(e, "error")
        else:
            _log("lawyer_profile_edit", f"user:{user_id}", {"name": user.name})
            db.session.commit()
            flash(f"{user.name} 변호사 프로필을 수정했습니다.", "success")
            return redirect(url_for("admin.lawyer_detail", user_id=user_id))

    stats = {
        "view_count": prof.view_count or 0,
        "contact_click_count": prof.contact_click_count or 0,
        "answers": ConsultationAnswer.query.filter_by(lawyer_id=user.id).filter(
            ConsultationAnswer.deleted_at.is_(None)
        ).count(),
        "posts": LawyerPost.query.filter_by(lawyer_id=user.id, status="published").filter(
            LawyerPost.deleted_at.is_(None)
        ).count(),
    }
    files = LawyerVerificationFile.query.filter_by(user_id=user.id).all()
    ads = (
        LawyerAd.query.filter_by(lawyer_id=user.id)
        .options(joinedload(LawyerAd.category))
        .order_by(LawyerAd.sort_order)
        .all()
    )
    return render_template(
        "admin/lawyer_detail.html",
        user=user,
        profile=prof,
        stats=stats,
        files=files,
        ads=ads,
        **profile_form_context(prof),
    )


@bp.route("/lawyers/<int:user_id>/approve", methods=["POST"])
@role_required("admin")
def lawyer_approve(user_id):
    user = db.session.get(User, user_id)
    if user is None or user.role != "lawyer":
        abort(404)
    user.status = "active"
    user.status_reason = None
    if user.lawyer_profile:
        user.lawyer_profile.approved_at = datetime.now()
    _log("lawyer_approve", f"user:{user_id}", {"name": user.name})
    db.session.commit()
    flash(f"{user.name} 변호사를 승인했습니다.", "success")
    return redirect(url_for("admin.lawyers"))


@bp.route("/lawyers/<int:user_id>/reject", methods=["POST"])
@role_required("admin")
def lawyer_reject(user_id):
    user = db.session.get(User, user_id)
    if user is None or user.role != "lawyer":
        abort(404)
    reason = request.form.get("reason", "").strip()
    user.status = "rejected"
    user.status_reason = reason[:300] or "서류 확인 불가"
    _log("lawyer_reject", f"user:{user_id}", {"reason": user.status_reason})
    db.session.commit()
    flash(f"{user.name} 변호사 가입을 반려했습니다.", "success")
    return redirect(url_for("admin.lawyers"))


@bp.route("/lawyers/<int:user_id>/toggle-visible", methods=["POST"])
@role_required("admin")
def lawyer_toggle_visible(user_id):
    prof = db.session.get(LawyerProfile, user_id)
    if prof is None:
        abort(404)
    prof.is_visible = not prof.is_visible
    _log("lawyer_toggle_visible", f"user:{user_id}", {"is_visible": prof.is_visible})
    db.session.commit()
    flash("노출 상태를 변경했습니다.", "success")
    return redirect(url_for("admin.lawyers", status="all"))


@bp.route("/lawyers/<int:user_id>/toggle-new", methods=["POST"])
@role_required("admin")
def lawyer_toggle_new(user_id):
    """메인 '새로 함께하는 변호사' 섹션 노출 on/off."""
    prof = db.session.get(LawyerProfile, user_id)
    if prof is None:
        abort(404)
    prof.show_in_new = not prof.show_in_new
    _log("lawyer_toggle_new", f"user:{user_id}", {"show_in_new": prof.show_in_new})
    db.session.commit()
    flash("메인 신규 섹션 노출 상태를 변경했습니다.", "success")
    return redirect(url_for("admin.lawyers", status="all"))


# ─────────────────── 변호사 광고 관리 (카테고리별) ───────────────────
AD_SLOTS = [("photocard", "최상단 포토카드"), ("adlist", "AD LAWYERS")]
AD_SLOT_LABELS = dict(AD_SLOTS)


@bp.route("/lawyer-ads")
@role_required("admin")
def lawyer_ads():
    """분야별 변호사 광고 목록 — 어느 카테고리에 누구를 어느 슬롯으로."""
    from models import LawyerAd

    slot = request.args.get("slot")
    category_id = request.args.get("category", type=int)
    q = LawyerAd.query.options(
        joinedload(LawyerAd.lawyer), joinedload(LawyerAd.category)
    )
    if slot in AD_SLOT_LABELS:
        q = q.filter_by(slot=slot)
    if category_id:
        q = q.filter_by(category_id=category_id)
    items = q.order_by(LawyerAd.category_id, LawyerAd.slot, LawyerAd.sort_order).all()

    # 카테고리별 그룹 (전체 노출이 맨 앞)
    groups = {}
    for ad in items:
        groups.setdefault(ad.category.name if ad.category else "전체 노출", []).append(ad)
    ordered = sorted(groups.items(), key=lambda kv: (kv[0] != "전체 노출", kv[0]))

    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    return render_template(
        "admin/lawyer_ads.html",
        groups=ordered,
        total=len(items),
        slot=slot,
        slots=AD_SLOTS,
        slot_labels=AD_SLOT_LABELS,
        parents=parents,
        category_id=category_id,
        now=datetime.now(),
    )


@bp.route("/lawyer-ads/new", methods=["GET", "POST"])
@bp.route("/lawyer-ads/<int:ad_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def lawyer_ad_form(ad_id=None):
    from models import LawyerAd

    item = db.session.get(LawyerAd, ad_id) if ad_id else None
    if ad_id and item is None:
        abort(404)
    if request.method == "POST":
        form = request.form
        lawyer_id = form.get("lawyer_id", type=int)
        lawyer = db.session.get(User, lawyer_id) if lawyer_id else None
        if lawyer is None or lawyer.role != "lawyer":
            flash("변호사를 선택해주세요.", "error")
        else:
            if item is None:
                item = LawyerAd()
                db.session.add(item)
            item.lawyer_id = lawyer_id
            item.category_id = form.get("category_id", type=int) or None  # 없으면 전체
            item.slot = form.get("slot") if form.get("slot") in AD_SLOT_LABELS else "photocard"
            item.sort_order = form.get("sort_order", type=int) or 0
            item.is_active = form.get("is_active") == "1"
            item.starts_at = (
                datetime.fromisoformat(form["starts_at"]) if form.get("starts_at") else None
            )
            item.ends_at = (
                datetime.fromisoformat(form["ends_at"]) if form.get("ends_at") else None
            )
            _log("lawyer_ad_save", f"lawyer_ad:{item.id or 'new'}", {"lawyer": lawyer.name})
            db.session.commit()
            flash("변호사 광고가 저장되었습니다.", "success")
            return redirect(url_for("admin.lawyer_ads"))

    lawyers_opts = (
        User.query.filter_by(role="lawyer", status="active")
        .filter(User.deleted_at.is_(None))
        .options(joinedload(User.lawyer_profile))
        .order_by(User.name)
        .all()
    )
    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    return render_template(
        "admin/lawyer_ad_form.html",
        item=item,
        lawyers=lawyers_opts,
        parents=parents,
        slots=AD_SLOTS,
    )


@bp.route("/lawyer-ads/<int:ad_id>/delete", methods=["POST"])
@role_required("admin")
def lawyer_ad_delete(ad_id):
    from models import LawyerAd

    item = db.session.get(LawyerAd, ad_id)
    if item:
        db.session.delete(item)
        _log("lawyer_ad_delete", f"lawyer_ad:{ad_id}")
        db.session.commit()
        flash("변호사 광고를 삭제했습니다.", "success")
    return redirect(url_for("admin.lawyer_ads"))


@bp.route("/verification-files/<int:file_id>")
@role_required("admin")
def verification_file(file_id):
    """인증 서류는 이 라우트로만 서빙 — 공개 URL 금지 (§11)."""
    vf = db.session.get(LawyerVerificationFile, file_id)
    if vf is None or not vf.file_url:
        abort(404)
    return send_from_directory(
        os.path.normpath(current_app.config["UPLOAD_FOLDER"]), vf.file_url
    )


# ─────────────────────────── 포스트 검수 ───────────────────────────
@bp.route("/posts")
@role_required("admin")
def posts():
    status = request.args.get("status", "pending")
    q = LawyerPost.query.filter(LawyerPost.deleted_at.is_(None))
    if status != "all":
        q = q.filter_by(status=status)
    items = (
        q.options(joinedload(LawyerPost.lawyer))
        .order_by(LawyerPost.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template(
        "admin/posts.html", items=items, status=status, type_labels=POST_TYPE_LABELS
    )


@bp.route("/posts/<int:post_id>/approve", methods=["POST"])
@role_required("admin")
def post_approve(post_id):
    post = db.session.get(LawyerPost, post_id)
    if post is None:
        abort(404)
    post.status = "published"
    post.published_at = datetime.now()
    post.reject_reason = None
    _log("post_approve", f"post:{post_id}", {"title": post.title})
    db.session.commit()
    flash("포스트를 승인·게시했습니다.", "success")
    return redirect(url_for("admin.posts"))


@bp.route("/posts/<int:post_id>/reject", methods=["POST"])
@role_required("admin")
def post_reject(post_id):
    post = db.session.get(LawyerPost, post_id)
    if post is None:
        abort(404)
    post.status = "rejected"
    post.reject_reason = request.form.get("reason", "").strip()[:300] or "검수 기준 미충족"
    _log("post_reject", f"post:{post_id}", {"reason": post.reject_reason})
    db.session.commit()
    flash("포스트를 반려했습니다.", "success")
    return redirect(url_for("admin.posts"))


# ─────────────────────────── 판례돋보기 CRUD ───────────────────────────
@bp.route("/cases")
@role_required("admin")
def cases():
    items = (
        LegalCase.query.filter(LegalCase.deleted_at.is_(None))
        .order_by(LegalCase.created_at.desc())
        .all()
    )
    return render_template("admin/cases.html", items=items, case_types=dict(CASE_TYPES))


@bp.route("/cases/new", methods=["GET", "POST"])
@bp.route("/cases/<int:case_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def case_form(case_id=None):
    case = db.session.get(LegalCase, case_id) if case_id else None
    if case_id and case is None:
        abort(404)
    if request.method == "POST":
        form = request.form
        if case is None:
            case = LegalCase()
            db.session.add(case)
        case.title = form.get("title", "").strip()[:200]
        case.summary = form.get("summary", "").strip()[:500]
        case.content = form.get("content", "").strip()
        case.court = form.get("court", "").strip()[:50]
        case.case_no = form.get("case_no", "").strip()[:60]
        case.case_type = form.get("case_type") or None
        case.category_ids = [int(v) for v in form.getlist("category_ids") if v.isdigit()]
        _log("case_save", f"case:{case.id or 'new'}", {"title": case.title})
        db.session.commit()
        flash("판례가 저장되었습니다.", "success")
        return redirect(url_for("admin.cases"))
    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    return render_template(
        "admin/case_form.html", case=case, case_types=CASE_TYPES, parents=parents
    )


@bp.route("/cases/<int:case_id>/delete", methods=["POST"])
@role_required("admin")
def case_delete(case_id):
    case = db.session.get(LegalCase, case_id)
    if case:
        case.deleted_at = datetime.now()
        _log("case_delete", f"case:{case_id}", {"title": case.title})
        db.session.commit()
        flash("판례가 삭제되었습니다.", "success")
    return redirect(url_for("admin.cases"))


# ─────────────────────────── 안기모뉴스 CRUD ───────────────────────────
@bp.route("/news")
@role_required("admin")
def news():
    items = News.query.filter(News.deleted_at.is_(None)).order_by(
        News.published_at.desc()
    ).all()
    return render_template("admin/news.html", items=items)


@bp.route("/news/new", methods=["GET", "POST"])
@bp.route("/news/<int:news_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def news_form(news_id=None):
    item = db.session.get(News, news_id) if news_id else None
    if news_id and item is None:
        abort(404)
    if request.method == "POST":
        form = request.form
        if item is None:
            item = News(published_at=datetime.now())
            db.session.add(item)
        item.title = form.get("title", "").strip()[:200]
        item.content = form.get("content", "").strip()
        item.reporter = form.get("reporter", "").strip()[:50] or None
        item.hashtags = [
            t.strip().lstrip("#") for t in form.get("hashtags", "").split(",") if t.strip()
        ]
        thumb = request.files.get("thumbnail")
        if thumb and thumb.filename:
            saved = _save_image(thumb, "news")
            if saved:
                item.thumbnail_url = saved
            else:
                flash("썸네일은 jpg, jpeg, png만 업로드할 수 있습니다.", "error")
        _log("news_save", f"news:{item.id or 'new'}", {"title": item.title})
        db.session.commit()
        flash("뉴스가 저장되었습니다.", "success")
        return redirect(url_for("admin.news"))
    return render_template("admin/news_form.html", item=item)


@bp.route("/news/<int:news_id>/delete", methods=["POST"])
@role_required("admin")
def news_delete(news_id):
    item = db.session.get(News, news_id)
    if item:
        item.deleted_at = datetime.now()
        _log("news_delete", f"news:{news_id}", {"title": item.title})
        db.session.commit()
        flash("뉴스가 삭제되었습니다.", "success")
    return redirect(url_for("admin.news"))


# ─────────────────────────── 배너 관리 ───────────────────────────
@bp.route("/banners")
@role_required("admin")
def banners():
    items = Banner.query.order_by(Banner.position, Banner.sort_order).all()
    # 사이드 배너는 순서 상위 1장만 실제 노출 — 목록에서 구분 표시용
    side_live = next(
        (b for b in items if b.position == "main_side" and b.is_active), None
    )
    return render_template(
        "admin/banners.html", items=items, side_live_id=side_live.id if side_live else None
    )


@bp.route("/banners/new", methods=["GET", "POST"])
@bp.route("/banners/<int:banner_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def banner_form(banner_id=None):
    item = db.session.get(Banner, banner_id) if banner_id else None
    if banner_id and item is None:
        abort(404)
    if request.method == "POST":
        form = request.form
        if item is None:
            item = Banner()
            db.session.add(item)
        item.position = (
            form.get("position")
            if form.get("position") in ("main_hero", "main_side")
            else "main_hero"
        )
        item.title = form.get("title", "").strip()[:100]
        item.link_url = form.get("link_url", "").strip()[:300] or None
        item.sort_order = form.get("sort_order", type=int) or 0
        item.is_active = form.get("is_active") == "1"
        item.starts_at = (
            datetime.fromisoformat(form["starts_at"]) if form.get("starts_at") else None
        )
        item.ends_at = (
            datetime.fromisoformat(form["ends_at"]) if form.get("ends_at") else None
        )
        img = request.files.get("image")
        if img and img.filename:
            saved = _save_image(img, "banners")
            if saved:
                item.image_url = saved
        elif form.get("remove_image") == "1":
            item.image_url = None  # 기본 일러스트로 되돌리기
        _log("banner_save", f"banner:{item.id or 'new'}", {"title": item.title})
        db.session.commit()
        flash("배너가 저장되었습니다.", "success")
        return redirect(url_for("admin.banners"))
    return render_template("admin/banner_form.html", item=item)


@bp.route("/banners/<int:banner_id>/delete", methods=["POST"])
@role_required("admin")
def banner_delete(banner_id):
    item = db.session.get(Banner, banner_id)
    if item:
        db.session.delete(item)
        _log("banner_delete", f"banner:{banner_id}", {"title": item.title})
        db.session.commit()
        flash("배너가 삭제되었습니다.", "success")
    return redirect(url_for("admin.banners"))


# ─────────────────────────── 로펌 광고 관리 + 접수함 ───────────────────────────
@bp.route("/firms")
@role_required("admin")
def firms():
    items = FirmAd.query.options(joinedload(FirmAd.category)).order_by(
        FirmAd.sort_order
    ).all()
    return render_template("admin/firms.html", items=items)


@bp.route("/firms/new", methods=["GET", "POST"])
@bp.route("/firms/<int:firm_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def firm_form(firm_id=None):
    item = db.session.get(FirmAd, firm_id) if firm_id else None
    if firm_id and item is None:
        abort(404)
    if request.method == "POST":
        form = request.form
        if item is None:
            item = FirmAd()
            db.session.add(item)
        item.firm_name = form.get("firm_name", "").strip()[:100]
        item.headline = form.get("headline", "").strip()[:200]
        item.description = form.get("description", "").strip()
        item.address = form.get("address", "").strip()[:200] or None
        item.category_id = form.get("category_id", type=int) or None
        item.sort_order = form.get("sort_order", type=int) or 0
        item.is_active = form.get("is_active") == "1"
        item.starts_at = (
            datetime.fromisoformat(form["starts_at"]) if form.get("starts_at") else None
        )
        item.ends_at = (
            datetime.fromisoformat(form["ends_at"]) if form.get("ends_at") else None
        )
        # 링크칩: "라벨|URL" 줄 단위
        links = []
        for line in form.get("links", "").splitlines():
            if "|" in line:
                label, _, href = line.partition("|")
                if label.strip() and href.strip():
                    links.append({"label": label.strip(), "url": href.strip()})
        item.links = links or None
        photos = list(item.photos or [])
        for f in request.files.getlist("photos"):
            if f and f.filename:
                saved = _save_image(f, "firms")
                if saved:
                    photos.append(saved)
        item.photos = photos[:5] or None
        _log("firm_save", f"firm:{item.id or 'new'}", {"firm_name": item.firm_name})
        db.session.commit()
        flash("로펌 광고가 저장되었습니다.", "success")
        return redirect(url_for("admin.firms"))
    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    return render_template("admin/firm_form.html", item=item, parents=parents)


@bp.route("/firms/<int:firm_id>/delete", methods=["POST"])
@role_required("admin")
def firm_delete(firm_id):
    item = db.session.get(FirmAd, firm_id)
    if item:
        db.session.delete(item)
        _log("firm_delete", f"firm:{firm_id}", {"firm_name": item.firm_name})
        db.session.commit()
        flash("로펌 광고가 삭제되었습니다.", "success")
    return redirect(url_for("admin.firms"))


@bp.route("/firm-inquiries")
@role_required("admin")
def firm_inquiries():
    items = (
        FirmInquiry.query.options(joinedload(FirmInquiry.firm_ad))
        .order_by(FirmInquiry.status, FirmInquiry.created_at.desc())
        .all()
    )
    return render_template("admin/firm_inquiries.html", items=items)


@bp.route("/firm-inquiries/<int:inq_id>/process", methods=["POST"])
@role_required("admin")
def firm_inquiry_process(inq_id):
    item = db.session.get(FirmInquiry, inq_id)
    if item is None:
        abort(404)
    item.status = "processed"
    _log("firm_inquiry_process", f"inquiry:{inq_id}")
    db.session.commit()
    flash("문의를 처리 완료로 표시했습니다.", "success")
    return redirect(url_for("admin.firm_inquiries"))


# ─────────────────────────── 운영 로그 ───────────────────────────
@bp.route("/logs")
@role_required("admin")
def logs():
    items = (
        AdminLog.query.options(joinedload(AdminLog.admin))
        .order_by(AdminLog.created_at.desc())
        .limit(100)
        .all()
    )
    return render_template("admin/logs.html", items=items)


# ─────────────────────────── 상담 관리 ───────────────────────────
@bp.route("/consultations")
@role_required("admin")
def consultations():
    from models import ConsultationAnswer

    # 신고된 상담글 우선 표시 (§4-4)
    reported_ids = {
        r.target_id
        for r in Report.query.filter_by(target_type="consultation", status="new")
    }
    items = (
        Consultation.query.filter(Consultation.deleted_at.is_(None))
        .options(joinedload(Consultation.user), joinedload(Consultation.category))
        .order_by(Consultation.created_at.desc())
        .limit(50)
        .all()
    )
    items.sort(key=lambda c: c.id not in reported_ids)
    answer_counts = dict(
        db.session.query(
            ConsultationAnswer.consultation_id, db.func.count(ConsultationAnswer.id)
        )
        .filter(ConsultationAnswer.deleted_at.is_(None))
        .group_by(ConsultationAnswer.consultation_id)
        .all()
    )
    return render_template(
        "admin/consultations.html",
        items=items,
        reported_ids=reported_ids,
        answer_counts=answer_counts,
    )


@bp.route("/consultations/<int:cid>/hide", methods=["POST"])
@role_required("admin")
def consultation_hide(cid):
    c = db.session.get(Consultation, cid)
    if c is None:
        abort(404)
    c.status = "open" if c.status == "hidden" else "hidden"
    _log("consultation_toggle_hide", f"consultation:{cid}", {"status": c.status})
    db.session.commit()
    flash("상담글 상태를 변경했습니다.", "success")
    return redirect(url_for("admin.consultations"))


@bp.route("/consultations/<int:cid>/delete", methods=["POST"])
@role_required("admin")
def consultation_delete(cid):
    c = db.session.get(Consultation, cid)
    if c is None:
        abort(404)
    c.status = "deleted"
    c.deleted_at = datetime.now()
    _log("consultation_delete", f"consultation:{cid}", {"title": c.title})
    db.session.commit()
    flash("상담글을 삭제했습니다.", "success")
    return redirect(url_for("admin.consultations"))


# ─────────────────────────── 커뮤니티 관리 ───────────────────────────
@bp.route("/community", methods=["GET", "POST"])
@role_required("admin")
def community():
    from models import CommunityComment, CommunityPost

    if request.method == "POST":  # 공지글 작성 (상단 고정)
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if title and content:
            db.session.add(
                CommunityPost(
                    user_id=g.user.id,
                    category="공지",
                    title=title[:200],
                    content=content,
                    is_notice=True,
                )
            )
            _log("community_notice", "community:new", {"title": title})
            db.session.commit()
            flash("공지글이 등록되었습니다.", "success")
        else:
            flash("공지 제목과 내용을 입력해주세요.", "error")
        return redirect(url_for("admin.community"))

    reported_ids = {
        r.target_id
        for r in Report.query.filter_by(target_type="community_post", status="new")
    }
    posts = (
        CommunityPost.query.filter(CommunityPost.deleted_at.is_(None))
        .options(joinedload(CommunityPost.user))
        .order_by(CommunityPost.is_notice.desc(), CommunityPost.created_at.desc())
        .limit(50)
        .all()
    )
    posts.sort(key=lambda p: (not p.is_notice, p.id not in reported_ids), reverse=False)
    return render_template("admin/community.html", posts=posts, reported_ids=reported_ids)


@bp.route("/community/<int:pid>/hide", methods=["POST"])
@role_required("admin")
def community_hide(pid):
    from models import CommunityPost

    p = db.session.get(CommunityPost, pid)
    if p is None:
        abort(404)
    p.status = "open" if p.status == "hidden" else "hidden"
    _log("community_toggle_hide", f"community_post:{pid}", {"status": p.status})
    db.session.commit()
    flash("게시글 상태를 변경했습니다.", "success")
    return redirect(url_for("admin.community"))


@bp.route("/community/<int:pid>/delete", methods=["POST"])
@role_required("admin")
def community_delete(pid):
    from models import CommunityPost

    p = db.session.get(CommunityPost, pid)
    if p is None:
        abort(404)
    p.status = "deleted"
    p.deleted_at = datetime.now()
    _log("community_delete", f"community_post:{pid}", {"title": p.title})
    db.session.commit()
    flash("게시글을 삭제했습니다.", "success")
    return redirect(url_for("admin.community"))


# ─────────────────────────── 게시판 관리 ───────────────────────────
SLUG_RE = re.compile(r"^[a-z0-9-]{2,40}$")


def _board_or_404(board_id):
    from models import CommunityBoard

    b = db.session.get(CommunityBoard, board_id)
    if b is None:
        abort(404)
    return b


@bp.route("/boards")
@role_required("admin")
def boards():
    """게시판 관리 — 상위 그룹/하위 게시판 트리."""
    from models import CommunityBoard, CommunityPost

    groups = (
        CommunityBoard.query.filter_by(parent_id=None)
        .options(joinedload(CommunityBoard.children))
        .order_by(CommunityBoard.sort_order, CommunityBoard.id)
        .all()
    )
    # 게시판별 글 수 (라벨+토픽 카테고리 합산)
    counts = dict(
        db.session.query(CommunityPost.category, db.func.count())
        .filter(CommunityPost.deleted_at.is_(None))
        .group_by(CommunityPost.category)
        .all()
    )
    post_counts = {}
    for grp in groups:
        for it in grp.children:
            if it.slug:
                cats = [it.label] + list(it.topics or [])
                post_counts[it.id] = sum(counts.get(c, 0) for c in cats)
    return render_template(
        "admin/boards.html", groups=groups, post_counts=post_counts
    )


@bp.route("/boards/new", methods=["GET", "POST"])
@bp.route("/boards/<int:board_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def board_form(board_id=None):
    from models import CommunityBoard

    item = _board_or_404(board_id) if board_id else None
    group_choices = (
        CommunityBoard.query.filter_by(parent_id=None)
        .order_by(CommunityBoard.sort_order, CommunityBoard.id)
        .all()
    )
    if request.method == "POST":
        label = request.form.get("label", "").strip()
        parent_id = request.form.get("parent_id", type=int) or None
        slug = request.form.get("slug", "").strip().lower() or None
        link_url = request.form.get("link_url", "").strip() or None
        topics = [
            t.strip()
            for t in request.form.get("topics", "").replace("\n", ",").split(",")
            if t.strip()
        ]
        errors = []
        if not label:
            errors.append("이름을 입력해주세요.")
        if parent_id:  # 하위 항목: 게시판(slug) 또는 링크(link_url) 중 하나
            if not slug and not link_url:
                errors.append("게시판 주소(slug) 또는 링크 URL 중 하나를 입력해주세요.")
            if slug and not SLUG_RE.match(slug):
                errors.append("주소(slug)는 영문 소문자·숫자·하이픈 2~40자입니다.")
            if slug:
                dup = CommunityBoard.query.filter_by(slug=slug).first()
                if dup and dup.id != (item.id if item else None):
                    errors.append("이미 사용 중인 주소(slug)입니다.")
        else:
            slug = link_url = None
            topics = []
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            if item is None:
                item = CommunityBoard(label=label)
                db.session.add(item)
            item.label = label
            item.parent_id = parent_id
            item.slug = slug if parent_id else None
            item.link_url = link_url if parent_id else None
            item.topics = topics
            item.admin_only = request.form.get("admin_only") == "1"
            item.show_topics = request.form.get("show_topics") == "1"
            item.sort_order = request.form.get("sort_order", type=int) or 0
            item.is_active = request.form.get("is_active") == "1"
            db.session.flush()
            _log("board_save", f"community_board:{item.id}", {"label": label, "slug": slug})
            db.session.commit()
            flash("게시판 구성을 저장했습니다.", "success")
            return redirect(url_for("admin.boards"))
    return render_template(
        "admin/board_form.html", item=item, group_choices=group_choices
    )


@bp.route("/boards/<int:board_id>/delete", methods=["POST"])
@role_required("admin")
def board_delete(board_id):
    b = _board_or_404(board_id)
    if b.parent_id is None and b.children:
        flash("하위 게시판이 있는 그룹은 삭제할 수 없습니다. 하위 항목을 먼저 삭제해주세요.", "error")
        return redirect(url_for("admin.boards"))
    _log("board_delete", f"community_board:{board_id}", {"label": b.label, "slug": b.slug})
    db.session.delete(b)
    db.session.commit()
    flash("삭제했습니다. 해당 게시판의 글은 DB에 남지만 화면에서는 접근할 수 없습니다.", "success")
    return redirect(url_for("admin.boards"))


# ─────────────────────────── 신고 처리 ───────────────────────────
@bp.route("/reports")
@role_required("admin")
def reports():
    items = (
        Report.query.options(joinedload(Report.reporter))
        .order_by(Report.status, Report.created_at.desc())
        .limit(100)
        .all()
    )
    return render_template("admin/reports.html", items=items)


@bp.route("/reports/<int:rid>/done", methods=["POST"])
@role_required("admin")
def report_done(rid):
    r = db.session.get(Report, rid)
    if r is None:
        abort(404)
    r.status = "done"
    _log("report_done", f"report:{rid}", {"target": f"{r.target_type}:{r.target_id}"})
    db.session.commit()
    flash("신고를 처리 완료로 표시했습니다.", "success")
    return redirect(url_for("admin.reports"))
