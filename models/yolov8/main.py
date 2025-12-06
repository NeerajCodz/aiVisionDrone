import cv2
from ultralytics import YOLO
import os

# ------------------------------
# Load YOLO Model
# ------------------------------

current_dir = os.path.dirname(os.path.abspath(__file__))
# We will use 'yolov8n.pt' which is the standard nano model name. 
# Ultralytics auto-downloads it to the current working dir if not found of specific path.
# To keep it inside our model folder, we specify the path.
model_name = "yolov8n.pt" 
model_path = os.path.join(current_dir, model_name)

def load_model():
    print(f"[YOLO] Loading model from {model_path}...")
    # YOLO() will automatically download 'yolov8n.pt' from HF if not found locally at that path?
    # Actually YOLO('yolov8n.pt') checks current dir. 
    # Let's try to be robust.
    try:
        model = YOLO(model_path) # Attempts load
        print("[YOLO] Model loaded.")
        return model
    except Exception as e:
        print(f"[YOLO] Model not found locally, attempting download via YOLO('yolov8n.pt')...")
        # This usually saves to current working directory (project root probably).
        # We want it in this folder.
        # Let's just let ultralytics handle it, but we prefer it here.
        # Simple fix: Use standard load, if it downloads to root, we move it? 
        # Or Just use 'yolov8n.pt' and let it cache where it wants. 
        # But 'process_frame' logic needs the object.
        model = YOLO(model_name) # This triggers download if missing
        return model

# Global instance
yolo_model = load_model()

# ------------------------------
# Process Frame
# ------------------------------

def process_frame(frame):
    if frame is None:
        return frame, []

    logs = []

    # run detection (verbose=False to keep stdout clean)
    results = yolo_model(frame, verbose=False)

    annotated = frame.copy()

    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            
            # Safety check if class index is in names
            class_name = yolo_model.names[cls] if cls in yolo_model.names else str(cls)
            label = f"{class_name} {conf:.2f}"

            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cv2.putText(
                annotated,
                label,
                (x1, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2
            )

            logs.append(f"Detected: {label}")

    return annotated, logs


# ------------------------------
# Standalone Runner
# ------------------------------

def run_standalone():
    cap = cv2.VideoCapture(0)
    print("[YOLO] Starting camera...")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        out_frame, logs = process_frame(frame)
        
        # Overlay logs on screen for standalone
        y_off = 30
        for l in logs:
            cv2.putText(out_frame, l, (10, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            y_off += 20
            
        cv2.imshow("YOLO Object Detection", out_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_standalone()
