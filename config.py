import json
import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "angimo")

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        "?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # JSON 컬럼 한글을 \uXXXX 이스케이프 없이 저장 — JSON_CONTAINS 한글 비교를 위해 필수
    SQLALCHEMY_ENGINE_OPTIONS = {
        "json_serializer": lambda obj: json.dumps(obj, ensure_ascii=False)
    }

    # 업로드: 인증 서류는 static 밖 — admin 전용 라우트로만 서빙 (CLAUDE.md §11)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB
    ALLOWED_UPLOAD_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    SESSION_COOKIE_SAMESITE = "Lax"

    # 로그인 잠금·페이지 캐시 겸용. 배포(gunicorn 멀티워커) 시 FileSystemCache로 교체
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 120

    # 정적 자산 Cache-Control 30일 (§2-2). 배포 시 nginx가 /static 직접 서빙
    SEND_FILE_MAX_AGE_DEFAULT = 60 * 60 * 24 * 30

    # 브랜드 (템플릿 하드코딩 금지 — §11)
    SITE_NAME = "안기모"
    SITE_NAME_EN = "ANGIMO"

    # 로그인 실패 잠금 정책 (§2)
    LOGIN_FAIL_LIMIT = 5
    LOGIN_LOCK_SECONDS = 600
