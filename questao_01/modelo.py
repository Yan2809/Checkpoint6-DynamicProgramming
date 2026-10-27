"""
Questão 1 — modelo do problema "Operação Caixa 90".

Decisão: para cada SKU i, um índice j de nível de preço  ->  p_ij = preco_atual_i * nivel_j.

Demanda em 90 dias (elasticidade constante):
    d_ij = demanda_base_90d_i * nivel_j ** (-elasticidade_i)
Unidades vendidas (limitadas pelo estoque):
    q_ij = min(estoque_i, round(d_ij))
Margem de contribuição unitária (mesma definição usada pelo gerador para a meta):
    u_ij = p_ij * (1 - taxa_marketplace_i) - custo_unitario_i - custo_logistico_i
Caixa operacional do SKU:
    caixa_ij = q_ij * u_ij

Restrições:
  R1 (margem mínima)  u_ij / p_ij >= margem_minima_percentual          (por SKU)
  R2 (desconto profundo só para estoque envelhecido)
                       nivel_j < limiar  =>  idade_estoque_i >= idade_minima   (por SKU)
  R3 (sem desconto indiscriminado)
                       #{i : nivel escolhido < 1.00} <= floor(max_fracao * n)  (acopla os SKUs)
  R4 (giro de estoque) Σ_i q_ij · custo_i  >=  giro_minimo · Σ_i estoque_i · custo_i
                       ou seja: a política precisa transformar em venda pelo menos a
                       mesma fração do capital empatado em estoque que a política atual
                       (giro_minimo = "base"), ou uma fração informada.

Por que R4 existe: com a margem de contribuição desta instância, o ótimo SEM R4 é
subir o preço de quase tudo para 1,10 — o caixa cresce, mas o giro cai e o estoque
envelhecido fica parado. R4 obriga a escolher ONDE baixar preço (e quais SKUs
"pagam" o giro com menor perda de caixa). R1 e R2 viram uma máscara `permitido[i, j]`;
R3 e R4 são globais e acoplam os SKUs — é por isso que o problema exige busca
combinatória (Brute Force / GA) e não pode ser resolvido SKU a SKU.

SKUs sem nenhum nível permitido ficam "suspensos" (índice L = coluna extra, venda zero).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class InstanciaQ1:
    skus: np.ndarray
    categoria: np.ndarray
    preco_atual: np.ndarray
    custo: np.ndarray
    estoque: np.ndarray
    demanda_base: np.ndarray
    elasticidade: np.ndarray
    taxa: np.ndarray
    logistica: np.ndarray
    idade: np.ndarray
    niveis: np.ndarray                 # (L,)
    margem_minima: float
    meta_caixa: float
    divida: float
    orcamento: float
    max_fracao_desconto: float
    limiar_profundo: float
    idade_minima_profundo: int
    giro_minimo: float | str = "base"   # fração do valor do estoque (a custo) a ser vendida
    # tabelas pré-computadas (n, L+1); a última coluna é "suspenso"
    caixa_tab: np.ndarray = field(init=False)
    unidades_tab: np.ndarray = field(init=False)
    receita_tab: np.ndarray = field(init=False)
    permitido: np.ndarray = field(init=False)
    desconto_tab: np.ndarray = field(init=False)

    def __post_init__(self):
        self._precomputar()

    # ------------------------------------------------------------------ #
    @property
    def n(self) -> int:
        return len(self.skus)

    @property
    def L(self) -> int:
        return len(self.niveis)

    @property
    def idx_suspenso(self) -> int:
        return self.L

    @property
    def idx_base(self) -> int:
        """Índice do nível 1.00 (preço atual)."""
        return int(np.argmin(np.abs(self.niveis - 1.0)))

    @property
    def limite_descontos(self) -> int:
        return int(np.floor(self.max_fracao_desconto * self.n))

    # ------------------------------------------------------------------ #
    def _precomputar(self):
        n, L = self.n, self.L
        m = self.niveis[None, :]                                   # (1, L)
        preco = self.preco_atual[:, None] * m                       # (n, L)
        demanda = self.demanda_base[:, None] * m ** (-self.elasticidade[:, None])
        unidades = np.minimum(self.estoque[:, None], np.rint(demanda))
        u = preco * (1 - self.taxa[:, None]) - self.custo[:, None] - self.logistica[:, None]

        margem_ok = (u / preco) >= self.margem_minima - 1e-12
        profundo = m < self.limiar_profundo - 1e-12
        idade_ok = (self.idade[:, None] >= self.idade_minima_profundo) | ~profundo
        permitido = margem_ok & idade_ok

        suspenso = ~permitido.any(axis=1)                           # SKUs sem nível viável
        self.caixa_tab = np.zeros((n, L + 1))
        self.unidades_tab = np.zeros((n, L + 1))
        self.receita_tab = np.zeros((n, L + 1))
        self.caixa_tab[:, :L] = unidades * u
        self.unidades_tab[:, :L] = unidades
        self.receita_tab[:, :L] = unidades * preco
        self.permitido = np.zeros((n, L + 1), dtype=bool)
        self.permitido[:, :L] = permitido
        self.permitido[:, L] = suspenso
        self.desconto_tab = np.zeros((n, L + 1), dtype=bool)
        self.desconto_tab[:, :L] = np.broadcast_to(self.niveis < 1.0 - 1e-12, (n, L))
        self.margem_unit_tab = np.zeros((n, L + 1))
        self.margem_unit_tab[:, :L] = u
        self.preco_tab = np.zeros((n, L + 1))
        self.preco_tab[:, :L] = preco
        # valor (a custo) do estoque convertido em venda -> usado em R4
        self.valor_vendido_tab = self.unidades_tab * self.custo[:, None]
        self.valor_estoque_total = float((self.estoque * self.custo).sum())
        if self.giro_minimo == "base":
            self.giro_minimo_frac = self.giro(self.solucao_base())
        else:
            self.giro_minimo_frac = float(self.giro_minimo)
        self.valor_minimo_vendido = self.giro_minimo_frac * self.valor_estoque_total

    def opcoes(self, i: int) -> np.ndarray:
        """Índices de nível permitidos para o SKU i."""
        return np.flatnonzero(self.permitido[i])

    def skus_suspensos(self) -> list[str]:
        return list(self.skus[self.permitido[:, self.L]])

    def subconjunto(self, indices) -> "InstanciaQ1":
        """Nova instância restrita aos SKUs `indices` (mesmos parâmetros globais)."""
        idx = np.asarray(indices)
        return InstanciaQ1(
            skus=self.skus[idx], categoria=self.categoria[idx], preco_atual=self.preco_atual[idx],
            custo=self.custo[idx], estoque=self.estoque[idx], demanda_base=self.demanda_base[idx],
            elasticidade=self.elasticidade[idx], taxa=self.taxa[idx], logistica=self.logistica[idx],
            idade=self.idade[idx], niveis=self.niveis, margem_minima=self.margem_minima,
            meta_caixa=self.meta_caixa, divida=self.divida, orcamento=self.orcamento,
            max_fracao_desconto=self.max_fracao_desconto, limiar_profundo=self.limiar_profundo,
            idade_minima_profundo=self.idade_minima_profundo, giro_minimo=self.giro_minimo)

    # ------------------------------------------------------------------ #
    def caixa(self, sol: np.ndarray) -> float:
        return float(self.caixa_tab[np.arange(self.n), sol].sum())

    def n_descontos(self, sol: np.ndarray) -> int:
        return int(self.desconto_tab[np.arange(self.n), sol].sum())

    def valor_vendido(self, sol: np.ndarray) -> float:
        return float(self.valor_vendido_tab[np.arange(self.n), sol].sum())

    def giro(self, sol: np.ndarray) -> float:
        """Fração do valor (a custo) do estoque vendida em 90 dias."""
        return self.valor_vendido(sol) / self.valor_estoque_total

    def deficit_giro(self, sol: np.ndarray) -> float:
        return max(0.0, self.valor_minimo_vendido - self.valor_vendido(sol))

    def viavel(self, sol: np.ndarray) -> bool:
        sol = np.asarray(sol)
        if sol.shape != (self.n,):
            return False
        return bool(self.permitido[np.arange(self.n), sol].all()) and \
            self.n_descontos(sol) <= self.limite_descontos and \
            self.deficit_giro(sol) <= 1e-6

    def solucao_base(self) -> np.ndarray:
        """Política 'manter preço atual' (ou o menor nível permitido >= 1.00)."""
        sol = np.empty(self.n, dtype=int)
        for i in range(self.n):
            ops = self.opcoes(i)
            if ops[-1] == self.L:                       # SKU suspenso
                sol[i] = self.L
                continue
            sem_desc = [j for j in ops if self.niveis[j] >= 1.0 - 1e-12]
            sol[i] = sem_desc[0] if sem_desc else ops[-1]   # menor nível >= 1.00
        return sol

    def nivel_rotulo(self, j: int) -> str:
        return "suspenso" if j == self.L else f"{self.niveis[j]:.2f}"


def construir_instancia(catalogo: pd.DataFrame, config: dict, params: dict) -> InstanciaQ1:
    p = params["questao_01"]
    return InstanciaQ1(
        skus=catalogo["sku"].to_numpy(),
        categoria=catalogo["categoria"].to_numpy(),
        preco_atual=catalogo["preco_atual"].to_numpy(float),
        custo=catalogo["custo_unitario"].to_numpy(float),
        estoque=catalogo["estoque"].to_numpy(float),
        demanda_base=catalogo["demanda_base_90d"].to_numpy(float),
        elasticidade=catalogo["elasticidade"].to_numpy(float),
        taxa=catalogo["taxa_marketplace"].to_numpy(float),
        logistica=catalogo["custo_logistico"].to_numpy(float),
        idade=catalogo["idade_estoque_dias"].to_numpy(int),
        niveis=np.array(config["niveis_preco_relativos"], dtype=float),
        margem_minima=float(config["margem_minima_percentual"]),
        meta_caixa=float(config["meta_caixa_90d"]),
        divida=float(config["divida_total_90d"]),
        orcamento=float(config["orcamento_promocional"]),
        max_fracao_desconto=float(p["max_fracao_skus_com_desconto"]),
        limiar_profundo=float(p["limiar_desconto_profundo"]),
        idade_minima_profundo=int(p["idade_minima_desconto_profundo_dias"]),
        giro_minimo=p.get("giro_minimo", "base"),
    )


def tabela_politica(inst: InstanciaQ1, sol: np.ndarray) -> pd.DataFrame:
    """Tabela por SKU para uma política de preços."""
    r = np.arange(inst.n)
    return pd.DataFrame({
        "sku": inst.skus,
        "categoria": inst.categoria,
        "nivel": [inst.nivel_rotulo(j) for j in sol],
        "preco": np.round(inst.preco_tab[r, sol], 2),
        "unidades_90d": inst.unidades_tab[r, sol].astype(int),
        "estoque_restante": (inst.estoque - inst.unidades_tab[r, sol]).astype(int),
        "margem_unit": np.round(inst.margem_unit_tab[r, sol], 2),
        "receita": np.round(inst.receita_tab[r, sol], 2),
        "caixa": np.round(inst.caixa_tab[r, sol], 2),
    })
