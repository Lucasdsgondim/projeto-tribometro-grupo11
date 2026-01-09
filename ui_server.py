import os
import time
import math
import csv
import threading
from datetime import datetime
from pathlib import Path
import webbrowser

from flask import Flask, jsonify, request, send_from_directory
import serial
import serial.tools.list_ports

BAUD_RATE = 115200
SCRIPT_DIR = Path(__file__).resolve().parent
CSV_NOME = "resultados_tribometro.csv"
CAMINHO_CSV_PADRAO = SCRIPT_DIR / CSV_NOME
CAMINHO_LOG = SCRIPT_DIR / "interface_tribometro.log"
DIR_GRAFICOS_ENSAIO = SCRIPT_DIR / "graficos_ensaio"
DIR_SAIDA_ANALISE = SCRIPT_DIR / "saida_analise"
DIR_GRAFICOS_ANALISE = DIR_SAIDA_ANALISE / "graficos"
DIR_GRAFICOS_RESUMO = DIR_GRAFICOS_ANALISE / "resumo"

MAX_ALT_FILES = 5

app = Flask(__name__, static_folder="web", static_url_path="")


class GerenciadorSerial:
    def __init__(self):
        self.ser = None
        self._stop = threading.Event()
        self._thread = None
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._log = []
        self._log_idx = 0
        self._cabecalho_atual = None
        self._arquivo_ativo = None

    def conectado(self):
        return self.ser is not None and self.ser.is_open

    def conectar(self, porta):
        if self.conectado():
            return False, "Já conectado."
        try:
            self.ser = serial.Serial(porta, BAUD_RATE, timeout=1)
            time.sleep(2)
        except Exception as e:
            self.ser = None
            return False, f"Erro ao abrir porta: {e}"
        self._stop.clear()
        self._thread = threading.Thread(target=self._ler_serial, daemon=True)
        self._thread.start()
        return True, "Conectado."

    def desconectar(self):
        self._stop.set()
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def enviar(self, comando):
        if not self.conectado():
            return False, "Não conectado."
        try:
            self.ser.write((comando + "\n").encode("utf-8"))
            return True, "OK"
        except Exception as e:
            return False, f"Erro ao enviar: {e}"

    def _adicionar_log(self, linha):
        with self._lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self._log.append(f"[{ts}] {linha}")
            if len(self._log) > 1000:
                self._log = self._log[-800:]
            self._log_idx += 1

    def obter_log(self, desde=0):
        with self._lock:
            if desde < 0:
                desde = 0
            linhas = self._log[desde:]
            return linhas, len(self._log)

    def _decodificar(self, dados):
        try:
            return dados.decode("utf-8")
        except UnicodeDecodeError:
            return dados.decode("latin-1", errors="replace")

    def _montar_candidatos_saida(self):
        base_padrao = str(CAMINHO_CSV_PADRAO.with_suffix(""))
        ext_padrao = CAMINHO_CSV_PADRAO.suffix
        candidatos = []
        if self._arquivo_ativo:
            candidatos.append(self._arquivo_ativo)
        candidatos.append(str(CAMINHO_CSV_PADRAO))
        for i in range(1, MAX_ALT_FILES + 1):
            candidatos.append(f"{base_padrao}_{i}{ext_padrao}")
        vistos = set()
        unicos = []
        for caminho in candidatos:
            if caminho in vistos:
                continue
            vistos.add(caminho)
            unicos.append(caminho)
        return unicos

    def _salvar_em_csv(self, linha_dados):
        linha_dados = linha_dados.strip()
        if not linha_dados:
            return
        eh_cabecalho = "massa_g" in linha_dados and "LBC" in linha_dados
        candidatos = self._montar_candidatos_saida()
        for arquivo_alvo in candidatos:
            try:
                arquivo_existe = os.path.isfile(arquivo_alvo)
                arquivo_tem_dados = arquivo_existe and os.path.getsize(arquivo_alvo) > 0
                with open(arquivo_alvo, "a", newline="", encoding="utf-8-sig") as arquivo:
                    if eh_cabecalho and arquivo_tem_dados:
                        self._arquivo_ativo = arquivo_alvo
                        return
                    escritor = csv.writer(arquivo, delimiter=";")
                    colunas = linha_dados.split(";")
                    if not eh_cabecalho:
                        colunas.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    else:
                        colunas.append("Timestamp_PC")
                    escritor.writerow(colunas)
                self._arquivo_ativo = arquivo_alvo
                return
            except PermissionError as e:
                self._adicionar_log(f"[AVISO] Arquivo bloqueado: {arquivo_alvo} ({e})")
                continue
            except Exception as e:
                self._adicionar_log(f"[ERRO] Falha ao salvar: {e}")
                return

    def _ler_serial(self):
        while not self._stop.is_set():
            try:
                if self.ser and self.ser.in_waiting > 0:
                    byte_lido = self.ser.read()
                    if byte_lido == b"\n":
                        linha = self._decodificar(self._buffer).strip()
                        if linha:
                            self._adicionar_log(f"[Arduino] {linha}")
                            if linha.count(";") > 5:
                                self._salvar_em_csv(linha)
                        self._buffer.clear()
                    else:
                        self._buffer.extend(byte_lido)
            except Exception as e:
                self._adicionar_log(f"[ERRO Serial] {e}")
                self._stop.set()
                break
            time.sleep(0.01)


