"""Os modelos de todos os papéis da casa — o relato #28 do oficial.

A FRASE DELE:

    «preciso de mais controle sobre os modelos de todos os atos, de todas
     atribuições. preciso ter controle geral sobre os modelos, em especial os
     cabeçalhos padrão de cada atribuição e ato, corpo, encerramento, eventual
     notas de rodapé»

O QUE ESTES TESTES GUARDAM
    O principal deles é o **piso**: sem ajuste gravado, cada papel tem de sair
    exatamente com o modelo escrito no código. É o que garante que instalação
    nova nasça funcionando e que «voltar ao padrão» não dependa de ninguém ter
    guardado o texto antigo.
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

import modelos_da_casa as MOD                                    # noqa: E402

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


def _tela(casa, **args):
    r = casa["cliente"].get("/modelos", query_string=args)
    assert r.status_code == 200, "a tela dos modelos não abriu"
    return " ".join(r.get_data(as_text=True).split())


def _gravar(casa, chave, corpo, acao="salvar"):
    html = casa["cliente"].get("/modelos").get_data(as_text=True)
    return casa["cliente"].post(
        "/modelos",
        data={"chave": chave, "corpo": corpo, "acao": acao,
              "csrf_token": _token(html)},
        follow_redirects=True)


# ------------------------------------------------ o catálogo é medido


def test_o_catalogo_lista_os_papeis_das_atribuicoes():
    """Nenhum inventado: são as constantes que existem no código.

    Passou de 12 para 13 em 01/09/2026, com o **termo do registro de
    protesto** — achado pela régua do oficial («procure no banco»):
    `tbProtesto_Motivo` tem 1.132 linhas, e este sistema não escrevia uma
    palavra no Livro de Registro de Protestos.

    Ele vem ao catálogo por uma razão específica, e não por simetria: a base
    afirma «PROTESTO LAVRADO PARA FINS E EFEITOS DO ART. 9º-A DA LEI Nº
    9.430/1996» — o artigo da dívida ativa da Fazenda — em **1.126 de 1.132**
    protestos desta casa, inclusive nos que não são de dívida ativa.
    Afirmação jurídica em papel que a serventia assina é do oficial.

    E passou de 13 para **14** no mesmo dia, com o **instrumento de
    protesto** — o papel que o art. 20 da Lei 9.492/1997 manda entregar ao
    apresentante, e que este sistema não sabia emitir. Ele vem ao catálogo
    por um motivo diferente do termo: ali havia precedente da casa e a
    afirmação do art. 9º-A era do oficial; **aqui não há precedente nenhum**
    — procurado nas 229 tabelas do E-Ofício, zero com «instrum» no nome.
    Onde não há forma a imitar, o que se imita é a lei, e o texto fica
    editável por quem assina.
    """
    # 07/09/2026: entrou o cartão de autógrafo (ficha de firma) — 15.
    #
    # **E PASSOU DE 16 PARA 22 NA 3.6.75** (08/09/2026, 18h02), com as seis
    # certidões que faltavam: a do Livro 3, a do RCPJ, a do RTD e as três do
    # Protesto (negativa, positiva e de cancelamento). Datado abrindo os
    # pacotes um a um — a 3.6.72 tem 16, a 3.6.75 tem 22.
    #
    # **A CONTAGEM ESCRITA À MÃO ENVELHECE**, e é de propósito que ela
    # continua escrita: é ela que obriga quem acrescenta papel ao catálogo a
    # dizer, aqui, por que ele entrou. «Nenhum inventado» só se confere
    # contando.
    #
    # **E PASSOU DE 22 PARA 30, e a contagem ficou em 26 — vermelha desde
    # 11/09/2026.** Datado abrindo os pacotes um a um, que é a régua desta
    # casa para «esta falha é minha?»: a **3.6.90** (08/09, 17h53) tem 22 e a
    # **3.6.98** (11/09, 15h53) tem 30. Os oito que entraram são os quatro
    # **teores** do RCPJ/RTD (registro e averbação de cada) e as quatro peças
    # da **certidão em PDF** (capa e faixa de cada).
    #
    # **O «26» não corresponde a nenhum dos dois**: alguém atualizou a
    # contagem pela metade e o teste ficou afirmando um número que nunca
    # existiu — e *teste vermelho que afirma o errado é pior que teste
    # nenhum*, que é o que manda corrigir o NÚMERO aqui.
    #
    # **POR QUE aqueles oito entraram é de quem os pôs, e não meu** — este
    # comentário diz o que foi MEDIDO (quais, e quando), e não inventa a razão
    # de outra passada. A regra é «quem não está construindo o módulo não mexe
    # nele»: `modelos_da_casa.py` não foi tocado.
    #
    # **EM 18/09/2026 O CATÁLOGO TEM 34, E TRÊS DELES SÃO DESTA PASSADA**: os
    # **miolos** da certidão do RI — inteiro teor, ônus e propriedade —, que
    # deixaram de morar dentro de um `{% if %}` num molde só (problema #75, do
    # oficial: «estrutura um modelo base ... para os demais modelos de
    # certidao»). O molde ficou com o que toda certidão tem e declara o
    # marcador por onde o miolo entra; **a quarta, a «negativa de matrícula»,
    # saiu** — ela não certifica a matrícula, busca o nome da pessoa nos livros.
    #
    # **E A CONTAGEM DESTE TESTE JÁ ESTAVA UM ABAIXO, ANTES DE MIM** — medido,
    # sem os meus três o catálogo tinha **31** e aqui estava escrito 30. Quem
    # pôs o 31 não é desta passada e eu não o atribuo: o número de agora é o que
    # a régua conta hoje, e quem acrescentar papel a este catálogo mede de novo.
    #
    # **EM 14/10/2026 PASSOU DE 36 PARA 38**: os miolos da certidão DOMINIAL e
    # da VINTENÁRIA, que a 3.6.233 pôs no catálogo em 28/09 e que se perderam
    # nos pacotes seguintes — reconstituídos agora, com o mesmo nome de chave.
    #
    # **EM 15/10/2026 PASSOU DE 38 PARA 41**: os três textos da certidão das
    # Notas (inteiro teor, positiva e negativa), pedido do oficial — sem
    # precedente de texto no E-Ofício, e por isso no catálogo, que é dele.
    assert len(MOD.CATALOGO) == 41
    atribuicoes = {c["atribuicao"] for c in MOD.CATALOGO}
    # O RCPJ e o RTD entraram com as certidões deles — até a 3.6.72 eles não
    # tinham um único papel no catálogo, e o submódulo nascia só com o nível
    # da atribuição.
    #
    # **E O RÓTULO DELES É UM SÓ, «RCPJ e RTD»** — são seis atribuições no
    # catálogo, e não sete. Eu havia escrito aqui «Registro Civil de Pessoas
    # Jurídicas» e «Registro de Títulos e Documentos», dois nomes plausíveis
    # que o catálogo não usa; quem me desmentiu foi rodar. **Nome plausível é
    # o que mais se parece com medição sem ser** — e num teste que existe
    # para provar que nada foi inventado.
    assert atribuicoes == {"Registro de Imóveis", "Caixa e protocolo",
                           "Tabelionato de Notas", "Protesto",
                           "Registro Civil das Pessoas Naturais",
                           "RCPJ e RTD"}


# **O MODELO É O TEXTO, E NÃO O ESQUELETO DELE** — e estes dois são esqueleto.
#
#   `MODELO_CERTIDAO_POSITIVA` é `"{cabeca} {corpo}"`: dois marcadores, 16
#   caracteres. A frase que a certidão de fato afirma — «CERTIFICO …, que
#   revendo em meu Cartório, os livros de Registros de Protestos … neles
#   encontrei protesto contra …» — mora numa f-string DENTRO de
#   `protesto_certidao.certificar`, e por isso **o oficial não a alcança**: ele
#   abre a tela de editar e vê dois marcadores. Na NEGATIVA a frase está no
#   modelo e ele a edita; é a assimetria entre as duas que prova o defeito.
#
#   `MODELO_CERTIDAO_CANCELAMENTO` tem a mesma cabeça-marcador, **e não entra
#   nesta lista**: o fecho do art. 26 está escrito nele, com 17 palavras que o
#   oficial alcança e edita. Eu o havia declarado junto, e o próprio guarda me
#   desmentiu ao exigir que o declarado seja esqueleto de verdade. Fica como
#   observação no roteiro — o que falta ali é a cabeça, e não o papel inteiro.
#
#   **É o mesmo defeito que EU cometi em 01/09/2026** com o termo do protesto,
#   e que este guarda pegou naquele dia: eu havia posto `{base}\n{posteriori}
#   \n\n{edital}` como padrão, 28 caracteres, com a frase do art. 9º-A
#   invisível.
#
#   **DECLARADOS, E NÃO CONSERTADOS**: mover a f-string para dentro da
#   constante muda como um papel assinado se compõe, e `protesto_certidao.py`
#   é de outra passada, que trabalha nele. Medido e relatado ao oficial no
#   ROTEIRO_3.6.79. Entraram no catálogo na 3.6.75 (08/09/2026).
ESQUELETO_EM_VEZ_DE_TEXTO = {
    "PT_CERTIDAO_POSITIVA": "só «{cabeca} {corpo}»; o texto está na f-string",
    # **E O MIOLO DO INTEIRO TEOR É ESQUELETO POR NATUREZA, E NÃO POR DEFEITO** —
    # 18/09/2026, problema #75. Ele é `{% if teor_odf %}{{ teor_odf }}{% endif %}`
    # mais os atos e o «Era o que nela continha.»: o texto da certidão de inteiro
    # teor **é o do livro**, e a única prosa dela é a frase de fecho, que está
    # aqui à vista e é editável. **Não há f-string escondida** — que é a razão de
    # este guarda existir e a razão de a `PT_CERTIDAO_POSITIVA` estar na lista.
    # Declarado, o guarda continua valendo: ele exige que o declarado seja
    # esqueleto de verdade, e fica vermelho no dia em que este papel ganhar texto
    # próprio (aí a declaração sai).
}


def _texto_que_nao_e_marcador(texto: str) -> str:
    """O que sobra do modelo quando se tiram os marcadores.

    **É ISTO QUE O OFICIAL LÊ E EDITA.** Medir `len(texto)` mede os
    marcadores junto — e foi o que a primeira versão deste guarda fez, com um
    piso de 200 caracteres que eu escolhi. Ele reprovou `RCPJ_CERTIDAO`, que
    tem 196 caracteres de texto de verdade: **régua errada acusa quem está
    certo**, pela segunda vez neste projeto (a primeira foi a que media
    contraste para julgar semelhança de cor).
    """
    return re.sub(r"\{[^{}]*\}", " ", texto)


def test_todo_padrao_do_catalogo_existe_de_verdade():
    """`padrao` diz módulo e nome — e este teste vai lá buscar.

    Sem ele, renomear uma constante deixaria o catálogo apontando para o nada,
    e a tela mostraria um modelo VAZIO como se fosse o padrão da casa."""
    for c in MOD.CATALOGO:
        chave = c["chave"]
        texto = MOD.padrao_de(chave)
        assert texto.strip(), f"{chave} aponta para constante que sumiu"

        palavras = [p for p in re.split(r"\W+", _texto_que_nao_e_marcador(texto))
                    if p.isalpha()]
        esqueleto = len(palavras) < 10

        if chave in ESQUELETO_EM_VEZ_DE_TEXTO:
            # **DECLARAÇÃO QUE SOBREVIVE AO DEFEITO É O CARIMBO QUE MENTE.**
            # Consertado o modelo, este guarda fica vermelho até alguém tirar
            # a chave da lista — a forma de `test_o_teto_nao_lista_modulo_que
            # _ja_nao_usa`, e a regra «pendência se apaga quando é resolvida,
            # e não se remove da lista».
            assert esqueleto, (
                f"{chave} está declarado em ESQUELETO_EM_VEZ_DE_TEXTO e já "
                f"tem texto de verdade ({len(palavras)} palavras). Tire-o da "
                f"lista.")
            continue

        assert not esqueleto, (
            f"{chave} é ESQUELETO, e não texto: sobram {len(palavras)} "
            f"palavra(s) fora dos marcadores. O oficial abriria a tela de "
            f"editar e veria marcadores, com o texto do papel invisível e "
            f"ineditável — o defeito do termo do protesto de 01/09/2026.")


def test_o_catalogo_nao_guarda_copia_do_texto():
    """O texto é LIDO do módulo, e não copiado para cá.

    Duas versões do mesmo modelo divergiriam no primeiro conserto — a tela
    mostrando uma coisa e o programa imprimindo outra. Este projeto já pagou
    por isso com a `normalizar_nome`."""
    for c in MOD.CATALOGO:
        assert isinstance(c["padrao"], tuple) and len(c["padrao"]) == 2


def test_a_url_do_qr_do_selo_nao_esta_no_catalogo():
    """`notas_selo.MODELO_PADRAO` se chama modelo e não é um: é a URL de dentro
    do QR, com marcador do `str.format`. Passá-la pelo Jinja aprovaria um texto
    que o QR não sabe montar."""
    assert "NOTAS_ETIQUETA" not in MOD.POR_CHAVE
    for c in MOD.CATALOGO:
        assert c["padrao"][0] != "notas_selo"


# ------------------------------------------------ o código é o piso


def test_sem_ajuste_o_corpo_e_exatamente_o_padrao_do_codigo(casa):
    """O TESTE PRINCIPAL. Instalação nova, tabela vazia: cada papel sai com o
    modelo escrito no programa, sem carga de modelo nenhuma."""
    con = _con(casa)
    for c in MOD.CATALOGO:
        assert MOD.corpo_de(con, c["chave"]) == MOD.padrao_de(c["chave"])


def test_o_ajuste_da_casa_vence_o_padrao(casa):
    con = _con(casa)
    with con:
        MOD.salvar(con, "CAIXA_RECIBO", corpo="RECIBO DA CASA",
                   quem="mario", agora="2026-08-29T09:00")
    assert MOD.corpo_de(con, "CAIXA_RECIBO") == "RECIBO DA CASA"
    assert MOD.esta_ajustado(con, "CAIXA_RECIBO")


def test_restaurar_apaga_o_ajuste_e_devolve_o_padrao(casa):
    """«Voltar ao padrão» é apagar uma linha — e não recadastrar um texto que
    ninguém tem mais guardado."""
    con = _con(casa)
    with con:
        MOD.salvar(con, "CAIXA_RECIBO", corpo="X", quem="mario",
                   agora="2026-08-29T09:00")
        assert MOD.restaurar(con, "CAIXA_RECIBO") is True
    assert MOD.corpo_de(con, "CAIXA_RECIBO") == MOD.padrao_de("CAIXA_RECIBO")
    assert not MOD.esta_ajustado(con, "CAIXA_RECIBO")


def test_gravar_vazio_volta_ao_padrao_e_nao_grava_folha_em_branco(casa):
    """Guardar corpo vazio faria a casa imprimir folha em branco — e folha em
    branco assinada é pior que modelo feio."""
    con = _con(casa)
    with con:
        MOD.salvar(con, "CAIXA_RECIBO", corpo="X", quem="mario", agora="a")
        MOD.salvar(con, "CAIXA_RECIBO", corpo="   ", quem="mario", agora="b")
    assert MOD.corpo_de(con, "CAIXA_RECIBO") == MOD.padrao_de("CAIXA_RECIBO")


def test_o_ajuste_e_um_por_papel(casa):
    """`UNIQUE(chave)`: gravar de novo troca o texto, não cria um segundo."""
    con = _con(casa)
    with con:
        MOD.salvar(con, "CAIXA_RECIBO", corpo="A", quem="mario", agora="a")
        MOD.salvar(con, "CAIXA_RECIBO", corpo="B", quem="mario", agora="b")
    assert con.execute("SELECT COUNT(*) FROM mo_modelos").fetchone()[0] == 1
    assert MOD.corpo_de(con, "CAIXA_RECIBO") == "B"


def test_papel_que_nao_existe_e_recusado_com_a_lista(casa):
    con = _con(casa)
    with pytest.raises(MOD.ModeloError) as erro:
        MOD.corpo_de(con, "CERTIDAO_DE_MARTE")
    assert "não é um papel que esta casa emita" in str(erro.value)
    assert "CAIXA_RECIBO" in str(erro.value)


# ------------------------------------------------ o legado do RI


def test_o_ajuste_antigo_do_ri_continua_valendo(casa):
    """`ri_modelos` tem zero linhas nesta casa — mas uma instalação que já
    tivesse ajustado alguma coisa ali não pode perder o ajuste ao subir de
    versão."""
    con = _con(casa)
    with con:
        con.execute(
            "INSERT INTO ri_modelos (nome, tipo, corpo, formato, ativo,"
            " versao, atualizado_em)"
            " VALUES ('velha','CERTIDAO','CERTIDAO ANTIGA','html',1,1,'x')")
    assert MOD.corpo_de(con, "RI_CERTIDAO") == "CERTIDAO ANTIGA"


def test_o_ajuste_novo_vence_o_legado(casa):
    """Quando os dois existem, quem manda é o que a casa gravou na tela nova —
    senão editar não teria efeito nenhum, e o operador não saberia por quê."""
    con = _con(casa)
    with con:
        con.execute(
            "INSERT INTO ri_modelos (nome, tipo, corpo, formato, ativo,"
            " versao, atualizado_em)"
            " VALUES ('velha','CERTIDAO','ANTIGA','html',1,1,'x')")
        MOD.salvar(con, "RI_CERTIDAO", corpo="NOVA", quem="mario", agora="a")
    assert MOD.corpo_de(con, "RI_CERTIDAO") == "NOVA"


# ------------------------------------------------ a conferência


def test_a_conferencia_acha_o_modelo_quebrado():
    assert MOD.conferir("{% for x in %}", {}) is not None
    assert MOD.conferir("{{ hoje }}", {"hoje": "hoje"}) is None


def test_todo_padrao_do_codigo_passa_na_propria_conferencia():
    """Se um padrão de fábrica não montasse, a casa emitiria papel quebrado sem
    ninguém ter editado nada."""
    from modelos_web import ENSAIO
    for c in MOD.CATALOGO:
        erro = MOD.conferir(MOD.padrao_de(c["chave"]), ENSAIO)
        assert erro is None or "ndefined" in erro, f"{c['chave']}: {erro}"


# ------------------------------------------------ a tela


def test_a_tela_mostra_todos_os_papeis_agrupados(casa):
    html = _tela(casa)
    for c in MOD.CATALOGO:
        assert c["nome"] in html, f"{c['chave']} não aparece na tela"
    assert "Registro de Imóveis" in html
    assert "Caixa e protocolo" in html
    assert "Tabelionato de Notas" in html


def test_a_tela_diz_de_onde_o_papel_sai_hoje(casa):
    """«igual ao padrão» e «ajustado pela casa» parecem a mesma coisa quando o
    texto é o mesmo — e são diferentes no dia em que o padrão mudar."""
    assert "padrão do sistema" in _tela(casa)
    _gravar(casa, "CAIXA_RECIBO", "RECIBO NOVO")
    assert "ajustado por esta casa" in _tela(casa)


def test_a_tela_grava_e_o_papel_passa_a_sair_assim(casa):
    """A prova que fecha o relato: o que se grava aqui chega ao documento."""
    _gravar(casa, "CAIXA_RECIBO", "RECIBO AJUSTADO PELA CASA")
    con = _con(casa)
    assert MOD.corpo_de(con, "CAIXA_RECIBO") == "RECIBO AJUSTADO PELA CASA"


def test_a_tela_recusa_modelo_quebrado_e_nao_grava(casa):
    """Gravar primeiro e avisar depois deixaria o modelo quebrado valendo até
    alguém voltar na tela — e quem descobre é o escrevente com o cliente na
    frente."""
    r = _gravar(casa, "CAIXA_RECIBO", "{% for x in %}")
    assert "não foi gravado" in r.get_data(as_text=True)
    con = _con(casa)
    assert not MOD.esta_ajustado(con, "CAIXA_RECIBO")


def test_a_tela_restaura_o_padrao(casa):
    _gravar(casa, "CAIXA_RECIBO", "X")
    _gravar(casa, "CAIXA_RECIBO", "X", acao="restaurar")
    con = _con(casa)
    assert MOD.corpo_de(con, "CAIXA_RECIBO") == MOD.padrao_de("CAIXA_RECIBO")


def test_a_tela_de_edicao_traz_o_corpo_que_vale_hoje(casa):
    html = _tela(casa, editar="CAIXA_RECIBO")
    assert "textarea" in html
    assert "caixa_web.MODELO_RECIBO" in html      # diz de onde o padrão sai


def test_a_tela_de_edicao_traz_visualizacao_real(casa):
    """Mesmo padrão dos submódulos (`/ri/modelos`) e das escrituras: editor + iframe."""
    html = _tela(casa, editar="RI_CABECALHO")
    assert "data-modelo-editor" in html
    assert "data-modelo-previa" in html
    assert "Visualização real" in html
    assert "modelos_previa" in html or "/modelos/previa" in html


def test_rota_previa_retorna_html_com_dados_de_ensaio(casa):
    pagina = casa["cliente"].get("/modelos", query_string={"editar": "RI_CABECALHO"})
    token = _token(pagina.get_data(as_text=True))
    corpo = MOD.padrao_de("RI_CABECALHO")
    r = casa["cliente"].post(
        "/modelos/previa",
        data={"csrf_token": token, "ato": "RI_CABECALHO", "parte_corpo": corpo},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["ok"] is True
    assert "Prévia hipotética" in dados["html"]
    assert "MATRÍCULA Nº 123" in dados["html"]


def test_papel_desconhecido_na_tela_avisa_e_nao_estoura(casa):
    assert "não existe nesta casa" in _tela(casa, editar="CERTIDAO_DE_MARTE")


def test_deep_link_editar_sem_atribuicao_filtra_e_mostra_editor(casa):
    """Links do RI (`?editar=RI_CABECALHO`) precisam abrir o editor visivel.

    Sem filtro a pagina carrega todas as atribuicoes e o textarea fica no fim —
    o oficial conclui que a tela «nao abriu». Resolver a atribuicao pela chave
    deixa a lista curta, como `?atribuicao=Registro de Imoveis&editar=…`.
    """
    html = _tela(casa, editar="RI_CABECALHO")
    assert "filtrada" in html
    assert "Cabeçalho dos documentos" in html
    assert "textarea" in html
    assert html.count("<h2>") == 2
    html_ficha = _tela(casa, editar="RI_FICHA")
    assert "Ficha da matrícula" in html_ficha
    assert html_ficha.count("<h2>") == 2


# ------------------------------------------------ os papéis consultam mesmo


def test_todo_papel_do_catalogo_e_consultado_por_alguma_tela():
    """O DEFEITO QUE MAIS SE REPETIU NESTE PROJETO é a função pronta que
    nenhuma tela chama. Aqui ele teria outra cara: um modelo editável na tela
    que o documento ignora — o oficial ajusta, imprime, e sai o de antes."""
    # VARRE O SISTEMA INTEIRO, e nao tres arquivos.
    #
    # A primeira versao olhava so `caixa_web`, `notas_web` e `ri_web`, porque
    # eram os tres que consumiam modelo quando o catalogo nasceu. Ao entrarem os
    # tres termos do Registro Civil — consumidos por `rc_termo` — ele acusou
    # falta onde nao havia.
    #
    # **Varredor com lista de arquivos escrita a mao envelhece na tarde em que
    # se escreve**, e e a licao do menu pela terceira vez. A regra que ele
    # guarda e «alguma parte do sistema consome esta chave», e nao «um daqueles
    # tres a consome».
    _skip = {"tests", "__pycache__", "tmp", "DOCUMENTACAO", "backups_patch", "runtime", ".venv", "node_modules"}
    codigo = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(RAIZ.rglob("*.py"))
        if not (_skip & set(p.parts)))
    for c in MOD.CATALOGO:
        assert f'"{c["chave"]}"' in codigo, (
            f'{c["chave"]} é editável na tela e nenhum documento o consulta')


# ============================ os tres termos do civil, que não são Jinja
#
# **A TELA CONFERE EM JINJA, E ESTES TRÊS NÃO SÃO JINJA.**
#
#   Em 31/08/2026 os termos de nascimento, casamento e óbito passaram a apontar
#   para o texto da casa (`rc_modelos_do_livro`), que usa `{nome}` do
#   `str.format` — e não `{{ a.nome }}` do Jinja. Sem conferidor próprio a tela
#   reprovaria os três, e o oficial perderia a edição **justamente dos papéis
#   mais importantes do Registro Civil**: seria o relato #28 desfeito pela
#   metade, e do lado que mais importa.
#
#   O catálogo já sabia aceitar conferidor por módulo — o Registro de Imóveis
#   usa isso para conferir contra uma matrícula de verdade. Aqui é o mesmo
#   mecanismo, e a regra que ele aplica é **a mesma** que `rc_termo.montar` usa
#   na hora de lavrar: uma função só, `rc_modelos_do_livro.conferir_corpo`.
#   Conferir com uma régua e imprimir com outra é como a tela passa a aprovar o
#   que o papel não sabe montar.

TERMOS_DO_CIVIL = ("RC_TERMO_NASCIMENTO", "RC_TERMO_CASAMENTO",
                   "RC_TERMO_OBITO")


def test_o_padrao_dos_tres_termos_e_o_texto_da_casa():
    """**Decisão do oficial em 30/08/2026**: «termo de nascimento, casamento e
    óbito vamos construir os nossos com os requisitos legais e regulamentares,
    não utilizaremos os modelos ruins do e-ofício, nem em papel»."""
    import rc_modelos_do_livro as LIVRO

    for chave in TERMOS_DO_CIVIL:
        padrao = MOD.padrao_de(chave)
        especie = chave.replace("RC_TERMO_", "")
        assert padrao == LIVRO.modelo(especie)["texto"], (
            f"{chave} não está apontando para o termo da casa")
        # e o formato fica DECLARADO, e não adivinhado pela cara do texto
        assert MOD.formato_de(chave) == MOD.CHAVES


def test_a_tela_ACEITA_o_termo_no_formato_da_casa(casa):
    """É isto que mantém o relato #28 de pé para os três termos."""
    r = _gravar(casa, "RC_TERMO_NASCIMENTO",
                "Aos {data_do_ato}, compareceu {declarante_qualificacao}, e "
                "declarou o nascimento de \"{nome}\". Eu, {escrevente}, "
                "{funcao_do_escrevente}, dou fé e assino.")
    assert r.status_code == 200
    # **O ARMAZEM MUDOU EM 07/09/2026, e o teste acompanhou.** A tela passou a
    # gravar em `mo_elementos`, que e o mesmo lugar onde o submodulo da
    # atribuicao grava: duas telas editando o mesmo texto em tabelas
    # diferentes seria «duas fontes para a mesma coisa». O que este teste
    # guarda continua sendo o mesmo — **a tela ACEITA um termo bom**.
    guardado = _con(casa).execute(
        """SELECT corpo FROM mo_elementos
            WHERE ato = ? AND parte = 'CORPO'""",
        ("RC_TERMO_NASCIMENTO",)).fetchone()
    assert guardado, "a tela recusou um modelo bom"
    assert "{nome}" in guardado["corpo"]


