float readMPUPitchDegSigned() {
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x3B); Wire.endTransmission(false);
  byte n = Wire.requestFrom(MPU_ADDR, (byte)8, (byte)true);
  if (n != 8) {
    mpuOk = false;
    return lastMpuPitchDeg;
  }
  mpuRawX = (int16_t)(Wire.read() << 8 | Wire.read());
  mpuRawY = (int16_t)(Wire.read() << 8 | Wire.read());
  mpuRawZ = (int16_t)(Wire.read() << 8 | Wire.read());
  mpuRawTemp = (int16_t)(Wire.read() << 8 | Wire.read());
  if ((mpuRawX == 0 && mpuRawY == 0 && mpuRawZ == 0) ||
      (mpuRawX == -1 && mpuRawY == -1 && mpuRawZ == -1)) {
    mpuOk = false;
    return lastMpuPitchDeg;
  }
  mpuOk = true;
  float ay = mpuRawY / 16384.0f;
  float az = mpuRawZ / 16384.0f;
  float ang = atan2f(ay, az) * 180.0f / PI;
  mpuTempC = (mpuRawTemp / 340.0f) + 36.53f;
  lastMpuPitchDeg = -ang;
  return lastMpuPitchDeg;
}

byte readMPUWhoAmI() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x75); // WHO_AM_I
  if (Wire.endTransmission(false) != 0) return 0xFF;
  if (Wire.requestFrom(MPU_ADDR, (byte)1, (byte)true) != 1) return 0xFF;
  return Wire.read();
}

void scanI2CDevices() {
  byte count = 0;
  Serial.println(F("I2C scan:"));
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    byte err = Wire.endTransmission();
    if (err == 0) {
      Serial.print(F("  0x"));
      if (addr < 16) Serial.print('0');
      Serial.print(addr, HEX);
      Serial.println();
      count++;
    }
  }
  if (count == 0) Serial.println(F("  nenhum dispositivo encontrado"));
}
