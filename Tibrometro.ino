#include <Ultrasonic.h>
#include <Wire.h>
#include <math.h>
#include <stdlib.h>

const byte STEPPER_IN1 = 3;
const byte STEPPER_IN2 = 4;
const byte STEPPER_IN3 = 5;
const byte STEPPER_IN4 = 6;

const byte PIN_TRIG = 8;
const byte PIN_ECHO = 9;

const byte MPU_ADDR = 0x68;

const float G = 9.80665f;
const unsigned long SENSOR_PERIOD_MS = 50;
float filterAlpha = 0.90f;

const unsigned int STEP_DELAY_LEVELING_US = 900;
const unsigned int STEP_DELAY_FINE_US = 15000;
// Velocidades dinamicas para o ensaio:
const unsigned int STEP_DELAY_MIN_US = 2000; // Rapido (inicio)
const unsigned int STEP_DELAY_MAX_US = 8000; // Lento (final/inclinado)

unsigned int stepDelayMicros = STEP_DELAY_MIN_US;
const bool KEEP_HOLDING_TORQUE = false;

// Calcula delay baseado no ângulo atual para suavizar a subida em altas inclinações
unsigned int calcStepDelayForAngle(float ang) {
  if (ang < 10.0f) return STEP_DELAY_MIN_US;
  if (ang >= 40.0f) return STEP_DELAY_MAX_US;
  // Interpolacao linear entre 10 e 40 graus
  float factor = (ang - 10.0f) / 30.0f; // 0.0 a 1.0
  return STEP_DELAY_MIN_US + (unsigned int)(factor * (STEP_DELAY_MAX_US - STEP_DELAY_MIN_US));
}

byte stepIndex = 0;
unsigned long lastStepMicros = 0;
bool motorEnable = false;
bool motorDirUp  = true;

// Sequencia half-step otimizada para 28BYJ-48
const byte seq[8][4] = {
  {1,0,0,0}, 
  {1,1,0,0}, 
  {0,1,0,0}, 
  {0,1,1,0}, 
  {0,0,1,0}, 
  {0,0,1,1}, 
  {0,0,0,1}, 
  {1,0,0,1}
};

const unsigned long SONAR_PERIOD_MS = 40;
const unsigned long SONAR_STALE_MS  = 500;
const int SONAR_MAX_JUMP_MM = 500;

unsigned long lastSonarMs = 0;
unsigned long lastSonarValidMs = 0;
long lastValidDistMm = -1;
long sonarBuf[3] = {0,0,0};
byte sonarBufCount = 0;
byte sonarBufIndex = 0;
long distNowMm = -1;
long distInitialMm = -1;
long distFinalMm = -1;

float mass_g = 0.0f;
float d_target_mm = 0.0f;
int LBC = 1;
int LBT = 1;

const float RAMP_RATE_DEG_PER_S = 0.30f;
const float MAX_ANGLE_DEG       = 40.0f;
const float ANGLE_TOL_DEG       = 0.25f;

const int  SLIP_THRESHOLD_MM   = 20;
const byte SLIP_COUNT_REQUIRED = 4;
const unsigned long MOTION_TIMEOUT_MS = 10000;

const float LEVEL_TOL_DEG = 0.05f;
const float LEVEL_TARGET_DEG = 0.0f;
const unsigned long LEVEL_TIMEOUT_MS = 60000UL;
// Nivelamento simples: usa somente o erro do MPU.

enum State { IDLE, LEVELING, CALIBRATING, RAMPING_TO_SLIP, TRACKING_MOTION, DONE, PAUSED };
State state = IDLE;
State resumeState = IDLE;

unsigned long lastSensorMs = 0;
float pitchRawDeg  = 0.0f;
float pitchFiltDeg = 0.0f;
float levelRefDeg  = 0.0f;
float levelOffsetDeg = 0.0f;
float pitchZeroDeg = 0.0f;
float thetaDeg     = 0.0f;

