"""
Questão 1 — Etapa B: Algoritmo Genético (catálogo completo).

Representação: cromossomo = vetor de inteiros de tamanho n; gene i = índice do
nível de preço do SKU i. Os genes só assumem níveis PERMITIDOS (margem mínima e
regra de desconto profundo), então R1 e R2 nunca são violadas.

R3 (limite de SKUs com desconto) é garantida por um operador de REPARO: se um
indivíduo tem descontos demais, os descontos que custam menos caixa para
desfazer são trocados pelo melhor nível sem desconto daquele SKU.

Operadores:
  * seleção por torneio (tamanho t)
  * crossover uniforme (probabilidade pc)
  * mutação por gene (probabilidade pm): 50% passo para nível vizinho permitido,
    50% sorteio de qualquer nível permitido
  * elitismo (e melhores passam intactos)
  * parada: max_geracoes OU `paciencia` gerações sem melhora do melhor fitness

R4 (giro mínimo, restrição agregada) é tratada por PENALIDADE com regra de viabilidade:
    viável:    fitness = caixa
    inviável:  fitness = caixa − λ·déficit_de_giro − M
λ (penalidade_giro) orienta a busca entre inviáveis (menos déficit é melhor) e
M = 2·Σ_i max_j |caixa_ij| + 1 garante que QUALQUER solução viável vença QUALQUER
inviável (regra de Deb). O resultado final é conferido com `inst.viavel`.

Complexidade (G = gerações, P = população, n = SKUs, L = níveis):
  Tempo  O(G · P · n)   — avaliação vetorizada, crossover, mutação e reparo são lineares em n
                           (o reparo, no pior caso, ordena os genes com desconto: O(n log n))
  Memória O(P · n)      — população atual + filhos; o histórico guarda O(G) números.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from modelo import InstanciaQ1


@dataclass
class ConfigGA:
    populacao: int = 80
    taxa_crossover: float = 0.9
    taxa_mutacao: float = 0.03
    elitismo: int = 2
    torneio: int = 3
    max_geracoes: int = 300
    paciencia: int = 60
    incluir_solucao_base: bool = True
    vetorizado: bool = True
    penalidade_giro: float = 10.0

    @classmethod
    def de_dict(cls, d: dict) -> "ConfigGA":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ResultadoGA:
    melhor_sol: np.ndarray
    melhor_caixa: float
    historico_melhor: list = field(default_factory=list)
    historico_media: list = field(default_factory=list)
    geracoes: int = 0
    geracao_melhor: int = 0
    avaliacoes: int = 0


class AlgoritmoGenetico:
    def __init__(self, inst: InstanciaQ1, cfg: ConfigGA, seed: int):
        if cfg.populacao < 2 or cfg.elitismo >= cfg.populacao:
            raise ValueError("População deve ser >= 2 e maior que o elitismo.")
        if not (0 <= cfg.taxa_mutacao <= 1 and 0 <= cfg.taxa_crossover <= 1):
            raise ValueError("Taxas devem estar em [0, 1].")
        self.inst, self.cfg = inst, cfg
        self.rng = np.random.default_rng(seed)
        n = inst.n
        self.opcoes = [inst.opcoes(i) for i in range(n)]
        self.n_opcoes = np.array([len(o) for o in self.opcoes])
        # matriz (n, max_op) com as opções; usada para sortear níveis de forma vetorizada
        self.mat_opcoes = np.full((n, self.n_opcoes.max()), -1)
        for i, o in enumerate(self.opcoes):
            self.mat_opcoes[i, :len(o)] = o
        # posição de cada nível dentro da lista de opções (para mutação "vizinho")
        self.pos = np.full((n, inst.L + 1), -1)
        for i, o in enumerate(self.opcoes):
            self.pos[i, o] = np.arange(len(o))
        # para o reparo: melhor nível SEM desconto de cada SKU e o custo de desfazer o desconto
        self.melhor_sem_desc = np.empty(n, dtype=int)
        for i, o in enumerate(self.opcoes):
            nd = [j for j in o if not inst.desconto_tab[i, j]]
            self.melhor_sem_desc[i] = max(nd, key=lambda j: inst.caixa_tab[i, j]) if nd else o[0]
        self.linhas = np.arange(n)
        self.M = 2 * np.abs(inst.caixa_tab).max(axis=1).sum() + 1.0

    # ------------------------------ avaliação ------------------------------ #
    def avaliar(self, pop: np.ndarray) -> np.ndarray:
        inst, lam = self.inst, self.cfg.penalidade_giro
        if self.cfg.vetorizado:
            # indexação avançada: (P, n) -> soma por linha. Uma operação numpy por tabela.
            caixa = inst.caixa_tab[self.linhas, pop].sum(axis=1)
            vendido = inst.valor_vendido_tab[self.linhas, pop].sum(axis=1)
            deficit = np.maximum(0.0, inst.valor_minimo_vendido - vendido)
            return caixa - np.where(deficit > 1e-6, lam * deficit + self.M, 0.0)
        # versão "antes da otimização": laço Python duplo, recalculando tudo do zero
        out = np.empty(len(pop))
        for p, ind in enumerate(pop):
            caixa, vendido = 0.0, 0.0
            for i, j in enumerate(ind):
                if j == inst.L:
                    continue
                m = inst.niveis[j]
                preco = inst.preco_atual[i] * m
                q = min(inst.estoque[i], round(inst.demanda_base[i] * m ** (-inst.elasticidade[i])))
                caixa += q * (preco * (1 - inst.taxa[i]) - inst.custo[i] - inst.logistica[i])
                vendido += q * inst.custo[i]
            deficit = max(0.0, inst.valor_minimo_vendido - vendido)
            out[p] = caixa - (lam * deficit + self.M if deficit > 1e-6 else 0.0)
        return out

    # ------------------------------ operadores ----------------------------- #
    def _sortear_niveis(self, tamanho: int) -> np.ndarray:
        r = self.rng.random((tamanho, self.inst.n))
        pos = (r * self.n_opcoes).astype(int)
        return self.mat_opcoes[self.linhas, pos]

    def reparar(self, ind: np.ndarray) -> np.ndarray:
        inst = self.inst
        com_desc = np.flatnonzero(inst.desconto_tab[self.linhas, ind])
        excesso = len(com_desc) - inst.limite_descontos
        if excesso > 0:
            perda = inst.caixa_tab[com_desc, ind[com_desc]] - \
                inst.caixa_tab[com_desc, self.melhor_sem_desc[com_desc]]
            desfazer = com_desc[np.argsort(perda)[:excesso]]
            ind[desfazer] = self.melhor_sem_desc[desfazer]
        return ind

    def _torneio(self, fit: np.ndarray, k: int) -> np.ndarray:
        P = len(fit)
        cand = self.rng.integers(0, P, size=(k, self.cfg.torneio))
        venc = cand[np.arange(k), np.argmax(fit[cand], axis=1)]
        return venc

    def _crossover(self, pais_a: np.ndarray, pais_b: np.ndarray) -> np.ndarray:
        filhos = pais_a.copy()
        faz = self.rng.random(len(pais_a)) < self.cfg.taxa_crossover
        mascara = (self.rng.random(pais_a.shape) < 0.5) & faz[:, None]
        filhos[mascara] = pais_b[mascara]
        return filhos

    def _mutar(self, pop: np.ndarray) -> np.ndarray:
        muta = self.rng.random(pop.shape) < self.cfg.taxa_mutacao
        if not muta.any():
            return pop
        lin, col = np.nonzero(muta)
        vizinho = self.rng.random(len(lin)) < 0.5
        # passo para vizinho
        pos_atual = self.pos[col, pop[lin, col]]
        passo = self.rng.choice([-1, 1], size=len(lin))
        nova_pos = np.clip(pos_atual + passo, 0, self.n_opcoes[col] - 1)
        # sorteio livre
        livre = (self.rng.random(len(lin)) * self.n_opcoes[col]).astype(int)
        escolha = np.where(vizinho, nova_pos, livre)
        pop[lin, col] = self.mat_opcoes[col, escolha]
        return pop

    # --------------------------------- laço -------------------------------- #
    def executar(self) -> ResultadoGA:
        cfg, inst = self.cfg, self.inst
        P = cfg.populacao
        pop = self._sortear_niveis(P)
        if cfg.incluir_solucao_base:
            pop[0] = inst.solucao_base()
        for k in range(P):
            self.reparar(pop[k])
        fit = self.avaliar(pop)
        res = ResultadoGA(melhor_sol=pop[np.argmax(fit)].copy(), melhor_caixa=float(fit.max()))
        res.avaliacoes = P
        sem_melhora = 0

        for g in range(1, cfg.max_geracoes + 1):
            ordem = np.argsort(-fit)
            elite = pop[ordem[:cfg.elitismo]].copy()
            n_filhos = P - cfg.elitismo
            pa = pop[self._torneio(fit, n_filhos)]
            pb = pop[self._torneio(fit, n_filhos)]
            filhos = self._mutar(self._crossover(pa, pb))
            for k in range(n_filhos):
                self.reparar(filhos[k])
            pop = np.vstack([elite, filhos])
            fit = self.avaliar(pop)
            res.avaliacoes += n_filhos

            melhor_g = float(fit.max())
            res.historico_melhor.append(melhor_g)
            res.historico_media.append(float(fit.mean()))
            if melhor_g > res.melhor_caixa + 1e-9:
                res.melhor_caixa = melhor_g
                res.melhor_sol = pop[np.argmax(fit)].copy()
                res.geracao_melhor = g
                sem_melhora = 0
            else:
                sem_melhora += 1
            res.geracoes = g
            if sem_melhora >= cfg.paciencia:
                break
        return res


def executar_ga(inst: InstanciaQ1, cfg: ConfigGA, seed: int) -> ResultadoGA:
    return AlgoritmoGenetico(inst, cfg, seed).executar()
