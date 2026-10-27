# Respostas do Checkpoint 6 — item a item do enunciado

Grupo **G01** · seed_base **25** · seed_final **1025** · instância `386e6252eb25`

Este arquivo responde, na ordem do PDF, cada entrega e evidência pedida, e indica onde está a prova (arquivo e função). Os números são da execução oficial (`bash reproduzir.sh`); valores financeiros são reproduzíveis exatamente pela seed, já tempos e memória variam um pouco a cada execução. As tabelas completas estão nos relatórios gerados pelo código:

- Questão 1 → [`questao_01/resultados/relatorio_q1.md`](questao_01/resultados/relatorio_q1.md)
- Questão 2 → [`questao_02/resultados/relatorio_q2.md`](questao_02/resultados/relatorio_q2.md)

---

## Questão 1 — Operação Caixa 90

### Resposta direta

**A meta de caixa de 90 dias é atingida.** A política GA + Greedy gera **R$ 625.065,95** de caixa operacional líquido, contra meta de R$ 479.846,07: **folga de R$ 145.219,88**. Cobre **141,85%** da dívida de R$ 440.645,43, com margem de contribuição de 19,32% e sem piorar o giro do estoque (85,22% contra 84,16% da política atual). A política atual (todos os preços em 1,00) geraria R$ 546.248,68.

### "Nesta questão utilizamos 3 algoritmos"

Nesta questão utilizamos 3 algoritmos. O **Brute Force** enumera todas as combinações de preço de um subconjunto de 10 SKUs e encontra o ótimo exato. O **Algoritmo Genético** roda no mesmo subconjunto — o gap em relação ao ótimo mede a qualidade do GA — e depois no catálogo completo, onde o Brute Force é inviável (~10²² combinações). A **política de preços do GA é a entrada do Greedy**, que distribui o orçamento de incentivo comercial pelos SKUs com maior benefício marginal por real investido. Os dados passam de um algoritmo ao outro dentro de `questao_01/main.py` (variáveis `sub`, `sol_ga`, `res_gr`).

### 1.2 Objetivo e restrições

| Exigência do enunciado | Como foi tratada | Onde |
|---|---|---|
| Maximizar o caixa operacional | caixa = unidades × (preço × (1 − taxa) − custo − logística), a mesma definição que o gerador usa para a meta | `modelo.py::_precomputar` |
| Conjunto discreto de preços por SKU | 7 níveis (0,80 a 1,10) do `q1_config`; máscara de níveis permitidos por SKU | `modelo.py::permitido` |
| Margem mínima | R1: margem ≥ 7,79% (`margem_minima_percentual`) | `modelo.py` |
| Respeitar o estoque | unidades = min(estoque, demanda) | `modelo.py` |
| Evitar desconto indiscriminado | R2: desconto < 0,90 só para estoque com 120+ dias; R3: no máximo 40% dos SKUs (12) com desconto | `modelo.py`, `config/parametros_modelo.json` |
| Melhorar o giro de estoque | R4: a nova política precisa vender pelo menos o mesmo valor de estoque (a custo) que a atual (84,16%) | `modelo.py::giro` |
| Orçamento limitado de incentivos | Greedy com teto de R$ 84.576,03 | `greedy.py` |
| Informar meta, folga ou insuficiência | campo `folga_ou_insuficiencia_meta` | `main.py::resumo_financeiro` |

SKU **Q1-028** fica suspenso: nenhum preço permitido atinge a margem mínima (logística de R$ 148,93 num item de R$ 661,90).

### 1.4 Entregas técnicas

**1. Brute Force num subconjunto de pelo menos 6 produtos.** Subconjunto de **10 SKUs** (os de maior valor de estoque a custo): Q1-002, 003, 004, 005, 011, 014, 019, 024, 027 e 030. Espaço de busca de **100.800 combinações**; a DFS visitou 18.882 nós, cortando ramos que já violam R3 ou R4. **Ótimo: R$ 308.691,17.** → `brute_force.py::brute_force`, seção 1 do relatório.

**2. GA no mesmo subconjunto e gap.**

