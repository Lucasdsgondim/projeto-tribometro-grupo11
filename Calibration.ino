void resetFilter() {
  for(int i=0; i<5; i++) {
    pitchFiltDeg = readMPUPitchDegSigned();
    delay(5);
  }
}

bool calibrateSensors() {
  resetFilter();

  const int N = 40;
  float sumPitch = 0.0f;
  long sumDist = 0;
  int okDist = 0;
  for (int i = 0; i < N; i++) {
    sumPitch += readMPUPitchDegSigned();
    long d = readSonarMmOnce();
    if (d >= 0) { sumDist += d; okDist++; }
    delay(70); // respeita intervalo do sonar
  }
  pitchZeroDeg = sumPitch / N;
  if (okDist < (int)(N * 0.5f)) return false;
  dist0mm = sumDist / okDist;
  pitchFiltDeg = pitchZeroDeg;
  lastValidDistMm = dist0mm;
  lastSonarValidMs = millis();
  sonarBufCount = 0;
  sonarBufIndex = 0;
  distSlip0mm = dist0mm;
  return true;
}
