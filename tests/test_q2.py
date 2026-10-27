"""Testes da Questão 2 (Monte Carlo, DP, Greedy, integração)."""
import numpy as np
import pytest
from conftest import carregar_questao_modulos

from comum.dados import carregar_parametros, carregar_questao

M = carregar_questao_modulos("questao_02", ["modelo", "monte_carlo", "dynamic_programming", "greedy", "main"])
modelo, mc, dp, gr, main_q2 = (M[k] for k in ("modelo", "monte_carlo", "dynamic_programming", "greedy", "main"))


@pytest.fixture(scope="module")
def inst():
    cat, cfg, _ = carregar_questao(2)
    return modelo.construir_instancia(cat, cfg, carregar_parametros())


@pytest.fixture(scope="module")
def cen_est(inst):
    cen = mc.gerar_cenarios(inst, 300, 11)
    return cen, mc.estimar_estatisticas(inst, cen)


# --------------------------- Monte Carlo ---------------------------- #
def test_cenarios_reprodutiveis(inst):
    a, b = mc.gerar_cenarios(inst, 50, 3), mc.gerar_cenarios(inst, 50, 3)
    assert np.array_equal(a.eps, b.eps) and np.array_equal(a.logistica, b.logistica)
    c = mc.gerar_cenarios(inst, 50, 4)
    assert not np.array_equal(a.eps, c.eps)


def test_choque_demanda_tem_media_um(inst):
    cen = mc.gerar_cenarios(inst, 4000, 1)
    assert cen.eps.mean() == pytest.approx(1.0, abs=0.01)
    assert (cen.logistica / inst.logistica).mean() == pytest.approx(1.0, abs=0.01)


def test_concorrente_mais_barato_reduz_demanda():
    cat, cfg, _ = carregar_questao(2)
    from comum.dados import aplicar_cenario
    cat2, cfg2 = aplicar_cenario(cat, cfg, 2, concorrente_delta=-0.08)
    base = modelo.construir_instancia(cat, cfg, carregar_parametros())
    corte = modelo.construir_instancia(cat2, cfg2, carregar_parametros())
    pol = np.full(base.n, base.idx_base)
    v_base = mc.simular(base, mc.gerar_cenarios(base, 300, 5), pol).receita.mean()
    v_corte = mc.simular(corte, mc.gerar_cenarios(corte, 300, 5), pol).receita.mean()
    assert v_corte < v_base


def test_cenarios_invalidos(inst):
    with pytest.raises(ValueError):
        mc.gerar_cenarios(inst, 0, 1)


def test_distribuicoes_somam_um(cen_est):
    _, est = cen_est
    for P in est.prob_demanda:
        assert np.allclose(P.sum(axis=2), 1.0)


def test_simulacao_conserva_estoque(inst, cen_est):
    cen, _ = cen_est
    res = mc.simular(inst, cen, np.full(inst.n, inst.idx_base), registrar=True)
    assert (res.estoque_final >= 0).all()
    assert np.array_equal(res.vendas.sum(axis=1) + res.estoque_final, np.broadcast_to(inst.estoque, res.estoque_final.shape))


def test_falha_quando_divida_impagavel(inst, cen_est):
    cen, _ = cen_est
    import copy
    i2 = copy.copy(inst)
    i2.dividas = {4: 1e9, 8: 1.0, 12: 1.0}
    res = mc.simular(i2, cen, np.full(inst.n, inst.idx_base))
    assert not res.pago_no_prazo[4].any()
    assert not res.pago_no_prazo[8].any()          # o atraso da semana 4 é cobrado junto
    assert (res.saldo_devedor_final > 0).all()


# ------------------------ Programação Dinâmica ---------------------- #
def test_top_down_igual_bottom_up(inst, cen_est):
    _, est = cen_est
    i = int(np.argmin(inst.estoque))
    pesos = dp.pesos_urgencia(inst, 0.5)
    V, _ = dp.dp_sku(est.prob_demanda[i], est.margem_esperada[:, i, :], int(inst.estoque[i]), pesos)
    v_td, info = dp.dp_sku_top_down(est.prob_demanda[i], est.margem_esperada[:, i, :], int(inst.estoque[i]), pesos)
    assert V[0, inst.estoque[i]] == pytest.approx(v_td)
    assert info.hits > 0                           # houve reutilização de subproblemas


