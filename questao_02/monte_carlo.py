"""
Questão 2 — Etapas A e D: Monte Carlo.

A) CONSTRUÇÃO (2.000 cenários, seed S):
   `gerar_cenarios` sorteia as três fontes de incerteza (demanda, concorrente,
   logística) e `estimar_estatisticas` transforma os sorteios, para cada
   (SKU, semana, nível de preço), em:
     • distribuição empírica da demanda  P[D = d]   -> alimenta a transição da DP
     • custo logístico esperado E[l_t]               -> alimenta a recompensa da DP
     • resumo (média, P5, P95 da demanda e caixa esperado por nível) -> relatório

D) VALIDAÇÃO (5.000 cenários NOVOS, seed S + offset):
   `simular` aplica o plano completo (política da DP + destaques do Greedy)
   semana a semana e mede caixa, pagamento das parcelas, estoque e margem.

Os cenários são pré-sorteados e reutilizados por todas as políticas comparadas
(números aleatórios comuns): a diferença entre políticas vem da decisão, não da sorte.

Complexidade (S = cenários, T = semanas, N = SKUs, L = níveis, D = demanda máxima):
  gerar_cenarios         tempo O(S·T·N)        memória O(S·T·N)
  estimar_estatisticas   tempo O(S·T·N·L)      memória O(S·T·N·L) (λ e sorteios) + O(N·T·L·D)
  simular                tempo O(S·T·N)        memória O(S·T·N) quando registra trajetórias
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from modelo import InstanciaQ2


@dataclass
class Cenarios:
    eps: np.ndarray          # (S, T, N) choque multiplicativo de demanda (média 1)
    fator_conc: np.ndarray   # (S, T, N) Pc_t / Pc_0
    logistica: np.ndarray    # (S, T, N) custo logístico realizado (R$/unid)
    choque_mercado: np.ndarray  # (S, T) componente comum
    seed_poisson: int

    @property
    def S(self) -> int:
        return self.eps.shape[0]


def gerar_cenarios(inst: InstanciaQ2, n_cenarios: int, seed: int) -> Cenarios:
    if n_cenarios <= 0:
        raise ValueError("n_cenarios deve ser positivo.")
    rng = np.random.default_rng(seed)
    S, T, N = n_cenarios, inst.semanas, inst.n
    sd, sc, sl, rho = inst.sigma_demanda, inst.sigma_conc, inst.sigma_log, inst.rho_mercado
    z_m = rng.standard_normal((S, T))
    z_i = rng.standard_normal((S, T, N))
    z = np.sqrt(rho) * z_m[:, :, None] + np.sqrt(1 - rho) * z_i
    eps = np.exp(sd * z - sd ** 2 / 2)
    passos = rng.standard_normal((S, T, N)) * sc
    fator_conc = (1 + inst.choque_concorrente) * np.exp(np.cumsum(passos, axis=1))
    logistica = inst.logistica[None, None, :] * np.exp(sl * rng.standard_normal((S, T, N)) - sl ** 2 / 2)
    return Cenarios(eps, fator_conc, logistica, z_m, seed_poisson=int(rng.integers(0, 2**31 - 1)))


# ---------------------------------------------------------------------------- #
@dataclass
class EstatisticasMC:
    prob_demanda: list          # por SKU: array (T, L, Dmax_i + 1) com P[D = d]
    logistica_media: np.ndarray # (T, N)
    margem_esperada: np.ndarray # (T, N, L)  E[p(1−taxa) − c − l_t]
    resumo: pd.DataFrame


def estimar_estatisticas(inst: InstanciaQ2, cen: Cenarios) -> EstatisticasMC:
    rng = np.random.default_rng(cen.seed_poisson)
    T, N, L = inst.semanas, inst.n, inst.L
    fp = inst.fator_preco()                                            # (N, L)
    lam = (inst.demanda_base[None, None, :, None] * fp[None, None, :, :]
           * (cen.fator_conc ** inst.gamma)[..., None] * cen.eps[..., None])  # (S, T, N, L)
    D = rng.poisson(lam)
    log_media = cen.logistica.mean(axis=0)                              # (T, N)
    precos = inst.precos()
    margem = (precos[None, :, :] * (1 - inst.taxa[None, :, None]) - inst.custo[None, :, None]
              - log_media[:, :, None])                                  # (T, N, L)

    probs = []
    for i in range(N):
        dmax = int(D[:, :, i, :].max())
        P = np.zeros((T, L, dmax + 1))
        for t in range(T):
            for a in range(L):
                P[t, a] = np.bincount(D[:, t, i, a], minlength=dmax + 1) / cen.S
        probs.append(P)

    # resumo para o relatório: demanda e caixa por nível (média das 12 semanas, sem limite de estoque)
    linhas = []
    for i in range(N):
        for a in range(L):
            d = D[:, :, i, a]
            caixa_sem = d * (precos[i, a] * (1 - inst.taxa[i]) - inst.custo[i] - cen.logistica[:, :, i])
            linhas.append({"sku": inst.skus[i], "nivel": inst.niveis[a], "preco": round(precos[i, a], 2),
                           "demanda_media_sem": round(d.mean(), 3),
                           "demanda_p5": float(np.percentile(d, 5)),
                           "demanda_p95": float(np.percentile(d, 95)),
                           "caixa_esperado_sem": round(caixa_sem.mean(), 2),
                           "caixa_desvio_sem": round(caixa_sem.std(), 2)})
    return EstatisticasMC(probs, log_media, margem, pd.DataFrame(linhas))


# ---------------------------------------------------------------------------- #
@dataclass
class ResultadoSimulacao:
    caixa_semanal: np.ndarray       # (S, T) caixa ao FIM de cada semana (após parcelas)
    pago_no_prazo: dict             # {semana: (S,) bool}
    saldo_devedor_final: np.ndarray # (S,)
    receita: np.ndarray             # (S,)
    contribuicao: np.ndarray        # (S,)  antes do gasto promocional
    gasto_promocional: float
    estoque_final: np.ndarray       # (S, N)
    niveis: np.ndarray | None = None    # (S, T, N) índice do nível usado (L = pausado)
    estoque_ini: np.ndarray | None = None  # (S, T, N) estoque no início da semana
    lam: np.ndarray | None = None       # (S, T, N) intensidade de demanda (sem destaque)
    vendas: np.ndarray | None = None    # (S, T, N)

    @property
    def caixa_final(self) -> np.ndarray:
        """Posição final = caixa − parcelas não pagas."""
        return self.caixa_semanal[:, -1] - self.saldo_devedor_final

    @property
    def sucesso_total(self) -> np.ndarray:
        return np.all(np.vstack(list(self.pago_no_prazo.values())), axis=0)


def simular(inst: InstanciaQ2, cen: Cenarios, politica, destaques: np.ndarray | None = None,
            custo_destaques: np.ndarray | None = None, uplift: float = 0.0,
            registrar: bool = False) -> ResultadoSimulacao:
    """Simula um plano em todos os cenários.

    politica: array (N,) de níveis fixos  OU  lista com N tabelas (T, estoque0+1)
              vindas da DP (decisão depende da semana e do estoque restante).
    destaques: (T, N) bool — SKUs com destaque em cada semana (Greedy).
    """
    rng = np.random.default_rng(cen.seed_poisson + 1)
    S, T, N = cen.S, inst.semanas, inst.n
    fixa = isinstance(politica, np.ndarray) and politica.ndim == 1
    destaques = np.zeros((T, N), bool) if destaques is None else destaques
    custo_destaques = np.zeros(T) if custo_destaques is None else custo_destaques
    precos = inst.precos_ext()        # índice L = pausado (demanda zero)
    fp = inst.fator_preco_ext()

    estoque = np.broadcast_to(inst.estoque, (S, N)).copy()
    caixa = np.full(S, inst.caixa_inicial)
    atraso = np.zeros(S)
    caixa_sem = np.zeros((S, T))
    pago = {}
    receita = np.zeros(S)
    contrib = np.zeros(S)
    reg_niv = np.zeros((S, T, N), np.int8) if registrar else None
    reg_est = np.zeros((S, T, N), np.int32) if registrar else None
    reg_lam = np.zeros((S, T, N), np.float32) if registrar else None
    reg_vend = np.zeros((S, T, N), np.int32) if registrar else None
    colunas = np.arange(N)

    for t in range(T):
        if fixa:
            niv = np.broadcast_to(politica, (S, N))
        else:
            niv = np.empty((S, N), dtype=int)
            for i in range(N):
                niv[:, i] = politica[i][t, estoque[:, i]]
        p = precos[colunas, niv]                                         # (S, N)
        lam = (inst.demanda_base * fp[colunas, niv] * cen.fator_conc[:, t, :] ** inst.gamma
               * cen.eps[:, t, :])
        lam_eff = lam * (1 + uplift * destaques[t])
        dem = rng.poisson(lam_eff)
        vend = np.minimum(estoque, dem)
        u = p * (1 - inst.taxa) - inst.custo - cen.logistica[:, t, :]
        receita += (vend * p).sum(axis=1)
        c_t = (vend * u).sum(axis=1)
        contrib += c_t
        if registrar:
            reg_niv[:, t] = niv
            reg_est[:, t] = estoque
            reg_lam[:, t] = lam
            reg_vend[:, t] = vend
        estoque = estoque - vend
        caixa = caixa + c_t - custo_destaques[t]

        semana = t + 1
        if semana in inst.dividas:
            devido = inst.dividas[semana] + atraso
            ok = caixa >= devido
            pago[semana] = ok
            pagamento = np.where(ok, devido, np.maximum(caixa, 0.0))
            atraso = devido - pagamento
            caixa = caixa - pagamento
        caixa_sem[:, t] = caixa

    return ResultadoSimulacao(caixa_sem, pago, atraso, receita, contrib, float(custo_destaques.sum()),
                              estoque, reg_niv, reg_est, reg_lam, reg_vend)


def metricas(inst: InstanciaQ2, res: ResultadoSimulacao, percentil: float = 5) -> dict:
    final = res.caixa_final
    m = {f"P(pagar semana {w})": float(res.pago_no_prazo[w].mean()) for w in sorted(res.pago_no_prazo)}
    m["P(pagar as 3 no prazo)"] = float(res.sucesso_total.mean())
    m["P(falha)"] = 1 - m["P(pagar as 3 no prazo)"]
    m["atende_limite_risco"] = bool(m["P(falha)"] <= inst.limite_risco)
    m["caixa_final_esperado"] = float(final.mean())
    m[f"caixa_final_P{percentil:g}"] = float(np.percentile(final, percentil))
    m["caixa_final_P50"] = float(np.percentile(final, 50))
    m["caixa_final_P95"] = float(np.percentile(final, 95))
    m["receita_esperada"] = float(res.receita.mean())
    m["margem_contribuicao_pct"] = float((res.contribuicao - res.gasto_promocional).mean()
                                         / res.receita.mean() * 100)
    m["gasto_promocional"] = res.gasto_promocional
    m["estoque_final_unid_medio"] = float(res.estoque_final.sum(axis=1).mean())
    m["estoque_final_valor_custo"] = float((res.estoque_final * inst.custo).sum(axis=1).mean())
    m["cenarios"] = int(len(final))
    return m
