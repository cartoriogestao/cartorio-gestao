# -*- coding: utf-8 -*-
"""A fila de conferência das fichas: a máquina sugere, e só uma pessoa grava.

Dados fictícios. Os CPFs são calculados aqui, para nenhum número ficar escrito.
"""
from __future__ import annotations

import re

import pytest

from bd_nativo import banco
import ri_fila_fichas as F

AGORA = "2026-11-23T10:00:00"
DEPOIS = "2026-11-23T11:00:00"
CNS = "000000"


def _cpf(base: str) -> str:
    """Um CPF com os dígitos verificadores certos, a partir de nove dígitos."""
    n = base
    for corte in (9, 10):
        soma = sum(int(n[i]) * (corte + 1 - i) for i in range(corte))
        n += str((soma * 10) % 11 % 10)
    return n


CPF_A = _cpf("529982247")
CPF_B = _cpf("168995350")


def _teor(descricao: str, final: str = "") -> str:
    return (f" MATRÍCULA: 1\n\r\n LIVRO 2 FLS. 1\n\r\n \n\r\n IMÓVEL:- - {descricao}"
            f"\n\nProprietário: JOSE EXEMPLO DA SILVA, brasileiro, casado.{final}")


URBANO = _teor("Lote de terreno urbano situado na Rua das Flores, nº 123, bairro Jardim, "
               "nesta cidade de Cidade Exemplo, medindo 10,00 m de frente por 25,00 m de "
               "fundo, com área de 250,00 m2, confrontando com o lote nº 125.")
RURAL = _teor('Uma área de terras rural denominada "Fazenda Boa Esperança", situada no '
              "município de Cidade Exemplo, com área de 10,00 hectares.")
OUTRO_MUNICIPIO = _teor("Lote de terreno urbano situado na Rua das Flores, nº 9, bairro "
                        "Jardim, no município de Vila Distante, com área de 250,00 m2.")
ENCERRAMENTO = URBANO + "\nAV-2: a presente matrícula fica encerrada por unificação."


def _config(s) -> None:
    s["db"].set_settings({"ri_cidade": "Cidade Exemplo", "ri_uf": "ZZ", "ri_cns": CNS,
                          "serventia_cep": "00000-000"})


def _ficha(s, numero, teor=URBANO, *, rural_urbano=None, situacao="ATIVA", origem="EOFICIO",
           dono="JOSE EXEMPLO DA SILVA", **colunas) -> int:
    nomes = ["numero", "complemento", "livro", "livro_norm", "tipo_ficha", "situacao",
             "conferido", "origem", "criado_em", "teor_formato", "teor", "rural_urbano",
             *colunas]
    valores = [str(numero), "", "2", "2", "ACERVO", situacao, 0, origem, "2026-09-16", "texto",
               teor, rural_urbano, *colunas.values()]
    with s["db"].transaction() as con:
        bd = banco(con)
        linha = bd.escrever(
            f"INSERT INTO ri_matriculas ({', '.join(nomes)}) "
            f"VALUES ({', '.join(['%s'] * len(nomes))}) RETURNING id", valores)
        mid = int(linha[0]["id"])
        if dono:
            bd.escrever("INSERT INTO ri_partes (matricula_id, nome, papel, proprietario, "
                        "proprietario_ativo, documento_numero, documento_tipo, documento_valido) "
                        "VALUES (%s,%s,'proprietario',1,1,%s,'CPF',1)", (mid, dono, CPF_B))
    return mid


def _parte(s, mid, nome, documento=None, ativo=1) -> int:
    with s["db"].transaction() as con:
        return int(banco(con).escrever(
            "INSERT INTO ri_partes (matricula_id, nome, papel, proprietario, proprietario_ativo, "
            "documento_numero) VALUES (%s,%s,'proprietario',%s,%s,%s) RETURNING id",
            (mid, nome, ativo, ativo, documento))[0]["id"])


def _gerar(s) -> dict:
    with s["db"].transaction() as con:
        return F.gerar(con, agora=AGORA, settings=s["db"].get_settings())


