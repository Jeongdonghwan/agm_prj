import re

# 전화번호·주민등록번호 자동 마스킹 (§11 — 커뮤니티/상담글)
_PHONE_RE = re.compile(r"\b(01[016789])[-\s.]?(\d{3,4})[-\s.]?(\d{4})\b")
_RRN_RE = re.compile(r"\b(\d{6})[-\s.]?([1-4])(\d{6})\b")

NICKNAME_RE = re.compile(r"^[가-힣a-zA-Z0-9]{2,10}$")
NICKNAME_BANNED = ["관리자", "운영자", "어드민", "admin", "angimo", "안기모", "변호사"]


def mask_privacy(text: str) -> str:
    if not text:
        return text
    text = _PHONE_RE.sub(lambda m: f"{m.group(1)}-****-{m.group(3)}", text)
    text = _RRN_RE.sub(lambda m: f"{m.group(1)}-*******", text)
    return text


def validate_nickname(value: str):
    """(ok, reason) — 2~10자 한글/영문/숫자 + 금칙어 필터."""
    if not NICKNAME_RE.match(value or ""):
        return False, "닉네임은 2~10자의 한글/영문/숫자만 사용할 수 있습니다."
    lowered = value.lower()
    for banned in NICKNAME_BANNED:
        if banned in lowered:
            return False, "사용할 수 없는 단어가 포함되어 있습니다."
    return True, ""
