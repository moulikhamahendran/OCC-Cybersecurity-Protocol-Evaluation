#include <Arduino.h>

void setup() {
  Serial.begin(115200);
  delay(2000);

  Serial.println("ESP32 FEASIBILITY TEST");
  Serial.printf("Chip: %s\n", ESP.getChipModel());
  Serial.printf("Revision: %d\n", ESP.getChipRevision());
  Serial.printf("CPU MHz: %d\n", ESP.getCpuFreqMHz());
  Serial.printf("Flash bytes: %u\n", ESP.getFlashChipSize());
  Serial.printf("Heap bytes: %u\n", ESP.getHeapSize());
  Serial.printf("Free heap bytes: %u\n", ESP.getFreeHeap());
  Serial.printf("PSRAM bytes: %u\n", ESP.getPsramSize());

  pinMode(2, OUTPUT);
}

void loop() {
  digitalWrite(2, HIGH);
  delay(500);
  digitalWrite(2, LOW);
  delay(500);
}
