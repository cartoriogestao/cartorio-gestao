"""
Testes das telas do usucapiao — os autos, o dossie e a volta da analise.

O QUE ELES CONFEREM
    O caminho inteiro do balcao, e as travas que importam:

      - autua, junta peca, movimenta, responde, confere e decide pela tela;
      - o dossie sai mascarado por padrao e o `.md` baixa;
      - gerar dossie fica na AUDITORIA, com o sha256 do que saiu — tirar dado
        da casa e ato que se registra;
      - a analise volta por conferir, e a decisao apoiada nela e recusada ate
        alguem ler;
      - a tela nao repete a regra do dominio: quem recusa e o modulo.
"""
from __future__ import annotations

import glob
import io
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, papel)
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _post(s, rota: str, origem: str, **campos) -> str:
    c = s["c"]
    token = _token(c.get(origem).get_data(as_text=True))
    return c.post(rota, data={"csrf_token": token, **campos},
                  follow_redirects=True).get_data(as_text=True)


def _autuar(s, numero="US-2026-001", modalidade="EXTRAORDINARIA") -> int:
    _post(s, "/usucapiao/novo", "/usucapiao", numero=numero,
          modalidade=modalidade, requerente_nome="MARIA DA SILVA",
          requerente_documento="12345678901",
          imovel_descricao="Lote 4 da Quadra B",
          imovel_municipio="Cidade Exemplo")
    con = _con(s)
    pid = con.execute("SELECT id FROM us_processos WHERE numero=?",
                      (numero,)).fetchone()["id"]
    con.close()
    return pid


# ------------------------------------------------------------- a lista


def test_a_lista_abre_e_explica_que_e_processo(s):
    html = s["c"].get("/usucapiao").get_data(as_text=True)
    assert "216-A" in html
    assert "Nenhum processo" in html


def test_autua_pela_tela_e_o_checklist_ja_nasce(s):
    pid = _autuar(s)
    html = s["c"].get(f"/usucapiao/{pid}").get_data(as_text=True)
    assert "Conferência do rito" in html
    assert "Ata notarial do tabelião" in html
    # e a tela já diz o que fazer
    assert "O que fazer agora" in html


def test_numero_repetido_e_recusado_pela_tela(s):
    _autuar(s)
    html = _post(s, "/usucapiao/novo", "/usucapiao", numero="US-2026-001",
                 modalidade="ORDINARIA")
    assert "Já existe processo" in html


# ------------------------------------------------------- peças e rito


def test_juntar_peca_marca_o_checklist(s):
    pid = _autuar(s)
    html = _post(s, f"/usucapiao/{pid}/peca", f"/usucapiao/{pid}",
                 tipo="ATA_NOTARIAL", descricao="Ata do 1º Tabelionato",
                 teor="Compareceu a requerente e declarou posse desde 2005.")
    assert "Documento juntado" in html
    con = _con(s)
    estado = con.execute(
        """SELECT estado FROM us_conferencia
            WHERE processo_id=? AND item='ATA_NOTARIAL'""", (pid,)).fetchone()[0]
    assert estado == "CUMPRIDO"


