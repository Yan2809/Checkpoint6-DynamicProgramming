"""
Questão 1 — Etapa A: Brute Force (benchmark ótimo num subconjunto pequeno).

Enumera TODAS as combinações de níveis permitidos dos k SKUs do subconjunto e
guarda a melhor combinação viável (limite de SKUs com desconto R3 e giro mínimo R4).

Duas versões, para a evidência de "otimização antes/depois":

* `brute_force_ingenuo`  — itertools.product sobre as combinações; para cada
  combinação recalcula demanda, unidades e margem de cada SKU do zero.
  Tempo  O(L^k · k)   Memória O(k)

* `brute_force`          — busca em profundidade (DFS) que usa a tabela
  pré-computada caixa_tab[i, j], acumula somas parciais ao descer na árvore
  (O(1) por nó) e corta ramos que JÁ SÃO INVIÁVEIS: estouraram o limite de
  descontos ou não conseguem mais atingir o giro mínimo nem vendendo o máximo
  possível nos SKUs restantes. Não há corte por "promessa de caixa", então
  continua sendo enumeração exata de todas as soluções viáveis.
  Tempo  O(L^k) no pior caso (nós da árvore)   Memória O(k) (pilha da recursão)

Variáveis: k = SKUs no subconjunto; L = níveis permitidos por SKU (≤ 7).
"""
from __future__ import annotations

import itertools

import numpy as np

from modelo import InstanciaQ1


def _caixa_sku_do_zero(inst: InstanciaQ1, i: int, j: int) -> float:
    """Recalcula o caixa do SKU i no nível j sem usar tabelas (versão ingênua)."""
    if j == inst.L:
        return 0.0
    m = inst.niveis[j]
    preco = inst.preco_atual[i] * m
    demanda = inst.demanda_base[i] * m ** (-inst.elasticidade[i])
    unidades = min(inst.estoque[i], round(demanda))
    u = preco * (1 - inst.taxa[i]) - inst.custo[i] - inst.logistica[i]
    return unidades * u


def brute_force_ingenuo(inst: InstanciaQ1):
    """Versão sem otimização. Retorna (melhor_sol, melhor_caixa, combinacoes_avaliadas)."""
    opcoes = [inst.opcoes(i) for i in range(inst.n)]
    limite = inst.limite_descontos
    melhor, melhor_val, avaliadas = None, -np.inf, 0
    for comb in itertools.product(*opcoes):
        avaliadas += 1
        descontos = sum(1 for i, j in enumerate(comb) if inst.desconto_tab[i, j])
        if descontos > limite:
            continue
        vendido = sum(inst.unidades_tab[i, j] * inst.custo[i] for i, j in enumerate(comb))
        if vendido < inst.valor_minimo_vendido - 1e-6:
            continue
        val = sum(_caixa_sku_do_zero(inst, i, j) for i, j in enumerate(comb))
        if val > melhor_val:
            melhor_val, melhor = val, np.array(comb)
    return melhor, float(melhor_val), avaliadas


def brute_force(inst: InstanciaQ1):
    """Versão otimizada (DFS + tabela + poda por restrição). Retorna (sol, caixa, nos_visitados)."""
    n, limite = inst.n, inst.limite_descontos
    opcoes = [inst.opcoes(i).tolist() for i in range(n)]
    tab = inst.caixa_tab.tolist()              # listas Python: acesso O(1) mais rápido que numpy escalar
    desc = inst.desconto_tab.tolist()
    vend = inst.valor_vendido_tab.tolist()
    v_min = inst.valor_minimo_vendido - 1e-6
    # máximo valor vendável nos SKUs i..n-1 (para saber se ainda dá para atingir o giro)
    max_vend = [max(vend[i][j] for j in opcoes[i]) for i in range(n)]
    resto = [0.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        resto[i] = resto[i + 1] + max_vend[i]

    melhor_val = -np.inf
    melhor_sol = None
    atual = [0] * n
    nos = 0

    def dfs(i: int, soma: float, descontos: int, vendido: float):
        nonlocal melhor_val, melhor_sol, nos
        nos += 1
        if i == n:
            if soma > melhor_val:
                melhor_val, melhor_sol = soma, atual.copy()
            return
        linha_tab, linha_desc, linha_vend = tab[i], desc[i], vend[i]
        for j in opcoes[i]:
            d = descontos + linha_desc[j]
            if d > limite:                                  # poda R3
                continue
            v = vendido + linha_vend[j]
            if v + resto[i + 1] < v_min:                    # poda R4: giro inalcançável
                continue
            atual[i] = j
            dfs(i + 1, soma + linha_tab[j], d, v)

    dfs(0, 0.0, 0, 0.0)
    if melhor_sol is None:
        raise ValueError("Nenhuma solução viável no subconjunto.")
    return np.array(melhor_sol), float(melhor_val), nos


def espaco_de_busca(inst: InstanciaQ1) -> int:
    """Número total de combinações L_1 × L_2 × ... × L_k (antes da poda)."""
    return int(np.prod([len(inst.opcoes(i)) for i in range(inst.n)], dtype=float))


def escolher_subconjunto(inst: InstanciaQ1, k: int) -> np.ndarray:
    """Subconjunto reduzido: os k SKUs com maior valor de estoque a custo.

    São os itens de maior impacto financeiro, logo o benchmark é representativo.
    SKUs suspensos (sem nível viável) não entram, pois não têm decisão a tomar.
    """
    ativos = np.flatnonzero(~inst.permitido[:, inst.L])
    valor = inst.custo[ativos] * inst.estoque[ativos]
    return np.sort(ativos[np.argsort(-valor)[:k]])
