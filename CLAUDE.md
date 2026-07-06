# 안기모 (ANGIMO) — 전체 개발 스펙 v3 (CLAUDE.md)

> 로톡 벤치마킹 법률 플랫폼 — **초기 데모 버전 스코프**.
> 핵심 원칙: **예약/결제/후기 등 트랜잭션 기능 없음. 콘텐츠 + 프로필 중심.**
> 이용자는 변호사 프로필을 보고 **사이트 밖에서 직접 연락**(사무소 전화 / 카카오톡)한다.
> Claude Code 개발 시 항상 참조하는 단일 기준 문서.
> **시안 세트(12장 + icons/):** index / lawyers(분야찾기) / lawyers-list(변호사리스트) / lawyer-detail(프로필) / firms / counsel / posts / cases / news / community / lawyer-admin / admin + `icons/` 3D 아이콘 15종
> **개발 시작 방법:** 이 폴더를 프로젝트 루트에 두고 "CLAUDE.md를 읽고 §11 Phase 1부터 순서대로 구현해. 화면은 시안 HTML을 Jinja 템플릿(base.html 상속 + static 분리)으로 그대로 이식해." 라고 지시.

---

## 1. 데모 버전 스코프 (가장 중요)

**포함:**
- 회원 3종 (일반 / 변호사[승인제] / 총관리자)
- 변호사가 프로필을 작성하면 **프로필 페이지 자동 생성** → 이용자가 보고 직접 연락
- 변호사포스트 (변호사 작성 → 관리자 검수 → 게시)
- 상담사례 Q&A (일반회원 질문 → 변호사 답변, 단순 게시판 수준)
- 커뮤니티 (일반회원 글/댓글/추천, 익명 옵션)
- 관리자 콘텐츠: 판례돋보기 / 안기모뉴스 / 로펌 광고 / 배너 / 카테고리·지역 마스터

**제외 (구현 금지 — 스코프 크리프 방지):**
- ❌ 상담 예약 / 시간 슬롯 / 예약 캘린더
- ❌ 결제 / PG
- ❌ 의뢰인 후기 / 평점
- ❌ 실시간 채팅 / 알림 푸시
- ❌ 소셜 로그인 (추후)

## 2. 기술 스택 / 프로젝트 구조 (SEO 최우선 — SSR 멀티페이지)

- **렌더링: Flask + Jinja2 서버사이드 렌더링(MPA).** React/SPA 사용 금지 — 네이버(Yeti) 크롤링과 페이지별 meta 태그를 위해 모든 공개 페이지는 서버에서 완성된 HTML로 응답한다.
- Backend: Flask (Blueprint) + SQLAlchemy + PyMySQL / DB: MariaDB
- 인증: **Flask 세션 쿠키**(httpOnly, secure) + bcrypt. 로그인 5회 실패 시 10분 잠금
- 인터랙션: 시안 HTML의 vanilla JS 그대로 사용(탭 전환, 배너 롤링 등). 추천/좋아요·닉네임 중복확인 같은 부분 갱신만 fetch로 경량 /api 호출
- 어드민(변호사/총관리자)도 동일하게 Jinja 렌더링 (SEO 무관하지만 스택 통일)
- 업로드: `/uploads` 로컬 (인증 서류는 admin 전용 라우트로만 서빙) / 배포: Cafe24 가상서버 + gunicorn + nginx

```
angimo/
├── app.py / config.py / extensions.py
├── models/            # user, lawyer, consultation, content, community, ops
├── routes/            # 페이지 Blueprint: main, lawyers, counsel, contents, community, auth, mypage
│                      # 어드민 Blueprint: lawyer_admin(/lawyer), admin(/admin)
│                      # api Blueprint: 경량 AJAX 전용 (/api/*)
├── templates/
│   ├── base.html          # 공통: 띠배너/헤더/GNB/푸터 + {% block meta %}{% block content %}
│   ├── base_admin.html    # 어드민 공통: 사이드바 레이아웃
│   ├── main/ lawyers/ counsel/ contents/ community/ auth/ mypage/
│   └── lawyer_admin/ admin/
├── static/
│   ├── css/tokens.css + 페이지별 css (시안 <style> 분리)
│   ├── js/ (탭/롤링/모달 등 시안 스크립트 분리)
│   └── icons/ (Fluent 3D PNG 15종 — 시안 icons/ 그대로 복사)
└── CLAUDE.md
```

