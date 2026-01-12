void setCoils(byte a, byte b, byte c, byte d) {
  digitalWrite(STEPPER_IN1, a); digitalWrite(STEPPER_IN2, b);
  digitalWrite(STEPPER_IN3, c); digitalWrite(STEPPER_IN4, d);
}

void motorOff() { setCoils(0,0,0,0); }

void stepMotorHalfStep(bool dirUp) {
  bool realDir = !dirUp;
  if (motorFullStepMode && ((stepIndex & 0x01) == 0)) stepIndex = (stepIndex + 1) & 0x07;
  if (realDir) stepIndex = (stepIndex + (motorFullStepMode ? 2 : 1)) & 0x07;
  else         stepIndex = (stepIndex + (motorFullStepMode ? 6 : 7)) & 0x07;
  setCoils(seq[stepIndex][0], seq[stepIndex][1], seq[stepIndex][2], seq[stepIndex][3]);
}

void updateMotorNonBlocking() {
  if (!motorEnable) {
    if (!KEEP_HOLDING_TORQUE) motorOff();
    return;
  }
  unsigned long now = micros();
  if (now - lastStepMicros >= stepDelayMicros) {
    lastStepMicros = now;
    stepMotorHalfStep(motorDirUp);
  }
}
