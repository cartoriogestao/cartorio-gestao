"""
A ASSINATURA DIGITAL DO DELEGATARIO — o que a casa confere, e nunca assina.

Decisao do oficial em 01/09/2026: *«certificado e A3 do delegatario. Vamos
construir essa ferramenta, ela vai ser util em muitos modulos.»*

**O MODULO NAO ASSINA, E NAO E ESCOLHA: ELE NAO PODE.** A3 quer dizer que a
chave nao sai do token; e carregar o driver PKCS#11 desta maquina **derruba o
processo** — medido nos dois drivers instalados, segfault no `load`, codigo de
saida 139. Segfault nao se trata com `try/except`.

O QUE ESTES TESTES GUARDAM
      - **o documento embrulhado tem de ser byte a byte o que a casa emitiu**.
        E a conferencia que pega o caso real — assinar o arquivo errado, ou o
        arquivo alterado depois de gerado — e ela nao precisa de criptografia;
      - **quem assinou sai do `sid`, e nao do primeiro certificado da lista**:
        o pacote real traz TRES, e a pessoa e a do MEIO. Pegar o primeiro
        diria que quem assinou foi a autoridade certificadora;
      - **assinatura destacada e RECUSADA**, dizendo por que: sem o documento
        dentro nao ha como conferir que e o nosso;
      - o modulo **nao afirma que a firma e valida** — conferir isso exige as
        ancoras de confianca e a revogacao, que esta casa nao tem. Dizer
        «valida» sem ter conferido seria o carimbo que mente num papel que a
        serventia poe no mundo;
      - **nao ha funcao que assine**, e isso se varre.

E O ENSAIO CONTRA OS SEIS INSTRUMENTOS REAIS que o oficial subiu.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import assinatura_digital as AD
from as_schema import init_as_schema

AGORA = "2026-09-01T17:00:00"

PASTA_REAL = Path.home() / "Downloads" / "2025-06-13" / "2025-06-13"
tem_os_reais = pytest.mark.skipif(
    not PASTA_REAL.is_dir(),
    reason="os instrumentos assinados so existem na maquina do oficial")


def um_real() -> tuple[bytes, bytes]:
    """O primeiro par (documento, assinado) da pasta do oficial."""
    p7s = min(PASTA_REAL.glob("*.p7s"))
    return p7s.with_suffix("").read_bytes(), p7s.read_bytes()


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_as_schema(con)
    return con


# ------------------------------------------------------- o que ele nao faz


def test_nao_ha_funcao_que_assine():
    """ELE NAO PODE ASSINAR, e o guarda existe para ninguem tentar.

    A chave esta no token e o driver derruba o processo — uma funcao chamada
    `assinar` aqui seria promessa que o ambiente nao cumpre.
    """
    publicos = [n for n in dir(AD) if not n.startswith("_")]
    for palavra in ("assinar", "sign", "pkcs11", "token", "pin", "chave_privada"):
        assert not any(palavra in n.lower() for n in publicos), (
            f"«{palavra}» entre os nomes publicos: este modulo confere, "
            f"nao assina")


def test_nao_diz_que_a_firma_e_valida():
    """O modulo diz o que MEDIU, e nao o que nao conferiu.

    Validar a firma exige as ancoras da ICP-Brasil e a lista de revogacao,
    que esta casa nao tem. «Assinatura valida» sem isso e o carimbo que mente
    num papel que a serventia poe no mundo.
    """
    fonte = (RAIZ / "assinatura_digital.py").read_text(encoding="utf-8")
    codigo = "\n".join(l for l in fonte.splitlines()
                       if not l.strip().startswith("#"))
    assert '"valida"' not in codigo and "'valida'" not in codigo
    assert "assinatura_valida" not in codigo


# ------------------------------------------------------- ler o arquivo


@tem_os_reais
def test_le_o_p7s_real_e_acha_o_documento_dentro():
    """A ASSINATURA E ANEXADA, e nao destacada: o PDF vem embrulhado."""
    pdf, p7s = um_real()
    lido = AD.ler(p7s)
    assert lido["documento"] == pdf
    assert lido["sha256_do_documento"] == AD.sha256(pdf)


@tem_os_reais
def test_quem_assinou_sai_do_sid_e_nao_do_primeiro_certificado():
    """O PACOTE REAL TRAZ TRES CERTIFICADOS, e a pessoa e a do MEIO.

    Pegar o primeiro diria que quem assinou foi «AC SOLUTI v5», que e a
    autoridade certificadora e nao o tabeliao.
    """
    _, p7s = um_real()
    lido = AD.ler(p7s)
    assert len(lido["certificados"]) == 3
    assert lido["certificados"][0].startswith("AC "), "o primeiro e a AC"
    q = lido["quem_assinou"]
    # QUEM ASSINOU É UMA PESSOA DE VERDADE (o tabelião de outra serventia), e
    # o nome e o CPF dele saem do próprio arquivo — não se escrevem aqui
    # (sanitização B3, 10/10/2026). O que se prova é que é a PESSOA, e não a AC.
    assert q["nome"] and not q["nome"].startswith("AC ")
    assert q["cpf"].isdigit() and len(q["cpf"]) == 11


def test_arquivo_que_nao_e_assinatura_recusa_dizendo_o_que_se_espera():
    with pytest.raises(AD.AssinaturaError) as e:
        AD.ler(b"isto nao e um p7s")
    assert "assinador gera" in str(e.value)


def test_arquivo_vazio_recusa():
    with pytest.raises(AD.AssinaturaError):
        AD.ler(b"")


def test_arquivo_grande_demais_recusa_antes_de_ler():
    with pytest.raises(AD.AssinaturaError) as e:
        AD.ler(b"x" * (AD.LIMITE + 1))
    assert "teto" in str(e.value)


# ------------------------------------------------------- conferir


@tem_os_reais
def test_o_documento_assinado_e_o_que_a_casa_emitiu():
    pdf, p7s = um_real()
    r = AD.conferir(p7s, documento=pdf)
    assert r["confere"] is True
    assert r["serve"] is True
    assert r["problemas"] == []


@tem_os_reais
def test_documento_TROCADO_e_apanhado():
    """A CONFERENCIA QUE PROTEGE, e ela nao precisa de criptografia.

    Assinar o arquivo errado e o caso real: o balcao gera dois papeis e
    assina o de cima.
    """
    _, p7s = um_real()
    outro = sorted(PASTA_REAL.glob("*.pdf"))[1].read_bytes()
    r = AD.conferir(p7s, documento=outro)
    assert r["confere"] is False and r["serve"] is False
    assert "NAO e o que a casa emitiu" in AD.por_que_nao_serve(r)


@tem_os_reais
def test_documento_ALTERADO_depois_de_gerado_e_apanhado():
    """Um byte a mais e outro documento — e o sha256 diz isso."""
    pdf, p7s = um_real()
    r = AD.conferir(p7s, documento=pdf + b" ")
    assert r["confere"] is False


@tem_os_reais
def test_cpf_diferente_do_esperado_e_apanhado():
    pdf, p7s = um_real()
    r = AD.conferir(p7s, documento=pdf, cpf_esperado="000.000.042-60")
    assert r["serve"] is False
    assert "00000004260" in AD.por_que_nao_serve(r)


@tem_os_reais
def test_cpf_esperado_com_mascara_bate_com_o_do_certificado():
    """O CPF chega mascarado da tela e cru do certificado."""
    pdf, p7s = um_real()
    cru = AD.ler(p7s)["quem_assinou"]["cpf"]
    mascarado = f"{cru[:3]}.{cru[3:6]}.{cru[6:9]}-{cru[9:]}"
    r = AD.conferir(p7s, documento=pdf, cpf_esperado=mascarado)
    assert r["serve"] is True


@tem_os_reais
def test_sem_cpf_esperado_o_modulo_NAO_inventa_dono():
    """Ele diz quem assinou e deixa a comparacao para quem sabe."""
    pdf, p7s = um_real()
    r = AD.conferir(p7s, documento=pdf)
    assert r["serve"] is True
    assert r["quem_assinou"]["cpf"]


@tem_os_reais
def test_ensaio_os_SEIS_instrumentos_reais():
    """O ENSAIO CONTRA O ARQUIVO DE VERDADE — o que prova o leitor.

    Os seis sao de Carira/SE, do acervo que o oficial trouxe: **layout, sim;
    convencao, nao.** A forma do documento assinado e nacional.
    """
    p7s_todos = sorted(PASTA_REAL.glob("*.p7s"))
    assert len(p7s_todos) == 6
    quem = set()
    for p7s in p7s_todos:
        pdf = p7s.with_suffix("").read_bytes()
        r = AD.conferir(p7s.read_bytes(), documento=pdf)
        assert r["serve"] is True, p7s.name
        quem.add(r["quem_assinou"]["cpf"])
        # O PDF SOZINHO NAO TEM FIRMA: quem guardar so ele guardou papel sem
        # assinatura. Medido — nenhum dos seis traz `/Sig` dentro.
        assert b"Adobe.PPKLite" not in pdf
    # Os seis foram assinados pela MESMA pessoa (o CPF vem do arquivo).
    assert len(quem) == 1 and len(next(iter(quem))) == 11


# ------------------------------------------------------- a fila


def documento_na_fila(con, *, entidade="pt_atos", eid=1, sha="a" * 64) -> int:
    cur = con.execute(
        """INSERT INTO as_documentos(entidade, entidade_id, titulo,
               sha256_documento, criado_em)
           VALUES (?,?,'Instrumento de protesto',?,?)""",
        (entidade, eid, sha, AGORA))
    return int(cur.lastrowid)


def test_a_fila_e_da_casa_inteira_e_nao_de_uma_atribuicao():
    """Hoje sao nove papeis, e o instrumento e o decimo. O que muda de um para
    o outro e o documento, e nao a assinatura."""
    con = banco()
    documento_na_fila(con, entidade="pt_atos", eid=1)
    documento_na_fila(con, entidade="rc_certidoes", eid=1, sha="b" * 64)
    assert len(AD.pendentes(con)) == 2
    assert len(AD.pendentes(con, entidade="pt_atos")) == 1


def test_o_assinado_sai_da_fila():
    con = banco()
    doc = documento_na_fila(con)
    con.execute("UPDATE as_documentos SET assinado_em=? WHERE id=?",
                (AGORA, doc))
    assert AD.pendentes(con) == []


def test_um_papel_por_ato():
    """Dois registros do mesmo ato fariam o balcao assinar duas vezes, com o
    segundo sobrescrevendo o primeiro sem ninguem ver qual vale."""
    con = banco()
    documento_na_fila(con, entidade="pt_atos", eid=7)
    with pytest.raises(sqlite3.IntegrityError):
        documento_na_fila(con, entidade="pt_atos", eid=7, sha="c" * 64)


def test_as_contagens_separam_o_que_espera_do_que_voltou():
    con = banco()
    documento_na_fila(con, entidade="pt_atos", eid=1)
    doc = documento_na_fila(con, entidade="pt_atos", eid=2, sha="b" * 64)
    con.execute("UPDATE as_documentos SET assinado_em=? WHERE id=?",
                (AGORA, doc))
    assert AD.contagens(con) == {"pt_atos": {"espera": 1, "assinados": 1}}


def test_o_banco_nao_guarda_o_arquivo():
    """O banco viaja no backup, e o backup ja saiu da serventia. O que fica
    aqui e o sha256 e o caminho."""
    con = banco()
    colunas = {c[1] for c in con.execute("PRAGMA table_info(as_documentos)")}
    for proibida in ("conteudo", "documento", "assinado", "blob", "pdf"):
        assert proibida not in colunas
    assert "sha256_documento" in colunas and "caminho_documento" in colunas