def _item(s, mid, livro="4", parte_id=0) -> dict:
    with s["db"].connect() as con:
        r = banco(con).um("SELECT id FROM ri_ff_itens WHERE livro=%s AND matricula_id=%s "
                          "AND parte_id=%s", (livro, mid, parte_id))
        return F.ler(con, int(r["id"]))


def _coluna(s, mid, coluna):
    with s["db"].connect() as con:
        return banco(con).valor(f"SELECT {coluna} FROM ri_matriculas WHERE id=%s", (mid,))


def _parte_linha(s, parte_id) -> dict:
    with s["db"].connect() as con:
        return dict(banco(con).um("SELECT * FROM ri_partes WHERE id=%s", (parte_id,)))


def _aceitar(s, item_id, campos, *, ligada=False, motivo=""):
    with s["db"].transaction() as con:
        return F.aceitar(con, item_id, campos=campos, agora=DEPOIS, usuario="Pessoa Teste",
                         ligada=ligada, cns=CNS, motivo=motivo)


def _do_teor(item) -> list[str]:
    return [c["campo"] for c in item["campos"] if c["sugerido"] and c["origem"] == F.ORIGEM_TEOR]


@pytest.fixture
def casa(cg_casa_logada):
    _config(cg_casa_logada)
    return cg_casa_logada


# ───────────────────────────────────────────────────── nada grava sozinho


def test_gerar_nao_altera_ficha_nem_parte(casa):
    mid = _ficha(casa, 1)
    pid = _parte(casa, mid, "MARIA EXEMPLO", None)
    with casa["db"].connect() as con:
        antes_m = dict(banco(con).um("SELECT * FROM ri_matriculas WHERE id=%s", (mid,)))
    antes_p = _parte_linha(casa, pid)
    _gerar(casa)
    _gerar(casa)
    with casa["db"].connect() as con:
        assert dict(banco(con).um("SELECT * FROM ri_matriculas WHERE id=%s", (mid,))) == antes_m
        assert banco(con).valor("SELECT COUNT(*) FROM ri_ff_alteracoes") == 0
    assert _parte_linha(casa, pid) == antes_p


def test_aceitar_exige_quem_confirmou(casa):
    mid = _ficha(casa, 1)
    _gerar(casa)
    item = _item(casa, mid)
    with pytest.raises(F.FilaError, match="quem confirmou"):
        with casa["db"].transaction() as con:
            F.aceitar(con, item["id"], campos=_do_teor(item), agora=DEPOIS, usuario=" ",
                      ligada=False, cns=CNS)
    assert not _coluna(casa, mid, "logradouro")


# ───────────────────────────────────────────────────── classe e prioridade


def test_prioridade_segue_a_ordem_do_ri007(casa):
    conflito = _ficha(casa, 1, RURAL, rural_urbano="U")
    municipio = _ficha(casa, 2, OUTRO_MUNICIPIO)
    encerra = _ficha(casa, 3, ENCERRAMENTO)
    comum = _ficha(casa, 4)
    _gerar(casa)
    assert _item(casa, conflito)["prioridade"] == F.P_CONFLITO_UR
    assert _item(casa, municipio)["prioridade"] == F.P_MUNICIPIO
    assert _item(casa, encerra)["prioridade"] == F.P_ENCERRAMENTO
    assert _item(casa, comum)["prioridade"] == F.P_DEMAIS
    with casa["db"].connect() as con:
        ordem = [i["matricula_numero"] for i in F.listar(con, situacao=None)["itens"]]
    assert ordem == ["1", "2", "3", "4"]


@pytest.mark.parametrize("teor,situacao", [(ENCERRAMENTO, "ATIVA"), (URBANO, "ENCERRADA")])
def test_encerramento_fica_so_com_o_oficial(casa, teor, situacao):
    mid = _ficha(casa, 1, teor, situacao=situacao)
    _gerar(casa)
    item = _item(casa, mid)
    assert item["situacao"] == F.SINALIZADA
    with pytest.raises(F.FilaError, match="oficial"):
        _aceitar(casa, item["id"], ["logradouro"])
    with pytest.raises(F.FilaError, match="oficial"):
        with casa["db"].transaction() as con:
            F.corrigir(con, item["id"], valores={"bairro": "Jardim"}, agora=DEPOIS,
                       usuario="Pessoa Teste", cns=CNS)
    assert not _coluna(casa, mid, "logradouro")
    assert _coluna(casa, mid, "situacao") == situacao
    assert int(_coluna(casa, mid, "encerrada") or 0) == 0


