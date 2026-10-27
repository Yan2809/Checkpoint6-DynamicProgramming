"""Testes da Questão 1 (modelo, Brute Force, GA, Greedy, integração)."""
import numpy as np
import pandas as pd
import pytest
from conftest import carregar_questao_modulos

from comum.dados import carregar_parametros, carregar_questao

M = carregar_questao_modulos("questao_01", ["modelo", "brute_force", "genetic_algorithm", "greedy", "main"])
modelo, bf, ga, gr, main_q1 = (M[k] for k in ("modelo", "brute_force", "genetic_algorithm", "greedy", "main"))


@pytest.fixture(scope="module")
def inst():
    cat, cfg, _ = carregar_questao(1)
    return modelo.construir_instancia(cat, cfg, carregar_parametros())


def mini_instancia(**kw):
    """Instância artificial de 3 SKUs com resposta conhecida."""
    cat = pd.DataFrame({
        "sku": ["A", "B", "C"], "categoria": ["x"] * 3,
        "custo_unitario": [50.0, 50.0, 50.0], "preco_atual": [100.0, 100.0, 100.0],
        "estoque": [100, 100, 100], "demanda_base_90d": [50, 50, 50],
        "elasticidade": [1.5, 1.5, 1.5], "taxa_marketplace": [0.1, 0.1, 0.1],
        "custo_logistico": [5.0, 5.0, 5.0], "idade_estoque_dias": [200, 200, 10],
    })
    cfg = {"niveis_preco_relativos": [0.9, 1.0, 1.1], "margem_minima_percentual": 0.05,
           "meta_caixa_90d": 1000.0, "divida_total_90d": 1000.0, "orcamento_promocional": 500.0}
    par = {"questao_01": {"max_fracao_skus_com_desconto": kw.get("frac", 0.34),
                          "limiar_desconto_profundo": 0.95, "idade_minima_desconto_profundo_dias": 120,
                          "giro_minimo": kw.get("giro", 0.0)}}
    return modelo.construir_instancia(cat, cfg, par)


# ------------------------------ modelo ------------------------------ #
def test_tabela_caixa_formula(inst):
    i, j = 0, inst.idx_base
    p = inst.preco_atual[i]
    q = min(inst.estoque[i], round(inst.demanda_base[i]))
    esperado = q * (p * (1 - inst.taxa[i]) - inst.custo[i] - inst.logistica[i])
    assert inst.caixa_tab[i, j] == pytest.approx(esperado)


def test_margem_minima_respeitada(inst):
    ok = inst.permitido[:, :inst.L]
    u = inst.margem_unit_tab[:, :inst.L]
    p = inst.preco_tab[:, :inst.L]
    assert (u[ok] / p[ok] >= inst.margem_minima - 1e-9).all()


def test_desconto_profundo_so_estoque_velho():
    mi = mini_instancia()
    # nível 0.90 < limiar 0.95: permitido em A e B (200 dias), proibido em C (10 dias)
    assert mi.permitido[0, 0] and mi.permitido[1, 0] and not mi.permitido[2, 0]


def test_sku_sem_nivel_viavel_fica_suspenso(inst):
    for sku in inst.skus_suspensos():
        i = list(inst.skus).index(sku)
        assert inst.opcoes(i).tolist() == [inst.L]


def test_viavel_rejeita_formato_errado(inst):
    assert not inst.viavel(np.zeros(inst.n + 1, dtype=int))


# --------------------------- brute force ---------------------------- #
def test_bf_ingenuo_e_otimizado_iguais(inst):
    sub = inst.subconjunto(bf.escolher_subconjunto(inst, 6))
    _, v1, _ = bf.brute_force_ingenuo(sub)
    _, v2, _ = bf.brute_force(sub)
    assert v1 == pytest.approx(v2)


def test_bf_resposta_conhecida_mini():
    mi = mini_instancia(frac=0.34)               # no máximo 1 SKU com desconto
    sol, val, _ = bf.brute_force(mi)
    assert mi.viavel(sol)
    # confere contra enumeração manual
    import itertools
    melhor = max(mi.caixa(np.array(c)) for c in itertools.product(*[mi.opcoes(i) for i in range(3)])
                 if mi.viavel(np.array(c)))
    assert val == pytest.approx(melhor)


def test_bf_sem_solucao_viavel_levanta_erro():
    mi = mini_instancia(giro=0.99)               # giro impossível de atingir
    with pytest.raises(ValueError):
        bf.brute_force(mi)


