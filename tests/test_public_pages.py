# -*- coding: utf-8 -*-
"""공개 페이지 — 비회원 열람/슬러그/SEO(JSON-LD·sitemap·robots)/필터/페이지 캐시."""
import re

import pytest

from extensions import db
from models import LawyerProfile, LegalCase, News, User
from utils import invalidate_page_cache

# 커뮤니티는 승인 회원 전용으로 전환 — 공개 목록에서 제외 (게이트는 test_membership.py)
PUBLIC_PATHS = [
    "/", "/main-a", "/lawyers/", "/counsel/", "/posts", "/cases", "/news", "/firms",
    "/login", "/signup", "/signup/lawyer", "/admin/login",
]


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_public_pages_200(client, path):
    assert client.get(path).status_code == 200


class TestSlugAndDetail:
    def test_lawyer_detail_slug_and_jsonld(self, app, client):
        with app.app_context():
            uid = (
                LawyerProfile.query.join(User, LawyerProfile.user_id == User.id)
                .filter(User.status == "active", LawyerProfile.is_visible.is_(True))
                .first().user_id
            )
        r = client.get(f"/lawyers/{uid}", follow_redirects=False)
        assert r.status_code == 301  # 슬러그 canonical
        html = client.get(r.headers["Location"]).get_data(as_text=True)
        assert '"@type": "Attorney"' in html and "application/ld+json" in html

    def test_news_detail_jsonld(self, app, client):
        with app.app_context():
            nid = News.query.filter(News.published_at.isnot(None)).first().id
        r = client.get(f"/news/{nid}", follow_redirects=True)
        assert '"@type": "NewsArticle"' in r.get_data(as_text=True)

    def test_case_detail_views_increment(self, app, client):
        with app.app_context():
            case = LegalCase.query.first()
            cid, before = case.id, case.views or 0
        client.get(f"/cases/{cid}", follow_redirects=True)
        with app.app_context():
            db.session.expire_all()
            assert db.session.get(LegalCase, cid).views == before + 1


class TestFilters:
    def test_cases_category_json_contains(self, app, client):
        with app.app_context():
            case = LegalCase.query.filter(LegalCase.category_ids.isnot(None)).first()
            cat_id, title = case.category_ids[0], case.title
        html = client.get(f"/cases?category={cat_id}").get_data(as_text=True)
        assert title in html

    def test_news_tag_filter(self, app, client):
        with app.app_context():
            n = News.query.filter(News.hashtags.isnot(None)).first()
            tag, title = n.hashtags[0], n.title
        html = client.get(f"/news?tag={tag}").get_data(as_text=True)
        assert title in html

    def test_posts_type_tabs(self, client):
        for t in ("case", "guide", "video", "essay"):
            assert client.get(f"/posts?type={t}").status_code == 200


class TestSeoEndpoints:
    def test_robots(self, client):
        body = client.get("/robots.txt").get_data(as_text=True)
        assert "Disallow: /admin" in body
        assert "Disallow: /uploads/verification" in body
        assert "Sitemap:" in body

    def test_sitemap(self, client):
        r = client.get("/sitemap.xml")
        assert r.status_code == 200 and r.mimetype == "application/xml"
        body = r.get_data(as_text=True)
        for frag in ("/lawyers/", "/counsel/", "/cases/", "/news/"):
            assert frag in body
        assert "/community" not in body  # 회원 전용 — 색인 제외
        assert body.count("<loc>") >= 40  # 시드 규모 기준


