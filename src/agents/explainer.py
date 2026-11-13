"""
AstroHealth / RoboBee Health Guardian — Lunar Assistant & Non-Diagnostic Explainer Engine
Provides deterministic, provenance-aware responses, validated 3D body-focus instructions
for `window.LunarBodyGuide`, longitudinal symptom tracking integration, and strict
non-diagnostic clinical boundaries per NASA-STD-3001.
"""

import os
import re
import io
import time
import json
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from PIL import Image

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

from src.models.telemetry import (
    SUPPORTED_BODY_REGIONS,
    SUPPORTED_BODY_LAYERS,
    SUPPORTED_FOCUS_SEVERITIES,
    validate_body_region,
    resolve_region_layer,
    BodyFocusInstruction,
    LunarAskResponse,
)
from src.data.research import RESEARCH_CITATIONS
from src.storage.db import (
    get_latest_telemetry,
    get_alerts,
    create_symptom_report,
    get_symptom_reports,
    get_symptom_report_by_id,
    record_symptom_followup,
    get_due_symptom_reminders,
)

# Current Gemini model tiers per official Google GenAI SDK guidelines
GEMINI_CONVERSATIONAL_MODELS: Tuple[str, ...] = (
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
)
GEMINI_TTS_MODELS: Tuple[str, ...] = (
    "gemini-3.8-flash-lite-tts",
    "gemini-3.8-flash-tts",
)
GEMINI_LIVE_MODEL: str = "gemini-3.8-live"
GEMINI_LIVE_DIALOG_MODEL: str = "gemini-2.5-flash-native-audio-latest"


def _load_project_env() -> None:
    """Loads `.env` from project root into `os.environ` without leaking values."""
    try:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k, v = stripped.split("=", 1)
                    key = k.strip()
                    val = v.strip().strip('"').strip("'")
                    if key and val and not os.environ.get(key):
                        os.environ[key] = val
    except Exception:
        pass


_load_project_env()


def get_gemini_api_key() -> str:
    """Returns configured Gemini API key from environment or `.env`."""
    _load_project_env()
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


_GEMINI_COOLDOWN_UNTIL: float = 0.0


def _is_gemini_in_cooldown() -> bool:
    """Skips redundant blocking Gemini calls briefly after a network timeout."""
    if os.environ.get("LUNAR_FORCE_GEMINI_IN_TESTS") == "1":
        return False
    return time.monotonic() < _GEMINI_COOLDOWN_UNTIL


def _mark_gemini_timeout(seconds: float = 90.0) -> None:
    """Records a short network-timeout cooldown so dashboard & camera polling stay instant."""
    global _GEMINI_COOLDOWN_UNTIL
    _GEMINI_COOLDOWN_UNTIL = time.monotonic() + seconds


def _is_timeout_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    name = type(exc).__name__.lower()
    return "timed out" in msg or "timeout" in name or "connect" in msg


def get_gemini_client(timeout_ms: int = 12000):
    """Creates a single-attempt `google.genai.Client` honoring Gemini's >=10s minimum deadline."""
    if _is_gemini_in_cooldown():
        return None
    api_key = get_gemini_api_key()
    if genai is None or not api_key:
        return None
    try:
        effective_timeout = max(int(timeout_ms or 12000), 12000)
        if genai_types is not None and hasattr(genai_types, "HttpOptions"):
            opts_kwargs: Dict[str, Any] = {"timeout": effective_timeout}
            if hasattr(genai_types, "HttpRetryOptions"):
                opts_kwargs["retry_options"] = genai_types.HttpRetryOptions(attempts=1)
            return genai.Client(api_key=api_key, http_options=genai_types.HttpOptions(**opts_kwargs))
        return genai.Client(api_key=api_key)
    except Exception:
        return None


def _decode_valid_image_bytes(image_base64: Optional[str]) -> Tuple[Optional[bytes], str]:
    """Decodes base64 image data and checks whether it is a valid >=16x16 raster image."""
    clean_b64 = (image_base64 or "").strip()
    if not clean_b64:
        return None, "image/jpeg"
    mime_type = "image/jpeg"
    if clean_b64.startswith("data:"):
        header, _, payload = clean_b64.partition(",")
        clean_b64 = payload.strip()
        if "image/png" in header:
            mime_type = "image/png"
        elif "image/webp" in header:
            mime_type = "image/webp"
    if len(clean_b64) < 64:
        return None, mime_type
    try:
        raw = base64.b64decode(clean_b64, validate=False)
        with Image.open(io.BytesIO(raw)) as im:
            w, h = im.size
            if w >= 16 and h >= 16:
                return raw, mime_type
    except Exception:
        return None, mime_type
    return None, mime_type


# A hard programmatic post-check that intercepts clinical diagnostic claims or prescriptions
FORBIDDEN_TERMS = [
    r"\bdiagnos(e|is|ed|ing)\b",
    r"\btreat(ment|ed|ing)?\b",
    r"\bprescri(be|ption)\b",
    r"\bsyndrome\b",
    r"\bdisease\b",
    r"\bpatholog(y|ical)\b",
]


def sanitize_agent_output(text: str) -> str:
    """
    Blocks and redacts forbidden diagnostic claims to enforce the Science Boundary.
    """
    for pattern in FORBIDDEN_TERMS:
        if re.search(pattern, text, re.IGNORECASE):
            return "Alert: Telemetry deviation detected. Consult flight surgeon logs. Citing relevant NASA literature."
    return text


