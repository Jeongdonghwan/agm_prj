# -*- coding: utf-8 -*-
"""커뮤니티 — 목록/보드/글·댓글/익명/닉네임 규칙/첨부파일."""
import os

from extensions import db
from models import CommunityPost, User


def _set_nickname(app, email, nickname):
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        u.nickname = nickname
        db.session.commit()


def _write(client, sample_file=None, files=None, **kw):
    data = {"category": "자유게시판", "title": "커뮤 글", "content": "본문", **kw}
    if files is not None:
        data["attachments"] = files
    return client.post("/community/write", data=data,
                       content_type="multipart/form-data", follow_redirects=False)


class TestList:
    def test_200_chips_notice(self, client):
        html = client.get("/community/").get_data(as_text=True)
        assert "자유게시판" in html and "옥바라지 이야기" in html
        assert "공지" in html

    def test_category_filter(self, client):
        assert client.get("/community/?category=옥바라지 이야기").status_code == 200

    def test_popular_sort(self, client):
        assert client.get("/community/?sort=popular").status_code == 200


class TestBoard:
    def test_boards_200(self, client):
        for key in ("facility", "life", "forms"):
            assert client.get(f"/community/board/{key}").status_code == 200

    def test_bad_key_404(self, client):
        assert client.get("/community/board/unknown").status_code == 404

    def test_topic_filter(self, client):
        html = client.get("/community/board/facility?topic=영치금 계좌").get_data(as_text=True)
        assert "영치금" in html and "서울구치소 접견" not in html

    def test_forms_post_detail_renders_attachments(self, app, client):
        # 시드: 양식자료실 4건에 데모 첨부 — 목록은 이미지 썸네일만, 첨부는 상세에서 렌더
        with app.app_context():
            pid = CommunityPost.query.filter_by(category="탄원서").first().id
        html = client.get(f"/community/{pid}").get_data(as_text=True)
        assert "/uploads/community/samples/" in html and "탄원서_양식.txt" in html


class TestNicknameRule:
    def test_write_get_triggers_modal(self, client, login_as):
        login_as("user2@example.com")  # 시드: 닉네임 없음
        html = client.get("/community/write").get_data(as_text=True)
        assert 'data-need-nickname="1"' in html

    def test_write_post_blocked_without_nickname(self, app, client, login_as):
        login_as("user2@example.com")
        r = _write(client)
        assert "닉네임을 먼저 설정해주세요" in r.get_data(as_text=True)
        with app.app_context():
            assert CommunityPost.query.filter_by(title="커뮤 글").count() == 0

    def test_admin_writes_without_nickname(self, client, login_as):
        login_as("admin@angimo.kr")
        assert _write(client, title="관리자 글").status_code == 302


class TestWrite:
    def test_create_masking_anonymous(self, app, client, login_as):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, title="익명글 010-2222-3333", is_anonymous="1")
        assert r.status_code == 302
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        html = client.get(f"/community/{pid}").get_data(as_text=True)
        assert "010-****-3333" in html
        assert ">익명<" in html and "테스트닉넴" not in html  # 익명 글 닉네임 미노출 (§11)

    def test_lawyer_403(self, client, login_as):
        login_as("lawyer1@angimo.kr")
        assert client.get("/community/write").status_code == 403

    def test_anon_redirect(self, client):
        r = client.get("/community/write", follow_redirects=False)
        assert r.status_code == 302 and "/login" in r.headers["Location"]

    def test_bad_category_rejected(self, app, client, login_as):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, category="없는게시판")
        assert "게시판/제목/내용을 확인해주세요" in r.get_data(as_text=True)

    def test_topic_category_saved(self, app, client, login_as):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, category="탄원서", title="탄원서 팁")
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        with app.app_context():
            assert db.session.get(CommunityPost, pid).category == "탄원서"
        # 양식 자료실 보드에 노출
        assert "탄원서 팁" in client.get("/community/board/forms").get_data(as_text=True)


