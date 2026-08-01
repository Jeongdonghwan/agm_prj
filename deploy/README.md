# 배포 메모 (Cafe24 가상서버, gunicorn + nginx)

1. 서버에 `/srv/angimo` 로 코드 배치, `python -m venv .venv && .venv/bin/pip install -r requirements.txt gunicorn`
2. MariaDB 계정 분리 생성 후 `.env` 작성 (SECRET_KEY 교체, `SESSION_COOKIE_SECURE=1`)
3. `python seed.py` (최초 1회 — drop_all 후 재시드이므로 운영 중 재실행 금지)

## 이후 배포 (데이터 보존)

```bash
cd /var/www/angimo && git pull
.venv/bin/python migrate.py      # 모델에 컬럼이 늘었을 때만 실제 ALTER 실행(여러 번 실행해도 안전)
sudo systemctl restart angimo
```

⚠️ `seed.py`는 전체 테이블을 지우고 데모 데이터로 다시 만든다. 운영 데이터가 생긴 뒤에는
**절대 실행하지 말고** `migrate.py`로 스키마만 맞출 것. 새 컬럼은 `migrate.py`의
`MIGRATIONS` 목록에 (테이블, 컬럼, 정의) 한 줄을 추가해 관리한다.

4. `gunicorn.service.example` → systemd 등록, `nginx.conf.example` → nginx 사이트 등록
5. 멀티워커 환경에서는 `config.py`의 `CACHE_TYPE`을 `FileSystemCache`로 교체
   (로그인 잠금 카운터·페이지 캐시가 워커 간 공유되어야 함)
6. `/uploads/verification` 는 nginx에서 반드시 deny (인증 서류는 admin 라우트로만, §11)
