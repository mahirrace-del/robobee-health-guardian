"""
AstroHealth Guardian — Multi-Sensor Context Engine
Correlates biometrics, habitat environment, and computer vision observations
without producing clinical diagnostic claims.
"""

from typing import Dict, Any, Optional
from src.models.telemetry import TelemetryFrame, QualityFlag, SourceMode


def evaluate_crew_context(frame: TelemetryFrame) -> Dict[str, Any]:
    """
    Correlates physiological signals with vision and environmental context.
    Produces a transparent operational context summary without substituting
    synthetic defaults when measurements are missing or stale.
    """
    hr_item = frame.heart_rate
    spo2_item = frame.spo2
    posture_item = frame.exercise_posture_score
    co2_item = frame.co2_pp_mmhg

    hr = hr_item.value if hr_item.quality == QualityFlag.VALID else None
    spo2 = spo2_item.value if spo2_item.quality == QualityFlag.VALID else None
    posture = posture_item.value if posture_item.quality == QualityFlag.VALID else None
    co2 = co2_item.value if co2_item.quality == QualityFlag.VALID else None
    expression = (frame.detected_expression or "unavailable").lower()
    exercise_type = frame.exercise_type or "Rest"

    context_type = "Nominal Rest / Work"
    context_note = "All observed parameters within nominal spaceflight baseline."
    recommendation = "Continue planned mission timeline."
    is_anomaly = False

    # 0. Check for degraded, stale, or missing primary wearable telemetry first
    if hr_item.quality in (QualityFlag.MISSING, QualityFlag.STALE, QualityFlag.QUESTIONABLE, QualityFlag.INVALID) or \
       spo2_item.quality in (QualityFlag.MISSING, QualityFlag.STALE, QualityFlag.QUESTIONABLE, QualityFlag.INVALID):
        context_type = f"Telemetry {hr_item.quality.value.capitalize()} / Degraded"
        context_note = (
            f"Primary biometric channel degraded (HR quality: {hr_item.quality.value}, "
            f"SpO2 quality: {spo2_item.quality.value}). Clinical/operational interpretation suspended until valid signal resumes."
        )
        recommendation = "Inspect wristband optical contact, RF link, and packet timestamps."
        is_anomaly = True
    # 1. Exercise Exertion vs Resting Anomaly
    elif exercise_type not in ("Rest", "Unavailable"):
        if hr is not None and hr > 110:
            if posture is None or posture > 0.8:
                context_type = "Expected Exercise Exertion"
                posture_str = f" with good form ({posture:.2f})" if posture is not None else " (posture sensor unavailable)"
                context_note = f"Elevated HR ({hr:.1f} bpm) corresponds to active {exercise_type}{posture_str}."
                recommendation = "Maintain hydration and monitor heart rate recovery slope."
            else:
                context_type = "Sub-optimal Exercise Biomechanics"
                context_note = f"Elevated HR with degraded posture score ({posture:.2f}). Risk of harness injury or lumbar strain."
                recommendation = "Advise astronaut to verify harness tension and posture alignment."
                is_anomaly = True
    else:
        # At rest
        if hr is not None and hr > 100:
            context_type = "Unexplained Resting Tachycardia"
            context_note = f"Elevated HR ({hr:.1f} bpm) observed while crew is classified as at rest."
            recommendation = "Prompt astronaut to log perceived stress and check wristband fit."
            is_anomaly = True

        if posture is not None and posture < 0.25:
            context_type = "Critical: Suspected Fall / Incapacitation"
            context_note = f"HuskyLens detected sudden posture collapse ({posture:.2f}) during non-exercise period."
            recommendation = "Immediate flight surgeon and crew quarters intercom check."
            is_anomaly = True

        if co2 is not None and co2 > 3.5:
            context_type = "Environmental Hypercapnia Risk"
            context_note = f"Cabin ppCO2 elevated ({co2:.2f} mmHg) while crew is present in habitat module."
            recommendation = "Check local ventilation ducting for CO2 pocket accumulation."
            is_anomaly = True

    # 2. Vision expression qualification (strictly labeled by actual availability)
    if frame.source_mode == SourceMode.LIVE and expression in ("unavailable", "none", ""):
        expression_note = "Vision camera telemetry not connected in live wearable mode; facial affect is unavailable."
    else:
        expression_note = (
            f"HuskyLens Algorithm 13 classified facial affect as '{expression}' "
            "(Edge AI observation; not a diagnostic indicator)."
        )

    return {
        "context_type": context_type,
        "context_note": context_note,
        "expression_note": expression_note,
        "recommendation": recommendation,
        "is_anomaly": is_anomaly,
        "source_mode": frame.source_mode.value,
    }
