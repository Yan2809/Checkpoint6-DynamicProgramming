"""
Questão 2 — escalabilidade (tempo e memória) em três+ tamanhos de entrada.

Chamado por `main.py` (tabelas vão para o relatório; pule com --sem-desempenho) e
também executável sozinho:  python questao_02/analise_desempenho.py

Produz:
  escala   tempo e pico de memória de MC, DP e Greedy por nº de SKUs (8, 16, 24, 48)
  mc       MC de construção variando o nº de cenários (1.000, 2.000, 5.000, 10.000)
  reuso    DP Top-Down (memo) x Bottom-Up: mesmo valor, cache hits e tempo
e o gráfico resultados/desempenho_q2.png.

N = 48 é o catálogo replicado 2× (SKUs renomeados), só para medir escala.
"""
from __future__ import annotations

import sys
import time
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
from dynamic_programming import dp_sku, dp_sku_top_down, pesos_urgencia, resolver_dp
from greedy import alocar_destaques, estimar_candidatos
from modelo import construir_instancia
from monte_carlo import estimar_estatisticas, gerar_cenarios, simular


def mc_completo(inst, n, seed):
    cen = gerar_cenarios(inst, n, seed)
    return cen, estimar_estatisticas(inst, cen)


def greedy_completo(inst, cen, plano, p2):
    sim = simular(inst, cen, plano.politicas, registrar=True)
    cand = estimar_candidatos(inst, cen, sim, p2["uplift_destaque"], p2["custo_fixo_destaque"],
                              p2["custo_destaque_pct_receita"])
    return alocar_destaques(inst, cand, p2["destaques_por_semana"], inst.orcamento_semanal,
                            p2["destaque_roi_minimo"])


def medir_desempenho(catalogo, config, params, seed: int, saida: Path) -> dict:
    """Roda todas as medições; devolve {"escala", "mc", "reuso"} (DataFrames)."""
    saida.mkdir(parents=True, exist_ok=True)
    p2 = params["questao_02"]
    linhas = []

    for N in (8, 16, 24, 48):
        if N <= 24:
            cat = catalogo.iloc[:N]
        else:
            cat = pd.concat([catalogo.assign(sku=catalogo["sku"] + f"-r{r}") for r in range(N // 24)],
                            ignore_index=True)
        inst = construir_instancia(cat, config, params)
        estoque_total = int(inst.estoque.sum())
        (cen, est), t, m = medir(mc_completo, inst, 2000, seed)
        linhas.append({"etapa": "Monte Carlo construção (2.000)", "N": N, "estoque_total": estoque_total,
                       "tempo_s": t, "memoria_KiB": m})
        plano, t, m = medir(resolver_dp, inst, est, 0.0)
        estados = sum((inst.estoque + 1) * inst.semanas)
        linhas.append({"etapa": "Programação Dinâmica", "N": N, "estoque_total": estoque_total,
                       "estados": int(estados), "tempo_s": t, "memoria_KiB": m})
        _, t, m = medir(greedy_completo, inst, cen, plano, p2)
        linhas.append({"etapa": "Greedy (estimativa + seleção)", "N": N, "estoque_total": estoque_total,
                       "tempo_s": t, "memoria_KiB": m})
        cen_v = gerar_cenarios(inst, 5000, seed + 1)
        _, t, m = medir(simular, inst, cen_v, plano.politicas)
        linhas.append({"etapa": "Monte Carlo validação (5.000)", "N": N, "estoque_total": estoque_total,
                       "tempo_s": t, "memoria_KiB": m})
    df = pd.DataFrame(linhas)

    inst = construir_instancia(catalogo, config, params)
    linhas_mc = []
    for S in (1000, 2000, 5000, 10000):
        _, t, m = medir(mc_completo, inst, S, seed)
        linhas_mc.append({"cenarios": S, "tempo_s": t, "memoria_KiB": m})
    df_mc = pd.DataFrame(linhas_mc)

    # Reuso de subproblemas: Top-Down com memo x Bottom-Up, num SKU pequeno
    cen, est = mc_completo(inst, 2000, seed)
    pesos = pesos_urgencia(inst, 0.0)
    reuso = []
    for i in np.argsort(inst.estoque)[:3]:
        prob, marg, s0 = est.prob_demanda[i], est.margem_esperada[:, i, :], int(inst.estoque[i])
        t0 = time.perf_counter()
        V, _ = dp_sku(prob, marg, s0, pesos)
        t_bu = time.perf_counter() - t0
        t0 = time.perf_counter()
        v_td, info = dp_sku_top_down(prob, marg, s0, pesos)
        t_td = time.perf_counter() - t0
        reuso.append({"sku": inst.skus[i], "estoque": s0, "valor_bottom_up": V[0, s0], "valor_top_down": v_td,
                      "iguais": bool(abs(V[0, s0] - v_td) < 1e-6), "subproblemas_distintos": info.misses,
                      "reutilizacoes_cache": info.hits, "tempo_bottom_up_s": t_bu, "tempo_top_down_s": t_td})
    df_reuso = pd.DataFrame(reuso)

    fig, axs = plt.subplots(1, 2, figsize=(12, 4))
    for etapa, d in df.groupby("etapa", sort=False):
        axs[0].plot(d["N"], d["tempo_s"] * 1000, "o-", label=etapa)
        axs[1].plot(d["N"], d["memoria_KiB"] / 1024, "o-", label=etapa)
    axs[0].set_ylabel("tempo (ms)")
    axs[1].set_ylabel("pico de memória (MiB)")
    for a in axs:
        a.set_xlabel("N (SKUs)")
        a.grid(alpha=.3)
        a.legend(fontsize=7)
    axs[0].set_title("Tempo por etapa")
    axs[1].set_title("Memória por etapa")
    fig.tight_layout()
    fig.savefig(saida / "desempenho_q2.png", dpi=140)
    plt.close(fig)

    return {"escala": df, "mc": df_mc, "reuso": df_reuso}


if __name__ == "__main__":
    cat, cfg, man = carregar_questao(2)
    tabs = medir_desempenho(cat, cfg, carregar_parametros(), man["seed_final"], AQUI / "resultados")
    pd.set_option("display.width", 200)
    for nome, t in tabs.items():
        print(f"\n== {nome}\n{t.round(5).to_string(index=False)}")
