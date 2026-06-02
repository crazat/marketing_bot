"""Configuration APIs for keywords and business profile files."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from utils.json_io import atomic_write_json, json_file_lock

parent_dir = str(Path(__file__).parent.parent.parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

router = APIRouter()

KEYWORDS_FILE = os.path.join(parent_dir, "config", "keywords.json")
KEYWORDS_BACKUP_DIR = os.path.join(parent_dir, "config", "backups")
KEYWORDS_BACKUP_NAME_RE = re.compile(r"^keywords_\d{8}_\d{6}(?:_\d{1,6})?\.json$")
KEYWORDS_FILE_LOCK = threading.RLock()
KEYWORD_CATEGORIES = ("naver_place", "blog_seo")
MAX_KEYWORD_LENGTH = 100

BUSINESS_PROFILE_FILE = os.path.join(parent_dir, "config", "business_profile.json")

KeywordCategory = Literal["naver_place", "blog_seo"]


class KeywordsData(BaseModel):
    naver_place: List[str] = []
    blog_seo: List[str] = []


class KeywordAddRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=MAX_KEYWORD_LENGTH)
    category: KeywordCategory = "naver_place"


class KeywordDeleteRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=MAX_KEYWORD_LENGTH)
    category: KeywordCategory = "naver_place"


class KeywordMoveRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=MAX_KEYWORD_LENGTH)
    from_category: KeywordCategory
    to_category: KeywordCategory


def _normalize_keywords_payload(data: Dict[str, Any]) -> Dict[str, List[str]]:
    """Validate, trim, and deduplicate keyword config while preserving order."""
    if not isinstance(data, dict):
        raise ValueError("keywords data must be an object")

    normalized: Dict[str, List[str]] = {category: [] for category in KEYWORD_CATEGORIES}
    seen = set()

    for category in KEYWORD_CATEGORIES:
        values = data.get(category, [])
        if values is None:
            values = []
        if not isinstance(values, list):
            raise ValueError(f"{category} must be a list")

        for raw_keyword in values:
            if not isinstance(raw_keyword, str):
                raise ValueError(f"{category} contains a non-string keyword")
            keyword = raw_keyword.strip()
            if not keyword:
                continue
            if len(keyword) > MAX_KEYWORD_LENGTH:
                raise ValueError(f"keyword is too long: {keyword[:20]}")
            if keyword in seen:
                continue
            seen.add(keyword)
            normalized[category].append(keyword)

    return normalized


def load_keywords() -> Dict[str, List[str]]:
    default_data = {category: [] for category in KEYWORD_CATEGORIES}

    with KEYWORDS_FILE_LOCK:
        if not os.path.exists(KEYWORDS_FILE):
            return default_data

        try:
            with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _normalize_keywords_payload(data)
        except Exception as exc:
            print(f"[Config] failed to load keywords.json: {exc}")
            return default_data


def _safe_keywords_backup_path(filename: str) -> Path:
    if not KEYWORDS_BACKUP_NAME_RE.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid backup filename")

    backup_dir = Path(KEYWORDS_BACKUP_DIR).resolve()
    backup_path = (backup_dir / filename).resolve()
    try:
        backup_path.relative_to(backup_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid backup filename") from exc
    return backup_path


def save_keywords(data: Dict[str, List[str]], create_backup: bool = True) -> bool:
    with KEYWORDS_FILE_LOCK:
        try:
            with json_file_lock(KEYWORDS_FILE):
                normalized = _normalize_keywords_payload(data)

                if create_backup and os.path.exists(KEYWORDS_FILE):
                    os.makedirs(KEYWORDS_BACKUP_DIR, exist_ok=True)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    backup_path = os.path.join(KEYWORDS_BACKUP_DIR, f"keywords_{timestamp}.json")
                    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
                        backup_data = f.read()
                    with open(backup_path, "w", encoding="utf-8") as f:
                        f.write(backup_data)

                atomic_write_json(KEYWORDS_FILE, normalized, acquire_lock=False)
            return True
        except Exception as exc:
            print(f"[Config] failed to save keywords.json: {exc}")
            return False


def _save_keywords_or_error(data: Dict[str, List[str]]) -> None:
    if not save_keywords(data):
        raise HTTPException(status_code=500, detail="Failed to save keywords")


@router.get("/keywords")
async def get_keywords() -> Dict[str, Any]:
    data = load_keywords()
    return {
        "naver_place": data.get("naver_place", []),
        "blog_seo": data.get("blog_seo", []),
        "total_count": len(data.get("naver_place", [])) + len(data.get("blog_seo", [])),
    }


@router.put("/keywords")
async def update_keywords(keywords_data: KeywordsData) -> Dict[str, Any]:
    data = _normalize_keywords_payload(
        {
            "naver_place": keywords_data.naver_place,
            "blog_seo": keywords_data.blog_seo,
        }
    )

    _save_keywords_or_error(data)
    total_count = len(data["naver_place"]) + len(data["blog_seo"])
    return {
        "success": True,
        "message": f"Keywords saved ({total_count} total)",
        "total_count": total_count,
    }


@router.post("/keywords/add")
async def add_keyword(request: KeywordAddRequest) -> Dict[str, Any]:
    keyword = request.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword is required")

    with KEYWORDS_FILE_LOCK:
        data = load_keywords()
        all_keywords = data.get("naver_place", []) + data.get("blog_seo", [])
        if keyword in all_keywords:
            raise HTTPException(status_code=400, detail=f"'{keyword}' is already registered")

        data[request.category].append(keyword)
        _save_keywords_or_error(data)

    return {
        "success": True,
        "message": f"'{keyword}' added to {request.category}",
        "category": request.category,
        "keyword": keyword,
    }


@router.post("/keywords/delete")
async def delete_keyword(request: KeywordDeleteRequest) -> Dict[str, Any]:
    keyword = request.keyword.strip()

    with KEYWORDS_FILE_LOCK:
        data = load_keywords()
        if keyword not in data.get(request.category, []):
            raise HTTPException(status_code=404, detail=f"'{keyword}' was not found")

        data[request.category].remove(keyword)
        _save_keywords_or_error(data)

    return {
        "success": True,
        "message": f"'{keyword}' deleted",
        "category": request.category,
        "keyword": keyword,
    }


@router.post("/keywords/move")
async def move_keyword(request: KeywordMoveRequest) -> Dict[str, Any]:
    keyword = request.keyword.strip()
    if request.from_category == request.to_category:
        raise HTTPException(status_code=400, detail="Cannot move keyword to the same category")

    with KEYWORDS_FILE_LOCK:
        data = load_keywords()
        if keyword not in data.get(request.from_category, []):
            raise HTTPException(status_code=404, detail=f"'{keyword}' was not found")

        data[request.from_category].remove(keyword)
        if keyword not in data[request.to_category]:
            data[request.to_category].append(keyword)
        _save_keywords_or_error(data)

    return {
        "success": True,
        "message": f"'{keyword}' moved from {request.from_category} to {request.to_category}",
        "keyword": keyword,
        "from_category": request.from_category,
        "to_category": request.to_category,
    }


@router.get("/keywords/backups")
async def get_keywords_backups() -> Dict[str, Any]:
    backups = []

    if os.path.exists(KEYWORDS_BACKUP_DIR):
        for filename in sorted(os.listdir(KEYWORDS_BACKUP_DIR), reverse=True):
            if KEYWORDS_BACKUP_NAME_RE.fullmatch(filename):
                filepath = os.path.join(KEYWORDS_BACKUP_DIR, filename)
                stat = os.stat(filepath)
                backups.append(
                    {
                        "filename": filename,
                        "size_kb": round(stat.st_size / 1024, 1),
                        "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    }
                )

    return {
        "backups": backups[:10],
        "total": len(backups),
    }


@router.post("/keywords/restore/{filename}")
async def restore_keywords_backup(filename: str) -> Dict[str, Any]:
    with KEYWORDS_FILE_LOCK:
        backup_path = _safe_keywords_backup_path(filename)
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup file not found")

        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                backup_data = json.load(f)
            normalized = _normalize_keywords_payload(backup_data)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid backup JSON") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        _save_keywords_or_error(normalized)

    return {
        "success": True,
        "message": f"'{filename}' backup restored",
    }


def load_business_profile() -> Dict[str, Any]:
    default_profile = {
        "business": {
            "name": "",
            "short_name": "",
            "english_name": "",
            "industry": "",
            "region": "",
            "address": "",
        },
        "categories": {
            "main": [],
            "category_keywords": {},
            "category_colors": {},
        },
        "branding": {
            "signatures": {},
        },
    }

    if not os.path.exists(BUSINESS_PROFILE_FILE):
        return default_profile

    try:
        with open(BUSINESS_PROFILE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"[Config] failed to load business_profile.json: {exc}")
        return default_profile


@router.get("/business-profile")
async def get_business_profile() -> Dict[str, Any]:
    return load_business_profile()


@router.get("/categories")
async def get_categories() -> Dict[str, Any]:
    profile = load_business_profile()
    categories_data = profile.get("categories", {})
    return {
        "categories": categories_data.get("main", []),
        "category_keywords": categories_data.get("category_keywords", {}),
        "category_colors": categories_data.get("category_colors", {}),
    }


@router.get("/branding")
async def get_branding() -> Dict[str, Any]:
    profile = load_business_profile()
    business = profile.get("business", {})
    branding = profile.get("branding", {})
    return {
        "business_name": business.get("name", ""),
        "short_name": business.get("short_name", ""),
        "region": business.get("region", ""),
        "tagline": branding.get("tagline", ""),
        "signatures": branding.get("signatures", {}),
    }


@router.get("/view")
async def view_config_file(file: str = "keywords") -> Dict[str, Any]:
    file_map = {
        "keywords": os.path.join(parent_dir, "config", "keywords.json"),
        "config": os.path.join(parent_dir, "config", "config.json"),
        "schedule": os.path.join(parent_dir, "config", "schedule.json"),
    }

    if file not in file_map:
        raise HTTPException(status_code=400, detail=f"Unsupported config file: {file}")

    file_path = file_map[file]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = json.load(f)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse JSON: {exc}") from exc

    if file == "config":
        content = mask_sensitive_data(content)

    file_stat = os.stat(file_path)
    return {
        "file": file,
        "content": content,
        "metadata": {
            "size_bytes": file_stat.st_size,
            "modified": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
            "path": file_path,
        },
    }


def mask_sensitive_data(config: Dict[str, Any]) -> Dict[str, Any]:
    sensitive_keys = [
        "codex_cli_bin",
        "naver_client_id",
        "naver_client_secret",
        "password",
        "secret",
        "token",
        "key",
    ]

    def mask_recursive(obj):
        if isinstance(obj, dict):
            return {
                key: "***MASKED***"
                if any(sensitive_key in key.lower() for sensitive_key in sensitive_keys)
                else mask_recursive(value)
                for key, value in obj.items()
            }
        if isinstance(obj, list):
            return [mask_recursive(item) for item in obj]
        return obj

    return mask_recursive(config.copy())