# ------------------------------- GA --------------------------------- #
def test_ga_reprodutivel_por_seed(inst):
    cfg = ga.ConfigGA(populacao=20, max_geracoes=30, paciencia=30)
    a, b = ga.executar_ga(inst, cfg, 7), ga.executar_ga(inst, cfg, 7)
    assert a.melhor_caixa == b.melhor_caixa
    assert (a.melhor_sol == b.melhor_sol).all()


def test_ga_retorna_solucao_viavel_e_nao_piora(inst):
    res = ga.executar_ga(inst, ga.ConfigGA(populacao=30, max_geracoes=60), 1)
    assert inst.viavel(res.melhor_sol)
    assert all(np.diff(res.historico_melhor) >= -1e-9)          # elitismo: o melhor nunca cai


def test_ga_atinge_otimo_no_subconjunto(inst):
    sub = inst.subconjunto(bf.escolher_subconjunto(inst, 8))
    _, otimo, _ = bf.brute_force(sub)
    res = ga.executar_ga(sub, ga.ConfigGA(populacao=120, taxa_mutacao=0.05, max_geracoes=300), 1025)
    assert (otimo - res.melhor_caixa) / otimo < 0.01             # gap < 1%


def test_ga_vetorizado_igual_laco(inst):
    pop = ga.AlgoritmoGenetico(inst, ga.ConfigGA(), 0)._sortear_niveis(10)
    a = ga.AlgoritmoGenetico(inst, ga.ConfigGA(vetorizado=True), 0).avaliar(pop)
    b = ga.AlgoritmoGenetico(inst, ga.ConfigGA(vetorizado=False), 0).avaliar(pop)
    assert np.allclose(a, b)


def test_reparo_respeita_limite_de_descontos(inst):
    alg = ga.AlgoritmoGenetico(inst, ga.ConfigGA(), 0)
    ind = np.array([inst.opcoes(i)[0] for i in range(inst.n)])   # tudo no menor preço
    alg.reparar(ind)
    assert inst.n_descontos(ind) <= inst.limite_descontos


@pytest.mark.parametrize("cfg", [dict(populacao=1), dict(populacao=10, elitismo=10), dict(taxa_mutacao=1.5)])
def test_ga_parametros_invalidos(inst, cfg):
    with pytest.raises(ValueError):
        ga.AlgoritmoGenetico(inst, ga.ConfigGA(**cfg), 0)


# ----------------------------- Greedy ------------------------------- #
def test_greedy_respeita_orcamento_e_nao_piora_caixa(inst):
    sol = inst.solucao_base()
    res = gr.alocar_incentivos(inst, sol, orcamento=5000.0)
    assert res.orcamento_usado <= 5000.0 + 1e-6
    assert res.gasto.sum() == pytest.approx(res.orcamento_usado)
    assert (res.caixa_bruto - res.gasto).sum() >= inst.caixa(sol) - 1e-6   # ROI >= 1


def test_greedy_orcamento_zero(inst):
    res = gr.alocar_incentivos(inst, inst.solucao_base(), orcamento=0.0)
    assert res.orcamento_usado == 0 and (res.incentivo_pct == 0).all()


def test_greedy_entradas_invalidas(inst):
    with pytest.raises(ValueError):
        gr.alocar_incentivos(inst, inst.solucao_base(), orcamento=-1)
    with pytest.raises(ValueError):
        gr.alocar_incentivos(inst, inst.solucao_base(), passos=(0.10, 0.05))


def test_greedy_margem_minima_apos_incentivo(inst):
    sol = inst.solucao_base()
    res = gr.alocar_incentivos(inst, sol, roi_minimo=0.0)      # aceita tudo que a margem permitir
    r = np.arange(inst.n)
    u, p = inst.margem_unit_tab[r, sol], inst.preco_tab[r, sol]
    com = res.incentivo_pct > 0
    assert ((u[com] - res.incentivo_pct[com] * p[com]) / p[com] >= inst.margem_minima - 1e-9).all()


# --------------------------- integração ----------------------------- #
def test_fluxo_completo_cenario_surpresa(tmp_path):
    out = main_q1.main(["--modo", "rapido", "--saida", str(tmp_path), "--orcamento-delta", "-0.25",
                        "--meta-delta", "0.10", "--remover-sku", "Q1-005", "--populacao", "40"])
    fin = out["resultado_final"]
    assert fin["orcamento_usado"] <= fin["orcamento_promocional"] + 1e-6
    assert (tmp_path / "fitness_por_geracao.png").exists()
    rel = (tmp_path / "relatorio_q1.md").read_text(encoding="utf-8")
    assert "Cenário-surpresa aplicado" in rel and "Nesta questão utilizamos 3 algoritmos" in rel
    assert out["brute_force_vs_ga"][0]["viavel"]
