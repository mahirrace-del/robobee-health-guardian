# AstroHealth Guardian — ESP32 Wearable Firmware Guide

This directory contains the production-ready firmware sketch for the **Astronaut Bio-Wristband prototype** (`firmware/esp32_wearable.ino`).

---

## 1. Hardware Bill of Materials (BOM)
* **Microcontroller:** ESP32-WROOM-32, ESP32-S3, or NodeMCU ESP32.
* **Optical PPG Sensor:** MAX30102 or MAX30100 (Pulse Oximetry + Heart Rate).
* **Skin Temperature Sensor:** 10k NTC Thermistor with 10k voltage divider resistor (or DS18B20 digital 1-Wire probe).
* **IMU (Optional):** MPU6050 6-Axis Accelerometer/Gyroscope for actigraphy and motion tracking.

---

## 2. Electrical Wiring & Pinout

| Sensor Pin | ESP32 Pin | Function / Description |
| :--- | :--- | :--- |
| **MAX30102 VIN** | 3.3V | Regulated DC Power |
| **MAX30102 GND** | GND | Common Ground |
| **MAX30102 SDA** | GPIO 21 | I2C Serial Data line |
| **MAX30102 SCL** | GPIO 22 | I2C Serial Clock line |
| **MAX30102 INT** | GPIO 19 (Optional) | Data ready interrupt |
| **NTC Thermistor Signal** | GPIO 34 | Analog-to-Digital (ADC1) Input |
| **MPU6050 SDA** | GPIO 21 | Shared I2C Bus |
| **MPU6050 SCL** | GPIO 22 | Shared I2C Bus |

---

## 3. Arduino IDE Setup Instructions
1. Open Arduino IDE (v2.0+ recommended).
2. Install **ESP32 Board Support**:
   - Go to `File` > `Preferences` > `Additional Boards Manager URLs`.
   - Add: `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`.
   - Open `Tools` > `Board Manager` and install **esp32 by Espressif Systems**.
3. Install Required Libraries via Library Manager (`Sketch` > `Include Library` > `Manage Libraries`):
   - **ArduinoJson** (by Benoit Blanchon, v6 or v7)
   - **SparkFun MAX3010x Pulse and Proximity Sensor Library**
4. Configure Wi-Fi in `esp32_wearable.ino`:
   ```cpp
   const char* WIFI_SSID     = "YOUR_WIFI_NETWORK";
   const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
   const char* INGEST_URL    = "http://YOUR_SERVER_IP:8000/api/telemetry/ingest";
   ```
5. Select your ESP32 board and COM port, then click **Upload**.

---

## 4. Transmission Protocol (Schema v1.0)
The firmware automatically sends periodic HTTP POST requests to `/api/telemetry/ingest` at 1 Hz in JSON format:
```json
{
  "schema_version": "1.0",
  "device_id": "esp32-wearable-01",
  "sequence": 1042,
  "measurements": {
    "heart_rate": {
      "value": 72.0,
      "unit": "bpm",
      "quality": "valid"
    },
    "spo2": {
      "value": 98.2,
      "unit": "%",
      "quality": "valid"
    },
    "skin_temperature": {
      "value": 33.5,
      "unit": "°C",
      "quality": "valid"
    }
  }
}
```
Upon receiving validated packets, the AstroHealth Guardian web platform automatically switches from **SIMULATED** mode to **LIVE HARDWARE** mode.
