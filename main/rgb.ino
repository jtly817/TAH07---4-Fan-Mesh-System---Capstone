#include <Adafruit_NeoPixel.h>

#define LED_PIN    48
#define LED_COUNT  1

// Initialize the NeoPixel strip object
Adafruit_NeoPixel strip(LED_COUNT, LED_PIN, NEO_GRB + NEO_KHZ800);

// Function to initialize the onboard RGB LED
void setupRGB() {
  strip.begin();
  strip.setBrightness(15); // Slightly brighter for visibility
  setLEDColor(0, 0, 0);    // Clear to off at startup
}

// Helper function to change the color instantly
void setLEDColor(uint8_t r, uint8_t g, uint8_t b) {
  strip.setPixelColor(0, strip.Color(r, g, b));
  strip.show();
}
