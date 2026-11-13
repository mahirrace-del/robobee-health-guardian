"""
AstroHealth / RoboBee Health Guardian — Real-time Telemetry & API Server
FastAPI backend providing REST endpoints, SQLite persistence,
multi-client WebSocket broadcasting, rule evaluation, hardware ingestion,
symptom tracking, and Lunar assistant integration.
"""

import os
import json
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

from src.models.telemetry import (
    TelemetryFrame,
    MeasurementItem,
    QualityFlag,
    SourceMode,
    AlertRecord,
    AlertSeverity,
    AlertStatus,
    DeviceIngestPayload,
    SUPPORTED_BODY_REGIONS,
    SUPPORTED_BODY_LAYERS,
    SUPPORTED_FOCUS_SEVERITIES,
    validate_body_region,
    resolve_region_layer,
)
from src.compute.generator import TelemetryGenerator
from src.compute.rules import evaluate_telemetry_rules
from src.compute.context import evaluate_crew_context
from src.data.research import RESEARCH_CITATIONS
from src.data.incidents import (
    FIVE_HAZARDS_CATALOG,
    HISTORICAL_INCIDENTS,
    match_historical_incidents,
    get_five_hazards_status,
)
from src.data.nasa_open_apis import (
    get_nasa_live_bundle,
    set_offline_delay_mode,
    is_offline_delay_mode,
)
from src.storage.db import (
    init_db,
    save_telemetry_frame,
    get_latest_telemetry,
    get_telemetry_history,
    save_alert,
    get_alerts,
    acknowledge_alert_db,
    resolve_alert_db,
    update_device_status,
    get_registered_devices,
    create_symptom_report,
    get_symptom_reports,
    get_symptom_report_by_id,
    record_symptom_followup,
    get_due_symptom_reminders,
    save_crew_checkin,
    get_compliance_summary,
)
from src.agents.explainer import (
    build_body_focus_instruction,
    extract_body_region_and_intent,
    summarize_telemetry_provenance,
    sanitize_agent_output,
    LATEST_WEBCAM_STATE,
    get_gemini_api_key,
    get_gemini_client,
    GEMINI_CONVERSATIONAL_MODELS,
    GEMINI_TTS_MODELS,
    GEMINI_LIVE_MODEL,
    GEMINI_LIVE_DIALOG_MODEL,
)
from src.api.vision import (
    router as vision_router,
    AskRequest,
    SpeakRequest,
    WebcamAnalyzeRequest,
    ask_vision,
    speak_lunar,
    analyze_webcam_endpoint,
    get_vision_status,
)

# Initialize database
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(telemetry_broadcast_loop())
    yield
    task.cancel()


app = FastAPI(
    title="AstroHealth Guardian API",
    description="Intelligent Astronaut Health Monitoring & Mission Readiness Platform",
    version="2.0.0",
    lifespan=lifespan,
)

# Include existing vision router
app.include_router(vision_router, prefix="/api/vision")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State
generator = TelemetryGenerator(seed=42)
generator.apply_checkin_override(get_compliance_summary("CREW-01"))
current_source_mode = SourceMode.SIMULATED
last_live_packet_time: Optional[datetime] = None
last_live_device_id: str = "esp32-wearable-01"
latest_frame: Optional[TelemetryFrame] = None
latest_autonomous_action = "AstroHealth Guardian Autonomous Monitoring Engine Active"

# Physical plausibility bounds for hardware ingestion
MEASUREMENT_BOUNDS: Dict[str, tuple[float, float]] = {
    "heart_rate": (25.0, 260.0),
    "spo2": (50.0, 100.0),
    "skin_temperature": (20.0, 45.0),
    "core_temperature": (30.0, 44.0),
    "respiration_rate": (4.0, 60.0),
    "blood_pressure_systolic": (50.0, 260.0),
    "blood_pressure_diastolic": (30.0, 180.0),
    "hrv_rmssd": (1.0, 300.0),
    "co2_pp_mmhg": (0.0, 30.0),
    "cabin_temp_c": (-10.0, 60.0),
    "cabin_humidity_pct": (0.0, 100.0),
    "radiation_dose_rate_ugy_day": (0.0, 50000.0),
    "blood_glucose_mg_dl": (20.0, 600.0),
    "hydration_pct": (0.0, 100.0),
    "hydration_intake_ml": (0.0, 8000.0),
    "mood_score": (1.0, 5.0),
}


def _missing_item(unit: str, label: str = "Unavailable (Not provided by live device)") -> MeasurementItem:
    return MeasurementItem(
        value=None,
        unit=unit,
        quality=QualityFlag.MISSING,
        confidence=None,
        source=label,
        provenance="unavailable",
        is_derived=False,
    )


def _parse_and_validate_packet_timestamp(ts_str: Optional[str]) -> tuple[str, bool]:
    """
    Validates optional packet timestamp. Returns (iso_timestamp, is_stale).
    Raises ValueError if malformed or more than 300s in the future.
    """
    now_utc = datetime.now(timezone.utc)
    if not ts_str:
        return now_utc.isoformat(), False
    parsed = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_seconds = (now_utc - parsed).total_seconds()
    if age_seconds < -300.0:
        raise ValueError("Packet timestamp is more than 300 seconds in the future")
    is_stale = age_seconds > 60.0
    return parsed.isoformat(), is_stale


def _extract_live_measurement(
    measures: Dict[str, Any],
    key: str,
    default_unit: str,
    device_id: str,
    packet_is_stale: bool = False,
) -> MeasurementItem:
    """
    Extracts and validates a single measurement from a live hardware payload.
    Never substitutes a synthetic fallback value when a sensor reading is absent.
    """
    if key not in measures or measures[key] is None:
        return _missing_item(default_unit)

    raw_entry = measures[key]
    if not isinstance(raw_entry, dict):
        raise ValueError(f"Measurement '{key}' must be an object with 'value'")

    val = raw_entry.get("value")
    unit = str(raw_entry.get("unit", default_unit))
    raw_q = str(raw_entry.get("quality", "valid")).lower()
    try:
        q_flag = QualityFlag(raw_q)
    except ValueError:
        raise ValueError(f"Invalid quality flag '{raw_q}' for '{key}'")

    if val is None:
        return MeasurementItem(
            value=None,
            unit=unit,
            quality=QualityFlag.MISSING if q_flag == QualityFlag.VALID else q_flag,
            source=f"Live Hardware ({device_id})",
            provenance="unavailable",
        )

    try:
        f_val = float(val)
    except (TypeError, ValueError):
        raise ValueError(f"Measurement '{key}' value must be numeric")

    if key in MEASUREMENT_BOUNDS:
        low, high = MEASUREMENT_BOUNDS[key]
        if not (low <= f_val <= high):
            raise ValueError(f"{key} reading ({f_val}) out of physical bounds [{low}, {high}]")

    if packet_is_stale and q_flag == QualityFlag.VALID:
        q_flag = QualityFlag.STALE

    prov = "stale" if q_flag == QualityFlag.STALE else "live_hardware"
    return MeasurementItem(
        value=round(f_val, 2),
        unit=unit,
        quality=q_flag,
        confidence=raw_entry.get("confidence"),
        source=f"Live Hardware ({device_id})",
        provenance=prov,
        is_derived=False,
    )