long dist0mm = 0;
long distSlip0mm = 0;
long motionStartSmm = 0;
long lastTrackedDistMm = -1;
byte stableCount = 0;

long displacementRefMm() {
  if (distInitialMm >= 0 && distFinalMm >= 0) return distInitialMm;
  return distSlip0mm;
}

byte slipCounter = 0;
byte sonarInvalidCount = 0;

unsigned long levelStartMs = 0;
unsigned long rampStartMs  = 0;
unsigned long motionStartMs = 0;
unsigned long motionEndMs = 0;

float thetaSlipDeg = 0.0f;
float thetaDynDeg  = 0.0f;
float mu_s = 0.0f;
float mu_d = 0.0f;
float a_est = 0.0f;
float v_end = 0.0f;
float d_meas_m = 0.0f;
float dH_m = 0.0f;
float Wfat_energy = 0.0f;
float Wfat_mu = 0.0f;
float motionTime_s = 0.0f;
bool headerPrinted = false;
double sum_t2s = 0.0;
double sum_t4  = 0.0;
unsigned long motionSamples = 0;
bool mpuOk = true;
float lastMpuPitchDeg = 0.0f;

char lineBuf[32];
byte linePos = 0;

void setup() {
  pinMode(STEPPER_IN1, OUTPUT); pinMode(STEPPER_IN2, OUTPUT);
  pinMode(STEPPER_IN3, OUTPUT); pinMode(STEPPER_IN4, OUTPUT);
  pinMode(PIN_TRIG, OUTPUT); pinMode(PIN_ECHO, INPUT);
  Serial.begin(115200);
  Wire.begin();

  Wire.beginTransmission(MPU_ADDR); Wire.write(0x6B); Wire.write(0x00); Wire.endTransmission(true);
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x1A); Wire.write(0x06); Wire.endTransmission(true);
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x1C); Wire.write(0x00); Wire.endTransmission(true);

  pitchFiltDeg = readMPUPitchDegSigned();
  levelRefDeg = LEVEL_TARGET_DEG + levelOffsetDeg;
  pitchZeroDeg = pitchFiltDeg;

  Serial.println(F("Tribometro pronto."));
  printConfig();
}

