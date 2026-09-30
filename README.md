# Machine Vision PHEV Charging Pipeline with Spot-Price Validation

**Author:** Ivan Shuba  
**Institution:** Metropolia University of Applied Sciences (AMK)  
**Degree Programme:** Electrical and Automation Engineering  
**Project Date:** September 2026  

An autonomous, edge-assisted vision and energy optimization pipeline integrated with Home Assistant. The project automatically detects the presence of a Plug-in Hybrid Electric Vehicle (PHEV) in a driveway using local AI vision, verifies physical plug connectivity via dynamic load-testing, and calculates cheap Nord Pool electricity windows to complete charging before a daily 07:00 AM deadline.

---

## Problem & Workflow Supported

### Core Problem
The electricity contract features a flexible adjustment rate based on the difference between the monthly average electricity price and average consumption price. To minimize electricity bills, energy must be purchased at the lowest prices or below the daily mean.

Standard time-window automations present several operational challenges:
1. **Unnecessary Relaying:** Activating high-power relays when the vehicle is not parked at home.
2. **False Cable Detection:** Simple occupancy sensors cannot verify whether the charging cable is physically plugged into the vehicle inlet.
3. **Midnight Price Rollover Glitches:** At 00:00, Nord Pool resets "today" prices to "yesterday" data, causing naive schedulers to forget already completed charging cycles and attempt to schedule full multi-hour windows again before morning.

### Workflow Supported
1. **Visual Vehicle Detection:** Captures camera snapshots from the driveway, isolates a Region of Interest (ROI), and verifies vehicle presence using YOLOv8.
2. **Dynamic Cable Verification (Test Charge):** Triggers a 1-minute test charge upon arrival. If power consumption exceeds 1.5 kW, the cable connection is verified.
3. **Counter-Based Cheap Window Calculation:** Calculates required 15-minute charging slots (target_max - completed_slots) up to a strict 07:00 AM deadline.
4. **Forced Charging Mode:** Provides an instant override to charge immediately for up to 6 hours regardless of electricity tariffs, auto-reverting to normal mode afterward.

---

## Hardware Components

- **Vehicle:** Plug-in Hybrid Electric Vehicle (PHEV) requiring approximately 6 hours (24 x 15-min slots) for a full charge.
- **Server:** Raspberry Pi running Home Assistant Core.
- **Camera:** Ring Doorbell with camera covering the driveway parking space.
- **Relay:** ZigBee smart relay switch equipped with an integrated power meter on the main charger powerline.

---

### Architecture Diagram

```text
[ Ring Doorbell Camera ]
          │
          ▼ (Cloud Push / Snapshot Event)
[ Ring-MQTT Gateway ]
          │
          ▼ (MQTT Snapshot Topic)
[ Python Vision Daemon ]
   ├── Paho-MQTT Thread
   ├── YOLOv8 ROI Inference Engine
   └── State Publisher (binary_sensor.white_ev_driveway)
          │
          ▼ (MQTT Discovery & State Topics)
[ Home Assistant Engine ]
   ├── 1-Min Test Charge Logic (Power > 1.5 kW Check)
   ├── Dynamic Target Calculator (07:00 AM Deadline)
   ├── Forced Charge Override (6-Hour Safety Limit)
   └── ZigBee Relay Switch (switch.ev_charger_powerline)
```

---

## Models, Libraries, APIs & Services Used

- **Ultralytics YOLOv8 Nano (yolov8n):** Lightweight object detection model detecting COCO Class 2 (car) on edge hardware without high CPU usage.
- **OpenCV (cv2) & NumPy:** Matrix operations, frame decoding (imdecode), and bounding box ROI polygon intersection testing.
- **Paho-MQTT & Ring-MQTT:** Asynchronous MQTT pub/sub client connecting Ring camera streams to local processing threads.
- **Nord Pool Home Assistant Integration:** Provides 15-minute dynamic spot prices (raw_today, raw_tomorrow).

---

## Input & Output Data

### Inputs
1. **Camera Snapshots:** Binary JPEG image pushed via MQTT (`ring/.../snapshot/image`).
2. **Power Meter Telemetry:** Real-time power draw in Watts (`sensor.charger_power_meter`).
3. **Nord Pool Price Feed:** Array of 15-minute electricity rates (€/kWh).
4. **User Override:** Boolean switch for forced instant charging (`input_boolean.forced_charge`).

