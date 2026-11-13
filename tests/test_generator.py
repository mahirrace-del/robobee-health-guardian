"""
Automated Tests — High-Fidelity Telemetry Generator and Scenarios
"""

import pytest
from src.compute.generator import TelemetryGenerator
from src.models.telemetry import QualityFlag, SourceMode


def test_generator_initialization_and_reproducibility():
    gen1 = TelemetryGenerator(seed=123)
    frame1 = gen1.generate_frame(step=0)
    
    gen2 = TelemetryGenerator(seed=123)
    frame2 = gen2.generate_frame(step=0)
    
    assert frame1.heart_rate.value == frame2.heart_rate.value
    assert frame1.spo2.value == frame2.spo2.value
    assert frame1.source_mode == SourceMode.SIMULATED


def test_scenario_b_exercise_dynamics():
    gen = TelemetryGenerator(seed=42)
    gen.set_scenario("Scenario B: Exercise Session")
    
    # Check peak exercise step
    frame = gen.generate_frame(step=30)
    assert frame.exercise_type == "T2 Treadmill"
    assert frame.heart_rate.value > 120.0
    assert frame.respiration_rate.value > 20.0
    assert frame.exercise_load_w.value > 100.0


def test_scenario_c_sleep_deficit():
    gen = TelemetryGenerator(seed=42)
    gen.set_scenario("Scenario C: Sleep Deficit")
    
    frame = gen.generate_frame(step=5)
    assert frame.sleep_hours.value < 6.0
    assert frame.readiness_score.value < 65.0
    assert frame.reaction_time_ms.value > 300.0


def test_scenario_e_co2_excursion():
    gen = TelemetryGenerator(seed=42)
    gen.set_scenario("Scenario E: Environmental CO2 Excursion")
    
    # Progress step into excursion
    frame = gen.generate_frame(step=50)
    assert frame.co2_pp_mmhg.value > 3.0


def test_scenario_f_sensor_failure_handling():
    gen = TelemetryGenerator(seed=42)
    gen.set_scenario("Scenario F: Sensor Failure")
    
    # Step into missing sample cycle
    frame = gen.generate_frame(step=30)
    assert frame.heart_rate.value is None
    assert frame.heart_rate.quality == QualityFlag.MISSING
    assert frame.spo2.value is None


def test_generator_pause_and_reset():
    gen = TelemetryGenerator(seed=42)
    f1 = gen.generate_frame()
    gen.is_paused = True
    f2 = gen.generate_frame()
    assert gen.step_index == 1
    
    gen.reset()
    assert gen.step_index == 0