# ───────────────────────────────────────────────────── a regra da casa


def test_regra_desligada_por_padrao_nao_mostra_nem_aceita(casa):
    mid = _ficha(casa, 1, RURAL)
    _gerar(casa)
    item = _item(casa, mid)
    assert not F.regra_ligada(casa["db"].get_settings())
    guardados = {c["campo"]: c for c in item["campos"]}
    assert guardados["bairro"]["origem"] == F.ORIGEM_REGRA
    visiveis = {c["campo"]: c for c in F.campos_visiveis(item, False)}
    assert visiveis["bairro"]["sugerido"] == "" and visiveis["bairro"]["oculta_regra"]
    assert visiveis["cep"]["sugerido"] == ""
    html = casa["c"].get(f"/ri/fila-fichas/{item['id']}").get_data(as_text=True)
    assert "Zona Rural" not in html
    assert "Fazenda/Sítio/Chácara" not in html  # nem no aviso
    assert "**" not in " ".join(F.avisos_visiveis(item, False))
    with pytest.raises(F.FilaError, match="regra da casa"):
        _aceitar(casa, item["id"], ["bairro"])
    assert not _coluna(casa, mid, "bairro")


def test_regra_ligada_aparece_marcada_e_grava_a_origem(casa):
    mid = _ficha(casa, 1, RURAL)
    casa["db"].set_settings({F.CHAVE_REGRA_CASA: "1"})
    _gerar(casa)
    item = _item(casa, mid)
    assert {c["campo"]: c for c in F.campos_visiveis(item, True)}["bairro"]["sugerido"] \
        == "Zona Rural"
    _aceitar(casa, item["id"], ["bairro"], ligada=True)
    assert _coluna(casa, mid, "bairro") == "Zona Rural"
    with casa["db"].connect() as con:
        assert F.alteracoes(con, item_id=item["id"])[0]["origem"] == F.ORIGEM_REGRA


@pytest.mark.parametrize("valor", ["", "0", "sim", "true"])
def test_so_o_valor_1_liga_a_regra(valor):
    assert F.regra_ligada({F.CHAVE_REGRA_CASA: valor}) is False


def test_ligar_a_regra_reabre_a_ficha_conferida_sem_perder_o_rastro(casa):
    mid = _ficha(casa, 1, RURAL)
    _gerar(casa)
    item = _item(casa, mid)
    _aceitar(casa, item["id"], _do_teor(item))
    assert _item(casa, mid)["situacao"] == F.ACEITA and not _item(casa, mid)["pronta"]
    casa["db"].set_settings({F.CHAVE_REGRA_CASA: "1"})
    _gerar(casa)
    assert _item(casa, mid)["situacao"] == F.A_CONFERIR
    with casa["db"].connect() as con:
        assert F.alteracoes(con, item_id=item["id"])


def test_so_o_titular_liga_a_regra(casa):
    casa["db"].create_user("gerente", "GERENTE EXEMPLO", "Senha#12345", "MANAGER")
    casa["db"].set_settings({"serventia_titular": "MARIO EXEMPLO DOS SANTOS"})
    c = casa["app"].test_client()
    from tests.conftest import cg_login  # noqa: PLC0415
    cg_login(c, "gerente", "Senha#12345")
    html = c.get("/ri/fila-fichas").get_data(as_text=True)
    assert "/ri/fila-fichas/regra-da-casa" not in html
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    r = c.post("/ri/fila-fichas/regra-da-casa", data={"ligar": "1", "csrf_token": token})
    assert r.status_code == 403
    assert not F.regra_ligada(casa["db"].get_settings())


# ───────────────────────────────────────────────────── rastro e desfazer


