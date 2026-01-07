import serial
import serial.tools.list_ports
import time
import csv
import threading
import os
import tempfile
from datetime import datetime

# ================= CONFIGURAÇÕES =================
BAUD_RATE = 115200
FILENAME = "resultados_tribometro.csv"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_PATH = os.path.join(SCRIPT_DIR, FILENAME)
TEMP_OUTPUT_PATH = os.path.join(tempfile.gettempdir(), FILENAME)
LOG_PATH = os.path.join(SCRIPT_DIR, "interface_tribometro.log")
MAX_ALT_FILES = 5
ACTIVE_FILENAME = None
CURRENT_HEADER = None
CALIB_PITCH_STD_MAX = 0.5
CALIB_DIST_STD_MAX = 20.0
# =================================================

def list_serial_ports():
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def log_error(msg):
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(msg + "\n")
    except Exception:
        pass

def build_output_candidates():
    base_default, ext_default = os.path.splitext(DEFAULT_OUTPUT_PATH)
    base_temp, ext_temp = os.path.splitext(TEMP_OUTPUT_PATH)
    candidates = []
    if ACTIVE_FILENAME:
        candidates.append(ACTIVE_FILENAME)
    candidates.append(DEFAULT_OUTPUT_PATH)
    for i in range(1, MAX_ALT_FILES + 1):
        candidates.append(f"{base_default}_{i}{ext_default}")
    candidates.append(TEMP_OUTPUT_PATH)
    for i in range(1, MAX_ALT_FILES + 1):
        candidates.append(f"{base_temp}_{i}{ext_temp}")
    seen = set()
    unique = []
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        unique.append(c)
    return unique

def save_to_csv(data_line):
    """Recebe a string de dados separada por ; e salva no arquivo."""
    global ACTIVE_FILENAME
    data_line = data_line.strip()
    if not data_line:
        return
    is_header = "massa_g" in data_line and "LBC" in data_line
    candidates = build_output_candidates()

    tried = set()
    warned = False
    for target_filename in candidates:
        if target_filename in tried:
            continue
        tried.add(target_filename)
        try:
            file_exists = os.path.isfile(target_filename)
            file_has_data = file_exists and os.path.getsize(target_filename) > 0
            with open(target_filename, 'a', newline='', encoding='utf-8-sig') as f:
                if is_header and file_has_data:
                    ACTIVE_FILENAME = target_filename
                    return
                writer = csv.writer(f, delimiter=';')
                columns = data_line.split(';')
                if not is_header:
                    columns.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                else:
                    columns.append("Timestamp_PC")
                writer.writerow(columns)

            ACTIVE_FILENAME = target_filename
            if not is_header:
                print(f"\n[SUCESSO] Dados salvos em '{target_filename}'!")
            return
        except PermissionError as e:
            if not warned:
                print(f"\n[AVISO] Arquivo '{target_filename}' está aberto ou bloqueado!")
                print("Tentando salvar em um arquivo alternativo...")
                log_error(f"{datetime.now().isoformat()} PermissionError: {target_filename} ({e})")
                warned = True
            continue
        except Exception as e:
            print(f"\n[ERRO] Falha ao salvar: {e}")
            log_error(f"{datetime.now().isoformat()} Exception: {target_filename} ({e})")
            return

    if not is_header:
        print("\n[FALHA CRÍTICA] Não foi possível salvar os dados após várias tentativas.")
        log_error(f"{datetime.now().isoformat()} Falha critica. Tentativas: {', '.join(candidates)}")

def read_from_serial(ser, stop_event):
    """Thread dedicada a ler do Arduino e imprimir na tela."""
    buffer = ""
    while not stop_event.is_set():
        try:
            if ser.in_waiting > 0:
                char = ser.read().decode('utf-8', errors='ignore')
                if char == '\n':
                    line = buffer.strip()
                    print(f"\r[Arduino]: {line}")
                    print("> ", end="", flush=True) # Restaura o prompt
                    
                    # Verifica se parece ser uma linha de dados (tem muitos pontos e vírgula)
                    if line.count(';') > 5:
                        save_to_csv(line)
                        warn_quality_flags(line)
                    
                    buffer = ""
                else:
                    buffer += char
        except Exception as e:
            print(f"\n[ERRO Serial]: {e}")
            stop_event.set()
            break
        time.sleep(0.01)

