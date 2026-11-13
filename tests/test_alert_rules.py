"""
Automated Tests — Explainable Rules Engine, Persistence Windows, and Citations
"""

import pytest
from src.compute.generator import TelemetryGenerator
from src.compute.rules import evaluate_telemetry_rules, RULE_VIOLATION_COUNTERS
from src.models.telemetry import AlertSeverity, AlertStatus


def test_co2_excursion_triggers_critical_alert():
    gen = TelemetryGenerator(seed=42)
    gen.set_scenario("Scenario E: Environmental CO2 Excursion")
    
    # Reset counters
    RULE_VIOLATION_COUNTERS.clear()
    
    triggered_alerts = []
    # Advance generator into CO2 peak
    for i in range(50, 56):
        frame = gen.generate_frame(step=i)
        alerts = evaluate_telemetry_rules(frame)
        if alerts:
            triggered_alerts.extend(alerts)
            
    co2_alerts = [a for a in triggered_alerts if a.trigger_parameter == "co2_pp_mmhg"]
    assert len(co2_alerts) > 0
    assert co2_alerts[0].observed_value >= 3.0
    assert co2_alerts[0].literature_citation is not None
    assert "NASA-STD-3001" in co2_alerts[0].threshold_rule or "ppCO2" in co2_alerts[0].threshold_rule


def test_fall_event_immediate_trigger():
    gen = TelemetryGenerator(seed=42)
    gen.set_scenario("Scenario G: Fall Event")
    
    frame = gen.generate_frame(step=20)
    alerts = evaluate_telemetry_rules(frame)
    
    fall_alerts = [a for a in alerts if a.trigger_parameter == "exercise_posture_score"]
    assert len(fall_alerts) > 0
    assert fall_alerts[0].severity == AlertSeverity.CRITICAL
    assert "fall" in fall_alerts[0].explanation.lower()


def test_exercise_does_not_falsely_trigger_resting_tachycardia():
    gen = TelemetryGenerator(seed=42)
    gen.set_scenario("Scenario B: Exercise Session")
    
    RULE_VIOLATION_COUNTERS.clear()
    
    # Peak exercise step
    frame = gen.generate_frame(step=35)
    assert frame.heart_rate.value > 120.0
    assert frame.exercise_type == "T2 Treadmill"
    
    alerts = evaluate_telemetry_rules(frame)
    hr_alerts = [a for a in alerts if a.trigger_parameter == "heart_rate"]
    # Context-aware rule must NOT flag resting tachycardia when exercise is confirmed!
    assert len(hr_alerts) == 0