def test_aceite_fica_na_auditoria_e_pode_ser_desfeito(casa):
    mid = _ficha(casa, 1)
    _gerar(casa)
    item = _item(casa, mid)
    _aceitar(casa, item["id"], ["logradouro"])
    gravado = _coluna(casa, mid, "logradouro")
    assert gravado and "Flores" in gravado
    with casa["db"].connect() as con:
        linha = F.alteracoes(con, item_id=item["id"])[0]
    assert (linha["campo"], linha["valor_anterior"], linha["valor_novo"], linha["origem"],
            linha["confirmado_por"]) == ("logradouro", None, gravado, F.ORIGEM_TEOR,
                                         "Pessoa Teste")
    with casa["db"].transaction() as con:
        F.desfazer(con, item["id"], motivo="conferido errado no balcão", agora=DEPOIS,
                   usuario="Outra Pessoa", cns=CNS)
    assert _coluna(casa, mid, "logradouro") is None
    assert _item(casa, mid)["situacao"] == F.A_CONFERIR
    with casa["db"].connect() as con:
        rastro = F.alteracoes(con, item_id=item["id"])
    assert len(rastro) == 2 and rastro[0]["origem"] == F.ORIGEM_DESFAZER
    assert rastro[0]["desfaz_id"] == rastro[1]["id"] and rastro[1]["desfeita"]


def test_desfazer_nao_apaga_edicao_posterior(casa):
    mid = _ficha(casa, 1)
    _gerar(casa)
    item = _item(casa, mid)
    _aceitar(casa, item["id"], ["logradouro"])
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE ri_matriculas SET logradouro='Rua Editada' WHERE id=%s",
                            (mid,))
    with pytest.raises(F.FilaError, match="mudou"):
        with casa["db"].transaction() as con:
            F.desfazer(con, item["id"], motivo="tentativa de desfazer", agora=DEPOIS,
                       usuario="Pessoa Teste", cns=CNS)
    assert _coluna(casa, mid, "logradouro") == "Rua Editada"


def test_nao_grava_por_cima_de_quem_editou_depois_da_leitura(casa):
    mid = _ficha(casa, 1)
    _gerar(casa)
    item = _item(casa, mid)
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE ri_matriculas SET logradouro='Rua Editada' WHERE id=%s",
                            (mid,))
    with pytest.raises(F.FilaError, match="mudou"):
        _aceitar(casa, item["id"], ["logradouro"])
    assert _coluna(casa, mid, "logradouro") == "Rua Editada"


def test_trocar_valor_existente_exige_motivo(casa):
    mid = _ficha(casa, 1, RURAL, rural_urbano="U")
    _gerar(casa)
    item = _item(casa, mid)
    assert next(c for c in item["campos"] if c["campo"] == "rural_urbano")["conflito"]
    with pytest.raises(F.FilaError, match="motivo"):
        _aceitar(casa, item["id"], ["rural_urbano"])
    assert _coluna(casa, mid, "rural_urbano") == "U"
    _aceitar(casa, item["id"], ["rural_urbano"], motivo="o teor descreve imóvel rural")
    assert _coluna(casa, mid, "rural_urbano") == "R"


@pytest.mark.parametrize("campo,valor", [("cep", "123"), ("uf", "Estado"),
                                         ("rural_urbano", "talvez"), ("tipo_imovel", "Castelo"),
                                         ("logradouro", "Flores sem tipo")])
def test_correcao_valida_o_campo(casa, campo, valor):
    mid = _ficha(casa, 1)
    _gerar(casa)
    with pytest.raises(F.FilaError):
        with casa["db"].transaction() as con:
            F.corrigir(con, _item(casa, mid)["id"], valores={campo: valor}, agora=DEPOIS,
                       usuario="Pessoa Teste", cns=CNS)
    assert not _coluna(casa, mid, campo)


def test_nova_leitura_nao_apaga_decisao(casa):
    mid = _ficha(casa, 1)
    _gerar(casa)
    item = _item(casa, mid)
    _aceitar(casa, item["id"], ["logradouro"])
    _gerar(casa)
    assert _item(casa, mid)["situacao"] == F.ACEITA