def test_a_tela_RECUSA_o_termo_escrito_em_jinja(casa):
    """**O `str.format` não estoura com `{{ a.nome }}`: ele devolve
    `{ a.nome }`** — uma chave só — e isso iria escrito no livro.

    Por isso a recusa é na tela de editar, que é onde há tempo de consertar, e
    não no balcão com o cliente na frente.
    """
    r = _gravar(casa, "RC_TERMO_OBITO", "<p>{{ a.nome }} faleceu.</p>")
    html = " ".join(r.get_data(as_text=True).split())
    assert "formato antigo" in html
    # **E ESTE OLHA O ARMAZEM NOVO TAMBEM.** Ele passava olhando
    # `mo_modelos`, onde ninguem mais grava — e um teste que nao pode falhar
    # deixa de testar: e o «carimbo que mente» aplicado a suite.
    assert _con(casa).execute(
        """SELECT corpo FROM mo_elementos
            WHERE ato = ? AND parte = 'CORPO'""",
        ("RC_TERMO_OBITO",)).fetchone() is None, (
            "a tela gravou um modelo que o papel não sabe montar")


def test_a_tela_RECUSA_claro_que_o_termo_nao_tem(casa):
    """Claro inventado é o que faz a lavratura estourar meses depois."""
    r = _gravar(casa, "RC_TERMO_CASAMENTO", "Casaram-se em {nao_existe}.")
    html = " ".join(r.get_data(as_text=True).split())
    assert "claros que este termo não tem" in html
    assert "nao_existe" in html


