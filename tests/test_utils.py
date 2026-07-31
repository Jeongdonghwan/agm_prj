# -*- coding: utf-8 -*-
"""utils 순수 단위 — 마스킹, 닉네임 검증."""
import pytest

from utils import body_text, mask_privacy, validate_nickname


class TestBodyText:
    def test_strips_img_tokens(self):
        raw = "앞 텍스트\n[img]/uploads/community/1/a.png[/img]\n뒤 텍스트"
        assert body_text(raw) == "앞 텍스트 뒤 텍스트"

    def test_plain_untouched(self):
        assert body_text("그냥 본문") == "그냥 본문"
        assert body_text("") == ""


class TestMaskPrivacy:
    @pytest.mark.parametrize("raw,masked", [
        ("010-1234-5678", "010-****-5678"),
        ("연락처 010 1234 5678 입니다", "연락처 010-****-5678 입니다"),
        ("010.9999.8888", "010-****-8888"),
        ("01012345678", "010-****-5678"),
        ("011-234-5678", "011-****-5678"),
    ])
    def test_phone(self, raw, masked):
        assert mask_privacy(raw) == masked

    @pytest.mark.parametrize("raw,masked", [
        ("900101-1234567", "900101-*******"),
        ("주민번호 900101 1234567 끝", "주민번호 900101-******* 끝"),
    ])
    def test_rrn(self, raw, masked):
        assert mask_privacy(raw) == masked

    def test_untouched(self):
        text = "일반 텍스트 2026-07-27 사건번호 2026가단12345"
        assert mask_privacy(text) == text

    def test_empty(self):
        assert mask_privacy("") == ""
        assert mask_privacy(None) is None


class TestValidateNickname:
    @pytest.mark.parametrize("value", ["홍길동", "ab", "가나다라마바사아자차", "user123", "한글abc9"])
    def test_valid(self, value):
        ok, reason = validate_nickname(value)
        assert ok, reason

    @pytest.mark.parametrize("value", [
        "a",                # 1자
        "가나다라마바사아자차카",  # 11자
        "닉네임!",           # 특수문자
        "공백 있음",          # 공백
        "", None,
    ])
    def test_invalid_format(self, value):
        ok, _ = validate_nickname(value)
        assert not ok

    @pytest.mark.parametrize("value", ["관리자짱", "운영자님", "어드민1", "Admin99", "angimo1", "안기모팬", "변호사김"])
    def test_banned(self, value):
        ok, reason = validate_nickname(value)
        assert not ok
        assert "사용할 수 없는" in reason
