"""
AstroHealth Guardian — Five Hazards & Historical Spaceflight Incident Precedent Engine
Compares current telemetry anomalies, environmental excursions, solar space weather,
and crew complaints against documented NASA/ISS/Skylab/Apollo/Mir spaceflight incidents
to guide verification checks and operational countermeasures without clinical diagnosis.
"""

from typing import Dict, Any, List, Optional


FIVE_HAZARDS_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "radiation",
        "short": "RADIATION",
        "title": "Space Radiation",
        "summary": "GCRs, solar particle events (SPEs), and trapped belts outside Earth's magnetosphere.",
        "primary_sensors": "Independent Radiation Dosimeter + Live NASA DONKI Solar Alerts",
        "source_url": "https://www.nasa.gov/hrp/hazards/",
    },
    {
        "id": "isolation",
        "short": "ISOLATION",
        "title": "Isolation & Confinement",
        "summary": "Circadian drift, sleep restriction, workload spikes, and crew behavioral strain.",
        "primary_sensors": "Actigraphy Sleep + NASA-PVT + Crew Mood Check-In",
        "source_url": "https://www.nasa.gov/hrp/hazards/",
    },
    {
        "id": "distance",
        "short": "DISTANCE",
        "title": "Distance from Earth",
        "summary": "Up to 20-minute one-way Mars comms lag requiring autonomous local triage & follow-up.",
        "primary_sensors": "Local SQLite Vault + Autonomous Rules + Offline Incident Matcher",
        "source_url": "https://www.nasa.gov/hrp/hazards/",
    },
    {
        "id": "gravity",
        "short": "GRAVITY",
        "title": "Altered Gravity Fields",
        "summary": "Cephalad fluid shift, SANS eye pressure, venous stasis/clots, arrhythmias, & bone loss.",
        "primary_sensors": "PPG HR/SpO2 + Tonometry BP + ARED/T2 Load + Ultrasound Check Log",
        "source_url": "https://www.nasa.gov/hrp/hazards/",
    },
    {
        "id": "hostile_env",
        "short": "CLOSED ENV",
        "title": "Hostile & Closed Environment",
        "summary": "CO2 pocketing in zero-g, thermal buildup, smoke/off-gassing, hydration & renal stone risk.",
        "primary_sensors": "ECLSS ppCO2 + Cabin Temp/Humidity + Core Temp + Hydration/Glucose",
        "source_url": "https://www.nasa.gov/hrp/hazards/",
    },
]


