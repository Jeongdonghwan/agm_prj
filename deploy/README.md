# 배포 메모 (Cafe24 가상서버, gunicorn + nginx)

1. 서버에 `/srv/angimo` 로 코드 배치, `python -m venv .venv && .venv/bin/pip install -r requirements.txt gunicorn`
2. MariaDB 계정 분리 생성 후 `.env` 작성 (SECRET_KEY 교체, `SESSION_COOKIE_SECURE=1`)
3. `python seed.py` (최초 1회 — drop_all 후 재시드이므로 운영 중 재실행 금지)
4. `gunicorn.service.example` → systemd 등록, `nginx.conf.example` → nginx 사이트 등록
5. 멀티워커 환경에서는 `config.py`의 `CACHE_TYPE`을 `FileSystemCache`로 교체
   (로그인 잠금 카운터·페이지 캐시가 워커 간 공유되어야 함)
6. `/uploads/verification` 는 nginx에서 반드시 deny (인증 서류는 admin 라우트로만, §11)
