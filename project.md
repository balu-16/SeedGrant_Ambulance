# Edge-AI Based Adaptive Traffic Management System with Intelligent Ambulance Priority

## 1. Overview

The project is a prototype **Edge-AI Based Adaptive Traffic Management System with Intelligent Ambulance Priority** for a single four-way junction. It replaces fixed traffic-light timing with dynamic timing driven by real traffic density, and gives priority to ambulances using live GPS reported by a driver mobile app — not siren or camera-based ambulance detection.

Four fixed 1080p cameras, one per road approach, all feed a single **Raspberry Pi 5 (8 GB RAM)**, which acts as the real-time edge controller. All normal traffic decisions happen locally on the Pi and do not depend on the cloud. AWS is used only for centralized tasks such as authentication, ambulance-driver management, GPS tracking, junction and device registration, historical traffic data, analytics, dashboard data, and emergency-session coordination.

## 2. Problem Statement

Conventional traffic lights usually run fixed timings — for example, giving every road 60 seconds even when one side has 100 vehicles and another has only 10. The system makes this dynamic. Its two goals are:

1. **Adaptive signal timing** based on real traffic density at each approach.
2. **Automatic green priority** for approaching ambulances.

## 3. System Architecture

The separation between the edge layer and the cloud layer is a core design principle: the Pi handles **local real-time traffic control**, while AWS handles the **central backend**.

### 3.1 Edge Layer — Raspberry Pi 5

The Pi runs the full real-time pipeline locally:

- Camera capture (four streams)
- Vehicle detection
- Vehicle tracking
- Vehicle counting
- Density estimation
- Queue estimation
- Signal timing logic (adaptive control)
- Emergency override handling
- Telemetry
- Communication with the backend

Normal traffic decisions are computed entirely on the Pi, so the junction keeps operating even if the internet connection temporarily fails or AWS is offline.

### 3.2 Cloud Layer — AWS

AWS handles the centralized, non-real-time responsibilities:

- Authentication
- Ambulance-driver management
- Ambulance GPS tracking
- Junction and device registration
- Historical traffic data, analytics, and dashboard data
- Emergency-session coordination

### 3.3 Communication Rules

- The Pi never connects directly to the database; it communicates with the backend over **HTTPS, MQTT, or WebSocket**.
- The Pi does **not** continuously upload the four video streams — that would waste bandwidth and introduce latency. It sends only compact telemetry (see Section 9).

## 4. AI / Perception Pipeline

### 4.1 Dataset — BMD-45

**BMD-45** is the selected primary dataset because it closely matches the prototype: it is based on Indian urban traffic, captured from fixed CCTV cameras at 1080p, with dense heterogeneous traffic and many vehicle categories. Note that BMD-45 is primarily a *detection* dataset — it does not by itself provide vehicle counting across time, which is why a tracker is added (Section 6).

### 4.2 Model — YOLOv12-S

The preferred model is **YOLOv12-S**. It is **not trained on the Pi**; training runs first on a laptop or on Kaggle. After training, the model is exported to a Pi-friendly format — preferably **ONNX**, if that gives better Raspberry Pi performance — and copied to the Pi, where the model is loaded once and shared by all cameras (Section 5).

### 4.3 Class Mapping — 14 Detector Classes → 5 Project Classes

The detector keeps predicting its original detailed classes, and the software maps them into the five project classes after inference:

| BMD-45 detector class | Project class |
| --- | --- |
| Hatchback, Sedan, SUV, MUV, Van | Car |
| Two-wheeler | Two-Wheeler |
| Three-wheeler | Auto-Rickshaw |
| Bus, Mini-bus, Tempo-traveller | Bus |
| Truck, LCV | Truck |
| Bicycle, Other | Ignored in v1 |

Using the official 14-class model with software mapping is preferred initially because collapsing to 5 classes barely reduces model size or inference cost — most of YOLO's parameters are in the backbone and neck, not the final class-output head.

### 4.4 Training Plan

- **Stage 1 (start here):** Download the official BMD-45 YOLOv12-S pretrained `best.pt` weights and use them directly. Test the model on sample traffic images, verify the detections, then implement the class-mapping function. No retraining is needed for the first version.
- **Stage 2 (only if needed):** If the official 14-class model proves not accurate enough on the actual junction cameras, remap the BMD-45 annotations to the five classes and fine-tune YOLOv12-S — first with a small experiment (8K train / 2K validation images), then, for the final model, with the full official BMD-45 train and validation splits plus manually annotated footage from the actual junction.

## 5. Real-Time Inference Architecture on the Pi

- **One shared inference service** processes all four camera streams — never one separate YOLO model per camera.
- Each camera has its own **capture thread** with a **latest-frame buffer**.
- A single **inference worker** processes fresh frames from each camera in turn.
- Not every frame is processed: instead of the full 30 FPS from every camera, a few inference frames per second per road are enough for traffic-density decisions.
- The Pi runs Python with **OpenCV** and the trained YOLO model.

## 6. Traffic Sensing & Adaptive Signal Control

### 6.1 Perception → Counts

YOLO detections are passed to a lightweight tracker, **ByteTrack**, so the same vehicle keeps a temporary ID across frames and is not counted repeatedly. Each camera maintains its own tracker, counting line, and region of interest. From these, the system computes per approach:

- Vehicle counts
- Active vehicles in the queue region
- Arrival flow
- Approximate queue size

These values are **smoothed over a short configurable time window**, so a single missed detection or a sudden frame fluctuation never immediately changes the signal.

