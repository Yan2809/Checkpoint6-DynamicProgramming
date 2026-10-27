"""
Questão 2 — Etapa C: Greedy semanal de destaques (mídia / vitrine / frete promocional).

Entrada: o plano de preços da DP, simulado nos cenários de CONSTRUÇÃO (registro de
estoque, nível e intensidade de demanda λ por cenário/semana/SKU).

Recurso escasso por semana:  no máximo K destaques  e  orçamento semanal B.
Um destaque no SKU i na semana t aumenta a demanda em `uplift` (ex.: +30%).

Para cada candidato (t, i), estimado sobre os cenários de construção:
  Δunid_ti   = E[min(S, λ·(1+uplift))] − E[min(S, λ)]          (respeita o estoque)
  benefício  = Δunid_ti · margem_ti · P(sobra estoque no fim)_i
               (o último fator evita "premiar" um SKU que venderia tudo de qualquer
               jeito — nele o destaque só antecipa vendas)
  custo      = custo_fixo + pct · E[receita_ti]
  razão      = benefício / custo

Regra gulosa (por semana): ordena candidatos pela razão (maior primeiro) e aceita
enquanto houver vaga, couber no orçamento e razão ≥ ROI mínimo (1,0 = só investe
se o real gasto volta inteiro em margem).

Complexidade (T = semanas, N = SKUs, S = cenários de construção):
  estimar benefícios  O(S·T·N)      seleção por semana  O(N log N)  →  total O(S·T·N + T·N·log N)
  Memória O(T·N) para a matriz de candidatos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modelo import InstanciaQ2
from monte_carlo import Cenarios, ResultadoSimulacao


def estimar_candidatos(inst: InstanciaQ2, cen: Cenarios, sim: ResultadoSimulacao,
                       uplift: float, custo_fixo: float, custo_pct: float) -> pd.DataFrame:
    if sim.lam is None:
        raise ValueError("A simulação precisa ter sido feita com registrar=True.")
    S_ini = sim.estoque_ini.astype(float)          # (S, T, N)
    lam = sim.lam.astype(float)
    precos = inst.precos_ext()
    p = precos[np.arange(inst.n), sim.niveis]       # (S, T, N); pausado => λ = 0, sem benefício
    margem = p * (1 - inst.taxa) - inst.custo - cen.logistica
    base = np.minimum(S_ini, lam)
    com = np.minimum(S_ini, lam * (1 + uplift))
    delta = (com - base).mean(axis=0)               # (T, N)
    margem_media = (margem * base).sum(axis=0) / np.maximum(base.sum(axis=0), 1e-9)
    receita = (p * base).mean(axis=0)
    p_sobra = (sim.estoque_final > 0).mean(axis=0)  # (N,)
    beneficio = delta * np.maximum(margem_media, 0.0) * p_sobra[None, :]
    custo = custo_fixo + custo_pct * receita
    T, N = delta.shape
    return pd.DataFrame({
        "semana": np.repeat(np.arange(1, T + 1), N),
        "sku_idx": np.tile(np.arange(N), T),
        "sku": np.tile(inst.skus, T),
        "delta_unid": delta.ravel(),
        "margem_unit": margem_media.ravel(),
        "p_sobra": np.tile(p_sobra, T),
        "beneficio": beneficio.ravel(),
        "custo": custo.ravel(),
        "razao": (beneficio / custo).ravel(),
    })


def alocar_destaques(inst: InstanciaQ2, candidatos: pd.DataFrame, k_por_semana: int,
                     orcamento_semanal: float, roi_minimo: float = 1.0):
    """Retorna (destaques (T,N) bool, custo_por_semana (T,), tabela das escolhas)."""
    if k_por_semana < 0 or orcamento_semanal < 0:
        raise ValueError("Vagas e orçamento devem ser não negativos.")
    T, N = inst.semanas, inst.n
    dest = np.zeros((T, N), bool)
    custo_sem = np.zeros(T)
    escolhas = []
    for t in range(1, T + 1):
        cand = candidatos[candidatos["semana"] == t].sort_values("razao", ascending=False)
        saldo, vagas = orcamento_semanal, k_por_semana
        for row in cand.itertuples():
            if vagas == 0 or row.razao < roi_minimo:
                break
            if row.custo > saldo:
                continue
            dest[t - 1, row.sku_idx] = True
            saldo -= row.custo
            vagas -= 1
            custo_sem[t - 1] += row.custo
            escolhas.append({"semana": t, "sku": row.sku, "razao": round(row.razao, 3),
                             "beneficio_esperado": round(row.beneficio, 2), "custo": round(row.custo, 2),
                             "saldo_orcamento": round(saldo, 2)})
    return dest, custo_sem, pd.DataFrame(escolhas)
