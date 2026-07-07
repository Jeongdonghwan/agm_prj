import re
from datetime import datetime

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload

from extensions import db
from models import Category, FirmAd, LawyerPost, LegalCase, News
from utils import cached_page

bp = Blueprint("contents", __name__)

PER_PAGE = 10

POST_TYPES = [
    ("case", "해결사례"),
    ("guide", "법률가이드"),
    ("video", "법률동영상"),
    ("essay", "변호사에세이"),
]
POST_TYPE_LABELS = dict(POST_TYPES)

CASE_TYPES = [
    ("criminal", "형사"),
    ("civil", "민사"),
    ("administrative", "행정"),
    ("constitutional", "헌법"),
    ("patent", "특허"),
]
CASE_TYPE_LABELS = dict(CASE_TYPES)


def _slug(text: str) -> str:
    s = re.sub(r"[^\w가-힣-]", "", (text or "").replace(" ", "-"))
    return s[:40] or "item"


# ─────────────────────────── 변호사포스트 ───────────────────────────
@bp.route("/posts")
@cached_page(120)
def posts():
    ptype = request.args.get("type", "case")
    if ptype not in POST_TYPE_LABELS:
        ptype = "case"
    category_id = request.args.get("category", type=int)
    sort = request.args.get("sort", "recent")
    page = max(request.args.get("page", 1, type=int), 1)

    q = (
        LawyerPost.query.filter_by(type=ptype, status="published")
        .filter(LawyerPost.deleted_at.is_(None))
        .options(joinedload(LawyerPost.lawyer), joinedload(LawyerPost.category))
    )
    if category_id:
        q = q.filter(LawyerPost.category_id == category_id)
    q = q.order_by(
        LawyerPost.views.desc() if sort == "views" else LawyerPost.published_at.desc()
    )
    total = q.count()
    items = q.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()

    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    return render_template(
        "contents/posts.html",
        active_menu="posts",
        items=items,
        total=total,
        page=page,
        has_next=total > page * PER_PAGE,
        ptype=ptype,
        post_types=POST_TYPES,
        sort=sort,
        parents=parents,
        category_id=category_id,
        slug=_slug,
    )


@bp.route("/posts/<int:post_id>")
@bp.route("/posts/<int:post_id>-<slug>")
def post_detail(post_id, slug=None):
    post = (
        LawyerPost.query.options(joinedload(LawyerPost.lawyer))
        .filter_by(id=post_id, status="published")
        .filter(LawyerPost.deleted_at.is_(None))
        .first()
    )
    if post is None:
        abort(404)
    canonical = _slug(post.title)
    if slug != canonical:
        return redirect(url_for("contents.post_detail", post_id=post_id, slug=canonical), 301)
    post.views = (post.views or 0) + 1
    db.session.commit()
    profile = post.lawyer.lawyer_profile
    return render_template(
        "contents/post_detail.html",
        active_menu="posts",
        post=post,
        profile=profile,
        type_label=POST_TYPE_LABELS.get(post.type, ""),
        canonical_slug=canonical,
    )