| Método | Caixa | Gap | Tempo | Memória |
|---|---|---|---|---|
| Brute Force (ótimo) | R$ 308.691,17 | — | 4,2 ms | 9,2 KiB |
| GA config A (pop. 40) | R$ 303.527,08 | 1,673% | 18,1 ms | 35,0 KiB |
| GA config B (pop. 120) | R$ 308.691,17 | **0,000%** | 48,3 ms | 73,9 KiB |

Repetido para 6, 8, 10 e 12 SKUs: a config B ficou com gap ≤ 0,024% em todos (seção 5 do relatório).

**3. GA no catálogo completo — justificativa dos parâmetros** (config B, a usada):

| Componente | Escolha | Por quê |
|---|---|---|
| Representação | vetor de inteiros, 1 gene por SKU = índice do nível de preço | só níveis permitidos podem aparecer, então R1 e R2 nunca são violadas |
| População | 120 | com 40 (config A) a variação entre seeds foi 19× maior |
| Seleção | torneio de 3 | barata, pressão seletiva moderada, funciona com fitness negativo |
| Crossover | uniforme, taxa 0,9 | SKUs não têm ordem natural; corte em um ponto criaria dependência de posição |
| Mutação | 5% por gene: metade vai para o nível vizinho, metade sorteia | ajuste fino + exploração |
| Elitismo | 2 melhores passam intactos | o melhor caixa nunca piora (testado) |
| Restrição R3 | operador de reparo | desfaz os descontos que custam menos caixa |
| Restrição R4 | penalidade + regra de Deb | qualquer solução viável vence qualquer inviável |
| Parada | 400 gerações ou 60 sem melhorar | convergiu entre as gerações 65 e 75 |

→ `genetic_algorithm.py`, `docs/decisoes.md`.

**4. Greedy para o orçamento de incentivo.** Recebe a política do GA. Para cada SKU, avalia cupons direcionados de 5%, 10% e 15%; usa um heap para escolher sempre o incremento com **maior Δcaixa por real investido**, e só aceita se a razão for ≥ 1 (o real gasto volta inteiro), se couber no saldo e se a margem continuar ≥ 7,79%. Resultado: **7 incrementos em 6 SKUs, R$ 9.921,80 investidos (11,73% do orçamento), ganho líquido de R$ 5.422,75.** O restante do orçamento não foi usado porque todo incentivo adicional devolveria menos de R$ 1 por real — reduziria o caixa. → `greedy.py::alocar_incentivos`, seção 3 do relatório.

**5. Duas configurações do GA (5 seeds cada).**

| | Config A | Config B |
|---|---|---|
| Pop. / mutação / torneio / elitismo | 40 / 0,02 / 2 / 1 | 120 / 0,05 / 3 / 2 |
| Caixa médio ± desvio | R$ 617.154,86 ± 1.781,44 | R$ 619.579,72 ± 95,24 |
| Convergência (geração do melhor) | 65 | 75 |
| Tempo médio / pico de memória | 39 ms / 91 KiB | 95 ms / 204 KiB |

**Convergência:** A sobe rápido mas estaciona mais baixo — pouca mutação e torneio de 2 reduzem a diversidade. B gasta ~2,4× tempo e memória (cresce com a população: O(P·n)) e em troca é estável entre seeds e atinge o ótimo do Brute Force. Como os tempos são de décimos de segundo, escolhemos B. → seção 2 do relatório, `fitness_por_geracao.png`.

**6. Resultado final.**

| Indicador | Política atual (1,00) | GA + Greedy |
|---|---|---|
| Caixa operacional líquido | R$ 546.248,68 | **R$ 625.065,95** |
| Meta de caixa | R$ 479.846,07 | R$ 479.846,07 |
| Folga (+) / insuficiência (−) | +R$ 66.402,61 | **+R$ 145.219,88** |
| Cobertura da dívida (R$ 440.645,43) | 123,97% | **141,85%** |
| Margem de contribuição | 17,60% | 19,32% |
| Estoque remanescente | 856 un. · R$ 383.695,41 a custo | 715 un. · R$ 358.019,19 |
| Giro do estoque (a custo) | 84,16% | 85,22% |
| Orçamento promocional usado | — | R$ 9.921,80 (11,73%) |
| SKUs com desconto | 0 | 6 (limite 12) |