def test_o_conferidor_do_civil_e_a_MESMA_regra_de_quem_lavra(casa):
    """**Conferir com uma régua e imprimir com outra** é como a tela passa a
    aprovar o que o papel não sabe montar. Uma função só, e este teste a chama
    pelos dois lados para provar que é ela mesma."""
    import rc_modelos_do_livro as LIVRO

    conferidores = casa["app"].extensions.get("conferidores_de_modelo", {})
    for chave in TERMOS_DO_CIVIL:
        assert chave in conferidores, f"{chave} ficou sem conferidor próprio"
        especie = chave.replace("RC_TERMO_", "")
        torto = "Aos {nao_existe} dias."
        assert conferidores[chave](torto) == LIVRO.conferir_corpo(especie,
                                                                  torto)
        # e o padrão da casa passa pelos dois lados
        bom = LIVRO.modelo(especie)["texto"]
        assert conferidores[chave](bom) == ""


def test_a_tela_diz_qual_marcador_aquele_modelo_usa(casa):
    """**Sem esta frase a tela não dava pista nenhuma de qual é qual.**

    São dois formatos nesta casa, e escrever no errado é o engano mais fácil de
    cometer aqui. A pessoa descobriria pela recusa — depois de escrever o modelo
    inteiro —, e não antes dela.
    """
    civil = _tela(casa, editar="RC_TERMO_NASCIMENTO")
    assert "uma chave" in civil
    assert "<code>{nome}</code>" in civil

    # e o papel que É Jinja diz o contrário, com o exemplo dele
    outro = _tela(casa, editar="RI_FICHA")
    assert "duas chaves" in outro
    assert "a.numero" in outro
