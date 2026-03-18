import sys
import os

# Windows encoding fix
sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# Also add the parent directory to path to allow package imports if needed, 
# but since we are in marketing_bot, just import modules directly if we are running as script.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marketing_bot.content_studio_v3_llm import LLMContentGenerator
from marketing_bot.content_factory import ContentFactory

def test_llm():
    print("🧠 Testing LLM Content Generator...")
    gen = LLMContentGenerator()
    
    print("   [1] Testing Ad Copy...")
    ad = gen.generate_ad_copy("다이어트", "50% 할인")
    if ad and len(ad) > 10:
        print("      ✅ Ad Copy Generated")
    else:
        print("      ❌ Ad Copy Failed")

    print("   [2] Testing Premium Blog (Mock/Real)...")
    # We won't generate a full blog to save time/tokens unless necessary, 
    # but let's try a short one or check if method exists.
    try:
        blog = gen.generate_premium_blog("테스트 주제", "미용 모드", "맑음")
        if blog and len(blog) > 50:
             print("      ✅ Premium Blog Generated")
        else:
             print("      ❌ Blog Failed")
    except Exception as e:
        print(f"      ❌ Blog Error: {e}")

def test_factory():
    print("🏭 Testing Content Factory...")
    factory = ContentFactory()
    try:
        df = factory.generate_track_b_batch(1) # Generate 1
        if not df.empty:
            print("      ✅ Track B Generated (1 item)")
        else:
            print("      ❌ Track B Failed")
    except Exception as e:
        print(f"      ❌ Factory Error: {e}")

if __name__ == "__main__":
    test_llm()
    test_factory()