**Interpretação financeira:** a maior parte do ganho vem de **subir preço onde a margem é fina** — a perda de volume é menor que o ganho por unidade. Para cumprir o giro (R4), o GA baixa o preço em 6 SKUs de estoque mais parado, escolhendo os que custam menos caixa. O caixa cobre a dívida com folga de 41,85%.

### 1.5 Evidências obrigatórias

| Evidência | Onde |
|---|---|
| Tabela Brute Force × GA no subconjunto | relatório Q1, seção 1 (e seção 5, vários tamanhos) |
| Gráfico de fitness por geração | `questao_01/resultados/fitness_por_geracao.png` |
| Tabela antes/depois do Greedy | relatório Q1, seção 3 |
| Big O de tempo e memória dos 3 algoritmos | `docs/complexidade.md` (resumo abaixo) |
| Medição com `time.perf_counter()` e `tracemalloc` | `comum/desempenho.py::medir`; relatório Q1, seção 5 |
| Otimização antes/depois | Brute Force **190× mais rápido** (itertools + recálculo → DFS + tabela + poda); fitness do GA **15× mais rápido** (laço Python → numpy vetorizado); mesmo resultado nos dois casos (relatório Q1, seção 5; testes `test_bf_ingenuo_e_otimizado_iguais`, `test_ga_vetorizado_igual_laco`) |
| Texto "Nesta questão utilizamos 3 algoritmos" | acima e no topo do relatório Q1 |

---

## Questão 2 — Plano de Sobrevivência em 12 Semanas

### Resposta direta

**O plano DP + Greedy paga as três parcelas no prazo em 100% dos 5.000 cenários de validação** (semanas 4, 8 e 12), com caixa final esperado de **R$ 199.683,00** e **P5 de R$ 182.649,66** depois de pagar R$ 188.804,72 de dívida. A probabilidade de falha (0%) está abaixo do limite de risco de 10%. Mantendo o preço atual, o caixa final esperado seria só R$ 54.790,53.

Como a dívida oficial nunca falha, o **teste de estresse** mostra a margem de segurança: o plano continua pagando 100% com parcelas até **1,75× maiores**; a política atual quebra em 1,5×.

### "Nesta questão utilizamos 3 algoritmos"

Nesta questão utilizamos 3 algoritmos. O **Monte Carlo** (2.000 cenários com demanda, preço do concorrente e custo logístico incertos) estima, para cada SKU, semana e preço, a distribuição da demanda e o custo logístico esperado. **Essas estatísticas são a transição e a recompensa da Programação Dinâmica**, que, com estado (semana, estoque restante), escolhe o preço de cada semana. **O plano de preços da DP orienta o Greedy**, que decide quais SKUs recebem os destaques semanais limitados. Por fim, **o plano completo volta ao Monte Carlo** em 5.000 cenários novos, nunca usados na construção, para medir a probabilidade de pagar cada parcela.

### 2.3 Requisitos da Programação Dinâmica

| Exigência | Resposta | Onde |
|---|---|---|
| Estado | (t, s): semana t ∈ {1..12} e estoque restante s ∈ {0..estoque inicial}, por SKU — 34.392 estados no portfólio | `dynamic_programming.py::dp_sku` |
| Decisão | nível de preço (0,82 a 1,12) ou **pausar** as vendas | idem |
| Transição | s' = s − min(s, D), com P(D = d) estimada pelo Monte Carlo | idem |
| Função objetivo | V_t(s) = max_a Σ_d P_t,a(d) · [ω_t · min(s,d) · margem_t,a + V_{t+1}(s − min(s,d))], V_13 = 0 | idem |
| Bottom-Up ou Top-Down | Bottom-Up (vetorizado); Top-Down com `lru_cache` implementado para comprovar a equivalência | `dp_sku`, `dp_sku_top_down` |
| Onde ocorre a reutilização | linha `cont = V_prox[s_idx[:, None] - vend]`: V_{t+1} é calculado uma vez e reutilizado por todos os estados, decisões e demandas da semana t. No Top-Down, o SKU Q2-005 tem 322 subproblemas distintos e **21.154 reutilizações** de cache, com o mesmo valor | relatório Q2, seção 5 |
| Caminho ótimo reconstruído | tabela SKU × semana com o nível de cada semana e o estoque | `reconstruir_caminho`; relatório Q2, seção 2 |

