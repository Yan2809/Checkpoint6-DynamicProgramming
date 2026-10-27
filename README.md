# Checkpoint 6 — Recuperação financeira de varejistas por precificação online

FIAP · Dynamic Programming · Prof. André Marques

## Identificação da instância

| | |
|---|---|
| **Grupo** | G01 |
| **Seed base** | 25 |
| **Seed final** | 1025  (1000 × 1 + 25) |
| **ID da instância** | `386e6252eb25` |
| **SHA-256 do conjunto** | `386e6252eb251ad5b0b4133d2412e074e70e10e18d7cc43957e6cf63003b7750` |

| Integrante | RM |
|---|---|
| Yan Breno Barutti Conceição | 566412 |
| Luiz Antonio Morais Santos | 562142 |
| Nicolas Barnabe da Cruz | 561997 |
| Guilherme de Melo Sorrilha | 563825 |
| Kevin Carvalho Venancio | 561459 |

Os arquivos de `data/` foram gerados pelo notebook oficial (`gerador/Gerador_Inputs_Checkpoint_6.ipynb`), alterando **apenas o Bloco 02**. Todo programa confere os hashes de `data/manifesto_dados.json` ao carregar os dados (`comum/dados.py::verificar_integridade`) e para se algum arquivo tiver sido alterado.

## Por onde começar

| Arquivo | O que tem |
|---|---|
| **[`RESPOSTAS.md`](RESPOSTAS.md)** | resposta de cada item do enunciado, com números, evidências, cenários-surpresa e roteiro da defesa |
| [`questao_01/resultados/relatorio_q1.md`](questao_01/resultados/relatorio_q1.md) | todas as tabelas da Questão 1, geradas pelo código |
| [`questao_02/resultados/relatorio_q2.md`](questao_02/resultados/relatorio_q2.md) | todas as tabelas da Questão 2, geradas pelo código |
| [`docs/`](docs) | arquitetura, Big O, desempenho e decisões de modelagem |

## Como reproduzir

```bash
python -m pip install -r requirements.txt               # Python 3.13 (testado 3.13.17)
python questao_01/main.py --seed 1025 --modo completo   # Brute Force -> GA -> Greedy (+ desempenho)
python questao_02/main.py --seed 1025 --cenarios 5000   # Monte Carlo -> DP -> Greedy -> validação (+ desempenho)
python -m pytest -q tests                               # 46 testes
```
Ou tudo de uma vez: `bash reproduzir.sh` (~70 s). Cada `main.py` reescreve o relatório da questão, o resumo em JSON, os gráficos e `data/manifesto_execucao.json`. Para uma execução rápida: `--modo rapido` (Q1) ou `--sem-desempenho --sem-estresse` (Q2).

### Cenário-surpresa (sem alterar código nem dados)

```bash
python questao_01/main.py --meta-delta 0.10          # meta de caixa +10%
python questao_01/main.py --orcamento-delta -0.25    # orçamento promocional -25%
python questao_01/main.py --logistica-delta 0.15     # custo logístico +15%
python questao_01/main.py --remover-sku Q1-005       # SKU indisponível (pode repetir)
python questao_01/main.py --populacao 200 --mutacao 0.10   # parâmetros do GA
python questao_02/main.py --concorrente-delta -0.08  # concorrente reduz preço 8%
python questao_02/main.py --divida-delta 0.10 --destaques 2 --remover-sku Q2-015
```
Para não sobrescrever os resultados oficiais, acrescente `--saida /outra/pasta`. Os cenários são aplicados em memória (`comum/dados.py::aplicar_cenario`); os arquivos de `data/` nunca são reescritos. Parâmetros de modelagem do grupo: `config/parametros_modelo.json`. Resultados de todos os cenários da seção 7 do enunciado: `RESPOSTAS.md`.

## Resumo dos resultados (seed 1025)