def warn_quality_flags(line):
    global CURRENT_HEADER
    lower = line.lower()
    if "massa_g" in lower and "lbc" in lower:
        CURRENT_HEADER = [c.strip() for c in line.split(';')]
        return
    if CURRENT_HEADER is None:
        if "nan" in lower:
            print("[AVISO] Resultado contém NaN (medida inválida).")
        return
    cols = [c.strip() for c in line.split(';')]
    if len(cols) != len(CURRENT_HEADER) and len(cols) + 1 != len(CURRENT_HEADER):
        return
    idx = {name: i for i, name in enumerate(CURRENT_HEADER)}
    def get(name, default=None):
        i = idx.get(name)
        if i is None or i >= len(cols):
            return default
        return cols[i]
    mpu_ok = get("mpu_ok")
    mpu_ok_slip = get("mpu_ok_slip")
    sonar_ok = get("sonar_ok")
    sonar_stale = get("sonar_stale_ms")
    if mpu_ok == "0":
        print("[AVISO] MPU inválido nesta amostra (mpu_ok=0).")
    if mpu_ok_slip == "0":
        print("[AVISO] Escorregamento detectado sem MPU válido (mpu_ok_slip=0).")
    if sonar_ok == "0":
        print("[AVISO] Sonar inválido nesta amostra (sonar_ok=0).")
    try:
        if sonar_stale is not None and int(float(sonar_stale)) > 0:
            print(f"[AVISO] Sonar stale: {sonar_stale} ms.")
    except ValueError:
        pass
    if "nan" in lower:
        print("[AVISO] Resultado contém NaN (medida inválida).")
    sonar_filt = get("sonar_filt_mm")
    dist0 = get("dist0_mm")
    tempo_s = get("tempo_s")
    s_ok = get("s_ok")
    calib_pitch_std = get("calib_pitch_std_deg")
    calib_dist_std = get("calib_dist_std_mm")
    try:
        if sonar_filt is not None and dist0 is not None:
            delta = abs(float(sonar_filt) - float(dist0))
            t = float(tempo_s) if tempo_s is not None else None
            if delta > 50 and (t is None or t < 0.2):
                print(f"[AVISO] Divergência grande: sonar_filt_mm={sonar_filt} vs dist0_mm={dist0}.")
    except ValueError:
        pass
    if s_ok == "0":
        print("[AVISO] Percurso fora da tolerância (s_ok=0).")
    try:
        if calib_pitch_std is not None and float(calib_pitch_std) > CALIB_PITCH_STD_MAX:
            print(f"[AVISO] Calibração MPU instável (std={calib_pitch_std} deg).")
        if calib_dist_std is not None and float(calib_dist_std) > CALIB_DIST_STD_MAX:
            print(f"[AVISO] Calibração Sonar instável (std={calib_dist_std} mm).")
    except ValueError:
        pass

def main():
    print("=== Interface de Controle Tribometro ===")
    ports = list_serial_ports()
    
    selected_port = None
    if not ports:
        print("Nenhuma porta COM encontrada! Conecte o Arduino.")
        return
    elif len(ports) == 1:
        selected_port = ports[0]
        print(f"Conectando automaticamente em {selected_port}...")
    else:
        print("Portas disponíveis:")
        for i, p in enumerate(ports):
            print(f"{i}: {p}")
        try:
            idx = int(input("Escolha o número da porta: "))
            selected_port = ports[idx]
        except:
            print("Opção inválida.")
            return

    try:
        ser = serial.Serial(selected_port, BAUD_RATE, timeout=1)
        time.sleep(2) # Aguarda reset do Arduino
        print(f"\nConectado! Digite os comandos (s, z, m <g>, etc).")
        print(f"Os resultados serão salvos automaticamente em '{DEFAULT_OUTPUT_PATH}'.")
        print("Digite 'sair' para encerrar.\n")

        stop_event = threading.Event()
        t = threading.Thread(target=read_from_serial, args=(ser, stop_event))
        t.daemon = True
        t.start()

        while not stop_event.is_set():
            cmd = input("> ")
            if cmd.lower() in ['sair', 'exit', 'quit']:
                stop_event.set()
                break
            
            # Envia para o Arduino
            ser.write((cmd + '\n').encode('utf-8'))
            time.sleep(0.1)

    except serial.SerialException as e:
        print(f"Erro ao abrir porta: {e}")
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
        print("Desconectado.")

if __name__ == "__main__":
    main()
