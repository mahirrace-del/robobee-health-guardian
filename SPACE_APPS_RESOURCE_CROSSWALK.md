# NASA Space Apps 2026 Health Monitoring Software — Resource Crosswalk

**Reviewed:** 2026-11-13  
**Project:** RoboBee Health Guardian / Lunar  
**Scope:** Resources currently shown on the official challenge Resources tab, compared with the project concept and current workspace implementation. This is a product and evidence review, not clinical validation.

## Executive summary

The challenge asks for software that gathers health indicators and helps astronauts evaluate and act on health changes. NASA organizes the problem around five hazards: radiation, isolation/confinement, distance from Earth, altered gravity, and the hostile/closed environment. Its risks include changes to cardiovascular, immune, sensorimotor, bone/muscle, sleep/circadian, behavioral, and operational health. RoboBee already has a broad dashboard, telemetry and simulated scenarios, a 3D body guide, Lunar conversation/body-focus wiring, and persisted symptom follow-ups. The distinctive product direction is to connect those pieces into a crew-controlled, longitudinal decision-support workflow that uses multiple evidence sources and lets Lunar direct attention to a 3D body region.

The concept should not be pitched as “AI camera diagnoses astronauts” or as a replacement for wearables. NASA has completed wearable ECG/health-monitor prototypes, while NASA’s roadmap still lists automated video-analysis maturation as planned-unfunded. This supports a narrower, defensible gap: integrate available device/environment data, crew reports, and optional camera observations into one explainable, offline-capable workflow, with provenance and crew confirmation. The camera is an adjunct for observable context (for example, helping document a visible wound or movement), not a way to infer internal vitals, diagnose disease, or infer mental state.

## Challenge page resources checked

The official Resources tab lists the following five links:

