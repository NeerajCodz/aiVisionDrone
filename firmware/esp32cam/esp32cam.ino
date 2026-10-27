#include <Arduino.h>
#include <ESPmDNS.h>
#include <WiFi.h>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "secrets.h"

namespace {

constexpr int kPwdnPin = 32;
constexpr int kResetPin = -1;
constexpr int kXclkPin = 0;
constexpr int kSiodPin = 26;
constexpr int kSiocPin = 27;
constexpr int kY9Pin = 35;
constexpr int kY8Pin = 34;
constexpr int kY7Pin = 39;
constexpr int kY6Pin = 36;
constexpr int kY5Pin = 21;
constexpr int kY4Pin = 19;
constexpr int kY3Pin = 18;
constexpr int kY2Pin = 5;
constexpr int kVsyncPin = 25;
constexpr int kHrefPin = 23;
constexpr int kPclkPin = 22;

constexpr char kMdnsHost[] = "esp32cam";
constexpr char kStreamContentType[] = "multipart/x-mixed-replace;boundary=frame";
constexpr char kStreamBoundary[] = "\r\n--frame\r\n";
constexpr char kPartHeaderFormat[] = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t rootServer = nullptr;
httpd_handle_t streamServer = nullptr;
bool cameraReady = false;
bool mdnsStarted = false;
unsigned long lastWifiAttempt = 0;
unsigned long lastServerAttempt = 0;

bool hasWifiCredentials() {
  return strlen(WIFI_SSID) > 0 && strcmp(WIFI_SSID, "YOUR_WIFI_SSID") != 0 &&
         strlen(WIFI_PASSWORD) > 0 && strcmp(WIFI_PASSWORD, "YOUR_WIFI_PASSWORD") != 0;
}

bool initializeCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = kY2Pin;
  config.pin_d1 = kY3Pin;
  config.pin_d2 = kY4Pin;
  config.pin_d3 = kY5Pin;
  config.pin_d4 = kY6Pin;
  config.pin_d5 = kY7Pin;
  config.pin_d6 = kY8Pin;
  config.pin_d7 = kY9Pin;
  config.pin_xclk = kXclkPin;
  config.pin_pclk = kPclkPin;
  config.pin_vsync = kVsyncPin;
  config.pin_href = kHrefPin;
  config.pin_sccb_sda = kSiodPin;
  config.pin_sccb_scl = kSiocPin;
  config.pin_pwdn = kPwdnPin;
  config.pin_reset = kResetPin;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 12;
  config.fb_count = psramFound() ? 2 : 1;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  const esp_err_t error = esp_camera_init(&config);
  if (error != ESP_OK) {
    Serial.printf("Camera initialization failed (0x%x). Check the ESP32-CAM pin map and camera ribbon.\n", error);
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor != nullptr) {
    sensor->set_framesize(sensor, FRAMESIZE_QVGA);
  }
  Serial.println("Camera initialized: QVGA JPEG");
  return true;
}

esp_err_t rootHandler(httpd_req_t *request) {
  static const char page[] =
      "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<title>ESP32-CAM</title><style>body{background:#111;color:#eee;font:16px sans-serif;text-align:center}"
      "img{max-width:96vw;height:auto}</style></head><body><h1>ESP32-CAM live video</h1>"
      "<p id='url'></p><img id='feed' alt='Camera stream'></body><script>"
      "const u='http://'+location.hostname+':81/stream';document.getElementById('url').textContent=u;"
      "document.getElementById('feed').src=u;</script></html>";
  httpd_resp_set_type(request, "text/html; charset=utf-8");
  return httpd_resp_send(request, page, HTTPD_RESP_USE_STRLEN);
}

