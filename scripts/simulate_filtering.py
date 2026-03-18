
import logging

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Simulation")

class KeywordFilterSimulator:
    # COPIED EXACTLY FROM keyword_harvester.py
    MEDICAL_KEYWORDS = [
        # Facilities
        "병원", "의원", "한의원", "클리닉", "내과", "외과", "치과", "피부과", "성형외과", 
        "산부인과", "비뇨기과", "정형외과", "이비인후과", "정신과", "소아과", "안과", "요양병원",
        # Treatments & Procedures
        "치료", "수술", "시술", "교정", "검사", "진료", "입원", "재활", "처방",
        "다이어트", "비만", "살빼기", "식단", "피티", "요가", "필라테스", # Health/Fitness allows
        "여드름", "피부", "모공", "흉터", "점빼기", "아토피", "습진", "두드러기", "탈모",
        "보톡스", "필러", "리프팅", "슈링크", "인모드", "울쎄라", "제모", "레이저",
        "통증", "디스크", "관절", "염좌", "교통사고", "후유증", "추나", "도수",
        "한약", "보약", "임플란트", "스케일링", "사랑니", "미백", "라식", "라섹",
        "우울증", "불면증", "공황장애", "상담", "언어치료", "발달센터"
    ]
    
    BLACKLIST_KEYWORDS = [
        "유기견", "강아지", "고양이", "동물", "분양", "미용", "호텔", "카페", "맛집", 
        "물류", "이사", "용달", "퀵", "수리", "정비", "세탁", "청소", "철거", "폐기물",
        "학원", "과외", "학교", "유치원", "어린이집", "부동산", "아파트", "매매", "전세",
        "여행", "숙소", "펜션", "모텔", "대출", "보험", "법률", "변호사", "노무사"
    ]

    def _is_medically_relevant(self, keyword):
        # 1. Check Blacklist first (Fast fail)
        for bad in self.BLACKLIST_KEYWORDS:
            if bad in keyword:
                return False, f"Blacklisted ({bad})"
                
        # 2. Check Whitelist (Must contain at least one medical term)
        for good in self.MEDICAL_KEYWORDS:
            if good in keyword:
                return True, f"Whitelisted ({good})"
                
        # 3. Special Case: Brand Name "규림"
        if "규림" in keyword:
            return True, "Brand Match"
            
        return False, "No Medical Relevance"

# Test Data
bad_keywords = [
    "청주유기견보호센터", "세종시이삿짐센터", "청주물류센터", "청주카센터", 
    "진천이삿짐센터", "청주운동화세탁", "세종시성장앨범", "청주쿠팡물류센터",
    "청주동물병원", "강아지분양", "세종맛집"
]

good_keywords = [
    "청주 다이어트 한의원", "세종시 피부과", "복대동 교통사고 입원", "진천읍 다이어트약",
    "규림한의원 청주점", "산남동 도수치료", "율량동 추나요법", "오송 여드름 흉터"
]

ambiguous_keywords = [
    "청주 필라테스 잘하는곳", "세종시 요가", "오창 헬스장", "청주 마사지"
]

print("-" * 60)
print(f"{'KEYWORD':<30} | {'STATUS':<10} | {'REASON'}")
print("-" * 60)

sim = KeywordFilterSimulator()

all_kws = bad_keywords + good_keywords + ambiguous_keywords
pass_count = 0
fail_count = 0

for kw in all_kws:
    is_valid, reason = sim._is_medically_relevant(kw)
    status = "PASS" if is_valid else "FAIL"
    if is_valid: pass_count += 1
    else: fail_count += 1
    print(f"{kw:<30} | {status:<10} | {reason}")

print("-" * 60)
print(f"Total: {len(all_kws)} | Passed: {pass_count} | Failed: {fail_count}")