# ───────────────────────────────────────────────────── CPF/CNPJ


def _teor_com_doc(nome, doc):
    return URBANO + f"\nR-1: {nome}, brasileira, solteira, CPF {doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}."


def test_documento_sugerido_grava_e_desfaz_sem_mexer_no_dono(casa):
    mid = _ficha(casa, 1, _teor_com_doc("MARIA EXEMPLO", CPF_A))
    pid = _parte(casa, mid, "MARIA EXEMPLO", None, ativo=0)
    _gerar(casa)
    item = _item(casa, mid, "5", pid)
    assert item["campos"][0]["sugerido"] == CPF_A and "MARIA EXEMPLO" in item["campos"][0]["trecho"]
    antes = _parte_linha(casa, pid)
    _aceitar(casa, item["id"], ["documento_numero"])
    depois = _parte_linha(casa, pid)
    assert (depois["documento_numero"], depois["documento_tipo"], depois["documento_valido"]) \
        == (CPF_A, "CPF", 1)
    assert depois["proprietario_ativo"] == 0 and depois["papel"] == antes["papel"]
    with casa["db"].transaction() as con:
        F.desfazer(con, item["id"], motivo="número era de outra pessoa", agora=DEPOIS,
                   usuario="Pessoa Teste", cns=CNS)
    assert _parte_linha(casa, pid) == antes


def test_correcao_de_documento_valida_os_digitos(casa):
    mid = _ficha(casa, 1, _teor_com_doc("MARIA EXEMPLO", CPF_A))
    pid = _parte(casa, mid, "MARIA EXEMPLO", None)
    _gerar(casa)
    invalido = CPF_A[:-1] + str((int(CPF_A[-1]) + 1) % 10)
    with pytest.raises(F.FilaError, match="verificadores"):
        with casa["db"].transaction() as con:
            F.corrigir(con, _item(casa, mid, "5", pid)["id"],
                       valores={"documento_numero": invalido}, agora=DEPOIS,
                       usuario="Pessoa Teste", cns=CNS)
    assert _parte_linha(casa, pid)["documento_numero"] is None


def test_documento_invalido_no_teor_nao_vira_sugestao():
    invalido = CPF_A[:-1] + str((int(CPF_A[-1]) + 1) % 10)
    assert F.sugerir_documento(f"MARIA EXEMPLO, CPF {invalido}.", "MARIA EXEMPLO") is None


def test_documento_de_outra_pessoa_derruba_a_confianca():
    parte = {"id": 1, "nome": "MARIA EXEMPLO"}
    conjuge = {"id": 2, "nome": "JOAO TESTADOR"}
    sug = F.sugerir_documento(f"MARIA EXEMPLO e JOAO TESTADOR, CPF {CPF_A}.", "MARIA EXEMPLO")
    donos = {CPF_A: {"joao testador"}}
    assert F.avaliar_documento(sug, parte, [parte, conjuge], donos)[0] == "baixa"
    assert F.avaliar_documento(sug, parte, [parte, conjuge], {})[0] == "alta"
    sem_meio = F.sugerir_documento(f"MARIA EXEMPLO, CPF {CPF_A}.", "MARIA EXEMPLO")
    assert F.avaliar_documento(sem_meio, parte, [parte], donos)[0] == "media"
    # Grafia diferente da mesma pessoa não é outra pessoa.
    assert F.avaliar_documento(sem_meio, parte, [parte], {CPF_A: {"maria da exemplo"}})[0] == "alta"


def test_documento_nao_tem_lote(casa):
    with pytest.raises(F.FilaError, match="não vai em lote"):
        with casa["db"].transaction() as con:
            F.sortear_amostra(con, F.DOC_TEOR, agora=DEPOIS, usuario="Pessoa Teste", ligada=False)


# ───────────────────────────────────────────────────── amostra e lote


def _fatia_com_fichas(s, quantas=5) -> tuple[list[int], str]:
    ids = [_ficha(s, n) for n in range(1, quantas + 1)]
    _gerar(s)
    item = _item(s, ids[0])
    assert item["classe"] == F.TEOR and item["confianca"] == "alta"
    return ids, item["fatia"]


