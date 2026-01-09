import serial
import serial.tools.list_ports
import time
import csv
import threading
import os
import tempfile
from datetime import datetime
import math
import sys
import io
import locale
import atexit
import analise_de_ensaios

# ================= CONFIGURAÇÕES =================
TAXA_BAUD = 115200
NOME_ARQUIVO = "resultados_tribometro.csv"
DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CAMINHO_SAIDA_PADRAO = os.path.join(DIR_SCRIPT, NOME_ARQUIVO)
CAMINHO_SAIDA_TEMP = os.path.join(tempfile.gettempdir(), NOME_ARQUIVO)
CAMINHO_LOG = os.path.join(DIR_SCRIPT, "interface_tribometro.log")
DIR_GRAFICOS_ENSAIO = os.path.join(DIR_SCRIPT, "graficos_ensaio")
ARQUIVO_GRAFICO_PADRAO = os.path.join(DIR_GRAFICOS_ENSAIO, "grafico_ensaio_atual.png")
CAMINHO_HISTORICO = os.path.join(DIR_SCRIPT, ".interface_tribometro_history")
MAX_ARQUIVOS_ALT = 5
ARQUIVO_ATIVO = None
CABECALHO_ATUAL = None
LIMITE_CALIB_PITCH_STD = 0.5
LIMITE_CALIB_DIST_STD = 20.0
# =================================================

def configurar_terminal_utf8():
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    if os.name == "nt":
        try:
            os.system("chcp 65001 > nul")
        except Exception:
            pass
    try:
        locale.setlocale(locale.LC_ALL, "")
    except Exception:
        try:
            locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")
        except Exception:
            pass
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
        except Exception:
            pass

def configurar_readline():
    try:
        import readline
    except Exception:
        return
    try:
        readline.parse_and_bind("set editing-mode emacs")
        readline.set_history_length(200)
        if os.path.isfile(CAMINHO_HISTORICO):
            readline.read_history_file(CAMINHO_HISTORICO)
        atexit.register(readline.write_history_file, CAMINHO_HISTORICO)
    except Exception:
        pass

def listar_portas_seriais():
    portas = serial.tools.list_ports.comports()
    return [porta.device for porta in portas]

def registrar_erro(mensagem):
    try:
        with open(CAMINHO_LOG, 'a', encoding='utf-8') as arquivo:
            arquivo.write(mensagem + "\n")
    except Exception:
        pass

def montar_candidatos_saida():
    base_padrao, ext_padrao = os.path.splitext(CAMINHO_SAIDA_PADRAO)
    base_temp, ext_temp = os.path.splitext(CAMINHO_SAIDA_TEMP)
    candidatos = []
    if ARQUIVO_ATIVO:
        candidatos.append(ARQUIVO_ATIVO)
    candidatos.append(CAMINHO_SAIDA_PADRAO)
    for indice in range(1, MAX_ARQUIVOS_ALT + 1):
        candidatos.append(f"{base_padrao}_{indice}{ext_padrao}")
    candidatos.append(CAMINHO_SAIDA_TEMP)
    for indice in range(1, MAX_ARQUIVOS_ALT + 1):
        candidatos.append(f"{base_temp}_{indice}{ext_temp}")
    vistos = set()
    unicos = []
    for caminho in candidatos:
        if caminho in vistos:
            continue
        vistos.add(caminho)
        unicos.append(caminho)
    return unicos

def selecionar_arquivo_saida_mais_recente():
    candidatos = montar_candidatos_saida()
    melhor_caminho = None
    melhor_mtime = None
    for caminho in candidatos:
        if not caminho or not os.path.isfile(caminho):
            continue
        if os.path.getsize(caminho) <= 0:
            continue
        tempo_modificacao = os.path.getmtime(caminho)
        if melhor_mtime is None or tempo_modificacao > melhor_mtime:
            melhor_mtime = tempo_modificacao
            melhor_caminho = caminho
    return melhor_caminho

def converter_float(valor):
    if valor is None:
        return None
    try:
        numero = float(valor)
    except ValueError:
        return None
    if math.isnan(numero) or math.isinf(numero):
        return None
    return numero