### 6.2 Adaptive Control Algorithm

The traffic-control algorithm is fully separate from YOLO: YOLO only reports which vehicles are present, while the algorithm decides how much green time each road receives. The Pi computes a traffic score for each road and applies a simple **deterministic adaptive-control algorithm** to decide which side gets green and for how long. It always respects:

- Minimum green time and maximum green time
- Yellow time and safe switching rules
- Waiting time and fairness across approaches

Green time is **not** simply proportional to vehicle count. All of this runs locally on the Pi, independent of AWS.

## 7. Ambulance Priority Pipeline

There is **no siren detection and no camera-based ambulance detection**. Priority is driven entirely by the ambulance driver's mobile app:

1. The driver logs in and starts an emergency in the app.
2. The app sends **authorized background GPS updates** to the AWS backend.
3. The backend tracks the ambulance, identifies the upcoming (nearest) junction and the approach direction, and sends a valid emergency override command to that junction's Pi.
4. The Pi safely finishes any required transition, clears conflicting movements, gives green priority to the ambulance side, and temporarily overrides the normal density-based controller.
5. Once the ambulance passes — or the emergency session times out — the Pi returns to normal adaptive control.

### 7.1 Mobile App

- **Stack:** React Native + TypeScript, built with an Expo development build.
- **Features:** driver login, ambulance registration, Start Emergency, Stop Emergency.
- **Capabilities:** background location updates while emergency mode is active; push notifications via **OneSignal** for Android and iOS. React Native provides the GPS, background-location, and notification capabilities required.

### 7.2 Future Expansion — Green Corridor

If the system is expanded to multiple junctions, AWS can coordinate several Raspberry Pis to create a moving green corridor for the ambulance.

## 8. AWS Backend

The backend is built with **FastAPI** on **PostgreSQL**, and all data access goes through **SQLAlchemy 2.0 as the ORM**. It implements the cloud responsibilities listed in Section 3.2: authentication, driver and ambulance management, junction and device registration, traffic history, analytics, dashboard data, and emergency-session coordination with command dispatch to the Pis.

### 8.1 Data Layer — How the ORM Is Used

- **Async ORM end to end:** SQLAlchemy 2.0 declarative models (`Mapped` / `mapped_column`) running on the `asyncpg` driver. A single async engine serves the whole app, and each request receives its own `AsyncSession` through a FastAPI dependency.
- **Schema:** 16 tables — users, ambulances, hospitals, junctions, approaches, police_assignments, devices, telemetry, heartbeats, audit_logs, push_subscriptions, emergency_sessions, gps_points, emergency_commands, driver_profiles, detections — with UUID primary keys and JSONB payload columns (telemetry, heartbeats, audit details, detection bounding boxes, approach metadata). Partial unique indexes enforce "one active emergency session per ambulance and per driver".
- **Query style:** queries are composed where they are used — inline in route handlers and services — as `select()` / `update()` / `delete()` statements. Hot paths add row locks (`SELECT … FOR UPDATE`) and nested savepoints so concurrent emergency starts and command creation stay race-safe.
- **Migrations:** Alembic with hand-written, PostgreSQL-flavored migrations; the ORM's autogenerate is not used for shipped schema changes.
- **Testing:** the test suite runs hermetically against in-memory SQLite (aiosqlite) with UUID/JSONB compile shims, so the full backend test suite needs no live PostgreSQL and no cloud access.

## 9. Telemetry & Communication

During normal operation, the Pi sends compact telemetry to the backend instead of continuous raw video:

- Vehicle counts and queue estimates
- Current signal phase / state
- Timestamps and traffic statistics
- Inference latency
- Device health
- Emergency status

## 10. Prototype Scope & Demo

This is a prototype, so no full physical traffic-light hardware setup is required:

- Signal behavior is demonstrated through software and the dashboard: green/red states, timers, density values, and emergency priority.
- No real ambulance or government traffic signal is needed — a bike or car running the driver app can simulate the ambulance on a controlled campus or private road.

## 11. Hardware Plan & Budget

The finalized budget is **₹49,000** (SEED grant), covering:

| Item | Notes |
| --- | --- |
| Raspberry Pi 5 | With PSU and cooling |
| 4× 1080p USB cameras | One per road approach |
| Mounts and powered USB hub | With enclosure |
| Router and network accessories | Junction networking |
| microSD card (storage) | OS, model, and frame buffers |
| Cloud services | AWS infrastructure |
| Testing and integration | Includes field testing |
| Consumables | Miscellaneous |
| Contingency | — |

## 12. End-to-End Flow Summary

**Normal operation:**

> four cameras → shared YOLOv12-S model → 14-to-5 class mapping → per-camera tracking → vehicle counting → density and queue estimation → local adaptive signal decision

**Emergency priority:**

> ambulance app GPS → AWS backend → junction and approach identified → emergency command → Raspberry Pi → safe green priority → return to normal adaptive mode

**Build sequence:**

1. Train YOLO on BMD-45 (Kaggle) or download the official pretrained weights.
2. Merge the dataset classes into the five project categories (software mapping).
3. Evaluate and export the model (ONNX if it performs better on the Pi).
4. Deploy the model on the Raspberry Pi and process the four camera streams.
5. Detect, track, and count vehicles; calculate traffic density.
6. Dynamically control signal timings.
7. Build the React Native ambulance app.
8. Deploy the FastAPI backend on AWS.
9. Send GPS from the app to AWS → detect the upcoming junction → send the emergency override to the Pi → give ambulance priority → return to normal adaptive control.