def _sortear(s, fatia, tamanho=2) -> int:
    with s["db"].transaction() as con:
        return F.sortear_amostra(con, fatia, agora=AGORA, usuario="Pessoa Teste", ligada=False,
                                 tamanho=tamanho)["amostra_id"]


def _lote(s, amostra_id, quantidade):
    with s["db"].transaction() as con:
        return F.aceitar_lote(con, amostra_id, quantidade=quantidade, agora=DEPOIS,
                              usuario="Pessoa Teste", ligada=False, cns=CNS)


def _da_amostra(s, amostra_id) -> list[dict]:
    with s["db"].connect() as con:
        ids = [r["id"] for r in banco(con).ler(
            "SELECT id FROM ri_ff_itens WHERE amostra_id=%s ORDER BY id", (amostra_id,))]
        return [F.ler(con, i) for i in ids]


def test_lote_so_abre_com_amostra_inteira_conferida(casa):
    _, fatia = _fatia_com_fichas(casa)
    amostra = _sortear(casa, fatia)
    with pytest.raises(F.FilaError, match="amostra inteira"):
        _lote(casa, amostra, 3)
    primeira, segunda = _da_amostra(casa, amostra)
    _aceitar(casa, primeira["id"], _do_teor(primeira))
    with pytest.raises(F.FilaError, match="amostra inteira"):
        _lote(casa, amostra, 3)
    _aceitar(casa, segunda["id"], _do_teor(segunda))
    with pytest.raises(F.FilaError, match="número exato"):
        _lote(casa, amostra, 99)
    feito = _lote(casa, amostra, 3)
    assert feito["gravados"] == 3
    with casa["db"].connect() as con:
        lote = banco(con).ler("SELECT DISTINCT origem FROM ri_ff_alteracoes WHERE amostra_id=%s",
                              (amostra,))
        assert [r["origem"] for r in lote] == [F.ORIGEM_TEOR]  # regra desligada não entra
        assert F.estado_da_amostra(con, amostra)["estado"] == "USADA"


def test_uma_correcao_na_amostra_mantem_o_lote_fechado(casa):
    _, fatia = _fatia_com_fichas(casa)
    amostra = _sortear(casa, fatia)
    primeira, segunda = _da_amostra(casa, amostra)
    _aceitar(casa, primeira["id"], _do_teor(primeira))
    with casa["db"].transaction() as con:
        F.corrigir(con, segunda["id"], valores={"bairro": "Bairro Certo"}, agora=DEPOIS,
                   usuario="Pessoa Teste", cns=CNS)
    with pytest.raises(F.FilaError, match="sem nenhuma correção"):
        _lote(casa, amostra, 3)
    with casa["db"].connect() as con:
        assert F.estado_da_amostra(con, amostra)["estado"] == "REPROVADA"


def test_lote_nao_pega_confianca_media_nem_outra_fatia(casa):
    ids, fatia = _fatia_com_fichas(casa, 4)
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE ri_ff_itens SET confianca='media' WHERE matricula_id=%s",
                            (ids[3],))
    amostra = _sortear(casa, fatia, tamanho=1)
    unica = _da_amostra(casa, amostra)[0]
    _aceitar(casa, unica["id"], _do_teor(unica))
    assert _lote(casa, amostra, 2)["gravados"] == 2
    assert _item(casa, ids[3])["situacao"] == F.A_CONFERIR
    assert not _coluna(casa, ids[3], "logradouro")


def test_item_recalculado_depois_da_amostra_fica_fora_do_lote(casa):
    ids, fatia = _fatia_com_fichas(casa, 3)
    amostra = _sortear(casa, fatia, tamanho=1)
    unica = _da_amostra(casa, amostra)[0]
    _aceitar(casa, unica["id"], _do_teor(unica))
    fora = next(i for i in ids if i != unica["matricula_id"])
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE ri_ff_itens SET calculado_em=%s WHERE matricula_id=%s",
                            ("2026-11-23T23:00:00", fora))
    assert _lote(casa, amostra, 1)["gravados"] == 1
    assert _item(casa, fora)["situacao"] == F.A_CONFERIR