gerenciador = GerenciadorSerial()


def _ler_resultado_do_fim(caminho, deslocamento):
    cabecalho = None
    linhas_dados = []
    with open(caminho, "r", newline="", encoding="utf-8-sig") as arquivo:
        leitor = csv.reader(arquivo, delimiter=";")
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


def _converter_float(valor):
    if valor is None:
        return None
    try:
        numero = float(valor)
    except ValueError:
        return None
    if math.isnan(numero) or math.isinf(numero):
        return None
    return numero


def gerar_grafico_ensaio(deslocamento=0):
    try:
        import matplotlib.pyplot as plt
    except Exception as e:
        return False, f"Matplotlib indisponível: {e}"

    if not CAMINHO_CSV_PADRAO.is_file():
        return False, "CSV padrão não encontrado."

    dados = _ler_resultado_do_fim(str(CAMINHO_CSV_PADRAO), deslocamento)
    if not dados:
        return False, f"Não existe ensaio para g {deslocamento}."

    massa_g = _converter_float(dados.get("massa_g"))
    angulo_deg = _converter_float(dados.get("angulo_deg"))
    mu_s = _converter_float(dados.get("mu_s"))
    mu_d = _converter_float(dados.get("mu_d"))

    if massa_g is None or angulo_deg is None:
        return False, "Dados insuficientes para plotar (massa_g/angulo_deg ausentes)."

    if mu_s is None and mu_d is None:
        return False, "mu_s e mu_d inválidos no ensaio."

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
        return False, "Não foi possível calcular forças de atrito."

    forca_fim = max(forca_atrito_estatico_max, forca_atrito_dinamico) * 1.6
    if forca_fim <= 0:
        return False, "Forças inválidas para plotagem."

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

    y_max = max(forca_atrito_estatico_max, forca_atrito_dinamico) * 1.15
    x_rotulo = forca_fim * 0.02
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
    plt.text(forca_atrito_estatico_max * 1.08, forca_atrito_dinamico * 1.03, "Movimento", fontsize=11)

    DIR_GRAFICOS_ENSAIO.mkdir(parents=True, exist_ok=True)
    carimbo_tempo_pc = dados.get("carimbo_tempo_pc")
    if carimbo_tempo_pc:
        carimbo_tempo_seguro = (
            carimbo_tempo_pc.replace(":", "-")
            .replace("/", "-")
            .replace("\\", "-")
            .replace(" ", "_")
        )
        caminho_saida = DIR_GRAFICOS_ENSAIO / f"grafico_ensaio_{carimbo_tempo_seguro}.png"
    else:
        caminho_saida = DIR_GRAFICOS_ENSAIO / "grafico_ensaio_atual.png"

    plt.savefig(caminho_saida, dpi=200)
    plt.close()
    return True, str(caminho_saida)


