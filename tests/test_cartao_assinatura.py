"""Quem assina o cartão de autógrafo — o relato #27 do oficial.

A FRASE DELE, inteira:

    «a ficha de assinatura do reconhecimento de firma nao vai assinada pelo
     oficial. A ficha de assinatura só vai assinada pelo cliente, precisa de
     mais espaço livre para desenvolver a assinatura, algo como dois campos em
     aberto para assinatura livre e um campo para rubrica»

EU LI ISSO AO CONTRARIO, E ESTE ARQUIVO GUARDAVA O ERRO.
    Peguei o titulo — «nao vai assinada pelo oficial» — como queixa de FALTA,
    e acrescentei a assinatura do delegatario ao cartao. **A segunda frase, que
    estava citada aqui em cima, dizia o contrario**: «só vai assinada pelo
    cliente».

    O oficial teve de me corrigir em 31/08/2026, com todas as letras: «voce
    entendeu errado, o oficial nao assina a ficha de assinatura, so o cliente».

    A licao nao e sobre ambiguidade: a frase que decidia estava no arquivo,
    citada por mim, duas linhas acima da conclusao errada. **Eu escolhi a
    leitura que dava trabalho de programar, em vez da que o texto dizia.**

POR QUE A CASA NAO ASSINA ESTE PAPEL
    O cartao de autografo e o padrao de assinatura DA PESSOA — o papel contra
    o qual a firma de um documento e comparada depois. Quem assina um padrao
    de comparacao e quem esta sendo padronizado; a serventia COLHE, e nao
    afirma. A fe do delegatario aparece no RECONHECIMENTO, que e outro ato e
    outro papel.

E EM 21/10/2026 O PREPOSTO QUE CONFERIU VOLTOU — SO ELE.
    O CN-MA art. 864, § 1º, VI, pede na ficha o «nome, assinatura e carimbo
    do tabeliao ou do seu substituto ou outro preposto designado que
    verificou a regularidade do preenchimento». Perguntado, o oficial
    respondeu «9 b» (LH13): «Preenchimento conferido por: NOME — funcao», com
    linha de assinatura e espaco para o carimbo, do escrevente que ABRIU o
    cartao (gravado nele na abertura). O cliente continua assinando so os
    autografos e o fecho dele, e o delegatario continua fora.

O QUE O RELATO PEDIA DE VERDADE JA ESTAVA FEITO, e continua:
    Os tres campos — «Assinatura por extenso», «Assinatura abreviada» e
    «Rubrica» — que sao exatamente «dois campos em aberto para assinatura
    livre e um campo para rubrica», cada um com espaco em branco antes da
    linha. E o cartao sai em `.odt` para imprimir.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


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


def _cartao(con, *, nome="MARIA DAS DORES DA SILVA", numero=4063,
            conferente_nome=None, conferente_funcao=None):
    cur = con.execute(
        """INSERT INTO nt_cartoes (numero, nome, nome_norm, documento,
               origem, criado_em, conferente_nome, conferente_funcao)
           VALUES (?,?,?, '00000000191', 'MANUAL', '2026-08-29T09:00', ?, ?)""",
        (numero, nome, nome.lower(), conferente_nome, conferente_funcao))
    return int(cur.lastrowid)


def _texto_do_odt(dados: bytes) -> str:
    """O texto de dentro do `.odt`, que é um zip com um `content.xml`.

    O teste lê o ARQUIVO QUE SAI, e não o HTML de antes de gerar: é o papel
    que a serventia entrega, e é nele que a assinatura tem de estar."""
    with zipfile.ZipFile(BytesIO(dados)) as z:
        bruto = z.read("content.xml").decode("utf-8")
    return " ".join(re.sub(r"<[^>]+>", " ", bruto).split())


def _ficha(casa, cartao_id):
    r = casa["cliente"].get(f"/notas/cartoes/{cartao_id}/ficha")
    assert r.status_code == 200, "a ficha do cartão não saiu"
    return _texto_do_odt(r.data)


def _paragrafos_do_odt(dados: bytes) -> list[str]:
    """Um item por parágrafo do `.odt`, **inclusive os vazios**.

    `_texto_do_odt` colapsa o branco: ele responde «o texto está lá?». Para
    medir ESPAÇO ele não serve — parágrafo vazio some na colagem, e foi assim
    que o teste de baixo nasceu vermelho com o conserto de pé. **O branco é o
    conteúdo que se está medindo, e por isso tem de sobreviver à leitura.**
    """
    with zipfile.ZipFile(BytesIO(dados)) as z:
        bruto = z.read("content.xml").decode("utf-8")
    pedacos = re.split(r"<text:p[^>]*/>|<text:p[^>]*>", bruto)
    return [" ".join(re.sub(r"<[^>]+>", " ", x).split()) for x in pedacos]


def _ficha_em_paragrafos(casa, cartao_id) -> list[str]:
    r = casa["cliente"].get(f"/notas/cartoes/{cartao_id}/ficha")
    assert r.status_code == 200, "a ficha do cartão não saiu"
    return _paragrafos_do_odt(r.data)


# ------------------------------------------- o que já existia


def test_os_tres_campos_de_assinatura_ja_existiam(casa):
    """«dois campos em aberto para assinatura livre e um campo para rubrica» —
    e eram exatamente esses três."""
    con = _con(casa)
    with con:
        cid = _cartao(con)
    texto = _ficha(casa, cid)
    assert "Assinatura por extenso" in texto
    assert "Assinatura abreviada" in texto
    assert "Rubrica" in texto


def test_o_cartao_sai_em_arquivo_para_imprimir(casa):
    """Relato #8: «o selo é emitido, mas o sistema não gera o cartão para ser
    impresso e assinado pelo usuário». Ele gera — e este teste guarda isso."""
    con = _con(casa)
    with con:
        cid = _cartao(con)
    r = casa["cliente"].get(f"/notas/cartoes/{cid}/ficha")
    assert r.mimetype == "application/vnd.oasis.opendocument.text"
    assert "CARTÃO DE AUTÓGRAFO" in _texto_do_odt(r.data)


# ------------------------------------------- o que faltava


def test_o_delegatario_nao_assina_a_ficha_so_o_cliente_e_quem_conferiu(casa):
    """«o oficial nao assina a ficha de assinatura, so o cliente» — 31/08/2026.

    E a assinatura do ESCREVENTE saiu junto, pela mesma frase. Ela estava no
    papel antes do meu engano, e nao foi ele que a pos — mas «so o cliente»
    alcanca as duas.

    ESTE TESTE SE CHAMAVA «so o cliente assina a ficha» (`test_so_o_cliente_
    assina_a_ficha`), e mudou em 21/10/2026: o oficial respondeu «9 b» à
    pergunta do CN-MA art. 864, § 1º, VI (LH13), e o PREPOSTO QUE ABRIU O
    CARTAO assina a linha «Preenchimento conferido por». O delegatario e a
    substituta continuam fora — a conta abaixo e a mesma de antes.
    """
    casa["db"].set_settings({"ri_registrador": "MARIO EXEMPLO DOS SANTOS",
                             "ri_substituta": "BEATRIZ EXEMPLO DE SOUZA"})
    con = _con(casa)
    with con:
        cid = _cartao(con, nome="MARIA DAS DORES DA SILVA",
                      conferente_nome="CARLA EXEMPLO",
                      conferente_funcao="Escrevente Autorizada")
    texto = _ficha(casa, cid)

    assert "MARIA DAS DORES DA SILVA" in texto
    assert "o titular do cartão" in texto
    assert ("Preenchimento conferido por: CARLA EXEMPLO — Escrevente Autorizada"
            in texto)
    # NEM O TITULAR NEM A SUBSTITUTA aparecem embaixo de uma linha de assinar.
    #
    # TESTE VELHO, ATUALIZADO EM 14/10/2026: a conta é do CORPO da ficha, e
    # não do cabeçalho. O cabeçalho da serventia («<unidade> / <título>:
    # <titular> / CNS») está no cartão desde a 3.6.59 (01/09) e identifica a
    # casa, como em todo papel dela — não é assinatura. Ele não acusava antes
    # porque o titular saía de `serventia_titular`; na 3.6.286 (06/10/2026,
    # migração B0) `serventia.ALIASES_LEGADOS` passou a lê-lo de
    # `ri_registrador`, que é o nome que este teste grava.
    corpo = texto.split("CARTÃO DE AUTÓGRAFO", 1)[1]
    assert "MARIO EXEMPLO DOS SANTOS" not in corpo
    assert "BEATRIZ EXEMPLO DE SOUZA" not in texto


def test_ha_duas_linhas_de_assinar_no_fecho_e_nao_tres(casa):
    """Tres linhas no fecho eram o cliente, o escrevente e o oficial.

    A conta e do FECHO, e nao da folha: os tres campos de autografo — por
    extenso, abreviada e rubrica — tambem tem linha, e esses ficam.

    ERA «UMA LINHA, E NAO TRES» ATE 21/10/2026 (`test_ha_uma_linha_de_assinar_
    no_fecho_e_nao_tres`). Com a resposta «9 b» do oficial (LH13), depois da
    do titular vem UMA linha, a do preposto que conferiu o preenchimento
    (CN-MA art. 864, § 1º, VI) — e a do oficial continua fora.
    """
    con = _con(casa)
    with con:
        cid = _cartao(con, nome="MARIA DAS DORES DA SILVA",
                      conferente_nome="CARLA EXEMPLO",
                      conferente_funcao="Escrevente Autorizada")
    texto = _ficha(casa, cid)
    titular, depois = texto.split("o titular do cartão", 1)
    assert len(re.findall(r"_{27,}", titular.rsplit("Autógrafos", 1)[1])) == 10, (
        "nove linhas de autógrafo e a do titular")
    assert len(re.findall(r"_{27,}", depois)) == 1, (
        "depois do titular, só a linha de quem conferiu o preenchimento")
    assert depois.strip().endswith("assinatura e carimbo de quem conferiu o preenchimento")


def test_a_serventia_nao_e_nomeada_como_quem_assina(casa):
    """Sem esta guarda, alguem devolve a assinatura da casa daqui a um ano —
    e o papel volta a afirmar, nesta folha, o que ele so afirma na seguinte.

    **A GUARDA ESTAVA DESLIGADA DESDE O LF06A** (19/10/2026): o texto do cartão
    saiu do `notas_web.py` para `modelos_padrao/notas/NOTAS_CARTAO_FICHA.txt`,
    a âncora «CARTÃO DE AUTÓGRAFO» sumiu do módulo, e o teste estourava em
    `IndexError` antes de conferir qualquer coisa. Achado pelo LF06D. A
    assinatura da casa só voltaria pela ROTA que monta o cartão — o papel do
    catálogo não chama função —, e é ela que se confere, até a rota seguinte."""
    fonte = (RAIZ / "notas_web.py").read_text(encoding="utf-8")
    trecho = fonte.split("def notas_cartao_ficha(", 1)[1].split("@app.route", 1)[0]
    assert "NOTAS_CARTAO_FICHA" in trecho, "o trecho não é mais a rota do cartão"
    for proibido in ("_quem_responde_pela_serventia",
                     "_titulo_de_quem_responde"):
        assert proibido not in trecho, (
            f"{proibido} voltou ao cartão de autógrafo — o oficial não assina "
            f"a ficha de assinatura")


def test_cada_autografo_tem_espaco_para_DESENVOLVER_a_assinatura(casa):
    """A OUTRA METADE DO #27, e ela ficou por fazer até 31/08/2026.

    Os três campos já existiam quando o oficial escreveu o relato — logo o
    «precisa de MAIS espaço livre para desenvolver a assinatura» era queixa
    sobre o espaço que havia, e não pedido de campo novo. Eu tinha lido as
    duas metades como uma só, e dado a primeira por resposta à segunda.

    Assinatura apertada num papel que serve de PADRÃO DE COMPARAÇÃO estraga
    justamente aquilo para que o papel existe: quem confere por semelhança
    compara com a forma natural, e a forma natural não sai em meia linha.
    """
    con = _con(casa)
    with con:
        cid = _cartao(con)
    paragrafos = _ficha_em_paragrafos(casa, cid)
    # Conta-se o que sai no PAPEL — os parágrafos vazios entre o rótulo e a
    # linha de assinar —, e não a constante do código: a constante prova que
    # eu escrevi cinco; o papel prova que cinco chegaram lá.
    for rotulo in ("Assinatura por extenso", "Assinatura abreviada",
                   "Rubrica"):
        onde = [i for i, x in enumerate(paragrafos) if rotulo in x]
        assert onde, f"«{rotulo}» não está na ficha"
        i = onde[0]
        linha = next(j for j in range(i, len(paragrafos))
                     if "____" in paragrafos[j])
        brancos = sum(1 for x in paragrafos[i + 1:linha] if not x)
        assert brancos >= 5, (
            f"«{rotulo}» tem {brancos} linhas de espaço antes da linha de "
            f"assinar; o relato #27 pediu mais espaço para desenvolver a "
            f"assinatura")


def test_a_ficha_nao_cresce_sem_ninguem_ver(casa):
    """UM TETO DE CRESCIMENTO — e não uma promessa de página.

    **Este teste se chamava «a ficha continua cabendo numa folha», e o nome
    afirmava o que ele não mede**: ele conta parágrafos, e parágrafo não é
    folha. Era carimbo que mente, no meu próprio teste.

    Medido de verdade em 31/08/2026, convertendo com o LibreOffice desta
    máquina:

        0 linhas em branco por autógrafo -> 2 páginas
        3 linhas em branco por autógrafo -> 2 páginas
        5 linhas em branco por autógrafo -> 2 páginas

    **A ficha já eram duas páginas, e o espaço não custou folha nenhuma.** Ela
    não cabe numa por causa da tabela de qualificação, dos quadros de foto e
    digital e do fecho — e pôr o cartão numa folha só é decisão de layout do
    oficial, não consequência deste conserto.

    O que este teto faz é pegar quem triplicar o espaço sem olhar o resto: de
    duas páginas para três, aí sim, quem arquiva perde a do meio.
    """
    con = _con(casa)
    with con:
        cid = _cartao(con)
    linhas = len(_ficha_em_paragrafos(casa, cid))
    assert linhas <= 90, (
        f"a ficha está com {linhas} parágrafos — mediu-se 75 em 31/08/2026, "
        f"e este teto existe para o crescimento não passar calado")
