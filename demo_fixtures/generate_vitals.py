"""
AstroHealth Guardian — Fixture Generator Script
Generates 600 records of temporally coherent, realistic NASA astronaut telemetry
incorporating baseline routines, exercise cycles, and physiological anomalies.
"""

import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.compute.generator import TelemetryGenerator


def generate_vitals(records_count: int = 600, output_filename: str = "vitals.json"):
    gen = TelemetryGenerator(seed=42)
    data = []
    
    print(f"Generating {records_count} high-fidelity astronaut telemetry records...")
    
    for i in range(records_count):
        # We simulate a rich 10-minute session:
        # 0-120s: Scenario A (Routine)
        # 121-240s: Scenario B (T2 Exercise Session)
        # 241-360s: Scenario C (Sleep Deficit & Fatigue)
        # 361-460s: Scenario D (Physiological Anomaly: Tachycardia + SpO2 drop)
        # 461-540s: Scenario E (ECLSS CO2 Excursion)
        # 541-600s: Scenario G (Fall Event & Recovery)
        
        if i < 120:
            gen.active_scenario = "Scenario A: Routine Operations"
        elif i < 240:
            gen.active_scenario = "Scenario B: Exercise Session"
        elif i < 360:
            gen.active_scenario = "Scenario C: Sleep Deficit"
        elif i < 460:
            gen.active_scenario = "Scenario D: Physiological Anomaly"
        elif i < 540:
            gen.active_scenario = "Scenario E: Environmental CO2 Excursion"
        else:
            gen.active_scenario = "Scenario G: Fall Event"
            
        frame = gen.generate_frame(step=i)
        data.append(frame.model_dump())
        
    out_dir = Path(__file__).parent
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / output_filename
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    print(f"Successfully generated {len(data)} records at {out_path}")
    return out_path


if __name__ == "__main__":
    generate_vitals()
