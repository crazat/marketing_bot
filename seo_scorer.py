import re
from collections import Counter

class SeoScorer:
    """
    Analyzes blog content and calculates an SEO score (0-100) based on Naver Blog algorithms.
    """
    def __init__(self):
        pass

    def analyze(self, content, main_keyword):
        feedback = []
        score = 100
        
        # 1. Length Check
        length = len(content)
        if length < 1000:
            score -= 20
            feedback.append(f"⚠️ **Content Too Short**: Current {length} chars. Aim for 1500+ for Naver.")
        elif length > 3000:
            feedback.append(f"ℹ️ **Good Length**: {length} chars (In-depth content).")
        else:
            feedback.append(f"✅ **Perfect Length**: {length} chars.")

        # 2. Keyword Density Check
        # Normalize content and keyword
        count = content.count(main_keyword)
        density = (count * len(main_keyword)) / length * 100 if length > 0 else 0
        
        if count < 5:
            score -= 15
            feedback.append(f"⚠️ **Keyword Deficiency**: '{main_keyword}' found only {count} times. Aim for 5-8 times.")
        elif density > 3.0:
            score -= 10
            feedback.append(f"⚠️ **Keyword Stuffing**: Density is {density:.1f}%. Reduces it to under 2% to avoid penalty.")
        else:
            feedback.append(f"✅ **Keyword Density**: Good ({count} times, {density:.1f}%).")

        # 3. Structure Check (Headings)
        # Count markdown headers #, ##, ### (or text based if plain text)
        headers = re.findall(r'^#{1,3}\s', content, re.MULTILINE)
        if len(headers) < 2:
            score -= 10
            feedback.append("⚠️ **Structure Weak**: Use more Subheadings (##) to break up text.")
        else:
            feedback.append(f"✅ **Structure**: Good ({len(headers)} sections detected).")

        # 4. Image Placeholders Check
        # Check if user/agent included [Image] or (이미지) markers
        images = re.findall(r'\[.*?이미지.*?\]|\(.*이미지.*\)', content)
        if len(images) < 3:
            score -= 10
            feedback.append("⚠️ **Visuals Missing**: Include at least 3 image placeholders (e.g. [진맥 이미지]).")
        else:
            feedback.append(f"✅ **Visuals**: {len(images)} image spots identified.")

        # 5. LSI / Related Keywords (Mock Logic for MVP)
        # In a real tool, we'd query Naver's related keywords API.
        # Here we check for essential "semantic" words for a clinic.
        essential_words = ["상담", "진료", "원장", "청주", "위치"]
        missing_lsi = [w for w in essential_words if w not in content]
        if missing_lsi:
            deduction = len(missing_lsi) * 5
            score -= deduction
            feedback.append(f"⚠️ **Context Missing**: Try adding words: {', '.join(missing_lsi)}")

        # Cap score
        score = max(0, min(100, score))
        
        return {
            "score": score,
            "feedback": feedback
        }

if __name__ == "__main__":
    scorer = SeoScorer()
    sample_text = """
    # 청주 다이어트 한의원 추천
    안녕하세요. 청주 규림한의원입니다.
    오늘은 다이어트에 대해 알아봅시다.
    다이어트는 힘들지만... (중략) ...
    규림한의원은 원장님이 직접 진료합니다.
    """
    result = scorer.analyze(sample_text, "다이어트")
    print(f"Score: {result['score']}")
    print("\n".join(result['feedback']))