### 2-1. SEO 필수 구현 (모든 공개 페이지)
- 페이지별 고유 `<title>` / `<meta description>` / OG 태그 / canonical URL — base.html의 meta 블록으로 각 템플릿에서 지정
- 상세 페이지 URL에 슬러그 포함: `/lawyers/12-김OO`, `/counsel/345-전세보증금-반환`, `/cases/…`, `/news/…`
- **JSON-LD 구조화 데이터**: 변호사 프로필(Person/Attorney + LocalBusiness), 뉴스(NewsArticle), 상담글(QAPage)
- `sitemap.xml` 동적 생성(변호사/상담글/판례/뉴스/커뮤니티 URL 포함, 신규 글 자동 반영) + `robots.txt`
- 페이지네이션은 쿼리스트링(`?page=2`) + rel prev/next, 목록도 서버 렌더링
- 이미지 alt, 시맨틱 태그(h1은 페이지당 1개), 응답은 gzip

### 2-2. 성능 규칙
- **Flask-Caching**: 메인 페이지·목록 페이지(판례/뉴스/변호사 리스트) 60~300초 캐시, 글 작성/수정 시 해당 캐시 무효화
- 정적 자산(css/js/icons) Cache-Control 헤더 30일 + 파일명 버저닝, 이미지 lazy loading(`loading="lazy"`)
- 목록 쿼리는 반드시 LIMIT + 인덱스 사용(스키마의 idx_* 활용), N+1 금지(joinedload)
- 메인 페이지는 섹션별 쿼리를 하나의 서비스 함수로 묶어 한 번에 렌더링
- **nginx가 /static, /uploads를 직접 서빙**(Flask 미경유), gunicorn worker 수 = CPU코어×2+1

## 3. 디자인 시스템

```css
:root{
  --blue-900:#0A2A5E; --blue-700:#0F47C2; --blue-600:#1B5CFF; /* 프라이머리 */
  --blue-100:#E9F0FF; --blue-050:#F4F8FF;
  --ink-900:#191F28; --ink-500:#6B7684; --ink-200:#E5E8EB;
  --red-500:#FF4B4B; /* NEW 뱃지·삭제 버튼 전용 */
  --radius-lg:16px; --radius-md:12px; --radius-sm:8px;
  --shadow-card:0 2px 10px rgba(10,42,94,.06);
}
```

- Pretendard / lucide-react / 컨테이너 1080px / 브레이크포인트 960px
- 카운터는 아이콘 없이 텍스트: `조회 1,024 · 댓글 18 · 추천 32`
- GNB: **커뮤니티가 첫 메뉴**, NEW 뱃지는 글자 위 중앙 — **positioning은 `nav.gnb .badge-new`로 스코프 한정**(absolute, top:2px, left:50% translateX(-50%)). 기본 `.badge-new`는 배경/폰트만 정의(다른 위치에서 인라인 배치 가능해야 함)
- 헤더 우측 유틸(오늘의집 스타일): `로그인 | 회원가입 | 고객센터`(얇은 구분선) + **[글쓰기 ▾] blue-600 버튼**(클릭 시 상담글/커뮤니티 글 선택 드롭다운). 상단 유틸바(topbar)는 제거, 대신 **최상단 띠배너** 사용
- 어드민: blue-900 사이드바 240px (시안 lawyer-admin.html / admin.html)
- **시안 HTML을 Jinja 템플릿으로 그대로 이식할 것** (공통 부분은 base.html 블록으로, CSS/JS는 static으로 분리)

## 4. 역할별 기능 정의 (★ 이 표가 전체 기획의 기준)

