"""
O TEXTO QUE VAI NO REGISTRO DO PROTESTO — e este sistema nunca o teve.

COMO APARECEU
    Pela regua que o oficial deu em 01/09/2026: *«sobre tudo que o e-oficio
    faz, tente buscar dados dentro do banco de dados. Se nao encontrar,
    possivelmente nao e importante»*. A tabela apareceu com **1.132 linhas**
    contra **1.164 protestos** — quase um por protesto —, e o nosso
    `lancar_protesto` gravava livro, folha e numero de ordem, e mais nada.

    E o mesmo defeito do Registro Civil, achado em 29/08: «o termo e o texto
    que vai no livro, e este sistema nunca o teve». Segunda atribuicao.

O QUE SE MEDIU NAS 1.132 LINHAS
    23 formas distintas, e as 23 sao a mesma base mais duas frases:

        base ............................. 1.126   (99,5%)
        «pagamento a posteriori» ......... 1.105   (97,6%)
        «intimado por Edital em <data>» .. 1.078   (95,2%)
        «pelo motivo <motivo>» ........... 1.007

O QUE ESTES TESTES GUARDAM
      - o texto sai NAS FORMAS MEDIDAS, e o padrao e o desta casa — copiado
        do catalogo do E-Oficio, e nao redigido aqui;
      - a frase do edital sai dos FATOS do titulo, e so quando houve edital:
        escreve-la numa intimacao em maos afirmaria no livro uma publicacao
        que nao houve;
      - o MOTIVO ENTRA UMA VEZ — o E-Oficio o repetia («Ausente Ausente» 24
        vezes) porque cada edital emitido acrescentava o seu;
      - o termo CONGELA no ato;
      - e o MODELO E O TEXTO, e nao o esqueleto dele. Este foi um defeito meu
        que o guarda do catalogo apanhou.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_da_casa as MOD
import protesto as PT
import protesto_termo as TERMO
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-09-01T10:00:00"
SV = {"unit_name": "SERVENTIA", "cidade": "Cidade Exemplo", "uf": "MA"}


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo(con) -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
               valor_centavos, saldo_centavos, situacao, origem, criado_em)
           VALUES ('DMI','84713/1','00200000991',148278,148278,'RECEBIDO',
                   'CRA',?)""", (AGORA,))
    tid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
               documento_numero) VALUES (?,'MARIA SANTOS','CPF','04785512388')""",
        (tid,))
    return tid


# ------------------------------------------------ as formas medidas


def test_o_texto_sai_na_forma_que_a_casa_escreveu():
    """A forma mais comum das 23: base + a posteriori + edital com motivo —
    912 das 1.132 linhas medidas."""
    texto = TERMO.montar(edital_data="2023-05-26", edital_motivo="Ausente")
    assert "CERTIFICO que não houve manifestação" in texto
    assert "ART. 9º-A DA LEI Nº 9.430/1996" in texto
    assert "pagamento a posteriori" in texto
    assert "O Sacado foi intimado por Edital em 26/05/2023 pelo motivo Ausente." in texto


def test_sem_edital_a_frase_NAO_entra_e_nao_sobra_linha_vazia():
    texto = TERMO.montar(edital_data=None)
    assert "Edital" not in texto
    assert "\n\n" not in texto
    assert texto.strip() == texto


# ------------------------------------------------- texto corrido, sem claros
#
# «o corpo de todos os atos do cartorio eh texto corrido, sem espacos» — o
# oficial, 07/09/2026. Até essa data `montar()` juntava as partes com `"\n"`:
# o texto ia para `pt_atos.teor` — o próprio Livro de Registro de Protestos —
# com quebra de linha real entre a base, a frase do pagamento a posteriori e
# a do edital. É o mesmo `claro` que o art. 795, § 2º do Código de Normas
# proíbe, e a mesma regra que `notas_modelos.py` já cumpre.

def test_o_termo_MONTADO_nao_tem_quebra_de_linha():
    texto = TERMO.montar(edital_data="2023-05-26", edital_motivo="Ausente")
    assert "\n" not in texto


def test_o_termo_MONTADO_nao_tem_espaco_duplo_nem_antes_de_pontuacao():
    for dados in ({"edital_data": "2023-05-26", "edital_motivo": "Ausente"},
                  {"edital_data": None}):
        texto = TERMO.montar(**dados)
        assert "  " not in texto, dados
        assert not re.search(r"\s[,.;:]", texto), dados


def test_o_motivo_entra_UMA_VEZ():
    """O E-Ofício o repetia: «pelo motivo Ausente Ausente» aparece 24 vezes
    nas linhas medidas, e três vezes seguidas em outras 4 — cada edital
    emitido acrescentava o seu. Reemitir edital é rotina nesta casa: são
    1.618 avisos para 1.361 títulos."""
    frase = TERMO.frase_do_edital(data="2023-05-26", motivo="Ausente")
    assert frase.count("Ausente") == 1


def test_a_frase_termina_com_PONTO():
    """Em 7 linhas medidas a seguinte veio colada: «...pelo motivo Ausente
    Este protesto foi registrado...»."""
    assert TERMO.frase_do_edital(data="2023-05-26",
                                 motivo="Ausente").endswith(".")
    assert TERMO.frase_do_edital(data="2023-05-26").endswith(".")


def test_edital_sem_motivo_nao_escreve_a_expressao_solta():
    frase = TERMO.frase_do_edital(data="2023-05-26", motivo=None)
    assert "pelo motivo" not in frase
    assert "26/05/2023" in frase


def test_a_data_sai_como_o_livro_escreve():
    assert "26/05/2023" in TERMO.frase_do_edital(data="2023-05-26")


def test_data_ilegivel_nao_gera_frase_com_lixo():
    """Melhor a frase não sair do que sair afirmando um edital numa data que
    ninguém sabe qual é."""
    assert TERMO.frase_do_edital(data=None) == ""
    assert TERMO.frase_do_edital(data="") == ""


# ------------------------------------------- os fatos saem do título


def test_a_frase_do_edital_sai_da_INTIMACAO_do_titulo():
    con = banco()
    tid = titulo(con)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_intimacao(con, tid, modo="EDITAL", agora="2026-08-20",
                        codigo_edital="ED-2026-014")
    fatos = TERMO.dados_do_titulo(con, tid)
    assert fatos["edital_data"] == "2026-08-20"


def test_intimacao_PESSOAL_nao_gera_a_frase_do_edital():
    """Escrevê-la numa intimação em mãos afirmaria no livro uma publicação
    que não houve."""
    con = banco()
    tid = titulo(con)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_intimacao(con, tid, modo="PESSOAL", agora="2026-08-20")
    assert TERMO.dados_do_titulo(con, tid)["edital_data"] is None


def test_a_ULTIMA_intimacao_e_a_que_conta():
    """O aviso não é um por título — 1.618 para 1.361 —, e reemitir é rotina.
    O texto do livro descreve a intimação que levou a ESTE protesto."""
    con = banco()
    tid = titulo(con)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_intimacao(con, tid, modo="PESSOAL", agora="2026-08-10")
    PT.lancar_intimacao(con, tid, modo="EDITAL", agora="2026-08-28",
                        codigo_edital="ED-2026-015")
    assert TERMO.dados_do_titulo(con, tid)["edital_data"] == "2026-08-28"


# ------------------------------------------------- o termo no ato


def test_o_protesto_lavrado_GRAVA_o_texto():
    con = banco()
    tid = titulo(con)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_intimacao(con, tid, modo="EDITAL", agora="2026-08-20",
                        codigo_edital="ED-2026-014")
    r = PT.lancar_protesto(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    teor = con.execute("SELECT teor FROM pt_atos WHERE id=?",
                       (r["ato_id"],)).fetchone()[0]
    assert "CERTIFICO" in teor
    assert "Edital em 20/08/2026" in teor


def test_o_termo_CONGELA():
    """É o texto que foi escrito no livro naquele dia. Remontá-lo depois faria
    o livro de hoje discordar do papel — e corrigir protesto é averbar ao
    lado, não reescrever."""
    con = banco()
    tid = titulo(con)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_intimacao(con, tid, modo="EDITAL", agora="2026-08-20",
                        codigo_edital="ED-2026-014")
    r = PT.lancar_protesto(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    antes = con.execute("SELECT teor FROM pt_atos WHERE id=?",
                        (r["ato_id"],)).fetchone()[0]
    assert "20/08/2026" in antes

    # MUDA-SE O FATO POR BAIXO — a data da intimação —, e o texto lavrado
    # continua o mesmo. Este é o teste de verdade do congelamento: lançar uma
    # intimação nova não serve, porque o domínio a recusa depois do protesto
    # («só se intima título já apontado») — e ele está certo.
    con.execute("UPDATE pt_atos SET data_ato='2020-01-01' "
                "WHERE titulo_id=? AND tipo='INTIMACAO'", (tid,))
    depois = con.execute("SELECT teor FROM pt_atos WHERE id=?",
                         (r["ato_id"],)).fetchone()[0]
    assert depois == antes
    assert "20/08/2026" in depois


# --------------------------------------------- o modelo que o oficial edita


def test_o_MODELO_E_O_TEXTO_e_nao_o_esqueleto():
    """ESTE FOI UM DEFEITO MEU, e o guarda do catálogo o apanhou.

    Eu havia posto como padrão `"{base}\\n{posteriori}\\n{edital}"` — 28
    caracteres. O oficial abriria a tela de editar e veria **três
    marcadores**, com a frase que afirma o art. 9º-A da Lei 9.430/1996 — que é
    a razão de este modelo ir ao catálogo — invisível e ineditável.
    """
    padrao = MOD.padrao_de("PT_TERMO_PROTESTO")
    assert len(padrao) > 200
    assert "CERTIFICO" in padrao
    assert "9.430/1996" in padrao
    assert "{edital}" in padrao


def test_um_marcador_so_e_ele_e_o_edital():
    """As demais frases são texto, e se escrevem inteiras no modelo — quem
    escreve o termo não deveria precisar de condição para dizer que houve
    edital. É a razão de o formato ser `CHAVES` e não Jinja."""
    padrao = MOD.padrao_de("PT_TERMO_PROTESTO")
    import re
    assert set(re.findall(r"\{(\w+)\}", padrao)) == {"edital"}


def test_o_catalogo_declara_o_formato_CHAVES():
    entrada = next(c for c in MOD.CATALOGO
                   if c["chave"] == "PT_TERMO_PROTESTO")
    assert entrada["formato"] == "CHAVES"
    assert entrada["atribuicao"] == "Protesto"


def test_marcador_que_nao_existe_recusa_com_mensagem_de_balcao():
    with pytest.raises(TERMO.TermoError, match="marcador que não existe"):
        TERMO.montar(modelo="{base} e {nao_existe}")


def test_o_modelo_editado_manda():
    texto = TERMO.montar(modelo="Só isto. {edital}",
                         edital_data="2023-05-26")
    assert texto.startswith("Só isto.")
    assert "CERTIFICO" not in texto


# ------------------------------------- e o texto tem de estar À VISTA


def test_a_ficha_MOSTRA_o_texto_que_foi_ao_livro(cg_casa):
    """GRAVAR E NÃO MOSTRAR É «PEÇA PRONTA SEM CHAMADOR» OUTRA VEZ — e foi o
    que eu fiz na primeira hora deste módulo: `lancar_protesto` passou a
    escrever o teor, e nenhuma tela o lia de volta.

    Aqui o preço é alto: numa correição a pergunta é o que o registro do
    protesto diz, e a resposta estaria só dentro do banco.
    """
    import glob
    import re as _re

    from app import create_app
    from database import Database

    senha = "Senha#12345"
    app = cg_casa['app']
    banco_ = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "JEAN", senha, "ADMIN")
    # O PROTESTO ESTA DESLIGADO DE FABRICA desde 01/09/2026 — ordem do
    # oficial. Estes testes exercitam as TELAS dele, e por isso o LIGAM
    # aqui, de proposito e a vista: eles provam que o modulo funciona
    # quando ele voltar, que e o que «fica para um futuro» quer dizer.
    cg_casa['db'].set_settings({"modulo_protesto_ligado": "1"})
    c = app.test_client()

    def token(html):
        return _re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                          html).group(1)

    c.post("/login", data={"username": "tabeliao", "password": senha,
                           "csrf_token": token(c.get("/login").get_data(
                               as_text=True))}, follow_redirects=True)

    con = sqlite3.connect(banco_)
    con.row_factory = sqlite3.Row
    with con:
        tid = titulo(con)
        PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
        PT.lancar_intimacao(con, tid, modo="EDITAL", agora="2026-08-20",
                            codigo_edital="ED-2026-014")
        PT.lancar_protesto(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    con.close()

    html = c.get(f"/protesto/{tid}").get_data(as_text=True)
    assert "O texto que foi ao livro" in html
    assert "CERTIFICO que não houve manifestação" in html
    assert "Edital em 20/08/2026" in html
