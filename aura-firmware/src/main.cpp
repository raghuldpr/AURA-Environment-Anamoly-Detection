#include <Arduino.h>
#include <DHT.h>
#include <esp_system.h>

#define DHTPIN      4
#define DHTTYPE     DHT11   // the sensor on this build is a DHT11 (not DHT22)
#define LDR_PIN     34
#define MQ_PIN      35   // MQ analog out via voltage divider (ADC1, input-only)
#define RED_PIN     27
#define YELLOW_PIN  25
#define GREEN_PIN   26
#define BUZZER      33

DHT dht(DHTPIN, DHTTYPE);
const unsigned long INTERVAL_MS = 2000;
const unsigned long FAILSAFE_MS = 10000;  // no command for 10 s -> yellow
unsigned long lastRead = 0;
unsigned long lastCmd = 0;

// '0' = normal (green), '1' = anomaly (red + buzzer), '2' = calibrating / idle (yellow)
char currentState = 0;

void setState(char s) {
  if (s != currentState) {                    // '#' lines are ignored by the app
    Serial.printf("# state=%c\n", s);
    currentState = s;
  }
  digitalWrite(GREEN_PIN,  s == '0');
  digitalWrite(RED_PIN,    s == '1');
  digitalWrite(BUZZER,     s == '1');
  digitalWrite(YELLOW_PIN, s == '2');
}

void setup() {
  Serial.begin(115200);
  Serial.printf("# boot reset_reason=%d\n", (int)esp_reset_reason());  // 1=power-on 3=sw 6=brownout...
  pinMode(GREEN_PIN, OUTPUT);
  pinMode(YELLOW_PIN, OUTPUT);
  pinMode(RED_PIN, OUTPUT);
  pinMode(BUZZER, OUTPUT);
  analogReadResolution(12);  // 0..4095
  // MQ analog out is small in clean air and halved by the divider: use a lower input
  // range (about 0..1.25 V at the pin) so low voltages are not lost in the ADC dead zone.
  // Strong gas readings simply saturate at 4095, which is still a clear anomaly.
  analogSetPinAttenuation(MQ_PIN, ADC_2_5db);
  dht.begin();
  setState('2');
  lastCmd = millis();
}

void loop() {
  // Commands from the PC. The app re-sends its state every ~2 s (heartbeat).
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '0' || c == '1' || c == '2') {
      setState(c);
      lastCmd = millis();
    }
  }

  // Failsafe: app silent -> yellow, so a stale alarm never sticks.
  if (millis() - lastCmd > FAILSAFE_MS) {
    setState('2');
    lastCmd = millis();
  }

  if (millis() - lastRead >= INTERVAL_MS) {
    lastRead = millis();
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    int light = analogRead(LDR_PIN);
    int gas = analogRead(MQ_PIN);

    if (isnan(t) || isnan(h)) {
      // '#' lines are ignored by the app; handy for wiring diagnosis
      Serial.printf("# DHT read failed | light=%d gas=%d\n", light, gas);
      return;
    }
    // Line format: "temp,hum,light,gas*XX" where XX is the XOR of the payload bytes (hex).
    // The app discards lines that fail the check (dropped/garbled characters).
    char buf[48];
    snprintf(buf, sizeof(buf), "%.1f,%.1f,%d,%d", t, h, light, gas);
    uint8_t x = 0;
    for (const char *p = buf; *p; ++p) x ^= (uint8_t)*p;
    Serial.printf("%s*%02X\n", buf, x);
  }
}
