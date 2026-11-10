#include <ld2410.h>

#define RADAR_RX_PIN 5  // Connect to Sensor TX
#define RADAR_TX_PIN 4  // Connect to Sensor RX

// Create the radar object here
ld2410 radar;

// Expose the object globally so the main tab can read distances from it
extern ld2410 radar;

// Function to initialize the radar hardware channel
void setupRadar() {
  // Initialize Serial1 for the sensor
  Serial1.begin(256000, SERIAL_8N1, RADAR_RX_PIN, RADAR_TX_PIN);
  
  Serial.print("Initializing Radar... ");
  if (radar.begin(Serial1)) {
    Serial.println("SUCCESS!");
  } else {
    Serial.println("FAILED. Verify connections on pins 4 & 5.");
  }
}

// Function to process radar data and return target type
// 0 = Empty, 1 = Moving Target, 2 = Stationary Target, 3 = Both
int checkRadarPresence() {
  radar.read(); // Stream incoming packets asynchronously

  if (radar.isConnected()) {
    if (radar.presenceDetected()) {
      if (radar.movingTargetDetected() && radar.stationaryTargetDetected()) return 3;
      if (radar.stationaryTargetDetected()) return 2;
      if (radar.movingTargetDetected()) return 1;
    }
  }
  return 0; // Default to empty
}
