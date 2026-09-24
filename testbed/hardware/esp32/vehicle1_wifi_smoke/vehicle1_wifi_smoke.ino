#include <WiFi.h>
#include "secrets.h"

const char* BROKER_HOST = "192.168.1.181";
const uint16_t BROKER_PORT = 1883;

WiFiClient client;

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println("=== ESP32 VEHICLE 1 CONNECTIVITY TEST ===");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to Wi-Fi");

  unsigned long start = millis();

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");

    if (millis() - start > 20000) {
      Serial.println();
      Serial.println("FAIL: Wi-Fi connection timeout");
      return;
    }
  }

  Serial.println();
  Serial.println("Wi-Fi connected");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());

  Serial.print("RSSI: ");
  Serial.print(WiFi.RSSI());
  Serial.println(" dBm");

  Serial.print("Testing broker ");
  Serial.print(BROKER_HOST);
  Serial.print(":");
  Serial.println(BROKER_PORT);

  if (client.connect(BROKER_HOST, BROKER_PORT)) {
    Serial.println("PASS: MQTT broker TCP port reachable");
    client.stop();
  } else {
    Serial.println("FAIL: MQTT broker TCP port not reachable");
  }
}

void loop() {
}
