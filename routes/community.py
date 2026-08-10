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
    url_for,
)
from sqlalchemy.orm import joinedload

from extensions import db
from models import CommunityBoard, CommunityComment, CommunityPost
from models.community import community_likes
from routes.decorators import community_member_required, role_required
from utils import mask_privacy

bp = Blueprint("community", __name__, url_prefix="/community")

PER_PAGE = 15

# 커뮤니티 카테고리 (전체 = 아래 카테고리 합침) — 칩 줄 기본 3종은 코드 고정
COMMUNITY_CATS = ["자유게시판", "옥바라지 이야기", "사연신청"]
_FIXED_BOARDS = {
    "free": {"label": "자유게시판", "topics": [], "admin_only": False},
    "care": {"label": "옥바라지 이야기", "topics": [], "admin_only": False},
    "story": {"label": "사연신청", "topics": [], "admin_only": False},
}

# 칩 줄에 항상 노출하는 정보 게시판 slug
INFO_BOARD_SLUGS = ("facility", "life", "forms")


# ── 게시판 트리는 DB(community_boards)가 원본 — 어드민 [게시판 관리]에서 편집 ──
def _board_data():
    """DB 트리 → (메가메뉴, slug→게시판 dict). 요청당 1회 로드."""
    if not hasattr(g, "_board_data"):
        menu, page_boards = [], {}
        groups = (
            CommunityBoard.query.filter_by(parent_id=None, is_active=True)
            .options(joinedload(CommunityBoard.children))
            .order_by(CommunityBoard.sort_order, CommunityBoard.id)
            .all()
        )
        for grp in groups:
            items = []
            for it in grp.children:
                if not it.is_active:
                    continue
                if it.link_url:
                    items.append({
                        "label": it.label,
                        "url": it.link_url,
                        "external": it.link_url.startswith("http"),
                    })
                elif it.slug:
                    b = {
                        "label": it.label,
                        "topics": list(it.topics or []),
                        "admin_only": bool(it.admin_only),
                    }
                    page_boards[it.slug] = b
                    items.append({
                        "board": it.slug, **b,
                        # 메뉴에서 세부 주제 펼침은 게시판별 옵션 (페이지의 주제 칩과 무관)
                        "topics": b["topics"] if it.show_topics else [],
                    })
            if items:
                menu.append({"label": grp.label, "items": items})
        g._board_data = (menu, page_boards)
    return g._board_data


def get_menu():
    """GNB 메가메뉴 구조."""
    return _board_data()[0]


def get_page_boards():
    """/community/board/<slug> 페이지를 갖는 게시판 전체."""
    return _board_data()[1]


def get_info_boards():
    """커뮤니티 칩 줄에 상시 노출하는 정보 게시판(교정시설/수용생활/양식)."""
    boards = get_page_boards()
    return {k: boards[k] for k in INFO_BOARD_SLUGS if k in boards}


def get_boards():
    """글쓰기 폼용 전체 보드 (고정 카테고리 3종 + DB 게시판)."""
    return {**_FIXED_BOARDS, **get_page_boards()}


def get_category_map():
    """토픽/보드 라벨 → 보드 키 역매핑 (post.category에는 토픽명 또는 보드 라벨 저장)."""
    m = {}
    for key, b in get_boards().items():
        m[b["label"]] = key
        for t in b["topics"]:
            m[t] = key
    return m

# 첨부파일 허용 확장자 (양식/이미지 위주)
ATTACH_EXTENSIONS = {"pdf", "hwp", "hwpx", "doc", "docx", "xls", "xlsx", "txt", "jpg", "jpeg", "png", "zip"}
MAX_ATTACHMENTS = 5


# 본문 이미지 토큰: [img]/uploads/community/…[/img] — 에디터가 삽입, 렌더 시 <img> 치환
_BODY_IMG_RE = re.compile(r"\[img\](.*?)\[/img\]", re.S)
BODY_IMG_PREFIX = "/uploads/community/"


def _clean_body(text: str) -> str:
    """본문 이미지 토큰 검증 — 내부 업로드 경로가 아닌 토큰은 제거(외부 이미지 차단)."""
    def _keep(m):
        url = m.group(1).strip()
        if url.startswith(BODY_IMG_PREFIX) and re.fullmatch(r"[\w/.\-]+", url):
            return f"[img]{url}[/img]"
        return ""
    return _BODY_IMG_RE.sub(_keep, text or "")


