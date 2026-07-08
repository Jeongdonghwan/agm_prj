"""DB 생성 + 전체 테이블 + 시드 데이터 (멱등: 재실행 시 전체 재구축).

실행: .venv\\Scripts\\python seed.py  또는  flask seed
"""

import json
from datetime import datetime, timedelta

import pymysql

from config import Config


def ensure_database():
    """DB 자체가 없으면 생성 (root 등 서버 계정으로 접속)."""
    conn = pymysql.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{Config.DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


# ── 분야 2-depth (대분류 15 = index 아이콘 그리드 1:1, 시안 lawyers.html 세부 4종 포함) ──
CATEGORIES = [
    ("성범죄", [
        ("성매매", "조건만남, 랜덤채팅, 유흥업소, 유사성매매 등"),
        ("성폭력/강제추행 등", "성폭행, 준강간, 데이트폭력, 성희롱, 성추행 등"),
        ("미성년 대상 성범죄", "아동청소년보호법, 미성년성매매 등"),
        ("디지털 성범죄", "통신매체이용음란죄, 몰카, 음란물유포 등"),
    ]),
    ("재산범죄", [
        ("횡령/배임", "업무상 횡령/배임, 신용카드 범죄, 점유이탈물횡령 등"),
        ("사기/공갈", "보이스피싱, 명의 대여/도용, 유사수신, 중고사기 등"),
        ("기타 재산범죄", "절도, 주거침입, 재물손괴, 장물 등"),
    ]),
    ("교통사고/범죄", [
        ("교통사고/도주", "교통사고 합의, 손해사정, 뺑소니, 보복운전 등"),
        ("음주/무면허", "음주운전, 음주사고, 무면허운전 등"),
    ]),
    ("형사절차", [
        ("고소/소송절차", "합의, 무혐의, 공소시효, 고소대리, 약식명령, 즉결심판 등"),
        ("수사/체포/구속", "체포/구속, 현행범, 영장, 압수수색, 포렌식 등"),
    ]),
    ("폭행/협박", [
        ("폭행/상해", "단순폭행, 상해, 특수폭행, 쌍방폭행 등"),
        ("협박", "협박죄, 특수협박, 공갈성 협박 등"),
        ("스토킹/데이트폭력", "스토킹처벌법, 접근금지, 데이트폭력 등"),
    ]),
    ("명예훼손/모욕", [
        ("명예훼손", "사실적시/허위사실 명예훼손, 출판물 명예훼손 등"),
        ("모욕", "모욕죄 고소/방어, 집단 모욕 등"),
        ("사이버 명예훼손", "SNS/커뮤니티 게시글, 댓글, 단톡방 등"),
    ]),
    ("기타 형사범죄", [
        ("마약", "단순 투약, 소지, 매매, 재범 등"),
        ("도박", "온라인 도박, 도박장 개설, 상습도박 등"),
        ("소년사건", "소년보호처분, 학교폭력, 촉법소년 등"),
        ("병역/군형법", "병역기피, 군무이탈, 군내 사건 등"),
    ]),
    ("부동산/임대차", [
        ("주택/상가 임대차", "보증금 반환, 계약갱신, 권리금, 명도 등"),
        ("부동산 매매/소유권", "매매 분쟁, 소유권이전, 등기, 하자담보 등"),
        ("재개발/재건축", "조합 분쟁, 분양권, 현금청산 등"),
        ("경매/공매", "부동산 경매, 배당, 유치권 등"),
    ]),
    ("금전/계약 문제", [
        ("대여금/채권추심", "대여금 반환, 지급명령, 채권 추심 등"),
        ("계약 분쟁", "계약 해제/해지, 위약금, 용역대금 등"),
        ("손해배상", "불법행위, 채무불이행 손해배상 등"),
    ]),
    ("민사절차", [
        ("민사소송 절차", "소장 작성, 답변서, 항소/상고 등"),
        ("강제집행/보전처분", "가압류, 가처분, 강제집행 등"),
        ("지급명령", "지급명령 신청/이의 등"),
    ]),
    ("기타 민사문제", [
        ("개인회생/파산", "개인회생, 파산/면책, 워크아웃 등"),
        ("국제/섭외", "국제거래, 국제이혼, 섭외사건 등"),
        ("기타 민사", "부당이득, 사해행위취소 등"),
    ]),
    ("가족", [
        ("이혼", "협의/재판 이혼, 재산분할, 위자료 등"),
        ("양육권/친권", "양육권, 양육비, 친권, 면접교섭 등"),
        ("상속", "상속분할, 유류분, 유언, 상속포기 등"),
        ("가정폭력", "가정폭력 보호처분, 접근금지 등"),
    ]),
    ("회사", [
        ("기업 자문/분쟁", "기업 법률자문, 계약 검토, 영업비밀 등"),
        ("인사/노무", "부당해고, 임금체불, 산재 등"),
        ("주주/지분 분쟁", "주주총회, 지분 양수도, 경영권 분쟁 등"),
    ]),
    ("의료/세금/행정", [
        ("의료", "의료사고, 의료소송, 의료분쟁조정 등"),
        ("세금", "조세불복, 세무조사, 상속/증여세 등"),
        ("행정소송/심판", "영업정지, 운전면허, 인허가 등"),
    ]),
    ("IT/지식재산/금융", [
        ("IT/통신", "개인정보, 전자상거래, 플랫폼 분쟁 등"),
        ("지식재산권/저작권", "저작권 침해, 상표, 특허 분쟁 등"),
        ("금융/보험", "보험금 청구, 금융투자 분쟁 등"),
    ]),
]

REGIONS = [
    "서울", "경기", "인천/부천", "춘천/강원", "대전/충남/세종", "청주/충북",
    "대구/경북", "부산/울산/경남", "광주/전남", "전주/전북", "제주",
]

LAWYERS = [
    # (이름, 헤드라인, 소속, 변호사회, 지역idx, 대분류명 목록, 전화, 카톡)
    ("김서연", "형사 전문, 초동 대응이 결과를 바꿉니다", "법률사무소 서연", "서울지방변호사회", 0,
     ["성범죄", "형사절차"], "02-555-0101", "https://pf.kakao.com/_demo01"),
    ("이준호", "10년차 부동산 분쟁 전담 변호사", "법무법인 한결로", "서울지방변호사회", 0,
     ["부동산/임대차", "금전/계약 문제"], "02-555-0102", None),
    ("박지민", "이혼·상속, 가족의 내일을 설계합니다", "법률사무소 지민", "경기중앙지방변호사회", 1,
     ["가족"], "031-555-0103", "https://pf.kakao.com/_demo03"),
    ("최현우", "교통사고·음주 사건 500건 상담 경력", "법무법인 도로", "서울지방변호사회", 0,
     ["교통사고/범죄"], "02-555-0104", None),
    ("정다은", "기업 자문과 노무, 실무형 해법 제시", "법무법인 다온", "부산지방변호사회", 7,
     ["회사"], "051-555-0105", "https://pf.kakao.com/_demo05"),
    ("강민석", "재산범죄·사기 사건 피해 회복 전담", "법률사무소 민석", "대구지방변호사회", 6,
     ["재산범죄", "금전/계약 문제"], "053-555-0106", None),
    ("윤소라", "의료사고, 환자의 편에서 끝까지", "법무법인 소명", "서울지방변호사회", 0,
     ["의료/세금/행정"], "02-555-0107", "https://pf.kakao.com/_demo07"),
    ("한지훈", "IT·저작권 분쟁, 개발자 출신 변호사", "법률사무소 코드", "서울지방변호사회", 0,
     ["IT/지식재산/금융", "회사"], "02-555-0108", None),
    ("오세영", "폭행·명예훼손 사건 신속 대응", "법무법인 세영", "인천지방변호사회", 2,
     ["폭행/협박", "명예훼손/모욕"], "032-555-0109", "https://pf.kakao.com/_demo09"),
    ("서예린", "민사소송 절차의 처음부터 끝까지", "법률사무소 예린", "광주지방변호사회", 8,
     ["민사절차", "기타 민사문제"], "062-555-0110", None),
]

CONSULT_TITLES = [
    ("전세보증금을 돌려받지 못하고 있습니다", "부동산/임대차"),
    ("중고거래 사기를 당했는데 고소 가능할까요?", "재산범죄"),
    ("음주운전 초범인데 처벌 수위가 궁금합니다", "교통사고/범죄"),
    ("협의이혼 시 재산분할 비율이 궁금합니다", "가족"),
    ("회사에서 갑자기 해고 통보를 받았습니다", "회사"),
    ("층간소음으로 이웃과 다툼이 있었습니다", "폭행/협박"),
    ("단톡방에서 험담을 들었는데 모욕죄가 될까요?", "명예훼손/모욕"),
    ("빌려준 돈을 2년째 못 받고 있습니다", "금전/계약 문제"),
    ("의료사고가 의심되는데 무엇부터 해야 하나요?", "의료/세금/행정"),
    ("제 사진이 무단으로 사용되고 있습니다", "IT/지식재산/금융"),
    ("상속 재산 분할 협의가 되지 않습니다", "가족"),
    ("보이스피싱 인출책으로 조사를 받게 됐습니다", "재산범죄"),
    ("스토킹 피해, 접근금지 신청이 가능한가요?", "폭행/협박"),
    ("경찰 조사 출석 요구를 받았습니다", "형사절차"),
    ("월세 계약 중도 해지 위약금 문제입니다", "부동산/임대차"),
    ("온라인 게시글 명예훼손으로 고소당했습니다", "명예훼손/모욕"),
    ("교통사고 합의금이 적정한지 봐주세요", "교통사고/범죄"),
    ("지급명령 이의신청을 하려고 합니다", "민사절차"),
    ("개인회생 신청 자격이 되는지 궁금합니다", "기타 민사문제"),
    ("양육비를 지급하지 않는 전 배우자 문제", "가족"),
]

LEGAL_CASES = [
    ("임차인의 계약갱신요구권 행사와 실거주 목적 해지의 판단 기준",
     "임대인의 실거주 목적이 인정되기 위한 구체적 증명 책임을 다룬 판결", "대법원", "2024다11111", "civil", ["부동산/임대차"]),
    ("음주측정 거부와 위드마크 공식 적용의 한계",
     "사후 음주측정 추산 방식의 증명력에 관한 판단", "대법원", "2024도22222", "criminal", ["교통사고/범죄"]),
    ("단체 채팅방 발언의 공연성 인정 여부",
     "소규모 단톡방 내 발언도 전파가능성이 있으면 공연성이 인정될 수 있다고 본 사례", "대법원", "2023도33333", "criminal", ["명예훼손/모욕"]),
    ("퇴직금 산정 시 정기 상여금의 평균임금 포함 여부",
     "정기적·일률적으로 지급된 상여금의 평균임금 산입 기준", "대법원", "2023다44444", "civil", ["회사"]),
    ("이혼 시 특유재산의 재산분할 대상성",
     "혼인 중 유지·증식에 기여한 특유재산의 분할 인정 범위", "대법원", "2024므55555", "civil", ["가족"]),
    ("의료과실 추정의 전제가 되는 간접사실의 증명 정도",
     "환자 측 증명책임 완화 법리의 적용 한계를 밝힌 판결", "대법원", "2023다66666", "civil", ["의료/세금/행정"]),
    ("전동킥보드 음주운전의 처벌 규정 적용",
     "개인형 이동장치 음주운전에 적용되는 법령의 해석", "대법원", "2024도77777", "criminal", ["교통사고/범죄"]),
    ("영업정지 처분에 대한 집행정지 인용 요건",
     "회복하기 어려운 손해와 긴급한 필요의 판단 기준", "대법원", "2024두88888", "administrative", ["의료/세금/행정"]),
]

NEWS_ITEMS = [
    ("전세사기 피해자 지원 특별법 개정안, 달라지는 내용은", ["부동산", "전세사기", "특별법"]),
    ("스토킹처벌법 시행 이후 접근금지 명령 신청 급증", ["스토킹", "형사", "접근금지"]),
    ("중대재해처벌법 확대 적용, 중소기업이 준비할 것들", ["기업", "노무", "중대재해"]),
    ("음주운전 처벌 강화 논의, 상습범 차량 몰수까지", ["교통", "음주운전"]),
    ("AI 생성물 저작권 논쟁, 법원 판단 잇따라", ["IT", "저작권", "AI"]),
    ("양육비 미지급 제재 강화, 출국금지 요건 완화", ["가족", "양육비"]),
]

# (변호사idx 0~9, type, 결과뱃지, 분야명, 제목)
LAWYER_POSTS = [
    (0, "case", "무혐의", "성범죄", "강제추행 혐의, 초기 조사 대응으로 무혐의 처분을 받은 사례"),
    (0, "case", "집행유예", "형사절차", "1심 실형 선고 사건, 항소심에서 집행유예로 석방된 사례"),
    (1, "case", "승소", "부동산/임대차", "전세보증금 반환 소송, 전액 회수에 성공한 사례"),
    (1, "case", "조정성립", "금전/계약 문제", "공사대금 분쟁, 조정으로 신속하게 마무리한 사례"),
    (2, "case", "조정성립", "가족", "양육권 포함 전반적 조건을 반영해 조정성립을 이끌어낸 사례"),
    (3, "case", "벌금", "교통사고/범죄", "음주 측정 절차를 다투어 벌금형 선처로 종결한 사례"),
    (4, "case", "승소", "회사", "부당해고 구제신청 인용, 복직과 임금 상당액을 확보한 사례"),
    (5, "case", "무죄", "재산범죄", "중고거래 사기 누명, 무죄 판결로 결백을 밝힌 사례"),
    (6, "case", "조정성립", "의료/세금/행정", "의료분쟁조정으로 수술 후유증 배상을 받아낸 사례"),
    (7, "guide", None, "IT/지식재산/금융", "내 사진이 무단으로 사용됐다면 — 저작권 침해 대응 절차 정리"),
    (8, "guide", None, "폭행/협박", "쌍방폭행으로 몰렸을 때 반드시 확인해야 할 3가지"),
    (9, "essay", None, "민사절차", "10년차 민사 변호사가 말하는 소송보다 나은 화해의 기술"),
    # 검수 대기 2건 + 반려 1건 (관리자 검수 플로우 데모용)
    (0, "guide", None, "형사절차", "경찰 조사 출석 전 꼭 알아야 할 5가지"),
    (2, "essay", None, "가족", "이혼 상담실에서 만난 사람들"),
    (3, "case", "기각", "교통사고/범죄", "블랙박스 분석으로 과실 비율을 뒤집은 사례"),
]

FIRM_ADS = [
    ("법무법인 다온하늘", "가사·상속 분야에 집중한 프리미엄 법률서비스",
     "가사·상속 분야만 집중적으로 수행해 온 전문 변호사들이 함께합니다. 상속·유류분 사건 다수 수행 경험을 보유하고 있습니다.",
     "가족", "서울특별시 서초구 서초대로 100 다온빌딩 3층",
     [{"label": "홈페이지", "url": "https://example.com/daon"}, {"label": "성공사례", "url": "https://example.com/daon/cases"}]),
    ("법무법인 한결로", "부동산 분쟁, 계약서 검토부터 소송까지 원스톱",
     "임대차·매매·재건축 분쟁을 전담하는 부동산 전문 로펌입니다. 보증금 반환·명도 사건 실무 경험이 풍부합니다.",
     "부동산/임대차", "서울특별시 강남구 테헤란로 200 한결타워 5층",
     [{"label": "홈페이지", "url": "https://example.com/hangyul"}, {"label": "블로그", "url": "https://example.com/hangyul/blog"}]),
    ("법률사무소 미리내", "형사 사건 초기 대응, 24시간 긴급 상담 체계",
     "형사 전담 변호사들이 경찰 조사 단계부터 동행합니다. 초기 대응이 결과를 바꿉니다.",
     "형사절차", "인천광역시 남동구 예술로 150 미리내빌딩 2층",
     [{"label": "홈페이지", "url": "https://example.com/mirinae"}, {"label": "긴급상담", "url": "https://example.com/mirinae/sos"}]),
]

# category = 보드 토픽명 (routes/community.py BOARDS와 일치해야 함)
COMMUNITY_POSTS = [
    ("공지", "안기모 커뮤니티 이용 안내 및 운영 원칙", True),
    # 교정시설 정보
    ("접견 가능 시간", "서울구치소 평일 접견 시간과 예약 방법 정리", False),
    ("영치금 계좌", "영치금 입금 방법과 월 한도, 직접 해본 후기", False),
    ("우편 주소", "교정시설 우편 보낼 때 주소 쓰는 법과 반송 안 되는 팁", False),
    ("택배 가능 여부", "책·의류 택배로 넣어봤어요 — 되는 것과 안 되는 것", False),
    ("자주 묻는 질문", "처음이라 막막한 분들을 위한 접견 FAQ 모음", False),
    # 수용생활 정보
    ("초범 가족이 궁금한 것", "가족이 처음 수감됐을 때 가장 많이 묻는 질문 10가지", False),
    ("이감 절차", "이감 통보는 언제 오나요? 겪어본 절차 공유합니다", False),
    ("영치품", "영치품으로 넣을 수 있는 물품 목록 정리해봤어요", False),
    ("교도소 생활", "하루 일과가 어떻게 되는지 면회 때 들은 이야기", False),
    ("출소 절차", "출소일 아침, 가족이 준비해야 할 것들", False),
    ("교정기관 식단표", "이번 달 식단표 보는 방법 알려드려요", False),
    # 양식 자료실
    ("탄원서", "탄원서 쓸 때 꼭 들어가야 하는 내용 (예시 포함)", False),
    ("반성문", "반성문, 형식보다 중요한 것 — 작성 요령 정리", False),
    ("합의서", "합의서 작성 시 주의할 조항 체크리스트", False),
    ("자주 쓰는 서류 모음", "가족들이 자주 쓰는 서류 양식 한 번에 모았습니다", False),
    # 자유게시판 / 옥바라지 이야기
    ("자유게시판", "변호사 상담 처음 받아봤는데 생각보다 편했어요", False),
    ("자유게시판", "법률 드라마에서 본 장면, 실제로 가능한가요?", False),
    ("옥바라지 이야기", "면회 다녀오는 길, 같은 처지 가족분들께", False),
    ("옥바라지 이야기", "1년째 옥바라지 중입니다. 버티는 법을 나눠요", False),
]


def run_seed(app):
    from extensions import db
    from models import (
        Banner,
        Category,
        CommunityComment,
        CommunityPost,
        Consultation,
        ConsultationAnswer,
        FirmAd,
        LawyerPost,
        LawyerProfile,
        LegalCase,
        News,
        Region,
        User,
    )
    from models.community import community_likes

    with app.app_context():
        db.drop_all()
        db.create_all()

        now = datetime.now()

        # 분야 2-depth
        cat_by_name = {}
        for i, (name, subs) in enumerate(CATEGORIES):
            parent = Category(name=name, sort_order=i)
            db.session.add(parent)
            db.session.flush()
            cat_by_name[name] = parent
            for j, (sub_name, desc) in enumerate(subs):
                child = Category(
                    parent_id=parent.id, name=sub_name, description=desc, sort_order=j
                )
                db.session.add(child)
                cat_by_name[sub_name] = child

        # 지역 11
        regions = []
        for i, name in enumerate(REGIONS):
            r = Region(name=name, sort_order=i)
            db.session.add(r)
            regions.append(r)
        db.session.flush()

        # 총관리자 (시드로만 생성 — §4-4)
        admin = User(
            email="admin@angimo.kr", name="총관리자", role="admin", status="active"
        )
        admin.set_password("angimo-admin-1234")
        db.session.add(admin)

        # 더미 변호사 10 (active + 프로필 + 분야)
        lawyer_users = []
        for i, (name, headline, firm, bar, region_idx, cats, phone, kakao) in enumerate(
            LAWYERS, start=1
        ):
            u = User(
                email=f"lawyer{i}@angimo.kr",
                name=name,
                phone=f"010-555-01{i:02d}",
                role="lawyer",
                status="active",
                created_at=now - timedelta(days=90 - i * 7),
            )
            u.set_password("lawyer-1234")
            db.session.add(u)
            db.session.flush()
            profile = LawyerProfile(
                user_id=u.id,
                license_no=f"제{2024000 + i}호",
                headline=headline,
                firm_name=firm,
                bar_association=bar,
                photo_url=f"/static/img/avatars/lawyer{i}.svg",
                office_phone=phone,
                kakao_url=kakao,
                address=f"{REGIONS[region_idx].split('/')[0]} 중심가 {i}길 {10 + i}",
                intro_full=(
                    f"{name} 변호사입니다. 의뢰인의 상황을 정확히 진단하고 "
                    "실현 가능한 해결책을 제시하는 것을 원칙으로 합니다."
                ),
                career=[
                    {"year": "2016", "text": "변호사시험 합격"},
                    {"year": "2018", "text": f"{firm} 합류"},
                    {"year": "2023", "text": "관련 분야 전문 등록"},
                ],
                region_id=regions[region_idx].id,
                view_count=120 + i * 37,
                contact_click_count=8 + i * 3,
                approved_at=now - timedelta(days=80 - i * 7),
            )
            profile.categories = [cat_by_name[c] for c in cats]
            db.session.add(profile)
            lawyer_users.append(u)

        # 더미 일반회원 5 (상담글/커뮤니티 작성자)
        members = []
        for i in range(1, 6):
            u = User(
                email=f"user{i}@example.com",
                name=f"회원{i}",
                nickname=f"익명늑대{i}" if i % 2 else None,
                phone=f"010-777-02{i:02d}",
                role="user",
                status="active",
                created_at=now - timedelta(days=60 - i * 5),
            )
            u.set_password("user-1234")
            db.session.add(u)
            members.append(u)
        db.session.flush()

        # 상담글 20 (앞 8건에 답변 1개씩)
        for i, (title, cat_name) in enumerate(CONSULT_TITLES):
            c = Consultation(
                user_id=members[i % len(members)].id,
                category_id=cat_by_name[cat_name].id,
                title=title,
                content=(
                    f"{title} 상황이 이렇습니다. 구체적인 사정을 정리해서 남깁니다. "
                    "어떤 절차로 대응해야 할지 변호사님들의 의견이 궁금합니다."
                ),
                is_public=(i % 5 != 4),
                views=30 + i * 11,
                created_at=now - timedelta(days=20 - i, hours=i),
            )
            db.session.add(c)
            db.session.flush()
            if i < 8:
                lawyer = lawyer_users[i % len(lawyer_users)]
                db.session.add(
                    ConsultationAnswer(
                        consultation_id=c.id,
                        lawyer_id=lawyer.id,
                        content=(
                            "안녕하세요, 답변드립니다. 우선 관련 자료(계약서, 대화 내역 등)를 "
                            "확보해 두시는 것이 중요합니다. 사안에 따라 진행 절차가 달라지므로 "
                            "가까운 사무소 상담을 권해드립니다."
                        ),
                        created_at=c.created_at + timedelta(hours=6),
                    )
                )

        # 판례 8
        for i, (title, summary, court, case_no, case_type, cats) in enumerate(
            LEGAL_CASES
        ):
            db.session.add(
                LegalCase(
                    title=title,
                    summary=summary,
                    content=f"{summary}. 사건의 경위와 법원의 판단 요지를 정리한 데모 본문입니다.",
                    court=court,
                    case_no=case_no,
                    case_type=case_type,
                    category_ids=[cat_by_name[c].id for c in cats],
                    views=200 + i * 45,
                    created_at=now - timedelta(days=30 - i * 3),
                )
            )

        # 뉴스 6
        for i, (title, tags) in enumerate(NEWS_ITEMS):
            db.session.add(
                News(
                    title=title,
                    content=f"{title}에 대한 데모 기사 본문입니다. 주요 쟁점과 향후 전망을 다룹니다.",
                    hashtags=tags,
                    reporter="안기모 뉴스팀",
                    views=150 + i * 60,
                    published_at=now - timedelta(days=12 - i * 2),
                )
            )

        # 커뮤니티 15 (공지 1) + 댓글/추천 소량
        comm_posts = []
        for i, (category, title, is_notice) in enumerate(COMMUNITY_POSTS):
            p = CommunityPost(
                user_id=(admin.id if is_notice else members[i % len(members)].id),
                category=category,
                title=title,
                content=f"{title} — 데모 본문입니다. 경험과 정보를 나누는 공간입니다.",
                is_anonymous=(not is_notice and i % 3 == 0),
                is_notice=is_notice,
                views=50 + i * 21,
                likes=0,
                # 최근 글일수록 촘촘하게 — 마지막 2~3개는 24시간 내(NEW 뱃지 데모)
                created_at=now - timedelta(hours=(len(COMMUNITY_POSTS) - 1 - i) * 9),
            )
            db.session.add(p)
            comm_posts.append(p)
        db.session.flush()

        for i, p in enumerate(comm_posts[1:6], start=1):
            db.session.add(
                CommunityComment(
                    post_id=p.id,
                    user_id=members[(i + 1) % len(members)].id,
                    content="좋은 정보 감사합니다. 저도 비슷한 경험이 있어요.",
                    is_anonymous=(i % 2 == 0),
                    created_at=p.created_at + timedelta(hours=3),
                )
            )
            likers = members[: (i % 3) + 1]
            for m in likers:
                db.session.execute(
                    community_likes.insert().values(post_id=p.id, user_id=m.id)
                )
            p.likes = len(likers)

        # 변호사 포스트 15 (published 12 / pending 2 / rejected 1)
        for i, (lidx, ptype, badge, cat_name, title) in enumerate(LAWYER_POSTS):
            if i < 12:
                status, published_at, reject_reason = "published", now - timedelta(days=14 - i), None
            elif i < 14:
                status, published_at, reject_reason = "pending", None, None
            else:
                status, published_at, reject_reason = "rejected", None, "개인정보가 포함된 문단 수정이 필요합니다."
            db.session.add(
                LawyerPost(
                    lawyer_id=lawyer_users[lidx].id,
                    type=ptype,
                    title=title,
                    content=(
                        f"{title}. 사건의 경위와 대응 전략, 결과에 이르기까지의 과정을 "
                        "정리한 데모 본문입니다. 유사한 상황이라면 초기 대응이 중요합니다."
                    ),
                    result_badge=badge,
                    category_id=cat_by_name[cat_name].id,
                    views=80 + i * 33,
                    status=status,
                    published_at=published_at,
                    reject_reason=reject_reason,
                    created_at=now - timedelta(days=15 - i),
                )
            )

        # 로펌 광고 3
        for i, (firm_name, headline, desc, cat_name, address, links) in enumerate(FIRM_ADS):
            db.session.add(
                FirmAd(
                    firm_name=firm_name,
                    headline=headline,
                    description=desc,
                    links=links,
                    address=address,
                    category_id=cat_by_name[cat_name].id,
                    sort_order=i,
                    is_active=True,
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=180),
                )
            )

        # 메인 히어로 롤링 배너 3 (title 규칙: "메인|포인트|서브", image_url = 3D 아이콘)
        hero_banners = [
            ("법률 문제의 시작부터 끝까지|안기모가 함께합니다|분야별 전문 변호사를 지금 바로 만나보세요",
             "/static/icons/etc-civil.png", "/lawyers/"),
            ("법률 고민, 혼자 끙끙 앓지 마세요|커뮤니티에서 나눠보세요|비슷한 경험을 한 사람들의 이야기를 들어보세요",
             "/static/icons/defame.png", "/community/"),
            ("변호사 답변을 무료로 받는|온라인 상담사례|질문을 남기면 분야 전문 변호사가 답변해드려요",
             "/static/icons/civil.png", "/counsel/"),
        ]
        for i, (title, image_url, link_url) in enumerate(hero_banners):
            db.session.add(
                Banner(
                    position="main_hero",
                    title=title,
                    image_url=image_url,
                    link_url=link_url,
                    sort_order=i,
                    is_active=True,
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=365),
                )
            )

        db.session.commit()

        # 요약 출력
        from sqlalchemy import func as sa_func

        counts = {
            "categories(대분류)": Category.query.filter_by(parent_id=None).count(),
            "categories(세부)": Category.query.filter(
                Category.parent_id.isnot(None)
            ).count(),
            "regions": Region.query.count(),
            "users(admin)": User.query.filter_by(role="admin").count(),
            "users(lawyer)": User.query.filter_by(role="lawyer").count(),
            "users(user)": User.query.filter_by(role="user").count(),
            "lawyer_profiles": LawyerProfile.query.count(),
            "consultations": Consultation.query.count(),
            "consultation_answers": ConsultationAnswer.query.count(),
            "legal_cases": LegalCase.query.count(),
            "news": News.query.count(),
            "community_posts": CommunityPost.query.count(),
            "community_comments": CommunityComment.query.count(),
            "lawyer_posts(published)": LawyerPost.query.filter_by(status="published").count(),
            "lawyer_posts(pending)": LawyerPost.query.filter_by(status="pending").count(),
            "firm_ads": FirmAd.query.count(),
            "banners": Banner.query.count(),
        }
        table_count = len(db.metadata.tables)
        print(f"[seed] tables created: {table_count}")
        for k, v in counts.items():
            print(f"[seed] {k}: {v}")
        print("[seed] admin 로그인: admin@angimo.kr / angimo-admin-1234 (/admin/login)")
        print("[seed] 변호사 로그인: lawyer1@angimo.kr / lawyer-1234")
        print("[seed] 일반회원 로그인: user1@example.com / user-1234")


if __name__ == "__main__":
    ensure_database()
    from app import create_app

    run_seed(create_app())
