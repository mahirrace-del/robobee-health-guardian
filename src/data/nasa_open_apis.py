"""
AstroHealth Guardian — Live Public NASA Open Data & API Bridge
Connects cleanly (with caching and local offline fallback for Distance-from-Earth delays) to:
  1. NASA DONKI (api.nasa.gov) — Real-time solar flare, CME, and SPE space-weather notifications
  2. NASA OSDR (osdr.nasa.gov) — Open Science Data Repository spaceflight biology datasets
  3. NASA NTRS (ntrs.nasa.gov) — Technical Reports Server operational & aerospace literature
"""

import os
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

CACHE_DIR = Path("data")
CACHE_DIR.mkdir(exist_ok=True)
CACHE_FILE = CACHE_DIR / "nasa_api_cache.json"
CACHE_TTL_SECONDS = 600.0

_MEMORY_CACHE: Dict[str, Any] = {}
_OFFLINE_DELAY_MODE: bool = False


NASA_PUBLIC_PORTALS: List[Dict[str, str]] = [
    {
        "name": "NASA Open Data Portal",
        "url": "https://data.nasa.gov",
        "role": "Public datasets covering spaceflight operations, hardware, and environmental records.",
    },
    {
        "name": "NASA API Portal (DONKI Space Weather)",
        "url": "https://api.nasa.gov",
        "role": "Live Coronal Mass Ejection (CME), Solar Flare (FLR), and Solar Particle Event notifications.",
    },
    {
        "name": "NASA Open Science Data Repository (OSDR)",
        "url": "https://osdr.nasa.gov",
        "role": "FAIR spaceflight biology, phenotypic, and multi-omics space radiation/microgravity studies.",
    },
    {
        "name": "NASA Technical Reports Server (NTRS)",
        "url": "https://ntrs.nasa.gov",
        "role": "NASA-STD-3001, Spaceflight Standard Measures, sleep architecture, and CO2 technical briefs.",
    },
    {
        "name": "NASA Earthdata & JPL Resources",
        "url": "https://earthdata.nasa.gov",
        "role": "Planetary and Earth-observation open APIs (paired with jpl.nasa.gov engineering resources).",
    },
]


DEFAULT_OFFLINE_NASA_BUNDLE: Dict[str, Any] = {
    "fetched_at": "2026-11-14T00:00:00+00:00",
    "source_status": "offline_cached_reference",
    "donki": {
        "radiation_alert_active": False,
        "count": 1,
        "latest_event_type": "CME",
        "latest_event_id": "20261106-AL-001",
        "latest_issue_time": "2026-11-06T01:56Z",
        "notifications": [
            {
                "messageID": "20261106-AL-001",
                "messageType": "CME",
                "messageIssueTime": "2026-11-06T01:56Z",
                "messageURL": "https://ccmc.gsfc.nasa.gov/DONKI/view/Alert/49397/1",
                "summary": "Cached reference CME space weather alert (NASA CCMC DONKI). Switch off Offline Mode for live refresh.",
            }
        ],
    },
    "osdr_studies": [
        {
            "accession": "OSD-87",
            "title": "Microgravity & Spaceflight Autonomic / Rodent Cardiac Gene Expression Reference",
            "url": "https://osdr.nasa.gov/bio/repo/data/studies/OSD-87",
            "source": "NASA OSDR (Model Organism Archive)",
        },
        {
            "accession": "OSD-665",
            "title": "Spaceflight Tissue Multi-Omics & Bone Density Adaptation Dataset",
            "url": "https://osdr.nasa.gov/bio/repo/data/studies/OSD-665",
            "source": "NASA OSDR",
        },
    ],
    "ntrs_citations": [
        {
            "id": "20230014025",
            "title": "Spaceflight Standard Measures: Comprehensive Human Research Protocol",
            "published": "2023",
            "url": "https://ntrs.nasa.gov/citations/20230014025",
        },
        {
            "id": "20230003916",
            "title": "Astronaut Sleep Duration and Sleep Architecture During Long-Duration Space Missions",
            "published": "2023",
            "url": "https://ntrs.nasa.gov/citations/20230003916",
        },
    ],
}


def set_offline_delay_mode(enabled: bool) -> bool:
    """Toggles Mars Deep-Space Delay / Offline Autonomous Mode."""
    global _OFFLINE_DELAY_MODE
    _OFFLINE_DELAY_MODE = bool(enabled)
    return _OFFLINE_DELAY_MODE


def is_offline_delay_mode() -> bool:
    return _OFFLINE_DELAY_MODE


def _http_get_json(url: str, timeout: float = 4.5) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "RoboBee-AstroHealth-Guardian/2.0 (NASA-Space-Apps-2026)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
        return json.loads(raw)


def _fetch_donki_notifications() -> Dict[str, Any]:
    api_key = (os.environ.get("NASA_API_KEY") or "DEMO_KEY").strip()
    url = f"https://api.nasa.gov/DONKI/notifications?type=all&api_key={urllib.parse.quote(api_key)}"
    raw = _http_get_json(url)
    items = raw if isinstance(raw, list) else []
    parsed: List[Dict[str, str]] = []
    solar_alert = False
    for row in items[:5]:
        mtype = str(row.get("messageType", "SpaceWeather"))
        if mtype in ("FLR", "SEP", "CME", "RBE", "IPS"):
            solar_alert = True
        body_clean = " ".join(str(row.get("messageBody", "")).split())
        parsed.append({
            "messageID": str(row.get("messageID", "")),
            "messageType": mtype,
            "messageIssueTime": str(row.get("messageIssueTime", "")),
            "messageURL": str(row.get("messageURL", "https://api.nasa.gov/")),
            "summary": body_clean[:240] + ("..." if len(body_clean) > 240 else ""),
        })
    latest = parsed[0] if parsed else {}
    return {
        "radiation_alert_active": solar_alert,
        "count": len(items),
        "latest_event_type": latest.get("messageType", "Nominal"),
        "latest_event_id": latest.get("messageID", "None"),
        "latest_issue_time": latest.get("messageIssueTime", ""),
        "notifications": parsed,
    }


