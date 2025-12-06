import cv2
import numpy as np
import time

# Load pre-trained face detector from OpenCV
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

def process_frame(frame):
    """
    Takes a raw frame (numpy array), processes it, and returns (processed_frame, logs).
    """
    if frame is None:
        return None, []

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)
    
    logs = []
    
    # Draw rectangles around faces
    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
        logs.append(f"Face detected at x={x}, y={y}")
    
    if len(faces) == 0:
       pass 
       # We could log 'No face' but that spam logs
       
    return frame, logs

def run_standalone():
    print("Running OpenCV Model Standalone Mode (Laptop Camera)")
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: Could not open video device.")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break
            
        processed_frame, logs = process_frame(frame)
        
        for l in logs:
            print(f"[LOG] {l}")
            
        cv2.imshow('OpenCV Model - Standalone', processed_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_standalone()
