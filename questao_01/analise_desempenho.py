"""
Questão 1 — medição de desempenho (tempo e memória) e otimização antes/depois.

Chamado por `main.py --modo completo` (que coloca as tabelas no relatório) e também
executável sozinho:  python questao_01/analise_desempenho.py

Produz três tabelas:
  desempenho   tempo e pico de memória por algoritmo e tamanho de entrada (pequena/média/grande)
  otimizacao   antes/depois (BF ingênuo x DFS; GA laço Python x vetorizado)
  gaps         gap do GA em relação ao ótimo do Brute Force para vários tamanhos de subconjunto
e o gráfico resultados/desempenho_q1.png.

Entradas "grandes" do GA e do Greedy (n=60, 120) são o catálogo replicado (SKUs
renomeados) — servem só para medir escalabilidade, não para a análise financeira.
"""
from __future__ import annotations

import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parent))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from comum.dados import carregar_parametros, carregar_questao
from comum.desempenho import medir
from brute_force import brute_force, brute_force_ingenuo, escolher_subconjunto, espaco_de_busca
from genetic_algorithm import ConfigGA, executar_ga
from greedy import alocar_incentivos
from modelo import construir_instancia


def catalogo_replicado(catalogo: pd.DataFrame, fator: int) -> pd.DataFrame:
    partes = []
    for r in range(fator):
        c = catalogo.copy()
        c["sku"] = c["sku"] + f"-r{r}"
        partes.append(c)
    return pd.concat(partes, ignore_index=True)


def medir_desempenho(catalogo, config, params, seed: int, saida: Path) -> dict:
    """Roda todas as medições; devolve {"desempenho", "otimizacao", "gaps"} (DataFrames)."""
    saida.mkdir(parents=True, exist_ok=True)
    p1 = params["questao_01"]
    inst = construir_instancia(catalogo, config, params)
    cfg_B = ConfigGA.de_dict(p1["ga_config_B"])
    cfg_B.penalidade_giro = p1["penalidade_giro_ga"]
    cfg_A = ConfigGA.de_dict(p1["ga_config_A"])
    cfg_A.penalidade_giro = p1["penalidade_giro_ga"]

    linhas, otim, gaps = [], [], []

    # ---------- Brute Force: pequena / média / grande + antes/depois ----------
    for k in (6, 8, 10, 12):
        sub = inst.subconjunto(escolher_subconjunto(inst, k))
        (s, v, nos), t, m = medir(brute_force, sub)
        linhas.append({"algoritmo": "Brute Force (DFS)", "n": k, "espaco": espaco_de_busca(sub),
                       "tempo_s": t, "memoria_KiB": m})
        if k <= 10:
            (s0, v0, aval), t0, m0 = medir(brute_force_ingenuo, sub)
            assert abs(v0 - v) < 1e-6, "versões do Brute Force discordam!"
            otim.append({"otimizacao": "Brute Force: itertools + recálculo  ->  DFS + tabela + poda",
                         "n": k, "antes_s": t0, "depois_s": t, "speedup": t0 / t,
                         "antes_mem_KiB": m0, "depois_mem_KiB": m, "mesmo_resultado": True})
        for nome, cfg in (("A", cfg_A), ("B", cfg_B)):
            res = executar_ga(sub, cfg, seed)
            gaps.append({"k": k, "espaco": espaco_de_busca(sub), "otimo_bf": v, "config": nome,
                         "ga": res.melhor_caixa, "gap_pct": (v - res.melhor_caixa) / v * 100,
                         "avaliacoes_ga": res.avaliacoes, "nos_bf": nos})

    # ---------- GA e Greedy: n = 10, 20, 30 (oficial) e 60, 120 (replicado) ----------
    for n in (10, 20, 30, 60, 120):
        if n <= 30:
            inst_n = inst.subconjunto(np.arange(n))
        else:
            inst_n = construir_instancia(catalogo_replicado(catalogo, n // 30), config, params)
        res, t, m = medir(executar_ga, inst_n, cfg_B, seed)
        linhas.append({"algoritmo": "Algoritmo Genético (cfg B)", "n": n, "espaco": None,
                       "tempo_s": t, "memoria_KiB": m, "geracoes": res.geracoes,
                       "tempo_por_geracao_ms": t / max(res.geracoes, 1) * 1000})
        g, t, m = medir(alocar_incentivos, inst_n, res.melhor_sol, p1["incentivo_passos"],
                        p1["incentivo_saliencia_beta"], p1["incentivo_roi_minimo"],
                        p1["incentivo_canibalizacao_alfa"], repeticoes_tempo=20)
        linhas.append({"algoritmo": "Greedy (heap)", "n": n, "espaco": None, "tempo_s": t, "memoria_KiB": m})

    # ---------- GA: avaliação em laço Python x vetorizada ----------
    for vet in (False, True):
        c = ConfigGA.de_dict(p1["ga_config_B"])
        c.penalidade_giro = p1["penalidade_giro_ga"]
        c.vetorizado = vet
        res, t, m = medir(executar_ga, inst, c, seed)
        if not vet:
            antes = (res, t, m)
    assert abs(antes[0].melhor_caixa - res.melhor_caixa) < 1e-6, "GA vetorizado mudou o resultado!"
    otim.append({"otimizacao": "GA: fitness em laço Python  ->  indexação vetorizada numpy",
                 "n": inst.n, "antes_s": antes[1], "depois_s": t, "speedup": antes[1] / t,
                 "antes_mem_KiB": antes[2], "depois_mem_KiB": m, "mesmo_resultado": True})

    df = pd.DataFrame(linhas)
    df_ot = pd.DataFrame(otim)
    df_gap = pd.DataFrame(gaps)
    df_gap["gap_pct"] = df_gap["gap_pct"].clip(lower=0.0)       # remove -0,000 de arredondamento

    fig, axs = plt.subplots(1, 3, figsize=(13, 3.8))
    for ax, alg in zip(axs, ["Brute Force (DFS)", "Algoritmo Genético (cfg B)", "Greedy (heap)"]):
        d = df[df["algoritmo"] == alg]
        ax.plot(d["n"], d["tempo_s"] * 1000, "o-", color="#1f6feb", label="tempo (ms)")
        ax.set_xlabel("k (SKUs no subconjunto)" if "Brute" in alg else "n (SKUs)")
        ax.set_ylabel("tempo (ms)", color="#1f6feb")
        if "Brute" in alg:
            ax.set_yscale("log")
        ax2 = ax.twinx()
        ax2.plot(d["n"], d["memoria_KiB"], "s--", color="#d1462f", label="memória (KiB)")
        ax2.set_ylabel("pico de memória (KiB)", color="#d1462f")
        ax.set_title(alg)
        ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(saida / "desempenho_q1.png", dpi=140)
    plt.close(fig)

    return {"desempenho": df, "otimizacao": df_ot, "gaps": df_gap}


if __name__ == "__main__":
    cat, cfg, man = carregar_questao(1)
    tabs = medir_desempenho(cat, cfg, carregar_parametros(), man["seed_final"], AQUI / "resultados")
    pd.set_option("display.width", 200)
    for nome, t in tabs.items():
        print(f"\n== {nome}\n{t.round(5).to_string(index=False)}")
