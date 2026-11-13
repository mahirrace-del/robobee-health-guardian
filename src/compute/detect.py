import numpy as np
from typing import Dict, Any, List

def check_zscore_anomaly(
    series: List[float], 
    metric_name: str,
    baseline_window: int = 30, 
    threshold_sd: float = 2.0,
    check_type: str = "drop" # "drop" (e.g. HRV, SpO2) or "spike" (e.g. Heart Rate)
) -> Dict[str, Any]:
    """
    Computes rolling mean and standard deviation against personal baseline.
    Flags when the current value deviates more than threshold_sd from baseline.
    """
    if len(series) < baseline_window + 1:
        return {"fired": False, "reason": "Insufficient baseline history"}
    
    # Establish baseline from preceding window
    baseline = np.array(series[-(baseline_window + 1):-1], dtype=float)
    mu = float(np.mean(baseline))
    sd = float(np.std(baseline, ddof=1))
    current = float(series[-1])
    
    z = (current - mu) / sd if sd > 1e-6 else 0.0
    
    if check_type == "drop":
        fired = bool(z <= -threshold_sd)
    elif check_type == "spike":
        fired = bool(z >= threshold_sd)
    else:
        fired = False
        
    return {
        "rule": f"{metric_name}_{check_type}_anomaly",
        "current": round(current, 2),
        "baseline_mean": round(mu, 2),
        "baseline_sd": round(sd, 2),
        "z": round(z, 2),
        "fired": fired,
        "window_days": baseline_window
    }

def multi_signal_trigger(active_alerts_48h: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Fires when two or more distinct physiological signals deviate within 48 hours.
    """
    unique_signals = {alert["signal"] for alert in active_alerts_48h if alert.get("fired")}
    fired = len(unique_signals) >= 2
    return {
        "rule": "multi_signal_concordance",
        "signals_flagged": list(unique_signals),
        "count": len(unique_signals),
        "fired": fired
    }