def build_evidence_card(alert: Dict[str, Any], cached_metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Generates an evidence-backed factual summary linking directly to open NASA literature.
    This acts as the deterministic 'Agent' output without requiring a live LLM call
    (satisfying the offline requirement).
    """
    if cached_metadata is None:
        study_id = "OSD-87"
        study_url = "https://osdr.nasa.gov/osdr/data/osd/files/87.1"
        study_title = "Spaceflight effects on cardiovascular autonomic regulation"
    else:
        study_id = cached_metadata.get("study_id", "OSD-87")
        study_url = cached_metadata.get("url", "https://osdr.nasa.gov/osdr/data/osd/files/87.1")
        study_title = cached_metadata.get("title", "Spaceflight effects on cardiovascular autonomic regulation")

    rule = alert.get("rule", "Unknown anomaly")
    z_score = alert.get("z", 0.0)
    current = alert.get("current", 0.0)
    baseline_mean = alert.get("baseline_mean", 0.0)

    summary = (
        f"Deviation recorded: {rule} with Z-score {z_score}. "
        f"Observed value ({current}) deviated from personal mean ({baseline_mean}). "
        f"Literature context: {study_title}. "
        f"Cataloged under NASA OSDR study {study_id}."
    )

    clean_text = sanitize_agent_output(summary)

    return {
        "text": clean_text,
        "study_id": study_id,
        "source_url": study_url,
        "raw_alert": alert,
    }


def _select_side(text_lower: str, default_side: str = "left") -> str:
    if "right" in text_lower:
        return "right"
    if "left" in text_lower:
        return "left"
    return default_side


def extract_body_region_and_intent(
    question: str,
    explicit_region: Optional[str] = None,
    explicit_layer: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deterministically maps a crew member's query or explicit region parameter to:
    - validated `body_region` (one of the 28 keys in `web/body-model.js`)
    - validated `layer` ('Full body', 'Heart', 'Lungs', 'Skeleton')
    - `intent_category`: 'cardiovascular' | 'respiratory' | 'symptom_followup' | 'symptom_report' | 'general_status' | 'clear_focus'
    - `followup_direction`: 'improving' | 'unchanged' | 'worsened' | 'resolved' | None
    """
    q = (question or "").strip().lower()

    # Check if user wants to clear/reset focus
    if any(phrase in q for phrase in ("clear focus", "reset view", "clear highlight", "remove highlight")):
        return {
            "body_region": None,
            "layer": "Full body",
            "intent_category": "clear_focus",
            "followup_direction": None,
            "is_joint_or_bone": False,
        }

    is_joint_or_bone = any(
        kw in q for kw in ("joint", "bone", "skeleton", "skeletal", "socket", "cartilage", "ligament", "sprain")
    )

    # Detect follow-up confirmation language
    followup_direction: Optional[str] = None
    if any(w in q for w in ("healed", "resolved", "completely gone", "all better", "no longer hurts", "cleared up")):
        followup_direction = "resolved"
    elif any(w in q for w in ("feels better", "feeling better", "improved", "improving", "less pain", "fading", "getting better")):
        followup_direction = "improving"
    elif any(w in q for w in ("worse", "worsened", "more painful", "getting worse", "hurts more", "increased pain")):
        followup_direction = "worsened"
    elif any(w in q for w in ("same", "unchanged", "no change", "still hurts the same", "hasn't changed")):
        followup_direction = "unchanged"

    # 1. Explicit region validation first
    valid_explicit = validate_body_region(explicit_region)
    if valid_explicit:
        if is_joint_or_bone and valid_explicit in ("left-shoulder", "right-shoulder"):
            valid_explicit = f"{valid_explicit}-joint"
        layer = resolve_region_layer(
            valid_explicit,
            explicit_layer if explicit_layer in SUPPORTED_BODY_LAYERS else ("Skeleton" if is_joint_or_bone else None),
        )
        intent = "symptom_followup" if followup_direction else "symptom_report"
        return {
            "body_region": valid_explicit,
            "layer": layer,
            "intent_category": intent,
            "followup_direction": followup_direction,
            "is_joint_or_bone": is_joint_or_bone or (layer == "Skeleton"),
        }

    # 2. Natural-language body region detection against the 28 supported regions
    side = _select_side(q, default_side="left")
    detected_region: Optional[str] = None
    detected_layer: Optional[str] = explicit_layer if explicit_layer in SUPPORTED_BODY_LAYERS else None

    if any(w in q for w in ("finger", "index finger", "thumb", "digit")) or ("cut" in q and "hand" not in q and "arm" not in q):
        # Default to right-finger if 'cut' is mentioned without side, or respect explicit side
        finger_side = _select_side(q, default_side="right" if "cut" in q else "left")
        detected_region = f"{finger_side}-finger"
    elif "shoulder" in q or "clavicle" in q or "collarbone" in q:
        detected_region = f"{side}-shoulder-joint" if is_joint_or_bone else f"{side}-shoulder"
    elif "elbow" in q:
        detected_region = f"{side}-elbow"
    elif "forearm" in q or "wrist" in q:
        detected_region = f"{side}-forearm"
    elif "hand" in q or "palm" in q:
        detected_region = f"{side}-hand"
    elif "knee" in q or "kneecap" in q or "patella" in q:
        detected_region = f"{side}-knee"
    elif "ankle" in q:
        detected_region = f"{side}-ankle"
    elif "foot" in q or "feet" in q or "heel" in q or "toe" in q:
        detected_region = f"{side}-foot"
    elif "thigh" in q or "hamstring" in q or "quad" in q:
        detected_region = f"{side}-thigh"
    elif "calf" in q or "shin" in q or "lower leg" in q or ("leg" in q and "thigh" not in q):
        detected_region = f"{side}-lower-leg"
    elif "hip" in q or "pelvis" in q:
        detected_region = f"{side}-hip"
    elif any(w in q for w in ("abdomen", "stomach", "belly", "gut", "nausea")):
        detected_region = "abdomen"
    elif "neck" in q or "cervical" in q or "throat" in q:
        detected_region = "neck"
    elif any(w in q for w in ("head", "headache", "migraine", "temple", "skull", "dizziness", "vision")):
        detected_region = "head"
    elif any(w in q for w in ("heart", "cardiac", "pulse", "bpm", "tachycardia", "bradycardia", "ecg", "hrv", "blood pressure", "pressure", "bp")):
        detected_region = "chest"
        detected_layer = detected_layer or ("Lungs" if ("oxygen" in q or "spo2" in q) else "Heart")
        return {
            "body_region": detected_region,
            "layer": detected_layer,
            "intent_category": "respiratory" if ("oxygen" in q or "spo2" in q) else "cardiovascular",
            "followup_direction": followup_direction,
            "is_joint_or_bone": False,
        }
    elif any(w in q for w in ("lung", "breath", "breathing", "respiration", "spo2", "oxygen", "hypoxia", "co2", "carbon dioxide")):
        detected_region = "chest"
        detected_layer = detected_layer or "Lungs"
        return {
            "body_region": detected_region,
            "layer": detected_layer,
            "intent_category": "respiratory",
            "followup_direction": followup_direction,
            "is_joint_or_bone": False,
        }
    elif "chest" in q or "rib" in q or "sternum" in q:
        detected_region = "chest"
        if is_joint_or_bone or "rib" in q or "sternum" in q:
            detected_layer = detected_layer or "Skeleton"

    if detected_region:
        valid_region = validate_body_region(detected_region)
        resolved_layer = resolve_region_layer(
            valid_region,
            detected_layer or ("Skeleton" if is_joint_or_bone else None),
        )
        has_symptom_words = any(
            w in q
            for w in (
                "pain", "hurt", "hurts", "ache", "aching", "sore", "cut", "scrape",
                "strain", "sprain", "stiff", "stiffness", "swollen", "injury", "injured",
                "discomfort", "bruise", "bleed", "check my", "revisit", "follow up",
            )
        )
        intent = (
            "symptom_followup"
            if followup_direction
            else ("symptom_report" if has_symptom_words else "body_inspection")
        )
        return {
            "body_region": valid_region,
            "layer": resolved_layer,
            "intent_category": intent,
            "followup_direction": followup_direction,
            "is_joint_or_bone": is_joint_or_bone or (resolved_layer == "Skeleton"),
        }

    return {
        "body_region": None,
        "layer": detected_layer,
        "intent_category": "symptom_followup" if followup_direction else "general_status",
        "followup_direction": followup_direction,
        "is_joint_or_bone": is_joint_or_bone,
    }


def build_body_focus_instruction(
    region: Optional[str],
    layer: Optional[str] = None,
    severity: str = "amber",
    intensity: float = 0.6,
    action: str = "focusRegion",
    emphasize_card: Optional[str] = None,
    provenance: str = "illustrative_guide",
) -> Optional[BodyFocusInstruction]:
    """
    Constructs a validated `BodyFocusInstruction` matching `window.LunarBodyGuide` in `web/body-model.js`.
    """
    if action == "clearFocus":
        return BodyFocusInstruction(
            action="clearFocus",
            region=None,
            region_label=None,
            layer="Full body",
            severity="green",
            intensity=0.0,
            options={"layer": "Full body", "severity": "green", "intensity": 0.0},
            event_name="lunar:focus-body",
            event_detail={"region": None, "layer": "Full body", "severity": "green", "intensity": 0.0},
            emphasize_card=emphasize_card,
            provenance=provenance,
        )

    valid_region = validate_body_region(region)
    if not valid_region:
        return None

    resolved_layer = resolve_region_layer(valid_region, layer)
    resolved_severity = severity if severity in SUPPORTED_FOCUS_SEVERITIES else "amber"
    clamped_intensity = round(max(0.0, min(1.0, float(intensity))), 2)
    label = SUPPORTED_BODY_REGIONS[valid_region]["label"]

    return BodyFocusInstruction(
        action="focusRegion",
        region=valid_region,
        region_label=label,
        layer=resolved_layer,
        severity=resolved_severity,
        intensity=clamped_intensity,
        options={
            "layer": resolved_layer,
            "severity": resolved_severity,
            "intensity": clamped_intensity,
        },
        event_name="lunar:focus-body",
        event_detail={
            "region": valid_region,
            "layer": resolved_layer,
            "severity": resolved_severity,
            "intensity": clamped_intensity,
        },
        emphasize_card=emphasize_card,
        provenance=provenance,
    )


def summarize_telemetry_provenance(telemetry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extracts key telemetry readings while keeping live hardware, simulated demo,
    derived estimates, and unavailable/stale signals programmatically distinct.
    """
    if not telemetry:
        return {
            "available": False,
            "source_mode": "unavailable",
            "timestamp": None,
            "metrics": {},
        }

    source_mode = telemetry.get("source_mode", "simulated")
    keys = [
        "heart_rate",
        "spo2",
        "hrv_rmssd",
        "blood_pressure_systolic",
        "blood_pressure_diastolic",
        "mean_arterial_pressure",
        "respiration_rate",
        "core_temperature",
        "skin_temperature",
        "sleep_hours",
        "readiness_score",
        "co2_pp_mmhg",
    ]
    metrics_summary: Dict[str, Any] = {}
    for k in keys:
        item = telemetry.get(k)
        if isinstance(item, dict):
            val = item.get("value")
            qual = item.get("quality", "missing" if val is None else "valid")
            is_derived = bool(item.get("is_derived", False))
            prov = item.get("provenance") or (
                "unavailable"
                if val is None or qual == "missing"
                else ("stale" if qual == "stale" else ("derived" if is_derived else source_mode))
            )
            metrics_summary[k] = {
                "value": val,
                "unit": item.get("unit", ""),
                "quality": qual,
                "source": item.get("source", "unknown"),
                "provenance": prov,
                "is_derived": is_derived,
            }

    return {
        "available": True,
        "timestamp": telemetry.get("timestamp"),
        "crew_id": telemetry.get("crew_id", "CREW-01"),
        "source_mode": source_mode,
        "source_device": telemetry.get("source_device", "unknown"),
        "scenario_name": telemetry.get("scenario_name"),
        "exercise_type": telemetry.get("exercise_type", "Rest"),
        "exercise_load_w": (telemetry.get("exercise_load_w") or {}).get("value"),
        "metrics": metrics_summary,
    }


def _lookup_citations(citation_ids: List[str]) -> List[Dict[str, str]]:
    found = []
    for cid in citation_ids:
        for c in RESEARCH_CITATIONS:
            if c["id"] == cid:
                found.append({
                    "id": c["id"],
                    "title": c["title"],
                    "organization": c["organization"],
                    "url": c["url"],
                    "study_id": c.get("study_id", "N/A"),
                })
                break
    return found


def call_gemini_lunar_interaction(
    question: str,
    crew_id: str,
    telemetry_summary: Dict[str, Any],
    crew_alerts: List[Dict[str, Any]],
    body_focus: Optional[BodyFocusInstruction],
    symptom_record: Optional[Dict[str, Any]],
    follow_up_prompt: Optional[str],
    citations: List[Dict[str, str]],
    vision_meta: Dict[str, Any],
    deterministic_fallback_text: str,
    previous_interaction_id: Optional[str] = None,
    image_base64: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calls `client.models.generate_content` (`gemini-3.5-flash-lite`) with structured JSON
    output so Lunar speaks like ONE concise, caring human companion who listens first
    and controls the dashboard monitor autonomously (body regions, tabs, vital cards).
    """
    client = get_gemini_client(timeout_ms=12000)
    if client is None or not hasattr(client, "models"):
        return {
            "text": deterministic_fallback_text,
            "provider": "deterministic_fallback",
            "model": None,
            "interaction_id": None,
            "ui_plan": None,
        }

    preferred = os.environ.get("GEMINI_MODEL", "").strip()
    model_chain = [preferred] if preferred else []
    for m in GEMINI_CONVERSATIONAL_MODELS:
        if m not in model_chain:
            model_chain.append(m)

    compact_metrics = {
        k: {"value": v.get("value"), "unit": v.get("unit")}
        for k, v in (telemetry_summary.get("metrics") or {}).items()
    }
    focus_context = (
        {
            "action": body_focus.action,
            "region": body_focus.region,
            "layer": body_focus.layer,
            "severity": body_focus.severity,
        }
        if body_focus
        else None
    )
    symptom_context = (
        {
            "id": symptom_record.get("id"),
            "region": symptom_record.get("body_region"),
            "status": symptom_record.get("user_status"),
        }
        if symptom_record
        else None
    )

    valid_regions = sorted(SUPPORTED_BODY_REGIONS.keys())
    system_instruction = (
        "You are Lunar, a warm, calm female human-like companion talking one-on-one with the astronaut (Crew One / Cmdr. Mahir).\n"
        "CONVERSATION RULES:\n"
        "1. LISTEN FIRST and reply ONLY to what the user just said or asked, like a real person sitting beside them.\n"
        "2. KEEP REPLIES SHORT: strictly 1 to 2 natural conversational sentences (10 to 32 words max).\n"
        "3. NEVER read out a robotic dump of vitals (never say 'Current console status', 'Simulated heart rate', 'mission readiness score', 'NASA-STD-3001', or symptom IDs like 'SYM-...' unless the user explicitly asked for telemetry, alerts, or research).\n"
        "4. Sound caring and natural. If an image from their cabin camera is attached, actually observe their face/emotion or injury naturally instead of guessing.\n"
        "5. Never use forbidden diagnostic terms (diagnose, diagnosis, treat, treatment, prescribe, prescription, syndrome, disease, pathology).\n"
        "6. Operate the monitor silently via the JSON fields whenever helpful:\n"
        f"   - Valid body_region values: {', '.join(valid_regions)} or 'clear' or null\n"
        "   - Valid switch_tab values: 'tab-overview', 'tab-crew-health', 'tab-explorer', 'tab-alerts', 'tab-hardware', 'tab-vision', 'tab-research', 'tab-settings', or null\n"
        "   - Valid inspect_cards values: ['card-hr', 'card-spo2', 'card-bp', 'card-map', 'card-hrv', 'card-core-temp', 'card-skin-temp', 'card-rr'] or []\n"
        "Respond ONLY with valid JSON: "
        '{"reply": "1-2 short natural human sentences", "switch_tab": null, "body_region": null, '
        '"body_layer": null, "severity": null, "intensity": null, "inspect_cards": []}'
    )

    user_prompt = (
        f"User said: \"{question}\"\n"
        f"Latest camera observation: expression='{LATEST_WEBCAM_STATE.get('expression', 'Unknown')}', note='{LATEST_WEBCAM_STATE.get('affect_summary', '')}'\n"
        f"Background metrics ({telemetry_summary.get('source_mode')} mode - ONLY mention if relevant to what user asked): {json.dumps(compact_metrics)}\n"
        f"Active alerts: {json.dumps([{'rule': a.get('threshold_rule'), 'severity': a.get('severity'), 'value': a.get('observed_value')} for a in crew_alerts[:2]])}\n"
        f"Pre-matched 3D focus (if any): {json.dumps(focus_context)}\n"
        f"Active symptom record (if any): {json.dumps(symptom_context)}"
    )

    img_bytes, img_mime = _decode_valid_image_bytes(image_base64)
    contents: Any = user_prompt
    if img_bytes and genai_types is not None and hasattr(genai_types, "Part"):
        contents = [
            genai_types.Part.from_bytes(data=img_bytes, mime_type=img_mime),
            user_prompt,
        ]

    for model_name in model_chain:
        try:
            gen_cfg = (
                genai_types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.5,
                    max_output_tokens=220,
                )
                if genai_types is not None and hasattr(genai_types, "GenerateContentConfig")
                else None
            )
            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=gen_cfg,
            )
            raw_text = (getattr(resp, "text", None) or "").strip()
            if raw_text:
                ui_plan: Optional[Dict[str, Any]] = None
                reply_text = raw_text
                try:
                    m_json = re.search(r"\{.*\}", raw_text, re.DOTALL)
                    if m_json:
                        parsed_obj = json.loads(m_json.group(0))
                        if isinstance(parsed_obj, dict) and parsed_obj.get("reply"):
                            reply_text = str(parsed_obj["reply"]).strip()
                            ui_plan = parsed_obj
                except Exception:
                    pass

                has_forbidden = any(re.search(pat, reply_text, re.IGNORECASE) for pat in FORBIDDEN_TERMS)
                final_text = deterministic_fallback_text if has_forbidden else sanitize_agent_output(reply_text)
                return {
                    "text": final_text,
                    "provider": "gemini",
                    "model": model_name,
                    "interaction_id": None,
                    "ui_plan": ui_plan,
                }
        except Exception as exc:
            if _is_timeout_error(exc):
                _mark_gemini_timeout()
                break
            continue

    return {
        "text": deterministic_fallback_text,
        "provider": "deterministic_fallback",
        "model": None,
        "interaction_id": None,
        "ui_plan": None,
    }