**O que a DP decidiu:** preço **1,12** (o mais alto) em quase todos os SKUs e semanas — com estas margens e elasticidades, subir o preço aumenta a margem total. As decisões que dependem do estado:
- **Q2-008** é **pausado** nas 12 semanas: dá prejuízo em qualquer preço (logística de R$ 123,33 num item de R$ 512,90).
- SKUs como Q2-002, 005, 006, 012, 014 e 024 **esgotam antes da semana 12** ao preço máximo — a DP vende tudo pelo maior preço possível.
- Q2-015 (o maior estoque, 499 un.) termina com 1 unidade: o preço máximo é exatamente o que esvazia o estoque no horizonte.

**Peso de urgência ρ:** a DP multiplica a margem das semanas 1–4 por (1+ρ) e das semanas 5–8 por (1+ρ/2), para antecipar caixa antes dos vencimentos. Testamos ρ ∈ {0; 0,25; 0,5; 1; 2} no Monte Carlo de construção. Com a dívida oficial todos pagam 100%, então fica ρ = 0. No estresse, o critério passa a escolher ρ > 0 (até 2,0).

### 2.4 Cenários de incerteza

| Fonte | Modelo | Parâmetro |
|---|---|---|
| Demanda | Poisson com intensidade × choque lognormal de média 1; 30% do choque é comum a todos os SKUs na semana (mercado fraco atinge todo o varejo) | σ = 0,1099 |
| Preço do concorrente | passeio aleatório lognormal semanal; elasticidade cruzada γ = 0,8 | σ = 0,0647 |
| Custo logístico | lognormal independente por semana, média = custo base | σ = 0,0654 |

**Quantidade:** 2.000 cenários na construção (seed 1025) e **5.000 independentes na validação** (seed 778802). → `monte_carlo.py`.

### 2.5 Entregas técnicas

**1. Comportamento de demanda/caixa por preço (Monte Carlo).** Para os 24 SKUs × 6 preços: demanda média, P5, P95 e caixa semanal esperado. Exemplo: Q2-015 (Moda) tem demanda média de 60,5 un./semana (P5 41, P95 83); o caixa semanal esperado é maior no nível 0,94 (R$ 10.438,33) que no 1,12 (R$ 10.061,17) — mas o estoque limitado faz a DP preferir 1,12 (vende tudo mais caro). → relatório Q2, seção 1.

**2. DP e trajetória semanal.** Ver 2.3. → relatório Q2, seção 2; figura `trajetoria_preco_estoque.png`.

**3. Greedy semanal de destaques.** Até 4 destaques por semana (+30% de demanda), custo de R$ 150 + 5% da receita esperada, teto de R$ 4.538,92 por semana. Ordena os candidatos por benefício/custo e aceita se a razão for ≥ 1,2. Resultado: **12 destaques (Q2-011 em todas as semanas), R$ 4.168,98 gastos.** Os demais candidatos tinham razão < 1,2. Com limiar 1,0, o Greedy escolheu 21 destaques e a validação mostrou **perda** líquida de R$ 732 — foi a validação que nos levou ao limiar 1,2. → `greedy.py`, relatório Q2, seção 3.

**4. Validação em cenários novos.** 5.000 cenários com seed diferente da construção, aplicados aos três planos com os mesmos números aleatórios. → `monte_carlo.py::simular`.

**5. Probabilidade de pagamento no prazo.**

| | Preço atual fixo | DP | **DP + Greedy** |
|---|---|---|---|
| P(pagar semana 4 — R$ 45.313,13) | 100% | 100% | **100%** |
| P(pagar semana 8 — R$ 58.529,46) | 100% | 100% | **100%** |
| P(pagar semana 12 — R$ 84.962,13) | 100% | 100% | **100%** |
| P(pagar as três) | 100% | 100% | **100%** |

**6. Caixa, risco, margem, estoque e falhas.**

