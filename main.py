import json
import logging
import queue
import time
import os
import cv2
import numpy as np
import paho.mqtt.client as mqtt
from ultralytics import YOLO
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

logging.basicConfig(level=logging.CRITICAL, format="%(asctime)s [%(levelname)s] %(message)s")

# MQTT Configuration
MQTT_BROKER = os.getenv("MQTT_BROKER_IP", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

RING_LOCATION_ID = os.getenv("RING_LOCATION_ID")
RING_CAMERA_ID = os.getenv("RING_CAMERA_ID")

# Construct dynamic MQTT topics
RING_IMAGE_TOPIC = f"ring/{RING_LOCATION_ID}/camera/{RING_CAMERA_ID}/snapshot/image"
RING_MOTION_TOPIC = f"ring/{RING_LOCATION_ID}/camera/{RING_CAMERA_ID}/motion/state"
RING_SNAPSHOT_REQ_TOPIC - f"ring/{RING_LOCATION_ID}/camera/{RING_CAMERA_ID}/snapshot/request"

HA_RESULT_TOPIC = "homeassistant/sensor/white_ev_driveway/state"

# Initialize YOLO model
model = YOLO("yolov8n.pt")

frame_queue = queue.Queue(maxsize=2)
last_frame_time = 0
last_snapshot_request_time = 0
SNAPSHOT_INTERVAL = 30  # Interval in seconds to request fresh frames

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logging.info("Connected to MQTT Broker successfully!")
        discovery_topic = "homeassistant/binary_sensor/white_ev_driveway/config"
        discovery_payload = {
            "name": "White EV Driveway",
            "state_topic": HA_RESULT_TOPIC,
            "value_template": "{{ value_json.state }}",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": "occupancy",
            "unique_id": "white_ev_driveway_ring_yolo"
        }
        client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)
        client.subscribe([(RING_IMAGE_TOPIC, 0), (RING_MOTION_TOPIC, 0)])
        client.publish(RING_SNAPSHOT_REQ_TOPIC, "ON")
    else:
        logging.error(f"Failed to connect to MQTT broker, return code: {rc}")

def check_roi(img):
    if img is None:
        return False
    
    h, w, _ = img.shape
    
    # ROI boundaries calculation
    roi_x1, roi_y1 = int(w * 0.65), int(h * 0.40)
    roi_x2, roi_y2 = int(w * 0.80), int(h * 0.90)
    
    car_detected_in_roi = False
    results = model(img, verbose=False)
    
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            if cls_id == 2:  # COCO Class 2 = car
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                if x2 > roi_x1 and x1 < roi_x2 and y2 > roi_y1 and y1 < roi_y2:
                    car_detected_in_roi = True
                    break
        if car_detected_in_roi:
            break

    return car_detected_in_roi

def on_message(client, userdata, msg):
    global last_frame_time
    topic = msg.topic

    if "snapshot/image" in topic:
        logging.info(f"Snapshot image received! ({len(msg.payload)} bytes)")
        np_arr = np.frombuffer(msg.payload, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is not None:
            last_frame_time = time.time()
            if frame_queue.full():
                try:
                    frame_queue.get_nowait()
                except queue.Empty:
                    pass
            frame_queue.put(img)

    elif "motion/state" in topic:
        payload = msg.payload.decode("utf-8")
        if payload == "ON":
            logging.info("Motion detected by Ring! Requesting immediate snapshot...")
            client.publish(RING_SNAPSHOT_REQ_TOPIC, "ON")

def main():
    global last_snapshot_request_time

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    logging.info("Headless Vision Service Started.")

    try:
        while True:
            current_time = time.time()
            
            # Periodically request snapshot if idle
            if current_time - last_snapshot_request_time >= SNAPSHOT_INTERVAL:
                client.publish(RING_SNAPSHOT_REQ_TOPIC, "ON")
                last_snapshot_request_time = current_time

            try:
                frame = frame_queue.get(timeout=1.0)
                is_car_present = check_roi(frame)
                
                state_str = "ON" if is_car_present else "OFF"
                result = {"state": state_str, "car_detected": is_car_present}
                client.publish(HA_RESULT_TOPIC, json.dumps(result), retain=True)
                logging.info(f"Published HA State: {state_str}")
            except queue.Empty:
                pass

    except KeyboardInterrupt:
        logging.info("Stopping service...")
    finally:
        client.loop_stop()
        logging.info("Service stopped successfully.")

if __name__ == "__main__":
    main()
