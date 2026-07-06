from flask import Blueprint

# 경량 AJAX 전용 (/api/*) — Phase 2부터 엔드포인트 추가
bp = Blueprint("api", __name__)
