// arduino/turac_pid_demo.ino
#include <Servo.h>

const int NUM_CHANNELS = 4;

// ----- SG90 pump demo (CH1) -----
const int SERVO_PIN = 9;      // requested
Servo pumpServo;
const int SERVO_IDLE = 10;
const int SERVO_PUMP = 45;

// ----- Setpoint (default) -----
float PID_SETPOINTS[NUM_CHANNELS] = {0.65, 0.65, 0.65, 0.65};
float PID_Kp[NUM_CHANNELS]        = {1.5,  1.5,  1.5,  1.5};
float PID_Ki[NUM_CHANNELS]        = {0.05, 0.05, 0.05, 0.05};
float PID_Kd[NUM_CHANNELS]        = {0.02, 0.02, 0.02, 0.02};

// ----- Demo OD values -----
float odValue[NUM_CHANNELS] = {0.70, 0.70, 0.70, 0.70};  // start above SP

// ----- PID state (per channel) -----
float pidError[NUM_CHANNELS] = {0,0,0,0};
float pidLastError[NUM_CHANNELS] = {0,0,0,0};
float pidIntegral[NUM_CHANNELS] = {0,0,0,0};
float pidDerivative[NUM_CHANNELS] = {0,0,0,0};
float pidOutputPercent[NUM_CHANNELS] = {0,0,0,0};

// ----- Pump state -----
bool pumpOn = false;

// ----- Timing -----
unsigned long lastTick = 0;
const unsigned long TICK_MS = 1000;

// ----- Deterministic demo pattern -----
// 0..59 sec: force OD above setpoint (SP + 0.05)
// 60..119 sec: force OD below setpoint (SP - 0.05)
// Repeat forever
unsigned long cycleStart = 0;

float clampf(float x, float lo, float hi) {
  if (x < lo) return lo;
  if (x > hi) return hi;
  return x;
}

// PID calculation uses: error = od - setpoint
void calculatePID(int ch) {
  pidLastError[ch] = pidError[ch];
  pidError[ch] = odValue[ch] - PID_SETPOINTS[ch];

  float deltaTime = 1.0;

  float P = PID_Kp[ch] * pidError[ch];

  pidIntegral[ch] += pidError[ch] * deltaTime;
  pidIntegral[ch] = clampf(pidIntegral[ch], -100, 100);

  float I = PID_Ki[ch] * pidIntegral[ch];

  pidDerivative[ch] = (pidError[ch] - pidLastError[ch]) / deltaTime;
  float D = PID_Kd[ch] * pidDerivative[ch];

  pidOutputPercent[ch] = P + I + D;
  pidOutputPercent[ch] = clampf(pidOutputPercent[ch], 0, 100);
}

// ----- Interpret controller output as ON/OFF pump for demo -----
// If OD is above SP -> pump ON
// If OD is below SP -> pump OFF
void applyPumpLogic() {
  // CH1 controls pump
  if (odValue[0] > PID_SETPOINTS[0]) {
    pumpOn = true;
    pumpServo.write(SERVO_PUMP);
  } else {
    pumpOn = false;
    pumpServo.write(SERVO_IDLE);
  }
}

// ----- Receive PID line from backend -----
// format: PID,SP,a,b,c,d,KP,a,b,c,d,KI,a,b,c,d,KD,a,b,c,d
void handlePIDLine(String line) {
  line.trim();
  if (!line.startsWith("PID,")) return;

  const int MAX_TOK = 80;
  String tok[MAX_TOK];
  int n = 0;

  int start = 0;
  while (true) {
    int idx = line.indexOf(',', start);
    if (idx == -1) {
      tok[n++] = line.substring(start);
      break;
    }
    tok[n++] = line.substring(start, idx);
    start = idx + 1;
    if (n >= MAX_TOK) break;
  }

  auto loadSection = [&](const String& key, float arr[]) {
    for (int i = 0; i < n; i++) {
      if (tok[i] == key) {
        if (i + NUM_CHANNELS >= n) return;
        for (int ch = 0; ch < NUM_CHANNELS; ch++) {
          arr[ch] = tok[i + 1 + ch].toFloat();
        }
        return;
      }
    }
  };

  loadSection("SP", PID_SETPOINTS);
  loadSection("KP", PID_Kp);
  loadSection("KI", PID_Ki);
  loadSection("KD", PID_Kd);

  // reset integrators for clean behavior
  for (int ch = 0; ch < NUM_CHANNELS; ch++) pidIntegral[ch] = 0;

  Serial.print("ACK,SP1=");
  Serial.print(PID_SETPOINTS[0], 3);
  Serial.print(",SP2=");
  Serial.print(PID_SETPOINTS[1], 3);
  Serial.print(",SP3=");
  Serial.print(PID_SETPOINTS[2], 3);
  Serial.print(",SP4=");
  Serial.println(PID_SETPOINTS[3], 3);
}

void checkSerial() {
  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.startsWith("PID,")) handlePIDLine(line);
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial) { ; }

  pumpServo.attach(SERVO_PIN);
  pumpServo.write(SERVO_IDLE);

  cycleStart = millis();

  Serial.println("TuRAC Demo: OD toggles 1min above/below setpoint, pump switches (SG90 pin 9).");
  Serial.println("Format: OD,v1,v2,v3,v4");
}

void loop() {
  checkSerial();

  unsigned long now = millis();
  if (now - lastTick >= TICK_MS) {
    lastTick = now;

    // Determine which minute we are in within a 2-minute cycle
    unsigned long elapsed = (now - cycleStart) / 1000UL;   // seconds
    unsigned long phase = elapsed % 120UL;                 // 0..119

    // Create OD values relative to setpoint (no gradual drift)
    for (int ch = 0; ch < NUM_CHANNELS; ch++) {
      if (phase < 60UL) {
        // 1st minute: above setpoint
        odValue[ch] = PID_SETPOINTS[ch] + 0.05;
      } else {
        // 2nd minute: below setpoint
        odValue[ch] = PID_SETPOINTS[ch] - 0.05;
      }
    }

    // Calculate PID (not required for ON/OFF demo, but kept to match your structure)
    for (int ch = 0; ch < NUM_CHANNELS; ch++) {
      calculatePID(ch);
    }

    // Pump logic: ON when above SP, OFF when below SP
    applyPumpLogic();

    // Send OD to backend (dashboard)
    Serial.print("OD,");
    for (int ch = 0; ch < NUM_CHANNELS; ch++) {
      Serial.print(odValue[ch], 3);
      if (ch < NUM_CHANNELS - 1) Serial.print(",");
    }
    Serial.println();

    // Debug for demo
    Serial.print("DBG,phase=");
    Serial.print(phase);
    Serial.print(",SP1=");
    Serial.print(PID_SETPOINTS[0], 3);
    Serial.print(",OD1=");
    Serial.print(odValue[0], 3);
    Serial.print(",PUMP=");
    Serial.println(pumpOn ? "ON" : "OFF");
  }
}
