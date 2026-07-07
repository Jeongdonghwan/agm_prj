import re
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
from models import Category, Consultation, ConsultationAnswer, LawyerProfile, User
from routes.decorators import role_required
from utils import mask_privacy

bp = Blueprint("counsel", __name__, url_prefix="/counsel")

PER_PAGE = 10


def _slug(text: str) -> str:
    s = re.sub(r"[^\w가-힣-]", "", (text or "").replace(" ", "-"))
    return s[:40] or "consult"


def _active_lawyer_ranking(limit=3):
    """최근 30일 답변수 랭킹 (시안 우측 rank-box)."""
    since = datetime.now() - timedelta(days=30)
    rows = (
        db.session.query(
            ConsultationAnswer.lawyer_id, db.func.count(ConsultationAnswer.id).label("cnt")
        )
        .filter(ConsultationAnswer.created_at >= since, ConsultationAnswer.deleted_at.is_(None))
        .group_by(ConsultationAnswer.lawyer_id)
        .order_by(db.text("cnt DESC"))
        .limit(limit)
        .all()
    )
    profiles = {
        p.user_id: p
        for p in LawyerProfile.query.options(joinedload(LawyerProfile.user)).filter(
            LawyerProfile.user_id.in_([r[0] for r in rows] or [0])
        )
    }
    return [
        {"profile": profiles[lid], "count": cnt}
        for lid, cnt in rows
        if lid in profiles
    ]


@bp.route("/")
def list_():
    sort = request.args.get("sort", "recent_answer")
    page = max(request.args.get("page", 1, type=int), 1)

    q = (
        Consultation.query.filter_by(status="open", is_public=True)
        .filter(Consultation.deleted_at.is_(None))
        .options(joinedload(Consultation.category), joinedload(Consultation.answers))
    )
    if sort == "views":
        q = q.order_by(Consultation.views.desc())
    elif sort == "recent":
        q = q.order_by(Consultation.created_at.desc())
    else:  # 최신 답변순: 마지막 답변 시각 우선
        last_answer = (
            db.session.query(
                ConsultationAnswer.consultation_id,
                db.func.max(ConsultationAnswer.created_at).label("last_at"),
            )
            .filter(ConsultationAnswer.deleted_at.is_(None))
            .group_by(ConsultationAnswer.consultation_id)
            .subquery()
        )
        q = q.outerjoin(last_answer, Consultation.id == last_answer.c.consultation_id).order_by(
            db.func.coalesce(last_answer.c.last_at, Consultation.created_at).desc()
        )

    total = q.count()
    items = q.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()

    lawyer_names = {}
    lawyer_ids = {a.lawyer_id for c in items for a in c.answers}
    for u in User.query.filter(User.id.in_(lawyer_ids or [0])):
        lawyer_names[u.id] = u.name

    return render_template(
        "counsel/list.html",
        active_menu="counsel",
        items=items,
        total=total,
        page=page,
        has_next=total > page * PER_PAGE,
        sort=sort,
        lawyer_names=lawyer_names,
        ranking=_active_lawyer_ranking(),
        slug=_slug,
    )


@bp.route("/write", methods=["GET", "POST"])
@role_required("user", "admin")
def write():
    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            flash("제목과 내용을 입력해주세요.", "error")
        else:
            c = Consultation(
                user_id=g.user.id,
                category_id=request.form.get("category_id", type=int) or None,
                title=mask_privacy(title)[:200],
                content=mask_privacy(content),
                is_public=request.form.get("is_public", "1") == "1",
            )
            db.session.add(c)
            db.session.commit()
            flash("상담글이 등록되었습니다. 변호사 답변을 기다려주세요.", "success")
            return redirect(url_for("counsel.detail", consult_id=c.id))
    return render_template(
        "counsel/write.html", active_menu="counsel", parents=parents, consult=None
    )


@bp.route("/<int:consult_id>")
@bp.route("/<int:consult_id>-<slug>")
def detail(consult_id, slug=None):
    c = (
        Consultation.query.options(
            joinedload(Consultation.category), joinedload(Consultation.user)
        )
        .filter_by(id=consult_id)
        .filter(Consultation.deleted_at.is_(None))
        .first()
    )
    if c is None or c.status == "deleted":
        abort(404)
    is_owner = g.user and g.user.id == c.user_id
    is_staff = g.user and g.user.role in ("lawyer", "admin")
    if c.status == "hidden" and not (g.user and g.user.role == "admin"):
        abort(404)
    if not c.is_public and not (is_owner or is_staff):
        # 비공개 글: 작성자·변호사·관리자만 열람
        abort(403)

    canonical = _slug(c.title)
    if slug != canonical:
        return redirect(url_for("counsel.detail", consult_id=consult_id, slug=canonical), 301)

    c.views = (c.views or 0) + 1
    db.session.commit()

    answers = (
        ConsultationAnswer.query.filter_by(consultation_id=c.id)
        .filter(ConsultationAnswer.deleted_at.is_(None))
        .options(joinedload(ConsultationAnswer.lawyer))
        .order_by(ConsultationAnswer.created_at)
        .all()
    )
    profiles = {
        p.user_id: p
        for p in LawyerProfile.query.filter(
            LawyerProfile.user_id.in_([a.lawyer_id for a in answers] or [0])
        )
    }
    return render_template(
        "counsel/detail.html",
        active_menu="counsel",
        consult=c,
        answers=answers,
        profiles=profiles,
        is_owner=is_owner,
        can_edit=is_owner and not answers,  # 답변 전까지만 수정/삭제 (§4-2)
        ranking=_active_lawyer_ranking(),
        canonical_slug=canonical,
    )


@bp.route("/<int:consult_id>/edit", methods=["GET", "POST"])
@role_required("user", "admin")
def edit(consult_id):
    c = Consultation.query.filter_by(id=consult_id, user_id=g.user.id).filter(
        Consultation.deleted_at.is_(None)
    ).first()
    if c is None:
        abort(404)
    if ConsultationAnswer.query.filter_by(consultation_id=c.id).filter(
        ConsultationAnswer.deleted_at.is_(None)
    ).count():
        flash("답변이 달린 상담글은 수정할 수 없습니다.", "error")
        return redirect(url_for("counsel.detail", consult_id=c.id))
    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            flash("제목과 내용을 입력해주세요.", "error")
        else:
            c.title = mask_privacy(title)[:200]
            c.content = mask_privacy(content)
            c.category_id = request.form.get("category_id", type=int) or None
            c.is_public = request.form.get("is_public", "1") == "1"
            db.session.commit()
            flash("상담글이 수정되었습니다.", "success")
            return redirect(url_for("counsel.detail", consult_id=c.id))
    return render_template(
        "counsel/write.html", active_menu="counsel", parents=parents, consult=c
    )


@bp.route("/<int:consult_id>/delete", methods=["POST"])
@role_required("user", "admin")
def delete(consult_id):
    c = Consultation.query.filter_by(id=consult_id, user_id=g.user.id).first()
    if c is None:
        abort(404)
    if ConsultationAnswer.query.filter_by(consultation_id=c.id).filter(
        ConsultationAnswer.deleted_at.is_(None)
    ).count():
        flash("답변이 달린 상담글은 삭제할 수 없습니다.", "error")
        return redirect(url_for("counsel.detail", consult_id=c.id))
    c.status = "deleted"
    c.deleted_at = datetime.now()
    db.session.commit()
    flash("상담글이 삭제되었습니다.", "success")
    return redirect(url_for("counsel.list_"))
