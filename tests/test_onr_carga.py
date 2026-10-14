"""A carga completa para o Next Cloud SAS do ONR — modalidade (b).

    «vamos seguir a modalidade b. processse, escreva, me ensine a usar.
     e como fica o indicador real?»               — o oficial, 04/09/2026

O TESTE QUE MAIS VALE AQUI É O DA PERGUNTA DELE
    O Next Cloud SAS leva DUAS das três coisas. O indicador real continua indo
    pela API — medido: «indicador real» aparece **zero vezes** nos seis
    documentos do ONR que estão na casa. Quem lesse «Next Cloud SAS ligado»
    concluiria que o Registro de Imóveis inteiro está integrado, e o índice
    real pararia sem ninguém ver.

E O SEGUNDO É O DA CÓPIA QUE NÃO SE FEZ
    O formato do `<BANCOLIGHT>` foi levantado dos 19 arquivos que esta casa
    realmente mandou. Escrevê-lo de novo aqui daria duas versões do mesmo
    arquivo, divergindo no primeiro conserto — e o que a tela mostrasse
    deixaria de ser o que o programa IPS lê.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import struct
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.lento  # carga/geracao integral; fica na suite completa

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_carga as OCG                                          # noqa: E402
import ri_onr as ONR                                             # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "db": bd, "tmp": dados}


def _con(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _matricula(s, numero: str, *, livro: str = "2",
               abertura: str = "1980-05-10") -> int:
    con = sqlite3.connect(s["banco"])
    cur = con.execute(
        "INSERT INTO ri_matriculas (numero, livro, data_abertura, criado_em) "
        "VALUES (?,?,?,?)", (numero, livro, abertura, "2026-09-04"))
    con.commit()
    mid = int(cur.lastrowid)
    con.close()
    return mid


def _parte(s, matricula_id: int, nome: str, documento: str | None = None,
           tipo: str | None = None) -> None:
    con = sqlite3.connect(s["banco"])
    con.execute(
        "INSERT INTO ri_partes (matricula_id, nome, documento_numero, "
        "documento_tipo, papel) VALUES (?,?,?,?,?)",
        (matricula_id, nome, documento, tipo, "proprietario"))
    con.commit()
    con.close()


def _tiff(caminho: Path, *, dpi: int = 200, compressao: int = 4,
          unidade: int = 2) -> None:
    """Um TIFF mínimo, de verdade — cabeçalho com as quatro tags que o ONR pede.

    **Escrever o cabeçalho à mão é o ponto**: o teste tem de exercitar o mesmo
    leitor que a tela usa, e um arquivo de mentira com bytes aleatórios provaria
    só que ele não estoura.
    """
    tags = [(256, 3, 1, 100), (257, 3, 1, 100), (258, 3, 1, 1),
            (259, 3, 1, compressao), (296, 3, 1, unidade)]
    # 282/283 sao RATIONAL: o valor mora fora, depois do diretorio.
    cabecalho = 8
    n = len(tags) + 2
    fim_do_dir = cabecalho + 2 + n * 12 + 4
    dados = struct.pack("<IIII", dpi, 1, dpi, 1)          # x/1 e y/1
    tags = tags + [(282, 5, 1, fim_do_dir), (283, 5, 1, fim_do_dir + 8)]
    tags.sort()
    saida = b"II" + struct.pack("<HI", 42, cabecalho)
    saida += struct.pack("<H", len(tags))
    for etiqueta, tipo, cnt, valor in tags:
        if tipo == 3:
            saida += struct.pack("<HHIHH", etiqueta, tipo, cnt, valor, 0)
        else:
            saida += struct.pack("<HHII", etiqueta, tipo, cnt, valor)
    saida += struct.pack("<I", 0) + dados
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(saida)


def _disco(s, *itens: tuple[str, str]) -> Path:
    """Cada item é (pasta, nome). A pasta do ONR agrupa de mil em mil."""
    raiz = s["tmp"] / "ONR" / "IMAGENS"
    for pasta, nome in itens:
        _tiff(raiz / pasta / nome)
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz


# ============================================ a pergunta do oficial


def test_o_INDICADOR_REAL_nao_passa_pelo_next_cloud_sas(s):
    """**A pergunta dele, respondida no código.**

    Medido em 04/09/2026 nos seis documentos do ONR: «indicador real» aparece
    zero vezes em todos. O Next Cloud SAS é armazenamento — Bucket e Firestore
    —, e o indicador real é envio pela API, que tem tela própria.

    Aderir à modalidade (b) **não desliga** o indicador real, e a tela tem de
    dizer isso: quem lesse «Next Cloud SAS ligado» concluiria que o Registro de
    Imóveis inteiro está integrado.
    """
    publicos = [n for n in dir(OCG) if not n.startswith("_")]
    assert not [n for n in publicos if "real" in n.lower()], (
        "este módulo não trata do indicador real — ele vai pela API, em "
        "ri_onr_central")

    _matricula(s, "1")
    html = " ".join(s["c"].get("/registro-imoveis/onr/next-cloud-sas")
                    .get_data(as_text=True).split())
    assert "Indicador Real" in html
    assert "não passa pelo Next Cloud SAS" in html
    assert "não desliga o indicador real" in html
    # e ela LEVA à tela em que ele acontece
    assert "/ri/onr" in html


# ============================================ o Indicador Pessoal


def test_a_carga_e_COMPLETA_e_nao_de_um_periodo(s):
    """O `ri_onr` gera o mês; o Next Cloud SAS pede tudo, «desde 1976».

    Mandar um mês faria a base «parcial» que o ONR recusa por escrito.
    """
    a = _matricula(s, "1", abertura="1977-03-16")
    b = _matricula(s, "2", abertura="2026-01-05")
    _parte(s, a, "JOÃO TEIXEIRA DA SILVA")
    _parte(s, b, "MARIA DAS DORES", "00000002801", "CPF")
    with _con(s) as con:
        vinculos = OCG.vinculos_da_carga(con)
    assert len(vinculos) == 2, "os dois entram, apesar de 49 anos de distância"


def test_o_xml_sai_no_formato_dos_arquivos_que_a_casa_MANDOU(s):
    """Os seis campos do modelo do ONR, na ordem, com a data em ddmmaaaa."""
    m = _matricula(s, "1", abertura="1977-03-16")
    _parte(s, m, "JOÃO TEIXEIRA DA SILVA")
    with _con(s) as con:
        xml = OCG.gerar_indicador_pessoal(con, "000000")
    assert "<BANCOLIGHT>" in xml and "</BANCOLIGHT>" in xml
    assert "<NOME>JOÃO TEIXEIRA DA SILVA</NOME>" in xml
    assert "<NMATRICULA>1</NMATRICULA>" in xml
    assert "<DTREGAVERB>16031977</DTREGAVERB>" in xml, "ddmmaaaa, sem barra"
    for campo in ("NOME", "CNPJCPF", "NMATRICULA", "TIPODEATO",
                  "DTREGAVERB", "DTVENDA"):
        assert f"<{campo}>" in xml, f"o modelo do ONR exige {campo}"


def test_NAO_HA_SEGUNDA_MONTAGEM_do_xml(s):
    """**O formato mora num lugar só.**

    `ri_onr.gerar_indicador_pessoal` foi levantado dos 19 arquivos reais desta
    casa. Uma cópia aqui divergiria no primeiro conserto, e o que a tela
    mostrasse deixaria de ser o que o programa IPS lê — a lição da
    `normalizar_nome` pela quinta vez.
    """
    import ast
    fonte = (RAIZ / "onr_carga.py").read_text(encoding="utf-8")
    assert "ONR.gerar_indicador_pessoal(" in fonte, (
        "onr_carga tem de CHAMAR ri_onr, e não remontar o XML")

    # **O VARREDOR LÊ O CÓDIGO, E NÃO A PROSA** — pela nona vez neste projeto,
    # e a primeira em que a prosa era a minha. O docstring deste módulo cita
    # `<BANCOLIGHT>` justamente para explicar que ele NÃO o monta; procurar a
    # palavra no arquivo inteiro acusaria a explicação.
    # **E O DOCSTRING SE EXCLUI PELO NÓ, E NÃO PELO TEXTO** — defeito meu na
    # primeira versão: `ast.get_docstring` **limpa** a indentação, e o texto
    # limpo nunca bate com o literal cru da árvore. Comparar textos deixava
    # todo docstring passar como se fosse código.
    arvore = ast.parse(fonte)
    docs = set()
    for n in ast.walk(arvore):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                          ast.AsyncFunctionDef)) and n.body:
            primeiro = n.body[0]
            if (isinstance(primeiro, ast.Expr)
                    and isinstance(primeiro.value, ast.Constant)
                    and isinstance(primeiro.value.value, str)):
                docs.add(id(primeiro.value))
    literais = [n.value for n in ast.walk(arvore)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docs]
    for marca in ("<BANCOLIGHT>", "<INDIVIDUO>", "<CNPJCPF>"):
        assert not [s for s in literais if marca in s], (
            f"{marca} não pode ser escrito aqui: o formato mora em ri_onr")


def test_o_documento_zerado_e_PRECEDENTE_DA_CASA_e_fica_DECLARADO(s):
    """**Os dois lados aparecem, porque quem assina precisa dos dois.**

    O modelo do ONR diz «a informação deve ser maior que zero»; os arquivos
    que esta casa mandou trazem 7.812 de 10.781 com onze zeros. Vale a regra
    do oficial — como o E-Ofício fazia —, e a divergência não passa calada.
    """
    m = _matricula(s, "1")
    _parte(s, m, "SEM DOCUMENTO NENHUM")
    _parte(s, m, "COM CPF", "00000002801", "CPF")
    with _con(s) as con:
        r = OCG.conferir_indicador_pessoal(con)
        xml = OCG.gerar_indicador_pessoal(con, "000000")
    assert r["sem_documento"] == 1 and r["com_documento"] == 1
    assert ONR.DOC_DESCONHECIDO in xml
    assert "maior que zero" in r["precedente_da_casa"]

    html = " ".join(s["c"].get("/registro-imoveis/onr/next-cloud-sas")
                    .get_data(as_text=True).split())
    assert "documento zerado" in html
    assert "decisão sua, não do sistema" in html


# ============================================ as imagens


def test_a_pasta_do_ONR_agrupa_de_mil_em_mil(s):
    """`00000000` guarda 1 a 999; `00000001` guarda 1000 a 1999."""
    raiz = _disco(s, ("00000000", "00000005.0001"),
                     ("00000003", "00003744.0001"))
    r = OCG.conferir_imagens(raiz)
    assert r["no_padrao"] == 2
    assert r["quantos_fora_da_pasta"] == 0
    assert r["matriculas"] == 2


def test_arquivo_na_pasta_ERRADA_aparece_com_o_nome(s):
    """Pasta errada é arquivo que o CSL2 não acha — e some sem avisar."""
    raiz = _disco(s, ("00000000", "00003744.0001"))   # 3744 pertence à 00000003
    r = OCG.conferir_imagens(raiz)
    assert r["no_padrao"] == 0
    assert r["quantos_fora_da_pasta"] == 1
    assert "00003744.0001" in r["fora_da_pasta"][0]


def test_arquivo_NA_RAIZ_conta_como_fora_da_pasta(s):
    """Os quatro `00000000.000N` desta casa estão na raiz, sem pasta nenhuma —
    e o número deles é ZERO, que não é matrícula."""
    raiz = s["tmp"] / "ONR" / "IMAGENS"
    _tiff(raiz / "00000000.0001")
    r = OCG.conferir_imagens(raiz)
    assert r["quantos_fora_da_pasta"] == 1


def test_a_resolucao_e_a_compressao_se_MEDEM_no_cabecalho(s):
    """200 × 200 dpi e compressão sem perdas — o que o ONR exige por escrito."""
    raiz = _disco(s, ("00000000", "00000005.0001"))
    r = OCG.conferir_imagens(raiz)
    assert r["amostra"] == 1
    assert r["resolucao_ok"] == 1
    assert r["compressao_ok"] == 1
    assert not r["achados"]


def test_resolucao_ERRADA_vira_achado_com_o_numero(s):
    """Dizer «fora do padrão» sem dizer quanto é não ajuda a consertar."""
    raiz = s["tmp"] / "ONR" / "IMAGENS"
    _tiff(raiz / "00000000" / "00000005.0001", dpi=96)
    r = OCG.conferir_imagens(raiz)
    assert r["resolucao_ok"] == 0
    assert any("96" in a and "200" in a for a in r["achados"])


def test_compressao_COM_PERDAS_e_recusada_pelo_nome(s):
    """JPEG num documento registral é perda de informação que não volta."""
    raiz = s["tmp"] / "ONR" / "IMAGENS"
    _tiff(raiz / "00000000" / "00000005.0001", compressao=7)
    r = OCG.conferir_imagens(raiz)
    assert r["compressao_ok"] == 0
    assert any("JPEG" in a for a in r["achados"])


def test_conferir_imagens_NAO_GRAVA_nada(s):
    _matricula(s, "5")
    raiz = _disco(s, ("00000000", "00000005.0001"))
    with _con(s) as con:
        antes = con.execute("SELECT COUNT(*) FROM ri_imagens").fetchone()[0]
        OCG.conferir_imagens(raiz)
        OCG.matriculas_sem_imagem(con, raiz)
        assert con.execute(
            "SELECT COUNT(*) FROM ri_imagens").fetchone()[0] == antes == 0


def test_pasta_que_nao_existe_e_erro_de_regra_com_a_dica_do_SYSTEM(s):
    with pytest.raises(OCG.CargaOnrError) as erro:
        OCG.conferir_imagens(s["tmp"] / "nao-existe")
    assert "SYSTEM" in str(erro.value)


# ============================================ o que o ONR recusa


def test_matricula_SEM_UMA_UNICA_PAGINA_e_o_que_torna_a_base_incompleta(s):
    """Ficha pela metade não entra nesta conta: para o Bucket, matrícula com
    uma página é matrícula que existe."""
    com = _matricula(s, "5")
    sem = _matricula(s, "9")
    raiz = _disco(s, ("00000000", "00000005.0001"))
    with _con(s) as con:
        faltando = OCG.matriculas_sem_imagem(con, raiz)
    assert [f["id"] for f in faltando] == [sem]
    assert com not in [f["id"] for f in faltando]


def test_067_e_67_sao_a_MESMA_matricula_para_o_disco(s):
    """O disco guarda `00000067.0001`; o banco pode ter `067`. Comparar o texto
    cru diria que a matrícula não tem imagem, e ela tem."""
    m = _matricula(s, "067")
    raiz = _disco(s, ("00000000", "00000067.0001"))
    with _con(s) as con:
        assert OCG.matriculas_sem_imagem(con, raiz) == []
    assert m


def test_a_prontidao_NAO_DIZ_pronto_nem_nao_pronto(s):
    """**Quem decide se manda a base como está é quem assina.**

    Um verde ou vermelho aqui seria o sistema decidindo pelo oficial — a regra
    do CNIB pela sétima vez. A conferência devolve os números; a declaração de
    base incompleta é dele.
    """
    _matricula(s, "5", abertura="1951-04-14")
    raiz = _disco(s, ("00000000", "00000005.0001"))
    with _con(s) as con:
        q = OCG.prontidao(con, raiz)
    assert set(q) >= {"matriculas", "indicador_pessoal", "imagens",
                      "sem_imagem", "alcanca_1976"}
    for proibida in ("pronto", "aprovado", "pode_enviar", "ok"):
        assert proibida not in q, (
            "a conferência mede; quem decide é o oficial")
    assert q["alcanca_1976"] is True


def test_pasta_que_nao_abre_NAO_VIRA_ZERO(s):
    """**Zero medido e zero por engano são a mesma tela e coisas diferentes.**

    Se a pasta não abre, o erro sobe no lugar dos números — senão a tela diria
    «nenhuma imagem faltando» com cara de medição.
    """
    _matricula(s, "5")
    with _con(s) as con:
        q = OCG.prontidao(con, s["tmp"] / "nao-existe")
    assert q["imagens"] is None
    assert q["sem_imagem"] is None
    assert q["erro_do_disco"] and "SYSTEM" in q["erro_do_disco"]

    con = sqlite3.connect(s["banco"])
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                ("ri_imagens_raiz", str(s["tmp"] / "nao-existe")))
    con.commit()
    con.close()
    html = " ".join(s["c"].get("/registro-imoveis/onr/next-cloud-sas")
                    .get_data(as_text=True).split())
    assert "Não deu para ler a pasta" in html


# ============================================ a tela


def test_as_duas_rotas_existem_E_A_TELA_AS_CHAMA(s):
    """Função pronta que nenhuma tela chama é o defeito mais repetido daqui."""
    regras = {r.rule for r in s["app"].url_map.iter_rules()}
    assert "/registro-imoveis/onr/next-cloud-sas" in regras
    assert "/registro-imoveis/onr/next-cloud-sas/indicador-pessoal" in regras

    m = _matricula(s, "5")
    _parte(s, m, "ALGUEM")
    html = s["c"].get("/registro-imoveis/onr/next-cloud-sas").get_data(
        as_text=True)
    assert "/registro-imoveis/onr/next-cloud-sas/indicador-pessoal" in html
    assert "csrf_token" in html, "toda tela que grava manda o token"


def test_gerar_pela_tela_entrega_o_XML_com_nome_de_CARGA_COMPLETA(s):
    m = _matricula(s, "1", abertura="1977-03-16")
    _parte(s, m, "JOÃO TEIXEIRA DA SILVA")
    html = s["c"].get("/registro-imoveis/onr/next-cloud-sas").get_data(
        as_text=True)
    r = s["c"].post("/registro-imoveis/onr/next-cloud-sas/indicador-pessoal",
                    data={"csrf_token": _token(html)})
    assert r.status_code == 200
    assert "CARGA_COMPLETA" in r.headers["Content-Disposition"]
    corpo = r.get_data(as_text=True)
    assert "<BANCOLIGHT>" in corpo
    assert "<NMATRICULA>1</NMATRICULA>" in corpo


def test_a_tela_diz_que_o_sistema_NAO_TRANSMITE(s):
    """Quem sobe são o IPS e o CSL2, programas do ONR instalados aqui. Uma tela
    que dissesse «enviar» faria o oficial esperar um envio que não acontece."""
    _matricula(s, "1")
    html = " ".join(s["c"].get("/registro-imoveis/onr/next-cloud-sas")
                    .get_data(as_text=True).split())
    assert "não transmite nada" in html
    assert "CSL2" in html and "IPS" in html


# ============================================ o que o ensaio contra a produção achou
#
# **TESTE DE MESA PROVA A REGRA; ENSAIO CONTRA A PRODUÇÃO PROVA O DADO.** Os
# vinte primeiros testes deste arquivo passavam, e rodar o módulo contra o
# banco de verdade achou duas coisas em minutos.


def test_DTVENDA_leva_a_mesma_data_como_a_casa_sempre_mandou(s):
    """**Medido: `DTVENDA` == `DTREGAVERB` em 10.781 de 10.781.**

    Nos 19 arquivos que esta serventia mandou ao ONR, sem uma única exceção. A
    primeira versão deste módulo deixava o campo vazio — e os testes de mesa
    passavam, porque no teste eu escrevia o que esperava ver.

    Vale a regra do oficial de 24/08/2026: na dúvida, como o E-Ofício fazia.
    """
    m = _matricula(s, "1", abertura="1977-03-16")
    _parte(s, m, "JOÃO TEIXEIRA DA SILVA")
    with _con(s) as con:
        xml = OCG.gerar_indicador_pessoal(con, "000000")
    assert "<DTREGAVERB>16031977</DTREGAVERB>" in xml
    assert "<DTVENDA>16031977</DTVENDA>" in xml, (
        "a casa sempre mandou a mesma data nos dois — 10.781 de 10.781")
    assert "<DTVENDA></DTVENDA>" not in xml


def test_nome_com_lixo_na_frente_se_DECLARA_e_nao_se_limpa(s):
    """**Limpar seria pior que declarar.**

    O ensaio achou `: WILSON ROCHEDO DE OLIVEIRA` — 11 em 3.992 —, e os arquivos
    do E-Ofício têm 19 iguais: é sujeira do acervo, e não defeito nosso. Tirar
    «: » parece seguro; cortar o começo de «1ª SUEZ ENERGIA RENOVÁVEL S/A»
    estragaria a razão social. O nome identifica a pessoa na pesquisa nacional
    de bens.
    """
    m = _matricula(s, "1")
    _parte(s, m, ": WILSON ROCHEDO DE OLIVEIRA")
    _parte(s, m, "1ª SUEZ ENERGIA RENOVÁVEL S/A")
    _parte(s, m, "MARIA LIMPA")
    with _con(s) as con:
        r = OCG.conferir_indicador_pessoal(con)
        xml = OCG.gerar_indicador_pessoal(con, "000000")
    assert r["quantos_nomes_estranhos"] == 2
    assert ": WILSON ROCHEDO DE OLIVEIRA" in r["nomes_estranhos"]
    # **e o XML os leva INTEIROS** — o sistema declara, não conserta
    assert "<NOME>: WILSON ROCHEDO DE OLIVEIRA</NOME>" in xml
    assert "<NOME>1ª SUEZ ENERGIA RENOVÁVEL S/A</NOME>" in xml

    html = " ".join(s["c"].get("/registro-imoveis/onr/next-cloud-sas")
                    .get_data(as_text=True).split())
    assert "começam com sinal em vez de letra" in html
    assert "não os limpa" in html


def test_AS_DUAS_TELAS_preenchem_DTVENDA(s):
    """**O guarda que impede as duas divergirem de novo.**

    São duas telas que geram o mesmo XML: a exportação do mês (`ri_onr`) e a
    carga completa (`onr_carga`). A mensal mandava `DTVENDA` **vazia desde que
    nasceu**, e ninguém viu — porque o defeito só aparece do lado do ONR.

    `ri_onr.gerar_indicador_pessoal` sempre aceitou `data_venda`; era quem a
    chama que não passava. **A peça estava pronta e faltava um argumento dela**
    — a família de defeito mais repetida deste projeto, numa forma nova.
    """
    m = _matricula(s, "1", abertura="1977-03-16")
    _parte(s, m, "JOÃO TEIXEIRA DA SILVA")

    # a carga completa
    with _con(s) as con:
        assert "<DTVENDA>16031977</DTVENDA>" in OCG.gerar_indicador_pessoal(
            con, "000000")

    # e a exportação do mês, pela tela
    html = s["c"].get("/registro-imoveis/onr?inicio=1977-01-01&fim=1977-12-31")
    r = s["c"].post("/registro-imoveis/onr?inicio=1977-01-01&fim=1977-12-31",
                    data={"csrf_token": _token(html.get_data(as_text=True)),
                          "tipo": "PESSOAL"})
    corpo = r.get_data(as_text=True)
    assert "<DTREGAVERB>16031977</DTREGAVERB>" in corpo
    assert "<DTVENDA>16031977</DTVENDA>" in corpo, (
        "a exportação mensal também tem de preencher DTVENDA")
    assert "<DTVENDA></DTVENDA>" not in corpo


# ============================================ o formulário de adesão
#
# **ELE É UMA DECLARAÇÃO ASSINADA, E NÃO UM CADASTRO** — e quem achou isso foi
# a pergunta do oficial em 07/09/2026, «qual a necessidade do formulário de
# adesão?». Eu o havia recomendado sem abrir o arquivo.


def test_o_quadro_traz_o_que_o_formulario_pede(s):
    m = _matricula(s, "4013", livro="2S")
    _matricula(s, "5")
    raiz = _disco(s, ("00000004", "00004013.0001"))
    with _con(s) as con:
        f = OCG.para_o_formulario(con, raiz, cns="000000")
    assert f["cns"] == "000000"
    assert f["total_de_matriculas"] == 2
    assert f["ultima_matricula"]["numero"] == "4013", (
        "a última é a de maior NÚMERO — em ordem de texto, 5 viria depois")
    assert f["espaco"]["bytes"] > 0
    assert "Cartório Gestão" in f["sistema"]
    assert m


def test_a_ultima_matricula_ordena_por_NUMERO_e_nao_por_TEXTO(s):
    """`999` viria depois de `4013` em ordem alfabética, e o formulário
    receberia a matrícula errada."""
    _matricula(s, "999")
    _matricula(s, "4013")
    with _con(s) as con:
        assert OCG.ultima_matricula(con)["numero"] == "4013"


def test_a_conta_do_google_NAO_e_o_email_de_contato(s):
    """**Correção do oficial em 07/09/2026**: «esse é email do google, nao
    oficial da serventia para contato geral».

    Eu tinha achado o mesmo endereço em duas colunas do acervo e escrito que
    «as três fontes batem» — como se a coincidência provasse que é o e-mail da
    casa. Duas colunas com o mesmo valor são uma medição; **o que elas
    significam não se deduz de elas concordarem.**
    """
    _matricula(s, "1")
    raiz = _disco(s, ("00000000", "00000001.0001"))
    with _con(s) as con:
        f = OCG.para_o_formulario(con, raiz)
    assert "Google Cloud" in f["conta_google_e_para"]
    assert "NÃO é o e-mail de contato" in f["conta_google_e_para"]

    html = " ".join(s["c"].get("/registro-imoveis/onr/next-cloud-sas")
                    .get_data(as_text=True).split())
    assert "não é o e-mail de contato do cartório" in html
    assert "a senha dela não entra neste sistema" in html


def test_o_que_SO_O_OFICIAL_SABE_fica_dito_e_nao_adivinhado(s):
    """IP do servidor e telefone do técnico não se inventam: o suporte do ONR
    liga para esse número."""
    _matricula(s, "1")
    raiz = _disco(s, ("00000000", "00000001.0001"))
    with _con(s) as con:
        f = OCG.para_o_formulario(con, raiz)
    for esperado in ("IP", "técnico", "link"):
        assert esperado in f["so_o_oficial_sabe"]

    html = " ".join(s["c"].get("/registro-imoveis/onr/next-cloud-sas")
                    .get_data(as_text=True).split())
    assert "O que só você tem" in html
    assert "firewall" in html


def test_a_tela_avisa_que_o_formulario_e_DECLARACAO_antes_de_qualquer_numero(s):
    """A ordem estava errada no roteiro: assinar vinha antes de decidir."""
    _matricula(s, "1")
    html = " ".join(s["c"].get("/registro-imoveis/onr/next-cloud-sas")
                    .get_data(as_text=True).split())
    assert "não é cadastro: é uma declaração assinada" in html
    assert "antes de assinalar qualquer uma" in html


# ============================================ a ficha nova sem digitalização
#
# «se quiser, meu próximo passo é a tela avisar quando uma matrícula nova passa
#  dos dias sem digitalização» — e o oficial: **«faça isso»**, 07/09/2026.


def test_ficha_nova_atrasada_aparece_com_os_dias(s):
    m = _matricula(s, "4013", abertura="2026-07-31")
    raiz = _disco(s, ("00000000", "00000001.0001"))
    with _con(s) as con:
        r = OCG.sem_digitalizacao(con, raiz, hoje="2026-09-07", dias=30)
    assert [x["id"] for x in r] == [m]
    assert r[0]["dias"] == 38


def test_ficha_dentro_do_prazo_NAO_aparece(s):
    _matricula(s, "4014", abertura="2026-09-01")
    raiz = _disco(s, ("00000000", "00000001.0001"))
    with _con(s) as con:
        assert OCG.sem_digitalizacao(con, raiz, hoje="2026-09-07", dias=30) == []


def test_O_ACERVO_NAO_VIRA_ATRASO(s):
    """**A regra da casa pela oitava vez.** As 55 fichas de 1977 sem imagem não
    são atraso de ninguém — e pô-las aqui faria a lista nascer com cinquenta e
    cinco linhas que o balcão não tem como zerar."""
    _matricula(s, "8", abertura="1977-03-16")
    raiz = _disco(s, ("00000000", "00000001.0001"))
    with _con(s) as con:
        assert OCG.sem_digitalizacao(con, raiz, hoje="2026-09-07",
                                     dias=30, meses=12) == []


def test_A_REGUA_E_A_DATA_E_NAO_A_ORIGEM(s):
    """**Defeito meu, na primeira versão desta função.**

    Eu filtrava `origem <> 'EOFICIO'`, achando que «veio do acervo» quisesse
    dizer «é antiga». Medido na produção: das cinco matrículas de 2026 sem
    imagem, **três têm `origem = 'EOFICIO'`** — o E-Ofício foi o sistema desta
    casa até agosto de 2026. O filtro esconderia três dos cinco casos reais.

    `origem` diz **de onde a linha veio**; `data_abertura` diz **quando o ato
    aconteceu** — e a pergunta aqui é a segunda.
    """
    con = sqlite3.connect(s["banco"])
    cur = con.execute(
        "INSERT INTO ri_matriculas (numero, livro, data_abertura, origem, "
        "criado_em) VALUES (?,?,?,?,?)",
        ("4012", "2", "2026-07-31", "EOFICIO", "2026-09-04"))
    con.commit()
    veio_do_acervo = int(cur.lastrowid)
    con.close()
    raiz = _disco(s, ("00000000", "00000001.0001"))
    with _con(s) as con:
        r = OCG.sem_digitalizacao(con, raiz, hoje="2026-09-07", dias=30)
    assert [x["id"] for x in r] == [veio_do_acervo], (
        "matrícula de 2026 marcada EOFICIO é ficha NOVA, e tem de entrar")


def test_a_ficha_digitalizada_SAI_DA_LISTA_sozinha(s):
    """É uma lente: mede na hora, e nada grava marca. Marca que volta é pior
    que marca que nunca existiu."""
    _matricula(s, "4013", abertura="2026-07-31")
    raiz = _disco(s, ("00000004", "00004013.0001"))
    with _con(s) as con:
        assert OCG.sem_digitalizacao(con, raiz, hoje="2026-09-07", dias=30) == []


def test_a_tela_das_fichas_MOSTRA_as_atrasadas(s):
    """Função pronta que nenhuma tela chama é o defeito mais repetido daqui."""
    _matricula(s, "4013", abertura="2026-07-31")
    raiz = _disco(s, ("00000000", "00000001.0001"))
    con = sqlite3.connect(s["banco"])
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                ("ri_imagens_raiz", str(raiz)))
    con.commit()
    con.close()
    html = " ".join(s["c"].get("/registro-imoveis/imagens/do-disco")
                    .get_data(as_text=True).split())
    assert "Fichas novas sem digitalização" in html
    assert "não são acervo" in html.lower() or "Não são acervo" in html
    assert "cresce" in html
