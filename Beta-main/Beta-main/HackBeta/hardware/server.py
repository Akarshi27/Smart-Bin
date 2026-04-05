import cv2
import numpy as np
import tensorflow as tf
from datetime import datetime
import json
import time
import requests  # <-- NEW: for HTTP POST to Express
import paho.mqtt.client as mqtt

# ===== CONFIG =====
MODEL_PATH = "waste_classifier.tflite"
CLASSES = ['Hazardous', 'Organic', 'Recyclable']
INPUT_SIZE = (224, 224)

IP_ADDRESS = "192.168.153.201"    # DroidCam IP (change this)
PORT = "4747"
STREAM_URLS = [
    f"http://{IP_ADDRESS}:{PORT}/video",
    f"http://{IP_ADDRESS}:{PORT}/mjpegfeed"
]

# ===== MQTT CONFIG =====
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_REQUEST = "futurecan/capture_request"
TOPIC_RESULT  = "futurecan/waste_class"

# ===== EXPRESS API CONFIG =====
# Change this to your deployed backend URL when live
# Local dev example:  "http://localhost:5005"
# Render deploy:      "https://your-app.onrender.com"
EXPRESS_BASE_URL = "http://localhost:5005"
WASTE_LOG_ENDPOINT = f"{EXPRESS_BASE_URL}/api/dashboard/waste-log"

# ===== LOAD MODEL =====
print("[INFO] Loading TensorFlow Lite model...")
interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
interpreter.allocate_tensors()
input_details  = interpreter.get_input_details()
output_details = interpreter.get_output_details()
print("[INFO] Model ready.")

# ===== OPEN CAMERA =====
cap = None
for url in STREAM_URLS:
    print(f"[INFO] Trying camera stream: {url}")
    cap = cv2.VideoCapture(url)
    if cap.isOpened():
        print(f"✅ Connected to {url}")
        break
    else:
        print(f"❌ Failed to open {url}")

if not cap or not cap.isOpened():
    print("[ERROR] No camera stream found. Check DroidCam IP.")
    exit()

# ===== MQTT CALLBACKS =====
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ Connected to MQTT Broker at {MQTT_BROKER}")
        client.subscribe(TOPIC_REQUEST)
        print(f"📡 Subscribed to topic: {TOPIC_REQUEST}")
    else:
        print(f"[ERROR] Connection failed with code {rc}")

def on_message(client, userdata, msg):
    print("\n🔔 Capture request received!")
    print(f"Topic: {msg.topic}")

    try:
        payload_str = msg.payload.decode()
        print(f"Payload: {payload_str}")

        data = json.loads(payload_str)

        # Get User ID from JSON (sent by ESP32)
        # If ESP32 doesn't send uid, fall back to the demo bin ID for testing (matches Shreya's account)
        user_id = data.get('uid', '2428cseaiml2556')

        print(f"Request received for user: {user_id}")
        run_inference_and_publish(user_id)

    except json.JSONDecodeError:
        print(f"[ERROR] Invalid JSON from ESP32: {msg.payload.decode()}")
    except Exception as e:
        print(f"[ERROR] in on_message: {e}")

# ===== FUNCTION: Capture and classify =====
def run_inference_and_publish(user_id):
    print("📸 Starting camera capture...")

    # Countdown display
    start_time = time.time()
    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WARN] Frame not captured.")
            continue

        elapsed = time.time() - start_time
        remaining = 3 - int(elapsed)
        if remaining > 0:
            cv2.putText(frame, f"Capturing in {remaining}s", (50, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
        cv2.imshow("FutureCan Capture", frame)

        if elapsed >= 3:
            break

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("🛑 Cancelled manually.")
            return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"📸 Capturing frame at {timestamp}...")

    img_resized = cv2.resize(frame, INPUT_SIZE)
    img_rgb     = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
    input_data  = np.expand_dims(img_rgb.astype(np.float32), axis=0)

    # Run inference
    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()
    preds = interpreter.get_tensor(output_details[0]['index'])[0]

    class_idx   = int(np.argmax(preds))
    confidence  = float(preds[class_idx]) * 100.0
    class_name  = CLASSES[class_idx]

    print(f"\n🧠 Prediction: {class_name} ({confidence:.2f}%)")

    # --------------------------------------------------
    # 1. Publish MQTT result → ESP32 (for servo control)
    # --------------------------------------------------
    mqtt_payload = {
        "timestamp":        timestamp,
        "primary_category": class_name,
        "item_name":        round(confidence, 2)
    }
    mqtt_msg = json.dumps(mqtt_payload)
    client.publish(TOPIC_RESULT, mqtt_msg)
    print(f"📤 Sent MQTT result to '{TOPIC_RESULT}': {mqtt_msg}")

    # --------------------------------------------------
    # 2. POST to Express API → saves to MongoDB
    # --------------------------------------------------
    mongo_payload = {
        "userId":     user_id,
        "category":   class_name,
        "confidence": round(confidence, 2)
    }

    try:
        response = requests.post(
            WASTE_LOG_ENDPOINT,
            json=mongo_payload,
            timeout=5            # 5 second timeout so it doesn't hang
        )

        if response.status_code == 201:
            print(f"✅ Logged to MongoDB via Express: {mongo_payload}")
        else:
            print(f"⚠️ Express API returned status {response.status_code}: {response.text}")

    except requests.exceptions.ConnectionError:
        print(f"❌ Could not reach Express API at {WASTE_LOG_ENDPOINT}")
        print("   → Is your backend server running? Check EXPRESS_BASE_URL in config.")
    except requests.exceptions.Timeout:
        print("❌ Express API request timed out after 5 seconds.")
    except Exception as e:
        print(f"❌ Unexpected error posting to Express API: {e}")

    # --------------------------------------------------
    # 3. Show result on screen
    # --------------------------------------------------
    label_text = f"{class_name} ({confidence:.1f}%)"
    cv2.putText(frame, label_text, (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
    cv2.imshow("FutureCan Result", frame)
    cv2.waitKey(2000)

# ===== MAIN =====
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
client.on_connect = on_connect
client.on_message = on_message

print("[INFO] Connecting to MQTT broker...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)

try:
    print("🚀 Ready. Waiting for ESP32 capture requests...")
    client.loop_forever()
except KeyboardInterrupt:
    print("\n[STOP] Closing camera and MQTT...")
    cap.release()
    cv2.destroyAllWindows()
    client.disconnect()