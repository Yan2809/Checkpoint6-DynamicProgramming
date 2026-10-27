"""
Questão 1 — Operação Caixa 90.  Fluxo integrado:

    dados oficiais ─► modelo (tabelas por SKU × nível)
         │
         ├─► [A] Brute Force no subconjunto (k SKUs) ──► ótimo exato
         │        └─► [B] GA no MESMO subconjunto ──► gap % vs ótimo  (validação do GA)
         │
         └─► [B] GA no catálogo completo (configs A e B) ──► melhor política de preços
                   └─► [C] Greedy recebe a política do GA ──► aloca orçamento de incentivo
                             └─► resultado financeiro final (caixa, margem, estoque, dívida)

Uso:
    python questao_01/main.py --seed 1025 --modo completo
    python questao_01/main.py --meta-delta 0.10 --orcamento-delta -0.25 --remover-sku Q1-005
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parent))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from comum.dados import aplicar_cenario, carregar_parametros, carregar_questao, gerar_manifesto_execucao
from comum.relatorio import Relatorio, num_br, pct_br
from comum.desempenho import medir
from analise_desempenho import medir_desempenho
from brute_force import brute_force, escolher_subconjunto, espaco_de_busca
from genetic_algorithm import ConfigGA, executar_ga
from greedy import ResultadoGreedy, alocar_incentivos, tabela_antes_depois
from modelo import construir_instancia, tabela_politica


def argumentos(argv=None):
    ap = argparse.ArgumentParser(description="Questão 1 — Brute Force + GA + Greedy")
    ap.add_argument("--seed", type=int, default=None, help="seed dos algoritmos (padrão: seed_final do manifesto)")
    ap.add_argument("--modo", choices=["rapido", "completo"], default="completo",
                    help="completo = 5 seeds por config do GA + medição de desempenho (pequena/média/grande)")
    ap.add_argument("--saida", type=Path, default=AQUI / "resultados")
    # cenário-surpresa (aplicado em memória)
    ap.add_argument("--meta-delta", type=float, default=0.0, help="ex.: 0.10 = meta de caixa +10%%")
    ap.add_argument("--logistica-delta", type=float, default=0.0, help="ex.: 0.15 = custo logístico +15%%")
    ap.add_argument("--orcamento-delta", type=float, default=0.0, help="ex.: -0.25 = orçamento promocional -25%%")
    ap.add_argument("--remover-sku", action="append", default=[], help="SKU indisponível (pode repetir)")
    ap.add_argument("--populacao", type=int, help="sobrescreve a população do GA (config B)")
    ap.add_argument("--mutacao", type=float, help="sobrescreve a taxa de mutação do GA (config B)")
    ap.add_argument("--subconjunto", type=int, help="tamanho do subconjunto do Brute Force")
    return ap.parse_args(argv)


def resumo_financeiro(inst, sol, res_greedy) -> dict:
    r = np.arange(inst.n)
    unid = res_greedy.unidades
    preco = inst.preco_tab[r, sol]
    receita = float((unid * preco).sum())
    caixa_bruto = float(res_greedy.caixa_bruto.sum())
    gasto = float(res_greedy.gasto.sum())
    caixa_liq = caixa_bruto - gasto
    restante = inst.estoque - unid
    vendido_custo = float((unid * inst.custo).sum())
    return {
        "receita_90d": round(receita, 2),
        "caixa_operacional_bruto": round(caixa_bruto, 2),
        "gasto_incentivos": round(gasto, 2),
        "caixa_operacional_liquido": round(caixa_liq, 2),
        "margem_contribuicao_pct": round(caixa_liq / receita * 100, 2) if receita else 0.0,
        "unidades_vendidas": int(unid.sum()),
        "estoque_inicial_unid": int(inst.estoque.sum()),
        "estoque_remanescente_unid": int(restante.sum()),
        "estoque_remanescente_valor_custo": round(float((restante * inst.custo).sum()), 2),
        "giro_valor_custo_pct": round(vendido_custo / inst.valor_estoque_total * 100, 2),
        "meta_caixa_90d": inst.meta_caixa,
        "meta_atingida": bool(caixa_liq >= inst.meta_caixa),
        "folga_ou_insuficiencia_meta": round(caixa_liq - inst.meta_caixa, 2),
        "divida_total_90d": inst.divida,
        "cobertura_divida_pct": round(caixa_liq / inst.divida * 100, 2),
        "orcamento_promocional": inst.orcamento,
        "orcamento_usado": round(res_greedy.orcamento_usado, 2),
        "orcamento_usado_pct": round(res_greedy.orcamento_usado / inst.orcamento * 100, 2) if inst.orcamento else 0.0,
        "skus_com_desconto": inst.n_descontos(sol),
        "limite_skus_com_desconto": inst.limite_descontos,
        "skus_suspensos": inst.skus_suspensos(),
    }


def grafico_fitness(historicos: dict, caminho: Path, ref: float | None = None):
    fig, ax = plt.subplots(figsize=(9, 4.8))
    cores = {"A": "#1f6feb", "B": "#d1462f"}
    for nome, (melhor, media) in historicos.items():
        g = np.arange(1, len(melhor) + 1)
        ax.plot(g, np.array(melhor) / 1e3, color=cores.get(nome, None), lw=2, label=f"Config {nome} — melhor")
        ax.plot(g, np.array(media) / 1e3, color=cores.get(nome, None), lw=1, ls="--", alpha=.6,
                label=f"Config {nome} — média da população")
    if ref is not None:
        ax.axhline(ref / 1e3, color="gray", lw=1, ls=":", label="Política atual (preço 1,00)")
    ax.set_xlabel("Geração")
    ax.set_ylabel("Fitness (caixa, R$ mil)")
    ax.set_title("GA — fitness por geração (catálogo completo)")
    ax.grid(alpha=.3)
    ax.legend(fontsize=8, loc="lower right")
    lo = min(min(m) for _, m in historicos.values())
    ax.set_ylim(bottom=max(lo, (ref or lo) * 0.9) / 1e3 * 0.98)
    fig.tight_layout()
    fig.savefig(caminho, dpi=140)
    plt.close(fig)


def main(argv=None) -> dict:
    args = argumentos(argv)
    args.saida.mkdir(parents=True, exist_ok=True)
    catalogo, config, manifesto = carregar_questao(1)
    if args.saida == AQUI / "resultados":
        gerar_manifesto_execucao()
    params = carregar_parametros()
    p1 = params["questao_01"]
    seed = manifesto["seed_final"] if args.seed is None else args.seed

    catalogo, config = aplicar_cenario(catalogo, config, 1, meta_delta=args.meta_delta,
                                       logistica_delta=args.logistica_delta,
                                       orcamento_delta=args.orcamento_delta,
                                       remover_skus=args.remover_sku)
    inst = construir_instancia(catalogo, config, params)

    cfg_A = ConfigGA.de_dict(p1["ga_config_A"])
    cfg_B = ConfigGA.de_dict(p1["ga_config_B"])
    for c in (cfg_A, cfg_B):
        c.penalidade_giro = p1["penalidade_giro_ga"]
    if args.populacao:
        cfg_B.populacao = args.populacao
    if args.mutacao is not None:
        cfg_B.taxa_mutacao = args.mutacao

    print("=" * 72)
    print(f"QUESTÃO 1 — Operação Caixa 90 | grupo {manifesto['grupo']} | instância {manifesto['id_instancia']}")
    print(f"seed dos algoritmos = {seed} | SKUs = {inst.n} | níveis = {[float(x) for x in inst.niveis]}")
    print(f"giro mínimo (R4) = {inst.giro_minimo_frac:.2%} do estoque a custo | "
          f"máx. SKUs com desconto (R3) = {inst.limite_descontos}")
    print("Nesta questão utilizamos 3 algoritmos: Brute Force -> Algoritmo Genético -> Greedy.")
    print("=" * 72)

    rel = Relatorio("Questão 1 — Operação Caixa 90",
                    f"Grupo **{manifesto['grupo']}** · instância `{manifesto['id_instancia']}` · "
                    f"seed dos algoritmos **{seed}** · {inst.n} SKUs")
    if any([args.meta_delta, args.logistica_delta, args.orcamento_delta, args.remover_sku]):
        rel.texto(f"> **Cenário-surpresa aplicado:** meta {args.meta_delta:+.0%}, logística "
                  f"{args.logistica_delta:+.0%}, orçamento {args.orcamento_delta:+.0%}, "
                  f"SKUs removidos: {args.remover_sku or 'nenhum'}.")
    rel.texto("**Nesta questão utilizamos 3 algoritmos.** O *Brute Force* calcula o ótimo exato num "
              "subconjunto pequeno; o *Algoritmo Genético* roda no mesmo subconjunto (o gap mede sua "
              "qualidade) e depois no catálogo completo; a política de preços do GA é a entrada do "
              "*Greedy*, que distribui o orçamento de incentivo comercial.")
    rel.texto(f"Restrições: margem mínima {pct_br(inst.margem_minima, 2)} (R1); desconto abaixo de "
              f"{num_br(inst.limiar_profundo)} só para estoque com {inst.idade_minima_profundo}+ dias (R2); "
              f"no máximo {inst.limite_descontos} SKUs com desconto (R3); giro do estoque a custo "
              f"≥ {pct_br(inst.giro_minimo_frac, 2)}, o giro da política atual (R4). SKUs sem preço viável "
              f"(suspensos): {', '.join(inst.skus_suspensos()) or 'nenhum'}.")

    # ---------------- [A] Brute Force + [B] GA no subconjunto ---------------- #
    k = args.subconjunto or p1["subconjunto_brute_force"]
    idx_sub = escolher_subconjunto(inst, k)
    sub = inst.subconjunto(idx_sub)
    (sol_bf, val_bf, nos), t_bf, m_bf = medir(brute_force, sub)
    linhas = [{"metodo": "Brute Force (ótimo)", "caixa": round(val_bf, 2), "gap_pct": 0.0,
               "tempo_ms": t_bf * 1000, "memoria_pico_KiB": m_bf,
               "avaliacoes": nos, "viavel": sub.viavel(sol_bf),
               "politica": " ".join(sub.nivel_rotulo(j) for j in sol_bf)}]
    for nome, cfg in (("A", cfg_A), ("B", cfg_B)):
        res, t, m = medir(executar_ga, sub, cfg, seed)
        gap = max(0.0, (val_bf - res.melhor_caixa) / val_bf * 100)
        linhas.append({"metodo": f"GA config {nome}", "caixa": round(res.melhor_caixa, 2),
                       "gap_pct": gap, "tempo_ms": t * 1000, "memoria_pico_KiB": m,
                       "avaliacoes": res.avaliacoes, "viavel": sub.viavel(res.melhor_sol),
                       "politica": " ".join(sub.nivel_rotulo(j) for j in res.melhor_sol)})
    tab_bf = pd.DataFrame(linhas)
    print(f"\n[A] Brute Force no subconjunto de {k} SKUs ({', '.join(sub.skus)})")
    print(f"    espaço de busca = {espaco_de_busca(sub):,} combinações | nós visitados = {nos:,}")
    print(tab_bf.drop(columns="politica").round(4).to_string(index=False))
    rel.secao("1. Brute Force × Algoritmo Genético (subconjunto)")
    rel.texto(f"Subconjunto: os {k} SKUs de maior valor de estoque a custo ({', '.join(sub.skus)}). "
              f"Espaço de busca: {num_br(espaco_de_busca(sub))} combinações; a DFS visitou "
              f"{num_br(nos)} nós (podas de R3/R4). A coluna *política* lista o nível de preço de cada SKU, "
              "na ordem acima.")
    rel.tabela(tab_bf, casas={"gap_pct": 3, "tempo_ms": 1, "memoria_pico_KiB": 1})

    # ---------------- [B] GA no catálogo completo ---------------- #
    print("\n[B] Algoritmo Genético no catálogo completo")
    resultados_ga, historicos, linhas_cfg = {}, {}, []
    seeds_teste = [seed + s for s in range(5)] if args.modo == "completo" else [seed]
    for nome, cfg in (("A", cfg_A), ("B", cfg_B)):
        vals, gens, tempos, mems = [], [], [], []
        for s in seeds_teste:
            res, t, m = medir(executar_ga, inst, cfg, s)
            vals.append(res.melhor_caixa); gens.append(res.geracoes); tempos.append(t); mems.append(m)
            if s == seed:
                resultados_ga[nome] = res
                historicos[nome] = (res.historico_melhor, res.historico_media)
        linhas_cfg.append({"config": nome, "populacao": cfg.populacao, "mutacao": cfg.taxa_mutacao,
                           "torneio": cfg.torneio, "elitismo": cfg.elitismo, "seeds": len(seeds_teste),
                           "caixa_melhor": max(vals), "caixa_medio": float(np.mean(vals)),
                           "caixa_desvio": float(np.std(vals)), "geracoes_media": float(np.mean(gens)),
                           "geracao_do_melhor": resultados_ga[nome].geracao_melhor,
                           "avaliacoes": resultados_ga[nome].avaliacoes,
                           "tempo_medio_ms": float(np.mean(tempos)) * 1000, "memoria_pico_KiB": max(mems)})
    tab_cfg = pd.DataFrame(linhas_cfg)
    print(tab_cfg.round(2).to_string(index=False))

    escolhido = max(resultados_ga, key=lambda n: resultados_ga[n].melhor_caixa)
    sol_ga = resultados_ga[escolhido].melhor_sol
    assert inst.viavel(sol_ga), "GA retornou política inviável"
    sol_base = inst.solucao_base()
    grafico_fitness(historicos, args.saida / "fitness_por_geracao.png", ref=inst.caixa(sol_base))
    print(f"    política escolhida: config {escolhido} | caixa = R$ {inst.caixa(sol_ga):,.2f} | "
          f"giro = {inst.giro(sol_ga):.2%} | SKUs com desconto = {inst.n_descontos(sol_ga)}")
    rel.secao("2. Algoritmo Genético no catálogo completo — duas configurações")
    rel.texto(f"Cada configuração rodou com {len(seeds_teste)} seed(s) a partir de {seed}. "
              f"Política escolhida: **config {escolhido}** (maior caixa na seed {seed}).")
    rel.tabela(tab_cfg, casas={"mutacao": 2, "geracoes_media": 1, "tempo_medio_ms": 1, "memoria_pico_KiB": 1})
    rel.figura("fitness_por_geracao.png", "Fitness (caixa) por geração — melhor indivíduo e média da população")

    # ---------------- [C] Greedy recebe a política do GA ---------------- #
    print("\n[C] Greedy: alocação do orçamento de incentivo sobre a política do GA")
    res_gr, t_gr, m_gr = medir(alocar_incentivos, inst, sol_ga, p1["incentivo_passos"],
                               p1["incentivo_saliencia_beta"], p1["incentivo_roi_minimo"],
                               p1["incentivo_canibalizacao_alfa"])
    tab_gr = tabela_antes_depois(inst, sol_ga, res_gr)
    print(tab_gr[tab_gr["incentivo_pct"] > 0].to_string(index=False))
    print(f"    orçamento usado: R$ {res_gr.orcamento_usado:,.2f} de R$ {inst.orcamento:,.2f} | "
          f"ganho líquido: R$ {tab_gr['ganho_liquido'].sum():,.2f}")
    rel.secao("3. Política de preços (GA) e Greedy de incentivos — antes/depois")
    rel.texto(f"O Greedy recebeu a política do GA e investiu **R$ {num_br(res_gr.orcamento_usado)}** de "
              f"R$ {num_br(inst.orcamento)} ({pct_br(res_gr.orcamento_usado / inst.orcamento) if inst.orcamento else '—'}), com ganho "
              f"líquido de **R$ {num_br(float(tab_gr['ganho_liquido'].sum()))}**. Só entram incentivos "
              f"com retorno ≥ {num_br(float(p1['incentivo_roi_minimo']))} real por real investido; o restante do "
              "orçamento reduziria o caixa. Tempo do Greedy: "
              f"{num_br(t_gr * 1000, 3)} ms, pico de memória {num_br(m_gr, 1)} KiB.")
    pol = tabela_politica(inst, sol_ga)
    tab_completa = pol[["sku", "categoria", "nivel", "preco"]].merge(
        tab_gr.drop(columns="nivel_preco_GA"), on="sku")
    rel.tabela(tab_completa, casas={"incentivo_pct": 2})
    if res_gr.log_decisoes:
        rel.secao("Ordem das escolhas do Greedy", 3)
        rel.tabela(pd.DataFrame(res_gr.log_decisoes), casas={"razao": 3})

    # ---------------- resultado final ---------------- #
    r = np.arange(inst.n)
    nulo = ResultadoGreedy(np.full(inst.n, -1), np.zeros(inst.n), inst.unidades_tab[r, sol_base],
                           inst.caixa_tab[r, sol_base], np.zeros(inst.n), 0.0, [])
    final = resumo_financeiro(inst, sol_ga, res_gr)
    base = resumo_financeiro(inst, sol_base, nulo)
    linhas_fin = ["receita_90d", "caixa_operacional_bruto", "gasto_incentivos", "caixa_operacional_liquido",
                  "margem_contribuicao_pct", "unidades_vendidas", "estoque_remanescente_unid",
                  "estoque_remanescente_valor_custo", "giro_valor_custo_pct", "meta_caixa_90d",
                  "meta_atingida", "folga_ou_insuficiencia_meta", "divida_total_90d", "cobertura_divida_pct",
                  "orcamento_usado", "orcamento_usado_pct", "skus_com_desconto"]
    comparativo = pd.DataFrame({"indicador": linhas_fin,
                                "politica_atual_1,00": [base[k] for k in linhas_fin],
                                "GA_+_Greedy": [final[k] for k in linhas_fin]})
    print("\n" + "=" * 72 + "\nRESULTADO FINAL\n" + "=" * 72)
    print(comparativo.to_string(index=False))
    rel.secao("4. Resultado financeiro final")
    status = "atingida" if final["meta_atingida"] else "NÃO atingida"
    rel.texto(f"Meta de caixa **{status}**: caixa líquido de R$ {num_br(final['caixa_operacional_liquido'])} "
              f"contra meta de R$ {num_br(final['meta_caixa_90d'])} → "
              f"{'folga' if final['folga_ou_insuficiencia_meta'] >= 0 else 'insuficiência'} de "
              f"R$ {num_br(abs(final['folga_ou_insuficiencia_meta']))}. Cobertura da dívida: "
              f"{num_br(final['cobertura_divida_pct'])}%.")
    rel.partes.append(pd.DataFrame({
        "Indicador": comparativo["indicador"],
        "Política atual (1,00)": [num_br(v) for v in comparativo["politica_atual_1,00"]],
        "GA + Greedy": [num_br(v) for v in comparativo["GA_+_Greedy"]],
    }).to_markdown(index=False, colalign=("left", "right", "right"), disable_numparse=True) + "\n")

    # ---------------- desempenho (modo completo) ---------------- #
    desemp = None
    if args.modo == "completo":
        print("\n[Desempenho] medindo tempo e memória em entradas pequena, média e grande...")
        desemp = medir_desempenho(catalogo, config, params, seed, args.saida)
        rel.secao("5. Desempenho: tempo e memória")
        rel.texto("Tempo com `time.perf_counter()`, memória com `tracemalloc` (execução separada). "
                  "n = 60 e 120 são o catálogo replicado, só para medir escala. Análise em "
                  "`docs/complexidade.md` e `docs/desempenho.md`.")
        d = desemp["desempenho"].copy()
        d["tempo_ms"] = d.pop("tempo_s") * 1000
        rel.tabela(d, casas={"tempo_ms": 3, "memoria_KiB": 1, "tempo_por_geracao_ms": 3, "espaco": 0, "geracoes": 0})
        rel.figura("desempenho_q1.png", "Escalabilidade de tempo e memória dos três algoritmos")
        rel.secao("Otimização demonstrada (antes × depois)", 3)
        o = desemp["otimizacao"].copy()
        o["antes_ms"], o["depois_ms"] = o.pop("antes_s") * 1000, o.pop("depois_s") * 1000
        rel.tabela(o, casas={"speedup": 1, "antes_mem_KiB": 1, "depois_mem_KiB": 1, "antes_ms": 2, "depois_ms": 2})
        rel.secao("Gap do GA para vários tamanhos de subconjunto", 3)
        rel.tabela(desemp["gaps"], casas={"gap_pct": 3, "espaco": 0})

    rel.salvar(args.saida / "relatorio_q1.md")
    saida = {
        "grupo": manifesto["grupo"], "id_instancia": manifesto["id_instancia"], "seed": seed,
        "cenario": {"meta_delta": args.meta_delta, "logistica_delta": args.logistica_delta,
                    "orcamento_delta": args.orcamento_delta, "remover_sku": args.remover_sku},
        "brute_force_vs_ga": tab_bf.to_dict(orient="records"),
        "configs_ga": tab_cfg.to_dict(orient="records"),
        "ga_config_escolhida": escolhido,
        "politica_precos": dict(zip(pol["sku"], pol["nivel"])),
        "greedy": {"tempo_s": t_gr, "memoria_pico_KiB": m_gr, "decisoes": res_gr.log_decisoes},
        "resultado_final": final, "politica_atual": base,
        "desempenho": {k: v.to_dict(orient="records") for k, v in desemp.items()} if desemp else None,
    }
    with open(args.saida / "resumo_q1.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2,
                  default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(f"\nRelatório: {args.saida / 'relatorio_q1.md'}")
    return saida


if __name__ == "__main__":
    t0 = time.perf_counter()
    main()
    print(f"Tempo total: {time.perf_counter() - t0:.1f}s")