def ler_resultado_do_fim(caminho, deslocamento):
    cabecalho = None
    linhas_dados = []
    with open(caminho, 'r', newline='', encoding='utf-8-sig') as arquivo:
        leitor = csv.reader(arquivo, delimiter=';')
        for linha in leitor:
            if not linha:
                continue
            linha_minuscula = [c.strip().lower() for c in linha]
            if "massa_g" in linha_minuscula and "lbc" in linha_minuscula:
                cabecalho = [c.strip() for c in linha]
                continue
            if cabecalho is None:
                continue
            if len(linha) >= len(cabecalho) - 1:
                linhas_dados.append([c.strip() for c in linha])
    if cabecalho is None or not linhas_dados:
        return None
    if deslocamento < 0 or deslocamento >= len(linhas_dados):
        return None
    linha_escolhida = linhas_dados[-1 - deslocamento]
    indice = {nome: i for i, nome in enumerate(cabecalho)}
    def obter(nome):
        i = indice.get(nome)
        if i is None or i >= len(linha_escolhida):
            return None
        return linha_escolhida[i]
    return {
        "massa_g": obter("massa_g"),
        "LBC": obter("LBC"),
        "LBT": obter("LBT"),
        "angulo_deg": obter("angulo_deg"),
        "mu_s": obter("mu_s"),
        "mu_d": obter("mu_d"),
        "carimbo_tempo_pc": obter("Timestamp_PC"),
    }