| | Preço atual fixo | DP | **DP + Greedy** |
|---|---|---|---|
| Caixa final esperado (após as parcelas) | R$ 54.790,53 | R$ 198.150,31 | **R$ 199.683,00** |
| **P5 do caixa final** (percentil de risco do grupo) | R$ 47.892,77 | R$ 181.923,16 | **R$ 182.649,66** |
| Margem de contribuição | 13,95% | 22,35% | 22,24% |
| Estoque final médio | 670 un. · R$ 281.302,53 | 917 un. · R$ 386.458,75 | 874 un. · R$ 380.110,22 |
| Gasto com destaques | — | — | R$ 4.168,98 |

**Cenários de falha:** nenhum dos 5.000 falhou com a dívida oficial. O pior cenário ainda termina com R$ 148.846,15 de caixa; a maioria dos piores tem **choque de mercado negativo** (demanda geral baixa por várias semanas). Teste de estresse:

| Parcelas × | Preço atual | DP | DP + Greedy |
|---|---|---|---|
| 1,00 | 100% | 100% | 100% |
| 1,25 | 96,1% | 100% | 100% |
| 1,50 | 0% | 100% | 100% |
| 1,75 | 0% | 100% | 100% |
| 2,00 | 0% | 83,9% | **86,0%** |
| 2,25 | 0% | 0% | 0% |

Leitura: o ganho da DP é transformar uma empresa que quebra com 50% a mais de dívida em uma que aguenta 75% a mais; o Greedy acrescenta ~2 pontos percentuais justamente na faixa de risco (2×). → relatório Q2, seção 4; `painel_risco_q2.png`.

**7. Três tamanhos de entrada e escalabilidade.**

| Etapa | N = 8 | N = 16 | N = 24 | N = 48 |
|---|---|---|---|---|
| MC construção (2.000) | 176 ms · 23 MB | 533 ms · 45 MB | 732 ms · 67 MB | 1.403 ms · 134 MB |
| Programação Dinâmica | 5 ms · 0,2 MB | 31 ms · 3,5 MB | 37 ms · 3,5 MB | 76 ms · 4,2 MB |
| Greedy | 39 ms · 13 MB | 61 ms · 26 MB | 78 ms · 39 MB | 157 ms · 77 MB |
| MC validação (5.000) | 46 ms · 3,9 MB | 96 ms · 6,9 MB | 123 ms · 10 MB | 268 ms · 19 MB |

Monte Carlo e Greedy crescem linearmente com N. A DP cresce com o **estoque** (estados), não com N: de 8 para 16 SKUs o estoque salta de 439 para 2.151 unidades e o tempo 6×. O gargalo de memória é o MC de construção (array cenários × semanas × SKUs × preços: 35 MB com 1.000 cenários, 341 MB com 10.000). (N = 48 é o catálogo replicado.) → relatório Q2, seção 5; `docs/desempenho.md`.

### 2.6 Evidências obrigatórias

| Evidência | Onde |
|---|---|
| Diagrama MC → DP → Greedy → validação MC | `docs/arquitetura.png` (metade inferior) |
| Distribuição do caixa final | `painel_risco_q2.png` (a); tabela da seção 4 do relatório Q2 |
| Trajetória semanal de preço e estoque | `trajetoria_preco_estoque.png`; tabela da seção 2 |
| Probabilidade de pagamento de cada compromisso | tabela 5 acima; relatório Q2, seção 4 |
| Big O de MC, DP e Greedy | `docs/complexidade.md` (resumo abaixo) |
| Texto "Nesta questão utilizamos 3 algoritmos" | acima e no topo do relatório Q2 |

---

## Seção 5 — Big O (resumo; derivação completa em `docs/complexidade.md`)

| Algoritmo | Tempo | Memória | Trecho dominante | Deixa de ser viável quando… / alternativa |
|---|---|---|---|---|
| Brute Force | O(Lᵏ) (ingênuo O(Lᵏ·k)) | O(k) | recursão `dfs` | k > 12 (3 milhões de combinações; cada SKU multiplica por 5–7) → GA |
| Algoritmo Genético | O(G·P·n) | O(P·n) | `avaliar(pop)` + reparo | não garante ótimo; com n grande, aumentar P/G ou rodar várias seeds |
| Greedy (Q1) | O(n·K·log n) | O(n·K) | `heappop` | sempre viável |
| Monte Carlo | O(S·T·N·L) | O(S·T·N·L) | `rng.poisson(lam)` em `estimar_estatisticas` | memória linear em S → processar um SKU por vez |
| Programação Dinâmica | O(T·L·Σ Eᵢ·Dᵢ) | O(T·Σ Eᵢ) | produto `(… ) @ prob[t, a]` | estoques muito grandes → agrupar estoque em faixas; estado conjunto dos SKUs é inviável → DP por SKU |
| Greedy (Q2) | O(S·T·N + T·N·log N) | O(T·N) | `estimar_candidatos` | sempre viável |

