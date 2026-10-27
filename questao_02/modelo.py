"""
Questão 2 — modelo do "Plano de Sobrevivência em 12 Semanas".

Por SKU i, semana t (1..12), nível de preço a (multiplicador m_a sobre preco_atual):

  Demanda (intensidade):
     λ_ita = demanda_base_semanal_i · m_a^(−e_i) · (Pc_it / Pc_i0)^γ · ε_it · (1 + uplift · destaque_it)
     D_ita ~ Poisson(λ_ita)            vendas = min(estoque_it, D_ita)

  Fontes de incerteza (as três exigidas + correlação de mercado):
     ε_it   = exp(σ_d·(√ρ·Z_t + √(1−ρ)·Z_it) − σ_d²/2)   choque de demanda (média 1);
              Z_t é comum a todos os SKUs na semana (choque de mercado, correlação ρ)
     Pc_it  = Pc_i0 · (1 + choque) · exp(Σ_{τ≤t} σ_c·W_iτ)   concorrente em passeio aleatório
              (choque = cenário-surpresa, ex.: −8%; 0 na instância oficial)
     l_it   = l_i0 · exp(σ_l·V_it − σ_l²/2)              custo logístico (média l_i0)

  Caixa semanal (margem de contribuição — mesma base usada pelo gerador para as dívidas):
     C_t = C_{t−1} + Σ_i vendas_it · (p_ia·(1 − taxa_i) − custo_i − l_it) − gasto_promocional_t
  Nas semanas 4, 8 e 12 paga-se a parcela. Se C_t < parcela, a parcela não é paga
  no prazo (FALHA): paga-se o que houver e o saldo devedor é somado à parcela seguinte.

γ (elasticidade cruzada) e ρ são parâmetros de modelagem do grupo (config/parametros_modelo.json).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class InstanciaQ2:
    skus: np.ndarray
    categoria: np.ndarray
    custo: np.ndarray
    preco_atual: np.ndarray
    estoque: np.ndarray            # int
    demanda_base: np.ndarray
    elasticidade: np.ndarray
    taxa: np.ndarray
    logistica: np.ndarray
    preco_conc: np.ndarray
    niveis: np.ndarray
    semanas: int
    caixa_inicial: float
    dividas: dict                  # {semana: valor}
    sigma_demanda: float
    sigma_conc: float
    sigma_log: float
    orcamento_semanal: float
    limite_risco: float
    gamma: float = 0.8
    rho_mercado: float = 0.3
    choque_concorrente: float = 0.0   # deslocamento do preço do concorrente vs. o oficial

    @property
    def n(self) -> int:
        return len(self.skus)

    @property
    def L(self) -> int:
        return len(self.niveis)

    @property
    def idx_base(self) -> int:
        return int(np.argmin(np.abs(self.niveis - 1.0)))

    def precos(self) -> np.ndarray:
        """(n, L) preço de cada SKU em cada nível."""
        return self.preco_atual[:, None] * self.niveis[None, :]

    def precos_ext(self) -> np.ndarray:
        """(n, L+1): coluna extra = PAUSADO (preço de referência; não há venda)."""
        return np.hstack([self.precos(), self.preco_atual[:, None]])

    def fator_preco_ext(self) -> np.ndarray:
        """(n, L+1): coluna extra = PAUSADO (demanda zero)."""
        return np.hstack([self.fator_preco(), np.zeros((self.n, 1))])

    def niveis_ext(self) -> np.ndarray:
        """níveis + NaN para PAUSADO (útil em gráficos e tabelas)."""
        return np.append(self.niveis, np.nan)

    def margem_unit(self, logistica: np.ndarray | float | None = None) -> np.ndarray:
        """(n, L) margem unitária com custo logístico informado (padrão: base)."""
        l = self.logistica if logistica is None else logistica
        return self.precos() * (1 - self.taxa[:, None]) - self.custo[:, None] - np.asarray(l)[..., None]

    def fator_preco(self) -> np.ndarray:
        """(n, L) multiplicador de demanda m^(−e)."""
        return self.niveis[None, :] ** (-self.elasticidade[:, None])

    def subconjunto(self, indices) -> "InstanciaQ2":
        idx = np.asarray(indices)
        campos = dict(self.__dict__)
        for k in ("skus", "categoria", "custo", "preco_atual", "estoque", "demanda_base",
                  "elasticidade", "taxa", "logistica", "preco_conc"):
            campos[k] = campos[k][idx]
        return InstanciaQ2(**campos)


def construir_instancia(catalogo: pd.DataFrame, config: dict, params: dict) -> InstanciaQ2:
    p2 = params["questao_02"]
    v = config["variabilidade"]
    dividas = {int(k.split("_")[1]): float(val) for k, val in config["dividas"].items()}
    return InstanciaQ2(
        skus=catalogo["sku"].to_numpy(),
        categoria=catalogo["categoria"].to_numpy(),
        custo=catalogo["custo_unitario"].to_numpy(float),
        preco_atual=catalogo["preco_atual"].to_numpy(float),
        estoque=catalogo["estoque_inicial"].to_numpy(int),
        demanda_base=catalogo["demanda_base_semanal"].to_numpy(float),
        elasticidade=catalogo["elasticidade"].to_numpy(float),
        taxa=catalogo["taxa_marketplace"].to_numpy(float),
        logistica=catalogo["custo_logistico_base"].to_numpy(float),
        preco_conc=catalogo["preco_concorrente_base"].to_numpy(float),
        niveis=np.array(config["niveis_preco_relativos"], dtype=float),
        semanas=int(config["numero_semanas"]),
        caixa_inicial=float(config["caixa_inicial"]),
        dividas=dividas,
        sigma_demanda=float(v["sigma_demanda"]),
        sigma_conc=float(v["sigma_preco_concorrente"]),
        sigma_log=float(v["sigma_custo_logistico"]),
        orcamento_semanal=float(config["orcamento_promocional_semanal"]),
        limite_risco=float(config["limite_risco_falha"]),
        gamma=float(p2["elasticidade_cruzada_concorrente"]),
        rho_mercado=float(p2["correlacao_choque_mercado"]),
        choque_concorrente=float(config.get("choque_concorrente", 0.0)),
    )