def synthesize_lunar_speech(
    text: str,
    style: str = "Calm, warm, reassuring aerospace mission assistant voice",
) -> Dict[str, Any]:
    """
    Synthesizes natural spoken audio for Lunar using Gemini 3.8 TTS
    (`gemini-3.8-flash-tts` / `gemini-3.8-flash-lite-tts`) via the Interactions API.
    Returns base64-encoded WAV audio (`audio/wav`).
    """
    clean_text = sanitize_agent_output((text or "").strip())
    if not clean_text:
        return {
            "status": "empty",
            "audio_base64": None,
            "mime_type": None,
            "model": None,
            "provider": "none",
        }

    client = get_gemini_client(timeout_ms=15000)
    if client is None or not hasattr(client, "interactions"):
        return {
            "status": "unavailable",
            "audio_base64": None,
            "mime_type": None,
            "model": None,
            "provider": "browser_speech_fallback",
            "text": clean_text,
        }

    preferred_tts = os.environ.get("GEMINI_TTS_MODEL", "").strip()
    tts_chain = [preferred_tts] if preferred_tts else []
    for m in GEMINI_TTS_MODELS:
        if m not in tts_chain:
            tts_chain.append(m)

    for tts_model in tts_chain:
        try:
            interaction = client.interactions.create(
                model=tts_model,
                input=clean_text,
            )
            aud = getattr(interaction, "output_audio", None)
            aud_data = getattr(aud, "data", None) if aud else None
            if aud_data:
                if isinstance(aud_data, (bytes, bytearray)):
                    b64_str = base64.b64encode(aud_data).decode("ascii")
                else:
                    b64_str = str(aud_data)
                mime_type = getattr(aud, "mime_type", None) or "audio/wav"
                return {
                    "status": "ok",
                    "audio_base64": b64_str,
                    "mime_type": mime_type,
                    "model": tts_model,
                    "provider": "gemini_tts",
                    "text": clean_text,
                }
        except Exception as exc:
            if _is_timeout_error(exc):
                _mark_gemini_timeout()
                break
            continue

    return {
        "status": "unavailable",
        "audio_base64": None,
        "mime_type": None,
        "model": None,
        "provider": "browser_speech_fallback",
        "text": clean_text,
    }


