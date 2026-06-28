"""
Channel behavior analyzer — Phase 8.

Performs holistic fraud-risk assessment of a channel based on its full signal,
edit, delete, and screenshot history. Called after each verification pass for
channels with new resolved signals. Results feed into the trust score as an
integrity penalty (fraud_risk_score × AI_BEHAVIOR_PENALTY_MAX, max 10 pts).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import anthropic

from backend.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

logger = logging.getLogger(__name__)

_CHANNEL_PROMPT = """\
You are a XAUUSD signal channel fraud analyst. Assess the channel described below
for signs of manipulation or dishonest signal presentation.

Channel: {channel_name}

Summary data:
- Resolved signals: {total_signals}
- Stated win rate: {win_rate_pct:.1f}%
- Signals flagged as retrospective (posted after the move): {retrospective_count}
- Signals flagged as low quality: {low_quality_count}
- Edit pattern: {edit_summary}
- Delete pattern: {delete_summary}
- Signal timing: {timing_summary}
- Screenshot claims — confirmed: {screenshot_confirmed}, contradicted (fabricated): {screenshot_contradicted}

Score each dimension 0.0–1.0 where 1.0 = highest manipulation risk:
- fraud_risk_score: overall channel honesty (0 = fully honest, 1 = clearly manipulative)
- timing_score: manipulation risk from signal timing (1 = consistently posts after moves begin)
- edit_manipulation_score: manipulation risk from edit pattern (1 = systematically edits in own favor)
- delete_manipulation_score: manipulation risk from deletion pattern (1 = deletes losses, keeps wins)

key_findings: 1–3 sentences of the most important observations. Be specific with numbers.

Return ONLY this JSON:
{{
  "fraud_risk_score": <0.0–1.0>,
  "timing_score": <0.0–1.0>,
  "edit_manipulation_score": <0.0–1.0>,
  "delete_manipulation_score": <0.0–1.0>,
  "key_findings": "<1–3 specific sentences>"
}}
"""


@dataclass
class ChannelAnalysis:
    fraud_risk_score: float
    timing_score: float
    edit_manipulation_score: float
    delete_manipulation_score: float
    key_findings: str
    signals_analyzed: int


def _extract_json(text: str) -> dict | None:
    m = re.search(r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def analyze_channel_behavior(
    channel_name: str,
    summary_data: dict,
) -> ChannelAnalysis | None:
    """
    Assess a channel's overall behaviour for fraud risk.

    Args:
        channel_name: Display name of the channel.
        summary_data: Dict with keys: total_signals, win_rate_pct, retrospective_count,
            low_quality_count, edit_summary, delete_summary, timing_summary,
            screenshot_confirmed, screenshot_contradicted.

    Returns ChannelAnalysis or None on failure. Never raises.
    """
    if not ANTHROPIC_API_KEY:
        return None

    prompt = _CHANNEL_PROMPT.format(
        channel_name=channel_name,
        total_signals=summary_data.get("total_signals", 0),
        win_rate_pct=float(summary_data.get("win_rate_pct", 0)),
        retrospective_count=summary_data.get("retrospective_count", 0),
        low_quality_count=summary_data.get("low_quality_count", 0),
        edit_summary=summary_data.get("edit_summary", "No edit data."),
        delete_summary=summary_data.get("delete_summary", "No delete data."),
        timing_summary=summary_data.get("timing_summary", "No timing data."),
        screenshot_confirmed=summary_data.get("screenshot_confirmed", 0),
        screenshot_contradicted=summary_data.get("screenshot_contradicted", 0),
    )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        data = _extract_json(raw)
        if data is None:
            logger.debug("Channel analyzer: no JSON in response for channel=%r", channel_name)
            return None

        def _score(key: str) -> float | None:
            v = data.get(key)
            if v is None:
                return None
            try:
                return max(0.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                return None

        fraud = _score("fraud_risk_score")
        timing = _score("timing_score")
        edit_manip = _score("edit_manipulation_score")
        delete_manip = _score("delete_manipulation_score")

        if any(s is None for s in (fraud, timing, edit_manip, delete_manip)):
            logger.warning(
                "Channel analyzer: missing scores in response for channel=%r", channel_name
            )
            return None

        key_findings = str(data.get("key_findings", ""))[:2000]

        return ChannelAnalysis(
            fraud_risk_score=round(fraud, 3),  # type: ignore[arg-type]
            timing_score=round(timing, 3),  # type: ignore[arg-type]
            edit_manipulation_score=round(edit_manip, 3),  # type: ignore[arg-type]
            delete_manipulation_score=round(delete_manip, 3),  # type: ignore[arg-type]
            key_findings=key_findings,
            signals_analyzed=int(summary_data.get("total_signals", 0)),
        )

    except Exception as exc:
        logger.warning("Channel behavior analysis failed (non-fatal): %s", exc)
        return None
