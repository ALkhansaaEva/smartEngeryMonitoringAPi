#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>

// ---------- WIFI ----------
// WiFi credentials
const char* WIFI_SSID = "YOUR_SSID";
const char* WIFI_PASS = "YOUR_PASS";

// ---------- API ----------
// API base URL and device info
const char* API_BASE_URL = "http://YOUR_SERVER:8000";
const char* DEVICE_ID    = "a7cf48f2-4139-4d52-a1e1-23de3c3fb3c2";
const char* HOUSE_ID     = "1";
const char* APPLIANCE_KEY = "Appliance5";

// ---------- CREDENTIALS ----------
// User credentials for API login
const char* USER_EMAIL = "your_email@example.com";
const char* USER_PASS  = "your_password";

// ---------- SENSOR ----------
// Analog pin and conversion factor for power measurement
const int   ADC_PIN   = 34;
const float WATTS_PER_VOLT = 200.0;

// ---------- RELAY ----------
// Relay pin and control variables
const int   RELAY_PIN = 2;
bool        pendingOff = false;
unsigned long offTime  = 0;
const unsigned long WARNING_DELAY_MS = 5000;

// ---------- GLOBAL TOKEN ----------
// JWT token storage
String jwt_token = "";

// ---------- Read power consumption ----------
// Reads the analog input and converts to watts
float readWatts() {
  int raw = analogRead(ADC_PIN);
  float volts = (raw / 4095.0) * 3.3;
  return volts * WATTS_PER_VOLT;
}

// ---------- Login to get JWT token ----------
// Performs HTTP POST login to obtain JWT for authorization
bool login() {
  if (WiFi.status() != WL_CONNECTED) return false;

  HTTPClient http;
  String url = String(API_BASE_URL) + "/token";
  http.begin(url);
  http.addHeader("Content-Type", "application/x-www-form-urlencoded");

  // Prepare login data
  String postData = "username=" + String(USER_EMAIL) + "&password=" + String(USER_PASS);

  int httpCode = http.POST(postData);
  if (httpCode == 200) {
    String payload = http.getString();
    StaticJsonDocument<256> doc;
    DeserializationError err = deserializeJson(doc, payload);
    if (!err) {
      jwt_token = doc["access_token"].as<String>();
      Serial.println("Login successful, JWT obtained");
      http.end();
      return true;
    }
  }
  Serial.printf("Login failed, HTTP code: %d\n", httpCode);
  http.end();
  return false;
}

// ---------- Setup function ----------
// Initializes WiFi, synchronizes time, and logs in
void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH);

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println(" connected");

  configTime(0, 0, "pool.ntp.org");

  if (!login()) {
    Serial.println("Error: Could not login and get JWT token");
  }
}

// ---------- Main loop ----------
// Reads sensor data, sends it with JWT, handles response and relay control
void loop() {
  if (jwt_token == "") {
    Serial.println("JWT token empty, retry login...");
    if (!login()) {
      delay(10000);
      return;
    }
  }

  float watts = readWatts();
  time_t now = time(nullptr);

  StaticJsonDocument<512> doc;
  doc["timestamp"] = now;
  doc["aggregate"] = watts;

  JsonObject apps = doc.createNestedObject("appliances");
  for (int i = 1; i <= 9; i++) apps[String("Appliance") + String(i)] = 0;
  apps[APPLIANCE_KEY] = watts;

  String payload;
  serializeJson(doc, payload);
  Serial.println("Payload:");
  Serial.println(payload);

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String url = String(API_BASE_URL) + "/houses/" + HOUSE_ID + "/reading/" + DEVICE_ID;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", "Bearer " + jwt_token);

    int respCode = http.POST(payload);

    if (respCode == 401) {
      // Token expired or invalid, reset to force re-login
      Serial.println("Unauthorized, refreshing token...");
      jwt_token = "";
      http.end();
      return;
    }

    if (respCode == 200) {
      String body = http.getString();
      Serial.println("Response: " + body);

      StaticJsonDocument<512> resp;
      DeserializationError err = deserializeJson(resp, body);

      if (!err) {
        for (JsonObject act : resp.as<JsonArray>()) {
          const char* devId = act["device_id"];
          const char* action = act["action"];

          if (String(devId) == DEVICE_ID && String(action) == "OFF" && !pendingOff) {
            Serial.println("⚠️ Peak detected, will turn OFF in 5 s");
            pendingOff = true;
            offTime = millis() + WARNING_DELAY_MS;
          }
        }
      } else {
        Serial.println("❌ Failed to parse response JSON");
      }
    } else {
      Serial.printf("❌ HTTP Error: %d\n", respCode);
    }
    http.end();
  }

  if (pendingOff && millis() >= offTime) {
    digitalWrite(RELAY_PIN, LOW);
    Serial.println("✅ Relay OFF (auto-shut)");
    pendingOff = false;
  }

  delay(5000);
}