def test_juntar_peca_aceita_upload_e_guarda_no_arquivo_do_sistema(s):
    """Relato Beatriz: anexar não era anexo — só aceitava nome/caminho.

    O upload real precisa ir para o arquivo do Cartório Gestão, com hash e
    vínculo de anexo, para não depender de uma pasta solta do usuário.
    """
    pid = _autuar(s)
    html = s["c"].get(f"/usucapiao/{pid}").get_data(as_text=True)
    assert 'enctype="multipart/form-data"' in html
    assert 'type="file" name="documento"' in html

    r = s["c"].post(
        f"/usucapiao/{pid}/peca",
        data={
            "csrf_token": _token(html),
            "tipo": "ATA_NOTARIAL",
            "descricao": "Ata em PDF",
            "documento": (io.BytesIO(b"%PDF-1.4\nata"), "ata.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=True)
    assert "ata.pdf juntado aos autos" in r.get_data(as_text=True)

    con = _con(s)
    peca = con.execute("SELECT * FROM us_pecas WHERE processo_id=?",
                       (pid,)).fetchone()
    assert peca["nome_arquivo"] == "ata.pdf"
    assert peca["sha256"]
    assert Path(peca["caminho"]).exists()
    anexo = con.execute(
        "SELECT * FROM attachments WHERE entity_type='USUCAPIAO_PECA'").fetchone()
    assert anexo["entity_id"] == peca["id"]


def test_a_tela_recusa_pular_etapa(s):
    pid = _autuar(s)
    html = _post(s, f"/usucapiao/{pid}/etapa", f"/usucapiao/{pid}",
                 etapa="EDITAL")
    assert "pular a etapa" in html


def test_movimenta_com_prazo_e_o_vencido_aparece(s):
    pid = _autuar(s)
    _post(s, f"/usucapiao/{pid}/movimento", f"/usucapiao/{pid}",
          tipo="NOTIFICACAO", descricao="Notificado o confrontante do leste.",
          destinatario="JOÃO DO LADO", destinatario_papel="CONFRONTANTE",
          prazo_dias="15", prazo_inicio="2020-01-01", prazo_fim="2020-01-16")
    html = s["c"].get(f"/usucapiao/{pid}").get_data(as_text=True)
    assert "vencido" in html
    assert "decurso do prazo" in html      # virou próximo passo
    # e a lista também marca
    assert "vencido" in s["c"].get("/usucapiao").get_data(as_text=True)


def test_o_silencio_e_resposta_e_se_grava(s):
    # No rito do art. 216-A o silêncio tem efeito: é valor, não ausência.
    pid = _autuar(s)
    _post(s, f"/usucapiao/{pid}/movimento", f"/usucapiao/{pid}",
          tipo="NOTIFICACAO", descricao="Notificado.", destinatario="VIZINHO",
          prazo_dias="15", prazo_fim="2020-01-16")
    con = _con(s)
    mid = con.execute(
        "SELECT id FROM us_movimentos WHERE tipo='NOTIFICACAO'").fetchone()[0]
    con.close()
    html = _post(s, f"/usucapiao/{pid}/responder/{mid}", f"/usucapiao/{pid}",
                 resposta="SILENCIO")
    assert "Silêncio" in html


def test_dispensar_item_sem_motivo_e_recusado_pela_tela(s):
    pid = _autuar(s)
    html = _post(s, f"/usucapiao/{pid}/conferencia", f"/usucapiao/{pid}",
                 item="JUSTO_TITULO", estado="DISPENSADO", motivo="não tem")
    assert "motivo escrito" in html


# ------------------------------------------------------------ o dossiê


def test_o_dossie_sai_mascarado_por_padrao(s):
    pid = _autuar(s)
    html = s["c"].get(f"/usucapiao/{pid}/dossie").get_data(as_text=True)
    assert "12345678901" not in html
    assert "Documentos mascarados" in html
    assert "SHA-256" in html


def test_o_dossie_sem_mascara_avisa_em_vermelho(s):
    pid = _autuar(s)
    html = s["c"].get(f"/usucapiao/{pid}/dossie?mascarar=nao").get_data(as_text=True)
    assert "NÃO está mascarado" in html


def test_o_dossie_baixa_como_arquivo(s):
    pid = _autuar(s)
    r = s["c"].get(f"/usucapiao/{pid}/dossie?formato=txt")
    assert r.status_code == 200
    assert "attachment" in r.headers["Content-Disposition"]
    assert "US-2026-001" in r.headers["Content-Disposition"]
    assert "216-A" in r.get_data(as_text=True)


def test_gerar_dossie_fica_na_auditoria(s):
    # Tirar dado da casa é ato que se registra — com o sha256 do que saiu e se
    # foi mascarado.
    pid = _autuar(s)
    s["c"].get(f"/usucapiao/{pid}/dossie?mascarar=nao")
    con = _con(s)
    linha = con.execute(
        """SELECT * FROM audit_logs WHERE action='USUCAPIAO_DOSSIE'
            ORDER BY id DESC LIMIT 1""").fetchone()
    assert linha is not None
    assert "mascarado" in (linha["details"] or "")
    assert "false" in (linha["details"] or "").lower()


# -------------------------------------------------- a análise e a decisão


def _cumprir_tudo(s, pid):
    con = _con(s)
    with con:
        con.execute(
            """UPDATE us_conferencia SET estado='CUMPRIDO'
                WHERE processo_id=?""", (pid,))
    con.close()


def test_a_analise_volta_por_conferir(s):
    pid = _autuar(s)
    html = _post(s, f"/usucapiao/{pid}/analise", f"/usucapiao/{pid}",
                 parecer="Falta a ART do profissional que assinou a planta.",
                 ferramenta="IA de teste", dossie_sha256="abc123")
    assert "precisa da sua conferência" in html
    assert "Falta a ART" in s["c"].get(f"/usucapiao/{pid}").get_data(as_text=True)


def test_achados_em_json_invalido_nao_derrubam_o_parecer(s):
    pid = _autuar(s)
    html = _post(s, f"/usucapiao/{pid}/analise", f"/usucapiao/{pid}",
                 parecer="Está tudo certo.", achados_json="{isto não é json")
    assert "não estão em JSON válido" in html
    assert "o parecer em texto basta" in html.lower()


def test_decidir_apoiado_em_analise_nao_conferida_e_recusado_pela_tela(s):
    pid = _autuar(s)
    _cumprir_tudo(s, pid)
    _post(s, f"/usucapiao/{pid}/analise", f"/usucapiao/{pid}",
          parecer="Está tudo certo.")
    con = _con(s)
    aid = con.execute("SELECT id FROM us_analises").fetchone()[0]
    con.close()
    html = _post(s, f"/usucapiao/{pid}/decidir", f"/usucapiao/{pid}",
                 sentido="PROCEDENTE", analise_id=str(aid),
                 fundamento="A posse está comprovada pelos documentos juntados.",
                 teor="RECONHEÇO a usucapião.")
    assert "ainda não foi conferida" in html


def test_depois_de_conferir_a_analise_a_decisao_passa(s):
    pid = _autuar(s)
    _cumprir_tudo(s, pid)
    _post(s, f"/usucapiao/{pid}/analise", f"/usucapiao/{pid}",
          parecer="Está tudo certo.")
    con = _con(s)
    aid = con.execute("SELECT id FROM us_analises").fetchone()[0]
    con.close()
    html = _post(s, f"/usucapiao/{pid}/analise/{aid}/conferir",
                 f"/usucapiao/{pid}")
    assert "Conferir não é concordar" in html
    html = _post(s, f"/usucapiao/{pid}/decidir", f"/usucapiao/{pid}",
                 sentido="PROCEDENTE", analise_id=str(aid),
                 fundamento="A posse está comprovada pelos documentos juntados.",
                 teor="RECONHEÇO a usucapião.")
    assert "Decisão lavrada" in html


def test_a_tela_avisa_quando_ha_item_pendente(s):
    pid = _autuar(s)
    html = s["c"].get(f"/usucapiao/{pid}").get_data(as_text=True)
    assert "item(ns) pendente(s)" in html
    assert "registro nulo" in html


def test_nao_se_decide_procedente_com_item_pendente(s):
    pid = _autuar(s)
    html = _post(s, f"/usucapiao/{pid}/decidir", f"/usucapiao/{pid}",
                 sentido="PROCEDENTE",
                 fundamento="A posse está comprovada pelos documentos juntados.",
                 teor="RECONHEÇO.")
    assert "do rito pendente" in html


def test_os_modelos_de_decisao_chegam_na_tela(s):
    pid = _autuar(s)
    html = s["c"].get(f"/usucapiao/{pid}").get_data(as_text=True)
    assert "COMPLETAR" in html                 # o modelo não finge estar pronto
    assert "MARIA DA SILVA" in html            # e vem preenchido


def test_decidir_nao_registra_e_a_tela_pede_o_registro(s):
    pid = _autuar(s)
    _cumprir_tudo(s, pid)
    _post(s, f"/usucapiao/{pid}/decidir", f"/usucapiao/{pid}",
          sentido="PROCEDENTE",
          fundamento="A posse está comprovada pelos documentos juntados.",
          teor="RECONHEÇO a usucapião.")
    html = s["c"].get(f"/usucapiao/{pid}").get_data(as_text=True)
    assert "Registrar o reconhecimento" in html
    assert "Decidir não é registrar" in html
    con = _con(s)
    assert con.execute("SELECT situacao FROM us_processos WHERE id=?",
                       (pid,)).fetchone()[0] == "EM_ANDAMENTO"


def _um_ato_de_ri(s) -> int:
    """Um ato de verdade no RI, para o registro ter a que se amarrar."""
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO ri_matriculas(numero, criado_em)
               VALUES ('4014','2026-08-24T09:00:00')""")
        mid = con.execute("SELECT id FROM ri_matriculas").fetchone()[0]
        con.execute(
            """INSERT INTO ri_atos(matricula_id, tipo, numero, hash_ato,
                   lavrado_em)
               VALUES (?, 'R', 1, 'abc', '2026-08-24T09:00:00')""", (mid,))
        ato_id = con.execute("SELECT id FROM ri_atos").fetchone()[0]
    con.close()
    return ato_id


def test_registrar_encerra_o_processo(s):
    pid = _autuar(s)
    _cumprir_tudo(s, pid)
    _post(s, f"/usucapiao/{pid}/decidir", f"/usucapiao/{pid}",
          sentido="PROCEDENTE",
          fundamento="A posse está comprovada pelos documentos juntados.",
          teor="RECONHEÇO a usucapião.")
    ato_id = _um_ato_de_ri(s)
    html = _post(s, f"/usucapiao/{pid}/registrar", f"/usucapiao/{pid}",
                 ato_id=str(ato_id), selo="REGAVD000000OD1Q8BV5TOOZE492")
    assert "registrado e encerrado" in html
    con = _con(s)
    assert con.execute("SELECT situacao FROM us_processos WHERE id=?",
                       (pid,)).fetchone()[0] == "REGISTRADO"


def test_registrar_em_ato_que_nao_existe_da_frase_de_balcao(s):
    # Sem a conferência, isto batia na chave estrangeira e virava HTTP 500 no
    # fim de um processo de meses. O teste de domínio não pegava: lá a trava
    # de FK está desligada.
    pid = _autuar(s)
    _cumprir_tudo(s, pid)
    _post(s, f"/usucapiao/{pid}/decidir", f"/usucapiao/{pid}",
          sentido="PROCEDENTE",
          fundamento="A posse está comprovada pelos documentos juntados.",
          teor="RECONHEÇO a usucapião.")
    html = _post(s, f"/usucapiao/{pid}/registrar", f"/usucapiao/{pid}",
                 ato_id="99999")
    assert "Não existe ato 99999" in html
    assert "Lavre o registro na matrícula primeiro" in html


def test_processo_encerrado_nao_oferece_mais_formulario(s):
    pid = _autuar(s)
    _cumprir_tudo(s, pid)
    _post(s, f"/usucapiao/{pid}/decidir", f"/usucapiao/{pid}",
          sentido="REMESSA_JUIZO",
          fundamento="Houve impugnação do confrontante do lado leste.",
          teor="REMETAM-SE os autos ao juízo.")
    html = s["c"].get(f"/usucapiao/{pid}").get_data(as_text=True)
    assert "Lançar movimento" not in html
    assert "Nada a fazer" in html


def test_o_usucapiao_aparece_no_menu_do_registro_de_imoveis(s):
    html = s["c"].get("/usucapiao").get_data(as_text=True)
    assert "Usucapião extrajudicial" in html
    assert "Matrículas" in html                # o menu do RI está aberto
