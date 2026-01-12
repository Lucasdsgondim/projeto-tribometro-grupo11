extern bool sonarOk;
extern bool sonarStale;
extern unsigned long sonarAgeMs;
extern long lastSonarRawMm;
extern long distNowMm;
extern long distInitialMm;
extern long distFinalMm;
extern long dist0mm;
extern long motionStartSmm;
extern unsigned long motionStartMs;
extern unsigned long motionEndMs;
extern long distEndMm;
long displacementRefMm();
long displacementMmToward(long dRef, long dNow);
extern const float TARGET_OFFSET_MM;

void printCSVHeader() {
  Serial.println(F("massa_g;LBC;LBT;angulo_deg;altura_m;mu_s;mu_d;aceleracao_mps2;velocidade_mps;tempo_s;t_inicio_ms;t_fim_ms;amostras_validas;trabalho_energia_J;trabalho_atrito_J;mpu_ok;mpu_ok_no_escorregamento;sonar_ok;sonar_stale_ms;filtro_alpha;pitch_bruto_deg;pitch_filtrado_deg;pitch_zero_deg;sonar_bruto_mm;sonar_filtrado_mm;dist0_mm;dist_ref_mm;dist_alvo_mm;offset_mm;s_abs_mm;s_rel_mm;dist_fim_mm;s_ok;calib_pitch_std_deg;calib_dist_std_mm;calib_pitch_n;calib_dist_n;temp_mpu_c"));
}

void finishAndPrintResults() {
  bool sonarFresh = sonarOk && !sonarStale;
  bool mpuValid = mpuOk;
  long dUse = sonarFresh ? distNowMm : -1;
  long refMm = displacementRefMm();
  long s_mm = (dUse >= 0) ? displacementMmToward(refMm, dUse) : 0;
  long s_rel_mm = (dUse >= 0) ? (s_mm - motionStartSmm) : 0;
  if (s_rel_mm < 0) s_rel_mm = 0;
  if (dUse < 0) d_meas_m = NAN;
  else d_meas_m = s_mm / 1000.0f;

  if (motionEndMs >= motionStartMs) motionTime_s = (motionEndMs - motionStartMs) / 1000.0f;
  else motionTime_s = 0.0f;
  unsigned long tStart = motionStartMs;
  unsigned long tEnd = motionEndMs;
  if (dUse < 0 || motionSamples < MIN_MOTION_SAMPLES) {
    a_est = NAN;
  } else if (sum_t4 > 1e-9) {
    a_est = (float)(2.0 * sum_t2s / sum_t4);
  } else if (motionTime_s > 0.05f && d_meas_m > 0.0f) {
    a_est = (2.0f * d_meas_m) / (motionTime_s * motionTime_s);
  } else {
    a_est = 0.0f;
  }

  float thetaRad = thetaDynDeg * PI / 180.0f;
  if (dUse < 0) {
    v_end = NAN;
    mu_d = NAN;
    dH_m = NAN;
    Wfat_energy = NAN;
    Wfat_mu = NAN;
  } else {
    v_end = sqrtf(fmaxf(0.0f, 2.0f * a_est * d_meas_m));
    float den = (G * cosf(thetaRad));
    mu_d = (fabsf(den) > 1e-9f) ? ((G * sinf(thetaRad) - a_est) / den) : 0.0f;
    dH_m = d_meas_m * sinf(thetaRad);
    float m_kg = mass_g / 1000.0f;
    Wfat_energy = 0.5f * m_kg * v_end * v_end - m_kg * G * dH_m;
    Wfat_mu     = mu_d * m_kg * G * cosf(thetaRad) * d_meas_m;
  }
  if (!mpuValid || !mpuOkAtSlip) {
    mu_s = NAN;
  }
  if (!mpuValid) {
    mu_d = NAN;
  }
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
  Serial.print(tStart); Serial.print(';');
  Serial.print(tEnd); Serial.print(';');
  Serial.print(motionSamples); Serial.print(';');
  Serial.print(Wfat_energy, 4); Serial.print(';');
  Serial.print(Wfat_mu, 4); Serial.print(';');
  Serial.print(mpuOk ? 1 : 0); Serial.print(';');
  Serial.print(mpuOkAtSlip ? 1 : 0); Serial.print(';');
  Serial.print(sonarOk ? 1 : 0); Serial.print(';');
  Serial.print(sonarAgeMs); Serial.print(';');
  Serial.print(filterAlpha, 3); Serial.print(';');
  Serial.print(pitchRawDeg, 3); Serial.print(';');
  Serial.print(pitchFiltDeg, 3); Serial.print(';');
  Serial.print(pitchZeroDeg, 3); Serial.print(';');
  Serial.print(lastSonarRawMm); Serial.print(';');
  Serial.print(distNowMm); Serial.print(';');
  Serial.print(dist0mm); Serial.print(';');
  Serial.print(refMm); Serial.print(';');
  Serial.print(d_target_mm, 0); Serial.print(';');
  Serial.print(TARGET_OFFSET_MM, 1); Serial.print(';');
  Serial.print(s_mm); Serial.print(';');
  Serial.print(s_rel_mm); Serial.print(';');
  Serial.print(distEndMm); Serial.print(';');
  long s_ok_ref = s_mm;
  int s_ok = (dUse >= 0) ? ((labs((long)d_target_mm - s_ok_ref) <= 20) ? 1 : 0) : 0;
  Serial.print(s_ok); Serial.print(';');
  Serial.print(calibPitchStdDeg, 3); Serial.print(';');
  Serial.print(calibDistStdMm, 1); Serial.print(';');
  Serial.print(calibPitchSamples); Serial.print(';');
  Serial.print(calibDistSamples); Serial.print(';');
  Serial.println(mpuTempC, 2);
}