def test_desfazer_o_lote_inteiro(casa):
    ids, fatia = _fatia_com_fichas(casa, 3)
    amostra = _sortear(casa, fatia, tamanho=1)
    unica = _da_amostra(casa, amostra)[0]
    _aceitar(casa, unica["id"], _do_teor(unica))
    _lote(casa, amostra, 2)
    outras = [i for i in ids if i != unica["matricula_id"]]
    assert all(_coluna(casa, i, "logradouro") for i in outras)
    with casa["db"].transaction() as con:
        feito = F.desfazer_lote(con, amostra, motivo="lote com leitura errada", agora=DEPOIS,
                                usuario="Pessoa Teste", cns=CNS)
    assert feito == {"desfeitos": 2, "ficaram": 0}
    assert not any(_coluna(casa, i, "logradouro") for i in outras)
    # A ficha da amostra foi conferida uma a uma e não é desfeita com o lote.
    assert _coluna(casa, unica["matricula_id"], "logradouro")


# ───────────────────────────────────────────────────── as travas achadas na revisão


def test_area_e_unidade_andam_juntas(casa):
    """A leitura é em m². Sem a unidade junto, «ha» multiplicaria por dez mil."""
    mid = _ficha(casa, 1, URBANO, area_valor="9", area_unidade="ha")
    _gerar(casa)
    item = _item(casa, mid)
    campos = {c["campo"]: c for c in item["campos"]}
    assert campos["area_valor"]["sugerido"] == "250" and campos["area_valor"]["conflito"]
    assert campos["area_unidade"]["sugerido"] == "m2"
    _aceitar(casa, item["id"], ["area_valor"], motivo="o teor diz 250 metros quadrados")
    assert (_coluna(casa, mid, "area_valor"), _coluna(casa, mid, "area_unidade")) == ("250", "m2")


def test_correcao_da_area_exige_a_unidade(casa):
    mid = _ficha(casa, 1)
    _gerar(casa)
    with pytest.raises(F.FilaError, match="juntas"):
        with casa["db"].transaction() as con:
            F.corrigir(con, _item(casa, mid)["id"], valores={"area_valor": "250"},
                       agora=DEPOIS, usuario="Pessoa Teste", cns=CNS)
    assert not _coluna(casa, mid, "area_valor")


def test_lote_nao_grava_area_sem_unidade(casa):
    ids = [_ficha(casa, n, area_unidade="ha") for n in (1, 2, 3)]
    _gerar(casa)
    fatia = _item(casa, ids[0])["fatia"]
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE ri_ff_itens SET confianca='alta' WHERE livro='4'")
    amostra = _sortear(casa, fatia, tamanho=1)
    unica = _da_amostra(casa, amostra)[0]
    _aceitar(casa, unica["id"], ["logradouro"])
    _lote(casa, amostra, 2)
    for mid in ids:
        assert not _coluna(casa, mid, "area_valor")
        assert _coluna(casa, mid, "area_unidade") == "ha"


def test_cpf_ja_gravado_para_outra_pessoa_exige_conferencia(casa):
    """O casal do mesmo trecho: o número aceito para um não passa calado para o outro."""
    teor = URBANO + f"\nR-1: MARIA EXEMPLO e JOAO TESTADOR, CPF {CPF_A}."
    mid = _ficha(casa, 1, teor)
    maria = _parte(casa, mid, "MARIA EXEMPLO", None)
    joao = _parte(casa, mid, "JOAO TESTADOR", None)
    _gerar(casa)
    _aceitar(casa, _item(casa, mid, "5", maria)["id"], ["documento_numero"])
    item = _item(casa, mid, "5", joao)
    with pytest.raises(F.FilaError, match="já está gravado"):
        _aceitar(casa, item["id"], ["documento_numero"])
    assert _parte_linha(casa, joao)["documento_numero"] is None
    with casa["db"].transaction() as con:
        F.aceitar(con, item["id"], campos=["documento_numero"], agora=DEPOIS,
                  usuario="Pessoa Teste", ligada=False, cns=CNS, mesma_pessoa=True)
    with casa["db"].connect() as con:
        assert "mesma pessoa" in F.alteracoes(con, item_id=item["id"])[0]["motivo"]


