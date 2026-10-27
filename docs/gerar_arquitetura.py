"""Gera docs/arquitetura.png (fluxo dos algoritmos das duas questões). Uso: python docs/gerar_arquitetura.py"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

AZUL, VERM, VERDE, CINZA, ROXO = "#1f6feb", "#d1462f", "#2da44e", "#57606a", "#8250df"


def caixa(ax, x, y, w, h, titulo, texto, cor):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=cor + "18", ec=cor, lw=1.8))
    ax.text(x + w / 2, y + h - 0.17, titulo, ha="center", va="top", fontsize=10.5, weight="bold", color=cor)
    ax.text(x + w / 2, y + h / 2 - 0.12, texto, ha="center", va="center", fontsize=8, color="#24292f")


def seta(ax, a, b, rotulo="", cor=CINZA, curva=0.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=14, lw=1.5, color=cor,
                                 connectionstyle=f"arc3,rad={curva}"))
    if rotulo:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 0.12, rotulo, ha="center", fontsize=7.5,
                color=cor, style="italic")


fig, ax = plt.subplots(figsize=(15, 9))
ax.set_xlim(0, 15)
ax.set_ylim(0, 9)
ax.axis("off")

ax.text(7.5, 8.75, "Arquitetura — dados oficiais → algoritmos integrados → resultados", ha="center",
        fontsize=14, weight="bold")
caixa(ax, 0.2, 6.2, 2.6, 2.0, "Instância oficial",
      "gerador/ notebook (Bloco 02)\nseed_final = 1025\ndata/*.csv, *.json\nmanifesto SHA-256\n(verificado ao carregar)", CINZA)
caixa(ax, 0.2, 3.6, 2.6, 2.0, "Cenário / parâmetros",
      "config/parametros_modelo.json\n+ flags de linha de comando\n(meta, concorrente, logística,\norçamento, SKU removido, GA)", CINZA)

# Questão 1
ax.text(9.0, 8.15, "QUESTÃO 1 — Operação Caixa 90", ha="center", fontsize=11.5, weight="bold", color=AZUL)
caixa(ax, 3.4, 6.2, 2.7, 1.7, "Modelo Q1", "tabelas SKU × nível:\ncaixa, unidades, giro\nmáscara R1 (margem) e R2\n(desconto profundo)", AZUL)
caixa(ax, 6.6, 6.75, 2.5, 1.15, "[A] Brute Force", "subconjunto k=10\nótimo exato (DFS)", AZUL)
caixa(ax, 6.6, 5.35, 2.5, 1.15, "[B] Algoritmo Genético", "subconjunto → gap %\ncatálogo completo", AZUL)
caixa(ax, 9.7, 5.35, 2.4, 1.15, "[C] Greedy (heap)", "orçamento de incentivo\nmaior Δcaixa / R$", AZUL)
caixa(ax, 12.6, 5.6, 2.2, 2.3, "Resultado Q1", "caixa líquido 90d\nmeta: folga/insuf.\ncobertura da dívida\nmargem, giro,\nestoque, orçamento", AZUL)
seta(ax, (6.1, 7.2), (6.6, 7.3))
seta(ax, (6.1, 6.6), (6.6, 6.0))
seta(ax, (7.85, 6.75), (7.85, 6.5), "", AZUL)
ax.text(8.0, 6.57, "ótimo valida o GA", fontsize=7.5, color=AZUL, style="italic")
seta(ax, (9.1, 5.9), (9.7, 5.9), "política de preços", AZUL)
seta(ax, (12.1, 5.9), (12.6, 6.3), "", AZUL)

# Questão 2
ax.text(9.0, 4.35, "QUESTÃO 2 — Sobrevivência em 12 semanas", ha="center", fontsize=11.5, weight="bold", color=VERM)
caixa(ax, 3.4, 2.1, 2.7, 1.9, "[A] Monte Carlo\nconstrução", "2.000 cenários\ndemanda · concorrente ·\nlogística (+choque comum)", VERM)
caixa(ax, 6.6, 2.1, 2.5, 1.9, "[B] Prog. Dinâmica", "estado (semana, estoque)\ndecisão: preço ou pausar\nescolhe ρ pelo MC", VERM)
caixa(ax, 9.7, 2.1, 2.4, 1.9, "[C] Greedy semanal", "K destaques/semana\norçamento semanal\nmaior benefício / custo", VERM)
caixa(ax, 12.6, 2.1, 2.2, 1.9, "[D] Monte Carlo\nvalidação", "5.000 cenários NOVOS\nP(sem 4, 8, 12)\ncaixa, P5, falhas", VERM)
seta(ax, (6.1, 3.05), (6.6, 3.05), "P[D=d], E[logística]", VERM)
seta(ax, (9.1, 3.05), (9.7, 3.05), "plano de preços", VERM)
seta(ax, (12.1, 3.05), (12.6, 3.05), "plano completo", VERM)
seta(ax, (7.85, 2.1), (4.75, 2.1), "", ROXO, curva=-0.35)
ax.text(6.3, 1.2, "política simulada no MC de construção → seleção de ρ e estimativa do Greedy",
        ha="center", fontsize=7.5, color=ROXO, style="italic")
caixa(ax, 9.7, 0.15, 5.1, 1.0, "Teste de estresse", "parcelas ×1,0 … ×2,25 → ponto de ruptura de cada plano", VERM)
seta(ax, (13.7, 2.1), (13.0, 1.15), "", VERM)

seta(ax, (2.8, 7.2), (3.4, 7.05))
seta(ax, (2.8, 6.6), (3.4, 3.2), "", CINZA, curva=0.25)
seta(ax, (2.8, 4.6), (3.4, 6.4), "", CINZA, curva=-0.2)
seta(ax, (2.8, 4.2), (3.4, 2.8), "", CINZA, curva=0.15)

fig.tight_layout()
fig.savefig(Path(__file__).with_name("arquitetura.png"), dpi=140)
