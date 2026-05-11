"""Canonical URL keys for Viral Hunter targets."""
from __future__ import annotations

from urllib.parse import parse_qs, quote, unquote, urlparse, urlunparse


def _with_scheme(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if "://" in value:
        return value
    return f"https://{value}"


def _query_first(query: dict[str, list[str]], *names: str) -> str:
    lowered = {key.lower(): values for key, values in query.items()}
    for name in names:
        values = lowered.get(name.lower())
        if values:
            value = str(values[0] or "").strip()
            if value:
                return value
    return ""


def _path_segments(path: str) -> list[str]:
    return [
        unquote(part).strip()
        for part in (path or "").split("/")
        if unquote(part).strip()
    ]


def _safe_segment(value: str) -> str:
    return quote((value or "").strip(), safe="-_.~")


def _normalize_path(path: str) -> str:
    segments = [_safe_segment(part) for part in _path_segments(path)]
    if not segments:
        return "/"
    return "/" + "/".join(segments)


def _canonical_kin(host: str, path: str, query: dict[str, list[str]]) -> str:
    doc_id = _query_first(query, "docId", "docid")
    if not doc_id:
        return ""
    return f"https://kin.naver.com/qna/detail.naver?docId={_safe_segment(doc_id)}"


def _canonical_blog(host: str, path: str, query: dict[str, list[str]]) -> str:
    blog_id = _query_first(query, "blogId", "blogid")
    log_no = _query_first(query, "logNo", "logno")

    if not (blog_id and log_no):
        segments = _path_segments(path)
        if len(segments) >= 2 and not segments[0].lower().endswith(".naver"):
            blog_id, log_no = segments[0], segments[1]

    if blog_id and log_no:
        return (
            "https://blog.naver.com/"
            f"{_safe_segment(blog_id.lower())}/{_safe_segment(log_no)}"
        )
    return ""


def _canonical_cafe(host: str, path: str, query: dict[str, list[str]]) -> str:
    article_id = _query_first(query, "articleId", "articleid")
    club_id = _query_first(query, "clubId", "clubid", "clubUrl", "cluburl")
    if club_id and article_id:
        return (
            "https://cafe.naver.com/"
            f"{_safe_segment(club_id.lower())}/{_safe_segment(article_id)}"
        )

    segments = _path_segments(path)
    lowered = [segment.lower() for segment in segments]
    if "cafes" in lowered and "articles" in lowered:
        cafe_idx = lowered.index("cafes")
        article_idx = lowered.index("articles")
        if cafe_idx + 1 < len(segments) and article_idx + 1 < len(segments):
            return (
                "https://cafe.naver.com/ca-fe/web/cafes/"
                f"{_safe_segment(segments[cafe_idx + 1].lower())}/articles/"
                f"{_safe_segment(segments[article_idx + 1])}"
            )

    if len(segments) >= 2 and not segments[0].lower().endswith(".nhn"):
        return (
            "https://cafe.naver.com/"
            f"{_safe_segment(segments[0].lower())}/{_safe_segment(segments[1])}"
        )
    return ""


def canonicalize_viral_url(url: str) -> str:
    """Return the duplicate-comparison URL for Naver Viral Hunter targets.

    - kin.naver.com is keyed by docId.
    - blog.naver.com and cafe.naver.com are keyed by stable post paths.
    - Other URLs keep path and query, but drop fragments and normalize host/path.
    """
    raw = _with_scheme(url)
    if not raw:
        return ""

    try:
        parsed = urlparse(raw)
    except Exception:
        return (url or "").strip()

    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    query = parse_qs(parsed.query, keep_blank_values=False)

    if host.endswith("kin.naver.com"):
        canonical = _canonical_kin(host, parsed.path, query)
        if canonical:
            return canonical

    if host.endswith("blog.naver.com"):
        canonical = _canonical_blog(host, parsed.path, query)
        if canonical:
            return canonical

    if host.endswith("cafe.naver.com"):
        canonical = _canonical_cafe(host, parsed.path, query)
        if canonical:
            return canonical

    scheme = (parsed.scheme or "https").lower()
    path = _normalize_path(parsed.path)
    return urlunparse((scheme, host, path, "", parsed.query, ""))
