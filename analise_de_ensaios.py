import os
import sys
import math
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

LEGENDAS = {
    'Variável': [
        'massa_g', 'LBC', 'LBT', 'repeticao',
        'angulo_deg', 'altura_m',
        'mu_s', 'mu_d',
        'aceleracao_mps2', 'velocidade_mps', 'tempo_s',
        't_inicio_ms', 't_fim_ms',
        'trabalho_energia_J', 'trabalho_atrito_J',
        'mpu_ok', 'mpu_ok_no_escorregamento',
        'sonar_ok', 'sonar_stale_ms', 's_ok',
        'pitch_bruto_deg', 'pitch_filtrado_deg',
        'sonar_bruto_mm', 'sonar_filtrado_mm',
        'dist_ref_mm', 'dist_alvo_mm', 's_abs_mm',
        'temp_mpu_c', 'Timestamp_PC',
        'mu_s_media', 'mu_s_std', 'mu_s_count',
        'mu_d_media', 'mu_d_std', 'mu_d_count',
        'tempo_media', 'tempo_std',
        'distancia_media', 'angulo_media',
        'trabalho_energia_media', 'trabalho_energia_std',
        'trabalho_atrito_media', 'trabalho_atrito_std',
        'comparacao_trabalho_delta_J'
    ],
    'Descrição': [
        'Massa do conjunto deslizante (corpo de prova + pesos) em gramas.',
        'Lixa da Base do Corpo de prova (1=Fina/1200, 2=Média/600, 3=Grossa/280).',
        'Lixa da Base do Tribômetro (1=Fina/1200, 2=Média/600, 3=Grossa/280).',
        'Número sequencial da repetição do ensaio.',
        'Ângulo de inclinação da rampa medido pelo MPU6050 (graus).',
        'Altura vertical correspondente ao ângulo e comprimento da rampa (metros).',
        'Coeficiente de Atrito Estático calculado (adimensional).',
        'Coeficiente de Atrito Dinâmico calculado (adimensional).',
        'Aceleração média durante a descida (m/s²).',
        'Velocidade final atingida (m/s).',
        'Tempo total de descida (segundos).',
        'Timestamp (ms) do início do movimento detectado.',
        'Timestamp (ms) do fim do movimento detectado.',
        'Energia Potencial convertida (Joule).',
        'Trabalho realizado pela força de atrito (Joule).',
        'Flag (0/1): Dados do acelerômetro/giroscópio válidos durante todo o ensaio?',
        'Flag (0/1): Dados do MPU válidos no momento do disparo (para cálculo de mu_s)?',
        'Flag (0/1): Dados do Sonar válidos e consistentes?',
        'Tempo (ms) que o sonar ficou sem atualizar (stale). Deve ser 0.',
        'Flag (0/1): Deslocamento total foi consistente com o esperado?',
        'Leitura crua do ângulo de inclinação (sem filtro).',
        'Leitura do ângulo após filtro complementar/exponencial.',
        'Leitura crua de distância do sonar (mm).',
        'Leitura de distância filtrada (mediana) (mm).',
        'Distância de referência (Initial Point) medida antes do disparo.',
        'Distância alvo configurada para o ensaio.',
        'Deslocamento absoluto real percorrido durante o ensaio (mm).',
        'Temperatura interna do sensor MPU6050 (°C).',
        'Data e hora da coleta dos dados pelo computador.',
        'Média de mu_s para o grupo (LBT/LBC/massa).',
        'Desvio padrão de mu_s para o grupo (LBT/LBC/massa).',
        'Quantidade de amostras válidas de mu_s no grupo.',
        'Média de mu_d para o grupo (LBT/LBC/massa).',
        'Desvio padrão de mu_d para o grupo (LBT/LBC/massa).',
        'Quantidade de amostras válidas de mu_d no grupo.',
        'Média do tempo de descida para o grupo (s).',
        'Desvio padrão do tempo de descida para o grupo (s).',
        'Média do deslocamento absoluto para o grupo (mm).',
        'Média do ângulo de inclinação para o grupo (graus).',
        'Média da perda de energia (J) para o grupo.',
        'Desvio padrão da perda de energia (J) para o grupo.',
        'Média do trabalho da força de atrito (J) para o grupo.',
        'Desvio padrão do trabalho da força de atrito (J) para o grupo.',
        'Comparação (delta) entre trabalho de atrito e perda de energia (J).'
    ]
}


