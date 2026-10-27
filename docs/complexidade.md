# Análise de complexidade (Big O)

Cada expressão está ligada ao trecho de código que a domina e ao tamanho real da instância do grupo (seed 1025). Medições em `docs/desempenho.md`.

## Questão 1

Variáveis: **n** = SKUs (30), **L** = níveis de preço permitidos por SKU (≤ 7), **k** = SKUs do subconjunto do Brute Force (10), **P** = população do GA (40 ou 120), **G** = gerações executadas (≈ 70–350, com parada por paciência), **K** = passos de incentivo (3).

Pré-processamento comum (`modelo.py::_precomputar`): tabelas `caixa_tab`, `unidades_tab`, `valor_vendido_tab` de tamanho n × (L+1). Tempo **O(n·L)**, memória **O(n·L)**. Todo o resto consulta essas tabelas em O(1).

### Brute Force — `brute_force.py`

| Versão | Tempo | Memória |
|---|---|---|
| `brute_force_ingenuo` | **O(Lᵏ · k)** | **O(k)** |
| `brute_force` (DFS) | **O(Lᵏ)** no pior caso | **O(k)** |

- Dominante, versão ingênua: o laço `for comb in itertools.product(*opcoes)` executa ∏ Lᵢ vezes (100.800 com k = 10), e cada iteração faz três somas de k termos.
- Dominante, DFS: a recursão `dfs(i + 1, …)`; cada nó custa O(1) porque a soma parcial é carregada ao descer. O número de nós é ≤ 1 + L + L² + … + Lᵏ = O(Lᵏ). As podas de R3 e R4 cortam ramos inviáveis: com k = 10 foram 18.882 nós em vez de 100.800 folhas.
- Memória: a pilha da recursão tem profundidade k e a solução atual tem k posições; as tabelas são do pré-processamento.
- **Quando deixa de ser viável**: com k = 12 já são 3,0 milhões de combinações (0,1 s); cada SKU a mais multiplica o espaço por ~5–7. Para os 30 SKUs seriam ~10²² combinações (7²⁹ com um suspenso): é por isso que o catálogo completo vai para o GA, e o Brute Force fica só como benchmark.

### Algoritmo Genético — `genetic_algorithm.py`

**Tempo O(G · P · n)** · **Memória O(P · n)**

- Por geração: torneio O(P·t), crossover uniforme O(P·n), mutação O(P·n), reparo de R3 O(n log n) por indivíduo no pior caso (ordena os genes com desconto; na prática poucos), avaliação O(P·n) (`caixa_tab[self.linhas, pop].sum(axis=1)`). O termo dominante é **O(P·n)** por geração, mais **O(P·n log n)** se o reparo atuar em todo indivíduo.
- Trecho dominante: `executar()` → `avaliar(pop)` e o laço `for k in range(n_filhos): self.reparar(...)`.
- Memória: população e filhos (2·P·n inteiros) + histórico O(G).
- Medido: o tempo por geração cresce de ~0,6 ms (n = 30) para ~1,3 ms (n = 120), coerente com O(P·n) mais o custo fixo do numpy por chamada.
- **Limite**: o GA não garante o ótimo. Com n grande, aumentar P e G (custo linear) ou reiniciar com várias seeds. A validação contra o Brute Force mostra gap ≤ 0,024% na config B.

### Greedy — `greedy.py::alocar_incentivos`

**Tempo O(n·K + n·K·log n) = O(n·K·log n)** · **Memória O(n·K)**

- Pré-cálculo do efeito de cada passo: arrays (K+1) × n → O(n·K).
- Heap: cada SKU entra no heap no máximo K vezes; `heappush`/`heappop` custam O(log n) porque o heap guarda no máximo um item por SKU.
- Trecho dominante: o laço `while heap:` com `heapq.heappop`.
- Medido: 0,09 ms (n = 10) → 0,62 ms (n = 120), praticamente linear.

## Questão 2

Variáveis: **S** = cenários (2.000 na construção, 5.000 na validação), **T** = semanas (12), **N** = SKUs (24), **L** = níveis (6, +1 para pausar), **Eᵢ** = estoque inicial do SKU i (até 499; Σ = 2.842), **Dᵢ** = maior demanda semanal sorteada do SKU i + 1 (até ~160).

### Monte Carlo — `monte_carlo.py`

| Função | Tempo | Memória |
|---|---|---|
| `gerar_cenarios` | O(S·T·N) | O(S·T·N) |
| `estimar_estatisticas` | O(S·T·N·L) | O(S·T·N·L) + O(Σᵢ T·L·Dᵢ) |
| `simular` | O(S·T·N) | O(S·N) (O(S·T·N) com `registrar=True`) |

- Dominante em `estimar_estatisticas`: o array `lam` de forma (S, T, N, L) e o sorteio `rng.poisson(lam)` — 2.000 × 12 × 24 × 6 ≈ 3,5 milhões de valores (55–69 MB de pico). Os `np.bincount` geram as distribuições em O(S) por (i, t, a).
- Dominante em `simular`: o laço `for t in range(T)`, com operações vetorizadas sobre (S, N) em cada semana; a consulta à política da DP (`politica[i][t, estoque[:, i]]`) é O(S) por SKU.
- **Limite**: a memória cresce linearmente com S (1.000 → 10.000 cenários: 35 → 341 MB). Acima disso, processar um SKU por vez em `estimar_estatisticas` reduz a memória para O(S·T·L) sem mudar o resultado.

### Programação Dinâmica — `dynamic_programming.py::dp_sku`

**Tempo O(T · L · Eᵢ · Dᵢ)** por SKU, **O(T · L · Σᵢ Eᵢ · Dᵢ)** no portfólio · **Memória O(T · Eᵢ)** (tabelas V e política) + **O(Eᵢ · Dᵢ)** temporária

- Estados: T × (Eᵢ + 1). No portfólio são 34.392 estados (12 × Σ(Eᵢ+1)).
- Para cada estado e cada decisão, a esperança soma sobre Dᵢ valores de demanda: `(pesos[t] * margem[t, a] * vend + cont) @ prob[t, a]` — esta linha domina.
- **Reutilização de subproblemas**: `cont = V_prox[s_idx[:, None] - vend]` lê V_{t+1} já calculado para todas as combinações (estado, demanda) da semana t. Sem memória, cada V_t(s) recalcularia V_{t+1} para L·Dᵢ sucessores, ou seja, O((L·D)ᵀ). A versão Top-Down (`dp_sku_top_down`, `lru_cache`) confirma: no SKU Q2-005 são 322 subproblemas distintos e **21.154 reutilizações** de cache (seção 5 de `questao_02/resultados/relatorio_q2.md`), com o mesmo valor do Bottom-Up.
- **Limite**: com estoques de dezenas de milhares de unidades, Eᵢ·Dᵢ fica grande; a alternativa é agregar o estoque em faixas (ex.: de 10 em 10 unidades), trocando precisão por tempo. O estado conjunto de todos os SKUs (∏ Eᵢ) é inviável — por isso a DP é resolvida por SKU e o acoplamento financeiro (caixa e parcelas) é avaliado no Monte Carlo.

### Greedy — `greedy.py`

**Tempo O(S·T·N + T·N·log N)** · **Memória O(S·T·N)** (leitura do registro) + **O(T·N)** candidatos

- `estimar_candidatos`: médias sobre os S cenários para cada (t, i) → O(S·T·N).
- `alocar_destaques`: por semana ordena N candidatos (`sort_values`) → O(N log N); total O(T·N log N).
- A estimativa domina o tempo; a seleção gulosa em si leva ~11 ms.
