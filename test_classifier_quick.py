"""실제 발견된 문제 댓글 테스트"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from lead_classifier import LeadClassifier, LeadPriority

classifier = LeadClassifier(use_nlp=False)

# 실제 발견된 문제 케이스
test_comments = [
    # 이건 유의미한 리드여야 함
    ("비형간염 있는데 다이어트 한약가능한가요?", True, "건강 조건 문의"),

    # 이건 필터링되어야 함
    ("사람 목이 이렇게 길어질수가 있다뇨 헉", False, "단순 리액션"),
    ("이 운동법은 제가 추나 전문 한의원에서 부원장으로 있을 때 배웠던 건데", False, "한의원 직원 홍보"),
    ("원장님 허리 디스크 운동법 쉽게 따라 할수 있어서 좋습니다 감사 드리고", False, "단순 감사"),
    ("그간 다이어트 한약 듣기만해봐서 궁금해봤는데 개인마다 다르군요", True, "관심 표현 (경계)"),
]

print("=== 실제 문제 케이스 테스트 ===\n")
for comment, should_pass, reason in test_comments:
    result = classifier.classify(comment)
    passed = result.priority != LeadPriority.NONE

    status = "✓" if passed == should_pass else "✗"
    print(f"[{status}] {comment[:50]}...")
    print(f"   예상: {'PASS' if should_pass else 'REJECT'} | 실제: {'PASS' if passed else 'REJECT'}")
    if not passed:
        print(f"   제외 사유: {result.reject_reason}")
    else:
        score = classifier.get_lead_score(result)
        print(f"   Score: {score} | Keywords: {result.matched_keywords}")
    print(f"   설명: {reason}")
    print()
