import re

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload

from extensions import db
from models import Category, ConsultationAnswer, LawyerPost, LawyerProfile, Region, User
from utils import cached_page

bp = Blueprint("lawyers", __name__, url_prefix="/lawyers")

PER_PAGE = 10


def _slugify(name: str) -> str:
    return re.sub(r"[^\w가-힣-]", "", (name or "").replace(" ", "-")) or "lawyer"


def _visible_profiles_query():
    """목록 노출 조건: is_visible + 필수 필드 완성 + 활성 계정 (§7)."""
    return (
        LawyerProfile.query.join(User, LawyerProfile.user_id == User.id)
        .filter(
            User.status == "active",
            User.deleted_at.is_(None),
            LawyerProfile.is_visible.is_(True),
            LawyerProfile.photo_url.isnot(None),
            LawyerProfile.headline.isnot(None),
            db.or_(
                LawyerProfile.office_phone.isnot(None),
                LawyerProfile.kakao_url.isnot(None),
            ),
            LawyerProfile.categories.any(),
        )
        .options(
            joinedload(LawyerProfile.user),
            joinedload(LawyerProfile.categories),
            joinedload(LawyerProfile.region),
        )
    )


@bp.route("/")
@cached_page(120)
def find():
    """변호사 찾기 — 대분류 탭 클릭 시 바로 해당 분야 변호사 리스트."""
    category_id = request.args.get("category", type=int)
    region_id = request.args.get("region", type=int)
    page = max(request.args.get("page", 1, type=int), 1)

    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()

    # 선택 분야: 대분류/세부분야 모두 허용
    selected = None
    parent_sel = None
    if category_id:
        selected = db.session.get(Category, category_id)
        if selected is None:
            abort(404)
        parent_sel = selected.parent if selected.parent_id else selected
    children = (
        Category.query.filter_by(parent_id=parent_sel.id)
        .order_by(Category.sort_order)
        .all()
        if parent_sel
        else []
    )

    q = _visible_profiles_query()
    if selected:
        cat_ids = [selected.id]
        if selected.parent_id:
            cat_ids.append(selected.parent_id)  # 세부 선택 시 대분류 보유 변호사도 매칭
        else:
            cat_ids += [c.id for c in children]
        q = q.filter(LawyerProfile.categories.any(Category.id.in_(cat_ids)))

    region = None
    if region_id:
        region = db.session.get(Region, region_id)
        if region is None:
            abort(404)
        q = q.filter(LawyerProfile.region_id == region_id)

    total = q.count()
    profiles = (
        q.order_by(LawyerProfile.view_count.desc())
        .offset((page - 1) * PER_PAGE)
        .limit(PER_PAGE)
        .all()
    )
    # 상위 2명은 AD LAWYERS 카드 (데모: 조회수 상위)
    ad_profiles = profiles[:2] if page == 1 else []
    plain_profiles = profiles[2:] if page == 1 else profiles

    # 맞춤 법률 정보: 관련 분야 published 해결사례 6개
    cases_q = LawyerPost.query.filter_by(type="case", status="published").filter(
        LawyerPost.deleted_at.is_(None)
    )
    if selected:
        cases_q = cases_q.filter(
            LawyerPost.category_id.in_(
                [selected.id] + ([selected.parent_id] if selected.parent_id else [])
            )
        )
    solve_cases = (
        cases_q.options(joinedload(LawyerPost.lawyer))
        .order_by(LawyerPost.published_at.desc())
        .limit(6)
        .all()
    )

    answer_counts = dict(
        db.session.query(
            ConsultationAnswer.lawyer_id, db.func.count(ConsultationAnswer.id)
        )
        .filter(
            ConsultationAnswer.lawyer_id.in_([p.user_id for p in profiles] or [0])
        )
        .group_by(ConsultationAnswer.lawyer_id)
        .all()
    )

    regions = Region.query.order_by(Region.sort_order).all()
    has_more = total > page * PER_PAGE
    return render_template(
        "lawyers/list.html",
        active_menu="lawyers",
        parents=parents,
        parent_sel=parent_sel,
        selected=selected,
        children=children,
        regions=regions,
        profiles=profiles,
        ad_profiles=ad_profiles,
        plain_profiles=plain_profiles,
        total=total,
        page=page,
        has_more=has_more,
        remaining=max(total - page * PER_PAGE, 0),
        category=selected,
        region=region,
        solve_cases=solve_cases,
        answer_counts=answer_counts,
        slugify=_slugify,
    )


@bp.route("/list")
def list_():
    """구 리스트 URL — 통합된 찾기 페이지로 리다이렉트 (기존 링크 호환)."""
    return redirect(url_for("lawyers.find", **request.args), code=301)


@bp.route("/<int:user_id>")
@bp.route("/<int:user_id>-<slug>")
def detail(user_id, slug=None):
    """3단계 — 프로필 페이지 (시안 lawyer-detail.html 1:1). URL 슬러그 포함 (§2-1)."""
    profile = (
        LawyerProfile.query.options(
            joinedload(LawyerProfile.user),
            joinedload(LawyerProfile.categories),
            joinedload(LawyerProfile.region),
        )
        .filter_by(user_id=user_id)
        .first()
    )
    if (
        profile is None
        or profile.user.status != "active"
        or profile.user.deleted_at is not None
        or not profile.is_visible
    ):
        abort(404)

    canonical_slug = _slugify(profile.user.name)
    if slug != canonical_slug:
        return redirect(
            url_for("lawyers.detail", user_id=user_id, slug=canonical_slug), code=301
        )

    # 상세 GET 시 views+1 (§7 규칙)
    profile.view_count = (profile.view_count or 0) + 1
    db.session.commit()

    solve_posts = (
        LawyerPost.query.filter_by(
            lawyer_id=user_id, type="case", status="published"
        )
        .filter(LawyerPost.deleted_at.is_(None))
        .order_by(LawyerPost.published_at.desc())
        .limit(5)
        .all()
    )
    solve_total = LawyerPost.query.filter_by(
        lawyer_id=user_id, type="case", status="published"
    ).filter(LawyerPost.deleted_at.is_(None)).count()
    answer_count = ConsultationAnswer.query.filter_by(lawyer_id=user_id).count()

    return render_template(
        "lawyers/detail.html",
        profile=profile,
        user=profile.user,
        solve_posts=solve_posts,
        solve_total=solve_total,
        answer_count=answer_count,
        canonical_slug=canonical_slug,
    )
