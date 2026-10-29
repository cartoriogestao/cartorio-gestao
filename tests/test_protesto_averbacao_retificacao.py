"""A AVERBAÇÃO DE RETIFICAÇÃO DE ERRO MATERIAL, DE OFÍCIO — Lei 9.492/1997, art. 25.

    «A averbação de retificação de erros materiais pelo serviço poderá ser
     efetuada de ofício ou a requerimento do interessado, sob
     responsabilidade do Tabelião de Protesto de Títulos.»

Nasceu do caso de 29/10/2026: a carga do acervo gravou o credor errado, o
cadastro foi corrigido, e o termo dos protestos já lavrados congelou o credor
errado — ou nenhum. O oficial aprovou a averbação de ofício.

O QUE ESTES TESTES GUARDAM
      - **o registro que diz outro credor, ou nenhum, é achado** — e o termo
        do acervo (sem texto) e o termo certo não são;
      - **o instrumento não sai contra o registro**: recusa até a averbação, e
        depois sai com a menção — sem repetir o nome que constou errado;
      - **só o ADMIN em pessoa lavra**, com a afirmação expressa do contrato
        comum (caixa «Afirmo» e 30 letras); o robô não lavra, nem pela rota;
      - **o ato retificado não muda**: a averbação é ato novo, ligado a ele,
        sem selo, sem custas e sem lugar em livro;
      - **o que se diz errado tem de estar escrito**, e a mesma retificação não
        se averba duas vezes;
      - **a certidão a menciona**, e o instrumento e a certidão sem averbação
        saem como saíam;
      - a auditoria leva a afirmação e o ato, **sem nome de credor**.

Dados fictícios (LGPD): a lista de `tests/fixtures/anti_vazamento`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from navegador_de_teste import postar_e_seguir  # noqa: E402

import protesto_averbacao as PAV  # noqa: E402
import protesto_certidao as PTC  # noqa: E402
import protesto_instrumento as PI  # noqa: E402
import protesto_termo as TERMO  # noqa: E402
from bd_nativo import banco as _banco  # noqa: E402

from test_protesto_instrumento import AGORA, SERVENTIA, banco  # noqa: E402
from test_protesto_aviso_web import _con, _sessao, _token  # noqa: E402

# Os documentos são os fictícios da lista do anti-vazamento.
CNPJ_CERTO = "00000001000055"          # 00.000.001/0000-55
CPF_ERRADO = "00000000272"             # 000.000.002-72 — a «outra pessoa»
CPF_DEVEDOR = "00000000191"            # 000.000.001-91
CREDOR_CERTO = "EMPRESA DE EXEMPLO S.A."
CREDOR_ERRADO = "JOAO DE EXEMPLO"
HOJE = "2026-10-29T16:00:00"
AFIRMA = ("Afirmo, sob minha responsabilidade, que o credor do termo veio da "
          "carga errada do acervo e o cadastro do título já foi corrigido.")


def _titulo(bd, *, cedente, documento, numero="AV-1/1",
            protocolo="2610280001", apresentante="BANCO DE EXEMPLO") -> int:
    return int(bd.escrever(
        """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
               valor_centavos, saldo_centavos, protocolo, apresentante_codigo,
               apresentante_nome, motivo_protesto, tipo_protesto, situacao,
               origem, origem_chave, criado_em, cedente_nome, cedente_documento)
           VALUES ('DMI', %s, %s, 69979, 69979, %s, '237', %s,
                   '1', 'C', 'PROTESTADO', 'CRA', %s, %s, %s, %s)
           RETURNING id""",
        (numero, numero, protocolo, apresentante, f"t:{numero}", AGORA,
         cedente, documento))[0]["id"])


def _protestado(con, *, cedente=CREDOR_ERRADO, documento=CPF_ERRADO,
                numero="AV-1/1", protocolo="2610280001",
                apresentante="BANCO DE EXEMPLO") -> tuple[int, int]:
    """Um título protestado com o TERMO QUALIFICADO, montado como o livro o
    monta — com o credor que o cadastro tinha no dia. Devolve (título, ato)."""
    bd = _banco(con)
    tid = _titulo(bd, cedente=cedente, documento=documento, numero=numero,
                  protocolo=protocolo, apresentante=apresentante)
    bd.escrever(
        """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
               documento_numero, nome_norm)
           VALUES (%s, 'MARIA DE EXEMPLO', 'CPF', %s, 'maria de exemplo')""",
        (tid, CPF_DEVEDOR))
    bd.escrever("""INSERT INTO pt_atos(titulo_id, tipo, data_ato, criado_em)
                   VALUES (%s, 'APONTAMENTO', '2026-10-20', %s)""", (tid, AGORA))
    bd.escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json, criado_em)
           VALUES (%s, 'INTIMACAO', '2026-10-22',
                   '{"modo": "EDITAL", "motivo_nao_entrega": "Ausente"}', %s)""",
        (tid, AGORA))
    ato = int(bd.escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, criado_em, folha,
               numero_ordem, rotulo)
           VALUES (%s, 'PROTESTO', '2026-10-28T14:31:30', %s, 194, 1806, '194v')
           RETURNING id""", (tid, AGORA))[0]["id"])
    fatos = TERMO.dados_do_titulo(con, tid)
    teor = TERMO.montar(edital_data=fatos["edital_data"],
                        edital_motivo=fatos["edital_motivo"],
                        motivo_protesto=fatos["motivo_protesto"],
                        tipo_protesto=fatos["tipo_protesto"],
                        qualificacao_do_registro=fatos["qualificacao_do_registro"])
    bd.escrever("UPDATE pt_atos SET teor = %s WHERE id = %s", (teor, ato))
    return tid, ato


def _corrigir_o_cadastro(con, tid: int) -> None:
    _banco(con).escrever(
        """UPDATE pt_titulos SET cedente_nome = %s, cedente_documento = %s
            WHERE id = %s""", (CREDOR_CERTO, CNPJ_CERTO, tid))


def _lavrar(con, ato: int, **muda):
    sugestao = PAV.divergencia_do_credor(con, _banco(con).um(
        "SELECT * FROM pt_atos WHERE id = %s", (ato,)))
    args = {"elemento": sugestao["elemento"], "constava": sugestao["constava"],
            "correto": sugestao["correto"], "afirmo": True, "afirmacao": AFIRMA,
            "agora": HOJE, "usuario": "MARIO EXEMPLO DOS SANTOS",
            "papel": "ADMIN", "eh_robo": False}
    args.update(muda)
    return PAV.lavrar(con, ato, **args)


# ------------------------------------------------- o que o registro diz


def test_o_registro_com_outro_credor_e_achado_e_o_instrumento_recusa():
    con = banco()
    tid, ato = _protestado(con)
    teor = _banco(con).valor("SELECT teor FROM pt_atos WHERE id = %s", (ato,))
    assert PAV.registro_qualificado(teor)
    assert PAV.credor_no_registro(teor) == CREDOR_ERRADO
    assert PAV.divergencias_do_titulo(con, tid) == []     # ainda igual ao cadastro
    _corrigir_o_cadastro(con, tid)
    [d] = PAV.divergencias_do_titulo(con, tid)
    assert d["ato_id"] == ato and d["forma"] == PAV.ERRADO
    assert d["constava"] == CREDOR_ERRADO
    assert d["correto"] == f"{CREDOR_CERTO}, CPF/CNPJ {CNPJ_CERTO}"
    with pytest.raises(PI.InstrumentoError, match="averbação de retificação"):
        PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)


def test_o_registro_sem_credor_e_omissao():
    con = banco()
    tid, ato = _protestado(con, cedente=None, documento=None)
    teor = _banco(con).valor("SELECT teor FROM pt_atos WHERE id = %s", (ato,))
    assert PAV.registro_qualificado(teor) and PAV.credor_no_registro(teor) is None
    _corrigir_o_cadastro(con, tid)
    [d] = PAV.divergencias_do_titulo(con, tid)
    assert d["forma"] == PAV.OMITIDO and d["constava"] == ""
    with pytest.raises(PI.InstrumentoError, match="não indica credor nenhum"):
        PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)


def test_o_registro_certo_e_o_protesto_sem_texto_nao_sao_alcancados():
    """O protesto do acervo do E-Ofício não tem texto aqui (1.186 na produção
    em 29/10/2026), e não pode ser barrado nem oferecido para averbar."""
    con = banco()
    tid, _ato = _protestado(con, cedente=CREDOR_CERTO, documento=CNPJ_CERTO)
    assert PAV.divergencias_do_titulo(con, tid) == []
    bd = _banco(con)
    sem_texto = _titulo(bd, cedente=CREDOR_CERTO, documento=CNPJ_CERTO,
                        numero="AV-2/1", protocolo="2610280002")
    bd.escrever("""INSERT INTO pt_atos(titulo_id, tipo, data_ato, criado_em, origem)
                   VALUES (%s, 'PROTESTO', '2026-01-10', %s, 'EOFICIO')""",
                (sem_texto, AGORA))
    assert PAV.divergencias_do_titulo(con, sem_texto) == []
    assert PAV.atos_que_se_retificam(con, sem_texto) == []


def test_o_nome_com_ponto_no_meio_se_le_inteiro():
    """«S. A.» tem ponto e espaço no meio: a peça vai até a do devedor."""
    teor = ("Registro do protesto: folha 1, em 01/10/2026. Credor "
            "(sacador/favorecido): EMPRESA S. A. DE EXEMPLO. Devedor: MARIA "
            "DE EXEMPLO. CERTIFICO que não houve manifestação.")
    assert PAV.credor_no_registro(teor) == "EMPRESA S. A. DE EXEMPLO"
    com_doc = teor.replace("DE EXEMPLO. Devedor",
                           f"DE EXEMPLO, CPF/CNPJ {CNPJ_CERTO}. Devedor", 1)
    assert PAV.credor_no_registro(com_doc) == "EMPRESA S. A. DE EXEMPLO"


# ------------------------------------------------------- quem lavra


@pytest.mark.parametrize("papel, robo", [("MANAGER", False), ("USER", False),
                                         ("ADMIN", True)])
def test_so_o_admin_em_pessoa_lavra(papel, robo):
    con = banco()
    tid, ato = _protestado(con)
    _corrigir_o_cadastro(con, tid)
    with pytest.raises(PAV.AverbacaoError, match="só o oficial"):
        _lavrar(con, ato, papel=papel, eh_robo=robo)
    assert _banco(con).valor(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo = %s", (PAV.TIPO,)) == 0


@pytest.mark.parametrize("afirmo, afirmacao", [
    (False, AFIRMA), (True, ""), (True, "Afirmo que sim."), (False, "")])
def test_a_afirmacao_expressa_e_obrigatoria(afirmo, afirmacao):
    con = banco()
    tid, ato = _protestado(con)
    _corrigir_o_cadastro(con, tid)
    with pytest.raises(PAV.AverbacaoError, match="afirmação expressa"):
        _lavrar(con, ato, afirmo=afirmo, afirmacao=afirmacao)


def test_o_que_se_diz_errado_tem_de_estar_escrito():
    con = banco()
    tid, ato = _protestado(con)
    _corrigir_o_cadastro(con, tid)
    with pytest.raises(PAV.AverbacaoError, match="não está escrito"):
        _lavrar(con, ato, constava="OUTRA PESSOA QUE NAO CONSTA")
    with pytest.raises(PAV.AverbacaoError, match="mesmo"):
        _lavrar(con, ato, constava=CREDOR_ERRADO, correto=CREDOR_ERRADO)
    with pytest.raises(PAV.AverbacaoError, match="Escreva o que passa a constar"):
        _lavrar(con, ato, correto="")


def test_so_o_texto_lavrado_do_protesto_ou_do_cancelamento_se_retifica():
    con = banco()
    tid, _ato = _protestado(con)
    _corrigir_o_cadastro(con, tid)
    intimacao = _banco(con).valor(
        "SELECT id FROM pt_atos WHERE titulo_id = %s AND tipo = 'INTIMACAO'", (tid,))
    with pytest.raises(PAV.AverbacaoError, match="INTIMACAO"):
        PAV.lavrar(con, intimacao, elemento=PAV.ELEMENTO_CREDOR, constava="",
                   correto=CREDOR_CERTO, afirmo=True, afirmacao=AFIRMA,
                   agora=HOJE, usuario="mario", papel="ADMIN", eh_robo=False)
    with pytest.raises(PAV.AverbacaoError, match="outro título"):
        _lavrar(con, _ato, titulo_id=tid + 999)


# ----------------------------------------------- o que a averbação é


def test_o_ato_retificado_nao_muda_e_a_averbacao_e_ato_novo():
    con = banco()
    tid, ato = _protestado(con)
    _corrigir_o_cadastro(con, tid)
    bd = _banco(con)
    antes = dict(bd.um("SELECT * FROM pt_atos WHERE id = %s", (ato,)))
    feito = _lavrar(con, ato, titulo_id=tid)
    depois = dict(bd.um("SELECT * FROM pt_atos WHERE id = %s", (ato,)))
    assert antes == depois                       # o termo ficou como foi lavrado
    nova = bd.um("SELECT * FROM pt_atos WHERE id = %s", (feito["ato_id"],))
    assert nova["tipo"] == PAV.TIPO and nova["titulo_id"] == tid
    assert not nova["selo"] and nova["lancamento_id"] is None
    assert nova["livro_id"] is None and nova["numero_ordem"] is None
    assert nova["criado_por"] == "MARIO EXEMPLO DOS SANTOS"
    detalhe = json.loads(nova["detalhe_json"])
    assert detalhe["ato_retificado_id"] == ato and detalhe["de_oficio"] is True
    assert detalhe["afirmacoes_expressas"][0]["afirmacao"] == AFIRMA
    teor = nova["teor"]
    assert "art. 25 da Lei 9.492/1997" in teor and "de ofício" in teor
    assert f"constou erroneamente como “{CREDOR_ERRADO}”" in teor
    assert f"“{CREDOR_CERTO}, CPF/CNPJ {CNPJ_CERTO}”" in teor
    assert "MARIA DE EXEMPLO" not in teor        # o devedor não é o que se corrige
    # a situação do título e a divergência
    assert bd.valor("SELECT situacao FROM pt_titulos WHERE id = %s", (tid,)) == "PROTESTADO"
    assert PAV.divergencias_do_titulo(con, tid) == []


def test_a_omissao_tem_a_sua_frase():
    con = banco()
    tid, ato = _protestado(con, cedente=None, documento=None)
    _corrigir_o_cadastro(con, tid)
    feito = _lavrar(con, ato)
    assert feito["forma"] == PAV.OMITIDO
    assert "Nele deixou de constar o credor (sacador/favorecido)." in feito["teor"]
    assert "erroneamente" not in feito["teor"]


def test_o_credor_que_e_o_proprio_apresentante_ainda_e_omissao():
    """Medido na produção em 29/10/2026: em três títulos o credor é o próprio
    apresentante, e o termo saiu sem a peça «Credor». O nome está no texto —
    como APRESENTANTE —, e isso não supre a omissão do credor."""
    con = banco()
    tid, ato = _protestado(con, cedente=None, documento=None,
                           apresentante=CREDOR_CERTO)
    _banco(con).escrever("UPDATE pt_titulos SET cedente_nome = %s WHERE id = %s",
                         (CREDOR_CERTO, tid))
    [d] = PAV.divergencias_do_titulo(con, tid)
    assert d["forma"] == PAV.OMITIDO and d["correto"] == CREDOR_CERTO
    feito = _lavrar(con, ato)
    assert "Nele deixou de constar o credor (sacador/favorecido)." in feito["teor"]


def test_omissao_onde_o_texto_tem_credor_e_recusada():
    con = banco()
    tid, ato = _protestado(con)
    _corrigir_o_cadastro(con, tid)
    with pytest.raises(PAV.AverbacaoError, match="não omissão"):
        _lavrar(con, ato, constava="")


def test_preparar_mostra_o_que_lavrar_grava_e_nao_grava_nada():
    """O script que mede antes de gravar usa `preparar(travar=False)`: a
    prévia tem de ser o teor que `lavrar` grava, e não uma cópia parecida."""
    con = banco()
    tid, ato = _protestado(con)
    _corrigir_o_cadastro(con, tid)
    d = PAV.divergencias_do_titulo(con, tid)[0]
    previa = PAV.preparar(con, ato, elemento=d["elemento"], constava=d["constava"],
                          correto=d["correto"], afirmo=True, afirmacao=AFIRMA,
                          agora=HOJE, usuario="mario", papel="ADMIN",
                          eh_robo=False, travar=False)
    assert _banco(con).valor("SELECT COUNT(*) FROM pt_atos WHERE tipo = %s",
                             (PAV.TIPO,)) == 0
    feito = _lavrar(con, ato, usuario="mario")
    assert feito["teor"] == previa["teor"]


def test_a_mesma_retificacao_nao_se_averba_duas_vezes():
    con = banco()
    tid, ato = _protestado(con)
    _corrigir_o_cadastro(con, tid)
    feito = _lavrar(con, ato)
    with pytest.raises(PAV.AverbacaoError, match=f"ato {feito['ato_id']}"):
        PAV.lavrar(con, ato, elemento=PAV.ELEMENTO_CREDOR, constava=CREDOR_ERRADO,
                   correto=f"{CREDOR_CERTO}, CPF/CNPJ {CNPJ_CERTO}", afirmo=True,
                   afirmacao=AFIRMA, agora=HOJE, usuario="mario", papel="ADMIN",
                   eh_robo=False)


def test_a_auditoria_leva_a_afirmacao_e_o_ato_sem_nome_de_credor():
    con = banco()
    tid, ato = _protestado(con)
    _corrigir_o_cadastro(con, tid)
    feito = _lavrar(con, ato)
    linhas = PAV.para_a_auditoria(feito)
    assert [x[0] for x in linhas] == ["AFIRMACAO_EXPRESSA", PAV.ACAO_DA_AUDITORIA]
    assert all(x[1] == "pt_atos" and x[2] == feito["ato_id"] for x in linhas)
    assert linhas[0][3]["regra"] == PAV.REGRA_DA_AFIRMACAO
    assert linhas[0][3]["afirmacao"] == AFIRMA and linhas[0][3]["o_que_faltava"]
    texto = json.dumps(linhas, ensure_ascii=False)
    assert CREDOR_ERRADO not in texto and CREDOR_CERTO not in texto


# ---------------------------------------- o instrumento e a certidão


def test_depois_da_averbacao_o_instrumento_sai_com_a_mencao():
    con = banco()
    tid, ato = _protestado(con)
    _corrigir_o_cadastro(con, tid)
    _lavrar(con, ato)
    r = PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)
    assert "Consta à margem do registro deste protesto averbação de " \
           "retificação de erro material, lavrada de ofício em 29/10/2026" in r["teor"]
    assert "pela qual se retificou o credor (sacador/favorecido)" in r["teor"]
    assert CREDOR_CERTO in r["teor"]              # a descrição lê o cadastro
    assert CREDOR_ERRADO not in r["teor"]         # e a menção não repete o errado
    corpo = json.loads(_banco(con).valor(
        "SELECT corpo_json FROM pt_instrumentos WHERE id = %s", (r["id"],)))
    assert corpo["averbacoes"][0]["elemento"] == PAV.ELEMENTO_CREDOR


def test_o_instrumento_sem_averbacao_sai_como_saia():
    con = banco()
    tid, _ato = _protestado(con, cedente=CREDOR_CERTO, documento=CNPJ_CERTO)
    r = PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)
    assert "averbação de retificação" not in r["teor"]
    corpo = json.loads(_banco(con).valor(
        "SELECT corpo_json FROM pt_instrumentos WHERE id = %s", (r["id"],)))
    assert "averbacoes" not in corpo              # o mesmo corpo — e hash — de antes


def test_a_certidao_menciona_a_averbacao():
    con = banco()
    tid, ato = _protestado(con)
    _corrigir_o_cadastro(con, tid)
    _lavrar(con, ato)
    mencoes = PAV.mencoes(con, tid)
    assert mencoes == [{"id": mencoes[0]["id"], "data": HOJE,
                        "elemento": PAV.ELEMENTO_CREDOR,
                        "ato": "registro do protesto"}]
    linha = PTC._linha_do_protesto(
        {"numero_titulo": "AV-1/1", "valor": "699,79",
         "data_protesto": "2026-10-28", "cedente": CREDOR_CERTO,
         "averbacoes": mencoes}, 1)
    assert ("averbação de retificação de erro material do registro do "
            "protesto, de ofício, em 29/10/2026 (Lei 9.492/1997, art. 25): "
            "retificou-se o credor (sacador/favorecido)") in linha
    sem = PTC._linha_do_protesto({"numero_titulo": "AV-1/1", "valor": "699,79",
                                  "data_protesto": "2026-10-28"}, 1)
    assert "averbação" not in sem


# ------------------------------------------------------------ a tela


def _cenario_na_casa(s) -> tuple[int, int]:
    from database import Database
    db = Database(s["banco"])
    with db.transaction() as con:
        tid, ato = _protestado(con, numero="AV-9/1", protocolo="2610280009")
        _corrigir_o_cadastro(con, tid)
    return tid, ato


def test_o_oficial_lavra_pela_ficha_e_a_auditoria_fica(cg_casa):
    s = _sessao(cg_casa, "ADMIN")
    tid, ato = _cenario_na_casa(s)
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "data-credor-a-averbar" in ficha
    assert "data-averbacao-retificacao" in ficha
    assert f"/protesto/{tid}/averbacao-retificacao" in ficha
    feito = postar_e_seguir(s["c"], f"/protesto/{tid}/averbacao-retificacao", {
        "csrf_token": _token(ficha), "ato_id": str(ato),
        "elemento": PAV.ELEMENTO_CREDOR, "constava": CREDOR_ERRADO,
        "correto": f"{CREDOR_CERTO}, CPF/CNPJ {CNPJ_CERTO}",
        "afirmo": "1", "afirmacao": AFIRMA}).get_data(as_text=True)
    assert "Averbação de retificação lavrada" in feito
    assert "data-credor-a-averbar" not in feito
    assert "data-averbado-a-margem" in feito
    con = _con(s)
    assert con.execute("SELECT COUNT(*) FROM pt_atos WHERE tipo = ?",
                       (PAV.TIPO,)).fetchone()[0] == 1
    linha = con.execute(
        "SELECT entity_type, details FROM audit_logs "
        "WHERE action = 'AFIRMACAO_EXPRESSA' ORDER BY id DESC LIMIT 1").fetchone()
    assert linha["entity_type"] == "pt_atos"
    assert json.loads(linha["details"])["regra"] == PAV.REGRA_DA_AFIRMACAO
    assert con.execute("SELECT COUNT(*) FROM audit_logs WHERE action = ?",
                       (PAV.ACAO_DA_AUDITORIA,)).fetchone()[0] == 1


def test_sem_a_afirmacao_a_ficha_recusa_e_nada_se_grava(cg_casa):
    s = _sessao(cg_casa, "ADMIN")
    tid, ato = _cenario_na_casa(s)
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    volta = postar_e_seguir(s["c"], f"/protesto/{tid}/averbacao-retificacao", {
        "csrf_token": _token(ficha), "ato_id": str(ato),
        "elemento": PAV.ELEMENTO_CREDOR, "constava": CREDOR_ERRADO,
        "correto": CREDOR_CERTO, "afirmacao": AFIRMA}).get_data(as_text=True)
    assert "afirmação expressa" in volta
    assert _con(s).execute("SELECT COUNT(*) FROM pt_atos WHERE tipo = ?",
                           (PAV.TIPO,)).fetchone()[0] == 0


def test_o_balcao_ve_o_aviso_e_nao_lavra(cg_casa):
    s = _sessao(cg_casa, "USER")
    tid, ato = _cenario_na_casa(s)
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "data-credor-a-averbar" in ficha
    assert "data-averbacao-retificacao" not in ficha
    assert "Ela é do oficial" in " ".join(ficha.split())
    token = _token(s["c"].get("/protesto/novo").get_data(as_text=True))
    r = s["c"].post(f"/protesto/{tid}/averbacao-retificacao", data={
        "csrf_token": token, "ato_id": str(ato), "elemento": PAV.ELEMENTO_CREDOR,
        "constava": CREDOR_ERRADO, "correto": CREDOR_CERTO, "afirmo": "1",
        "afirmacao": AFIRMA})
    assert r.status_code == 403
    assert _con(s).execute("SELECT COUNT(*) FROM pt_atos WHERE tipo = ?",
                           (PAV.TIPO,)).fetchone()[0] == 0


def test_o_robo_nao_alcanca_a_rota():
    import rotas_do_robo as RR
    import selo_robo as SR
    assert "protesto_averbacao_retificacao" not in RR.ROTAS_PERMITIDAS_AO_ROBO
    assert not SR.rota_permitida_ao_robo("protesto_averbacao_retificacao")


def test_o_ato_nao_sela_e_nao_entra_na_conferencia_do_selo():
    import protesto as PT
    import protesto_selo_previo as PSELO
    assert PAV.TIPO in PT.TIPOS_ATO
    assert PAV.TIPO in PSELO.ATOS_SEM_SELO_PROPRIO
    assert PAV.TIPO not in PSELO.TIPOS_QUE_SELAM
    assert not PSELO.pede_selo_agora(PAV.TIPO)
