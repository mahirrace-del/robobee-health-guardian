"""
Automated Tests — SQLite Persistence Layer and Bounded Tables
"""

import pytest
from src.compute.generator import TelemetryGenerator
from src.storage.db import (
    init_db,
    save_telemetry_frame,
    get_latest_telemetry,
    get_telemetry_history,
    save_alert,
    get_alerts,
    acknowledge_alert_db,
    resolve_alert_db,
    get_registered_devices
)


def test_database_initialization_and_device_registry():
    init_db()
    devices = get_registered_devices()
    assert len(devices) >= 3
    ids = [d["device_id"] for d in devices]
    assert "esp32-wearable-01" in ids
    assert "huskylens-01" in ids


def test_save_and_retrieve_telemetry():
    init_db()
    gen = TelemetryGenerator(seed=99)
    frame = gen.generate_frame(step=1)
    
    save_telemetry_frame(frame.model_dump())
    
    latest = get_latest_telemetry(crew_id="CREW-01")
    assert latest is not None
    assert latest["crew_id"] == "CREW-01"
    assert "heart_rate" in latest
    
    history = get_telemetry_history(limit=5)
    assert len(history) >= 1


def test_alert_lifecycle_workflow():
    init_db()
    test_alert = {
        "id": "ALT-TEST-99",
        "timestamp": "2026-10-14T00:00:00Z",
        "crew_id": "CREW-01",
        "severity": "warning",
        "status": "active",
        "trigger_parameter": "heart_rate",
        "observed_value": 105.2,
        "unit": "bpm",
        "threshold_rule": "Test Rule",
        "quality_flag": "valid",
        "explanation": "Test explanation.",
        "suggested_actions": ["Action 1"],
        "literature_citation": None
    }
    
    save_alert(test_alert)
    alerts = get_alerts()
    saved = next((a for a in alerts if a["id"] == "ALT-TEST-99"), None)
    assert saved is not None
    assert saved["status"] == "active"
    
    # Acknowledge
    ack_res = acknowledge_alert_db("ALT-TEST-99", operator_id="Test Surgeon")
    assert ack_res is True
    alerts_after_ack = get_alerts()
    acked = next((a for a in alerts_after_ack if a["id"] == "ALT-TEST-99"), None)
    assert acked["status"] == "acknowledged"
    assert acked["acknowledged_by"] == "Test Surgeon"
    
    # Resolve
    resolve_res = resolve_alert_db("ALT-TEST-99", notes="Issue addressed", operator_id="Test Surgeon")
    assert resolve_res is True
    resolved = next((a for a in get_alerts() if a["id"] == "ALT-TEST-99"), None)
    assert resolved["status"] == "resolved"
    assert resolved["resolution_notes"] == "Issue addressed"