1. [NASA — 5 Hazards of Human Spaceflight](https://www.nasa.gov/hrp/hazards/)
2. [NASA — Risks of Human Spaceflight](https://www.nasa.gov/hrp/risks/)
3. [NASA — Ongoing HRP Research in Space](https://www.nasa.gov/hrp/ongoing-hrp-research/)
4. [Canadian Space Agency — Monitoring radiation for astronaut health (2026-02-26)](https://www.asc-csa.gc.ca/eng/news/articles/2026/2026-02-26-monitoring-radiation-astronaut-health.asp)
5. [Canadian Space Agency — Why do we conduct science experiments in space?](https://www.asc-csa.gc.ca/eng/iss/science/why-do-we-conduct-science-experiments-in-space.asp)

The partner resources shown on this page are Canadian Space Agency (CSA) resources. CSA is Canada’s national space agency, not a U.S. agency; NASA is the U.S. agency represented in the NASA data/resources section. The challenge page also warns that NASA does not endorse non-U.S. Government entities and that participants must follow each external site’s data-use terms.

## What the resources say

### Five hazards and example product implications

NASA’s five-hazards framing is a useful top-level taxonomy. It is not a list of sensors that one camera or wearable can measure.

| Hazard | Why it matters to the product | RoboBee state and recommended extension |
|---|---|---|
| Space radiation | Cumulative exposure and solar events matter to long missions. | Radiation is present in the telemetry model and dashboard, but must be shown as live only when supplied by a connected, identified instrument. Add dose history, rate/trend, source, timestamp, quality, and a crew/mission threshold. Do not claim the camera measures radiation. CSA’s CANS work is specifically an autonomous neutron-radiation measurement instrument; this is a separate sensor domain from optical monitoring. |
| Isolation and confinement | Sleep, mood, cognition, workload, team functioning, and behavior can change over time. | Add private crew check-ins and validated task-level measures where allowed; offer optional camera-based observable-event summaries only with consent and explicit limitations. Never label facial expression as a mental-health diagnosis. Provide crew-controlled visibility and retention. |
| Distance from Earth | Communication delay and limited access to Earth-based care raise the value of local autonomy. | Prioritize offline-first operation, locally stored crew records/protocols, graceful degraded modes, asynchronous handoff, compact data, and clear “not available” states. The current app is local-first in its demo architecture but needs explicit offline/reconnect and data-retention behavior for mission use. |
| Altered gravity | Cardiovascular adaptation, bone/muscle loss, balance/sensorimotor changes, and movement risk require longitudinal context. | Pair physiological trends with exercise/activity and crew-reported symptoms. Camera may help document posture or a movement task, but such measures need validation and should be compared to an individual baseline. Wearables/IMUs remain valuable. |
| Hostile/closed environment | Cabin atmosphere, temperature, and other habitat conditions can affect crew health. | The UI already has habitat/environment cards and telemetry fields. Connect them to real sensors, distinguish measured/derived/demo values, show quality and stale state, and correlate environmental changes with symptoms without asserting causation. |

NASA’s risks page and Human Research Program cover further risks including immune alterations, sensorimotor/vestibular changes, cardiovascular changes, sleep loss/circadian desynchronization, workload, injury, radiation-related risks, and other performance/health outcomes. NASA’s ongoing research page describes work across the hazards and uses biological samples and other research methods; a software dashboard should link evidence to its source rather than present research results as individual crew diagnoses. [NASA HRP risks](https://www.nasa.gov/hrp/risks/) · [NASA ongoing HRP research](https://www.nasa.gov/hrp/ongoing-hrp-research/)

Examples currently highlighted on NASA’s ongoing-research page include Artemis II immune biomarkers and standard measures; ISS work on brain/fluid pressure and eye changes, CIPHER multi-system observations, gravity-transition effects on piloting, occupant protection, spinal-fluid biomarkers, standardized physiological and psychological measures, venous haemostasis, and exercise research. The page also describes past investigations using blood, saliva, urine, and other biospecimens for immunity and omics, and a Tempus Pro telemedicine/data-integration device. This makes two product boundaries clear: many important risks require lab samples, clinical instruments, or validated task measures rather than an ordinary camera; and the integration/record layer can still be useful if it preserves source, meaning, and limits for each measure. These are research programs/investigations, not necessarily cleared or available commercial products.

### CSA partner material

The CSA radiation resource describes the Canadian Active Neutron Spectrometer (CANS), a compact autonomous instrument being developed to measure neutron exposure continuously. This reinforces that radiation monitoring is an instrument/data integration problem; it is not achievable from a regular camera feed. The CSA science overview explains why ISS experiments support deep-space preparation: longer exposure to microgravity and radiation, isolation, communication delay, and reduced reliance on Earth-based resources. [CSA CANS overview](https://www.asc-csa.gc.ca/eng/news/articles/2026/2026-02-26-monitoring-radiation-astronaut-health.asp) · [CSA why space science](https://www.asc-csa.gc.ca/eng/iss/science/why-do-we-conduct-science-experiments-in-space.asp)

### Existing work and the actual opportunity

NASA’s Human Research Roadmap lists completed wearable systems and a completed Lunar Health Monitor task that demonstrated a TRL 5 wearable system using dry-electrode ECG in a harness. Therefore, continuous wearable ECG/physiological monitoring is not by itself a defensible novelty claim. NASA’s roadmap also lists a planned-unfunded task to mature automated video analysis for monitoring crew in autonomous missions. That indicates a research need, not evidence that general-purpose camera health diagnosis is already validated or ready for flight. [NASA Medical-701 gap and tasks](https://humanresearchroadmap.nasa.gov/gaps/gap.aspx?i=716) · [NASA Automated Video Analysis Software Maturation](https://humanresearchroadmap.nasa.gov/Tasks/task.aspx?i=2249) · [NASA Lunar Health Monitor task](https://humanresearchroadmap.nasa.gov/tasks/task.aspx?i=897)

**Defensible distinction:** RoboBee can aim to be the coordination and interaction layer that brings together wearables, habitat sensors, crew self-report, optional camera observations, trend context, scheduled check-ins, and the 3D Lunar body guide. Claim this as a prototype workflow/integration concept, not a validated diagnostic capability or a guaranteed first-of-its-kind system. A full novelty claim requires a broader product and literature search.

## Current implementation cross-check

Based on the current workspace as of this review:

- **Implemented:** telemetry model and ingest, provenance labels (live/simulated/derived/stale/unavailable), missing-sensor behavior, device/alert/research endpoints, scenario simulation, symptom records and crew-confirmed follow-ups, follow-up reminders, Lunar chat/voice endpoints, and a body-focus instruction bridge to the 3D explorer.
- **3D explorer:** manual region selection and Lunar-driven region focus are wired. The model is a visual reference and is not a medical scan; the model mesh is not rigged for limb motion. Focus/zoom must not imply centimeter-level measurement or precise anatomical localization unless calibrated data supports it.
- **Camera:** the application reports camera status and can use a connected configured camera path, but current status behavior explicitly allows “not connected”; no camera hardware is guaranteed. The UI must never imply a live view or detected injury when only a demo/example is shown.
- **Simulated and estimated data:** the dashboard explicitly labels blood pressure as a demo estimate and core temperature as simulated in the current HTML. Radiation and environmental channels must also show source/quality. Keep demo mode visibly separate from real hardware mode.
- **Still needed for a credible mission-oriented demo:** a real device adapter for each claimed signal; explicit live-data provenance on every value and chart; a camera consent/state/retention flow; a small, testable camera use case limited to observable evidence; offline/degraded connectivity behavior; crew privacy/access controls; escalation and crew/medical protocol references; and evaluation with representative scenarios. Do not market the present demo as flight-ready or clinically validated.

## Recommended additions, in priority order

### P0 — Evidence and trust

1. Add a single evidence record contract: value/observation, source device or crew report, observed time, received time, freshness, quality/confidence, mode (live/simulated/derived), and associated body region when relevant.
2. Show provenance consistently on cards, charts, alerts, Lunar replies, body highlights, and exports. A simulation must never be visually indistinguishable from live data.
3. Make Lunar explain what evidence triggered a body focus and what is uncertain. Ask clarifying questions and request crew confirmation before creating or changing a symptom record.
4. Separate observation, interpretation, and action. Use approved crew/medical procedures for escalation; do not diagnose or prescribe medication.

### P1 — Make the camera concept specific and credible

1. Start with one narrow use case: crew-directed capture/documentation of a visible injury or guided movement check, with the crew choosing when the camera runs.
2. Show an evidence preview and allow correction/decline. Attach the observation to the crew-confirmed body region and event timeline; do not silently persist raw video.
3. Do not use facial emotion inference as a proxy for mood or mental health. Use validated self-report/task measures for those domains; any video-derived behavior metrics require validation and privacy review.
4. Add explicit states: camera unavailable, permission needed, ready, capturing, processing, result uncertain, and crew-confirmed. Current camera availability is not guaranteed.

### P2 — Cover the full hazard model with complementary sources

Add a five-hazard view showing coverage, data source, and missing instrumentation for each hazard. Support device adapters for physiology and activity; environmental sensors for cabin conditions; an independent radiation dosimeter; crew check-ins and sleep/workload measures; plus research/library links. Do not suggest that one sensor or AI model covers all five hazards.

### P3 — Deep-space autonomy

Prioritize offline operation, local encrypted records, explicit crew control, minimal-data synchronization, asynchronous ground handoff, and helpful behavior when a sensor/network is unavailable. Preserve audit trails for changes and reminders. For symptom timelines, use confirmed follow-up entries rather than automatically fading an anatomical highlight on a schedule.

### P4 — Validate the claims

Build a small benchmark/demo matrix: missing or stale sensor; contradictory signals; camera unavailable; visible cut with crew confirmation; shoulder pain follow-up improving/not improving; high HR during exercise vs at rest; radiation alert; cabin CO₂/temp excursion; network outage. Measure false alarms, missed events, correct provenance, user understanding, and recovery from unavailable inputs. Label outcomes as prototype evaluation, not clinical validation.

## Suggested presentation wording

> **RoboBee Health Guardian is a crew-centered health monitoring and decision-support prototype for space missions. It combines physiological and habitat telemetry with crew-confirmed symptom tracking, optional camera observations, and Lunar’s interactive 3D body guide. Every signal is labeled by source and freshness, and the system is designed to keep working when connectivity is limited. It supports astronaut awareness and follow-up; it does not replace clinical judgment or diagnose from a camera.**

Describe the value as **integration + longitudinal context + crew interaction + offline-aware decision support**, not as “we invented the astronaut wristband” or “the AI sees every disease.”

## Originality and AI-use record

- **Human-originated concept:** RoboBee/Lunar as a persistent astronaut health guardian; combining camera-assisted observation with wearable/environmental signals; zooming Lunar’s 3D body guide to a relevant area; tracking a crew-reported issue over days and asking whether it improved; and wanting the project’s human ideas separated from AI assistance.
- **AI-assisted work in this review:** visiting and summarizing the challenge’s published resources; checking current workspace capabilities; mapping NASA/CSA hazard and research material to implementation gaps; and drafting this crosswalk and prioritized recommendations.
- **Source/claim boundary:** NASA/CSA descriptions are linked to their primary pages. The product differentiation above is an assessment/inference from those resources and the current repository, not a NASA/CSA endorsement or a verified competitive novelty claim.

