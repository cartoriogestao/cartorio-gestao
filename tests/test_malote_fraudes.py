"""Do malote para a lista de fraudes — 13/10/2026.

O que se guarda: a proposta leva a referência inteira do aviso (pedido do
oficial: «guarde a referência de onde veio o aviso de fraude»); nada entra na
lista sem aprovação; descartar exige motivo; aplicar usa a porta da casa e não
repete o alerta.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import malote_fraudes as MF                                      # noqa: E402

AVISO = {"codigo_malote": "81020265958952", "documento_malote": "CIRC-CSERVCOGEX_0002026.pdf",
         "assunto": "Suspeita de fraude em procuração pública", "remetente": "Coordenadoria Exemplo — TJMA",
         "enviado_em": "2026-10-13 10:59:18", "processos": "717762026; 0002737-02.2026.2.00.0806",
         "arquivo": r"arquivos\malote\entrada\CIRC\x.pdf", "resumo": "Procuração falsa em Cidade Exemplo/CE."}


@pytest.fixture()
def con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _p(**kw):
    p = dict(AVISO)
    p.update({"nome": "FULANO DE TAL EXEMPLO", "documento": None, "papel": "ENVOLVIDO",
              "trecho": "inquérito em face de FULANO DE TAL EXEMPLO"})
    p.update(kw)
    return p


def test_a_referencia_leva_codigo_documento_processo_e_trecho():
    r = MF.referencia(_p())
    assert r["origem"].startswith("Malote Digital nº 81020265958952")
    assert "CIRC-CSERVCOGEX_0002026.pdf" in r["origem"] and "717762026" in r["origem"]
    assert r["origem_data"] == "2026-10-13" and r["origem_orgao"].startswith("Coordenadoria")
    assert "Trecho: «inquérito em face de" in r["observacao"] and "Arquivo nesta casa" in r["observacao"]


def test_proposta_nao_entra_na_lista_sem_aprovacao(con):
    assert MF.carregar(con, [_p(), _p()]) == {"novas": 1, "repetidas": 1}
    assert MF.aplicar(con, usuario="mario") == {"incluidos": 0, "ja_havia": 0}
    assert con.execute("SELECT count(*) FROM fr_alertas").fetchone()[0] == 0


def test_aprovada_vira_alerta_com_a_referencia_e_nao_repete(con):
    MF.carregar(con, [_p(), _p(nome="BELTRANA EXEMPLO", papel="VITIMA", documento="000.000.001-91")])
    ids = [r[0] for r in con.execute("SELECT id FROM mt_alertas_propostos")]
    assert MF.revisar(con, ids, aprovar=True, revisor="mario") == 2
    assert MF.aplicar(con, usuario="mario") == {"incluidos": 2, "ja_havia": 0}
    a = con.execute("SELECT * FROM fr_alertas WHERE papel='VITIMA'").fetchone()
    assert a["documento"] == "00000000191" and a["origem"].startswith("Malote Digital nº 81020265958952")
    assert a["origem_data"] == "2026-10-13" and "Trecho:" in a["observacao"]
    assert con.execute("SELECT count(*) FROM mt_alertas_propostos WHERE situacao='APLICADO' "
                       "AND alerta_id IS NOT NULL").fetchone()[0] == 2
    # a mesma pessoa do mesmo aviso, proposta e aprovada de novo, não vira segundo alerta
    con.execute("DELETE FROM mt_alertas_propostos")
    MF.carregar(con, [_p()])
    MF.revisar(con, [con.execute("SELECT id FROM mt_alertas_propostos").fetchone()[0]], aprovar=True, revisor="mario")
    assert MF.aplicar(con, usuario="mario") == {"incluidos": 0, "ja_havia": 1}
    assert con.execute("SELECT count(*) FROM fr_alertas").fetchone()[0] == 2


def test_descartar_exige_motivo(con):
    MF.carregar(con, [_p()])
    i = con.execute("SELECT id FROM mt_alertas_propostos").fetchone()[0]
    with pytest.raises(MF.PropostaError, match="motivo"):
        MF.revisar(con, [i], aprovar=False, revisor="mario")
    assert MF.revisar(con, [i], aprovar=False, revisor="mario", motivo="homônimo, não é a pessoa") == 1


def test_papel_desconhecido_recusa(con):
    with pytest.raises(MF.PropostaError, match="Papel"):
        MF.carregar(con, [_p(papel="SUSPEITO")])


def test_a_pagina_mostra_a_referencia_e_o_trecho():
    html = MF.pagina_de_revisao([_p(id=1)])
    assert "Malote Digital nº 81020265958952" in html and "inquérito em face de" in html


# ================================================== PELA IA INTERNA (13/10/2026)
# «quando for fraude, apenas cadastrar em fraudes, sem tarefa» … «nem tarefa,
# nem expediente» … «pode ser a ia interna». O que se guarda: banco não entra;
# marca que não volta a ser nome não entra; documento que não confere entra só
# pelo nome; o que sai para a IA vai mascarado e volta com o número.

import json                                                       # noqa: E402
import re                                                         # noqa: E402


def test_a_regua_de_quem_entra():
    boas, fora = MF.pessoas_validas([
        {"nome": "FULANO DE TAL EXEMPLO", "documento": "000.000.001-91", "papel": "ENVOLVIDO", "trecho": "t"},
        {"nome": "Banco Bradesco S/A", "documento": "", "papel": "VITIMA"},
        {"nome": "SANTANDER", "papel": "DOCUMENTO"},
        {"nome": "[PESSOA_09]", "papel": "VITIMA"},
        {"nome": "BELTRANA EXEMPLO", "documento": "111.222.333-44", "papel": "vitima"},
        {"nome": "CICRANO EXEMPLO", "papel": "TESTEMUNHA"},
        {"nome": "FRAUDE", "papel": "DOCUMENTO"},
        {"nome": "FULANO DE TAL EXEMPLO", "documento": "00000000191", "papel": "ENVOLVIDO"},
    ])
    assert [(p["nome"], p["documento"], p["papel"]) for p in boas] == [
        ("FULANO DE TAL EXEMPLO", "00000000191", "ENVOLVIDO"), ("BELTRANA EXEMPLO", "", "VITIMA")]
    texto = " ".join(fora)
    assert "Bradesco" in texto and "SANTANDER" in texto and "[PESSOA_09]" in texto
    assert "TESTEMUNHA" in texto and "111" in texto and "«FRAUDE»: uma palavra só" in texto


def test_a_porta_da_ia_e_a_palavra_de_fraude():
    assert MF.parece_fraude("Suspeição de fraude.")
    assert MF.parece_fraude("", "procuração falsa lavrada em outra comarca")
    assert MF.parece_fraude("Comunica golpe com selo")
    assert not MF.parece_fraude("Circular sobre o recesso forense", "PORTARIA-COGEX_1942026.pdf")


def _ia_que_responde(pessoas, aviso=True, enviados=None):
    def conversar(pasta, *, provedor, sistema, conversa, ferramentas, modelo, maximo_de_saida, **_registro):
        texto = conversa[0]["texto"]
        if enviados is not None:
            enviados.append(texto)
        cpf = re.search(r"\[CPF_\d+\]", texto)
        saida = [dict(p, documento=(cpf.group(0) if p.get("documento") == "CPF" and cpf else p.get("documento")))
                 for p in pessoas]
        return {"texto": json.dumps({"aviso_de_fraude": aviso, "resumo": "Procuração falsa.",
                                     "processos": ["0001/2026"], "pessoas": saida}),
                "modelo": "claude-sonnet-5", "entrada": 100, "saida": 50, "provedor": "claude"}
    return conversar


def test_o_que_sai_vai_mascarado_e_volta_com_o_numero(tmp_path):
    enviados = []
    ia = _ia_que_responde([{"nome": "FULANO DE TAL EXEMPLO", "documento": "CPF", "papel": "ENVOLVIDO",
                            "trecho": "em face de FULANO"}], enviados=enviados)
    r = MF.ler_aviso(tmp_path, "Inquérito em face de FULANO DE TAL EXEMPLO, CPF 000.000.001-91, por fraude.",
                     conversar=ia, provedor="claude")
    assert "000.000.001-91" not in enviados[0] and "00000000191" not in enviados[0]
    # o nome vai por extenso: a máscara inteira juntava duas pessoas numa marca só
    assert "FULANO DE TAL EXEMPLO" in enviados[0]
    assert r["aviso"] and r["pessoas"][0]["documento"] == "00000000191"
    assert r["processos"] == ["0001/2026"] and r["modelo"] == "claude-sonnet-5"


def test_sem_chave_a_ia_recusa_e_nao_inventa(tmp_path):
    with pytest.raises(MF.PropostaError):
        MF.ler_aviso(tmp_path, "fraude", conversar=lambda *a, **k: pytest.fail("não podia chamar"))


# ================================================== REVISÃO DO L033 (17/10/2026)
# O que a conversão para o PostgreSQL nativo deixou, e a revisão achou:
#   - `tratar_grupo` travava outro assunto que `aplicar`, e os dois procuram e
#     incluem em `fr_alertas` pela mesma `_aplicar_uma`: sem a ponte (que hoje
#     tem uma trava só para tudo), um não esperaria o outro e o alerta dobraria;
#   - a linha de comando abria o banco com `sqlite3.connect`: fora do sistema
#     ninguém instala o desvio, e o acesso nativo recusa o sqlite3 cru;
#   - o `VACUUM INTO` levava o caminho escrito no SQL, e a ponte não lê o
#     apóstrofo dobrado: a cópia não saía e o comando recusava.

import banco_pg                                                   # noqa: E402

so_no_postgres = pytest.mark.skipif(
    not banco_pg.ativo(), reason="mede a trava e a porta do PostgreSQL (CG_PG_DSN)")

TEXTO_DO_AVISO = ("Ofício circular. Comunica-se a lavratura de procuração falsa atribuída a outra "
                  "serventia, com assinatura e selo falsificados, para que as serventias fiquem atentas. ") * 3


def _assunto_livre(chave: str) -> bool:
    """Outra conexão consegue a trava do assunto agora? Não espera por ela."""
    import psycopg
    with psycopg.connect(banco_pg.dsn(), autocommit=True) as outra:
        return bool(outra.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext(%s))", (chave,)).fetchone()[0])


@pytest.fixture()
def fora_do_sistema(monkeypatch):
    """O processo da linha de comando (os .cmd de tools/): ninguém montou
    `Database()`, e o `sqlite3.connect` é o de fábrica."""
    monkeypatch.setattr(sqlite3, "connect", banco_pg._CONNECT_ORIGINAL)


@so_no_postgres
def test_aplicar_e_a_ia_interna_incluem_o_alerta_sob_a_mesma_trava(con, cg_casa, tmp_path, monkeypatch):
    import agente_provedores as AP
    import malote_agente as MA
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, provedor=None: True)
    livre_ao_incluir = []
    original = MF._aplicar_uma

    def espiao(c, p, **kw):
        livre_ao_incluir.append(_assunto_livre("fr_alertas.aplicar_do_malote"))
        return original(c, p, **kw)

    monkeypatch.setattr(MF, "_aplicar_uma", espiao)
    # pela revisão do oficial
    MF.carregar(con, [_p()])
    MF.revisar(con, [con.execute("SELECT id FROM mt_alertas_propostos").fetchone()[0]],
               aprovar=True, revisor="mario")
    assert MF.aplicar(con, usuario="mario") == {"incluidos": 1, "ja_havia": 0}
    # pela IA interna, direto do malote (como a `rodada` do agente a chama)
    MA.init_schema(con)
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "Suspeita de fraude.pdf").write_bytes(b"%PDF-1.4\n% x\n%%EOF\n")
    ia = _ia_que_responde([{"nome": "BELTRANA EXEMPLO", "documento": "", "papel": "VITIMA",
                            "trecho": "em nome de BELTRANA EXEMPLO"}])
    r = MF.tratar_grupo(con, MA.varrer([entrada])[0], cg_casa["dados"], tmp_path / "arquivos", "mario",
                        conversar=ia, ler_texto=lambda arquivos: TEXTO_DO_AVISO)
    assert r["caminho"] == "FRAUDE" and len(r["incluidos"]) == 1
    assert livre_ao_incluir == [False, False], (
        "um dos caminhos incluiu em fr_alertas sem a trava que o outro usa: os dois "
        "ao mesmo tempo achariam o alerta ausente e o incluiriam duas vezes")


@so_no_postgres
def test_a_linha_de_comando_chega_ao_banco_fora_do_sistema(con, cg_casa, fora_do_sistema, tmp_path):
    MF.carregar(con, [_p()])
    pagina = tmp_path / "revisao.html"
    assert MF.main(["--banco", str(cg_casa["banco"]), "--em-nome-de", "mario",
                    "--pagina", str(pagina)]) == 0
    assert "FULANO DE TAL EXEMPLO" in pagina.read_text(encoding="utf-8")


@so_no_postgres
def test_a_copia_antes_de_gravar_sai_com_apostrofo_no_caminho(con, cg_casa, tmp_path, monkeypatch):
    monkeypatch.setenv("CARTORIO_GESTAO_COPIAS", str(tmp_path / "copias d'agua"))
    pedidas = []

    def pg_dump_de_mentira(db_path, destino):
        pedidas.append(Path(destino))
        Path(destino).parent.mkdir(parents=True, exist_ok=True)
        Path(destino).write_bytes(b"copia")
        return Path(destino)

    monkeypatch.setattr(banco_pg, "copiar_para_arquivo", pg_dump_de_mentira)
    MF.carregar(con, [_p()])
    assert MF.main(["--banco", str(cg_casa["banco"]), "--em-nome-de", "mario", "--aprovar", "todas"]) == 0
    assert len(pedidas) == 1 and "copias d'agua" in str(pedidas[0])
    assert pedidas[0].name.startswith("antes_malote_fraudes_") and pedidas[0].is_file()
    assert con.execute("SELECT situacao FROM mt_alertas_propostos").fetchone()[0] == "APROVADO"


# ================================================== CONSERTO DO L033R (18/10/2026)
# `ler_aviso` FALA COM A REDE, e nunca dentro de transação. O `executescript` do
# esquema confirmava o que estava aberto e não deixava transação; o
# `bd.escrever` que o trocou abre a transação com a trava única da ponte e não
# a confirmava: a trava ficava presa durante toda a leitura da IA, e quem
# gravasse no balcão esperava 15 s e levava «database is locked».

@so_no_postgres
def test_o_balcao_grava_enquanto_a_ia_interna_le_o_aviso(con, cg_casa, tmp_path, monkeypatch):
    import agente_provedores as AP
    import malote_agente as MA
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, provedor=None: True)
    MA.init_schema(con)
    con.commit()                       # como a `rodada`, que confirma antes do laço
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "Suspeita de fraude.pdf").write_bytes(b"%PDF-1.4\n% x\n%%EOF\n")
    ia = _ia_que_responde([{"nome": "BELTRANA EXEMPLO", "documento": "", "papel": "VITIMA",
                            "trecho": "em nome de BELTRANA EXEMPLO"}])
    no_balcao = []

    def ia_enquanto_o_balcao_grava(pasta, **kw):
        balcao = sqlite3.connect(cg_casa["banco"])
        try:
            balcao.execute("PRAGMA busy_timeout = 500")
            balcao.execute("INSERT INTO settings(key, value) VALUES ('balcao_gravou', '1') "
                           "ON CONFLICT(key) DO UPDATE SET value = excluded.value")
            balcao.commit()
            no_balcao.append("gravou")
        except sqlite3.OperationalError as erro:
            no_balcao.append(str(erro))
        finally:
            balcao.close()
        return ia(pasta, **kw)

    r = MF.tratar_grupo(con, MA.varrer([entrada])[0], cg_casa["dados"], tmp_path / "arquivos", "mario",
                        conversar=ia_enquanto_o_balcao_grava, ler_texto=lambda arquivos: TEXTO_DO_AVISO)
    assert no_balcao == ["gravou"], (
        "a leitura da IA interna rodou com a transação aberta e a trava da ponte presa: "
        f"o balcão não gravou ({no_balcao})")
    assert r["caminho"] == "FRAUDE" and len(r["incluidos"]) == 1


# ================================================== LX13 (A4 da auditoria LS03)
# A ordem de 13/10/2026 fica: o que a IA lê no aviso entra ATIVO, sem revisão
# antes. O que muda é a régua do que entra e o rastro para a revisão depois:
#   (a) CPF só entra se os dígitos estão no texto do PDF — senão, só o nome;
#   (b) o alerta diz «entrado pela IA», e o despacho diário do oficial o lista;
#   (c) ENVOLVIDO só com o trecho do texto que o diga — senão, DOCUMENTO.
# Quem escreve o PDF é de fora, sem login; um CPF inventado acusaria um
# inocente com a força de documento, que não tem homônimo.

from datetime import date                                        # noqa: E402

AVISO_COM_NOMES = (
    "Ofício circular. Comunica-se a lavratura de procuração falsa, com selo falsificado. "
    "Figura como outorgante BELTRANA EXEMPLO, CPF 000.000.001-91, cujo nome foi usado sem o "
    "seu conhecimento. Foi instaurado inquérito em face de FULANO DE TAL EXEMPLO, que se "
    "apresentou com documento falso. Consta ainda do instrumento CICRANO EXEMPLO DIAS. ") * 2


def test_o_cpf_que_nao_esta_no_texto_do_pdf_nao_entra(tmp_path):
    # 000.000.050-70 é CPF válido e NÃO está no texto: a IA o inventou
    ia = _ia_que_responde([
        {"nome": "BELTRANA EXEMPLO", "documento": "CPF", "papel": "VITIMA",
         "trecho": "outorgante BELTRANA EXEMPLO"},
        {"nome": "CICRANO EXEMPLO DIAS", "documento": "000.000.050-70", "papel": "DOCUMENTO",
         "trecho": "Consta ainda do instrumento CICRANO EXEMPLO DIAS"}])
    r = MF.ler_aviso(tmp_path, AVISO_COM_NOMES, conversar=ia, provedor="claude")
    docs = {p["nome"]: p["documento"] for p in r["pessoas"]}
    assert docs == {"BELTRANA EXEMPLO": "00000000191", "CICRANO EXEMPLO DIAS": ""}
    assert any("00000005070 não está no texto do PDF" in f for f in r["fora"])


def test_o_cpf_escrito_com_espacos_no_pdf_conta_como_no_texto():
    assert MF.documento_esta_no_texto("00000000191", "CPF 000 000 001 91, solteira")
    assert not MF.documento_esta_no_texto("00000005070", "CPF 000.000.001-91; processo 0000000507")


def test_envolvido_sem_o_trecho_que_o_diga_entra_como_nome_em_documento(tmp_path):
    ia = _ia_que_responde([
        # trecho que está no texto e cita a pessoa: fica ENVOLVIDO
        {"nome": "FULANO DE TAL EXEMPLO", "documento": "", "papel": "ENVOLVIDO",
         "trecho": "inquérito em face de FULANO DE TAL EXEMPLO"},
        # trecho inventado (não está no texto)
        {"nome": "CICRANO EXEMPLO DIAS", "documento": "", "papel": "ENVOLVIDO",
         "trecho": "CICRANO EXEMPLO DIAS falsificou a assinatura"},
        # trecho verdadeiro, mas sobre outra pessoa: a vítima não vira autora
        {"nome": "BELTRANA EXEMPLO", "documento": "", "papel": "ENVOLVIDO",
         "trecho": "inquérito em face de FULANO DE TAL EXEMPLO"}])
    r = MF.ler_aviso(tmp_path, AVISO_COM_NOMES, conversar=ia, provedor="claude")
    papeis = {p["nome"]: p["papel"] for p in r["pessoas"]}
    assert papeis == {"FULANO DE TAL EXEMPLO": "ENVOLVIDO", "CICRANO EXEMPLO DIAS": "DOCUMENTO",
                      "BELTRANA EXEMPLO": "DOCUMENTO"}
    assert sum("ENVOLVIDO sem trecho do texto" in f for f in r["fora"]) == 2


def test_o_trecho_com_reticencias_e_outra_caixa_ainda_e_o_do_texto():
    assert MF.trecho_diz_envolvido(
        "Fulano de Tal Exemplo",
        "Foi instaurado inquérito … em face de fulano de tal exemplo", AVISO_COM_NOMES)
    assert not MF.trecho_diz_envolvido("Fulano de Tal Exemplo", "", AVISO_COM_NOMES)


def test_o_alerta_da_ia_diz_que_entrou_pela_ia_e_vai_ao_despacho_do_oficial(con, cg_casa, tmp_path,
                                                                            monkeypatch):
    import agente_provedores as AP
    import gestor_rotina as GR
    import malote_agente as MA
    from gestor_schema import init_gestor_schema
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, provedor=None: True)
    MA.init_schema(con)
    init_gestor_schema(con)
    con.commit()
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "Suspeita de fraude.pdf").write_bytes(b"%PDF-1.4\n% x\n%%EOF\n")
    ia = _ia_que_responde([{"nome": "FULANO DE TAL EXEMPLO", "documento": "", "papel": "ENVOLVIDO",
                            "trecho": "inquérito em face de FULANO DE TAL EXEMPLO"}])
    r = MF.tratar_grupo(con, MA.varrer([entrada])[0], cg_casa["dados"], tmp_path / "arquivos", "mario",
                        conversar=ia, agora="2026-10-14T09:00:00",
                        ler_texto=lambda arquivos: AVISO_COM_NOMES)
    assert r["caminho"] == "FRAUDE" and len(r["incluidos"]) == 1
    alerta = con.execute("SELECT * FROM fr_alertas").fetchone()
    assert alerta["situacao"] == "ATIVO" and alerta["observacao"].startswith(MF.MARCA_DA_IA)
    # a lista diária: o que a IA pôs, e não o que o oficial aprovou
    MF.carregar(con, [_p(nome="OUTRA PESSOA EXEMPLO", papel="VITIMA")], agora="2026-10-14T10:00:00")
    MF.revisar(con, [con.execute("SELECT id FROM mt_alertas_propostos WHERE nome = 'OUTRA PESSOA EXEMPLO'"
                                 ).fetchone()[0]], aprovar=True, revisor="mario",
               agora="2026-10-14T10:00:00")
    MF.aplicar(con, usuario="mario", agora="2026-10-14T10:00:00")
    assert [a["id"] for a in MF.entradas_pela_ia(con, "2026-10-14")] == [alerta["id"]]
    assert MF.entradas_pela_ia(con, "2026-10-15") == []
    texto = GR.despacho_do_oficial(con, date(2026, 10, 15), {}, None)
    secao = texto.split("7. FRAUDES ENTRADAS PELA IA")[1]
    assert secao.startswith(" (1)") and f"#{alerta['id']} FULANO DE TAL EXEMPLO" in secao
    assert "OUTRA PESSOA EXEMPLO" not in secao
    # o alerta que o oficial inativou não volta a pedir revisão
    con.execute("UPDATE fr_alertas SET situacao = 'INATIVO' WHERE id = ?", (alerta["id"],))
    assert MF.entradas_pela_ia(con, "2026-10-14") == []


def test_a_aprovacao_do_oficial_nao_leva_a_marca_da_ia(con):
    MF.carregar(con, [_p()])
    MF.revisar(con, [con.execute("SELECT id FROM mt_alertas_propostos").fetchone()[0]],
               aprovar=True, revisor="mario")
    MF.aplicar(con, usuario="mario")
    assert MF.MARCA_DA_IA not in con.execute("SELECT observacao FROM fr_alertas").fetchone()[0]