class TestLayout:
    """헤더 메뉴 순서 · 메인 고정 배너 · 광고 포토카드 · 구 A안 숨김."""

    def test_design_a_is_hidden(self, client):
        """구 디자인 A안은 검색 제외 + 메인은 B안 마크업."""
        home = client.get("/").get_data(as_text=True)
        assert "svc-cards" in home and "hero-b" in home  # B안 히어로·서비스 카드
        assert 'name="robots" content="noindex"' not in home  # 메인은 색인 허용
        old = client.get("/main-a").get_data(as_text=True)
        assert 'name="robots" content="noindex"' in old  # 숨김 페이지
        # 옛 B안 주소는 메인으로 영구 이동
        r = client.get("/main-b", follow_redirects=False)
        assert r.status_code == 301 and r.headers["Location"].endswith("/")

    def test_no_design_toggle_on_main(self, client):
        """메인에는 A/B 전환 토글이 없다."""
        assert "디자인 A 보기" not in client.get("/").get_data(as_text=True)

    def test_gnb_order_and_menu_set(self, client):
        html = client.get("/").get_data(as_text=True)
        nav = html.split('<nav class="gnb', 1)[1].split("</nav>", 1)[0]
        menu = nav.split("</ul>", 1)[0]  # 상단 메뉴 줄 (메가메뉴 패널 제외)
        assert menu.index(">변호사<") < menu.index("커뮤니티<")
        assert menu.index(">안기모뉴스<") < menu.index("커뮤니티<")
        # 상담사례 → 상담신청으로 명칭 변경
        assert ">상담신청<" in menu and ">상담사례<" not in menu
        # 정보 게시판 3종은 상단 메뉴에서 빠지고 커뮤니티 칩·메가메뉴로 이동
        for gone in ("교정시설 정보", "수용생활 정보", "양식 자료실"):
            assert f">{gone}<" not in menu, gone

    def test_cafe_floating_button(self, client):
        """네이버 카페 바로가기 플로팅 버튼 — 전 페이지 공통, 새 탭."""
        for path in ("/", "/counsel/", "/lawyers/"):
            html = client.get(path).get_data(as_text=True)
            assert "https://cafe.naver.com/32genius" in html, path
            assert "카페 바로가기" in html, path
        block = html.split('class="fab-cafe"', 1)[1][:200]
        assert 'target="_blank"' in block and "noopener" in block

    def test_community_chips_include_info_boards(self, client, login_as):
        """커뮤니티 칩에 정보 게시판 3종이 함께 노출되고 서로 이동 가능."""
        login_as("user1@example.com")
        html = client.get("/community/").get_data(as_text=True)
        chips = html.split('class="cat-chips"', 1)[1].split("</div>", 1)[0]
        for label in ("자유게시판", "옥바라지 이야기", "사연신청",
                      "교정시설 정보", "수용생활 정보", "양식 자료실"):
            assert label in chips, label
        # 정보 게시판 화면에도 같은 칩 + 세부 주제 칩
        board = client.get("/community/board/facility").get_data(as_text=True)
        assert 'class="cat-chips"' in board and 'class="topic-chips"' in board
        assert "자유게시판" in board and "영치금 계좌" in board

    def test_side_banner_is_fixed_single(self, app, client):
        """메인 우측 커뮤니티 배너는 고정 1장 — 인디케이터·롤링 없음."""
        html = client.get("/").get_data(as_text=True)
        assert 'id="side-banner"' in html
        assert 'id="side-cur"' not in html  # 1/N 인디케이터 제거
        assert html.count('class="side-slide on"') == 1
        from services import get_home_data
        with app.app_context():
            assert len(get_home_data()["side_banners"]) <= 1

    def test_ad_photocard_shows_profile(self, client):
        """포토카드 — 사진/소속/이름/소개글만 노출(사례 제목·안내 문구 없음)."""
        html = client.get("/lawyers/").get_data(as_text=True)
        block = html.split('class="sa-grid"', 1)[1].split("sec-title", 1)[0]
        for cls in ('class="ph"', 'class="firm"', 'class="nm"', 'class="intro"', 'class="cta"'):
            assert cls in block, cls
        assert "이런 고민, 이렇게 해결됩니다" not in html  # 안내 문구 제거
        assert 'class="case"' not in block  # 사례 제목 블록 제거

    def test_ad_photocard_no_duplicate_lawyer(self, client):
        """광고 영역은 변호사 1인 1카드."""
        html = client.get("/lawyers/").get_data(as_text=True)
        block = html.split('class="sa-grid"', 1)[1].split("sec-title", 1)[0]
        names = re.findall(r'class="nm">(.*?) 변호사<', block)
        assert names and len(names) == len(set(names))

    def test_ad_area_hidden_when_none_designated(self, app, client):
        """광고 지정이 0건이면 포토카드·AD LAWYERS 영역 자체가 사라짐."""
        from models import LawyerAd

        with app.app_context():
            LawyerAd.query.delete()
            db.session.commit()
            invalidate_page_cache()
        html = client.get("/lawyers/").get_data(as_text=True)
        assert 'class="sa-grid"' not in html and "AD LAWYERS" not in html

    def test_ad_lawyers_has_no_hardcoded_merit(self, client):
        """AD LAWYERS의 '명쾌한 변호사/해결사' 하드코딩 뱃지 제거 확인."""
        html = client.get("/lawyers/").get_data(as_text=True)
        assert "명쾌한 변호사" not in html and ">해결사<" not in html

    def test_kakao_buttons_use_brand_symbol(self, app, client):
        """카카오톡 버튼은 lucide 말풍선이 아니라 카카오 심볼 사용."""
        from models import LawyerProfile as LP
        with app.app_context():
            uid = LP.query.filter(LP.kakao_url.isnot(None)).first().user_id
        html = client.get(f"/lawyers/{uid}", follow_redirects=True).get_data(as_text=True)
        assert "ico-kakao" in html
        assert 'data-lucide="message-circle"' not in html


