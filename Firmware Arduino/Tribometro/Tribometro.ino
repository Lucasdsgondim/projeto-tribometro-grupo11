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

extern bool sonarOk;
extern bool sonarStale;
extern unsigned long sonarAgeMs;
extern long distNowMm;
extern long distInitialMm;
extern long distFinalMm;

float readMPUPitchDegSigned();
void updateSonarFiltered();
void updateMotorNonBlocking();
void readSerialLine();
bool calibrateSensors();
void finishAndPrintResults();
void printConfig();

const unsigned int STEP_DELAY_FINE_US = 18000;
const unsigned int STEP_DELAY_MIN_US = 2000; // Rapido (inicio)
const unsigned int STEP_DELAY_MAX_US = 8000; // Lento (final/inclinado)
const unsigned int STEP_DELAY_SMOOTH_US_PER_MS = 15;
const unsigned int STEP_DELAY_MANUAL_US = 2000;
const unsigned int STEP_DELAY_LEVELING_US = 1000;

unsigned int stepDelayMicros = STEP_DELAY_MIN_US;
unsigned int targetStepDelayMicros = STEP_DELAY_MIN_US;
unsigned long lastDelayUpdateMs = 0;
const bool KEEP_HOLDING_TORQUE = false;

unsigned int calcStepDelayForAngle(float ang) {
  if (ang < 10.0f) return STEP_DELAY_MIN_US;
  if (ang >= 40.0f) return STEP_DELAY_MAX_US;
  float factor = (ang - 10.0f) / 30.0f; 
  return STEP_DELAY_MIN_US + (unsigned int)(factor * (STEP_DELAY_MAX_US - STEP_DELAY_MIN_US));
}

void updateStepDelaySmooth(unsigned long nowMs) {
  unsigned long dt = nowMs - lastDelayUpdateMs;
  if (dt == 0) return;
  lastDelayUpdateMs = nowMs;
  long delta = (long)targetStepDelayMicros - (long)stepDelayMicros;
  long maxDelta = (long)STEP_DELAY_SMOOTH_US_PER_MS * (long)dt;
  if (delta > maxDelta) delta = maxDelta;
  else if (delta < -maxDelta) delta = -maxDelta;
  stepDelayMicros = (unsigned int)((long)stepDelayMicros + delta);
}

byte stepIndex = 0;
unsigned long lastStepMicros = 0;
bool motorEnable = false;
bool motorDirUp  = true;
bool motorFullStepMode = false;

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

const float MAX_ANGLE_DEG       = 45.0f;

const int  SLIP_THRESHOLD_MM   = 20;
const int  SLIP_VEL_THRESHOLD_MM_S = 40;
const int  SLIP_MIN_STEP_MM = 3;
const float SLIP_MIN_ANGLE_DEG = 2.0f;
const int  START_REF_MAX_DELTA_MM = 50;
const float TARGET_OFFSET_MM = 10.0f;
const float CALIB_PITCH_STD_MAX = 0.5f;
const float CALIB_DIST_STD_MAX = 20.0f;
const byte CALIB_MAX_RETRIES = 3;
const byte SLIP_COUNT_REQUIRED = 2;
const unsigned long MOTION_TIMEOUT_MS = 10000;
const unsigned long MIN_MOTION_SAMPLES = 6;
const float STABLE_END_FRACTION = 0.7f;

const float LEVEL_TOL_DEG = 0.025f;
const float LEVEL_PAUSE_TOL_DEG = 0.20f;
const unsigned long LEVEL_TIMEOUT_MS = 60000UL;
const float LEVEL_FINE_ENTER_DEG = 3.0f;
const float LEVEL_FINE_EXIT_DEG  = 4.5f;
const float LEVEL_FINE_RATE_MAX_DEG_S = 0.6f;
const unsigned long LEVEL_VERIFY_MS = 500;

enum State { IDLE, LEVELING, CALIBRATING, RAMPING_TO_SLIP, TRACKING_MOTION, DONE, PAUSED };
State state = IDLE;
State resumeState = IDLE;
bool levelingFineMode = false;
bool levelVerifyPending = false;
unsigned long levelVerifyStartMs = 0;

unsigned long lastSensorMs = 0;
float pitchRawDeg  = 0.0f;
float pitchFiltDeg = 0.0f;
float levelRefDeg  = 0.0f;
float pitchZeroDeg = 0.0f;
float thetaDeg     = 0.0f;
float mpuTempC = 0.0f;
int16_t mpuRawX = 0;
int16_t mpuRawY = 0;
int16_t mpuRawZ = 0;
int16_t mpuRawTemp = 0;

float calibPitchStdDeg = 0.0f;
float calibDistStdMm = 0.0f;
int calibPitchSamples = 0;
int calibDistSamples = 0;

long dist0mm = 0;
long distSlip0mm = 0;
long motionStartSmm = 0;
long lastTrackedDistMm = -1;
byte stableCount = 0;
long lastSlipSmm = 0;
unsigned long lastSlipCheckMs = 0;
byte slipVelCounter = 0;
bool slipArmed = false;

