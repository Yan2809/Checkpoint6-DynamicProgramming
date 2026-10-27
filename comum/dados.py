"""
Leitura da instância oficial do grupo com verificação de integridade.

Os arquivos em data/ são os gerados pelo notebook oficial (gerador/). Eles NUNCA são
alterados: cenários-surpresa são aplicados em memória por `aplicar_cenario`.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PASTA_DADOS = RAIZ / "data"
ARQ_PARAMETROS = RAIZ / "config" / "parametros_modelo.json"


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def carregar_manifesto(pasta: Path = PASTA_DADOS) -> dict:
    with open(pasta / "manifesto_dados.json", encoding="utf-8") as f:
        return json.load(f)


def verificar_integridade(pasta: Path = PASTA_DADOS) -> dict:
    """Recalcula o SHA-256 de cada arquivo e compara com o manifesto.

    Levanta ValueError se algum arquivo tiver sido alterado depois da geração.
    """
    manifesto = carregar_manifesto(pasta)
    divergentes = []
    for nome, esperado in manifesto["arquivos"].items():
        atual = sha256_arquivo(pasta / nome)
        if atual != esperado:
            divergentes.append(nome)
    if divergentes:
        raise ValueError(f"Arquivos alterados após a geração: {divergentes}")
    hash_conjunto = hashlib.sha256(
        "".join(manifesto["arquivos"][k] for k in sorted(manifesto["arquivos"])).encode("utf-8")
    ).hexdigest()
    if hash_conjunto != manifesto["sha256_conjunto"]:
        raise ValueError("Hash do conjunto não confere com o manifesto.")
    return manifesto


def carregar_questao(questao: int, pasta: Path = PASTA_DADOS, verificar: bool = True):
    """Retorna (catalogo DataFrame, config dict, manifesto dict) da questão 1 ou 2."""
    manifesto = verificar_integridade(pasta) if verificar else carregar_manifesto(pasta)
    grupo = manifesto["grupo"]
    catalogo = pd.read_csv(pasta / f"q{questao}_catalogo_{grupo}.csv", encoding="utf-8-sig")
    with open(pasta / f"q{questao}_config_{grupo}.json", encoding="utf-8") as f:
        config = json.load(f)
    return catalogo, config, manifesto


def carregar_parametros(caminho: Path = ARQ_PARAMETROS) -> dict:
    """Parâmetros de modelagem definidos pelo grupo (não fazem parte da instância oficial)."""
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def aplicar_cenario(catalogo: pd.DataFrame, config: dict, questao: int,
                    meta_delta: float = 0.0,
                    concorrente_delta: float = 0.0,
                    logistica_delta: float = 0.0,
                    orcamento_delta: float = 0.0,
                    remover_skus: list[str] | None = None):
    """Aplica um cenário-surpresa EM MEMÓRIA, sem tocar nos arquivos oficiais.

    Deltas são relativos: 0.10 = +10%, -0.25 = -25%.
    """
    cat = catalogo.copy()
    cfg = copy.deepcopy(config)

    if remover_skus:
        desconhecidos = set(remover_skus) - set(cat["sku"])
        if desconhecidos:
            raise ValueError(f"SKUs inexistentes: {sorted(desconhecidos)}")
        cat = cat[~cat["sku"].isin(remover_skus)].reset_index(drop=True)

    col_log = "custo_logistico" if questao == 1 else "custo_logistico_base"
    cat[col_log] = cat[col_log] * (1 + logistica_delta)

    if questao == 1:
        cfg["meta_caixa_90d"] = round(cfg["meta_caixa_90d"] * (1 + meta_delta), 2)
        cfg["orcamento_promocional"] = round(cfg["orcamento_promocional"] * (1 + orcamento_delta), 2)
    else:
        cat["preco_concorrente_base"] = cat["preco_concorrente_base"] * (1 + concorrente_delta)
        # a demanda_base foi calibrada com o preço ORIGINAL do concorrente; o modelo precisa
        # saber o deslocamento para reduzir/aumentar a demanda (ver questao_02/modelo.py)
        cfg["choque_concorrente"] = (1 + cfg.get("choque_concorrente", 0.0)) * (1 + concorrente_delta) - 1
        cfg["orcamento_promocional_semanal"] = round(
            cfg["orcamento_promocional_semanal"] * (1 + orcamento_delta), 2)
        if meta_delta:
            cfg["dividas"] = {k: round(v * (1 + meta_delta), 2) for k, v in cfg["dividas"].items()}
    return cat, cfg


def gerar_manifesto_execucao(caminho: Path = PASTA_DADOS / "manifesto_execucao.json") -> dict:
    """Manifesto pedido na seção 6 do enunciado: seed, quantidade de SKUs, metas
    financeiras, hash do dataset e versões do ambiente.

    O `manifesto_dados.json` oficial (gerado pelo notebook) não pode ser alterado sem
    mudar o hash da instância, por isso estas informações ficam num arquivo à parte,
    que REFERENCIA o hash oficial. É regenerado a cada execução dos main.py.
    """
    import platform
    from importlib.metadata import PackageNotFoundError, version

    man = verificar_integridade()
    cat1, cfg1, _ = carregar_questao(1, verificar=False)
    cat2, cfg2, _ = carregar_questao(2, verificar=False)
    versoes = {}
    for pacote in ("numpy", "pandas", "matplotlib", "tabulate", "pytest"):
        try:
            versoes[pacote] = version(pacote)
        except PackageNotFoundError:
            versoes[pacote] = None
    dados = {
        "grupo": man["grupo"],
        "quantidade_integrantes": man["quantidade_integrantes"],
        "seed_base": man["seed_base"],
        "seed_final": man["seed_final"],
        "id_instancia": man["id_instancia"],
        "sha256_conjunto": man["sha256_conjunto"],
        "sha256_arquivos": man["arquivos"],
        "questao_01": {
            "quantidade_skus": int(len(cat1)),
            "estoque_total_unid": int(cat1["estoque"].sum()),
            "meta_caixa_90d": cfg1["meta_caixa_90d"],
            "divida_total_90d": cfg1["divida_total_90d"],
            "orcamento_promocional": cfg1["orcamento_promocional"],
            "margem_minima_percentual": cfg1["margem_minima_percentual"],
        },
        "questao_02": {
            "quantidade_skus": int(len(cat2)),
            "estoque_total_unid": int(cat2["estoque_inicial"].sum()),
            "caixa_inicial": cfg2["caixa_inicial"],
            "dividas": cfg2["dividas"],
            "divida_total": round(sum(cfg2["dividas"].values()), 2),
            "orcamento_promocional_semanal": cfg2["orcamento_promocional_semanal"],
            "limite_risco_falha": cfg2["limite_risco_falha"],
        },
        "ambiente": {"python": platform.python_version(), "pacotes": versoes},
    }
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    return dados
