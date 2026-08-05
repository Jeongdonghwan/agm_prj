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
from models import CommunityComment, CommunityPost
from models.community import community_likes
from routes.decorators import role_required
from utils import mask_privacy

bp = Blueprint("community", __name__, url_prefix="/community")

PER_PAGE = 15

# 정보 게시판 3종 — GNB 별도 메뉴 (/community/board/<key>)
INFO_BOARDS = {
    "facility": {
        "label": "교정시설 정보",
        "topics": ["접견 가능 시간", "영치금 계좌", "우편 주소", "택배 가능 여부", "자주 묻는 질문"],
    },
    "life": {
        "label": "수용생활 정보",
        "topics": ["초범 가족 안내", "이감 절차", "영치품", "교도소 생활", "출소 절차", "교정기관 식단표"],
    },
    "forms": {
        "label": "양식 자료실",
        "topics": [
            "탄원서", "반성문", "합의서", "서류 모음",
            # 아래는 운영 요청으로 추가된 세부 주제
            "다운로드 자료실", "고소취하서", "영장실질심사의견서", "구속적부심사청구서",
            "보석허가청구서", "항소이유서·답변서", "형사소송 주요판례", "책자발송신청게시판",
        ],
    },
}

# ── GNB '커뮤니티' 메가메뉴 = 게시판 구성의 단일 진실 공급원 ──────────────
# 항목 3종:
#   {"board": key, ...}   새 게시판 (/community/board/<key> 페이지 생성)
#   {"topic_of": key}     기존 게시판의 세부 주제로 링크 (중복 게시판을 만들지 않음)
#   {"url": "https://…"}  외부 사이트 (새 탭)
COMMUNITY_MENU = [
    {"label": "안내", "items": [
        {"board": "ad-inquiry", "label": "광고 및 협업 문의"},
        {"board": "notice-angimo", "label": "안기모 공지사항", "admin_only": True},
        {"board": "notice-community", "label": "커뮤니티 공지사항", "admin_only": True},
    ]},
    {"label": "상담소", "items": [
        {"board": "parole", "label": "가석방관련 상담신청"},
    ]},
    {"label": "커뮤니티", "items": [
        {"board": "suggest", "label": "커뮤니티 건의사항"},
        {"board": "letter", "label": "편지발송 인터넷 서신"},
        {"board": "faq", "label": "자주 묻는 질문 FAQ", "admin_only": True},
        {"board": "ask", "label": "아뭇따 질문!"},
        {"board": "trial-qna", "label": "형사재판 절차 QnA"},
        {"board": "prison-qna", "label": "교정기관생활 QnA"},
        {"board": "cheer", "label": "위로 칭찬 격려 축하 해주세요"},
        {"board": "market", "label": "안기모 중고세상"},
        {"board": "envelope", "label": "나의 대봉투 꾸미기"},
        {"topic_of": "life", "label": "교정기관 식단표"},
    ]},
    {"label": "양식 자료실", "items": [
        {"topic_of": "forms", "label": "다운로드 자료실"},
        {"topic_of": "forms", "label": "고소취하서"},
        {"topic_of": "forms", "label": "영장실질심사의견서"},
        {"topic_of": "forms", "label": "구속적부심사청구서"},
        {"topic_of": "forms", "label": "보석허가청구서"},
        {"topic_of": "forms", "label": "항소이유서·답변서"},
        {"topic_of": "forms", "label": "형사소송 주요판례"},
        {"topic_of": "forms", "label": "책자발송신청게시판"},
    ]},
    {"label": "교정시설 정보", "items": [
        {"board": "facility", "label": "교정시설 정보"},   # 기존 게시판 (정의는 INFO_BOARDS가 우선)
        {"board": "life", "label": "수용생활 정보"},       # 기존 게시판
        {"board": "prison", "label": "교정기관별 게시판", "topics": [
            "서울,남부교&구,동부", "수원,안양,평택지소", "여주,화성,소망,인천",
            "강원북부,강릉,춘천", "의정부,영월,원주", "대구,상주,경주,포항",
            "경북북부제123.김천", "경북직훈,안동,울산", "부산교&구,통영,거창",
            "창원,진주,밀양,정읍", "대전,논산,공주,충주", "천안,청주,홍성,서산",
            "광주,전주,군산,제주", "목포,순천,장흥,해남",
        ]},
    ]},
    {"label": "단계별 소통게시판", "items": [
        {"board": "stage", "label": "단계별 소통게시판", "topics": [
            "체포·유치장·구속단계", "경찰·검찰수사중단계", "기소후 1심재판 단계",
            "1심 판결선고후 단계", "항소·상고진행중단계", "재판종료·형확정단계",
        ]},
    ]},
    {"label": "공지사항", "items": [
        {"board": "petition", "label": "징계청원 게시판"},
    ]},
    {"label": "도움되는 사이트", "items": [
        {"url": "https://www.moj.go.kr/corrections/1125/subview.do", "label": "전국 교정기관 주소"},
        {"url": "https://www.scourt.go.kr/portal/information/events/search/search.jsp", "label": "대법원 나의사건검색"},
        {"url": "https://www.kics.go.kr/", "label": "KICS 형사사법포털"},
        {"url": "https://sc.scourt.go.kr/sc/krsc/criterion/down/standard_down.jsp", "label": "양형기준 양형위원회"},
        {"url": "https://koreha.or.kr/", "label": "출소자 법무보호사업"},
    ]},
]