def adicionar_legenda_excel(writer):
    df_legenda = pd.DataFrame(LEGENDAS)
    df_legenda.to_excel(writer, sheet_name='legenda', index=False)


def ajustar_largura_colunas(writer, sheet_name, df, padding=2, max_width=50):
    try:
        from openpyxl.utils import get_column_letter
    except Exception:
        return
    worksheet = writer.sheets.get(sheet_name)
    if worksheet is None:
        return
    for idx, coluna in enumerate(df.columns, start=1):
        valores = df[coluna].astype(str).tolist()
        max_len = max([len(str(coluna))] + [len(v) for v in valores]) if valores else len(str(coluna))
        largura = min(max_len + padding, max_width)
        worksheet.column_dimensions[get_column_letter(idx)].width = largura


def plotar_grafico_atrito(massa_g, angulo_deg, mu_s, mu_d, titulo, titulo_extra, caminho_saida):
    if massa_g is None or angulo_deg is None:
        return False

    mu_s_val = None if pd.isna(mu_s) else mu_s
    mu_d_val = None if pd.isna(mu_d) else mu_d
    if mu_s_val is None and mu_d_val is None:
        return False

    gravidade = 9.80665
    angulo_rad = math.radians(angulo_deg)
    massa_kg = massa_g / 1000.0
    forca_normal = massa_kg * gravidade * math.cos(angulo_rad)
    forca_atrito_estatico_max = mu_s_val * forca_normal if mu_s_val is not None else None
    forca_atrito_dinamico = mu_d_val * forca_normal if mu_d_val is not None else None

    if forca_atrito_estatico_max is None:
        forca_atrito_estatico_max = forca_atrito_dinamico
    if forca_atrito_dinamico is None:
        forca_atrito_dinamico = forca_atrito_estatico_max
    if forca_atrito_estatico_max is None or forca_atrito_dinamico is None:
        return False

    forca_fim = max(forca_atrito_estatico_max, forca_atrito_dinamico) * 1.6
    if forca_fim <= 0:
        return False

    x_estatico = [0.0, forca_atrito_estatico_max]
    y_estatico = [0.0, forca_atrito_estatico_max]
    x_dinamico = [forca_atrito_estatico_max, forca_fim]
    y_dinamico = [forca_atrito_dinamico, forca_atrito_dinamico]

    with plt.rc_context({
        "font.size": 11,
        "axes.titlesize": 14,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
    }):
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
        plt.title(f"{titulo}\n{titulo_extra}")
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

        plt.savefig(caminho_saida, dpi=200)
        plt.close()
    return True


