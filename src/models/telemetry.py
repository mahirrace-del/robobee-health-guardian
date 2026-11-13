"""
AstroHealth Guardian — Telemetry Data Models & Contracts
Standardized, typed models for astronaut biometrics, environmental metrics,
data quality indicators, and ingestion envelopes.
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class QualityFlag(str, Enum):
    VALID = "valid"
    QUESTIONABLE = "questionable"
    INVALID = "invalid"
    MISSING = "missing"
    STALE = "stale"


class SourceMode(str, Enum):
    SIMULATED = "simulated"
    LIVE = "live"
    REPLAY = "replay"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class MeasurementItem(BaseModel):
    value: Optional[float] = None
    unit: str
    quality: QualityFlag = QualityFlag.VALID
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    source: str = "synthetic_generator"
    provenance: Optional[str] = None
    is_derived: bool = False
    calculation_method: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# Supported 3D body regions and default layers matching web/body-model.js
SUPPORTED_BODY_REGIONS: Dict[str, Dict[str, str]] = {
    "head": {"label": "Head", "default_layer": "Full body"},
    "neck": {"label": "Neck", "default_layer": "Full body"},
    "left-shoulder": {"label": "Left shoulder", "default_layer": "Full body"},
    "right-shoulder": {"label": "Right shoulder", "default_layer": "Full body"},
    "left-shoulder-joint": {"label": "Left shoulder joint", "default_layer": "Skeleton"},
    "right-shoulder-joint": {"label": "Right shoulder joint", "default_layer": "Skeleton"},
    "left-elbow": {"label": "Left elbow joint", "default_layer": "Skeleton"},
    "right-elbow": {"label": "Right elbow joint", "default_layer": "Skeleton"},
    "left-forearm": {"label": "Left forearm", "default_layer": "Full body"},
    "right-forearm": {"label": "Right forearm", "default_layer": "Full body"},
    "left-hand": {"label": "Left hand", "default_layer": "Full body"},
    "right-hand": {"label": "Right hand", "default_layer": "Full body"},
    "left-finger": {"label": "Left index finger", "default_layer": "Full body"},
    "right-finger": {"label": "Right index finger", "default_layer": "Full body"},
    "chest": {"label": "Chest", "default_layer": "Full body"},
    "abdomen": {"label": "Abdomen", "default_layer": "Full body"},
    "left-hip": {"label": "Left hip", "default_layer": "Full body"},
    "right-hip": {"label": "Right hip", "default_layer": "Full body"},
    "left-thigh": {"label": "Left thigh", "default_layer": "Full body"},
    "right-thigh": {"label": "Right thigh", "default_layer": "Full body"},
    "left-knee": {"label": "Left knee joint", "default_layer": "Skeleton"},
    "right-knee": {"label": "Right knee joint", "default_layer": "Skeleton"},
    "left-lower-leg": {"label": "Left lower leg", "default_layer": "Full body"},
    "right-lower-leg": {"label": "Right lower leg", "default_layer": "Full body"},
    "left-ankle": {"label": "Left ankle joint", "default_layer": "Skeleton"},
    "right-ankle": {"label": "Right ankle joint", "default_layer": "Skeleton"},
    "left-foot": {"label": "Left foot", "default_layer": "Full body"},
    "right-foot": {"label": "Right foot", "default_layer": "Full body"},
}

SUPPORTED_BODY_LAYERS = {"Full body", "Heart", "Lungs", "Skeleton"}
SUPPORTED_FOCUS_SEVERITIES = {"red", "amber", "green"}


def validate_body_region(region: Optional[str]) -> Optional[str]:
    """Validates a region key against the frontend's supported 28-region list."""
    if not region:
        return None
    normalized = region.strip().lower()
    if normalized in SUPPORTED_BODY_REGIONS:
        return normalized
    return None


def resolve_region_layer(region: str, explicit_layer: Optional[str] = None) -> str:
    """Returns a validated layer for a body region, defaulting joint regions to Skeleton."""
    if explicit_layer and explicit_layer in SUPPORTED_BODY_LAYERS:
        return explicit_layer
    region_meta = SUPPORTED_BODY_REGIONS.get(region, {})
    return region_meta.get("default_layer", "Full body")