def _save_attachments(files, limit=None):
    """첨부파일 저장 → [{name, url}] 반환. 허용 외 확장자는 (None, 에러메시지)."""
    saved = []
    if limit is None:
        limit = MAX_ATTACHMENTS
    for f in files[:max(limit, 0)]:
        if not f or not f.filename:
            continue
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in ATTACH_EXTENSIONS:
            return None, f"첨부할 수 없는 파일 형식입니다: {f.filename}"
        d = os.path.join(current_app.config["UPLOAD_FOLDER"], "community", str(g.user.id))
        os.makedirs(d, exist_ok=True)
        fname = f"{uuid.uuid4().hex}.{ext}"
        f.save(os.path.join(d, fname))
        saved.append(
            {
                "name": f.filename[:120],
                "url": url_for("main.uploads", filename=f"community/{g.user.id}/{fname}"),
            }
        )
    return saved, None

def writable_boards(user):
    """글쓰기 폼에 띄울 게시판 — 공지·FAQ류는 관리자에게만."""
    boards = get_boards()
    if user is not None and user.role == "admin":
        return boards
    return {k: b for k, b in boards.items() if not b.get("admin_only")}


def writable_board_groups(user):
    """글쓰기 폼 게시판 선택용 — [(그룹 라벨, [(key, board), …])] (optgroup 렌더)."""
    allowed = writable_boards(user)
    groups = [["커뮤니티", [(k, allowed[k]) for k in _FIXED_BOARDS if k in allowed]]]
    used = set(_FIXED_BOARDS)
    for grp in get_menu():
        items = []
        for it in grp["items"]:
            if "board" in it and it["board"] in allowed:
                items.append((it["board"], allowed[it["board"]]))
                used.add(it["board"])
        if items:
            groups.append([grp["label"], items])
    # 메뉴 그룹에 묶이지 않은 게시판 — 같은 라벨 그룹에 붙이거나 새 그룹으로
    for key, b in allowed.items():
        if key in used:
            continue
        for grp in groups:
            if grp[0] == b["label"]:
                grp[1].insert(0, (key, b))
                break
        else:
            groups.append([b["label"], [(key, b)]])
    return groups


def _admin_only_category(category):
    """해당 카테고리가 관리자 전용 게시판에 속하는지."""
    b = get_boards().get(get_category_map().get(category, ""))
    return bool(b and b.get("admin_only"))


def author_name(obj):
    """익명 글은 어디서도 닉네임 미노출 (§11)."""
    if obj.is_anonymous:
        return "익명"
    return obj.user.display_name if obj.user else "탈퇴회원"


def first_image(post):
    """첨부 또는 본문 첫 이미지 URL — 목록 우측 미리보기용."""
    for a in post.attachments or []:
        if (a.get("url") or "").lower().endswith((".jpg", ".jpeg", ".png")):
            return a["url"]
    m = _BODY_IMG_RE.search(post.content or "")
    if m and m.group(1).startswith(BODY_IMG_PREFIX):
        return m.group(1)
    return None


@bp.route("/locked")
def locked():
    """커뮤니티 인증 안내 — 미승인 회원의 랜딩. 접견예약확인 제출 폼 포함."""
    if g.user is None:
        return redirect(url_for("auth.login", next="/community/"))
    if g.user.community_approved:
        return redirect(url_for("community.list_"))
    return render_template(
        "community/locked.html",
        active_menu="community",
        moj_url=MOJ_VISIT_URL,
    )


# 법무부 온라인민원 — 접견예약 (가입/인증 안내에 공통 사용)
MOJ_VISIT_URL = (
    "https://minwon.moj.go.kr/minwon/1999/subview.do"
    "?enc=Zm5jdDF8QEB8JTJGcHJpc29uUmVzZXJ2YXRpb24lMkZtaW53b24lMkY2JTJGYXJ0Y2xTdGVwMS5kbyUzRg%3D%3D"
)


@bp.route("/menu")
@community_member_required
def menu():
    """전체 게시판 메뉴 — 모바일에서 GNB 커뮤니티의 랜딩.

    상단에 최신 전체 글 미리보기(화면 1/3가량) + 아래 게시판 목록(카페 스타일).
    """
    recent = (
        CommunityPost.query.filter_by(status="open", is_notice=False)
        .filter(CommunityPost.deleted_at.is_(None))
        .options(joinedload(CommunityPost.user), joinedload(CommunityPost.comments))
        .order_by(CommunityPost.created_at.desc())
        .limit(4)
        .all()
    )
    return render_template(
        "community/menu.html",
        active_menu="community",
        categories=COMMUNITY_CATS,
        recent=recent,
        author_name=author_name,
    )


