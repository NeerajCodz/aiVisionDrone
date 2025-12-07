#!/usr/bin/env python3
"""
Laptop Server - Receives Pi stream and serves to website
Run this on your laptop
"""

from flask import Flask, Response, send_file
import cv2
import requests
import numpy as np
import threading

app = Flask(_name_)

# Configuration
PI_IP = "10.52.156.90"  # CHANGE THIS to your Raspberry Pi's IP
PI_PORT = 5000
LAPTOP_PORT = 8080

# Global variable for latest frame
latest_frame = None
frame_lock = threading.Lock()

def receive_stream():
    """Receive stream from Raspberry Pi"""
    global latest_frame
    
    stream_url = f"http://{PI_IP}:{PI_PORT}/video_feed"
    print(f"Connecting to Pi stream at {stream_url}...")
    
    try:
        response = requests.get(stream_url, stream=True, timeout=10)
        
        if response.status_code == 200:
            print("✓ Connected to Pi camera stream!")
            
            bytes_data = b''
            for chunk in response.iter_content(chunk_size=1024):
                bytes_data += chunk
                
                # Find start and end of JPEG
                a = bytes_data.find(b'\xff\xd8')  # JPEG start
                b = bytes_data.find(b'\xff\xd9')  # JPEG end
                
                if a != -1 and b != -1:
                    jpg = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]
                    
                    # Decode image
                    img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    
                    if img is not None:
                        with frame_lock:
                            latest_frame = img
                            
    except Exception as e:
        print(f"Error receiving stream: {e}")
        print("Make sure the Pi server is running!")

def generate_frames():
    """Generate frames for web browser"""
    global latest_frame
    
    while True:
        with frame_lock:
            if latest_frame is None:
                # Create waiting message
                blank = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(blank, "Connecting to Pi...", (150, 240), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                frame = blank
            else:
                frame = latest_frame.copy()
        
        # Encode as JPEG
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        frame_bytes = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def index():
    """Serve the web interface"""
    try:
        return send_file('index.html')
    except:
        # Fallback if index.html not found
        return '''
        <html>
            <head><title>Pi Camera Stream</title></head>
            <body style="background: #1a1a1a; color: white; font-family: Arial; text-align: center; padding: 20px;">
                <h1>📷 Raspberry Pi Camera Stream</h1>
                <img src="/video_feed" style="max-width: 100%; border-radius: 10px; margin-top: 20px;">
                <p style="margin-top: 20px;">index.html not found - using fallback interface</p>
            </body>
        </html>
        '''

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if _name_ == '_main_':
    # Start stream receiver in background thread
    receiver_thread = threading.Thread(target=receive_stream, daemon=True)
    receiver_thread.start()
    
    print("\n" + "="*60)
    print("Laptop Server Starting...")
    print("="*60)
    print(f"\nReceiving stream from Pi: http://{PI_IP}:{PI_PORT}")
    print(f"\nAccess website at:")
    print(f"  • http://localhost:{LAPTOP_PORT}")
    print(f"  • http://<your-laptop-ip>:{LAPTOP_PORT}")
    print("\nPress Ctrl+C to stop")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=LAPTOP_PORT, threaded=True)