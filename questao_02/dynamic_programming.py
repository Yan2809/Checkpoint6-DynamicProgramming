"""
Questão 2 — Etapa B: Programação Dinâmica (Bottom-Up) por SKU.

Formulação (para cada SKU i, resolvida de forma independente):

  ESTADO      (t, s)  — semana t ∈ {0..T−1} e estoque restante s ∈ {0..estoque_i}
  DECISÃO     a       — nível de preço da semana (6 opções) ou PAUSAR (a = L: anúncio
                        fora do ar, não vende). Pausar só compensa quando vender dá
                        prejuízo em qualquer preço (margem negativa em todos os níveis).
  TRANSIÇÃO   s' = s − min(s, D),   D ~ distribuição empírica do Monte Carlo P_t,a[d]
  RECOMPENSA  r(t, a, s, D) = ω_t · min(s, D) · ū_t,a
              ū_t,a = p_a·(1 − taxa) − custo − E[l_t]   (E[l_t] também vem do Monte Carlo)
  OBJETIVO    V_t(s) = max_a  Σ_d P_t,a[d] · ( r(t,a,s,d) + V_{t+1}(s − min(s,d)) )
              V_T(s) = 0                            (estoque que sobra não vira caixa)

Peso de urgência ω_t: o caixa precisa chegar ANTES dos vencimentos (sem. 4, 8, 12).
Com k_t = nº de parcelas ainda por vencer na semana t (3, 2 ou 1) e K = 3:
    ω_t = 1 + ρ · (k_t − 1) / (K − 1)     →  1+ρ (sem. 1–4), 1+ρ/2 (5–8), 1 (9–12)
ρ = 0 maximiza o caixa esperado total; ρ > 0 antecipa vendas. O main.py testa
vários ρ e escolhe pelo Monte Carlo a maior probabilidade de pagar as 3 parcelas.

Reutilização de subproblemas: V_{t+1}(·) é calculado UMA vez por semana e reutilizado
por todos os estados s, todas as decisões a e todas as demandas d da semana t
(linha `V_prox[s_idx - vend]`). Sem a tabela, a recursão reavaliaria V_{t+1}(s')
L·D vezes para cada (t, s) — crescimento exponencial em T.

Complexidade por SKU (T = semanas, S = estoque_i + 1, L = níveis, D = demanda máx + 1):
  Tempo   O(T · L · S · D)        Memória  O(T · S) (tabelas V e política) + O(S · D) temporário
Portfólio de N SKUs: O(N · T · L · S̄ · D̄).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from modelo import InstanciaQ2
from monte_carlo import EstatisticasMC


def pesos_urgencia(inst: InstanciaQ2, rho: float) -> np.ndarray:
    venc = sorted(inst.dividas)
    K = len(venc)
    w = np.empty(inst.semanas)
    for t in range(inst.semanas):
        k_t = sum(1 for v in venc if v >= t + 1)
        w[t] = 1 + rho * (k_t - 1) / (K - 1) if K > 1 else 1.0
    return w


def dp_sku(prob: np.ndarray, margem: np.ndarray, estoque0: int, pesos: np.ndarray):
    """DP bottom-up de um SKU.

    prob    (T, L, D+1)  distribuição da demanda por semana e nível
    margem  (T, L)       margem unitária esperada
    Retorna V (T+1, S) e politica (T, S) com o índice do nível ótimo (L = pausar).
    """
    T, L, Dm = prob.shape
    S = estoque0 + 1
    s_idx = np.arange(S)
    d_idx = np.arange(Dm)
    vend = np.minimum.outer(s_idx, d_idx)              # (S, D) unidades vendidas
    V = np.zeros((T + 1, S))
    politica = np.zeros((T, S), dtype=np.int8)
    for t in range(T - 1, -1, -1):
        V_prox = V[t + 1]
        cont = V_prox[s_idx[:, None] - vend]           # (S, D)  <- REUTILIZA V_{t+1}
        Q = np.empty((L + 1, S))
        for a in range(L):
            Q[a] = (pesos[t] * margem[t, a] * vend + cont) @ prob[t, a]
        Q[L] = V_prox                                  # pausar: não vende, estoque fica
        # empate (ex.: s = 0, onde nada muda): vence o índice MAIOR (pausar / maior preço)
        politica[t] = L - np.argmax(Q[::-1], axis=0)
        V[t] = Q[politica[t], s_idx]
    return V, politica


def dp_sku_top_down(prob: np.ndarray, margem: np.ndarray, estoque0: int, pesos: np.ndarray):
    """Mesma DP em versão Top-Down com memoization (lru_cache).

    Usada nos testes para comprovar que dá o mesmo valor do Bottom-Up e para
    contar quantas vezes um subproblema foi reutilizado (cache hits).
    """
    T, L, Dm = prob.shape

    @lru_cache(maxsize=None)
    def V(t: int, s: int) -> float:
        if t == T:
            return 0.0
        melhor = -np.inf
        for a in range(L):
            tot = 0.0
            for d in range(Dm):
                pd_ = prob[t, a, d]
                if pd_ == 0.0:
                    continue
                v = min(s, d)
                tot += pd_ * (pesos[t] * margem[t, a] * v + V(t + 1, s - v))
            melhor = max(melhor, tot)
        return max(melhor, V(t + 1, s))            # opção pausar

    valor = V(0, estoque0)
    return valor, V.cache_info()


@dataclass
class PlanoDP:
    rho: float
    pesos: np.ndarray
    politicas: list          # N tabelas (T, S_i)
    valores: list            # N tabelas (T+1, S_i)
    valor_esperado: float    # Σ_i V_0(estoque_i)  (ponderado por ω)


def resolver_dp(inst: InstanciaQ2, est: EstatisticasMC, rho: float = 0.0) -> PlanoDP:
    pesos = pesos_urgencia(inst, rho)
    pols, vals, total = [], [], 0.0
    for i in range(inst.n):
        V, pol = dp_sku(est.prob_demanda[i], est.margem_esperada[:, i, :], int(inst.estoque[i]), pesos)
        pols.append(pol)
        vals.append(V)
        total += V[0, inst.estoque[i]]
    return PlanoDP(rho, pesos, pols, vals, float(total))


def reconstruir_caminho(inst: InstanciaQ2, est: EstatisticasMC, plano: PlanoDP, i: int):
    """Caminho ótimo do SKU i ao longo das semanas, seguindo a política da DP e
    descontando a cada semana as vendas ESPERADAS (E[min(s, D)]) do estoque.

    Retorna lista de dicts: semana, estoque no início, nível, preço, vendas esperadas.
    """
    s = int(inst.estoque[i])
    caminho = []
    for t in range(inst.semanas):
        a = int(plano.politicas[i][t, s])
        if a == inst.L or s == 0:                  # pausado ou sem estoque
            caminho.append({"semana": t + 1, "estoque_inicio": s, "nivel": "pausado" if s else "esgotado",
                            "preco": None, "vendas_esperadas": 0.0})
            continue
        P = est.prob_demanda[i][t, a]
        esperado = float(np.minimum(s, np.arange(len(P))) @ P)
        caminho.append({"semana": t + 1, "estoque_inicio": s, "nivel": float(inst.niveis[a]),
                        "preco": round(float(inst.preco_atual[i] * inst.niveis[a]), 2),
                        "vendas_esperadas": round(esperado, 2)})
        s = max(0, int(round(s - esperado)))
    return caminho