# 메뉴에서 새 게시판을 뽑는다 — 기존 INFO_BOARDS 키는 그 정의(세부 주제)를 그대로 쓴다
MENU_BOARDS = {
    it["board"]: {
        "label": it["label"],
        "topics": it.get("topics", []),
        "admin_only": it.get("admin_only", False),
    }
    for grp in COMMUNITY_MENU for it in grp["items"]
    if "board" in it and it["board"] not in INFO_BOARDS
}
# /community/board/<key> 페이지를 갖는 게시판 전체
PAGE_BOARDS = {**INFO_BOARDS, **MENU_BOARDS}

# 커뮤니티 카테고리 (전체 = 아래 카테고리 합침)
COMMUNITY_CATS = ["자유게시판", "옥바라지 이야기", "사연신청"]

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

# 글쓰기 폼용 전체 보드 (커뮤니티 카테고리 3종 + 페이지를 가진 게시판 전체)
BOARDS = {
    "free": {"label": "자유게시판", "topics": []},
    "care": {"label": "옥바라지 이야기", "topics": []},
    "story": {"label": "사연신청", "topics": []},
    **PAGE_BOARDS,
}

# 토픽/보드 라벨 → 보드 키 역매핑 (post.category에는 토픽명 또는 보드 라벨 저장)
CATEGORY_TO_BOARD = {}
for _key, _b in BOARDS.items():
    CATEGORY_TO_BOARD[_b["label"]] = _key
    for _t in _b["topics"]:
        CATEGORY_TO_BOARD[_t] = _key


def writable_boards(user):
    """글쓰기 폼에 띄울 게시판 — 공지·FAQ류는 관리자에게만."""
    if user is not None and user.role == "admin":
        return BOARDS
    return {k: b for k, b in BOARDS.items() if not b.get("admin_only")}


def writable_board_groups(user):
    """글쓰기 폼 게시판 선택용 — [(그룹 라벨, [(key, board), …])] (optgroup 렌더)."""
    allowed = writable_boards(user)
    groups = [["커뮤니티", [(k, BOARDS[k]) for k in ("free", "care", "story") if k in allowed]]]
    used = {"free", "care", "story"}
    for grp in COMMUNITY_MENU:
        items = []
        for it in grp["items"]:
            if "board" in it and it["board"] in allowed:
                items.append((it["board"], PAGE_BOARDS[it["board"]]))
                used.add(it["board"])
        if items:
            groups.append([grp["label"], items])
    # 메뉴에 board 항목으로 없는 게시판(예: 양식 자료실은 토픽 링크만) — 같은 라벨 그룹에 붙인다
    for key in allowed:
        if key in used:
            continue
        b = BOARDS[key]
        for grp in groups:
            if grp[0] == b["label"]:
                grp[1].insert(0, (key, b))
                break
        else:
            groups.append([b["label"], [(key, b)]])
    return groups


def _admin_only_category(category):
    """해당 카테고리가 관리자 전용 게시판에 속하는지."""
    b = BOARDS.get(CATEGORY_TO_BOARD.get(category, ""))
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


@bp.route("/")
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
        categories=COMMUNITY_CATS,
        category=category,
        info_boards=INFO_BOARDS,
        topic=None,
        sort=sort,
        view_label=category or ("인기 글" if sort == "popular" else "전체"),
        author_name=author_name,
        first_image=first_image,
    )


@bp.route("/board/<key>")
def board(key):
    """게시판 페이지 — 정보 게시판 3종 + 메가메뉴로 추가된 게시판들."""
    if key not in PAGE_BOARDS:
        abort(404)
    b = PAGE_BOARDS[key]
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
    return render_template(
        "community/board.html",
        active_menu="community",  # 정보 게시판도 커뮤니티 메뉴 안에 속한다
        board_key=key,
        board=b,
        categories=COMMUNITY_CATS,
        category=None,
        info_boards=INFO_BOARDS,
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
        elif not title or not content or category not in CATEGORY_TO_BOARD:
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
        elif not title or not content or category not in CATEGORY_TO_BOARD:
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
        default_board=CATEGORY_TO_BOARD.get(p.category, "free"),
        nickname_required=False,
        form=request.form,
        post=p,
    )


@bp.route("/<int:post_id>/delete", methods=["POST"])
@role_required("user", "admin")
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
