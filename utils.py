import re
from functools import wraps

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


def cached_page(timeout=120):
    """비로그인 GET 응답만 캐시하는 목록 페이지용 데코레이터 (§2-2).

    글 작성/수정 시 cache.clear()로 무효화.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            from flask import g, request, session

            from extensions import cache

            # 로그인 사용자·flash 메시지 대기 중에는 캐시 우회 (개인화 응답 보존)
            if (
                g.get("user") is not None
                or request.method != "GET"
                or "_flashes" in session
            ):
                return view(*args, **kwargs)
            ver = cache.get("page_ver") or 1
            key = f"page:{ver}:{request.full_path}"
            rv = cache.get(key)
            if rv is None:
                rv = view(*args, **kwargs)
                if isinstance(rv, str):
                    cache.set(key, rv, timeout=timeout)
            return rv

        return wrapped

    return decorator


def invalidate_page_cache():
    """콘텐츠 생성/수정 시 페이지 캐시 무효화.

    버전 키 증가 방식 — 로그인 잠금 카운터(login_fail:*)는 보존된다.
    """
    from extensions import cache

    cache.set("page_ver", (cache.get("page_ver") or 1) + 1, timeout=0)