# ─────────────────────────── 판례돋보기 ───────────────────────────
@bp.route("/cases")
@cached_page(120)
def cases():
    case_type = request.args.get("case_type")
    category_id = request.args.get("category", type=int)
    page = max(request.args.get("page", 1, type=int), 1)

    q = LegalCase.query.filter(LegalCase.deleted_at.is_(None))
    if case_type in CASE_TYPE_LABELS:
        q = q.filter(LegalCase.case_type == case_type)
    if category_id:
        # category_ids JSON 배열 포함 검사 (데모 규모 — JSON_CONTAINS)
        q = q.filter(
            db.func.json_contains(LegalCase.category_ids, db.literal(str(category_id)))
        )
    q = q.order_by(LegalCase.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()

    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    cat_names = {c.id: c.name for c in parents}
    for c in Category.query.filter(Category.parent_id.isnot(None)):
        cat_names[c.id] = c.name
    return render_template(
        "contents/cases.html",
        active_menu="cases",
        items=items,
        total=total,
        page=page,
        has_next=total > page * PER_PAGE,
        case_types=CASE_TYPES,
        case_type=case_type,
        parents=parents,
        category_id=category_id,
        cat_names=cat_names,
        slug=_slug,
    )


@bp.route("/cases/<int:case_id>")
@bp.route("/cases/<int:case_id>-<slug>")
def case_detail(case_id, slug=None):
    case = LegalCase.query.filter_by(id=case_id).filter(
        LegalCase.deleted_at.is_(None)
    ).first()
    if case is None:
        abort(404)
    canonical = _slug(case.title)
    if slug != canonical:
        return redirect(url_for("contents.case_detail", case_id=case_id, slug=canonical), 301)
    case.views = (case.views or 0) + 1
    db.session.commit()
    cat_names = {
        c.id: c.name
        for c in Category.query.filter(Category.id.in_(case.category_ids or []))
    }
    return render_template(
        "contents/case_detail.html",
        active_menu="cases",
        case=case,
        cat_names=cat_names,
        case_type_label=CASE_TYPE_LABELS.get(case.case_type, ""),
        canonical_slug=canonical,
    )


# ─────────────────────────── 안기모뉴스 ───────────────────────────
@bp.route("/news")
@cached_page(120)
def news():
    tag = request.args.get("tag")
    page = max(request.args.get("page", 1, type=int), 1)
    q = News.query.filter(News.deleted_at.is_(None), News.published_at.isnot(None))
    if tag:
        q = q.filter(db.func.json_contains(News.hashtags, db.literal(f'"{tag}"')))
    q = q.order_by(News.published_at.desc())
    total = q.count()
    items = q.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()

    # 태그 목록 (데모 규모 — 전체에서 수집)
    all_tags = []
    for n in News.query.filter(News.deleted_at.is_(None)).all():
        for t in n.hashtags or []:
            if t not in all_tags:
                all_tags.append(t)
    return render_template(
        "contents/news.html",
        active_menu="news",
        items=items,
        total=total,
        page=page,
        has_next=total > page * PER_PAGE,
        tag=tag,
        all_tags=all_tags,
        slug=_slug,
    )


@bp.route("/news/<int:news_id>")
@bp.route("/news/<int:news_id>-<slug>")
def news_detail(news_id, slug=None):
    item = News.query.filter_by(id=news_id).filter(News.deleted_at.is_(None)).first()
    if item is None:
        abort(404)
    canonical = _slug(item.title)
    if slug != canonical:
        return redirect(url_for("contents.news_detail", news_id=news_id, slug=canonical), 301)
    item.views = (item.views or 0) + 1
    db.session.commit()
    return render_template(
        "contents/news_detail.html",
        active_menu="news",
        item=item,
        canonical_slug=canonical,
    )


# ─────────────────────────── 로펌 ───────────────────────────
@bp.route("/firms")
@cached_page(120)
def firms():
    category_id = request.args.get("category", type=int)
    now = datetime.now()
    q = FirmAd.query.filter(
        FirmAd.is_active.is_(True),
        db.or_(FirmAd.starts_at.is_(None), FirmAd.starts_at <= now),
        db.or_(FirmAd.ends_at.is_(None), FirmAd.ends_at >= now),
    ).options(joinedload(FirmAd.category))
    if category_id:
        q = q.filter(FirmAd.category_id == category_id)
    items = q.order_by(FirmAd.sort_order).all()

    # 칩: 광고가 존재하는 분야만
    used_cat_ids = {
        f.category_id
        for f in FirmAd.query.filter(FirmAd.is_active.is_(True)).all()
        if f.category_id
    }
    chips = (
        Category.query.filter(Category.id.in_(used_cat_ids or {0}))
        .order_by(Category.sort_order)
        .all()
    )
    return render_template(
        "contents/firms.html",
        active_menu="firms",
        items=items,
        chips=chips,
        category_id=category_id,
    )
