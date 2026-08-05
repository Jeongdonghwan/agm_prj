from functools import wraps

from flask import abort, g, redirect, request, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def community_member_required(view):
    """커뮤니티 전용 게이트 — 로그인 + (일반회원은) 관리자 승인 필요.

    비로그인 → 로그인으로, 미승인 일반회원 → 인증 안내(locked)로.
    admin·lawyer는 승인 개념이 없으므로 통과한다.
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        if not g.user.community_approved:
            return redirect(url_for("community.locked"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                # admin 전용 페이지만 관리자 로그인으로 (user+admin 겸용은 일반 로그인)
                if set(roles) == {"admin"}:
                    return redirect(url_for("auth.admin_login"))
                return redirect(url_for("auth.login", next=request.path))
            if g.user.role not in roles:
                abort(403)
            # 승인 전 변호사는 어드민 진입 불가 — 대기 안내로
            if g.user.role == "lawyer" and g.user.status != "active":
                return redirect(url_for("auth.pending"))
            return view(*args, **kwargs)

        return wrapped

    return decorator