### Outputs
1. **Occupancy Sensor:** `binary_sensor.white_ev_driveway` (ON/OFF).
2. **Cable Status:** `binary_sensor.ev_cable_connected` (Verified if test power > 1500 W).
3. **Target Slot Engine:** Counter-based dynamic 15-minute state matching (target_max - done).
4. **Relay Actuation:** Physical ZigBee relay toggle (`switch.ev_charger_powerline`).

---

## Pipeline Execution & Integration Workflow

1. **Arrival & Snapshot Processing:** Upon driveway motion, Ring-MQTT pushes a snapshot. The Ring cloud endpoint freezes frame capture for 3 minutes during motion recording—this delay provides a built-in buffer allowing the driver to park and plug in the car without triggering false early scans.
2. **ROI Scan:** The Python script crops the incoming snapshot against the predefined driveway ROI coordinates.
3. **Cable Validation (Test Charge):** When the car enters the ROI, Home Assistant activates the relay for a 1-minute test. If power draw exceeds 1.5 kW, the system flags the cable as plugged in; otherwise, the relay turns off.
4. **Optimized Schedule Execution:** The system ranks future 15-minute price slots up to 07:00 AM and turns on the relay during the cheapest slots until `counter.ev_15min_done` reaches `target_max`.

---

## Testing, Validation & Edge-Case Handling

- **Test Charge Verification:** Verified using real power consumption graphs. Vehicles plugged in immediately register >1.5 kW during the 1-minute test, whereas unplugged states show 0 W, preventing relay activation during cheap price windows when the car is absent.
- **00:00 Rollover Fix:** Mitigated day-change bugs by replacing fixed 24-hour array matching with a dynamic counter equation: `needed_slots = target_max - counter.ev_15min_done`. The counter increments on each active 15-minute slot and resets strictly at 07:00 AM.
- **Forced Charge Safety:** Forced charging overrides energy price checks and automatically turns off after 6 hours to prevent overcharging or prolonged high-power exposure.

---

## Observed Issues & Limitations

1. **Neighbor Vehicle Triggers:** The baseline `yolov8n` COCO model detects any `car` class. If a neighbor's vehicle enters the ROI periphery, it can trigger false occupancy alerts.
   * *Proposed Solution:* Fine-tuning YOLOv8 on custom driveway dataset labeled specifically for the user's white PHEV or tightening polygon coordinates using `cv2.pointPolygonTest`.
2. **Ring API Snapshot Lockouts:** Ring cameras lock snapshot feeds during active motion clip uploading (~3 minutes). While non-critical for battery charging, real-time tracking requires a dedicated local RTSP camera feed.

---

## Setup & Quickstart Guide
### 1. Repository Setup

```code
git clone [https://github.com/IvaShuba/Machine-Vision-PHEV-Charging-Pipeline-with-Spot-Price-Validation](https://github.com/IvaShuba/Machine-Vision-PHEV-Charging-Pipeline-with-Spot-Price-Validation)
cd phev-vision-charging

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration (.env)
```code
MQTT_BROKER_IP=127.0.0.1
MQTT_PORT=1883
MQTT_USER=YourMQTTUsername
MQTT_PASSWORD=YourSecretPassword
RING_CAMERA_ID=YourRingID
RING_LOCATION_ID=YourRingLocationID
```
### 3. Execution
```code
# Run Vision Processing Daemon
python3 main.py
```

---

## Privacy, Security & Safety Considerations

- **Privacy:** All frame decoding and YOLOv8 inference execute 100% locally on internal hardware. Camera streams are not transmitted to third-party AI clouds.
- **Equipment Safety:** Relay toggling is bound to 15-minute interval boundaries, preventing high-frequency switching chatter and protecting onboard EV contactors.
- **Surveillance Ethics:** ROI mask is bounded strictly to private property lines to comply with local privacy regulations regarding public space surveillance.

---

## References & Citations

1. **Shuba, I. (2026).** *Machine vision PHEV charging pipeline with electricity price validation.* Project Report, Metropolia University of Applied Sciences.
2. **Ultralytics YOLOv8 Documentation:** https://docs.ultralytics.com/
3. **Home Assistant Core Documentation:** https://www.home-assistant.io/docs/
4. **Nord Pool Integration for Home Assistant:** https://github.com/custom-components/nordpool
