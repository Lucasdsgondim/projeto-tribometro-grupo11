float readMPUPitchDegSigned() {
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x3B); Wire.endTransmission(false);
  byte n = Wire.requestFrom(MPU_ADDR, (byte)6, (byte)true);
  if (n != 6) {
    mpuOk = false;
    return lastMpuPitchDeg;
  }
  int16_t mpuRawX = (int16_t)(Wire.read() << 8 | Wire.read());
  int16_t mpuRawY = (int16_t)(Wire.read() << 8 | Wire.read());
  int16_t mpuRawZ = (int16_t)(Wire.read() << 8 | Wire.read());
  if ((mpuRawX == 0 && mpuRawY == 0 && mpuRawZ == 0) ||
      (mpuRawX == -1 && mpuRawY == -1 && mpuRawZ == -1)) {
    mpuOk = false;
    return lastMpuPitchDeg;
  }
  mpuOk = true;
  float ay = mpuRawY / 16384.0f;
  float az = mpuRawZ / 16384.0f;
  float ang = atan2f(ay, az) * 180.0f / PI;
  lastMpuPitchDeg = -ang;
  return lastMpuPitchDeg;
}
