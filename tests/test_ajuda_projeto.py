"""O que a ajuda sabe do projeto — o relato #26 do oficial.

AS FRASES DELE:

    «melhorar as capacidades da resolução de problemas. Precisa poder permitir,
     caso preciso, acesso a mais informações, inclusive acesso ao projeto do
     sistema para saber o que já foi feito, o que falta.»
    «Ajuda precisa ganhar mais ferramentas e autonomia.»

O QUE ESTES TESTES GUARDAM
    Dois defeitos, e os dois já aconteceram nesta construção:

    **O `except` largo que vira medição.** `pendencias_declaradas` chamava uma
    função com o nome errado, e um `except Exception: return []` transformava o
    `AttributeError` em «zero pendências» — com cara de medição. São **nove**.
    Zero medido e zero por engano são a mesma tela e coisas diferentes.

    **A biblioteca inteira em toda pergunta.** São 80 documentos e mais de um
    milhão de caracteres. Mandá-los sempre custaria em toda pergunta, e a API
    cobra por uso.
"""
from __future__ import annotations

import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.lento  # inventaria a arvore inteira; fica na suite completa


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — DROP TABLE
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ajuda_projeto as PROJ                                     # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(tmp_path):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(banco)
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "cliente": c, "banco": banco, "db": db}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------ os documentos são medidos


def test_os_documentos_saem_da_pasta_e_nao_de_uma_lista():
    """Nada aqui se escreve à mão — é a regra de `ajuda_mapa`, e pelo mesmo
    motivo escrito lá: quem lê a lista velha não é um operador que estranha, é
    uma máquina que responde com convicção."""
    docs = PROJ.documentos()
    assert docs, "a pasta DOCUMENTACAO não foi achada"
    nomes = {d["arquivo"] for d in docs}
    na_pasta = {p.name for p in (RAIZ / "DOCUMENTACAO").glob("*.md")}
    assert nomes == na_pasta


def test_a_documentacao_viaja_com_o_sistema():
    """A pasta tem de estar DENTRO da pasta empacotada, senão o servidor não a
    recebe — e a ajuda roda no servidor.

    Foi o que se mediu ao construir isto: havia duas pastas, 67 documentos na
    raiz do projeto e 13 dentro, e só a de dentro viaja no `.cgu`. O servidor
    nunca teve um único documento."""
    assert (RAIZ / "DOCUMENTACAO").is_dir()
    assert len(list((RAIZ / "DOCUMENTACAO").glob("*.md"))) >= 70


def test_cada_documento_traz_titulo():
    """Um nome de arquivo sozinho («ROTEIRO_3.6.29.md») não diz nada a quem
    escolhe o que ler.

    **O NOME DESTE TESTE FALAVA DE UM GANCHO QUE NÃO EXISTE MAIS** (15/09/2026):
    o índice levava a primeira frase de cada documento, e ela custava 11.099
    caracteres em toda pergunta. Nome de teste que descreve o que não se mede
    mais é o carimbo que mente — e num teste ele é pior, porque quem o ler
    conclui que a peça está lá.
    """
    sem_titulo = [d["arquivo"] for d in PROJ.documentos() if not d["titulo"]]
    assert not sem_titulo, f"documentos sem título: {sem_titulo}"


def test_o_indice_nao_leva_a_primeira_frase_dos_documentos():
    """**A ECONOMIA QUE ESTE TESTE GUARDA É DE TODA PERGUNTA.**

    15/09/2026: o índice ia com o nome, o título e a primeira frase de cada
    documento. Medido na árvore, o índice inteiro dava **23.949 caracteres** —
    e a frase de abertura, **11.099**, isto é 70 % de tudo o que a ajuda
    mandava junto de cada pergunta, para dar o COMEÇO de 162 documentos.

    O que a frase fazia — achar o documento pelo assunto — quem faz agora é
    `procurar_nos_documentos`: lê o documento inteiro, conta o que achou e diz
    de onde saiu, e só custa quando é chamada.

    A MEDIÇÃO AQUI É DE PROPRIEDADE, E NÃO DE NÚMERO: pega-se a linha mais
    longa do MEIO de um documento — prosa, e não título — e exige-se que ela
    não esteja no índice. Número escrito à mão envelheceria com o próximo
    documento; a propriedade não.

    O teto existe, e é folgado de propósito: hoje são **12.850** caracteres
    para 162 documentos. Ele não mede tamanho — ele pega o RETORNO da primeira
    frase, que levaria o índice de volta aos 23.949 sem ninguém notar.
    """
    indice = "\n".join(PROJ.indice())
    assert len(indice) <= 16_000, (
        "o índice dos documentos cresceu de mais — confira se a primeira frase "
        f"voltou a ele ({len(indice)} caracteres)")
    d = PROJ.documentos()[0]
    texto = (RAIZ / "DOCUMENTACAO" / d["arquivo"]).read_text(encoding="utf-8")
    prosa = [ln.strip() for ln in texto.splitlines()
             if len(ln.strip()) > 80 and not ln.lstrip().startswith("#")]
    assert prosa, f"{d['arquivo']} não tem prosa para conferir"
    assert max(prosa, key=len) not in indice
    # e cada documento tem a sua linha, com o nome e o título
    assert len(PROJ.indice()) == len(PROJ.documentos())
    for linha in PROJ.indice():
        assert linha.startswith("- `")


