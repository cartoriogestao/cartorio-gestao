"""As telas da retificação de área — e o que só o teste de TELA pega.

POR QUE ESTE ARQUIVO EXISTE SEPARADO DO `test_retificacao.py`
    Aquele prova que o **domínio** recusa. Este prova que a **tela** chama o
    domínio — e são coisas diferentes.

    Este projeto pagou por essa diferença duas vezes: em 27/08 os testes de rota
    passavam montando o POST **com o token na mão**, e nenhum provava que a TELA
    mandava o token que a rota exige; e no usucapião o teste de domínio rodava
    com a trava de chave estrangeira desligada, de modo que registrar um ato
    inexistente passava ali e virava HTTP 500 na tela.

    Por isso aqui o POST vai **pela tela**, com o token que a tela deu.
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

import retificacao as RT                                         # noqa: E402
import rt_tjma as NORMA                                          # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-29T09:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _matricula(casa, numero="1083"):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, situacao, criado_em)
               VALUES (?, '2', 'ATIVA', ?)""", (numero, AGORA))
    return int(cur.lastrowid)


def _abrir(casa, url="/registro-imoveis/retificacoes"):
    r = casa["cliente"].get(url)
    assert r.status_code == 200, f"{url} não abriu ({r.status_code})"
    return " ".join(r.get_data(as_text=True).split())


def _autuar_pela_tela(casa, *, especie=NORMA.GEORREFERENCIADA, rural="1",
                      numero="1/2026"):
    m = _matricula(casa)
    html = casa["cliente"].get(
        "/registro-imoveis/retificacoes/nova").get_data(as_text=True)
    r = casa["cliente"].post(
        "/registro-imoveis/retificacoes/nova",
        data={"csrf_token": _token(html), "numero": numero,
              "matricula_id": str(m), "especie": especie,
              "fundamento": NORMA.A_REQUERIMENTO, "rural": rural,
              "requerente_nome": "ANTONIO JARDINEIRO PEREIRA"},
        follow_redirects=True)
    assert r.status_code == 200
    con = _con(casa)
    linha = con.execute("SELECT id FROM rt_processos WHERE numero = ?",
                        (numero,)).fetchone()
    assert linha, "a tela não autuou o processo"
    return int(linha["id"]), m


def test_a_recusa_volta_com_o_que_foi_digitado(casa):
    """A recusa redirecionava para a tela em branco, e a matrícula, o profissional e a área se perdiam (31/10/2026)."""
    m = _matricula(casa)
    html = casa["cliente"].get("/registro-imoveis/retificacoes/nova").get_data(as_text=True)
    saida = casa["cliente"].post(
        "/registro-imoveis/retificacoes/nova",
        data={"csrf_token": _token(html), "numero": "   ", "matricula_id": str(m), "especie": NORMA.GEORREFERENCIADA,
              "fundamento": NORMA.A_REQUERIMENTO, "rural": "0", "requerente_nome": "ANA EXEMPLO",
              "profissional_conselho": "CAU", "area_pretendida": "12,45 ha", "sigef_codigo": "ABC"},
        follow_redirects=True).get_data(as_text=True)
    assert "precisa de um número" in saida
    for trecho in (f'<option value="{m}" selected>', f'<option value="{NORMA.GEORREFERENCIADA}" selected>',
                   f'<option value="{NORMA.A_REQUERIMENTO}" selected>', 'name="rural" value="0" checked',
                   'value="ANA EXEMPLO"', "<option selected>CAU</option>", 'value="12,45 ha"', 'value="ABC"'):
        assert trecho in saida, trecho
    assert 'name="rural" value="1" checked' not in saida
    assert _con(casa).execute("SELECT COUNT(*) FROM rt_processos").fetchone()[0] == 0


# ------------------------------------------------ as telas abrem


def test_a_lista_abre_vazia_dizendo_o_que_e(casa):
    """Lista vazia que só mostra nada faz o operador achar que quebrou — custou
    três respostas na tela de assinaturas."""
    html = _abrir(casa)
    assert "Nenhum processo de retificação aberto" in html
    assert "arts. 212 e 213" in html


