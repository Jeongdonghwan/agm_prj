# -*- coding: utf-8 -*-
"""커뮤니티 게시판 트리 초기 데이터 — seed.py(새 DB)와 migrate.py(기존 DB)가 공유.

community_boards 테이블이 비어 있을 때만 넣는다(재실행 안전).
이후 추가/삭제는 어드민 [게시판 관리]에서 하며 이 파일은 다시 쓰이지 않는다.
"""

# (그룹 라벨, [항목…]) — 항목: {"slug","label","topics","admin_only"} 게시판 | {"label","url"} 링크
SEED_BOARD_TREE = [
    ("안내", [
        {"slug": "ad-inquiry", "label": "광고 및 협업 문의"},
        {"slug": "notice-angimo", "label": "안기모 공지사항", "admin_only": True},
        {"slug": "notice-community", "label": "커뮤니티 공지사항", "admin_only": True},
    ]),
    ("상담소", [
        {"slug": "parole", "label": "가석방관련 상담신청"},
    ]),
    ("커뮤니티", [
        {"slug": "suggest", "label": "커뮤니티 건의사항"},
        {"slug": "letter", "label": "편지발송 인터넷 서신"},
        {"slug": "faq", "label": "자주 묻는 질문 FAQ", "admin_only": True},
        {"slug": "ask", "label": "아뭇따 질문!"},
        {"slug": "trial-qna", "label": "형사재판 절차 QnA"},
        {"slug": "prison-qna", "label": "교정기관생활 QnA"},
        {"slug": "cheer", "label": "위로 칭찬 격려 축하 해주세요"},
        {"slug": "market", "label": "안기모 중고세상"},
        {"slug": "envelope", "label": "나의 대봉투 꾸미기"},
        {"label": "교정기관 식단표", "url": "/community/board/life?topic=교정기관 식단표"},
    ]),
    ("양식 자료실", [
        {"slug": "forms", "label": "양식 자료실", "topics": [
            "탄원서", "반성문", "합의서", "서류 모음",
            "다운로드 자료실", "고소취하서", "영장실질심사의견서", "구속적부심사청구서",
            "보석허가청구서", "항소이유서·답변서", "형사소송 주요판례", "책자발송신청게시판",
        ]},
    ]),
    ("교정시설 정보", [
        {"slug": "facility", "label": "교정시설 정보", "show_topics": False, "topics": [
            "접견 가능 시간", "영치금 계좌", "우편 주소", "택배 가능 여부", "자주 묻는 질문",
        ]},
        {"slug": "life", "label": "수용생활 정보", "show_topics": False, "topics": [
            "초범 가족 안내", "이감 절차", "영치품", "교도소 생활", "출소 절차", "교정기관 식단표",
        ]},
        {"slug": "prison", "label": "교정기관별 게시판", "topics": [
            "서울,남부교&구,동부", "수원,안양,평택지소", "여주,화성,소망,인천",
            "강원북부,강릉,춘천", "의정부,영월,원주", "대구,상주,경주,포항",
            "경북북부제123.김천", "경북직훈,안동,울산", "부산교&구,통영,거창",
            "창원,진주,밀양,정읍", "대전,논산,공주,충주", "천안,청주,홍성,서산",
            "광주,전주,군산,제주", "목포,순천,장흥,해남",
        ]},
    ]),
    ("단계별 소통게시판", [
        {"slug": "stage", "label": "단계별 소통게시판", "topics": [
            "체포·유치장·구속단계", "경찰·검찰수사중단계", "기소후 1심재판 단계",
            "1심 판결선고후 단계", "항소·상고진행중단계", "재판종료·형확정단계",
        ]},
    ]),
    ("공지사항", [
        {"slug": "petition", "label": "징계청원 게시판"},
    ]),
    ("도움되는 사이트", [
        {"label": "전국 교정기관 주소", "url": "https://www.moj.go.kr/corrections/1125/subview.do"},
        {"label": "대법원 나의사건검색", "url": "https://www.scourt.go.kr/portal/information/events/search/search.jsp"},
        {"label": "KICS 형사사법포털", "url": "https://www.kics.go.kr/"},
        {"label": "양형기준 양형위원회", "url": "https://sc.scourt.go.kr/sc/krsc/criterion/down/standard_down.jsp"},
        {"label": "출소자 법무보호사업", "url": "https://koreha.or.kr/"},
    ]),
]


def seed_boards(db):
    """community_boards가 비어 있으면 초기 트리 삽입. 넣은 게시판 수 반환."""
    from models import CommunityBoard

    if CommunityBoard.query.count():
        return 0
    n = 0
    for gi, (group_label, items) in enumerate(SEED_BOARD_TREE):
        grp = CommunityBoard(label=group_label, sort_order=gi)
        db.session.add(grp)
        db.session.flush()
        for ii, it in enumerate(items):
            db.session.add(CommunityBoard(
                parent_id=grp.id,
                label=it["label"],
                slug=it.get("slug"),
                topics=it.get("topics") or [],
                admin_only=it.get("admin_only", False),
                show_topics=it.get("show_topics", True),
                link_url=it.get("url"),
                sort_order=ii,
            ))
            n += 1
    db.session.commit()
    return n