def test_desfazer_volta_so_a_ultima_decisao(casa):
    mid = _ficha(casa, 1, RURAL)
    _gerar(casa)
    item = _item(casa, mid)
    _aceitar(casa, item["id"], ["logradouro"])
    primeiro = _coluna(casa, mid, "logradouro")
    casa["db"].set_settings({F.CHAVE_REGRA_CASA: "1"})
    _gerar(casa)
    assert _item(casa, mid)["situacao"] == F.A_CONFERIR
    with casa["db"].transaction() as con:
        F.aceitar(con, item["id"], campos=["bairro"], agora="2026-11-23T12:00:00",
                  usuario="Pessoa Teste", ligada=True, cns=CNS)
    with casa["db"].transaction() as con:
        F.desfazer(con, item["id"], motivo="bairro não confere", agora="2026-11-23T13:00:00",
                   usuario="Pessoa Teste", cns=CNS)
    assert _coluna(casa, mid, "bairro") is None
    assert _coluna(casa, mid, "logradouro") == primeiro


# ───────────────────────────────────────────────────── contador e telas


def test_contador_separa_conferida_de_pronta(casa):
    mid = _ficha(casa, 1)
    _ficha(casa, 2)
    _gerar(casa)
    item = _item(casa, mid)
    _aceitar(casa, item["id"], _do_teor(item))
    with casa["db"].connect() as con:
        linha = next(c for c in F.contar(con)["classes"] if c["classe"] == F.TEOR)
    assert (linha["total"], linha["aceitas"], linha["a_conferir"], linha["percentual"]) \
        == (2, 1, 1, 50)
    assert linha["prontas"] == 0  # sem a regra da casa, faltam CEP e tipo


def test_tela_percorre_o_caminho_inteiro(casa):
    mid = _ficha(casa, 1)
    c = casa["c"]
    html = c.get("/ri/fila-fichas").get_data(as_text=True)
    assert "Fila de conferência" in html
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    assert c.post("/ri/fila-fichas/gerar", data={"csrf_token": token}).status_code == 302
    item = _item(casa, mid)
    html = c.get(f"/ri/fila-fichas/{item['id']}").get_data(as_text=True)
    assert "Rua" in html and "Trecho que sustenta" in html
    r = c.post(f"/ri/fila-fichas/{item['id']}/aceitar",
               data={"csrf_token": token, "campo": ["logradouro"]})
    assert r.status_code == 302
    assert "Flores" in _coluna(casa, mid, "logradouro")
    assert c.get("/ri/fila-fichas/auditoria").status_code == 200
    r = c.post(f"/ri/fila-fichas/{item['id']}/desfazer",
               data={"csrf_token": token, "motivo": "teste do caminho de volta"})
    assert r.status_code == 302 and _coluna(casa, mid, "logradouro") is None


def test_fila_esta_no_menu_do_layout_novo(casa):
    html = casa["c"].get("/ri/fila-fichas").get_data(as_text=True)
    assert 'href="/ri/fila-fichas"' in html


def test_auditor_ve_e_nao_decide(casa):
    mid = _ficha(casa, 1)
    _gerar(casa)
    item = _item(casa, mid)
    casa["db"].create_user("auditora", "AUDITORA EXEMPLO", "Senha#12345", "AUDITOR")
    a = casa["app"].test_client()
    from tests.conftest import cg_login  # noqa: PLC0415
    cg_login(a, "auditora", "Senha#12345")
    html = a.get(f"/ri/fila-fichas/{item['id']}").get_data(as_text=True)
    assert "Aceitar o que está marcado" not in html
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    dados = {"campo": ["logradouro"], "csrf_token": token.group(1) if token else ""}
    assert a.post(f"/ri/fila-fichas/{item['id']}/aceitar", data=dados).status_code in (302, 403)
    assert not _coluna(casa, mid, "logradouro")