def mark_frame_stale(frame: TelemetryFrame) -> TelemetryFrame:
    """Marks all present measurements in a live frame as STALE when packet stream times out."""
    metric_fields = [
        "heart_rate", "spo2", "hrv_rmssd", "blood_pressure_systolic",
        "blood_pressure_diastolic", "mean_arterial_pressure", "respiration_rate",
        "core_temperature", "skin_temperature", "sleep_hours", "sleep_efficiency",
        "sleep_interruptions", "reaction_time_ms", "attention_lapses", "readiness_score",
        "exercise_minutes", "exercise_load_w", "exercise_posture_score",
        "co2_pp_mmhg", "cabin_temp_c", "cabin_humidity_pct", "radiation_dose_rate_ugy_day",
        "blood_glucose_mg_dl", "hydration_pct", "hydration_intake_ml", "mood_score",
    ]
    for field_name in metric_fields:
        item: MeasurementItem = getattr(frame, field_name)
        if item.value is not None and item.quality == QualityFlag.VALID:
            item.quality = QualityFlag.STALE
            item.provenance = "stale"
    frame.context_note = "Live hardware telemetry stream stale (>5s since last packet)."
    return frame


# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "server_time": datetime.now(timezone.utc).isoformat(),
            "source_mode": current_source_mode.value,
            "scenario": generator.active_scenario,
        })

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for dead_conn in disconnected:
            self.disconnect(dead_conn)


manager = ConnectionManager()


# Background broadcast loop
async def telemetry_broadcast_loop():
    """
    Continuous 1 Hz telemetry loop:
    Generates or relays telemetry, evaluates operational rules,
    persists records, and broadcasts to all WebSocket subscribers.
    """
    global latest_frame, current_source_mode
    while True:
        try:
            # Check if live mode has gone stale (> 5 seconds since last packet)
            # Never silently replace live hardware mode with synthetic generator values.
            if current_source_mode == SourceMode.LIVE and last_live_packet_time:
                age = (datetime.now(timezone.utc) - last_live_packet_time).total_seconds()
                if age > 5.0:
                    update_device_status(last_live_device_id, "stale")
                    if latest_frame is not None:
                        latest_frame = mark_frame_stale(latest_frame)

            if current_source_mode == SourceMode.SIMULATED:
                frame = generator.generate_frame()
                frame.source_mode = SourceMode.SIMULATED
            else:
                frame = latest_frame

            if frame is not None:
                latest_frame = frame

                # 1. Evaluate Context
                context_summary = evaluate_crew_context(frame)
                if LATEST_WEBCAM_STATE.get("connected") and LATEST_WEBCAM_STATE.get("affect_summary"):
                    context_summary["webcam_affect"] = LATEST_WEBCAM_STATE.get("expression")
                    context_summary["webcam_note"] = LATEST_WEBCAM_STATE.get("affect_summary")

                # 2. Evaluate Alert Rules
                active_alerts = evaluate_telemetry_rules(frame)
                for alert in active_alerts:
                    alert_dict = alert.model_dump()
                    persisted_id = save_alert(alert_dict)
                    alert.id = persisted_id

                # 3. Persist Telemetry Frame
                frame_dict = frame.model_dump()
                save_telemetry_frame(frame_dict)

                # 4. Five Hazards, Historical Precedent Match & Compliance Summary (non-blocking cache)
                nasa_snap = get_nasa_live_bundle(fetch_live=False)
                donki_stat = nasa_snap.get("donki") or {}
                alert_dicts = [a.model_dump() for a in active_alerts]
                hazards_summary = get_five_hazards_status(
                    frame_dict=frame_dict,
                    alerts=alert_dicts,
                    donki_status=donki_stat,
                    offline_delay_mode=is_offline_delay_mode(),
                )
                incident_matches = match_historical_incidents(
                    frame_dict=frame_dict,
                    alerts=alert_dicts,
                    donki_active=bool(donki_stat.get("radiation_alert_active")),
                    limit=2,
                )
                compliance = get_compliance_summary(crew_id=frame.crew_id)

                # 5. Construct WebSocket broadcast envelope
                envelope = {
                    "type": "telemetry",
                    "schema_version": "1.0",
                    "timestamp": frame.timestamp,
                    "source_mode": frame.source_mode.value,
                    "source_device": frame.source_device,
                    "scenario_name": frame.scenario_name,
                    "telemetry": frame_dict,
                    "context": context_summary,
                    "alerts": alert_dicts,
                    "hazards": hazards_summary,
                    "incident_matches": incident_matches,
                    "donki_summary": donki_stat,
                    "offline_delay_mode": is_offline_delay_mode(),
                    "compliance": compliance,
                    "autonomous_action": latest_autonomous_action,
                    "webcam": LATEST_WEBCAM_STATE,
                }

                await manager.broadcast(envelope)

            await asyncio.sleep(1.0)

        except Exception as e:
            print(f"Error in broadcast loop: {e}")
            await asyncio.sleep(1.0)


# --- REST API Endpoints ---

@app.get("/api/health")
async def get_health():
    """System health check and diagnostic status."""
    return {
        "status": "operational",
        "service": "AstroHealth Guardian",
        "version": "2.0.0",
        "server_time": datetime.now(timezone.utc).isoformat(),
        "source_mode": current_source_mode.value,
        "active_scenario": generator.active_scenario,
        "is_paused": generator.is_paused,
        "connected_clients": len(manager.active_connections),
        "database": "sqlite_connected",
    }


@app.get("/api/telemetry/latest")
async def get_latest(crew_id: Optional[str] = None):
    """Fetches the latest stored telemetry sample."""
    if current_source_mode == SourceMode.LIVE and latest_frame is not None:
        if crew_id is None or latest_frame.crew_id == crew_id:
            return latest_frame.model_dump()
    sample = get_latest_telemetry(crew_id=crew_id)
    if not sample:
        frame = generator.generate_frame()
        return frame.model_dump()
    return sample


@app.get("/api/telemetry/history")
async def get_history(limit: int = Query(120, ge=1, le=1000), crew_id: Optional[str] = None):
    """Fetches chronological historical telemetry samples with limits."""
    records = get_telemetry_history(limit=limit, crew_id=crew_id)
    return {
        "count": len(records),
        "limit": limit,
        "records": records,
    }


class LegacyVitalsRecord(BaseModel):
    heart_rate: float
    hrv: float
    spo2: float
    exercise_posture_score: float = 1.0
    detected_expression: str = "neutral"


