"""
Questão 1 — Etapa C: Greedy para alocar o orçamento de incentivo comercial.

Entrada: a política de preços do GA (vetor `sol`).

Incentivo = cupom/cashback DIRECIONADO de k% sobre o preço (ex.: carrinho abandonado,
cliente inativo), pago pelo orçamento promocional. Diferente de um corte de preço,
não é dado a todos os compradores. Cada SKU recebe incentivo em passos (5%, 10%, 15%).

Efeito na demanda (q0 = unidades sem incentivo, na política do GA):
    q_i(k) = min(estoque_i, round( d_i(preço GA) · (1 - k) ** (-elasticidade_i · β) ))
β (saliência) > 1: o consumidor reage mais a cupom/cashback do que a um corte de
preço equivalente.

Custo do incentivo: paga-se o cupom nas vendas INCREMENTAIS e numa fração α das
vendas que já ocorreriam (canibalização: clientes que comprariam de qualquer jeito
e também recebem o cupom):
    gasto_i(k)       = k · p_i · ( (q_i(k) − q0_i) + α · q0_i )
    caixa_bruto_i(k) = q_i(k) · u_i                (u_i = margem unitária no preço do GA)
    caixa_líquido    = caixa_bruto − gasto

Regra gulosa: a cada passo, escolhe o incremento de incentivo com MAIOR benefício
marginal por real investido:

    razão = Δcaixa_bruto / Δgasto

e aceita se (a) razão ≥ ROI mínimo (padrão 1,0: cada real precisa voltar inteiro,
logo o caixa líquido nunca piora), (b) cabe no saldo do orçamento e (c) a margem
líquida do SKU após o incentivo continua ≥ margem mínima.

Estrutura de dados: heap (fila de prioridade) com o PRÓXIMO incremento de cada SKU.
Complexidade (n = SKUs, K = passos de incentivo):
  Tempo  O(n·K·log n)   — cada SKU entra no heap no máximo K vezes; push/pop = O(log n)
  Memória O(n)          — o heap guarda no máximo um item por SKU
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np
import pandas as pd

from modelo import InstanciaQ1


@dataclass
class ResultadoGreedy:
    passo_por_sku: np.ndarray        # índice do passo escolhido (-1 = sem incentivo)
    incentivo_pct: np.ndarray
    unidades: np.ndarray
    caixa_bruto: np.ndarray
    gasto: np.ndarray
    orcamento_usado: float
    log_decisoes: list


def _efeito(inst: InstanciaQ1, sol: np.ndarray, k: float, beta: float, alfa: float = 0.0,
            q0: np.ndarray | None = None):
    r = np.arange(inst.n)
    preco = inst.preco_tab[r, sol]
    u = inst.margem_unit_tab[r, sol]
    m = np.where(sol == inst.L, 1.0, inst.niveis[np.minimum(sol, inst.L - 1)])
    demanda = inst.demanda_base * m ** (-inst.elasticidade) * (1 - k) ** (-inst.elasticidade * beta)
    q = np.minimum(inst.estoque, np.rint(demanda))
    q = np.where(sol == inst.L, 0.0, q)
    base = q if q0 is None else q0
    gasto = k * preco * (np.maximum(0.0, q - base) + alfa * base)
    return q, q * u, gasto, preco, u


def alocar_incentivos(inst: InstanciaQ1, sol: np.ndarray, passos=(0.05, 0.10, 0.15),
                      beta: float = 1.6, roi_minimo: float = 1.0, alfa: float = 0.25,
                      orcamento: float | None = None) -> ResultadoGreedy:
    orcamento = inst.orcamento if orcamento is None else orcamento
    if orcamento < 0:
        raise ValueError("Orçamento não pode ser negativo.")
    passos = list(passos)
    if any(not (0 < k < 1) for k in passos) or passos != sorted(passos):
        raise ValueError("Passos de incentivo devem ser crescentes e estar em (0, 1).")

    n, K = inst.n, len(passos)
    # pré-calcula efeito de cada passo: arrays (K+1, n); linha 0 = sem incentivo
    Q, B, G = np.zeros((K + 1, n)), np.zeros((K + 1, n)), np.zeros((K + 1, n))
    if not 0 <= alfa <= 1:
        raise ValueError("alfa (canibalização) deve estar em [0, 1].")
    Q[0], B[0], G[0], preco, u = _efeito(inst, sol, 0.0, beta)
    for s, k in enumerate(passos, start=1):
        Q[s], B[s], G[s], _, _ = _efeito(inst, sol, k, beta, alfa, Q[0])

    def candidato(i, s):
        """Item do heap para levar o SKU i do passo s ao passo s+1 (ou None)."""
        if s + 1 > K or sol[i] == inst.L:
            return None
        k = passos[s]
        if (u[i] - k * preco[i]) / preco[i] < inst.margem_minima:   # margem líquida após incentivo
            return None
        d_bruto = B[s + 1, i] - B[s, i]
        d_gasto = G[s + 1, i] - G[s, i]
        if d_gasto <= 0:
            return None
        razao = d_bruto / d_gasto
        return (-razao, i, s + 1, d_bruto, d_gasto)

    heap = [c for i in range(n) if (c := candidato(i, 0)) is not None]
    heapq.heapify(heap)

    atual = np.zeros(n, dtype=int)
    saldo = orcamento
    log = []
    while heap:
        neg_razao, i, s_novo, d_bruto, d_gasto = heapq.heappop(heap)
        razao = -neg_razao
        if razao < roi_minimo:
            break                     # heap ordenado: nenhum item restante passa no ROI
        if d_gasto > saldo:
            continue                  # não cabe; tenta o próximo melhor (itens menores podem caber)
        saldo -= d_gasto
        atual[i] = s_novo
        log.append({"sku": inst.skus[i], "incentivo": passos[s_novo - 1], "razao": round(razao, 3),
                    "delta_caixa_bruto": round(d_bruto, 2), "delta_gasto": round(d_gasto, 2),
                    "saldo_restante": round(saldo, 2)})
        prox = candidato(i, s_novo)
        if prox is not None:
            heapq.heappush(heap, prox)

    r = np.arange(n)
    return ResultadoGreedy(
        passo_por_sku=atual - 1,
        incentivo_pct=np.array([0.0] + passos)[atual],
        unidades=Q[atual, r], caixa_bruto=B[atual, r], gasto=G[atual, r],
        orcamento_usado=float(orcamento - saldo), log_decisoes=log)


def tabela_antes_depois(inst: InstanciaQ1, sol: np.ndarray, res: ResultadoGreedy) -> pd.DataFrame:
    r = np.arange(inst.n)
    antes_q = inst.unidades_tab[r, sol]
    antes_c = inst.caixa_tab[r, sol]
    df = pd.DataFrame({
        "sku": inst.skus,
        "nivel_preco_GA": [inst.nivel_rotulo(j) for j in sol],
        "unid_antes": antes_q.astype(int),
        "caixa_antes": np.round(antes_c, 2),
        "incentivo_pct": res.incentivo_pct,
        "unid_depois": res.unidades.astype(int),
        "gasto_incentivo": np.round(res.gasto, 2),
        "caixa_liq_depois": np.round(res.caixa_bruto - res.gasto, 2),
    })
    df["ganho_liquido"] = np.round(df["caixa_liq_depois"] - df["caixa_antes"], 2)
    return df
