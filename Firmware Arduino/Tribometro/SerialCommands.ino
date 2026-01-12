extern bool sonarOk;
extern bool sonarStale;
extern const float TARGET_OFFSET_MM;

long readSonarMmFresh();

byte readMPUWhoAmI();
void scanI2CDevices();

void printHelp() { Serial.println(F("\nComandos: h r z s x p u <ms> j <ms> ip fp scan who | m <g> lbc <val> lbt <val>")); }

void printConfig() {
  Serial.print(F("Massa: "));
  if (mass_g > 0.0f) Serial.print(mass_g, 1); else Serial.print(F("[INDEFINIDA]"));
  Serial.print(F(" | LBC=")); Serial.print(LBC);
  Serial.print(F(" | LBT=")); Serial.print(LBT);

  Serial.print(F(" | IP=")); Serial.print(distInitialMm);
  Serial.print(F(" | FP=")); Serial.print(distFinalMm);

  if (distInitialMm >= 0 && distFinalMm >= 0) {
    Serial.print(F(" | Dist Alvo=")); Serial.print(d_target_mm, 0);
  }
  Serial.println();
}

void handleCommand(char *cmd) {
  while (*cmd == ' ') cmd++;
  if (*cmd == 0) return;
  char c = cmd[0];

  if (c == 'h') { printHelp(); return; }
  if (c == 'r') { printConfig(); return; }
  if (cmd[0] == 's' && cmd[1] == 'c' && cmd[2] == 'a' && cmd[3] == 'n') {
    scanI2CDevices();
    return;
  }
  if (cmd[0] == 'w' && cmd[1] == 'h' && cmd[2] == 'o') {
    byte who = readMPUWhoAmI();
    Serial.print(F("MPU WHO_AM_I: 0x"));
    if (who < 16) Serial.print('0');
    Serial.println(who, HEX);
    return;
  }

  if (cmd[0] == 'i' && cmd[1] == 'p') {
    long d = readSonarMmFresh();
    if (d < 0) { Serial.println(F("Leitura do Sonar inválida.")); return; }
    distInitialMm = d;
    dist0mm = d;
    Serial.print(F("Posição Inicial (IP) definida: ")); Serial.println(distInitialMm);
    if (distFinalMm >= 0) {
      long delta = labs(distFinalMm - distInitialMm);
      long target = (delta > (long)TARGET_OFFSET_MM) ? (delta - (long)TARGET_OFFSET_MM) : 1;
      d_target_mm = (float)target;
      Serial.print(F("Distância alvo (mm): ")); Serial.println(d_target_mm, 0);
    }
    return;
  }
  if (cmd[0] == 'f' && cmd[1] == 'p') {
    long d = readSonarMmFresh();
    if (d < 0) { Serial.println(F("Leitura do Sonar inválida.")); return; }
    distFinalMm = d;
    if (distInitialMm >= 0) dist0mm = distInitialMm;
    Serial.print(F("Posição Final (FP) definida: ")); Serial.println(distFinalMm);
    if (distInitialMm >= 0) {
      long delta = labs(distFinalMm - distInitialMm);
      long target = (delta > (long)TARGET_OFFSET_MM) ? (delta - (long)TARGET_OFFSET_MM) : 1;
      d_target_mm = (float)target;
      Serial.print(F("Distância alvo (mm): ")); Serial.println(d_target_mm, 0);
    }
    return;
  }
  
  if (c == 'm') { mass_g = atof(cmd + 1); Serial.print(F("OK massa: ")); Serial.println(mass_g); return; }
  if (c == 'd') { d_target_mm = atof(cmd + 1); Serial.println(F("OK dist.")); return; }
  
  if (cmd[0] == 'l' && cmd[1] == 'b' && cmd[2] == 'c') { LBC = atoi(cmd + 3); Serial.print(F("OK LBC: ")); Serial.println(LBC); return; }
  if (cmd[0] == 'l' && cmd[1] == 'b' && cmd[2] == 't') { LBT = atoi(cmd + 3); Serial.print(F("OK LBT: ")); Serial.println(LBT); return; }

  if (c == 't') { LBT = atoi(cmd + 1); return; }

  if (c == 'z') {
    levelStartMs = millis();
    pitchFiltDeg = readMPUPitchDegSigned();
    levelRefDeg = 0.0f;
    lastLevelPitchDeg = pitchFiltDeg;
    lastLevelMs = levelStartMs;
    state = LEVELING;
    filterAlpha = 0.80f;
    Serial.println(F("Iniciando nivelamento..."));
    return;
  }

  if (c == 's') {
    if (state == IDLE || state == DONE) {
      if (mass_g <= 0.0f) { Serial.println(F("ERRO: Massa não definida (use 'm <g>').")); return; }
      if (distInitialMm < 0 || distFinalMm < 0) {
        Serial.println(F("Defina IP e FP antes de iniciar."));
        return;
      }
      state = CALIBRATING;
      filterAlpha = 0.90f;
    }
    return;
  }

  if (c == 'x') { state = IDLE; motorEnable = false; filterAlpha = 0.85f; Serial.println(F("IDLE.")); return; }

  if (c == 'p') {
    if (state == PAUSED) { state = resumeState; Serial.println(F("RETOMADO.")); }
    else if (state != IDLE && state != DONE) { resumeState = state; state = PAUSED; motorEnable = false; Serial.println(F("PAUSADO.")); }
    return;
  }

  if (c == 'u') {
    int ms = atoi(cmd + 1); if (ms <= 0) ms = 250; if (ms > 8000) ms = 8000;
    unsigned int prevDelay = stepDelayMicros;
    bool prevFull = motorFullStepMode;
    stepDelayMicros = STEP_DELAY_MANUAL_US;
    targetStepDelayMicros = STEP_DELAY_MANUAL_US;
    motorFullStepMode = true;
    stepIndex |= 0x01; // garante passo de duas bobinas
    motorDirUp = true; motorEnable = true;
    unsigned long start = millis();
    while (millis() - start < (unsigned long)ms) updateMotorNonBlocking();
    motorEnable = false; stepDelayMicros = prevDelay; targetStepDelayMicros = prevDelay; motorFullStepMode = prevFull; return;
  }
  if (c == 'j') {
    int ms = atoi(cmd + 1); if (ms <= 0) ms = 250; if (ms > 8000) ms = 8000;
    unsigned int prevDelay = stepDelayMicros;
    bool prevFull = motorFullStepMode;
    stepDelayMicros = STEP_DELAY_MANUAL_US;
    targetStepDelayMicros = STEP_DELAY_MANUAL_US;
    motorFullStepMode = true;
    stepIndex |= 0x01; // garante passo de duas bobinas
    motorDirUp = false; motorEnable = true;
    unsigned long start = millis();
    while (millis() - start < (unsigned long)ms) updateMotorNonBlocking();
    motorEnable = false; stepDelayMicros = prevDelay; targetStepDelayMicros = prevDelay; motorFullStepMode = prevFull; return;
  }
}

void readSerialLine() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r' || ch == '\n') {
      if (linePos > 0) { lineBuf[linePos] = 0; handleCommand(lineBuf); linePos = 0; }
    } else if (linePos < 30) lineBuf[linePos++] = ch;
  }
}
