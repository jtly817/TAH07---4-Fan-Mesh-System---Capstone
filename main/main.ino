#include <ld2410.h>

// Tell the main tab that 'radar' is defined in another tab (radar.ino)
extern ld2410 radar;

// Track display timestamps to avoid flooding the console
uint32_t lastPrintTime = 0;

void setup() {
  // Initialize debug output channel to PC
  Serial.begin(115200);
  while(!Serial) {
    delay(10); // Hold for native USB monitor window
  }

  Serial.println("\n=== Combined Modular Smart Radar System ===");

  // Call initialization setups from the other tabs
  setupRGB();
  setupRadar();
}

void loop() {
  // Fetch the current detection state from the radar tab
  int presenceState = checkRadarPresence();

  // Update loop checks every 200 milliseconds for responsiveness
  if (millis() - lastPrintTime >= 200) {
    lastPrintTime = millis();

    switch(presenceState) {
      case 1: // Moving target only
        Serial.print("▼ TARGET MOVING | Distance: ");
        Serial.print(radar.movingTargetDistance());
        Serial.println("cm");
        setLEDColor(0, 0, 255); // Turn LED Solid BLUE for motion
        break;

      case 2: // Stationary target only
        Serial.print("▼ TARGET STATIC | Distance: ");
        Serial.print(radar.stationaryTargetDistance());
        Serial.println("cm");
        setLEDColor(255, 165, 0); // Turn LED Solid AMBER/ORANGE for sitting still
        break;

      case 3: // Both moving and stationary targets found
        Serial.println("▼ TARGET DETECTED | Complex Presence");
        setLEDColor(255, 0, 0); // Turn LED Solid RED for complex presence
        break;

      default: // No target (Room is empty)
        Serial.println("▲ Room Empty");
        setLEDColor(0, 255, 0); // Turn LED Solid GREEN when clear
        break;
    }
  }
}