Variáveis: k = SKUs do subconjunto (10), L = níveis de preço (6–7), n/N = SKUs (30/24), P = população (120), G = gerações (~70–350), K = passos de incentivo (3), S = cenários (2.000/5.000), T = semanas (12), Eᵢ = estoque do SKU i (até 499), Dᵢ = demanda máxima sorteada do SKU i (até ~160).

## Seção 6 — Testes, reprodutibilidade e execução

| Exigência | Atendida em |
|---|---|
| Seed explícita em todo componente aleatório | GA (`seed`), Monte Carlo (`gerar_cenarios(seed)`), Poisson (`seed_poisson` derivada); `--seed` na linha de comando |
| Testes de casos pequenos, limites, entradas inválidas e funções principais | 46 testes em `tests/` (ex.: instância de 3 SKUs com resposta conhecida, giro impossível, orçamento zero e negativo, população inválida, DP com margens negativas, arquivo de dados adulterado) |
| Comando único | `bash reproduzir.sh` |
| Versão do Python e dependências | `requirements.txt`; `data/manifesto_execucao.json` → `ambiente` |
| manifesto com seed, nº de SKUs, metas e hash | `data/manifesto_execucao.json` (o `manifesto_dados.json` oficial não é alterado para não mudar o hash; o de execução referencia o hash oficial e acrescenta nº de SKUs, metas, dívidas e versões) |
| Integridade da instância | todo programa recalcula os SHA-256 e para se algum arquivo foi alterado (`comum/dados.py::verificar_integridade`, teste `test_arquivo_alterado_e_detectado`) |

## Seção 7 — Cenário-surpresa (já executados)

Todos rodam só com parâmetros de linha de comando, sem mudar código nem dados (`comum/dados.py::aplicar_cenario`).

**Questão 1** — `python questao_01/main.py <opção>`

| Cenário | Opção | Caixa líquido | Meta | Folga | Cobertura da dívida | Orçamento usado |
|---|---|---|---|---|---|---|
| Base | — | R$ 625.065,95 | atingida | R$ 145.219,88 | 141,85% | R$ 9.921,80 |
| Meta de caixa +10% | `--meta-delta 0.10` | R$ 625.065,95 | atingida | R$ 97.235,27 | 141,85% | R$ 9.921,80 |
| Custo logístico +15% | `--logistica-delta 0.15` | R$ 594.760,97 | atingida | R$ 114.914,90 | 134,97% | R$ 11.479,48 |
| Orçamento −25% | `--orcamento-delta -0.25` | R$ 625.065,95 | atingida | R$ 145.219,88 | 141,85% | R$ 9.921,80 |
| SKU indisponível | `--remover-sku Q1-005` | R$ 566.246,60 | atingida | R$ 86.400,53 | 128,50% | R$ 12.378,50 |
| GA alterado | `--populacao 200 --mutacao 0.10` | R$ 622.596,28 | atingida | R$ 142.750,21 | 141,29% | R$ 7.995,46 |

Notas: com orçamento −25% nada muda porque o Greedy só usa 11,7% do orçamento. Com mutação 0,10 o GA explora demais e termina 0,4% abaixo — mesmo assim acerta o ótimo do Brute Force no subconjunto.

**Questão 2** — `python questao_02/main.py <opção>` (plano DP + Greedy; última coluna = política atual)