def executar_analise(caminho_csv='resultados_tribometro.csv'):
    print("Iniciando análise de dados do Tribômetro...")

    dir_saida = "saida_analise"
    dir_graficos = os.path.join(dir_saida, "graficos")
    dir_graficos_resumo = os.path.join(dir_graficos, "resumo")
    os.makedirs(dir_graficos_resumo, exist_ok=True)

    if not os.path.isfile(caminho_csv):
        print(f"Arquivo não encontrado: {caminho_csv}")
        return 1

    try:
        df_raw = pd.read_csv(caminho_csv, sep=';', decimal='.')
        print(f"Dados carregados: {len(df_raw)} linhas.")
    except Exception as e:
        print(f"Erro ao ler o arquivo CSV: {e}")
        return 1

    criterios_validade = (
        (df_raw['mpu_ok'] == 1) &
        (df_raw['sonar_ok'] == 1) &
        (df_raw['s_ok'] == 1) &
        (df_raw['sonar_stale_ms'] == 0)
    )

    df_limpos = df_raw[criterios_validade].copy()

    cols_criticas = ['massa_g', 'LBC', 'LBT', 'mu_d', 'tempo_s']
    df_limpos.dropna(subset=cols_criticas, inplace=True)

    print(f"Dados limpos: {len(df_limpos)} linhas válidas (de {len(df_raw)} originais).")

    df_limpos['mu_s_final'] = df_limpos.apply(
        lambda row: row['mu_s'] if row['mpu_ok_no_escorregamento'] == 1 else None,
        axis=1
    )

    df_limpos['mu_d_final'] = df_limpos['mu_d']

    group_cols = ['LBT', 'LBC', 'massa_g']
    resumo = df_limpos.groupby(group_cols).agg(
        mu_s_media=('mu_s_final', 'mean'),
        mu_s_std=('mu_s_final', 'std'),
        mu_s_count=('mu_s_final', 'count'),
        mu_d_media=('mu_d_final', 'mean'),
        mu_d_std=('mu_d_final', 'std'),
        mu_d_count=('mu_d_final', 'count'),
        tempo_media=('tempo_s', 'mean'),
        tempo_std=('tempo_s', 'std'),
        distancia_media=('s_abs_mm', 'mean'),
        angulo_media=('angulo_deg', 'mean'),
        trabalho_energia_media=('trabalho_energia_J', 'mean'),
        trabalho_energia_std=('trabalho_energia_J', 'std'),
        trabalho_atrito_media=('trabalho_atrito_J', 'mean'),
        trabalho_atrito_std=('trabalho_atrito_J', 'std'),
    ).reset_index()

    resumo['comparacao_trabalho_delta_J'] = (
        resumo['trabalho_atrito_media'] - resumo['trabalho_energia_media']
    )
    resumo = resumo.round(4)

    output_excel = os.path.join(dir_saida, 'analise_tribometro.xlsx')
    try:
        with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
            resumo.to_excel(writer, sheet_name='resumo', index=False)
            df_raw.to_excel(writer, sheet_name='dados_raw', index=False)
            df_limpos.to_excel(writer, sheet_name='dados_limpos', index=False)
            adicionar_legenda_excel(writer)
            ajustar_largura_colunas(writer, 'resumo', resumo)
            ajustar_largura_colunas(writer, 'dados_raw', df_raw)
            ajustar_largura_colunas(writer, 'dados_limpos', df_limpos)
            df_legenda = pd.DataFrame(LEGENDAS)
            ajustar_largura_colunas(writer, 'legenda', df_legenda, max_width=80)
        print(f"Arquivo Excel gerado com sucesso: {output_excel}")
    except ImportError:
        print("Biblioteca 'openpyxl' não encontrada. Salvando resumo em CSV.")
        resumo.to_csv(os.path.join(dir_saida, 'analise_resumo.csv'), sep=';', decimal=',', index=False)
        df_limpos.to_csv(os.path.join(dir_saida, 'analise_dados_limpos.csv'), sep=';', decimal=',', index=False)

    sns.set_theme(style="whitegrid", context="talk")

    plt.figure(figsize=(10, 6))
    df_plot_mus = df_limpos.dropna(subset=['mu_s_final'])
    sns.barplot(
        data=df_plot_mus,
        x='LBT',
        y='mu_s_final',
        hue='massa_g',
        palette="viridis",
        estimator='mean',
        errorbar='sd',
        capsize=0.2,
    )
    plt.title('Atrito Estático (mu_s) por Lixa da Base')
    plt.ylabel('Coeficiente de Atrito Estático (mu_s)')
    plt.xlabel('Lixa Base (LBT)')
    plt.legend(title='Massa (g)', bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0)
    plt.tight_layout()
    plt.savefig(os.path.join(dir_graficos, 'grafico_01_media_mu_s.png'), dpi=300)
    plt.close()

    plt.figure(figsize=(10, 6))
    sns.barplot(
        data=df_limpos,
        x='LBT',
        y='mu_d_final',
        hue='massa_g',
        palette="viridis",
        estimator='mean',
        errorbar='sd',
        capsize=0.2,
    )
    plt.title('Atrito Dinâmico (mu_d) por Lixa da Base')
    plt.ylabel('Coeficiente de Atrito Dinâmico (mu_d)')
    plt.xlabel('Lixa Base (LBT)')
    plt.legend(title='Massa (g)', bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0)
    plt.tight_layout()
    plt.savefig(os.path.join(dir_graficos, 'grafico_02_media_mu_d.png'), dpi=300)
    plt.close()

    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df_limpos, x='massa_g', y='mu_d_final', hue='LBT', style='LBC', s=150, palette="deep")
    plt.title('Dispersão: mu_d vs Massa')
    plt.ylabel('Coeficiente de Atrito Dinâmico (mu_d)')
    plt.xlabel('Massa (g)')
    plt.legend(title='LBT / LBC', bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0)
    plt.tight_layout()
    plt.savefig(os.path.join(dir_graficos, 'grafico_03_scatter_mu_d_massa.png'), dpi=300)
    plt.close()

    plt.figure(figsize=(10, 6))
    df_trabalho = df_limpos.dropna(subset=['trabalho_energia_J', 'trabalho_atrito_J']).copy()
    df_trabalho['delta_trabalho_J'] = df_trabalho['trabalho_atrito_J'] - df_trabalho['trabalho_energia_J']
    sns.scatterplot(
        data=df_trabalho,
        x='massa_g',
        y='delta_trabalho_J',
        hue='LBT',
        style='LBC',
        s=150,
        palette="deep",
    )
    plt.axhline(0.0, linestyle='--', color='#555555', linewidth=1)
    plt.title('Delta: Trabalho de Atrito − Perda de Energia')
    plt.xlabel('Massa (g)')
    plt.ylabel('Delta de trabalho (J)')
    plt.legend(title='LBT / LBC', bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0)
    plt.tight_layout()
    plt.savefig(os.path.join(dir_graficos, 'grafico_04_delta_trabalho.png'), dpi=300)
    plt.close()

    for massa_val in sorted(resumo['massa_g'].unique()):
        df_massa = resumo[resumo['massa_g'] == massa_val]
        if df_massa.empty:
            continue
        tabela = df_massa.pivot(index='LBT', columns='LBC', values='comparacao_trabalho_delta_J')
        if tabela.empty:
            continue
        plt.figure(figsize=(10, 6))
        sns.heatmap(
            tabela,
            annot=True,
            fmt=".3f",
            cmap="vlag",
            center=0.0,
            linewidths=0.4,
            linecolor="#e6e6e6",
            cbar_kws={"label": "Delta trabalho (J)"},
        )
        plt.title(f'Delta trabalho (atr - energia) | m={massa_val:.1f} g')
        plt.xlabel('LBC')
        plt.ylabel('LBT')
        plt.tight_layout()
        massa_tag = f"{massa_val:.1f}".replace('.', 'p')
        plt.savefig(os.path.join(dir_graficos, f"grafico_05_heatmap_delta_m{massa_tag}.png"), dpi=300)
        plt.close()

    print(f"Gráficos salvos em: {dir_graficos}")

    for _, linha in resumo.iterrows():
        lbt_val = linha['LBT']
        lbc_val = linha['LBC']
        massa_val = linha['massa_g']
        mu_s_media = linha['mu_s_media']
        mu_d_media = linha['mu_d_media']
        angulo_media = linha['angulo_media']

        titulo = "Atrito estático e dinâmico do ensaio"
        titulo_extra = f"LBC={lbc_val} | LBT={lbt_val} | m={massa_val:.1f} g"
        massa_tag = f"{massa_val:.1f}".replace('.', 'p')
        caminho_saida = os.path.join(
            dir_graficos_resumo,
            f"grafico_atrito_medio_LBC{lbc_val}_LBT{lbt_val}_m{massa_tag}.png"
        )

        plotar_grafico_atrito(
            massa_val,
            angulo_media,
            mu_s_media,
            mu_d_media,
            titulo,
            titulo_extra,
            caminho_saida
        )

    print(f"Gráficos médios de atrito gerados em: {dir_graficos_resumo}")
    return 0


if __name__ == "__main__":
    caminho = sys.argv[1] if len(sys.argv) > 1 else 'resultados_tribometro.csv'
    sys.exit(executar_analise(caminho))
