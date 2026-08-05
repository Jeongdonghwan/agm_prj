import os
import re

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    redirect,
    render_template,
    send_from_directory,
    url_for,
)

from services import get_home_data
from utils import cached_page

bp = Blueprint("main", __name__)


def _slug(text: str) -> str:
    s = re.sub(r"[^\w가-힣-]", "", (text or "").replace(" ", "-"))
    return s[:40] or "item"


@bp.route("/")
@cached_page(60)  # 비로그인 응답만 60초 캐시 (§2-2 — 로그인 헤더 분기 보존)
def index():
    """메인 — 네이비 히어로 + 커뮤니티 사이드 배너 + 서비스 카드(구 디자인 B안)."""
    return render_template(
        "main/index_b.html", active_menu="home", design="b", **get_home_data()
    )


@bp.route("/main-b")
def index_b():
    """구 B안 주소 — 이제 메인이므로 / 로 보낸다."""
    return redirect(url_for("main.index"), 301)


@bp.route("/main-a")
@cached_page(60)
def index_a():
    """구 디자인 A안 — 공개 메뉴에서 숨김(검색 제외). 비교·복구용으로만 유지."""
    return render_template(
        "main/index.html", active_menu="home", design="a", **get_home_data()
    )


@bp.route("/uploads/<path:filename>")
def uploads(filename):
    """공개 업로드 파일 서빙 (프로필 사진 등).

    인증 서류(verification/)는 admin 전용 라우트로만 — 여기서 차단 (§11).
    배포 시 nginx가 /uploads를 직접 서빙하되 /uploads/verification은 deny 설정 필요.
    """
    normalized = filename.replace("\\", "/")
    if normalized.startswith("verification/"):
        abort(403)
    return send_from_directory(
        os.path.normpath(current_app.config["UPLOAD_FOLDER"]), filename
    )


@bp.route("/robots.txt")
def robots():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        "Disallow: /lawyer",
        "Disallow: /mypage",
        "Disallow: /uploads/verification",
        f"Sitemap: {url_for('main.sitemap', _external=True)}",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap():
    """동적 sitemap — 변호사/상담글/포스트/판례/뉴스 (§2-1).

    커뮤니티는 승인 회원 전용(비공개)으로 전환되어 sitemap에서 제외한다.
    """
    from models import (
        Consultation,
        LawyerPost,
        LawyerProfile,
        LegalCase,
        News,
        User,
    )

    urls = [
        url_for("main.index", _external=True),
        url_for("lawyers.find", _external=True),
        url_for("counsel.list_", _external=True),
        url_for("contents.posts", _external=True),
        url_for("contents.cases", _external=True),
        url_for("contents.news", _external=True),
        url_for("contents.firms", _external=True),
    ]
    for p in (
        LawyerProfile.query.join(User, LawyerProfile.user_id == User.id)
        .filter(User.status == "active", LawyerProfile.is_visible.is_(True))
        .all()
    ):
        urls.append(
            url_for("lawyers.detail", user_id=p.user_id, slug=_slug(p.user.name), _external=True)
        )
    for c in Consultation.query.filter_by(status="open", is_public=True).filter(
        Consultation.deleted_at.is_(None)
    ):
        urls.append(url_for("counsel.detail", consult_id=c.id, slug=_slug(c.title), _external=True))
    for p in LawyerPost.query.filter_by(status="published").filter(
        LawyerPost.deleted_at.is_(None)
    ):
        urls.append(url_for("contents.post_detail", post_id=p.id, slug=_slug(p.title), _external=True))
    for c in LegalCase.query.filter(LegalCase.deleted_at.is_(None)):
        urls.append(url_for("contents.case_detail", case_id=c.id, slug=_slug(c.title), _external=True))
    for n in News.query.filter(News.deleted_at.is_(None), News.published_at.isnot(None)):
        urls.append(url_for("contents.news_detail", news_id=n.id, slug=_slug(n.title), _external=True))

    body = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{body}</urlset>"
    )
    return Response(xml, mimetype="application/xml")
