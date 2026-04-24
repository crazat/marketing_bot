# Advanced Marketing Automation Features Research (2026)

> Korean Local Healthcare Marketing - Features NOT Yet in Current System
> Research Date: 2026-03-24
> Based on: Web research across 30+ sources, current system analysis

---

## Table of Contents

1. [Reputation Management 2.0](#1-reputation-management-20)
2. [Hyper-Local Targeting](#2-hyper-local-targeting)
3. [Patient Lifecycle Automation](#3-patient-lifecycle-automation)
4. [Advanced Analytics](#4-advanced-analytics)
5. [Emerging Channels](#5-emerging-channels)
6. [Workflow Automation](#6-workflow-automation)
7. [Implementation Priority Matrix](#7-implementation-priority-matrix)
8. [Architecture Recommendations](#8-architecture-recommendations)

---

## 1. Reputation Management 2.0

### 1.1 Automated Reputation Score Calculation

**Current gap**: The system tracks reviews and has sentiment analysis (`review_nlp_analyzer.py`) but lacks a unified reputation score.

**Proposed approach**:

```
Reputation Score = weighted average across platforms:
  - Naver Place Rating (NEW: 5-star system launching April 6, 2026)
  - Google Business Profile Rating
  - KakaoMap Rating (when API key renewed)
  - Blog/Cafe Sentiment Score (from community_mentions)
  - Naver Kin Sentiment (from naver_kin_lead_finder data)
```

**Critical Naver Place Update (March 2026)**:
- Naver Place is introducing a **5-point star rating system** starting April 6, 2026
- Previously Naver had keyword-based satisfaction only (no numeric scores)
- Star ratings will be visible as averages in the review tab
- Reviews can only be modified within 3 months of posting (anti-abuse measure)
- Initial data collection period: ratings visible only to the reviewer and business owner
- Applies to: restaurants, shopping, services, healthcare, accommodations, etc.

**Implementation design**:

```python
class ReputationScoreEngine:
    """Cross-platform reputation score calculator"""

    PLATFORM_WEIGHTS = {
        'naver_place': 0.40,    # Highest weight for Korean local business
        'google_business': 0.20,
        'kakao_map': 0.15,
        'blog_sentiment': 0.15,
        'community_sentiment': 0.10,
    }

    def calculate_composite_score(self, business_id: str) -> ReputationScore:
        """
        Returns:
          - composite_score: 0-100
          - platform_breakdown: per-platform scores
          - trend: improving/declining/stable (30-day rolling)
          - benchmark: vs. competitors average
        """

    def calculate_trend(self, days=30) -> TrendDirection:
        """Rolling window trend analysis using linear regression"""

    def generate_reputation_report(self) -> ReputationReport:
        """Weekly reputation report with actionable insights"""
```

**DB table**: `reputation_scores`
```sql
CREATE TABLE reputation_scores (
    id INTEGER PRIMARY KEY,
    business_id TEXT,
    platform TEXT,          -- naver_place, google, kakao, blog, community
    raw_score REAL,         -- platform-native score
    normalized_score REAL,  -- 0-100 normalized
    review_count INTEGER,
    composite_score REAL,   -- weighted composite
    trend TEXT,             -- improving/declining/stable
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Industry benchmark**: Healthcare NPS average is 34 globally, 53 for top performers. Korean healthcare tends to run 40-60 on domestic platforms.

### 1.2 Fake Review Detection and Reporting

**Research findings**:
- Naver has been **tightening review policies** aggressively since October 2025
- May 2025: Additional authentication (location-based, receipt, real-name verification)
- Naver POS integration for receipt-verified reviews
- Academic research on Korean platforms (Naver Shopping) uses: review ratings, image counts, positive/negative text content, review length, repetition of affirmative words
- State-of-art: DeBERTa + Monarch Butterfly Optimizer (MBO-DeBERTa) for fake review detection
- Practical approach: Use existing Gemini AI for Korean-language analysis

**Implementation design**:

```python
class FakeReviewDetector:
    """ML-based fake review detection for Naver Place / Google reviews"""

    SIGNALS = [
        'review_length_anomaly',      # Too short or formulaic
        'timing_pattern',              # Burst of reviews in short window
        'reviewer_profile_age',        # New accounts with single review
        'keyword_stuffing_score',      # Unnatural keyword repetition
        'sentiment_consistency',       # Mismatch between text and rating
        'photo_reuse_detection',       # Same photos across reviews
        'cross_platform_consistency',  # Same reviewer, different stories
    ]

    def analyze_review(self, review: Review) -> FakeReviewResult:
        """
        Returns:
          - fake_probability: 0.0 - 1.0
          - signals_triggered: list of triggered signals
          - recommendation: 'report' | 'flag' | 'clean'
        """

    def batch_analyze_competitor(self, competitor_id: str) -> CompetitorFakeReport:
        """Analyze all competitor reviews for fake patterns"""

    def auto_report(self, review_id: str, platform: str):
        """Submit fake review report to platform (Naver/Google)"""
```

**Naver fake review reporting**: Use Naver Smart Place Center's reporting function programmatically via Selenium automation when confidence > 0.8.

### 1.3 Review Response A/B Testing

**Research findings**:
- A/B testing across 10,000 patient interactions showed **personalized messages mentioning provider name achieved 31% higher response rates** than generic templates
- Adding visit-specific context increased responses another 18%
- Healthcare review responses must be **HIPAA/Korean privacy law compliant** (never reference specific treatments or conditions)
- Implementation timeline: basic setup 2-4 weeks, full integration 6-8 weeks

**Implementation design**:

```python
class ReviewResponseABTester:
    """A/B test review response templates for engagement optimization"""

    TEMPLATE_CATEGORIES = [
        'positive_short',      # 1-2 sentence thank you
        'positive_detailed',   # Personalized with provider name
        'negative_empathetic', # Acknowledge + offer resolution
        'negative_factual',    # Correct misinformation politely
        'neutral_engaging',    # Encourage return visit
    ]

    def create_experiment(self,
                          template_a: str,
                          template_b: str,
                          category: str,
                          target_metric: str = 'engagement_rate') -> Experiment:
        """
        Metrics tracked:
          - Response engagement (likes, replies)
          - Subsequent review sentiment
          - Patient return rate correlation
          - Profile view increase after response
        """

    def generate_response_variant(self, review: Review) -> Tuple[str, str]:
        """Use Gemini to generate two response variants"""

    def evaluate_experiment(self, experiment_id: str) -> ABResult:
        """Statistical significance test (chi-squared) after n responses"""
```

### 1.4 NPS Automation

**Research findings**:
- Healthcare NPS benchmark: average 34, top performers 53-87
- Digital health companies score highest (Hinge Health: 87)
- Best practice: send surveys via SMS/KakaoTalk 24-48 hours after visit
- NPS = % Promoters (9-10) minus % Detractors (0-6)

**Implementation design**:

```python
class NPSAutomation:
    """Automated NPS collection and analysis for healthcare"""

    SURVEY_CHANNELS = ['kakaotalk', 'sms', 'naver_booking']

    def trigger_survey(self, patient_visit: PatientVisit):
        """
        Trigger NPS survey 24-48 hours after visit.
        Channel priority: KakaoTalk > SMS > Email
        """

    def calculate_nps(self, period: str = '30d') -> NPSResult:
        """
        Returns:
          - nps_score: -100 to +100
          - promoters_pct, passives_pct, detractors_pct
          - trend_vs_previous_period
          - benchmark_vs_competitors
        """

    def segment_analysis(self) -> Dict[str, NPSResult]:
        """NPS by treatment type, provider, time of day, etc."""
```

---

## 2. Hyper-Local Targeting

### 2.1 Geo-Fencing Based Marketing Triggers

**Market context**:
- Global geofencing market: $3.22B (2025) -> $11.85B by 2034, CAGR 14.8%
- Healthcare applications: appointment reminders, competitor proximity targeting, event-based triggers
- Case study: ABC Clinic reduced no-shows by 30% with location-based messaging
- Korean context: Naver Place + KakaoMap both support location-based notifications

**Implementation design**:

```python
class GeoFenceManager:
    """Manage geo-fences for hyper-local marketing triggers"""

    FENCE_TYPES = [
        'clinic_proximity',    # Within 500m of our clinic
        'competitor_proximity', # Near competitor clinics
        'residential_area',    # Target residential neighborhoods
        'commercial_district', # Near offices/shopping
        'event_venue',         # Near local event venues
    ]

    def create_fence(self,
                     center_lat: float, center_lng: float,
                     radius_meters: int,
                     fence_type: str,
                     trigger_action: str) -> GeoFence:
        """
        trigger_action options:
          - 'push_notification': Send KakaoTalk notification
          - 'display_ad': Trigger Naver display ad
          - 'content_personalize': Show location-specific content
        """

    def check_triggers(self, user_location: Location) -> List[TriggeredAction]:
        """Evaluate which fences are triggered"""
```

**Korean-specific implementation**:
- Use **Naver Map API** for geocoding and boundary definitions
- **KakaoTalk push** for Korean users (95%+ smartphone penetration)
- Integration with `commercial_district_data` table (already in system from Phase 9-10)
- Compliance: Korean Personal Information Protection Act (PIPA) requires explicit opt-in for location tracking

### 2.2 Neighborhood-Level Content Personalization

**Implementation approach**:

```python
class NeighborhoodPersonalizer:
    """Personalize marketing content by neighborhood characteristics"""

    # Cheongju (청주) neighborhood profiles
    NEIGHBORHOOD_PROFILES = {
        '성안길/중앙동': {
            'demographics': 'commercial_mixed',
            'age_skew': '30-50',
            'content_angle': '직장인 건강관리, 점심시간 진료',
        },
        '복대동/사직동': {
            'demographics': 'residential_family',
            'age_skew': '30-40',
            'content_angle': '소아 성장, 산후조리, 가족건강',
        },
        '분평동/율량동': {
            'demographics': 'new_residential',
            'age_skew': '30-45',
            'content_angle': '신도시 건강검진, 다이어트',
        },
        '수곡동/산남동': {
            'demographics': 'established_residential',
            'age_skew': '40-60',
            'content_angle': '만성질환, 교통사고, 관절',
        },
    }

    def personalize_content(self, base_content: str, neighborhood: str) -> str:
        """Adapt content for neighborhood demographics using Gemini"""

    def generate_neighborhood_campaign(self, neighborhood: str) -> Campaign:
        """Generate location-specific campaign"""
```

### 2.3 Local Event-Based Marketing

**Implementation design**:

```python
class LocalEventTrigger:
    """Monitor local events and trigger relevant marketing content"""

    EVENT_SOURCES = [
        'naver_local_events',      # Naver Place event listings
        'cheongju_city_calendar',  # 청주시 행사 캘린더
        'culture_portal',          # 문화포털 공연/행사
    ]

    EVENT_CONTENT_MAPPING = {
        '마라톤': ['교통사고한의원', '근육통', '스포츠한의원'],
        '축제': ['숙취해소', '체력보강', '면역'],
        '학교행사': ['성장클리닉', '수험생건강', '집중력'],
        '기업행사': ['직장인건강', '스트레스', 'VDT증후군'],
    }

    def scan_upcoming_events(self, days_ahead: int = 14) -> List[LocalEvent]:
        """Scan for upcoming local events"""

    def match_events_to_content(self, events: List[LocalEvent]) -> List[ContentSuggestion]:
        """Map events to relevant healthcare content opportunities"""

    def auto_schedule_content(self, suggestions: List[ContentSuggestion]):
        """Schedule content publication before events"""
```

### 2.4 Weather-Based Marketing

**Research findings**:
- Weather APIs (OpenWeatherMap, Weatherbit) provide 70+ hyper-contextual triggers
- Healthcare-specific triggers: pollen counts, temperature extremes, humidity, seasonal shifts
- Korean seasonal health patterns are well-documented

**Implementation design**:

```python
class WeatherBasedMarketing:
    """Trigger marketing content based on weather conditions"""

    # Korean healthcare weather triggers
    WEATHER_HEALTH_TRIGGERS = {
        'temperature_drop_10': {
            'threshold': '10도 이상 급격한 기온 변화',
            'content_topics': ['환절기 면역', '감기예방 한약', '온열치료'],
            'blog_keywords': ['환절기 건강관리', '청주 보약'],
        },
        'fine_dust_bad': {
            'threshold': 'PM2.5 > 35 (나쁨)',
            'content_topics': ['미세먼지 해독', '폐 건강', '호흡기 한약'],
            'blog_keywords': ['미세먼지 한의원', '청주 호흡기'],
        },
        'high_humidity': {
            'threshold': '습도 80% 이상',
            'content_topics': ['관절통', '습담', '부종관리'],
            'blog_keywords': ['장마철 건강', '습기 관절'],
        },
        'pollen_high': {
            'threshold': '꽃가루 지수 높음',
            'content_topics': ['알레르기', '비염치료', '면역강화'],
            'blog_keywords': ['봄 알레르기 한의원', '비염 한약'],
        },
        'cold_wave': {
            'threshold': '기온 -10도 이하',
            'content_topics': ['동상', '냉증', '보양식', '온보요법'],
            'blog_keywords': ['겨울 한의원', '청주 냉증치료'],
        },
        'heat_wave': {
            'threshold': '기온 33도 이상',
            'content_topics': ['일사병', '여름보약', '수분관리'],
            'blog_keywords': ['여름 보양', '더위 한약'],
        },
    }

    def check_weather_triggers(self, location: str = '청주') -> List[WeatherTrigger]:
        """Check current and forecasted weather against triggers"""

    def generate_weather_content(self, trigger: WeatherTrigger) -> ContentPlan:
        """Generate content plan based on weather trigger using Gemini"""

    def schedule_proactive_content(self, forecast_days: int = 3):
        """Pre-schedule content based on weather forecast"""
```

**API integration**:
```python
# OpenWeatherMap API (free tier: 1000 calls/day)
OPENWEATHER_API = "https://api.openweathermap.org/data/2.5/forecast"

# Korea Meteorological Administration (기상청) API
KMA_API = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"

# AirKorea (미세먼지)
AIRKOREA_API = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc"
```

---

## 3. Patient Lifecycle Automation

### 3.1 Automated Satisfaction Surveys (CSAT/NPS)

**Research findings**:
- Best practice: automated multilingual surveys via SMS or KakaoTalk 24-48 hours after visit
- Journey-based insights identify gaps across the patient lifecycle
- Key KPIs: CSAT, NPS, CES (Customer Effort Score)
- Higher patient satisfaction = stronger margins, better outcomes, higher retention

**Implementation design**:

```python
class PatientSurveyAutomation:
    """Automated post-visit survey system"""

    SURVEY_TYPES = {
        'nps': {
            'question': '율림한의원을 지인에게 추천할 의향이 있으신가요? (0-10)',
            'timing_hours': 48,
            'channel': 'kakaotalk',
        },
        'csat': {
            'question': '오늘 진료에 만족하셨나요? (1-5)',
            'timing_hours': 24,
            'channel': 'kakaotalk',
        },
        'ces': {
            'question': '예약부터 진료까지 얼마나 편하셨나요? (1-7)',
            'timing_hours': 24,
            'channel': 'kakaotalk',
        },
    }

    def trigger_post_visit_survey(self, visit: PatientVisit):
        """Schedule survey after visit based on type"""

    def process_response(self, response: SurveyResponse):
        """
        Process survey response:
          - If NPS <= 6 (detractor): alert staff immediately
          - If NPS >= 9 (promoter): trigger review request
          - Store for analytics
        """

    def generate_insights(self, period: str = '30d') -> SurveyInsights:
        """Aggregate insights from survey responses"""
```

**KakaoTalk integration** (extends existing `kakao/` module):
```python
# Survey message template (must be registered with KakaoTalk Business)
SURVEY_TEMPLATE = {
    'template_type': 'button',
    'message': '안녕하세요, 율림한의원입니다.\n'
               '최근 방문은 만족스러우셨나요?\n'
               '간단한 설문에 응해주시면 감사하겠습니다.',
    'buttons': [
        {'type': 'web_link', 'label': '설문 참여하기', 'url': '{survey_url}'},
    ],
}
```

### 3.2 Treatment-Specific Follow-Up Sequences

**Implementation design**:

```python
class TreatmentFollowUpEngine:
    """Automated follow-up sequences based on treatment type"""

    FOLLOW_UP_SEQUENCES = {
        '다이어트한약': {
            'day_3': {'type': 'check_in', 'message': '한약 복용은 잘 되고 있나요?'},
            'day_7': {'type': 'tip', 'message': '첫 주 식단 관리 팁'},
            'day_14': {'type': 'progress', 'message': '2주차 체중 변화 체크'},
            'day_21': {'type': 'motivation', 'message': '3주차, 변화가 보이시나요?'},
            'day_28': {'type': 'review_request', 'message': '한달 후기를 남겨주세요'},
            'day_60': {'type': 'retention', 'message': '유지 관리 진료 안내'},
        },
        '교통사고치료': {
            'day_1': {'type': 'care', 'message': '치료 후 주의사항 안내'},
            'day_3': {'type': 'check_in', 'message': '통증은 줄어들고 있나요?'},
            'day_7': {'type': 'follow_up', 'message': '다음 진료 일정 확인'},
            'day_30': {'type': 'review', 'message': '보험 서류 필요시 안내'},
            'day_90': {'type': 'retention', 'message': '정기 검진 안내'},
        },
        '침치료': {
            'day_1': {'type': 'care', 'message': '침 치료 후 주의사항'},
            'day_7': {'type': 'follow_up', 'message': '다음 진료 예약 안내'},
            'day_30': {'type': 'review_request', 'message': '치료 후기를 남겨주세요'},
        },
    }

    def start_sequence(self, patient_id: str, treatment_type: str):
        """Start follow-up sequence for patient"""

    def send_scheduled_message(self, message: ScheduledMessage):
        """Send via KakaoTalk / SMS based on patient preference"""

    def handle_response(self, patient_id: str, response: str):
        """
        AI-powered response handling:
          - Positive: continue sequence
          - Negative: escalate to staff
          - Question: match to Q&A repository
        """
```

### 3.3 Seasonal Health Campaign Automation

**Implementation design**:

```python
class SeasonalCampaignEngine:
    """Automated seasonal health campaigns for Korean healthcare"""

    SEASONAL_CAMPAIGNS = {
        '봄_알레르기': {
            'active_months': [3, 4, 5],
            'trigger': 'pollen_index_high OR month_start',
            'keywords': ['봄 알레르기 한의원', '비염치료', '면역강화'],
            'content_themes': ['비염 한약 효과', '봄철 면역관리', '알레르기 예방'],
            'target_audience': '비염/알레르기 환자',
        },
        '여름_보양': {
            'active_months': [6, 7, 8],
            'trigger': 'temperature > 30 OR month_start',
            'keywords': ['여름 보양', '삼복더위 한약', '여름 보약'],
            'content_themes': ['복날 보양 한약', '여름철 체력관리', '냉방병 치료'],
            'target_audience': '체력저하, 만성피로 환자',
        },
        '가을_환절기': {
            'active_months': [9, 10, 11],
            'trigger': 'temperature_change > 10 OR month_start',
            'keywords': ['환절기 건강', '가을 보약', '면역력'],
            'content_themes': ['환절기 감기예방', '가을 보약 추천', '건조함 피부관리'],
            'target_audience': '면역저하, 만성질환 환자',
        },
        '겨울_면역': {
            'active_months': [12, 1, 2],
            'trigger': 'temperature < 0 OR month_start',
            'keywords': ['겨울 면역', '냉증치료', '겨울 보약'],
            'content_themes': ['겨울철 면역관리', '수족냉증 치료', '동지 보약'],
            'target_audience': '냉증, 관절, 면역저하 환자',
        },
        '수능시즌': {
            'active_months': [9, 10, 11],
            'trigger': 'date_range(9/1, 11/15)',
            'keywords': ['수험생 건강', '집중력 한약', '수능 컨디션'],
            'content_themes': ['수험생 체력관리', '집중력 향상 한약', '수능 긴장 완화'],
            'target_audience': '수험생 학부모',
        },
        '신학기': {
            'active_months': [2, 3],
            'trigger': 'month_start',
            'keywords': ['성장클리닉', '소아성장', '키크는한약'],
            'content_themes': ['봄 성장 한약', '신학기 건강검진', '소아 면역'],
            'target_audience': '초등학생 학부모',
        },
    }

    def check_active_campaigns(self) -> List[Campaign]:
        """Check which seasonal campaigns should be active"""

    def generate_campaign_content(self, campaign: Campaign) -> List[Content]:
        """Use Gemini to generate campaign-specific content"""

    def auto_schedule_blog_posts(self, campaign: Campaign):
        """Schedule blog posts throughout the campaign period"""
```

### 3.4 Referral Program Automation

```python
class ReferralProgramEngine:
    """Automated patient referral tracking and rewards"""

    def identify_promoters(self) -> List[Patient]:
        """
        Identify potential referrers:
          - NPS score >= 9
          - Left positive review
          - Visited 3+ times
          - Active on social media
        """

    def generate_referral_code(self, patient_id: str) -> str:
        """Generate unique referral code/link"""

    def send_referral_invitation(self, patient_id: str):
        """
        KakaoTalk message with referral link:
          - Personalized message
          - Trackable link
          - Incentive description
        """

    def track_referral(self, code: str, new_patient_id: str):
        """Track referral conversion"""

    def process_reward(self, referrer_id: str, referred_id: str):
        """Process referral reward (notification to staff)"""
```

---

## 4. Advanced Analytics

### 4.1 Attribution Modeling

**Research findings**:
- 63% of healthcare marketers say attribution models fail to capture ROI due to data fragmentation
- Healthcare patient journeys are longer and more complex than typical consumer journeys
- Multi-touch attribution is critical: Naver Blog -> Naver Place -> Google Search -> Visit
- Organizations using marketing mix modeling see up to 15% stronger ROI
- By 2026, AI-powered predictive attribution models anticipate which channels will drive highest patient LTV

**Implementation design**:

```python
class MarketingAttributionEngine:
    """Multi-touch attribution for healthcare marketing"""

    TOUCHPOINTS = [
        'naver_place_view',       # Naver Place profile view
        'naver_blog_read',        # Blog post read
        'naver_cafe_mention',     # Cafe discussion
        'naver_kin_answer',       # Knowledge iN answer
        'google_search',          # Google organic search
        'google_business_view',   # Google Business Profile
        'instagram_post',         # Instagram content
        'youtube_video',          # YouTube content
        'kakaotalk_message',      # KakaoTalk communication
        'phone_call',             # Direct phone call (from call_tracking)
        'naver_booking',          # Online booking
        'referral',               # Patient referral
        'direct_walkin',          # Walk-in (no digital touchpoint)
    ]

    ATTRIBUTION_MODELS = {
        'first_touch': 'Credit to first interaction',
        'last_touch': 'Credit to final interaction before visit',
        'linear': 'Equal credit to all touchpoints',
        'time_decay': 'More credit to recent touchpoints',
        'position_based': '40% first, 40% last, 20% middle (U-shaped)',
        'data_driven': 'ML-based attribution (Shapley values)',
    }

    def track_touchpoint(self, patient_id: str, touchpoint: Touchpoint):
        """Record a marketing touchpoint"""

    def calculate_attribution(self,
                              model: str = 'position_based',
                              period: str = '90d') -> AttributionResult:
        """
        Returns:
          - channel_contributions: % credit per channel
          - cost_per_acquisition: by channel
          - conversion_paths: most common patient journeys
          - recommendations: budget reallocation suggestions
        """

    def predict_channel_effectiveness(self) -> ChannelForecast:
        """AI prediction: which channels will drive most patients next month"""
```

**Data sources already available in system**:
- `community_mentions` - Blog/Cafe touchpoints
- `call_tracking` - Phone call touchpoints
- `smartplace_stats` - Naver Place views/interactions
- `web_visibility` - Search visibility
- `naver_ad_keyword_data` - Paid ad performance

### 4.2 Customer Lifetime Value (CLV) Prediction

**Research findings**:
- Most healthcare relationships generate $10,000-$20,000 in lifetime value
- Some health systems project values up to $1.2 million across care continuum
- PyMC-Marketing's CLV module provides production-ready Python implementations
- Key factors: visit frequency, service range, retention rates, satisfaction levels

**Implementation design**:

```python
class HealthcareCLVPredictor:
    """Predict Customer Lifetime Value for healthcare patients"""

    CLV_FACTORS = {
        'visit_frequency': 0.30,    # How often they visit
        'treatment_diversity': 0.20, # Range of services used
        'retention_probability': 0.25, # Likelihood of returning
        'referral_value': 0.15,     # Value of referrals generated
        'satisfaction_score': 0.10,  # NPS/CSAT correlation
    }

    def predict_clv(self, patient_id: str, horizon_months: int = 24) -> CLVPrediction:
        """
        Predict CLV using BG/NBD + Gamma-Gamma model (via PyMC-Marketing)

        Returns:
          - predicted_clv: monetary value
          - visit_probability: likelihood of return visit
          - expected_visits: predicted visit count
          - segment: 'high_value' | 'medium_value' | 'at_risk' | 'churned'
        """

    def segment_patients(self) -> Dict[str, List[Patient]]:
        """RFM-based patient segmentation"""

    def identify_at_risk_patients(self) -> List[Patient]:
        """Patients likely to churn based on CLV trends"""

    def recommend_retention_actions(self, patient_id: str) -> List[Action]:
        """AI-recommended actions to retain high-CLV patients"""
```

### 4.3 Cohort Analysis for Patient Retention

**Research findings**:
- Python + Pandas cohort analysis is well-established
- Visualization with seaborn heatmaps is standard
- PyMC-Marketing offers advanced Bayesian cohort modeling
- Key metric: retention rate by cohort month

**Implementation design**:

```python
class PatientCohortAnalyzer:
    """Cohort analysis for patient retention tracking"""

    def create_cohort_matrix(self,
                              cohort_by: str = 'first_visit_month',
                              metric: str = 'retention_rate') -> pd.DataFrame:
        """
        Build cohort retention matrix:
          - Rows: cohort month (first visit)
          - Columns: months since first visit
          - Values: retention rate or revenue
        """

    def visualize_retention_heatmap(self) -> str:
        """Generate retention heatmap (saved as PNG for dashboard)"""

    def compare_treatment_cohorts(self) -> Dict[str, pd.DataFrame]:
        """Compare retention by treatment type"""

    def identify_retention_drivers(self) -> List[RetentionInsight]:
        """AI analysis: what drives patient retention"""
```

### 4.4 Marketing ROI Dashboard

**Implementation design**:

```python
class MarketingROIDashboard:
    """Multi-touch attribution ROI dashboard"""

    DASHBOARD_METRICS = {
        'cost_metrics': [
            'total_marketing_spend',
            'cost_per_lead',
            'cost_per_patient_acquisition',
            'cost_per_channel',
        ],
        'revenue_metrics': [
            'revenue_per_patient',
            'revenue_per_channel',
            'marketing_roi_percentage',
            'roas_by_channel',       # Return on Ad Spend
        ],
        'engagement_metrics': [
            'naver_place_views',
            'blog_traffic',
            'phone_call_volume',
            'booking_conversion_rate',
        ],
        'patient_metrics': [
            'new_patients_this_month',
            'retention_rate',
            'average_clv',
            'nps_score',
        ],
    }

    def generate_roi_report(self, period: str = '30d') -> ROIReport:
        """Comprehensive ROI report with multi-touch attribution"""

    def budget_optimization_recommendation(self) -> BudgetRecommendation:
        """AI-driven budget reallocation suggestions"""
```

**Frontend component**: New dashboard tab in React frontend showing:
- Channel attribution pie chart
- ROI trend over time
- Patient acquisition funnel
- Budget vs. performance comparison

---

## 5. Emerging Channels

### 5.1 Naver Smart Store for Health Products

**Research findings**:
- Naver Smart Store API requires IP registration (enforced since 2025)
- API groups needed: "Product", "Order Seller", "Seller Information"
- New in 2026: Group buying management tool for creators
- Naver is integrating booking/ratings data into credit assessment (March 2026)
- System already has `naver_shop_trend_monitor.py` tracking health product trends

**Implementation design**:

```python
class NaverSmartStoreIntegration:
    """Naver Smart Store integration for health product sales"""

    PRODUCT_CATEGORIES = [
        '한약재', '건강보조식품', '한방화장품',
        '건강기구', '다이어트보조제',
    ]

    def sync_products(self) -> List[Product]:
        """Sync product catalog with Smart Store"""

    def track_sales_metrics(self) -> SalesMetrics:
        """Track health product sales performance"""

    def cross_promote(self, blog_post_id: str, product_ids: List[str]):
        """Cross-promote blog content with related products"""

    def analyze_product_reviews(self) -> ProductReviewAnalysis:
        """Analyze Smart Store product reviews for insights"""
```

### 5.2 Naver Booking API Deep Integration

**Research findings**:
- Naver Smart Place app provides reservation management
- Reservation data can be automatically transmitted to other services
- Real-time reservation/order status dashboard available
- March 2026: Naver booking data being used for credit assessment

**Implementation design**:

```python
class NaverBookingIntegration:
    """Deep integration with Naver Booking system"""

    def sync_bookings(self) -> List[Booking]:
        """Pull booking data from Naver Place"""

    def track_booking_conversion(self) -> ConversionMetrics:
        """
        Track: Naver Place view -> Booking -> Visit -> Repeat
        Feeds into attribution model
        """

    def optimize_booking_page(self) -> List[Recommendation]:
        """AI recommendations for booking page optimization"""

    def automate_booking_reminders(self):
        """Send automated reminders via KakaoTalk before appointments"""

    def handle_cancellation(self, booking_id: str):
        """Automated rebooking flow for cancellations"""
```

### 5.3 Google Business Profile API

**Research findings**:
- GBP API supports: fetch reviews, reply to reviews, list review metadata
- Push notifications available for new reviews
- Can manage multiple locations programmatically
- Healthcare-specific: patient feedback monitoring, HIPAA-compliant responses

**Implementation design**:

```python
class GoogleBusinessProfileManager:
    """Dual-platform management: Naver Place + Google Business Profile"""

    def sync_business_info(self):
        """Keep Naver Place and GBP info in sync"""

    def monitor_reviews(self) -> List[Review]:
        """Real-time review monitoring across both platforms"""

    def respond_to_review(self, review_id: str, response: str):
        """Respond to Google review via API"""

    def compare_platform_performance(self) -> PlatformComparison:
        """Compare Naver vs Google performance metrics"""

    def sync_posts(self, content: str):
        """Post updates to both Naver Place and GBP simultaneously"""
```

**API endpoints**:
```python
# Google Business Profile API
GBP_API_BASE = "https://mybusiness.googleapis.com/v4"
# GET /accounts/{accountId}/locations/{locationId}/reviews
# POST /accounts/{accountId}/locations/{locationId}/reviews/{reviewId}/reply
```

### 5.4 Threads / BlueSky Social Monitoring

**Research findings**:
- Threads: 400M MAU (August 2025), 115.1M daily active users
- Bluesky: 41.41M users (December 2025), 2026 roadmap includes better Discover feed and real-time features
- Social monitoring market: $6.56B (2026)
- Most monitoring tools (Brand24, Mention, Awario) added Threads support; Bluesky coverage is limited
- Recommendation: Use Threads for audience growth, Bluesky for authenticity testing

**Implementation design**:

```python
class EmergingSocialMonitor:
    """Monitor Threads and BlueSky for healthcare mentions"""

    PLATFORMS = {
        'threads': {
            'api': 'Meta Threads API',  # Instagram-based auth
            'monitoring': ['brand_mentions', 'keyword_tracking', 'competitor_activity'],
            'priority': 'medium',  # Growing Korean user base
        },
        'bluesky': {
            'api': 'AT Protocol API',   # Open API
            'monitoring': ['brand_mentions', 'healthcare_discussions'],
            'priority': 'low',  # Small Korean user base
        },
    }

    def monitor_mentions(self, platform: str) -> List[SocialMention]:
        """Track brand and keyword mentions"""

    def analyze_sentiment(self, mentions: List[SocialMention]) -> SentimentReport:
        """Analyze sentiment of social mentions using Gemini"""

    def identify_influencers(self, platform: str) -> List[Influencer]:
        """Find healthcare-related influencers on emerging platforms"""
```

---

## 6. Workflow Automation

### 6.1 Workflow Engine Options

**Research findings**:

**n8n (Recommended for immediate use)**:
- Open-source, self-hosted workflow automation
- 2,740+ marketing automation templates
- Pattern: "AI proposes -> rules validate -> workflow executes -> humans approve"
- Webhook triggers + HTTP Request nodes for connecting to any API
- Active community, strong 2026 growth
- n8n + Telegram integration template already exists for inline keyboard menus

**Temporal (Recommended for long-term)**:
- Durable execution platform: code runs to completion even through crashes
- Raised $300M at $5B valuation (Feb 2026)
- 1.86 trillion executions from AI companies
- OpenAI integrated Temporal into their Agents SDK (Feb 2026)
- Python SDK available with Pydantic AI integration
- Best for: long-running workflows, critical business processes, AI pipelines

**Comparison for this system**:

| Feature | n8n | Temporal | Current (workflow_engine.py) |
|---------|-----|----------|------------------------------|
| Durability | Low (in-memory) | Very High (event-sourced) | Low |
| Complexity | Low | High | Medium |
| Visual Editor | Yes | No | No |
| Self-hosted | Yes | Yes | N/A (built-in) |
| Python SDK | No (JS/TS) | Yes | Yes |
| Learning Curve | Low | High | Low |
| Best For | Simple triggers | Complex multi-step | Basic event chains |

**Recommendation**:
- Phase 1: Enhance current `core/workflow_engine.py` with durability (SQLite state persistence)
- Phase 2: Adopt Temporal for complex patient lifecycle workflows
- Use n8n for visual workflow building if non-developer staff need to create workflows

### 6.2 Enhanced Trigger-Based Automation

**Implementation design** (extends existing `core/workflow_engine.py`):

```python
class AdvancedTriggerEngine:
    """Advanced trigger system for marketing automation"""

    TRIGGER_DEFINITIONS = {
        'rank_drop_alert': {
            'event': 'rank_change',
            'condition': lambda e: e['new_rank'] > e['old_rank'] + 5,
            'actions': [
                'notify_telegram',
                'analyze_competitor_change',
                'generate_recovery_plan',
                'schedule_extra_content',
            ],
        },
        'negative_review_escalation': {
            'event': 'new_review',
            'condition': lambda e: e['rating'] <= 2,
            'actions': [
                'notify_telegram_urgent',
                'generate_response_draft',
                'schedule_staff_followup',
                'log_to_reputation_tracker',
            ],
        },
        'competitor_surge': {
            'event': 'competitor_rank_change',
            'condition': lambda e: e['competitor_rank_improvement'] > 10,
            'actions': [
                'analyze_competitor_strategy',
                'generate_counter_content',
                'notify_telegram',
            ],
        },
        'viral_opportunity': {
            'event': 'trending_keyword',
            'condition': lambda e: e['trend_velocity'] > 200,
            'actions': [
                'generate_trending_content',
                'schedule_immediate_post',
                'notify_telegram',
            ],
        },
        'patient_churn_risk': {
            'event': 'patient_activity',
            'condition': lambda e: e['days_since_last_visit'] > 90,
            'actions': [
                'send_reactivation_campaign',
                'offer_special_promotion',
                'notify_staff',
            ],
        },
        'weather_health_trigger': {
            'event': 'weather_change',
            'condition': lambda e: e['trigger_type'] in WeatherBasedMarketing.WEATHER_HEALTH_TRIGGERS,
            'actions': [
                'generate_weather_content',
                'schedule_social_posts',
                'activate_targeted_ads',
            ],
        },
    }

    def register_trigger(self, trigger_def: TriggerDefinition):
        """Register a new trigger"""

    def evaluate_triggers(self, event: Event) -> List[TriggeredAction]:
        """Evaluate all triggers against an event"""

    def execute_action_chain(self, actions: List[Action], context: Dict):
        """Execute chain of actions with error handling and rollback"""
```

### 6.3 Telegram Approval Workflows

**Research findings**:
- Telegram inline keyboards support callback buttons (no message sent to chat)
- python-telegram-bot library provides InlineKeyboardButton/InlineKeyboardMarkup
- n8n has a Telegram bot inline keyboard template for dynamic menus
- Callback data is limited to 64 bytes

**Implementation design** (extends existing `alert_bot.py`):

```python
class TelegramApprovalWorkflow:
    """Telegram-based approval workflows with inline keyboards"""

    APPROVAL_TYPES = {
        'content_publish': {
            'description': '블로그 콘텐츠 발행 승인',
            'buttons': [
                ('승인', 'approve_content'),
                ('수정요청', 'revise_content'),
                ('거부', 'reject_content'),
            ],
        },
        'review_response': {
            'description': '리뷰 답변 승인',
            'buttons': [
                ('발행', 'approve_response'),
                ('수정', 'edit_response'),
                ('스킵', 'skip_response'),
            ],
        },
        'ad_budget_change': {
            'description': '광고 예산 변경 승인',
            'buttons': [
                ('승인', 'approve_budget'),
                ('거부', 'reject_budget'),
            ],
        },
        'escalation_response': {
            'description': '부정리뷰 대응 승인',
            'buttons': [
                ('대응', 'respond_escalation'),
                ('무시', 'ignore_escalation'),
                ('상위보고', 'escalate_further'),
            ],
        },
    }

    async def send_approval_request(self,
                                     approval_type: str,
                                     context: Dict[str, Any]) -> str:
        """
        Send inline keyboard approval request to Telegram.
        Returns: message_id for tracking
        """

    async def handle_callback(self, callback_query: CallbackQuery):
        """Process inline button callback and execute corresponding action"""

    def create_inline_keyboard(self, buttons: List[Tuple[str, str]]) -> InlineKeyboardMarkup:
        """Create Telegram inline keyboard"""
```

---

## 7. Implementation Priority Matrix

| Feature | Impact | Effort | Priority | Dependencies |
|---------|--------|--------|----------|--------------|
| **Reputation Score Engine** | HIGH | MEDIUM | P1 | Naver Place star rating (Apr 2026) |
| **Weather-Based Marketing** | HIGH | LOW | P1 | OpenWeatherMap API key |
| **Seasonal Campaign Engine** | HIGH | LOW | P1 | Content factory integration |
| **Advanced Triggers** | HIGH | MEDIUM | P1 | Existing workflow_engine.py |
| **Telegram Approval Workflows** | MEDIUM | LOW | P1 | Existing alert_bot.py |
| **NPS Automation** | HIGH | MEDIUM | P2 | KakaoTalk Business API |
| **Treatment Follow-Ups** | HIGH | MEDIUM | P2 | Patient data integration |
| **Attribution Modeling** | HIGH | HIGH | P2 | Multiple data source integration |
| **Google Business Profile** | MEDIUM | MEDIUM | P2 | GBP API credentials |
| **Fake Review Detection** | MEDIUM | HIGH | P2 | ML model training |
| **Review A/B Testing** | MEDIUM | MEDIUM | P3 | Review response system |
| **CLV Prediction** | MEDIUM | HIGH | P3 | Patient financial data |
| **Cohort Analysis** | MEDIUM | MEDIUM | P3 | Patient visit data |
| **Geo-Fencing** | MEDIUM | HIGH | P3 | Location permissions, PIPA compliance |
| **Naver Smart Store** | LOW | HIGH | P3 | Smart Store seller account |
| **Naver Booking Deep** | MEDIUM | HIGH | P3 | Naver Partner API access |
| **Neighborhood Personalization** | LOW | MEDIUM | P4 | Neighborhood data collection |
| **Referral Program** | LOW | MEDIUM | P4 | Patient management system |
| **Threads/BlueSky Monitoring** | LOW | LOW | P4 | Small Korean user base |
| **Temporal Adoption** | MEDIUM | VERY HIGH | P4 | Major architecture change |
| **ROI Dashboard** | HIGH | HIGH | P4 | Attribution model complete |

---

## 8. Architecture Recommendations

### 8.1 Recommended Implementation Order

**Phase 1 (Weeks 1-4): Quick Wins**
1. Reputation Score Engine - Leverage existing review data + new Naver star ratings
2. Weather-Based Marketing - Simple API integration, high content output
3. Seasonal Campaign Engine - Configuration-driven, uses existing content factory
4. Enhanced Triggers - Build on existing workflow_engine.py and event_bus.py
5. Telegram Approval Workflows - Extend existing alert_bot.py

**Phase 2 (Months 2-3): Core Capabilities**
1. NPS/CSAT Automation - Requires KakaoTalk Business API setup
2. Treatment Follow-Up Sequences - Requires patient data structure
3. Attribution Modeling - Connect existing data sources
4. Google Business Profile - Dual platform management

**Phase 3 (Months 3-5): Advanced Features**
1. Fake Review Detection - ML model development
2. Review A/B Testing - Statistical framework
3. CLV Prediction - PyMC-Marketing integration
4. Cohort Analysis - Analytics infrastructure

**Phase 4 (Months 5+): Future Vision**
1. Geo-fencing with privacy compliance
2. Naver Smart Store / Booking deep integration
3. Temporal workflow engine migration
4. Full ROI dashboard

### 8.2 New DB Tables Required

```sql
-- Reputation Management 2.0
CREATE TABLE reputation_scores (...);
CREATE TABLE fake_review_flags (...);
CREATE TABLE review_ab_experiments (...);
CREATE TABLE nps_surveys (...);
CREATE TABLE nps_responses (...);

-- Patient Lifecycle
CREATE TABLE patient_surveys (...);
CREATE TABLE treatment_followups (...);
CREATE TABLE seasonal_campaigns (...);
CREATE TABLE referral_tracking (...);

-- Advanced Analytics
CREATE TABLE marketing_touchpoints (...);
CREATE TABLE attribution_results (...);
CREATE TABLE patient_clv (...);
CREATE TABLE patient_cohorts (...);

-- Emerging Channels
CREATE TABLE gbp_reviews (...);
CREATE TABLE social_mentions_emerging (...);

-- Workflow
CREATE TABLE workflow_approvals (...);
CREATE TABLE trigger_execution_log (...);
```

### 8.3 External API Keys Required

| API | Purpose | Free Tier | Priority |
|-----|---------|-----------|----------|
| OpenWeatherMap | Weather triggers | 1000 calls/day | P1 |
| KMA (기상청) API | Korean weather data | Free (data.go.kr) | P1 |
| AirKorea API | Fine dust data | Free (data.go.kr) | P1 |
| Google Business Profile API | GBP management | Free | P2 |
| KakaoTalk Business API | Patient messaging | Paid | P2 |
| Naver Smart Store API | Product management | Free | P3 |
| Threads API (Meta) | Social monitoring | Free | P4 |
| Bluesky AT Protocol | Social monitoring | Free | P4 |

---

## Sources

### Reputation Management
- [Healthcare Reputation Management Software 2026 - Birdeye](https://birdeye.com/blog/healthcare-reputation-management-software/)
- [Healthcare Reputation Management Software 2026 - Psychreg](https://www.psychreg.org/top-healthcare-reputation-management-software-2026/)
- [AI in Healthcare Marketing 2026 - Keragon](https://www.keragon.com/blog/ai-in-healthcare-marketing)
- [Reputation Management Tools 2026 - TEAM LEWIS](https://www.teamlewis.com/magazine/top-reputation-management-tools/)
- [AI-Generated Review Detection - SCITEPRESS](https://www.scitepress.org/Papers/2025/135720/135720.pdf)
- [Fake Review Detection DeBERTa - Nature Scientific Reports](https://www.nature.com/articles/s41598-025-89453-8)

### Naver Place / Korean Market
- [Naver Place 2026 Algorithm - PineAd](https://pinead.co.kr/%EB%84%A4%EC%9D%B4%EB%B2%84-%ED%94%8C%EB%A0%88%EC%9D%B4%EC%8A%A4-%EC%83%81%EC%9C%84%EB%85%B8%EC%B6%9C-%EB%8B%A4%EA%B0%80-%EC%98%AC-2026%EB%85%84%EC%9D%84-%EC%9C%84%ED%95%9C-%ED%95%B5%EC%8B%AC/)
- [Naver Place Star Rating Launch - MoneyToday](https://www.mt.co.kr/tech/2026/03/18/2026031809075469786)
- [Naver Place Review Overhaul - AjuNews](https://www.ajunews.com/view/20260318093445140)
- [Naver Place Review Policy - iBoss](https://www.i-boss.co.kr/ab-6141-66992)
- [2026 Hospital Marketing Strategies - AdFlyer](https://adflyercompany.com/2024-%EB%B3%91%EC%9B%90%EB%A7%88%EC%BC%80%ED%8C%85-%EC%A0%84%EB%9E%B5/)
- [2026 Local Marketing: Naver Place - StoreArt Magazine](https://www.storeartmagazine.com/news/articleView.html?idxno=1049)
- [Naver Booking Data for SME Lending - Seoul Economic Daily](https://en.sedaily.com/finance/2026/03/09/naver-ratings-booking-data-to-ease-small-business-lending)
- [Naver Smart Store Group Buying - Seoul Economic Daily](https://en.sedaily.com/finance/2026/01/06/naver-launches-group-buying-feature-for-smart-store-on)

### Patient Experience & NPS
- [Patient Experience Tools 2026 - Zonka](https://www.zonkafeedback.com/blog/patient-experience-tools)
- [NPS in Healthcare - Viseven](https://viseven.com/healthcare-net-promoter-score/)
- [NPS Scores by Industry 2026 - Sybill](https://www.sybill.ai/blogs/nps-scores-of-companies-2026-benchmarks-industry-standards-and-how-to-calculate-your-net-promoter-score)
- [Patient Satisfaction Survey Guide - Curogram](https://curogram.com/blog/types-of-patient-satisfaction-surveys)
- [Medical Survey System 2026 - DoctorConnect](https://doctorconnect.net/surveys-for-the-best-medical-survey-system-2026/)

### Attribution & Analytics
- [Healthcare Marketing Attribution 2026 - Anzolo Medical](https://business.anzolomed.com/healthcare-marketing-attribution-in-2026-how-medical-practices-can-track-roi-when-traditional-analytics-fail/)
- [Healthcare Marketing Metrics 2026 - Evokad](https://evokad.com/healthcare-marketing-metrics-patient-growth-2026/)
- [Marketing Attribution Guide 2026 - KEO Marketing](https://keomarketing.com/marketing-analytics-attribution-guide-150191-3)
- [Multi-Touch Attribution Guide - Northbeam](https://www.northbeam.io/blog/multi-touch-attribution-models-guide)
- [Patient Acquisition ROI Guide - Anzolo Medical](https://business.anzolomed.com/patient-acquisition-roi-the-complete-2025-guide-to-measuring-and-maximizing-healthcare-marketing-returns/)
- [Cohort Analysis Python - GitHub](https://github.com/tranthienmy22/cohort-analysis-customer-retention)
- [Cohort Retention in PyMC - Dr. Orduz](https://juanitorduz.github.io/retention/)

### Geo-Fencing & Hyper-Local
- [Geofencing Market Size - Fortune Business Insights](https://www.fortunebusinessinsights.com/geofencing-market-108565)
- [Micro Geofencing for Urban Marketing 2026 - Influencers Time](https://www.influencers-time.com/micro-geofencing-transforming-urban-marketing-in-2026/)
- [Geofencing for Healthcare - FetchFunnel](https://www.fetchfunnel.com/geofencing-for-healthcare-complete-guide/)
- [Geofencing Marketing for Hospitals - Propellant Media](https://propellant.media/geofencing-marketing-for-hospital-patient-targeting/)

### Weather-Based Marketing
- [Weather Targeting - The Weather Company](https://www.weathercompany.com/advertising/weather-targeting/)
- [Weather-Based Marketing Guide - WeatherAds](https://www.weatherads.io/blog/the-complete-guide-to-weather-based-marketing)
- [AI-Driven Dynamic Ads with Weather - Influencers Time](https://www.influencers-time.com/ai-driven-dynamic-ads-personalize-with-live-weather-data/)

### Emerging Channels
- [Bluesky vs Threads 2026 - Lovable](https://lovable.dev/guides/bluesky-vs-threads)
- [Bluesky 2026 Roadmap - TechCrunch](https://techcrunch.com/2026/01/27/bluesky-teases-2026-roadmap-a-better-discover-feed-real-time-features-and-more/)
- [Social Media Monitoring Tools 2026 - Statusbrew](https://statusbrew.com/insights/social-media-monitoring-tools)
- [Google Business Profile API - Google Developers](https://developers.google.com/my-business/content/review-data)
- [Review Automation Software 2026 - Reviewflowz](https://www.reviewflowz.com/blog/review-automation-software)
- [Automated Review Responses 2026 - RepliFast](https://www.replifast.com/blog/automated-google-review-responses)

### Workflow Automation
- [n8n for Marketing 2026 - Marketing Agent Blog](https://marketingagent.blog/2026/01/22/n8n-for-marketing-in-2026-the-automation-fabric-behind-ai-first-growth-with-real-workflow-examples/)
- [n8n Workflow Automation 2026 Guide - Medium](https://medium.com/@aksh8t/n8n-workflow-automation-the-2026-guide-to-building-ai-powered-workflows-that-actually-work-cd62f22afcc8)
- [Temporal Durable Execution 2026 - byteiota](https://byteiota.com/temporal-tutorial-durable-execution-in-python-2026/)
- [Temporal Workflow Engine Guide 2026 - Kunal Ganglani](https://www.kunalganglani.com/blog/temporal-workflow-engine-guide)
- [Telegram Bot Inline Keyboard - python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot/blob/master/examples/inlinekeyboard.py)
- [Telegram Bot Inline Keyboard n8n Template](https://n8n.io/workflows/7664-telegram-bot-inline-keyboard-with-dynamic-menus-and-rating-system/)
- [AI-Native Hospital Trends 2026 - Makebot](https://www.makebot.ai/blog/ai-native-byeongweonyi-sidae-2026nyeon-yiryo-hyeogsineul-gyujeonghaneun-10dae-teurendeu)
