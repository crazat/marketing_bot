"""Pathfinder insight broker.

Turns keyword_insights rows into user-facing briefs and agent handoff packets.
The broker is intentionally deterministic so it can be used before or inside
Codex/LLM prompts without making another model call.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


AGENT_ALIASES = {
    "blog": "blog_agent",
    "blog_agent": "blog_agent",
    "content": "blog_agent",
    "content_agent": "blog_agent",
    "shorts": "shorts_studio_agent",
    "shorts_studio": "shorts_studio_agent",
    "shorts_studio_agent": "shorts_studio_agent",
    "reels": "shorts_studio_agent",
    "viral": "viral_hunter_agent",
    "viral_hunter": "viral_hunter_agent",
    "viral_hunter_agent": "viral_hunter_agent",
    "ads": "ad_agent",
    "ad": "ad_agent",
    "ad_agent": "ad_agent",
}


def _json_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item is not None]
        except json.JSONDecodeError:
            return [value] if value else []
    return []


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


class PathfinderInsightBroker:
    """Builds cross-agent insight contracts from Pathfinder output."""

    VERSION = "pathfinder.insight.v1"

    TEXT_DEFAULTS: Dict[str, str] = {
        "keyword": "",
        "competition": "",
        "grade": "C",
        "category": "기타",
        "source": "",
        "trend_status": "unknown",
        "search_intent": "unknown",
        "content_cluster_key": "",
        "rank_status": "unknown",
        "availability_intent_type": "none",
        "payment_coverage_type": "none",
        "access_convenience_type": "none",
        "recommended_content_type": "",
        "preferred_search_surface": "",
        "brand_intent_type": "generic",
        "review_intent_type": "none",
        "quality_flags_json": "[]",
        "source_signals_json": "[]",
        "created_at": "",
        "updated_at": "",
    }

    NUMERIC_DEFAULTS: Dict[str, float] = {
        "search_volume": 0,
        "difficulty": 50,
        "opportunity": 50,
        "priority_v3": 0,
        "opp_score": 0,
        "document_count": 0,
        "kei": 0,
        "business_core": 0,
        "longtail_score": 0,
        "business_value_score": 0,
        "high_value_longtail": 0,
        "mobile_share": 0,
        "rank_gap_signal": 0,
        "community_signal": 0,
        "conversion_signal": 0,
        "profile_action_signal": 0,
        "availability_intent_score": 0,
        "payment_coverage_score": 0,
        "access_convenience_score": 0,
        "medical_ad_risk_score": 0,
        "content_actionability_score": 0,
        "local_service_fit_score": 0,
        "local_surface_score": 0,
        "brand_signal_score": 0,
        "competitor_brand_risk_score": 0,
        "review_surface_score": 0,
        "reputation_risk_score": 0,
        "verification_score": 0,
        "novelty_score": 0,
        "last_scan_run_id": 0,
    }

    def __init__(self, db_path: str):
        self.db_path = str(db_path)

    def build_user_brief(
        self,
        *,
        limit: int = 12,
        business_core_only: bool = True,
        latest_verified_only: bool = True,
        use_codex: bool = False,
    ) -> Dict[str, Any]:
        cards = self.keyword_cards(
            limit=limit,
            business_core_only=business_core_only,
            latest_verified_only=latest_verified_only,
        )
        metrics = self._brief_metrics(cards)
        action_queue = self._build_action_queue(cards)
        summary = self._build_summary(cards, metrics)
        top_insights = self._build_top_insights(cards, metrics)
        codex_synthesis = self._codex_synthesis(
            cards=cards,
            metrics=metrics,
            action_queue=action_queue,
            requested=use_codex,
        )
        provenance = self._build_provenance(
            cards,
            latest_verified_only=latest_verified_only,
            business_core_only=business_core_only,
        )
        quality_gate = self._quality_gate(cards, metrics)
        feedback_summary = self._feedback_summary(cards)
        decision_overview = self._decision_overview(cards)

        return {
            "version": self.VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": "pathfinder",
            "audience": "user",
            "summary": summary,
            "top_insights": top_insights,
            "codex_synthesis": codex_synthesis,
            "provenance": provenance,
            "quality_gate": quality_gate,
            "feedback_summary": feedback_summary,
            "decision_overview": decision_overview,
            "delivery_contract": self._delivery_contract(),
            "feedback_contract": self._feedback_contract(),
            "action_queue": action_queue,
            "keyword_cards": cards,
            "agent_handoffs": self.build_agent_handoffs(cards=cards),
            "codex_prompt_context": self.format_prompt_context(cards=cards, agent="all"),
            "metrics": metrics,
        }

    def build_agent_handoffs(
        self,
        *,
        cards: Optional[List[Dict[str, Any]]] = None,
        agent: str = "all",
        limit: int = 8,
        business_core_only: bool = True,
        latest_verified_only: bool = True,
    ) -> Dict[str, Any]:
        if cards is None:
            cards = self.keyword_cards(
                limit=limit,
                business_core_only=business_core_only,
                latest_verified_only=latest_verified_only,
            )
        selected = cards[:limit]
        requested = AGENT_ALIASES.get(agent, agent)
        packets = {
            "blog_agent": self._blog_packet(selected),
            "shorts_studio_agent": self._shorts_packet(selected),
            "viral_hunter_agent": self._viral_packet(selected),
            "ad_agent": self._ad_packet(selected),
        }
        if requested != "all":
            packets = {requested: packets.get(requested, {"tasks": [], "prompt_context": ""})}
        return {
            "version": self.VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": "pathfinder",
            "agent": requested,
            "feedback_summary": self._feedback_summary(selected),
            "decision_overview": self._decision_overview(selected),
            "packets": packets,
        }

    def export_user_brief(self, output_path: str, **kwargs: Any) -> Dict[str, Any]:
        brief = self.build_user_brief(**kwargs)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
        return brief

    def keyword_cards(
        self,
        *,
        limit: int = 12,
        business_core_only: bool = True,
        latest_verified_only: bool = True,
    ) -> List[Dict[str, Any]]:
        rows = self._fetch_keywords(
            limit=max(1, min(int(limit), 100)),
            business_core_only=business_core_only,
            latest_verified_only=latest_verified_only,
        )
        cards = [self._row_to_card(row) for row in rows]
        cards.sort(key=lambda item: item["insight_score"], reverse=True)
        selected = cards[:limit]
        self._attach_feedback_snapshots(selected)
        return selected

    def format_prompt_context(
        self,
        *,
        cards: Optional[Sequence[Dict[str, Any]]] = None,
        agent: str = "all",
        topic: Optional[str] = None,
        limit: int = 5,
    ) -> str:
        if cards is None:
            cards = self.keyword_cards(limit=limit)
        selected = list(cards)[:limit]
        lines = [
            "[Pathfinder Insight Handoff]",
            f"- Agent: {agent}",
            f"- Topic filter: {topic or 'none'}",
            "- Use these as evidence-backed campaign inputs, not as generic keyword stuffing.",
        ]
        for idx, card in enumerate(selected, 1):
            metrics = card["metrics"]
            lines.append(
                f"{idx}. {card['keyword']} | id={card.get('handoff_id', '')} | grade={card['grade']} | "
                f"confidence={card.get('confidence_band', 'unknown')}:{card.get('confidence', 0)} | "
                f"business={metrics['business_value_score']:.0f} | volume={metrics['search_volume']} | "
                f"intent={card['search_intent']} | reasons={', '.join(card['why_it_matters'][:4])}"
            )
            evidence = [
                f"{item.get('signal')}={item.get('value')}"
                for item in card.get("evidence_trace", [])[:4]
            ]
            if evidence:
                lines.append(f"   - Evidence: {', '.join(evidence)}")
            decision = card.get("decision_packet") or {}
            if decision:
                lines.append(
                    f"   - Decision: {decision.get('state')} | policy={decision.get('publish_policy')} | "
                    f"reasons={', '.join(decision.get('reason_codes') or [])}"
                )
            data_quality = card.get("data_quality") or {}
            if data_quality:
                lines.append(
                    f"   - Data quality: {data_quality.get('status')}:{data_quality.get('score')} | "
                    f"warnings={', '.join(data_quality.get('warnings') or [])}"
                )
            measurement = card.get("measurement_plan") or {}
            if measurement:
                lines.append(f"   - Measure: {measurement.get('primary_metric')}")
            if card.get("human_review", {}).get("required"):
                lines.append(
                    "   - Human review: "
                    + ", ".join(card.get("human_review", {}).get("reasons", []))
                )
            feedback = card.get("feedback_snapshot") or {}
            if feedback.get("total_events"):
                lines.append(
                    f"   - Feedback: {feedback.get('learning_status')} "
                    f"{json.dumps(feedback.get('counts') or {}, ensure_ascii=False)}"
                )
            if card["agent_notes"].get(agent):
                lines.append(f"   - Agent note: {card['agent_notes'][agent]}")
            elif agent == "all":
                lines.append(f"   - Blog: {card['agent_notes']['blog_agent']}")
                lines.append(f"   - Shorts: {card['agent_notes']['shorts_studio_agent']}")
            if card["risks"]:
                lines.append(f"   - Guardrails: {', '.join(card['risks'])}")
        return "\n".join(lines)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _table_exists(self, cursor: sqlite3.Cursor, table: str) -> bool:
        row = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    def _columns(self, cursor: sqlite3.Cursor, table: str = "keyword_insights") -> set[str]:
        return {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}

    def _latest_completed_run_id(self, cursor: sqlite3.Cursor) -> Optional[int]:
        if not self._table_exists(cursor, "scan_runs"):
            return None
        try:
            row = cursor.execute(
                """
                SELECT id
                FROM scan_runs
                WHERE status = 'completed'
                  AND scan_type = 'legion'
                ORDER BY completed_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return int(row[0]) if row else None

    def _select_expr(self, column: str, columns: set[str], alias: str = "ki") -> str:
        default = self.TEXT_DEFAULTS.get(column, self.NUMERIC_DEFAULTS.get(column, 0))
        if column in columns:
            return f"COALESCE({alias}.{column}, {_literal(default)}) AS {column}"
        return f"{_literal(default)} AS {column}"

    def _fetch_keywords(
        self,
        *,
        limit: int,
        business_core_only: bool,
        latest_verified_only: bool,
    ) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            if not self._table_exists(cursor, "keyword_insights"):
                return []
            columns = self._columns(cursor)
            text_cols = list(self.TEXT_DEFAULTS)
            numeric_cols = list(self.NUMERIC_DEFAULTS)
            select_cols = [self._select_expr(col, columns) for col in text_cols + numeric_cols]
            filters = ["1=1"]
            params: List[Any] = []

            if "status" in columns:
                filters.append("COALESCE(ki.status, 'active') != 'archived'")
            if "document_count" in columns:
                filters.append("COALESCE(ki.document_count, 0) > 0")
            if business_core_only and "business_core" in columns:
                filters.append("COALESCE(ki.business_core, 0) = 1")
            if latest_verified_only and "last_scan_run_id" in columns:
                latest_run_id = self._latest_completed_run_id(cursor)
                if latest_run_id:
                    filters.append("ki.last_scan_run_id = ?")
                    params.append(latest_run_id)

            order_terms = []
            for column, direction in (
                ("high_value_longtail", "DESC"),
                ("business_value_score", "DESC"),
                ("priority_v3", "DESC"),
                ("opportunity", "DESC"),
                ("search_volume", "DESC"),
            ):
                if column in columns:
                    order_terms.append(f"COALESCE(ki.{column}, 0) {direction}")
            order_clause = ", ".join(order_terms) or "ki.keyword ASC"

            params.append(limit)
            cursor.execute(
                f"""
                SELECT {", ".join(select_cols)}
                FROM keyword_insights ki
                WHERE {" AND ".join(filters)}
                ORDER BY {order_clause}
                LIMIT ?
                """,
                params,
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def _row_to_card(self, row: Dict[str, Any]) -> Dict[str, Any]:
        quality_flags = _json_list(row.get("quality_flags_json"))
        source_signals = _json_list(row.get("source_signals_json"))
        reasons = self._why_it_matters(row, quality_flags, source_signals)
        risks = self._risks(row, quality_flags)
        evidence_trace = self._evidence_trace(row, quality_flags, source_signals)
        confidence = self._confidence(row, evidence_trace, risks, source_signals)
        human_review = self._human_review(row, risks, confidence, evidence_trace)
        data_quality = self._data_quality_snapshot(row, evidence_trace, quality_flags, source_signals)
        decision_packet = self._decision_packet(row, confidence, human_review, data_quality, risks)
        measurement_plan = self._measurement_plan(row, decision_packet)
        handoff_id = self._handoff_id(row, evidence_trace)
        agent_notes = self._agent_notes(row, reasons, risks)
        actions = self._keyword_actions(row, reasons, risks)
        metrics = {
            key: _as_float(row.get(key))
            for key in self.NUMERIC_DEFAULTS
            if key not in {"business_core", "high_value_longtail"}
        }
        metrics["search_volume"] = _as_int(row.get("search_volume"))
        metrics["document_count"] = _as_int(row.get("document_count"))

        score = self._insight_score(row, reasons, risks)
        return {
            "handoff_id": handoff_id,
            "keyword": row.get("keyword", ""),
            "category": row.get("category") or "기타",
            "grade": row.get("grade") or "C",
            "search_intent": row.get("search_intent") or "unknown",
            "trend_status": row.get("trend_status") or "unknown",
            "content_cluster_key": row.get("content_cluster_key") or "",
            "insight_score": round(score, 2),
            "confidence": confidence,
            "confidence_band": self._confidence_band(confidence),
            "why_it_matters": reasons,
            "risks": risks,
            "evidence_trace": evidence_trace,
            "human_review": human_review,
            "data_quality": data_quality,
            "decision_packet": decision_packet,
            "measurement_plan": measurement_plan,
            "quality_flags": quality_flags,
            "source_signals": source_signals,
            "provenance": {
                "source_table": "keyword_insights",
                "source": row.get("source") or "pathfinder",
                "last_scan_run_id": _as_int(row.get("last_scan_run_id")),
                "created_at": row.get("created_at") or "",
                "updated_at": row.get("updated_at") or "",
            },
            "metrics": metrics,
            "signals": {
                "high_value_longtail": bool(_as_int(row.get("high_value_longtail"))),
                "preferred_search_surface": row.get("preferred_search_surface") or "",
                "recommended_content_type": row.get("recommended_content_type") or "",
                "availability_intent_type": row.get("availability_intent_type") or "none",
                "payment_coverage_type": row.get("payment_coverage_type") or "none",
                "access_convenience_type": row.get("access_convenience_type") or "none",
                "review_intent_type": row.get("review_intent_type") or "none",
                "brand_intent_type": row.get("brand_intent_type") or "generic",
            },
            "agent_notes": agent_notes,
            "recommended_actions": actions,
        }

    def _confidence_band(self, confidence: float) -> str:
        if confidence >= 0.78:
            return "high"
        if confidence >= 0.58:
            return "medium"
        return "low"

    def _evidence_trace(
        self,
        row: Dict[str, Any],
        quality_flags: Sequence[str],
        source_signals: Sequence[str],
    ) -> List[Dict[str, Any]]:
        evidence: List[Dict[str, Any]] = []

        def add_score(signal: str, threshold: float, meaning: str, source: str = "keyword_insights") -> None:
            value = _as_float(row.get(signal))
            if value >= threshold:
                evidence.append({
                    "signal": signal,
                    "value": round(value, 2),
                    "threshold": threshold,
                    "source": source,
                    "meaning": meaning,
                })

        if _as_int(row.get("high_value_longtail")):
            evidence.append({
                "signal": "high_value_longtail",
                "value": True,
                "threshold": True,
                "source": "keyword_insights",
                "meaning": "business value and long-tail specificity passed the Legion gate",
            })
        add_score("business_value_score", 70, "commercial or conversion value is strong")
        add_score("longtail_score", 70, "query is specific enough to carry long-tail intent")
        add_score("local_surface_score", 70, "local/place exposure is a meaningful surface")
        add_score("profile_action_signal", 60, "profile action or visit signal is present")
        add_score("availability_intent_score", 70, "reservation or availability intent is explicit")
        add_score("payment_coverage_score", 70, "cost, insurance, or document intent is explicit")
        add_score("access_convenience_score", 70, "parking, route, or access convenience intent is explicit")
        add_score("review_surface_score", 70, "review or reputation comparison intent is explicit")
        add_score("community_signal", 40, "community demand signal is present")
        add_score("conversion_signal", 35, "conversion-like behavior signal is present")
        add_score("verification_score", 65, "external verification score is strong")
        add_score("novelty_score", 65, "keyword is meaningfully differentiated from common terms")

        mobile_share = _as_float(row.get("mobile_share"))
        if mobile_share >= 0.65:
            evidence.append({
                "signal": "mobile_share",
                "value": round(mobile_share, 3),
                "threshold": 0.65,
                "source": "keyword_insights",
                "meaning": "mobile-heavy search behavior supports short-form or local content",
            })
        if row.get("trend_status") == "rising":
            evidence.append({
                "signal": "trend_status",
                "value": "rising",
                "threshold": "rising",
                "source": "keyword_insights",
                "meaning": "trend movement supports near-term execution",
            })
        for signal in source_signals[:6]:
            evidence.append({
                "signal": "source_signal",
                "value": signal,
                "threshold": "observed",
                "source": "source_signals_json",
                "meaning": "the keyword was observed by an upstream research source",
            })
        for flag in quality_flags[:4]:
            evidence.append({
                "signal": "quality_flag",
                "value": flag,
                "threshold": "review",
                "source": "quality_flags_json",
                "meaning": "quality flag must be considered before execution",
            })
        return evidence[:18]

    def _confidence(
        self,
        row: Dict[str, Any],
        evidence_trace: Sequence[Dict[str, Any]],
        risks: Sequence[str],
        source_signals: Sequence[str],
    ) -> float:
        positive_evidence_count = sum(1 for item in evidence_trace if item.get("signal") != "quality_flag")
        source_diversity = len(set(source_signals))
        score = 0.42
        score += min(0.30, positive_evidence_count * 0.035)
        score += min(0.12, source_diversity * 0.035)
        score += min(0.08, _as_float(row.get("verification_score")) / 1000.0)
        score += min(0.05, _as_int(row.get("document_count")) / 10000.0)
        if _as_int(row.get("high_value_longtail")):
            score += 0.05
        if row.get("trend_status") == "rising":
            score += 0.03
        score -= min(0.14, len(risks) * 0.035)
        score -= min(0.10, _as_float(row.get("medical_ad_risk_score")) / 1000.0)
        score -= min(0.08, _as_float(row.get("competitor_brand_risk_score")) / 1100.0)
        return round(max(0.05, min(0.95, score)), 2)

    def _human_review(
        self,
        row: Dict[str, Any],
        risks: Sequence[str],
        confidence: float,
        evidence_trace: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        if confidence < 0.58:
            reasons.append("low_confidence")
        if len(evidence_trace) < 2:
            reasons.append("thin_evidence")
        if risks:
            reasons.append("guardrail_risk")
        if _as_float(row.get("medical_ad_risk_score")) >= 50:
            reasons.append("medical_ad_review")
        if _as_float(row.get("competitor_brand_risk_score")) >= 50:
            reasons.append("competitor_brand_review")
        if _as_float(row.get("reputation_risk_score")) >= 50:
            reasons.append("reputation_review")
        reasons = list(dict.fromkeys(reasons))
        return {
            "required": bool(reasons),
            "reasons": reasons,
            "recommended_owner": "operator" if reasons else "agent",
        }

    def _handoff_id(self, row: Dict[str, Any], evidence_trace: Sequence[Dict[str, Any]]) -> str:
        payload = {
            "keyword": row.get("keyword", ""),
            "category": row.get("category", ""),
            "grade": row.get("grade", ""),
            "last_scan_run_id": _as_int(row.get("last_scan_run_id")),
            "evidence": [
                {
                    "signal": item.get("signal"),
                    "value": item.get("value"),
                }
                for item in evidence_trace[:8]
            ],
        }
        digest = hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return f"pf-{digest[:12]}"

    def _data_quality_snapshot(
        self,
        row: Dict[str, Any],
        evidence_trace: Sequence[Dict[str, Any]],
        quality_flags: Sequence[str],
        source_signals: Sequence[str],
    ) -> Dict[str, Any]:
        required_values = {
            "keyword": bool(row.get("keyword")),
            "grade": bool(row.get("grade")),
            "category": bool(row.get("category")),
            "search_volume": _as_int(row.get("search_volume")) > 0,
            "document_count": _as_int(row.get("document_count")) > 0,
            "business_value_score": _as_float(row.get("business_value_score")) > 0,
            "longtail_score": _as_float(row.get("longtail_score")) > 0,
            "evidence_trace": bool(evidence_trace),
        }
        completeness = sum(1 for present in required_values.values() if present) / len(required_values)
        source_diversity = len(set(source_signals))
        has_recent_scan = _as_int(row.get("last_scan_run_id")) > 0
        warnings: List[str] = []
        if completeness < 0.75:
            warnings.append("missing_core_fields")
        if source_diversity < 2:
            warnings.append("single_or_missing_source_signal")
        if not has_recent_scan:
            warnings.append("scan_run_not_linked")
        if quality_flags:
            warnings.append("quality_flags_present")

        score = completeness * 0.55
        score += min(0.20, source_diversity * 0.07)
        score += 0.15 if has_recent_scan else 0.0
        score += min(0.10, len(evidence_trace) * 0.015)
        if quality_flags:
            score -= min(0.15, len(quality_flags) * 0.035)
        score = round(max(0.0, min(1.0, score)), 2)
        if score >= 0.78 and not warnings:
            status = "fit_for_action"
        elif score >= 0.58:
            status = "fit_with_caveats"
        else:
            status = "thin"
        return {
            "status": status,
            "score": score,
            "dimensions": {
                "completeness": round(completeness, 2),
                "source_diversity": source_diversity,
                "scan_run_linked": has_recent_scan,
                "evidence_items": len(evidence_trace),
                "quality_flag_count": len(quality_flags),
            },
            "warnings": warnings,
            "required_fields_present": required_values,
        }

    def _decision_packet(
        self,
        row: Dict[str, Any],
        confidence: float,
        human_review: Dict[str, Any],
        data_quality: Dict[str, Any],
        risks: Sequence[str],
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        if confidence < 0.58:
            reasons.append("low_confidence")
        elif confidence < 0.78:
            reasons.append("medium_confidence")
        if human_review.get("required"):
            reasons.extend(human_review.get("reasons") or ["human_review_required"])
        if data_quality.get("status") == "thin":
            reasons.append("thin_data_quality")
        elif data_quality.get("warnings"):
            reasons.append("data_quality_caveat")
        if risks:
            reasons.append("guardrail_risk")

        if "low_confidence" in reasons or "thin_data_quality" in reasons:
            state = "hold"
        elif human_review.get("required") or risks or confidence < 0.78 or data_quality.get("warnings"):
            state = "review"
        else:
            state = "go"
        publish_policy = {
            "go": "agent_can_draft_and_operator_can_publish",
            "review": "agent_can_draft_operator_must_review",
            "hold": "operator_review_only",
        }[state]
        return {
            "state": state,
            "owner": "agent" if state == "go" else "operator",
            "publish_policy": publish_policy,
            "reason_codes": list(dict.fromkeys(reasons)),
            "primary_decision": self._primary_decision(row),
        }

    def _primary_decision(self, row: Dict[str, Any]) -> str:
        if _as_float(row.get("access_convenience_score")) >= 70:
            return "publish access-convenience content only if route/parking details are verified"
        if _as_float(row.get("payment_coverage_score")) >= 70:
            return "publish FAQ content only if cost, insurance, and document claims are verified"
        if _as_float(row.get("availability_intent_score")) >= 70:
            return "publish reservation-focused content only if availability wording is current"
        if _as_float(row.get("review_surface_score")) >= 70:
            return "publish selection-criteria content without review manipulation"
        return "draft intent-matched content with evidence and guardrails preserved"

    def _measurement_plan(self, row: Dict[str, Any], decision_packet: Dict[str, Any]) -> Dict[str, Any]:
        keyword = row.get("keyword", "")
        if _as_float(row.get("access_convenience_score")) >= 70:
            primary_metric = "visit-inquiry or profile-action feedback for access convenience content"
        elif _as_float(row.get("payment_coverage_score")) >= 70:
            primary_metric = "consultation inquiry after cost/insurance FAQ engagement"
        elif _as_float(row.get("availability_intent_score")) >= 70:
            primary_metric = "reservation or availability-check inquiry"
        elif _as_float(row.get("review_surface_score")) >= 70:
            primary_metric = "inquiry after selection-criteria or reputation-safety content"
        else:
            primary_metric = "accepted or completed Pathfinder handoff feedback"
        review_after_days = 14 if row.get("trend_status") == "rising" else 30
        return {
            "hypothesis": f"{keyword} will create higher-quality intent-matched demand than a generic head keyword.",
            "primary_metric": primary_metric,
            "secondary_metrics": [
                "accepted/completed feedback on the handoff_id",
                "needs_review/rejected/failed feedback ratio",
                "rank or visibility movement for the keyword cluster",
                "agent output preserves evidence_trace and guardrails",
            ],
            "review_after_days": review_after_days,
            "success_threshold": "at least one accepted/completed signal and no unresolved guardrail feedback",
            "stop_condition": "hold or rewrite if rejected/failed feedback appears or human_review remains unresolved",
            "decision_state_at_creation": decision_packet.get("state"),
        }

    def _empty_feedback_snapshot(self) -> Dict[str, Any]:
        return {
            "total_events": 0,
            "counts": {},
            "latest_feedback_type": None,
            "latest_agent": None,
            "latest_note": None,
            "last_seen_at": None,
            "learning_status": "unseen",
        }

    def _attach_feedback_snapshots(self, cards: Sequence[Dict[str, Any]]) -> None:
        if not cards:
            return
        rows = self._feedback_rows([card.get("handoff_id", "") for card in cards])
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row.get("handoff_id")), []).append(row)

        for card in cards:
            events = grouped.get(str(card.get("handoff_id")), [])
            if not events:
                card["feedback_snapshot"] = self._empty_feedback_snapshot()
                continue

            counts = Counter(str(event.get("feedback_type") or "unknown") for event in events)
            latest = events[0]
            card["feedback_snapshot"] = {
                "total_events": len(events),
                "counts": dict(counts),
                "latest_feedback_type": latest.get("feedback_type"),
                "latest_agent": latest.get("agent"),
                "latest_note": latest.get("note"),
                "last_seen_at": latest.get("created_at"),
                "learning_status": self._feedback_learning_status(counts),
            }
            if any(counts.get(key, 0) for key in ("needs_review", "rejected", "failed")):
                review = dict(card.get("human_review") or {})
                reasons = list(review.get("reasons") or [])
                for reason in ("feedback_review",):
                    if reason not in reasons:
                        reasons.append(reason)
                review.update({
                    "required": True,
                    "reasons": reasons,
                    "recommended_owner": "operator",
                })
                card["human_review"] = review
                self._apply_feedback_to_decision(card, counts)

    def _apply_feedback_to_decision(self, card: Dict[str, Any], counts: Counter) -> None:
        packet = dict(card.get("decision_packet") or {})
        reasons = list(packet.get("reason_codes") or [])
        if counts.get("rejected", 0) or counts.get("failed", 0):
            packet["state"] = "hold"
            packet["owner"] = "operator"
            packet["publish_policy"] = "operator_review_only"
            reasons.append("negative_feedback")
        elif counts.get("needs_review", 0):
            packet["state"] = "review"
            packet["owner"] = "operator"
            packet["publish_policy"] = "agent_can_draft_operator_must_review"
            reasons.append("feedback_review")
        packet["reason_codes"] = list(dict.fromkeys(reasons))
        card["decision_packet"] = packet
        plan = dict(card.get("measurement_plan") or {})
        plan["decision_state_after_feedback"] = packet.get("state")
        card["measurement_plan"] = plan

    def _feedback_rows(self, handoff_ids: Sequence[str]) -> List[Dict[str, Any]]:
        ids = [handoff_id for handoff_id in handoff_ids if handoff_id]
        if not ids:
            return []
        conn = self._connect()
        try:
            cursor = conn.cursor()
            if not self._table_exists(cursor, "pathfinder_insight_feedback"):
                return []
            placeholders = ", ".join("?" for _ in ids)
            cursor.execute(
                f"""
                SELECT handoff_id, keyword, agent, feedback_type, note, metadata_json, created_at
                FROM pathfinder_insight_feedback
                WHERE handoff_id IN ({placeholders})
                ORDER BY created_at DESC, id DESC
                LIMIT 500
                """,
                ids,
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def _feedback_learning_status(self, counts: Counter) -> str:
        if not counts:
            return "unseen"
        negative = counts.get("rejected", 0) + counts.get("failed", 0)
        review = counts.get("needs_review", 0)
        positive = counts.get("accepted", 0) + counts.get("completed", 0) + counts.get("sent_to_agent", 0)
        if negative:
            return "intervention"
        if review:
            return "review"
        if positive:
            return "validated"
        return "observed"

    def _feedback_summary(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        total_events = 0
        counts: Counter = Counter()
        per_handoff: Dict[str, Dict[str, Any]] = {}
        for card in cards:
            snapshot = card.get("feedback_snapshot") or self._empty_feedback_snapshot()
            handoff_id = card.get("handoff_id")
            total_events += int(snapshot.get("total_events") or 0)
            counts.update(snapshot.get("counts") or {})
            if handoff_id:
                per_handoff[handoff_id] = {
                    "keyword": card.get("keyword"),
                    "learning_status": snapshot.get("learning_status"),
                    "counts": snapshot.get("counts") or {},
                    "last_seen_at": snapshot.get("last_seen_at"),
                }

        positive = counts.get("accepted", 0) + counts.get("completed", 0) + counts.get("sent_to_agent", 0)
        negative = counts.get("rejected", 0) + counts.get("failed", 0)
        actionable_rate = round(positive / total_events, 2) if total_events else None
        failure_rate = round(negative / total_events, 2) if total_events else None
        adjustments: List[str] = []
        if not total_events:
            adjustments.append("collect operator and agent feedback before treating insight quality as proven")
        if counts.get("needs_review", 0):
            adjustments.append("route needs_review handoffs to operator review before downstream publishing")
        if negative:
            adjustments.append("inspect rejected or failed handoffs and adjust scoring thresholds or guardrails")
        if counts.get("completed", 0):
            adjustments.append("promote completed handoffs as validated examples for future agent prompts")

        return {
            "total_events": total_events,
            "counts": dict(counts),
            "actionable_rate": actionable_rate,
            "failure_rate": failure_rate,
            "learning_status": self._feedback_learning_status(counts),
            "per_handoff": per_handoff,
            "recommended_adjustments": adjustments,
            "evaluation_contract": {
                "monitors": [
                    "accepted versus rejected handoffs",
                    "needs_review ratio",
                    "agent completion and failure outcomes",
                    "feedback attached to the same handoff_id as downstream drafts",
                ],
                "next_step": "use feedback_summary together with quality_gate before scaling automated execution",
            },
        }

    def _decision_overview(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        counts = Counter(
            (card.get("decision_packet") or {}).get("state", "unknown")
            for card in cards
        )
        go_cards = [
            {
                "handoff_id": card.get("handoff_id"),
                "keyword": card.get("keyword"),
                "primary_metric": (card.get("measurement_plan") or {}).get("primary_metric"),
            }
            for card in cards
            if (card.get("decision_packet") or {}).get("state") == "go"
        ]
        review_cards = [
            {
                "handoff_id": card.get("handoff_id"),
                "keyword": card.get("keyword"),
                "reasons": (card.get("decision_packet") or {}).get("reason_codes", []),
            }
            for card in cards
            if (card.get("decision_packet") or {}).get("state") in {"review", "hold"}
        ]
        return {
            "counts": dict(counts),
            "publishable_count": counts.get("go", 0),
            "operator_review_count": counts.get("review", 0) + counts.get("hold", 0),
            "go_cards": go_cards[:8],
            "review_cards": review_cards[:8],
            "measurement_contract": {
                "unit": "handoff_id",
                "must_track": [
                    "decision_packet.state",
                    "measurement_plan.primary_metric",
                    "feedback_snapshot.learning_status",
                    "human_review.required",
                    "data_quality.status",
                ],
                "cadence": "review after each content/ad execution and again at measurement_plan.review_after_days",
            },
        }

    def _why_it_matters(
        self,
        row: Dict[str, Any],
        quality_flags: Sequence[str],
        source_signals: Sequence[str],
    ) -> List[str]:
        reasons: List[str] = []
        if _as_int(row.get("high_value_longtail")):
            reasons.append("고가치 롱테일로 판정됨")
        if _as_float(row.get("business_value_score")) >= 70:
            reasons.append("사업 가치 점수가 높음")
        if _as_float(row.get("longtail_score")) >= 70:
            reasons.append("구체적인 의사결정형 검색어")
        if _as_float(row.get("local_surface_score")) >= 70:
            reasons.append("로컬/플레이스 노출 가치가 큼")
        if _as_float(row.get("profile_action_signal")) >= 60:
            reasons.append("프로필 액션 전환 신호가 있음")
        if _as_float(row.get("review_surface_score")) >= 70:
            reasons.append("리뷰/평판 탐색 의도가 강함")
        if _as_float(row.get("availability_intent_score")) >= 70:
            reasons.append("예약/진료 가능 여부 확인 의도")
        if _as_float(row.get("payment_coverage_score")) >= 70:
            reasons.append("비용/보험/서류 확인 의도")
        if _as_float(row.get("access_convenience_score")) >= 70:
            reasons.append("주차/길찾기/접근성 같은 방문 편의 의도")
        if _as_float(row.get("community_signal")) >= 40:
            reasons.append("커뮤니티 수요 신호가 있음")
        if _as_float(row.get("conversion_signal")) >= 35:
            reasons.append("전화 전환 신호가 있음")
        if _as_float(row.get("mobile_share")) >= 0.65:
            reasons.append("모바일 로컬 검색 비중이 높음")
        if row.get("trend_status") == "rising":
            reasons.append("상승 추세")
        if len(source_signals) >= 2:
            reasons.append("다중 소스 검증")
        if not reasons and quality_flags:
            reasons.append("품질 플래그 기반 검토 필요")
        if not reasons:
            reasons.append("기본 Pathfinder 점수 기준 후보")
        return reasons[:8]

    def _risks(self, row: Dict[str, Any], quality_flags: Sequence[str]) -> List[str]:
        risks: List[str] = []
        if _as_float(row.get("medical_ad_risk_score")) >= 70:
            risks.append("의료광고 고위험 표현 금지")
        if _as_float(row.get("competitor_brand_risk_score")) >= 70:
            risks.append("경쟁사 브랜드 직접 비교 주의")
        if _as_float(row.get("reputation_risk_score")) >= 70:
            risks.append("평판 리스크 대응 문구 검토")
        if _as_float(row.get("content_actionability_score")) and _as_float(row.get("content_actionability_score")) < 45:
            risks.append("콘텐츠 실행 가능성 낮음")
        for flag in quality_flags:
            if any(token in flag for token in ("negative", "weak_service", "medical_ad", "competitor")):
                risks.append(f"품질 플래그: {flag}")
        return list(dict.fromkeys(risks))[:5]

    def _insight_score(
        self,
        row: Dict[str, Any],
        reasons: Sequence[str],
        risks: Sequence[str],
    ) -> float:
        base = max(
            _as_float(row.get("priority_v3")),
            _as_float(row.get("business_value_score")),
            _as_float(row.get("opportunity")),
            _as_float(row.get("opp_score")),
        )
        grade_bonus = {"S": 16.0, "A": 10.0, "B": 4.0}.get(str(row.get("grade") or "C"), 0.0)
        signal_bonus = min(18.0, len(reasons) * 2.5)
        risk_penalty = min(10.0, len(risks) * 2.0)
        return max(0.0, base + grade_bonus + signal_bonus - risk_penalty)

    def _agent_notes(
        self,
        row: Dict[str, Any],
        reasons: Sequence[str],
        risks: Sequence[str],
    ) -> Dict[str, str]:
        keyword = row.get("keyword", "")
        if _as_float(row.get("payment_coverage_score")) >= 70:
            blog_note = "비용/보험 적용 범위와 준비 서류를 정보형 FAQ로 풀 것"
            shorts_note = "보험/서류 체크리스트를 3컷 구조로 짧게 전달"
        elif _as_float(row.get("access_convenience_score")) >= 70:
            blog_note = "주차, 길찾기, 엘리베이터, 초진 동선을 방문 전 체크리스트로 구성"
            shorts_note = "입구, 주차, 접수 동선을 시각적으로 보여주는 방문 가이드"
        elif _as_float(row.get("availability_intent_score")) >= 70:
            blog_note = "당일/야간/주말 진료 가능 여부와 예약 방법을 명확히 설명"
            shorts_note = "대기 시간, 예약, 진료 가능 시간을 빠르게 확인시키는 훅"
        elif _as_float(row.get("review_surface_score")) >= 70:
            blog_note = "후기 자체보다 선택 기준과 확인 포인트를 중심으로 작성"
            shorts_note = "방문 전 확인할 3가지 기준을 카드형 쇼츠로 구성"
        elif _as_float(row.get("local_surface_score")) >= 70:
            blog_note = "지역명, 증상, 방문 행동을 자연스럽게 연결한 로컬 랜딩형 글"
            shorts_note = "지역 상황과 방문 맥락을 첫 3초 훅으로 제시"
        else:
            blog_note = "검색 의도, 증상 설명, 내원 전 확인사항을 균형 있게 구성"
            shorts_note = "문제 제기, 핵심 설명, 행동 유도 순서로 60초 이하 구성"

        guardrail = " / ".join(risks) if risks else "과장, 보장, 직접 비교 표현 금지"
        return {
            "blog_agent": f"{keyword}: {blog_note}. 가드레일: {guardrail}",
            "shorts_studio_agent": f"{keyword}: {shorts_note}. 가드레일: {guardrail}",
            "viral_hunter_agent": f"{keyword}: 커뮤니티 질문에 답할 때 광고성보다 확인 포인트 중심으로 대응",
            "ad_agent": f"{keyword}: 랜딩/광고 문구는 증상·방문 의도·확인 정보를 분리해 테스트",
        }

    def _keyword_actions(
        self,
        row: Dict[str, Any],
        reasons: Sequence[str],
        risks: Sequence[str],
    ) -> List[Dict[str, Any]]:
        keyword = row.get("keyword", "")
        return [
            {
                "owner": "blog_agent",
                "action": "create_blog_outline",
                "keyword": keyword,
                "priority": "high" if _as_float(row.get("business_value_score")) >= 70 else "medium",
                "angle": self._blog_angle(row),
                "must_include": reasons[:4],
                "avoid": risks or ["효과 보장", "과장된 비교", "후기 조작처럼 보이는 표현"],
            },
            {
                "owner": "shorts_studio_agent",
                "action": "create_short_script",
                "keyword": keyword,
                "priority": "high" if self._is_visual(row) else "medium",
                "angle": self._shorts_angle(row),
                "must_include": reasons[:3],
                "avoid": risks or ["자극적 치료 전후", "단정적 효과 표현"],
            },
        ]

    def _blog_angle(self, row: Dict[str, Any]) -> str:
        if _as_float(row.get("payment_coverage_score")) >= 70:
            return "비용/보험/서류를 내원 전 확인하는 정보형 FAQ"
        if _as_float(row.get("access_convenience_score")) >= 70:
            return "처음 방문하는 사용자를 위한 주차·길찾기·접근성 안내"
        if _as_float(row.get("availability_intent_score")) >= 70:
            return "예약 가능 시간과 진료 흐름을 설명하는 방문 준비 가이드"
        if _as_float(row.get("review_surface_score")) >= 70:
            return "후기보다 중요한 선택 기준 정리"
        return "증상 원인, 치료 선택 기준, 내원 전 확인사항을 묶은 설명형 글"

    def _shorts_angle(self, row: Dict[str, Any]) -> str:
        if _as_float(row.get("access_convenience_score")) >= 70:
            return "주차부터 접수까지 15초 방문 동선"
        if _as_float(row.get("availability_intent_score")) >= 70:
            return "오늘 갈 수 있는지 확인하는 3단계"
        if _as_float(row.get("payment_coverage_score")) >= 70:
            return "보험/서류 질문에 답하는 체크리스트"
        if _as_float(row.get("review_surface_score")) >= 70:
            return "방문 전 후기에서 확인할 3가지"
        return "검색자가 궁금해하는 핵심 질문 1개를 60초 안에 답변"

    def _is_visual(self, row: Dict[str, Any]) -> bool:
        return any(
            _as_float(row.get(col)) >= threshold
            for col, threshold in (
                ("access_convenience_score", 70),
                ("availability_intent_score", 70),
                ("local_surface_score", 70),
                ("review_surface_score", 70),
            )
        )

    def _brief_metrics(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        categories = Counter(card["category"] for card in cards)
        avg_confidence = (
            sum(float(card.get("confidence", 0)) for card in cards) / len(cards)
            if cards
            else 0.0
        )
        feedback_counts: Counter = Counter()
        for card in cards:
            feedback_counts.update((card.get("feedback_snapshot") or {}).get("counts") or {})
        decision_counts = Counter(
            (card.get("decision_packet") or {}).get("state", "unknown")
            for card in cards
        )
        return {
            "total_keywords": len(cards),
            "high_value_longtail_count": sum(1 for card in cards if card["signals"]["high_value_longtail"]),
            "access_intent_count": sum(1 for card in cards if card["metrics"].get("access_convenience_score", 0) >= 70),
            "payment_intent_count": sum(1 for card in cards if card["metrics"].get("payment_coverage_score", 0) >= 70),
            "availability_intent_count": sum(1 for card in cards if card["metrics"].get("availability_intent_score", 0) >= 70),
            "review_intent_count": sum(1 for card in cards if card["metrics"].get("review_surface_score", 0) >= 70),
            "risk_count": sum(1 for card in cards if card["risks"]),
            "avg_confidence": round(avg_confidence, 2),
            "low_confidence_count": sum(1 for card in cards if card.get("confidence", 0) < 0.58),
            "human_review_required_count": sum(1 for card in cards if card.get("human_review", {}).get("required")),
            "evidence_trace_count": sum(len(card.get("evidence_trace", [])) for card in cards),
            "feedback_event_count": sum(feedback_counts.values()),
            "feedback_counts": dict(feedback_counts),
            "decision_counts": dict(decision_counts),
            "measurement_plan_count": sum(1 for card in cards if card.get("measurement_plan")),
            "data_quality_thin_count": sum(1 for card in cards if (card.get("data_quality") or {}).get("status") == "thin"),
            "data_quality_caveat_count": sum(1 for card in cards if (card.get("data_quality") or {}).get("warnings")),
            "category_counts": dict(categories),
        }

    def _build_summary(self, cards: Sequence[Dict[str, Any]], metrics: Dict[str, Any]) -> Dict[str, Any]:
        top = cards[0] if cards else None
        if not top:
            headline = "Pathfinder 인사이트가 아직 없습니다"
            next_best_action = "Legion 모드를 실행해 최신 검증 키워드를 확보하세요."
        else:
            headline = f"가장 먼저 실행할 키워드는 '{top['keyword']}'입니다"
            next_best_action = top["recommended_actions"][0]["angle"]
        return {
            "headline": headline,
            "next_best_action": next_best_action,
            "agent_ready": bool(cards),
            "handoff_targets": ["blog_agent", "shorts_studio_agent", "viral_hunter_agent", "ad_agent"],
            "confidence": {
                "average": metrics.get("avg_confidence", 0.0),
                "band": self._confidence_band(float(metrics.get("avg_confidence", 0.0))),
                "human_review_required": metrics.get("human_review_required_count", 0),
            },
            "decision_counts": metrics.get("decision_counts", {}),
            "coverage": metrics,
        }

    def _build_top_insights(self, cards: Sequence[Dict[str, Any]], metrics: Dict[str, Any]) -> List[str]:
        if not cards:
            return ["최신 Pathfinder Legion 결과가 없어 인사이트 브리프를 만들 수 없습니다."]
        insights = [
            f"상위 {len(cards)}개 후보 중 고가치 롱테일은 {metrics['high_value_longtail_count']}개입니다.",
        ]
        if metrics["access_intent_count"]:
            insights.append(f"방문 편의/접근성 의도가 {metrics['access_intent_count']}개 있어 쇼츠와 플레이스형 콘텐츠에 적합합니다.")
        if metrics["payment_intent_count"]:
            insights.append(f"비용/보험 확인 의도가 {metrics['payment_intent_count']}개 있어 FAQ형 블로그로 전환 설명을 강화해야 합니다.")
        if metrics["availability_intent_count"]:
            insights.append(f"예약/시간 민감 의도가 {metrics['availability_intent_count']}개 있어 즉시성 있는 CTA가 필요합니다.")
        if metrics["review_intent_count"]:
            insights.append(f"리뷰/평판 탐색 의도가 {metrics['review_intent_count']}개 있어 후기보다 선택 기준 중심의 메시지가 안전합니다.")
        if metrics["risk_count"]:
            insights.append(f"{metrics['risk_count']}개 후보는 의료광고/브랜드/평판 가드레일 검토 후 실행해야 합니다.")
        if metrics.get("human_review_required_count"):
            insights.append(
                f"{metrics['human_review_required_count']}개 후보는 신뢰도·근거·가드레일 기준상 사람 검토가 먼저 필요합니다."
            )
        if metrics.get("feedback_event_count"):
            insights.append(
                f"기존 피드백 {metrics['feedback_event_count']}건이 반영되어 승인/검토/실패 이력을 함께 봅니다."
            )
        decision_counts = metrics.get("decision_counts") or {}
        if decision_counts:
            insights.append(
                f"실행 상태는 go {decision_counts.get('go', 0)}개, review {decision_counts.get('review', 0)}개, hold {decision_counts.get('hold', 0)}개입니다."
            )
        top_categories = ", ".join(name for name, _ in Counter(metrics["category_counts"]).most_common(3))
        if top_categories:
            insights.append(f"우선 카테고리는 {top_categories}입니다.")
        return insights[:7]

    def _build_provenance(
        self,
        cards: Sequence[Dict[str, Any]],
        *,
        latest_verified_only: bool,
        business_core_only: bool,
    ) -> Dict[str, Any]:
        run_ids = sorted({
            card.get("provenance", {}).get("last_scan_run_id")
            for card in cards
            if card.get("provenance", {}).get("last_scan_run_id")
        })
        sources = sorted({
            card.get("provenance", {}).get("source") or "pathfinder"
            for card in cards
        })
        return {
            "model": "w3c-prov-lite",
            "source_table": "keyword_insights",
            "database": Path(self.db_path).name,
            "latest_verified_only": latest_verified_only,
            "business_core_only": business_core_only,
            "last_scan_run_ids": run_ids,
            "source_labels": sources,
            "cards": [
                {
                    "handoff_id": card.get("handoff_id"),
                    "keyword": card.get("keyword"),
                    "last_scan_run_id": card.get("provenance", {}).get("last_scan_run_id"),
                    "source": card.get("provenance", {}).get("source"),
                }
                for card in cards[:12]
            ],
        }

    def _quality_gate(self, cards: Sequence[Dict[str, Any]], metrics: Dict[str, Any]) -> Dict[str, Any]:
        checks = [
            {
                "name": "has_keywords",
                "passed": bool(cards),
                "detail": f"{len(cards)} keyword cards",
            },
            {
                "name": "has_evidence_trace",
                "passed": metrics.get("evidence_trace_count", 0) >= len(cards),
                "detail": f"{metrics.get('evidence_trace_count', 0)} evidence items",
            },
            {
                "name": "confidence_calibrated",
                "passed": not cards or metrics.get("avg_confidence", 0) >= 0.58,
                "detail": f"average confidence {metrics.get('avg_confidence', 0)}",
            },
            {
                "name": "review_queue_visible",
                "passed": True,
                "detail": f"{metrics.get('human_review_required_count', 0)} items require human review",
            },
            {
                "name": "agent_contract_ready",
                "passed": bool(cards),
                "detail": "blog, shorts, viral, and ad packets include shared handoff fields",
            },
            {
                "name": "decision_states_declared",
                "passed": not cards or sum((metrics.get("decision_counts") or {}).values()) == len(cards),
                "detail": f"decision states {metrics.get('decision_counts', {})}",
            },
            {
                "name": "measurement_plan_ready",
                "passed": not cards or metrics.get("measurement_plan_count", 0) == len(cards),
                "detail": f"{metrics.get('measurement_plan_count', 0)} measurement plans",
            },
            {
                "name": "data_quality_visible",
                "passed": True,
                "detail": f"{metrics.get('data_quality_thin_count', 0)} thin data-quality cards",
            },
        ]
        if not cards:
            status = "empty"
        elif any(not check["passed"] for check in checks):
            status = "review"
        elif metrics.get("human_review_required_count", 0):
            status = "review"
        elif metrics.get("data_quality_thin_count", 0):
            status = "review"
        elif (metrics.get("decision_counts") or {}).get("hold", 0):
            status = "review"
        else:
            status = "pass"
        return {
            "status": status,
            "checks": checks,
            "required_before_publish": [
                "review all human_review.required items",
                "keep evidence_trace with generated content or campaign drafts",
                "do not use medical guarantees, competitor attacks, or review manipulation",
            ],
        }

    def _delivery_contract(self) -> Dict[str, Any]:
        return {
            "handoff_fields": [
                "handoff_id",
                "primary_keyword",
                "confidence",
                "confidence_band",
                "evidence_trace",
                "human_review",
                "feedback_snapshot",
                "decision_packet",
                "measurement_plan",
                "data_quality",
                "risk_guardrails",
                "success_criteria",
            ],
            "agent_packets": {
                "blog_agent": "produce evidence-backed outline, FAQ, and safe local intent copy",
                "shorts_studio_agent": "produce short-form hook and visual beats from explicit intent signals",
                "viral_hunter_agent": "listen for community questions and reply with verification-first guidance",
                "ad_agent": "test landing and ad messaging only after guardrail review",
            },
            "guardrails": [
                "preserve the handoff_id in downstream drafts",
                "cite or restate the evidence_trace that justifies the angle",
                "respect decision_packet.publish_policy before publishing",
                "measure outcome using measurement_plan.primary_metric",
                "send low-confidence or risk-marked cards back to human review",
            ],
        }

    def _feedback_contract(self) -> Dict[str, Any]:
        return {
            "endpoint": "/pathfinder/insight-feedback",
            "method": "POST",
            "feedback_types": [
                "accepted",
                "rejected",
                "needs_review",
                "sent_to_agent",
                "completed",
                "failed",
            ],
            "minimum_payload": ["handoff_id", "feedback_type"],
        }

    def _codex_synthesis(
        self,
        *,
        cards: Sequence[Dict[str, Any]],
        metrics: Dict[str, Any],
        action_queue: Sequence[Dict[str, Any]],
        requested: bool,
    ) -> Dict[str, Any]:
        fallback = self._deterministic_synthesis(cards=cards, metrics=metrics, action_queue=action_queue)
        if not requested:
            return {
                **fallback,
                "status": "not_requested",
                "model": "deterministic_fallback",
            }
        if not cards:
            return {
                **fallback,
                "status": "empty",
                "model": "deterministic_fallback",
            }

        prompt_cards = [
            {
                "handoff_id": card.get("handoff_id"),
                "keyword": card["keyword"],
                "grade": card["grade"],
                "category": card["category"],
                "intent": card["search_intent"],
                "insight_score": card["insight_score"],
                "confidence": card.get("confidence"),
                "confidence_band": card.get("confidence_band"),
                "why_it_matters": card["why_it_matters"],
                "risks": card["risks"],
                "evidence_trace": card.get("evidence_trace", [])[:8],
                "human_review": card.get("human_review", {}),
                "feedback_snapshot": card.get("feedback_snapshot", {}),
                "decision_packet": card.get("decision_packet", {}),
                "measurement_plan": card.get("measurement_plan", {}),
                "data_quality": card.get("data_quality", {}),
                "agent_notes": card["agent_notes"],
                "signals": card["signals"],
                "metrics": {
                    "business_value_score": card["metrics"].get("business_value_score", 0),
                    "longtail_score": card["metrics"].get("longtail_score", 0),
                    "search_volume": card["metrics"].get("search_volume", 0),
                    "local_surface_score": card["metrics"].get("local_surface_score", 0),
                    "payment_coverage_score": card["metrics"].get("payment_coverage_score", 0),
                    "access_convenience_score": card["metrics"].get("access_convenience_score", 0),
                    "availability_intent_score": card["metrics"].get("availability_intent_score", 0),
                    "review_surface_score": card["metrics"].get("review_surface_score", 0),
                },
            }
            for card in list(cards)[:8]
        ]
        prompt = f"""
You are Codex acting as a senior marketing strategist for a Korean medicine clinic.
Read the Pathfinder keyword insight cards and produce a concise Korean executive synthesis.

Return JSON only with this shape:
{{
  "executive_summary": "2-3 sentence Korean summary for the user",
  "decision": "what should be done first",
  "confidence": 0.0,
  "agent_routing": [
    {{"agent": "blog_agent", "priority": "high|medium|low", "instruction": "specific handoff"}},
    {{"agent": "shorts_studio_agent", "priority": "high|medium|low", "instruction": "specific handoff"}}
  ],
  "watchouts": ["guardrail 1", "guardrail 2"],
  "why_this_is_not_generic": "explain why these are insight-backed, not keyword stuffing"
}}

Metrics:
{json.dumps(metrics, ensure_ascii=False)}

Action queue:
{json.dumps(list(action_queue)[:6], ensure_ascii=False)}

Keyword cards:
{json.dumps(prompt_cards, ensure_ascii=False)}
"""
        try:
            try:
                from services.ai_client import ai_generate_json
            except Exception:
                from marketing_bot_web.backend.services.ai_client import ai_generate_json

            result = ai_generate_json(
                prompt,
                temperature=0.2,
                max_tokens=1400,
                task="strategy",
            )
            if isinstance(result, dict) and result:
                return {
                    **fallback,
                    **result,
                    "status": "codex",
                    "model": "codex_cli",
                }
        except Exception as exc:
            fallback["error"] = str(exc)
        return {
            **fallback,
            "status": "fallback",
            "model": "deterministic_fallback",
        }

    def _deterministic_synthesis(
        self,
        *,
        cards: Sequence[Dict[str, Any]],
        metrics: Dict[str, Any],
        action_queue: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not cards:
            return {
                "executive_summary": "최신 Pathfinder 인사이트가 아직 없습니다. Legion 모드를 실행해 검증된 키워드와 에이전트 handoff를 먼저 확보해야 합니다.",
                "decision": "Pathfinder Legion 실행",
                "confidence": 0.0,
                "agent_routing": [],
                "watchouts": [],
                "why_this_is_not_generic": "실행 가능한 키워드 카드가 없어 일반적인 조언만 가능합니다.",
            }

        top = cards[0]
        first_action = action_queue[0] if action_queue else top["recommended_actions"][0]
        summary_parts = [
            f"가장 높은 실행 우선순위는 '{top['keyword']}'입니다.",
            f"상위 후보 {len(cards)}개 중 고가치 롱테일은 {metrics.get('high_value_longtail_count', 0)}개입니다.",
        ]
        if metrics.get("access_intent_count", 0):
            summary_parts.append("방문 편의/접근성 신호가 있어 쇼츠와 플레이스형 콘텐츠로도 전달 가치가 큽니다.")
        if metrics.get("payment_intent_count", 0):
            summary_parts.append("비용/보험 신호는 FAQ형 블로그로 풀어야 전환 설명력이 높아집니다.")

        routing = []
        for action in list(action_queue)[:4]:
            routing.append({
                "agent": action.get("owner", ""),
                "priority": action.get("priority", "medium"),
                "instruction": f"{action.get('keyword', '')}: {action.get('angle', '')}",
            })

        watchouts: List[str] = []
        for card in cards[:5]:
            watchouts.extend(card.get("risks") or [])
        watchouts = list(dict.fromkeys(watchouts))[:4]

        return {
            "executive_summary": " ".join(summary_parts),
            "decision": f"{first_action.get('owner', 'blog_agent')}에서 '{first_action.get('keyword', top['keyword'])}' 실행",
            "confidence": round(float(metrics.get("avg_confidence") or top.get("confidence") or 0.0), 2),
            "agent_routing": routing,
            "watchouts": watchouts,
            "why_this_is_not_generic": "Pathfinder의 사업가치, 롱테일, 로컬/예약/비용/접근성/리뷰 신호와 가드레일을 함께 사용해 생성된 실행 브리프입니다.",
        }

    def _build_action_queue(self, cards: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        queue: List[Dict[str, Any]] = []
        for card in cards[:6]:
            for action in card["recommended_actions"]:
                item = dict(action)
                item["handoff_id"] = card.get("handoff_id")
                item["insight_score"] = card["insight_score"]
                item["confidence"] = card.get("confidence")
                item["confidence_band"] = card.get("confidence_band")
                item["human_review"] = card.get("human_review", {})
                item["feedback_snapshot"] = card.get("feedback_snapshot", {})
                item["decision_packet"] = card.get("decision_packet", {})
                item["measurement_plan"] = card.get("measurement_plan", {})
                item["data_quality"] = card.get("data_quality", {})
                item["evidence_trace"] = card.get("evidence_trace", [])[:6]
                item["rationale"] = card["why_it_matters"][:3]
                queue.append(item)
        queue.sort(key=lambda item: (item["priority"] != "high", -item["insight_score"]))
        return queue[:10]

    def _support_keywords(self, cards: Sequence[Dict[str, Any]], card: Dict[str, Any]) -> List[str]:
        same_category = [
            other["keyword"]
            for other in cards
            if other["keyword"] != card["keyword"] and other["category"] == card["category"]
        ]
        return same_category[:4]

    def _task_contract(self, card: Dict[str, Any], agent: str) -> Dict[str, Any]:
        return {
            "handoff_id": card.get("handoff_id"),
            "confidence": card.get("confidence"),
            "confidence_band": card.get("confidence_band"),
            "human_review": card.get("human_review", {}),
            "feedback_snapshot": card.get("feedback_snapshot", {}),
            "decision_packet": card.get("decision_packet", {}),
            "measurement_plan": card.get("measurement_plan", {}),
            "data_quality": card.get("data_quality", {}),
            "evidence_trace": card.get("evidence_trace", [])[:8],
            "risk_guardrails": card.get("risks", []),
            "success_criteria": self._success_criteria(card, agent),
        }

    def _success_criteria(self, card: Dict[str, Any], agent: str) -> List[str]:
        criteria = [
            "uses the primary keyword naturally without stuffing",
            "preserves the handoff_id for traceability",
            "reflects at least two evidence_trace signals in the output",
        ]
        if card.get("human_review", {}).get("required"):
            criteria.append("waits for human review before publishing or running ads")
        if agent == "blog_agent":
            criteria.append("turns intent into an outline, FAQ, and safe CTA")
        elif agent == "shorts_studio_agent":
            criteria.append("turns explicit intent into a hook and visual beats")
        elif agent == "viral_hunter_agent":
            criteria.append("answers community demand with verification-first wording")
        elif agent == "ad_agent":
            criteria.append("separates landing-page proof from ad copy claims")
        return criteria

    def _blog_packet(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        tasks = []
        for card in cards:
            action = card["recommended_actions"][0]
            tasks.append({
                **self._task_contract(card, "blog_agent"),
                "primary_keyword": card["keyword"],
                "category": card["category"],
                "angle": action["angle"],
                "support_keywords": self._support_keywords(cards, card),
                "must_include": action["must_include"],
                "avoid": action["avoid"],
                "evidence": card["why_it_matters"],
            })
        return {"tasks": tasks, "prompt_context": self.format_prompt_context(cards=cards, agent="blog_agent")}

    def _shorts_packet(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        tasks = []
        for card in cards:
            action = card["recommended_actions"][1]
            tasks.append({
                **self._task_contract(card, "shorts_studio_agent"),
                "primary_keyword": card["keyword"],
                "hook": action["angle"],
                "visual_beats": self._shorts_visual_beats(card),
                "must_include": action["must_include"],
                "avoid": action["avoid"],
            })
        return {"tasks": tasks, "prompt_context": self.format_prompt_context(cards=cards, agent="shorts_studio_agent")}

    def _shorts_visual_beats(self, card: Dict[str, Any]) -> List[str]:
        signal = card["signals"]
        if signal["access_convenience_type"] != "none":
            return ["외부/주차 컷", "입구 또는 접수 동선", "방문 전 체크 문구"]
        if signal["availability_intent_type"] != "none":
            return ["시계 또는 예약 화면", "대기/접수 상황", "빠른 문의 CTA"]
        if signal["payment_coverage_type"] != "none":
            return ["서류 체크리스트", "보험/비용 질문 자막", "상담 전 확인 CTA"]
        return ["검색 질문 자막", "핵심 설명 컷", "방문 전 확인 CTA"]

    def _viral_packet(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        tasks = [{
            **self._task_contract(card, "viral_hunter_agent"),
            "keyword": card["keyword"],
            "listening_angle": "질문형 글과 댓글에서 정보 부족/방문 전 불안을 찾기",
            "reply_guidance": card["agent_notes"]["viral_hunter_agent"],
            "risk_guardrails": card["risks"],
        } for card in cards]
        return {"tasks": tasks, "prompt_context": self.format_prompt_context(cards=cards, agent="viral_hunter_agent")}

    def _ad_packet(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        tasks = [{
            **self._task_contract(card, "ad_agent"),
            "keyword": card["keyword"],
            "test_idea": card["agent_notes"]["ad_agent"],
            "landing_focus": card["recommended_actions"][0]["angle"],
            "risk_guardrails": card["risks"],
        } for card in cards]
        return {"tasks": tasks, "prompt_context": self.format_prompt_context(cards=cards, agent="ad_agent")}


def load_pathfinder_prompt_context(
    db_path: str,
    *,
    agent: str = "all",
    topic: Optional[str] = None,
    limit: int = 5,
) -> str:
    """Convenience helper for legacy agents that only accept prompt text."""
    try:
        broker = PathfinderInsightBroker(db_path)
        cards = broker.keyword_cards(limit=limit)
        if topic:
            topic_norm = topic.replace(" ", "").lower()
            filtered = [
                card for card in cards
                if topic_norm in card["keyword"].replace(" ", "").lower()
                or card["keyword"].replace(" ", "").lower() in topic_norm
            ]
            if filtered:
                cards = filtered + [card for card in cards if card not in filtered]
        return broker.format_prompt_context(cards=cards, agent=AGENT_ALIASES.get(agent, agent), topic=topic, limit=limit)
    except Exception as exc:
        return f"[Pathfinder Insight Handoff unavailable: {exc}]"