# ------------------------------------- a busca: a frase que saiu do índice


def test_a_busca_acha_o_trecho_e_diz_de_que_documento_e():
    """O que a primeira frase do índice fazia mal, e isto faz bem: achar o
    assunto DENTRO de um documento de cem mil caracteres, e dizer onde."""
    achado = PROJ.procurar_nos_documentos("impressora")
    assert "ROTEIRO_3.6.65.md" in achado
    assert "linha(s) com «impressora»" in achado
    assert "[ROTEIRO_3.6.65.md:" in achado       # arquivo E linha, que é o endereço


def test_a_busca_acha_sem_acento_o_que_esta_escrito_com_acento():
    """**É A DIFERENÇA ENTRE ACHAR E NÃO ACHAR.** Quem procura escreve
    «matricula», sem acento, com a maior naturalidade; o documento diz
    «matrícula». Sem a normalização a busca devolveria «ninguém escreveu sobre
    isso» — com a mesma cara de quem mediu."""
    assert "matrícula" in PROJ.procurar_nos_documentos("matricula")
    assert "matrícula" in PROJ.procurar_nos_documentos("MATRÍCULA")


def test_a_busca_diz_quando_nao_acha_nada():
    """Silêncio, aqui, viraria «a casa nunca escreveu sobre isso» — e a resposta
    certa é «ninguém escreveu», que não é a mesma coisa que «não existe»."""
    achado = PROJ.procurar_nos_documentos("xilofone_quantico_inexistente")
    assert "Nenhuma linha" in achado
    assert "não que a coisa não exista" in achado


def test_a_busca_avisa_quando_mostra_menos_do_que_achou():
    """Busca que devolve quarenta achados sem dizer que há duzentos faz quem lê
    concluir que o assunto se resolve ali — e o modelo é quem lê."""
    achado = PROJ.procurar_nos_documentos("selo", limite=3)
    assert "Mostrando 3 das" in achado
    assert achado.count("[") >= 3
    assert "Os documentos com mais linhas" in achado


def test_a_busca_recusa_termo_vazio_e_limite_zero_nao_mente():
    with pytest.raises(ValueError):
        PROJ.procurar_nos_documentos("   ")
    # limite zero achava tudo e não devolvia nada: o piso é UM
    achado = PROJ.procurar_nos_documentos("selo", limite=0)
    assert "Nenhuma linha" not in achado
    assert "Mostrando 1 das" in achado


def test_o_nome_do_documento_nao_vira_caminho():
    """Esta função alimenta uma consulta que SAI da casa. Sem descartar o
    caminho, um nome vindo da tela leria arquivo de fora da pasta."""
    assert PROJ.documento("../CLAUDE.md") is None
    assert PROJ.documento("../../CLAUDE.md") is None
    assert PROJ.documento("/etc/passwd") is None
    assert PROJ.documento("app.py") is None          # não é `.md`
    assert PROJ.documento("nao_existe_mesmo.md") is None


def test_um_documento_pedido_pelo_nome_vem_inteiro():
    doc = PROJ.documento("MODELOS_DA_CASA.md")
    assert doc is not None
    assert doc["arquivo"] == "MODELOS_DA_CASA.md"
    assert len(doc["texto"]) > 500