def gerar_grafico_ensaio(deslocamento=0):
    try:
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"[ERRO] Matplotlib indisponível: {e}")
        return

    caminho = selecionar_arquivo_saida_mais_recente()
    if not caminho:
        print("[ERRO] Nenhum arquivo de resultados encontrado.")
        return

    dados = ler_resultado_do_fim(caminho, deslocamento)
    if not dados:
        print(f"[ERRO] Não existe ensaio para g {deslocamento} em '{caminho}'.")
        return

    massa_g = converter_float(dados.get("massa_g"))
    angulo_deg = converter_float(dados.get("angulo_deg"))
    mu_s = converter_float(dados.get("mu_s"))
    mu_d = converter_float(dados.get("mu_d"))

    if massa_g is None or angulo_deg is None:
        print("[ERRO] Dados insuficientes para plotar (massa_g/angulo_deg ausentes).")
        return

    if mu_s is None and mu_d is None:
        print("[ERRO] mu_s e mu_d inválidos no último ensaio.")
        return

    gravidade = 9.80665
    angulo_rad = math.radians(angulo_deg)
    massa_kg = massa_g / 1000.0
    forca_normal = massa_kg * gravidade * math.cos(angulo_rad)
    forca_atrito_estatico_max = mu_s * forca_normal if mu_s is not None else None
    forca_atrito_dinamico = mu_d * forca_normal if mu_d is not None else None

    if forca_atrito_estatico_max is None:
        forca_atrito_estatico_max = forca_atrito_dinamico
    if forca_atrito_dinamico is None:
        forca_atrito_dinamico = forca_atrito_estatico_max
    if forca_atrito_estatico_max is None or forca_atrito_dinamico is None:
        print("[ERRO] Não foi possível calcular forças de atrito.")
        return

    forca_fim = max(forca_atrito_estatico_max, forca_atrito_dinamico) * 1.6
    if forca_fim <= 0:
        print("[ERRO] Forças inválidas para plotagem.")
        return

    x_estatico = [0.0, forca_atrito_estatico_max]
    y_estatico = [0.0, forca_atrito_estatico_max]
    x_dinamico = [forca_atrito_estatico_max, forca_fim]
    y_dinamico = [forca_atrito_dinamico, forca_atrito_dinamico]

    plt.figure(figsize=(8, 4.6))
    eixos = plt.gca()
    plt.plot(x_estatico, y_estatico, color="#c0392b", linewidth=3)
    plt.plot([forca_atrito_estatico_max, forca_atrito_estatico_max], [forca_atrito_estatico_max, forca_atrito_dinamico], color="#c0392b", linewidth=3)
    plt.plot(x_dinamico, y_dinamico, color="#c0392b", linewidth=3)
    plt.axvline(forca_atrito_estatico_max, color="#555555", linestyle="--", linewidth=1)
    plt.axhline(forca_atrito_estatico_max, color="#888888", linestyle="--", linewidth=1)
    plt.axhline(forca_atrito_dinamico, color="#888888", linestyle="--", linewidth=1)
    plt.text(forca_atrito_estatico_max * 1.08, forca_atrito_dinamico * 1.03, "Movimento", fontsize=11)
    y_max = max(forca_atrito_estatico_max, forca_atrito_dinamico) * 1.15
    x_rotulo = forca_fim * 0.02
    deslocamento_y = y_max * 0.02
    delta_forcas = abs(forca_atrito_estatico_max - forca_atrito_dinamico)
    min_gap = y_max * 0.06
    ajuste = max(0.0, (min_gap - delta_forcas) / 2.0)
    y_estatico = forca_atrito_estatico_max + ajuste
    y_dinamico = forca_atrito_dinamico - ajuste
    bbox = dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.85)
    plt.text(
        x_rotulo,
        y_estatico,
        f"Fat estático — {forca_atrito_estatico_max:.3f} N",
        fontsize=10,
        va="center",
        ha="left",
        bbox=bbox,
    )
    plt.text(
        x_rotulo,
        y_dinamico,
        f"Fat dinâmico — {forca_atrito_dinamico:.3f} N",
        fontsize=10,
        va="center",
        ha="left",
        bbox=bbox,
    )
    plt.xlabel("Força aplicada (N)")
    plt.ylabel("Força de atrito (N)")
    lbc_valor = dados.get("LBC")
    lbt_valor = dados.get("LBT")
    massa_str = f"{massa_g:.1f} g" if massa_g is not None else "?"
    titulo_extra = f"LBC={lbc_valor} | LBT={lbt_valor} | m={massa_str}"
    plt.title(f"Atrito estático e dinâmico do ensaio\n{titulo_extra}")
    plt.xlim(0, forca_fim * 1.05)
    plt.ylim(0, y_max)
    plt.tight_layout()
    figura = plt.gcf()
    figura.canvas.draw()
    ponto1 = eixos.transData.transform((0.0, 0.0))
    ponto2 = eixos.transData.transform((forca_atrito_estatico_max, forca_atrito_estatico_max))
    angulo_rampa = math.degrees(math.atan2(ponto2[1] - ponto1[1], ponto2[0] - ponto1[0]))
    plt.text(
        forca_atrito_estatico_max * 0.55,
        forca_atrito_estatico_max * 0.6,
        "Repouso",
        rotation=angulo_rampa,
        rotation_mode="anchor",
        ha="center",
        va="center",
        fontsize=11,
    )
    carimbo_tempo_pc = dados.get("carimbo_tempo_pc")
    os.makedirs(DIR_GRAFICOS_ENSAIO, exist_ok=True)
    if carimbo_tempo_pc:
        carimbo_tempo_seguro = (
            carimbo_tempo_pc.replace(":", "-")
            .replace("/", "-")
            .replace("\\", "-")
            .replace(" ", "_")
        )
        caminho_saida = os.path.join(DIR_GRAFICOS_ENSAIO, f"grafico_ensaio_{carimbo_tempo_seguro}.png")
    else:
        caminho_saida = ARQUIVO_GRAFICO_PADRAO
    plt.savefig(caminho_saida, dpi=200)
    plt.close()
    print(f"[OK] Gráfico salvo em '{caminho_saida}'.")
    if carimbo_tempo_pc:
        print(f"[INFO] Ensaio g {deslocamento}: {carimbo_tempo_pc}")

