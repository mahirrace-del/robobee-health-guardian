"""
AstroHealth Guardian — High-Fidelity Telemetry Generator
Generates realistic, temporally coherent demonstration telemetry across all 7 scenarios:
  Scenario A: Routine operations (Nominal baselines)
  Scenario B: Exercise session (T2 / ARED exertion & recovery)
  Scenario C: Sleep deficit (Low sleep, high PVT reaction latency, low readiness)
  Scenario D: Physiological anomaly (Resting tachycardia + SpO2 drop + HRV collapse)
  Scenario E: Environmental CO2 excursion (ppCO2 spike > 4.0 mmHg)
  Scenario F: Sensor failure (Frozen signals, questionable quality, missing packets)
  Scenario G: Fall event (Acute posture collapse to 0.12 with autonomic response)
  Scenario H: Solar Particle Event (SPE Radiation surge > 5,000 µGy/day)

Notice: Generated data represents synthetic engineering approximations for demonstration
and testing purposes; not flight-certified clinical measurements.
"""

import math
import random
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

from src.models.telemetry import (
    TelemetryFrame,
    MeasurementItem,
    QualityFlag,
    SourceMode
)


class TelemetryGenerator:
    def __init__(self, seed: Optional[int] = 42):
        if seed is not None:
            random.seed(seed)
        self.step_index = 0
        self.active_scenario = "Scenario A: Routine Operations"
        self.is_paused = False
        self.start_time = datetime.now(timezone.utc)
        
        # Base healthy astronaut parameters
        self.base_hr = 68.0
        self.base_spo2 = 98.4
        self.base_hrv = 56.0
        self.base_sbp = 118.0
        self.base_dbp = 76.0
        self.base_core_temp = 37.1  # NASA Space Fever baseline
        self.base_skin_temp = 33.4
        self.base_rr = 14.0
        self.base_co2 = 2.4  # mmHg
        self.base_readiness = 92.0
        self.checkin_override: Dict[str, Any] = {}

    def apply_checkin_override(self, summary: Dict[str, Any]):
        """Applies latest crew hydration, glucose, mood, and ultrasound self-reports."""
        self.checkin_override = dict(summary or {})

    def set_scenario(self, scenario_name: str):
        """Sets the active scenario and resets step counter."""
        self.active_scenario = scenario_name
        self.step_index = 0

    def reset(self):
        """Resets the generator state."""
        self.step_index = 0
        self.start_time = datetime.now(timezone.utc)

    def generate_frame(self, step: Optional[int] = None) -> TelemetryFrame:
        """
        Generates a single continuous TelemetryFrame according to the active scenario.
        """
        if step is not None:
            self.step_index = step
            
        i = self.step_index
        if not self.is_paused:
            self.step_index += 1
            
        now_ts = (self.start_time + timedelta(seconds=i)).isoformat()
        scenario = self.active_scenario
        
        # Default baseline noise
        hr_noise = math.sin(i * 0.1) * 2.0 + random.uniform(-1.0, 1.0)
        spo2_noise = random.uniform(-0.3, 0.3)
        hrv_noise = math.cos(i * 0.08) * 3.0 + random.uniform(-1.5, 1.5)
        co2_noise = random.uniform(-0.1, 0.1)
        temp_noise = random.uniform(-0.05, 0.05)
        
        # Initialize default values
        hr = self.base_hr + hr_noise
        spo2 = self.base_spo2 + spo2_noise
        hrv = self.base_hrv + hrv_noise
        sbp = self.base_sbp + random.uniform(-2.0, 2.0)
        dbp = self.base_dbp + random.uniform(-1.5, 1.5)
        core_t = self.base_core_temp + temp_noise
        skin_t = self.base_skin_temp + temp_noise
        rr = self.base_rr + random.uniform(-0.5, 0.5)
        co2_pp = self.base_co2 + co2_noise
        
        sleep_h = 7.4
        sleep_eff = 86.0
        sleep_wake_count = 2
        pvt_reaction = 245.0
        pvt_lapses = 0
        readiness = self.base_readiness
        
        exercise_type = "Rest"
        exercise_load = 0.0
        exercise_mins = 0
        posture = round(random.uniform(0.92, 0.99), 2)
        expression = "neutral"
        context_note = "Normal orbital station routines."
        quality_status = QualityFlag.VALID
        rad_rate = 315.0
        glucose_val = float(self.checkin_override.get("latest_glucose_mg_dl") or 94.0)
        hydration_ml = float(self.checkin_override.get("hydration_total_ml") or 2100.0)
        hydration_pct = float(self.checkin_override.get("hydration_pct") or 84.0)
        mood_val = float(self.checkin_override.get("latest_mood_score") or 4.2)
        mood_lbl = str(self.checkin_override.get("latest_mood_label") or "steady")
        ultrasound_note = str(self.checkin_override.get("latest_ultrasound") or "Nominal • Last IJV / SANS Check Clear")

        # --- SCENARIO LOGIC ---
        if "Scenario B" in scenario or "Exercise" in scenario:
            # Exercise curve: warmup (0-15s), peak exercise (15-45s), recovery (45-70s)
            cycle_pos = i % 75
            if cycle_pos < 15:
                # Warmup
                exercise_type = "T2 Treadmill"
                exercise_load = 60.0 + cycle_pos * 4.0
                exercise_mins = 15
                hr = self.base_hr + 20.0 + (cycle_pos * 2.5)
                rr = 16.0 + (cycle_pos * 0.5)
                posture = 0.95
                expression = "focused"
                context_note = "T2 Treadmill warmup protocol."
            elif cycle_pos < 50:
                # Peak aerobic workload
                exercise_type = "T2 Treadmill"
                exercise_load = 160.0 + math.sin(cycle_pos) * 15.0
                exercise_mins = 40
                hr = 142.0 + random.uniform(-4.0, 6.0)
                rr = 28.0 + random.uniform(-1.5, 2.0)
                core_t = 37.8 + random.uniform(-0.1, 0.1)
                skin_t = 34.6 + random.uniform(-0.1, 0.1)
                hrv = 18.0 + random.uniform(-2.0, 2.0)  # Sympathetic drive drops HRV
                sbp = 148.0 + random.uniform(-3.0, 3.0)
                dbp = 74.0 + random.uniform(-2.0, 2.0)
                posture = 0.94
                expression = "focused"
                context_note = "High intensity cardiovascular conditioning on T2."
            else:
                # Active recovery
                exercise_type = "Cool-down"
                progress = (cycle_pos - 50) / 25.0
                hr = 140.0 - progress * 60.0
                rr = 26.0 - progress * 10.0
                exercise_load = 40.0 * (1.0 - progress)
                exercise_mins = 55
                posture = 0.91
                expression = "fatigued"
                context_note = "Heart rate recovery phase."

        elif "Scenario C" in scenario or "Sleep" in scenario:
            # Sleep deficit & neurobehavioral degradation
            sleep_h = 4.6
            sleep_eff = 68.0
            sleep_wake_count = 7
            pvt_reaction = 385.0 + random.uniform(-15.0, 25.0)  # Slowed cognitive reaction
            pvt_lapses = 4
            readiness = 54.0 + random.uniform(-2.0, 2.0)
            hr = self.base_hr + 8.0 + hr_noise  # Elevated resting sympathetic tone
            hrv = 32.0 + random.uniform(-3.0, 3.0)  # Depressed HRV
            expression = "fatigued"
            context_note = "Chronic sleep restriction; reduced cognitive readiness score."

        elif "Scenario D" in scenario or "Physiological Anomaly" in scenario:
            # Sudden resting tachycardia, hypoxia, and HRV drop without exercise
            if 15 <= (i % 60) <= 50:
                hr = 118.0 + random.uniform(-3.0, 8.0)
                spo2 = 91.8 + random.uniform(-1.0, 1.2)  # Critical Hypoxia
                hrv = 16.0 + random.uniform(-2.0, 2.0)
                rr = 24.0 + random.uniform(-1.0, 2.0)
                sbp = 145.0 + random.uniform(-2.0, 4.0)
                expression = "stressed"
                posture = 0.72
                context_note = "Multi-signal concordance: Resting tachycardia accompanied by SpO2 drop and low HRV."
            else:
                hr = self.base_hr + hr_noise
                spo2 = self.base_spo2 + spo2_noise

        elif "Scenario E" in scenario or "CO2" in scenario:
            # Environmental CO2 Excursion (ECLSS anomaly)
            progress = min(1.0, (i % 90) / 60.0)
            co2_pp = self.base_co2 + (progress * 2.8)  # Climbs from 2.4 to 5.2 mmHg
            if co2_pp > 3.0:
                rr = 18.0 + (progress * 5.0)  # Mild tachypnea in response to CO2
                expression = "stressed" if co2_pp > 4.0 else "neutral"
                context_note = f"Habitat ppCO2 ({co2_pp:.2f} mmHg) exceeds NASA-STD-3001 threshold."
                
        elif "Scenario F" in scenario or "Sensor Failure" in scenario:
            # Stale / Questionable / Missing sensor data
            cycle_sub = i % 40
            if cycle_sub < 15:
                # Frozen reading
                hr = 72.0
                spo2 = 98.0
                quality_status = QualityFlag.STALE
                context_note = "Sensor packet unchanged: possible telemetry freeze or buffer stall."
            elif cycle_sub < 25:
                # Questionable noise
                hr = 185.0  # Erroneous unphysical spike
                spo2 = 78.0
                quality_status = QualityFlag.QUESTIONABLE
                context_note = "Poor optical contact / high motion artifact flag."
            else:
                # Missing sample
                hr = None
                spo2 = None
                quality_status = QualityFlag.MISSING
                context_note = "Wearable packet drop: RF packet loss."

        elif "Scenario G" in scenario or "Fall" in scenario:
            # Fall event detected by HuskyLens
            if 15 <= (i % 50) <= 35:
                posture = 0.12  # Slump / horizontal on floor
                expression = "stressed"
                hr = self.base_hr + 28.0 + random.uniform(-2.0, 4.0)  # Autonomic distress response
                context_note = "HuskyLens Fall Detection Event (Algorithm 19) triggered."
            else:
                posture = 0.95
                expression = "neutral"

        elif "Scenario H" in scenario or "Radiation" in scenario or "SPE" in scenario:
            # Solar Particle Event (Space Radiation Hazard + NASA DONKI flare correlation)
            progress = min(1.0, (i % 70) / 35.0)
            rad_rate = 1200.0 + (progress * 6400.0)  # Climbs 1,200 -> 7,600 µGy/day
            expression = "focused"
            context_note = f"Solar Particle Event (SPE): Dosimeter reading {rad_rate:.0f} µGy/day; shelter advisories active."

        # Derived Mean Arterial Pressure (MAP)
        # Formula: MAP = (SBP + 2 * DBP) / 3
        map_val = round((sbp + 2.0 * dbp) / 3.0, 1)

        sim_prov = "unavailable" if quality_status == QualityFlag.MISSING else ("stale" if quality_status == QualityFlag.STALE else "simulated")

        return TelemetryFrame(
            timestamp=now_ts,
            crew_id="CREW-01",
            crew_name="Cmdr. Alex Vance",
            source_mode=SourceMode.SIMULATED,
            source_device="astro_simulator_v2",
            scenario_name=scenario,
            heart_rate=MeasurementItem(
                value=round(hr, 1) if hr is not None else None,
                unit="bpm",
                quality=quality_status,
                confidence=0.98 if quality_status == QualityFlag.VALID else 0.40,
                source="Simulated PPG (MAX30102 Model)",
                provenance=sim_prov
            ),
            spo2=MeasurementItem(
                value=round(spo2, 1) if spo2 is not None else None,
                unit="%",
                quality=quality_status,
                confidence=0.97 if quality_status == QualityFlag.VALID else 0.35,
                source="Simulated Pulse-Ox (MAX30102 Model)",
                provenance=sim_prov
            ),
            hrv_rmssd=MeasurementItem(
                value=round(hrv, 1) if hrv is not None else None,
                unit="ms",
                quality=QualityFlag.VALID,
                source="Calculated RMSSD over 5m Window",
                provenance="derived",
                is_derived=True,
                calculation_method="Root Mean Square of Successive Differences (RMSSD)"
            ),
            blood_pressure_systolic=MeasurementItem(
                value=round(sbp, 1),
                unit="mmHg",
                quality=QualityFlag.VALID,
                source="Simulated Non-Invasive Tonometry (DEMO)",
                provenance="simulated",
                metadata={"note": "DEMO: Not directly measured by PPG wristband."}
            ),
            blood_pressure_diastolic=MeasurementItem(
                value=round(dbp, 1),
                unit="mmHg",
                quality=QualityFlag.VALID,
                source="Simulated Non-Invasive Tonometry (DEMO)",
                provenance="simulated",
                metadata={"note": "DEMO: Not directly measured by PPG wristband."}
            ),
            mean_arterial_pressure=MeasurementItem(
                value=map_val,
                unit="mmHg",
                quality=QualityFlag.VALID,
                is_derived=True,
                calculation_method="MAP ≈ (SBP + 2 × DBP) / 3",
                source="Derived Estimate",
                provenance="derived"
            ),
            respiration_rate=MeasurementItem(
                value=round(rr, 1),
                unit="breaths/min",
                quality=QualityFlag.VALID,
                source="Derived from PPG Respiratory Modulation (PRV)",
                provenance="derived",
                is_derived=True
            ),
            core_temperature=MeasurementItem(
                value=round(core_t, 2),
                unit="°C",
                quality=QualityFlag.VALID,
                source="Simulated Double-Sensor Core Temp (DEMO)",
                provenance="simulated",
                metadata={"note": "Simulated; requires ingest from dedicated double-sensor heat flux probe."}
            ),
            skin_temperature=MeasurementItem(
                value=round(skin_t, 2),
                unit="°C",
                quality=QualityFlag.VALID,
                source="Simulated NTC Thermistor Wristband",
                provenance="simulated"
            ),
            sleep_hours=MeasurementItem(
                value=sleep_h,
                unit="hours",
                quality=QualityFlag.VALID,
                source="Simulated Actiwatch Actigraphy (NASA-SSM)",
                provenance="simulated"
            ),
            sleep_efficiency=MeasurementItem(
                value=sleep_eff,
                unit="%",
                quality=QualityFlag.VALID,
                source="Simulated Actiwatch Sleep Analysis",
                provenance="simulated"
            ),
            sleep_interruptions=MeasurementItem(
                value=float(sleep_wake_count),
                unit="events",
                quality=QualityFlag.VALID,
                source="Actigraphy Awakening Counter",
                provenance="simulated"
            ),
            reaction_time_ms=MeasurementItem(
                value=round(pvt_reaction, 1),
                unit="ms",
                quality=QualityFlag.VALID,
                source="NASA-PVT Reaction Self Test Simulation",
                provenance="simulated"
            ),
            attention_lapses=MeasurementItem(
                value=float(pvt_lapses),
                unit="lapses (>500ms)",
                quality=QualityFlag.VALID,
                source="NASA-PVT Assessment",
                provenance="simulated"
            ),
            readiness_score=MeasurementItem(
                value=round(readiness, 1),
                unit="/100",
                quality=QualityFlag.VALID,
                is_derived=True,
                calculation_method="Weighted composite: 0.40*Sleep + 0.35*PVT_Speed + 0.25*HRV_Tone",
                source="AstroHealth Composite Readiness Algorithm",
                provenance="derived"
            ),
            exercise_minutes=MeasurementItem(
                value=float(exercise_mins),
                unit="minutes/day",
                quality=QualityFlag.VALID,
                source="Daily Mission Countermeasure Schedule",
                provenance="simulated"
            ),
            exercise_type=exercise_type,
            exercise_load_w=MeasurementItem(
                value=round(exercise_load, 1),
                unit="Watts",
                quality=QualityFlag.VALID,
                source="T2/CEVIS Workload Telemetry",
                provenance="simulated"
            ),
            exercise_posture_score=MeasurementItem(
                value=posture,
                unit="score (0-1)",
                quality=QualityFlag.VALID,
                confidence=0.94,
                source="HuskyLens 2 Pose Recognition (Algorithm 9)",
                provenance="simulated"
            ),
            detected_expression=expression,
            co2_pp_mmhg=MeasurementItem(
                value=round(co2_pp, 2),
                unit="mmHg",
                quality=QualityFlag.VALID,
                source="Habitat Life Support ECLSS Sensor Array",
                provenance="simulated"
            ),
            cabin_temp_c=MeasurementItem(
                value=round(22.4 + random.uniform(-0.2, 0.2), 1),
                unit="°C",
                quality=QualityFlag.VALID,
                source="Cabin Environmental System",
                provenance="simulated"
            ),
            cabin_humidity_pct=MeasurementItem(
                value=round(44.0 + random.uniform(-1.0, 1.0), 1),
                unit="%",
                quality=QualityFlag.VALID,
                source="Cabin Environmental System",
                provenance="simulated"
            ),
            radiation_dose_rate_ugy_day=MeasurementItem(
                value=round(rad_rate + random.uniform(-10.0, 10.0), 1),
                unit="µGy/day",
                quality=QualityFlag.VALID,
                source="Habitat Active Radiation Dosimeter (CPDS / CANS Model)",
                provenance="simulated"
            ),
            blood_glucose_mg_dl=MeasurementItem(
                value=round(glucose_val, 1),
                unit="mg/dL",
                quality=QualityFlag.VALID,
                source="Crew Metabolic Check (Simulated / Fingerstick)",
                provenance="crew_self_report" if self.checkin_override.get("latest_glucose_mg_dl") else "simulated"
            ),
            hydration_pct=MeasurementItem(
                value=round(hydration_pct, 1),
                unit="%",
                quality=QualityFlag.VALID,
                is_derived=True,
                calculation_method="Fluid Intake / 2500 mL NASA Target",
                source="Crew Fluid Log",
                provenance="derived"
            ),
            hydration_intake_ml=MeasurementItem(
                value=round(hydration_ml, 0),
                unit="mL",
                quality=QualityFlag.VALID,
                source="Crew Hydration Self-Log",
                provenance="crew_self_report" if self.checkin_override else "simulated"
            ),
            mood_score=MeasurementItem(
                value=round(mood_val if "Scenario C" not in scenario else min(mood_val, 2.3), 1),
                unit="/5",
                quality=QualityFlag.VALID,
                source="Crew Private Self-Report (Non-Camera)",
                provenance="crew_self_report"
            ),
            mood_label="fatigued" if "Scenario C" in scenario else mood_lbl,
            ultrasound_last_check=ultrasound_note,
            context_note=context_note
        )
