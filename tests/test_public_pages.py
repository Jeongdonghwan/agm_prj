# -*- coding: utf-8 -*-
"""공개 페이지 — 비회원 열람/슬러그/SEO(JSON-LD·sitemap·robots)/필터/페이지 캐시."""
import re

import pytest

from extensions import db
from models import LawyerProfile, LegalCase, News, User
from utils import invalidate_page_cache

PUBLIC_PATHS = [
    "/", "/main-b", "/lawyers/", "/counsel/", "/posts", "/cases", "/news", "/firms",
    "/community/", "/community/board/facility", "/community/board/life",
    "/community/board/forms", "/login", "/signup", "/signup/lawyer", "/admin/login",
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
        for frag in ("/lawyers/", "/counsel/", "/cases/", "/news/", "/community/"):
            assert frag in body
        assert body.count("<loc>") >= 50  # 시드 규모 기준


class TestLayout:
    """헤더 메뉴 순서 · B안 고정 배너 · 해결사례 포토카드."""

    def test_gnb_order_lawyers_before_community(self, client):
        html = client.get("/").get_data(as_text=True)
        nav = html.split('<nav class="gnb', 1)[1].split("</nav>", 1)[0]
        assert nav.index(">변호사<") < nav.index(">커뮤니티<")
        assert nav.index(">안기모뉴스<") < nav.index(">커뮤니티<")
        # 옥바라지 정보 메뉴는 커뮤니티 뒤에 묶여 유지
        assert nav.index(">커뮤니티<") < nav.index(">교정시설 정보<") < nav.index(">양식 자료실<")

    def test_side_banner_is_fixed_single(self, app, client):
        """B안 우측 배너는 고정 1장 — 인디케이터·롤링 없음."""
        html = client.get("/main-b").get_data(as_text=True)
        assert 'id="side-banner"' in html
        assert 'id="side-cur"' not in html  # 1/N 인디케이터 제거
        assert html.count('class="side-slide on"') == 1
        from services import get_home_data
        with app.app_context():
            assert len(get_home_data()["side_banners"]) <= 1

    def test_solve_ad_photocard_shows_profile(self, client):
        """포토카드 — 사진/소속/이름/소개글만 노출(사례 제목·안내 문구 없음)."""
        html = client.get("/lawyers/").get_data(as_text=True)
        block = html.split('class="sa-grid"', 1)[1].split("sec-title", 1)[0]
        for cls in ('class="ph"', 'class="firm"', 'class="nm"', 'class="intro"', 'class="cta"'):
            assert cls in block, cls
        assert "이런 고민, 이렇게 해결됩니다" not in html  # 안내 문구 제거
        assert 'class="case"' not in block  # 사례 제목 블록 제거

    def test_solve_ad_no_duplicate_lawyer(self, client):
        """광고 영역은 변호사 1인 1카드."""
        html = client.get("/lawyers/").get_data(as_text=True)
        block = html.split('class="sa-grid"', 1)[1].split("sec-title", 1)[0]
        names = re.findall(r'class="nm">(.*?) 변호사<', block)
        assert names and len(names) == len(set(names))


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
