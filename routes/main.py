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


# ── 운영정책 (푸터 링크) — 정적 문서, 필요 시 여기서 문구 수정 ──────────────
POLICIES = {
    "counsel": ("상담신청 운영정책", [
        ("목적", "상담신청 게시판은 이용자가 법률 고민을 남기고 변호사 회원의 일반적 답변을 받는 공간입니다. 게시된 답변은 참고용 정보 제공이며, 개별 사건에 대한 법률 자문·수임 계약을 의미하지 않습니다."),
        ("작성 규칙", "질문에는 사건 관계인의 실명, 주민등록번호, 연락처 등 개인정보를 기재하지 않아야 하며, 기재된 개인정보(전화번호·주민등록번호 패턴)는 자동으로 가려집니다. 동일 내용의 반복 게시, 특정 변호사·로펌에 대한 비방, 광고성 게시물은 통보 없이 숨김·삭제될 수 있습니다."),
        ("답변 규칙", "답변은 승인된 변호사 회원만 작성할 수 있으며 상담글당 변호사 1인 1답변으로 제한됩니다. 답변을 근거로 한 직접 수임 권유·비용 안내는 프로필의 연락 수단을 통해 사이트 밖에서 이루어집니다."),
        ("수정·삭제", "질문 글은 답변이 등록되기 전까지 작성자가 수정·삭제할 수 있습니다. 답변이 등록된 후에는 답변 변호사의 권익 보호를 위해 운영팀 검토를 거쳐 처리됩니다."),
    ]),
    "content": ("콘텐츠 운영정책", [
        ("검수 원칙", "변호사포스트(해결사례·법률가이드·법률동영상·변호사에세이)는 작성 후 운영팀 검수를 거쳐 게시됩니다. 사실과 다른 내용, 과장·허위 광고 소지, 타인의 권리를 침해하는 콘텐츠는 반려되며 반려 사유가 함께 안내됩니다."),
        ("해결사례 기준", "해결사례는 실제 수행 사건을 기반으로 하되 의뢰인을 특정할 수 있는 정보(성명·지역·사건번호 등)를 포함할 수 없습니다. 결과 뱃지(무죄·집행유예 등)는 판결문 등 근거 자료로 확인 가능한 범위에서 표기합니다."),
        ("판례·뉴스", "판례돋보기와 안기모뉴스는 운영팀이 직접 작성·편집하며, 원문 출처가 있는 경우 출처를 표기합니다. 오류 제보는 문의 채널로 접수받아 확인 후 정정합니다."),
        ("저작권", "게시된 콘텐츠의 저작권은 작성자에게 있으며, 무단 전재·재배포를 금지합니다. 저작권 침해 신고가 접수되면 임시 블라인드 정책에 따라 처리합니다."),
    ]),
    "search": ("검색결과 표시에 관한 운영정책", [
        ("기본 원칙", "변호사 검색 결과의 일반 목록은 특정 변호사에게 유불리가 없도록 무작위 순서로 표시되며, 주기적으로 순서가 변경됩니다. 검색어 입력 시에는 분야(해시태그)·이름·소속·소개글과의 일치 여부를 기준으로 결과를 표시합니다."),
        ("광고 표시", "목록 상단 포토카드, AD LAWYERS, 메인 상담하기 슬라이더 등 광고 구좌는 일반 검색 결과와 구분되도록 AD 표기를 하며, 구좌 내 순서 역시 무작위로 회전합니다. 광고 집행 여부는 검색 결과의 일반 목록 순서에 영향을 주지 않습니다."),
        ("노출 제외", "프로필 필수 정보(사진·소개·분야·연락 수단)가 완성되지 않았거나 운영정책 위반으로 노출 정지된 변호사는 검색 결과에 표시되지 않습니다."),
    ]),
    "blind": ("게시물 임시 블라인드 정책", [
        ("적용 대상", "권리 침해(명예훼손·저작권·개인정보), 허위 사실, 혐오·차별 표현 등의 신고가 접수된 게시물·댓글은 사실 확인 전이라도 임시로 블라인드(숨김) 처리될 수 있습니다."),
        ("처리 절차", "신고 접수 → 운영팀 1차 검토(영업일 기준 3일 이내) → 필요 시 임시 블라인드 → 작성자 소명 접수(7일) → 최종 판단(복구 또는 삭제) 순으로 진행합니다. 처리 결과는 신고자와 작성자에게 안내됩니다."),
        ("이의 제기", "블라인드 처리에 이의가 있는 작성자는 처리 안내를 받은 날로부터 7일 이내 문의 채널로 소명 자료를 제출할 수 있습니다. 소명이 타당한 경우 게시물은 지체 없이 복구됩니다."),
        ("반복 위반", "동일 유형 위반이 반복되는 계정은 커뮤니티 운영정책의 제재 기준(경고→이용 제한→계정 정지)에 따라 단계적으로 제재됩니다."),
    ]),
    "community": ("커뮤니티 운영정책", [
        ("이용 자격", "커뮤니티는 수용자 가족·지인을 위한 공간으로, 접견예약확인 제출 후 운영팀 승인을 받은 회원만 열람·작성할 수 있습니다. 제출 자료는 확인 용도로만 사용하며 외부에 공개되지 않습니다."),
        ("금지 행위", "타인의 개인정보(수용자 정보 포함) 무단 게시, 사건 관계인 비방, 금전 요구·사기 권유, 광고·홍보(운영팀 승인 없는), 혐오 표현을 금지합니다. 전화번호·주민등록번호는 자동으로 가려집니다."),
        ("게시판 규칙", "각 게시판의 주제에 맞게 글을 작성해주세요. 공지·FAQ 게시판은 운영팀만 작성할 수 있으며, 카테고리별 작성 권한은 운영 상황에 따라 조정될 수 있습니다."),
        ("제재 기준", "위반 시 게시물 숨김·삭제와 함께 경고가 부여되며, 경고 누적 또는 중대한 위반 시 커뮤니티 이용 제한·계정 정지가 이루어질 수 있습니다. 제재에 대한 이의는 문의 채널로 접수할 수 있습니다."),
    ]),
}


@bp.route("/policy/<key>")
def policy(key):
    """운영정책 문서 — 푸터에서 연결."""
    if key not in POLICIES:
        abort(404)
    title, sections = POLICIES[key]
    return render_template(
        "main/policy.html",
        active_menu=None,
        title=title,
        sections=sections,
        policies=POLICIES,
        current=key,
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