| Cenário | Opção | P(sem 4) | P(sem 8) | P(sem 12) | Caixa final esperado | P5 | P(3 parcelas) preço atual |
|---|---|---|---|---|---|---|---|
| Base | — | 100% | 100% | 100% | R$ 199.683,00 | R$ 182.649,66 | 100% |
| Concorrente −8% | `--concorrente-delta -0.08` | 100% | 100% | 100% | R$ 186.863,18 | R$ 167.000,27 | 100% |
| Logística +15% | `--logistica-delta 0.15` | 100% | 100% | 100% | R$ 186.209,07 | R$ 169.568,24 | 100% |
| Orçamento −25% | `--orcamento-delta -0.25` | 100% | 100% | 100% | R$ 199.683,00 | R$ 182.649,66 | 100% |
| SKU indisponível | `--remover-sku Q2-015` | 100% | 100% | 100% | R$ 92.601,49 | R$ 77.198,93 | **0%** |
| Parcelas +10% | `--divida-delta 0.10` | 100% | 100% | 100% | R$ 180.802,53 | R$ 163.769,19 | 100% |
| Todos juntos | as cinco opções acima | 100% | 100% | 100% | R$ 51.678,11 | R$ 35.599,51 | **0%** |

Leitura: perder o Q2-015 (o SKU de maior giro) faz a política atual falhar em todos os cenários, enquanto o plano da DP continua pagando. O mesmo vale para todos os choques combinados.

## Seção 9 — Como evitamos as condições que descaracterizam a solução

| Condição | Como foi evitada |
|---|---|
| Algoritmos sem integração | saídas viram entradas no mesmo `main.py`: ótimo BF → gap do GA; `sol_ga` → Greedy; `est` (MC) → DP; `plano.politicas` → Greedy; plano completo → MC de validação |
| Resultado sem evidência de execução | relatórios gerados pelo próprio código, com tempo e memória medidos |
| Big O sem justificativa | `docs/complexidade.md`: variáveis, trecho dominante, limite e alternativa |
| Só funciona na instância original | cenários-surpresa por parâmetro (tabela acima) e `--seed` |
| Resultado aleatório sem seed | toda aleatoriedade vem de `numpy.random.default_rng(seed)`; teste `test_ga_reprodutivel_por_seed` |
| Um único commit | histórico por etapa: dados → Q1 → Q2 → testes → documentação → consolidação |
| Conclusões financeiras sem ligação com métricas | cada conclusão acima cita o valor calculado e a seção do relatório |

---

## Roteiro para a defesa técnica

Perguntas prováveis e onde está a resposta no código:

1. **Por que o Brute Force não roda no catálogo completo?** São ~7²⁹ ≈ 10²² combinações; com k = 12 já leva 0,1 s para 3 milhões, e cada SKU multiplica o espaço por 5–7. (`brute_force.py::espaco_de_busca`)
2. **O GA garante o ótimo?** Não. Por isso comparamos com o Brute Force no subconjunto: gap 0% (config B). (`main.py`, seção 1)
3. **Por que existe a restrição de giro (R4)?** Sem ela o ótimo é subir quase todos os preços para 1,10: o caixa sobe para ~R$ 708 mil, mas o giro cai de 84% para 78% e sobra mais estoque parado. (`docs/decisoes.md`)
4. **Como o GA respeita as restrições?** R1/R2 pela representação (só níveis permitidos), R3 por reparo (`reparar`), R4 por penalidade com regra de Deb (`avaliar`).
5. **Por que o Greedy não gastou o orçamento todo?** Cada incentivo restante devolveria menos de R$ 1 por real; gastar reduziria o caixa. (`greedy.py`, critério `razao < roi_minimo`)
6. **Onde a DP reutiliza subproblemas?** `cont = V_prox[s_idx[:, None] - vend]` em `dp_sku`; versão `dp_sku_top_down` mostra 21 mil acertos de cache.
7. **Por que a DP é por SKU e não conjunta?** O estado conjunto teria ~10⁴⁶ combinações de estoque por semana. O acoplamento pelo caixa é avaliado no Monte Carlo (escolha de ρ e validação).
8. **Por que a DP escolhe 1,12 em quase tudo?** O caixa semanal esperado cresce com o preço para quase todos os SKUs (tabela da seção 1 do relatório Q2): a perda de volume é menor que o ganho de margem.
9. **Por que construção e validação usam seeds diferentes?** Para não avaliar o plano nos mesmos cenários em que ele foi ajustado (evita otimismo).
10. **Como mudar um parâmetro ao vivo?** Linha de comando (seção 7) ou `config/parametros_modelo.json`; nenhum arquivo de `data/` é tocado.
