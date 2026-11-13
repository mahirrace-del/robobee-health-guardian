"""
AstroHealth Guardian — SQLite Persistence Layer
Handles storage, bounded history, alert management, and device registration.
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import uuid

from src.models.telemetry import (
    SUPPORTED_BODY_REGIONS,
    validate_body_region,
    resolve_region_layer,
)

DB_DIR = Path("data")
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "astrohealth.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes tables and indexes for AstroHealth Guardian."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Telemetry Samples (Bounded)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                crew_id TEXT NOT NULL,
                source_mode TEXT NOT NULL,
                source_device TEXT NOT NULL,
                scenario_name TEXT,
                payload_json TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry_samples(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_crew ON telemetry_samples(crew_id)")
        
        # 2. Managed Alerts & Events
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                crew_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL,
                trigger_parameter TEXT NOT NULL,
                observed_value REAL NOT NULL,
                unit TEXT NOT NULL,
                threshold_rule TEXT NOT NULL,
                quality_flag TEXT NOT NULL,
                explanation TEXT NOT NULL,
                suggested_actions TEXT NOT NULL,
                literature_citation TEXT,
                acknowledged_at TEXT,
                acknowledged_by TEXT,
                resolved_at TEXT,
                resolved_by TEXT,
                resolution_notes TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(timestamp)")
        
        # 3. Device Registry
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                device_type TEXT NOT NULL,
                status TEXT NOT NULL,
                supported_metrics TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                total_packets INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0
            )
        """)
        
        # Seed default demo devices
        cursor.execute("""
            INSERT OR IGNORE INTO devices (device_id, name, device_type, status, supported_metrics, last_seen, total_packets, error_count)
            VALUES 
            ('esp32-wearable-01', 'Astronaut Bio-Wristband (ESP32 + MAX30102)', 'Wearable PPG', 'standby', '["heart_rate", "spo2", "skin_temperature"]', datetime('now'), 0, 0),
            ('huskylens-01', 'HuskyLens 2 Vision Sensor (Habitat Cam 1)', 'Edge AI Vision', 'standby', '["expression", "posture", "fall_detection"]', datetime('now'), 0, 0),
            ('env-habitat-01', 'Habitat Environmental Suite (Station Life Support)', 'Fixed Sensor Array', 'online', '["co2_pp_mmhg", "cabin_temp_c", "radiation"]', datetime('now'), 0, 0)
        """)

        # 4. Crew Symptom Reports & Follow-Up History
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symptom_reports (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                crew_id TEXT NOT NULL,
                body_region TEXT NOT NULL,
                region_label TEXT NOT NULL,
                layer TEXT NOT NULL,
                symptom_text TEXT NOT NULL,
                user_status TEXT NOT NULL,
                severity TEXT NOT NULL,
                initial_intensity REAL NOT NULL,
                current_intensity REAL NOT NULL,
                provenance TEXT NOT NULL,
                follow_up_history_json TEXT NOT NULL,
                next_followup_due_at TEXT,
                reminder_delivery_channel TEXT NOT NULL,
                human_review_needed INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_symptom_crew ON symptom_reports(crew_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_symptom_status ON symptom_reports(user_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_symptom_region ON symptom_reports(body_region)")
        
        conn.commit()


def save_telemetry_frame(frame_dict: Dict[str, Any]):
    """Persists a telemetry frame and bounds table to last 10,000 records."""
    ts = frame_dict.get("timestamp", datetime.now(timezone.utc).isoformat())
    crew_id = frame_dict.get("crew_id", "CREW-01")
    source_mode = frame_dict.get("source_mode", "simulated")
    source_device = frame_dict.get("source_device", "simulator")
    scenario = frame_dict.get("scenario_name", "Scenario A: Routine")
    payload = json.dumps(frame_dict)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO telemetry_samples (timestamp, crew_id, source_mode, source_device, scenario_name, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ts, crew_id, str(source_mode), source_device, scenario, payload))
        
        # Prune if too large to prevent runaway storage (Bounded Table)
        cursor.execute("""
            DELETE FROM telemetry_samples 
            WHERE id NOT IN (
                SELECT id FROM telemetry_samples ORDER BY id DESC LIMIT 5000
            )
        """)
        conn.commit()


def get_latest_telemetry(crew_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetches the latest stored telemetry sample."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if crew_id:
            cursor.execute("SELECT payload_json FROM telemetry_samples WHERE crew_id = ? ORDER BY id DESC LIMIT 1", (crew_id,))
        else:
            cursor.execute("SELECT payload_json FROM telemetry_samples ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            return json.loads(row["payload_json"])
    return None


def get_telemetry_history(limit: int = 120, crew_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns chronologically ordered telemetry frames."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if crew_id:
            cursor.execute("""
                SELECT payload_json FROM (
                    SELECT id, payload_json FROM telemetry_samples WHERE crew_id = ? ORDER BY id DESC LIMIT ?
                ) ORDER BY id ASC
            """, (crew_id, limit))
        else:
            cursor.execute("""
                SELECT payload_json FROM (
                    SELECT id, payload_json FROM telemetry_samples ORDER BY id DESC LIMIT ?
                ) ORDER BY id ASC
            """, (limit,))
        rows = cursor.fetchall()
        return [json.loads(row["payload_json"]) for row in rows]


def save_alert(alert_dict: Dict[str, Any]) -> str:
    """
    Saves or updates an alert record.
    For generated active operational alerts, deduplicates against an existing active
    alert for the same (crew_id, trigger_parameter, threshold_rule) so 1 Hz evaluations
    update the active alert instead of flooding the audit trail with duplicate UUIDs.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        alert_id = alert_dict["id"]
        status = alert_dict.get("status", "active")

        if status == "active" and not alert_id.startswith("ALT-TEST"):
            cursor.execute("""
                SELECT id FROM alerts
                WHERE crew_id = ? AND trigger_parameter = ? AND threshold_rule = ? AND status = 'active'
                ORDER BY timestamp DESC LIMIT 1
            """, (alert_dict["crew_id"], alert_dict["trigger_parameter"], alert_dict["threshold_rule"]))
            existing = cursor.fetchone()
            if existing:
                alert_id = existing["id"]
                alert_dict["id"] = alert_id

        cursor.execute("""
            INSERT OR REPLACE INTO alerts (
                id, timestamp, crew_id, severity, status, trigger_parameter, 
                observed_value, unit, threshold_rule, quality_flag, explanation, 
                suggested_actions, literature_citation, acknowledged_at, 
                acknowledged_by, resolved_at, resolved_by, resolution_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alert_id,
            alert_dict["timestamp"],
            alert_dict["crew_id"],
            alert_dict["severity"],
            status,
            alert_dict["trigger_parameter"],
            alert_dict["observed_value"],
            alert_dict["unit"],
            alert_dict["threshold_rule"],
            alert_dict.get("quality_flag", "valid"),
            alert_dict["explanation"],
            json.dumps(alert_dict.get("suggested_actions", [])),
            json.dumps(alert_dict.get("literature_citation", {})) if alert_dict.get("literature_citation") else None,
            alert_dict.get("acknowledged_at"),
            alert_dict.get("acknowledged_by"),
            alert_dict.get("resolved_at"),
            alert_dict.get("resolved_by"),
            alert_dict.get("resolution_notes")
        ))
        conn.commit()
        return alert_id


def get_alerts(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves alerts, optionally filtered by status."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if status_filter:
            cursor.execute("SELECT * FROM alerts WHERE status = ? ORDER BY timestamp DESC", (status_filter,))
        else:
            cursor.execute("SELECT * FROM alerts ORDER BY timestamp DESC")
        rows = cursor.fetchall()
        
        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "timestamp": r["timestamp"],
                "crew_id": r["crew_id"],
                "severity": r["severity"],
                "status": r["status"],
                "trigger_parameter": r["trigger_parameter"],
                "observed_value": r["observed_value"],
                "unit": r["unit"],
                "threshold_rule": r["threshold_rule"],
                "quality_flag": r["quality_flag"],
                "explanation": r["explanation"],
                "suggested_actions": json.loads(r["suggested_actions"]) if r["suggested_actions"] else [],
                "literature_citation": json.loads(r["literature_citation"]) if r["literature_citation"] else None,
                "acknowledged_at": r["acknowledged_at"],
                "acknowledged_by": r["acknowledged_by"],
                "resolved_at": r["resolved_at"],
                "resolved_by": r["resolved_by"],
                "resolution_notes": r["resolution_notes"]
            })
        return results


def acknowledge_alert_db(alert_id: str, operator_id: str = "Flight Surgeon") -> bool:
    """Marks an alert as acknowledged without deleting it."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE alerts 
            SET status = 'acknowledged', acknowledged_at = ?, acknowledged_by = ?
            WHERE id = ? AND status = 'active'
        """, (datetime.now(timezone.utc).isoformat(), operator_id, alert_id))
        conn.commit()
        return cursor.rowcount > 0


def resolve_alert_db(alert_id: str, notes: str, operator_id: str = "Flight Surgeon") -> bool:
    """Marks an alert as resolved with operator notes."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE alerts 
            SET status = 'resolved', resolved_at = ?, resolved_by = ?, resolution_notes = ?
            WHERE id = ?
        """, (datetime.now(timezone.utc).isoformat(), operator_id, notes, alert_id))
        conn.commit()
        return cursor.rowcount > 0


def update_device_status(device_id: str, status: str, packet_received: bool = False, is_error: bool = False):
    """Updates the device registry with packet metrics and health."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE devices 
            SET status = ?, 
                last_seen = datetime('now'),
                total_packets = total_packets + ?,
                error_count = error_count + ?
            WHERE device_id = ?
        """, (status, 1 if packet_received else 0, 1 if is_error else 0, device_id))
        conn.commit()


