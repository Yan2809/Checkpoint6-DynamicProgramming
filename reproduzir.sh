#!/usr/bin/env bash
# Reproduz todos os resultados a partir da instância oficial em data/ (~70 s).
# Saída: questao_0X/resultados/relatorio_q0X.md (+ resumo JSON e gráficos) e data/manifesto_execucao.json
set -euo pipefail
cd "$(dirname "$0")"
SEED=1025
python questao_01/main.py --seed "$SEED" --modo completo
python questao_02/main.py --seed "$SEED" --cenarios 5000
python docs/gerar_arquitetura.py
python -m pytest -q tests
