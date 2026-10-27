# Decisões de modelagem e justificativas

Os parâmetros citados aqui estão em `config/parametros_modelo.json`. Nenhum deles altera a instância oficial; todos podem mudar no cenário-surpresa.

## Comuns às duas questões

- **Caixa = margem de contribuição** (preço × (1 − taxa) − custo − logística, por unidade vendida). É a mesma definição que o notebook gerador usa para calcular a meta de caixa (Q1) e as parcelas da dívida (Q2). Usar outra definição tornaria a comparação com a meta e a dívida inconsistente. Interpretação: o custo unitário é devido aos fornecedores, então só a margem fica livre para pagar a dívida.
- **Elasticidade constante**: demanda = base × m^(−elasticidade), onde m é o multiplicador do preço. Simples, usa o campo `elasticidade` do dado e é o modelo padrão em precificação.
- **Integridade**: todo programa recalcula os SHA-256 e compara com o manifesto antes de ler os dados.

## Questão 1

### Restrições

| | Regra | Por quê |
|---|---|---|
| R1 | margem unitária / preço ≥ `margem_minima_percentual` (7,79%) | exigida no enunciado; vira máscara de níveis permitidos |
| R2 | níveis < 0,90 só para SKUs com estoque de 120+ dias | desconto profundo reservado para estoque envelhecido (usa `idade_estoque_dias`) |
| R3 | no máximo 40% dos SKUs com preço < 1,00 | "evitar política de descontos indiscriminada" |
| R4 | valor vendido (a custo) ≥ giro da política atual (84,16%) | ver abaixo |

**Por que R4 existe.** Sem ela, o ótimo é trivial: subir o preço de quase tudo para 1,10. Com as margens desta instância, o volume perdido não compensa a margem ganha (caixa sobe para R$ 708 mil), mas o giro cai de 84% para 78% e sobra mais estoque parado. Isso contraria o objetivo do enunciado (caixa **e** giro). Exigir que a nova política gire pelo menos tanto quanto a atual obriga a decidir **onde** baixar preço, acopla os SKUs e torna o problema combinatório de verdade — o que justifica Brute Force e GA. O valor de referência vem dos próprios dados (giro da política atual), não de um número escolhido por nós.

**SKU sem preço viável.** Q1-028 não atinge 7,79% de margem em nenhum nível (logística de R$ 148,93 sobre um preço de R$ 661,90). Fica "suspenso" (não vende); isso é reportado na saída.

### Brute Force
- Subconjunto: os 10 SKUs com maior valor de estoque a custo (os de maior impacto financeiro), excluindo suspensos. 100.800 combinações; ainda roda em milissegundos.
- A versão otimizada só poda ramos **inviáveis** (R3 estourada ou R4 inalcançável mesmo vendendo o máximo no resto). Não usamos poda por limite de caixa (branch-and-bound), para continuar sendo uma enumeração completa das soluções viáveis.

### Algoritmo Genético
- **Representação**: vetor de inteiros, um gene por SKU com o índice do nível; genes só assumem níveis permitidos, então R1 e R2 nunca são violadas.
- **População**: 120 (config B). Com 40 (A) a variância entre seeds foi 19× maior.
- **Seleção**: torneio de 3 — pressão moderada, barata (O(P)) e sem depender da escala do fitness, que pode ser negativo.
- **Crossover**: uniforme, taxa 0,9. Como os SKUs não têm ordem natural, o crossover de um ponto criaria dependência artificial da posição.
- **Mutação**: 0,05 por gene; metade vira o nível vizinho (ajuste fino), metade um nível aleatório (exploração).
- **Elitismo**: 2 melhores passam intactos, então o melhor fitness nunca piora (testado).
- **R3**: operador de reparo que desfaz os descontos que custam menos caixa.
- **R4**: penalidade com regra de viabilidade (Deb): qualquer solução viável vence qualquer inviável; entre inviáveis vence a de menor déficit. Antes usávamos só penalidade linear (λ = 10) e um teste encontrou o GA devolvendo uma solução inviável com caixa maior — a regra de Deb resolveu.
- **Parada**: 400 gerações ou 60 sem melhorar.
- **Warm start**: a política atual entra na população inicial, garantindo um indivíduo viável desde a geração 0.