@bp.route("/")
@community_member_required
def list_():
    """커뮤니티 — 전체(자유게시판+옥바라지 이야기) / 카테고리 칩."""
    category = request.args.get("category")
    if category not in COMMUNITY_CATS:
        category = None
    # 칩은 한 축 — 카테고리를 고르면 정렬은 최신으로 되돌려 '인기'와 동시 선택되지 않게 한다
    sort = "recent" if category else request.args.get("sort", "recent")
    page = max(request.args.get("page", 1, type=int), 1)

    q = CommunityPost.query.filter_by(status="open", is_notice=False).filter(
        CommunityPost.deleted_at.is_(None)
    ).options(joinedload(CommunityPost.user), joinedload(CommunityPost.comments))
    if category:
        q = q.filter_by(category=category)
    else:
        q = q.filter(CommunityPost.category.in_(COMMUNITY_CATS))

    if sort == "popular":
        q = q.order_by((CommunityPost.views + CommunityPost.likes * 3).desc())
    else:
        q = q.order_by(CommunityPost.created_at.desc())

    total = q.count()
    items = q.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()

    # 커뮤니티 메인 공지 = category '공지'(전체 대상)만. 게시판 지정 공지는 그 게시판에서.
    notices = (
        CommunityPost.query.filter_by(status="open", is_notice=True, category="공지")
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
        categories=COMMUNITY_CATS,
        category=category,
        info_boards=get_info_boards(),
        topic=None,
        sort=sort,
        view_label=category or ("인기 글" if sort == "popular" else "전체"),
        author_name=author_name,
        first_image=first_image,
    )


@bp.route("/board/<key>")
@community_member_required
def board(key):
    """게시판 페이지 — 정보 게시판 3종 + 메가메뉴로 추가된 게시판들."""
    boards = get_page_boards()
    if key not in boards:
        abort(404)
    b = boards[key]
    topic = request.args.get("topic")
    if topic not in b["topics"]:
        topic = None
    sort = request.args.get("sort", "recent")
    page = max(request.args.get("page", 1, type=int), 1)

    q = CommunityPost.query.filter_by(status="open", is_notice=False).filter(
        CommunityPost.deleted_at.is_(None)
    ).options(joinedload(CommunityPost.user), joinedload(CommunityPost.comments))
    # 세부 주제가 없는 게시판은 글의 category에 보드 라벨이 그대로 저장된다
    if topic:
        q = q.filter_by(category=topic)
    else:
        q = q.filter(CommunityPost.category.in_(b["topics"] or [b["label"]]))
    if sort == "popular":
        q = q.order_by((CommunityPost.views + CommunityPost.likes * 3).desc())
    else:
        q = q.order_by(CommunityPost.created_at.desc())

    total = q.count()
    items = q.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()

    # 이 게시판을 대상으로 등록된 공지 (어드민 커뮤니티 관리)
    notices = (
        CommunityPost.query.filter_by(status="open", is_notice=True, category=b["label"])
        .filter(CommunityPost.deleted_at.is_(None))
        .order_by(CommunityPost.created_at.desc())
        .limit(3)
        .all()
    )
    return render_template(
        "community/board.html",
        active_menu="community",  # 정보 게시판도 커뮤니티 메뉴 안에 속한다
        notices=notices,
        board_key=key,
        board=b,
        categories=COMMUNITY_CATS,
        category=None,
        info_boards=get_info_boards(),
        topic=topic,
        sort=sort,
        view_label=topic or b["label"],
        items=items,
        total=total,
        page=page,
        has_next=total > page * PER_PAGE,
        author_name=author_name,
        first_image=first_image,
    )


def _require_nickname():
    """닉네임 미설정 시 설정 모달을 띄우도록 신호 (§4-2)."""
    return g.user.role == "user" and not g.user.nickname


@bp.route("/write", methods=["GET", "POST"])
@role_required("user", "admin")
@community_member_required
def write():
    nickname_required = _require_nickname()
    boards = writable_boards(g.user)
    default_board = request.args.get("board") if request.args.get("board") in boards else "free"
    if request.method == "POST":
        if _require_nickname():
            flash("커뮤니티 이용을 위해 닉네임을 먼저 설정해주세요.", "error")
            return render_template(
                "community/write.html",
                active_menu="community",
                boards=boards,
                board_groups=writable_board_groups(g.user),
                default_board=default_board,
                nickname_required=True,
                form=request.form,
                post=None,
            )
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        category = request.form.get("category")  # 토픽명 또는 보드 라벨
        if _admin_only_category(category) and g.user.role != "admin":
            flash("공지·FAQ 게시판은 관리자만 작성할 수 있습니다.", "error")
        elif not title or not content or category not in get_category_map():
            flash("게시판/제목/내용을 확인해주세요.", "error")
        else:
            attachments, err = _save_attachments(request.files.getlist("attachments"))
            if err:
                flash(err, "error")
            else:
                p = CommunityPost(
                    user_id=g.user.id,
                    category=category,
                    title=mask_privacy(title)[:200],
                    content=_clean_body(mask_privacy(content)),
                    is_anonymous=request.form.get("is_anonymous") == "1",
                    is_notice=False,
                    attachments=attachments or None,
                )
                db.session.add(p)
                db.session.commit()
                flash("글이 등록되었습니다.", "success")
                return redirect(url_for("community.detail", post_id=p.id))
    return render_template(
        "community/write.html",
        active_menu="community",
        boards=boards,
        board_groups=writable_board_groups(g.user),
        default_board=default_board,
        nickname_required=nickname_required,
        form=request.form,
        post=None,
    )


