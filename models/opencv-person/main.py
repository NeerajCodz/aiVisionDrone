import cv2
import mediapipe as mp
import numpy as np

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=1,
    enable_segmentation=False,
    min_detection_confidence=0.5
)

def process_frame(frame):
    if frame is None:
        return None, []
    
    logs = []
    
    # Convert RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = pose.process(frame_rgb)
    
    if results.pose_landmarks:
        h, w, c = frame.shape
        
        # Calculate Bounding Box
        x_min, x_max = w, 0
        y_min, y_max = h, 0
        
        detected = False
        for lm in results.pose_landmarks.landmark:
            x, y = int(lm.x * w), int(lm.y * h)
            if x < x_min: x_min = x
            if x > x_max: x_max = x
            if y < y_min: y_min = y
            if y > y_max: y_max = y
            detected = True
            
        if detected:
            # Add padding
            pad = 20
            x_min = max(0, x_min - pad)
            x_max = min(w, x_max + pad)
            y_min = max(0, y_min - pad)
            y_max = min(h, y_max + pad)
            
            # Draw Box
            cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)
            cv2.putText(frame, "Person", (x_min, y_min - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            
            logs.append("Person Detected")

    return frame, logs

def run_standalone():
    cap = cv2.VideoCapture(0)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        proc, _ = process_frame(frame)
        cv2.imshow("Person Track", proc)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_standalone()