class TelemetryFrame(BaseModel):
    """
    Standardized telemetry frame representing a single snapshot in time
    for a monitored astronaut in habitat.
    """
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    crew_id: str = "CREW-01"
    crew_name: str = "Cmdr. Alex Vance"
    source_mode: SourceMode = SourceMode.SIMULATED
    source_device: str = "astro_simulator_v2"
    
    # Cardiovascular
    heart_rate: MeasurementItem
    spo2: MeasurementItem
    hrv_rmssd: MeasurementItem
    blood_pressure_systolic: MeasurementItem
    blood_pressure_diastolic: MeasurementItem
    mean_arterial_pressure: MeasurementItem
    
    # Respiratory & Thermal
    respiration_rate: MeasurementItem
    core_temperature: MeasurementItem
    skin_temperature: MeasurementItem
    
    # Sleep & Readiness
    sleep_hours: MeasurementItem
    sleep_efficiency: MeasurementItem
    sleep_interruptions: MeasurementItem
    reaction_time_ms: MeasurementItem
    attention_lapses: MeasurementItem
    readiness_score: MeasurementItem
    
    # Exercise & Biomechanics
    exercise_minutes: MeasurementItem
    exercise_type: str = "Rest"  # "Rest", "T2 Treadmill", "ARED Resistance"
    exercise_load_w: MeasurementItem
    exercise_posture_score: MeasurementItem
    detected_expression: str = "neutral"
    
    # Habitat & Environment
    co2_pp_mmhg: MeasurementItem
    cabin_temp_c: MeasurementItem
    cabin_humidity_pct: MeasurementItem
    radiation_dose_rate_ugy_day: MeasurementItem

    # Challenge Metabolic, Hydration, Mood & SANS Ultrasound Check-ins
    blood_glucose_mg_dl: MeasurementItem = Field(
        default_factory=lambda: MeasurementItem(
            value=94.0,
            unit="mg/dL",
            quality=QualityFlag.VALID,
            source="Simulated Metabolic Check (DEMO)",
            provenance="simulated",
        )
    )
    hydration_pct: MeasurementItem = Field(
        default_factory=lambda: MeasurementItem(
            value=84.0,
            unit="%",
            quality=QualityFlag.VALID,
            is_derived=True,
            calculation_method="Daily Fluid Intake / 2500 mL NASA Target",
            source="Derived Crew Hydration Log",
            provenance="derived",
        )
    )
    hydration_intake_ml: MeasurementItem = Field(
        default_factory=lambda: MeasurementItem(
            value=2100.0,
            unit="mL",
            quality=QualityFlag.VALID,
            source="Crew Fluid Log",
            provenance="simulated",
        )
    )
    mood_score: MeasurementItem = Field(
        default_factory=lambda: MeasurementItem(
            value=4.2,
            unit="/5",
            quality=QualityFlag.VALID,
            source="Crew Private Self-Report (Non-Camera)",
            provenance="crew_self_report",
        )
    )
    mood_label: str = "steady"
    ultrasound_last_check: str = "Nominal • Last IJV / SANS Check Clear"

    # Anomaly and Context
    context_note: Optional[str] = None
    scenario_name: str = "Scenario A: Routine Operations"


class DeviceIngestPayload(BaseModel):
    """
    Contract for ESP32 and external hardware sensor data ingestion (Schema v1.0).
    """
    schema_version: str = "1.0"
    device_id: str
    timestamp: Optional[str] = None
    sequence: int
    measurements: Dict[str, Dict[str, Any]]


class AlertRecord(BaseModel):
    """
    Managed alert record with full provenance, rules, and lifecycle tracking.
    """
    id: str
    timestamp: str
    crew_id: str
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.ACTIVE
    trigger_parameter: str
    observed_value: float
    unit: str
    threshold_rule: str
    quality_flag: QualityFlag
    explanation: str
    suggested_actions: List[str]
    literature_citation: Optional[Dict[str, str]] = None
    historical_precedent: Optional[Dict[str, Any]] = None
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None