def salvar_em_csv(linha_dados):
    """Recebe a string de dados separada por ; e salva no arquivo."""
    global ARQUIVO_ATIVO
    linha_dados = linha_dados.strip()
    if not linha_dados:
        return
    eh_cabecalho = "massa_g" in linha_dados and "LBC" in linha_dados
    candidatos = montar_candidatos_saida()

    tentados = set()
    avisou = False
    for arquivo_alvo in candidatos:
        if arquivo_alvo in tentados:
            continue
        tentados.add(arquivo_alvo)
        try:
            arquivo_existe = os.path.isfile(arquivo_alvo)
            arquivo_tem_dados = arquivo_existe and os.path.getsize(arquivo_alvo) > 0
            with open(arquivo_alvo, 'a', newline='', encoding='utf-8-sig') as arquivo:
                if eh_cabecalho and arquivo_tem_dados:
                    ARQUIVO_ATIVO = arquivo_alvo
                    return
                escritor = csv.writer(arquivo, delimiter=';')
                colunas = linha_dados.split(';')
                if not eh_cabecalho:
                    colunas.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                else:
                    colunas.append("Timestamp_PC")
                escritor.writerow(colunas)

            ARQUIVO_ATIVO = arquivo_alvo
            if not eh_cabecalho:
                print(f"\n[SUCESSO] Dados salvos em '{arquivo_alvo}'!")
            return
        except PermissionError as e:
            if not avisou:
                print(f"\n[AVISO] Arquivo '{arquivo_alvo}' está aberto ou bloqueado!")
                print("Tentando salvar em um arquivo alternativo...")
                registrar_erro(f"{datetime.now().isoformat()} PermissionError: {arquivo_alvo} ({e})")
                avisou = True
            continue
        except Exception as e:
            print(f"\n[ERRO] Falha ao salvar: {e}")
            registrar_erro(f"{datetime.now().isoformat()} Exception: {arquivo_alvo} ({e})")
            return

    if not eh_cabecalho:
        print("\n[FALHA CRÍTICA] Não foi possível salvar os dados após várias tentativas.")
        registrar_erro(f"{datetime.now().isoformat()} Falha critica. Tentativas: {', '.join(candidatos)}")

def decodificar_linha_serial(dados):
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        return dados.decode("latin-1", errors="replace")

def ler_da_serial(porta_serial, evento_parar):
    """Thread dedicada a ler do Arduino e imprimir na tela."""
    buffer_linha = bytearray()
    while not evento_parar.is_set():
        try:
            if porta_serial.in_waiting > 0:
                byte_lido = porta_serial.read()
                if byte_lido == b'\n':
                    linha = decodificar_linha_serial(buffer_linha).strip()
                    print(f"\r[Arduino]: {linha}")
                    print("> ", end="", flush=True) # Restaura o prompt
                    
                    # Verifica se parece ser uma linha de dados (tem muitos pontos e vírgula)
                    if linha.count(';') > 5:
                        salvar_em_csv(linha)
                        avisar_flags_qualidade(linha)
                    
                    buffer_linha.clear()
                else:
                    buffer_linha.extend(byte_lido)
        except Exception as e:
            print(f"\n[ERRO Serial]: {e}")
            evento_parar.set()
            break
        time.sleep(0.01)

def avisar_flags_qualidade(linha):
    global CABECALHO_ATUAL
    linha_minuscula = linha.lower()
    if "massa_g" in linha_minuscula and "lbc" in linha_minuscula:
        CABECALHO_ATUAL = [c.strip() for c in linha.split(';')]
        return
    if CABECALHO_ATUAL is None:
        if "nan" in linha_minuscula:
            print("[AVISO] Resultado contém NaN (medida inválida).")
        return
    colunas = [c.strip() for c in linha.split(';')]
    if len(colunas) != len(CABECALHO_ATUAL) and len(colunas) + 1 != len(CABECALHO_ATUAL):
        return
    indice = {nome: i for i, nome in enumerate(CABECALHO_ATUAL)}
    def obter(nome, default=None):
        i = indice.get(nome)
        if i is None or i >= len(colunas):
            return default
        return colunas[i]
    mpu_ok = obter("mpu_ok")
    mpu_ok_escorregamento = obter("mpu_ok_slip")
    sonar_ok = obter("sonar_ok")
    sonar_atraso_ms = obter("sonar_stale_ms")
    if mpu_ok == "0":
        print("[AVISO] MPU inválido nesta amostra (mpu_ok=0).")
    if mpu_ok_escorregamento == "0":
        print("[AVISO] Escorregamento detectado sem MPU válido (mpu_ok_slip=0).")
    if sonar_ok == "0":
        print("[AVISO] Sonar inválido nesta amostra (sonar_ok=0).")
    try:
        if sonar_atraso_ms is not None and int(float(sonar_atraso_ms)) > 0:
            print(f"[AVISO] Sonar stale: {sonar_atraso_ms} ms.")
    except ValueError:
        pass
    if "nan" in linha_minuscula:
        print("[AVISO] Resultado contém NaN (medida inválida).")
    sonar_filtrado = obter("sonar_filt_mm")
    dist0 = obter("dist0_mm")
    tempo_s = obter("tempo_s")
    s_ok = obter("s_ok")
    calib_pitch_std = obter("calib_pitch_std_deg")
    calib_dist_std = obter("calib_dist_std_mm")
    try:
        if sonar_filtrado is not None and dist0 is not None:
            delta = abs(float(sonar_filtrado) - float(dist0))
            tempo = float(tempo_s) if tempo_s is not None else None
            if delta > 50 and (tempo is None or tempo < 0.2):
                print(f"[AVISO] Divergência grande: sonar_filt_mm={sonar_filtrado} vs dist0_mm={dist0}.")
    except ValueError:
        pass
    if s_ok == "0":
        print("[AVISO] Percurso fora da tolerância (s_ok=0).")
    try:
        if calib_pitch_std is not None and float(calib_pitch_std) > LIMITE_CALIB_PITCH_STD:
            print(f"[AVISO] Calibração MPU instável (std={calib_pitch_std} deg).")
        if calib_dist_std is not None and float(calib_dist_std) > LIMITE_CALIB_DIST_STD:
            print(f"[AVISO] Calibração Sonar instável (std={calib_dist_std} mm).")
    except ValueError:
        pass