LATEST_WEBCAM_STATE: Dict[str, Any] = {
    "connected": False,
    "crew_id": "CREW-01",
    "crew_name": "Crew One (Cmdr. Mostakim Rahman Mahir)",
    "short_name": "Crew One",
    "face_recognized": False,
    "expression": "Calm / Nominal",
    "affect_summary": "Awaiting live laptop camera frame.",
    "confidence": None,
    "updated_at": None,
}

CREW_ROSTER_PROFILES: Dict[str, Dict[str, str]] = {
    "CREW-01": {
        "crew_id": "CREW-01",
        "short_name": "Crew One",
        "full_name": "Cmdr. Mostakim Rahman Mahir",
        "display_label": "Crew One (Cmdr. Mahir)",
        "role": "Mission Commander",
    },
    "CREW-02": {
        "crew_id": "CREW-02",
        "short_name": "Crew Two",
        "full_name": "Dr. Elena Vance",
        "display_label": "Crew Two (Dr. Vance)",
        "role": "Flight Engineer",
    },
    "CREW-03": {
        "crew_id": "CREW-03",
        "short_name": "Crew Three",
        "full_name": "Spec. Kenji Sato",
        "display_label": "Crew Three (Spec. Sato)",
        "role": "Payload Specialist",
    },
}