def test_documento_grande_e_cortado_avisando():
    """Cortar avisando é melhor que mandar tudo e a consulta falhar inteira — e
    o corte aparece no texto, para quem lê saber que há mais."""
    grande = max(PROJ.documentos(), key=lambda d: d["tamanho"])
    doc = PROJ.documento(grande["arquivo"])
    if grande["tamanho"] > PROJ.LIMITE_DO_DOCUMENTO:
        assert doc["cortado"]
        assert "o documento continua" in doc["texto"]
    assert len(doc["texto"]) <= PROJ.LIMITE_DO_DOCUMENTO + 400


# ------------------------------------------------ o defeito que já aconteceu


def test_as_pendencias_do_oficial_nao_voltam_caladas_como_zero(casa):
    """O DEFEITO QUE ESTE MÓDULO JÁ TEVE. Eu chamava `implantacao.pendentes`,
    que não existe — a função é `abertas` —, e um `except Exception: return []`
    devolvia «zero pendências» com cara de medição.

    Este teste declara uma pendência e exige que ela apareça. Com o `except`
    largo de volta, ele fica vermelho."""
    import implantacao
    con = _con(casa)
    with con:
        implantacao.declarar(
            con, "numeracao:PT_PROTESTO", tipo="NUMERO",
            titulo="O próximo número do Livro de Registro de Protestos",
            motivo="O acervo guarda livro e folha, e nenhuma coluna com o "
                   "número do protesto.",
            consequencia="O primeiro ato novo nasce com o número 1.",
            agora="2026-08-29T09:00")
    achadas = PROJ.pendencias_declaradas(con)
    assert achadas, "a pendência declarada não apareceu"
    assert any("Protestos" in (x.get("titulo") or "") for x in achadas)


def test_erro_ao_medir_pendencia_nao_se_disfarca_de_zero(casa):
    """A função devolve o erro em vez de uma lista vazia. Quem chama decide o
    que fazer — e o que a tela faz é MOSTRAR que não deu para medir."""
    con = _con(casa)
    con.execute("DROP TABLE IF EXISTS nu_implantacao")
    with pytest.raises(Exception):
        PROJ.pendencias_declaradas(con)


def test_o_contexto_diz_que_nao_deu_para_medir_em_vez_de_calar(casa):
    """Silêncio aqui seria lido como «não há pendência nenhuma» — que é
    exatamente o engano que este módulo já teve."""
    con = _con(casa)
    con.execute("DROP TABLE IF EXISTS nu_implantacao")
    texto = PROJ.para_a_consulta(con, versao="3.6.32")
    assert "não deu para medir" in texto


# ------------------------------------------------ a fatia, e não a biblioteca


def test_o_contexto_leva_o_indice_e_nao_os_textos(casa):
    """São 80 documentos e mais de um milhão de caracteres. Mandá-los em toda
    pergunta custaria em toda pergunta — e a API cobra por uso."""
    con = _con(casa)
    texto = PROJ.para_a_consulta(con, versao="3.6.32")
    biblioteca = sum(d["tamanho"] for d in PROJ.documentos())
    assert len(texto) < 60_000
    assert len(texto) < biblioteca / 10
    # mas o índice inteiro vai, para quem responde saber o que existe
    for d in PROJ.documentos():
        assert d["arquivo"] in texto


def test_o_documento_pedido_entra_no_contexto(casa):
    con = _con(casa)
    texto = PROJ.para_a_consulta(con, versao="3.6.32",
                                 documento_pedido="MODELOS_DA_CASA.md")
    assert "MODELOS_DA_CASA.md — texto" in texto
    assert "o código é o piso" in texto.lower()


def test_documento_inexistente_diz_que_nao_achou(casa):
    """Omitindo, quem responde acharia que o documento não tem nada sobre o
    assunto — e responderia com convicção sobre uma leitura que não houve."""
    con = _con(casa)
    texto = PROJ.para_a_consulta(con, versao="3.6.32",
                                 documento_pedido="INVENTADO.md")
    assert "não existe nesta instalação" in texto


# ------------------------------------------- as regras da casa vão no contexto


def test_o_contexto_leva_o_indice_das_regras_da_casa(casa):
    """**A AJUDA RESPONDE PELO QUE ESTA CASA DECIDIU, E NÃO PELA REGRA GERAL.**

    O modelo que responde sabe Notariado e Registro em geral; o que ele não sabe
    é o que ESTA serventia decidiu, com que medição e por quê. Sem esta fatia, a
    resposta sai genérica e bonita — que é a pior forma de resposta errada.

    E vai o ÍNDICE, e não a prosa: são 385 mil caracteres no arquivo das regras.
    """
    import ajuda_regras as REGRAS
    con = _con(casa)
    texto = PROJ.para_a_consulta(con, versao="3.6.32")
    assert "As regras desta casa" in texto
    secao = REGRAS.indice()[3]
    assert secao["titulo"] in texto, "o índice das regras não chegou ao contexto"
    # o texto das seções não vai: quem quiser pede pelo número
    corpo = REGRAS.ler(str(secao["n"]))
    longa = [linha for linha in corpo.splitlines() if len(linha.strip()) > 120]
    assert longa and longa[0].strip() not in texto


