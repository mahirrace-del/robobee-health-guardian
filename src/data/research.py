"""
AstroHealth Guardian — Verified Research & Engineering References Catalog
Grounded strictly in official NASA standards, NTRS technical reports, and hardware protocols.
"""

from typing import List, Dict, Any

RESEARCH_CITATIONS: List[Dict[str, Any]] = [
    {
        "id": "NASA-SSM-CORE",
        "title": "NASA Spaceflight Standard Measures",
        "organization": "NASA Human Research Program (HRP)",
        "url": "https://www.nasa.gov/reference/standard-measures/",
        "study_id": "SSM-ISS-01",
        "publication_date": "Updated 2024",
        "summary": "The canonical NASA program collecting a standard set of core physiological, behavioral, and biological measurements from astronauts across spaceflight missions to establish longitudinal adaptation baselines.",
        "parameters_established": [
            "Cardiovascular regulatory status",
            "Actigraphy sleep & rest-activity cycles",
            "Sensorimotor coordination",
            "Immune & cytokine profiles"
        ],
        "dashboard_relevance": "Provides the baseline ranges and monitoring cadence used for AstroHealth Guardian's physiological telemetry dashboard.",
        "limitations": "Measures represent healthy, highly conditioned astronauts in low Earth orbit. Individual baseline variation requires personalized calibration."
    },
    {
        "id": "NASA-STD-3001-V1",
        "title": "NASA Spaceflight Human-System Standard, Volume 1: Crew Health",
        "organization": "NASA Office of the Chief Health and Medical Officer (OCHMO)",
        "url": "https://www.nasa.gov/reference/nasa-std-3001v1/",
        "study_id": "NASA-STD-3001-VOL-1-REV-B",
        "publication_date": "Revision B (2022)",
        "summary": "Establishes mandatory standards and levels of medical care for human space exploration, covering health stabilization, physiological countermeasures, and medical monitoring requirements.",
        "parameters_established": [
            "Clinical monitoring thresholds",
            "Medical event categorization",
            "Aeromedical evacuation triggers",
            "Countermeasure prescription"
        ],
        "dashboard_relevance": "Governs the severity categorization (Info, Warning, Critical) and non-diagnostic explanation boundaries for physiological alerts.",
        "limitations": "Standard is operational policy, not an algorithm. Clinical decisions require a certified NASA Flight Surgeon."
    },
    {
        "id": "NASA-STD-3001-V2",
        "title": "NASA Spaceflight Human-System Standard, Volume 2: Human Factors, Habitability, and Environmental Health",
        "organization": "NASA OCHMO / Johnson Space Center",
        "url": "https://www.nasa.gov/reference/nasa-std-3001v2/",
        "study_id": "NASA-STD-3001-VOL-2-REV-D",
        "publication_date": "Revision D (2023)",
        "summary": "Defines environmental limits for spacecraft habitats, including atmosphere composition, partial pressure of carbon dioxide, cabin acoustics, lighting, and radiation thresholds.",
        "parameters_established": [
            "ppCO2 nominal target: < 3.0 mmHg (0.4 kPa)",
            "ppCO2 24-hour limit: < 4.0 mmHg",
            "Cabin temperature: 18.3°C to 26.7°C",
            "Oxygen partial pressure: 19.5% to 23.1%"
        ],
        "dashboard_relevance": "Direct source for the environmental habitat alert thresholds (Scenario E and environmental HUD).",
        "limitations": "Environmental thresholds apply to bulk cabin air; microgravity lacks buoyant convection, meaning micro-pockets near crew heads may exceed sensor readings."
    },
    {
        "id": "NASA-OCHMO-TB-004",
        "title": "OCHMO Technical Brief: Carbon Dioxide in Spaceflight",
        "organization": "NASA Office of the Chief Health and Medical Officer",
        "url": "https://www.nasa.gov/ochmo-tb-004-carbon-dioxide-2/",
        "study_id": "OCHMO-TB-004",
        "publication_date": "2020",
        "summary": "Scientific review of astronaut hypercapnic symptoms, documenting that astronauts experience headaches, cognitive slowing, and vision alterations at lower CO2 concentrations in microgravity than on Earth.",
        "parameters_established": [
            "CO2 pocket accumulation risk during exercise",
            "Headache probability vs 24h ppCO2 average",
            "Interaction between CO2 and cephalad fluid shifts"
        ],
        "dashboard_relevance": "Correlates habitat ppCO2 spikes with cognitive alertness drops and elevated respiration in the alert explanation engine.",
        "limitations": "Individual susceptibility to space headaches from CO2 varies significantly among crew members."
    },
    {
        "id": "NTRS-20230014025",
        "title": "Spaceflight Standard Measures: Comprehensive Human Research Protocol",
        "organization": "NASA Technical Reports Server (NTRS)",
        "url": "https://ntrs.nasa.gov/citations/20230014025",
        "study_id": "NASA/TM-20230014025",
        "publication_date": "2023",
        "summary": "Technical memorandum detailing the sensor modalities, test batteries, and standard operating procedures for human physiological tracking aboard long-duration exploration missions.",
        "parameters_established": [
            "Continuous wearable PPG and ECG telemetry methods",
            "Resting vs active heart rate dynamics in microgravity",
            "Core temperature circadian amplitude shifts ('Space Fever')"
        ],
        "dashboard_relevance": "Provides baseline parameters for the high-fidelity synthetic telemetry generator.",
        "limitations": "Focuses on LEO (ISS) data; deep space galactic cosmic ray interactions remain an open research frontier."
    },
    {
        "id": "NTRS-20230003916",
        "title": "Astronaut Sleep Duration and Sleep Architecture During Long-Duration Space Missions",
        "organization": "NASA Technical Reports Server (NTRS)",
        "url": "https://ntrs.nasa.gov/citations/20230003916",
        "study_id": "NASA/TP-20230003916",
        "publication_date": "2023",
        "summary": "Actigraphy and sleep log analysis establishing that astronauts average 6.0 to 6.4 hours of sleep per night aboard the ISS, suffering frequent sleep fragmentation and circadian misalignment.",
        "parameters_established": [
            "Actigraphy sleep efficiency norm: 75% to 85%",
            "Sleep deficiency threshold: < 6.0 hours/night",
            "Psychomotor Vigilance Task (PVT) performance decay"
        ],
        "dashboard_relevance": "Informs the Crew Health sleep architecture card and the Scenario C (Sleep Deficit) demonstration.",
        "limitations": "Subjective sleep quality does not always align with objective actigraphy sleep efficiency."
    },
    {
        "id": "NASA-OSDR-OVERVIEW",
        "title": "NASA Open Science Data Repository (OSDR)",
        "organization": "NASA Biological and Physical Sciences Division",
        "url": "https://science.nasa.gov/biological-physical/data/osdr/",
        "study_id": "OSDR-OPEN-SCIENCE",
        "publication_date": "Active 2026",
        "summary": "NASA's premier public repository unifying biological, phenotypic, and multi-omics data from spaceflight experiments and analog investigations.",
        "parameters_established": [
            "FAIR data principles for spaceflight science",
            "Multi-omics cross-referencing capabilities"
        ],
        "dashboard_relevance": "Serves as the research anchor for open science exploration. Note: OSDR primarily houses non-human and omics datasets; human operational biometrics require LSDA protocol access.",
        "limitations": "Studies in OSDR vary widely in model organisms (rodents, plants, cell cultures). Specific human telemetry must not be attributed to model organism studies (e.g. OSD-87/OSD-665)."
    },
    {
        "id": "DFROBOT-HUSKYLENS-V2",
        "title": "HUSKYLENS 2 Protocol and Algorithm Reference",
        "organization": "DFRobot Technical Documentation",
        "url": "https://github.com/DFRobot/DFRobot_HuskylensV2/blob/master/HuskyLens2_Protocol.md",
        "study_id": "DFR-HL2-PROTO",
        "publication_date": "2024",
        "summary": "Technical communication specification for the HuskyLens 2 AI vision sensor, detailing serial protocol, algorithm IDs, coordinate systems, and confidence metrics.",
        "parameters_established": [
            "Algorithm 13: Facial Expression Recognition",
            "Algorithm 19: Fall Detection",
            "Algorithm 9: Pose Recognition",
            "Algorithm 2: Object Recognition"
        ],
        "dashboard_relevance": "Direct technical blueprint for the computer vision adapter and hardware integration workspace.",
        "limitations": "Edge AI confidence depends on habitat ambient lighting, camera angle, and subject distance."
    }
]