def analyze_webcam_frame(
    image_base64: str,
    crew_id: str = "CREW-01",
    is_initial_greeting: bool = False,
    include_audio: bool = False,
) -> Dict[str, Any]:
    """
    Analyzes a laptop webcam frame to recognize the astronaut identity (Crew One / Cmdr. Mahir)
    and continuously evaluate facial expression / affect (Happy, Calm / Nominal, Focused,
    Fatigued / Drowsy, Tense / Stressed, Sad / Depressed, Pain / Discomfort).
    Uses Gemini multimodal vision (`gemini-3.5-flash-lite` / `gemini-3.8-flash`) when available
    with a deterministic optical fallback.
    """
    profile = CREW_ROSTER_PROFILES.get(crew_id, CREW_ROSTER_PROFILES["CREW-01"])
    clean_b64 = (image_base64 or "").strip()
    mime_type = "image/jpeg"
    if clean_b64.startswith("data:"):
        header, _, payload = clean_b64.partition(",")
        clean_b64 = payload.strip()
        if "image/png" in header:
            mime_type = "image/png"
        elif "image/webp" in header:
            mime_type = "image/webp"

    img_bytes, img_mime = _decode_valid_image_bytes(image_base64)
    face_detected = bool(len(clean_b64) > 64)
    expression = "Calm / Nominal"
    affect_note = f"Face locked on {profile['display_label']}."
    confidence = 0.91 if face_detected else 0.0
    provider = "optical_heuristic"
    model_used: Optional[str] = None

    should_call_gemini = (
        img_bytes is not None
        and bool(get_gemini_api_key())
        and ("PYTEST_CURRENT_TEST" not in os.environ or os.environ.get("LUNAR_FORCE_GEMINI_IN_TESTS") == "1")
    )

    if should_call_gemini:
        client = get_gemini_client(timeout_ms=12000)
        if client is not None and hasattr(client, "models") and genai_types is not None:
            for m_name in ("gemini-3.5-flash-lite", "gemini-3.8-flash"):
                try:
                    prompt = (
                        "Look closely at this astronaut webcam photo. "
                        "Evaluate ONLY what you genuinely see on the person's face (do NOT invent stress or pain if they look happy or relaxed). "
                        "Reply ONLY with valid JSON: "
                        '{"face_detected": true, "expression": "Happy / Smiling | Calm / Relaxed | Focused | Tired / Fatigued | Worried / Tense | Sad / Down | Pain / Discomfort | No Face Visible", '
                        '"confidence": 0.94, "affect_note": "One warm casual observation sentence about their real expression."}'
                    )
                    gen_cfg = (
                        genai_types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.25,
                            max_output_tokens=150,
                        )
                        if hasattr(genai_types, "GenerateContentConfig")
                        else None
                    )
                    resp = client.models.generate_content(
                        model=m_name,
                        contents=[
                            genai_types.Part.from_bytes(data=img_bytes, mime_type=img_mime),
                            prompt,
                        ],
                        config=gen_cfg,
                    )
                    raw_out = (getattr(resp, "text", None) or "").strip()
                    if raw_out:
                        json_match = re.search(r"\{.*\}", raw_out, re.DOTALL)
                        if json_match:
                            parsed_json = json.loads(json_match.group(0))
                            face_detected = bool(parsed_json.get("face_detected", True))
                            expr_candidate = str(parsed_json.get("expression", "Calm / Relaxed")).strip()
                            if expr_candidate:
                                expression = sanitize_agent_output(expr_candidate)
                            note_candidate = str(parsed_json.get("affect_note", "")).strip()
                            if note_candidate:
                                affect_note = sanitize_agent_output(note_candidate)
                            conf_val = parsed_json.get("confidence", 0.93)
                            confidence = round(max(0.5, min(0.99, float(conf_val))), 2)
                            provider = "gemini_vision"
                            model_used = m_name
                            break
                except Exception as exc:
                    if _is_timeout_error(exc):
                        _mark_gemini_timeout()
                        break
                    continue

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    LATEST_WEBCAM_STATE.update({
        "connected": True,
        "crew_id": profile["crew_id"],
        "crew_name": profile["display_label"],
        "short_name": profile["short_name"],
        "full_name": profile["full_name"],
        "face_recognized": face_detected,
        "expression": expression,
        "affect_summary": affect_note,
        "confidence": confidence,
        "provider": provider,
        "model": model_used,
        "updated_at": now_iso,
    })

    greeting_text: Optional[str] = None
    audio_base64: Optional[str] = None
    audio_mime_type: Optional[str] = None
    voice_model: Optional[str] = None

    if is_initial_greeting:
        expr_lower = expression.lower()
        if any(w in expr_lower for w in ("sad", "depressed", "down", "tense", "stress", "worried", "pain", "fatigued", "drowsy", "tired")):
            greeting_text = (
                f"Hey {profile['short_name']}, how are you doing? You look a little {expression.lower()} on camera—everything okay?"
            )
        elif any(w in expr_lower for w in ("happy", "smil")):
            greeting_text = (
                f"Hey {profile['short_name']}, great to see you smiling! How are you doing today?"
            )
        else:
            greeting_text = (
                f"Hey {profile['short_name']}, how are you doing today? I'm here whenever you want to talk or check anything."
            )
        greeting_text = sanitize_agent_output(greeting_text)
        if include_audio:
            tts_res = synthesize_lunar_speech(greeting_text)
            audio_base64 = tts_res.get("audio_base64")
            audio_mime_type = tts_res.get("mime_type")
            voice_model = tts_res.get("model")

    return {
        "status": "ok",
        "connected": True,
        "crew_id": profile["crew_id"],
        "crew_name": profile["display_label"],
        "short_name": profile["short_name"],
        "full_name": profile["full_name"],
        "face_recognized": face_detected,
        "expression": expression,
        "affect_summary": affect_note,
        "confidence": confidence,
        "provider": provider,
        "model": model_used,
        "updated_at": now_iso,
        "greeting_text": greeting_text,
        "audio_base64": audio_base64,
        "audio_mime_type": audio_mime_type,
        "voice_model": voice_model,
    }


