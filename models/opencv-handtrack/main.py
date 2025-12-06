import cv2
import mediapipe as mp
import numpy as np
import json
import os

# Load values
current_dir = os.path.dirname(os.path.abspath(__file__))
values_path = os.path.join(current_dir, "values.json")

config = {
    "max_num_hands": 2,
    "min_detection_confidence": 0.85,
    "min_tracking_confidence": 0.85,
    "colors": {
        "circle": [255, 255, 255],
        "line": [200, 200, 200],
        "text": [255, 0, 0]
    },
    "dimensions": {
        "circle_radius": 3,
        "line_thickness": 2
    }
}

# External override
if os.path.exists(values_path):
    with open(values_path, "r") as f:
        config.update(json.load(f))

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=config["max_num_hands"],
    min_detection_confidence=config["min_detection_confidence"],
    min_tracking_confidence=config["min_tracking_confidence"]
)

def draw_hand_skeleton(image, hand_landmarks, connections):
    colors = config["colors"]
    dims = config["dimensions"]

    circle_color = tuple(colors["circle"])
    line_color = tuple(colors["line"])
    text_color = tuple(colors["text"])

    h, w, _ = image.shape

    # 1️⃣ Draw connections only
    for start_idx, end_idx in connections:
        start = hand_landmarks[start_idx]
        end = hand_landmarks[end_idx]

        p1 = (int(start.x * w), int(start.y * h))
        p2 = (int(end.x * w), int(end.y * h))

        cv2.line(image, p1, p2, line_color, dims["line_thickness"])

    # 2️⃣ Draw joint circles + numbers
    for idx, landmark in enumerate(hand_landmarks):
        cx = int(landmark.x * w)
        cy = int(landmark.y * h)

        # circle
        cv2.circle(image, (cx, cy), dims["circle_radius"], circle_color, -1)

        # index text
        cv2.putText(image, str(idx), (cx + 5, cy - 5), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.4, text_color, 1)

    return image


def process_frame(frame):
    if frame is None:
        return None, []

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = hands.process(frame_rgb)
    logs = []

    if result.multi_hand_landmarks:
        for hand_landmarks, hand_info in zip(result.multi_hand_landmarks, result.multi_handedness):
            frame = draw_hand_skeleton(frame, hand_landmarks.landmark, mp_hands.HAND_CONNECTIONS)
            logs.append(f"Detected {hand_info.classification[0].label} Hand")

    return frame, logs


def run_standalone():
    print("Running Hand Tracking Standalone…")
    cap = cv2.VideoCapture(0)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        processed, logs = process_frame(frame)
        cv2.imshow("HandTrack", processed)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_standalone()
