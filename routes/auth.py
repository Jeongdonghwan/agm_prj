import os
import re
import uuid
from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from extensions import cache, db
from models import LawyerProfile, LawyerVerificationFile, User

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _fail_key(email: str) -> str:
    return f"login_fail:{email.lower()}"


def _is_locked(email: str) -> bool:
    count = cache.get(_fail_key(email)) or 0
    return count >= current_app.config["LOGIN_FAIL_LIMIT"]


def _record_fail(email: str) -> None:
    key = _fail_key(email)
    count = (cache.get(key) or 0) + 1
    cache.set(key, count, timeout=current_app.config["LOGIN_LOCK_SECONDS"])


def _login_session(user: User) -> None:
    session.clear()  # 세션 고정 방지
    session["user_id"] = user.id
    session["role"] = user.role
    user.last_login_at = datetime.now()
    db.session.commit()


def _redirect_by_role(user: User):
    if user.role == "admin":
        return redirect(url_for("admin.dashboard"))
    if user.role == "lawyer":
        if user.status != "active":
            return redirect(url_for("auth.pending"))
        return redirect(url_for("lawyer_admin.dashboard"))
    next_url = request.args.get("next") or request.form.get("next")
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect(url_for("main.index"))


def _authenticate(email: str, password: str, template: str, **ctx):
    """공통 로그인 처리. 실패 시 렌더된 응답, 성공 시 User 반환."""
    if _is_locked(email):
        flash("로그인 5회 실패로 잠금되었습니다. 10분 후 다시 시도해주세요.", "error")
        return None, render_template(template, **ctx)

    user = User.query.filter_by(email=email).filter(User.deleted_at.is_(None)).first()
    if (
        user is None
        or user.status == "withdrawn"
        or not user.check_password(password)
    ):
        _record_fail(email)
        flash("이메일 또는 비밀번호가 올바르지 않습니다.", "error")
        return None, render_template(template, **ctx)

    if user.status == "suspended":
        flash(f"정지된 계정입니다. {user.status_reason or ''}", "error")
        return None, render_template(template, **ctx)

    cache.delete(_fail_key(email))
    return user, None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return _redirect_by_role(g.user)
    tab = request.values.get("tab", "user")
    ctx = {"active_menu": None, "tab": tab, "next": request.values.get("next", "")}
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user, fail_resp = _authenticate(email, password, "auth/login.html", **ctx)
        if user is None:
            return fail_resp
        if user.role == "admin":
            # 총관리자는 /admin/login 전용
            flash("관리자 계정은 관리자 로그인 페이지를 이용해주세요.", "error")
            return render_template("auth/login.html", **ctx)
        _login_session(user)
        return _redirect_by_role(user)
    return render_template("auth/login.html", **ctx)


@bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if g.user and g.user.role == "admin":
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user, fail_resp = _authenticate(email, password, "admin/login.html")
        if user is None:
            return fail_resp
        if user.role != "admin":
            _record_fail(email)
            flash("관리자 계정이 아닙니다.", "error")
            return render_template("admin/login.html")
        _login_session(user)
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.index"))


def _validate_signup_common(form, *, require_name=False):
    """가입 공통 검증. 오류 메시지 리스트 반환(비면 통과)."""
    errors = []
    email = form.get("email", "").strip()
    password = form.get("password", "")
    phone = form.get("phone", "").strip()
    if not EMAIL_RE.match(email):
        errors.append("올바른 이메일을 입력해주세요.")
    elif User.query.filter_by(email=email).first():
        errors.append("이미 가입된 이메일입니다.")
    if len(password) < 8:
        errors.append("비밀번호는 8자 이상이어야 합니다.")
    elif password != form.get("password2", ""):
        errors.append("비밀번호 확인이 일치하지 않습니다.")
    if not phone:
        errors.append("휴대폰 번호를 입력해주세요.")
    if require_name and not form.get("name", "").strip():
        errors.append("실명을 입력해주세요.")
    return errors


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if g.user:
        return redirect(url_for("main.index"))
    ctx = {"active_menu": None, "form": request.form}
    if request.method == "POST":
        errors = _validate_signup_common(request.form)
        nickname = request.form.get("nickname", "").strip() or None
        if nickname and User.query.filter_by(nickname=nickname).first():
            errors.append("이미 사용 중인 닉네임입니다.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("auth/signup.html", **ctx)

        user = User(
            email=request.form["email"].strip(),
            name=request.form.get("name", "").strip() or None,
            nickname=nickname,
            phone=request.form["phone"].strip(),
            role="user",
            status="active",  # 일반회원 즉시 가입
        )
        user.set_password(request.form["password"])
        db.session.add(user)
        db.session.commit()
        _login_session(user)
        flash("가입이 완료되었습니다. 환영합니다!", "success")
        return redirect(url_for("main.index"))
    return render_template("auth/signup.html", **ctx)


@bp.route("/signup/lawyer", methods=["GET", "POST"])
def signup_lawyer():
    if g.user:
        return redirect(url_for("main.index"))
    ctx = {"active_menu": None, "form": request.form}
    if request.method == "POST":
        errors = _validate_signup_common(request.form, require_name=True)
        license_no = request.form.get("license_no", "").strip()
        firm_name = request.form.get("firm_name", "").strip()
        if not license_no:
            errors.append("변호사 등록번호를 입력해주세요.")
        if not firm_name:
            errors.append("소속(로펌·사무소명)을 입력해주세요.")

        files = [f for f in request.files.getlist("verification_files") if f.filename]
        allowed = current_app.config["ALLOWED_UPLOAD_EXTENSIONS"]
        if not files:
            errors.append("인증 서류를 1개 이상 업로드해주세요.")
        else:
            for f in files:
                ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
                if ext not in allowed:
                    errors.append(
                        "인증 서류는 jpg, jpeg, png, pdf 형식만 업로드할 수 있습니다."
                    )
                    break

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("auth/signup_lawyer.html", **ctx)

        user = User(
            email=request.form["email"].strip(),
            name=request.form["name"].strip(),
            phone=request.form["phone"].strip(),
            role="lawyer",
            status="pending",  # 관리자 승인 후 활성
        )
        user.set_password(request.form["password"])
        db.session.add(user)
        db.session.flush()

        db.session.add(
            LawyerProfile(user_id=user.id, license_no=license_no, firm_name=firm_name)
        )

        # 인증 서류: static 밖 저장, 원본 파일명 미사용 (admin 전용 서빙 — §11)
        upload_dir = os.path.join(
            current_app.config["UPLOAD_FOLDER"], "verification", str(user.id)
        )
        os.makedirs(upload_dir, exist_ok=True)
        for f in files:
            ext = f.filename.rsplit(".", 1)[-1].lower()
            fname = f"{uuid.uuid4().hex}.{ext}"
            f.save(os.path.join(upload_dir, fname))
            db.session.add(
                LawyerVerificationFile(
                    user_id=user.id,
                    file_url=f"verification/{user.id}/{fname}",
                    file_type=ext,
                )
            )
        db.session.commit()
        _login_session(user)
        return redirect(url_for("auth.pending"))
    return render_template("auth/signup_lawyer.html", **ctx)


@bp.route("/auth/pending")
def pending():
    if g.user is None or g.user.role != "lawyer":
        return redirect(url_for("auth.login"))
    return render_template("auth/pending.html", active_menu=None)