HISTORICAL_INCIDENTS: List[Dict[str, Any]] = [
    {
        "id": "INC-APOLLO13-CO2",
        "mission": "Apollo 13 (1970)",
        "hazard_id": "hostile_env",
        "hazard_label": "Hostile & Closed Environment",
        "title": "Cabin Carbon Dioxide (CO2) Scrubber Saturation & Hypercapnia Risk",
        "what_happened": (
            "Inside the crippled Lunar Module, two-person CO2 lithium hydroxide scrubbers saturated under a three-crew load, "
            "forcing an improvised duct-tape adapter to purge hazardous CO2 buildup before narcosis set in."
        ),
        "early_signs": [
            "Cabin ppCO2 rising >= 3.0 mmHg (24h limit 4.0 mmHg per NASA-STD-3001)",
            "Mild tachypnea, headache, or slowed NASA-PVT reaction latency",
            "Poor buoyant convection causing CO2 pockets near the crew head",
        ],
        "how_to_figure_it_out": [
            "Verify ECLSS CDRA / LiOH scrubber flow and check crew quarters air velocity (> 15 ft/min).",
            "Correlate ppCO2 spike with current respiration rate, PVT latency, and headache self-report.",
            "Check sensor provenance to rule out a stale environmental packet.",
        ],
        "recommended_actions": [
            "Activate personal airflow ventilation ducting directly toward crew face/sleeping berth.",
            "Inspect and rotate CO2 sorbent canisters or reduce heavy exertion until ppCO2 drops below 3.0 mmHg.",
            "Log any persistent visual blur or headache for asynchronous Flight Surgeon review.",
        ],
        "body_region": "head",
        "body_layer": "Full body",
        "citation": "NASA-STD-3001 Vol 2 & NASA-OCHMO-TB-004",
        "citation_url": "https://www.nasa.gov/hrp/hazards/",
        "keywords": ["co2", "carbon dioxide", "scrubber", "headache", "stuffy", "hypercapnia", "eclss", "air", "apollo 13"],
    },
    {
        "id": "INC-SKYLAB2-ARRHYTHMIA",
        "mission": "Skylab 2 (1973)",
        "hazard_id": "gravity",
        "hazard_label": "Altered Gravity Fields",
        "title": "Microgravity Resting Arrhythmia, Fluid Shift & Electrolyte Deconditioning",
        "what_happened": (
            "During Skylab 2, crew cardiovascular monitoring recorded intermittent arrhythmias (PVCs and junctional rhythms) "
            "linked to microgravity plasma volume loss (~10–15%), electrolyte shifts, and autonomic stress."
        ),
        "early_signs": [
            "Resting heart rate >= 100 bpm with exercise load at 0 W (true rest)",
            "Depressed HRV RMSSD (< 25 ms) or elevated resting systolic blood pressure",
            "Lightheadedness, chest fluttering, or hydration deficit",
        ],
        "how_to_figure_it_out": [
            "Confirm exercise vs. rest state (check T2/ARED workload wattage before assuming resting tachycardia).",
            "Verify PPG optical wristband contact and sequence freshness to rule out motion artifact.",
            "Review same-day hydration intake (mL/day) and HRV trend.",
        ],
        "recommended_actions": [
            "Pause exertion, hydrate with electrolyte fluid (+250–500 mL), and capture a 60-second resting check.",
            "Inspect chest/heart reference layer and log any palpitations or chest discomfort.",
            "Escalate trend bundle to Flight Surgeon if resting elevation persists past confirmation window.",
        ],
        "body_region": "chest",
        "body_layer": "Heart",
        "citation": "NASA Spaceflight Standard Measures (NTRS 20230014025)",
        "citation_url": "https://ntrs.nasa.gov/citations/20230014025",
        "keywords": ["heart", "tachycardia", "arrhythmia", "skylab 2", "palpitation", "pulse", "chest", "dizzy", "hrv"],
    },
    {
        "id": "INC-ISS-SANS-THROMBOSIS",
        "mission": "ISS Vascular & Ocular Fluid Shift (2020 Discovery / SANS)",
        "hazard_id": "gravity",
        "hazard_label": "Altered Gravity Fields",
        "title": "Headward Fluid Shift, Internal Jugular Stasis (DVT) & SANS",
        "what_happened": (
            "Long-duration ISS ultrasound vascular studies uncovered stagnant/retrograde internal jugular vein flow and an "
            "asymptomatic blood clot in orbit, alongside optic disc edema from Spaceflight-Associated Neuro-ocular Syndrome (SANS)."
        ),
        "early_signs": [
            "Persistent resting systolic BP >= 140 mmHg without exercise",
            "Headache, facial fullness, neck tightness, or altered near vision",
            "Overdue scheduled neck/ocular ultrasound check on long-duration flight",
        ],
        "how_to_figure_it_out": [
            "Focus 3D neck/head regions and review last scheduled Internal Jugular Vein (IJV) ultrasound check.",
            "Pair blood pressure & ppCO2 readings with crew-confirmed vision or neck swelling check-in.",
            "Never claim vascular diagnosis from RGB webcam alone—confirm via guided ultrasound.",
        ],
        "recommended_actions": [
            "Perform guided neck/ocular ultrasound scan and log observation inside Crew Health Check-In.",
            "Transmit ultrasound & BP bundle to Earth Flight Surgeon (asynchronous packet on deep-space delay).",
            "Maintain prescribed LBNP / resistive countermeasure and hydration schedule.",
        ],
        "body_region": "neck",
        "body_layer": "Full body",
        "citation": "NASA Ongoing HRP Research — SANS & Venous Haemostasis",
        "citation_url": "https://www.nasa.gov/hrp/ongoing-hrp-research/",
        "keywords": ["sans", "vision", "eye", "neck", "jugular", "clot", "thrombosis", "dvt", "ultrasound", "blood pressure", "fluid shift"],
    },
    {
        "id": "INC-SKYLAB4-STRAIN",
        "mission": "Skylab 4 (1973–1974)",
        "hazard_id": "isolation",
        "hazard_label": "Isolation & Confinement",
        "title": "Cumulative Workload Overload, Sleep Deficit & Behavioral Fatigue",
        "what_happened": (
            "An unbroken high-tempo schedule combined with early space motion sickness and sleep fragmentation caused acute fatigue "
            "and a historic crew-ground communication impasse before schedule pacing restored mission productivity."
        ),
        "early_signs": [
            "Sleep duration < 6.0 hrs or sleep efficiency < 75%",
            "NASA-PVT reaction slowing (> 350 ms) or readiness score < 65/100",
            "Crew self-reported fatigue or high workload stress mood log",
        ],
        "how_to_figure_it_out": [
            "Combine objective actigraphy sleep + NASA-PVT lapses with confidential crew mood check-in (1–5).",
            "Do NOT label facial expressions from camera frames as clinical depression or mental disorder.",
            "Inspect multi-day sleep debt slope and CO2 overnight cabin readings.",
        ],
        "recommended_actions": [
            "Initiate crew workload decompression window and protect uninterrupted 8h sleep period.",
            "Apply circadian lighting schedule and check cabin noise / ventilation.",
            "Schedule private behavioral check-in or asynchronous Earth family link.",
        ],
        "body_region": "head",
        "body_layer": "Full body",
        "citation": "NASA HRP BMed Risk & NTRS-20230003916 (Sleep Architecture)",
        "citation_url": "https://ntrs.nasa.gov/citations/20230003916",
        "keywords": ["sleep", "tired", "fatigue", "stress", "workload", "mood", "skylab 4", "exhausted", "pvt", "insomnia"],
    },
    {
        "id": "INC-EVA-PARMITANO-HYPOXIA",
        "mission": "ISS EVA-23 (Luca Parmitano, 2013) & Hypobaric EVA Risk",
        "hazard_id": "distance",
        "hazard_label": "Distance from Earth",
        "title": "Suit / Airlock Hypoxia, Decompression Sickness & Loss of Situational Aids",
        "what_happened": (
            "Blocked EMU suit ventilation leaked ~1.5 L of water into astronaut Luca Parmitano's helmet during EVA-23, "
            "cutting off vision and voice radio; deep-space EVAs also raise hypobaric hypoxia and DCS risks far from Earth."
        ),
        "early_signs": [
            "SpO2 dropping <= 95% (critical <= 92%) or rapid respiration",
            "Posture slump / fall detection trigger (< 0.25) or acute joint pain after depressurization",
            "Communications blackout or Earth comms delay exceeding emergency response window",
        ],
        "how_to_figure_it_out": [
            "Cross-check finger perfusion / pulse-ox quality before ruling out sensor slip.",
            "Verify cabin/suit ppO2 and total pressure history for possible O2/N2 DCS joint symptoms.",
            "Engage local offline voice-first 3D guidance so crew can act with zero Earth dependency.",
        ],
        "recommended_actions": [
            "Activate emergency O2 / terminate EVA immediately and verify buddy check back to airlock.",
            "If joint pain follows pressure drop, focus affected 3D joint in Skeleton view and log DCS check.",
            "Operate from local SQLite mission vault until habitat atmosphere & SpO2 stabilize >= 96%.",
        ],
        "body_region": "chest",
        "body_layer": "Lungs",
        "citation": "NASA HRP Risk of Hypoxia / DCS & NASA-STD-3001 Vol 1",
        "citation_url": "https://www.nasa.gov/hrp/risks/",
        "keywords": ["hypoxia", "spo2", "oxygen", "eva", "suit", "parmitano", "fall", "collapse", "dcs", "bends", "joint", "shoulder", "knee", "airlock"],
    },
    {
        "id": "INC-APOLLO-SPE-RADIATION",
        "mission": "Deep-Space Transit (Apollo Legacy) & CSA CANS Monitoring (2026)",
        "hazard_id": "radiation",
        "hazard_label": "Space Radiation",
        "title": "Galactic Cosmic Rays & Solar Particle Event (SPE) Storm Surge",
        "what_happened": (
            "Outside low-Earth geomagnetic shielding, crews encounter chronic GCR dose and sudden Solar Particle Events. "
            "Continuous autonomous instruments like CSA's Active Neutron Spectrometer (CANS) warn crews when radiation spikes."
        ),
        "early_signs": [
            "Live NASA DONKI flare/CME/SEP alert or active neutron dosimeter >= 1,000 µGy/day",
            "Critical SPE alert >= 5,000 µGy/day during unshielded EVA windows",
        ],
        "how_to_figure_it_out": [
            "Inspect live NASA DONKI solar notifications alongside dedicated radiation dosimeter telemetry.",
            "Distinguish simulated drill vs. live spectrometer stream—never claim optical cameras detect radiation.",
            "Track cumulative mission mSv budget across transit days.",
        ],
        "recommended_actions": [
            "Cancel or postpone any planned EVA until SPE flux subsides.",
            "Relocate crew to high-hydrogen storm shelter (water wall / polyethylene shielding).",
            "Increase antioxidant nutrition, hydration, and post-event immune biomarker check.",
        ],
        "body_region": "head",
        "body_layer": "Full body",
        "citation": "CSA CANS (2026-02-26) & NASA HRP Space Radiation Hazard",
        "citation_url": "https://www.asc-csa.gc.ca/eng/news/articles/2026/2026-02-26-monitoring-radiation-astronaut-health.asp",
        "keywords": ["radiation", "solar", "flare", "cme", "sep", "donki", "dosimeter", "storm", "cans", "neutron"],
    },
    {
        "id": "INC-MIR-ENV-METABOLIC",
        "mission": "Mir Fire (1997) & ISS Renal Stone / Closed-Loop Metabolic Strain",
        "hazard_id": "hostile_env",
        "hazard_label": "Hostile & Closed Environment",
        "title": "Thermal / Atmospheric Contamination & Dehydration-Calcium Renal Risk",
        "what_happened": (
            "During Mir-23, an oxygen-generator fire filled the station with toxic smoke and heat; long-duration closed loops "
            "also combine microgravity bone calcium loss with low water intake, elevating acute kidney stone & metabolic risk."
        ),
        "early_signs": [
            "Core temperature >= 37.8°C ('Space Fever') or cabin temp >= 27.0°C",
            "Hydration index < 72% (< 1,800 mL/day) or abdominal/flank discomfort",
            "Blood glucose excursion (< 70 mg/dL hypoglycemia or > 180 mg/dL stress spike)",
        ],
        "how_to_figure_it_out": [
            "Check convective cooling fans and double-sensor heat flux probe (resting vs. post-exercise thermal buildup).",
            "Review 24h fluid intake log and metabolic glucometer reading alongside abdominal/flank self-report.",
        ],
        "recommended_actions": [
            "Verify ECLSS particulate & atmosphere scrubbers; don respirators immediately if smoke/odor detected.",
            "Increase fluid intake toward 2,500 mL/day target to lower renal calcium concentration.",
            "Log flank pain, glucose check, or skin cut cleanly in the longitudinal symptom tracker.",
        ],
        "body_region": "abdomen",
        "body_layer": "Full body",
        "citation": "NASA HRP Renal Stone Risk & NASA-STD-3001 Vol 1/2",
        "citation_url": "https://www.nasa.gov/hrp/risks/",
        "keywords": ["fire", "smoke", "toxic", "fever", "temperature", "heat", "dehydration", "hydration", "water", "kidney", "renal", "glucose", "sugar", "mir", "cut", "wound", "infection"],
    },
]


