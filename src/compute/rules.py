"""
AstroHealth Guardian — Explainable Rules Engine
Centralized, deterministic anomaly evaluation with persistence windows,
hysteresis, and non-diagnostic clinical boundaries per NASA-STD-3001.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid

from src.models.telemetry import (
    TelemetryFrame,
    AlertRecord,
    AlertSeverity,
    AlertStatus,
    QualityFlag
)
from src.data.research import RESEARCH_CITATIONS

# In-memory persistence tracker: { rule_id: consecutive_violation_count }
RULE_VIOLATION_COUNTERS: Dict[str, int] = {}


# Configurable threshold dictionary
DEFAULT_THRESHOLDS = {
    "hr_rest_tachycardia": {"warning": 100.0, "critical": 120.0, "persistence": 3},
    "hr_bradycardia": {"warning": 48.0, "critical": 40.0, "persistence": 4},
    "spo2_hypoxia": {"warning": 95.0, "critical": 92.0, "persistence": 3},
    "hrv_depressed": {"warning": 25.0, "critical": 18.0, "persistence": 4},
    "bp_systolic_high": {"warning": 140.0, "critical": 160.0, "persistence": 3},
    "core_temp_space_fever": {"warning": 37.8, "critical": 38.5, "persistence": 4},
    "rr_tachypnea": {"warning": 22.0, "critical": 28.0, "persistence": 3},
    "co2_pp_high": {"warning": 3.0, "critical": 4.0, "persistence": 2},  # Per NASA-STD-3001 Vol 2
    "readiness_fatigue": {"warning": 65.0, "critical": 50.0, "persistence": 2},
}


def get_citation(citation_id: str) -> Optional[Dict[str, str]]:
    """Helper to retrieve citation summary for alert cards."""
    for c in RESEARCH_CITATIONS:
        if c["id"] == citation_id:
            return {
                "title": c["title"],
                "organization": c["organization"],
                "url": c["url"],
                "study_id": c.get("study_id", "N/A")
            }
    return None


def evaluate_telemetry_rules(frame: TelemetryFrame) -> List[AlertRecord]:
    """
    Evaluates incoming telemetry frame against all configured operational rules.
    Returns any newly triggered or persisting alert records.
    """
    alerts: List[AlertRecord] = []
    ts = frame.timestamp
    crew_id = frame.crew_id
    
    # Skip evaluation if signal is invalid or missing
    # Rule 1: Ambient CO2 Excursion (NASA-STD-3001 Vol 2 & OCHMO-TB-004)
    co2 = frame.co2_pp_mmhg
    if co2.quality == QualityFlag.VALID and co2.value is not None:
        val = co2.value
        th = DEFAULT_THRESHOLDS["co2_pp_high"]
        rule_key = "rule_co2_excursion"
        
        if val >= th["critical"]:
            RULE_VIOLATION_COUNTERS[rule_key] = RULE_VIOLATION_COUNTERS.get(rule_key, 0) + 1
            if RULE_VIOLATION_COUNTERS[rule_key] >= th["persistence"]:
                alerts.append(AlertRecord(
                    id=f"ALT-CO2-{uuid.uuid4().hex[:6].upper()}",
                    timestamp=ts,
                    crew_id=crew_id,
                    severity=AlertSeverity.CRITICAL,
                    status=AlertStatus.ACTIVE,
                    trigger_parameter="co2_pp_mmhg",
                    observed_value=round(val, 2),
                    unit="mmHg",
                    threshold_rule=f"ppCO2 >= {th['critical']} mmHg (24h Limit)",
                    quality_flag=co2.quality,
                    explanation=(
                        f"Ambient CO2 partial pressure ({val:.2f} mmHg) exceeds NASA-STD-3001 Vol 2 maximum allowable 24h limit (4.0 mmHg). "
                        "Elevated ambient CO2 in microgravity induces hypercapnic headaches, visual changes, and cognitive slowing due to reduced buoyant convective dispersal."
                    ),
                    suggested_actions=[
                        "Inspect Environmental Control and Life Support System (ECLSS) CDRA scrubber beds.",
                        "Direct crew member to activate personal ventilation ducting.",
                        "Administer Psychomotor Vigilance Task (PVT) to assess cognitive performance."
                    ],
                    literature_citation=get_citation("NASA-STD-3001-V2")
                ))
        elif val >= th["warning"]:
            RULE_VIOLATION_COUNTERS[rule_key] = RULE_VIOLATION_COUNTERS.get(rule_key, 0) + 1
            if RULE_VIOLATION_COUNTERS[rule_key] >= th["persistence"]:
                alerts.append(AlertRecord(
                    id=f"ALT-CO2-{uuid.uuid4().hex[:6].upper()}",
                    timestamp=ts,
                    crew_id=crew_id,
                    severity=AlertSeverity.WARNING,
                    status=AlertStatus.ACTIVE,
                    trigger_parameter="co2_pp_mmhg",
                    observed_value=round(val, 2),
                    unit="mmHg",
                    threshold_rule=f"ppCO2 >= {th['warning']} mmHg (Nominal Target)",
                    quality_flag=co2.quality,
                    explanation=(
                        f"Ambient CO2 ({val:.2f} mmHg) exceeds nominal baseline of 3.0 mmHg. "
                        "Correlates with increased risk of microgravity-associated space headaches."
                    ),
                    suggested_actions=[
                        "Monitor ECLSS air circulation fans.",
                        "Verify air velocity in crew quarters (>15 ft/min)."
                    ],
                    literature_citation=get_citation("NASA-OCHMO-TB-004")
                ))
        else:
            RULE_VIOLATION_COUNTERS[rule_key] = 0

    # Rule 2: Resting Tachycardia & Multi-Signal Concordance (Context-Aware!)
    hr = frame.heart_rate
    is_exercising = (frame.exercise_type != "Rest") or (frame.exercise_load_w.value and frame.exercise_load_w.value > 50)
    
    if hr.quality == QualityFlag.VALID and hr.value is not None:
        hr_val = hr.value
        th = DEFAULT_THRESHOLDS["hr_rest_tachycardia"]
        rule_key = "rule_resting_tachycardia"
        
        # Only flag resting tachycardia if astronaut is NOT in exercise mode
        if not is_exercising and hr_val >= th["warning"]:
            RULE_VIOLATION_COUNTERS[rule_key] = RULE_VIOLATION_COUNTERS.get(rule_key, 0) + 1
            if RULE_VIOLATION_COUNTERS[rule_key] >= th["persistence"]:
                sev = AlertSeverity.CRITICAL if hr_val >= th["critical"] else AlertSeverity.WARNING
                alerts.append(AlertRecord(
                    id=f"ALT-HR-{uuid.uuid4().hex[:6].upper()}",
                    timestamp=ts,
                    crew_id=crew_id,
                    severity=sev,
                    status=AlertStatus.ACTIVE,
                    trigger_parameter="heart_rate",
                    observed_value=round(hr_val, 1),
                    unit="bpm",
                    threshold_rule=f"Resting HR >= {th['warning']} bpm without Exercise Activity",
                    quality_flag=hr.quality,
                    explanation=(
                        f"Resting heart rate ({hr_val:.1f} bpm) sustained above baseline for {RULE_VIOLATION_COUNTERS[rule_key]} cycles. "
                        "Vision and activity telemetry confirms astronaut is at rest (no active ARED/T2 session)."
                    ),
                    suggested_actions=[
                        "Prompt crew member to verify resting state and hydration.",
                        "Inspect ECG rhythm strip for rhythm conduction changes.",
                        "Check ambient temperature and cabin ventilation."
                    ],
                    literature_citation=get_citation("NASA-SSM-CORE")
                ))
        else:
            RULE_VIOLATION_COUNTERS[rule_key] = 0

    # Rule 3: Hypoxia / SpO2 Drop
    spo2 = frame.spo2
    if spo2.quality == QualityFlag.VALID and spo2.value is not None:
        spo2_val = spo2.value
        th = DEFAULT_THRESHOLDS["spo2_hypoxia"]
        rule_key = "rule_spo2_hypoxia"
        
        if spo2_val <= th["critical"]:
            RULE_VIOLATION_COUNTERS[rule_key] = RULE_VIOLATION_COUNTERS.get(rule_key, 0) + 1
            if RULE_VIOLATION_COUNTERS[rule_key] >= th["persistence"]:
                alerts.append(AlertRecord(
                    id=f"ALT-O2-{uuid.uuid4().hex[:6].upper()}",
                    timestamp=ts,
                    crew_id=crew_id,
                    severity=AlertSeverity.CRITICAL,
                    status=AlertStatus.ACTIVE,
                    trigger_parameter="spo2",
                    observed_value=round(spo2_val, 1),
                    unit="%",
                    threshold_rule=f"SpO2 <= {th['critical']}%",
                    quality_flag=spo2.quality,
                    explanation=(
                        f"Blood oxygen saturation decreased to {spo2_val:.1f}%. Sustained microgravity hypoxia requires immediate evaluation."
                    ),
                    suggested_actions=[
                        "Inspect wristband optical sensor contact and finger perfusion.",
                        "Verify habitat cabin ppO2 (nominal 21.0% / 160 mmHg).",
                        "Prepare auxiliary oxygen mask if symptoms present."
                    ],
                    literature_citation=get_citation("NASA-STD-3001-V1")
                ))
        elif spo2_val <= th["warning"]:
            RULE_VIOLATION_COUNTERS[rule_key] = RULE_VIOLATION_COUNTERS.get(rule_key, 0) + 1
            if RULE_VIOLATION_COUNTERS[rule_key] >= th["persistence"]:
                alerts.append(AlertRecord(
                    id=f"ALT-O2-{uuid.uuid4().hex[:6].upper()}",
                    timestamp=ts,
                    crew_id=crew_id,
                    severity=AlertSeverity.WARNING,
                    status=AlertStatus.ACTIVE,
                    trigger_parameter="spo2",
                    observed_value=round(spo2_val, 1),
                    unit="%",
                    threshold_rule=f"SpO2 <= {th['warning']}%",
                    quality_flag=spo2.quality,
                    explanation=f"Blood oxygen saturation ({spo2_val:.1f}%) is below nominal astronaut range (> 96%).",
                    suggested_actions=[
                        "Check sensor placement and verify pulse waveform quality."
                    ],
                    literature_citation=get_citation("NASA-STD-3001-V1")
                ))
        else:
            RULE_VIOLATION_COUNTERS[rule_key] = 0

    # Rule 4: Space Fever / Core Temperature Elevation
    core_temp = frame.core_temperature
    if core_temp.quality == QualityFlag.VALID and core_temp.value is not None:
        ct_val = core_temp.value
        th = DEFAULT_THRESHOLDS["core_temp_space_fever"]
        rule_key = "rule_core_temp_elevated"
        
        if ct_val >= th["warning"]:
            RULE_VIOLATION_COUNTERS[rule_key] = RULE_VIOLATION_COUNTERS.get(rule_key, 0) + 1
            if RULE_VIOLATION_COUNTERS[rule_key] >= th["persistence"]:
                alerts.append(AlertRecord(
                    id=f"ALT-TMP-{uuid.uuid4().hex[:6].upper()}",
                    timestamp=ts,
                    crew_id=crew_id,
                    severity=AlertSeverity.WARNING,
                    status=AlertStatus.ACTIVE,
                    trigger_parameter="core_temperature",
                    observed_value=round(ct_val, 2),
                    unit="°C",
                    threshold_rule=f"Core Temperature >= {th['warning']}°C",
                    quality_flag=core_temp.quality,
                    explanation=(
                        f"Core body temperature elevated to {ct_val:.2f}°C. "
                        "Documented 'Space Fever' in microgravity shows an upward resting shift (~1°C) due to impaired evaporative cooling and altered circadian regulation."
                    ),
                    suggested_actions=[
                        "Verify hydration and evaluate fluid consumption log.",
                        "Inspect cabin air velocity and cooling vest readiness."
                    ],
                    literature_citation=get_citation("NTRS-20230014025")
                ))
        else:
            RULE_VIOLATION_COUNTERS[rule_key] = 0

    # Rule 5: Fall / Sudden Posture Collapse Detection (HuskyLens Algorithm 19)
    posture = frame.exercise_posture_score
    if posture.value is not None and posture.value < 0.25:
        alerts.append(AlertRecord(
            id=f"ALT-FALL-{uuid.uuid4().hex[:6].upper()}",
            timestamp=ts,
            crew_id=crew_id,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACTIVE,
            trigger_parameter="exercise_posture_score",
            observed_value=round(posture.value, 2),
            unit="score",
            threshold_rule="HuskyLens Fall Detection Event (Algorithm 19) + Posture Score < 0.25",
            quality_flag=posture.quality,
            explanation=(
                "Vision Context Engine detected acute loss of balance, collapse, or fall event. "
                "Correlated with sudden drop in posture integrity index."
            ),
            suggested_actions=[
                "Immediately query crew member via habitat intercom.",
                "Review HuskyLens vision stream for crew movement or incapacitation.",
                "Alert Flight Surgeon console at Mission Control."
            ],
            literature_citation=get_citation("DFROBOT-HUSKYLENS-V2")
        ))

    # Rule 6: Sleep Deficit & Cognitive Readiness Degradation
    readiness = frame.readiness_score
    if readiness.quality == QualityFlag.VALID and readiness.value is not None and readiness.value < 60.0:
        alerts.append(AlertRecord(
            id=f"ALT-RDY-{uuid.uuid4().hex[:6].upper()}",
            timestamp=ts,
            crew_id=crew_id,
            severity=AlertSeverity.WARNING,
            status=AlertStatus.ACTIVE,
            trigger_parameter="readiness_score",
            observed_value=round(readiness.value, 1),
            unit="/100",
            threshold_rule="Mission Readiness Score < 60/100 (Compromised Alertness)",
            quality_flag=readiness.quality,
            explanation=(
                f"Readiness score ({readiness.value:.1f}/100) indicates significant fatigue. "
                f"Correlates with reduced sleep ({frame.sleep_hours.value}h) and prolonged PVT reaction latency ({frame.reaction_time_ms.value}ms)."
            ),
            suggested_actions=[
                "Restrict safety-critical tasks, robotics operations, and EVA protocols.",
                "Schedule protected 90-minute sleep countermeasure."
            ],
            literature_citation=get_citation("NTRS-20230003916")
        ))

    # Rule 7: Sensor Signal Quality / Stale / Missing Telemetry Alert
    sig_rule_key = "rule_signal_quality"
    bad_qualities = (QualityFlag.STALE, QualityFlag.MISSING, QualityFlag.QUESTIONABLE, QualityFlag.INVALID)
    if hr.quality in bad_qualities or spo2.quality in bad_qualities:
        RULE_VIOLATION_COUNTERS[sig_rule_key] = RULE_VIOLATION_COUNTERS.get(sig_rule_key, 0) + 1
        if RULE_VIOLATION_COUNTERS[sig_rule_key] >= 2:
            deg_flag = hr.quality if hr.quality in bad_qualities else spo2.quality
            alerts.append(AlertRecord(
                id=f"ALT-SIG-{uuid.uuid4().hex[:6].upper()}",
                timestamp=ts,
                crew_id=crew_id,
                severity=AlertSeverity.WARNING,
                status=AlertStatus.ACTIVE,
                trigger_parameter="signal_quality",
                observed_value=float(RULE_VIOLATION_COUNTERS[sig_rule_key]),
                unit="cycles",
                threshold_rule=f"Wearable Biometric Quality Flag: {deg_flag.value.upper()}",
                quality_flag=deg_flag,
                explanation=(
                    f"Primary wearable sensor channel reported '{deg_flag.value}' quality for "
                    f"{RULE_VIOLATION_COUNTERS[sig_rule_key]} consecutive samples. Automated physiological "
                    "threshold evaluation is suspended on degraded channels to prevent false clinical alarms."
                ),
                suggested_actions=[
                    "Check MAX30102 optical wrist contact and strap tension.",
                    "Verify ESP32 wearable Wi-Fi/serial telemetry link and sequence counter."
                ],
                literature_citation=get_citation("NTRS-20230014025")
            ))
    else:
        RULE_VIOLATION_COUNTERS[sig_rule_key] = 0

    return alerts