void loop() {
  readSerialLine();
  updateMotorNonBlocking();
  if (state == PAUSED) return;

  unsigned long nowMs = millis();
  if (nowMs - lastSensorMs < SENSOR_PERIOD_MS) return;
  lastSensorMs = nowMs;

  pitchRawDeg  = readMPUPitchDegSigned();
  pitchFiltDeg = filterAlpha * pitchFiltDeg + (1.0f - filterAlpha) * pitchRawDeg;
  thetaDeg = fabsf(pitchFiltDeg - pitchZeroDeg);
  updateSonarFiltered();


  switch (state) {
    case IDLE:
      motorEnable = false;
      slipCounter = 0;
      break;

    case LEVELING: {
      if (millis() - levelStartMs > LEVEL_TIMEOUT_MS) {
        motorEnable = false;
        state = IDLE;
        Serial.println(F("Erro: Tempo limite de nivelamento."));
        break;
      }
      
      // Alvo sempre absoluto em 0.0
      levelRefDeg = 0.0f;
      float err = pitchFiltDeg - levelRefDeg;
      float absErr = fabsf(err);

      if (absErr <= LEVEL_TOL_DEG) {
        motorEnable = false;
        state = IDLE;
        // Auto-tara: define a posição atual como novo Zero absoluto
        pitchZeroDeg = pitchFiltDeg; 
        Serial.print(F("Nivelado. Referência Zero: ")); Serial.println(pitchZeroDeg, 3);
      } else {
        // Logica de duas velocidades
        if (absErr > 2.0f) {
          stepDelayMicros = STEP_DELAY_LEVELING_US; // Rapido
        } else {
          stepDelayMicros = STEP_DELAY_FINE_US;     // Lento/Preciso
        }
        
        motorDirUp = (err >= 0.0f);
        motorEnable = true;
      }
    } break;

    case CALIBRATING:
      motorEnable = false;
      Serial.println(F("Calibrando..."));
      if (calibrateSensors()) {
        rampStartMs = millis();
        slipCounter = 0;
        sonarInvalidCount = 0;
        state = RAMPING_TO_SLIP;
        Serial.println(F("Iniciando rampa..."));
      } else {
        Serial.println(F("Erro Sonar."));
        state = IDLE;
      }
      break;

    case RAMPING_TO_SLIP: {
      // Ajusta velocidade dinamicamente conforme a inclinacao aumenta
      stepDelayMicros = calcStepDelayForAngle(thetaDeg);
      
      motorDirUp = true;
      motorEnable = true;

      if (distNowMm >= 0) {
        long s_mm = displacementMmAbs(dist0mm, distNowMm);
        if (s_mm >= SLIP_THRESHOLD_MM) slipCounter++;
        else slipCounter = 0;

        if (slipCounter >= SLIP_COUNT_REQUIRED) {
          thetaSlipDeg = thetaDeg;
          mu_s = tanf(thetaSlipDeg * PI / 180.0f);
          thetaDynDeg = thetaDeg;
          motorEnable = false;
          motionStartMs = millis();
          sum_t2s = 0.0;
          sum_t4  = 0.0;
          motionSamples = 0;
          motionStartSmm = displacementMmAbs(displacementRefMm(), distNowMm);
          distSlip0mm = distNowMm;
          
          lastTrackedDistMm = distNowMm;
          stableCount = 0;
          
          state = TRACKING_MOTION;
          Serial.println(F("Movimento detectado."));
        }
      }

      if (thetaDeg >= (MAX_ANGLE_DEG - 0.1f)) {
        motorEnable = false;
        thetaSlipDeg = thetaDeg;
        mu_s = tanf(thetaSlipDeg * PI / 180.0f);
        thetaDynDeg = thetaDeg;
        motionStartMs = millis();
        motionEndMs = motionStartMs;
        Serial.println(F("Ângulo máximo atingido (sem movimento)."));
        finishAndPrintResults();
        state = DONE;
      }
    } break;

    case TRACKING_MOTION: {
      if (distNowMm < 0) {
        sonarInvalidCount++;
        if (sonarInvalidCount > 20) {
          motionEndMs = millis();
          Serial.println(F("Erro: Perda de sinal do Sonar."));
          finishAndPrintResults();
          state = DONE;
        }
        break;
      }
      sonarInvalidCount = 0;

      if (labs(distNowMm - lastTrackedDistMm) <= 2) {
        stableCount++;
      } else {
        stableCount = 0;
        lastTrackedDistMm = distNowMm;
      }

      long s_mm = displacementMmAbs(displacementRefMm(), distNowMm);
      long s_rel_mm = s_mm - motionStartSmm;
      if (s_rel_mm < 0) s_rel_mm = 0;
      float t = (millis() - motionStartMs) / 1000.0f;
      if (t > 0.0f) {
        double s_m = (double)s_rel_mm / 1000.0;
        double t2 = (double)t * (double)t;
        sum_t2s += t2 * s_m;
        sum_t4  += t2 * t2;
        motionSamples++;
      }

      if (s_rel_mm >= (long)d_target_mm) {
        motionEndMs = millis();
        Serial.println(F("Fim de curso atingido."));
        finishAndPrintResults();
        state = DONE;
        break;
      }
      
      if (stableCount > 20) {
        motionEndMs = millis() - (stableCount * SENSOR_PERIOD_MS);
        Serial.println(F("Movimento encerrado (estável)."));
        finishAndPrintResults();
        state = DONE;
        break;
      }

      if (millis() - motionStartMs > MOTION_TIMEOUT_MS) {
        motionEndMs = millis();
        Serial.println(F("Timeout do movimento."));
        finishAndPrintResults();
        state = DONE;
      }
    } break;

    case DONE:
      motorEnable = false;
      break;
  }
}