def test_o_contexto_avisa_quando_o_material_escrito_ficou_para_tras(casa):
    """Rodando uma versão à frente do arquivo das regras, o aviso aparece — e
    ele aparece NO CONTEXTO, porque quem lê a resposta precisa saber que a
    própria ajuda está apoiada em material velho."""
    con = _con(casa)
    texto = PROJ.para_a_consulta(con, versao="99.0.0")
    assert "material escrito pode estar atrás" in texto
    assert "99.0.0" in texto


def test_o_contexto_avisa_quando_a_biblioteca_de_documentos_nao_chegou(monkeypatch):
    """Medido em 15/09/2026: o servidor tinha TRÊS documentos contra 169 da
    árvore de desenvolvimento, porque o `ATUALIZAR_SISTEMA.cmd` não copiava
    `.md` nenhum. A ajuda respondia sobre uma biblioteca vazia e **nada dizia
    que ela não tinha chegado** — ausência com cara de medição."""
    assert PROJ.conferir_biblioteca() == ""
    monkeypatch.setattr(PROJ, "documentos", lambda: [{"arquivo": "um.md"}])
    aviso = PROJ.conferir_biblioteca()
    assert "1 documento" in aviso
    assert "ficou para trás" in aviso


# ------------------------------------------------ o que «ABERTO» quer dizer


def test_o_contexto_explica_o_que_aberto_quer_dizer(casa):
    """Sem esta frase a máquina responde «você tem 28 problemas em aberto» a
    quem teve vinte e quatro consertados — o relato #23 outra vez, duas vistas
    do mesmo fato sem o mesmo texto."""
    con = _con(casa)
    texto = PROJ.para_a_consulta(con, versao="3.6.32")
    assert "ninguém marcou como resolvido" in texto
    assert "quem fecha é o oficial" in texto.lower()


def test_os_relatos_vao_com_o_numero(casa):
    """Relato #23: «claude relacionou o problema 8, 9 e 20 como finalizados,
    mas não sei quais são esses». O número é o mesmo da tela."""
    import ajuda_problemas as AP
    con = _con(casa)
    with con:
        AP.anotar(con, titulo="um defeito de ensaio", onde="ajuda_problemas",
                  caminho="/ajuda/problemas", detalhe="detalhe",
                  versao="3.6.32", agora="2026-08-29T09:00",
                  usuario="jean", origem="RELATADO")
    texto = PROJ.para_a_consulta(con, versao="3.6.32")
    assert "#1" in texto
    assert "um defeito de ensaio" in texto


# ------------------------------------------------ a tela


def test_a_tela_abre_e_lista_os_documentos(casa):
    r = casa["cliente"].get("/ajuda/projeto")
    assert r.status_code == 200
    html = " ".join(r.get_data(as_text=True).split())
    assert "MODELOS_DA_CASA.md" in html
    assert "O que a ajuda sabe do projeto" in html


def test_a_tela_mostra_o_texto_que_sairia(casa):
    """A mesma regra da pré-visualização da consulta: quem manda dado para fora
    tem direito de ver o que está mandando — e de graça."""
    html = casa["cliente"].get("/ajuda/projeto").get_data(as_text=True)
    assert "O texto que sairia" in html
    assert "Os documentos do projeto" in html


def test_a_tela_le_um_documento_pedido(casa):
    r = casa["cliente"].get("/ajuda/projeto",
                            query_string={"documento": "MODELOS_DA_CASA.md"})
    html = r.get_data(as_text=True)
    assert "O código é o piso" in html