**Questão 1 — Nesta questão utilizamos 3 algoritmos:** Brute Force → Algoritmo Genético → Greedy. Caixa líquido em 90 dias de **R$ 625.065,95** (meta de R$ 479.846,07 atingida, folga de R$ 145.219,88; cobertura da dívida de 141,85%). O GA (config B) atinge o ótimo do Brute Force no subconjunto de 10 SKUs (gap 0%).

**Questão 2 — Nesta questão utilizamos 3 algoritmos:** Monte Carlo → Programação Dinâmica → Greedy, com validação final em Monte Carlo. Probabilidade de pagar as parcelas das semanas 4, 8 e 12: **100% em 5.000 cenários novos**; caixa final esperado de R$ 199.683,00 (P5 R$ 182.649,66). O plano aguenta parcelas até 1,75× maiores; a política atual quebra em 1,5×.

## Onde está cada resultado

| Resultado | Arquivo | Função que produz |
|---|---|---|
| Integridade da instância | `data/manifesto_dados.json` (oficial) | `comum/dados.py::verificar_integridade` |
| Manifesto da seção 6 (seed, nº SKUs, metas, hash, versões) | `data/manifesto_execucao.json` | `comum/dados.py::gerar_manifesto_execucao` |
| Brute Force × GA | relatório Q1, seção 1 | `brute_force.py::brute_force`, `genetic_algorithm.py::executar_ga` |
| Configurações do GA e fitness por geração | relatório Q1, seção 2; `fitness_por_geracao.png` | `main.py::grafico_fitness` |
| Política de preços e Greedy antes/depois | relatório Q1, seção 3 | `modelo.py::tabela_politica`, `greedy.py::tabela_antes_depois` |
| Resultado financeiro Q1 | relatório Q1, seção 4 | `main.py::resumo_financeiro` |
| Desempenho e otimização Q1 | relatório Q1, seção 5; `desempenho_q1.png` | `analise_desempenho.py::medir_desempenho` |
| Estatísticas do Monte Carlo | relatório Q2, seção 1 | `monte_carlo.py::estimar_estatisticas` |
| DP: escolha de ρ e caminho ótimo | relatório Q2, seção 2 | `main.py::escolher_rho`, `dynamic_programming.py::reconstruir_caminho` |
| Destaques do Greedy | relatório Q2, seção 3 | `greedy.py::alocar_destaques` |
| Validação, falhas e estresse | relatório Q2, seção 4; `painel_risco_q2.png`, `trajetoria_preco_estoque.png` | `monte_carlo.py::simular`, `main.py::analisar_falhas` |
| Escalabilidade e reuso de subproblemas | relatório Q2, seção 5; `desempenho_q2.png` | `analise_desempenho.py::medir_desempenho` |

Todos os números também ficam em `resultados/resumo_q0X.json`, para quem quiser processar.

## Estrutura

```
avaliacao-varejo-grupo01/
├── README.md  RESPOSTAS.md  IA_USO.md  requirements.txt  reproduzir.sh
├── config/parametros_modelo.json      parâmetros de modelagem do grupo
├── data/                              instância oficial + manifestos (não editar)
├── gerador/                           notebook oficial (só o Bloco 02 alterado)
├── comum/                             leitura + integridade, cenários, medição, relatório
├── questao_01/  modelo  brute_force  genetic_algorithm  greedy  analise_desempenho  main
│   └── resultados/  relatorio_q1.md  resumo_q1.json  fitness_por_geracao.png  desempenho_q1.png
├── questao_02/  modelo  monte_carlo  dynamic_programming  greedy  analise_desempenho  main
│   └── resultados/  relatorio_q2.md  resumo_q2.json  painel_risco_q2.png
│                    trajetoria_preco_estoque.png  desempenho_q2.png
├── tests/                             pytest (46 testes)
└── docs/  arquitetura.png  complexidade.md  desempenho.md  decisoes.md
```

### Trocar o código do grupo
Se o código oficial não for G01: editar `GRUPO` no Bloco 02 do notebook, executar todos os blocos, copiar a pasta gerada para `data/` e rodar `bash reproduzir.sh`. Os relatórios mudam sozinhos; os números citados em `RESPOSTAS.md` e neste README precisam ser atualizados à mão.
