import cv2
import face_recognition
import numpy as np
import os

# Load known faces
known_face_encodings = []
known_face_names = []

current_dir = os.path.dirname(os.path.abspath(__file__))
faces_dir = os.path.join(current_dir, "known_faces")

def load_faces():
    global known_face_encodings, known_face_names

    if not os.path.exists(faces_dir):
        os.makedirs(faces_dir)
        return

    # Loop through each folder (each person)
    for person_name in os.listdir(faces_dir):
        person_folder = os.path.join(faces_dir, person_name)

        if not os.path.isdir(person_folder):
            continue  # skip files

        print(f"[FaceDetect] Loading faces for: {person_name}")

        # Load all images for this person
        for img_name in os.listdir(person_folder):
            if img_name.lower().endswith(('.jpg', '.jpeg', '.png')):
                img_path = os.path.join(person_folder, img_name)
                
                try:
                    img = face_recognition.load_image_file(img_path)
                    enc = face_recognition.face_encodings(img)

                    if enc:
                        known_face_encodings.append(enc[0])
                        known_face_names.append(person_name)
                        print(f"   - Loaded {img_name}")
                    else:
                        print(f"   - No face found in {img_name}")

                except Exception as e:
                    print(f"   - Error loading {img_name}: {e}")


# Load on startup
load_faces()

def process_frame(frame):
    if frame is None:
        return None, []
        
    logs = []
    
    # Resize frame for faster processing
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB) # face_recognition expects RGB
    
    # Detect faces
    face_locations = face_recognition.face_locations(rgb_small_frame)
    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
    
    face_names = []
    for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
        name = "Unknown"
        
        # Use distance for better match
        face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
        if len(face_distances) > 0:
            best_match_index = np.argmin(face_distances)
            if matches[best_match_index]:
                name = known_face_names[best_match_index]
        
        face_names.append(name)
        if name != "Unknown":
            logs.append(f"Identified: {name}")
        else:
            # logs.append("Detected Unknown Person")
            pass

    # Display results
    for (top, right, bottom, left), name in zip(face_locations, face_names):
        # Scale back up
        top *= 4
        right *= 4
        bottom *= 4
        left *= 4
        
        color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
        
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        
        cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
        cv2.putText(frame, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 1)
        
    return frame, logs

def run_standalone():
    cap = cv2.VideoCapture(0)
    print("Add images to 'known_faces' to track specific people.")
    while True:
        ret, frame = cap.read()
        if not ret: break
        
        res, l = process_frame(frame)
        cv2.imshow('Face Recognition', res)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_standalone()
