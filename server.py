import cv2
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import numpy as np
import io
import asyncio

app = FastAPI(title="Drone Feed Server")

# Global variable to store the latest frame
latest_frame = None

@app.get("/")
def read_root():
    return {"status": "active", "message": "Drone Feed Server is Running"}

@app.post("/upload_feed")
async def upload_feed(file: UploadFile = File(...)):
    global latest_frame
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        latest_frame = frame
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def generate_frames():
    global latest_frame
    while True:
        if latest_frame is not None:
            ret, buffer = cv2.imencode('.jpg', latest_frame)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        else:
            # Send a blank frame or wait if no frame is available
            pass
        # Small sleep to prevent CPU hogging
        cv2.waitKey(10) # roughly 10ms

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

# Endpoint for app.py to get a single raw frame easily if needed
@app.get("/current_frame")
def get_current_frame():
    global latest_frame
    if latest_frame is not None:
        ret, buffer = cv2.imencode('.jpg', latest_frame)
        if ret:
            return StreamingResponse(io.BytesIO(buffer.tobytes()), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="No frame available")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