def _fetch_osdr_studies(topic: str = "microgravity") -> List[Dict[str, str]]:
    q = urllib.parse.quote(topic or "microgravity")
    url = f"https://osdr.nasa.gov/osdr/data/search?term={q}&size=4"
    raw = _http_get_json(url)
    hits = ((raw or {}).get("hits") or {}).get("hits") or []
    studies: List[Dict[str, str]] = []
    for hit in hits[:4]:
        src = hit.get("_source") or {}
        acc = str(src.get("Accession") or hit.get("_id") or "OSD").strip()
        title = str(src.get("Study Title") or src.get("Study Protocol Name") or f"NASA OSDR Study {acc}").strip()
        studies.append({
            "accession": acc,
            "title": title[:140],
            "url": f"https://osdr.nasa.gov/bio/repo/data/studies/{urllib.parse.quote(acc)}",
            "source": f"NASA OSDR ({src.get('Project Type', 'Space Biology')})",
        })
    return studies


def _fetch_ntrs_citations(topic: str = "spaceflight CO2") -> List[Dict[str, str]]:
    q = urllib.parse.quote(topic or "spaceflight health")
    url = f"https://ntrs.nasa.gov/api/citations/search?q={q}&page%5Bsize%5D=4"
    raw = _http_get_json(url)
    results = (raw or {}).get("results") or []
    out: List[Dict[str, str]] = []
    for item in results[:4]:
        cid = str(item.get("id", "")).strip()
        title = str(item.get("title", f"NASA Technical Report {cid}")).strip()
        pub_list = item.get("publications") or []
        pub_date = str(pub_list[0].get("publicationDate", ""))[:10] if pub_list and isinstance(pub_list[0], dict) else "NASA NTRS"
        out.append({
            "id": cid,
            "title": title[:140],
            "published": pub_date or "NASA NTRS",
            "url": f"https://ntrs.nasa.gov/citations/{cid}" if cid else "https://ntrs.nasa.gov/",
        })
    return out


def _read_disk_cache() -> Optional[Dict[str, Any]]:
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _write_disk_cache(bundle: Dict[str, Any]) -> None:
    try:
        CACHE_FILE.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_nasa_live_bundle(
    topic: str = "microgravity",
    fetch_live: bool = True,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Returns cached or freshly fetched NASA DONKI + OSDR + NTRS data.
    Automatically serves cached/offline fallback during Mars Delay mode or network loss.
    """
    cache_key = (topic or "microgravity").strip().lower()
    now_mono = time.monotonic()

    if _OFFLINE_DELAY_MODE:
        cached = _MEMORY_CACHE.get(cache_key, {}).get("data") or _read_disk_cache() or dict(DEFAULT_OFFLINE_NASA_BUNDLE)
        return {
            **cached,
            "offline_delay_mode": True,
            "source_status": "offline_mars_delay_autonomous_cache",
            "portals": NASA_PUBLIC_PORTALS,
        }

    if not force_refresh and cache_key in _MEMORY_CACHE:
        entry = _MEMORY_CACHE[cache_key]
        if (now_mono - entry["ts"]) < CACHE_TTL_SECONDS:
            return {
                **entry["data"],
                "offline_delay_mode": False,
                "portals": NASA_PUBLIC_PORTALS,
            }

    if not fetch_live:
        cached = _read_disk_cache() or dict(DEFAULT_OFFLINE_NASA_BUNDLE)
        return {
            **cached,
            "offline_delay_mode": False,
            "portals": NASA_PUBLIC_PORTALS,
        }

    donki = DEFAULT_OFFLINE_NASA_BUNDLE["donki"]
    osdr = DEFAULT_OFFLINE_NASA_BUNDLE["osdr_studies"]
    ntrs = DEFAULT_OFFLINE_NASA_BUNDLE["ntrs_citations"]
    live_hits = 0

    try:
        donki = _fetch_donki_notifications()
        live_hits += 1
    except Exception:
        pass

    try:
        osdr_res = _fetch_osdr_studies(topic)
        if osdr_res:
            osdr = osdr_res
            live_hits += 1
    except Exception:
        pass

    try:
        ntrs_res = _fetch_ntrs_citations(topic)
        if ntrs_res:
            ntrs = ntrs_res
            live_hits += 1
    except Exception:
        pass

    status = "live_nasa_apis" if live_hits >= 2 else ("partial_live_nasa_apis" if live_hits == 1 else "offline_cached_fallback")
    bundle = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "source_status": status,
        "live_feeds_connected": live_hits,
        "donki": donki,
        "osdr_studies": osdr,
        "ntrs_citations": ntrs,
    }
    _MEMORY_CACHE[cache_key] = {"ts": now_mono, "data": bundle}
    if live_hits > 0:
        _write_disk_cache(bundle)

    return {
        **bundle,
        "offline_delay_mode": False,
        "portals": NASA_PUBLIC_PORTALS,
    }
