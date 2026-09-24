#include <WiFi.h>
#include <ArduinoMqttClient.h>
#include "secrets.h"

const char* BROKER_HOST = "192.168.1.181";
const int BROKER_PORT = 1883;

const char* TOPIC = "uagv/v2/OvGU-Testbed/VM-001/state";

const unsigned long SEND_PERIOD_MS = 100;

WiFiClient wifiClient;
MqttClient mqttClient(wifiClient);

unsigned long sequenceNumber = 0;
unsigned long nextSendMs = 0;

void connectWiFi() {

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting Wi-Fi");

  unsigned long start = millis();

  while (WiFi.status() != WL_CONNECTED) {

    delay(500);
    Serial.print(".");

    if (millis() - start > 20000) {
      Serial.println();
      Serial.println("FAIL: Wi-Fi connection timeout");
      delay(2000);
      ESP.restart();
    }
  }

  Serial.println();

  Serial.print("Wi-Fi connected, IP=");
  Serial.println(WiFi.localIP());

  Serial.print("RSSI=");
  Serial.print(WiFi.RSSI());
  Serial.println(" dBm");
}

void connectMQTT() {

  Serial.print("Connecting MQTT C0 to ");
  Serial.print(BROKER_HOST);
  Serial.print(":");
  Serial.println(BROKER_PORT);

  if (!mqttClient.connect(BROKER_HOST, BROKER_PORT)) {

    Serial.print("MQTT connection failed, error=");
    Serial.println(mqttClient.connectError());

    delay(2000);
    ESP.restart();
  }

  Serial.println("MQTT connected");
}

void setup() {

  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println("=== ESP32 VEHICLE 1 MQTT C0 ===");

  connectWiFi();

  mqttClient.setConnectionTimeout(3000);

  connectMQTT();

  nextSendMs = millis();
}

void loop() {

  mqttClient.poll();

  long timeUntilSend = (long)(nextSendMs - millis());

  if (timeUntilSend > 0) {
    delay(timeUntilSend);
  }

  unsigned long nowMs = millis();

  if ((long)(nowMs - nextSendMs) >= (long)SEND_PERIOD_MS) {
    nextSendMs = nowMs;
  }

  char payload[256];

  unsigned long headerId = sequenceNumber;
  unsigned long tSendMs = millis();

  snprintf(
    payload,
    sizeof(payload),
    "{\"serialNumber\":\"VM-001\","
    "\"headerId\":%lu,"
    "\"t_send_ms\":%lu,"
    "\"speed\":1.0,"
    "\"batteryState\":80.0}",
    headerId,
    tSendMs
  );

  unsigned long ackStartUs = micros();

  mqttClient.beginMessage(
    TOPIC,
    strlen(payload),
    false,
    1,
    false
  );

  mqttClient.print(payload);

  int result = mqttClient.endMessage();

  unsigned long ackRttUs =
      micros() - ackStartUs;

  float ackRttMs =
      ackRttUs / 1000.0;

  if (result) {

    Serial.print("ACK,");
    Serial.print(sequenceNumber);
    Serial.print(",");
    Serial.print(ackRttMs, 3);
    Serial.print(",");
    Serial.println(strlen(payload));

  } else {

    Serial.print("ERROR,");
    Serial.println(sequenceNumber);
  }

  sequenceNumber++;

  nextSendMs += SEND_PERIOD_MS;
}