esp_err_t streamHandler(httpd_req_t *request) {
  if (!cameraReady) {
    httpd_resp_set_status(request, "503 Service Unavailable");
    httpd_resp_set_type(request, "text/plain; charset=utf-8");
    return httpd_resp_send(request,
                           "Camera initialization failed; check serial output and camera pin map.",
                           HTTPD_RESP_USE_STRLEN);
  }

  esp_err_t result = httpd_resp_set_type(request, kStreamContentType);
  if (result != ESP_OK) {
    return result;
  }
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");

  char partHeader[80];
  while (true) {
    camera_fb_t *frame = esp_camera_fb_get();
    if (frame == nullptr) {
      Serial.println("Camera frame capture failed");
      result = ESP_FAIL;
      break;
    }

    result = httpd_resp_send_chunk(request, kStreamBoundary, strlen(kStreamBoundary));
    if (result == ESP_OK) {
      const int headerLength = snprintf(partHeader, sizeof(partHeader), kPartHeaderFormat,
                                        static_cast<unsigned int>(frame->len));
      result = httpd_resp_send_chunk(request, partHeader, headerLength);
    }
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(request, reinterpret_cast<const char *>(frame->buf), frame->len);
    }
    esp_camera_fb_return(frame);

    if (result != ESP_OK) {
      break;
    }
  }

  return result;
}

bool startWebServers() {
  if (rootServer == nullptr) {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.ctrl_port = 32768;
    config.max_uri_handlers = 4;
    config.stack_size = 6144;

    const esp_err_t result = httpd_start(&rootServer, &config);
    if (result != ESP_OK) {
      Serial.printf("Could not start camera web page server (0x%x)\n", result);
      rootServer = nullptr;
      return false;
    }

    httpd_uri_t rootUri = {};
    rootUri.uri = "/";
    rootUri.method = HTTP_GET;
    rootUri.handler = rootHandler;
    httpd_register_uri_handler(rootServer, &rootUri);
  }

  if (streamServer == nullptr) {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 81;
    config.ctrl_port = 32769;
    config.max_open_sockets = 2;
    config.stack_size = 8192;

    const esp_err_t result = httpd_start(&streamServer, &config);
    if (result != ESP_OK) {
      Serial.printf("Could not start camera stream server (0x%x)\n", result);
      streamServer = nullptr;
      return false;
    }

    httpd_uri_t streamUri = {};
    streamUri.uri = "/stream";
    streamUri.method = HTTP_GET;
    streamUri.handler = streamHandler;
    httpd_register_uri_handler(streamServer, &streamUri);
  }

  Serial.println("Camera web and MJPEG servers started");
  return true;
}

void connectWifi() {
  const unsigned long now = millis();
  if (WiFi.status() == WL_CONNECTED || now - lastWifiAttempt < 15000) {
    return;
  }
  lastWifiAttempt = now;

  if (!hasWifiCredentials()) {
    Serial.println("Wi-Fi credentials are placeholders. Edit firmware/esp32cam/secrets.h before connecting.");
    return;
  }

  Serial.println("Connecting to the configured Wi-Fi network...");
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(250);
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi connection timed out; will retry.");
    return;
  }

  Serial.printf("Wi-Fi connected. Camera IP: %s\n", WiFi.localIP().toString().c_str());
  if (!mdnsStarted) {
    mdnsStarted = MDNS.begin(kMdnsHost);
    Serial.println(mdnsStarted ? "mDNS host: esp32cam.local" : "mDNS startup failed; use the camera IP.");
  }
  Serial.printf("Stream URL: http://%s:81/stream\n", WiFi.localIP().toString().c_str());
  Serial.println("Hostname URL: http://esp32cam.local:81/stream");
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("Starting ESP32-CAM wireless MJPEG server");
  cameraReady = initializeCamera();

  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
      Serial.println("Wi-Fi disconnected; reconnecting.");
    }
  });
  connectWifi();
  if (WiFi.status() == WL_CONNECTED) {
    startWebServers();
  }
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
  } else if ((rootServer == nullptr || streamServer == nullptr) && millis() - lastServerAttempt > 15000) {
    lastServerAttempt = millis();
    startWebServers();
  }
  delay(100);
}
