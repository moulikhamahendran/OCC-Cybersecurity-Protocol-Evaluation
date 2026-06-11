#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

const char* ssid = "iPhone";
const char* password = "moulikha";

const char* mqtt_server = "2d0d6f6575dc4006bebe6f5c459bad88.s1.eu.hivemq.cloud";
const int mqtt_port = 8883;

const char* mqtt_user = "occuser";
const char* mqtt_password = "Occpassword123";

WiFiClientSecure espClient;
PubSubClient client(espClient);

int sequenceNumber = 0;

void connectWiFi() {
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi...");
  }

  Serial.println("WiFi Connected");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());
}

void connectMQTT() {
  while (!client.connected()) {
    Serial.println("Connecting to HiveMQ Cloud...");

    if (client.connect("ESP32_REAL_CLIENT", mqtt_user, mqtt_password)) {
      Serial.println("MQTT Connected");
    } else {
      Serial.print("MQTT Failed, state: ");
      Serial.println(client.state());
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  connectWiFi();

  espClient.setInsecure();

  client.setServer(mqtt_server, mqtt_port);

  connectMQTT();
}

void loop() {
  if (!client.connected()) {
    connectMQTT();
  }

  client.loop();

  StaticJsonDocument<512> doc;

  doc["vehicle_id"] = "ESP32_REAL";
  doc["timestamp"] = time(NULL);
  doc["sequence"] = sequenceNumber++;
  doc["speed"] = random(20, 80);
  doc["battery"] = random(50, 100);
  doc["temperature"] = random(25, 45);

  JsonObject location = doc.createNestedObject("location");
  location["lat"] = 52.1;
  location["lon"] = 11.6;

  char buffer[512];
  serializeJson(doc, buffer);

  client.publish("vehicle/raw", buffer);

  Serial.println(buffer);

  delay(3000);
}
