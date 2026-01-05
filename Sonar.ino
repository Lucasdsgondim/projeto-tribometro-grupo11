Ultrasonic sonar(PIN_TRIG, PIN_ECHO, 30000UL);
long readSonarMmOnce() {
  unsigned int distMm = sonar.readMM();
  if (distMm == 0) return -1;
  return (long)distMm;
}

long median3(long a, long b, long c) {
  if ((a <= b && b <= c) || (c <= b && b <= a)) return b;
  if ((b <= a && a <= c) || (c <= a && a <= b)) return a;
  return c;
}

long medianFromBuffer() {
  if (sonarBufCount == 0) return -1;
  if (sonarBufCount == 1) return sonarBuf[0];
  if (sonarBufCount == 2) return (sonarBuf[0] + sonarBuf[1]) / 2;
  return median3(sonarBuf[0], sonarBuf[1], sonarBuf[2]);
}

void pushSonarSample(long d) {
  sonarBuf[sonarBufIndex] = d;
  sonarBufIndex = (sonarBufIndex + 1) % 3;
  if (sonarBufCount < 3) sonarBufCount++;
}

void updateSonarFiltered() {
  unsigned long nowMs = millis();
  if (nowMs - lastSonarMs < SONAR_PERIOD_MS) {
    if (lastValidDistMm >= 0 && (nowMs - lastSonarValidMs) <= SONAR_STALE_MS) distNowMm = lastValidDistMm;
    else distNowMm = -1;
    return;
  }
  lastSonarMs = nowMs;
  long d = readSonarMmOnce();
  if (d >= 0) {
    if (lastValidDistMm >= 0 && labs(d - lastValidDistMm) > SONAR_MAX_JUMP_MM) {
      if ((nowMs - lastSonarValidMs) <= SONAR_STALE_MS) distNowMm = lastValidDistMm;
      else distNowMm = -1;
      return;
    }
    pushSonarSample(d);
    long med = medianFromBuffer();
    lastValidDistMm = med;
    lastSonarValidMs = nowMs;
    distNowMm = med;
  } else {
    if (lastValidDistMm >= 0 && (nowMs - lastSonarValidMs) <= SONAR_STALE_MS) distNowMm = lastValidDistMm;
    else distNowMm = -1;
  }
}

long displacementMmAbs(long d0, long dNow) {
  if (d0 < 0 || dNow < 0) return 0;
  long delta = dNow - d0;
  if (delta < 0) delta = -delta;
  return delta;
}