@app.post("/api/telemetry/ingest")
async def ingest_telemetry(payload: Dict[str, Any] = Body(...)):
    """
    Ingests live hardware telemetry from ESP32 or external sensor suites.
    Supports both Schema v1.0 and legacy fixture formats.
    Strictly separates live hardware values from unmeasured sensors (never fills
    missing sensors in a live frame with synthetic generator numbers).
    """
    global current_source_mode, last_live_packet_time, last_live_device_id, latest_frame

    if "measurements" in payload:
        device_id = str(payload.get("device_id", "")).strip() or "esp32-wearable-01"
        schema_ver = str(payload.get("schema_version", "1.0"))
        if schema_ver != "1.0":
            update_device_status(device_id, "error", packet_received=True, is_error=True)
            raise HTTPException(status_code=422, detail=f"Unsupported schema_version '{schema_ver}'")

        seq = payload.get("sequence")
        if seq is None or not isinstance(seq, int) or seq < 0:
            update_device_status(device_id, "error", packet_received=True, is_error=True)
            raise HTTPException(status_code=422, detail="Valid non-negative integer 'sequence' is required")

        measures = payload.get("measurements")
        if not isinstance(measures, dict) or len(measures) == 0:
            update_device_status(device_id, "error", packet_received=True, is_error=True)
            raise HTTPException(status_code=422, detail="Non-empty 'measurements' dictionary is required")

        try:
            packet_ts, is_stale_ts = _parse_and_validate_packet_timestamp(payload.get("timestamp"))
        except ValueError as e:
            update_device_status(device_id, "error", packet_received=True, is_error=True)
            raise HTTPException(status_code=422, detail=f"Invalid timestamp: {e}")

        try:
            hr_item = _extract_live_measurement(measures, "heart_rate", "bpm", device_id, is_stale_ts)
            spo2_item = _extract_live_measurement(measures, "spo2", "%", device_id, is_stale_ts)
            skin_t_item = _extract_live_measurement(measures, "skin_temperature", "°C", device_id, is_stale_ts)
            core_t_item = _extract_live_measurement(measures, "core_temperature", "°C", device_id, is_stale_ts)
            hrv_item = _extract_live_measurement(measures, "hrv_rmssd", "ms", device_id, is_stale_ts)
            sbp_item = _extract_live_measurement(measures, "blood_pressure_systolic", "mmHg", device_id, is_stale_ts)
            dbp_item = _extract_live_measurement(measures, "blood_pressure_diastolic", "mmHg", device_id, is_stale_ts)
            rr_item = _extract_live_measurement(measures, "respiration_rate", "breaths/min", device_id, is_stale_ts)
            co2_item = _extract_live_measurement(measures, "co2_pp_mmhg", "mmHg", device_id, is_stale_ts)
            cabin_t_item = _extract_live_measurement(measures, "cabin_temp_c", "°C", device_id, is_stale_ts)
            cabin_h_item = _extract_live_measurement(measures, "cabin_humidity_pct", "%", device_id, is_stale_ts)
            rad_item = _extract_live_measurement(measures, "radiation_dose_rate_ugy_day", "µGy/day", device_id, is_stale_ts)
            glucose_item = _extract_live_measurement(measures, "blood_glucose_mg_dl", "mg/dL", device_id, is_stale_ts)
            hydration_pct_item = _extract_live_measurement(measures, "hydration_pct", "%", device_id, is_stale_ts)
            hydration_ml_item = _extract_live_measurement(measures, "hydration_intake_ml", "mL", device_id, is_stale_ts)
            mood_item = _extract_live_measurement(measures, "mood_score", "/5", device_id, is_stale_ts)
        except ValueError as e:
            update_device_status(device_id, "error", packet_received=True, is_error=True)
            raise HTTPException(status_code=422, detail=str(e))

        # Derived MAP only when both live SBP and DBP are actually measured
        if sbp_item.value is not None and dbp_item.value is not None:
            map_val = round((sbp_item.value + 2.0 * dbp_item.value) / 3.0, 1)
            map_item = MeasurementItem(
                value=map_val,
                unit="mmHg",
                quality=QualityFlag.STALE if is_stale_ts else QualityFlag.VALID,
                source=f"Derived from Live BP ({device_id})",
                provenance="derived",
                is_derived=True,
                calculation_method="MAP ≈ (SBP + 2 × DBP) / 3",
            )
        else:
            map_item = _missing_item("mmHg", "Unavailable (Requires live SBP & DBP)")

        crew_id = str(payload.get("crew_id", "CREW-01"))
        crew_name = str(payload.get("crew_name", "Cmdr. Alex Vance"))

        live_frame = TelemetryFrame(
            timestamp=packet_ts,
            crew_id=crew_id,
            crew_name=crew_name,
            source_mode=SourceMode.LIVE,
            source_device=device_id,
            scenario_name="Live Hardware Telemetry",
            heart_rate=hr_item,
            spo2=spo2_item,
            hrv_rmssd=hrv_item,
            blood_pressure_systolic=sbp_item,
            blood_pressure_diastolic=dbp_item,
            mean_arterial_pressure=map_item,
            respiration_rate=rr_item,
            core_temperature=core_t_item,
            skin_temperature=skin_t_item,
            sleep_hours=_missing_item("hours"),
            sleep_efficiency=_missing_item("%"),
            sleep_interruptions=_missing_item("events"),
            reaction_time_ms=_missing_item("ms"),
            attention_lapses=_missing_item("lapses (>500ms)"),
            readiness_score=_missing_item("/100"),
            exercise_minutes=_missing_item("minutes/day"),
            exercise_type=str(payload.get("exercise_type", "Rest")),
            exercise_load_w=_missing_item("Watts"),
            exercise_posture_score=_missing_item("score (0-1)"),
            detected_expression=str(payload.get("detected_expression", "unavailable")),
            co2_pp_mmhg=co2_item,
            cabin_temp_c=cabin_t_item,
            cabin_humidity_pct=cabin_h_item,
            radiation_dose_rate_ugy_day=rad_item,
            blood_glucose_mg_dl=glucose_item,
            hydration_pct=hydration_pct_item,
            hydration_intake_ml=hydration_ml_item,
            mood_score=mood_item,
            mood_label=str(payload.get("mood_label", "unavailable")),
            ultrasound_last_check=str(payload.get("ultrasound_last_check", "Unavailable in live hardware packet")),
            context_note=f"Live hardware packet #{seq} from {device_id}. Unconnected sensors marked missing.",
        )

        latest_frame = live_frame
        current_source_mode = SourceMode.LIVE
        last_live_packet_time = datetime.now(timezone.utc)
        last_live_device_id = device_id

        save_telemetry_frame(live_frame.model_dump())
        for alert in evaluate_telemetry_rules(live_frame):
            save_alert(alert.model_dump())

        update_device_status(device_id, "stale" if is_stale_ts else "online", packet_received=True, is_error=False)

        return {
            "status": "accepted",
            "device_id": device_id,
            "sequence": seq,
            "timestamp": packet_ts,
            "is_stale": is_stale_ts,
            "mode": "live",
        }

    # Legacy ingestion format fallback
    elif "heart_rate" in payload:
        try:
            legacy = LegacyVitalsRecord(**payload)
            if not (25.0 <= legacy.heart_rate <= 260.0):
                raise ValueError("Heart rate out of physical bounds")
            if not (50.0 <= legacy.spo2 <= 100.0):
                raise ValueError("SpO2 out of physical bounds")

            now_iso = datetime.now(timezone.utc).isoformat()
            live_frame = TelemetryFrame(
                timestamp=now_iso,
                crew_id="CREW-01",
                crew_name="Cmdr. Alex Vance",
                source_mode=SourceMode.LIVE,
                source_device="legacy_ingest",
                scenario_name="Live Hardware Telemetry (Legacy)",
                heart_rate=MeasurementItem(value=legacy.heart_rate, unit="bpm", quality=QualityFlag.VALID, source="Live Ingest", provenance="live_hardware"),
                spo2=MeasurementItem(value=legacy.spo2, unit="%", quality=QualityFlag.VALID, source="Live Ingest", provenance="live_hardware"),
                hrv_rmssd=MeasurementItem(value=legacy.hrv, unit="ms", quality=QualityFlag.VALID, source="Live Ingest", provenance="live_hardware"),
                blood_pressure_systolic=_missing_item("mmHg"),
                blood_pressure_diastolic=_missing_item("mmHg"),
                mean_arterial_pressure=_missing_item("mmHg"),
                respiration_rate=_missing_item("breaths/min"),
                core_temperature=_missing_item("°C"),
                skin_temperature=_missing_item("°C"),
                sleep_hours=_missing_item("hours"),
                sleep_efficiency=_missing_item("%"),
                sleep_interruptions=_missing_item("events"),
                reaction_time_ms=_missing_item("ms"),
                attention_lapses=_missing_item("lapses (>500ms)"),
                readiness_score=_missing_item("/100"),
                exercise_minutes=_missing_item("minutes/day"),
                exercise_type="Rest",
                exercise_load_w=_missing_item("Watts"),
                exercise_posture_score=MeasurementItem(value=legacy.exercise_posture_score, unit="score (0-1)", quality=QualityFlag.VALID, source="Live Ingest", provenance="live_hardware"),
                detected_expression=legacy.detected_expression,
                co2_pp_mmhg=_missing_item("mmHg"),
                cabin_temp_c=_missing_item("°C"),
                cabin_humidity_pct=_missing_item("%"),
                radiation_dose_rate_ugy_day=_missing_item("µGy/day"),
                blood_glucose_mg_dl=_missing_item("mg/dL"),
                hydration_pct=_missing_item("%"),
                hydration_intake_ml=_missing_item("mL"),
                mood_score=_missing_item("/5"),
                mood_label="unavailable",
                ultrasound_last_check="Unavailable in legacy live packet",
                context_note="Legacy live ingest packet.",
            )

            latest_frame = live_frame
            current_source_mode = SourceMode.LIVE
            last_live_packet_time = datetime.now(timezone.utc)
            save_telemetry_frame(live_frame.model_dump())
            update_device_status("esp32-wearable-01", "online", packet_received=True)
            return {"status": "ok", "mode": "live"}
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Legacy format error: {e}")
    else:
        raise HTTPException(status_code=400, detail="Unrecognized telemetry payload schema")


