from functools import wraps

from flask import abort, g, redirect, request, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                if "admin" in roles:
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
