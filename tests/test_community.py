# -*- coding: utf-8 -*-
"""커뮤니티 — 목록/보드/글·댓글/익명/닉네임 규칙/첨부파일."""
import os
import re

from extensions import db
from models import CommunityPost, User


def _active_chips(html):
    """칩 줄에서 선택(class="on")된 칩의 라벨 목록."""
    row = html.split('class="cat-chips"', 1)[1].split("</div>", 1)[0]
    return re.findall(r'<a [^>]*class="on"[^>]*>([^<]+)</a>', row)


def _chip_labels(html):
    row = html.split('class="cat-chips"', 1)[1].split("</div>", 1)[0]
    return [m.strip() for m in re.findall(r"<a [^>]*>([^<]+)</a>", row)]


def _list_head(html):
    return html.split('class="list-head"', 1)[1].split("</div>", 1)[0]


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
        assert "사연신청" in html  # 신규 카테고리
        assert "공지" in html

    def test_story_category_write_and_filter(self, app, client, login_as):
        """사연신청 카테고리 — 글 작성 후 해당 칩으로 필터."""
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, category="사연신청", title="사연 신청합니다")
        assert r.status_code == 302
        html = client.get("/community/?category=사연신청").get_data(as_text=True)
        assert "사연 신청합니다" in html

    def test_category_filter(self, client):
        assert client.get("/community/?category=옥바라지 이야기").status_code == 200

    def test_popular_sort(self, client):
        assert client.get("/community/?sort=popular").status_code == 200


class TestChips:
    """칩은 한 축 — 전체/인기/카테고리/정보 게시판 중 항상 하나만 선택된다."""

    def test_chip_order_without_latest(self, client):
        labels = _chip_labels(client.get("/community/").get_data(as_text=True))
        assert labels[:2] == ["전체", "인기"]
        assert "최신" not in labels
        assert labels[2:5] == ["자유게시판", "옥바라지 이야기", "사연신청"]
        assert labels[5:] == ["교정시설 정보", "수용생활 정보", "양식 자료실"]

    def test_exactly_one_active(self, client):
        cases = {
            "/community/": "전체",
            "/community/?sort=popular": "인기",
            "/community/?category=자유게시판": "자유게시판",
            "/community/?category=사연신청": "사연신청",
            "/community/board/facility": "교정시설 정보",
            "/community/board/forms": "양식 자료실",
        }
        for path, expected in cases.items():
            active = _active_chips(client.get(path).get_data(as_text=True))
            assert active == [expected], (path, active)

    def test_category_wins_over_popular(self, client):
        """카테고리 + 인기를 같이 넘겨도 활성 칩은 카테고리 하나뿐."""
        html = client.get("/community/?category=자유게시판&sort=popular").get_data(as_text=True)
        assert _active_chips(html) == ["자유게시판"]

    def test_list_head_shows_selection(self, client):
        for path, expected in (("/community/", "전체"),
                               ("/community/?sort=popular", "인기 글"),
                               ("/community/?category=옥바라지 이야기", "옥바라지 이야기"),
                               ("/community/board/life", "수용생활 정보")):
            head = _list_head(client.get(path).get_data(as_text=True))
            assert expected in head and "개의 글" in head, path


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
        # 상세: 이미지는 본문 아래 인라인 <img>, 일반 파일은 다운로드 링크
        html = client.get(f"/community/{pid}").get_data(as_text=True)
        with app.app_context():
            img_url, pdf_name = atts[0]["url"], atts[1]["name"]
        assert f'<img src="{img_url}"' in html  # 이미지 인라인 표시
        assert pdf_name in html and "attach-list" in html  # pdf는 링크 유지
        assert client.get(img_url).status_code == 200  # 공개 서빙

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


