"""Configuração dos testes.

As duas questões têm módulos com o mesmo nome (modelo.py, greedy.py, main.py).
`carregar_questao_modulos` limpa o cache de importação e carrega os módulos da
pasta pedida, para que cada arquivo de teste use os módulos da sua questão.
"""
import importlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

NOMES = ["modelo", "greedy", "brute_force", "genetic_algorithm", "monte_carlo",
         "dynamic_programming", "main", "analise_desempenho"]


def carregar_questao_modulos(pasta: str, nomes: list[str]) -> dict:
    for n in NOMES:
        sys.modules.pop(n, None)
    caminho = str(RAIZ / pasta)
    while caminho in sys.path:
        sys.path.remove(caminho)
    sys.path.insert(0, caminho)
    mods = {n: importlib.import_module(n) for n in nomes}
    sys.path.remove(caminho)
    return mods
