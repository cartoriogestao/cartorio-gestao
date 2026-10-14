# -*- coding: utf-8 -*-
"""CI anti-vazamento (sanitizacao B0) — testa o MOTOR, nao exige o sandbox limpo.

O QUE ESTE ARQUIVO GARANTE
    - os detectores genericos (CPF/CNPJ com DV, CNS em contexto, selo TJMA,
      C:\\Users\\<perfil>) acham o que devem e deixam passar os ficticios;
    - a deny-list nominal so existe LOCAL (`ci/denylist.local.txt`); aqui so
      se testa o motor com listas sinteticas, e a lista real so e exercitada
      se o arquivo existir na maquina (senao, skip);
    - nenhum CPF valido nao-ficticio fica gravado no repo: o caso «falha» e
      gerado em tempo de execucao, em `tmp_path`;
    - `serventia.PADRAO_GENERICO` nao carrega dado de serventia real.

A VARREDURA DA ARVORE INTEIRA (o gate de verdade) so roda com
`CG_ANTI_VAZAMENTO_ESTRITO=1` — hoje o sandbox ainda tem literais da casa, e
ela so deve ficar verde depois dos lotes B1..B6. Na CI do repo publico o
workflow liga a variavel.
"""
from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

from ci import anti_vazamento as AV

RAIZ = Path(__file__).resolve().parent.parent
FIX = RAIZ / "tests" / "fixtures" / "anti_vazamento"


def _ficticios() -> set[str]:
    return AV.carregar_ficticios(RAIZ / AV.FICTICIOS)


def _cpf_com_dv(base9: str) -> str:
    d = [int(c) for c in base9]
    for corte in (9, 10):
        s = sum(d[i] * ((corte + 1) - i) for i in range(corte))
        d.append((s * 10) % 11 % 10)
    n = "".join(map(str, d))
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"


def _cnpj_com_dv(base12: str) -> str:
    d = [int(c) for c in base12]
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    for p, c in ((p1, 12), (p2, 13)):
        r = sum(d[i] * p[i] for i in range(c)) % 11
        d.append(0 if r < 2 else 11 - r)
    n = "".join(map(str, d))
    return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"


def _cpf_aleatorio_nao_ficticio() -> str:
    rnd = random.Random()
    while True:
        cpf = _cpf_com_dv("".join(str(rnd.randint(0, 9)) for _ in range(9)))
        if AV.so_digitos(cpf) not in _ficticios() and AV.cpf_valido(cpf):
            return cpf


# ------------------------------------------------------------ DV

def test_os_ficticios_tem_dv_valido():
    fict = _ficticios()
    assert fict, "allowlist de ficticios vazia"
    for doc in fict:
        if len(doc) == 11:
            assert AV.cpf_valido(doc), doc
        elif len(doc) == 14:
            assert AV.cnpj_valido(doc), doc


def test_dv_recusa_repetidos_e_errados():
    assert not AV.cpf_valido("111.111.111-11")
    assert not AV.cpf_valido("000.000.001-92")
    assert not AV.cnpj_valido("00.000.001/0000-56")
    assert AV.cpf_valido(_cpf_com_dv("123456789"))
    assert AV.cnpj_valido(_cnpj_com_dv("123456780001"))


# ------------------------------------------------------------ fixtures sinteticas

def test_arquivo_limpo_passa():
    texto = (FIX / "limpo.txt").read_text(encoding="utf-8")
    assert AV.varrer_texto(texto, ficticios=_ficticios()) == []


def test_cpf_ficticio_allowlisted_passa():
    texto = (FIX / "com_cpf_ficticio.txt").read_text(encoding="utf-8")
    assert AV.varrer_texto(texto, ficticios=_ficticios()) == []


def test_cpf_valido_nao_allowlisted_falha(tmp_path):
    cpf = _cpf_aleatorio_nao_ficticio()
    arq = tmp_path / "vazou.py"
    arq.write_text(f'parte = {{"cpf": "{cpf}"}}\n', encoding="utf-8")
    achados = AV.varrer_arvore(tmp_path, modo="arvore", ficticios=_ficticios())
    assert [a.tipo for a in achados] == ["CPF"]
    # o log e publico: o numero nunca sai inteiro
    assert AV.so_digitos(cpf) not in str(achados[0])