### Greedy (incentivos)
- Incentivo = **cupom/cashback direcionado** de 5%, 10% ou 15%. Um cupom dado a todos os compradores é economicamente igual a um corte de preço (e com estas margens nunca se paga: testamos e o ROI máximo foi 0,57). Direcionado, paga-se o cupom nas vendas incrementais e numa fração α = 25% das vendas que já aconteceriam (canibalização).
- β = 1,6: o consumidor reage mais a cupom/cashback do que a um corte de preço equivalente. É uma premissa, fica no arquivo de parâmetros.
- Critério guloso: maior Δcaixa bruto / Δgasto, aceito só com razão ≥ 1 (cada real precisa voltar inteiro). Por isso o caixa líquido nunca piora e o orçamento não é gasto todo — gastar o resto **reduziria** o caixa.
- A margem líquida após o incentivo também precisa respeitar R1.

## Questão 2

### Incerteza (Monte Carlo)
- **Demanda**: Poisson com intensidade λ (vendas são contagens inteiras e pequenas, 3 a 60 por semana) multiplicada por um choque lognormal de média 1 e σ = `sigma_demanda`. O choque tem um componente comum a todos os SKUs na semana (correlação ρ = 0,3), porque uma semana fraca de mercado afeta todo o varejo ao mesmo tempo; sem isso, o risco do portfólio seria subestimado.
- **Concorrente**: passeio aleatório lognormal (σ = `sigma_preco_concorrente` por semana); preço do concorrente subindo aumenta nossa demanda com elasticidade cruzada γ = 0,8.
- **Logística**: lognormal independente por semana, média = custo base.
- 2.000 cenários de construção e 5.000 de validação com seeds diferentes (1025 e 778802). Os cenários são sorteados uma vez e usados por todas as políticas comparadas (números aleatórios comuns).

### Programação Dinâmica
- Estado (semana, estoque) por SKU, como pedido. O estado conjunto de 24 SKUs é inviável (∏ (estoque+1) ≈ 10⁴⁶ estados por semana), então a DP é separada por SKU, e o acoplamento pelo caixa é tratado de duas formas: (1) peso de urgência ω_t que valoriza o caixa antes dos vencimentos; (2) a escolha de ρ é feita pela probabilidade de pagar as três parcelas, medida no MC de construção.
- **Pausar** é uma decisão permitida: para Q2-008 (margem negativa em qualquer preço) vender só gera prejuízo. Sem essa opção, a DP era obrigada a vender e o valor da DP diminuía com mais estoque — um teste pegou isso.
- Terminal V_T = 0: o estoque que sobra não vira caixa no horizonte.
- Empate entre decisões (ex.: estoque zero): fica o maior índice (preço maior / pausar).
- Seleção de ρ: maior P(3 parcelas); diferenças de caixa < 0,1% são tratadas como ruído e vence o menor ρ. No cenário oficial ρ = 0; no estresse a escolha passa a ser ρ > 0 (0,25 a 2,0), antecipando vendas para cobrir as parcelas.

### Greedy (destaques)
- Até 4 destaques por semana (+30% de demanda), custo = R$ 150 + 5% da receita esperada do SKU na semana, limitado ao orçamento semanal.
- O benefício é multiplicado pela probabilidade de o SKU ainda ter estoque no fim: se ele esgota de qualquer forma, o destaque só antecipa vendas.
- **ROI mínimo de 1,2** (e não 1,0): com 1,0, o Greedy escolheu 21 destaques com ganho estimado positivo, mas a validação em cenários novos mostrou **perda líquida de R$ 732**, porque a estimativa superestimou o SKU Q2-017. Com 1,2 a validação dá ganho líquido. O próprio fluxo de validação do enunciado corrigiu o parâmetro.

### Leitura do risco
Com a dívida oficial, nenhum dos 5.000 cenários falha — o caixa base cobre as parcelas com folga. Por isso acrescentamos o teste de estresse (parcelas × 1,25 até × 2,25), que mostra o ponto em que cada plano quebra. O percentil de risco escolhido é o **P5** do caixa final (o caixa que se tem em 95% dos cenários).