def test_a_tela_do_codigo_de_normas_abre_e_a_leitura_fecha(casa):
    html = _abrir(casa, "/registro-imoveis/retificacoes/codigo-de-normas")
    assert "arts. 587 a 605" in html
    assert "a leitura fecha" in html
    assert "Atenção: há artigos citados fora" not in html


def test_a_tela_das_normas_mostra_o_prazo_do_sigef(casa):
    html = _abrir(casa, "/registro-imoveis/retificacoes/codigo-de-normas")
    assert "art. 620, § 2º" in html
    assert "30" in html


def test_a_tela_das_normas_mostra_as_duas_regras_opostas(casa):
    html = _abrir(casa, "/registro-imoveis/retificacoes/codigo-de-normas")
    assert "art. 599, § 1º" in html
    assert "art. 599, § 3º" in html
    assert "a porta só fecha quando a averbação sai" in html


# ------------------------------------------------ a tela autua de verdade


def test_a_tela_autua_e_o_checklist_nasce_junto(casa):
    pid, _ = _autuar_pela_tela(casa)
    con = _con(casa)
    itens = RT.conferencia(con, pid)
    assert len(itens) == len(NORMA.checklist(georreferenciada=True, rural=True))


def test_usuario_comum_pode_autuar_retificacao_georreferenciamento(casa):
    """Relato Beatriz: o perfil USER trabalhava no balcão, mas a rota de
    abertura aceitava só perfis antigos/administrativos."""
    casa["db"].create_user("beatriz", "Beatriz Exemplo Souza",
                           SENHA, "USER")
    m = _matricula(casa, "2001")
    c = casa["app"].test_client()
    c.post("/login",
           data={"username": "beatriz", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    html = c.get("/registro-imoveis/retificacoes/nova").get_data(as_text=True)
    # A FRASE É A DA TELA, e não a que este teste supunha. Medido em 18/09/2026
    # nos nove pacotes guardados (3.6.59 a 3.6.141): a tela escreve «Novo
    # processo de retificação de área» desde antes do primeiro deles, e
    # «Processo de retificação» não existe em arquivo nenhum do produto — só
    # dentro deste teste. A assercao cobrava uma frase que nunca existiu, e por
    # isso ficou vermelha sem ninguém ter mexido em nada. O que este teste
    # precisa provar é o que ele faz em seguida: o USER abre a tela E autua.
    assert "Novo processo de retificação" in html
    r = c.post(
        "/registro-imoveis/retificacoes/nova",
        data={"csrf_token": _token(html), "numero": "LEI-1/2026",
              "matricula_id": str(m), "especie": NORMA.GEORREFERENCIADA,
              "fundamento": NORMA.A_REQUERIMENTO, "rural": "1",
              "requerente_nome": "ANTONIO JARDINEIRO PEREIRA"},
        follow_redirects=True)
    assert r.status_code == 200
    assert "checklist do art. 592" in r.get_data(as_text=True)


def test_a_ficha_diz_o_que_fazer_agora(casa):
    """Num rito de meses, «e agora?» é a pergunta que mais se repete."""
    pid, _ = _autuar_pela_tela(casa)
    html = _abrir(casa, f"/registro-imoveis/retificacoes/{pid}")
    assert "O que fazer agora" in html
    assert "art. 592" in html


def test_a_ficha_junta_documento_e_marca_item_da_conferencia(casa):
    """O anexo do georreferenciamento entra como peça e cumpre o item
    correspondente da conferência do art. 592."""
    pid, _ = _autuar_pela_tela(casa)
    html = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    assert 'enctype="multipart/form-data"' in html
    assert 'type="file" name="documento"' in html
    item = RT.conferencia(_con(casa), pid)[0]["item"]

    r = casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/peca",
        data={"csrf_token": _token(html), "tipo": item,
              "descricao": "Planta e memorial",
              "documento": (io.BytesIO(b"%PDF-1.4\nplanta"), "planta.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True)
    assert r.status_code == 200
    #  A TELA DIZ AS DUAS COISAS: qual arquivo entrou — que é o que prova ao
    #  balcão que subiu o certo — e que o item da conferência já foi marcado.
    #
    #  **ESTA SEGUNDA FRASE SUMIU EM 21/09/2026**, quando o envio de vários
    #  arquivos nasceu (a 3.6.155 não tem o ramo; a 3.6.156 tem), e foi por ela
    #  que este teste ficou vermelho. Ele cobrava a frase literal
    #  «Documento juntado ao processo», que o ramo novo trocou pelo nome do
    #  arquivo; agora cobra **o que não pode sumir**.
    pagina = r.get_data(as_text=True)
    assert "planta.pdf juntado ao processo" in pagina
    assert "marcado como atendido" in pagina

    con = _con(casa)
    peca = con.execute("SELECT * FROM rt_pecas WHERE processo_id=?",
                       (pid,)).fetchone()
    assert peca["arquivo"]
    assert peca["sha256"]
    assert Path(peca["arquivo"]).exists()
    estado = con.execute(
        "SELECT situacao FROM rt_conferencia WHERE processo_id=? AND item=?",
        (pid, item)).fetchone()[0]
    assert estado == "ATENDIDO"
    anexo = con.execute(
        "SELECT * FROM attachments WHERE entity_type='RT_PECA'").fetchone()
    assert anexo["entity_id"] == peca["id"]


def test_a_ficha_mostra_a_dispensa_com_o_artigo(casa):
    """Dispensa que não se vê vira dúvida no balcão, e a dúvida vira notificação
    a mais."""
    pid, _ = _autuar_pela_tela(casa)
    con = _con(casa)
    with con:
        RT.anotar_confrontante(con, pid, nome="JOAO DA MATA", agora=AGORA,
                               divisa_afetada=False)
    html = _abrir(casa, f"/registro-imoveis/retificacoes/{pid}")
    assert "não precisam ser notificados" in html
    assert "art. 596, parágrafo único" in html


# ------------------------------------------------ a tela não repete a regra


def test_a_rota_recusa_decisao_procedente_com_item_pendente(casa):
    """MANDADO DIRETO PARA A ROTA, sem passar pelos botões: quem recusa é o
    domínio, e a tela só esconde o botão por educação."""
    pid, _ = _autuar_pela_tela(casa)
    html = _abrir(casa, f"/registro-imoveis/retificacoes/{pid}")
    r = casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/decidir",
        data={"csrf_token": _token(html), "sentido": "PROCEDENTE",
              "fundamento": "está tudo em ordem e conferido"},
        follow_redirects=True)
    assert "conferência do art. 592" in r.get_data(as_text=True)
    con = _con(casa)
    assert RT.processo(con, pid)["decisao"] is None


def test_a_rota_recusa_averbacao_de_ato_que_nao_existe(casa):
    """Sem conferir, batia na chave estrangeira e virava HTTP 500 no fim de um
    processo de meses. **Com a trava LIGADA**, que é como a tela roda — e é por
    isso que este teste está no arquivo de tela."""
    pid, _ = _autuar_pela_tela(casa)
    con = _con(casa)
    with con:
        for item in RT.conferencia(con, pid):
            RT.marcar_item(con, pid, item["item"], situacao="ATENDIDO",
                           agora=AGORA)
        RT.decidir(con, pid, sentido=RT.PROCEDENTE,
                   fundamento="planta e memorial conferem com as divisas",
                   agora=AGORA, hoje="2026-08-29")
    html = _abrir(casa, f"/registro-imoveis/retificacoes/{pid}")
    r = casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/averbacao",
        data={"csrf_token": _token(html), "ato_id": "99999"},
        follow_redirects=True)
    assert r.status_code == 200, "a rota estourou em vez de recusar"
    assert "Não achei o ato" in r.get_data(as_text=True)


def test_a_rota_recusa_impugnacao_sem_fundamento(casa):
    pid, _ = _autuar_pela_tela(casa)
    con = _con(casa)
    with con:
        cid = RT.anotar_confrontante(con, pid, nome="X", agora=AGORA)
    html = _abrir(casa, f"/registro-imoveis/retificacoes/{pid}")
    r = casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/resposta",
        data={"csrf_token": _token(html), "confrontante_id": str(cid),
              "resposta": "IMPUGNOU", "impugnacao": "não"},
        follow_redirects=True)
    assert "mera alegação de prejuízo" in r.get_data(as_text=True)


# ------------------------------------------------ o prazo do SIGEF na tela


def test_o_prazo_do_sigef_aparece_no_alto_da_lista(casa):
    """É O ÚNICO PRAZO DESTE RITO QUE É DA SERVENTIA. Ele nasce depois do ato,
    com o cliente já fora do balcão, e não há ninguém de fora para cobrá-lo —
    por isso vem primeiro na tela."""
    pid, m = _autuar_pela_tela(casa)
    con = _con(casa)
    with con:
        for item in RT.conferencia(con, pid):
            RT.marcar_item(con, pid, item["item"], situacao="ATENDIDO",
                           agora=AGORA)
        RT.decidir(con, pid, sentido=RT.PROCEDENTE,
                   fundamento="planta e memorial conferem com as divisas",
                   agora=AGORA, hoje="2026-08-29")
        cur = con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, teor,
                   teor_formato, origem, hash_ato, lavrado_em)
               VALUES (?, 'AVERBACAO', 16, 'teor', 'texto', 'SISTEMA',
                       'hash-de-ensaio', ?)""", (m, AGORA))
        RT.registrar_averbacao(con, pid, ato_id=int(cur.lastrowid),
                               agora=AGORA)
    html = _abrir(casa)
    assert "Prazo da serventia" in html
    assert "30 dias" in html
    assert "art. 620, § 2º" in html


def test_a_ficha_oferece_o_sigef_e_ele_encerra_o_processo(casa):
    pid, m = _autuar_pela_tela(casa)
    con = _con(casa)
    with con:
        for item in RT.conferencia(con, pid):
            RT.marcar_item(con, pid, item["item"], situacao="ATENDIDO",
                           agora=AGORA)
        RT.decidir(con, pid, sentido=RT.PROCEDENTE,
                   fundamento="planta e memorial conferem com as divisas",
                   agora=AGORA, hoje="2026-08-29")
        cur = con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, teor,
                   teor_formato, origem, hash_ato, lavrado_em)
               VALUES (?, 'AVERBACAO', 16, 'teor', 'texto', 'SISTEMA',
                       'hash-de-ensaio', ?)""", (m, AGORA))
        RT.registrar_averbacao(con, pid, ato_id=int(cur.lastrowid),
                               agora=AGORA)
    html = _abrir(casa, f"/registro-imoveis/retificacoes/{pid}")
    assert "Requerer o registro no SIGEF" in html
    r = casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/sigef",
        data={"csrf_token": _token(html), "quando": "2026-09-10",
              "protocolo": "SIGEF-2026-0001"},
        follow_redirects=True)
    assert r.status_code == 200
    con = _con(casa)
    assert RT.processo(con, pid)["situacao"] == RT.ENCERRADO
    assert RT.sigef_a_vencer(con) == []


# ------------------------------------------------ o menu e o token


def test_a_retificacao_esta_no_menu_do_registro_de_imoveis(casa):
    """As rotas se chamam `ri_retificacao_*` para caírem neste grupo: o módulo
    sai do PREFIXO, e é aqui que a matrícula está."""
    html = _abrir(casa, "/registro-imoveis/retificacoes")
    assert "Retificação de área" in html


def test_todo_formulario_da_ficha_manda_o_token(casa):
    """A varredura geral já cobre isto, mas aqui ele é conferido na ficha que
    mais tem formulário — foi um token que faltava que derrubou os quatro
    cliques do selador em 27/08."""
    pid, _ = _autuar_pela_tela(casa)
    con = _con(casa)
    with con:
        RT.anotar_confrontante(con, pid, nome="X", agora=AGORA)
    bruto = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    formularios = re.findall(r"<form\b.*?</form>", bruto, re.S)
    assert len(formularios) >= 4
    sem = [f[:80] for f in formularios if "csrf_token" not in f]
    assert not sem, f"formulário sem token: {sem}"