def test_cpf_sem_mascara_so_com_rotulo(tmp_path):
    cpf = AV.so_digitos(_cpf_aleatorio_nao_ficticio())
    assert AV.varrer_texto(f"cpf={cpf}", ficticios=_ficticios())
    # 11 digitos soltos sem rotulo (telefone, protocolo) nao disparam
    assert AV.varrer_texto(f"protocolo {cpf}", ficticios=_ficticios()) == []


def test_cnpj_valido_nao_allowlisted_falha():
    cnpj = _cnpj_com_dv("987654320001")
    achados = AV.varrer_texto(f"CNPJ: {cnpj}", ficticios=_ficticios())
    assert {a.tipo for a in achados} == {"CNPJ"}


# Os gatilhos sinteticos abaixo sao montados por concatenacao para que ESTE
# arquivo nao dispare a varredura da arvore (ele vai para o repo publico).
CNS_ROTULO = "CN" + "S"
USERS = "C:" + "\\" + "Users" + "\\"


def test_cns_em_contexto():
    assert [a.tipo for a in AV.varrer_texto(CNS_ROTULO + ": 123456")] == ["CNS"]
    assert [a.tipo for a in AV.varrer_texto(
        "User-Agent CartorioGestao/" + CNS_ROTULO + "123456")] == ["CNS"]
    assert AV.varrer_texto('ri_cns = "000000"') == []
    assert AV.varrer_texto("protocolo 123456") == []


def test_selo_tjma_real_falha_e_ficticio_passa():
    real = "PRENOT" + "123456" + "ZX9Q2W8E7R6T5Y4U"
    assert [a.tipo for a in AV.varrer_texto(f"Selo: {real}")] == ["SELO"]
    assert AV.varrer_texto("Selo: PRENOT000000ZX9Q2W8E7R6T5Y4U") == []


def test_selo_tjma_bate_com_o_formato_do_sistema():
    import selo
    exemplo = "AVERBA" + "123456" + "AB12CD34EF56GH78"
    assert selo.CODIGO_SELO.match(exemplo)
    assert AV.RX_SELO_TJMA.search(exemplo)


def test_perfil_windows():
    assert [a.tipo for a in AV.varrer_texto(USERS + "maria" + "\\Desktop")] == ["PERFIL_WINDOWS"]
    assert AV.varrer_texto(USERS + "<usuario>\\Desktop") == []
    assert AV.varrer_texto(USERS + "Public\\x") == []


def test_arquivos_proibidos():
    for nome in ("selador.cred", "secret.key", "chave.key", "x.pfx", "a.p12",
                 "dados/cartorio_gestao.sqlite3", "c.db", "tests/selos_reais.json",
                 "tmp_probe.py", ".env", "ci/denylist.local.txt"):
        assert AV.arquivo_proibido(nome), nome
    for nome in (".env.example", "ci/denylist.example.txt", "serventia.py",
                 "static/brasao.jpg"):
        assert not AV.arquivo_proibido(nome), nome


def test_varredura_ignora_as_proprias_fixtures(tmp_path):
    pasta = tmp_path / "tests" / "fixtures" / "anti_vazamento"
    pasta.mkdir(parents=True)
    (pasta / "exemplo_sujo.txt").write_text(CNS_ROTULO + ": 123456", encoding="utf-8")
    assert AV.varrer_arvore(tmp_path, modo="arvore") == []


# ------------------------------------------------------------ deny-list

def test_denylist_sintetica_motor(tmp_path):
    lista = tmp_path / "deny.txt"
    lista.write_text("# comentario\nCidade Fictícia de Teste\nre:\\b10\\.9\\.8\\.\\d+\\b\n",
                     encoding="utf-8")
    deny = AV.carregar_denylist(lista)
    assert len(deny) == 2
    achados = AV.varrer_texto("linha1\ncidade ficticia de teste\nhost 10.9.8.7",
                              denylist=deny)
    assert [(a.linha, a.detalhe) for a in achados] == [
        (2, "entrada #2 da deny-list local"), (3, "entrada #3 da deny-list local")]
    assert AV.varrer_texto("nada aqui", denylist=deny) == []


def test_denylist_example_e_so_placeholder():
    exemplo = RAIZ / AV.DENYLIST_EXEMPLO
    assert exemplo.is_file()
    deny = AV.carregar_denylist(exemplo)
    assert deny, "o exemplo deve ter entradas (placeholders)"
    # o exemplo nao pode conter CPF/CNPJ/CNS/selo reais
    assert AV.varrer_texto(exemplo.read_text(encoding="utf-8"),
                           ficticios=_ficticios()) == []


