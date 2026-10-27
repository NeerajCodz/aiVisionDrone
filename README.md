# Vision Hub

Vision Hub is a local dashboard for viewing multiple camera feeds and running vision models on them. ESP32-CAM boards send video over Wi-Fi; the computer running Vision Hub handles the model processing. Each camera can be named and configured separately.

## Start the dashboard

On Windows, install Python 3.12 and the C++ build tools needed for `dlib`, then run these commands from the project directory in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open [http://localhost:5000](http://localhost:5000). For a phone or another computer on the same network, use `http://<server-ip>:5000`; `ipconfig` shows the server's Wi-Fi IPv4 address. The app listens on all interfaces. Allow inbound TCP port 5000 in the Windows firewall for the intended network if another device cannot connect. The dashboard currently has no login, so use it on a trusted network.

New cameras start without an AI model selected. Choose a model for a camera when you want inference; the selection is saved and restored when the server restarts. Running more cameras or models increases CPU and memory use.

## Prepare an ESP32-CAM

The sketch targets the common AI Thinker ESP32-CAM pin layout and joins a 2.4 GHz Wi-Fi network. Install Arduino CLI and the Espressif `esp32` board platform first. Copy the template and edit the local file with your network name and password:

```powershell
if (-not (Test-Path firmware\esp32cam\secrets.h)) {
    Copy-Item firmware\esp32cam\secrets.example.h firmware\esp32cam\secrets.h
}
```

`secrets.h` is ignored by Git. Keep it local; do not commit or publish it.

Connect the board through a compatible USB serial adapter. On this PC, Arduino CLI is installed at the path below; adjust it if your installation is elsewhere. List the ports and use the board's actual COM port in the commands. This example uses `COM5`:

```powershell
$arduino = 'C:\Program Files\Arduino CLI\arduino-cli.exe'
& $arduino board list
```

For adapters without automatic boot control, connect GPIO0 to GND and reset the board to enter flashing mode. Compile and upload:

```powershell
& $arduino compile --fqbn esp32:esp32:esp32cam firmware\esp32cam
& $arduino upload --fqbn esp32:esp32:esp32cam --port COM5 firmware\esp32cam
```

After upload, remove the GPIO0-to-GND connection and reset the board. Open the serial monitor at 115200 baud:

```powershell
& $arduino monitor --port COM5 --config baudrate=115200
```

The board prints its IP address, `http://<camera-ip>:81/stream`, and a unique `esp32cam-<suffix>.local` hostname. If the hostname does not resolve, use the IP address printed by that board. The camera and server need network connectivity to each other.

You can also open `firmware/esp32cam/esp32cam.ino` in Arduino IDE, select the **AI Thinker ESP32-CAM** board and the board's COM port, then upload and open Serial Monitor at 115200 baud.

## Add multiple cameras

Flash each board with the sketch and the Wi-Fi credentials for its network. Each board receives its own IP address and hostname. In Vision Hub, add a camera for each board and enter the stream URL printed by its serial monitor, for example `http://192.168.1.42:81/stream`. Give each camera a distinct name, then choose a model independently for its feed. You can add other reachable HTTP MJPEG sources in the same way.

Camera settings are saved locally in `camera_config.json`, which is ignored by Git. If there is no saved camera configuration, `AIVISION_CAMERA_URL` can provide the first camera's stream URL:

```powershell
$env:AIVISION_CAMERA_URL = 'http://192.168.1.42:81/stream'
.\.venv\Scripts\python.exe app.py
```

If a camera is offline, check its power, serial output, Wi-Fi connection, stream URL, and whether the network permits devices to reach each other. A hostname lookup failure alone does not establish whether the camera is online.

See [DEVELOPER.md](DEVELOPER.md) for the application layout, camera API, and model interface.