@app.get("/api/alerts")
async def list_alerts(status: Optional[str] = None):
    """Retrieves managed alerts and events."""
    alerts = get_alerts(status_filter=status)
    return {
        "total": len(alerts),
        "alerts": alerts,
    }


class AckRequest(BaseModel):
    operator_id: str = "Flight Surgeon (MCC)"


@app.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, req: AckRequest = AckRequest()):
    """Marks an alert as acknowledged without removing it from audit history."""
    success = acknowledge_alert_db(alert_id, operator_id=req.operator_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found or already acknowledged/resolved")
    return {"status": "acknowledged", "alert_id": alert_id}


class ResolveRequest(BaseModel):
    operator_id: str = "Flight Surgeon (MCC)"
    resolution_notes: str


@app.post("/api/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, req: ResolveRequest):
    """Resolves an alert with clinical operator notes."""
    success = resolve_alert_db(alert_id, notes=req.resolution_notes, operator_id=req.operator_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "resolved", "alert_id": alert_id}


@app.get("/api/devices")
async def list_devices():
    """Lists registered hardware and simulated devices with health statistics."""
    devices = get_registered_devices()
    return {
        "count": len(devices),
        "devices": devices,
    }


@app.get("/api/research")
async def get_research():
    """Returns verified NASA and hardware research references."""
    return {
        "citations": RESEARCH_CITATIONS,
    }


@app.get("/api/incidents")
async def get_historical_incidents_overview(q: Optional[str] = None):
    """Returns all 5 NASA Hazards, historical spaceflight incidents catalog, and current matches."""
    frame_dict = latest_frame.model_dump() if latest_frame is not None else get_latest_telemetry()
    active_alerts = get_alerts(status_filter="active")
    nasa_snap = get_nasa_live_bundle(fetch_live=False)
    donki_stat = nasa_snap.get("donki") or {}
    return {
        "five_hazards": get_five_hazards_status(
            frame_dict=frame_dict,
            alerts=active_alerts,
            donki_status=donki_stat,
            offline_delay_mode=is_offline_delay_mode(),
        ),
        "incidents": HISTORICAL_INCIDENTS,
        "matched_now": match_historical_incidents(
            frame_dict=frame_dict,
            alerts=active_alerts,
            query_text=q,
            donki_active=bool(donki_stat.get("radiation_alert_active")),
            limit=4,
        ),
    }


@app.get("/api/incidents/match")
async def match_incidents_endpoint(q: Optional[str] = None, limit: int = Query(default=3, ge=1, le=7)):
    """Compares live telemetry + query text against historical spaceflight incidents."""
    frame_dict = latest_frame.model_dump() if latest_frame is not None else get_latest_telemetry()
    active_alerts = get_alerts(status_filter="active")
    nasa_snap = get_nasa_live_bundle(fetch_live=False)
    donki_stat = nasa_snap.get("donki") or {}
    matches = match_historical_incidents(
        frame_dict=frame_dict,
        alerts=active_alerts,
        query_text=q,
        donki_active=bool(donki_stat.get("radiation_alert_active")),
        limit=limit,
    )
    return {
        "count": len(matches),
        "query": q,
        "scenario": generator.active_scenario,
        "matches": matches,
    }


@app.get("/api/nasa/live-context")
async def get_nasa_live_context_endpoint(
    topic: str = Query(default="microgravity"),
    refresh: bool = Query(default=False),
    fetch_live: bool = Query(default=True),
):
    """Fetches cached or live public NASA DONKI, OSDR, and NTRS resources with offline fallback."""
    bundle = await asyncio.to_thread(
        get_nasa_live_bundle,
        topic=topic,
        fetch_live=fetch_live,
        force_refresh=refresh,
    )
    return bundle


class OfflineModeRequest(BaseModel):
    offline: bool


@app.post("/api/nasa/offline-mode")
async def toggle_offline_delay_mode(req: OfflineModeRequest):
    """Toggles Mars Deep-Space Delay / Offline Autonomous Mode."""
    active = set_offline_delay_mode(req.offline)
    return {
        "status": "ok",
        "offline_delay_mode": active,
        "message": (
            "Mars 20-Min Signal Delay Mode active: running 100% locally via SQLite & cached NASA catalog."
            if active
            else "Live NASA Open API sync enabled."
        ),
    }


class CrewCheckinRequest(BaseModel):
    crew_id: str = "CREW-01"
    mood_score: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    mood_label: Optional[str] = None
    hydration_delta_ml: float = Field(default=0.0, ge=0.0, le=2000.0)
    blood_glucose_mg_dl: Optional[float] = Field(default=None, ge=20.0, le=600.0)
    ultrasound_region: Optional[str] = None
    ultrasound_note: Optional[str] = None
    notes: str = ""


@app.post("/api/crew/checkin")
async def record_crew_checkin_endpoint(req: CrewCheckinRequest):
    """Logs crew hydration, mood, glucose, or SANS/IJV ultrasound check and updates compliance streak."""
    summary = save_crew_checkin(
        crew_id=req.crew_id,
        mood_score=req.mood_score,
        mood_label=req.mood_label,
        hydration_delta_ml=req.hydration_delta_ml,
        blood_glucose_mg_dl=req.blood_glucose_mg_dl,
        ultrasound_region=req.ultrasound_region,
        ultrasound_note=req.ultrasound_note,
        notes=req.notes,
    )
    generator.apply_checkin_override(summary)
    return {
        "status": "ok",
        "compliance": summary,
    }


@app.get("/api/crew/compliance")
async def get_crew_compliance_endpoint(crew_id: str = "CREW-01"):
    """Returns daily compliance streak, XP badges, hydration total, glucose, mood, and SANS ultrasound log."""
    return get_compliance_summary(crew_id=crew_id)


class ScenarioRequest(BaseModel):
    scenario_name: str


@app.post("/api/simulation/scenario")
async def change_scenario(req: ScenarioRequest):
    """Dynamically activates one of the 7 predefined demonstration scenarios."""
    global current_source_mode
    generator.set_scenario(req.scenario_name)
    current_source_mode = SourceMode.SIMULATED
    return {
        "status": "success",
        "active_scenario": generator.active_scenario,
        "mode": current_source_mode.value,
    }


class ControlRequest(BaseModel):
    action: str  # "pause", "resume", "reset"


@app.post("/api/simulation/control")
async def simulation_control(req: ControlRequest):
    """Controls the telemetry generator playback."""
    global current_source_mode
    if req.action == "pause":
        generator.is_paused = True
    elif req.action == "resume":
        generator.is_paused = False
    elif req.action == "reset":
        generator.reset()
        current_source_mode = SourceMode.SIMULATED
    else:
        raise HTTPException(status_code=400, detail="Action must be 'pause', 'resume', or 'reset'")
    return {
        "status": "success",
        "action": req.action,
        "is_paused": generator.is_paused,
        "step_index": generator.step_index,
    }


class ActionRecord(BaseModel):
    action_text: str


@app.post("/api/telemetry/action")
async def update_action(record: ActionRecord):
    """Preserves compatibility with autonomous guardian script."""
    global latest_autonomous_action
    latest_autonomous_action = record.action_text
    return {"status": "ok"}


# --- Lunar Assistant & Symptom Tracking Endpoints ---

@app.get("/api/lunar/status")
async def get_lunar_status_endpoint():
    """Returns Lunar Gemini conversational, TTS, and Live API readiness alongside camera status."""
    return await get_vision_status()


@app.post("/api/lunar/ask")
async def ask_lunar_endpoint(req: AskRequest):
    """Direct Lunar assistant endpoint mirroring `/api/vision/ask`."""
    return await ask_vision(req)


@app.post("/api/lunar/speak")
async def speak_lunar_endpoint(req: SpeakRequest):
    """Direct Lunar Gemini TTS endpoint mirroring `/api/vision/speak`."""
    return await speak_lunar(req)


@app.post("/api/lunar/vision-check")
async def lunar_vision_check_endpoint(req: WebcamAnalyzeRequest):
    """Direct laptop webcam face identification & affect check endpoint mirroring `/api/vision/webcam-analyze`."""
    return await analyze_webcam_endpoint(req)


class CreateSymptomRequest(BaseModel):
    crew_id: str = "CREW-01"
    body_region: str
    symptom_text: str
    layer: Optional[str] = None
    severity: str = "amber"
    initial_intensity: float = Field(default=0.6, ge=0.0, le=1.0)
    followup_after_hours: float = Field(default=24.0, gt=0.0)
    human_review_needed: bool = False


@app.post("/api/symptoms")
async def create_symptom_endpoint(req: CreateSymptomRequest):
    """
    Logs a crew-reported symptom with validated body region and explicit provenance.
    Returns both the persisted report and the `body_focus` instruction for `window.LunarBodyGuide`.
    """
    valid_region = validate_body_region(req.body_region)
    if not valid_region:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported body_region '{req.body_region}'. Valid regions: {sorted(SUPPORTED_BODY_REGIONS.keys())}",
        )
    if req.layer is not None and req.layer not in SUPPORTED_BODY_LAYERS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported layer '{req.layer}'. Valid layers: {sorted(SUPPORTED_BODY_LAYERS)}",
        )
    if req.severity not in SUPPORTED_FOCUS_SEVERITIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported severity '{req.severity}'. Valid severities: {sorted(SUPPORTED_FOCUS_SEVERITIES)}",
        )

    report = create_symptom_report(
        crew_id=req.crew_id,
        body_region=valid_region,
        symptom_text=req.symptom_text,
        user_status="reported",
        severity=req.severity,
        initial_intensity=req.initial_intensity,
        layer=req.layer,
        provenance="crew_self_report",
        followup_after_hours=req.followup_after_hours,
        human_review_needed=req.human_review_needed,
    )
    focus = build_body_focus_instruction(
        region=report["body_region"],
        layer=report["layer"],
        severity=report["severity"],
        intensity=report["current_intensity"],
        provenance="crew_self_report",
    )
    return {
        "status": "created",
        "symptom_report": report,
        "body_focus": focus.model_dump() if focus else None,
    }


