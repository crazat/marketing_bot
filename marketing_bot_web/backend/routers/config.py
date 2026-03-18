"""
Config API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 6.1] keywords.json 웹 편집 API
설정 파일 조회 및 수정 API
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Literal
from pydantic import BaseModel, Field
import os
import json
from pathlib import Path
from datetime import datetime

import sys
# 프로젝트 루트
parent_dir = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, parent_dir)

from backend_utils.error_handlers import handle_exceptions

router = APIRouter()

# 설정 파일 경로
KEYWORDS_FILE = os.path.join(parent_dir, 'config', 'keywords.json')
KEYWORDS_BACKUP_DIR = os.path.join(parent_dir, 'config', 'backups')


KeywordCategory = Literal["naver_place", "blog_seo"]


class KeywordsData(BaseModel):
    """키워드 데이터 모델"""
    naver_place: List[str] = []
    blog_seo: List[str] = []


class KeywordAddRequest(BaseModel):
    """키워드 추가 요청"""
    keyword: str = Field(..., min_length=1, max_length=100)
    category: KeywordCategory = "naver_place"


class KeywordDeleteRequest(BaseModel):
    """키워드 삭제 요청"""
    keyword: str = Field(..., min_length=1, max_length=100)
    category: KeywordCategory = "naver_place"


class KeywordMoveRequest(BaseModel):
    """키워드 이동 요청"""
    keyword: str = Field(..., min_length=1, max_length=100)
    from_category: KeywordCategory
    to_category: KeywordCategory


def load_keywords() -> Dict[str, List[str]]:
    """keywords.json 로드"""
    default_data = {
        "naver_place": [],
        "blog_seo": []
    }

    if not os.path.exists(KEYWORDS_FILE):
        return default_data

    try:
        with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 필수 키가 없으면 추가
        for key in default_data:
            if key not in data:
                data[key] = []
        return data
    except Exception as e:
        print(f"[Config] keywords.json 로드 실패: {e}")
        return default_data


def save_keywords(data: Dict[str, List[str]], create_backup: bool = True) -> bool:
    """keywords.json 저장"""
    try:
        # 백업 생성
        if create_backup and os.path.exists(KEYWORDS_FILE):
            os.makedirs(KEYWORDS_BACKUP_DIR, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(KEYWORDS_BACKUP_DIR, f"keywords_{timestamp}.json")
            with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
                backup_data = f.read()
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(backup_data)

        # 저장
        os.makedirs(os.path.dirname(KEYWORDS_FILE), exist_ok=True)
        with open(KEYWORDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[Config] keywords.json 저장 실패: {e}")
        return False


@router.get("/keywords")
async def get_keywords() -> Dict[str, Any]:
    """
    [Phase 6.1] keywords.json 조회

    Returns:
        - naver_place: 네이버 플레이스 키워드 목록
        - blog_seo: 블로그 SEO 키워드 목록
        - total_count: 전체 키워드 수
    """
    try:
        data = load_keywords()

        return {
            "naver_place": data.get("naver_place", []),
            "blog_seo": data.get("blog_seo", []),
            "total_count": len(data.get("naver_place", [])) + len(data.get("blog_seo", []))
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"키워드 조회 실패: {str(e)}"
        )


@router.put("/keywords")
async def update_keywords(keywords_data: KeywordsData) -> Dict[str, Any]:
    """
    [Phase 6.1] keywords.json 전체 업데이트

    Args:
        naver_place: 네이버 플레이스 키워드 목록
        blog_seo: 블로그 SEO 키워드 목록

    Returns:
        - success: 성공 여부
        - message: 결과 메시지
    """
    try:
        data = {
            "naver_place": keywords_data.naver_place,
            "blog_seo": keywords_data.blog_seo
        }

        if save_keywords(data):
            total_count = len(data["naver_place"]) + len(data["blog_seo"])
            return {
                "success": True,
                "message": f"키워드가 저장되었습니다 (총 {total_count}개)",
                "total_count": total_count
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="키워드 저장 실패"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"키워드 업데이트 실패: {str(e)}"
        )


@router.post("/keywords/add")
async def add_keyword(request: KeywordAddRequest) -> Dict[str, Any]:
    """
    [Phase 6.1] 키워드 추가

    Args:
        keyword: 추가할 키워드
        category: naver_place 또는 blog_seo

    Returns:
        - success: 성공 여부
        - message: 결과 메시지
    """
    try:
        keyword = request.keyword.strip()
        category = request.category

        if not keyword:
            raise HTTPException(status_code=400, detail="키워드를 입력하세요")

        if category not in ["naver_place", "blog_seo"]:
            raise HTTPException(status_code=400, detail="잘못된 카테고리입니다")

        data = load_keywords()

        # 이미 존재하는지 확인 (전체 카테고리에서)
        all_keywords = data.get("naver_place", []) + data.get("blog_seo", [])
        if keyword in all_keywords:
            raise HTTPException(status_code=400, detail=f"'{keyword}'는 이미 등록된 키워드입니다")

        # 추가
        data[category].append(keyword)

        if save_keywords(data):
            return {
                "success": True,
                "message": f"'{keyword}'가 {category}에 추가되었습니다",
                "category": category,
                "keyword": keyword
            }
        else:
            raise HTTPException(status_code=500, detail="키워드 저장 실패")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"키워드 추가 실패: {str(e)}"
        )


@router.post("/keywords/delete")
async def delete_keyword(request: KeywordDeleteRequest) -> Dict[str, Any]:
    """
    [Phase 6.1] 키워드 삭제

    Args:
        keyword: 삭제할 키워드
        category: naver_place 또는 blog_seo

    Returns:
        - success: 성공 여부
        - message: 결과 메시지
    """
    try:
        keyword = request.keyword.strip()
        category = request.category

        if category not in ["naver_place", "blog_seo"]:
            raise HTTPException(status_code=400, detail="잘못된 카테고리입니다")

        data = load_keywords()

        if keyword not in data.get(category, []):
            raise HTTPException(status_code=404, detail=f"'{keyword}'를 찾을 수 없습니다")

        # 삭제
        data[category].remove(keyword)

        if save_keywords(data):
            return {
                "success": True,
                "message": f"'{keyword}'가 삭제되었습니다",
                "category": category,
                "keyword": keyword
            }
        else:
            raise HTTPException(status_code=500, detail="키워드 저장 실패")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"키워드 삭제 실패: {str(e)}"
        )


@router.post("/keywords/move")
async def move_keyword(request: KeywordMoveRequest) -> Dict[str, Any]:
    """
    [Phase 6.1] 키워드 카테고리 이동

    Args:
        keyword: 이동할 키워드
        from_category: 원본 카테고리
        to_category: 대상 카테고리

    Returns:
        - success: 성공 여부
        - message: 결과 메시지
    """
    try:
        keyword = request.keyword.strip()
        from_cat = request.from_category
        to_cat = request.to_category

        if from_cat not in ["naver_place", "blog_seo"] or to_cat not in ["naver_place", "blog_seo"]:
            raise HTTPException(status_code=400, detail="잘못된 카테고리입니다")

        if from_cat == to_cat:
            raise HTTPException(status_code=400, detail="같은 카테고리로는 이동할 수 없습니다")

        data = load_keywords()

        if keyword not in data.get(from_cat, []):
            raise HTTPException(status_code=404, detail=f"'{keyword}'를 {from_cat}에서 찾을 수 없습니다")

        # 이동
        data[from_cat].remove(keyword)
        data[to_cat].append(keyword)

        if save_keywords(data):
            return {
                "success": True,
                "message": f"'{keyword}'가 {from_cat}에서 {to_cat}로 이동되었습니다",
                "keyword": keyword,
                "from_category": from_cat,
                "to_category": to_cat
            }
        else:
            raise HTTPException(status_code=500, detail="키워드 저장 실패")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"키워드 이동 실패: {str(e)}"
        )


@router.get("/keywords/backups")
async def get_keywords_backups() -> Dict[str, Any]:
    """
    [Phase 6.1] keywords.json 백업 목록 조회

    Returns:
        - backups: 백업 파일 목록
        - total: 전체 백업 수
    """
    try:
        backups = []

        if os.path.exists(KEYWORDS_BACKUP_DIR):
            for filename in sorted(os.listdir(KEYWORDS_BACKUP_DIR), reverse=True):
                if filename.startswith("keywords_") and filename.endswith(".json"):
                    filepath = os.path.join(KEYWORDS_BACKUP_DIR, filename)
                    stat = os.stat(filepath)
                    backups.append({
                        "filename": filename,
                        "size_kb": round(stat.st_size / 1024, 1),
                        "created": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })

        return {
            "backups": backups[:10],  # 최근 10개만
            "total": len(backups)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"백업 목록 조회 실패: {str(e)}"
        )


@router.post("/keywords/restore/{filename}")
async def restore_keywords_backup(filename: str) -> Dict[str, Any]:
    """
    [Phase 6.1] keywords.json 백업 복원

    Args:
        filename: 복원할 백업 파일명

    Returns:
        - success: 성공 여부
        - message: 결과 메시지
    """
    try:
        backup_path = os.path.join(KEYWORDS_BACKUP_DIR, filename)

        if not os.path.exists(backup_path):
            raise HTTPException(status_code=404, detail="백업 파일을 찾을 수 없습니다")

        # 백업 파일 로드
        with open(backup_path, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)

        # 현재 파일 백업 후 복원
        if save_keywords(backup_data, create_backup=True):
            return {
                "success": True,
                "message": f"'{filename}' 백업이 복원되었습니다"
            }
        else:
            raise HTTPException(status_code=500, detail="복원 실패")

    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="잘못된 백업 파일 형식입니다")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"백업 복원 실패: {str(e)}"
        )


# ============================================
# [Phase 7.0] Business Profile API
# ============================================

BUSINESS_PROFILE_FILE = os.path.join(parent_dir, 'config', 'business_profile.json')


def load_business_profile() -> Dict[str, Any]:
    """business_profile.json 로드"""
    default_profile = {
        "business": {
            "name": "",
            "short_name": "",
            "english_name": "",
            "industry": "",
            "region": "",
            "address": ""
        },
        "categories": {
            "main": [],
            "category_keywords": {},
            "category_colors": {}
        },
        "branding": {
            "signatures": {}
        }
    }

    if not os.path.exists(BUSINESS_PROFILE_FILE):
        return default_profile

    try:
        with open(BUSINESS_PROFILE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[Config] business_profile.json 로드 실패: {e}")
        return default_profile


@router.get("/business-profile")
async def get_business_profile() -> Dict[str, Any]:
    """
    [Phase 7.0] business_profile.json 조회

    비즈니스 설정, 카테고리, 브랜딩 정보를 반환합니다.

    Returns:
        - business: 업체 정보 (name, region, industry 등)
        - categories: 카테고리 정보 (main, keywords, colors)
        - branding: 브랜딩 정보 (signatures)
        - service_keywords: 서비스 키워드
        - priority_keywords: 우선순위 키워드
    """
    try:
        profile = load_business_profile()
        return profile
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"비즈니스 프로필 조회 실패: {str(e)}"
        )


@router.get("/categories")
async def get_categories() -> Dict[str, Any]:
    """
    [Phase 7.0] 카테고리 목록만 조회

    Returns:
        - categories: 메인 카테고리 목록
        - category_keywords: 카테고리별 키워드
        - category_colors: 카테고리별 색상
    """
    try:
        profile = load_business_profile()
        categories_data = profile.get("categories", {})

        return {
            "categories": categories_data.get("main", []),
            "category_keywords": categories_data.get("category_keywords", {}),
            "category_colors": categories_data.get("category_colors", {})
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"카테고리 조회 실패: {str(e)}"
        )


@router.get("/branding")
async def get_branding() -> Dict[str, Any]:
    """
    [Phase 7.0] 브랜딩 정보 조회

    Returns:
        - business_name: 업체명
        - region: 지역
        - tagline: 태그라인
        - signatures: 플랫폼별 서명
    """
    try:
        profile = load_business_profile()
        business = profile.get("business", {})
        branding = profile.get("branding", {})

        return {
            "business_name": business.get("name", ""),
            "short_name": business.get("short_name", ""),
            "region": business.get("region", ""),
            "tagline": branding.get("tagline", ""),
            "signatures": branding.get("signatures", {})
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"브랜딩 정보 조회 실패: {str(e)}"
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4] 설정 파일 뷰어
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/view")
async def view_config_file(file: str = "keywords") -> Dict[str, Any]:
    """
    설정 파일 내용 조회 (읽기 전용)
    
    Args:
        file: 파일 종류 (keywords, config, schedule)
    
    Returns:
        파일 내용 및 메타데이터
    """
    try:
        # 파일 경로 매핑
        file_map = {
            'keywords': os.path.join(parent_dir, 'config', 'keywords.json'),
            'config': os.path.join(parent_dir, 'config', 'config.json'),
            'schedule': os.path.join(parent_dir, 'config', 'schedule.json')
        }
        
        if file not in file_map:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 파일: {file}"
            )
        
        file_path = file_map[file]
        
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=404,
                detail=f"파일을 찾을 수 없습니다: {file}"
            )
        
        # 파일 읽기
        with open(file_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        
        # config.json은 민감한 정보 마스킹
        if file == 'config':
            content = mask_sensitive_data(content)
        
        # 파일 정보
        file_stat = os.stat(file_path)
        
        return {
            'file': file,
            'content': content,
            'metadata': {
                'size_bytes': file_stat.st_size,
                'modified': datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                'path': file_path
            }
        }
        
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"JSON 파싱 실패: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"파일 조회 실패: {str(e)}"
        )


def mask_sensitive_data(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    민감한 정보 마스킹
    
    Args:
        config: 원본 설정
    
    Returns:
        마스킹된 설정
    """
    masked = config.copy()
    
    # API 키 마스킹
    sensitive_keys = [
        'gemini_api_key',
        'naver_client_id',
        'naver_client_secret',
        'password',
        'secret',
        'token',
        'key'
    ]
    
    def mask_recursive(obj):
        if isinstance(obj, dict):
            return {
                k: '***MASKED***' if any(sk in k.lower() for sk in sensitive_keys) 
                else mask_recursive(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [mask_recursive(item) for item in obj]
        else:
            return obj
    
    return mask_recursive(masked)
