# -*- coding: utf-8 -*-
"""공개 페이지 — 비회원 열람/슬러그/SEO(JSON-LD·sitemap·robots)/필터/페이지 캐시."""
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
