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
  float sumPitch2 = 0.0f;
  long sumDist = 0;
  double sumDist2 = 0.0;
  int okDist = 0;
  for (int i = 0; i < N; i++) {
    float p = readMPUPitchDegSigned();
    sumPitch += p;
    sumPitch2 += p * p;
    long d = readSonarMmOnce();
    if (d >= 0) { sumDist += d; sumDist2 += (double)d * (double)d; okDist++; }
    delay(70);
  }
  pitchZeroDeg = sumPitch / N;
  calibPitchSamples = N;
  float meanPitch = pitchZeroDeg;
  float varPitch = (sumPitch2 / N) - (meanPitch * meanPitch);
  if (varPitch < 0.0f) varPitch = 0.0f;
  calibPitchStdDeg = sqrtf(varPitch);
  if (okDist < (int)(N * 0.5f)) return false;
  dist0mm = sumDist / okDist;
  calibDistSamples = okDist;
  float meanDist = (float)dist0mm;
  float varDist = (float)(sumDist2 / okDist) - (meanDist * meanDist);
  if (varDist < 0.0f) varDist = 0.0f;
  calibDistStdMm = sqrtf(varDist);
  pitchFiltDeg = pitchZeroDeg;
  lastValidDistMm = dist0mm;
  lastSonarValidMs = millis();
  sonarBufCount = 0;
  sonarBufIndex = 0;
  distSlip0mm = dist0mm;
  return true;
}
