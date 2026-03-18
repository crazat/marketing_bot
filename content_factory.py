import sys
import os
import time
import random
from datetime import datetime
import pandas as pd

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from content_studio_v3_llm import LLMContentGenerator
from utils import ConfigManager

class ContentFactory:
    def __init__(self):
        self.config = ConfigManager()
        self.generator = LLMContentGenerator()
        self.draft_dir = os.path.join(self.config.root_dir, 'drafts_factory')
        if not os.path.exists(self.draft_dir):
            os.makedirs(self.draft_dir)
            
        # 3-Zone Strategy
        self.zones = {
            "Zone1_Back": ["용암동", "금천동", "탑대성동", "동남지구"],
            "Zone2_Lack": ["송절동", "테크노폴리스", "오송", "오창"],
            "Zone3_Comp": ["복대동", "지웰시티", "율량동", "사천동"]
        }
        
        self.targets = ["직장인", "출산맘", "예비신부", "학생", "갱년기여성"]
        self.symptoms = ["뱃살", "팔뚝살", "식욕억제", "요요현상", "붓기관리"]

    def _load_prompt(self, key, default_prompt):
        """Load prompt from JSON via ConfigManager."""
        return self.config.get_prompt(key, default_prompt)

    def generate_track_b_batch(self, count=5):
        """Generates 'count' number of variations for Track B."""
        print(f"🏭 Factory Started: Generating {count} posts...")
        
        # Default Prompt (Fallback)
        default_prompt = """
        당신은 {location}에 실제로 거주하는 '청주 지역주민'입니다. 
        [키워드]: {keyword}
        [상황]: {focus}
        
        동네 언니처럼 친근하게 {keyword} 고민을 이야기하다가, 규림한의원을 추천해주세요.
        마크다운 헤더(##) 쓰지 말고, 엔터로만 문단 나누세요.
        """
        
        # Load Prompt from JSON
        raw_prompt = self._load_prompt("track_b_factory", default_prompt)

        generated_data = []
        
        # [Systematic Generation] Replace random.choice with Round-Robin / Full Census
        # We want to cycle through meaningful combinations, not random ones.
        
        import itertools
        
        # Flatten the zones
        all_neighborhoods = []
        for z, hoods in self.zones.items():
            for h in hoods:
                all_neighborhoods.append((z, h))
                
        # Create all possible combinations (Cartesian Product)
        # Total combinations = len(neighborhoods) * len(targets) * len(symptoms)
        # e.g. 12 hoods * 5 targets * 5 symptoms = 300 variations.
        all_combinations = list(itertools.product(all_neighborhoods, self.targets, self.symptoms))
        
        # To avoid generating the same starting 5 every time, we need a 'cursor' or we shuffle ONCE.
        # Ideally, we store the 'last_used_index' in a state file, but for now, let's shuffle deterministically
        # based on date or just Shuffle once to ensure variety in this batch, specifically requesting 'count'.
        # Or better: "Today's Batch" based on day of year?
        
        # Let's shuffle the master list to ensure variety in the output, 
        # BUT the underlying list is a Full Census list, so we are sampling from the Census, not random noise.
        # User wants "Real" logic.
        
        # Real Logic: Today's date defines the slice.
        day_of_year = datetime.now().timetuple().tm_yday
        start_idx = (day_of_year * count) % len(all_combinations)
        
        # Select 'count' items starting from today's index (Round Robin over the year)
        selected_combinations = []
        for i in range(count):
            idx = (start_idx + i) % len(all_combinations)
            selected_combinations.append(all_combinations[idx])
            
        print(f"   📊 Census Mode: Selecting batch starting at index {start_idx}/{len(all_combinations)}")
        
        for combo in selected_combinations:
            (zone_name, neighborhood), target, symptom = combo
            
            # Logic Focus: Strategic Mapping
            if zone_name == "Zone1_Back": focus = "시내 접근성 강조 (전략: 시외곽 이탈 방지)"
            elif zone_name == "Zone2_Lack": focus = "동네 병원 부족 강조 (전략: 의료 공백 공략)"
            else: focus = "프리미엄/시설 강조 (전략: 경쟁 우위 소구)"
            
            topic = f"{neighborhood} {target} {symptom}"
            print(f"   ⚙️ [Strategy Engine] Target: {topic} | Focus: {focus}")
            
            # 3. Generate Content (Lite Version)
            try:
                # Format the raw prompt loaded from JSON
                prompt = raw_prompt
                prompt = prompt.replace("{keyword}", f"{target} {symptom}")
                prompt = prompt.replace("{location}", neighborhood)
                prompt = prompt.replace("{focus}", focus)
                
                # Check LLM
                # Check LLM
                if not self.generator:
                    raise Exception("Generator instance missing")
 
                # Generate
                if hasattr(self.generator, 'crew'):
                     response_text = self.generator.crew.writer.generate(prompt)
                elif hasattr(self.generator, 'model') and self.generator.model:
                     response_text = self.generator.model.generate_content(prompt).text
                else:
                     raise Exception("LLM Generator not properly initialized")
 
                content = response_text
                
                # Save Draft
                timestamp = datetime.now().strftime('%Y%m%d')
                filename = f"{timestamp}_{neighborhood}_{target}_{symptom}.md"
                save_path = os.path.join(self.draft_dir, filename)
                
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                generated_data.append({"target": neighborhood, "keyword": topic, "file": filename})
            
            except Exception as e:
                print(f"❌ Error: {e}")
                
        return pd.DataFrame(generated_data)

if __name__ == "__main__":
    factory = ContentFactory()
    df = factory.generate_track_b_batch(3)
    print(df)