bool isSonarFresh() {
  return sonarOk && !sonarStale;
}

long displacementRefMm() {
  if (distInitialMm >= 0 && distFinalMm >= 0) return distInitialMm;
  return distSlip0mm;
}

long displacementMmToward(long dRef, long dNow) {
  if (dRef < 0 || dNow < 0) return 0;
  long delta = dRef - dNow; // positive when approaching the sonar
  if (delta < 0) delta = 0;
  return delta;
}

byte slipCounter = 0;
byte sonarInvalidCount = 0;

unsigned long levelStartMs = 0;
unsigned long rampStartMs  = 0;
unsigned long motionStartMs = 0;
unsigned long motionEndMs = 0;
long distEndMm = -1;

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
bool mpuOkAtSlip = true;
float lastMpuPitchDeg = 0.0f;
float lastLevelPitchDeg = 0.0f;
unsigned long lastLevelMs = 0;

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
  levelRefDeg = 0.0f;
  pitchZeroDeg = pitchFiltDeg;
  targetStepDelayMicros = stepDelayMicros;
  lastDelayUpdateMs = millis();

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
  if (state == RAMPING_TO_SLIP || state == TRACKING_MOTION) {
    updateStepDelaySmooth(nowMs);
  } else {
    stepDelayMicros = targetStepDelayMicros;
    lastDelayUpdateMs = nowMs;
  }


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
      float rateAbsDegS = 0.0f;
      unsigned long nowLevelMs = nowMs;
      unsigned long dtLevelMs = nowLevelMs - lastLevelMs;
      if (dtLevelMs > 0) {
        float dPitch = pitchFiltDeg - lastLevelPitchDeg;
        rateAbsDegS = fabsf(dPitch * (1000.0f / (float)dtLevelMs));
        lastLevelPitchDeg = pitchFiltDeg;
        lastLevelMs = nowLevelMs;
      }

      if (levelingFineMode && absErr <= LEVEL_PAUSE_TOL_DEG) {
        if (!levelVerifyPending) {
          levelVerifyPending = true;
          levelVerifyStartMs = nowMs;
        }
        motorEnable = false;
        if (nowMs - levelVerifyStartMs >= LEVEL_VERIFY_MS) {
          if (absErr <= LEVEL_TOL_DEG) {
            state = IDLE;
            levelVerifyPending = false;
            // Auto-tara: define a posição atual como novo Zero absoluto
            pitchZeroDeg = pitchFiltDeg; 
            Serial.print(F("Nivelado. Referência Zero: ")); Serial.println(pitchZeroDeg, 3);
          } else {
            levelVerifyPending = false;
          }
        }
      } else {
        levelVerifyPending = false;
        // Logica de duas velocidades com histerese
        if (!levelingFineMode && absErr <= LEVEL_FINE_ENTER_DEG) {
          levelingFineMode = true;
        } else if (levelingFineMode && (absErr >= LEVEL_FINE_EXIT_DEG || rateAbsDegS > LEVEL_FINE_RATE_MAX_DEG_S)) {
          levelingFineMode = false;
        }
        if (levelingFineMode) {
          targetStepDelayMicros = STEP_DELAY_FINE_US; // Lento/Preciso
        } else {
          targetStepDelayMicros = STEP_DELAY_LEVELING_US; // Rapido
        }
        
        motorDirUp = (err >= 0.0f);
        motorEnable = true;
      }
    } break;

    case CALIBRATING:
      motorEnable = false;
      Serial.println(F("Calibrando..."));
      {
        bool ok = false;
        for (byte i = 0; i < CALIB_MAX_RETRIES; i++) {
          if (!calibrateSensors()) continue;
          Serial.print(F("Calibracao: pitch_std=")); Serial.print(calibPitchStdDeg, 3);
          Serial.print(F(" deg, dist_std=")); Serial.print(calibDistStdMm, 1);
          Serial.print(F(" mm (tentativa ")); Serial.print(i + 1); Serial.println(F(")"));
          if (calibPitchStdDeg <= CALIB_PITCH_STD_MAX && calibDistStdMm <= CALIB_DIST_STD_MAX) {
            ok = true;
            break;
          }
          Serial.print(F("Calibracao instavel. Tentando novamente (")); Serial.print(i + 1); Serial.println(F(")..."));
        }
        if (!ok) {
          Serial.println(F("Erro: Calibracao instavel. Reposicione e tente novamente."));
          state = IDLE;
          break;
        }
        rampStartMs = millis();
        slipCounter = 0;
        slipVelCounter = 0;
        lastSlipSmm = 0;
        lastSlipCheckMs = millis();
        slipArmed = false;
        mpuOkAtSlip = mpuOk;
        sonarInvalidCount = 0;
        state = RAMPING_TO_SLIP;
        Serial.println(F("Iniciando rampa..."));
      }
      break;

    case RAMPING_TO_SLIP: {
      // Ajusta velocidade dinamicamente conforme a inclinacao aumenta
      targetStepDelayMicros = calcStepDelayForAngle(thetaDeg);
      
      motorDirUp = true;
      motorEnable = true;

      if (isSonarFresh()) {
        long refMm = displacementRefMm();
        long s_mm = displacementMmToward(refMm, distNowMm);
        if ((refMm - distNowMm) > START_REF_MAX_DELTA_MM && slipCounter == 0 && slipVelCounter == 0) {
          motorEnable = false;
          Serial.println(F("Erro: dist0 divergente. Refaça calibracao/posicionamento."));
          state = IDLE;
          break;
        }
        if (!slipArmed) {
          lastSlipSmm = s_mm;
          lastSlipCheckMs = millis();
          slipCounter = 0;
          slipVelCounter = 0;
          slipArmed = true;
          break;
        }
        if (s_mm >= SLIP_THRESHOLD_MM && thetaDeg >= SLIP_MIN_ANGLE_DEG) slipCounter++;
        else slipCounter = 0;

        unsigned long nowMs = millis();
        unsigned long dt = nowMs - lastSlipCheckMs;
        if (dt > 0) {
          long ds = s_mm - lastSlipSmm;
          if (ds >= SLIP_MIN_STEP_MM) {
            long vel = (ds * 1000L) / (long)dt;
            if (vel >= SLIP_VEL_THRESHOLD_MM_S) slipVelCounter++;
            else slipVelCounter = 0;
          } else if (ds <= -SLIP_MIN_STEP_MM) {
            slipVelCounter = 0;
          }
          lastSlipSmm = s_mm;
          lastSlipCheckMs = nowMs;
        }
      } else {
        slipCounter = 0;
        slipVelCounter = 0;
      }

      if (slipCounter >= SLIP_COUNT_REQUIRED && slipVelCounter >= 2) {
        thetaSlipDeg = thetaDeg;
        mu_s = tanf(thetaSlipDeg * PI / 180.0f);
        thetaDynDeg = thetaDeg;
        mpuOkAtSlip = mpuOk;
        motorEnable = false;
          motionStartMs = millis();
          distEndMm = -1;
        sum_t2s = 0.0;
        sum_t4  = 0.0;
        motionSamples = 0;
        motionStartSmm = displacementMmToward(displacementRefMm(), distNowMm);
        distSlip0mm = distNowMm;
        
        lastTrackedDistMm = distNowMm;
        stableCount = 0;
        
        state = TRACKING_MOTION;
        Serial.println(F("Movimento detectado."));
      }

      if (thetaDeg >= (MAX_ANGLE_DEG - 0.1f)) {
        motorEnable = false;
        thetaSlipDeg = thetaDeg;
        mu_s = tanf(thetaSlipDeg * PI / 180.0f);
        thetaDynDeg = thetaDeg;
        mpuOkAtSlip = mpuOk;
        motionStartMs = millis();
        distEndMm = -1;
        motionEndMs = motionStartMs;
        Serial.println(F("Ângulo máximo atingido (sem movimento)."));
        finishAndPrintResults();
        state = DONE;
      }
    } break;

    case TRACKING_MOTION: {
      if (!isSonarFresh()) {
        sonarInvalidCount++;
        if (sonarInvalidCount > 20) {
          motionEndMs = millis();
          distEndMm = distNowMm;
          Serial.println(F("Erro: Perda de sinal do Sonar."));
          finishAndPrintResults();
          state = DONE;
        }
        break;
      }
      sonarInvalidCount = 0;

      bool movingSample = (labs(distNowMm - lastTrackedDistMm) > 2);
      if (movingSample) {
        stableCount = 0;
        lastTrackedDistMm = distNowMm;
      } else {
        stableCount++;
      }

      long s_mm = displacementMmToward(displacementRefMm(), distNowMm);
      long s_rel_mm = s_mm - motionStartSmm;
      if (s_rel_mm < 0) s_rel_mm = 0;
      float t = (millis() - motionStartMs) / 1000.0f;
      if (t > 0.0f && movingSample) {
        double s_m = (double)s_rel_mm / 1000.0;
        double t2 = (double)t * (double)t;
        sum_t2s += t2 * s_m;
        sum_t4  += t2 * t2;
        motionSamples++;
      }

      bool useAbsTarget = (distInitialMm >= 0 && distFinalMm >= 0);
      long s_check_mm = useAbsTarget ? s_mm : s_rel_mm;
      if (s_check_mm >= (long)d_target_mm) {
        motionEndMs = millis();
        distEndMm = distNowMm;
        Serial.println(F("Fim de curso atingido."));
        finishAndPrintResults();
        state = DONE;
        break;
      }
      
      if (stableCount > 20) {
        if (d_target_mm > 0.0f && s_rel_mm < (long)(d_target_mm * STABLE_END_FRACTION)) {
          break;
        }
        motionEndMs = millis() - (stableCount * SENSOR_PERIOD_MS);
        distEndMm = distNowMm;
        Serial.println(F("Movimento encerrado (estável)."));
        finishAndPrintResults();
        state = DONE;
        break;
      }

      if (millis() - motionStartMs > MOTION_TIMEOUT_MS) {
        motionEndMs = millis();
        distEndMm = distNowMm;
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
