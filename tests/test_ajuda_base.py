"""A BASE DE CONHECIMENTO PRÉ-CARREGADA DA AJUDA — 18/09/2026.

A FRASE DELE:

    «Preciso que o modulo de ajuda tenha uma base de conhecimento
     pré-carregada, não dá pra buscar as respostas de tudo para cada problema.»

E ele está certo, e o custo está medido: a mesma busca que ele descreve custava
**450 ms** no disco (`procurar_nos_documentos`), e a mesma pergunta podia custar
**três** dessas — uma nos documentos, outra nas regras, outra no que ele
escreveu. Com a base carregada uma vez por processo, a busca sai em dezenas de
milissegundos e as três fontes são varridas na mesma leitura.

O QUE ESTES TESTES GUARDAM, em ordem de importância:

1. **O ENDEREÇO QUE ELA DEVOLVE É CONFERRÍVEL.** Ela promete «a linha e o
   endereço de onde saiu». Endereço que mente manda quem lê para a linha errada
   e é pior que endereço nenhum, porque quem lê acredita — é a mesma família do
   «carimbo que mente». Aqui se abre o arquivo e se confere a linha, uma a uma.

2. **O QUE NÃO SE ACHA TAMBÉM TEM DE SER DITO.** Silêncio, numa base de
   conhecimento, se lê como «a casa nunca escreveu sobre isso» — e pode ser só
   que o arquivo não chegou ao servidor. Zero medido e zero por engano são a
   mesma tela e coisas diferentes.

3. **A ABA NÃO SE DECIDE POR MAIÚSCULA NEM POR ACENTO.** Era um defeito real da
   busca antiga: `UPPER` do SQLite é ASCII, e quem digitasse «matricula» não
   achava «matrícula» — a lição do `nome_da_casa`, aplicada à prosa.

4. **O TÍTULO TAMBÉM É CONTEÚDO.** A primeira versão não varria o cabeçalho, e
   procurar pelo nome de uma seção — que é como se procura o que se sabe que
   existe — não a achava.

5. **A BASE SE RECARREGA SOZINHA, E O CACHE NÃO MENTE.** O documento que mudou
   no disco tem de aparecer na busca seguinte. Cache que não confere entrega
   resposta velha com a cara da nova.

6. **O TEXTO DA BASE NÃO VAI EM TODA PERGUNTA.** São ~2 MB. O que vai é o
   número e os títulos do que o oficial escreveu — a mesma regra da fatia que
   `ajuda_projeto` já segue.

7. **O VERBETE TEM PISO, E É O MESMO DAS NOTAS.** Dez letras. Um verbete de
   três palavras não ensina nada a quem vem depois, e vai ser lido como se
   ensinasse.

8. **ESCREVER AQUI NÃO É ESCREVER NO CARTÓRIO.** A tabela é da ajuda, e nada do
   que a serventia lavrou passa por ela.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ajuda_base as BASE                                        # noqa: E402
import ajuda_projeto as PROJ                                     # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def sem_poluir_o_indice():
    """Devolve o índice ao estado de antes — os testes não deixam rastro.

    `_INDICE` é global e vive enquanto o processo viver; um teste que aponta a
    pasta para um `tmp_path` e não volta deixaria **todos os testes seguintes**
    procurando numa pasta vazia, e a falha apareceria longe daqui.
    """
    guardado = dict(BASE._INDICE)
    try:
        yield
    finally:
        BASE._INDICE.clear()
        BASE._INDICE.update(guardado)


@pytest.fixture()
def casa(tmp_path):
    """A aplicação de verdade, com banco de verdade — para o que é de tela."""
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


# ------------------------------------------------------- o que ela carrega


def test_a_base_carrega_as_fontes_da_casa():
    """Os documentos do projeto e as regras, medidos — e não uma lista escrita."""
    r = BASE.carregar(forcar=True)
    assert r["pronta"], f"a base não carregou: {r['falha']}"
    docs = r["por_fonte"].get(BASE.FONTE_DOCUMENTO, {})
    assert docs.get("origens", 0) >= BASE.PISO_DE_DOCUMENTOS, (
        f"só {docs.get('origens', 0)} documentos entraram — o piso é "
        f"{BASE.PISO_DE_DOCUMENTOS}"
    )
    assert r["por_fonte"].get(BASE.FONTE_REGRA), (
        "as regras da casa (CLAUDE.md) não entraram na base"
    )


def test_a_pasta_dos_documentos_e_uma_so_definicao():
    """`ajuda_projeto` e `ajuda_base` têm de apontar para a MESMA pasta.

    Duas definições do caminho divergem no primeiro conserto, e a que ficasse
    velha passaria a indexar metade do que a outra lê.
    """
    assert PROJ.PASTA == BASE.PASTA_DOS_DOCUMENTOS


def test_a_base_nao_carrega_documento_de_outra_pasta_da_casa():
    """Ela indexa a pasta dos documentos e o arquivo das regras — e mais nada.

    O `FONTES_EXTERNAS` (22 MB de doutrina) fica de fora de propósito, e não
    por esquecimento: ele não viaja no `.cgu`.
    """
    r = BASE.carregar()
    origens = {f["origem"] for f in BASE.fontes()}
    assert BASE.NOME_DAS_REGRAS in origens
    na_pasta = {p.name for p in BASE.PASTA_DOS_DOCUMENTOS.glob("*.md")}
    assert origens - {BASE.NOME_DAS_REGRAS} == na_pasta
    assert r["total_de_caracteres"] > 0


# --------------------------------------- o endereço aponta para a linha certa


def test_o_endereco_que_ela_devolve_aponta_para_a_linha_certa():
    """**O TESTE QUE MAIS IMPORTA.** Abre o arquivo e confere a linha.

    Ela promete «a linha e o endereço de onde saiu». Um endereço deslocado em
    uma linha manda quem lê para o parágrafo errado — e quem lê não desconfia
    de um endereço. Aqui se confere contra o arquivo, e não contra a própria
    memória da base (que é o defeito do teste que aplica a suposição aos dois
    lados).
    """
    for termo in ("carimbo que mente", "selo", "matrícula"):
        achado = BASE.buscar(termo, fonte=BASE.FONTE_DOCUMENTO, limite=8)
        assert achado["achados"], f"a base não achou «{termo}» nos documentos"
        for a in achado["achados"]:
            caminho = BASE.PASTA_DOS_DOCUMENTOS / a["origem"]
            linhas = caminho.read_text(encoding="utf-8", errors="replace").splitlines()
            assert 1 <= a["linha"] <= len(linhas), (
                f"{a['origem']}:{a['linha']} não existe — o arquivo tem "
                f"{len(linhas)} linhas"
            )
            na_linha = BASE.sem_acento(linhas[a["linha"] - 1])
            alvo = BASE.sem_acento(a["texto"]).strip()
            assert alvo and alvo[:60] in na_linha, (
                f"o endereço mente: {a['origem']}:{a['linha']} diz "
                f"«{a['texto'][:70]}», e o arquivo ali diz "
                f"«{linhas[a['linha'] - 1][:70]}»"
            )


def test_o_endereco_das_regras_leva_a_secao_e_nao_a_um_numero_solto():
    """Nas regras o endereço é a SEÇÃO, com o número e o título.

    Número solto não se encontra no `CLAUDE.md`, que tem 42 seções e nenhum
    marcador de linha; a seção se encontra.
    """
    achado = BASE.buscar("carimbo", fonte=BASE.FONTE_REGRA, limite=5)
    assert achado["achados"], "as regras não falaram de «carimbo»"
    for a in achado["achados"]:
        endereco = BASE._endereco(a)
        assert endereco.startswith("regras, seção ")
        assert a["secao"], "o achado veio sem a seção de onde saiu"
        assert str(a["secao_n"]) in endereco


def test_o_numero_da_linha_conta_o_cabecalho():
    """A primeira linha do arquivo é a linha 1 — e não a primeira do texto."""
    fonte = next(f for f in BASE.fontes() if f["fonte"] == BASE.FONTE_DOCUMENTO)
    primeiro = fonte["blocos"][0]
    assert primeiro["linha"] == 1, (
        "o primeiro bloco tem de começar na linha 1, que é o título do arquivo"
    )
    assert primeiro["primeira"] >= 1


# ------------------------------------------------------- como ela procura


def test_a_busca_nao_depende_de_acento_nem_de_maiuscula():
    """«matricula» tem de achar «matrícula» — e era defeito real na busca antiga.

    A lição do `nome_da_casa`: onde a igualdade importa, ela se constrói. Aqui
    vale para a prosa, e o termo existe nos documentos de verdade.
    """
    sem = BASE.buscar("matricula", limite=5)
    com = BASE.buscar("matrícula", limite=5)
    assert com["total"], "nem com acento a base achou «matrícula»"
    assert sem["total"] == com["total"], (
        f"«matricula» achou {sem['total']} e «matrícula» achou {com['total']} — "
        "a busca voltou a depender do acento"
    )
    assert BASE.buscar("SELO", limite=5)["total"] == BASE.buscar("selo", limite=5)["total"]


def test_o_titulo_da_secao_tambem_e_procurado():
    """O nome da seção é conteúdo: é por ele que se procura o que se sabe existir."""
    fonte = next(f for f in BASE.fontes() if f["fonte"] == BASE.FONTE_DOCUMENTO)
    titulo = fonte["titulo"]
    assert titulo and len(titulo) > 12, "o documento não tem título para procurar"
    achado = BASE.buscar(titulo, fonte=BASE.FONTE_DOCUMENTO, limite=40)
    assert any(a["linha"] == 1 for a in achado["achados"]), (
        f"a busca por «{titulo}» não achou o título do próprio arquivo"
    )


def test_a_busca_diz_quantas_linhas_tem_a_frase_e_quantas_tem_so_as_palavras():
    """Dois números diferentes, e a diferença é o que os separa.

    «carimbo que mente» numa linha é a casa escrevendo sobre aquilo; «carimbo» e
    «mente» em linhas separadas é a palavra aparecendo. Quem lê precisa saber
    qual dos dois achou, senão busca ampla vira citação errada.
    """
    achado = BASE.buscar("carimbo que mente", limite=40)
    assert achado["total"] >= achado["exatas"] >= 0
    assert achado["exatas"] > 0, (
        "a expressão «carimbo que mente» é da casa e não foi achada inteira"
    )
    # A ORDEM É A PERTINÊNCIA: o primeiro da lista é o que tem a frase inteira.
    assert achado["achados"][0]["pontos"] >= 1000
    mostrados_exatos = [a for a in achado["achados"] if a["pontos"] >= 1000]
    assert 0 < len(mostrados_exatos) <= achado["exatas"], (
        f"foram mostradas {len(mostrados_exatos)} linhas com a frase exata, e o "
        f"número declarado é {achado['exatas']} — a conta e a lista discordam"
    )


def test_a_busca_espalha_os_achados_e_nao_deixa_um_documento_so_encher_a_lista():
    """O defeito antigo: o primeiro documento de 300 KB respondia por tudo."""
    achado = BASE.buscar("selo", limite=BASE.LIMITE_DA_BUSCA)
    origens = [a["origem"] for a in achado["achados"]]
    contagem: dict[str, int] = {}
    for o in origens:
        contagem[o] = contagem.get(o, 0) + 1
    assert len(contagem) >= 4, (
        f"a lista veio de {len(contagem)} origem(ns) só: {contagem}"
    )
    assert max(contagem.values()) > BASE.LIMITE_POR_ORIGEM or achado["total"] < 20


def test_termo_vazio_e_recusado_com_frase_da_casa():
    """Recusar é melhor que devolver tudo — e a frase diz o que fazer."""
    with pytest.raises(BASE.BaseError) as erro:
        BASE.buscar("   ")
    assert "procurar" in str(erro.value).lower()


def test_limite_zero_nao_devolve_nada_com_cara_de_achado():
    """`limite=0` não pode achar 200 linhas e mostrar zero — o pior dos dois mundos."""
    achado = BASE.buscar("selo", limite=0)
    assert achado["total"] > 0
    assert achado["mostrando"] >= 1 and achado["achados"]


# --------------------------------------------- a busca única, nas três fontes


def test_buscar_em_tudo_procura_nas_tres_fontes_numa_chamada_so():
    """É o pedido dele: uma chamada em vez de três."""
    # Um termo que só o oficial escreveu — e ele tem de aparecer junto.
    termo = "zircônio ornamental de prova"
    with sqlite3.connect(":memory:") as con:
        BASE.init_ajuda_base_schema(con)
        BASE.gravar_verbete(con, titulo="A prova da busca única da ajuda",
                            texto=f"Este verbete fala do {termo}, e de mais nada.",
                            por="JEAN", agora="2026-09-18 15:00:00")
        texto = BASE.buscar_em_tudo(termo, con=con)
    assert "verbete" in BASE.sem_acento(texto), texto
    # E as três fontes são varridas na mesma leitura: o número sai repartido.
    assert "linha(s) com" in texto


def test_o_que_nao_se_acha_diz_que_nao_se_achou_e_por_que_isso_nao_e_prova():
    """Silêncio viraria «a casa nunca escreveu sobre isso»."""
    texto = BASE.buscar_em_tudo("xyzzy plugh quux inexistente")
    assert "não tem nada" in texto
    assert "não que a coisa não exista" in texto


def test_o_que_nao_se_achou_e_contado_por_fonte_e_nao_por_arquivo():
    """**A parede de números foi defeito meu, e ela saiu medida.**

    A primeira versão somava o que `fontes()` devolve — e `fontes()` é uma
    linha por ARQUIVO. A resposta saía com **173 números**, um por documento
    (medido em 18/09/2026: 2.400 caracteres de lista para dizer «procurei em
    tudo»). Quem pergunta «não achou?» quer o tamanho do que foi varrido, e
    são três os lugares, não cento e setenta e três.

    O guarda mede o que a resposta promete: os números de `linhas` têm de ser
    poucos, e nenhum pode mandar conferir o arquivo — porque aqui não se achou
    linha nenhuma para conferir.
    """
    texto = BASE.buscar_em_tudo("xyzzy plugh quux inexistente")
    quantos = texto.count("linhas ")
    assert quantos <= 3, (
        f"a resposta listou {quantos} tamanhos de fonte — ela tem de contar por "
        f"fonte (documentos, regras e verbetes), e não por arquivo: {texto[:400]}"
    )
    assert "nos documentos do projeto" in texto
    assert "nas regras da casa" in texto
    # E a frase não é uma lista de origens: o nome de arquivo de documento
    # nenhum entra, porque nada foi achado nele.
    for f in BASE.fontes():
        if f["fonte"] != BASE.FONTE_DOCUMENTO:
            continue
        assert f["origem"] not in texto, (
            f"a resposta sem achado citou o arquivo {f['origem']} — o tamanho é "
            "por fonte, e não por origem"
        )
        break


# ------------------------------------------------------------- o contexto


def test_o_contexto_nao_leva_o_texto_da_base():
    """São ~2 MB; o que vai em toda pergunta é o número, e não a prosa."""
    r = BASE.carregar()
    contexto = BASE.para_o_contexto()
    assert len(contexto) < 6_000, (
        f"o contexto tem {len(contexto)} caracteres — a base inteira tem "
        f"{r['total_de_caracteres']}"
    )
    docs = r["por_fonte"][BASE.FONTE_DOCUMENTO]
    regras = r["por_fonte"][BASE.FONTE_REGRA]
    assert f"{docs['origens']} documentos" in contexto
    assert str(docs["linhas"]) in contexto
    assert str(regras["linhas"]) in contexto
    assert "buscar_na_base" in contexto, (
        "o contexto tem de dizer QUE a busca existe, senão o modelo volta a "
        "procurar de um em um"
    )


def test_o_contexto_leva_o_titulo_do_verbete_e_nao_o_texto_dele():
    """A regra da fatia: o título deixa pedir o resto."""
    with sqlite3.connect(":memory:") as con:
        BASE.init_ajuda_base_schema(con)
        BASE.gravar_verbete(
            con, titulo="Como se confere a folha de segurança do civil",
            texto="A folha é única e a próxima é a MENOR em branco, por número. "
                  "Este texto não pode ir no contexto de toda pergunta.",
            por="JEAN", agora="2026-09-18 15:00:00")
        contexto = BASE.para_o_contexto(con)
    assert "Como se confere a folha de segurança do civil" in contexto
    assert "MENOR em branco" not in contexto


def test_o_contexto_diz_que_nao_carregou_em_vez_de_dizer_zero(sem_poluir_o_indice,
                                                             tmp_path, monkeypatch):
    """Zero medido e zero por engano são a mesma tela e coisas diferentes."""
    monkeypatch.setattr(BASE, "carregar", lambda **_: {
        "pronta": False, "falha": "PermissionError: acesso negado",
        "por_fonte": {}, "construida_em": "", "segundos": 0})
    texto = BASE.para_o_contexto()
    assert "não carregou" in texto
    assert "acesso negado" in texto


# --------------------------------------------------- o que o oficial escreve


def test_verbete_curto_e_recusado_pelo_mesmo_piso_das_notas():
    with sqlite3.connect(":memory:") as con:
        BASE.init_ajuda_base_schema(con)
        with pytest.raises(BASE.BaseError) as erro:
            BASE.gravar_verbete(con, titulo="ok", texto="sim", por="JEAN")
        assert "dez letras" in str(erro.value)
        with pytest.raises(BASE.BaseError) as erro:
            BASE.gravar_verbete(con, titulo="Um título bem formado",
                                texto="curto", por="JEAN")
        assert "dez letras" in str(erro.value)


def test_alterar_verbete_que_nao_existe_recusa_em_vez_de_criar_outro():
    with sqlite3.connect(":memory:") as con:
        BASE.init_ajuda_base_schema(con)
        with pytest.raises(BASE.BaseError) as erro:
            BASE.gravar_verbete(con, id_=999, titulo="Título trocado por engano",
                                texto="Este texto é longo o bastante.", por="JEAN")
        assert "não existe mais" in str(erro.value)


def test_apagar_verbete_que_nao_existe_devolve_falso():
    """`rowcount` é resposta; «deu certo» é suposição."""
    with sqlite3.connect(":memory:") as con:
        BASE.init_ajuda_base_schema(con)
        assert BASE.apagar_verbete(con, id_=123) is False


def test_verbete_gravado_alterado_e_apagado_na_base():
    with sqlite3.connect(":memory:") as con:
        BASE.init_ajuda_base_schema(con)
        n = BASE.gravar_verbete(con, titulo="O selo do casamento é um só",
                                texto="Ele é emitido na habilitação e "
                                      "espelhado no assento.", assunto="selo",
                                onde="/notas/selo", por="JEAN",
                                agora="2026-09-18 15:00:00")
        assert n > 0
        v = BASE.verbete(con, n)
        assert v["titulo"] == "O selo do casamento é um só"
        BASE.gravar_verbete(con, id_=n, titulo="O selo do casamento é um só",
                            texto="Texto corrigido, e mais longo que o piso.",
                            por="JEAN", agora="2026-09-18 15:10:00")
        assert "corrigido" in BASE.verbete(con, n)["texto"]
        assert BASE.apagar_verbete(con, id_=n) is True
        assert BASE.verbete(con, n) is None


def test_o_verbete_entra_na_busca_como_uma_fonte_a_mais():
    """Ele é lido com a mesma convicção dos documentos — e é por isso o piso."""
    with sqlite3.connect(":memory:") as con:
        BASE.init_ajuda_base_schema(con)
        BASE.gravar_verbete(con, titulo="O caminho do selo da escritura",
                            texto="O ato de livro não estava em CAMINHO_DAS_NOTAS.",
                            por="JEAN", agora="2026-09-18 15:00:00")
        achado = BASE.buscar("CAMINHO_DAS_NOTAS", fonte=BASE.FONTE_MANUAL, con=con)
    assert achado["total"] == 1
    assert achado["achados"][0]["verbete"] == 1
    assert "escrito por JEAN" in BASE._endereco(achado["achados"][0])


# ------------------------------------------- o cache não mente, e não trava


def test_a_base_se_recarrega_quando_o_documento_muda(sem_poluir_o_indice,
                                                     tmp_path, monkeypatch):
    """O arquivo mudou no disco; a busca seguinte tem de enxergar o novo texto.

    Cache que não confere entrega a resposta velha com a cara da nova — e aqui
    quem lê é uma máquina, que responde com convicção.
    """
    pasta = tmp_path / "DOCUMENTACAO"
    pasta.mkdir()
    (pasta / "NOTA_DE_TESTE.md").write_text(
        "# Nota de teste\n\nO primeiro texto fala de abacaxi.\n", encoding="utf-8")
    monkeypatch.setattr(BASE, "PASTA_DOS_DOCUMENTOS", pasta)
    monkeypatch.setattr(BASE, "INTERVALO_DA_CONFERENCIA", 0.0)
    BASE.carregar(forcar=True)
    assert BASE.buscar("abacaxi")["total"] == 1
    assert BASE.buscar("jabuticaba")["total"] == 0
    (pasta / "NOTA_DE_TESTE.md").write_text(
        "# Nota de teste\n\nO segundo texto fala de jabuticaba.\n", encoding="utf-8")
    BASE.carregar()
    assert BASE.buscar("jabuticaba")["total"] == 1, (
        "a base continuou lendo o texto velho — o cache não conferiu o arquivo"
    )
    assert BASE.buscar("abacaxi")["total"] == 0


def test_arquivo_ilegivel_nao_derruba_a_base_inteira(sem_poluir_o_indice,
                                                     tmp_path, monkeypatch):
    """Um arquivo ruim tira ele da base — e não deixa a ajuda sem nenhuma."""
    pasta = tmp_path / "DOCUMENTACAO"
    pasta.mkdir()
    (pasta / "BOM.md").write_text("# Bom\n\nFala de laranja.\n", encoding="utf-8")
    (pasta / "RUIM.md").write_bytes(b"\xff\xfe\x00\x00bin\x00rio")
    monkeypatch.setattr(BASE, "PASTA_DOS_DOCUMENTOS", pasta)
    monkeypatch.setattr(BASE, "INTERVALO_DA_CONFERENCIA", 0.0)
    r = BASE.carregar(forcar=True)
    assert r["pronta"], "a base caiu por causa de um arquivo"
    assert BASE.buscar("laranja")["total"] >= 1


def test_zero_documento_na_pasta_aparece_como_zero_e_nao_como_pronto(
        sem_poluir_o_indice, tmp_path, monkeypatch):
    """Pasta vazia é base vazia — com o número à vista, e não silêncio."""
    pasta = tmp_path / "DOCUMENTACAO"
    pasta.mkdir()
    monkeypatch.setattr(BASE, "PASTA_DOS_DOCUMENTOS", pasta)
    monkeypatch.setattr(BASE, "INTERVALO_DA_CONFERENCIA", 0.0)
    r = BASE.carregar(forcar=True)
    docs = r["por_fonte"].get(BASE.FONTE_DOCUMENTO, {})
    assert docs.get("origens", 0) == 0
    assert docs.get("origens", 0) < BASE.PISO_DE_DOCUMENTOS, (
        "o piso existe para a tela poder denunciar a pasta que não chegou"
    )


# ----------------------------------------------------------------- a tela


def test_a_tela_da_base_abre_e_nao_gasta_consulta(casa):
    """Ver o que a ajuda sabe não pode custar uma pergunta."""
    con = _con(casa)
    antes = con.execute("SELECT COUNT(*) FROM aj_consultas").fetchone()[0]
    con.close()
    r = casa["cliente"].get("/ajuda/base")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Base de conhecimento da ajuda" in html
    assert "Experimentar uma busca" in html
    assert "O que a ajuda recebe em toda pergunta" in html
    con = _con(casa)
    depois = con.execute("SELECT COUNT(*) FROM aj_consultas").fetchone()[0]
    con.close()
    assert antes == depois, "abrir a tela da base gastou uma consulta"


def test_a_tela_da_base_procura_com_a_mesma_funcao_que_a_ajuda_usa(casa):
    """O que a tela mostra é o que a ajuda receberia — a mesma função."""
    r = casa["cliente"].get("/ajuda/base?procurar=carimbo+que+mente")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "carimbo que mente" in html
    assert "linha(s) com" in html


def test_a_tela_escreve_e_apaga_o_verbete_do_oficial(casa):
    cliente = casa["cliente"]
    pagina = cliente.get("/ajuda/base").get_data(as_text=True)
    r = cliente.post("/ajuda/base/gravar",
                     data={"csrf_token": _token(pagina),
                           "titulo": "A regra da etiqueta que se ajusta",
                           "assunto": "etiqueta",
                           "onde": "/reconhecimentos/cartoes",
                           "texto": "A impressora térmica nunca encaixa de "
                                    "primeira, e por isso a tela de ajuste."},
                     follow_redirects=True)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "A regra da etiqueta que se ajusta" in html, "o verbete não apareceu"
    con = _con(casa)
    v = con.execute("SELECT * FROM aj_verbetes").fetchone()
    con.close()
    assert v["criado_por"] == "MARIO EXEMPLO DOS SANTOS", (
        "o rastro do verbete é o NOME, e não o login — quem lê meses depois "
        "pergunta «quem escreveu isto?»"
    )
    pagina = cliente.get("/ajuda/base").get_data(as_text=True)
    r = cliente.post(f"/ajuda/base/{v['id']}/apagar",
                     data={"csrf_token": _token(pagina)},
                     follow_redirects=True)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    # A FRASE DO AVISO CITA O TÍTULO QUE SAIU — por isso a conferência é a
    # LINHA do verbete e a tabela, e não a página inteira: procurar a palavra no
    # HTML acharia o próprio aviso, que é onde ela deve mesmo estar.
    assert "saiu da base" in html
    assert "Nenhum verbete escrito ainda" in html, (
        "o verbete apagado continuou na lista"
    )
    con = _con(casa)
    assert con.execute("SELECT COUNT(*) FROM aj_verbetes").fetchone()[0] == 0
    con.close()


def test_a_tela_recusa_verbete_curto_com_frase_para_o_balcao(casa):
    cliente = casa["cliente"]
    pagina = cliente.get("/ajuda/base").get_data(as_text=True)
    r = cliente.post("/ajuda/base/gravar",
                     data={"csrf_token": _token(pagina), "titulo": "ok",
                           "texto": "sim"},
                     follow_redirects=True)
    assert r.status_code == 200
    assert "dez letras" in r.get_data(as_text=True)
    con = _con(casa)
    assert con.execute("SELECT COUNT(*) FROM aj_verbetes").fetchone()[0] == 0
    con.close()


def test_a_tela_nao_e_do_balcao(casa):
    """Escrever na base é da gerência — o que entra ali volta como resposta."""
    from database import Database
    casa["db"].create_user("ana", "ANA DA SILVA", SENHA, "USER")
    outro = casa["app"].test_client()
    outro.post("/login",
               data={"username": "ana", "password": SENHA,
                     "csrf_token": _token(outro.get("/login").get_data(as_text=True))},
               follow_redirects=True)
    r = outro.get("/ajuda/base")
    assert r.status_code in (302, 403), (
        "o balcão não escreve na base de conhecimento da ajuda"
    )