class ResearchCitation(BaseModel):
    """
    Verified research literature reference item.
    """
    id: str
    title: str
    organization: str
    url: str
    study_id: Optional[str] = None
    publication_date: str
    summary: str
    parameters_established: List[str]
    dashboard_relevance: str
    limitations: str


class BodyFocusInstruction(BaseModel):
    """
    Structured instruction for the browser UI bridge (`window.LunarBodyGuide`
    and the `lunar:focus-body` CustomEvent).
    """
    action: str = "focusRegion"  # "focusRegion" | "clearFocus" | "none"
    region: Optional[str] = None
    region_label: Optional[str] = None
    layer: Optional[str] = None
    severity: Optional[str] = None  # "red" | "amber" | "green"
    intensity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    options: Dict[str, Any] = Field(default_factory=dict)
    event_name: str = "lunar:focus-body"
    event_detail: Dict[str, Any] = Field(default_factory=dict)
    emphasize_card: Optional[str] = None
    provenance: str = "illustrative_guide"
    is_illustrative: bool = True
    scale_disclaimer: str = (
        "Illustrative 3D anatomical focus only; not scale-accurate, not a live scan, and not a clinical diagnosis."
    )


class SymptomFollowUpEntry(BaseModel):
    """
    Single confirmed follow-up entry in a symptom's longitudinal history.
    """
    timestamp: str
    actor: str = "CREW-01"
    previous_status: str
    new_status: str
    previous_intensity: float = Field(ge=0.0, le=1.0)
    new_intensity: float = Field(ge=0.0, le=1.0)
    notes: str = ""
    provenance: str = "crew_followup_confirmed"


class SymptomReport(BaseModel):
    """
    Persisted crew symptom report with explicit provenance, follow-up history,
    and non-automatic highlight fading governed strictly by recorded follow-ups.
    """
    id: str
    created_at: str
    updated_at: str
    crew_id: str = "CREW-01"
    body_region: str
    region_label: str
    layer: str = "Full body"
    symptom_text: str
    user_status: str = "reported"  # "reported" | "improving" | "unchanged" | "worsened" | "resolved"
    severity: str = "amber"  # "red" | "amber" | "green"
    initial_intensity: float = Field(default=0.6, ge=0.0, le=1.0)
    current_intensity: float = Field(default=0.6, ge=0.0, le=1.0)
    provenance: str = "crew_self_report"
    follow_up_history: List[SymptomFollowUpEntry] = Field(default_factory=list)
    next_followup_due_at: Optional[str] = None
    reminder_delivery_channel: str = "in_console_pull"
    human_review_needed: bool = False


class LunarAskResponse(BaseModel):
    """
    Backward-compatible and structured response from the Lunar assistant.
    Preserves `status` and `answer` for existing `web/app.js` while exposing
    validated body-focus, telemetry provenance, symptom tracking, Gemini model
    provenance, optional TTS audio, and safety metadata.
    """
    status: str = "success"
    assistant_name: str = "Lunar"
    answer: str
    response_text: str
    referenced_telemetry: Dict[str, Any] = Field(default_factory=dict)
    body_focus: Optional[BodyFocusInstruction] = None
    body_region: Optional[str] = None
    layer: Optional[str] = None
    severity: Optional[str] = None
    intensity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    emphasize_card: Optional[str] = None
    symptom_report: Optional[Dict[str, Any]] = None
    follow_up_prompt: Optional[str] = None
    vision_status: Dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    limitations: List[str] = Field(default_factory=list)
    human_review_needed: bool = False
    routing_protocol: Optional[str] = None
    citations: List[Dict[str, str]] = Field(default_factory=list)
    llm_provider: str = "deterministic_fallback"
    llm_model: Optional[str] = None
    interaction_id: Optional[str] = None
    audio_base64: Optional[str] = None
    audio_mime_type: Optional[str] = None
    voice_model: Optional[str] = None
    ui_actions: List[Dict[str, Any]] = Field(default_factory=list)
    webcam_affect: Optional[str] = None