@app.get("/api/symptoms")
async def list_symptoms_endpoint(
    crew_id: Optional[str] = None,
    status: Optional[str] = None,
    body_region: Optional[str] = None,
):
    """Lists persisted symptom reports with follow-up histories."""
    if body_region is not None and validate_body_region(body_region) is None:
        raise HTTPException(status_code=422, detail=f"Unsupported body_region '{body_region}'")
    reports = get_symptom_reports(crew_id=crew_id, status_filter=status, body_region=body_region)
    return {
        "count": len(reports),
        "symptoms": reports,
    }


class SymptomFollowUpRequest(BaseModel):
    status_update: str  # "improving" | "unchanged" | "worsened" | "resolved"
    new_intensity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: str = ""
    actor: str = "CREW-01"
    followup_after_hours: float = Field(default=24.0, gt=0.0)


@app.post("/api/symptoms/{symptom_id}/followup")
async def followup_symptom_endpoint(symptom_id: str, req: SymptomFollowUpRequest):
    """
    Records a crew-confirmed follow-up on an existing symptom.
    Highlight fading/intensity changes are driven strictly by this confirmed follow-up,
    never by an automatic elapsed-time schedule.
    """
    updated = record_symptom_followup(
        symptom_id=symptom_id,
        status_update=req.status_update,
        new_intensity=req.new_intensity,
        notes=req.notes,
        actor=req.actor,
        followup_after_hours=req.followup_after_hours,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Symptom report '{symptom_id}' not found")

    if updated["user_status"] == "resolved":
        focus = build_body_focus_instruction(
            region=updated["body_region"],
            layer=updated["layer"],
            severity="green",
            intensity=0.0,
            action="clearFocus",
            provenance="crew_followup_confirmed",
        )
    else:
        focus = build_body_focus_instruction(
            region=updated["body_region"],
            layer=updated["layer"],
            severity=updated["severity"],
            intensity=updated["current_intensity"],
            provenance="crew_followup_confirmed",
        )

    return {
        "status": "updated",
        "symptom_report": updated,
        "body_focus": focus.model_dump() if focus else None,
    }


@app.get("/api/symptoms/reminders")
async def list_symptom_reminders_endpoint(crew_id: Optional[str] = None):
    """
    Returns scheduled symptom follow-up check-ins.
    Explicitly documents that reminders are delivered via in-console pull (`external_push_sent: False`).
    """
    reminders = get_due_symptom_reminders(crew_id=crew_id)
    return {
        "count": len(reminders),
        "delivery_mechanism": "in_console_pull",
        "background_push_daemon_active": False,
        "reminders": reminders,
    }


# --- WebSocket Streaming ---

@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """
    Subscribes client to live broadcast stream of astronaut telemetry, alerts, and context.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


@app.websocket("/ws/lunar/live")
async def websocket_lunar_live_endpoint(websocket: WebSocket):
    """
    Real-time bidirectional voice, webcam video, & monitor control WebSocket bridge to
    Gemini 2.5 Flash Native Audio Dialog (`gemini-2.5-flash-native-audio-latest`) with
    single locked voice (`Aoede`) and real-time UI function calling.
    """
    await websocket.accept()
    api_key = get_gemini_api_key()
    if not api_key:
        await websocket.send_json({
            "type": "error",
            "message": "GEMINI_API_KEY is not configured in .env.",
        })
        await websocket.close()
        return

    try:
        from google import genai
        from google.genai import types as genai_types
        import base64

        client = genai.Client(api_key=api_key)
        valid_regions = ", ".join(sorted(SUPPORTED_BODY_REGIONS.keys()))

        live_tools = [genai_types.Tool(function_declarations=[
            genai_types.FunctionDeclaration(
                name="focus_body_region",
                description="Focus and highlight a body area on the 3D astronaut hologram and switch to Overview tab.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "region": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description=f"Must match one of: {valid_regions}",
                        ),
                        "layer": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Optional layer: 'Full body', 'Skeleton', 'Heart', or 'Lungs'",
                        ),
                        "severity": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="'green' (info/improving), 'amber' (mild/caution), or 'red' (pain/urgent)",
                        ),
                        "intensity": genai_types.Schema(
                            type=genai_types.Type.NUMBER,
                            description="Highlight intensity from 0.1 to 1.0",
                        ),
                        "is_pain_marker": genai_types.Schema(
                            type=genai_types.Type.BOOLEAN,
                            description="True if crew member is reporting pain, hurt, or a cut there",
                        ),
                        "symptom_text": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Short note if logging a pain/cut symptom",
                        ),
                    },
                    required=["region"],
                ),
            ),
            genai_types.FunctionDeclaration(
                name="clear_body_focus",
                description="Clear active 3D highlight and zoom back out on the astronaut body model.",
                parameters=genai_types.Schema(type=genai_types.Type.OBJECT, properties={}),
            ),
            genai_types.FunctionDeclaration(
                name="switch_dashboard_tab",
                description="Switch the active screen tab on the monitor.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "tab": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="One of: tab-overview, tab-crew-health, tab-explorer, tab-alerts, tab-hardware, tab-vision, tab-research, tab-settings",
                        )
                    },
                    required=["tab"],
                ),
            ),
            genai_types.FunctionDeclaration(
                name="inspect_vital_cards",
                description="Pulse/highlight specific telemetry cards on the monitor while checking them.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "cards": genai_types.Schema(
                            type=genai_types.Type.ARRAY,
                            items=genai_types.Schema(type=genai_types.Type.STRING),
                            description="List from: card-hr, card-spo2, card-bp, card-map, card-hrv, card-core-temp, card-skin-temp, card-rr",
                        )
                    },
                    required=["cards"],
                ),
            ),
            genai_types.FunctionDeclaration(
                name="get_live_vitals_and_alerts",
                description="Read the astronaut's current heart rate, blood pressure estimate, oxygen SpO2, cabin CO2, sleep, readiness, and open alerts/symptoms.",
                parameters=genai_types.Schema(type=genai_types.Type.OBJECT, properties={}),
            ),
            genai_types.FunctionDeclaration(
                name="set_simulation_mode",
                description="Switch simulation scenario or pause/resume telemetry playback.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "scenario_name": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Optional scenario substring e.g. 'Scenario A', 'Scenario B', 'Scenario E', etc.",
                        ),
                        "control_action": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Optional: pause, resume, or reset",
                        ),
                    },
                ),
            ),
            genai_types.FunctionDeclaration(
                name="set_body_fullscreen",
                description="Turn the 3D body-only full-screen view on or off. Activate during full-body or region discussion, or turn off to return to the unified home dashboard.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "active": genai_types.Schema(
                            type=genai_types.Type.BOOLEAN,
                            description="true for full-screen body-only mode, false to exit back to the unified home screen",
                        ),
                    },
                    required=["active"],
                ),
            ),
            genai_types.FunctionDeclaration(
                name="compare_historical_incidents",
                description="Compare current crew telemetry, environmental values, or described symptoms against documented earlier NASA/ISS/Skylab/Apollo incidents and return what happened and concrete steps to verify and mitigate.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "situation": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Short description of current anomaly, symptom, or hazard e.g. 'CO2 high headache', 'resting heart rate', 'radiation solar flare', 'sleep fatigue'",
                        ),
                    },
                ),
            ),
            genai_types.FunctionDeclaration(
                name="log_crew_checkin",
                description="Log crew hydration intake (+250/500 mL), mood score (1-5), blood glucose (mg/dL), or SANS/IJV ultrasound observation and update the crew compliance streak.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "hydration_delta_ml": genai_types.Schema(type=genai_types.Type.NUMBER),
                        "mood_score": genai_types.Schema(type=genai_types.Type.NUMBER),
                        "mood_label": genai_types.Schema(type=genai_types.Type.STRING),
                        "blood_glucose_mg_dl": genai_types.Schema(type=genai_types.Type.NUMBER),
                        "ultrasound_region": genai_types.Schema(type=genai_types.Type.STRING),
                        "ultrasound_note": genai_types.Schema(type=genai_types.Type.STRING),
                    },
                ),
            ),
        ])]

        live_sys_prompt = (
            "You are Lunar, a warm, friendly human-like female companion talking live with Cmdr. Mahir (Crew One) on RoboBee Health Guardian.\n"
            "STRICT CONVERSATION STYLE:\n"
            "- Whenever Cmdr. Mahir greets you or calls 'Hey Lunar' (even repeated like 'Hey Lunar, Hey Lunar'), ALWAYS respond right away warmly in 1 short sentence (e.g., 'Hey Mahir, I'm right here—how can I help?').\n"
            "- Listen first and reply naturally to whatever he says—whether casual chat, asking how he looks, asking about vitals, asking about earlier NASA incidents, or mentioning soreness anywhere on his body.\n"
            "- Keep EVERY reply brief and conversational: 1 to 2 natural spoken sentences max.\n"
            "- NEVER recite giant console readouts (do NOT mention raw numbers, readiness scores, or IDs unless specifically asked about numbers, incidents, or alerts).\n"
            "- HISTORICAL INCIDENT COMPARISON: When alerts are active or Mahir asks whether something happened before (e.g., CO2 spike, sleep fatigue, arrhythmia, SANS/DVT fluid shift, radiation storm), call `compare_historical_incidents` and briefly explain what earlier mission matched (Apollo 13, Skylab 2/4, ISS DVT/EVA-23, Mir) and the 1–2 checks to take.\n"
            "- Look at incoming camera frames when present to genuinely observe his face, visible skin checks, or anything held up without claiming clinical diagnosis.\n"
            "- AUTONOMOUS MONITOR & BODY CONTROL: use your tools (`focus_body_region`, `clear_body_focus`, `set_body_fullscreen`, `switch_dashboard_tab`, `inspect_vital_cards`, `get_live_vitals_and_alerts`, `compare_historical_incidents`, `log_crew_checkin`, `set_simulation_mode`) without waiting for mouse clicks.\n"
            "  * Calling `focus_body_region` automatically switches to the full-screen 3D whole-body inspection view; call `clear_body_focus` or `set_body_fullscreen(active=false)` when done discussing a body region so the dashboard exits full-screen by default.\n"
            "- Non-diagnostic boundary: never diagnose diseases or prescribe medications."
        )

        config = genai_types.LiveConnectConfig(
            response_modalities=[genai_types.Modality.AUDIO],
            speech_config=genai_types.SpeechConfig(
                voice_config=genai_types.VoiceConfig(
                    prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
            input_audio_transcription=genai_types.AudioTranscriptionConfig(),
            output_audio_transcription=genai_types.AudioTranscriptionConfig(),
            tools=live_tools,
            system_instruction=genai_types.Content(
                parts=[genai_types.Part(text=live_sys_prompt)]
            ),
        )

        async def _execute_live_tool(fname: str, fargs: Dict[str, Any]) -> Dict[str, Any]:
            global latest_frame
            if fname == "focus_body_region":
                raw_reg = str(fargs.get("region", "")).strip()
                norm_reg = validate_body_region(raw_reg)
                if not norm_reg:
                    norm_reg = validate_body_region(raw_reg.replace(" ", "-"))
                if not norm_reg:
                    parsed_r = extract_body_region_and_intent(raw_reg)
                    norm_reg = parsed_r.get("body_region")
                if not norm_reg:
                    return {"ok": False, "error": f"Unknown region '{raw_reg}'"}
                layer_arg = fargs.get("layer") if fargs.get("layer") in SUPPORTED_BODY_LAYERS else None
                sev_arg = fargs.get("severity") if fargs.get("severity") in SUPPORTED_FOCUS_SEVERITIES else ("red" if fargs.get("is_pain_marker") else "amber")
                try:
                    int_arg = round(max(0.1, min(1.0, float(fargs.get("intensity", 0.7 if fargs.get("is_pain_marker") else 0.5)))), 2)
                except Exception:
                    int_arg = 0.6
                bf = build_body_focus_instruction(
                    region=norm_reg,
                    layer=layer_arg,
                    severity=sev_arg,
                    intensity=int_arg,
                    provenance="lunar_live_tool",
                )
                sym_rec = None
                if fargs.get("is_pain_marker") and bf:
                    sym_rec = create_symptom_report(
                        crew_id="CREW-01",
                        body_region=norm_reg,
                        symptom_text=str(fargs.get("symptom_text") or f"Crew reported pain in {norm_reg}"),
                        user_status="reported",
                        severity=sev_arg,
                        initial_intensity=int_arg,
                        layer=bf.layer,
                        provenance="crew_self_report",
                    )
                if bf:
                    region_lbl = bf.region_label or bf.region or norm_reg
                    ui_act = {
                        "action": "focus_body",
                        "region": bf.region,
                        "region_label": region_lbl,
                        "layer": bf.layer,
                        "severity": bf.severity,
                        "intensity": bf.intensity,
                        "is_pain_marker": bool(fargs.get("is_pain_marker")),
                        "marker_label": (
                            f"PAIN TRADEMARK • {region_lbl.upper()} ({sym_rec['id']})"
                            if sym_rec
                            else f"3D SCAN • {region_lbl.upper()}"
                        ),
                        "symptom_id": sym_rec["id"] if sym_rec else None,
                    }
                    await websocket.send_json({
                        "type": "ui_actions",
                        "body_focus": bf.model_dump(),
                        "symptom_report": sym_rec,
                        "ui_actions": [
                            {"action": "switch_tab", "tab": "tab-overview"},
                            {"action": "body_fullscreen", "active": True},
                            ui_act,
                        ],
                    })
                return {"ok": True, "focused_region": norm_reg, "layer": bf.layer if bf else None, "fullscreen": True}

            if fname == "clear_body_focus":
                bf = build_body_focus_instruction(region=None, action="clearFocus", provenance="lunar_live_tool")
                await websocket.send_json({
                    "type": "ui_actions",
                    "body_focus": bf.model_dump() if bf else {"action": "clearFocus"},
                    "ui_actions": [
                        {"action": "body_fullscreen", "active": False},
                    ],
                })
                return {"ok": True, "cleared": True, "fullscreen": False}

            if fname == "set_body_fullscreen":
                active_fs = bool(fargs.get("active", True))
                actions_list: List[Dict[str, Any]] = []
                if active_fs:
                    actions_list.append({"action": "switch_tab", "tab": "tab-overview"})
                actions_list.append({"action": "body_fullscreen", "active": active_fs})
                await websocket.send_json({
                    "type": "ui_actions",
                    "ui_actions": actions_list,
                })
                return {"ok": True, "fullscreen": active_fs}

            if fname == "switch_dashboard_tab":
                tab = str(fargs.get("tab", "tab-overview")).strip()
                valid_tabs = {"tab-overview", "tab-crew-health", "tab-explorer", "tab-alerts", "tab-hardware", "tab-vision", "tab-research", "tab-settings"}
                if tab not in valid_tabs:
                    return {"ok": False, "error": "Unsupported tab"}
                await websocket.send_json({
                    "type": "ui_actions",
                    "ui_actions": [
                        {"action": "body_fullscreen", "active": False},
                        {"action": "switch_tab", "tab": tab},
                    ],
                })
                return {"ok": True, "active_tab": tab}

            if fname == "inspect_vital_cards":
                raw_cards = fargs.get("cards") or ["card-bp", "card-spo2", "card-hr"]
                cards = [str(c) for c in raw_cards if str(c).startswith("card-")]
                await websocket.send_json({
                    "type": "ui_actions",
                    "ui_actions": [
                        {"action": "body_fullscreen", "active": False},
                        {"action": "switch_tab", "tab": "tab-overview"},
                        {"action": "inspect_vitals", "cards": cards},
                    ],
                })
                return {"ok": True, "highlighted_cards": cards}

            if fname == "get_live_vitals_and_alerts":
                tel_obj = get_latest_telemetry(crew_id="CREW-01") or get_latest_telemetry()
                tel_sum = summarize_telemetry_provenance(tel_obj)
                alerts_list = get_alerts(status_filter="active")
                open_list = get_symptom_reports(crew_id="CREW-01", status_filter="open")
                comp = get_compliance_summary(crew_id="CREW-01")
                metrics_map = tel_sum.get("metrics") or {}
                hr_m = metrics_map.get("heart_rate", {}).get("value")
                bp_sys = int(round(118 + ((hr_m - 72.0) * 0.35))) if hr_m is not None else 118
                bp_dia = int(round(76 + ((hr_m - 72.0) * 0.20))) if hr_m is not None else 76
                matches = match_historical_incidents(frame_dict=tel_obj, alerts=alerts_list, limit=2)
                return {
                    "source_mode": tel_sum.get("source_mode"),
                    "heart_rate_bpm": hr_m,
                    "estimated_bp": f"{bp_sys}/{bp_dia}",
                    "spo2_pct": metrics_map.get("spo2", {}).get("value"),
                    "co2_mmhg": metrics_map.get("co2_pp_mmhg", {}).get("value"),
                    "radiation_ugy_day": (tel_obj or {}).get("radiation_dose_rate_ugy_day", {}).get("value"),
                    "hydration_pct": comp.get("hydration_pct"),
                    "blood_glucose_mg_dl": comp.get("latest_glucose_mg_dl"),
                    "mood_score": comp.get("latest_mood_score"),
                    "streak_days": comp.get("streak_days"),
                    "sleep_hours": metrics_map.get("sleep_hours", {}).get("value"),
                    "readiness_score": metrics_map.get("readiness_score", {}).get("value"),
                    "active_alerts": [{"severity": a.get("severity"), "rule": a.get("threshold_rule")} for a in alerts_list[:3]],
                    "top_historical_precedent": (
                        {"mission": matches[0]["mission"], "title": matches[0]["title"], "checks": matches[0]["how_to_figure_it_out"][:2]}
                        if matches
                        else None
                    ),
                    "open_symptoms": [{"region": s.get("body_region"), "text": s.get("symptom_text"), "severity": s.get("severity")} for s in open_list[:4]],
                }

            if fname == "compare_historical_incidents":
                tel_obj = latest_frame.model_dump() if latest_frame is not None else get_latest_telemetry()
                alerts_list = get_alerts(status_filter="active")
                nasa_snap = get_nasa_live_bundle(fetch_live=False)
                sit = str(fargs.get("situation", "") or "")
                matches = match_historical_incidents(
                    frame_dict=tel_obj,
                    alerts=alerts_list,
                    query_text=sit,
                    donki_active=bool((nasa_snap.get("donki") or {}).get("radiation_alert_active")),
                    limit=2,
                )
                return {
                    "ok": True,
                    "matches": [
                        {
                            "mission": m["mission"],
                            "hazard": m["hazard_label"],
                            "title": m["title"],
                            "what_happened": m["what_happened"],
                            "verify_checks": m["how_to_figure_it_out"],
                            "actions": m["recommended_actions"],
                        }
                        for m in matches
                    ],
                }

            if fname == "log_crew_checkin":
                summary = save_crew_checkin(
                    crew_id="CREW-01",
                    mood_score=fargs.get("mood_score"),
                    mood_label=fargs.get("mood_label"),
                    hydration_delta_ml=float(fargs.get("hydration_delta_ml") or 0.0),
                    blood_glucose_mg_dl=fargs.get("blood_glucose_mg_dl"),
                    ultrasound_region=fargs.get("ultrasound_region"),
                    ultrasound_note=fargs.get("ultrasound_note"),
                    notes="Logged via Lunar voice tool",
                )
                generator.apply_checkin_override(summary)
                return {"ok": True, "compliance": summary}

            if fname == "set_simulation_mode":
                scen = fargs.get("scenario_name")
                ctrl = fargs.get("control_action")
                if scen:
                    generator.set_scenario(str(scen))
                    latest_frame = generator.generate_frame()
                if ctrl == "pause":
                    generator.is_paused = True
                elif ctrl == "resume":
                    generator.is_paused = False
                elif ctrl == "reset":
                    generator.reset()
                return {"ok": True, "active_scenario": generator.active_scenario, "is_paused": generator.is_paused}

            return {"ok": False, "error": f"Unknown tool '{fname}'"}

        live_model = os.environ.get("GEMINI_LIVE_MODEL", GEMINI_LIVE_DIALOG_MODEL)
        async with client.aio.live.connect(model=live_model, config=config) as session:
            await websocket.send_json({
                "type": "session_ready",
                "model": live_model,
                "assistant_name": "Lunar",
                "voice": "Aoede",
            })

            async def _browser_to_gemini():
                try:
                    while True:
                        raw = await websocket.receive_text()
                        msg = json.loads(raw)
                        mtype = msg.get("type")
                        if mtype == "audio" and msg.get("data"):
                            pcm_bytes = base64.b64decode(msg["data"])
                            await session.send_realtime_input(
                                audio=genai_types.Blob(
                                    data=pcm_bytes,
                                    mime_type=msg.get("mime_type", "audio/pcm;rate=16000"),
                                )
                            )
                        elif mtype == "video" and msg.get("data"):
                            raw_b64 = str(msg["data"])
                            if "," in raw_b64:
                                raw_b64 = raw_b64.split(",", 1)[1]
                            img_bytes = base64.b64decode(raw_b64)
                            await session.send_realtime_input(
                                media=genai_types.Blob(
                                    data=img_bytes,
                                    mime_type=msg.get("mime_type", "image/jpeg"),
                                )
                            )
                        elif mtype == "audio_stream_end":
                            await session.send_realtime_input(audio_stream_end=True)
                        elif mtype == "text" and msg.get("text"):
                            user_text = str(msg["text"]).strip()
                            await session.send_client_content(
                                turns=genai_types.Content(
                                    role="user",
                                    parts=[genai_types.Part(text=user_text)],
                                ),
                                turn_complete=True,
                            )
                except WebSocketDisconnect:
                    pass
                except Exception:
                    pass

            async def _gemini_to_browser():
                transcript_buf: List[str] = []
                try:
                    # google-genai AsyncSession.receive() exits on turn_complete, so loop continuously across turns
                    while True:
                        async for response in session.receive():
                            if getattr(response, "tool_call", None):
                                func_resps = []
                                for fc in response.tool_call.function_calls:
                                    try:
                                        res_obj = await _execute_live_tool(fc.name, dict(fc.args or {}))
                                    except Exception as ex:
                                        res_obj = {"ok": False, "error": str(ex)}
                                    func_resps.append(
                                        genai_types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response=res_obj,
                                        )
                                    )
                                if func_resps:
                                    await session.send_tool_response(function_responses=func_resps)

                            sc = getattr(response, "server_content", None)
                            if not sc:
                                continue
                            if sc.model_turn and sc.model_turn.parts:
                                for part in sc.model_turn.parts:
                                    inline = getattr(part, "inline_data", None)
                                    if inline and getattr(inline, "data", None):
                                        raw_audio = inline.data
                                        b64_audio = (
                                            base64.b64encode(raw_audio).decode("ascii")
                                            if isinstance(raw_audio, (bytes, bytearray))
                                            else str(raw_audio)
                                        )
                                        await websocket.send_json({
                                            "type": "audio",
                                            "data": b64_audio,
                                            "mime_type": getattr(inline, "mime_type", None) or "audio/pcm;rate=24000",
                                        })
                            if getattr(sc, "input_transcription", None) and sc.input_transcription.text:
                                utext = sc.input_transcription.text.strip()
                                if utext:
                                    await websocket.send_json({"type": "input_transcript", "text": utext})
                            if getattr(sc, "output_transcription", None) and sc.output_transcription.text:
                                otext = sanitize_agent_output(sc.output_transcription.text)
                                transcript_buf.append(otext)
                                await websocket.send_json({"type": "output_transcript", "text": otext})
                            if getattr(sc, "interrupted", False):
                                transcript_buf.clear()
                                await websocket.send_json({"type": "interrupted"})
                            if getattr(sc, "turn_complete", False):
                                full_turn = sanitize_agent_output("".join(transcript_buf).strip())
                                transcript_buf.clear()
                                await websocket.send_json({"type": "turn_complete", "text": full_turn})
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    print(f"[Lunar Live] _gemini_to_browser closed: {exc}")
                    try:
                        await websocket.send_json({"type": "error", "message": str(exc)})
                    except Exception:
                        pass

            t1 = asyncio.create_task(_browser_to_gemini())
            t2 = asyncio.create_task(_gemini_to_browser())
            await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
            t1.cancel()
            t2.cancel()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# Mount static files for the frontend dashboard
web_dir = Path(__file__).resolve().parent.parent.parent / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