class TestAttachments:
    def _login(self, app, login_as):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        return login_as("user1@example.com")

    def test_upload_saved(self, app, client, login_as, sample_file):
        uid = self._login(app, login_as)
        r = _write(client, title="첨부 글",
                   files=[sample_file("사진.png"), sample_file("양식.pdf", b"%PDF-1.4")])
        assert r.status_code == 302
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        with app.app_context():
            atts = db.session.get(CommunityPost, pid).attachments
            assert len(atts) == 2
            assert atts[0]["name"] == "사진.png"  # 표시명은 원본 유지
            assert atts[0]["url"].startswith(f"/uploads/community/{uid}/")
            assert "사진" not in atts[0]["url"]  # 저장 파일명은 uuid
            fname = atts[0]["url"].split("/")[-1]
            assert os.path.exists(os.path.join(
                app.config["UPLOAD_FOLDER"], "community", str(uid), fname))
        # 상세에서 첨부 렌더 + 공개 서빙 200
        assert "사진.png" in client.get(f"/community/{pid}").get_data(as_text=True)
        with app.app_context():
            url = atts[0]["url"]
        assert client.get(url).status_code == 200

    def test_bad_extension_rejected(self, app, client, login_as, sample_file):
        self._login(app, login_as)
        r = _write(client, title="악성 글", files=[sample_file("virus.exe", b"MZ")])
        assert "첨부할 수 없는 파일 형식" in r.get_data(as_text=True)
        with app.app_context():
            assert CommunityPost.query.filter_by(title="악성 글").count() == 0

    def test_max_5_attachments(self, app, client, login_as, sample_file):
        self._login(app, login_as)
        files = [sample_file(f"f{i}.png") for i in range(6)]
        r = _write(client, title="첨부 6개", files=files)
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        with app.app_context():
            assert len(db.session.get(CommunityPost, pid).attachments) == 5


class TestComments:
    def _post_id(self, app, client, login_as):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, title="댓글 대상 글")
        return int(r.headers["Location"].rstrip("/").split("/")[-1])

    def test_comment_and_reply(self, app, client, login_as):
        pid = self._post_id(app, client, login_as)
        r = client.post(f"/community/{pid}/comments", data={"content": "첫 댓글"},
                        follow_redirects=True)
        assert "첫 댓글" in r.get_data(as_text=True)
        from models import CommunityComment
        with app.app_context():
            cmt = CommunityComment.query.filter_by(post_id=pid).first()
        r = client.post(f"/community/{pid}/comments",
                        data={"content": "대댓글", "parent_id": cmt.id}, follow_redirects=True)
        assert "대댓글" in r.get_data(as_text=True)
        # 대댓글의 대댓글(2-depth)은 400
        with app.app_context():
            reply = CommunityComment.query.filter_by(post_id=pid, parent_id=cmt.id).first()
        r = client.post(f"/community/{pid}/comments",
                        data={"content": "3단계", "parent_id": reply.id})
        assert r.status_code == 400

    def test_empty_comment_rejected(self, app, client, login_as):
        pid = self._post_id(app, client, login_as)
        r = client.post(f"/community/{pid}/comments", data={"content": " "},
                        follow_redirects=True)
        assert "댓글 내용을 입력해주세요" in r.get_data(as_text=True)

    def test_lawyer_comment_403(self, app, client, login_as):
        pid = self._post_id(app, client, login_as)
        login_as("lawyer1@angimo.kr")
        assert client.post(f"/community/{pid}/comments",
                           data={"content": "변호사 댓글"}).status_code == 403


class TestHidden:
    def test_hidden_post_404_except_admin(self, app, client, login_as):
        with app.app_context():
            p = CommunityPost.query.filter_by(status="open", is_notice=False).first()
            p.status = "hidden"
            db.session.commit()
            pid = p.id
        assert client.get(f"/community/{pid}").status_code == 404
        login_as("admin@angimo.kr")
        assert client.get(f"/community/{pid}").status_code == 200