def get_registered_devices() -> List[Dict[str, Any]]:
    """Returns list of registered hardware devices and their connection health."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices ORDER BY name ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def _row_to_symptom_dict(r: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": r["id"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "crew_id": r["crew_id"],
        "body_region": r["body_region"],
        "region_label": r["region_label"],
        "layer": r["layer"],
        "symptom_text": r["symptom_text"],
        "user_status": r["user_status"],
        "severity": r["severity"],
        "initial_intensity": r["initial_intensity"],
        "current_intensity": r["current_intensity"],
        "provenance": r["provenance"],
        "follow_up_history": json.loads(r["follow_up_history_json"]) if r["follow_up_history_json"] else [],
        "next_followup_due_at": r["next_followup_due_at"],
        "reminder_delivery_channel": r["reminder_delivery_channel"],
        "human_review_needed": bool(r["human_review_needed"]),
    }


def create_symptom_report(
    crew_id: str,
    body_region: str,
    symptom_text: str,
    user_status: str = "reported",
    severity: str = "amber",
    initial_intensity: float = 0.6,
    layer: Optional[str] = None,
    provenance: str = "crew_self_report",
    followup_after_hours: float = 24.0,
    human_review_needed: bool = False,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Persists a validated crew symptom report.
    Highlight intensity never fades automatically by time; it only changes when
    a crew member or operator confirms a follow-up update.
    """
    valid_region = validate_body_region(body_region)
    if not valid_region:
        raise ValueError(f"Unsupported body_region '{body_region}'. Must be one of {sorted(SUPPORTED_BODY_REGIONS.keys())}")

    region_meta = SUPPORTED_BODY_REGIONS[valid_region]
    resolved_layer = resolve_region_layer(valid_region, layer)
    clamped_intensity = round(max(0.0, min(1.0, float(initial_intensity))), 2)
    resolved_severity = severity if severity in ("red", "amber", "green") else "amber"

    now_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    due_iso = (now_dt + timedelta(hours=max(0.1, float(followup_after_hours)))).isoformat()
    sym_id = f"SYM-{uuid.uuid4().hex[:8].upper()}"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO symptom_reports (
                id, created_at, updated_at, crew_id, body_region, region_label, layer,
                symptom_text, user_status, severity, initial_intensity, current_intensity,
                provenance, follow_up_history_json, next_followup_due_at,
                reminder_delivery_channel, human_review_needed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sym_id,
            now_iso,
            now_iso,
            crew_id,
            valid_region,
            region_meta["label"],
            resolved_layer,
            symptom_text,
            user_status,
            resolved_severity,
            clamped_intensity,
            clamped_intensity,
            provenance,
            json.dumps([]),
            due_iso,
            "in_console_pull",
            1 if human_review_needed else 0,
        ))
        conn.commit()

    return get_symptom_report_by_id(sym_id)


