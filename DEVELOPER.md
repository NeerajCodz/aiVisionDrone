# AI Vision Drone - Developer Guide

## Overview

This project implements a modular AI vision system for drones. It separates the "Drone Side" (Video ingestion) from the "Client Side" (AI Processing & UI).

## Architecture

The system consists of three main components:

1.  **Drone Server (`server.py`)**: 
    -   Acts as the video feed buffer.
    -   Receives raw frames from the drone via POST requests.
    -   Exposes a video stream endpoint for consumers.
2.  **AI Application (`app.py`)**: 
    -   The main orchestrator.
    -   Connects to the `server.py` video stream.
    -   Loads AI models dynamically from the `models/` directory.
    -   Processes frames and generates logs.
    -   Host the Web UI.
3.  **Frontend (`static/`)**:
    -   A responsive, modern dashboard.
    -   Displays the AI-annotated video feed.
    -   Shows real-time mission logs.
    -   Allows switching models on the fly.

## File Structure

```
aiVisionDrone/
├── app.py              # Main Entry Point (UI + AI Processor)
├── server.py           # Drone Video Buffer Server
├── logs.py             # Log management utility
├── static/             # Frontend Assets
│   ├── index.html      # Main Dashboard
│   ├── css/
│   │   └── style.css   # Styling (Dark Mode)
│   └── js/
│       └── script.js   # Logic (Polling, Model Switching)
└── models/             # AI Models Directory
    └── opencv/         # Example Model
        ├── main.py     # Model Logic (process_frame function)
        └── model.json  # Metadata
```

## How to Run

### 1. Prerequisites
Install dependencies:
```bash
pip install fastapi uvicorn opencv-python numpy
```

### 2. Start the Drone Server
This simulates the drone's video sender or acts as the receiver for the real drone.
```bash
python server.py
```
*   Server runs on `http://localhost:8000`

### 3. Start the Main App
This launches the dashboard and AI processor.
```bash
python app.py
```
*   App runs on `http://localhost:5000`

### 4. Access Dashboard
Open your browser and navigate to:
`http://localhost:5000/static/index.html`

## Development

### Adding a New Model
1. Create a new folder in `models/`, e.g., `models/yolo_v8/`.
2. Add a `model.json` with metadata.
3. Add a `main.py` with the following structure:
    ```python
    def process_frame(frame):
        # Process frame...
        return processed_frame, ["Log message 1", "Log message 2"]
    
    if __name__ == "__main__":
        # Code to run with local webcam for testing
    ```

### Logs
Logs are stored in-memory in `logs.py`. They are displayed in the "Mission Logs" panel on the right side of the dashboard.