def principal():
    configurar_terminal_utf8()
    configurar_readline()
    print("=== Interface de Controle Tribometro ===")
    portas = listar_portas_seriais()
    
    porta_selecionada = None
    if not portas:
        print("Nenhuma porta COM encontrada! Conecte o Arduino.")
        return
    elif len(portas) == 1:
        porta_selecionada = portas[0]
        print(f"Conectando automaticamente em {porta_selecionada}...")
    else:
        print("Portas disponíveis:")
        for indice, porta in enumerate(portas):
            print(f"{indice}: {porta}")
        try:
            indice = int(input("Escolha o número da porta: "))
            porta_selecionada = portas[indice]
        except:
            print("Opção inválida.")
            return

    try:
        porta_serial = serial.Serial(porta_selecionada, TAXA_BAUD, timeout=1)
        time.sleep(2) # Aguarda reset do Arduino
        print("\n=== Conexão estabelecida ===")
        print(f"Porta: {porta_selecionada} | Baud rate: {TAXA_BAUD}")
        print("Comandos do Arduino: s (iniciar), z (nivelar), m <g> (massa), ip (posição inicial), fp (posição final), r (config), x (abortar).")
        print("Comandos locais: g (último ensaio) | g 1 (anterior) | g 2 (penúltimo), etc. | a (análise completa).")
        print(f"Saída padrão: {CAMINHO_SAIDA_PADRAO}")
        print("Digite 'sair' para encerrar.\n")

        evento_parar = threading.Event()
        thread_leitura = threading.Thread(target=ler_da_serial, args=(porta_serial, evento_parar))
        thread_leitura.daemon = True
        thread_leitura.start()

        while not evento_parar.is_set():
            comando = input("> ")
            if comando.lower() in ['sair', 'exit', 'quit']:
                evento_parar.set()
                break
            if comando.strip().lower().startswith('g'):
                partes = comando.strip().split()
                if len(partes) == 1:
                    deslocamento = 0
                else:
                    try:
                        deslocamento = int(partes[1])
                    except ValueError:
                        print("[ERRO] Use g ou g <numero> (ex: g 1).")
                        continue
                if deslocamento < 0:
                    print("[ERRO] Use um número >= 0 (ex: g 0, g 1).")
                    continue
                gerar_grafico_ensaio(deslocamento)
                continue
            if comando.strip().lower() == 'a':
                analise_de_ensaios.executar_analise(CAMINHO_SAIDA_PADRAO)
                continue
            
            # Envia para o Arduino
            porta_serial.write((comando + '\n').encode('utf-8'))
            time.sleep(0.1)

    except serial.SerialException as e:
        print(f"Erro ao abrir porta: {e}")
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        if 'porta_serial' in locals() and porta_serial.is_open:
            porta_serial.close()
        print("Desconectado.")

if __name__ == "__main__":
    principal()