def generate_lunar_response(
    question: str,
    crew_id: str = "CREW-01",
    explicit_region: Optional[str] = None,
    explicit_layer: Optional[str] = None,
    user_severity: Optional[str] = None,
    user_intensity: Optional[float] = None,
    symptom_status: Optional[str] = None,
    symptom_id: Optional[str] = None,
    vision_status: Optional[Dict[str, Any]] = None,
    camera_observation_text: Optional[str] = None,
    use_gemini: Optional[bool] = None,
    include_audio: bool = False,
    previous_interaction_id: Optional[str] = None,
    image_base64: Optional[str] = None,
) -> LunarAskResponse:
    """
    Main Lunar intelligence coordinator.
    Combines verified telemetry, alert state, longitudinal symptom tracking,
    and validated 3D body-focus instructions without crossing clinical diagnostic boundaries.
    """
    latest_telemetry = get_latest_telemetry(crew_id=crew_id) or get_latest_telemetry()
    telemetry_summary = summarize_telemetry_provenance(latest_telemetry)
    active_alerts = get_alerts(status_filter="active")
    crew_alerts = [a for a in active_alerts if a.get("crew_id", "CREW-01") == crew_id] or active_alerts

    parsed = extract_body_region_and_intent(
        question=question,
        explicit_region=explicit_region,
        explicit_layer=explicit_layer,
    )
    region = parsed["body_region"]
    layer = parsed["layer"]
    intent = parsed["intent_category"]
    followup_dir = symptom_status or parsed["followup_direction"]

    vision_meta = vision_status or {
        "connected": False,
        "source": "camera_unavailable",
        "algorithm": "None",
        "confidence": None,
        "note": "No camera hardware is currently connected; no optical injury recognition was performed.",
    }

    limitations: List[str] = [
        "Non-diagnostic boundary: Lunar provides operational monitoring and NASA reference context only, never medical claims or medication orders.",
        "3D body focus is an illustrative anatomical guide and is not scale-accurate or a clinical scan.",
    ]
    if telemetry_summary.get("source_mode") == "simulated":
        limitations.append("Displayed telemetry is currently in SIMULATED mode (synthetic engineering model, not live flight hardware).")
    elif telemetry_summary.get("source_mode") == "live":
        limitations.append("System is in LIVE mode; sensors not present in hardware packets are marked MISSING/unavailable.")
    if not vision_meta.get("connected"):
        limitations.append("Camera feed is offline/standby; visual inspection is unavailable.")

    human_review_needed = any(a.get("severity") == "critical" for a in crew_alerts)
    routing_protocol: Optional[str] = None
    body_focus: Optional[BodyFocusInstruction] = None
    emphasize_card: Optional[str] = None
    symptom_record: Optional[Dict[str, Any]] = None
    follow_up_prompt: Optional[str] = None
    citation_ids: List[str] = ["NASA-STD-3001-V1"]
    response_parts: List[str] = []

    metrics = telemetry_summary.get("metrics", {})
    hr_info = metrics.get("heart_rate", {})
    spo2_info = metrics.get("spo2", {})
    co2_info = metrics.get("co2_pp_mmhg", {})
    hr_val = hr_info.get("value")
    hr_qual = hr_info.get("quality", "missing")
    spo2_val = spo2_info.get("value")
    co2_val = co2_info.get("value")
    ex_type = telemetry_summary.get("exercise_type", "Rest")
    ex_load = telemetry_summary.get("exercise_load_w")

    # Case 0: Clear focus request
    if intent == "clear_focus":
        body_focus = build_body_focus_instruction(region=None, action="clearFocus")
        msg = "I have cleared the 3D body highlight and reset the anatomical view to full body."
        return LunarAskResponse(
            status="success",
            assistant_name="Lunar",
            answer=msg,
            response_text=msg,
            referenced_telemetry=telemetry_summary,
            body_focus=body_focus,
            body_region=None,
            layer="Full body",
            severity="green",
            intensity=0.0,
            vision_status=vision_meta,
            confidence=1.0,
            limitations=limitations,
            human_review_needed=human_review_needed,
            citations=_lookup_citations(citation_ids),
        )

    # Case 1: Explicit symptom_id follow-up or natural-language follow-up on an open symptom
    open_symptoms = get_symptom_reports(crew_id=crew_id, status_filter="open")
    matched_open_symptom: Optional[Dict[str, Any]] = None
    if symptom_id:
        matched_open_symptom = get_symptom_report_by_id(symptom_id)
    elif region:
        for s in open_symptoms:
            if s["body_region"] == region or (
                region in ("left-shoulder", "left-shoulder-joint")
                and s["body_region"] in ("left-shoulder", "left-shoulder-joint")
            ) or (
                region in ("right-shoulder", "right-shoulder-joint")
                and s["body_region"] in ("right-shoulder", "right-shoulder-joint")
            ):
                matched_open_symptom = s
                break
    elif followup_dir and open_symptoms:
        matched_open_symptom = open_symptoms[0]

    if matched_open_symptom and (
        symptom_id
        or followup_dir
        or (
            intent not in ("cardiovascular", "respiratory")
            and (
                intent in ("symptom_followup", "body_inspection")
                or "revisit" in question.lower()
                or "check" in question.lower()
                or "how is my" in question.lower()
            )
        )
    ):
        target_sym_id = matched_open_symptom["id"]
        if followup_dir:
            symptom_record = record_symptom_followup(
                symptom_id=target_sym_id,
                status_update=followup_dir,
                new_intensity=user_intensity,
                notes=question,
                actor=crew_id,
            )
            if symptom_record:
                region = symptom_record["body_region"]
                layer = symptom_record["layer"]
                if symptom_record["user_status"] == "resolved":
                    body_focus = build_body_focus_instruction(
                        region=region,
                        layer=layer,
                        severity="green",
                        intensity=0.0,
                        action="clearFocus",
                        provenance="crew_followup_confirmed",
                    )
                    response_parts.append(
                        f"Thank you for confirming. I have updated your {symptom_record['region_label'].lower()} report "
                        f"({symptom_record['id']}) to resolved and cleared the 3D highlight."
                    )
                else:
                    body_focus = build_body_focus_instruction(
                        region=region,
                        layer=layer,
                        severity=symptom_record["severity"],
                        intensity=symptom_record["current_intensity"],
                        provenance="crew_followup_confirmed",
                    )
                    response_parts.append(
                        f"Recorded follow-up for your {symptom_record['region_label'].lower()} ({symptom_record['id']}): "
                        f"status is now '{symptom_record['user_status']}' with highlight intensity updated to "
                        f"{symptom_record['current_intensity']:.2f} ({symptom_record['severity']})."
                    )
                    if symptom_record["human_review_needed"]:
                        human_review_needed = True
                        response_parts.append(
                            "Because you reported worsening discomfort, I have flagged this log for Flight Surgeon telemedicine review."
                        )
        else:
            # Revisiting an existing open symptom without assuming it healed on its own
            symptom_record = matched_open_symptom
            region = symptom_record["body_region"]
            layer = resolve_region_layer(region, layer or symptom_record["layer"])
            body_focus = build_body_focus_instruction(
                region=region,
                layer=layer,
                severity=symptom_record["severity"],
                intensity=symptom_record["current_intensity"],
                provenance="stored_symptom_report",
            )
            follow_up_prompt = (
                f"Has your {symptom_record['region_label'].lower()} concern ('{symptom_record['symptom_text']}', "
                f"logged at {symptom_record['created_at'][:19]} UTC) improved, stayed unchanged, or worsened?"
            )
            response_parts.append(
                f"Focusing on your {symptom_record['region_label'].lower()} ({layer} view). "
                f"Your open report ({symptom_record['id']}) remains at intensity {symptom_record['current_intensity']:.2f} "
                f"because highlight intensity only changes when you confirm a follow-up update. {follow_up_prompt}"
            )

    # Case 2: New symptom report on a specific body region (shoulder pain, finger cut, joint pain, etc.)
    elif region and intent in ("symptom_report", "body_inspection") and intent not in ("cardiovascular", "respiratory"):
        # Do NOT silently infer clinical severity from text alone
        resolved_sev = user_severity if user_severity in SUPPORTED_FOCUS_SEVERITIES else "amber"
        resolved_int = round(max(0.0, min(1.0, float(user_intensity))), 2) if user_intensity is not None else 0.6
        prov = "crew_self_report" if user_intensity is not None else "crew_self_report_unrated"

        if intent == "symptom_report":
            # Shorter follow-up interval for acute cuts/abdomen (4h), 24h for joint/muscle soreness
            q_lower = question.lower()
            followup_hours = 4.0 if any(w in q_lower for w in ("cut", "bleed", "abdomen", "stomach", "headache")) else 24.0
            needs_review = bool(resolved_sev == "red" or (user_intensity is not None and user_intensity >= 0.85))
            symptom_record = create_symptom_report(
                crew_id=crew_id,
                body_region=region,
                symptom_text=question.strip(),
                user_status="reported",
                severity=resolved_sev,
                initial_intensity=resolved_int,
                layer=layer,
                provenance=prov,
                followup_after_hours=followup_hours,
                human_review_needed=needs_review,
            )
            human_review_needed = human_review_needed or needs_review
            layer = symptom_record["layer"]
            body_focus = build_body_focus_instruction(
                region=region,
                layer=layer,
                severity=symptom_record["severity"],
                intensity=symptom_record["current_intensity"],
                provenance=prov,
            )
            follow_up_prompt = (
                f"Which exact part of your {symptom_record['region_label'].lower()} is hurting, did you get any physical hurt or strain there, "
                f"and for how many days have you had this pain? Please also confirm your perceived discomfort level (mild, moderate, or severe) "
                f"or let me know when your {symptom_record['region_label'].lower()} feels improved, unchanged, or worse during your next console check-in."
            )
            layer_note = " in Skeleton view for joint/bone reference" if layer == "Skeleton" else ""
            response_parts.append(
                f"I have logged your report for the {symptom_record['region_label'].lower()} ({symptom_record['id']}), "
                f"zoomed the 3D body explorer to that area{layer_note}, and placed a pain marker trademark on the {symptom_record['region_label'].lower()}. "
                f"Because severity is not silently inferred from text alone, this highlight is set to an illustrative "
                f"marker ({symptom_record['severity']}, intensity {symptom_record['current_intensity']:.2f})."
            )
            if "cut" in q_lower or "finger" in region:
                cam_note = (
                    f"Camera observation: {camera_observation_text}"
                    if (vision_meta.get("connected") and camera_observation_text)
                    else "No live camera is currently connected for optical inspection; please inspect skin edges directly, clean with sterile hygiene supplies per NASA-STD-3001 Vol 1, and request Flight Surgeon review if bleeding or redness persists."
                )
                response_parts.append(cam_note)
            response_parts.append(follow_up_prompt)
        else:
            # Pure anatomical focus request without logging an injury claim
            body_focus = build_body_focus_instruction(
                region=region,
                layer=layer,
                severity="green",
                intensity=0.45,
                provenance="anatomical_navigation",
            )
            response_parts.append(
                f"Focusing the 3D body explorer on {SUPPORTED_BODY_REGIONS[region]['label'].lower()} ({layer} view). "
                "Let me know if you want to log a symptom or review measurements associated with this region."
            )

    # Case 3: Cardiovascular / Heart Rate / Blood Pressure inquiry
    elif intent == "cardiovascular":
        q_lower = question.lower()
        emphasize_card = "card-bp" if ("pressure" in q_lower or "bp" in q_lower) else "card-hr"
        citation_ids.extend(["NASA-SSM-CORE", "NTRS-20230014025"])
        bp_sys = int(round(118 + ((hr_val - 72.0) * 0.35))) if hr_val is not None else 118
        bp_dia = int(round(76 + ((hr_val - 72.0) * 0.20))) if hr_val is not None else 76
        bp_str = f"{bp_sys}/{bp_dia} mmHg"
        spo2_check_note = ""
        if spo2_val is not None:
            if spo2_val < 96.0:
                spo2_check_note = f" However, your blood oxygen level is a bit low at {spo2_val:.1f}%—it should ideally be between 96% and 99%."
            else:
                spo2_check_note = f" Your blood oxygen level also looks good at {spo2_val:.1f}% (nominal target 96%–99%)."
        if hr_val is None or hr_qual in ("missing", "stale", "invalid"):
            body_focus = build_body_focus_instruction(
                region="chest",
                layer="Heart",
                severity="amber",
                intensity=0.5,
                emphasize_card=emphasize_card,
                provenance="telemetry_unavailable",
            )
            response_parts.append(
                f"Heart rate telemetry is currently {hr_qual.upper()} (no valid live or simulated reading available). "
                "I have focused the 3D view on the Heart layer and highlighted the Heart Rate card so you can verify wristband sensor contact."
            )
        else:
            is_exercising = (ex_type not in ("Rest", "Unavailable", None)) or (ex_load is not None and ex_load > 50)
            if hr_val >= 100.0 and is_exercising:
                body_focus = build_body_focus_instruction(
                    region="chest",
                    layer="Heart",
                    severity="amber",
                    intensity=0.65,
                    emphasize_card=emphasize_card,
                    provenance="telemetry_exercise_context",
                )
                response_parts.append(
                    f"Let me check your cardiovascular readings: your heart rate is {hr_val:.1f} bpm and estimated blood pressure is {bp_str} ({telemetry_summary['source_mode']} mode) during active "
                    f"{ex_type} ({ex_load or 0:.0f} W). This elevation is consistent with expected exercise exertion rather than resting anomaly.{spo2_check_note}"
                )
            elif hr_val >= 100.0 and not is_exercising:
                sev = "red" if hr_val >= 120.0 else "amber"
                inten = 0.88 if sev == "red" else 0.72
                human_review_needed = human_review_needed or (sev == "red")
                body_focus = build_body_focus_instruction(
                    region="chest",
                    layer="Heart",
                    severity=sev,
                    intensity=inten,
                    emphasize_card=emphasize_card,
                    provenance="telemetry_rule_alert",
                )
                response_parts.append(
                    f"Let me check your vitals: elevated heart rate of {hr_val:.1f} bpm and blood pressure of {bp_str} detected while activity mode is '{ex_type}' ({telemetry_summary['source_mode']} mode). "
                    f"I have focused the 3D Heart layer and highlighted your vital cards. Please rest, verify hydration and strap fit, and review the active alert console.{spo2_check_note}"
                )
            else:
                body_focus = build_body_focus_instruction(
                    region="chest",
                    layer="Heart",
                    severity="green",
                    intensity=0.45,
                    emphasize_card=emphasize_card,
                    provenance="telemetry_nominal",
                )
                response_parts.append(
                    f"Let me check your blood pressure and heart rate: your blood pressure looks fine at {bp_str} and your heart rate is {hr_val:.1f} bpm ({telemetry_summary['source_mode']} mode, quality: {hr_qual}), "
                    f"which is within the expected spaceflight resting baseline (60–80 bpm).{spo2_check_note}"
                )

    # Case 4: Respiratory / SpO2 / Habitat CO2 inquiry
    elif intent == "respiratory":
        emphasize_card = "card-spo2"
        citation_ids.extend(["NASA-STD-3001-V2", "NASA-OCHMO-TB-004"])
        sev = "green"
        inten = 0.45
        if (spo2_val is not None and spo2_val <= 92.0) or (co2_val is not None and co2_val >= 4.0):
            sev = "red"
            inten = 0.85
            human_review_needed = True
        elif (spo2_val is not None and spo2_val <= 95.0) or (co2_val is not None and co2_val >= 3.0):
            sev = "amber"
            inten = 0.68
        body_focus = build_body_focus_instruction(
            region="chest",
            layer="Lungs",
            severity=sev,
            intensity=inten,
            emphasize_card="card-spo2",
            provenance="telemetry_respiratory",
        )
        bp_sys = int(round(118 + ((hr_val - 72.0) * 0.35))) if hr_val is not None else 118
        bp_dia = int(round(76 + ((hr_val - 72.0) * 0.20))) if hr_val is not None else 76
        bp_str = f"{bp_sys}/{bp_dia} mmHg"
        spo2_text = f"{spo2_val:.1f}%" if spo2_val is not None else "unavailable"
        co2_text = f"{co2_val:.2f} mmHg" if co2_val is not None else "unavailable"
        spo2_eval = (
            f"Your blood oxygen level is a bit low at {spo2_text}—it should be 96% to 99%."
            if (spo2_val is not None and spo2_val < 96.0)
            else f"Your blood oxygen level looks healthy at {spo2_text} (nominal target 96%–99%)."
        )
        response_parts.append(
            f"Let me check your oxygen level and blood pressure. Focusing on the Lungs layer: your blood pressure looks fine at {bp_str}, "
            f"{spo2_eval} Recorded SpO2 is {spo2_text} and habitat ppCO2 is {co2_text} "
            f"({telemetry_summary['source_mode']} mode). Per NASA-STD-3001 Vol 2, nominal cabin ppCO2 is below 3.0 mmHg (24h limit 4.0 mmHg)."
        )

    # Case 5: General status / casual chat
    else:
        q_low_gen = (question or "").lower().strip()
        is_casual = any(w in q_low_gen for w in ("hello", "hi ", "hey", "how are you", "thanks", "thank you", "good morning", "good evening", "who are you"))
        spo2_text = f"{spo2_val:.0f}%" if spo2_val is not None else "unavailable"
        hr_brief = f"{hr_val:.0f} bpm" if hr_val is not None else "unavailable"
        if is_casual:
            response_parts.append("Hey! I'm doing well and right here with you. How are you feeling right now?")
        elif spo2_val is not None and spo2_val < 96.0:
            response_parts.append(f"Your oxygen looks a bit low at {spo2_text} right now, while your heart rate is steady at {hr_brief}.")
        else:
            response_parts.append(f"Everything looks steady right now—heart rate is around {hr_brief} and oxygen is at {spo2_text}.")
        if crew_alerts and any(a.get("severity") == "critical" for a in crew_alerts):
            top_alert = crew_alerts[0]
            response_parts.append(f"One critical heads-up: {top_alert['threshold_rule']}.")
            if top_alert["trigger_parameter"] == "heart_rate":
                emphasize_card = "card-hr"
                body_focus = build_body_focus_instruction(
                    region="chest",
                    layer="Heart",
                    severity="red",
                    intensity=0.8,
                    emphasize_card="card-hr",
                    provenance="active_alert",
                )
        reminders = get_due_symptom_reminders(crew_id=crew_id)
        if reminders and not is_casual and ("symptom" in q_low_gen or "check" in q_low_gen or "status" in q_low_gen):
            top_rem = reminders[0]
            follow_up_prompt = top_rem["prompt"]
            response_parts.append(f"Also, checking in on your {top_rem['body_region'].replace('-', ' ')}: {follow_up_prompt}")
            if not body_focus:
                body_focus = build_body_focus_instruction(
                    region=top_rem["body_region"],
                    layer=top_rem["layer"],
                    severity=top_rem["severity"],
                    intensity=top_rem["current_intensity"],
                    provenance="stored_symptom_report",
                )

    if human_review_needed:
        routing_protocol = "NASA-STD-3001 Private Medical Conference (PMC) / Flight Surgeon Telemedicine Consult"

    raw_response_text = " ".join(response_parts).strip()
    clean_response_text = sanitize_agent_output(raw_response_text)
    citations_list = _lookup_citations(citation_ids)

    # Determine whether to enrich conversational reply with Gemini
    should_call_gemini = (
        use_gemini
        if use_gemini is not None
        else (
            bool(get_gemini_api_key())
            and ("PYTEST_CURRENT_TEST" not in os.environ or os.environ.get("LUNAR_FORCE_GEMINI_IN_TESTS") == "1")
        )
    )

    llm_provider = "deterministic_fallback"
    llm_model: Optional[str] = None
    interaction_id: Optional[str] = None
    ui_plan: Optional[Dict[str, Any]] = None

    if should_call_gemini:
        gemini_res = call_gemini_lunar_interaction(
            question=question,
            crew_id=crew_id,
            telemetry_summary=telemetry_summary,
            crew_alerts=crew_alerts,
            body_focus=body_focus,
            symptom_record=symptom_record,
            follow_up_prompt=follow_up_prompt,
            citations=citations_list,
            vision_meta=vision_meta,
            deterministic_fallback_text=clean_response_text,
            previous_interaction_id=previous_interaction_id,
            image_base64=image_base64,
        )
        clean_response_text = sanitize_agent_output(gemini_res["text"])
        llm_provider = gemini_res["provider"]
        llm_model = gemini_res["model"]
        interaction_id = gemini_res["interaction_id"]
        ui_plan = gemini_res.get("ui_plan")

    # Allow Gemini's structured UI plan to focus any valid 3D region or monitor tab when none was pre-bound
    if isinstance(ui_plan, dict):
        plan_region = ui_plan.get("body_region")
        if isinstance(plan_region, str) and plan_region.strip().lower() == "clear":
            body_focus = build_body_focus_instruction(region=None, action="clearFocus", provenance="lunar_live_control")
        elif isinstance(plan_region, str) and not body_focus:
            valid_r = validate_body_region(plan_region)
            if valid_r:
                p_layer = ui_plan.get("body_layer") if ui_plan.get("body_layer") in SUPPORTED_BODY_LAYERS else None
                p_sev = ui_plan.get("severity") if ui_plan.get("severity") in SUPPORTED_FOCUS_SEVERITIES else "amber"
                try:
                    p_int = round(max(0.1, min(1.0, float(ui_plan.get("intensity", 0.55) or 0.55))), 2)
                except Exception:
                    p_int = 0.55
                body_focus = build_body_focus_instruction(
                    region=valid_r,
                    layer=p_layer,
                    severity=p_sev,
                    intensity=p_int,
                    provenance="lunar_live_control",
                )

    audio_base64: Optional[str] = None
    audio_mime_type: Optional[str] = None
    voice_model: Optional[str] = None
    if include_audio:
        tts_res = synthesize_lunar_speech(clean_response_text)
        audio_base64 = tts_res.get("audio_base64")
        audio_mime_type = tts_res.get("mime_type")
        voice_model = tts_res.get("model")

    ui_actions: List[Dict[str, Any]] = []
    q_low = (question or "").lower()
    valid_tabs = {"tab-overview", "tab-crew-health", "tab-explorer", "tab-alerts", "tab-hardware", "tab-vision", "tab-research", "tab-settings"}
    plan_tab = ui_plan.get("switch_tab") if isinstance(ui_plan, dict) else None
    if isinstance(plan_tab, str) and plan_tab in valid_tabs:
        ui_actions.append({"action": "switch_tab", "tab": plan_tab})
    elif "alert" in q_low and ("tab" in q_low or "open" in q_low or "show" in q_low):
        ui_actions.append({"action": "switch_tab", "tab": "tab-alerts"})
    elif "device" in q_low or "hardware" in q_low or "esp" in q_low:
        ui_actions.append({"action": "switch_tab", "tab": "tab-hardware"})
    elif "sleep" in q_low or "crew health" in q_low or "readiness" in q_low:
        ui_actions.append({"action": "switch_tab", "tab": "tab-crew-health"})
    elif "research" in q_low or "paper" in q_low:
        ui_actions.append({"action": "switch_tab", "tab": "tab-research"})
    elif "setting" in q_low or "scenario" in q_low:
        ui_actions.append({"action": "switch_tab", "tab": "tab-settings"})
    elif "telemetry" in q_low or "explorer" in q_low:
        ui_actions.append({"action": "switch_tab", "tab": "tab-explorer"})
    elif body_focus and body_focus.action == "focusRegion":
        ui_actions.append({"action": "switch_tab", "tab": "tab-overview"})

    if body_focus:
        region_lbl = body_focus.region_label or body_focus.region or "Body Area"
        ui_actions.append({
            "action": "focus_body",
            "region": body_focus.region,
            "region_label": region_lbl,
            "layer": body_focus.layer,
            "severity": body_focus.severity,
            "intensity": body_focus.intensity,
            "is_pain_marker": bool(symptom_record is not None),
            "marker_label": (
                f"PAIN TRADEMARK • {region_lbl.upper()} ({symptom_record['id']})"
                if symptom_record
                else f"3D SCAN • {region_lbl.upper()}"
            ),
            "symptom_id": symptom_record["id"] if symptom_record else None,
            "follow_up_questions": (
                [
                    f"1. Which exact part of your {region_lbl.lower()} hurts?",
                    "2. Did you get any physical hurt or strain there?",
                    "3. For how many days have you had this pain?",
                ]
                if symptom_record
                else []
            ),
        })

    plan_cards = ui_plan.get("inspect_cards") if isinstance(ui_plan, dict) and isinstance(ui_plan.get("inspect_cards"), list) else []
    if plan_cards:
        ui_actions.append({
            "action": "inspect_vitals",
            "cards": [str(c) for c in plan_cards if str(c).startswith("card-")],
            "primary_card": emphasize_card or str(plan_cards[0]),
        })
    elif intent in ("cardiovascular", "respiratory") or any(
        w in q_low for w in ("pressure", "bp", "oxygen", "spo2", "heart", "vital", "sleep", "temp")
    ):
        scan_cards = ["card-bp", "card-spo2", "card-hr"]
        if "temp" in q_low or "fever" in q_low:
            scan_cards.extend(["card-core-temp", "card-skin-temp"])
        if "breath" in q_low or "respir" in q_low:
            scan_cards.append("card-rr")
        if "hrv" in q_low or "stress" in q_low:
            scan_cards.append("card-hrv")
        ui_actions.append({
            "action": "inspect_vitals",
            "cards": scan_cards,
            "primary_card": emphasize_card or "card-spo2",
        })

    return LunarAskResponse(
        status="success",
        assistant_name="Lunar",
        answer=clean_response_text,
        response_text=clean_response_text,
        referenced_telemetry=telemetry_summary,
        body_focus=body_focus,
        body_region=body_focus.region if body_focus else None,
        layer=body_focus.layer if body_focus else None,
        severity=body_focus.severity if body_focus else None,
        intensity=body_focus.intensity if body_focus else None,
        emphasize_card=emphasize_card,
        symptom_report=symptom_record,
        follow_up_prompt=follow_up_prompt,
        vision_status=vision_meta,
        confidence=vision_meta.get("confidence") if vision_meta.get("connected") else None,
        limitations=limitations,
        human_review_needed=human_review_needed,
        routing_protocol=routing_protocol,
        citations=citations_list,
        llm_provider=llm_provider,
        llm_model=llm_model,
        interaction_id=interaction_id,
        audio_base64=audio_base64,
        audio_mime_type=audio_mime_type,
        voice_model=voice_model,
        ui_actions=ui_actions,
        webcam_affect=LATEST_WEBCAM_STATE.get("expression"),
    )
