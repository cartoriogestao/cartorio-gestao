"""O proclama que vai ao e-Proclamas — a corrente entre a habilitacao e a
Central.

O QUE ESTES TESTES PROTEGEM, e cada um custou uma decisao:

    a ordem da corrente     edital -> assento no Livro D -> envio. Cada elo
                            existe por um motivo, e a recusa diz em qual se
                            parou, porque o conserto de cada um e num lugar
                            diferente da casa

    o que NAO se inventa    o endereco nao vai (seis campos contra um de texto
                            livre), a naturalidade so vai quando o IBGE
                            resolve, e o que a Central devolve e o NUMERO DO
                            LOTE — nao ha campo `protocolo` na resposta

    nao publicar duas vezes publicacao custa e sai no mundo

QUEM RECUSA E O DOMINIO. Estes testes chamam as funcoes direto, sem rota
nenhuma — e **nenhum deles fala com a Central**: o envio de verdade tem o seu
proprio guarda, e teste que bate na rede nao e teste.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import habilitacao as HAB
import onrcpn_api as API
import proclamas as PROC
import rc_assento as RC
import rc_matricula as MATR
from hc_schema import init_hc_schema
from ibge_schema import init_ibge_schema
from nucleo_schema import init_nucleo_schema
from rc_schema import init_rc_schema

AGORA = "2026-09-03T10:00:00"
CNS = "000000"
TEOR = ("Faco saber que pretendem casar-se FULANO DE TAL e BELTRANA DE TAL, "
        "e que apresentaram os documentos exigidos pelo art. 1.525 do Codigo "
        "Civil. Quem souber de impedimento, oponha-o na forma da lei.")
SV = {"ri_cns": CNS, "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
      "escrevente": "JEAN", "funcao": "Escrevente"}


@pytest.fixture()
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(c)
    init_rc_schema(c)
    init_hc_schema(c)
    init_ibge_schema(c)
    # O MUNICIPIO DESTA CASA, para a naturalidade ter onde bater. E o codigo
    # real: 2198765 = 21 (MA) + 07001, conferido na remessa do IBGE.
    c.execute(
        "INSERT INTO ib_municipios(codigo_ibge, codigo_uf, codigo_mun, uf, "
        " nome, nome_norm, criado_em) VALUES(?,?,?,?,?,?,?)",
        (2198765, 21, "98765", "MA", "Cidade Exemplo", "cidade exemplo", AGORA))
    return c


def _habilitacao(con, **extra) -> int:
    dados = {"nubente1_nome": "FULANO DE TAL",
             "nubente1_estado_civil": "SOLTEIRO",
             "nubente1_sexo": "M",
             "nubente1_nascimento": "1990-05-12",
             "nubente1_documento": "000.000.046-93",
             "nubente1_naturalidade": "Cidade Exemplo/MA",
             "nubente1_profissao": "lavrador",
             "nubente1_pai": "JOSE DE TAL",
             "nubente1_mae": "MARIA DE TAL",
             "nubente1_endereco": "Rua das Flores, 100, Centro",
             "nubente2_nome": "BELTRANA DE TAL",
             "nubente2_estado_civil": "SOLTEIRA",
             "nubente2_sexo": "F",
             "nubente2_nascimento": "1992-03-08",
             "nubente2_documento": "00000004693",
             "nubente2_naturalidade": "Cidade Exemplo/MA",
             "nubente2_nome_pos": "BELTRANA DE TAL E SILVA",
             "nubente2_pai": "ANTONIO DE TAL",
             "nubente2_mae": "JOANA DE TAL",
             "tipo": "CIVIL", "regime": "COMUNHAO_PARCIAL"}
    dados.update(extra)
    h = HAB.abrir(con, dados, agora=AGORA, usuario="JEAN")
    for d in HAB.o_que_falta(con, h):
        HAB.marcar_documento(con, d["id"], apresentado=True, agora=AGORA,
                             usuario="JEAN")
    return h


def _publicar(con, h) -> None:
    HAB.publicar_edital(con, h, teor=TEOR, agora=AGORA, hoje="2026-09-03",
                        usuario="JEAN")


def _assento_de_proclamas(con, h) -> int:
    """Lavra o registro no Livro D e o amarra a habilitacao."""
    feito = RC.lavrar_assento(
        con, especie="PROCLAMAS", nome="FULANO DE TAL e BELTRANA DE TAL",
        sv=SV, agora=AGORA, data_extenso="tres de setembro de dois mil e "
        "vinte e seis", data_fato="2026-09-03", usuario="JEAN")
    con.execute("UPDATE hc_habilitacoes SET proclamas_assento_id=? WHERE id=?",
                (feito["assento_id"], h))
    return feito["assento_id"]


# ------------------------------------------------------- a corrente


def test_sem_edital_publicado_nao_se_manda(con):
    """E do edital que saem a data e o teor que vao para a Central."""
    h = _habilitacao(con)
    r = PROC.conferir(con, h, cns=CNS)
    assert r["pronto"] is False
    assert any("edital" in i.lower() for i in r["impedem"])


def test_sem_o_registro_no_livro_D_nao_se_manda(con):
    """E dele que sai a matricula com que a Central identifica o proclama."""
    h = _habilitacao(con)
    _publicar(con, h)
    r = PROC.conferir(con, h, cns=CNS)
    assert r["pronto"] is False
    assert any("Livro D" in i for i in r["impedem"])
    # E a recusa DIZ ONDE SE CONSERTA — recusa que nao diz manda procurar.
    assert any("Novo assento" in i for i in r["impedem"])


def test_com_os_dois_elos_fica_pronto(con):
    h = _habilitacao(con)
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    r = PROC.conferir(con, h, cns=CNS)
    assert r["pronto"] is True, r["impedem"]
    assert len(r["matricula"]["matricula"]) == MATR.TAMANHO


# ------------------------------------------------------- a matricula


def test_a_matricula_sai_do_assento_e_confere(con):
    h = _habilitacao(con)
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    m = PROC.matricula_do_proclama(
        con, con.execute("SELECT * FROM hc_habilitacoes WHERE id=?",
                         (h,)).fetchone(), cns=CNS)
    assert MATR.confere(m["matricula"])["ok"] is True
    assert MATR.partes(m["matricula"])["livro_nome"] == "D"


def test_a_procedencia_do_digito_do_livro_D_sobe_ate_a_tela(con):
    """Quem assina precisa saber que o `6` saiu do exemplo de um contrato.

    As outras seis letras vieram do guia do SIRC ou dos assentos desta casa; o
    Livro D veio do exemplo do contrato do e-Proclamas, que e **fabricado**.
    Esconder isso seria o carimbo que mente na identidade nacional do ato.
    """
    h = _habilitacao(con)
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    r = PROC.conferir(con, h, cns=CNS)
    assert "e-Proclamas" in r["matricula"]["procedencia"]


def test_a_matricula_gravada_manda_sobre_a_calculada(con):
    """Divergencia entre as duas e assunto do oficial, e nao de um UPDATE."""
    h = _habilitacao(con)
    _publicar(con, h)
    assento = _assento_de_proclamas(con, h)
    con.execute("UPDATE rc_assentos SET matricula=? WHERE id=?",
                ("0" * 32, assento))
    m = PROC.matricula_do_proclama(
        con, con.execute("SELECT * FROM hc_habilitacoes WHERE id=?",
                         (h,)).fetchone(), cns=CNS)
    assert m["matricula"] == "0" * 32
    assert m["de_onde"] == "gravada no assento"


# ------------------------------------------------------- o que se monta


def test_o_proclama_sai_nas_convencoes_do_contrato(con):
    """CPF sem pontuacao, data dd/mm/aaaa, sexo minusculo, estado civil seco."""
    h = _habilitacao(con)
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    p = PROC.conferir(con, h, cns=CNS)["proclama"]

    assert p["data_proclamas"] == "03/09/2026"
    assert p["tipo_casamento"] == "civil"
    c1, c2 = p["conjuge_1"], p["conjuge_2"]
    assert c1["cpf"] == "00000004693"          # entrou pontuado
    assert c1["sexo"] == "masculino" and c2["sexo"] == "feminino"
    assert c1["estado_civil"] == "SOLTEIRO"
    # `SOLTEIRA` nao existe no vocabulario da Central; vira `SOLTEIRO`.
    assert c2["estado_civil"] == "SOLTEIRO"
    assert c1["data_nascimento"] == "12/05/1990"
    assert c2["novo_nome"] == "BELTRANA DE TAL E SILVA"


def test_a_filiacao_vai_com_o_sexo_que_a_coluna_declara(con):
    """`nubente1_pai` e `nubente1_mae` DIZEM o sexo pelo nome da coluna."""
    h = _habilitacao(con)
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    c1 = PROC.conferir(con, h, cns=CNS)["proclama"]["conjuge_1"]
    assert c1["filiacao"] == [
        {"nome_genitor": "JOSE DE TAL", "sexo_genitor": "masculino"},
        {"nome_genitor": "MARIA DE TAL", "sexo_genitor": "feminino"}]


def test_a_naturalidade_vira_os_sete_digitos_do_ibge(con):
    h = _habilitacao(con)
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    c1 = PROC.conferir(con, h, cns=CNS)["proclama"]["conjuge_1"]
    assert c1["ibge_municipio_naturalidade"] == "2198765"
    assert c1["pais_nascimento"] == API.BRASIL_M49 == "076"


def test_naturalidade_ambigua_vai_em_branco_e_a_tela_diz_por_que(con):
    """Sem UF, so vale se o nome for unico no Brasil — a regra do IBGE.

    Escolher o municipio mais parecido poria o casal no estado errado, e
    ninguem notaria nunca.
    """
    con.execute(
        "INSERT INTO ib_municipios(codigo_ibge, codigo_uf, codigo_mun, uf, "
        " nome, nome_norm, criado_em) VALUES(?,?,?,?,?,?,?)",
        (2103307, 21, "03307", "MA", "Bom Jesus", "bom jesus", AGORA))
    con.execute(
        "INSERT INTO ib_municipios(codigo_ibge, codigo_uf, codigo_mun, uf, "
        " nome, nome_norm, criado_em) VALUES(?,?,?,?,?,?,?)",
        (2201903, 22, "01903", "PI", "Bom Jesus", "bom jesus", AGORA))
    h = _habilitacao(con, nubente1_naturalidade="Bom Jesus")
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    r = PROC.conferir(con, h, cns=CNS)
    assert r["proclama"]["conjuge_1"]["ibge_municipio_naturalidade"] == ""
    assert any("unico no Brasil" in a or "único no Brasil" in a
               for a in r["avisos"])


def test_nao_achar_o_municipio_nao_faz_o_nubente_de_estrangeiro(con):
    """Erro de digitacao na cidade nao pode virar «nasceu fora do Brasil».

    A Central tem `naturalidade_estrangeiro`, e marca-la por ausencia diria a
    ela uma coisa que ninguem apurou.
    """
    h = _habilitacao(con, nubente1_naturalidade="Cidade Exemploo/MA")
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    c1 = PROC.conferir(con, h, cns=CNS)["proclama"]["conjuge_1"]
    assert c1["ibge_municipio_naturalidade"] == ""
    assert c1["naturalidade_estrangeiro"] is False
    assert c1["pais_nascimento"] == ""


def test_o_endereco_nao_vai_e_a_conferencia_diz_isso(con):
    """Seis campos contra um de texto livre. Campo errado afirma; vazio nao."""
    h = _habilitacao(con)
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    r = PROC.conferir(con, h, cns=CNS)
    assert r["proclama"]["conjuge_1"]["endereco_residencia"] == {
        "cep": "", "logradouro": "", "numero": "", "complemento": "",
        "bairro": "", "ibge_municipio": ""}
    assert any("endereço" in a.lower() for a in r["avisos"])
    # E o texto que a casa tem NAO vazou para dentro de campo nenhum.
    assert "Rua das Flores" not in str(r["proclama"])


def test_quem_paga_vem_sugerido_do_primeiro_conjuge_e_e_editavel(con):
    h = _habilitacao(con)
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    p = PROC.conferir(con, h, cns=CNS)["proclama"]
    assert p["cpf_fatura"] == "00000004693"
    assert p["nome_fatura"] == "FULANO DE TAL"
    outro = PROC.conferir(con, h, cns=CNS, cpf_fatura="000.000.048-55",
                          nome_fatura="QUEM PAGA")["proclama"]
    assert outro["cpf_fatura"] == "00000004855"
    assert outro["nome_fatura"] == "QUEM PAGA"


# ------------------------------------------------------- as recusas


def test_nao_se_manda_sem_marcar_nada(con):
    """Dois booleanos falsos sao um envio que nao faz nada."""
    h = _habilitacao(con)
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    r = PROC.conferir(con, h, cns=CNS, publicacao=False,
                      livro_eletronico=False)
    assert r["pronto"] is False
    assert any("ao menos uma" in i for i in r["impedem"])


def test_nao_se_publica_duas_vezes(con):
    """Publicacao custa e sai no mundo. A recusa traz a data e o protocolo."""
    h = _habilitacao(con)
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    con.execute(
        "INSERT INTO hc_eproclamas(habilitacao_id, matricula, publicacao, "
        " livro_eletronico, ambiente, corpo_enviado, corpo_hash, protocolo, "
        " enviado_em) VALUES(?,?,1,0,?,?,?,?,?)",
        (h, "0" * 32, PROC.ambiente(), "{}", "x", "PROTO-1",
         "2026-09-03T11:00:00"))
    r = PROC.conferir(con, h, cns=CNS)
    assert r["pronto"] is False
    assert any("PROTO-1" in i for i in r["impedem"])
    # MAS O LIVRO D ELETRONICO CONTINUA PODENDO IR SOZINHO.
    so_livro = PROC.conferir(con, h, cns=CNS, publicacao=False,
                             livro_eletronico=True)
    assert so_livro["pronto"] is True, so_livro["impedem"]


def test_envio_de_homologacao_nao_impede_a_publicacao_de_verdade(con):
    """Travar o balcao por causa de um teste seria o pior dos dois lados."""
    h = _habilitacao(con)
    _publicar(con, h)
    _assento_de_proclamas(con, h)
    con.execute(
        "INSERT INTO hc_eproclamas(habilitacao_id, matricula, publicacao, "
        " livro_eletronico, ambiente, corpo_enviado, corpo_hash, protocolo, "
        " enviado_em) VALUES(?,?,1,0,'OUTRO_AMBIENTE',?,?,?,?)",
        (h, "0" * 32, "{}", "x", "PROTO-TESTE", "2026-09-03T11:00:00"))
    assert PROC.conferir(con, h, cns=CNS)["pronto"] is True


# ------------------------------------------------------- a fila


def test_a_fila_traz_o_que_publicou_edital_e_nao_foi_a_central(con):
    h1 = _habilitacao(con)
    _publicar(con, h1)
    h2 = _habilitacao(con, nubente1_nome="OUTRO", nubente2_nome="OUTRA")
    # h2 NAO publica edital — nao entra na fila.
    assert [p["id"] for p in PROC.pendentes(con)] == [h1]
    assert h2 not in [p["id"] for p in PROC.pendentes(con)]

    con.execute(
        "INSERT INTO hc_eproclamas(habilitacao_id, matricula, publicacao, "
        " livro_eletronico, ambiente, corpo_enviado, corpo_hash, protocolo, "
        " enviado_em) VALUES(?,?,1,0,?,?,?,?,?)",
        (h1, "0" * 32, PROC.ambiente(), "{}", "x", "PROTO-1",
         "2026-09-03T11:00:00"))
    assert PROC.pendentes(con) == []


# ------------------------------------------------------- o que ele NAO faz


def test_o_modulo_nao_lavra_ato():
    """Pela sexta vez: usucapiao, fraudes, CNIB, CENPROT, ONRTDPJ, e este.

    Quem publica o edital e `habilitacao`; quem lanca no Livro D e
    `rc_assento`. Este comunica o que ja foi decidido e lavrado.
    """
    proibidos = ("lavrar", "registrar_assento", "numerar", "selar", "cobrar",
                 "cancelar", "publicar_edital", "habilitar")
    publicos = [n for n in dir(PROC) if not n.startswith("_")]
    for nome in publicos:
        for palavra in proibidos:
            assert palavra not in nome.lower(), (
                f"«{nome}» tem cara de ato — este modulo nao lavra")


def test_o_que_a_central_devolve_e_o_NUMERO_DO_LOTE():
    """E nao um protocolo por proclama — medido no esquema da resposta.

    A primeira versao deste modulo procurava um campo `protocolo` por varios
    nomes provaveis, porque eu tinha concluido que o corpo da resposta nao era
    declarado. **Era.** O que ha e `batchId`, e e ele que a casa guarda.
    """
    lido = API.ler_o_lote({"proclamas": {"batchId": 12, "success": [
        {"matricula": "9" * 32}], "error": []}})
    assert lido["lote"] == "12"
    assert lido["aceitos"] == ["9" * 32]
