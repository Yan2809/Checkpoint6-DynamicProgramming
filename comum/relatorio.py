"""Relatório em Markdown gerado pelos programas (substitui os vários CSVs soltos).

Cada execução de `questao_0X/main.py` reescreve `questao_0X/resultados/relatorio_q0X.md`
com todas as tabelas, já formatadas em padrão brasileiro e legíveis direto no GitHub.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


def num_br(x, casas: int = 2) -> str:
    """1234567.891 -> '1.234.567,89'."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    if isinstance(x, (bool, np.bool_)):
        return "sim" if x else "não"
    if isinstance(x, (int, np.integer)):
        return f"{int(x):,}".replace(",", ".")
    if isinstance(x, (float, np.floating)):
        s = f"{float(x):,.{casas}f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    return str(x)


def pct_br(x, casas: int = 1) -> str:
    return num_br(x * 100, casas) + "%"


class Relatorio:
    def __init__(self, titulo: str, subtitulo: str = ""):
        self.partes = [f"# {titulo}\n"]
        if subtitulo:
            self.partes.append(subtitulo + "\n")
        self.partes.append(f"*Gerado automaticamente em {datetime.now():%d/%m/%Y %H:%M}. "
                           "Não editar à mão: rode o main.py de novo.*\n")

    def secao(self, titulo: str, nivel: int = 2):
        self.partes.append(f"\n{'#' * nivel} {titulo}\n")

    def texto(self, s: str):
        self.partes.append(s.strip() + "\n")

    def tabela(self, df: pd.DataFrame, index: bool = False, casas: dict | None = None, padrao: int = 2):
        """Tabela Markdown; `casas` define decimais por coluna (o resto usa `padrao`)."""
        casas = casas or {}
        d = df.reset_index() if index else df.copy()
        alinhamento = []
        for c in d.columns:
            numerica = pd.api.types.is_numeric_dtype(d[c]) and not pd.api.types.is_bool_dtype(d[c])
            d[c] = [num_br(v, casas.get(c, padrao)) for v in d[c]]
            alinhamento.append("right" if numerica else "left")
        self.partes.append(d.to_markdown(index=False, colalign=alinhamento, disable_numparse=True) + "\n")

    def figura(self, arquivo: str, legenda: str):
        self.partes.append(f"![{legenda}]({arquivo})\n\n*{legenda}*\n")

    def salvar(self, caminho: Path):
        Path(caminho).write_text("\n".join(self.partes), encoding="utf-8")
