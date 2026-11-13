"""
Automated Tests — Telemetry Schema and Data Contracts
"""

import pytest
from pydantic import ValidationError
from src.models.telemetry import (
    TelemetryFrame,
    MeasurementItem,
    QualityFlag,
    SourceMode,
    DeviceIngestPayload
)


def test_valid_measurement_item():
    item = MeasurementItem(
        value=72.5,
        unit="bpm",
        quality=QualityFlag.VALID,
        source="MAX30102 PPG"
    )
    assert item.value == 72.5
    assert item.unit == "bpm"
    assert item.quality == QualityFlag.VALID
    assert item.is_derived is False


def test_missing_measurement_item():
    item = MeasurementItem(
        value=None,
        unit="bpm",
        quality=QualityFlag.MISSING
    )
    assert item.value is None
    assert item.quality == QualityFlag.MISSING


def test_derived_map_measurement():
    item = MeasurementItem(
        value=93.3,
        unit="mmHg",
        quality=QualityFlag.VALID,
        is_derived=True,
        calculation_method="MAP ≈ (SBP + 2 × DBP) / 3"
    )
    assert item.is_derived is True
    assert item.calculation_method is not None


def test_valid_device_ingest_payload():
    payload = {
        "schema_version": "1.0",
        "device_id": "esp32-wearable-01",
        "sequence": 42,
        "measurements": {
            "heart_rate": {"value": 75.0, "unit": "bpm", "quality": "valid"},
            "spo2": {"value": 98.5, "unit": "%", "quality": "valid"}
        }
    }
    model = DeviceIngestPayload(**payload)
    assert model.device_id == "esp32-wearable-01"
    assert model.sequence == 42
    assert "heart_rate" in model.measurements
    assert model.measurements["heart_rate"]["value"] == 75.0


def test_invalid_device_ingest_payload():
    # Missing sequence
    invalid_payload = {
        "schema_version": "1.0",
        "device_id": "esp32-wearable-01",
        "measurements": {}
    }
    with pytest.raises(ValidationError):
        DeviceIngestPayload(**invalid_payload)