def _extract_val(frame_dict: Optional[Dict[str, Any]], key: str) -> Optional[float]:
    if not frame_dict or key not in frame_dict:
        return None
    item = frame_dict.get(key)
    if isinstance(item, dict):
        q = str(item.get("quality", "valid")).lower()
        if q in ("missing", "invalid"):
            return None
        val = item.get("value")
        return float(val) if val is not None else None
    if isinstance(item, (int, float)):
        return float(item)
    return None


def match_historical_incidents(
    frame_dict: Optional[Dict[str, Any]] = None,
    alerts: Optional[List[Dict[str, Any]]] = None,
    query_text: Optional[str] = None,
    donki_active: bool = False,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    Compares live telemetry, active alerts, NASA DONKI solar status, and optional
    crew query text against documented historical NASA/ISS/Skylab/Apollo incidents.
    Returns ranked precedent matches with explicit match reasons and SOP actions.
    """
    alerts = alerts or []
    q_lower = (query_text or "").strip().lower()

    co2 = _extract_val(frame_dict, "co2_pp_mmhg")
    hr = _extract_val(frame_dict, "heart_rate")
    hrv = _extract_val(frame_dict, "hrv_rmssd")
    spo2 = _extract_val(frame_dict, "spo2")
    sbp = _extract_val(frame_dict, "blood_pressure_systolic")
    core_t = _extract_val(frame_dict, "core_temperature")
    cabin_t = _extract_val(frame_dict, "cabin_temp_c")
    rad = _extract_val(frame_dict, "radiation_dose_rate_ugy_day")
    sleep_h = _extract_val(frame_dict, "sleep_hours")
    pvt_ms = _extract_val(frame_dict, "reaction_time_ms")
    rdy = _extract_val(frame_dict, "readiness_score")
    posture = _extract_val(frame_dict, "exercise_posture_score")
    ex_load = _extract_val(frame_dict, "exercise_load_w") or 0.0
    hydration_pct = _extract_val(frame_dict, "hydration_pct")
    glucose = _extract_val(frame_dict, "blood_glucose_mg_dl")
    mood_score = _extract_val(frame_dict, "mood_score")
    ex_type = str((frame_dict or {}).get("exercise_type", "Rest"))
    is_exercising = (ex_type not in ("Rest", "Unavailable", "")) or (ex_load > 50.0)

    alert_params = {str(a.get("trigger_parameter", "")) for a in alerts}
    results: List[Dict[str, Any]] = []

    for inc in HISTORICAL_INCIDENTS:
        score = 0
        reasons: List[str] = []
        inc_id = inc["id"]

        if inc_id == "INC-APOLLO13-CO2":
            if co2 is not None and co2 >= 3.0:
                score += 92 if co2 >= 4.0 else 76
                reasons.append(f"Habitat ppCO2 is {co2:.2f} mmHg (NASA-STD-3001 limit <= 3.0 / 4.0 mmHg)")
            if "co2_pp_mmhg" in alert_params:
                score += 20
                reasons.append("Active CO2 excursion alert present")

        elif inc_id == "INC-SKYLAB2-ARRHYTHMIA":
            if hr is not None and hr >= 100.0 and not is_exercising:
                score += 88 if hr >= 120.0 else 72
                reasons.append(f"Resting HR elevated ({hr:.1f} bpm) with no exercise load")
            if hrv is not None and hrv < 25.0 and not is_exercising:
                score += 30
                reasons.append(f"Depressed HRV RMSSD ({hrv:.1f} ms)")
            if "heart_rate" in alert_params:
                score += 18

        elif inc_id == "INC-ISS-SANS-THROMBOSIS":
            if sbp is not None and sbp >= 140.0 and not is_exercising:
                score += 78
                reasons.append(f"Elevated resting SBP ({sbp:.0f} mmHg) suggesting possible vascular/fluid shift load")
            if "blood_pressure_systolic" in alert_params:
                score += 18

        elif inc_id == "INC-SKYLAB4-STRAIN":
            if sleep_h is not None and sleep_h < 6.0:
                score += 72
                reasons.append(f"Sleep duration restricted ({sleep_h:.1f} hrs < 6.0 hr floor)")
            if pvt_ms is not None and pvt_ms >= 350.0:
                score += 32
                reasons.append(f"NASA-PVT reaction slowed ({pvt_ms:.0f} ms)")
            if rdy is not None and rdy < 65.0:
                score += 25
                reasons.append(f"Readiness depressed ({rdy:.0f}/100)")
            if mood_score is not None and mood_score <= 2.5:
                score += 28
                reasons.append(f"Crew mood self-report low ({mood_score:.1f}/5)")

        elif inc_id == "INC-EVA-PARMITANO-HYPOXIA":
            if spo2 is not None and spo2 <= 95.0:
                score += 94 if spo2 <= 92.0 else 76
                reasons.append(f"SpO2 dropped to {spo2:.1f}% (hypoxia caution <= 95%)")
            if posture is not None and posture < 0.25:
                score += 96
                reasons.append(f"Acute fall/slump posture event ({posture:.2f})")
            if "spo2" in alert_params or "exercise_posture_score" in alert_params:
                score += 20

        elif inc_id == "INC-APOLLO-SPE-RADIATION":
            if rad is not None and rad >= 1000.0:
                score += 95 if rad >= 5000.0 else 80
                reasons.append(f"Dosimeter reading spiked ({rad:.0f} µGy/day vs ~315 nominal)")
            if donki_active:
                score += 55
                reasons.append("Live NASA DONKI space weather flare/CME notification active")
            if "radiation_dose_rate_ugy_day" in alert_params:
                score += 20

        elif inc_id == "INC-MIR-ENV-METABOLIC":
            if core_t is not None and core_t >= 37.8 and not is_exercising:
                score += 78
                reasons.append(f"Elevated resting core temp ({core_t:.2f}°C Space Fever threshold)")
            if cabin_t is not None and cabin_t >= 27.0:
                score += 65
                reasons.append(f"Cabin temperature elevated ({cabin_t:.1f}°C)")
            if hydration_pct is not None and hydration_pct < 72.0:
                score += 68
                reasons.append(f"Hydration status low ({hydration_pct:.0f}% of 2,500 mL target)")
            if glucose is not None and (glucose < 70.0 or glucose > 180.0):
                score += 70
                reasons.append(f"Blood glucose outside nominal 70–180 mg/dL ({glucose:.0f} mg/dL)")
            if "hydration_pct" in alert_params or "core_temperature" in alert_params:
                score += 18

        # Keyword / voice complaint matching
        if q_lower:
            kw_hits = [kw for kw in inc.get("keywords", []) if kw in q_lower]
            if kw_hits:
                score += 55 + min(30, len(kw_hits) * 12)
                reasons.append(f"Situation keywords matched: {', '.join(kw_hits[:3])}")

        if score > 0:
            match_level = "HIGH" if score >= 85 else ("MODERATE" if score >= 55 else "WATCH")
            results.append({
                **inc,
                "match_score": min(100, score),
                "match_level": match_level,
                "match_reasons": reasons,
            })

    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results[:limit]


def get_five_hazards_status(
    frame_dict: Optional[Dict[str, Any]] = None,
    alerts: Optional[List[Dict[str, Any]]] = None,
    donki_status: Optional[Dict[str, Any]] = None,
    offline_delay_mode: bool = False,
) -> List[Dict[str, Any]]:
    """
    Computes live status across all 5 NASA Hazards of Human Spaceflight
    with explicit source attribution and non-diagnostic boundaries.
    """
    alerts = alerts or []
    donki_status = donki_status or {}
    rad = _extract_val(frame_dict, "radiation_dose_rate_ugy_day")
    co2 = _extract_val(frame_dict, "co2_pp_mmhg")
    sleep_h = _extract_val(frame_dict, "sleep_hours")
    rdy = _extract_val(frame_dict, "readiness_score")
    mood_score = _extract_val(frame_dict, "mood_score")
    hr = _extract_val(frame_dict, "heart_rate")
    sbp = _extract_val(frame_dict, "blood_pressure_systolic")
    spo2 = _extract_val(frame_dict, "spo2")
    hydration_pct = _extract_val(frame_dict, "hydration_pct")
    core_t = _extract_val(frame_dict, "core_temperature")
    ex_load = _extract_val(frame_dict, "exercise_load_w") or 0.0
    ex_type = str((frame_dict or {}).get("exercise_type", "Rest"))
    is_ex = (ex_type not in ("Rest", "Unavailable", "")) or (ex_load > 50.0)

    donki_alert = bool(donki_status.get("radiation_alert_active"))

    statuses: Dict[str, Dict[str, str]] = {}

    # 1. Radiation
    if rad is not None and rad >= 5000.0:
        statuses["radiation"] = {"state": "ALERT", "detail": f"SPE Surge {rad:.0f} µGy/d"}
    elif (rad is not None and rad >= 1000.0) or donki_alert:
        statuses["radiation"] = {
            "state": "WATCH",
            "detail": f"DONKI Alert" if donki_alert else f"{rad:.0f} µGy/d elevated",
        }
    else:
        statuses["radiation"] = {
            "state": "NOMINAL",
            "detail": f"{rad:.0f} µGy/d • DONKI synced" if rad is not None else "Dosimeter unavailable",
        }

    # 2. Isolation & Confinement
    if (rdy is not None and rdy < 55.0) or (sleep_h is not None and sleep_h < 5.5):
        statuses["isolation"] = {"state": "ALERT", "detail": f"Sleep {sleep_h or '--'}h / Rdy {rdy or '--'}"}
    elif (rdy is not None and rdy < 70.0) or (mood_score is not None and mood_score <= 2.5):
        statuses["isolation"] = {"state": "WATCH", "detail": "Monitor fatigue & workload"}
    else:
        statuses["isolation"] = {"state": "NOMINAL", "detail": f"Sleep {sleep_h or '--'}h • Mood OK"}

    # 3. Distance from Earth
    if offline_delay_mode:
        statuses["distance"] = {"state": "WATCH", "detail": "Mars 20m Lag • Local Autonomous"}
    elif spo2 is not None and spo2 <= 92.0:
        statuses["distance"] = {"state": "ALERT", "detail": "Local Emergency Triage Active"}
    else:
        statuses["distance"] = {"state": "NOMINAL", "detail": "Local SQLite + Voice Ready"}

    # 4. Altered Gravity
    if hr is not None and hr >= 120.0 and not is_ex:
        statuses["gravity"] = {"state": "ALERT", "detail": f"Resting HR {hr:.0f} bpm"}
    elif (hr is not None and hr >= 100.0 and not is_ex) or (sbp is not None and sbp >= 140.0 and not is_ex):
        statuses["gravity"] = {"state": "WATCH", "detail": f"CV / Fluid Shift Watch"}
    else:
        statuses["gravity"] = {"state": "NOMINAL", "detail": f"ARED/T2 & SANS Check Active"}

    # 5. Hostile & Closed Environment
    if co2 is not None and co2 >= 4.0:
        statuses["hostile_env"] = {"state": "ALERT", "detail": f"ppCO2 {co2:.2f} mmHg (>4.0)"}
    elif (co2 is not None and co2 >= 3.0) or (hydration_pct is not None and hydration_pct < 72.0) or (core_t is not None and core_t >= 37.8 and not is_ex):
        statuses["hostile_env"] = {"state": "WATCH", "detail": "CO2 / Thermal / Hydration Watch"}
    else:
        statuses["hostile_env"] = {"state": "NOMINAL", "detail": f"CO2 {co2 or '--'} mmHg • Hydr {hydration_pct or '--'}%"}

    enriched = []
    for h in FIVE_HAZARDS_CATALOG:
        st = statuses[h["id"]]
        enriched.append({**h, "state": st["state"], "detail": st["detail"]})
    return enriched
