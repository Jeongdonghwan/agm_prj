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


# ── 회사소개·약관·방침 (푸터 링크) ─────────────────────────────────────────
# ⚠️ 아래 약관·방침은 실제 서비스 내용을 반영해 작성한 초안입니다.
#    사업자 정보(OOO 표기)를 채우고, 시행 전 법률 검토를 받으세요.
LEGAL_DOCS = {
    "about": ("회사소개", [
        ("우리가 하는 일", "{site}는 수용자 가족·지인이 겪는 법률 문제와 옥바라지 과정의 막막함을 덜기 위해 만들어진 플랫폼입니다. 분야별 변호사 프로필과 해결사례, 상담신청 게시판, 그리고 같은 처지의 가족들이 정보를 나누는 커뮤니티를 함께 제공합니다."),
        ("서비스 구성", "① 변호사 찾기 — 분야·지역별로 변호사를 살펴보고 사무소 전화나 카카오톡으로 직접 연락합니다. ② 상담신청 — 법률 고민을 남기면 변호사 회원이 답변합니다. ③ 커뮤니티 — 접견·영치·재판 절차 등 실제 경험과 정보를 나눕니다. ④ 판례돋보기·안기모뉴스 — 알아두면 도움이 되는 판례와 소식을 정리합니다."),
        ("중개하지 않습니다", "{site}는 법률사무를 제공하거나 중개하는 주체가 아닙니다. 모든 법률상담과 사건 수임은 이용자와 변호사·로펌 사이에서 직접 이루어지며, 저희는 서로를 연결하는 정보만 제공합니다. 사이트 안에서 상담 예약이나 결제를 받지 않습니다."),
        ("문의", "제휴·광고 문의는 커뮤니티의 [광고 및 협업 문의] 게시판 또는 contact@angimo.co.kr로 보내주세요. 서비스 이용 중 불편한 점은 [커뮤니티 건의사항]에 남겨주시면 운영팀이 확인합니다."),
    ]),
    "terms": ("이용약관", [
        ("제1조 (목적)", "본 약관은 {site}(이하 '회사')가 제공하는 온라인 서비스(이하 '서비스')의 이용 조건과 절차, 회사와 회원의 권리·의무 및 책임사항을 정하는 것을 목적으로 합니다."),
        ("제2조 (회원의 종류)", "회원은 일반회원과 변호사회원으로 구분됩니다. 일반회원은 가입 즉시 상담신청을 이용할 수 있고, 커뮤니티는 수용자 가족 확인 절차를 거쳐 승인된 후 이용할 수 있습니다. 변호사회원은 변호사 등록번호와 인증 서류를 제출하고 회사의 승인을 받은 후 프로필 등록·상담 답변·포스트 작성을 할 수 있습니다."),
        ("제3조 (서비스의 성격)", "회사는 법률사무 제공 주체가 아니며, 변호사와 이용자를 중개하지 않습니다. 서비스에 게시된 변호사 프로필, 상담 답변, 해결사례, 판례 및 뉴스는 일반적인 정보 제공을 목적으로 하며 개별 사안에 대한 법률 자문이 아닙니다. 이용자가 게시된 정보를 근거로 행한 판단과 그 결과에 대한 책임은 이용자에게 있습니다."),
        ("제4조 (회원의 의무)", "회원은 가입 시 정확한 정보를 제공해야 하며, 타인의 계정을 사용하거나 계정을 양도·대여할 수 없습니다. 회원은 타인의 개인정보·명예·저작권을 침해하는 게시물, 허위 사실, 광고·홍보성 게시물, 혐오 표현을 게시해서는 안 됩니다."),
        ("제5조 (게시물의 관리)", "회사는 회원이 게시한 내용이 관계 법령 또는 각 운영정책에 위반된다고 판단되는 경우 사전 통지 없이 임시 블라인드 처리하거나 삭제할 수 있으며, 처리 기준과 이의 절차는 [게시물 임시 블라인드 정책]을 따릅니다. 게시물의 저작권은 작성자에게 있으나, 회사는 서비스 운영·노출을 위해 해당 게시물을 이용할 수 있습니다."),
        ("제6조 (이용 제한)", "회사는 회원이 본 약관 또는 운영정책을 위반한 경우 경고, 게시물 삭제, 커뮤니티 이용 제한, 계정 정지 순으로 단계적 조치를 할 수 있습니다. 중대한 위반(타인 사칭, 금전 사기, 반복적 권리 침해)의 경우 즉시 계정을 정지할 수 있습니다."),
        ("제7조 (회원 탈퇴)", "회원은 마이페이지에서 언제든지 탈퇴할 수 있습니다. 탈퇴 시 계정은 비활성화되며 재로그인할 수 없습니다. 다만 이미 게시된 글과 댓글은 다른 이용자의 이용을 위해 그대로 남을 수 있고, 삭제를 원하는 경우 탈퇴 전 직접 삭제하거나 문의 채널로 요청해주세요."),
        ("제8조 (책임의 제한)", "회사는 천재지변, 회선 장애 등 불가항력으로 서비스를 제공할 수 없는 경우 책임을 지지 않습니다. 회사는 회원 간 또는 회원과 변호사·로펌 사이에 발생한 분쟁에 개입하지 않으며 그로 인한 손해에 대해 책임지지 않습니다."),
        ("제9조 (약관의 개정)", "회사는 필요한 경우 약관을 개정할 수 있으며, 개정 시 시행일과 개정 내용을 서비스 내 공지사항에 게시합니다. 개정 약관 시행일 이후에도 서비스를 계속 이용하는 경우 개정에 동의한 것으로 봅니다."),
    ]),
    "privacy": ("개인정보처리방침", [
        ("1. 수집하는 항목", "① 일반회원 가입: 이메일, 비밀번호(암호화 저장), 휴대폰 번호, 이름·닉네임(선택) ② 변호사회원 가입: 위 항목에 더해 실명, 변호사 등록번호, 소속 사무소, 인증 서류 파일 ③ 커뮤니티 이용 인증: 접견예약확인 화면 캡처 ④ 로펌 간편상담: 휴대폰 번호 ⑤ 서비스 이용 과정에서 회원이 직접 작성·업로드한 게시물, 댓글, 첨부파일."),
        ("2. 이용 목적", "회원 식별과 로그인, 커뮤니티 이용 자격(수용자 가족 여부) 확인, 변호사 자격 확인 및 프로필 공개, 게시물 작성자 표시, 문의 접수 및 처리, 부정 이용 방지와 분쟁 대응, 서비스 개선을 위해 이용합니다. 수집한 정보를 위 목적 외로 이용하지 않습니다."),
        ("3. 제3자 제공", "회사는 원칙적으로 개인정보를 제3자에게 제공하지 않습니다. 다만 이용자가 로펌 간편상담을 신청하면서 별도로 동의한 경우, 신청 대상 로펌에게 휴대폰 번호가 제공되어 상담 연락 목적으로만 이용됩니다. 그 밖에는 법령에 따른 요청이 있는 경우에 한해 제공합니다."),
        ("4. 보관 기간과 파기", "회원 정보는 탈퇴 시까지 보관하며, 탈퇴하면 계정을 비활성화하고 로그인·서비스 이용이 차단됩니다. 분쟁 대응과 부정 가입 방지를 위해 계정 기록은 일정 기간 보존 후 파기하며, 관계 법령이 정한 경우(전자상거래법 등)에는 해당 기간 동안 보관합니다. 변호사 인증 서류와 접견예약확인 이미지는 확인 목적을 달성한 뒤 지체 없이 파기합니다."),
        ("5. 보호 조치", "비밀번호는 복호화가 불가능한 방식으로 암호화해 저장합니다. 변호사 인증 서류와 접견예약확인 이미지는 공개 주소로 접근할 수 없으며 관리자 전용 경로로만 열람할 수 있습니다. 게시물에 포함된 전화번호·주민등록번호 형태의 문자열은 자동으로 가려집니다. 관리자 화면은 권한이 부여된 계정만 접근할 수 있고 주요 조치는 운영 로그로 기록됩니다."),
        ("6. 이용자의 권리", "이용자는 언제든지 마이페이지에서 자신의 정보를 조회·수정하거나 탈퇴할 수 있습니다. 개인정보 열람·정정·삭제·처리정지를 원하는 경우 아래 연락처로 요청하시면 지체 없이 조치합니다."),
        ("7. 개인정보 보호책임자", "성명: OOO / 이메일: contact@angimo.co.kr. 개인정보 관련 문의·불만 처리는 위 연락처로 접수받습니다. 개인정보 침해에 대한 신고·상담이 필요한 경우 개인정보침해신고센터(privacy.kisa.or.kr, 국번없이 118), 대검찰청 사이버수사과(1301), 경찰청 사이버수사국(ecrm.police.go.kr, 182)에 문의하실 수 있습니다."),
        ("8. 방침의 변경", "본 방침의 내용이 추가·삭제·수정되는 경우 시행일 최소 7일 전부터 서비스 내 공지사항을 통해 안내합니다."),
    ]),
}


def _doc_tabs(group, current, endpoint):
    """문서 상단 이동 탭 — 같은 묶음 안에서만 이동."""
    return [
        {
            "url": url_for(endpoint, key=k),
            "label": title.replace(" 운영정책", "").replace("에 관한", ""),
            "on": k == current,
        }
        for k, (title, _) in group.items()
    ]


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
        tabs=_doc_tabs(POLICIES, key, "main.policy"),
        numbered=True,
    )


@bp.route("/docs/<key>")
def doc(key):
    """회사소개·이용약관·개인정보처리방침 — 푸터에서 연결."""
    if key not in LEGAL_DOCS:
        abort(404)
    from flask import current_app

    title, sections = LEGAL_DOCS[key]
    site = current_app.config["SITE_NAME"]
    sections = [(h, b.replace("{site}", site)) for h, b in sections]
    return render_template(
        "main/policy.html",
        active_menu=None,
        title=title,
        sections=sections,
        tabs=_doc_tabs(LEGAL_DOCS, key, "main.doc"),
        numbered=False,  # 조문 번호가 본문에 이미 있음
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
