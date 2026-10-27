"""Integridade da instância oficial e cenários-surpresa."""
import shutil

import pytest

from comum.dados import PASTA_DADOS, aplicar_cenario, carregar_questao, verificar_integridade


def test_manifesto_confere_com_arquivos():
    man = verificar_integridade()
    assert man["grupo"] == "G01"
    assert man["seed_base"] == 25            # 2 + 2 + 7 + 5 + 9
    assert man["seed_final"] == 1025         # 1000 * 1 + 25


def test_arquivo_alterado_e_detectado(tmp_path):
    for f in PASTA_DADOS.iterdir():
        shutil.copy(f, tmp_path / f.name)
    alvo = tmp_path / "q1_catalogo_G01.csv"
    alvo.write_text(alvo.read_text(encoding="utf-8-sig").replace("Q1-001", "Q1-999"), encoding="utf-8-sig")
    with pytest.raises(ValueError, match="alterados"):
        verificar_integridade(tmp_path)


def test_cenario_nao_altera_original():
    cat, cfg, _ = carregar_questao(1)
    meta = cfg["meta_caixa_90d"]
    cat2, cfg2 = aplicar_cenario(cat, cfg, 1, meta_delta=0.10, orcamento_delta=-0.25,
                                 logistica_delta=0.15, remover_skus=["Q1-005"])
    assert cfg["meta_caixa_90d"] == meta
    assert cfg2["meta_caixa_90d"] == pytest.approx(meta * 1.10, abs=0.01)
    assert len(cat2) == len(cat) - 1 and "Q1-005" not in set(cat2["sku"])
    assert cat2["custo_logistico"].iloc[0] == pytest.approx(cat["custo_logistico"].iloc[0] * 1.15)


def test_cenario_sku_inexistente():
    cat, cfg, _ = carregar_questao(2)
    with pytest.raises(ValueError):
        aplicar_cenario(cat, cfg, 2, remover_skus=["NAO-EXISTE"])


def test_cenario_concorrente_q2():
    cat, cfg, _ = carregar_questao(2)
    cat2, cfg2 = aplicar_cenario(cat, cfg, 2, concorrente_delta=-0.08)
    assert (cat2["preco_concorrente_base"] < cat["preco_concorrente_base"]).all()
    assert cfg2["choque_concorrente"] == pytest.approx(-0.08)


def test_manifesto_execucao_tem_campos_da_secao_6(tmp_path):
    from comum.dados import gerar_manifesto_execucao
    m = gerar_manifesto_execucao(tmp_path / "m.json")
    assert m["seed_final"] == 1025 and m["sha256_conjunto"]
    assert m["questao_01"]["quantidade_skus"] == 30 and m["questao_02"]["quantidade_skus"] == 24
    assert m["questao_01"]["meta_caixa_90d"] > 0 and m["questao_02"]["divida_total"] > 0
    assert m["ambiente"]["python"]


def test_formatacao_brasileira():
    from comum.relatorio import num_br, pct_br
    assert num_br(1234567.891) == "1.234.567,89"
    assert num_br(16050) == "16.050"
    assert pct_br(0.0779, 2) == "7,79%"