def test_denylist_local_se_existir():
    local = RAIZ / AV.DENYLIST_LOCAL
    if not local.is_file():
        pytest.skip("ci/denylist.local.txt ausente (normal fora do SERVIDOR)")
    deny = AV.carregar_denylist(local)
    assert deny, "ci/denylist.local.txt existe mas esta vazia"
    # cada entrada literal precisa se achar a si mesma (lista bem formada);
    # nada e impresso alem do numero da linha.
    linhas = local.read_text(encoding="utf-8").splitlines()
    for e in deny:
        if e.literal:
            assert AV.varrer_texto(linhas[e.numero - 1], denylist=[e]), f"entrada #{e.numero}"


def test_denylist_pelo_ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv(AV.ENV_DENYLIST, "Nome Secreto Exemplo")
    deny = AV.denylist_ativa(tmp_path)   # sem arquivo local em tmp_path
    assert len(deny) == 1


# ------------------------------------------------------------ gitignore

ESSENCIAIS_NO_GITIGNORE = (".env", "*.cred", "secret.key", "*.key",
                           "ci/denylist.local.txt", "*.sqlite3")


def test_gitignore_cobre_segredos():
    gi = RAIZ / ".gitignore"
    if not gi.is_file():
        pytest.skip(".gitignore ainda nao aplicado (dono: B1 Integracoes RCPN/Protesto)")
    linhas = {l.strip() for l in gi.read_text(encoding="utf-8").splitlines()}
    faltam = [p for p in ESSENCIAIS_NO_GITIGNORE if p not in linhas]
    assert not faltam, f".gitignore sem: {faltam}"
    assert "static/brasao.jpg" not in linhas, "brasao e simbolo publico: vai para o repo"


# ------------------------------------------------------------ serventia generica

def test_serventia_padrao_generico_sem_dado_real():
    import serventia
    texto = repr(dict(serventia.PADRAO_GENERICO))
    assert AV.varrer_texto(texto, ficticios=_ficticios(),
                           denylist=AV.denylist_ativa(RAIZ)) == []
    assert serventia.PADRAO_GENERICO["ri_cns"] == "000000"
    assert serventia.PADRAO_GENERICO["unit_name"] == "NOME DA SERVENTIA"
    for k in ("serventia_brasao", "selador_host"):
        assert k in serventia.CAMPOS


def test_serventia_fallback_e_aliases_legados():
    import serventia
    vazio = serventia.dados({})
    for k, v in serventia.PADRAO.items():
        assert vazio[k] == v
    d = serventia.dados({"serventia_cns": "000001", "ri_registrador": "Titular Teste",
                         "ri_cidade": "Cidade X", "ri_uf": "ZZ"})
    assert d["ri_cns"] == "000001"
    assert d["serventia_titular"] == "Titular Teste"
    assert d["cidade_uf"] == "Cidade X/ZZ"
    # a chave canonica vence a legada
    d2 = serventia.dados({"ri_cns": "000002", "serventia_cns": "000001"})
    assert d2["ri_cns"] == "000002"


def test_serventia_forma_do_endereco_completo():
    import serventia
    d = serventia.dados({"serventia_endereco": "Rua A, 1", "serventia_cep": "00.000-000",
                         "ri_cidade": "Cidade X", "ri_uf": "ZZ"})
    assert d["endereco_completo"] == "Rua A, 1, CEP 00.000-000, Cidade X-ZZ"


def test_namespace_modelos_aliases():
    import serventia
    ns = serventia.namespace_modelos(serventia.dados({"ri_cns": "000003"}))
    esperados = {"nome", "cns", "cnpj", "cidade", "uf", "cidade_uf", "endereco",
                 "endereco_completo", "cep", "telefone", "email", "titular",
                 "titulo", "substituta", "brasao"}
    assert esperados <= set(ns)
    assert ns["cns"] == "000003"
    assert ns["brasao"] == serventia.PADRAO["serventia_brasao"]


# ------------------------------------------------------------ o gate real

@pytest.mark.lento
@pytest.mark.skipif(os.environ.get("CG_ANTI_VAZAMENTO_ESTRITO") != "1",
                    reason="gate estrito so apos B1..B6 (CG_ANTI_VAZAMENTO_ESTRITO=1)")
def test_arvore_sem_vazamento():
    achados = AV.varrer_arvore(RAIZ, denylist=AV.denylist_ativa(RAIZ), ficticios=_ficticios())
    assert not achados, "\n".join(map(str, achados[:50]))