class TestOwnPost:
    """내 글 수정/삭제 — 언제든 가능."""

    def _mine(self, app, client, login_as, title="수정 대상 커뮤 글"):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, title=title)
        return int(r.headers["Location"].rstrip("/").split("/")[-1])

    def test_owner_sees_actions(self, app, client, login_as):
        pid = self._mine(app, client, login_as)
        html = client.get(f"/community/{pid}").get_data(as_text=True)
        assert "own-actions" in html and f"/community/{pid}/edit" in html

    def test_edit(self, app, client, login_as):
        pid = self._mine(app, client, login_as)
        r = client.post(f"/community/{pid}/edit", data={
            "category": "옥바라지 이야기", "title": "수정된 제목", "content": "수정된 본문",
        }, content_type="multipart/form-data", follow_redirects=True)
        assert "글이 수정되었습니다" in r.get_data(as_text=True)
        with app.app_context():
            p = db.session.get(CommunityPost, pid)
            assert p.title == "수정된 제목" and p.category == "옥바라지 이야기"

    def test_edit_allowed_with_comments(self, app, client, login_as):
        pid = self._mine(app, client, login_as)
        client.post(f"/community/{pid}/comments", data={"content": "댓글"})
        r = client.post(f"/community/{pid}/edit", data={
            "category": "자유게시판", "title": "댓글 있어도 수정", "content": "c",
        }, content_type="multipart/form-data", follow_redirects=True)
        assert "글이 수정되었습니다" in r.get_data(as_text=True)

    def test_edit_removes_attachment(self, app, client, login_as, sample_file):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, title="첨부 수정 글",
                   files=[sample_file("a.png"), sample_file("b.pdf", b"%PDF-1.4")])
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        with app.app_context():
            remove_url = db.session.get(CommunityPost, pid).attachments[0]["url"]
        client.post(f"/community/{pid}/edit", data={
            "category": "자유게시판", "title": "첨부 수정 글", "content": "c",
            "remove_attachments": remove_url,
        }, content_type="multipart/form-data")
        with app.app_context():
            atts = db.session.get(CommunityPost, pid).attachments
            assert len(atts) == 1 and atts[0]["name"] == "b.pdf"

    def test_delete_soft(self, app, client, login_as):
        pid = self._mine(app, client, login_as)
        r = client.post(f"/community/{pid}/delete", follow_redirects=True)
        assert "글이 삭제되었습니다" in r.get_data(as_text=True)
        with app.app_context():
            p = db.session.get(CommunityPost, pid)
            assert p.status == "deleted" and p.deleted_at is not None
        assert client.get(f"/community/{pid}").status_code == 404

    def test_others_cannot_edit_or_delete(self, app, client, login_as):
        pid = self._mine(app, client, login_as)
        _set_nickname(app, "user3@example.com", "다른유저닉")
        login_as("user3@example.com")
        assert client.get(f"/community/{pid}/edit").status_code == 404
        assert client.post(f"/community/{pid}/delete").status_code == 404
        # 타인 화면에는 수정/삭제 버튼 미노출
        assert "own-actions" not in client.get(f"/community/{pid}").get_data(as_text=True)

    def test_anon_redirects(self, app, client, login_as):
        pid = self._mine(app, client, login_as)
        client.get("/logout")
        assert client.get(f"/community/{pid}/edit", follow_redirects=False).status_code == 302


class TestBodyEditor:
    """본문 이미지 간이 에디터 — 업로드 API + [img] 토큰 렌더."""

    def _login(self, app, login_as):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        return login_as("user1@example.com")

    def test_upload_image(self, app, client, login_as, sample_file):
        uid = self._login(app, login_as)
        r = client.post("/community/upload-image", data={"image": sample_file("body.png")},
                        content_type="multipart/form-data")
        assert r.status_code == 200
        url = r.get_json()["url"]
        assert url.startswith(f"/uploads/community/{uid}/")
        assert client.get(url).status_code == 200  # 공개 서빙

    def test_upload_bad_ext(self, app, client, login_as, sample_file):
        self._login(app, login_as)
        r = client.post("/community/upload-image", data={"image": sample_file("x.gif", b"GIF89a")},
                        content_type="multipart/form-data")
        assert r.status_code == 400 and r.get_json()["error"]["code"] == "INVALID_TYPE"

    def test_upload_requires_login(self, client, sample_file):
        r = client.post("/community/upload-image", data={"image": sample_file()},
                        content_type="multipart/form-data", follow_redirects=False)
        assert r.status_code == 302

    def test_lawyer_403(self, client, login_as, sample_file):
        login_as("lawyer1@angimo.kr")
        r = client.post("/community/upload-image", data={"image": sample_file()},
                        content_type="multipart/form-data")
        assert r.status_code == 403

    def test_body_token_renders_img(self, app, client, login_as):
        uid = self._login(app, login_as)
        body = f"첫 줄입니다\n[img]/uploads/community/{uid}/demo.png[/img]\n마지막 줄"
        r = _write(client, title="에디터 본문 글", content=body)
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        html = client.get(f"/community/{pid}").get_data(as_text=True)
        assert f'<img class="body-img" src="/uploads/community/{uid}/demo.png"' in html
        assert "[img]" not in html.split("comm-detail")[1].split("cmt-sec")[0]

    def test_external_token_stripped(self, app, client, login_as):
        self._login(app, login_as)
        r = _write(client, title="외부 이미지 글", content="본문 [img]https://evil.com/x.png[/img] 끝")
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        with app.app_context():
            content = db.session.get(CommunityPost, pid).content
        assert "evil.com" not in content

    def test_first_image_from_body(self, app, client, login_as):
        uid = self._login(app, login_as)
        _write(client, title="본문 이미지 썸네일 글",
               content=f"글\n[img]/uploads/community/{uid}/thumb.png[/img]")
        # 목록 썸네일에 본문 이미지 사용 + 미리보기 텍스트에 토큰 미노출
        html = client.get("/community/").get_data(as_text=True)
        assert f"/uploads/community/{uid}/thumb.png" in html
        assert "[img]" not in html


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