### 4-1. 비회원 (누구나)
| 기능 | 설명 |
|---|---|
| 모든 콘텐츠 열람 | 메인, 변호사 목록/프로필, 상담사례, 변호사포스트, 판례, 뉴스, 로펌, 커뮤니티 열람 |
| 변호사에게 연락 | 프로필의 **사무소 전화(tel: 링크) / 카카오톡 채널(외부 링크)** 클릭 — 사이트는 클릭 수만 기록 |
| 로펌 간편 문의 | 이름/연락처/내용 폼 → 관리자 접수함으로 |

### 4-2. 일반회원 (user) — 즉시 가입
| 기능 | 설명 |
|---|---|
| 가입/로그인 | 이메일+비번+휴대폰(닉네임은 선택 입력), 즉시 active |
| 상담사례 질문 작성 | 제목/내용/분야, 공개·비공개 선택. 수정/삭제는 답변 달리기 전까지만 |
| 커뮤니티 | 글/댓글/대댓글 작성, 추천(글당 1회), 신고, **익명 옵션** |
| **닉네임 설정 (커뮤니티 이용 조건)** | 닉네임 미설정 상태에서 커뮤니티 글/댓글 작성 시도 시 → **닉네임 설정 모달** 표시(2~10자 한글/영문/숫자, 실시간 중복 확인, 금칙어 필터). 설정 완료 후 작성 이어서 진행. 이후 변경은 마이페이지에서 30일 1회 |
| 마이페이지 | 내 상담글, 내 커뮤니티 글/댓글, 정보 수정, 탈퇴 |

### 4-3. 변호사회원 (lawyer) — 승인제 가입
| 기능 | 설명 |
|---|---|
| 가입 신청 | 이메일/비번/실명/휴대폰 + **변호사 등록번호 + 소속 + 인증 서류 업로드** → `pending` (로그인 시 "승인 대기 중"만 표시) → 관리자 승인 후 활성 |
| 프로필 관리 → **프로필 페이지 자동 생성** | 아래 4-3-1 필드 저장 즉시 `/lawyers/:id` 공개 페이지 생성/갱신. 필수 필드(사진·헤드라인·분야·연락처) 미완성 시 목록 미노출 |
| 상담사례 답변 | 내 분야 매칭 피드에서 답변 작성 (상담글당 변호사 1인 1답변) |
| 변호사포스트 작성 | 해결사례/법률가이드/법률동영상/변호사에세이 → 저장 시 `pending` → **관리자 검수 후 게시**. 해결사례는 본인 프로필 페이지에도 자동 노출 |
| 커뮤니티 | **열람만** (역할 혼선 방지) |
| 계정 설정 | 비번 변경, 소속 변경 |

**4-3-1. 변호사 프로필 필드 (로톡 프로필 페이지 구조 기준):**
- 헤드라인 (예: "서울대 법대, 형사사건 전담 파트너 변호사") — 프로필 페이지 대제목
- 프로필 사진 / 실명(가입 시) / 소속(로펌·사무소명) / 소속 변호사회
- **사무실 전화** / **카카오톡 채널 URL** ← 연락 수단 (둘 중 하나 필수)
- 사무소 주소 (+ 네이버 지도 링크 자동 생성)
- 분야: categories에서 최대 7개 선택 / 지역 1개
- 경력: [{연도, 내용}] 반복 입력 / 상세 소개(에디터)

