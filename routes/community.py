from datetime import datetime, timedelta

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy.orm import joinedload

from extensions import db
from models import CommunityComment, CommunityPost
from models.community import community_likes
from routes.decorators import role_required
from utils import mask_privacy

bp = Blueprint("community", __name__, url_prefix="/community")

PER_PAGE = 15

# 커뮤니티 카테고리 (관리자 카테고리 관리 전 기본셋 — 시안 칩 기준)
CATEGORIES = ["생활법률", "이혼/가사", "부동산", "형사", "금전/계약", "회사/노동", "교통", "자유"]


def author_name(obj):
    """익명 글은 어디서도 닉네임 미노출 (§11)."""
    if obj.is_anonymous:
        return "익명"
    return obj.user.display_name if obj.user else "탈퇴회원"


def _hot_top5():
    """인기 TOP5: 최근 24h 우선(조회+추천×3), 부족하면 전체에서 보충."""
    score = CommunityPost.views + CommunityPost.likes * 3
    base = CommunityPost.query.filter_by(status="open", is_notice=False).filter(
        CommunityPost.deleted_at.is_(None)
    )
    since = datetime.now() - timedelta(hours=24)
    recent = base.filter(CommunityPost.created_at >= since).order_by(score.desc()).limit(5).all()
    if len(recent) < 5:
        seen = {p.id for p in recent}
        for p in base.order_by(score.desc()).limit(10):
            if p.id not in seen:
                recent.append(p)
                seen.add(p.id)
            if len(recent) == 5:
                break
    return recent


@bp.route("/")
def list_():
    category = request.args.get("category")
    sort = request.args.get("sort", "recent")
    page = max(request.args.get("page", 1, type=int), 1)

    q = CommunityPost.query.filter_by(status="open", is_notice=False).filter(
        CommunityPost.deleted_at.is_(None)
    ).options(joinedload(CommunityPost.user), joinedload(CommunityPost.comments))
    if category in CATEGORIES:
        q = q.filter_by(category=category)
    if sort == "popular":
        q = q.order_by((CommunityPost.views + CommunityPost.likes * 3).desc())
    else:
        q = q.order_by(CommunityPost.created_at.desc())

    total = q.count()
    items = q.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()

    notices = (
        CommunityPost.query.filter_by(status="open", is_notice=True)
        .filter(CommunityPost.deleted_at.is_(None))
        .order_by(CommunityPost.created_at.desc())
        .limit(3)
        .all()
    )
    return render_template(
        "community/list.html",
        active_menu="community",
        items=items,
        notices=notices,
        total=total,
        page=page,
        has_next=total > page * PER_PAGE,
        categories=CATEGORIES,
        category=category,
        sort=sort,
        hot_posts=_hot_top5(),
        author_name=author_name,
    )


def _require_nickname():
    """닉네임 미설정 시 설정 모달을 띄우도록 신호 (§4-2)."""
    return g.user.role == "user" and not g.user.nickname


@bp.route("/write", methods=["GET", "POST"])
@role_required("user", "admin")
def write():
    nickname_required = _require_nickname()
    if request.method == "POST":
        if _require_nickname():
            flash("커뮤니티 이용을 위해 닉네임을 먼저 설정해주세요.", "error")
            return render_template(
                "community/write.html",
                active_menu="community",
                categories=CATEGORIES,
                nickname_required=True,
                form=request.form,
            )
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        category = request.form.get("category")
        if not title or not content or category not in CATEGORIES:
            flash("카테고리/제목/내용을 확인해주세요.", "error")
        else:
            p = CommunityPost(
                user_id=g.user.id,
                category=category,
                title=mask_privacy(title)[:200],
                content=mask_privacy(content),
                is_anonymous=request.form.get("is_anonymous") == "1",
                is_notice=False,
            )
            db.session.add(p)
            db.session.commit()
            flash("글이 등록되었습니다.", "success")
            return redirect(url_for("community.detail", post_id=p.id))
    return render_template(
        "community/write.html",
        active_menu="community",
        categories=CATEGORIES,
        nickname_required=nickname_required,
        form=request.form,
    )


@bp.route("/<int:post_id>")
def detail(post_id):
    p = (
        CommunityPost.query.options(joinedload(CommunityPost.user))
        .filter_by(id=post_id)
        .filter(CommunityPost.deleted_at.is_(None))
        .first()
    )
    if p is None or p.status == "deleted":
        abort(404)
    if p.status == "hidden" and not (g.user and g.user.role == "admin"):
        abort(404)

    p.views = (p.views or 0) + 1
    db.session.commit()

    comments = (
        CommunityComment.query.filter_by(post_id=p.id, parent_id=None)
        .filter(CommunityComment.deleted_at.is_(None))
        .options(joinedload(CommunityComment.user))
        .order_by(CommunityComment.created_at)
        .all()
    )
    replies = {}
    for r in (
        CommunityComment.query.filter(
            CommunityComment.post_id == p.id, CommunityComment.parent_id.isnot(None)
        )
        .filter(CommunityComment.deleted_at.is_(None))
        .options(joinedload(CommunityComment.user))
        .order_by(CommunityComment.created_at)
    ):
        replies.setdefault(r.parent_id, []).append(r)

    liked = False
    if g.user:
        liked = bool(
            db.session.execute(
                community_likes.select().where(
                    community_likes.c.post_id == p.id,
                    community_likes.c.user_id == g.user.id,
                )
            ).first()
        )
    can_write = g.user and g.user.role in ("user", "admin")
    return render_template(
        "community/detail.html",
        active_menu="community",
        post=p,
        comments=comments,
        replies=replies,
        liked=liked,
        can_write=can_write,
        nickname_required=bool(g.user and _require_nickname()),
        author_name=author_name,
    )


@bp.route("/<int:post_id>/comments", methods=["POST"])
@role_required("user", "admin")
def comment(post_id):
    p = CommunityPost.query.filter_by(id=post_id, status="open").filter(
        CommunityPost.deleted_at.is_(None)
    ).first()
    if p is None:
        abort(404)
    if _require_nickname():
        flash("커뮤니티 이용을 위해 닉네임을 먼저 설정해주세요.", "error")
        return redirect(url_for("community.detail", post_id=post_id))
    content = request.form.get("content", "").strip()
    if not content:
        flash("댓글 내용을 입력해주세요.", "error")
        return redirect(url_for("community.detail", post_id=post_id))
    parent_id = request.form.get("parent_id", type=int) or None
    if parent_id:
        parent = CommunityComment.query.filter_by(id=parent_id, post_id=post_id).first()
        if parent is None or parent.parent_id:  # 대댓글까지만 (1-depth)
            abort(400)
    db.session.add(
        CommunityComment(
            post_id=post_id,
            user_id=g.user.id,
            parent_id=parent_id,
            content=mask_privacy(content),
            is_anonymous=request.form.get("is_anonymous") == "1",
        )
    )
    db.session.commit()
    flash("댓글이 등록되었습니다.", "success")
    return redirect(url_for("community.detail", post_id=post_id))