def test_a_tela_recusa_sair_da_pasta(casa):
    """Pedir `../CLAUDE.md` não pode servir o arquivo das regras.

    **A ASSERÇÃO QUE HAVIA AQUI MEDIA A PALAVRA, E NÃO O VAZAMENTO** — e ela
    ficou vermelha em 15/09/2026 quando a tela passou a mostrar o *índice* das
    regras, que inclui o título «As regras desta casa». A frase aparecia por
    causa do índice, e não do arquivo: quem mede palavra encontra prosa.

    O que não pode acontecer é o **conteúdo** do arquivo sair por este caminho —
    e é isso que se mede agora, numa linha do corpo dele.
    """
    import ajuda_regras as REGRAS
    r = casa["cliente"].get("/ajuda/projeto",
                            query_string={"documento": "../CLAUDE.md"},
                            follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "não existe nesta instalação" in html
    # o índice das regras aparece de propósito (é o que a ajuda leva no contexto);
    # o TEXTO delas, não. A linha usada como marca é a mais longa do arquivo —
    # escolhida em tempo de teste, e não escrita aqui: escrita à mão, ela
    # envelheceria na tarde em que as regras fossem editadas.
    maior = max(REGRAS._secoes(), key=lambda s: max((len(x) for x in s["linhas"]),
                                                    default=0))
    linha = max((x.strip() for x in maior["linhas"]), key=len)
    assert len(linha) > 120, linha
    assert linha not in html


def test_a_tela_nao_gasta_consulta(casa):
    """Ver o que a ajuda sabe não pode custar uma pergunta à API."""
    con = _con(casa)
    antes = con.execute("SELECT COUNT(*) FROM aj_consultas").fetchone()[0]
    casa["cliente"].get("/ajuda/projeto")
    depois = con.execute("SELECT COUNT(*) FROM aj_consultas").fetchone()[0]
    assert antes == depois == 0


# ------------------------------------------------ a ajuda continua não decidindo


def test_o_modulo_nao_decide_nada():
    """A IA AUXILIA; NÃO DECIDE — e isso está no código, como no usucapião, nas
    fraudes e na habilitação."""
    publicos = [n for n in dir(PROJ) if not n.startswith("_")]
    proibidos = ("lavrar", "numerar", "selar", "cobrar", "cancelar", "decidir",
                 "fechar", "resolver", "julgar")
    for nome in publicos:
        for p in proibidos:
            assert p not in nome.lower(), f"`{nome}` decide, e não devia"


def test_o_modulo_nao_escreve_no_banco():
    """Ele só lê: o estado do projeto é medido, nunca produzido."""
    codigo = (RAIZ / "ajuda_projeto.py").read_text(encoding="utf-8")
    for comando in ("INSERT ", "UPDATE ", "DELETE "):
        assert comando not in codigo.upper(), f"o módulo faz {comando.strip()}"


# ------------------------- o que mudou: a forma, medida, e o FUNDO, escrito


def _fotografar(con, versao, em, telas=("caixa",)):
    """Grava uma fotografia como `ajuda.fotografar` a grava."""
    con.execute("INSERT INTO aj_mapas(versao, medida_em, fotografia) "
                "VALUES (?, ?, ?)",
                (versao, em, json.dumps({"versao": versao, "telas": list(telas),
                                         "nomes": {t: t for t in telas},
                                         "menu": list(telas),
                                         "arquivos": [], "tabelas": []})))
    con.commit()


def _anotar(con, *, titulo, nota, estado, em, situacao="ABERTO"):
    """Abre um relato com a nota do desenvolvimento — o que a tela grava."""
    con.execute(
        "INSERT INTO aj_problemas(impressao, origem, titulo, primeira_em, "
        "ultima_em, situacao, nota_dev, nota_dev_estado, nota_dev_em) "
        "VALUES (?, 'RELATADO', ?, ?, ?, ?, ?, ?, ?)",
        (f"imp-{titulo}-{em}", titulo, em, em, situacao, nota, estado, em))
    con.commit()


def test_o_que_mudou_leva_o_que_o_desenvolvimento_escreveu(casa):
    """A diferença das fotografias diz o que mudou de FORMA — tela, arquivo,
    tabela —, e não diz POR QUÊ. Quem escreve o porquê é a nota do
    desenvolvimento, e ela já estava no banco sem ninguém a ler no «o que
    mudou»."""
    con = _con(casa)
    _fotografar(con, "3.6.129", "2026-09-15T10:11:53")
    _fotografar(con, "3.6.130", "2026-09-15T10:42:14",
                telas=("caixa", "ri_minuta_guardar"))
    _anotar(con, titulo="O AV-06 lavrava e não encerrava",
            nota="O ato que encerra a ficha deixava a ficha aberta, e fechá-la "
                 "depois lavraria uma segunda averbação de encerramento.",
            estado="ATENDIDO", em="2026-09-15T13:11:46")

    texto = "\n".join(PROJ.mudancas_medidas(con))
    assert "ri_minuta_guardar" in texto, texto          # a forma
    assert "#1" in texto and "ATENDIDO" in texto, texto  # o fundo, com o número
    assert "deixava a ficha aberta" in texto, texto

    # E OS DOIS ESTADOS SAO COISAS DIFERENTES E VAO DIZER-SE OS DOIS. `situacao`
    # e o que o OFICIAL marcou na tela; `nota_dev_estado` e o que o
    # desenvolvimento diz que fez. Ler so um e como a ajuda responde «28
    # problemas em aberto» a quem teve vinte e quatro consertados — relato #23.
    assert "relato ABERTO" in texto and "desenvolvimento ATENDIDO" in texto, texto


def test_a_nota_escrita_DEPOIS_da_fotografia_ainda_aparece(casa):
    """A janela começa na versão anterior e **não termina** na fotografia de
    hoje.

    Medido em 15/09/2026 na produção: a 3.6.130 foi fotografada às **10:42**, e
    as notas daquele dia foram escritas às **13:11** e às **14:18**. Fechar a
    janela na fotografia mostraria zero justamente no dia em que mais se
    escreveu — o trabalho de uma versão termina depois de ela subir."""
    con = _con(casa)
    _fotografar(con, "3.6.129", "2026-09-15T10:11:53")
    _fotografar(con, "3.6.130", "2026-09-15T10:42:14")
    _anotar(con, titulo="depois da fotografia",
            nota="Escrita às treze e onze, depois de a fotografia ser tirada.",
            estado="ATENDIDO", em="2026-09-15T13:11:46")
    texto = "\n".join(PROJ.mudancas_medidas(con))
    assert "Escrita às treze e onze" in texto, texto


def test_a_nota_anterior_ao_piso_fica_de_fora(casa):
    """A janela anda sozinha: quando a próxima fotografia entra, a de hoje vira
    o piso e as notas velhas saem — nada se apaga à mão."""
    con = _con(casa)
    _anotar(con, titulo="nota velha", nota="Escrita antes de tudo isto.",
            estado="ATENDIDO", em="2026-09-01T09:00:00")
    _fotografar(con, "3.6.129", "2026-09-15T10:11:53")
    _fotografar(con, "3.6.130", "2026-09-15T10:42:14")
    texto = "\n".join(PROJ.mudancas_medidas(con))
    assert "nota velha" not in texto and "Escrita antes" not in texto, texto


def test_sem_nota_nenhuma_a_secao_nao_aparece(casa):
    """Ausência de nota não pode virar «nada foi escrito»: quem não tem o dado
    não afirma sobre ele."""
    con = _con(casa)
    _fotografar(con, "3.6.129", "2026-09-15T10:11:53")
    _fotografar(con, "3.6.130", "2026-09-15T10:42:14")
    texto = "\n".join(PROJ.mudancas_medidas(con))
    assert "###" not in texto and "desenvolvimento escreveu" not in texto, texto


def test_banco_sem_as_colunas_das_notas_nao_derruba_nada(tmp_path):
    """Instalação que ainda não tem as colunas: a seção some, e não estoura.

    É o `except` ESTREITO de propósito — ele perdoa a coluna que falta (que é
    instalação velha) e não a consulta errada (que é defeito nosso)."""
    con = sqlite3.connect(tmp_path / "velho.sqlite3")
    con.execute("CREATE TABLE aj_problemas (id INTEGER PRIMARY KEY)")
    assert PROJ._notas_do_desenvolvimento(con, desde="2026-09-15T10:00:00") == []
    # e sem piso nenhum não se consulta nada
    assert PROJ._notas_do_desenvolvimento(con, desde="") == []


def test_a_primeira_frase_corta_e_nao_inventa():
    """Uma nota tem dez, vinte linhas, e ela inteira já vai na lista dos
    relatos. Aqui a pergunta é «o que mudou», e um resumo que ninguém acaba de
    ler não responde nada."""
    assert PROJ._primeira_frase("Curta. Segunda frase que não vai.") == \
        "Curta. […]"
    assert PROJ._primeira_frase("") == ""
    # frase única e longa: corta no limite, sem deixar palavra pela metade
    longa = "palavra " * 60
    cortada = PROJ._primeira_frase(longa)
    assert cortada.endswith("[…]") and len(cortada) <= 245, cortada
    assert "palavr " not in cortada