### 4-4. 총관리자 (admin) — DB 시드로만 생성, `/admin/login` 별도
| 메뉴 | 기능 |
|---|---|
| 대시보드 | 통계 카드(총회원/변호사/오늘 상담글/**승인 대기 N**), 승인 대기 목록, 검수 대기 포스트, 최근 신고 |
| 회원 관리 | 일반회원 검색/정지/해제/탈퇴 처리, 메모 |
| 변호사 관리 | **승인 대기 탭**: 서류 이미지 뷰어 + 승인/반려(사유) / 전체 탭: 프로필 강제 수정, 노출 정지, **분야(카테고리) 지정·수정** |
| 상담 관리 | 상담글/답변 숨김·삭제, 신고 글 우선 표시 |
| 커뮤니티 관리 | 글/댓글 숨김·삭제, 신고 처리(경고/숨김/제재), 커뮤니티 카테고리 관리, **공지글 작성**(상단 고정) |
| 콘텐츠 관리 | ① 변호사포스트 검수(승인/반려+사유) ② **판례돋보기 직접 CRUD** ③ **안기모뉴스 직접 CRUD**(썸네일·해시태그) ④ 분야(2-depth)·지역 마스터 관리 |
| 배너 관리 | 메인 히어로 배너 CRUD: 이미지/링크/기간/순서/on-off |
| 로펌 광고 관리 | firm_ads CRUD(로펌명/헤드라인/소개/링크칩/사진/주소/분야/기간/순서) + **간편 문의 접수함**(처리 상태) |
| 신고/문의 | 신고 통합 목록 처리 |
| 운영 로그 | admin_logs 열람 |

## 5. 사용자 화면 페이지 스펙 (시안 1:1)

| 시안 | 라우트 | 데모 스펙 |
|---|---|---|
| index.html | `/` | **로톡 구조 그대로 + 스킨만 차별화.** 섹션 순서: **최상단 띠배너**(blue-600 풀폭, "지금 가입하면 첫 상담 100% 지원!" + 티켓 아이콘, 배너관리 연동) → 헤더/GNB → 히어로(좌 배너+우 위젯) → **통합 콘텐츠 탭 "지금 안기모에서는"**(커뮤니티 인기글/판례돋보기/최신 상담글/변호사 해결사례 — 4탭 전환, 활성 탭 blue-900 필 pill, 페이드 전환, 패널별 더보기 pill) → 분야 그리드(**카테고리별 파스텔 스쿼클 + Microsoft Fluent Emoji 3D 아이콘(PNG)**: `/icons/*.png` 15종을 그대로 사용 — sex-crime(경광등)/property(돈주머니)/traffic(자동차)/criminal(경찰관)/assault(충돌)/defame(말풍선)/etc-criminal(경찰차)/realestate(집)/contract(영수증)/civil(클립보드)/etc-civil(저울)/family(깨진하트)/company(빌딩)/medical(병원)/it(노트북). MIT 라이선스, 상업 이용 가능. **이식 시 `static/icons/`로 복사해서 사용**, hover 시 떠오르는 효과) → 지역 → 요즘 활발한 변호사 → 새로 함께하는 변호사 → 푸터. **스킨 규칙(전 페이지 공통 적용):** 섹션 타이틀 좌측 5px 블루 액센트 바 / 히어로 배너 네이비 단색+원형 패턴, radius 22px / 사이드 카드 blue-050 필(보더 없음) / 분야 아이콘 스쿼클(radius 18px) 그라디언트, hover 시 blue-600 채움 / 지역 버튼 필(pill) / 판례 카드 풀보더 대신 좌측 3px 블루 바+하단 라인 / 커뮤니티 카드 상단 3px 블루 액센트 / 최신 상담글 blue-050 소프트 카드 / 더보기 버튼 blue-050 필 / 결과 뱃지 blue-100 필 pill / 검색바 blue-050 필 배경(보더 없음) |
| lawyers.html | `/lawyers` | **1단계 — 분야로 찾기:** 중앙 분야로/지역으로 찾기 토글, 좌측 분야 리스트, 분야별 섹션(세부분야 2열). **세부분야 클릭 → 2단계 리스트로 이동** |
| lawyers-list.html | `/lawyers/list?category=` | **2단계 — 변호사 리스트 (검색결과형):** 상단 추천키워드 칩 → **맞춤 법률 정보 박스**(해당 분야 해결사례 6개, 2열 + 변호사 미니 아바타) → 변호사 N명: **AD LAWYERS 카드**(대형 사진, 강점 뱃지, 이름/소속, #해시태그, 광고 카피, 관련분야 해결사례·답변 수, 전화/카톡 아이콘 버튼 + [프로필 보기]) → **LAWYERS 일반 리스트**(이름/소속/헤드라인 blue + 간편 문의·전화·카톡 버튼 + 원형 사진) → "변호사 N명 더보기". 우측 sticky: 연락 방법 안내 카드(사무소 전화/카톡/온라인 상담글). **변호사 클릭 → 3단계 프로필** |
| lawyer-detail.html | `/lawyers/:id` | **3단계 — 프로필 페이지 (미니멀 디자인, 시안이 기준):** 사이트 GNB 대신 **전용 미니멀 탭바**(로고 마크 + 변호사홈/변호사정보/해결사례/사무소 안내 + 목록으로) / 헤드라인 대제목(34px, 마침표 blue) / **기본정보 2단 텍스트 블록(카드·보더 없음)**: 좌 이름·소속·주소·사무실전화, 우 라벨행 분야(blue 링크)·자격·소속회·학력 / **간편 문의 박스**(가운데 정렬, new 뱃지 + "정식 상담이 고민된다면, 먼저 가볍게 문의해보세요" + 아웃라인 [사무소 전화]·[카카오톡 문의] + 안내문구) / 해결사례 **라인 리스트**(결과뱃지 + 제목 + 우측 화살표) / 소개·경력(연도 리스트) / 사무소 안내(로펌명+홈페이지 링크, 주소, 네이버 지도로 보기, 지도 영역). **우측 sticky 카드: 다크 그레이(#3A414B) 헤더(이름·소속+별/공유 아이콘) → 대형 프로필 사진 → "비용 부담 없이 지금 바로 문의하기" 필 → [전화 문의하기(tel:)] 연파랑 대형 버튼 → 사무소 전화/카카오톡 미니 버튼 → 조회/사례/답변 스탯.** 이벤트 배너·상담 스타일 게이지는 제외(구현 금지) |
| firms.html | `/firms` | 분야 칩 + firm_ads(기간 유효+active, sort_order) + 간편 문의 모달 → 관리자 접수 |
| counsel.html | `/counsel`, `/counsel/:id` | 질문 목록(최신답변/최신질문/조회순) + 작성(로그인) + 상세(질문+답변들+답변 변호사 미니 프로필 카드→프로필 링크) + 우측 활발한 변호사 랭킹(최근 30일 답변수) |
| posts.html | `/posts`, `/posts/:id` | published 포스트만, 서브탭=type 필터, 상세에 작성 변호사 프로필 카드 |
| cases.html | `/cases`, `/cases/:id` | 판례 목록 + 분야/사건종류 필터 |
| news.html | `/news`, `/news/:id` | 뉴스 목록/상세, 해시태그 필터 |
| community.html | `/community`, `/community/:id` | 카테고리 칩 + 최신/인기 탭 + 글쓰기 + 상세(댓글/추천/신고) + 인기 TOP5(24h 조회+추천×3) + 공지 고정 |
| 신규 | `/login` `/signup` `/signup/lawyer` `/mypage` | §4 참조. 로그인 탭 2개(일반/변호사) |

## 6. DB 스키마 (데모 버전 — 17개 테이블)

```sql
-- 회원
CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(120) UNIQUE NOT NULL,
  password_hash VARCHAR(200) NOT NULL,
  name VARCHAR(50),
  nickname VARCHAR(50) UNIQUE,               -- NULL 허용, 커뮤니티 작성 시 필수(모달로 설정)
  nickname_changed_at DATETIME,              -- 변경 30일 제한용
  phone VARCHAR(20),
  role ENUM('user','lawyer','admin') DEFAULT 'user',
  status ENUM('active','pending','rejected','suspended','withdrawn') DEFAULT 'active',
  status_reason VARCHAR(300),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_login_at DATETIME, deleted_at DATETIME
);

CREATE TABLE lawyer_profiles (
  user_id INT PRIMARY KEY,
  license_no VARCHAR(30) NOT NULL,
  headline VARCHAR(100),                    -- 프로필 대제목
  firm_name VARCHAR(100), bar_association VARCHAR(50),
  photo_url VARCHAR(300),
  office_phone VARCHAR(30), kakao_url VARCHAR(300),  -- 연락 수단(둘 중 하나 필수)
  address VARCHAR(200),
  intro_full TEXT, career JSON,             -- [{year,text}]
  region_id INT,
  view_count INT DEFAULT 0,
  contact_click_count INT DEFAULT 0,        -- 전화/카톡 클릭 합산
  is_visible TINYINT DEFAULT 1,
  approved_at DATETIME,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE lawyer_verification_files (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL, file_url VARCHAR(300), file_type VARCHAR(30),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 마스터 (관리자 관리)
CREATE TABLE categories (
  id INT AUTO_INCREMENT PRIMARY KEY,
  parent_id INT NULL, name VARCHAR(50), description VARCHAR(150), sort_order INT DEFAULT 0
);
CREATE TABLE regions (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(30), sort_order INT);
CREATE TABLE lawyer_categories (user_id INT, category_id INT, PRIMARY KEY(user_id, category_id));

-- 상담사례 Q&A
CREATE TABLE consultations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL, category_id INT,
  title VARCHAR(200), content TEXT,
  is_public TINYINT DEFAULT 1, views INT DEFAULT 0,
  status ENUM('open','hidden','deleted') DEFAULT 'open',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP, deleted_at DATETIME,
  INDEX idx_cat (category_id), INDEX idx_recent (created_at DESC)
);
CREATE TABLE consultation_answers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  consultation_id INT NOT NULL, lawyer_id INT NOT NULL,
  content TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, deleted_at DATETIME,
  UNIQUE KEY uq_one_answer (consultation_id, lawyer_id)
);

-- 콘텐츠
CREATE TABLE lawyer_posts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  lawyer_id INT NOT NULL,
  type ENUM('case','guide','video','essay'),
  title VARCHAR(200), content MEDIUMTEXT, thumbnail_url VARCHAR(300),
  result_badge VARCHAR(30),                 -- 해결사례용: 무죄/집행유예 등
  category_id INT, views INT DEFAULT 0,
  status ENUM('pending','published','rejected','hidden') DEFAULT 'pending',
  reject_reason VARCHAR(300),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP, published_at DATETIME, deleted_at DATETIME
);
CREATE TABLE legal_cases (                  -- 판례돋보기 (관리자)
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(200), summary VARCHAR(500), content MEDIUMTEXT,
  court VARCHAR(50), case_no VARCHAR(60),
  case_type ENUM('criminal','civil','administrative','constitutional','patent'),
  category_ids JSON, views INT DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP, deleted_at DATETIME
);
CREATE TABLE news (                         -- 안기모뉴스 (관리자)
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(200), content MEDIUMTEXT, thumbnail_url VARCHAR(300),
  hashtags JSON, reporter VARCHAR(50), views INT DEFAULT 0,
  published_at DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, deleted_at DATETIME
);

-- 커뮤니티
CREATE TABLE community_posts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL, category VARCHAR(30),
  title VARCHAR(200), content TEXT,
  is_anonymous TINYINT DEFAULT 0, is_notice TINYINT DEFAULT 0,
  views INT DEFAULT 0, likes INT DEFAULT 0,
  status ENUM('open','hidden','deleted') DEFAULT 'open',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP, deleted_at DATETIME,
  INDEX idx_popular (likes DESC, views DESC)
);
CREATE TABLE community_comments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  post_id INT NOT NULL, user_id INT NOT NULL, parent_id INT NULL,
  content TEXT, is_anonymous TINYINT DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP, deleted_at DATETIME
);
CREATE TABLE community_likes (post_id INT, user_id INT, PRIMARY KEY(post_id, user_id));

-- 광고/운영 (관리자)
CREATE TABLE banners (
  id INT AUTO_INCREMENT PRIMARY KEY,
  position ENUM('main_hero') DEFAULT 'main_hero',
  title VARCHAR(100), image_url VARCHAR(300), link_url VARCHAR(300),
  sort_order INT DEFAULT 0, is_active TINYINT DEFAULT 1,
  starts_at DATETIME, ends_at DATETIME
);
CREATE TABLE firm_ads (
  id INT AUTO_INCREMENT PRIMARY KEY,
  firm_name VARCHAR(100), headline VARCHAR(200), description TEXT,
  links JSON, photos JSON, address VARCHAR(200), category_id INT,
  sort_order INT DEFAULT 0, is_active TINYINT DEFAULT 1,
  starts_at DATETIME, ends_at DATETIME
);
CREATE TABLE firm_inquiries (
  id INT AUTO_INCREMENT PRIMARY KEY,
  firm_ad_id INT, name VARCHAR(50), phone VARCHAR(20), content VARCHAR(1000),
  status ENUM('new','processed') DEFAULT 'new',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE reports (
  id INT AUTO_INCREMENT PRIMARY KEY,
  reporter_id INT,
  target_type ENUM('community_post','community_comment','consultation','answer'),
  target_id INT, reason VARCHAR(300),
  status ENUM('new','done') DEFAULT 'new',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE admin_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  admin_id INT, action VARCHAR(60), target VARCHAR(100), detail JSON,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 7. API 설계

```
# auth
POST /api/auth/signup                 # 일반
POST /api/auth/signup/lawyer          # 변호사 (multipart 서류)
POST /api/auth/login | refresh | logout
GET  /api/auth/me

# public (비회원 열람 가능)
GET  /api/home                        # 메인 섹션 일괄
GET  /api/lawyers                     ?category=&region=&sort=&page=   # is_visible+프로필완성만
GET  /api/lawyers/:id                 # 프로필 + published 해결사례
POST /api/lawyers/:id/contact-click   # {type: phone|kakao} 카운트만 기록
GET/POST /api/consultations, GET /api/consultations/:id
POST /api/consultations/:id ← user 본인 수정/삭제(답변 전)
GET  /api/posts?type= | /api/posts/:id
GET  /api/cases | /api/news | /api/firms | /api/banners
POST /api/firms/:id/inquiry
GET/POST /api/community/posts, /:id/comments, /:id/like
POST /api/reports
GET  /api/me/* (마이페이지: consultations, community)
GET  /api/me/nickname/check?value=   # 닉네임 중복/금칙어 확인
PUT  /api/me/nickname                # 닉네임 설정/변경(30일 1회)
# 커뮤니티 글/댓글 POST 시 닉네임 미설정이면 409 {error:{code:"NICKNAME_REQUIRED"}} → 프론트에서 설정 모달 오픈

# lawyer-admin (@role_required('lawyer'), 본인 스코프)
GET  /api/lawyer-admin/dashboard      # 프로필 조회수, 연락 클릭수, 답변수, 포스트 상태
GET/PUT /api/lawyer-admin/profile
GET  /api/lawyer-admin/feed           # 내 분야 답변 대기 상담글
POST/PUT /api/lawyer-admin/answers
GET/POST/PUT/DELETE /api/lawyer-admin/posts

# admin (@role_required('admin'))
GET  /api/admin/dashboard
GET  /api/admin/users | POST .../:id/suspend|activate
GET  /api/admin/lawyers?status= | POST .../:id/approve|reject
PUT  /api/admin/lawyers/:id           # 프로필 강제수정, 분야 지정, 노출 정지
GET  /api/admin/verification-files/:id   # 서류 (admin 전용 서빙)
GET  /api/admin/consultations | POST .../:id/hide|delete
GET  /api/admin/community | POST .../:id/hide|delete | POST /api/admin/community/notice
GET  /api/admin/posts?status=pending | POST .../:id/approve|reject
CRUD /api/admin/cases, news, categories, regions, banners, firms
GET  /api/admin/firm-inquiries | POST .../:id/process
GET  /api/admin/reports | POST .../:id/done
GET  /api/admin/logs
```

규칙: 목록 `{items,total,page,per_page}` / 에러 `{error:{code,message}}` / 상세 GET 시 views+1

## 8. 권한 매트릭스

| 기능 | 비회원 | user | lawyer | admin |
|---|---|---|---|---|
| 콘텐츠 열람 / 연락 클릭 / 로펌 문의 | ✅ | ✅ | ✅ | ✅ |
| 상담 질문 작성 / 커뮤니티 글·댓글·추천 | ❌ | ✅ | ❌ | ✅ |
| 상담 답변 / 프로필 관리 / 포스트 작성 | ❌ | ❌ | ✅(본인) | ✅ |
| 포스트 검수 / 판례·뉴스·로펌·배너·카테고리 / 회원·변호사 관리 | ❌ | ❌ | ❌ | ✅ |

## 9. 변호사 어드민 메뉴 (시안 lawyer-admin.html — 5메뉴)

| 메뉴 | 라우트 | 기능 |
|---|---|---|
| 대시보드 | `/lawyer` | 통계 4카드(프로필 조회수 / **연락 클릭수(전화+카톡)** / 이번달 답변 / 게시중 포스트), 프로필 완성도 배너, 답변 대기 피드, 내 포스트 상태 |
| 프로필 관리 | `/lawyer/profile` | §4-3-1 전체 필드 + 실시간 미리보기 + 완성도 % |
| 상담 답변 | `/lawyer/answers` | 분야 매칭 피드 / 내 답변 목록 |
| 포스트 작성 | `/lawyer/posts` | 작성(타입/제목/본문/썸네일/결과뱃지/분야) → pending / 목록(게시중·검수대기·반려+사유) |
| 계정 설정 | `/lawyer/settings` | 비번, 소속 변경 |

## 10. 개발 단계 (Claude Code 실행 순서)

**Phase 1 — 기반**
1. Flask 스캐폴딩 + base.html/base_admin.html 공통 레이아웃(띠배너/헤더/GNB/푸터, 사이드바) + tokens.css
2. DB 17테이블 + 시드(분야 2-depth 전체, 지역 11, admin 계정, 더미 변호사 10·상담글 20·판례 8·뉴스 6·커뮤니티 15)
3. 인증: 가입 2종(변호사 서류 업로드), 로그인 탭 UI, 세션 인증 + 데코레이터, role별 리다이렉트

**Phase 2 — 변호사 프로필 (데모의 핵심)**
4. 변호사 어드민 레이아웃 + 프로필 관리(전체 필드 + 미리보기)
5. 프로필 공개 페이지 `/lawyers/:id` (시안 lawyer-detail.html 1:1) + 연락 클릭 카운트
6. 변호사 찾기(토글/분야/지역) + 목록 카드

**Phase 3 — 콘텐츠**
7. 변호사 포스트 작성 → 관리자 검수 플로우 → `/posts` 노출 + 프로필 해결사례 연동
8. 관리자 어드민 레이아웃 + 변호사 승인(서류 뷰어) + 판례/뉴스 CRUD → `/cases` `/news`
9. 배너 관리 → 메인 히어로 연동 / 로펌 광고 관리 + 접수함 → `/firms`

**Phase 4 — 게시판**
10. 상담사례: 질문 작성 → 변호사 답변 피드/작성 → 목록/상세
11. 커뮤니티 전체(글/댓글/추천/익명/신고/공지/인기 TOP5) + 관리자 게시판 관리·신고 처리

**Phase 5 — 마무리**
12. 메인 페이지 전체 연동(`/api/home`), 회원/마이페이지 마무리
13. SEO 마무리(§2-1 전체: JSON-LD, sitemap.xml, canonical, 슬러그 URL 점검), 반응형 QA, admin_logs, 배포(gunicorn+nginx)

각 Phase 완료 시 커밋 + 동작 확인 후 다음 진행.

## 11. 정책/주의사항

- 로톡 실제 콘텐츠 복사 금지 (구조만 벤치마킹)
- 프로필 연락처는 변호사 본인 입력 정보 — tel: 링크와 카카오 외부 링크로만 연결, 사이트 내 중개/결제 없음
- 커뮤니티/상담글 전화번호·주민번호 패턴 자동 마스킹, 익명 글은 어디서도 닉네임 미노출
- 인증 서류는 admin 전용 라우트로만 서빙 (공개 URL 금지)
- soft delete 원칙, 관리자 액션 admin_logs 자동 기록
- config.py + tokens.css 외 브랜드 하드코딩 금지
- **§1의 제외 목록 기능을 임의로 추가 구현하지 말 것**
