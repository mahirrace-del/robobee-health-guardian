"""
Automated Tests — FastAPI Endpoints, Health, Telemetry Ingestion, and Scenario Switching
"""

import pytest
from fastapi.testclient import TestClient
from src.api.stream import app

client = TestClient(app)


def test_api_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["service"] == "AstroHealth Guardian"
    assert "source_mode" in data


def test_get_telemetry_latest():
    response = client.get("/api/telemetry/latest")
    assert response.status_code == 200
    data = response.json()
    assert "heart_rate" in data
    assert "spo2" in data
    assert "co2_pp_mmhg" in data


def test_get_telemetry_history():
    response = client.get("/api/telemetry/history?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "records" in data
    assert "count" in data


def test_schema_v1_ingest_endpoint_valid():
    payload = {
        "schema_version": "1.0",
        "device_id": "esp32-wearable-01",
        "sequence": 105,
        "measurements": {
            "heart_rate": {"value": 73.2, "unit": "bpm", "quality": "valid"},
            "spo2": {"value": 98.4, "unit": "%", "quality": "valid"},
            "skin_temperature": {"value": 33.6, "unit": "°C", "quality": "valid"}
        }
    }
    response = client.post("/api/telemetry/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["mode"] == "live"


def test_schema_v1_ingest_endpoint_unphysical_value():
    payload = {
        "schema_version": "1.0",
        "device_id": "esp32-wearable-01",
        "sequence": 106,
        "measurements": {
            "heart_rate": {"value": 999.0, "unit": "bpm", "quality": "valid"} # Out of bounds
        }
    }
    response = client.post("/api/telemetry/ingest", json=payload)
    assert response.status_code == 422


def test_devices_endpoint():
    response = client.get("/api/devices")
    assert response.status_code == 200
    data = response.json()
    assert "devices" in data
    assert len(data["devices"]) >= 3


def test_research_citations_endpoint():
    response = client.get("/api/research")
    assert response.status_code == 200
    data = response.json()
    assert "citations" in data
    assert len(data["citations"]) >= 7
    # Verify no misuse of OSD-87/665 as human vitals
    ids = [c["id"] for c in data["citations"]]
    assert "NASA-STD-3001-V1" in ids
    assert "NASA-STD-3001-V2" in ids


def test_scenario_switching_endpoint():
    response = client.post("/api/simulation/scenario", json={"scenario_name": "Scenario B: Exercise Session"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "Exercise" in data["active_scenario"]


def test_simulation_control_endpoint():
    response = client.post("/api/simulation/control", json={"action": "pause"})
    assert response.status_code == 200
    assert response.json()["is_paused"] is True
    
    response = client.post("/api/simulation/control", json={"action": "resume"})
    assert response.status_code == 200
    assert response.json()["is_paused"] is False


def test_live_ingest_does_not_substitute_synthetic_fallbacks():
    """Verifies live hardware ingestion only populates provided sensors and marks unmeasured sensors missing."""
    payload = {
        "schema_version": "1.0",
        "device_id": "esp32-wearable-01",
        "sequence": 201,
        "measurements": {
            "heart_rate": {"value": 74.0, "unit": "bpm", "quality": "valid"},
            "spo2": {"value": 98.1, "unit": "%", "quality": "valid"}
        }
    }
    res = client.post("/api/telemetry/ingest", json=payload)
    assert res.status_code == 200

    latest = client.get("/api/telemetry/latest").json()
    assert latest["source_mode"] == "live"
    assert latest["heart_rate"]["value"] == 74.0
    assert latest["heart_rate"]["provenance"] == "live_hardware"
    # skin_temperature was omitted from payload -> must NOT default to 33.5 synthetic value
    assert latest["skin_temperature"]["value"] is None
    assert latest["skin_temperature"]["quality"] == "missing"
    assert latest["skin_temperature"]["provenance"] == "unavailable"
    # Unconnected habitat/tonometry sensors must also be marked missing in live mode
    assert latest["blood_pressure_systolic"]["value"] is None
    assert latest["blood_pressure_systolic"]["quality"] == "missing"
    assert latest["co2_pp_mmhg"]["value"] is None
    assert latest["co2_pp_mmhg"]["quality"] == "missing"

    # Reset back to simulated mode for subsequent tests
    client.post("/api/simulation/scenario", json={"scenario_name": "Scenario A: Routine Operations"})


def test_live_ingest_stale_and_future_timestamp_validation():
    """Verifies stale timestamps are flagged STALE and future timestamps are rejected."""
    from datetime import datetime, timezone, timedelta

    stale_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    res_stale = client.post("/api/telemetry/ingest", json={
        "schema_version": "1.0",
        "device_id": "esp32-wearable-01",
        "sequence": 202,
        "timestamp": stale_ts,
        "measurements": {
            "heart_rate": {"value": 71.0, "unit": "bpm", "quality": "valid"}
        }
    })
    assert res_stale.status_code == 200
    assert res_stale.json()["is_stale"] is True
    latest = client.get("/api/telemetry/latest").json()
    assert latest["heart_rate"]["quality"] == "stale"
    assert latest["heart_rate"]["provenance"] == "stale"

    future_ts = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    res_future = client.post("/api/telemetry/ingest", json={
        "schema_version": "1.0",
        "device_id": "esp32-wearable-01",
        "sequence": 203,
        "timestamp": future_ts,
        "measurements": {
            "heart_rate": {"value": 71.0, "unit": "bpm", "quality": "valid"}
        }
    })
    assert res_future.status_code == 422
    client.post("/api/simulation/scenario", json={"scenario_name": "Scenario A: Routine Operations"})


def test_vision_status_and_lunar_ask_body_focus():
    """Verifies honest camera standby status and Lunar structured body-focus output."""
    status_res = client.get("/api/vision/status")
    assert status_res.status_code == 200
    s_data = status_res.json()
    assert s_data["camera_connected"] is False
    assert s_data["confidence"] is None
    assert "left-shoulder-joint" in s_data["supported_body_regions"]

    # 1. Shoulder joint pain -> should select left-shoulder-joint and Skeleton layer
    ask_res = client.post("/api/vision/ask", json={
        "question": "My left shoulder joint hurts after the workout.",
        "crew_id": "CREW-TEST-1"
    })
    assert ask_res.status_code == 200
    a_data = ask_res.json()
    assert a_data["status"] == "success"
    assert a_data["assistant_name"] == "Lunar"
    assert a_data["body_region"] == "left-shoulder-joint"
    assert a_data["layer"] == "Skeleton"
    assert a_data["body_focus"]["action"] == "focusRegion"
    assert a_data["body_focus"]["options"]["layer"] == "Skeleton"
    assert a_data["vision_status"]["connected"] is False
    assert a_data["vision_status"]["confidence"] is None
    assert a_data["symptom_report"] is not None
    sym_id = a_data["symptom_report"]["id"]

    # 2. Follow-up confirming improvement -> intensity steps down only upon confirmation
    followup_res = client.post("/api/vision/ask", json={
        "question": "My left shoulder joint feels better today.",
        "crew_id": "CREW-TEST-1",
        "symptom_id": sym_id
    })
    assert followup_res.status_code == 200
    f_data = followup_res.json()
    assert f_data["symptom_report"]["user_status"] == "improving"
    assert f_data["symptom_report"]["current_intensity"] < a_data["symptom_report"]["initial_intensity"]

    # 3. Unsupported region name must be rejected with 422
    bad_region_res = client.post("/api/vision/ask", json={
        "question": "Focus on region",
        "body_region": "nonexistent-wing"
    })
    assert bad_region_res.status_code == 422


def test_symptom_highlight_does_not_auto_fade_without_followup():
    """Verifies a symptom logged 10 days ago retains its full initial intensity until a follow-up is confirmed."""
    from datetime import datetime, timezone, timedelta
    from src.storage.db import create_symptom_report

    ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    rep = create_symptom_report(
        crew_id="CREW-TIMETEST",
        body_region="right-finger",
        symptom_text="Small cut on right index finger",
        initial_intensity=0.7,
        created_at=ten_days_ago
    )
    assert rep["current_intensity"] == 0.7

    # Revisiting without confirming improvement must keep intensity at 0.7
    revisit = client.post("/api/vision/ask", json={
        "question": "Let's check my right index finger.",
        "crew_id": "CREW-TIMETEST"
    }).json()
    assert revisit["body_region"] == "right-finger"
    assert revisit["intensity"] == 0.7
    assert revisit["follow_up_prompt"] is not None

    # Confirming resolution via /api/symptoms/{id}/followup clears the highlight
    resolve_res = client.post(f"/api/symptoms/{rep['id']}/followup", json={
        "status_update": "resolved",
        "notes": "Skin fully closed and healed."
    })
    assert resolve_res.status_code == 200
    r_data = resolve_res.json()
    assert r_data["symptom_report"]["user_status"] == "resolved"
    assert r_data["symptom_report"]["current_intensity"] == 0.0
    assert r_data["body_focus"]["action"] == "clearFocus"

    # Check reminders endpoint
    rem_res = client.get("/api/symptoms/reminders?crew_id=CREW-TEST-1")
    assert rem_res.status_code == 200
    assert rem_res.json()["delivery_mechanism"] == "in_console_pull"
    assert rem_res.json()["background_push_daemon_active"] is False


def test_lunar_gemini_status_and_voice_endpoints():
    """Verifies Lunar Gemini status endpoint, model inventory, and TTS speak validation."""
    st_res = client.get("/api/lunar/status")
    assert st_res.status_code == 200
    st = st_res.json()
    assert "gemini-3.5-flash-lite" in st["conversational_models"]
    assert "gemini-3.8-flash-tts" in st["tts_models"]
    assert st["live_audio_model"] == "gemini-3.8-live"

    # Empty speak request is rejected with 422
    bad_speak = client.post("/api/lunar/speak", json={"text": "   "})
    assert bad_speak.status_code == 422


def test_autonomous_webcam_greeting_and_voice_ui_actions():
    """
    Verifies:
    1. Laptop camera frame face recognition + initial spoken greeting (`POST /api/lunar/vision-check`).
    2. Autonomous 3D shoulder zoom + pain marker trademark + 3 follow-up questions on 'I have some pain on the shoulder'.
    3. Autonomous vital card inspection (`card-bp`, `card-spo2`, `card-hr`) on 'let me check the pressure and oxygen level'.
    """
    dummy_b64 = "data:image/jpeg;base64," + ("A" * 128)
    vis_res = client.post("/api/lunar/vision-check", json={
        "image_base64": dummy_b64,
        "crew_id": "CREW-01",
        "is_initial_greeting": True,
        "include_audio": False,
    })
    assert vis_res.status_code == 200
    vdata = vis_res.json()
    assert vdata["connected"] is True
    assert vdata["face_recognized"] is True
    assert "Crew One" in vdata["crew_name"]
    assert "Crew One" in vdata["greeting_text"]
    assert "how are you doing" in vdata["greeting_text"].lower()

    # Shoulder pain voice command -> autonomous 3D focus + pain trademark + 3 follow-up questions
    shoulder_res = client.post("/api/vision/ask", json={
        "question": "I have some pain on the shoulder",
        "crew_id": "CREW-VOICE-TEST",
        "use_gemini": False,
    })
    assert shoulder_res.status_code == 200
    sdata = shoulder_res.json()
    assert sdata["body_region"] in ("right-shoulder", "left-shoulder", "right-shoulder-joint", "left-shoulder-joint")
    assert any(a["action"] == "focus_body" and a.get("is_pain_marker") is True for a in sdata["ui_actions"])
    focus_action = next(a for a in sdata["ui_actions"] if a["action"] == "focus_body")
    assert "PAIN TRADEMARK" in focus_action["marker_label"]
    assert len(focus_action["follow_up_questions"]) == 3
    assert "how many days" in sdata["follow_up_prompt"].lower()

    # Blood pressure & oxygen voice check -> autonomous vital card scanning
    vitals_res = client.post("/api/vision/ask", json={
        "question": "Just let me check the pressure, let me check the oxygen level",
        "crew_id": "CREW-01",
        "use_gemini": False,
    })
    assert vitals_res.status_code == 200
    vtdata = vitals_res.json()
    assert any(
        a["action"] == "inspect_vitals" and "card-bp" in a["cards"] and "card-spo2" in a["cards"]
        for a in vtdata["ui_actions"]
    )
    assert "mmhg" in vtdata["answer"].lower()
    assert "oxygen" in vtdata["answer"].lower() or "spo2" in vtdata["answer"].lower()