def get_symptom_report_by_id(symptom_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single symptom report by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM symptom_reports WHERE id = ?", (symptom_id,))
        row = cursor.fetchone()
        if row:
            return _row_to_symptom_dict(row)
    return None


def get_symptom_reports(
    crew_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    body_region: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieves symptom reports ordered from newest to oldest."""
    clauses = []
    params: List[Any] = []
    if crew_id:
        clauses.append("crew_id = ?")
        params.append(crew_id)
    if status_filter:
        if status_filter == "open":
            clauses.append("user_status != 'resolved'")
        else:
            clauses.append("user_status = ?")
            params.append(status_filter)
    if body_region:
        clauses.append("body_region = ?")
        params.append(body_region)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM symptom_reports {where_sql} ORDER BY updated_at DESC", tuple(params))
        rows = cursor.fetchall()
        return [_row_to_symptom_dict(r) for r in rows]


def record_symptom_followup(
    symptom_id: str,
    status_update: str,
    new_intensity: Optional[float] = None,
    notes: str = "",
    actor: str = "CREW-01",
    followup_after_hours: float = 24.0,
) -> Optional[Dict[str, Any]]:
    """
    Records a confirmed symptom follow-up and updates highlight intensity/severity
    strictly according to the documented follow-up protocol (never by elapsed time alone).
    """
    existing = get_symptom_report_by_id(symptom_id)
    if not existing:
        return None

    normalized_status = status_update.strip().lower()
    prev_status = existing["user_status"]
    prev_intensity = float(existing["current_intensity"])
    human_review = bool(existing["human_review_needed"])

    if normalized_status in ("resolved", "healed", "gone", "cleared"):
        target_status = "resolved"
        calc_intensity = 0.0 if new_intensity is None else round(max(0.0, min(1.0, float(new_intensity))), 2)
        target_severity = "green"
    elif normalized_status in ("improving", "improved", "better"):
        target_status = "improving"
        if new_intensity is not None:
            calc_intensity = round(max(0.0, min(1.0, float(new_intensity))), 2)
        else:
            calc_intensity = round(max(0.2, prev_intensity - 0.25), 2)
        target_severity = "green" if calc_intensity < 0.4 else "amber"
    elif normalized_status in ("worsened", "worse", "severe"):
        target_status = "worsened"
        if new_intensity is not None:
            calc_intensity = round(max(0.0, min(1.0, float(new_intensity))), 2)
        else:
            calc_intensity = round(min(1.0, prev_intensity + 0.25), 2)
        target_severity = "red"
        human_review = True
    else:
        target_status = "unchanged"
        calc_intensity = prev_intensity if new_intensity is None else round(max(0.0, min(1.0, float(new_intensity))), 2)
        target_severity = existing["severity"]

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    next_due = None if target_status == "resolved" else (now_dt + timedelta(hours=max(0.1, float(followup_after_hours)))).isoformat()

    history = existing["follow_up_history"]
    history.append({
        "timestamp": now_iso,
        "actor": actor,
        "previous_status": prev_status,
        "new_status": target_status,
        "previous_intensity": prev_intensity,
        "new_intensity": calc_intensity,
        "notes": notes or f"Crew follow-up confirmed status: {target_status}",
        "provenance": "crew_followup_confirmed",
    })

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE symptom_reports
            SET updated_at = ?,
                user_status = ?,
                severity = ?,
                current_intensity = ?,
                provenance = 'crew_followup_confirmed',
                follow_up_history_json = ?,
                next_followup_due_at = ?,
                human_review_needed = ?
            WHERE id = ?
        """, (
            now_iso,
            target_status,
            target_severity,
            calc_intensity,
            json.dumps(history),
            next_due,
            1 if human_review else 0,
            symptom_id,
        ))
        conn.commit()

    return get_symptom_report_by_id(symptom_id)


def get_due_symptom_reminders(
    crew_id: Optional[str] = None,
    reference_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Returns scheduled follow-up check-ins for open symptoms.
    Explicitly labels delivery as 'in_console_pull' (never claims an external push was sent).
    """
    ref_dt = reference_time or datetime.now(timezone.utc)
    open_reports = get_symptom_reports(crew_id=crew_id, status_filter="open")
    reminders = []
    for rep in open_reports:
        due_str = rep.get("next_followup_due_at")
        is_due = False
        if due_str:
            try:
                due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                is_due = ref_dt >= due_dt
            except Exception:
                is_due = False
        reminders.append({
            "symptom_id": rep["id"],
            "crew_id": rep["crew_id"],
            "body_region": rep["body_region"],
            "region_label": rep["region_label"],
            "layer": rep["layer"],
            "symptom_text": rep["symptom_text"],
            "user_status": rep["user_status"],
            "current_intensity": rep["current_intensity"],
            "severity": rep["severity"],
            "scheduled_due_at": due_str,
            "is_due": is_due,
            "delivery_channel": "in_console_pull",
            "external_push_sent": False,
            "delivery_note": (
                "Surfaced on-demand in console/Lunar chat when queried. No external push/notification daemon is connected."
            ),
            "prompt": (
                f"Follow-up check on your reported {rep['region_label'].lower()} concern "
                f"('{rep['symptom_text']}'): has it improved, remained unchanged, or worsened?"
            ),
        })
    return reminders