def executar_analise():
    try:
        import analise_de_ensaios
    except Exception as e:
        return False, f"Erro ao importar análise: {e}"
    codigo = analise_de_ensaios.executar_analise(str(CAMINHO_CSV_PADRAO))
    if codigo != 0:
        return False, "Falha ao executar análise."
    return True, "Análise concluída."


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/ports")
def api_ports():
    portas = serial.tools.list_ports.comports()
    return jsonify([p.device for p in portas])


@app.get("/api/status")
def api_status():
    return jsonify({
        "conectado": gerenciador.conectado(),
    })


@app.post("/api/connect")
def api_connect():
    data = request.get_json(silent=True) or {}
    porta = data.get("porta")
    if not porta:
        return jsonify({"ok": False, "msg": "Porta não informada."}), 400
    ok, msg = gerenciador.conectar(porta)
    return jsonify({"ok": ok, "msg": msg})


@app.post("/api/disconnect")
def api_disconnect():
    gerenciador.desconectar()
    return jsonify({"ok": True})


@app.post("/api/send")
def api_send():
    data = request.get_json(silent=True) or {}
    comando = data.get("comando", "").strip()
    if not comando:
        return jsonify({"ok": False, "msg": "Comando vazio."}), 400
    ok, msg = gerenciador.enviar(comando)
    return jsonify({"ok": ok, "msg": msg})


@app.get("/api/log")
def api_log():
    desde = request.args.get("desde", "0")
    try:
        desde = int(desde)
    except ValueError:
        desde = 0
    linhas, proximo = gerenciador.obter_log(desde)
    return jsonify({"linhas": linhas, "proximo": proximo})


@app.post("/api/grafico")
def api_grafico():
    data = request.get_json(silent=True) or {}
    try:
        deslocamento = int(data.get("deslocamento", 0))
    except ValueError:
        return jsonify({"ok": False, "msg": "Deslocamento inválido."}), 400
    if deslocamento < 0:
        return jsonify({"ok": False, "msg": "Deslocamento deve ser >= 0."}), 400
    ok, msg = gerar_grafico_ensaio(deslocamento)
    return jsonify({"ok": ok, "msg": msg})


@app.post("/api/analise")
def api_analise():
    ok, msg = executar_analise()
    return jsonify({"ok": ok, "msg": msg})

@app.post("/api/shutdown")
def api_shutdown():
    func = request.environ.get("werkzeug.server.shutdown")
    gerenciador.desconectar()
    if func is not None:
        func()
        return jsonify({"ok": True, "msg": "Servidor encerrado."})
    def _force_exit():
        os._exit(0)
    threading.Timer(0.5, _force_exit).start()
    return jsonify({"ok": True, "msg": "Servidor encerrando..."})


@app.get("/api/graficos")
def api_graficos():
    def listar(dir_path):
        if not dir_path.exists():
            return []
        return sorted([p.name for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg")])

    return jsonify({
        "graficos_ensaio": listar(DIR_GRAFICOS_ENSAIO),
        "graficos_analise": listar(DIR_GRAFICOS_ANALISE),
        "graficos_resumo": listar(DIR_GRAFICOS_RESUMO),
    })


@app.get("/files/<path:subpath>")
def api_files(subpath):
    bases = [DIR_GRAFICOS_ENSAIO, DIR_GRAFICOS_ANALISE, DIR_GRAFICOS_RESUMO]
    for base in bases:
        candidato = (base / subpath).resolve()
        if base in candidato.parents and candidato.is_file():
            return send_from_directory(base, candidato.name)
    return ("Não encontrado", 404)


def main():
    porta = int(os.environ.get("TRIBO_UI_PORT", "8088"))
    url = f"http://127.0.0.1:{porta}"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    app.run(host="127.0.0.1", port=porta, debug=False)


if __name__ == "__main__":
    main()
