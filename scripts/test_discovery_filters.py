import sys
import os
from unittest.mock import MagicMock

# Mock AgentCrew before importing pathfinder because it imports AgentCrew
sys.modules['agent_crew'] = MagicMock()
mock_crew = MagicMock()
sys.modules['agent_crew'].AgentCrew = mock_crew

# Add parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathfinder import Pathfinder

def test_filters():
    pf = Pathfinder()
    # Mock self.crew since it's initialized in __init__
    pf.crew = MagicMock()
    
    test_cases = [
        # Noise (Should be False)
        ("청주 유기견 보호소", False),
        ("세종 아이폰 수리센터", False),
        ("청주 맛집 추천", False),
        ("오창 애플 서비스센터", False),
        ("청주 어린이집", False),
        ("청주 요가 학원", False),
        ("세종시 부동산", False),
        
        # Valid Gems (Should be True)
        ("청주 다이어트 한의원", True),
        ("세종 여드름 피부과", True),
        ("청주 안면비대칭 교정", True),
        ("오창 교통사고 입원 병원", True),
        ("가경동 산후보약 추천", True),
        ("청주 규림한의원", True),
        ("청주 다이어트 센터", True), # Allowed center
    ]
    
    print("--- [Filter Validation Test] ---")
    pass_count = 0
    for kw, expected in test_cases:
        result = pf._is_medically_relevant(kw)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        if result == expected: pass_count += 1
        print(f"[{status}] Keyword: '{kw}' | Expected: {expected} | Got: {result}")
    
    print(f"\nResult: {pass_count}/{len(test_cases)} Passed")

def test_category_revalidation():
    pf = Pathfinder()
    pf.crew = MagicMock()
    
    test_cases = [
        ("청주 다이어트 한약 가격", "다이어트", "다이어트"),
        ("청주 여드름 흉터 치료", "다이어트", "여드름_피부"), # Drift Corrected
        ("청주 교통사고 한의원 입원", "통증_디스크", "교통사고_입원"), # Specificity Improved
        ("청주 일반 병원", "여드름_피부", "기타"), # Non-specific fallback
    ]
    
    print("\n--- [Category Revalidation Test] ---")
    pass_count = 0
    for kw, initial, expected in test_cases:
        result = pf._revalidate_category(kw, initial)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        if result == expected: pass_count += 1
        print(f"[{status}] Keyword: '{kw}' | Initial: {initial} | Got: {result}")
    
    print(f"\nResult: {pass_count}/{len(test_cases)} Passed")

if __name__ == "__main__":
    # Force UTF-8 output if needed
    if sys.platform.startswith('win'):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        
    test_filters()
    test_category_revalidation()
