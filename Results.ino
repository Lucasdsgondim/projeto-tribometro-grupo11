void printCSVHeader() {
  Serial.println(F("massa_g;LBC;LBT;angulo_deg;altura_m;mu_s;mu_d;aceleracao_mps2;velocidade_mps;tempo_s;amostras;trabalho_energia_J;trabalho_atrito_J"));
}

void finishAndPrintResults() {
  long dUse = (distNowMm >= 0) ? distNowMm : lastValidDistMm;
  long refMm = displacementRefMm();
  long s_mm = (dUse >= 0) ? displacementMmAbs(refMm, dUse) : 0;
  if (dUse < 0) d_meas_m = d_target_mm / 1000.0f;
  else d_meas_m = s_mm / 1000.0f;

  if (motionEndMs >= motionStartMs) motionTime_s = (motionEndMs - motionStartMs) / 1000.0f;
  else motionTime_s = 0.0f;
  if (sum_t4 > 1e-9) {
    a_est = (float)(2.0 * sum_t2s / sum_t4);
  } else if (motionTime_s > 0.05f && d_meas_m > 0.0f) {
    a_est = (2.0f * d_meas_m) / (motionTime_s * motionTime_s);
  } else {
    a_est = 0.0f;
  }

  float thetaRad = thetaDynDeg * PI / 180.0f;
  v_end = sqrtf(fmaxf(0.0f, 2.0f * a_est * d_meas_m));
  float den = (G * cosf(thetaRad));
  mu_d = (fabsf(den) > 1e-9f) ? ((G * sinf(thetaRad) - a_est) / den) : 0.0f;
  dH_m = d_meas_m * sinf(thetaRad);
  float m_kg = mass_g / 1000.0f;
  Wfat_energy = 0.5f * m_kg * v_end * v_end - m_kg * G * dH_m;
  Wfat_mu     = mu_d * m_kg * G * cosf(thetaRad) * d_meas_m;
  if (!headerPrinted) { printCSVHeader(); headerPrinted = true; }
  Serial.print(mass_g, 1); Serial.print(';');
  Serial.print(LBC); Serial.print(';');
  Serial.print(LBT); Serial.print(';');
  Serial.print(thetaDynDeg, 3); Serial.print(';');
  Serial.print(dH_m, 4); Serial.print(';');
  Serial.print(mu_s, 4); Serial.print(';');
  Serial.print(mu_d, 4); Serial.print(';');
  Serial.print(a_est, 4); Serial.print(';');
  Serial.print(v_end, 4); Serial.print(';');
  Serial.print(motionTime_s, 3); Serial.print(';');
  Serial.print(motionSamples); Serial.print(';');
  Serial.print(Wfat_energy, 4); Serial.print(';');
  Serial.println(Wfat_mu, 4);
}
