# Desempenho medido

Ambiente da medição: Linux, Python 3.13.17, numpy 2.5.3. Tempo com `time.perf_counter()` (melhor de N execuções para funções rápidas); memória com `tracemalloc` em execução separada, porque o tracemalloc desacelera o código (`comum/desempenho.py::medir`). Os números mudam de máquina para máquina; a tendência de crescimento é o que importa. Para refazer: `python questao_01/main.py --modo completo` e `python questao_02/main.py` (as medições entram na seção 5 de cada relatório); ou só as medições com `python questao_0X/analise_desempenho.py`.

## Questão 1 — seção 5 de `questao_01/resultados/relatorio_q1.md`, gráfico `desempenho_q1.png`

| Algoritmo | Pequena | Média | Grande |
|---|---|---|---|
| Brute Force (DFS) | k=6: 0,13 ms · 6,9 KiB | k=10: 4,2 ms · 10,9 KiB | k=12: 106 ms · 12,8 KiB |
| GA config B | n=10: 62 ms · 74 KiB | n=30: 82 ms · 199 KiB | n=120*: 426 ms · 759 KiB |
| Greedy | n=10: 0,09 ms · 7 KiB | n=30: 0,21 ms · 14 KiB | n=120*: 0,62 ms · 40 KiB |

\* n = 60 e 120 = catálogo oficial replicado, só para medir escala.

- Brute Force: de k = 10 para k = 12 o espaço cresce 30× (100.800 → 3.024.000) e o tempo 25×: exponencial, como previsto. A memória quase não muda (cresce com a profundidade k).
- GA: a memória dobra quando n dobra (O(P·n)). O tempo total depende também de quantas gerações rodam até a parada por paciência; o tempo por geração sobe de 0,6 para 1,3 ms entre n = 30 e n = 120.
- Greedy: linear na prática; nunca é o gargalo.

### Otimização demonstrada (antes × depois)

| Otimização | Entrada | Antes | Depois | Ganho | Mesmo resultado |
|---|---|---|---|---|---|
| Brute Force: `itertools.product` + recálculo de cada SKU → DFS com tabela pré-computada, soma acumulada e poda de inviáveis | k = 10 | 832 ms | 4,2 ms | **199×** | sim |
| GA: avaliação em laço Python → indexação vetorizada numpy (`caixa_tab[linhas, pop].sum(axis=1)`) | n = 30 | 1.266 ms | 91 ms | **14×** | sim (mesma seed, mesma solução) |

O preço da DFS é pouca memória extra (4,8 → 10,9 KiB) para guardar as tabelas em listas. Os testes `test_bf_ingenuo_e_otimizado_iguais` e `test_ga_vetorizado_igual_laco` garantem que a otimização não mudou a resposta.

### Duas configurações do GA (5 seeds, catálogo completo) — seção 2 do relatório

| | Config A | Config B |
|---|---|---|
| População / mutação / torneio / elitismo | 40 / 0,02 / 2 / 1 | 120 / 0,05 / 3 / 2 |
| Caixa médio (desvio) | R$ 617.155 (± 1.781) | R$ 619.580 (± 95) |
| Geração em que achou o melhor (seed 1025) | 65 | 75 |
| Avaliações de fitness | 4.915 | 16.050 |
| Tempo médio / pico de memória | 47 ms / 91 KiB | 108 ms / 204 KiB |

A config B gasta ~2,3× o tempo e a memória, mas converge de forma muito mais estável (desvio 19× menor) e é a que atinge o ótimo do Brute Force no subconjunto. Como 0,1 s é irrelevante para a decisão, usamos B. A A fica presa mais cedo: pressão seletiva baixa (torneio 2) e pouca mutação reduzem a diversidade (curva tracejada da média em `fitness_por_geracao.png`).

## Questão 2 — seção 5 de `questao_02/resultados/relatorio_q2.md`, gráfico `desempenho_q2.png`

| Etapa | N = 8 | N = 16 | N = 24 (oficial) | N = 48* |
|---|---|---|---|---|
| MC construção (2.000) | 175 ms · 23 MB | 340 ms · 45 MB | 535 ms · 67 MB | 1.145 ms · 134 MB |
| DP (todos os SKUs) | 4,6 ms · 0,2 MB | 44 ms · 3,5 MB | 36 ms · 3,5 MB | 79 ms · 4,2 MB |
| Greedy (estimativa + seleção) | 35 ms · 13 MB | 70 ms · 26 MB | 79 ms · 39 MB | 153 ms · 77 MB |
| MC validação (5.000) | 41 ms · 3,9 MB | 85 ms · 6,9 MB | 141 ms · 10 MB | 286 ms · 19 MB |

\* catálogo replicado 2×.

- Monte Carlo e Greedy crescem linearmente em N (tempo e memória dobram de 24 para 48 SKUs).
- A DP depende do **estoque**, não só de N: de 8 para 16 SKUs o estoque total salta de 439 para 2.151 unidades (16 → 34 mil estados), e o tempo sobe 9×; de 16 para 24 o estoque cresce pouco e o tempo fica estável.
- O gargalo de memória é o MC de construção (array S×T×N×L). Variando o nº de cenários: 1.000 → 35 MB, 2.000 → 69 MB, 5.000 → 171 MB, 10.000 → 341 MB — linear em S.

### Reutilização de subproblemas

| SKU | Estoque | Subproblemas distintos | Reutilizações (cache) | Bottom-Up | Top-Down |
|---|---|---|---|---|---|
| Q2-005 | 27 | 322 | 21.154 | 0,5 ms | 13,8 ms |
| Q2-007 | 32 | 373 | 25.477 | 0,5 ms | 17,1 ms |
| Q2-004 | 39 | 439 | 29.630 | 0,5 ms | 20,6 ms |

Os dois dão o mesmo valor. O Bottom-Up é ~30× mais rápido porque a esperança vira um produto de matriz por vetor no numpy, enquanto o Top-Down faz chamadas recursivas em Python puro.
