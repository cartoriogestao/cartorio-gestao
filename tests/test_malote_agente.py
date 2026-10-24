"""O agente do malote (agente 13) — 11/10/2026.

O que se guarda: o que está na pasta de entrada vira expediente com os anexos,
na forma da tela; o que já está no sistema (pelo sha256) não entra duas vezes;
papel produzido pela casa não é «recebido»; sem dizer em nome de quem, ele mede
e não cadastra; e a medição não grava nada.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import malote_agente as MA                                       # noqa: E402


@pytest.fixture()
def casa(cg_casa, tmp_path):
    cg_casa["db"].create_user("elisa", "Elisa Exemplo Lima", "Senha#12345", "USER")
    cg_casa["db"].set_settings({"serventia_cns": "000000",
                                 "malote_cadastra_em_nome_de": "mario"})
    pasta_malote = tmp_path / "MALOTE"
    (pasta_malote / "PARA CADASTRAR").mkdir(parents=True)
    (pasta_malote / "2026" / "CIRCULARES").mkdir(parents=True)
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    yield {"con": con, "pasta_malote": pasta_malote, "dados": cg_casa["dados"], "db": cg_casa["db"]}
    con.close()


def _pdf(caminho: Path, texto: str) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(b"%PDF-1.4\n% " + texto.encode() + b"\n%%EOF\n")
    return caminho


def test_sem_o_usuario_do_oficial_mede_e_nao_cadastra(casa):
    # a configuração diz «mario» (como a produção diz o login do oficial); aqui
    # ele não existe, e o agente não cai
    # para outro usuário: declara em cada grupo e não derruba a rodada
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "DECISAO-COGEx_14102026.pdf", "a")
    r = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True)
    assert r["cadastrados"] == 0
    assert r["grupos"][0]["situacao"] == "SEM_RESPONSAVEL"
    assert "mario" in r["grupos"][0]["nota"] and "não existe" in r["grupos"][0]["nota"]
    assert casa["con"].execute("SELECT count(*) FROM expedientes").fetchone()[0] == 0


def test_por_padrao_cadastra_em_nome_do_oficial(casa):
    casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "PORTARIA-COGEX_1942026.pdf", "p")
    r = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True)
    assert r["cadastrados"] == 1
    e = casa["con"].execute(
        "SELECT e.category, u.username FROM expedientes e JOIN users u ON u.id = e.created_by").fetchone()
    assert tuple(e) == ("Portarias", "mario")


def test_cadastra_com_anexo_na_forma_da_tela_e_nao_repete(casa):
    pdf = _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "CIRC-CSERVCOGEX_2232026.pdf", "circular")
    r = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"],
                  confirmar=True, em_nome_de="elisa")
    assert r["cadastrados"] == 1
    e = casa["con"].execute("SELECT * FROM expedientes").fetchone()
    assert e["source"] == "Malote Digital" and e["stage"] == "RECEBIDO"
    assert e["category"] == "Circulares" and e["internal_protocol"].startswith("EXP-")
    assert e["external_reference"] == pdf.name
    a = casa["con"].execute("SELECT * FROM attachments WHERE entity_type='EXPEDIENTE'").fetchone()
    assert a["entity_id"] == e["id"] and Path(a["stored_path"]).is_file()
    assert "Expedientes" in a["stored_path"] and e["internal_protocol"] in a["stored_path"]
    assert pdf.exists(), "o arquivo da pasta do malote não se move"
    log = casa["con"].execute("SELECT * FROM audit_logs WHERE action='EXPEDIENTE_CREATED'").fetchone()
    assert log["username_snapshot"] == MA.QUEM
    # a segunda rodada reconhece pelo sha256 e não abre outro expediente
    r2 = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"],
                   confirmar=True, em_nome_de="elisa")
    assert r2["cadastrados"] == 0 and r2["grupos"][0]["situacao"] == "JA_NO_SISTEMA"
    assert casa["con"].execute("SELECT count(*) FROM expedientes").fetchone()[0] == 1


def test_subpasta_vira_um_expediente_so(casa):
    pasta = casa["pasta_malote"] / "PARA CADASTRAR" / "MANDADO DE AVERBAÇÃO FULANO"
    _pdf(pasta / "OFICIO.pdf", "1")
    _pdf(pasta / "DOCUMENTOS.pdf", "2")
    MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True, em_nome_de="elisa")
    assert casa["con"].execute("SELECT count(*) FROM expedientes").fetchone()[0] == 1
    assert casa["con"].execute("SELECT count(*) FROM attachments").fetchone()[0] == 2


def test_papel_da_casa_nao_e_recebido(casa):
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "certidao-rcpn-81-2026.pdf", "x")
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "RECFIR000000D0XB4FK298AWP401.pdf", "y")
    r = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True, em_nome_de="elisa")
    assert {g["situacao"] for g in r["grupos"]} == {"DA_CASA"}
    assert r["cadastrados"] == 0


def test_arquivado_na_pasta_sem_expediente_so_vai_ao_relatorio(casa):
    _pdf(casa["pasta_malote"] / "2026" / "CIRCULARES" / "CIRC-DAFIC-132026.pdf", "z")
    r = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True, em_nome_de="elisa")
    assert r["cadastrados"] == 0
    assert [a["arquivo"] for a in r["arquivados_sem_expediente"]] == ["CIRC-DAFIC-132026.pdf"]
    assert "CIRC-DAFIC-132026.pdf" in MA.relatorio_html(r, MA.date.today())


def test_medir_nao_grava_nada(casa):
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "x.pdf", "m")
    MA.init_schema(casa["con"])
    contar = lambda: [casa["con"].execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: E731
                      for t in ("mt_execucoes", "mt_arquivos", "expedientes", "attachments", "audit_logs")]
    antes = contar()
    banco = casa["db"].db_path
    ro = sqlite3.connect(f"file:{Path(banco).as_posix()}?mode=ro", uri=True)
    r = MA.medir(ro, casa["dados"], casa["pasta_malote"])
    ro.close()
    assert r["so_mediu"] and r["grupos"][0]["situacao"] == "A_CADASTRAR"
    assert contar() == antes


def test_usuario_inexistente_recusa_com_frase(casa):
    with pytest.raises(MA.MaloteError, match="não existe"):
        MA.usuario_responsavel(casa["con"], "ninguem")


def test_a_raiz_dos_arquivos_e_a_mesma_regra_do_app(casa):
    import inspect
    import app
    fonte = inspect.getsource(app)
    assert 'db.get_setting("archive_root", "")' in fonte and 'data_dir / "arquivos"' in fonte
    assert MA.archive_root_de(Path("X")) == Path("X") / "arquivos"


def test_a_sonda_do_malote_nao_manda_credencial():
    pedidos = []

    def abrir(url):
        pedidos.append(url)
        return ('<input id="Login" name="Login"/><input name="Senha"/>'
                'Habilitado duplo fator de acesso (2FA). Malote Digital 26.05').encode()
    r = MA.sondar_malote_digital(abrir=abrir)
    assert r == {"responde": True, "versao": "26.05", "pede_login_e_senha": True, "aviso_2fa": True}
    assert pedidos == [MA.URL_MALOTE] and "Senha=" not in pedidos[0]


# A CAPA DO MALOTE, com o texto como o pypdf o devolve (medido em 11/10/2026 no
# PDF «Recomendacao_ANOREG_BR_002_2026_.pdf»): o assunto quebra a 64 caracteres
# no meio da palavra, e o remetente vem em três linhas.
CAPA_REAL = (
    "REPÚBLICA FEDERATIVA DO BRASIL\nPODER JUDICIÁRIO\nMALOTE DIGITAL\n"
    "Tipo de documento: Administrativo\nCódigo de rastreabilidade: 81020265934999\n"
    "Nome original: Recomendacao_ANOREG_BR_002_2026_.pdf\nData: 09/10/2026 12:40:11\n"
    "Remetente: \nGeisa Jinkings de Oliveira Melo\n"
    "Associação dos Notários e Registradores do Maranhão - ANOREG\nTJMA\n"
    "Documento: não assinado.\nPrioridade: Normal.\nMotivo de envio: Para conhecimento.\n"
    "Assunto: ORIENTAÇÕES PRÁTICAS SOBRE A IMPLEMENTAÇÃO DO IBS E DA CBS NA AT\n"
    "IVIDADE NOTARIAL E REGISTRAL\nRecomendação nº 2/2026 ...\n")


def test_a_capa_junta_o_assunto_quebrado_sem_espaco():
    c = MA.ler_capa(CAPA_REAL)
    assert c["assunto"] == ("ORIENTAÇÕES PRÁTICAS SOBRE A IMPLEMENTAÇÃO DO IBS E DA CBS NA "
                            "ATIVIDADE NOTARIAL E REGISTRAL")
    assert c["codigo"] == "81020265934999" and c["enviado_em"] == "2026-10-09 12:40:11"
    assert c["remetente"].startswith("Geisa Jinkings de Oliveira Melo — Associação")
    assert c["motivo"] == "Para conhecimento" and c["prioridade"] == "Normal"


def test_a_quebra_com_espaco_no_fim_da_linha_nao_cola_as_palavras():
    texto = ("Código de rastreabilidade: 1\nAssunto: " + "x" * 53 + " constantes \n"
             "no Proc. 0800228\nCorpo\n")
    assert MA.ler_capa(texto)["assunto"].endswith("constantes no Proc. 0800228")


def test_sem_capa_e_none():
    assert MA.ler_capa("Ofício nº 12/2026 sem capa") is None


def test_capa_preenche_o_expediente_e_copia_repetida_nao_entra(casa, monkeypatch):
    casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "Recomendacao.pdf", "a")
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "Recomendacao (1).pdf", "b")
    monkeypatch.setattr(MA, "capa_do_pdf", lambda p: MA.ler_capa(CAPA_REAL))
    r = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True)
    assert r["cadastrados"] == 1
    assert sorted(g["situacao"] for g in r["grupos"]) == ["CADASTRADO", "REPETIDO"]
    e = casa["con"].execute("SELECT * FROM expedientes").fetchone()
    assert e["external_reference"] == "81020265934999"
    assert e["sender"].startswith("Geisa Jinkings")
    assert e["subject"].endswith("NA ATIVIDADE NOTARIAL E REGISTRAL")
    assert "enviado em 2026-10-09 12:40:11" in e["notes"]
    # e numa rodada seguinte o código basta para reconhecer
    r2 = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True)
    assert r2["cadastrados"] == 0


def test_o_comando_tira_copia_antes_de_gravar_e_gera_o_relatorio(casa, tmp_path, monkeypatch):
    # a cópia vai para a pasta das cópias, LONGE do banco (ordem de 11/10/2026)
    monkeypatch.setenv("CARTORIO_GESTAO_COPIAS", str(tmp_path / "copias"))
    casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "OFC-COGEX_1.pdf", "c")
    dados = tmp_path / "dados"
    saida = tmp_path / "rel.html"
    assert MA.main(["--banco", str(casa["db"].db_path), "--pasta-dados", str(dados),
                    "--pasta", str(casa["pasta_malote"]), "--confirmar", "--em-nome-de", "mario",
                    "--saida", str(saida)]) == 0
    copias = list((tmp_path / "copias" / "antes_de_mexer").glob("antes_malote_agente_*.sqlite3"))
    assert len(copias) == 1 and copias[0].stat().st_size > 0
    assert not list(Path(casa["db"].db_path).parent.glob("antes_malote_agente_*"))
    assert not (dados / "backups").exists()
    assert "OFC-COGEX_1.pdf" in saida.read_text(encoding="utf-8")
    assert casa["con"].execute("SELECT count(*) FROM expedientes").fetchone()[0] == 1


def test_o_comando_chega_ao_banco_fora_do_sistema(casa, tmp_path, monkeypatch, capsys):
    # revisão do L033 (17/10/2026): o comando abria o banco com `sqlite3.connect`.
    # Fora do sistema (os .cmd de tools/) ninguém instala o desvio para o
    # PostgreSQL, e o acesso nativo recusa o sqlite3 cru (`BancoNaoEPostgres`).
    import banco_pg
    if not banco_pg.ativo():
        pytest.skip("mede a porta do PostgreSQL (CG_PG_DSN)")
    monkeypatch.setattr(sqlite3, "connect", banco_pg._CONNECT_ORIGINAL)
    casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "OFC-COGEX_2.pdf", "d")
    comum = ["--banco", str(casa["db"].db_path), "--pasta-dados", str(tmp_path / "dados"),
             "--pasta", str(casa["pasta_malote"])]
    assert MA.main(comum + ["--confirmar", "--sem-copia", "--em-nome-de", "mario"]) == 0
    assert casa["con"].execute("SELECT count(*) FROM expedientes").fetchone()[0] == 1
    capsys.readouterr()
    # e a medição (`mode=ro`) lê o mesmo banco: o que acabou de entrar já está lá
    assert MA.main(comum) == 0
    assert '"situacao": "JA_NO_SISTEMA"' in capsys.readouterr().out


def test_a_pasta_do_malote_vem_da_configuracao_e_nao_do_codigo(casa):
    # relato #111: o caminho até a pasta do malote é desta casa e não se escreve
    casa["db"].set_settings({"malote_pasta": str(casa["pasta_malote"])})
    assert MA.pasta_do_malote(casa["con"]) == casa["pasta_malote"]
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "CIRC-X.pdf", "k")
    r = MA.rodada(casa["con"], casa["dados"], confirmar=False)
    assert [g["nome"] for g in r["grupos"]] == ["CIRC-X.pdf"]


# ================================================== AVISO DE FRAUDE (13/10/2026)
# «nem tarefa, nem expediente» e «pode ser a ia interna»: o aviso vai à lista de
# fraudes; o que não é aviso vira expediente; se a IA não ler, fica na pasta.

import json                                                       # noqa: E402


def _ia(pessoas, aviso=True, chamadas=None, falha=None):
    def conversar(pasta, **kw):
        if chamadas is not None:
            chamadas.append(kw["conversa"][0]["texto"])
        if falha:
            raise falha
        return {"texto": json.dumps({"aviso_de_fraude": aviso, "resumo": "Escritura falsa.",
                                     "processos": ["0001/2026"], "pessoas": pessoas}),
                "modelo": "claude-sonnet-5", "entrada": 10, "saida": 5, "provedor": "claude"}
    return conversar


TEXTO_DO_AVISO = ("Ofício circular. Comunica-se a lavratura de escritura falsa atribuída a outra serventia, "
                  "com assinatura e selo falsificados, para que as serventias fiquem atentas. ") * 3


@pytest.fixture()
def com_chave(monkeypatch):
    # o PDF de teste não tem texto legível; o do malote tem (o ofício digitado)
    import agente_provedores as AP
    import malote_fraudes as MF
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, provedor=None: True)
    monkeypatch.setattr(MF, "texto_dos_arquivos", lambda arquivos: "--- arquivo: x.pdf" + chr(10) + TEXTO_DO_AVISO)


def test_aviso_que_e_so_imagem_fica_na_pasta_sem_chamar_a_ia(casa, monkeypatch):
    # ensaio de 13/10/2026: o ofício escaneado deu 61 caracteres e a IA inventou
    # «FRAUDE» e «PÚBLICA» como pessoas. Sem texto, a IA nem é chamada.
    import agente_provedores as AP
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, provedor=None: True)
    chamadas = []
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "Denuncia de fraude.pdf", "w")
    r = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True,
                  em_nome_de="elisa", conversar=_ia([], chamadas=chamadas))
    g = r["grupos"][0]
    assert g["situacao"] == "FRAUDE_PENDENTE" and "imagem" in g["nota"] and chamadas == []
    assert casa["con"].execute("SELECT count(*) FROM expedientes").fetchone()[0] == 0


def test_aviso_de_fraude_vai_a_lista_sem_expediente_e_nao_volta(casa, com_chave, monkeypatch):
    # O TEXTO DO OFÍCIO TEM DE TRAZER O TRECHO — LX22B2, 20/10/2026. Desde o
    # LX13 (regra (c) das fraudes) ENVOLVIDO só fica ENVOLVIDO se o trecho que a
    # IA cita está no PDF e nomeia a pessoa pelo prenome; o texto genérico de
    # `com_chave` não cita ninguém, e FULANO caía para DOCUMENTO e passava a ser
    # o primeiro «fora». Aqui o ofício diz de quem é a escritura, como o do
    # malote diz, e o que fica de fora volta a ser só o banco.
    import malote_fraudes as MF
    monkeypatch.setattr(MF, "texto_dos_arquivos", lambda arquivos: (
        "--- arquivo: x.pdf" + chr(10) + TEXTO_DO_AVISO
        + "Escritura lavrada em face de FULANO DE TAL EXEMPLO, sem comparecimento. "))
    chamadas = []
    pdf = _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "Suspeita de fraude.pdf", "x")
    ia = _ia([{"nome": "FULANO DE TAL EXEMPLO", "papel": "ENVOLVIDO", "trecho": "em face de FULANO"},
              {"nome": "Banco Exemplo S/A", "papel": "VITIMA"}], chamadas=chamadas)
    r = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True,
                  em_nome_de="elisa", conversar=ia)
    assert r["cadastrados"] == 0 and r["grupos"][0]["situacao"] == "NA_LISTA_DE_FRAUDES"
    c = casa["con"]
    assert c.execute("SELECT count(*) FROM expedientes").fetchone()[0] == 0
    assert c.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
    alertas = c.execute("SELECT * FROM fr_alertas").fetchall()
    assert [a["nome"] for a in alertas] == ["FULANO DE TAL EXEMPLO"], "banco não entra"
    assert alertas[0]["papel"] == "ENVOLVIDO", "o trecho está no texto e cita o prenome"
    assert alertas[0]["origem"].startswith("Malote Digital") and "0001/2026" in alertas[0]["origem"]
    assert "Escritura falsa." in alertas[0]["observacao"]
    p = c.execute("SELECT * FROM mt_alertas_propostos").fetchone()
    assert p["situacao"] == "APLICADO" and "IA interna" in p["revisado_por"]
    guardado = Path(p["arquivo"])
    assert guardado.is_file() and "fraudes" in guardado.parts and pdf.exists()
    assert c.execute("SELECT situacao FROM mt_arquivos").fetchone()[0] == "FRAUDE"
    leitura = c.execute("SELECT * FROM mt_fraude_leituras").fetchone()
    assert leitura["modelo"] == "claude-sonnet-5" and leitura["tokens_entrada"] == 10
    assert len(r["fraudes"][0]["fora"]) == 1 and "Banco Exemplo" in r["fraudes"][0]["fora"][0]
    assert "FULANO DE TAL EXEMPLO" in MA.relatorio_html(r, MA.date(2026, 10, 13))
    # a segunda rodada reconhece pelo sha256: nem IA, nem alerta repetido
    r2 = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True,
                   em_nome_de="elisa", conversar=ia)
    assert r2["grupos"][0]["situacao"] == "NA_LISTA_DE_FRAUDES" and len(chamadas) == 1
    assert c.execute("SELECT count(*) FROM fr_alertas").fetchone()[0] == 1


def test_o_que_a_ia_diz_nao_ser_aviso_vira_expediente(casa, com_chave):
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "Orientacao sobre fraudes.pdf", "y")
    r = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True,
                  em_nome_de="elisa", conversar=_ia([], aviso=False))
    assert r["cadastrados"] == 1 and "não é aviso" in r["grupos"][0]["nota"]
    assert casa["con"].execute("SELECT count(*) FROM fr_alertas").fetchone()[0] == 0


def test_se_a_ia_nao_le_o_aviso_fica_na_pasta(casa, com_chave):
    pdf = _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "Golpe com selo.pdf", "z")
    r = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True,
                  em_nome_de="elisa", conversar=_ia([], falha=OSError("rede caiu")))
    g = r["grupos"][0]
    assert g["situacao"] == "FRAUDE_PENDENTE" and "rede caiu" in g["nota"]
    assert casa["con"].execute("SELECT count(*) FROM expedientes").fetchone()[0] == 0
    assert casa["con"].execute("SELECT count(*) FROM fr_alertas").fetchone()[0] == 0
    assert pdf.exists()
    assert casa["con"].execute("SELECT erro FROM mt_fraude_leituras").fetchone()[0].startswith("OSError")


def test_sem_chave_o_aviso_fica_na_pasta(casa, monkeypatch):
    import malote_fraudes as MF
    monkeypatch.setattr(MF, "texto_dos_arquivos", lambda arquivos: TEXTO_DO_AVISO)
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "Golpe com selo.pdf", "z")
    r = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True,
                  em_nome_de="elisa", conversar=_ia([], chamadas=None))
    assert r["grupos"][0]["situacao"] == "FRAUDE_PENDENTE" and "sem chave" in r["grupos"][0]["nota"]


def test_sem_palavra_de_fraude_a_ia_nem_e_chamada(casa, com_chave, monkeypatch):
    import malote_fraudes as MF
    monkeypatch.setattr(MF, "texto_dos_arquivos", lambda arquivos: "Circular sobre o recesso forense. " * 20)
    chamadas = []
    _pdf(casa["pasta_malote"] / "PARA CADASTRAR" / "CIRC-CSERVCOGEX_2232026.pdf", "c")
    r = MA.rodada(casa["con"], casa["dados"], pasta_malote=casa["pasta_malote"], confirmar=True,
                  em_nome_de="elisa", conversar=_ia([], chamadas=chamadas))
    assert r["cadastrados"] == 1 and chamadas == []


def test_sem_configuracao_a_pasta_do_malote_nao_e_procurada(casa):
    """23/10/2026: onde a serventia guarda o malote é configuração dela. Sem
    `settings.malote_pasta`, não há pasta — o código não procura em lugar nenhum."""
    casa["db"].set_settings({"malote_pasta": ""})
    assert MA.pasta_do_malote(casa["con"]) is None