class TestNoStoreHeaders:
    """로그인·어드민 응답은 브라우저 캐시 금지 — 낡은 화면으로 인한 혼동 방지."""

    def test_logged_in_response_no_store(self, client, login_as):
        login_as("user1@example.com")
        assert client.get("/mypage/").headers.get("Cache-Control") == "no-store"

    def test_admin_paths_no_store(self, client, login_as):
        # 비로그인 리다이렉트 응답에도 부착
        assert client.get("/admin/", follow_redirects=False).headers.get(
            "Cache-Control") == "no-store"
        login_as("admin@angimo.kr")
        assert client.get("/admin/posts").headers.get("Cache-Control") == "no-store"

    def test_lawyer_admin_no_store_but_public_list_untouched(self, client, login_as):
        login_as("lawyer1@angimo.kr")
        assert client.get("/lawyer/").headers.get("Cache-Control") == "no-store"
        client.get("/logout")
        # 공개 변호사 목록(/lawyers)은 사설 경로가 아니므로 미부착
        assert client.get("/lawyers/").headers.get("Cache-Control") != "no-store"

    def test_public_pages_not_no_store(self, client):
        for path in ("/", "/counsel/", "/cases"):
            assert client.get(path).headers.get("Cache-Control") != "no-store", path


class TestPageCache:
    def test_anon_cached_until_invalidate(self, app, client):
        """비로그인 GET은 캐시 — ORM 직접 변경은 안 보이다가 invalidate 후 반영."""
        assert "캐시확인용판례" not in client.get("/cases").get_data(as_text=True)
        with app.app_context():
            db.session.add(LegalCase(title="캐시확인용판례", summary="s", content="c",
                                     case_type="civil"))
            db.session.commit()
        # 여전히 캐시된 응답
        assert "캐시확인용판례" not in client.get("/cases").get_data(as_text=True)
        with app.app_context():
            invalidate_page_cache()
        assert "캐시확인용판례" in client.get("/cases").get_data(as_text=True)

    def test_logged_in_bypasses_cache(self, app, client, login_as):
        client.get("/cases")  # (비로그인 캐시 적재)
        with app.app_context():
            db.session.add(LegalCase(title="로그인우회판례", summary="s", content="c",
                                     case_type="civil"))
            db.session.commit()
        login_as("user1@example.com")
        # 로그인 사용자는 캐시를 우회하므로 즉시 보임
        assert "로그인우회판례" in client.get("/cases").get_data(as_text=True)