def test_dp_caso_manual():
    """1 semana, estoque 1, demanda 1 com certeza: escolhe o nível de maior margem."""
    prob = np.zeros((1, 3, 2)); prob[:, :, 1] = 1.0
    margem = np.array([[5.0, 9.0, 7.0]])
    V, pol = dp.dp_sku(prob, margem, 1, np.ones(1))
    assert pol[0, 1] == 1 and V[0, 1] == pytest.approx(9.0)
    assert V[0, 0] == 0.0                          # sem estoque, nada a ganhar
    # todas as margens negativas -> pausar (índice 3) e valor zero
    V, pol = dp.dp_sku(prob, -margem, 1, np.ones(1))
    assert pol[0, 1] == 3 and V[0, 1] == 0.0


def test_dp_valor_monotono_no_estoque(inst, cen_est):
    """Como pausar é permitido, ter mais estoque nunca pode valer menos."""
    _, est = cen_est
    plano = dp.resolver_dp(inst, est, 0.0)
    for V in plano.valores:
        assert np.all(np.diff(V[0]) >= -1e-6)


def test_dp_pausa_sku_com_prejuizo(inst, cen_est):
    """Q2-008 tem margem negativa em todos os preços: a DP deve pausar as vendas."""
    _, est = cen_est
    i = list(inst.skus).index("Q2-008")
    assert (est.margem_esperada[:, i, :] < 0).all()
    plano = dp.resolver_dp(inst, est, 0.0)
    assert (plano.politicas[i][:, 1:] == inst.L).all()


def test_dp_melhor_que_preco_fixo(inst, cen_est):
    cen, est = cen_est
    plano = dp.resolver_dp(inst, est, 0.0)
    r_dp = mc.simular(inst, cen, plano.politicas)
    r_fx = mc.simular(inst, cen, np.full(inst.n, inst.idx_base))
    assert r_dp.contribuicao.mean() >= r_fx.contribuicao.mean()


def test_pesos_urgencia(inst):
    w = dp.pesos_urgencia(inst, 1.0)
    assert w[0] == pytest.approx(2.0) and w[4] == pytest.approx(1.5) and w[-1] == pytest.approx(1.0)
    assert np.allclose(dp.pesos_urgencia(inst, 0.0), 1.0)


def test_caminho_reconstruido(inst, cen_est):
    _, est = cen_est
    plano = dp.resolver_dp(inst, est, 0.0)
    cam = dp.reconstruir_caminho(inst, est, plano, 0)
    assert len(cam) == inst.semanas
    assert all(c["estoque_inicio"] >= 0 for c in cam)
    assert [c["estoque_inicio"] for c in cam] == sorted([c["estoque_inicio"] for c in cam], reverse=True)


# ------------------------------ Greedy ------------------------------ #
def test_greedy_respeita_vagas_e_orcamento(inst, cen_est):
    cen, est = cen_est
    plano = dp.resolver_dp(inst, est, 0.0)
    sim = mc.simular(inst, cen, plano.politicas, registrar=True)
    cand = gr.estimar_candidatos(inst, cen, sim, 0.3, 150.0, 0.05)
    dest, custo, esc = gr.alocar_destaques(inst, cand, 2, 500.0, roi_minimo=0.0)
    assert (dest.sum(axis=1) <= 2).all()
    assert (custo <= 500.0 + 1e-6).all()


def test_greedy_exige_registro(inst, cen_est):
    cen, _ = cen_est
    sim = mc.simular(inst, cen, np.full(inst.n, inst.idx_base))
    with pytest.raises(ValueError):
        gr.estimar_candidatos(inst, cen, sim, 0.3, 150.0, 0.05)


def test_greedy_vagas_negativas(inst, cen_est):
    with pytest.raises(ValueError):
        gr.alocar_destaques(inst, None, -1, 100.0)


# ---------------------------- integração ---------------------------- #
def test_fluxo_completo_cenario_surpresa(tmp_path):
    out = main_q2.main(["--construcao", "300", "--cenarios", "500", "--saida", str(tmp_path),
                        "--concorrente-delta", "-0.08", "--logistica-delta", "0.15", "--sem-estresse",
                        "--sem-desempenho"])
    v = out["validacao"]["DP + Greedy"]
    assert 0.0 <= v["P(pagar as 3 no prazo)"] <= 1.0
    assert (tmp_path / "painel_risco_q2.png").exists()