@bp.route("/<int:post_id>/edit", methods=["GET", "POST"])
@role_required("user", "admin")
@community_member_required
def edit(post_id):
    """내 글 수정 — 작성자 본인만, 언제든 가능."""
    p = CommunityPost.query.filter_by(id=post_id, user_id=g.user.id, status="open").filter(
        CommunityPost.deleted_at.is_(None)
    ).first()
    if p is None:
        abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        category = request.form.get("category")
        if _admin_only_category(category) and g.user.role != "admin":
            flash("공지·FAQ 게시판은 관리자만 작성할 수 있습니다.", "error")
        elif not title or not content or category not in get_category_map():
            flash("게시판/제목/내용을 확인해주세요.", "error")
        else:
            removed = set(request.form.getlist("remove_attachments"))
            kept = [a for a in (p.attachments or []) if a.get("url") not in removed]
            new_atts, err = _save_attachments(
                request.files.getlist("attachments"), limit=MAX_ATTACHMENTS - len(kept)
            )
            if err:
                flash(err, "error")
            else:
                p.category = category
                p.title = mask_privacy(title)[:200]
                p.content = _clean_body(mask_privacy(content))
                p.is_anonymous = request.form.get("is_anonymous") == "1"
                p.attachments = (kept + (new_atts or [])) or None
                db.session.commit()
                flash("글이 수정되었습니다.", "success")
                return redirect(url_for("community.detail", post_id=p.id))
    return render_template(
        "community/write.html",
        active_menu="community",
        boards=writable_boards(g.user),
        board_groups=writable_board_groups(g.user),
        default_board=get_category_map().get(p.category, "free"),
        nickname_required=False,
        form=request.form,
        post=p,
    )


@bp.route("/<int:post_id>/delete", methods=["POST"])
@role_required("user", "admin")
@community_member_required
def delete(post_id):
    """내 글 삭제 — soft delete (§11)."""
    p = CommunityPost.query.filter_by(id=post_id, user_id=g.user.id).filter(
        CommunityPost.deleted_at.is_(None)
    ).first()
    if p is None:
        abort(404)
    p.status = "deleted"
    p.deleted_at = datetime.now()
    db.session.commit()
    flash("글이 삭제되었습니다.", "success")
    return redirect(url_for("community.list_"))


@bp.route("/upload-image", methods=["POST"])
@role_required("user", "admin")
@community_member_required
def upload_image():
    """본문 에디터 이미지 업로드 — 저장 후 공개 URL 반환."""
    f = request.files.get("image")
    if not f or not f.filename:
        return {"error": {"code": "MISSING_FILE", "message": "이미지 파일이 없습니다."}}, 400
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ("jpg", "jpeg", "png"):
        return {"error": {"code": "INVALID_TYPE", "message": "jpg, jpeg, png만 업로드할 수 있습니다."}}, 400
    d = os.path.join(current_app.config["UPLOAD_FOLDER"], "community", str(g.user.id))
    os.makedirs(d, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    f.save(os.path.join(d, fname))
    return {"ok": True, "url": url_for("main.uploads", filename=f"community/{g.user.id}/{fname}")}


@bp.route("/<int:post_id>")
@community_member_required
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
    is_owner = bool(g.user and g.user.id == p.user_id and not p.is_notice)
    return render_template(
        "community/detail.html",
        active_menu="community",
        post=p,
        comments=comments,
        replies=replies,
        liked=liked,
        can_write=can_write,
        is_owner=is_owner,
        nickname_required=bool(g.user and _require_nickname()),
        author_name=author_name,
        first_image=first_image,
    )


@bp.route("/<int:post_id>/comments", methods=["POST"])
@role_required("user", "admin")
@community_member_required
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
