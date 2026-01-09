Ultrasonic sonar(PIN_TRIG, PIN_ECHO, 30000UL);
long lastSonarRawMm = -1;
bool sonarOk = false;
bool sonarStale = false;
unsigned long sonarAgeMs = 0;
long readSonarMmOnce() {
  unsigned int distMm = sonar.readMM();
  if (distMm == 0) {
    lastSonarRawMm = -1;
    return -1;
  }
  lastSonarRawMm = (long)distMm;
  return (long)distMm;
}

long readSonarMmFresh() {
  long d = readSonarMmOnce();
  if (d >= 0) {
    pushSonarSample(d);
    long med = medianFromBuffer();
    lastValidDistMm = med;
    lastSonarValidMs = millis();
    distNowMm = med;
    sonarOk = true;
    sonarStale = false;
    sonarAgeMs = 0;
    return med;
  }
  sonarOk = false;
  sonarStale = false;
  sonarAgeMs = 0;
  return -1;
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
  sonarOk = false;
  sonarStale = false;
  sonarAgeMs = 0;
  if (nowMs - lastSonarMs < SONAR_PERIOD_MS) {
    unsigned long age = (lastValidDistMm >= 0) ? (nowMs - lastSonarValidMs) : 0;
    if (lastValidDistMm >= 0 && age <= SONAR_STALE_MS) {
      distNowMm = lastValidDistMm;
      sonarOk = true;
      sonarStale = true;
      sonarAgeMs = age;
    } else {
      distNowMm = -1;
    }
    return;
  }
  lastSonarMs = nowMs;
  long d = readSonarMmOnce();
  if (d >= 0) {
    unsigned long age = (lastValidDistMm >= 0) ? (nowMs - lastSonarValidMs) : 0;
    if (lastValidDistMm >= 0 && labs(d - lastValidDistMm) > SONAR_MAX_JUMP_MM) {
      if (age <= SONAR_STALE_MS) {
        distNowMm = lastValidDistMm;
        sonarOk = true;
        sonarStale = true;
        sonarAgeMs = age;
      } else {
        distNowMm = -1;
      }
      return;
    }
    pushSonarSample(d);
    long med = medianFromBuffer();
    lastValidDistMm = med;
    lastSonarValidMs = nowMs;
    distNowMm = med;
    sonarOk = true;
  } else {
    unsigned long age = (lastValidDistMm >= 0) ? (nowMs - lastSonarValidMs) : 0;
    if (lastValidDistMm >= 0 && age <= SONAR_STALE_MS) {
      distNowMm = lastValidDistMm;
      sonarOk = true;
      sonarStale = true;
      sonarAgeMs = age;
    } else {
      distNowMm = -1;
    }
  }
}

long displacementMmAbs(long d0, long dNow) {
  if (d0 < 0 || dNow < 0) return 0;
  long delta = dNow - d0;
  if (delta < 0) delta = -delta;
  return delta;
}
