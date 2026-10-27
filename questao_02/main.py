"""
Questão 2 — Plano de Sobrevivência em 12 Semanas.  Fluxo integrado:

  [A] Monte Carlo de CONSTRUÇÃO (2.000 cenários)
        └─► distribuição de demanda e custo logístico por (SKU, semana, preço)
  [B] Programação Dinâmica  (estado = semana, estoque)   ← usa as estatísticas de [A]
        └─► testa pesos de urgência ρ; escolhe pelo MC a maior P(pagar as 3 parcelas)
  [C] Greedy semanal de destaques                         ← usa o plano de preços de [B]
  [D] Monte Carlo de VALIDAÇÃO (5.000 cenários NOVOS)     ← plano completo [B]+[C]
        └─► P(pagar sem. 4, 8, 12), caixa esperado, P5, margem, estoque, falhas, estresse

Uso:
    python questao_02/main.py --seed 1025 --cenarios 5000
    python questao_02/main.py --concorrente-delta -0.08 --logistica-delta 0.15
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
from dynamic_programming import reconstruir_caminho, resolver_dp
from greedy import alocar_destaques, estimar_candidatos
from modelo import construir_instancia
from monte_carlo import estimar_estatisticas, gerar_cenarios, metricas, simular

COR = {"Preço atual fixo (1,00)": "#8b949e", "DP": "#1f6feb", "DP + Greedy": "#d1462f"}


def argumentos(argv=None):
    ap = argparse.ArgumentParser(description="Questão 2 — Monte Carlo + DP + Greedy")
    ap.add_argument("--seed", type=int, default=None, help="seed (padrão: seed_final do manifesto)")
    ap.add_argument("--cenarios", type=int, default=None, help="cenários de validação (mín. 5000)")
    ap.add_argument("--construcao", type=int, default=None, help="cenários de construção (mín. 2000)")
    ap.add_argument("--saida", type=Path, default=AQUI / "resultados")
    ap.add_argument("--concorrente-delta", type=float, default=0.0, help="ex.: -0.08 = concorrente -8%%")
    ap.add_argument("--logistica-delta", type=float, default=0.0, help="ex.: 0.15 = logística +15%%")
    ap.add_argument("--orcamento-delta", type=float, default=0.0, help="ex.: -0.25 = orçamento -25%%")
    ap.add_argument("--divida-delta", type=float, default=0.0, help="ex.: 0.10 = parcelas +10%%")
    ap.add_argument("--remover-sku", action="append", default=[], help="SKU indisponível (pode repetir)")
    ap.add_argument("--destaques", type=int, default=None, help="vagas de destaque por semana")
    ap.add_argument("--sem-estresse", action="store_true", help="pula o teste de estresse")
    ap.add_argument("--sem-desempenho", action="store_true", help="pula a medição de escalabilidade")
    return ap.parse_args(argv)


def escolher_rho(inst, est, cen, rhos):
    """Para cada ρ: resolve a DP e mede no MC de construção. Critério: maior P(3 parcelas);
    desempate pelo caixa final esperado (tolerância de 0,1%) e, por fim, pelo menor ρ."""
    linhas, planos = [], {}
    for rho in rhos:
        plano = resolver_dp(inst, est, rho)
        m = metricas(inst, simular(inst, cen, plano.politicas))
        planos[rho] = plano
        linhas.append({"rho": rho, "P_3_parcelas": m["P(pagar as 3 no prazo)"],
                       "P_sem4": m["P(pagar semana 4)"], "P_sem8": m["P(pagar semana 8)"],
                       "P_sem12": m["P(pagar semana 12)"],
                       "caixa_final_esperado": m["caixa_final_esperado"],
                       "caixa_final_P5": m["caixa_final_P5"]})
    tab = pd.DataFrame(linhas)
    # entre os ρ com a maior probabilidade, diferenças de caixa < 0,1% são ruído de simulação:
    # fica o MENOR ρ (plano mais simples, que mais preserva o caixa total)
    top = tab[tab["P_3_parcelas"] >= tab["P_3_parcelas"].max() - 1e-12]
    melhor_caixa = top["caixa_final_esperado"].max()
    top = top[top["caixa_final_esperado"] >= melhor_caixa - abs(melhor_caixa) * 1e-3]
    melhor = float(top["rho"].min())
    tab["escolhido"] = tab["rho"] == melhor
    return melhor, planos[melhor], tab


def analisar_falhas(inst, cen, res) -> tuple[pd.DataFrame, dict]:
    falha = ~res.sucesso_total
    choque = cen.choque_mercado.mean(axis=1)
    conc = cen.fator_conc[:, -1, :].mean(axis=1)
    log = (cen.logistica / inst.logistica).mean(axis=(1, 2))
    resumo = {"cenarios_falha": int(falha.sum()),
              "falhas_por_semana": {w: int((~res.pago_no_prazo[w]).sum()) for w in res.pago_no_prazo}}
    for nome, arr in (("choque_mercado_medio", choque), ("fator_concorrente_sem12", conc),
                      ("fator_logistica_medio", log)):
        resumo[nome] = {"falha": float(arr[falha].mean()) if falha.any() else None,
                        "sucesso": float(arr[~falha].mean()) if (~falha).any() else None}
    piores = np.argsort(res.caixa_final)[:20]
    tab = pd.DataFrame({"cenario": piores, "caixa_final": res.caixa_final[piores].round(2),
                        "pagou_sem4": res.pago_no_prazo[4][piores], "pagou_sem8": res.pago_no_prazo[8][piores],
                        "pagou_sem12": res.pago_no_prazo[12][piores],
                        "choque_mercado_medio": choque[piores].round(3),
                        "fator_concorrente_sem12": conc[piores].round(3),
                        "fator_logistica_medio": log[piores].round(3)})
    return tab, resumo


def graficos(inst, res_val: dict, saida: Path, reps: list[int], percentile: float, tab_estresse=None):
    """Gera 2 figuras: painel_risco_q2.png (distribuição do caixa final, caixa semanal,
    teste de estresse) e trajetoria_preco_estoque.png."""
    n_pain = 3 if tab_estresse is not None else 2
    fig, axs = plt.subplots(1, n_pain, figsize=(6.2 * n_pain, 4.8))
    # 1) distribuição do caixa final
    ax = axs[0]
    for nome, r in res_val.items():
        ax.hist(r.caixa_final / 1e3, bins=60, alpha=.55, color=COR[nome], label=nome)
        ax.axvline(np.percentile(r.caixa_final, percentile) / 1e3, color=COR[nome], ls="--", lw=1)
    ax.axvline(0, color="black", lw=1)
    ax.set_xlabel("Caixa final após as 3 parcelas (R$ mil)")
    ax.set_ylabel("nº de cenários")
    ax.set_title(f"(a) Caixa final — {len(r.caixa_final):,} cenários (tracejado = P{percentile:g})".replace(",", "."),
                 fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    # 2) caixa semana a semana (leque) do plano final
    ax = axs[1]
    r = res_val["DP + Greedy"]
    sem = np.arange(1, inst.semanas + 1)
    q = np.percentile(r.caixa_semanal, [5, 25, 50, 75, 95], axis=0) / 1e3
    ax.fill_between(sem, q[0], q[4], color="#d1462f", alpha=.15, label="P5–P95")
    ax.fill_between(sem, q[1], q[3], color="#d1462f", alpha=.3, label="P25–P75")
    ax.plot(sem, q[2], color="#d1462f", lw=2, label="mediana")
    for w, v in inst.dividas.items():
        ax.annotate(f"parcela\nR$ {v/1e3:.1f} mil".replace(".", ","), (w, q[2][w - 1]),
                    textcoords="offset points", xytext=(0, 18), ha="center", fontsize=7.5)
        ax.axvline(w, color="gray", ls=":", lw=1)
    ax.axhline(0, color="black", lw=1)
    ax.set_xlabel("Semana")
    ax.set_ylabel("Caixa ao fim da semana (R$ mil)")
    ax.set_title("(b) Caixa semanal do plano final (após as parcelas)", fontsize=10)
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=.3)
    # 3) teste de estresse
    if tab_estresse is not None:
        ax = axs[2]
        for nome in COR:
            ax.plot(tab_estresse["multiplicador_dividas"], tab_estresse[f"P(3 parcelas) — {nome}"],
                    "o-", color=COR[nome], label=nome)
        ax.axhline(1 - inst.limite_risco, color="black", ls=":", lw=1,
                   label=f"limite de risco ({inst.limite_risco:.0%} de falha)")
        ax.set_xlabel("Multiplicador das parcelas da dívida")
        ax.set_ylabel("P(pagar as 3 parcelas no prazo)")
        ax.set_title("(c) Teste de estresse — até onde cada plano aguenta", fontsize=10)
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(saida / "painel_risco_q2.png", dpi=130)
    plt.close(fig)

    # 3) trajetória de preço e estoque dos SKUs representativos
    fig, axs = plt.subplots(2, len(reps), figsize=(3.4 * len(reps), 6), sharex=True)
    for c, i in enumerate(reps):
        niv = inst.niveis_ext()[r.niveis[:, :, i]]      # NaN = pausado/esgotado
        est = r.estoque_ini[:, :, i]
        a1, a2 = axs[0, c], axs[1, c]
        a1.plot(sem, np.nanmean(niv, axis=0), "o-", color="#1f6feb", label="nível médio")
        a1.fill_between(sem, np.nanpercentile(niv, 10, axis=0), np.nanpercentile(niv, 90, axis=0),
                        color="#1f6feb", alpha=.2, label="P10–P90")
        a1.set_ylim(inst.niveis.min() - .03, inst.niveis.max() + .03)
        a1.set_title(f"{inst.skus[i]} ({inst.categoria[i]})", fontsize=9)
        a2.plot(sem, np.median(est, axis=0), "s-", color="#2da44e", label="estoque (mediana)")
        a2.fill_between(sem, np.percentile(est, 10, axis=0), np.percentile(est, 90, axis=0),
                        color="#2da44e", alpha=.2)
        a2.set_xlabel("Semana")
        if c == 0:
            a1.set_ylabel("nível de preço")
            a2.set_ylabel("estoque no início da semana")
            a1.legend(fontsize=7)
        for a in (a1, a2):
            a.grid(alpha=.3)
    fig.suptitle("Trajetória semanal de preço e estoque — plano DP + Greedy (validação)")
    fig.tight_layout()
    fig.savefig(saida / "trajetoria_preco_estoque.png", dpi=140)
    plt.close(fig)



def main(argv=None) -> dict:
    args = argumentos(argv)
    args.saida.mkdir(parents=True, exist_ok=True)
    catalogo, config, manifesto = carregar_questao(2)
    if args.saida == AQUI / "resultados":
        gerar_manifesto_execucao()
    params = carregar_parametros()
    p2 = params["questao_02"]
    seed = manifesto["seed_final"] if args.seed is None else args.seed
    n_cons = args.construcao or p2["cenarios_construcao"]
    n_val = args.cenarios or p2["cenarios_validacao"]
    if n_cons < 2000 or n_val < 5000:
        print("AVISO: o enunciado pede no mínimo 2.000 cenários de construção e 5.000 de validação.")
    k_dest = p2["destaques_por_semana"] if args.destaques is None else args.destaques
    pct = p2["percentil_risco"]

    catalogo, config = aplicar_cenario(catalogo, config, 2, meta_delta=args.divida_delta,
                                       concorrente_delta=args.concorrente_delta,
                                       logistica_delta=args.logistica_delta,
                                       orcamento_delta=args.orcamento_delta,
                                       remover_skus=args.remover_sku)
    inst = construir_instancia(catalogo, config, params)

    print("=" * 76)
    print(f"QUESTÃO 2 — Sobrevivência em 12 semanas | grupo {manifesto['grupo']} | instância {manifesto['id_instancia']}")
    print(f"seed = {seed} | SKUs = {inst.n} | parcelas = {inst.dividas} | caixa inicial = R$ {inst.caixa_inicial:,.2f}")
    print("Nesta questão utilizamos 3 algoritmos: Monte Carlo -> Programação Dinâmica -> Greedy "
          "(e o Monte Carlo de novo, para validar).")
    print("=" * 76)
    tempos = {}
    rel = Relatorio("Questão 2 — Plano de Sobrevivência em 12 Semanas",
                    f"Grupo **{manifesto['grupo']}** · instância `{manifesto['id_instancia']}` · seed **{seed}** · "
                    f"{inst.n} SKUs · {num_br(n_cons)} cenários de construção · {num_br(n_val)} de validação")
    if any([args.concorrente_delta, args.logistica_delta, args.orcamento_delta, args.divida_delta, args.remover_sku]):
        rel.texto(f"> **Cenário-surpresa aplicado:** concorrente {args.concorrente_delta:+.0%}, logística "
                  f"{args.logistica_delta:+.0%}, orçamento {args.orcamento_delta:+.0%}, parcelas "
                  f"{args.divida_delta:+.0%}, SKUs removidos: {args.remover_sku or 'nenhum'}.")
    rel.texto("**Nesta questão utilizamos 3 algoritmos.** O *Monte Carlo* (2.000 cenários) estima a "
              "distribuição da demanda e o custo logístico para cada SKU, semana e preço; essas estatísticas "
              "alimentam a *Programação Dinâmica* (estado = semana e estoque restante), que escolhe a "
              "trajetória semanal de preços; o plano da DP orienta o *Greedy*, que distribui os destaques "
              "semanais; por fim o plano completo volta ao *Monte Carlo* em cenários novos para medir o risco.")
    parcelas = " · ".join(f"semana {w}: R$ {num_br(v)}" for w, v in inst.dividas.items())
    rel.texto(f"Caixa inicial R$ {num_br(inst.caixa_inicial)} · parcelas — {parcelas} "
              f"(total R$ {num_br(sum(inst.dividas.values()))}) · orçamento promocional semanal "
              f"R$ {num_br(inst.orcamento_semanal)} · limite de risco de falha {pct_br(inst.limite_risco, 0)}.")

    # [A] Monte Carlo de construção
    cen, t, m = medir(gerar_cenarios, inst, n_cons, seed)
    est, t2, m2 = medir(estimar_estatisticas, inst, cen)
    tempos["MC construção (sorteio + estatísticas)"] = (t + t2, max(m, m2))
    print(f"\n[A] Monte Carlo de construção: {n_cons:,} cenários × {inst.semanas} semanas × {inst.n} SKUs "
          f"× {inst.L} preços  ({t + t2:.2f}s)")
    print(est.resumo[est.resumo["sku"] == inst.skus[0]].to_string(index=False))
    rel.secao("1. Monte Carlo de construção — demanda e caixa por nível de preço")
    rel.texto("Fontes de incerteza: demanda (lognormal com choque comum de mercado + Poisson), passeio "
              "aleatório do preço do concorrente e custo logístico. Tabela: **caixa semanal esperado** "
              "(R$, sem limite de estoque) de cada SKU em cada nível de preço — é o que a DP compara. "
              "Demanda média, P5 e P95 de cada combinação estão em `resumo_q2.json`.")
    piv = est.resumo.pivot(index="sku", columns="nivel", values="caixa_esperado_sem")
    piv.columns = [f"nível {num_br(c)}" for c in piv.columns]
    dem = est.resumo[est.resumo["nivel"] == 1.0].set_index("sku")[["demanda_media_sem", "demanda_p5", "demanda_p95"]]
    dem.columns = ["demanda média (1,00)", "P5", "P95"]
    rel.tabela(dem.join(piv), index=True, casas={"demanda média (1,00)": 2, "P5": 0, "P95": 0})

    # [B] Programação Dinâmica (+ escolha de ρ via MC)
    (rho, plano, tab_rho), t, m = medir(escolher_rho, inst, est, cen, p2["pesos_urgencia_rho"])
    _, t_dp, m_dp = medir(resolver_dp, inst, est, rho)
    tempos["DP (um ρ)"] = (t_dp, m_dp)
    print(f"\n[B] Programação Dinâmica — estado (semana, estoque), {inst.L} preços + pausar por estado")
    print(tab_rho.round(4).to_string(index=False))
    print(f"    ρ escolhido = {rho}  (pesos de urgência: {np.round(plano.pesos, 3).tolist()})")
    caminhos = []
    for i in range(inst.n):
        for c in reconstruir_caminho(inst, est, plano, i):
            caminhos.append({"sku": inst.skus[i], **c})
    tab_cam = pd.DataFrame(caminhos)
    rel.secao("2. Programação Dinâmica")
    rel.texto("**Estado** (semana t, estoque restante s) · **decisão** nível de preço ou pausar · "
              "**transição** s' = s − min(s, D), com D sorteado da distribuição do Monte Carlo · "
              "**objetivo** V_t(s) = max_a Σ_d P(d)·[ω_t·min(s,d)·margem + V_{t+1}(s − min(s,d))], V_13 = 0 (depois da semana 12 o estoque não vira caixa). "
              "Bottom-Up: V_{t+1} é calculado uma vez por semana e reutilizado por todos os estados, "
              "decisões e demandas da semana t.")
    rel.secao("Escolha do peso de urgência ρ (avaliada no Monte Carlo de construção)", 3)
    rel.tabela(tab_rho, casas={"rho": 2, "P_3_parcelas": 4, "P_sem4": 4, "P_sem8": 4, "P_sem12": 4})
    rel.texto(f"ρ escolhido = **{num_br(rho)}** → pesos semanais {[num_br(float(w)) for w in plano.pesos]}.")
    rel.secao("Caminho ótimo reconstruído — nível de preço por semana (vendas esperadas)", 3)
    niv = tab_cam.pivot(index="sku", columns="semana", values="nivel")
    estq = tab_cam.pivot(index="sku", columns="semana", values="estoque_inicio")
    niv.columns = [f"S{c}" for c in niv.columns]
    niv["estoque S1→S12"] = [f"{estq.loc[k].iloc[0]} → {estq.loc[k].iloc[-1]}" for k in niv.index]
    rel.tabela(niv, index=True)

    # [C] Greedy de destaques, a partir do plano da DP (simulado na construção)
    sim_cons = simular(inst, cen, plano.politicas, registrar=True)
    cand = estimar_candidatos(inst, cen, sim_cons, p2["uplift_destaque"], p2["custo_fixo_destaque"],
                              p2["custo_destaque_pct_receita"])
    (dest, custo_sem, escolhas), t, m = medir(alocar_destaques, inst, cand, k_dest, inst.orcamento_semanal,
                                              p2["destaque_roi_minimo"])
    tempos["Greedy (seleção semanal)"] = (t, m)
    print(f"\n[C] Greedy: {len(escolhas)} destaques em 12 semanas | gasto R$ {custo_sem.sum():,.2f} "
          f"de R$ {inst.orcamento_semanal * inst.semanas:,.2f} disponíveis")
    rel.secao("3. Greedy semanal de destaques")
    rel.texto(f"Até {k_dest} destaques por semana (+{pct_br(p2['uplift_destaque'], 0)} de demanda), dentro "
              f"do orçamento semanal; só entram candidatos com benefício/custo ≥ "
              f"{num_br(float(p2['destaque_roi_minimo']))}. Resultado: **{len(escolhas)} destaques**, gasto "
              f"de R$ {num_br(float(custo_sem.sum()))} de R$ {num_br(inst.orcamento_semanal * inst.semanas)} "
              "disponíveis nas 12 semanas.")
    top = cand.sort_values("razao", ascending=False).drop_duplicates("sku").head(6)
    rel.texto("Melhores candidatos por SKU (melhor semana de cada um):")
    rel.tabela(top.drop(columns="sku_idx"), casas={"razao": 3, "p_sobra": 2})
    if len(escolhas):
        rel.texto("Destaques escolhidos:")
        rel.tabela(escolhas, casas={"razao": 3})

    # [D] Monte Carlo de validação (cenários novos)
    cen_val, t, m = medir(gerar_cenarios, inst, n_val, seed + p2["offset_seed_validacao"])
    planos = {"Preço atual fixo (1,00)": dict(politica=np.full(inst.n, inst.idx_base)),
              "DP": dict(politica=plano.politicas),
              "DP + Greedy": dict(politica=plano.politicas, destaques=dest, custo_destaques=custo_sem,
                                  uplift=p2["uplift_destaque"])}
    res_val, tab_val = {}, {}
    for nome, kw in planos.items():
        t0 = time.perf_counter()
        res_val[nome] = simular(inst, cen_val, registrar=(nome == "DP + Greedy"), **kw)
        if nome == "DP + Greedy":
            tempos["MC validação (simulação do plano)"] = (time.perf_counter() - t0 + t, m)
        tab_val[nome] = metricas(inst, res_val[nome], pct)
    tab_val = pd.DataFrame(tab_val)
    print(f"\n[D] Validação Monte Carlo — {n_val:,} cenários novos (seed {seed + p2['offset_seed_validacao']})")
    print(tab_val.to_string())
    final = res_val["DP + Greedy"]
    tab_falhas, resumo_falhas = analisar_falhas(inst, cen_val, final)
    print(f"\n    cenários de falha (plano final): {resumo_falhas['cenarios_falha']} | por parcela: "
          f"{resumo_falhas['falhas_por_semana']}")

    # Teste de estresse: até onde o plano aguenta?
    tab_estresse = None
    if not args.sem_estresse:
        linhas = []
        dividas_orig = dict(inst.dividas)
        for mult in p2["estresse_multiplicador_dividas"]:
            inst.dividas = {w: v * mult for w, v in dividas_orig.items()}
            rho_m, plano_m, _ = escolher_rho(inst, est, cen, p2["pesos_urgencia_rho"])
            linha = {"multiplicador_dividas": mult, "rho_escolhido": rho_m}
            for nome, kw in (("Preço atual fixo (1,00)", dict(politica=np.full(inst.n, inst.idx_base))),
                             ("DP", dict(politica=plano_m.politicas)),
                             ("DP + Greedy", dict(politica=plano_m.politicas, destaques=dest,
                                                  custo_destaques=custo_sem, uplift=p2["uplift_destaque"]))):
                r = simular(inst, cen_val, **kw)
                linha[f"P(3 parcelas) — {nome}"] = float(r.sucesso_total.mean())
            linhas.append(linha)
        inst.dividas = dividas_orig
        tab_estresse = pd.DataFrame(linhas)
        print("\n    Teste de estresse (parcelas multiplicadas; mesma validação):")
        print(tab_estresse.to_string(index=False))

    # SKUs representativos: maior valor de estoque em categorias distintas
    valor = inst.custo * inst.estoque
    reps, cats = [], set()
    for i in np.argsort(-valor):
        if inst.categoria[i] not in cats:
            reps.append(int(i)); cats.add(inst.categoria[i])
        if len(reps) == 4:
            break
    graficos(inst, res_val, args.saida, reps, pct, tab_estresse)

    rel.secao("4. Validação Monte Carlo — risco do plano completo")
    rel.texto(f"{num_br(n_val)} cenários novos (seed {seed + p2['offset_seed_validacao']}), não usados para "
              "construir a política. Comparação com a política atual (preço 1,00 fixo) e com a DP sem o Greedy. "
              f"Percentil de risco escolhido pelo grupo: **P{pct}** do caixa final.")
    tv = tab_val.copy()
    tv.index.name = "indicador"
    tv = tv.reset_index()
    rel.partes.append(pd.DataFrame({c: [num_br(v, 4 if str(tv.loc[k, 'indicador']).startswith('P(') else 2)
                                        for k, v in tv[c].items()] if c != "indicador" else tv[c]
                                    for c in tv.columns}).to_markdown(
        index=False, colalign=["left"] + ["right"] * (len(tv.columns) - 1), disable_numparse=True) + "\n")
    rel.secao("Cenários de falha", 3)
    if resumo_falhas["cenarios_falha"] == 0:
        rel.texto("Nenhum dos cenários de validação falhou com a dívida oficial. Os 5 piores cenários "
                  "(menor caixa final) mostram o que derruba o caixa:")
    else:
        rel.texto(f"{resumo_falhas['cenarios_falha']} cenários falharam; por parcela: "
                  f"{resumo_falhas['falhas_por_semana']}. Piores cenários:")
    rel.tabela(tab_falhas.head(5), casas={"choque_mercado_medio": 3, "fator_concorrente_sem12": 3,
                                          "fator_logistica_medio": 3})
    if tab_estresse is not None:
        rel.secao("Teste de estresse — parcelas multiplicadas", 3)
        rel.tabela(tab_estresse, casas={c: 4 for c in tab_estresse.columns if c.startswith("P(")} |
                   {"multiplicador_dividas": 2, "rho_escolhido": 2})
    rel.figura("painel_risco_q2.png", "(a) distribuição do caixa final, (b) caixa semanal do plano final, "
               "(c) teste de estresse")
    rel.figura("trajetoria_preco_estoque.png", "Trajetória semanal de preço e estoque de SKUs representativos "
               "(média e faixa P10–P90 na validação)")

    # Desempenho
    tab_tempo = pd.DataFrame([{"etapa": k, "tempo_ms": v[0] * 1000, "memoria_pico_KiB": v[1]}
                              for k, v in tempos.items()])
    print("\n" + tab_tempo.round(2).to_string(index=False))
    rel.secao("5. Desempenho: tempo e memória")
    rel.texto("Nesta execução (instância oficial):")
    rel.tabela(tab_tempo, casas={"tempo_ms": 1, "memoria_pico_KiB": 1})
    desemp = None
    if not args.sem_desempenho:
        print("\n[Desempenho] medindo escalabilidade (N = 8, 16, 24, 48 SKUs)...")
        desemp = medir_desempenho(catalogo, config, params, seed, args.saida)
        rel.texto("Escalabilidade em quatro tamanhos de entrada (N = 48 é o catálogo replicado):")
        e = desemp["escala"].copy()
        e["tempo_ms"] = e.pop("tempo_s") * 1000
        rel.tabela(e, casas={"tempo_ms": 1, "memoria_KiB": 0, "estados": 0})
        rel.texto("Monte Carlo de construção variando o número de cenários:")
        mc_ = desemp["mc"].copy()
        mc_["tempo_ms"] = mc_.pop("tempo_s") * 1000
        rel.tabela(mc_, casas={"tempo_ms": 1, "memoria_KiB": 0})
        rel.texto("Reutilização de subproblemas — DP Top-Down com memoization × Bottom-Up:")
        rel.tabela(desemp["reuso"], casas={"tempo_bottom_up_s": 4, "tempo_top_down_s": 4})
        rel.figura("desempenho_q2.png", "Tempo e memória por etapa em função do número de SKUs")

    rel.salvar(args.saida / "relatorio_q2.md")
    saida = {"grupo": manifesto["grupo"], "id_instancia": manifesto["id_instancia"], "seed": seed,
             "cenario": {"concorrente_delta": args.concorrente_delta, "logistica_delta": args.logistica_delta,
                         "orcamento_delta": args.orcamento_delta, "divida_delta": args.divida_delta,
                         "remover_sku": args.remover_sku},
             "estatisticas_monte_carlo": est.resumo.to_dict(orient="records"),
             "selecao_rho": tab_rho.to_dict(orient="records"), "rho_escolhido": rho,
             "trajetoria_otima_dp": tab_cam.to_dict(orient="records"),
             "destaques": escolhas.to_dict(orient="records"), "gasto_destaques": float(custo_sem.sum()),
             "validacao": tab_val.to_dict(), "falhas": resumo_falhas,
             "piores_cenarios": tab_falhas.to_dict(orient="records"),
             "estresse": tab_estresse.to_dict(orient="records") if tab_estresse is not None else None,
             "tempo_memoria": tab_tempo.to_dict(orient="records"),
             "desempenho": {k: v.to_dict(orient="records") for k, v in desemp.items()} if desemp else None}
    with open(args.saida / "resumo_q2.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2,
                  default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(f"\nRelatório: {args.saida / 'relatorio_q2.md'}")
    return saida


if __name__ == "__main__":
    t0 = time.perf_counter()
    main()
    print(f"Tempo total: {time.perf_counter() - t0:.1f}s")
