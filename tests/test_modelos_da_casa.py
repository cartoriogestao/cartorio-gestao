"""Os modelos de todos os papéis da casa — o relato #28 do oficial.

A FRASE DELE:

    «preciso de mais controle sobre os modelos de todos os atos, de todas
     atribuições. preciso ter controle geral sobre os modelos, em especial os
     cabeçalhos padrão de cada atribuição e ato, corpo, encerramento, eventual
     notas de rodapé»

O QUE ESTES TESTES GUARDAM
    O principal deles é o **piso**: sem ajuste gravado, cada papel tem de sair
    exatamente com o padrão. É o que garante que instalação nova nasça
    funcionando e que «voltar ao padrão» não dependa de ninguém ter guardado o
    texto antigo.

    Desde o LF06A (19/10/2026) o padrão não mora mais no código: mora na pasta
    `modelos_padrao/`, carregada na base dos padrões. O teste-ouro, no fim
    deste arquivo, prova que nenhum dos 41 textos mudou um byte na mudança.
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
    #
    # **EM 19/10/2026 PASSOU DE 41 PARA 50 (LF06G)**: os papéis da retificação
    # e da usucapião, que eram constantes e f-strings dos módulos — «não
    # deveríamos ter modelos no código», o oficial. São nove, e nenhum
    # inventado: a notificação do confrontante (`rt_notificacao.MODELO`), a
    # notificação, o edital e o ofício aos entes (`us_notificacao`), as quatro
    # decisões que a ficha da usucapião sugere e o pedido do dossiê
    # (`usucapiao`). Todos sob o Registro de Imóveis, que é a atribuição deles.
    #
    # **EM 19/10/2026 PASSOU DE 50 PARA 97 (LF06B)**: as 47 FRASES que os
    # módulos do Registro de Imóveis montavam em f-string — a cláusula das
    # prenotações em aberto, os cinco teores do encerramento, os fechos do ato
    # e da abertura, as atas do expurgo, os cancelamentos nos indicadores, o
    # título e o fecho da certidão do Livro 3, a parte fixa das minutas… —,
    # pedido do oficial no mesmo dia («Não deveríamos ter modelos no código;
    # deveriam estar no banco, para editar com mais facilidade»). Cada uma é
    # papel próprio porque a REGRA que a escolhe ficou no módulo: há/não há,
    # singular/plural, com ou sem a função de quem assina. A lista está em
    # `modelos_papeis/ri.py` (grupo LF06B) e no inventário.
    #
    # **EM 19/10/2026 PASSOU DE 97 PARA 109 (LF06C)**: os doze papéis do
    # Registro Civil que eram montados no código — «não deveríamos ter modelos
    # no código», o oficial. Nenhum inventado: cada um era uma f-string ou uma
    # constante achada pela varredura do `docs/MODELOS_INVENTARIO.md`, e o
    # ouro do LF06C prova que saem com os mesmos bytes. São a ordem da
    # qualificação dos termos, o fecho da certidão em resumo, a introdução da
    # de inteiro teor, as três anotações da CRC, a averbação de retificação,
    # a comunicação mensal de óbitos, o ofício à FUNAI, o edital de proclamas
    # (o texto e a folha) e a certidão de habilitação. As frases que uma
    # regra escolhe são peças desses papéis, e não linhas do catálogo.
    # (+ a frase do LH02, o fecho do papel reprográfico: `ri_frases` também.)
    assert len(_frases_do_ri_lf06b()) == 47 + NOVOS_NO_CATALOGO_LH02
    assert len(OURO_C.PAPEIS_NOVOS) == 12
    # Os lotes paralelos do LF06 somam aqui, cada um, a contagem que escreve à
    # mão no próprio bloco (`NOVOS_NO_CATALOGO_<lote> = n`, com o porquê):
    # mudando todos esta linha, o segundo a entrar conflitava e voltava.
    assert len(MOD.CATALOGO) == 50 + 47 + 12 + sum(
        n for nome, n in globals().items() if nome.startswith("NOVOS_NO_CATALOGO_"))
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
#
#   **E A ABERTURA SAIU DA F-STRING NO LF06E (19/10/2026)**: ela é a peça
#   `PT_CERTIDAO_CABECA`, que o oficial abre e edita na mesma tela — a
#   positiva continua «{cabeca} {corpo}» porque ela É a abertura mais a lista
#   dos protestos, e assim o ajuste que a casa já tenha feito continua
#   montando. O defeito (o texto inalcançável) acabou; o esqueleto ficou, e a
#   declaração diz agora onde o texto está.
ESQUELETO_EM_VEZ_DE_TEXTO = {
    "PT_CERTIDAO_POSITIVA": ("só «{cabeca} {corpo}»; a abertura é a peça "
                             "PT_CERTIDAO_CABECA, editável na tela"),
    # **E O MIOLO DO INTEIRO TEOR É ESQUELETO POR NATUREZA, E NÃO POR DEFEITO** —
    # 18/09/2026, problema #75. Ele é `{% if teor_odf %}{{ teor_odf }}{% endif %}`
    # mais os atos e o «Era o que nela continha.»: o texto da certidão de inteiro
    # teor **é o do livro**, e a única prosa dela é a frase de fecho, que está
    # aqui à vista e é editável. **Não há f-string escondida** — que é a razão de
    # este guarda existir e a razão de a `PT_CERTIDAO_POSITIVA` estar na lista.
    # Declarado, o guarda continua valendo: ele exige que o declarado seja
    # esqueleto de verdade, e fica vermelho no dia em que este papel ganhar texto
    # próprio (aí a declaração sai).
    #
    # **E A QUALIFICAÇÃO DOS TERMOS DO CIVIL TAMBÉM É, POR NATUREZA** — LF06C,
    # 19/10/2026. O papel é a ORDEM das partes («{nome}, {nacionalidade}, …,
    # {residencia}»); a frase de cada parte é uma peça à vista na pasta
    # (`RC_QUALIFICACAO__cpf_feminino`: «inscrita no CPF n.º {numero}»), e o
    # que fica no código é a REGRA — a concordância com o sexo e a parte vazia
    # que some junto com a vírgula. Não há f-string escondida com o texto.
    "RC_QUALIFICACAO": "a ordem das partes; as frases são as peças RC_QUALIFICACAO__*",
    # **E A ANOTAÇÃO DE MARGEM É CURTA POR NATUREZA** — LF06C. A moldura da
    # compacta tem seis palavras («ANOTAÇÃO: Aos …, anoto o …») e a da completa
    # oito; o resto é o dado da comunicação e as frases opcionais, que são
    # peças à vista na pasta (`__ocorrido_em`, `__na_serventia`, `__origem`…).
    # Medido: mantendo os bytes de antes, nenhuma moldura chega a dez. Não há
    # f-string escondida — a de fé pública, com a frase inteira, passa no guarda.
    "RC_ANOTACAO_CRC_COMPACTA": "moldura de seis palavras; as frases são as peças RC_ANOTACAO_CRC_COMPACTA__*",
    "RC_ANOTACAO_CRC_COMPLETA": "moldura de oito palavras; «Origem: …» é a peça RC_ANOTACAO_CRC_COMPLETA__origem",
}


# **A FÓRMULA CURTA NÃO É ESQUELETO** — LF06D, 19/10/2026. O reconhecimento de
# firma tem oito palavras, e todas estão à vista na tela: «RECONHEÇO POR
# SEMELHANÇA A FIRMA DE {quem}. DOU FÉ.». A régua das dez palavras a
# acusaria — e é a lição da régua errada que acusa quem está certo, escrita
# logo abaixo. Declaradas, com o mesmo rigor do esqueleto: o guarda exige que
# a fórmula seja curta DE VERDADE (menos de dez palavras) e que tenha texto à
# vista (três palavras ou mais); se crescer, a declaração sai.
FORMULA_CURTA = {
    "NOTAS_RECONHECIMENTO_SEMELHANCA": "a fórmula da etiqueta tem oito palavras",
    "NOTAS_RECONHECIMENTO_AUTENTICIDADE": "a fórmula da etiqueta tem oito palavras",
    "NOTAS_RECONHECIMENTO_SINAL": "a fórmula do sinal público tem sete palavras",
    "NOTAS_ETIQUETA_FECHO": "«EM TEST. DA VERDADE.» — o fecho é isso",
    "NOTAS_ANOTACAO_MARGEM": "«por ato lavrado nesta …» — o resto da anotação "
                             "são peças, cada uma escolhida pela regra",
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
        if c.get("peca"):
            # A PEÇA É UMA FRASE (LF06E), e frase curta não é papel sem texto:
            # «desta praça» tem duas palavras e é inteira. O guarda é dos papéis.
            continue

        palavras = [p for p in re.split(r"\W+", _texto_que_nao_e_marcador(texto))
                    if p.isalpha()]
        # AS FRASES DO RI (LF06B) SÃO CURTAS POR NATUREZA — «SELO DE
        # PRENOTAÇÃO» é a frase inteira. O defeito que este guarda pega é o
        # texto que ficou numa f-string e o modelo só com marcadores; frase com
        # uma palavra de verdade fora dos claros não é esqueleto.
        esqueleto = len(palavras) < (1 if c["padrao"][0] == "ri_frases" else 10)

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

        if chave in FORMULA_CURTA:
            assert 3 <= len(palavras) < 10, (
                f"{chave} está declarado em FORMULA_CURTA e tem {len(palavras)} "
                f"palavra(s) à vista: ou cresceu (tire-o da lista) ou virou "
                f"esqueleto.")
            continue

        assert not esqueleto, (
            f"{chave} é ESQUELETO, e não texto: sobram {len(palavras)} "
            f"palavra(s) fora dos marcadores. O oficial abriria a tela de "
            f"editar e veria marcadores, com o texto do papel invisível e "
            f"ineditável — o defeito do termo do protesto de 01/09/2026.")


def test_o_catalogo_nao_guarda_copia_do_texto():
    """O texto é LIDO da base, e não copiado para o catálogo.

    Duas versões do mesmo modelo divergiriam no primeiro conserto — a tela
    mostrando uma coisa e o programa imprimindo outra. Este projeto já pagou
    por isso com a `normalizar_nome`. O `padrao` continua dizendo o nome
    antigo da constante, que ainda responde (`constante_antiga`)."""
    for c in MOD.CATALOGO:
        assert isinstance(c["padrao"], tuple) and len(c["padrao"]) == 2
        assert "corpo" not in c and "texto" not in c


def test_a_url_do_qr_do_selo_nao_esta_no_catalogo():
    """`notas_selo.MODELO_PADRAO` se chama modelo e não é um: é a URL de dentro
    do QR, com marcador do `str.format`. Passá-la pelo Jinja aprovaria um texto
    que o QR não sabe montar."""
    assert "NOTAS_ETIQUETA" not in MOD.POR_CHAVE
    for c in MOD.CATALOGO:
        assert c["padrao"][0] != "notas_selo"


# ------------------------------------------------ o código é o piso


def test_sem_ajuste_o_corpo_e_exatamente_o_padrao_da_base(casa):
    """O TESTE PRINCIPAL. Instalação nova, tabela vazia: cada papel sai com o
    padrão que veio no pacote, sem carga de modelo nenhuma feita à mão."""
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


def test_restaurar_o_que_nao_havia_devolve_falso(casa):
    """«Devolve se havia ajuste»: o `DELETE ... RETURNING` sem linha apagada é
    lista vazia, e lista vazia é falso — a segunda vez não acha o que apagar."""
    con = _con(casa)
    with con:
        MOD.salvar(con, "CAIXA_RECIBO", corpo="X", quem="mario",
                   agora="2026-08-29T09:00")
        assert MOD.restaurar(con, "CAIXA_RECIBO") is True
        assert MOD.restaurar(con, "CAIXA_RECIBO") is False


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
    versão.

    DESDE O LF06A ELE VIRA AJUSTE NA SUBIDA (`trazer_ajustes_do_legado_ri`,
    chamada pelo `init_ri_schema`), e a busca fica uma só: a casa, depois a
    base."""
    con = _con(casa)
    with con:
        con.execute(
            "INSERT INTO ri_modelos (nome, tipo, corpo, formato, ativo,"
            " versao, atualizado_em)"
            " VALUES ('velha','CERTIDAO','CERTIDAO ANTIGA','html',1,1,'x')")
        assert MOD.trazer_ajustes_do_legado_ri(con, agora="2026-10-19T08:00") == 1
    assert MOD.corpo_de(con, "RI_CERTIDAO") == "CERTIDAO ANTIGA"
    assert MOD.esta_ajustado(con, "RI_CERTIDAO")


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
        assert MOD.trazer_ajustes_do_legado_ri(con, agora="b") == 0
    assert MOD.corpo_de(con, "RI_CERTIDAO") == "NOVA"


def test_voltar_ao_padrao_nao_ressuscita_o_legado_na_subida_seguinte(casa):
    """O legado lido é DESLIGADO (`ativo = 0`). Sem isso, «voltar ao padrão»
    apagaria o ajuste e a subida seguinte o traria de volta da tabela velha —
    a casa clicaria e o papel antigo voltaria sozinho."""
    con = _con(casa)
    with con:
        con.execute(
            "INSERT INTO ri_modelos (nome, tipo, corpo, formato, ativo,"
            " versao, atualizado_em)"
            " VALUES ('velha','NOTA','NOTA ANTIGA','html',1,1,'x')")
        MOD.trazer_ajustes_do_legado_ri(con, agora="a")
        assert MOD.restaurar(con, "RI_NOTA") is True
        assert MOD.trazer_ajustes_do_legado_ri(con, agora="b") == 0
    assert MOD.corpo_de(con, "RI_NOTA") == MOD.padrao_de("RI_NOTA")


def _legado(con, tipo, corpo, ativo=1):
    return banco(con).escrever(
        """INSERT INTO ri_modelos (nome, tipo, corpo, formato, ativo, versao,
               atualizado_em)
           VALUES ('velha', %s, %s, 'html', %s, 1, 'x') RETURNING id""",
        (tipo, corpo, ativo))[0]["id"]


def _ativo_no_legado(con, id_):
    return banco(con).valor("SELECT ativo FROM ri_modelos WHERE id = %s", (id_,))


def test_o_legado_nao_e_desligado_quando_a_casa_tem_outro_ajuste(casa):
    """REVISÃO DO LF06A: o `UPDATE ... ativo = 0` rodava mesmo quando o INSERT
    não copiava nada, e o texto velho sumia sem ter ido para lugar nenhum.

    Com um ajuste DIFERENTE na casa, a linha velha fica ligada — não é lida (a
    casa vence) — e volta a valer se a casa restaurar o padrão, que é o que a
    leitura de antes do LF06A fazia."""
    con = _con(casa)
    with con:
        MOD.salvar(con, "RI_CERTIDAO", corpo="NOVA DA CASA", quem="mario", agora="a")
        velha = _legado(con, "CERTIDAO", "CERTIDAO ANTIGA")
        assert MOD.trazer_ajustes_do_legado_ri(con, agora="b") == 0
        assert _ativo_no_legado(con, velha) == 1, "desligou sem ter copiado"
        assert MOD.corpo_de(con, "RI_CERTIDAO") == "NOVA DA CASA"
        MOD.restaurar(con, "RI_CERTIDAO")
        assert MOD.trazer_ajustes_do_legado_ri(con, agora="c") == 1
        assert _ativo_no_legado(con, velha) == 0
    assert MOD.corpo_de(con, "RI_CERTIDAO") == "CERTIDAO ANTIGA"


def test_ajuste_desligado_ou_vazio_na_casa_nao_impede_a_copia_do_legado(casa):
    """Linha desligada ou vazia em `mo_modelos` não é ajuste: a leitura de
    antes passava por ela e caía no legado. O `DO NOTHING` deixava o legado
    de fora e o desligava — o papel saía do padrão de fábrica, calado."""
    con = _con(casa)
    with con:
        banco(con).escrever(
            """INSERT INTO mo_modelos (chave, corpo, ativo, atualizado_em)
               VALUES ('RI_NOTA', 'NOTA DESLIGADA', 0, 'a'),
                      ('RI_FICHA', '', 1, 'a')""")
        nota = _legado(con, "NOTA", "NOTA ANTIGA")
        ficha = _legado(con, "FICHA", "FICHA ANTIGA")
        assert MOD.trazer_ajustes_do_legado_ri(con, agora="b") == 2
        assert _ativo_no_legado(con, nota) == 0 and _ativo_no_legado(con, ficha) == 0
    assert MOD.corpo_de(con, "RI_NOTA") == "NOTA ANTIGA"
    assert MOD.corpo_de(con, "RI_FICHA") == "FICHA ANTIGA"


def test_legado_identico_ao_ajuste_da_casa_e_desligado_sem_copia(casa):
    """O texto velho já está na casa, letra por letra: não há o que copiar, e
    a linha velha pode ser desligada sem perder nada."""
    con = _con(casa)
    with con:
        MOD.salvar(con, "RI_CABECALHO", corpo="CABECALHO IGUAL", quem="mario",
                   agora="a")
        velha = _legado(con, "CABECALHO", "CABECALHO IGUAL")
        assert MOD.trazer_ajustes_do_legado_ri(con, agora="b") == 0
        assert _ativo_no_legado(con, velha) == 0


def _matricula_de_exemplo(con) -> int:
    return banco(con).escrever(
        """INSERT INTO ri_matriculas (numero, complemento, livro, livro_norm,
               tipo_ficha, situacao, conferido, origem, criado_em, teor_formato)
           VALUES ('4901', '', '2', '2', 'ESTRUTURADA', 'ATIVA', 0, 'SISTEMA',
                   '2026-10-19', 'texto') RETURNING id""")[0]["id"]


def test_a_ficha_com_modelo_do_legado_acha_o_texto_pelo_caminho_novo(casa):
    """`?modelo=<id>` da ficha (`ri_web.ri_ficha_odt`). Depois da subida a
    linha velha está desligada e o texto dela mora no catálogo — a ficha que
    procurava só a linha ATIVA caía calada no modelo da casa (revisão do
    LF06A). Agora acha o texto pelo caminho novo."""
    import zipfile
    from io import BytesIO
    con = _con(casa)
    with con:
        mid = _matricula_de_exemplo(con)
        velha = _legado(con, "FICHA", "<p>FICHA LEGADA DE EXEMPLO {{ m.numero }}</p>")
        assert MOD.trazer_ajustes_do_legado_ri(con, agora="b") == 1
        assert _ativo_no_legado(con, velha) == 0
    achado = MOD.modelo_legado_ri(con, velha)
    assert achado["chave"] == "RI_FICHA" and achado["de_onde"] == "RI_FICHA"
    r = casa["cliente"].get(f"/registro-imoveis/{mid}/ficha.odt",
                            query_string={"modelo": velha, "formato": "odt"})
    assert r.status_code == 200 and r.data[:2] == b"PK"
    conteudo = zipfile.ZipFile(BytesIO(r.data)).read("content.xml").decode("utf-8")
    assert "FICHA LEGADA DE EXEMPLO 4901" in conteudo


def test_a_ficha_com_modelo_que_nao_existe_avisa_e_nao_imprime(casa):
    """Número que não se acha não pode virar «a ficha saiu com outro modelo»:
    a tela avisa e volta à ficha, sem papel."""
    con = _con(casa)
    with con:
        mid = _matricula_de_exemplo(con)
    r = casa["cliente"].get(f"/registro-imoveis/{mid}/ficha.odt",
                            query_string={"modelo": "987654", "formato": "odt"})
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/registro-imoveis/{mid}")
    with casa["cliente"].session_transaction() as sessao:
        avisos = " ".join(m for _, m in sessao.get("_flashes", []))
    assert "987654 não foi encontrado" in avisos
    assert MOD.modelo_legado_ri(con, "987654") is None
    assert MOD.modelo_legado_ri(con, "nao-e-numero") is None


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
    # diz de onde o padrão sai — o arquivo da pasta, desde o LF06A
    assert "modelos_padrao/caixa/CAIXA_RECIBO.txt" in html


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


# ============================================ O PROTESTO SEM TEXTO NO CÓDIGO — LF06E
#
# As frases que a REGRA escolhe — o pedido da certidão, a abertura e o fecho do
# art. 26, a intimação no termo e no instrumento, a menção da cópia — e o aviso,
# o edital e o canhoto inteiros saíram das f-strings dos módulos do protesto
# para `modelos_padrao/protesto/`. A regra (edital × pessoal, um × vários, com ×
# sem cópia) ficou no módulo; o texto, na pasta, editável na tela de Modelos.
#
# **A PROVA DE QUE NADA MUDOU É O OURO** gravado ANTES (commit 2c41e90,
# `fixtures/modelos_ouro/ouro_lf06e.py`): 119 papéis montados pelos montadores
# puros, 6 que leem o banco (aviso, canhoto, os dois livros), o retrato dos
# dicionários de rótulos e o HTML das 8 molduras impressas — byte a byte,
# porque termo lavrado, certidão e edital congelam.
#
# A SEÇÃO MORA AQUI, E NÃO NO FIM DO ARQUIVO: os lotes LF06 rodaram em
# paralelo, e cada um acrescentava a sua no fim — o mesmo lugar, conflito
# certo na integração (o LF06E já voltou uma vez por isso).

import importlib.util                                            # noqa: E402
import protesto_pecas as PECAS                                  # noqa: E402

_ESPEC_E = importlib.util.spec_from_file_location(
    "ouro_lf06e", RAIZ / "tests" / "fixtures" / "modelos_ouro" / "ouro_lf06e.py")
OURO_E = importlib.util.module_from_spec(_ESPEC_E)
_ESPEC_E.loader.exec_module(OURO_E)

PECAS_DO_PROTESTO = tuple(c["chave"] for c in MOD.CATALOGO if c.get("peca"))

# **EM 19/10/2026 O CATÁLOGO GANHOU 37 LINHAS (LF06E)**: o texto do Protesto
# que estava nas f-strings saiu do código — o aviso e o edital de intimação
# (2 papéis inteiros, que não tinham modelo) e 35 PEÇAS, as frases que a
# regra escolhe (pedido, abertura e fecho da certidão, a intimação no termo e
# no instrumento, o canhoto) e os vocabulários de rótulos (motivo, tipo,
# espécie, livros, a moldura do papel impresso). Medido em
# `modelos_papeis/protesto.py`. A contagem do catálogo, lá em cima, soma este
# número com o dos outros lotes paralelos do LF06.
NOVOS_NO_CATALOGO_LF06E = 37

# O QUE MUDOU DE PROPÓSITO DEPOIS DO OURO DO LF06E (LD04, 21/10/2026) — e só
# isto. A regra é a do LF06A, mais abaixo (`MUDOU_DEPOIS_DO_OURO`): o ouro NÃO
# se regera; as trocas se aplicam ao retrato de antes, serializado como o ouro
# o guarda, cada uma achada uma vez só, e o resto continua byte a byte.
#
#   - O Livro de Protocolo ganhou a coluna do CPF/CNPJ do devedor (CN-MA art.
#     906: o número identificador consta «no Livro de Protocolo»), e ela vai
#     NO FIM desde o LD11: as oito colunas do ouro ficam onde estavam, para
#     quem lê o livro por posição. No ouro, a MARIA tem CPF e o JOÃO não tem
#     documento. (O retrato do banco é dicionário serializado com as chaves em
#     ordem: a posição da coluna só aparece na moldura impressa.)
MUDOU_DEPOIS_DO_OURO_LF06E = {
    "banco": {
        "livro_de_protocolo": (
            ('"devedor": "MARIA DE EXEMPLO", ',
             '"devedor": "MARIA DE EXEMPLO", "documento": "000.000.001-91", '),
            ('"devedor": "JOÃO DE EXEMPLO", ',
             '"devedor": "JOÃO DE EXEMPLO", "documento": "", ')),
    },
    "molduras": {
        "livro_protocolo": (
            ("<th>Ocorrências</th></tr>",
             "<th>Ocorrências</th><th>CPF/CNPJ do devedor</th></tr>"),
            ("pago em 11/09/2026</td></tr>",
             "pago em 11/09/2026</td><td>000.000.001-91</td></tr>"),
            ("pago em 19/09/2026</td></tr>",
             "pago em 19/09/2026</td><td></td></tr>")),
    },
}


# O QUE O LD08 (21/10/2026) MUDOU NOS PADRÕES DO PROTESTO — e por que o ouro
# acima NÃO precisou de troca nenhuma. Cada pedaço novo só entra com um dado
# que nenhum contexto do ouro tem, e sem ele o papel sai byte a byte o de
# antes (os testes do ouro, logo abaixo, conferem):
#
#   - PT_AVISO_INTIMACAO: o claro `{documento_do_apresentante}` depois do nome
#     (CN-MA art. 923; CNN art. 356, § 4º). Vem do título do balcão ou do
#     cadastro dos apresentantes; o ouro não cadastra apresentante, e o claro
#     vem vazio — «Apresentante: BANCO DE EXEMPLO», como antes.
#   - PT_INSTRUMENTO_DESCRICAO: o rótulo `apresentante_endereco` (Lei
#     9.492/1997, art. 22, II), escolhido só quando há endereço; os contextos
#     `descricao_do_documento(...)` do ouro não têm.
#   - PT_CERTIDAO_LINHA: `protocolo_com_data` (CNN art. 259, p. ú., VII), só
#     com a data do apontamento — o `_achado` do ouro não a tem —, e `endosso`,
#     `endosso_M`, `endosso_T` (art. 259, p. ú., V), só com o código M ou T — o
#     `_achado` do ouro tem `tipo_endosso` vazio.
#
# As chamadas que exercitam os pedaços novos estão no teste dos claros (o
# bloco «AS CHAMADAS DO LD08»), e o papel inteiro, em `test_requisitos_protesto`.
MUDOU_NO_LD08 = {
    "PT_AVISO_INTIMACAO": ("{documento_do_apresentante}",),
    "PT_INSTRUMENTO_DESCRICAO": ("apresentante_endereco",),
    "PT_CERTIDAO_LINHA": ("protocolo_com_data", "endosso", "endosso_M", "endosso_T"),
}


def test_o_que_o_ld08_pos_nos_padroes_esta_la_e_o_ouro_nao_o_ve(ouro_e):
    """Os pedaços do LD08 estão no padrão; e nenhuma saída gravada no ouro os
    teria — se tivesse, o ouro teria de declarar a troca, e não declara."""
    import json
    for chave, pedacos in MUDOU_NO_LD08.items():
        padrao = MOD.padrao_de(chave)
        rotulos = PECAS._rotulos(padrao) if chave in PECAS.VOCABULARIOS else {}
        for pedaco in pedacos:
            assert pedaco in padrao if pedaco.startswith("{") else pedaco in rotulos, (
                chave, pedaco)
    gravado = json.dumps(ouro_e, ensure_ascii=False)
    # (o «endosso translativo» solto está no ouro, na hipótese de cancelamento:
    # a marca é o pedaço da linha, com o «; » que o junta)
    for marca in ("; endosso translativo;", "; endosso mandato;",
                  "protocolo 2609080001 de",
                  "Apresentante: BANCO DE EXEMPLO, endereço",
                  "Apresentante: BANCO DE EXEMPLO, CPF/CNPJ"):
        assert marca not in gravado, marca


def _ouro_e_de_hoje(secao: str, nome: str, antes):
    """O retrato de antes com as trocas declaradas acima, e só elas."""
    import json
    trocas = MUDOU_DEPOIS_DO_OURO_LF06E.get(secao, {}).get(nome)
    if not trocas:
        return antes
    texto = json.dumps(antes, ensure_ascii=False, sort_keys=True)
    return json.loads(_com_as_trocas(texto, trocas))


# **EM 21/10/2026 O CATÁLOGO GANHOU 4 LINHAS (LD04)**: os papéis do Protesto
# que a norma pede e o sistema não tinha — a qualificação do registro no alto
# do termo (peça; Lei 9.492/1997, arts. 21, § 4º, e 22), a certidão da
# intimação por meio eletrônico no instrumento (peça; CN-MA arts. 919, § 1º, e
# 921, § 6º, II), o termo do cancelamento (art. 26, § 6º) e a quitação do
# título pago no tabelionato (art. 19, § 2º; CN-MA art. 927). Nenhum tem
# precedente no E-Ofício: são afirmação jurídica em papel assinado, e vão ao
# catálogo, que é do oficial. O texto do termo da casa (`PT_TERMO_PROTESTO`)
# não mudou um byte: a qualificação é peça à parte, posta no alto pela regra.
PAPEIS_DO_LD04 = {"PT_TERMO_QUALIFICACAO", "PT_INSTRUMENTO_INTIMACAO_DIGITAL",
                  "PT_TERMO_CANCELAMENTO", "PT_QUITACAO"}
NOVOS_NO_CATALOGO_LD04 = 4


def test_os_papeis_do_ld04_estao_no_catalogo_e_a_tela_os_confere(casa):
    """A contagem escrita à mão bate com a lista; cada papel novo tem ficha e
    conferidor próprio — a tela recusa o claro que o montador não preenche e
    aceita o padrão, em vez de o balcão descobrir na hora do ato."""
    assert len(PAPEIS_DO_LD04) == NOVOS_NO_CATALOGO_LD04
    assert PAPEIS_DO_LD04 <= set(MOD.POR_CHAVE)
    conferidores = casa["app"].extensions.get("conferidores_de_modelo", {})
    for chave in PAPEIS_DO_LD04:
        c = MOD.POR_CHAVE[chave]
        assert c["atribuicao"] == "Protesto" and c["formato"] == MOD.CHAVES, chave
        assert c["nome"] != chave and c["explica"], chave
        assert conferidores[chave](MOD.padrao_de(chave)) == "", chave
        assert "claro_inventado_ld04" in conferidores[chave](
            "Texto {claro_inventado_ld04}."), chave


# **EM 23/10/2026 O CATÁLOGO GANHOU 1 LINHA (tarefa 56, o tríduo)**: a menção
# do atraso no instrumento — CN-MA art. 913, § 1º. Peça que só sai no protesto
# lavrado depois do termo final; o modelo do instrumento não mudou um byte.
PAPEIS_DO_TRIDUO = {"PT_INSTRUMENTO_ATRASO"}
NOVOS_NO_CATALOGO_TRIDUO = 1


def test_a_mencao_do_atraso_do_triduo_esta_no_catalogo_e_a_tela_a_confere(casa):
    assert len(PAPEIS_DO_TRIDUO) == NOVOS_NO_CATALOGO_TRIDUO
    assert PAPEIS_DO_TRIDUO <= set(MOD.POR_CHAVE)
    conferidores = casa["app"].extensions.get("conferidores_de_modelo", {})
    for chave in PAPEIS_DO_TRIDUO:
        c = MOD.POR_CHAVE[chave]
        assert c["atribuicao"] == "Protesto" and c["formato"] == MOD.CHAVES, chave
        assert c["nome"] != chave and c["explica"], chave
        assert conferidores[chave](MOD.padrao_de(chave)) == "", chave
        assert "claro_inventado_triduo" in conferidores[chave](
            "Texto {claro_inventado_triduo}."), chave


def test_o_que_mudou_depois_do_ouro_do_protesto_e_chamada_do_ouro(ouro_e):
    """A lista das mudanças de propósito só fala do que o ouro guarda — senão
    ela seria uma porta aberta, e não um registro."""
    assert set(MUDOU_DEPOIS_DO_OURO_LF06E["banco"]) <= set(ouro_e["banco"])
    assert set(MUDOU_DEPOIS_DO_OURO_LF06E["molduras"]) <= set(OURO_E.ouro_das_molduras())


@pytest.fixture(scope="module")
def ouro_e():
    return OURO_E.ouro()


def test_o_ouro_do_protesto_foi_gravado_na_arvore_de_antes(ouro_e):
    """Do commit 2c41e90, com a árvore limpa — nenhuma frase já movida."""
    assert ouro_e["commit"] == "2c41e90"
    assert ouro_e["mudado_na_arvore"] == []
    assert len(ouro_e["funcoes"]) == 120 and len(ouro_e["banco"]) == 6


def test_os_papeis_do_protesto_saem_iguais_aos_de_antes(ouro_e):
    """Certidões (os quatro pedidos, com e sem documento, um e vários
    protestos, o ajuste antigo com `{cabeca}`), termo, instrumento, edital, a
    linha de cada protesto e as datas — inclusive as recusas, com o mesmo
    recado."""
    chamadas = OURO_E.chamadas()
    assert set(chamadas) | {"vocabulario"} == set(ouro_e["funcoes"])
    for nome, f in chamadas.items():
        assert OURO_E.normal(OURO_E.tenta(f)) == ouro_e["funcoes"][nome], nome


def test_os_rotulos_que_viraram_peca_nasceram_iguais_aos_dicionarios(ouro_e):
    """`MOTIVO_NO_LIVRO`, `TIPO_NO_LIVRO`, `FORMAS`, `OCORRENCIA_DO_ATO` e o
    nome da espécie no papel eram dicionários; a peça lida dá o mesmo."""
    assert (OURO_E.normal(OURO_E.tenta(OURO_E.vocabulario_de_hoje))
            == ouro_e["funcoes"]["vocabulario"])


def test_o_aviso_o_canhoto_e_os_livros_saem_iguais_aos_de_antes(casa, ouro_e):
    """Os que leem o título do banco — pelo caminho inteiro da busca única,
    com a conexão (ajuste da casa → base)."""
    con = _con(casa)
    with con:
        semeado = OURO_E.semear(con)
        chamadas = OURO_E.chamadas_com_banco(con, semeado)
        assert set(chamadas) == set(ouro_e["banco"])
        for nome, f in chamadas.items():
            assert OURO_E.normal(OURO_E.tenta(f)) == _ouro_e_de_hoje(
                "banco", nome, ouro_e["banco"][nome]), nome


def test_o_texto_do_protesto_saiu_mesmo_do_codigo():
    """Uma frase de cada peça, procurada no módulo que a montava. Achar quer
    dizer cópia esquecida — a tela mostraria uma e o papel imprimiria outra."""
    procurar = {
        "protesto_certidao.py": ("nos referidos livros e folhas",
                                 "neles encontrei protesto contra",
                                 "por determinação judicial expressa"),
        "protesto_termo.py": ("por meio eletrônico, com o recebimento",
                              "FALTA DE DEVOLUÇÃO", "FALTA DE ACEITE"),
        "protesto_instrumento.py": ("Fica dispensada a transcrição literal",
                                    "Não consta desta serventia cópia",
                                    "entregue no endereço do devedor",
                                    "espécie não informada"),
        "protesto_aviso.py": ("Fica V. Sa. INTIMADO(A)", "FAZ SABER a quem",
                              "COMPROVANTE DE RECEBIMENTO DA INTIMAÇÃO",
                              "não informado pelo apresentante", "o prazo legal"),
        "protesto_livros.py": ("pagamento registrado no E-Ofício",
                               "retirado pelo apresentante", "por transferência"),
        "atribuicoes_web.py": ("DESTAQUE AQUI", "lançamento(s)", "Nº de ordem"),
    }
    for arquivo, frases in procurar.items():
        fonte = (RAIZ / arquivo).read_text(encoding="utf-8")
        for frase in frases:
            assert frase not in fonte, f"{arquivo} ainda escreve «{frase}»"


def test_a_peca_tem_ficha_propria_e_nao_herda_o_fecho_da_atribuicao():
    """Cada peça é linha do catálogo — por isso a tela a acha — e
    `elementos_comuns: False`: o encerramento da atribuição no meio de uma
    frase estragaria o papel."""
    # 35 do LF06E; a qualificação do registro e a intimação eletrônica no
    # instrumento (LD04).
    assert len(PECAS_DO_PROTESTO) == 35 + 2
    for chave in PECAS_DO_PROTESTO:
        c = MOD.POR_CHAVE[chave]
        assert c["atribuicao"] == "Protesto" and c["formato"] == MOD.CHAVES
        assert c["elementos_comuns"] is False, chave
        assert c["nome"] != chave and c["explica"], f"{chave} sem ficha"


def test_toda_peca_do_protesto_abre_para_editar_na_tela(casa):
    """O pedido do oficial é EDITAR. A peça `<CHAVE>__<peca>` do LF06A a tela
    não acha (ela põe a chave em maiúsculas); a do protesto é linha do
    catálogo, e abre com o editor e o arquivo de onde o padrão sai."""
    for chave in PECAS_DO_PROTESTO + ("PT_AVISO_INTIMACAO", "PT_EDITAL_INTIMACAO"):
        html = _tela(casa, editar=chave)
        assert "textarea" in html and "não existe nesta casa" not in html, chave
        assert f"modelos_padrao/protesto/{chave}.txt" in html, chave


def _achado_cancelado(i: int) -> dict:
    return {"numero_titulo": str(i), "valor": "10,00",
            "data_protesto": "2026-09-08", "cancelado": True,
            "data_cancelamento": "2026-09-20"}


def test_o_fecho_que_o_oficial_corrige_na_tela_sai_na_certidao(casa):
    """O plural do fecho sai «as BAIXAS e o CANCELAMENTOS» — achado da
    varredura, e o ouro o guarda como está. Agora quem conserta é o oficial,
    na tela, e a certidão seguinte sai consertada; a de um protesto não muda."""
    import protesto_certidao as PTC
    novo = ("CERTIFICO ainda que nos referidos livros e folhas constam as "
            "BAIXAS e os CANCELAMENTOS dos mesmos, de acordo com o art. 26 da "
            "Lei 9.492/1997.")
    _gravar(casa, "PT_CERTIDAO_FECHO_VARIOS", novo)
    con = _con(casa)

    def certidao(achados):
        return PTC.montar_teor(tipo="CANCELAMENTO", nome="MARIA DE EXEMPLO",
                               documento="00000000191", achados=achados,
                               desde="2021-09-08", hoje="2026-09-08", con=con)

    varios = certidao([_achado_cancelado(1), _achado_cancelado(2)])
    assert novo in varios and "o CANCELAMENTOS" not in varios
    assert MOD.padrao_de("PT_CERTIDAO_FECHO_UM") in certidao([_achado_cancelado(1)])
    # sem a conexão, o montador continua no padrão
    assert "o CANCELAMENTOS" in PTC.montar_teor(
        tipo="CANCELAMENTO", nome="MARIA DE EXEMPLO", documento="00000000191",
        achados=[_achado_cancelado(1), _achado_cancelado(2)],
        desde="2021-09-08", hoje="2026-09-08")


def test_com_a_conexao_o_termo_monta_a_frase_da_intimacao_editada(casa):
    """O leitor está pronto para quando o oficial decidir que o livro segue o
    ajuste: com `con`, o termo sai com a frase da casa. Hoje quem lavra não
    passa `con` — ver o teste seguinte."""
    import protesto_termo as PTT
    _gravar(casa, "PT_TERMO_INTIMACAO_PESSOAL",
            "O devedor recebeu a intimação em mãos no dia {data}.")
    con = _con(casa)
    termo = PTT.montar(pessoal_data="2026-09-08", motivo_protesto="1",
                       tipo_protesto="C", con=con)
    assert termo.endswith("O devedor recebeu a intimação em mãos no dia 08/09/2026.")


# O que a casa escreve na tela, para as seis peças que entram no termo.
AJUSTES_DO_TERMO = {
    "PT_TERMO_INTIMACAO_EDITAL": "Intimado por edital da casa em {data}, motivo {motivo}.",
    "PT_TERMO_INTIMACAO_EDITAL_SEM_MOTIVO": "Intimado por edital da casa em {data}.",
    "PT_TERMO_INTIMACAO_PESSOAL": "Intimado em mãos, à moda da casa, em {data}.",
    "PT_TERMO_INTIMACAO_DIGITAL": "Intimado pela plataforma, à moda da casa, em {data}.",
    "PT_TERMO_MOTIVOS": "1 = FALTA DE PAGAMENTO DA CASA\n2 = FALTA DE ACEITE\n"
                        "3 = FALTA DE DEVOLUÇÃO",
    "PT_TERMO_TIPOS": "C = COMUM DA CASA\nF = FALIMENTAR DA CASA",
}


def _protesto_lancado(con, i: int, *, modo: str, digital: bool = False,
                      motivo_nao_entrega: str | None = None) -> tuple[str, dict]:
    """Um título apontado, intimado e protestado pelo domínio; devolve o teor
    gravado em `pt_atos` e os fatos que o termo usou. Pessoa de exemplo."""
    import json
    import protesto as PT
    import protesto_termo as PTT
    from bd_nativo import banco
    sv = {"unit_name": "SERVENTIA DE EXEMPLO", "cidade": "Cidade Exemplo",
          "uf": "MA"}
    bd = banco(con)
    tid = int(bd.escrever(
        """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
               valor_centavos, saldo_centavos, situacao, origem, criado_em,
               motivo_protesto, tipo_protesto)
           VALUES ('DMI', %s, %s, 10000, 10000, 'RECEBIDO', 'CRA', %s, '1', 'F')
           RETURNING id""",
        (f"90{i}/1", f"0000000090{i}", "2026-09-01T10:00:00"))[0]["id"])
    bd.escrever(
        """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
               documento_numero)
           VALUES (%s, 'MARIA DE EXEMPLO', 'CPF', '00000000191')""", (tid,))
    PT.lancar_apontamento(con, tid, sv=sv, agora="2026-09-01T10:00:00",
                          data_extenso="x")
    intimacao = PT.lancar_intimacao(
        con, tid, modo=modo, agora="2026-09-08", digital=digital,
        codigo_edital=f"ED-2026-90{i}" if modo == "EDITAL" else None)
    if motivo_nao_entrega:
        # O motivo da não-entrega chega pela carga do E-Ofício, e não pela
        # intimação lançada aqui — o termo o lê do detalhe do ato.
        bd.escrever("UPDATE pt_atos SET detalhe_json = %s WHERE id = %s",
                    (json.dumps({"modo": modo, "digital": digital,
                                 "motivo_nao_entrega": motivo_nao_entrega}),
                     intimacao["ato_id"]))
    r = PT.lancar_protesto(con, tid, sv=sv, agora="2026-09-20T10:00:00",
                           data_extenso="x")
    teor = bd.valor("SELECT teor FROM pt_atos WHERE id = %s", (r["ato_id"],))
    return teor, PTT.dados_do_titulo(con, tid)


def test_o_protesto_lancado_lavra_o_padrao_e_nao_o_ajuste_da_casa(casa):
    """O TERMO É O QUE SE ESCREVE NO LIVRO, e ele congela no ato. As frases
    da intimação e as palavras do motivo e do tipo eram constantes até o
    LF06E, e o ajuste da casa não as alcançava; fazer o livro segui-las muda o
    que se lavra (Lei 9.492/1997, art. 22, IV) — regra de negócio, que espera
    o oficial (revisão do LF06E, 2ª volta). Com as seis peças ajustadas na
    tela, os quatro caminhos da intimação lavram o padrão, com os bytes de
    antes."""
    import protesto_termo as PTT
    for chave, corpo in AJUSTES_DO_TERMO.items():
        _gravar(casa, chave, corpo)
    con = _con(casa)
    try:
        for chave, corpo in AJUSTES_DO_TERMO.items():
            assert MOD.texto_do_papel(con, chave) == corpo, f"a tela não gravou {chave}"
        casos = {
            "O devedor foi intimado por Edital em 08/09/2026 pelo motivo Ausente.":
                dict(modo="EDITAL", motivo_nao_entrega="Ausente"),
            "O devedor foi intimado por Edital em 08/09/2026.": dict(modo="EDITAL"),
            "O devedor foi intimado pessoalmente em 08/09/2026.": dict(modo="PESSOAL"),
            ("O devedor foi intimado por meio eletrônico, com o recebimento "
             "confirmado em 08/09/2026."): dict(modo="PESSOAL", digital=True),
        }
        for i, (frase, como) in enumerate(casos.items(), start=1):
            teor, fatos = _protesto_lancado(con, i, **como)
            assert teor == PTT.montar(**fatos), como
            assert teor.endswith(" " + frase), como
            assert "PROTESTO PARA FINS FALIMENTARES LAVRADO POR FALTA DE PAGAMENTO." in teor
            assert "DA CASA" not in teor and "moda da casa" not in teor, como
            # e o ajuste está valendo: com `con`, o mesmo termo sairia outro
            assert PTT.montar(**fatos, con=con) != teor, como
    finally:
        con.rollback()
        con.close()


def test_o_vocabulario_editado_troca_o_texto_e_nao_a_regra(casa):
    """O NOME é do sistema e o TEXTO é do oficial: o motivo «1» se escreve
    como a casa quiser; o «9» que o ajuste inventou não vira motivo; e a linha
    que o ajuste perdeu volta ao padrão — o papel nunca fica sem a palavra.
    Quem a usa com o ajuste é a certidão (e o instrumento); o termo lavrado,
    não — ver o teste acima."""
    import protesto_certidao as PTC
    import protesto_termo as PTT
    _gravar(casa, "PT_TERMO_MOTIVOS",
            "1 = FALTA DE PAGAMENTO DO TÍTULO\n9 = MOTIVO INVENTADO\nlinha torta")
    con = _con(casa)
    assert PTT.motivo_no_livro("1", con) == "FALTA DE PAGAMENTO DO TÍTULO"
    assert PTT.motivo_no_livro("9", con) == ""
    assert PTT.motivo_no_livro("2", con) == "FALTA DE ACEITE"
    assert PTT.motivo_no_livro("1") == "FALTA DE PAGAMENTO"
    achado = {**_achado_cancelado(1), "cancelado": False,
              "motivo_protesto": "1", "tipo_protesto": "C"}
    assert "protesto comum por falta de pagamento do título;" in \
        PTC._linha_do_protesto(achado, 1, con)


def test_a_peca_com_claro_inventado_e_recusa_com_o_nome_dela(casa):
    """Gravado por fora da tela (que o recusaria), o ajuste com `{nao_existe}`
    não imprime papel torto: a certidão recusa e diz qual peça e quais claros
    valem."""
    import protesto_certidao as PTC
    con = _con(casa)
    with con:
        MOD.salvar(con, "PT_CERTIDAO_CABECA",
                   corpo="CERTIFICO {pedido} contra {nao_existe}.", quem="mario",
                   agora="2026-10-19T10:00:00")
    with pytest.raises(PTC.CertidaoError) as erro:
        PTC.montar_teor(tipo="POSITIVA", nome="MARIA DE EXEMPLO",
                        documento="00000000191", achados=[_achado_cancelado(1)],
                        desde="2021-09-08", hoje="2026-09-08", con=con)
    assert "PT_CERTIDAO_CABECA" in str(erro.value)
    assert "{ano_por_extenso}" in str(erro.value)


def test_claro_com_atributo_ou_indice_tambem_e_recusa_e_nao_erro_500():
    """`{data.ano}` e `{data[x]}` o `str.format` recusa com `AttributeError` e
    `TypeError`, e não com `KeyError`; o ajuste antigo que os tenha vira o
    mesmo recado do `{nao_existe}`, com o nome da peça (observação 3 da
    revisão do LF06E, 2ª volta)."""
    import protesto_pecas as PECAS
    import protesto_termo as PTT
    for modelo in ("O devedor foi intimado em {data.ano}.",
                   "O devedor foi intimado em {data[x]}."):
        with pytest.raises(PTT.TermoError) as erro:
            PECAS.preencher(modelo, "PT_TERMO_INTIMACAO_PESSOAL", PTT.TermoError,
                            data="08/09/2026")
        assert "PT_TERMO_INTIMACAO_PESSOAL" in str(erro.value), modelo
        assert "{data}" in str(erro.value), modelo


def test_a_tela_recusa_a_peca_com_claro_que_o_papel_nao_preencheria(casa):
    """A recusa vem ao gravar, para quem edita — e não no termo que se lavra,
    com o protesto parado. O papel continua no padrão."""
    r = _gravar(casa, "PT_TERMO_INTIMACAO_PESSOAL",
                "O devedor foi intimado em {data} por {oficial}.")
    html = r.get_data(as_text=True)
    assert "não foi gravado" in html and "«{oficial}»" in html
    assert MOD.texto_do_papel(_con(casa), "PT_TERMO_INTIMACAO_PESSOAL") == (
        MOD.padrao_de("PT_TERMO_INTIMACAO_PESSOAL"))


def test_cada_peca_do_protesto_tem_conferidor_que_aceita_o_padrao_e_recusa_o_resto(casa):
    """A tela confere CHAVES com a régua de quem monta, e não com o Jinja
    genérico, que aprovaria `{claro_inventado}` como texto qualquer. No
    vocabulário, linha por linha: o rótulo não pede claro que o mesmo rótulo
    do padrão não pede; o nome que o padrão não tem a leitura ignora, e a tela
    não confere."""
    conferidores = casa["app"].extensions.get("conferidores_de_modelo", {})
    conferidas = PECAS.chaves_conferidas()
    # os dois papéis inteiros do LF06E e os dois do LD04 (o termo do
    # cancelamento e a quitação), que nasceram sem ajuste antigo a aceitar
    assert set(conferidas) == set(PECAS_DO_PROTESTO) | {
        "PT_AVISO_INTIMACAO", "PT_EDITAL_INTIMACAO", "PT_TERMO_CANCELAMENTO",
        "PT_QUITACAO"}
    assert set(PECAS.VOCABULARIOS) <= set(PECAS_DO_PROTESTO)
    for chave in conferidas:
        padrao = MOD.padrao_de(chave)
        assert conferidores[chave](padrao) == "", chave
        if chave in PECAS.VOCABULARIOS:
            nome = next(iter(PECAS._rotulos(padrao)))
            erro = conferidores[chave](f"{nome} = Texto {{nao_existe}}.")
            assert "nao_existe" in erro and f"«{nome}»" in erro, chave
            assert "Jinja" in conferidores[chave](f"{nome} = {{{{ a.numero }}}}"), chave
            assert conferidores[chave]("inventado = {qualquer}") == "", chave
        else:
            assert "nao_existe" in conferidores[chave]("Texto {nao_existe}."), chave
            assert "Jinja" in conferidores[chave]("Texto {{ a.numero }}."), chave
    # os cinco do LF06A aceitam claros de ajustes antigos: conferidor geral
    for chave in ("PT_TERMO_PROTESTO", "PT_INSTRUMENTO_PROTESTO",
                  "PT_CERTIDAO_NEGATIVA", "PT_CERTIDAO_POSITIVA",
                  "PT_CERTIDAO_CANCELAMENTO"):
        assert chave not in conferidores, chave


def test_a_tela_confere_a_peca_com_os_claros_que_o_montador_preenche(casa, monkeypatch):
    """A régua da tela são os claros do PADRÃO; a do papel, os que o montador
    passa. Medido em cada chamada do ouro — certidões, termo, instrumento,
    edital, aviso, canhoto, livros e as oito molduras impressas: em cada peça
    e em cada rótulo são os mesmos. Uma lista a mais seria a tela aprovando o
    que o papel não monta; uma a menos, recusando o que ele monta."""
    passados: dict = {}
    real = PECAS.preencher

    def espiao(modelo, chave, erro, **claros):
        k = (chave, modelo)
        passados[k] = passados.get(k, set(claros)) & set(claros)
        return real(modelo, chave, erro, **claros)
    monkeypatch.setattr(PECAS, "preencher", espiao)
    for f in OURO_E.chamadas().values():
        OURO_E.tenta(f)
    casa["db"].set_settings({"modulo_protesto_ligado": "1"})
    con = _con(casa)
    with con:
        semeado = OURO_E.semear_molduras(con)
        for f in OURO_E.chamadas_com_banco(con, semeado).values():
            OURO_E.tenta(f)
    for rota in OURO_E.rotas_das_molduras(semeado).values():
        assert casa["cliente"].get(rota).status_code == 200, rota
    # AS CHAMADAS DO LD04 (21/10/2026): os papéis e as peças que nasceram
    # depois do ouro — a intimação eletrônica no instrumento, o parágrafo do
    # Livro de Protocolo na certidão a pedido escrito, o termo do cancelamento
    # e a quitação. Sem elas a régua da tela não teria com o que se medir, e o
    # «claro que nenhum montador preenche» acusaria os papéis novos.
    import protesto_certidao as PTC
    import protesto_instrumento as PTI
    import protesto_livros as PLIV
    import protesto_termo as PTT
    with con:
        bd = banco(con)
        pago = bd.valor("SELECT id FROM pt_atos WHERE tipo = 'PAGAMENTO' "
                        "AND cancelado = 0 ORDER BY id LIMIT 1")
        protestado = PTT.fatos_da_qualificacao(bd, semeado["titulos"]["magro"])
        for f in (
                lambda: PTI.montar_teor(
                    serventia="SERVENTIA DE EXEMPLO", praca="Cidade Exemplo",
                    motivo="falta de pagamento", copia_arquivada=False,
                    intimacao={"modo": "PESSOAL", "data": "2026-09-08",
                               "digital": True},
                    descricao="Título de exemplo."),
                lambda: PTC.paragrafo_do_protocolo(PLIV.protocolo_do_devedor(
                    con, nome=OURO_E.DEVEDOR, documento=OURO_E.CPF)),
                lambda: PTT.montar(motivo_protesto="1", tipo_protesto="C",
                                   pessoal_data="2026-09-15",
                                   qualificacao_do_registro=protestado),
                lambda: PTT.montar_cancelamento(
                    data="2026-09-20", hipotese="Pagamento do título",
                    fundamento_legal="Lei 9.492/1997, art. 26.",
                    fundamento="Recibo de exemplo", qualificacao_do_registro=protestado),
                lambda: PLIV.quitacao(con, pago)):
            saida = OURO_E.tenta(f)
            assert "ok" in saida and saida["ok"], saida
    # AS CHAMADAS DO LD08 (21/10/2026): os rótulos novos — o protocolo com a
    # data e o tipo do endosso na linha da certidão, o apresentante com o
    # endereço na descrição do instrumento — e o aviso com o CPF/CNPJ do
    # apresentante. Ver `MUDOU_NO_LD08`.
    for f in (
            lambda: PTC._linha_do_protesto(OURO_E._achado(
                tipo_endosso="T", data_protocolo="2026-09-08"), 1),
            lambda: PTC._linha_do_protesto(OURO_E._achado(tipo_endosso="M"), 2),
            lambda: PTI.descricao_do_documento({
                "titulo": {"especie": "DMI", "numero_titulo": "123",
                           "apresentante_nome": "BANCO DE EXEMPLO"},
                "protesto": None, "apontado_em": None, "devedores": [],
                "apresentante": {"endereco": "Rua de Exemplo, 1, Cidade Exemplo/MA"}})):
        saida = OURO_E.tenta(f)
        assert "ok" in saida and saida["ok"], saida
    medidos: dict = {}
    for (chave, modelo), claros in passados.items():
        if chave not in PECAS.chaves_conferidas():
            continue                       # os cinco do LF06A, e o ajuste do ouro
        if chave not in PECAS.VOCABULARIOS:
            alvos = [(chave, None)]
        else:
            alvos = [(chave, nome) for nome, valor
                     in PECAS._rotulos(MOD.padrao_de(chave)).items()
                     if valor == modelo]
            assert alvos, (chave, modelo)
        for k in alvos:
            medidos[k] = medidos.get(k, claros) & claros
    diferentes = {}
    for (chave, nome), claros in medidos.items():
        padrao = MOD.padrao_de(chave)
        texto = padrao if nome is None else PECAS._rotulos(padrao)[nome]
        if PECAS.claros_do_texto(texto) != claros:
            diferentes[(chave, nome)] = (sorted(PECAS.claros_do_texto(texto)),
                                         sorted(claros))
    assert diferentes == {}
    # o que nenhum montador preenche não pode pedir claro: sairia «{x}» no papel
    preenchidas = {chave for chave, _ in medidos}
    for chave in PECAS.chaves_conferidas():
        padrao = MOD.padrao_de(chave)
        if chave not in preenchidas:
            assert PECAS.claros_do_texto(padrao) == set(), chave
    assert len(medidos) > 60


def test_o_encerramento_da_atribuicao_vai_ao_papel_e_nao_a_peca(casa):
    """O oficial escreve um encerramento para todo o Protesto: o termo o
    recebe (é papel), e a frase do fecho não (é peça — entraria no meio da
    certidão)."""
    import modelos_elementos as ELEM
    con = _con(casa)
    with con:
        ELEM.salvar(con, atribuicao="PROTESTO", ato="", parte="ENCERRAMENTO",
                    corpo="Encerramento de ensaio.", quem="mario", agora="a")
    assert MOD.texto_do_papel(con, "PT_TERMO_PROTESTO").endswith(
        "Encerramento de ensaio.")
    assert MOD.texto_do_papel(con, "PT_CERTIDAO_FECHO_UM") == MOD.padrao_de(
        "PT_CERTIDAO_FECHO_UM")


def test_o_vocabulario_vale_so_com_os_nomes_do_padrao():
    """A leitura: «nome = texto»; linha sem `=` não é rótulo; o primeiro
    nome repetido vale; o espaço em volta do texto não conta."""
    assert PECAS._rotulos("a = um\nsem igual\n b=dois \na = outro\n= nada") == {
        "a": "um", "b": "dois"}


def _espiar_o_papel(casa, monkeypatch) -> list:
    """O HTML que as rotas do protesto entregam ao `.odt` — e o protesto ligado."""
    import atribuicoes_web as AW
    casa["db"].set_settings({"modulo_protesto_ligado": "1"})
    vistos: list = []
    real = AW.html_para_odf

    def espiao(html, *a, **k):
        vistos.append(html)
        return real(html, *a, **k)
    monkeypatch.setattr(AW, "html_para_odf", espiao)
    return vistos


def test_a_moldura_dos_papeis_impressos_sai_igual_a_de_antes(casa, monkeypatch):
    """Título e número da certidão e do instrumento, local e data, o rodapé
    de autenticidade, o «DESTAQUE AQUI» do canhoto, a folha dos editais e o
    cabeçalho e as colunas dos livros saíram de `atribuicoes_web.py` para a
    peça `PT_MOLDURAS` — e o papel de cada rota é o mesmo, byte a byte."""
    vistos = _espiar_o_papel(casa, monkeypatch)
    con = _con(casa)
    with con:
        semeado = OURO_E.semear_molduras(con)
    antes = OURO_E.ouro_das_molduras()
    rotas = OURO_E.rotas_das_molduras(semeado)
    assert set(rotas) == set(antes)
    for nome, rota in rotas.items():
        vistos.clear()
        r = casa["cliente"].get(rota)
        assert {"status": r.status_code, "html": vistos} == _ouro_e_de_hoje(
            "molduras", nome, antes[nome]), nome


def test_a_moldura_editada_na_tela_vai_ao_papel_impresso(casa, monkeypatch):
    """O oficial troca o título do instrumento; o rodapé, que ele não tocou,
    continua o do padrão."""
    vistos = _espiar_o_papel(casa, monkeypatch)
    _gravar(casa, "PT_MOLDURAS",
            "instrumento_titulo = INSTRUMENTO PÚBLICO DE PROTESTO")
    con = _con(casa)
    with con:
        semeado = OURO_E.semear_molduras(con)
    r = casa["cliente"].get(OURO_E.rotas_das_molduras(semeado)["instrumento"])
    assert r.status_code == 200
    assert "<b>INSTRUMENTO PÚBLICO DE PROTESTO</b>" in vistos[0]
    assert "Instrumento n. 3/2026, emitido em 2026-09-16T10:00:00. Autenticidade: def456" in vistos[0]


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


# ============================================ A BASE DOS PADRÕES — LF06A
#
#   «Não deveríamos ter modelos no código; deveriam estar no banco, para
#    editar com mais facilidade.» — o oficial, 19/10/2026.
#
# O texto de fábrica dos 41 papéis saiu de catorze módulos para a pasta
# `modelos_padrao/`, e de lá para a base dos padrões (um schema do PostgreSQL
# separado do da casa). **A PROVA DE QUE NADA MUDOU É O OURO**, gravado ANTES
# da mudança, das constantes que ainda existiam (`fixtures/modelos_ouro/`): o
# texto, byte a byte, e o papel montado, saída por saída.

import hashlib                                                   # noqa: E402
import importlib                                                 # noqa: E402
import importlib.util                                            # noqa: E402
import json                                                      # noqa: E402
import os                                                        # noqa: E402
import secrets                                                   # noqa: E402
import shutil                                                    # noqa: E402
import threading                                                 # noqa: E402

import banco_pg                                                  # noqa: E402
from bd_nativo import banco                                      # noqa: E402
from modelos_papeis import pasta as PASTA                        # noqa: E402

_ESPEC = importlib.util.spec_from_file_location(
    "ouro_lf06a", RAIZ / "tests" / "fixtures" / "modelos_ouro" / "ouro_lf06a.py")
OURO = importlib.util.module_from_spec(_ESPEC)
_ESPEC.loader.exec_module(OURO)

# O ouro do LF06C (os papéis do Registro Civil), um por grupo de módulos.
_ESPEC_C = importlib.util.spec_from_file_location(
    "ouro_lf06c", RAIZ / "tests" / "fixtures" / "modelos_ouro" / "ouro_lf06c.py")
OURO_C = importlib.util.module_from_spec(_ESPEC_C)
_ESPEC_C.loader.exec_module(OURO_C)


@pytest.fixture(scope="module")
def ouro():
    return OURO.ouro()


# O QUE MUDOU DE PROPÓSITO DEPOIS DO OURO DO LF06A — e só isto.
#
#   «TERMO E CERTIDÃO» — o oficial, 20/10/2026 (LT02). A certidão de inteiro
#   teor das Notas passou a dizer o termo do ato, a reproduzir o selo do ato
#   com o que o selo declara (o teor diz «Emolumentos e selo de fiscalização
#   ao final do ato», e a certidão não os mostrava) e a escrever «nele
#   encontrei o ato de …, lavrado em» (saía «substabelecimento lavrada»,
#   «testamento público lavrada»). O OURO NÃO SE REGERA: os testes de baixo
#   aplicam ao texto de antes exatamente estas trocas — cada uma achada uma
#   vez só — e exigem o resto byte a byte. Outra diferença continua vermelha.
_TERMO_DO_ATO_LT02 = ("{% if a.termo %}, termo n. {{ a.termo }}{% elif "
                      "a.numero_ordem %}, ordem n. {{ a.numero_ordem }}{% endif %}")
MUDOU_DEPOIS_DO_OURO = {
    "NOTAS_CERTIDAO_INTEIRO_TEOR": {
        "texto": (
            ("{% endif %}, deste Tabelionato de Notas, nele encontrei "
             "{{ rotulo_tipo|lower }} lavrada em",
             "{% endif %}" + _TERMO_DO_ATO_LT02 + ", deste Tabelionato de Notas, "
             "nele encontrei o ato de {{ rotulo_tipo|lower }}, lavrado em"),
            ("<p>«{{ teor }}»</p>\n",
             "<p>«{{ teor }}»</p>\n{% for s in selos_do_ato or [] %}<p><b>SELO DE "
             "FISCALIZAÇÃO DO ATO:</b> {{ s }}</p>{% endfor %}\n"),
        ),
        # o papel montado (prévia e montador): sem termo e sem selo no
        # contexto de ensaio, só a frase e a linha do selo, vazia
        "papel": (
            ("nele encontrei [rotulo_tipo] lavrada em",
             "nele encontrei o ato de [rotulo_tipo], lavrado em"),
            ("»</p>\n<p><b>ANOTAÇÕES", "»</p>\n\n<p><b>ANOTAÇÕES"),
        ),
    },
    # LD01 (21/10/2026), «corrija tudo» — os defeitos que os LT acharam no
    # RCPN. O termo de nascimento ganhou dois claros: `{frase_natimorto}` («nasceu
    # morta», LRP art. 53, § 1º, e art. 54, 5º — o natimorto se lavra por este
    # modelo) e `{testemunhas}` (as duas do parto sem assistência médica, LRP
    # art. 54, 9º; CN-MA art. 233, IX). Vazios, o texto montado é o de antes.
    "RC_TERMO_NASCIMENTO": {
        "texto": (("nasceu uma criança", "nasceu{frase_natimorto} uma criança"),
                  ("{frase_cpf} Lido e achado", "{frase_cpf}{testemunhas} Lido e achado")),
        "papel": (("nasceu uma criança", "nasceu[frase natimorto] uma criança"),
                  ("[frase cpf] Lido e achado",
                   "[frase cpf][testemunhas] Lido e achado")),
    },
    # LD01: o termo de casamento diz a data da celebração (LRP art. 70, 4º;
    # CN-MA art. 284, IV) — começava «Em <data do ato>» e calava a do fato.
    "RC_TERMO_CASAMENTO": {
        "texto": (("declarados casados sob", "declarados casados{frase_da_celebracao} sob"),),
        "papel": (("declarados casados sob",
                   "declarados casados[frase da celebracao] sob"),),
    },
}
# O REGISTRO TARDIO (LH05, 21/10/2026 — os hotfixes «registro tardio» 1 e 2 do
# servidor): o termo de nascimento ganhou o claro `{frase_tardio}` («Registro
# lavrado fora do prazo legal…», LRP art. 46; CN-MA art. 249), entre o CPF e
# as testemunhas do LD01. Vazio — todo registro dentro do prazo —, o texto
# montado é o de antes. Troca achada uma vez só, por cima das do LD01.
_LH05_TARDIO = {
    "texto": (("{frase_cpf}{testemunhas} Lido",
               "{frase_cpf}{frase_tardio}{testemunhas} Lido"),),
    "papel": (("[frase cpf][testemunhas] Lido",
               "[frase cpf][frase tardio][testemunhas] Lido"),),
}
MUDOU_DEPOIS_DO_OURO["RC_TERMO_NASCIMENTO"] = {
    k: MUDOU_DEPOIS_DO_OURO["RC_TERMO_NASCIMENTO"][k] + _LH05_TARDIO[k]
    for k in ("texto", "papel")}
# A FICHA DO CARTÃO DE FIRMA traz a data de emissão da identidade (LD02,
# 21/10/2026): o art. 864, § 1º, IV, do Código de Normas pede o RG «junto com a
# data de emissão», e a ficha não tinha a linha. Uma linha nova, logo abaixo da
# identidade — vazia no papel quando o cartão não a tem, para a caneta.
_LINHA_DA_IDENTIDADE = '<tr><td><b>Identidade</b></td><td>{{ identidade or "&#160;" }}</td></tr>\n'
_LINHA_DA_EMISSAO = ('<tr><td><b>Emissão da identidade</b></td><td>'
                     '{{ rg_emissao or "&#160;" }}</td></tr>\n')
MUDOU_DEPOIS_DO_OURO["NOTAS_CARTAO_FICHA"] = {
    "texto": ((_LINHA_DA_IDENTIDADE, _LINHA_DA_IDENTIDADE + _LINHA_DA_EMISSAO),),
    "papel": (("<tr><td><b>Identidade</b></td><td>[identidade]</td></tr>\n",
               "<tr><td><b>Identidade</b></td><td>[identidade]</td></tr>\n"
               "<tr><td><b>Emissão da identidade</b></td><td>[rg_emissao]</td></tr>\n"),),
}
# E O RESTO DO ART. 864, § 1º, NA FICHA (LD07, 21/10/2026, «corrija tudo»): a
# data de abertura (I — a impressa era só a do dia da impressão), o título
# eleitoral (III) e a firma «ao menos três vezes» (V; art. 867): cada forma de
# assinar ganhou mais duas linhas, com o espaço menor `espaco_curto`. Por cima
# das do LD02, cada troca achada uma vez só.
_FORMAS_DE_ASSINAR = ("(como o nome é assinado por inteiro)", "(a forma curta, se houver)",
                      "(para folhas e vias)")
MUDOU_DEPOIS_DO_OURO["NOTAS_CARTAO_FICHA"] = {
    "texto": MUDOU_DEPOIS_DO_OURO["NOTAS_CARTAO_FICHA"]["texto"] + (
        ("— Ficha nº {{ numero }}</p>",
         "— Ficha nº {{ numero }}{% if data_abertura %}, aberta em {{ data_abertura }}"
         "{% endif %}</p>"),
        ('<tr><td><b>Nascimento</b></td><td>{{ nascimento or "&#160;" }}</td></tr>\n',
         '<tr><td><b>Nascimento</b></td><td>{{ nascimento or "&#160;" }}</td></tr>\n'
         '<tr><td><b>Título eleitoral</b></td><td>{{ titulo_eleitor or "&#160;" }}</td></tr>\n'),
        ("assino na presença do escrevente as formas",
         "assino na presença do escrevente, três vezes cada uma, as formas"),
    ) + tuple((f"{forma}</span></p>\n{{{{ espaco }}}}{{{{ linha }}}}\n",
               f"{forma}</span></p>\n{{{{ espaco }}}}{{{{ linha }}}}{{{{ espaco_curto }}}}"
               "{{ linha }}{{ espaco_curto }}{{ linha }}\n") for forma in _FORMAS_DE_ASSINAR),
    "papel": MUDOU_DEPOIS_DO_OURO["NOTAS_CARTAO_FICHA"]["papel"] + (
        ("— Ficha nº [numero]</p>", "— Ficha nº [numero], aberta em [data_abertura]</p>"),
        ("<tr><td><b>Nascimento</b></td><td>[nascimento]</td></tr>\n",
         "<tr><td><b>Nascimento</b></td><td>[nascimento]</td></tr>\n"
         "<tr><td><b>Título eleitoral</b></td><td>[titulo_eleitor]</td></tr>\n"),
        ("assino na presença do escrevente as formas",
         "assino na presença do escrevente, três vezes cada uma, as formas"),
    ) + tuple((f"{forma}</span></p>\n[espaco][linha]\n",
               f"{forma}</span></p>\n[espaco][linha][espaco_curto][linha][espaco_curto]"
               "[linha]\n") for forma in _FORMAS_DE_ASSINAR),
}
# E QUEM CONFERIU O PREENCHIMENTO, AO PÉ DA FICHA (LH13, 21/10/2026): o CN-MA
# art. 864, § 1º, VI, pede «nome, assinatura e carimbo» do preposto que
# verificou o preenchimento, e o oficial respondeu «9 b» — «Preenchimento
# conferido por: NOME — função», com a linha da assinatura e do carimbo, do
# escrevente que abriu o cartão. Três linhas novas depois do «titular do
# cartão», que continua o fim da parte do cliente; por cima do LD07. (O papel
# da prévia vem sem o fim de linha do arquivo.)
_FIM_DO_TITULAR = '<p align="center">o titular do cartão</p>'
_QUEM_CONFERIU_LH13 = {
    "texto": (_FIM_DO_TITULAR + "\n", _FIM_DO_TITULAR + (
        '\n<p><b>Preenchimento conferido por:</b> {% if conferente_nome %}'
        '{{ conferente_nome }}{% if conferente_funcao %} — {{ conferente_funcao }}'
        '{% endif %}{% else %}________________________________ — ____________________'
        '{% endif %}</p>\n'
        '{{ espaco }}{{ linha }}\n'
        '<p align="center">assinatura e carimbo de quem conferiu o preenchimento</p>\n')),
    "papel": (_FIM_DO_TITULAR, _FIM_DO_TITULAR + (
        '\n<p><b>Preenchimento conferido por:</b> [conferente_nome] — [conferente_funcao]</p>\n'
        '[espaco][linha]\n'
        '<p align="center">assinatura e carimbo de quem conferiu o preenchimento</p>')),
}
MUDOU_DEPOIS_DO_OURO["NOTAS_CARTAO_FICHA"] = {
    k: MUDOU_DEPOIS_DO_OURO["NOTAS_CARTAO_FICHA"][k] + (_QUEM_CONFERIU_LH13[k],)
    for k in ("texto", "papel")}
# A CERTIDÃO POSITIVA DAS NOTAS diz o termo de cada ato achado (LD07): a
# localização do ato é livro, folha E número (CN-MA arts. 792 e 851, § 1º). O
# acervo sem termo traz a ordem, como o inteiro teor (`_TERMO_DO_ATO_LT02`).
# Sem termo no achado, o papel é o de antes — a prévia e o montador do ouro
# não mudam.
MUDOU_DEPOIS_DO_OURO["NOTAS_CERTIDAO_POSITIVA"] = {
    "texto": (("folha {{ x.folha or '—' }}, de {{ x.data }}",
               "folha {{ x.folha or '—' }}{% if x.termo %}, termo n. {{ x.termo }}{% elif "
               "x.numero_ordem %}, ordem n. {{ x.numero_ordem }}{% endif %}, de "
               "{{ x.data }}"),),
}
# O RECIBO DO DEPÓSITO PRÉVIO diz que a discriminação é ORÇAMENTO (LD06,
# 21/10/2026): ele passou a trazer o orçamento congelado no depósito, e o
# título da discriminação diz que ela é dos valores previstos para o serviço,
# e não do que se pagou de ato praticado (CN-MA art. 197). O recibo de
# pagamento não muda — `orcamento` só vem verdadeiro do depósito
# (`caixa_web.caixa_recibo`). Na prévia o boneco é verdadeiro, e o título sai
# inteiro. Fora do dicionário, como a ficha do cartão: a última linha dele é
# disputada pelos lotes que entram juntos.
MUDOU_DEPOIS_DO_OURO["CAIXA_RECIBO"] = {
    "texto": (
        ("<p><b>DISCRIMINAÇÃO</b></p>\n",
         "<p><b>DISCRIMINAÇÃO{% if orcamento %} ORÇAMENTÁRIA — valores previstos "
         "para o serviço requerido (CN-MA art. 197){% endif %}</b></p>\n"),
    ),
    "papel": (
        ("<p><b>DISCRIMINAÇÃO</b></p>",
         "<p><b>DISCRIMINAÇÃO ORÇAMENTÁRIA — valores previstos para o serviço "
         "requerido (CN-MA art. 197)</b></p>"),
    ),
}
MONTADORES_MUDADOS_DEPOIS_DO_OURO = {
    "notas_certidao.montar_teor(INTEIRO_TEOR)": (
        ("nele encontrei procuração lavrada em",
         "nele encontrei o ato de procuração, lavrado em"),
        ("»</p>\n<p><b>ANOTAÇÕES", "»</p>\n\n<p><b>ANOTAÇÕES"),
    ),
    # LD01 — os mesmos claros novos dos dois termos, acima: no texto de
    # fábrica e no formulário montado com cada claro escrito «[claro]».
    "rc_modelos_do_livro.modelo(NASCIMENTO)[texto]":
        MUDOU_DEPOIS_DO_OURO["RC_TERMO_NASCIMENTO"]["texto"],
    "rc_modelos_do_livro.modelo(CASAMENTO)[texto]":
        MUDOU_DEPOIS_DO_OURO["RC_TERMO_CASAMENTO"]["texto"],
    "rc_modelos_do_livro.montar_do_formulario(NASCIMENTO)": (
        ("nasceu uma criança", "nasceu[frase_natimorto] uma criança"),
        ("[frase_cpf] Lido e achado", "[frase_cpf][testemunhas] Lido e achado")),
    "rc_modelos_do_livro.montar_do_formulario(CASAMENTO)": (
        ("declarados casados sob", "declarados casados[frase_da_celebracao] sob"),),
}
# LH05 — o claro do registro tardio no formulário montado (o texto de fábrica,
# `modelo(NASCIMENTO)[texto]`, já leva as trocas de `MUDOU_DEPOIS_DO_OURO`).
MONTADORES_MUDADOS_DEPOIS_DO_OURO["rc_modelos_do_livro.montar_do_formulario(NASCIMENTO)"] += (
    ("[frase_cpf][testemunhas] Lido e achado",
     "[frase_cpf][frase_tardio][testemunhas] Lido e achado"),)


def _com_as_trocas(antes, trocas):
    """O texto de antes com as trocas declaradas — cada uma achada UMA vez.

    A saída que não é texto (o dicionário de `montar_do_formulario`, LD01) se
    troca na forma gravada (JSON): a troca vale dentro dela do mesmo jeito, e
    continua tendo de se achar uma vez só."""
    if not isinstance(antes, str):
        return json.loads(_com_as_trocas(json.dumps(antes, ensure_ascii=False),
                                         trocas))
    for velho, novo in trocas:
        assert antes.count(velho) == 1, f"a troca declarada não se acha uma vez: {velho!r}"
        antes = antes.replace(velho, novo)
    return antes


def _texto_de_hoje(chave: str, antes: str) -> str:
    return _com_as_trocas(antes, MUDOU_DEPOIS_DO_OURO.get(chave, {}).get("texto", ()))


def test_o_que_mudou_depois_do_ouro_e_papel_do_ouro():
    """A lista das mudanças de propósito só fala de papel que o ouro guarda —
    senão ela seria uma porta aberta, e não um registro."""
    textos = OURO.ouro()["textos"]
    assert set(MUDOU_DEPOIS_DO_OURO) <= set(textos)
    assert set(MONTADORES_MUDADOS_DEPOIS_DO_OURO) <= set(OURO.ouro()["funcoes"])


@pytest.fixture()
def schema_de_ensaio():
    """Uma base de padrões SÓ DESTE TESTE, apagada no fim.

    A base de verdade é uma por banco e todos os processos da suíte a leem; um
    teste que a apagasse e recriasse derrubaria a leitura de outro no meio.
    """
    nome = f"modelos_padrao_ensaio_{os.getpid()}_{secrets.token_hex(3)}"
    yield nome
    import psycopg
    with psycopg.connect(banco_pg.dsn(), autocommit=True) as pg:
        pg.execute(f'DROP SCHEMA IF EXISTS "{nome}" CASCADE')


def _pasta_de_ensaio(destino: Path, *chaves: str) -> Path:
    """Uma pasta dos padrões com alguns papéis de verdade, copiados."""
    for chave in chaves:
        origem = RAIZ / MOD.POR_CHAVE[chave]["arquivo"]
        alvo = destino / origem.parent.name
        alvo.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origem, alvo / origem.name)
        shutil.copyfile(origem.with_suffix(".json"), alvo / f"{chave}.json")
    PASTA.esquecer()
    return destino


# ------------------------------------------------ o ouro: nada mudou


def _frases_do_ri_lf06b() -> set[str]:
    """As frases do RI que o LF06B tirou do código — o ouro delas é o do LF06B."""
    return {c["chave"] for c in MOD.CATALOGO if c["padrao"][0] == "ri_frases"}


def test_o_ouro_foi_gravado_antes_da_mudanca_e_cobre_os_41_papeis(ouro):
    """O ouro é do commit de ANTES (90704fc) e tem os 41 — nem um a menos,
    senão o «nada mudou» valeria só para os que sobraram.

    Os papéis que entraram DEPOIS do LF06A têm o ouro do lote deles
    (`ouro_lf06g`, `ouro_lf06b`, `ouro_lf06c`…): este cobre os 41 que existiam, e todos continuam no
    catálogo."""
    assert ouro["commit"] == "90704fc"
    assert len(ouro["textos"]) == 41
    assert set(ouro["textos"]) <= set(MOD.POR_CHAVE)
    assert set(ouro["previa"]) == set(ouro["textos"])
    assert len(ouro["funcoes"]) == 36


def test_o_texto_lido_da_base_e_byte_a_byte_o_da_constante_de_antes(casa, ouro):
    """O TESTE-OURO. Lido DIRETO da tabela da base, e não pelo cache do
    processo: o que está gravado lá é o que estava no código."""
    MOD.carregar_base()
    linhas = banco(_con(casa)).ler(
        f'SELECT chave, corpo, impressao_digital FROM "{MOD.schema_da_base()}".padroes '
        "ORDER BY chave")
    na_base = {r["chave"]: r for r in linhas}
    # a base tem também os papéis e as peças dos lotes seguintes (LF06G, LF06B, LF06C…)
    assert set(ouro["textos"]) <= set(na_base)
    for chave, antes in ouro["textos"].items():
        antes = _texto_de_hoje(chave, antes)
        depois = na_base[chave]["corpo"]
        assert depois.encode("utf-8") == antes.encode("utf-8"), chave
        assert na_base[chave]["impressao_digital"] == hashlib.sha256(
            antes.encode("utf-8")).hexdigest(), chave
        assert MOD.padrao_de(chave) == antes, chave


def test_o_arquivo_da_pasta_tem_os_mesmos_bytes_da_constante_de_antes(ouro):
    for chave, antes in ouro["textos"].items():
        arquivo = RAIZ / MOD.POR_CHAVE[chave]["arquivo"]
        assert arquivo.read_bytes() == _texto_de_hoje(chave, antes).encode("utf-8"), chave


def test_o_papel_montado_pela_previa_sai_igual_ao_de_antes(ouro):
    """O papel montado com o contexto de ensaio da casa (`modelos_previa`,
    sem dado de ninguém), lido da base, contra o montado antes da mudança."""
    import modelos_previa as PREVIA
    for chave, antes in ouro["previa"].items():
        documento, erro = PREVIA.renderizar(chave, [MOD.padrao_de(chave), "", ""])
        antes = dict(antes, documento=_com_as_trocas(
            antes["documento"], MUDOU_DEPOIS_DO_OURO.get(chave, {}).get("papel", ())))
        assert {"documento": documento, "erro": erro} == antes, chave


def test_os_montadores_que_caem_no_padrao_saem_iguais_aos_de_antes(ouro):
    """Os montadores puros chamados SEM modelo — o caminho em que eles caíam na
    constante e agora caem na base. Mesmas chamadas do gerador do ouro."""
    chamadas = OURO.chamadas()
    assert set(chamadas) == set(ouro["funcoes"])
    for nome, f in chamadas.items():
        esperado = ouro["funcoes"][nome]
        if nome in MONTADORES_MUDADOS_DEPOIS_DO_OURO:
            esperado = {"ok": _com_as_trocas(
                esperado["ok"], MONTADORES_MUDADOS_DEPOIS_DO_OURO[nome])}
        assert OURO.normal(OURO.tenta(f)) == esperado, nome


def test_sem_ajuste_a_busca_unica_devolve_o_ouro(casa, ouro):
    """`texto_do_papel` — ajuste da casa → base → erro — sem ajuste nenhum é o
    texto de antes, pelo caminho inteiro (elementos, legado, base)."""
    con = _con(casa)
    for chave, antes in ouro["textos"].items():
        assert MOD.texto_do_papel(con, chave) == _texto_de_hoje(chave, antes), chave


# ------------------------------------------------ a pasta


def test_a_pasta_tem_um_txt_e_um_json_por_papel_e_nada_sobra():
    """Arquivo a mais seria papel que ninguém emite; a menos, papel sem
    padrão. E `problemas` vazio: nenhuma ficha torta, nenhum corpo vazio.

    **A PEÇA É `.txt`, COM OU SEM `.json`** (LF06G, LF06D): sem ficha, ela
    herda a do papel; com ficha, a dela diz quando a regra a escolhe. E o papel
    dela tem de estar no catálogo — peça de papel que não existe seria frase
    que ninguém imprime. As MINUTAS das Notas (`notas/minutas/`, LF06D) têm
    corpo e ficha, e minuta que o código não conhece também é arquivo a mais."""
    import notas_modelos as NM
    pasta = RAIZ / "modelos_padrao"
    txt = {p.stem: p for p in pasta.rglob("*.txt")}
    js = {p.stem for p in pasta.rglob("*.json")}
    minutas = {p.stem for p in (pasta / "notas" / "minutas").glob("*.txt")}
    assert minutas == {m["codigo"] for m in NM.MINUTAS}
    pecas = {t for t in txt if PASTA.SEPARADOR_DE_PECA in t}
    assert js <= set(txt)
    assert set(txt) - pecas - minutas == js - pecas - minutas == set(MOD.POR_CHAVE)
    for peca in pecas:
        papel, _, nome = peca.partition(PASTA.SEPARADOR_DE_PECA)
        assert papel in MOD.POR_CHAVE and nome == nome.lower(), peca
        # e mora na pasta do papel dela (LF06C)
        assert txt[peca].parent.name == MOD.POR_CHAVE[papel]["pasta"], peca
    assert {p.suffix for p in pasta.rglob("*")
            if p.is_file() and not p.name.startswith(".")} == {".txt", ".json"}
    PASTA.esquecer()
    assert PASTA.ler_pasta()["problemas"] == []


def test_a_ficha_da_pasta_e_a_que_o_catalogo_mostra():
    """**A FICHA MORA NUM LUGAR SÓ** — o `.json`. O catálogo a lê, e a pasta de
    cada papel é a da atribuição dele no `modelos_papeis`."""
    for c in MOD.CATALOGO:
        modulo = importlib.import_module(f"modelos_papeis.{c['pasta']}")
        ficha = json.loads((RAIZ / c["arquivo"]).with_suffix(".json").read_text(
            encoding="utf-8"))
        assert ficha["chave"] == c["chave"]
        assert ficha["atribuicao"] == c["atribuicao"] == modulo.ATRIBUICAO
        assert ficha["nome"] == c["nome"] and ficha["explica"] == c["explica"]
        assert ficha["formato"] == MOD.formato_de(c["chave"])
        assert ficha["formato"] in (MOD.JINJA, MOD.CHAVES)
        assert isinstance(ficha["campos"], list)
        for campo in ficha["campos"]:
            assert campo in MOD.padrao_de(c["chave"]), (c["chave"], campo)


def test_rcpj_e_rtd_certidao_continuam_o_mesmo_texto():
    """Os dois nasceram da MESMA constante (`MODELO_CERTIDAO_RCPJ_RTD`), e o
    montador sem modelo usa o do RCPJ. Se um dia divergirem, alguém tem de
    decidir qual vale para quem — e este teste avisa."""
    assert MOD.padrao_de("RCPJ_CERTIDAO") == MOD.padrao_de("RTD_CERTIDAO")


# ============================================ RCPJ/RTD E CAIXA FORA DO CÓDIGO — LF06F
#
#   «Não deveríamos ter modelos no código; deveriam estar no banco, para
#    editar com mais facilidade.» — o oficial, 19/10/2026.
#
# A segunda leva: o que o inventário do LF06A deixou para o RCPJ/RTD e o caixa.
# Papel inteiro virou papel do catálogo; frase que uma REGRA escolhe virou
# peça (`<CHAVE>__<peca>.txt`) ou parte (===PARTE===) de um papel, e a regra
# ficou no código. **A PROVA DE QUE NADA MUDOU É O OURO DO LOTE**, gravado na
# árvore de antes (2c41e90): o que os montadores devolviam e o que as telas
# imprimiam, com o banco de teste.

_ESPEC_F = importlib.util.spec_from_file_location(
    "ouro_lf06f", RAIZ / "tests" / "fixtures" / "modelos_ouro" / "ouro_lf06f.py")
OURO_F = importlib.util.module_from_spec(_ESPEC_F)
_ESPEC_F.loader.exec_module(OURO_F)

LF06F_PAPEIS = {
    "RCPJ_RTD_CERTIDAO_SO_AVERBACOES", "RCPJ_RTD_CERTIDAO_ODT", "RCPJ_RTD_NOTA",
    "RCPJ_RTD_ETIQUETA", "RCPJ_RTD_ETIQUETA_SELO_EXTERNO",
    "RCPJ_RTD_PDF_MOLDURA", "CAIXA_WHATSAPP"}
LF06F_PECAS = {
    "RCPJ_CERTIDAO__onde", "RCPJ_CERTIDAO__onde_folha", "RCPJ_CERTIDAO__onde_ato",
    "RCPJ_CERTIDAO__onde_data", "RCPJ_CERTIDAO__registro_rcpj",
    "RCPJ_CERTIDAO__registro_rtd", "RCPJ_CERTIDAO__registro",
    "RCPJ_CERTIDAO__averbacao", "RCPJ_CERTIDAO__cancelado",
    "RCPJ_RTD_ETIQUETA_SELO_EXTERNO__manual",
    "RCPJ_RTD_ETIQUETA_SELO_EXTERNO__razao", "CAIXA_ORCAMENTO__aviso"}

# **EM 19/10/2026 ENTRARAM SETE NO CATÁLOGO (LF06F)**: os papéis do RCPJ/RTD
# e do caixa que ainda moravam no código — «Não deveríamos ter modelos no
# código» é o pedido. A certidão só de averbações (que não tinha chave, e por
# isso nenhum ajuste a alcançava), o papel da certidão por texto, a nota
# devolutiva e as duas etiquetas (que eram templates), as frases do desenho
# dos PDFs e os rascunhos do WhatsApp. O ouro deles é o `LF06F_papeis.json`.
# As peças não contam: não são linhas do catálogo.
NOVOS_NO_CATALOGO_LF06F = 7


@pytest.fixture(scope="module")
def ouro_f():
    return OURO_F.ouro()


def test_o_ouro_do_lf06f_foi_gravado_antes_da_mudanca(ouro_f):
    """Do commit de ANTES, e com as MESMAS chamadas que o teste refaz — senão o
    «nada mudou» valeria só para o que sobrou na lista."""
    assert ouro_f["commit"] == OURO_F.COMMIT_DE_ANTES == "2c41e90"
    assert set(OURO_F.chamadas()) == set(ouro_f["funcoes"])
    assert set(OURO_F.chamadas_com_casa()) == set(ouro_f["telas"])
    assert len(ouro_f["funcoes"]) == 82 and len(ouro_f["telas"]) == 16
    assert all("ok" in v for v in ouro_f["telas"].values())


def test_os_montadores_do_rcpj_rtd_e_do_caixa_saem_iguais_aos_de_antes(ouro_f):
    """O teor da certidão, a intro e o encerramento do teor, o que o desenho
    dos PDFs escreve, o aviso do orçamento e os rascunhos do WhatsApp — sem
    ajuste da casa, byte a byte o que o código montava antes."""
    for nome, f in OURO_F.chamadas().items():
        assert OURO_F.normal(OURO_F.tenta(f)) == ouro_f["funcoes"][nome], nome


@pytest.mark.parametrize("nome", sorted(OURO_F.chamadas_com_casa()))
def test_as_telas_do_rcpj_rtd_e_do_caixa_saem_iguais_as_de_antes(casa, monkeypatch,
                                                                  ouro_f, nome):
    """A nota devolutiva, as etiquetas, a certidão em `.odt`, o objeto do PDF da
    certidão e o orçamento, montados pela rota com o banco de teste — o que a
    folha leva é o mesmo de antes (o dia de hoje vira «HOJE» dos dois lados)."""
    depois = OURO_F.tenta(lambda: OURO_F.chamadas_com_casa()[nome](casa, monkeypatch))
    assert OURO_F.normal(depois) == ouro_f["telas"][nome], nome


def test_os_papeis_do_lf06f_estao_na_pasta_no_catalogo_e_na_base():
    """Sete papéis novos no catálogo (editáveis na tela de Modelos) e as peças
    na pasta, herdando a ficha do papel. A base carrega os dois."""
    assert len(LF06F_PAPEIS) == NOVOS_NO_CATALOGO_LF06F
    assert LF06F_PAPEIS <= set(MOD.POR_CHAVE)
    lida = PASTA.ler_pasta()["padroes"]
    for chave in LF06F_PAPEIS | LF06F_PECAS:
        assert chave in lida, chave
        assert MOD.padrao_de(chave) == lida[chave]["corpo"], chave
    for peca in LF06F_PECAS:
        papel = peca.split("__")[0]
        assert lida[peca]["peca_de"] == papel
        assert lida[peca]["formato"] == MOD.formato_de(papel)
        # o ajuste da casa é gravado com `strip()`: o espaço que cola a peça
        # à frase anterior é do código, senão sairia no primeiro ajuste
        assert lida[peca]["corpo"] == lida[peca]["corpo"].strip(), peca
    # os quatro em HTML não herdam o fecho da atribuição, que é toda em chaves
    for chave in ("RCPJ_RTD_CERTIDAO_ODT", "RCPJ_RTD_NOTA", "RCPJ_RTD_ETIQUETA",
                  "RCPJ_RTD_ETIQUETA_SELO_EXTERNO", "RCPJ_RTD_PDF_MOLDURA",
                  "CAIXA_WHATSAPP"):
        assert MOD.POR_CHAVE[chave]["elementos_comuns"] is False, chave


def test_cada_papel_do_lf06f_tem_conferidor_proprio_e_o_padrao_passa_nele(casa):
    """O boneco geral da tela de Modelos não tem `t`, `e` nem `c`: sem
    conferidor próprio, o papel em HTML seria recusado com qualquer claro —
    editável só no nome —, e o de chaves aprovaria um claro inventado que só
    estouraria na emissão. Cada um confere com a montagem da própria emissão."""
    conferidores = casa["app"].extensions["conferidores_de_modelo"]
    for chave in LF06F_PAPEIS:
        assert chave in conferidores, chave
        assert conferidores[chave](MOD.padrao_de(chave)) == "", chave


@pytest.mark.parametrize("chave,torto", [
    ("RCPJ_RTD_PDF_MOLDURA", "===PAGINA===\nFolha {inventado}"),
    ("RCPJ_RTD_CERTIDAO_SO_AVERBACOES", "CERTIFICO {onde} e {inventado}"),
    ("CAIXA_WHATSAPP", "===HORARIO===\nOla {inventado}"),
    ("RCPJ_RTD_NOTA", "<p>{{ t.numero }}{% if %}</p>"),
])
def test_a_tela_recusa_o_papel_do_lf06f_que_nao_monta(casa, chave, torto):
    r = _gravar(casa, chave, torto)
    assert "não foi gravado" in r.get_data(as_text=True), chave
    assert not MOD.esta_ajustado(_con(casa), chave)


def test_o_texto_das_frases_saiu_dos_modulos():
    """Nenhuma das frases ficou escrita uma segunda vez no código: o nome antigo
    responde pelo `__getattr__`, com o texto da base."""
    import atrib_certidao
    import caixa_schema
    import rg_teor_rtdpj
    for modulo, nome in ((atrib_certidao, "MODELO_CERTIDAO_RCPJ_RTD_SO_AVERBACOES"),
                         (atrib_certidao, "NOME_DO_REGISTRO"),
                         (caixa_schema, "AVISO_ORCAMENTO"),
                         (rg_teor_rtdpj, "SELO_FAIXA_ROTULO"),
                         (rg_teor_rtdpj, "SELO_FAIXA_ROTULO_ARQUIVAMENTO")):
        assert nome not in vars(modulo), f"{modulo.__name__}.{nome}"
    assert caixa_schema.AVISO_ORCAMENTO == MOD.padrao_de("CAIXA_ORCAMENTO__aviso")
    assert rg_teor_rtdpj.SELO_FAIXA_ROTULO == "selo averbação"
    codigo = "\n".join((RAIZ / f).read_text(encoding="utf-8") for f in (
        "atrib_certidao.py", "rg_teor_rtdpj.py", "rg_certidao_pdf.py", "wa_textos.py",
        "caixa_schema.py", "rg_web.py"))
    for frase in ("MERO CÁLCULO DE EMOLUMENTOS", "ao qual constam as seguintes",
                  "Oficio unico de", "Nao enviamos pelo WhatsApp",
                  "Era o que continha o documento apresentado",
                  "RCPJ E RTD — SELO ELETRÔNICO", "QR / autenticação"):
        assert frase not in codigo, frase


def test_a_certidao_so_de_averbacoes_segue_o_ajuste_da_casa(casa):
    """**ERA O DEFEITO DA LINHA DO INVENTÁRIO**: sem chave própria, o ajuste da
    casa nunca chegava à certidão só de averbações. Gravado na tela, ele vale."""
    _gravar(casa, "RCPJ_RTD_CERTIDAO_SO_AVERBACOES",
            "AJUSTE DA CASA, {onde}, AVERBAÇÕES:\n\n{teor}")
    ids = OURO_F._registro_rcpj(casa, averbacoes=[
        ("2", "Averbação de exemplo.", "2026-09-01")])
    teor = OURO_F._emitir(casa, ids["registro"], ato_ids=ids["averbacoes"])["teor"]
    assert teor.startswith('AJUSTE DA CASA, no Livro "B-7" de Registro de Títulos')
    assert teor.endswith("--- AVERBAÇÃO n. 2 ---\nAverbação de exemplo.")


def test_a_frase_do_registro_cancelado_e_peca_e_o_ajuste_dela_vale(casa):
    """A REGRA (registro cancelado → a frase entra) é do código; o TEXTO é a
    peça RCPJ_CERTIDAO__cancelado, com o ajuste da casa por cima."""
    con = _con(casa)
    with con:
        MOD.salvar(con, "RCPJ_CERTIDAO__cancelado",
                   corpo="CERTIFICO, AINDA, QUE O REGISTRO ESTÁ CANCELADO.",
                   quem="mario", agora="2026-10-19T09:00")
    ids = OURO_F._registro_rcpj(casa, situacao="CANCELADO")
    teor = OURO_F._emitir(casa, ids["registro"])["teor"]
    assert teor.endswith("\n\nCERTIFICO, AINDA, QUE O REGISTRO ESTÁ CANCELADO.")


def test_a_data_ajustada_continua_separada_do_numero_do_ato(casa):
    """**O AJUSTE DA CASA É GRAVADO COM `strip()`** — a peça « datada de …» da
    primeira volta perdia o espaço no primeiro ajuste, e a certidão sairia com
    «ATO n. 148datada de». O espaço que cola a data é do código."""
    con = _con(casa)
    with con:
        MOD.salvar(con, "RCPJ_CERTIDAO__onde_data", corpo="   com data de {data}  ",
                   quem="mario", agora="2026-10-19T09:00")
    ids = OURO_F._registro_rcpj(casa)
    teor = OURO_F._emitir(casa, ids["registro"])["teor"]
    assert "ATO n. 1508 com data de " in teor


def test_a_peca_ajustada_com_claro_que_nao_existe_vira_frase_de_balcao(casa):
    """Um claro inventado na frase do «onde» recusa a certidão com a frase do
    que está errado — e nada se emite."""
    import atrib_certidao as CE
    con = _con(casa)
    with con:
        MOD.salvar(con, "RCPJ_CERTIDAO__onde", corpo="no livro {inventado}",
                   quem="mario", agora="2026-10-19T09:00")
    ids = OURO_F._registro_rcpj(casa)
    with pytest.raises(CE.CertidaoError) as erro:
        OURO_F._emitir(casa, ids["registro"])
    assert "«onde»" in str(erro.value) and "{livro}" in str(erro.value)


def test_o_papel_da_certidao_por_texto_segue_o_ajuste_da_tela(casa, monkeypatch):
    """O papel em `.odt` era f-string na rota; agora a tela o edita."""
    _gravar(casa, "RCPJ_RTD_CERTIDAO_ODT",
            "<p>PAPEL DA CASA {{ c.numero }}/{{ c.ano }}</p>"
            "{% for bloco in blocos %}<p>{{ bloco }}</p>{% endfor %}")
    con = _con(casa)
    assert banco(con).valor(
        "SELECT count(*) FROM mo_elementos WHERE ato = %s",
        ("RCPJ_RTD_CERTIDAO_ODT",)) == 1, "a tela recusou o papel"
    ids = OURO_F._registro_rcpj(casa)
    cid = OURO_F._emitir(casa, ids["registro"])["certidao_id"]
    odf = OURO_F._odt_da_certidao(casa, cid, monkeypatch)
    assert "PAPEL DA CASA 1/2026" in odf
    assert "Teor de exemplo do registro." in odf


def test_a_nota_devolutiva_segue_o_ajuste_da_tela(casa):
    """A nota era template, que a casa não alcançava; gravada na tela de
    Modelos, é ela que sai — a página em volta (botão de imprimir) é a mesma."""
    _gravar(casa, "RCPJ_RTD_NOTA", "<p>NOTA DEVOLUTIVA DA CASA</p>")
    html = OURO_F._nota(casa, exigencias="Falta a ata de eleição da diretoria.")
    assert "<p>NOTA DEVOLUTIVA DA CASA</p>" in html
    assert "window.print()" in html
    assert "EXIGÊNCIAS A CUMPRIR" not in html


def test_a_nota_escapa_o_texto_livre_como_o_template_escapava(casa):
    """Exigência com «<b>» digitado não vira marcação na folha."""
    html = OURO_F._nota(casa, exigencias="Traga o <b>original</b>.")
    assert "Traga o &lt;b&gt;original&lt;/b&gt;." in html


def test_o_ajuste_da_nota_e_da_etiqueta_sai_sem_o_que_executa(casa):
    """**A TELA DE MODELOS GRAVA COM O PAPEL USER, E A NOTA ABRE NO NAVEGADOR DE
    QUEM IMPRIME.** Template do programa, ninguém escrevia nela; papel do
    catálogo (LF06F), um `<script>` gravado no modelo — ou um `|safe` no meio
    dele — rodaria na sessão do oficial, o caso que o LS02 fechou nos teores. O
    ajuste sai pelo `html_sem_script`; o texto dele continua, e o QR do selo
    (SVG, que o filtro tiraria inteiro) também."""
    _gravar(casa, "RCPJ_RTD_NOTA",
            "<p onclick=\"alert('LF06F')\">NOTA DA CASA</p>"
            "<script>alert('LF06F')</script>"
            "{{ '<img src=x onerror=alert(1)>'|safe }}")
    html = OURO_F._nota(casa, exigencias="Exigência de exemplo.")
    assert "<p>NOTA DA CASA</p>" in html
    assert "alert(" not in html
    _gravar(casa, "RCPJ_RTD_ETIQUETA",
            "<div>TIRA DA CASA</div>{% if e.qr %}{{ e.qr|safe }}{% endif %}"
            "<script>alert('LF06F')</script>")
    tira = OURO_F._etiqueta(casa, selo="REGTER000000ABCDEFGHIJKL1234")
    assert "<div>TIRA DA CASA</div><svg" in tira
    assert "alert(" not in tira


def test_o_rotulo_do_desenho_segue_a_moldura_ajustada(casa):
    """A moldura dos PDFs é UM papel com partes; a parte ajustada vale e a
    que o ajuste apagou volta ao padrão."""
    import rg_certidao_pdf as CERT
    import rg_teor_rtdpj as TEOR
    from PIL import Image
    con = _con(casa)
    with con:
        MOD.salvar(con, "RCPJ_RTD_PDF_MOLDURA",
                   corpo="===PAGINA===\nFolha\n===LIVRO_RTD===\nLivro B do RTD",
                   quem="mario", agora="2026-10-19T09:00")
    rotulos = TEOR.moldura(con)
    assert rotulos["PAGINA"] == "Folha"
    assert rotulos["SELO_AVERBACAO"] == "selo averbação"
    textos = CERT.textos_prontos(numero=148, lavrante_nome="FULANO DE EXEMPLO",
                                 lavrante_funcao="Escrevente", serie="TD_B",
                                 volume="7", con=con)
    assert textos["ctx"]["livro"] == "Livro B do RTD B-7"
    folha = Image.new("RGB", (40, 60), "white")
    assert "Folha" in OURO_F._textos_desenhados(lambda: CERT.montar_folha_interna(
        folha, textos=textos, pagina=1, total_paginas=1))


def test_a_moldura_com_claro_que_nao_existe_e_recusada_com_a_excecao_de_quem_pede(casa):
    import rg_certidao_pdf as CERT
    import rg_teor_rtdpj as TEOR
    con = _con(casa)
    with con:
        MOD.salvar(con, "RCPJ_RTD_PDF_MOLDURA",
                   corpo="===SELO_CONSULTE===\nVeja em {site}",
                   quem="mario", agora="2026-10-19T09:00")
    with pytest.raises(CERT.CertidaoPdfError) as erro:
        TEOR.moldura(con, erro=CERT.CertidaoPdfError)
    assert "SELO_CONSULTE" in str(erro.value) and "{endereco}" in str(erro.value)
    with pytest.raises(TEOR.TeorRtdpjError):
        TEOR.moldura(con)


def test_o_teor_da_averbacao_no_livro_sai_do_padrao_mesmo_com_a_intro_ajustada(casa):
    """**O LIVRO GRAVA O QUE GRAVAVA ANTES** — a revisão do LF06F: fazer o teor
    lançado em `rg_atos` seguir a ===INTRO=== que a casa ajustou mudaria o que
    se lavra, e isso é regra da casa, não da migração do texto. A intro saiu do
    código (é a do padrão), mas o ajuste da tela vale só no PDF, como antes."""
    from selador_de_bancada import ligar_o_selador
    padrao = MOD.padrao_de("RTD_TEOR_AVERBACAO")
    ajuste = padrao.replace("CERTIFICO que me foi apresentado",
                            "CERTIFICO, A PEDIDO, que me foi apresentado")
    _gravar(casa, "RTD_TEOR_AVERBACAO", ajuste)
    assert "A PEDIDO" in MOD.texto_do_papel(_con(casa), "RTD_TEOR_AVERBACAO"), \
        "a tela recusou o ajuste, e o teste não provaria nada"
    ids = OURO_F._registro_rcpj(casa)
    with ligar_o_selador(casa):
        c = casa["cliente"]
        html = c.get(f"/rcpj-rtd/{ids['registro']}").get_data(as_text=True)
        c.post(f"/rcpj-rtd/{ids['registro']}/lancar",
               data={"csrf_token": _token(html), "tipo": "AVERBACAO",
                     "natureza_ato": "ALTERAÇÃO DE ESTATUTO",
                     "data_assinatura": "01/09/2026"}, follow_redirects=True)
    teor = banco(_con(casa)).valor(
        """SELECT teor FROM rg_atos WHERE registro_id = %s AND tipo = 'AVERBACAO'
            ORDER BY id DESC LIMIT 1""", (ids["registro"],))
    assert teor == OURO_F.ouro()["funcoes"][
        "rg_teor_rtdpj.intro(AVERBACAO,'ALTERAÇÃO DE ESTATUTO','01/09/2026')"]["ok"]
    assert "A PEDIDO" not in teor


def _intro_de_antes(n, tipo, nat, data):
    """A f-string de `rg_teor_rtdpj.intro` no commit de antes (2c41e90) — o
    oráculo para os valores que o ouro não tem."""
    base = (f"CERTIFICO que me foi apresentado para ser "
            f"{'REGISTRADO' if tipo == 'REGISTRO' else 'AVERBADO'} no "
            f"Registro nº {n} o documento digitalizado abaixo:")
    partes = [base]
    if nat:
        partes.append(f"Tipo do ato: {nat}.")
    if data:
        partes.append(f"Data da assinatura: {data}.")
    return "\n".join(partes)


@pytest.mark.parametrize("nat,data", [
    ("", ""), ("ALTERAÇÃO", ""), ("", "01/09/2026"),
    ("ata {da} assembleia", "01/09/2026"),      # chave no valor não é claro
    ("ATA\r\nDE ELEIÇÃO", ""),                  # quebra digitada fica como veio
    ("Tipo do ato:", "."),                       # o valor que parece linha vazia
])
def test_a_intro_do_livro_e_byte_a_byte_a_f_string_de_antes(nat, data):
    """O teor vai ao livro e congela: o padrão tem de dar os MESMOS bytes da
    f-string de antes para qualquer valor digitado, e não só para os do ouro."""
    import rg_teor_rtdpj as TEOR
    for tipo in ("AVERBACAO", "REGISTRO"):
        assert TEOR.intro(1508, tipo_ato=tipo, natureza_ato=nat,
                          data_assinatura=data) == \
            _intro_de_antes("1508", tipo, nat.strip(), data.strip()), (tipo, nat)


def test_o_aviso_do_orcamento_e_peca_e_o_ajuste_dela_vale(casa, monkeypatch):
    con = _con(casa)
    with con:
        MOD.salvar(con, "CAIXA_ORCAMENTO__aviso", corpo="AVISO DA CASA: SÓ CÁLCULO.",
                   quem="mario", agora="2026-10-19T09:00")
    odf = OURO_F._orcamento(casa, monkeypatch, tipo="ORCAMENTO")
    assert "AVISO DA CASA: SÓ CÁLCULO." in odf
    assert "MERO CÁLCULO" not in odf


def test_o_rascunho_do_whatsapp_segue_o_ajuste_e_o_torto_nao_perde_a_mensagem(casa):
    """O rascunho é montado no webhook, ao gravar a mensagem do cliente: o
    ajuste vale, e um ajuste com claro inventado sai como o padrão — a
    mensagem que chegou não pode se perder por causa do texto da resposta."""
    import wa_balcao as WAB
    sv = OURO_F.SERVENTIA_DE_EXEMPLO
    con = _con(casa)
    with con:
        MOD.salvar(con, "CAIXA_WHATSAPP",
                   corpo="===HORARIO===\nOla. Confirme o horario no balcao. {contato}",
                   quem="mario", agora="2026-10-19T09:00")
    assert WAB.rascunhar("abre?", "horario", sv, con=con) == (
        "Ola. Confirme o horario no balcao. SERVENTIA EXTRAJUDICIAL DE EXEMPLO, "
        "Oficio unico de Cidade Exemplo/MA. Telefone (99) 0000-0000. "
        "E-mail contato@exemplo.invalid.")
    # a parte que o ajuste não tem volta ao padrão
    assert WAB.rascunhar("certidao", "certidao", sv, con=con) == \
        WAB.rascunhar("certidao", "certidao", sv)
    with con:
        MOD.salvar(con, "CAIXA_WHATSAPP", corpo="===HORARIO===\nOla {inventado}",
                   quem="mario", agora="2026-10-19T09:01")
    assert WAB.rascunhar("abre?", "horario", sv, con=con) == \
        WAB.rascunhar("abre?", "horario", sv)


def test_o_txt_com_crlf_do_windows_le_os_mesmos_bytes(tmp_path):
    """Um git com `autocrlf` poria `\\r\\n` em cada linha; o padrão não pode
    mudar por isso — nem o texto, nem a impressão digital, nem a marca."""
    lf = _pasta_de_ensaio(tmp_path / "lf", "RI_NOTA")
    crlf = _pasta_de_ensaio(tmp_path / "crlf", "RI_NOTA")
    arq = crlf / "ri" / "RI_NOTA.txt"
    arq.write_bytes(arq.read_bytes().replace(b"\n", b"\r\n"))
    PASTA.esquecer()
    a, b = PASTA.ler_pasta(lf), PASTA.ler_pasta(crlf)
    assert a["padroes"]["RI_NOTA"]["corpo"] == b["padroes"]["RI_NOTA"]["corpo"]
    assert "\r" not in b["padroes"]["RI_NOTA"]["corpo"]
    assert (a["padroes"]["RI_NOTA"]["impressao_digital"]
            == b["padroes"]["RI_NOTA"]["impressao_digital"])
    assert a["marca"] == b["marca"]
    PASTA.esquecer()


def test_arquivo_torto_vira_problema_e_nao_derruba_os_outros(tmp_path):
    pasta = _pasta_de_ensaio(tmp_path, "RI_NOTA", "CAIXA_RECIBO")
    (pasta / "caixa" / "CAIXA_RECIBO.json").write_text("{ isto não é json",
                                                      encoding="utf-8")
    PASTA.esquecer()
    lida = PASTA.ler_pasta(pasta)
    assert set(lida["padroes"]) == {"RI_NOTA"}
    assert any("CAIXA_RECIBO" in p for p in lida["problemas"])
    PASTA.esquecer()


def test_txt_que_nao_e_utf8_vira_problema_e_nao_derruba_os_outros(tmp_path):
    """Medido no LF06B: um byte fora do UTF-8 num `.txt` (um editor que salva
    em Latin-1) estourava a leitura da pasta, e todos os papéis caíam juntos."""
    pasta = _pasta_de_ensaio(tmp_path, "RI_NOTA", "CAIXA_RECIBO")
    arq = pasta / "caixa" / "CAIXA_RECIBO.txt"
    arq.write_bytes(arq.read_bytes() + "Recibo emitido em São Luís".encode("latin-1"))
    PASTA.esquecer()
    lida = PASTA.ler_pasta(pasta)
    assert set(lida["padroes"]) == {"RI_NOTA"}
    assert any("CAIXA_RECIBO" in p and "UTF-8" in p for p in lida["problemas"])
    PASTA.esquecer()


def test_a_peca_de_um_papel_herda_a_ficha_dele(tmp_path):
    """A REGRA fica no código; o TEXTO da frase pode morar na pasta como peça
    (`<CHAVE>__<peca>.txt`), sem ficha própria."""
    pasta = _pasta_de_ensaio(tmp_path, "PT_TERMO_PROTESTO")
    (pasta / "protesto" / "PT_TERMO_PROTESTO__edital.txt").write_text(
        "O devedor foi intimado por Edital em {data}.", encoding="utf-8")
    PASTA.esquecer()
    peca = PASTA.ler_pasta(pasta)["padroes"]["PT_TERMO_PROTESTO__edital"]
    assert peca["peca_de"] == "PT_TERMO_PROTESTO"
    assert peca["formato"] == MOD.CHAVES
    assert peca["campos"] == ["data"]
    assert "peça «edital»" in peca["nome"]
    PASTA.esquecer()
    c = MOD._do_catalogo("pt_termo_protesto__EDITAL")
    assert c["chave"] == "PT_TERMO_PROTESTO__edital"
    assert c["arquivo"] == "modelos_padrao/protesto/PT_TERMO_PROTESTO__edital.txt"


# ------------------------------------------------ a base


def test_o_schema_da_base_segue_a_instalacao(monkeypatch):
    """Duas instalações no MESMO banco (a produção e o ensaio da virada, em
    19/10) não podem dividir a base: cada subida apagaria a da outra."""
    monkeypatch.delenv("CG_PG_SCHEMA", raising=False)
    assert MOD.schema_da_base() == "modelos_padrao"
    monkeypatch.setenv("CG_PG_SCHEMA", "producao")
    assert MOD.schema_da_base() == "modelos_padrao_producao"
    monkeypatch.setenv("CG_PG_SCHEMA", "ensaio_final")
    assert MOD.schema_da_base() == "modelos_padrao_ensaio_final"


def test_a_base_so_e_recarregada_quando_a_pasta_muda(tmp_path, schema_de_ensaio):
    """Apagada e recriada INTEIRA — mas só quando a marca da pasta muda. A
    subida de todo dia não reescreve nada."""
    pasta = _pasta_de_ensaio(tmp_path, "RI_NOTA", "CAIXA_RECIBO")
    r1 = MOD.carregar_base(schema=schema_de_ensaio, pasta=pasta)
    assert r1["carregou"] and set(r1["padroes"]) == {"RI_NOTA", "CAIXA_RECIBO"}
    r2 = MOD.carregar_base(schema=schema_de_ensaio, pasta=pasta)
    assert not r2["carregou"] and r2["padroes"] == r1["padroes"]

    # a versão nova trouxe uma vírgula a mais no recibo
    arq = pasta / "caixa" / "CAIXA_RECIBO.txt"
    arq.write_bytes(arq.read_bytes() + b"<p>Nova linha do padrao.</p>\n")
    PASTA.esquecer()
    r3 = MOD.carregar_base(schema=schema_de_ensaio, pasta=pasta)
    assert r3["carregou"]
    assert r3["padroes"]["CAIXA_RECIBO"]["corpo"].endswith("<p>Nova linha do padrao.</p>\n")
    assert (r3["padroes"]["CAIXA_RECIBO"]["impressao_digital"]
            != r1["padroes"]["CAIXA_RECIBO"]["impressao_digital"])
    assert r3["padroes"]["RI_NOTA"] == r1["padroes"]["RI_NOTA"]
    PASTA.esquecer()


def test_quem_sobe_junto_espera_a_carga_do_outro_e_nao_recarrega(tmp_path,
                                                                 schema_de_ensaio):
    """Vários processos sobem juntos (o serviço, a tarefa agendada). Com a
    trava, só UM carrega; os outros esperam, veem a marca nova e leem."""
    pasta = _pasta_de_ensaio(tmp_path, "RI_NOTA", "CAIXA_RECIBO", "RC_TERMO_OBITO")
    resultados, erros = [], []

    def subir():
        try:
            resultados.append(MOD.carregar_base(schema=schema_de_ensaio, pasta=pasta))
        except Exception as erro:                       # noqa: BLE001
            erros.append(erro)

    fios = [threading.Thread(target=subir) for _ in range(4)]
    for f in fios:
        f.start()
    for f in fios:
        f.join(60)
    PASTA.esquecer()
    assert not erros, erros
    assert sum(1 for r in resultados if r["carregou"]) == 1
    assert len({json.dumps(r["padroes"], sort_keys=True) for r in resultados}) == 1


def test_a_base_nao_guarda_nada_da_casa(casa):
    """Só o padrão e a marca. É por isso que ela pode ser apagada e recriada
    numa atualização sem levar ajuste nenhum junto."""
    MOD.carregar_base()
    tabelas = {r["t"] for r in banco(_con(casa)).ler(
        "SELECT table_name AS t FROM information_schema.tables "
        "WHERE table_schema = %s ORDER BY table_name", (MOD.schema_da_base(),))}
    assert tabelas == {"padroes", "padroes_marca"}


def test_padrao_que_nao_esta_na_base_e_erro_claro(monkeypatch):
    """Sem ajuste e sem padrão, o papel não sai — e quem lê o erro precisa
    saber qual arquivo faltou, e não ver uma folha em branco."""
    monkeypatch.setattr(MOD, "_padroes",
                        lambda: {"padroes": {}, "origem": "base", "erro": None})
    with pytest.raises(MOD.ModeloError) as erro:
        MOD.padrao_de("CAIXA_RECIBO")
    assert "não está carregado" in str(erro.value)
    assert "modelos_padrao/caixa/CAIXA_RECIBO.txt" in str(erro.value)


def test_base_fora_do_ar_serve_a_pasta_e_a_tela_avisa(casa, monkeypatch, ouro):
    """O piso do piso: a base que não carregou não deixa a casa sem papel — a
    pasta é a fonte dela, os mesmos bytes —, e a tela diz que a base caiu."""
    def fora_do_ar(**_):
        raise RuntimeError("base de ensaio fora do ar")
    monkeypatch.setattr(MOD, "carregar_base", fora_do_ar)
    MOD.esquecer_padroes()
    try:
        situacao = MOD.situacao_da_base()
        assert situacao["origem"] == "pasta"
        assert "fora do ar" in situacao["erro"]
        assert MOD.padrao_de("RI_FICHA") == ouro["textos"]["RI_FICHA"]
        assert "A base de padrões não carregou" in _tela(casa)
    finally:
        monkeypatch.undo()
        MOD.esquecer_padroes()


def _o_padrao_e_o_montador(c: dict) -> bool:
    """O texto não tinha constante — era montado numa f-string — e o `padrao`
    do catálogo diz a FUNÇÃO que o monta (LF06D; ver `docs/MODELOS_PADRAO.md`).
    Aí não há nome antigo a responder: há a função, e ela tem de ler o papel."""
    modulo, nome = c["padrao"]
    alvo = vars(importlib.import_module(modulo)).get(nome)
    return callable(alvo)


def test_o_montador_declarado_le_o_papel_dele():
    """Quando o `padrao` é a função, ela existe — e o módulo dela consulta a
    chave do papel. Sem isso, o catálogo apontaria para quem não o lê."""
    import inspect
    montados = [c for c in MOD.CATALOGO if _o_padrao_e_o_montador(c)]
    assert len(montados) == 11           # os do LF06D sem nome de constante
    for c in montados:
        modulo, nome = c["padrao"]
        fonte = inspect.getsource(importlib.import_module(modulo))
        assert f'"{c["chave"]}' in fonte, (c["chave"], modulo, nome)


def test_o_nome_antigo_da_constante_devolve_o_padrao_da_base():
    """`ri_odt.MODELO_FICHA_PADRAO` continua respondendo — com o MESMO texto
    que o papel imprime. E nome que não é de papel continua não existindo."""
    for c in MOD.CATALOGO:
        if _o_padrao_e_o_montador(c):
            continue
        modulo, nome = c["padrao"]
        # RCPJ_CERTIDAO e RTD_CERTIDAO dividem o nome antigo e o texto
        assert getattr(importlib.import_module(modulo), nome) == MOD.padrao_de(
            c["chave"]), c["chave"]
    import rg_certidao_pdf
    import rg_teor_rtdpj
    assert rg_teor_rtdpj.PADROES_POR_CHAVE == {
        k: MOD.padrao_de(k) for k in ("RCPJ_TEOR_AVERBACAO", "RCPJ_TEOR_REGISTRO",
                                      "RTD_TEOR_AVERBACAO", "RTD_TEOR_REGISTRO")}
    assert list(rg_certidao_pdf.PADROES_POR_CHAVE) == [
        "RCPJ_CERTIDAO_CAPA", "RTD_CERTIDAO_CAPA",
        "RCPJ_CERTIDAO_FAIXA", "RTD_CERTIDAO_FAIXA"]
    import ri_odt
    with pytest.raises(AttributeError):
        ri_odt.MODELO_QUE_NUNCA_EXISTIU  # noqa: B018


def test_o_texto_saiu_mesmo_do_codigo():
    """Nenhum dos catorze módulos guarda mais o texto: o nome antigo só
    responde pelo `__getattr__`, e não por uma constante esquecida no arquivo."""
    for c in MOD.CATALOGO:
        if _o_padrao_e_o_montador(c):
            continue
        modulo, nome = c["padrao"]
        assert nome not in vars(importlib.import_module(modulo)), f"{modulo}.{nome}"


# ------------------------------------------------ o ajuste e o padrão novo


def test_o_ajuste_guarda_sobre_qual_padrao_foi_feito(casa):
    """`base_impressao` nos DOIS armazéns — `mo_elementos`, onde a tela grava,
    e `mo_modelos`, o legado."""
    _gravar(casa, "CAIXA_RECIBO", "RECIBO NOVO")
    con = _con(casa)
    bd = banco(con)
    assert bd.valor(
        "SELECT base_impressao FROM mo_elementos WHERE ato = %s AND parte = 'CORPO'",
        ("CAIXA_RECIBO",)) == MOD.impressao_digital_de("CAIXA_RECIBO")
    with con:
        MOD.salvar(con, "RI_NOTA", corpo="NOTA DA CASA", quem="mario", agora="a")
    assert bd.valor("SELECT base_impressao FROM mo_modelos WHERE chave = %s",
                    ("RI_NOTA",)) == MOD.impressao_digital_de("RI_NOTA")


def test_a_tela_avisa_que_o_padrao_mudou_depois_do_ajuste_e_mostra_a_diferenca(casa):
    """A versão nova trouxe outro padrão; o ajuste da casa continua valendo —
    a atualização NUNCA o sobrescreve — e a tela avisa, com a diferença."""
    _gravar(casa, "CAIXA_RECIBO", "RECIBO NOVO DA CASA")
    con = _con(casa)
    with con:
        banco(con).escrever(
            "UPDATE mo_elementos SET base_impressao = %s WHERE ato = %s",
            ("sha256-de-um-padrao-de-antes", "CAIXA_RECIBO"))
    mudou = MOD.padrao_mudou_depois_do_ajuste(con, "CAIXA_RECIBO")
    assert mudou["situacao"] == "MUDOU" and mudou["onde"] == "mo_elementos"
    assert "-RECIBO NOVO DA CASA" in mudou["diferenca"]
    html = _tela(casa, editar="CAIXA_RECIBO")
    assert "O padrão mudou depois do seu ajuste" in html
    assert "o padrão de hoje" in html
    # e o papel continua saindo com o ajuste da casa
    assert MOD.texto_do_papel(con, "CAIXA_RECIBO") == "RECIBO NOVO DA CASA"


def test_sem_mudanca_do_padrao_a_tela_nao_avisa(casa):
    _gravar(casa, "CAIXA_RECIBO", "RECIBO NOVO")
    assert MOD.padrao_mudou_depois_do_ajuste(
        _con(casa), "CAIXA_RECIBO")["situacao"] == "IGUAL"
    assert "O padrão mudou depois do seu ajuste" not in _tela(
        casa, editar="CAIXA_RECIBO")
    assert MOD.padrao_mudou_depois_do_ajuste(_con(casa), "RI_NOTA") is None


def test_ajuste_antigo_sem_marca_diz_que_nao_ha_como_saber(casa):
    """O ajuste de antes do LF06A (o cartão de autógrafo da produção é um) não
    sabe sobre qual padrão foi feito. A tela diz isso, em vez de calar."""
    _gravar(casa, "CAIXA_RECIBO", "RECIBO ANTIGO")
    con = _con(casa)
    with con:
        banco(con).escrever(
            "UPDATE mo_elementos SET base_impressao = NULL WHERE ato = %s",
            ("CAIXA_RECIBO",))
    assert MOD.padrao_mudou_depois_do_ajuste(con, "CAIXA_RECIBO")["situacao"] == "SEM_MARCA"
    assert "não há como saber" in _tela(casa, editar="CAIXA_RECIBO")


# ------------------------------------------------ a subida e o pacote


def test_a_subida_traz_o_legado_e_carrega_a_base(casa, monkeypatch):
    """`init_ri_schema` é a subida: ela converte o `ri_modelos` e carrega a
    pasta na base. Sem isto a instalação nova só teria base no primeiro papel."""
    import ri_schema
    chamadas = []
    monkeypatch.setattr(MOD, "trazer_ajustes_do_legado_ri",
                        lambda con, **k: chamadas.append("legado") or 0)
    monkeypatch.setattr(MOD, "subir_base", lambda: chamadas.append("base"))
    con = _con(casa)
    with con:
        ri_schema.init_ri_schema(con)
    assert chamadas == ["legado", "base"]


def test_o_pacote_leva_a_pasta_dos_padroes():
    """Instalação nova nasce funcionando porque a pasta VAI no pacote — no
    `.cgu` (que leva a pasta inteira) e no público (que é lista do que entra).
    E vai byte a byte: o `.gitattributes` desliga a troca de fim de linha."""
    def _ferramenta(nome):
        espec = importlib.util.spec_from_file_location(nome, RAIZ / "tools" / f"{nome}.py")
        mod = importlib.util.module_from_spec(espec)
        espec.loader.exec_module(mod)
        return mod

    no_cgu = {rel for _p, rel in _ferramenta("criar_atualizacao").todos_os_arquivos(RAIZ)}
    for c in MOD.CATALOGO:
        assert c["arquivo"] in no_cgu
        assert c["arquivo"].replace(".txt", ".json") in no_cgu
    # e as peças e as minutas (LF06D), que estão em subpasta
    for p in (RAIZ / "modelos_padrao").rglob("*"):
        if p.is_file() and p.suffix in (".txt", ".json"):
            assert p.relative_to(RAIZ).as_posix() in no_cgu, p
    assert "modelos_padrao" in _ferramenta("exportar_publico").PASTAS
    assert "modelos_padrao/** -text" in (RAIZ / ".gitattributes").read_text(
        encoding="utf-8")


# ============================================ AS NOTAS — LF06D
#
#   «Não deveríamos ter modelos no código; deveriam estar no banco, para
#    editar com mais facilidade.» — o oficial, 19/10/2026.
#
# Os textos das Notas que o código ainda montava — a fórmula da etiqueta, os
# termos do livro, a inutilização, a anotação à margem, a abertura, o fecho e
# a qualificação do teor, o cabeçalho das páginas do traslado — foram para a
# pasta e para a base: 25 papéis no catálogo e as frases que a regra escolhe
# como peças. E as 33 minutas de fábrica (`notas_modelos`) também. **A PROVA DE
# QUE NADA MUDOU É O OURO DELES**, gravado antes, do commit 2c41e90
# (`fixtures/modelos_ouro/ouro_lf06d.py`): cada montador com um contexto de
# teste, saída por saída, e as minutas inteiras.

import subprocess                                                # noqa: E402

_ESPEC_D = importlib.util.spec_from_file_location(
    "ouro_lf06d", RAIZ / "tests" / "fixtures" / "modelos_ouro" / "ouro_lf06d.py")
OURO_D = importlib.util.module_from_spec(_ESPEC_D)
_ESPEC_D.loader.exec_module(OURO_D)

# Os papéis que o LF06D pôs no catálogo, escritos à mão — é a lista que
# `NOVOS_NO_CATALOGO_LF06D`, logo abaixo, conta.
PAPEIS_DO_LF06D = {
    "NOTAS_RECONHECIMENTO_SEMELHANCA", "NOTAS_RECONHECIMENTO_AUTENTICIDADE",
    "NOTAS_RECONHECIMENTO_SINAL", "NOTAS_AUTENTICACAO", "NOTAS_AUTENTICACAO_INTERNET",
    "NOTAS_ETIQUETA_FECHO", "NOTAS_TERMO_COMPARECIMENTO", "NOTAS_LIVRO_ABERTURA",
    "NOTAS_LIVRO_ENCERRAMENTO", "NOTAS_INUTILIZACAO", "NOTAS_INUTILIZACAO_FACE",
    "NOTAS_ANOTACAO_MARGEM", "NOTAS_ABERTURA_ESCRITURA", "NOTAS_ABERTURA_PROCURACAO",
    "NOTAS_ABERTURA_SUBSTABELECIMENTO", "NOTAS_ABERTURA_REVOGACAO", "NOTAS_ABERTURA_ATA",
    "NOTAS_FECHO_ESCRITURA", "NOTAS_FECHO_PROCURACAO", "NOTAS_FECHO_SUBSTABELECIMENTO",
    "NOTAS_FECHO_REVOGACAO", "NOTAS_FECHO_ATA", "NOTAS_QUALIFICACAO_PF",
    "NOTAS_QUALIFICACAO_PJ", "NOTAS_TRASLADO_CABECALHO",
}

# **EM 19/10/2026 O CATÁLOGO GANHOU 25 PAPÉIS (LF06D)**: os textos das Notas
# que o código ainda montava sozinho (`PAPEIS_DO_LF06D`, acima): as fórmulas do
# reconhecimento e da autenticação, o fecho da etiqueta, os termos do livro e
# o de comparecimento, a inutilização, a anotação à margem, as aberturas e os
# fechos do teor, a qualificação e o cabeçalho das páginas do traslado. «Não
# deveríamos ter modelos no código» — o oficial; medidos um a um em
# `docs/MODELOS_INVENTARIO.md`. A contagem do catálogo, lá em cima, soma este
# número com o dos outros lotes paralelos do LF06.
NOVOS_NO_CATALOGO_LF06D = 25

# **EM 19/10/2026 O CATÁLOGO GANHOU 6 PAPÉIS (LG04)**: os atos que acontecem e
# não tinham papel — a certidão da notificação extrajudicial do RTD, positiva e
# negativa (CN-MA arts. 986 a 993); os termos de abertura e de encerramento e a
# certidão da autenticação de livro do RCPJ; e a pública forma das Notas.
# Nenhum tem precedente de texto no E-Ofício: são afirmação jurídica em papel
# assinado, e por isso vão ao catálogo, que é do oficial. E DUAS MINUTAS
# (`notas_modelos`), que não são linha do catálogo mas contam na pasta das
# Notas: a procuração previdenciária e o auto de aprovação do testamento
# cerrado — o tipo de ato existia, a minuta não.
PAPEIS_DO_LG04 = {
    "RTD_CERTIDAO_NOTIFICACAO_POSITIVA", "RTD_CERTIDAO_NOTIFICACAO_NEGATIVA",
    "RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA", "RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO",
    "RCPJ_LIVRO_CONTABIL_CERTIDAO", "NOTAS_PUBLICA_FORMA"}
MINUTAS_DO_LG04 = {"NT-PROC-PREVIDENCIARIA", "NT-TESTAMENTO-CERRADO"}
NOVOS_NO_CATALOGO_LG04 = 6

# O QUE O LD02 MUDOU DE PROPÓSITO NAS MINUTAS DE DEPOIS DO OURO — e só isto.
#
#   «corrija tudo» — o oficial, 21/10/2026, sobre os defeitos que o LT02 achou.
#   Três minutas tinham marcação que o leitor dos modelos não resolve
#   (`ri_modelos_atos.preencher` passa uma vez por nível): a tela não oferecia
#   o campo, o teor ficava com o marcador, e a trava da lavratura recusava o
#   ato (CN-MA art. 795, § 2º). O OURO NÃO SE REGERA: as trocas abaixo se
#   aplicam ao corpo de antes — cada uma achada uma vez só — e o resto continua
#   byte a byte. Outra diferença continua vermelha.
MINUTAS_MUDADAS_NO_LD02 = {
    # A escolha {DURAÇÃO} estava DENTRO da {ATO}, e havia uma segunda {ATO}
    # (REGISTRADO | CANCELADO o registro) com outras opções. A duração foi para
    # as condições da instituição; a frase do registro, para cada opção do ATO.
    "NT-ESC-USUFRUTO": (
        (" o USUFRUTO {DURAÇÃO: VITALÍCIO | pelo prazo de [PRAZO DO USUFRUTO POR "
         "EXTENSO] ([PRAZO DO USUFRUTO EM ALGARISMOS]) anos} sobre o imóvel acima "
         "descrito, ficando o USUFRUTUÁRIO com o direito de usar e fruir do bem, e o "
         "NU-PROPRIETÁRIO com a nua propriedade |",
         " o USUFRUTO sobre o imóvel acima descrito, ficando o USUFRUTUÁRIO com o "
         "direito de usar e fruir do bem, e o NU-PROPRIETÁRIO com a nua propriedade; "
         "e ficam as partes cientes de que a instituição somente produz efeito "
         "depois de REGISTRADA no Registro de Imóveis competente, na forma do artigo "
         "1.391 do Código Civil |"),
        ("na forma do artigo 1.410, I, do Código Civil}.",
         "na forma do artigo 1.410, I, do Código Civil; e ficam as partes cientes de "
         "que a renúncia somente produz efeito depois de CANCELADO o registro no "
         "Registro de Imóveis competente}."),
        ("«SE INSTITUIÇÃO: Fica o USUFRUTUÁRIO obrigado",
         "«SE INSTITUIÇÃO: O usufruto ora instituído {DURAÇÃO: é VITALÍCIO | vigorará "
         "pelo prazo de [PRAZO DO USUFRUTO POR EXTENSO] ([PRAZO DO USUFRUTO EM "
         "ALGARISMOS]) anos}. Fica o USUFRUTUÁRIO obrigado"),
        (" Ficam as partes cientes de que o ato somente produz efeito depois de "
         "{ATO: REGISTRADO | CANCELADO o registro} no Registro de Imóveis competente.",
         ""),
    ),
    # Duas escolhas «ATO» com opções diferentes respondiam pelo mesmo campo da
    # tela: a do destino dos bens ganhou rótulo próprio.
    "NT-ESC-PARTILHA-ADJUDICACAO": (
        ("Os bens acima descritos são {ATO: partilhados",
         "Os bens acima descritos são {DESTINO DOS BENS: partilhados"),
    ),
    # A cláusula «SE HOUVER SUBSTITUTO» estava DENTRO da «SE NOMEAR PROCURADOR
    # DE SAÚDE»: a de fora não virava caixa na tela. Agora são vizinhas.
    "NT-ESC-DIRETIVAS-VONTADE": (
        ("e não para qualquer outra finalidade. «SE HOUVER SUBSTITUTO: Nomeia, como "
         "procurador de saúde substituto, na falta ou impedimento do primeiro, [NOME "
         "E QUALIFICAÇÃO DO PROCURADOR SUBSTITUTO].»»",
         "e não para qualquer outra finalidade.» «SE HOUVER SUBSTITUTO: Nomeia, ainda, "
         "como procurador de saúde substituto, na falta ou impedimento do primeiro, "
         "[NOME E QUALIFICAÇÃO DO PROCURADOR SUBSTITUTO].»"),
    ),
}


# O QUE O LD07 MUDOU DE PROPÓSITO NAS MINUTAS — e só isto, por cima do LD02.
#
#   «corrija tudo» — o oficial, 21/10/2026, sobre os elementos que a norma
#   exige e o LT02 achou faltando no papel (`tests/test_requisitos_notas.py`).
#   Sete escrituras de imóvel sem a certidão do INSS (CN-MA art. 800, III) e
#   seis sem o cadastro fiscal (art. 800, IV); a cessão de direitos
#   hereditários sem a ciência do negócio de risco (art. 804, § 8º); a
#   procuração em causa própria sem o ITBI (art. 835, III); a emancipação sem
#   a naturalidade (Lei 6.015/1973, art. 90); a ata de usucapião sem o valor,
#   o titular, a aquisição da posse, as circunscrições, o alerta da falsidade
#   e o endereço eletrônico (CNN arts. 401 e 402); a de adjudicação sem os
#   ônus e o valor venal (CNN art. 440-G, I e V). Cada troca, achada uma vez
#   só no corpo de antes; o resto continua byte a byte.
_INSS_LD07 = (
    "{INSS: As partes declaram não estar sujeitas às contribuições previdenciárias "
    "de que trata o artigo 47 da Lei n. 8.212, de 1991 | Foi apresentada a Certidão "
    "Negativa de Débitos do INSS n. [NÚMERO DA CND], expedida em [DATA DA CND], em "
    "[LOCAL DE EXPEDIÇÃO DA CND]}")


def _cadastro_ld07(de: str = "") -> str:
    """A escolha do cadastro fiscal (art. 800, IV): Prefeitura, INCRA, ou o
    comprovante de que não há lançamento. `de` distingue os dois da permuta."""
    return ("{CADASTRO FISCAL" + de + ": com inscrição cadastral n. [INSCRIÇÃO CADASTRAL"
            + de + "] junto à Prefeitura Municipal | com código n. [CÓDIGO"
            + (de or " DO IMÓVEL") + " NO INCRA] no cadastro do INCRA | sem número de "
            "cadastro fiscal lançado, conforme [COMPROVANTE DA FALTA DE CADASTRO FISCAL"
            + de + "]}")


MINUTAS_MUDADAS_NO_LD07 = {
    "NT-ESC-DOACAO": (
        ("do [CARTÓRIO DE REGISTRO DE IMÓVEIS]. E que, por este instrumento",
         "do [CARTÓRIO DE REGISTRO DE IMÓVEIS], " + _cadastro_ld07() + ". E que, por "
         "este instrumento"),
        ("recolhida em [DATA DO ITCMD].", "recolhida em [DATA DO ITCMD]. " + _INSS_LD07 + "."),
    ),
    "NT-ESC-HIPOTECA": (
        ("havido conforme registro n. [NÚMERO DO REGISTRO ANTERIOR], ao qual",
         "havido conforme registro n. [NÚMERO DO REGISTRO ANTERIOR], " + _cadastro_ld07()
         + ", ao qual"),
        ("e a certidão de ônus reais.", "e a certidão de ônus reais. " + _INSS_LD07 + "."),
    ),
    "NT-ESC-ALIENACAO-FIDUCIARIA": (
        ("registro n. [NÚMERO DO REGISTRO ANTERIOR]. <b>DA LIVRE",
         "registro n. [NÚMERO DO REGISTRO ANTERIOR], " + _cadastro_ld07() + ". <b>DA LIVRE"),
        ("<b>DA ACEITAÇÃO E DO REGISTRO.</b>",
         "<b>DA CERTIDÃO DO INSS.</b> " + _INSS_LD07 + ". <b>DA ACEITAÇÃO E DO REGISTRO.</b>"),
    ),
    "NT-ESC-CONFISSAO-DACAO": (
        ("havido conforme registro n. [NÚMERO DO REGISTRO ANTERIOR], ao qual",
         "havido conforme registro n. [NÚMERO DO REGISTRO ANTERIOR], " + _cadastro_ld07()
         + ", ao qual"),
        ("recolhida em [DATA DO ITBI].", "recolhida em [DATA DO ITBI]. " + _INSS_LD07 + "."),
    ),
    "NT-ESC-PERMUTA": (
        ("do [CARTÓRIO DO PRIMEIRO IMÓVEL], ao qual",
         "do [CARTÓRIO DO PRIMEIRO IMÓVEL], " + _cadastro_ld07(" DO PRIMEIRO IMÓVEL")
         + ", ao qual"),
        ("do [CARTÓRIO DO SEGUNDO IMÓVEL], ao qual",
         "do [CARTÓRIO DO SEGUNDO IMÓVEL], " + _cadastro_ld07(" DO SEGUNDO IMÓVEL")
         + ", ao qual"),
        ("recolhidas em [DATAS DO ITBI].", "recolhidas em [DATAS DO ITBI]. " + _INSS_LD07 + "."),
    ),
    "NT-ESC-USUFRUTO": (
        ("havido conforme registro n. [NÚMERO DO REGISTRO ANTERIOR], ao qual",
         "havido conforme registro n. [NÚMERO DO REGISTRO ANTERIOR], " + _cadastro_ld07()
         + ", ao qual"),
        ("recolhida em [DATA DO IMPOSTO].",
         "recolhida em [DATA DO IMPOSTO]. " + _INSS_LD07 + "."),
    ),
    # a rural já tinha o cadastro (o CCIR, do INCRA); faltava o INSS
    "NT-ESC-COMPRA-VENDA-RURAL": (
        ("IV - DO ITBI E DOS TRIBUTOS:", "IV - DO ITBI, DO INSS E DOS TRIBUTOS:"),
        ("» O OUTORGANTE VENDEDOR responde pelos tributos",
         "» " + _INSS_LD07 + ". O OUTORGANTE VENDEDOR responde pelos tributos"),
    ),
    "NT-ESC-CESSAO-HEREDITARIA": (
        ("até o limite das forças da herança.",
         "até o limite das forças da herança. FICAM AS PARTES CIENTES, na forma do "
         "artigo 804, § 8º, do Código de Normas, de que a presente cessão é NEGÓCIO DE "
         "RISCO, pois só produzirá efeito a partir da partilha, caso o bem cedido seja "
         "atribuído ao CEDENTE, e de que os direitos cedidos poderão ser absorvidos por "
         "dívidas pendentes do espólio."),
    ),
    "NT-PROC-CAUSA-PROPRIA": (
        ("do Código de Normas.» Declara o OUTORGANTE",
         "do Código de Normas.» {ITBI: Foi apresentado o comprovante do prévio "
         "recolhimento do Imposto sobre a Transmissão de Bens Imóveis - ITBI incidente "
         "sobre a operação, guia n. [NÚMERO DA GUIA DE ITBI], recolhida em [DATA DO ITBI], "
         "no valor de [VALOR DO ITBI] | Foi apresentado o reconhecimento, pela autoridade "
         "fazendária, da não incidência, isenção ou imunidade do Imposto sobre a "
         "Transmissão de Bens Imóveis - ITBI sobre a operação, conforme [DOCUMENTO DO "
         "RECONHECIMENTO]}, na forma do artigo 835, III, do Código de Normas. Declara o "
         "OUTORGANTE"),
    ),
    "NT-ESC-EMANCIPACAO": (
        ("portanto com dezesseis anos completos, conforme",
         "portanto com dezesseis anos completos, natural de [NATURALIDADE DO "
         "EMANCIPANDO], conforme"),
        ("que me foi apresentada e fica arquivada.",
         "que me foi apresentada e fica arquivada. Declaram ainda os OUTORGANTES, para o "
         "registro da emancipação (artigo 90 da Lei n. 6.015, de 1973), a sua "
         "naturalidade: [NATURALIDADE DOS OUTORGANTES]."),
    ),
    "NT-ATA-USUCAPIAO": (
        ("compareceu como REQUERENTE {{ outorgantes }}, reconhecido como o próprio por "
         "mim, tabelião, do que dou fé.",
         "compareceu como REQUERENTE {{ outorgantes }}, com endereço eletrônico "
         "[ENDEREÇO ELETRÔNICO DO REQUERENTE], reconhecido como o próprio por mim, "
         "tabelião, do que dou fé. «SE REQUERENTE TEM CÔNJUGE OU COMPANHEIRO: É cônjuge "
         "ou companheiro do REQUERENTE [QUALIFICAÇÃO DO CÔNJUGE OU COMPANHEIRO DO "
         "REQUERENTE, COM ENDEREÇO ELETRÔNICO, DOMICÍLIO E RESIDÊNCIA].»"),
        ("do [CARTÓRIO DE REGISTRO DE IMÓVEIS]»",
         "do [CARTÓRIO DE REGISTRO DE IMÓVEIS], em que figura como titular "
         "[QUALIFICAÇÃO DO TITULAR DO IMÓVEL NA MATRÍCULA, COM ENDEREÇO ELETRÔNICO, "
         "DOMICÍLIO E RESIDÊNCIA]»"),
        ("confrontando com [NOMES E QUALIFICAÇÃO DOS CONFRONTANTES].",
         "confrontando com [NOMES E QUALIFICAÇÃO DOS CONFRONTANTES]. O valor atribuído "
         "ao imóvel usucapiendo é de [VALOR DO IMÓVEL POR EXTENSO] ([VALOR DO IMÓVEL EM "
         "ALGARISMOS]), correspondente ao {BASE DO VALOR: valor venal do último "
         "lançamento do IPTU | valor venal do último lançamento do ITR | valor de mercado "
         "aproximado, por não haver valor venal estipulado}, na forma do artigo 401, "
         "§ 8º, do Código Nacional de Normas. A pretensão aquisitiva atinge [NÚMERO DE "
         "IMÓVEIS ATINGIDOS POR EXTENSO] ([NÚMERO DE IMÓVEIS ATINGIDOS EM ALGARISMOS]) "
         "imóvel(is), situado(s) {CIRCUNSCRIÇÃO: em uma só circunscrição imobiliária, a "
         "do [REGISTRO DE IMÓVEIS DA CIRCUNSCRIÇÃO] | em mais de uma circunscrição "
         "imobiliária, a saber: [CIRCUNSCRIÇÕES IMOBILIÁRIAS DOS IMÓVEIS]}."),
        ("e sem oposição de quem quer que seja.",
         "e sem oposição de quem quer que seja, tendo-a adquirido por [FORMA DE "
         "AQUISIÇÃO DA POSSE PELO REQUERENTE]."),
        ("Declara o REQUERENTE, sob as penas da lei,",
         "ALERTEI o REQUERENTE e as testemunhas, se houver, de que a prestação de "
         "declaração falsa neste instrumento configura CRIME DE FALSIDADE, sujeito às "
         "penas da lei, na forma do artigo 402 do Código Nacional de Normas. Declara o "
         "REQUERENTE, sob as penas da lei,"),
    ),
    # A advertência do CNN art. 440-G, § 2º («a ata não tem valor de título de
    # propriedade») NÃO entrou no LD07: a minuta seguia o CN-MA art. 848, § 2º,
    # que diz o contrário — pergunta ao oficial. Respondida no LH13 (abaixo).
    "NT-ATA-ADJUDICACAO": (
        ("assim descrito: [DESCRIÇÃO DO IMÓVEL CONFORME A MATRÍCULA].",
         "assim descrito: [DESCRIÇÃO DO IMÓVEL CONFORME A MATRÍCULA], {ÔNUS E GRAVAMES: "
         "livre de ônus e gravames, conforme a certidão da matrícula | com os seguintes "
         "ônus e gravames, conforme a certidão da matrícula: [ÔNUS E GRAVAMES DO "
         "IMÓVEL]}. Atribui-se ao imóvel o valor venal de [VALOR VENAL DO IMÓVEL POR "
         "EXTENSO] ([VALOR VENAL DO IMÓVEL EM ALGARISMOS]), na data do requerimento, "
         "segundo a legislação local, na forma do artigo 440-G, V, do Código Nacional "
         "de Normas."),
    ),
}

# A ATA DE ADJUDICAÇÃO SEGUE O CNN (LH13, 21/10/2026). O oficial respondeu «12
# a» à pergunta do LD07: o CNN art. 440-G, § 2º (Prov. CNJ 150/2023) prevalece
# sobre o CN-MA art. 848, § 2º. A frase final da minuta — «ATESTO o
# preenchimento dos requisitos (...), servindo a presente ata como título
# hábil para ingresso no Registro de Imóveis (...)» — dá lugar à advertência
# de que a ata não é título de propriedade. Uma troca só, item por item: o
# resto da ata (os requisitos do art. 848, § 1º, e os do LD07) não muda.
MINUTAS_MUDADAS_NO_LH13 = {
    "NT-ATA-ADJUDICACAO": (
        ("Diante do exposto, ATESTO o preenchimento dos requisitos legais para a "
         "adjudicação compulsória extrajudicial, servindo a presente ata como título "
         "hábil para ingresso no Registro de Imóveis competente, independentemente de "
         "homologação judicial, na forma do artigo 848, § 2º, do Código de Normas, "
         "ressalvada ao Oficial de Registro de Imóveis a qualificação do título, que "
         "lhe é privativa.",
         "A presente ata não tem valor de título de propriedade; presta-se à instrução "
         "do pedido de adjudicação compulsória perante o Registro de Imóveis e poderá "
         "ser aproveitada em processo judicial, na forma do artigo 440-G, § 2º, do "
         "Código Nacional de Normas."),
    ),
}


def _minuta_de_hoje(antes: dict) -> dict:
    """A minuta do ouro com as trocas declaradas do LD02, do LD07 e do LH13 — e
    nada mais."""
    corpo = _com_as_trocas(antes["corpo"], MINUTAS_MUDADAS_NO_LD02.get(antes["codigo"], ()))
    corpo = _com_as_trocas(corpo, MINUTAS_MUDADAS_NO_LD07.get(antes["codigo"], ()))
    return dict(antes, corpo=_com_as_trocas(
        corpo, MINUTAS_MUDADAS_NO_LH13.get(antes["codigo"], ())))


# **EM 21/10/2026 O CATÁLOGO GANHOU 1 PAPEL (LD02)**: a certidão das Notas em
# BREVE RELATO — a cópia resumida que o art. 851 do Código de Normas define
# («cópia integral ou resumida») e que a casa não emitia. Sem precedente de
# texto no E-Ofício: vai ao catálogo, que é do oficial, como as outras três. E
# TRÊS PEÇAS, que não são linha do catálogo mas contam na pasta das Notas: o
# título dela, a ordem do termo de presença (art. 866) e a conferência da
# autenticação de documento da internet (art. 839, § 1º).
PAPEIS_DO_LD02 = {"NOTAS_CERTIDAO_BREVE_RELATO"}
PECAS_DO_LD02 = {"NOTAS_CERTIDAO_BREVE_RELATO__titulo",
                 "NOTAS_TERMO_COMPARECIMENTO__ordem",
                 "NOTAS_AUTENTICACAO_INTERNET__conferencia"}
NOVOS_NO_CATALOGO_LD02 = 1

# O QUE O LD02 MUDOU DE PROPÓSITO NOS MONTADORES DO OURO DO LF06D — e só isto:
# o nome das certidões (`notas_certidao.NOME_DO_TIPO`) ganhou o breve relato.
# Os três de antes continuam iguais; a entrada nova é a única diferença aceita.
MONTADORES_DAS_NOTAS_MUDADOS_NO_LD02 = {
    "notas_certidao.NOME_DO_TIPO": {"BREVE_RELATO": "Certidão em breve relato"},
}


# O QUE O LD07 MUDOU DE PROPÓSITO NA QUALIFICAÇÃO — e só isto (21/10/2026,
# «corrija tudo»). O CNN art. 111 pôs na qualificação da pessoa física «o
# documento de identificação, ou, na sua falta, a filiação» e «a existência de
# união estável», e a de quem é casado leva o cônjuge e o regime de bens (CC
# art. 215, § 1º, III). A regra do que falta é a dos seis de antes: sai
# marcado. As partes do ouro não têm nenhum dos novos, e nenhuma é casada:
# em TODA qualificação de pessoa física que não é testemunha entram as duas
# marcas — a da união estável depois do estado civil, a do documento depois da
# profissão. A testemunha não muda (o art. 111 fala dos sujeitos do ato).
# Quantas saídas mudam, contado à mão: 3 `qualificar`, 40 `montar` e 4
# `contexto_jinja_partes`.
SAIDAS_DA_QUALIFICACAO_MUDADAS_NO_LD07 = 47
_PF_DE_ANTES = re.compile(r"<b>(?P<nome>[^<]*)</b>, (?P<nac>[^,<]*), (?P<ec>[^,<]*), "
                          r"(?P<prof>[^,<]*), inscrito\(a\) no CPF")


def _qualificacao_de_hoje(nome: str, antes):
    """A saída do ouro com as marcas do LD07 nas partes que não são testemunha."""
    if not nome.startswith(("notas_teor.qualificar(", "notas_teor.montar(",
                            "notas_teor.contexto_jinja_partes(")):
        return antes
    rotulo = nome.rsplit(",", 1)[-1].rsplit("(", 1)[-1].rstrip(")")
    testemunhas = {(t.get("nome") or "").strip().upper() or "[NOME]"
                   for t in OURO_D.PARTES.get(rotulo, []) if t.get("testemunha")}

    def marcar(m):
        if m["nome"] in testemunhas:
            return m.group(0)
        return (f"<b>{m['nome']}</b>, {m['nac']}, {m['ec']}, [UNIÃO ESTÁVEL — SIM OU "
                f"NÃO], {m['prof']}, [DOCUMENTO DE IDENTIDADE OU FILIAÇÃO], "
                "inscrito(a) no CPF")

    def no_texto(valor):
        return _PF_DE_ANTES.sub(marcar, valor) if isinstance(valor, str) else valor

    saida = antes.get("ok")
    if isinstance(saida, dict):          # contexto_jinja_partes: só os dois lados
        return {"ok": {k: (v if k == "testemunhas" else no_texto(v))
                       for k, v in saida.items()}}
    return {**antes, "ok": no_texto(saida)} if "ok" in antes else antes


def _montador_das_notas_de_hoje(nome: str, antes):
    """A saída do ouro com o acréscimo declarado do LD02 e a qualificação do
    LD07 — e nada mais."""
    novos = MONTADORES_DAS_NOTAS_MUDADOS_NO_LD02.get(nome)
    if not novos:
        return _qualificacao_de_hoje(nome, antes)
    assert not set(novos) & set(antes["ok"]), f"o acréscimo já estava no ouro: {nome}"
    return {"ok": {**antes["ok"], **novos}}


def test_os_papeis_do_ld02_estao_no_catalogo_e_as_pecas_na_pasta():
    """A contagem escrita à mão bate com a lista, o papel está no catálogo e
    cada peça tem o seu arquivo — a soma da contagem geral confia nos três."""
    assert len(PAPEIS_DO_LD02) == NOVOS_NO_CATALOGO_LD02
    assert PAPEIS_DO_LD02 <= set(MOD.POR_CHAVE)
    pasta = PASTA.ler_pasta()["padroes"]
    for peca in PECAS_DO_LD02:
        assert pasta[peca]["peca_de"] and pasta[peca]["formato"] == MOD.CHAVES, peca


# **EM 21/10/2026 A PASTA DAS NOTAS GANHOU 7 PEÇAS (LD07)**, e o catálogo
# nenhum papel: a ressalva do original na autenticação (CN-MA art. 836) e as
# frases que a qualificação da pessoa física escolhe pela parte — o documento
# de identidade ou a filiação, a união estável (sim, não, e o companheiro) e o
# cônjuge com o regime de bens (CNN art. 111; CC art. 215, § 1º, III).
PECAS_DO_LD07 = {"NOTAS_AUTENTICACAO__ressalva",
                 "NOTAS_QUALIFICACAO_PF__identidade", "NOTAS_QUALIFICACAO_PF__filiacao",
                 "NOTAS_QUALIFICACAO_PF__uniao_estavel_sim",
                 "NOTAS_QUALIFICACAO_PF__uniao_estavel_nao",
                 "NOTAS_QUALIFICACAO_PF__companheiro", "NOTAS_QUALIFICACAO_PF__conjuge"}


def test_as_pecas_do_ld07_estao_na_pasta_e_sao_do_papel_delas():
    """Cada peça tem o seu arquivo, é do formato que o montador preenche, e
    pertence ao papel cujo nome ela traz — a soma da contagem geral confia."""
    pasta = PASTA.ler_pasta()["padroes"]
    for peca in PECAS_DO_LD07:
        assert pasta[peca]["peca_de"] == peca.split("__")[0], peca
        assert pasta[peca]["formato"] == MOD.CHAVES, peca


def test_os_papeis_do_lg04_estao_no_catalogo_e_a_tela_os_confere(casa):
    """A contagem escrita à mão bate com a lista, e cada papel novo tem
    conferidor próprio: a tela de Modelos recusa o claro que o montador não
    preenche, em vez de o balcão descobrir na hora de emitir."""
    import modelos_elementos as ELEM
    assert len(PAPEIS_DO_LG04) == NOVOS_NO_CATALOGO_LG04
    assert PAPEIS_DO_LG04 <= set(MOD.POR_CHAVE)
    for chave in PAPEIS_DO_LG04:
        assert chave in ELEM.CONFERIDORES, chave
        inventado = ("{{ claro_inventado_lg04 }}" if MOD.formato_de(chave) == MOD.JINJA
                     else "{claro_inventado_lg04}")
        assert ELEM.CONFERIDORES[chave](inventado), chave


# **EM 21/10/2026 O CATÁLOGO GANHOU 2 PAPÉIS (LD05)**: o termo do cancelamento
# do RCPJ e o do RTD. O cancelamento era o único ato do livro sem termo datado
# e assinado — o ato guardava só o motivo, e a rota do termo o recusava —, e a
# lei manda o oficial certificar o cancelamento e a causa, mencionando o
# documento que o autorizou, «datando e assinando» (LRP art. 165; CN-MA art.
# 994, § 1º). Sem precedente de texto no E-Ofício e afirmação do oficial em
# papel assinado: vai ao catálogo, como os outros quatro teores. Nenhum papel
# antigo mudou de texto.
# E A CERTIDÃO NEGATIVA DO RTD E DO RCPJ (serviços 314 e 315): a casa só
# certificava um registro que existe (LRP arts. 16, 17 e 19; CN-MA art. 963,
# § 3º). Também sem precedente de texto, e por isso do oficial.
# E A CERTIDÃO DO RCPJ EM BREVE RELATO (CN-MA art. 420, II), que não existia:
# a casa só emitia o inteiro teor.
PAPEIS_DO_LD05 = {"RCPJ_TEOR_CANCELAMENTO", "RTD_TEOR_CANCELAMENTO",
                  "RCPJ_RTD_CERTIDAO_NEGATIVA", "RCPJ_CERTIDAO_BREVE_RELATO"}
NOVOS_NO_CATALOGO_LD05 = 4


def test_os_termos_do_cancelamento_estao_no_catalogo_e_a_tela_os_confere(casa):
    """A contagem escrita à mão bate com a lista; cada termo novo tem
    conferidor próprio, que aceita o padrão e recusa o claro que o termo não
    preenche — e o padrão tem a causa, quem subscreve e a data."""
    import modelos_elementos as ELEM
    assert len(PAPEIS_DO_LD05) == NOVOS_NO_CATALOGO_LD05
    assert PAPEIS_DO_LD05 <= set(MOD.POR_CHAVE)
    for chave in PAPEIS_DO_LD05:
        assert ELEM.CONFERIDORES[chave](MOD.padrao_de(chave)) == "", chave
        assert ELEM.CONFERIDORES[chave](
            MOD.padrao_de(chave) + "{claro_inventado_ld05}"), chave
    for chave in PAPEIS_DO_LD05 - {"RCPJ_RTD_CERTIDAO_NEGATIVA",
                                   "RCPJ_CERTIDAO_BREVE_RELATO"}:
        for campo in ("{numero}", "{motivo}", "{full_name}", "{funcao}",
                      "{data_extenso}", "CANCELADO"):
            assert campo in MOD.padrao_de(chave), (chave, campo)
    for campo in ("{nome}", "{documento}", "{registro}", "NÃO CONSTA"):
        assert campo in MOD.padrao_de("RCPJ_RTD_CERTIDAO_NEGATIVA"), campo
    for campo in ("{denominacao}", "{sede}", "{cnpj}", "{objeto}", "{capital}",
                  "{socios}", "{diretoria}", "{ultimo_ato}"):
        assert campo in MOD.padrao_de("RCPJ_CERTIDAO_BREVE_RELATO"), campo


# ------------------------------------- LD09 — o que o termo do RCPJ/RTD declara
#
# O TERMO DECLARA O QUE A LEI MANDA DECLARAR (LD09, 21/10/2026), «corrija tudo».
# Os quatro teores ganharam linhas, cada uma com o seu claro, que SAEM DO TERMO
# quando o ato não tem o dado (`rg_teor_rtdpj._sem_declaracao_vazia`) — e por
# isso a intro que vai ao livro, o cabeçalho curto e os textos montados do ouro
# do LF06F continuam byte a byte (os testes de lá não mudaram). O ouro do LF06A
# NÃO se regera: o texto de antes recebe exatamente estas trocas, e o resto
# continua igual.
#   - o REGISTRO, no RTD e no RCPJ: o protocolo do título — a data e o número
#     — e o apresentante, antes do registro (LRP arts. 136 e 143; art. 120,
#     caput e VI, que a matrícula segue pelo art. 126);
#   - o do RTD: o extrato do Livro C (LRP art. 143; CN-MA art. 981) e o total
#     de páginas do Livro F (art. 127-A, § 3º);
#   - o do RCPJ: a residência do apresentante (art. 120, VI), as indicações do
#     art. 120, I a VI, e as da matrícula do periódico (art. 123, I);
#   - a AVERBAÇÃO, no RTD e no RCPJ: o número de ordem dela, no cabeçalho (LRP
#     arts. 149 e 153; CN-MA art. 968) — na intro, mudaria o teor que o livro
#     grava (`test_a_intro_do_livro_e_byte_a_byte_a_f_string_de_antes`).
# Fora dos dicionários, como as do LD02 e do LD06: a última linha deles é
# disputada pelos lotes que entram juntos.
_LD09_ANTES = ("o documento digitalizado abaixo:\nTipo do ato: {natureza_ato}.\n"
               "Data da assinatura: {data_assinatura}.\n")
_LD09_PROTOCOLO = ("Protocolizado em {data_protocolo}, sob o nº {protocolo}.",
                   "Apresentante: {apresentante}.")
_LD09_DO_RTD = (
    "Valor: {valor}.", "Prazo: {prazo}.", "Instrumento celebrado em {lugar}.",
    "Partes e condição jurídica: {partes}.", "Testemunhas: {testemunhas}.",
    "Com firma reconhecida em {reconhecimento}.",
    "Importância e qualidade do imposto pago: {imposto}.",
    "Total de páginas registradas: {paginas}.")
_LD09_DO_RCPJ = (
    "Denominação: {denominacao}.", "Fundo social: {fundo_social}.",
    "Fins: {fins}.", "Sede: {sede}.", "Tempo de duração: {duracao}.",
    "Modo por que se administra e representa: {administracao}.",
    "Se o estatuto é reformável no tocante à administração, e de que modo: {reforma}.",
    "Se os membros respondem subsidiariamente pelas obrigações sociais: "
    "{responsabilidade}.",
    "Condições de extinção e destino do patrimônio: {extincao}.",
    "Fundadores ou instituidores: {fundadores}.", "Diretoria: {diretoria}.",
    "Título do periódico: {titulo_periodico}.", "Sede da redação: {sede_redacao}.",
    "Administração e oficinas impressoras: {oficinas}.", "Diretor: {diretor}.",
    "Proprietário: {proprietario}.")
_LD09_REGISTRO = {
    "RTD_TEOR_REGISTRO": (_LD09_PROTOCOLO, _LD09_DO_RTD),
    "RCPJ_TEOR_REGISTRO": (
        _LD09_PROTOCOLO + ("Residência do apresentante: {residencia_apresentante}.",),
        _LD09_DO_RCPJ),
}


def _ld09_na_previa(texto: str) -> str:
    """O trecho como a prévia da casa o monta: os claros do LD09 não têm
    amostra no boneco (`modelos_previa`), e saem «[claro]», como o
    `[natureza ato]` de sempre."""
    return re.sub(r"\{(\w+)\}", lambda m: f"[{m.group(1).replace('_', ' ')}]", texto)


for _chave, (_antes_da_natureza, _depois_da_data) in _LD09_REGISTRO.items():
    _novo = ("o documento digitalizado abaixo:\n"
             + "".join(f"{linha}\n" for linha in _antes_da_natureza)
             + "Tipo do ato: {natureza_ato}.\nData da assinatura: {data_assinatura}.\n"
             + "".join(f"{linha}\n" for linha in _depois_da_data))
    MUDOU_DEPOIS_DO_OURO[_chave] = {
        "texto": ((_LD09_ANTES, _novo),),
        "papel": ((_ld09_na_previa(_LD09_ANTES), _ld09_na_previa(_novo)),)}
    MONTADORES_MUDADOS_DEPOIS_DO_OURO[f"rg_teor_rtdpj.corpo_do_modelo({_chave})"] = (
        (_LD09_ANTES, _novo),)
for _chave in ("RTD_TEOR_AVERBACAO", "RCPJ_TEOR_AVERBACAO"):
    MUDOU_DEPOIS_DO_OURO[_chave] = {
        "texto": (("{atribuicao}\n===INTRO===",
                   "{atribuicao}\nAverbação nº {numero_averbacao}\n===INTRO==="),),
        # na prévia, a atribuição do boneco é a do RCPJ, nos dois
        "papel": (("Registro Civil das Pessoas Jurídicas\n===INTRO===",
                   "Registro Civil das Pessoas Jurídicas\nAverbação nº "
                   "[numero averbacao]\n===INTRO==="),)}
    MONTADORES_MUDADOS_DEPOIS_DO_OURO[f"rg_teor_rtdpj.corpo_do_modelo({_chave})"] = (
        MUDOU_DEPOIS_DO_OURO[_chave]["texto"])


def test_cada_declaracao_do_livro_tem_a_linha_dela_no_termo_do_livro():
    """A tabela das declarações (`rg_registro.DECLARACOES_POR_SERIE`) e o
    padrão do termo falam dos mesmos claros: declaração que a tela pergunta e
    o termo não tem seria dado gravado que nenhum papel imprime; e claro do
    termo que a tela não pergunta, linha que nunca sai (LD09)."""
    import string

    import rg_registro as RG
    import rg_teor_rtdpj as TEOR
    for serie, livro in RG.DECLARACOES_POR_SERIE.items():
        padrao = MOD.padrao_de(TEOR.chave_do_modelo(serie=serie, tipo_ato="REGISTRO"))
        for claro, _ in livro["campos"]:
            linha = next((ln for ln in padrao.splitlines() if "{" + claro + "}" in ln), "")
            assert linha, (serie, claro)
            # a linha é só dele, para sair inteira quando ele vem vazio
            assert TEOR._sem_declaracao_vazia(linha, {}) == "", (serie, claro)
    do_padrao = {nome for chave in ("RTD_TEOR_REGISTRO", "RCPJ_TEOR_REGISTRO")
                 for _, nome, _, _ in string.Formatter().parse(
                     MOD.padrao_de(chave)) if nome}
    assert set(RG.CLAROS_DAS_DECLARACOES) <= do_padrao
    assert do_padrao & TEOR.CLAROS_OPCIONAIS == (
        set(RG.CLAROS_DAS_DECLARACOES) | set(TEOR.CLAROS_DO_PROTOCOLO)
        | {TEOR.CLARO_DAS_PAGINAS})


def test_os_papeis_novos_das_notas_sao_os_da_lista_e_estao_no_catalogo():
    """A contagem escrita à mão bate com a lista escrita à mão, e cada papel
    da lista está no catálogo — a soma da contagem geral confia nas duas."""
    assert len(PAPEIS_DO_LF06D) == NOVOS_NO_CATALOGO_LF06D
    assert PAPEIS_DO_LF06D <= set(MOD.POR_CHAVE)
    assert {c for c in MOD.POR_CHAVE if c.startswith("NOTAS_")} == PAPEIS_DO_LF06D | {
        "NOTAS_TRASLADO", "NOTAS_TERMO_LIVRO", "NOTAS_CERTIDAO_INTEIRO_TEOR",
        "NOTAS_CERTIDAO_POSITIVA", "NOTAS_CERTIDAO_NEGATIVA", "NOTAS_CARTAO_FICHA"} | {
        c for c in PAPEIS_DO_LG04 if c.startswith("NOTAS_")} | PAPEIS_DO_LD02


@pytest.fixture(scope="module")
def ouro_d():
    return OURO_D.ouro()


# ------------------------------------------------ o ouro das Notas: nada mudou


def test_o_ouro_das_notas_foi_gravado_antes_da_mudanca(ouro_d):
    """Do commit de ANTES (2c41e90), com as 217 saídas, as 33 minutas e os dois
    textos de dentro das rotas — e as chamadas de hoje são as mesmas do
    gerador, nem uma a menos."""
    assert ouro_d["commit"] == "2c41e90"
    assert len(ouro_d["funcoes"]) == 217
    assert set(OURO_D.chamadas()) == set(ouro_d["funcoes"])
    assert len(ouro_d["minutas"]) == 33
    assert len(ouro_d["rotas"]["rotulo_do_selo"]) == 2
    assert len(ouro_d["rotas"]["cartao_sem_selo_de_abertura"]) == 1


def test_os_montadores_das_notas_saem_iguais_aos_de_antes(ouro_d):
    """O TESTE-OURO DO LF06D: cada montador, com o contexto de teste e sem
    `con` — o caminho do padrão —, devolve byte a byte o que devolvia quando o
    texto estava no código. Inclui os erros (inutilizar zero faces estoura
    igual)."""
    assert set(MONTADORES_DAS_NOTAS_MUDADOS_NO_LD02) <= set(ouro_d["funcoes"])
    for nome, f in OURO_D.chamadas().items():
        assert OURO_D.normal(OURO_D.tenta(f)) == _montador_das_notas_de_hoje(
            nome, ouro_d["funcoes"][nome]), nome


def test_a_regra_da_qualificacao_do_ld07_muda_so_as_saidas_contadas(ouro_d):
    """A regra declarada do LD07 não é porta aberta: ela muda exatamente as
    saídas contadas à mão, e cada uma ganha as duas marcas em cada parte que
    não é testemunha — nenhuma saída de testemunha muda."""
    mudadas = {n: s for n, s in ouro_d["funcoes"].items()
               if _qualificacao_de_hoje(n, s) != s}
    assert len(mudadas) == SAIDAS_DA_QUALIFICACAO_MUDADAS_NO_LD07, sorted(mudadas)
    assert {n.split("(")[0] for n in mudadas} == {
        "notas_teor.qualificar", "notas_teor.montar", "notas_teor.contexto_jinja_partes"}
    for nome, antes in mudadas.items():
        depois = json.dumps(_qualificacao_de_hoje(nome, antes), ensure_ascii=False)
        assert depois.count("[UNIÃO ESTÁVEL — SIM OU NÃO]") == depois.count(
            "[DOCUMENTO DE IDENTIDADE OU FILIAÇÃO]") >= 1, nome
    contexto = _qualificacao_de_hoje("notas_teor.contexto_jinja_partes(varios_e_testemunha)",
                                     ouro_d["funcoes"][
                                         "notas_teor.contexto_jinja_partes(varios_e_testemunha)"])
    assert "UNIÃO ESTÁVEL" not in contexto["ok"]["testemunhas"]


def test_as_minutas_saem_iguais_as_de_antes(ouro_d):
    """As 33 minutas, inteiras — o que ficou no código e o que veio da base —,
    e cada arquivo da pasta com os bytes do corpo de antes."""
    import notas_modelos as NM
    # as minutas que o LG04 acrescentou não existiam antes: ficam de fora
    assert set(MINUTAS_MUDADAS_NO_LD02) | set(MINUTAS_MUDADAS_NO_LD07) | set(
        MINUTAS_MUDADAS_NO_LH13) <= {m["codigo"] for m in ouro_d["minutas"]}
    assert OURO_D.normal([m for m in NM.MODELOS
                          if m["codigo"] not in MINUTAS_DO_LG04]) == [
        _minuta_de_hoje(m) for m in ouro_d["minutas"]]
    for antes in map(_minuta_de_hoje, ouro_d["minutas"]):
        arquivo = RAIZ / "modelos_padrao" / "notas" / "minutas" / f"{antes['codigo']}.txt"
        assert arquivo.read_bytes() == antes["corpo"].encode("utf-8"), antes["codigo"]
        ficha = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
        assert ficha["nome"] == antes["nome"] and ficha["chave"] == antes["codigo"]
        de_fabrica = NM.por_codigo(antes["codigo"])
        assert (de_fabrica["corpo"], de_fabrica["nome"]) == (antes["corpo"], antes["nome"])


def test_o_texto_das_notas_lido_direto_da_base_e_o_da_pasta(casa, ouro_d):
    """Direto da tabela da base, e não pelo cache: o que está lá é a pasta, e a
    minuta é a de antes."""
    MOD.carregar_base()
    linhas = banco(_con(casa)).ler(
        f'SELECT chave, corpo, impressao_digital FROM "{MOD.schema_da_base()}".padroes '
        "ORDER BY chave")
    na_base = {r["chave"]: r for r in linhas}
    pasta = PASTA.ler_pasta()["padroes"]
    novos = [c for c in pasta if c.startswith(("NOTAS_", "NT-"))]
    assert len(novos) == 102 + 33 + len(MINUTAS_DO_LG04) + len(
        {c for c in PAPEIS_DO_LG04 if c.startswith("NOTAS_")}) + len(
        PAPEIS_DO_LD02 | PECAS_DO_LD02) + len(PECAS_DO_LD07)
    for chave in novos:
        assert na_base[chave]["corpo"] == pasta[chave]["corpo"], chave
        assert na_base[chave]["impressao_digital"] == hashlib.sha256(
            pasta[chave]["corpo"].encode("utf-8")).hexdigest(), chave
    for antes in map(_minuta_de_hoje, ouro_d["minutas"]):
        assert na_base[antes["codigo"]]["corpo"] == antes["corpo"], antes["codigo"]


def test_o_rotulo_do_selo_e_o_aviso_do_cartao_saem_iguais_aos_de_antes(ouro_d):
    """Os dois textos que moravam DENTRO de rotas: o rótulo do selo (escrito
    duas vezes, igual — agora uma) e o aviso do cartão sem selo de abertura."""
    import notas_web as NW
    for rotulos in ouro_d["rotas"]["rotulo_do_selo"]:
        for tipo, rotulo in rotulos.items():
            assert NW.rotulo_do_selo(tipo) == rotulo, tipo
    assert "SELO DO ATO" in ouro_d["rotas"]["rotulo_do_selo_sem_tipo"]
    assert NW.rotulo_do_selo("NOTARIAL_QUE_NAO_EXISTE") == "SELO DO ATO"
    assert NW.rotulo_do_selo(None) == "SELO DO ATO"
    assert ouro_d["rotas"]["cartao_sem_selo_de_abertura"] == [
        MOD.padrao_de("NOTAS_CARTAO_FICHA__sem_selo")]


# ------------------------------------------------ a peça e a regra


def test_cada_peca_das_notas_tem_ficha_e_e_do_formato_que_o_codigo_preenche():
    """A peça é preenchida com `str.format` pelo montador: o formato dela é
    CHAVES — dito na ficha dela, que também diz QUANDO a regra a escolhe."""
    for chave, p in PASTA.ler_pasta()["padroes"].items():
        if not (chave.startswith("NOTAS_") and p["peca_de"]):
            continue
        assert p["formato"] == MOD.CHAVES, chave
        assert p["explica"].strip(), chave
        assert p["campos"] == PASTA._campos(p["corpo"], MOD.CHAVES), chave


def test_os_textos_de_uma_montagem_vao_ao_banco_uma_vez_so(monkeypatch):
    """Uma frase do teor passa por dez peças; a mesma peça pedida de novo na
    mesma montagem não volta ao banco. E quem abre a conexão (`db.connect`)
    só a abre na primeira vez."""
    lidas, abertas = [], []
    monkeypatch.setattr(MOD, "texto_do_papel",
                        lambda con, chave: lidas.append(chave) or f"<{chave}>")

    class _ComAjuste:
        def tem_tabela(self, nome):
            return True

    monkeypatch.setattr(MOD, "banco", lambda con: _ComAjuste())

    class _Aberta:
        def __enter__(self):
            abertas.append(1)
            return self

        def __exit__(self, *_):
            return False

    textos = MOD.textos(lambda: _Aberta())
    assert textos("NOTAS_FECHO_ATA") == textos("notas_fecho_ata") == "<NOTAS_FECHO_ATA>"
    assert lidas == ["NOTAS_FECHO_ATA"] and abertas == [1]
    assert MOD.textos(textos) is textos


def test_banco_sem_as_tabelas_do_ajuste_usa_o_padrao_e_nao_derruba_a_transacao():
    """O banco que só tem o esquema das Notas (o teste do livro, a ferramenta
    avulsa) não tem ajuste nenhum: vale o padrão. E a montagem não CONSULTA a
    tabela que falta — no PostgreSQL isso derrubaria a transação do
    lançamento que chamou o termo."""
    sys.path.insert(0, str(RAIZ / "tests"))
    from banco_de_teste import conexao_de_teste
    import notas_livro as NL
    from notas_schema import init_notas_schema
    con = conexao_de_teste()
    with con:
        init_notas_schema(con)
    assert not banco(con).tem_tabela("mo_elementos")
    with con:
        termo = NL.texto_termo_abertura("ESCRITURA", "7", 10, OURO_D.SV, OURO_D.DATA,
                                        con=con)
        assert banco(con).valor("SELECT 1 AS um") == 1      # a transação seguiu
    assert termo == NL.texto_termo_abertura("ESCRITURA", "7", 10, OURO_D.SV, OURO_D.DATA)
    con.close()


def test_ajuste_antigo_com_claro_que_o_montador_nao_preenche_e_erro_claro(casa):
    """O ajuste gravado em `mo_modelos` não passou pela tela. Claro inventado
    nele não pode virar `KeyError` no balcão: vira o recado de qual papel
    consertar."""
    import notas_schema as NS
    con = _con(casa)
    with con:
        MOD.salvar(con, "NOTAS_RECONHECIMENTO_SINAL",
                   corpo="RECONHEÇO O SINAL DE {cartorio}. DOU FÉ.",
                   quem="mario", agora="2026-10-19T09:00")
    with pytest.raises(MOD.ModeloError) as erro:
        NS.texto_reconhecimento_sinal("maria de exemplo", con=con)
    assert "NOTAS_RECONHECIMENTO_SINAL" in str(erro.value)
    assert "{quem}" in str(erro.value)


# ------------------------------------------------ o ajuste da casa chega ao papel


def test_o_ajuste_da_casa_vale_na_etiqueta_do_reconhecimento(casa):
    """A prova que fecha o pedido: o oficial muda a fórmula na tela de Modelos,
    e a próxima etiqueta sai com ela. Sem `con` — o caminho do padrão — sai a
    de fábrica."""
    import notas_schema as NS
    r = _gravar(casa, "NOTAS_RECONHECIMENTO_SEMELHANCA",
                "RECONHEÇO, POR SEMELHANÇA, A FIRMA DE {quem}. DOU FÉ.")
    assert r.status_code == 200
    con = _con(casa)
    assert (NS.texto_reconhecimento("SEMELHANCA", ["maria de exemplo"], con=con)
            == "RECONHEÇO, POR SEMELHANÇA, A FIRMA DE MARIA DE EXEMPLO. DOU FÉ.")
    assert (NS.texto_reconhecimento("SEMELHANCA", ["maria de exemplo"])
            == "RECONHEÇO POR SEMELHANÇA A FIRMA DE MARIA DE EXEMPLO. DOU FÉ.")
    # a outra espécie não foi tocada
    assert NS.texto_reconhecimento("AUTENTICIDADE", ["maria de exemplo"], con=con) == (
        "RECONHEÇO POR AUTENTICIDADE A FIRMA DE MARIA DE EXEMPLO. DOU FÉ.")


def test_o_ajuste_da_abertura_vale_no_teor_montado(casa):
    """A abertura da escritura editada na tela entra no teor que `montar`
    escreve — e o resto do teor continua o de fábrica."""
    import notas_teor as NT
    import modelos_elementos as ELEM
    con = _con(casa)
    with con:
        ELEM.salvar(con, atribuicao="NOTAS", ato="NOTAS_ABERTURA_ESCRITURA",
                    parte="CORPO", quem="mario", agora="2026-10-19T09:00",
                    corpo="SAIBAM os que virem esta escritura que, aos {data_extenso}, "
                          "em {cidade}, compareceram:")
    teor = NT.montar("ESCRITURA", OURO_D.PARTES["escritura"], "o objeto de exemplo",
                     OURO_D.DATA, "Cidade Exemplo", "MA", con=con)
    assert teor.startswith("<p>SAIBAM os que virem esta escritura que, aos "
                           + OURO_D.DATA + ", em Cidade Exemplo, compareceram: como VENDEDOR")
    assert MOD.padrao_de("NOTAS_FECHO_ESCRITURA").split(" Assinam")[0] in teor


def test_a_tela_recusa_claro_que_o_papel_das_notas_nao_preenche(casa):
    """`{cartorio}` passaria pela conferência das chaves e estouraria no balcão:
    a fórmula do sinal só recebe `{quem}`. A tela diz quais claros o papel tem,
    e não grava."""
    r = _gravar(casa, "NOTAS_RECONHECIMENTO_SINAL",
                "RECONHEÇO O SINAL PÚBLICO DE {cartorio}. DOU FÉ.")
    html = " ".join(r.get_data(as_text=True).split())
    assert "claros que este papel não tem: «{cartorio}»" in html
    assert "{quem}" in html
    assert banco(_con(casa)).um(
        "SELECT corpo FROM mo_elementos WHERE ato = %s AND parte = 'CORPO'",
        ("NOTAS_RECONHECIMENTO_SINAL",)) is None
    # e o encerramento e o rodapé PRÓPRIOS do papel entram no mesmo texto que
    # o montador preenche: conferem-se igual
    import modelos_elementos as ELEM
    for parte in ("ENCERRAMENTO", "RODAPE"):
        assert "claros que este papel não tem: «{cartorio}»" in ELEM.conferir(
            "NOTAS", "NOTAS_RECONHECIMENTO_SINAL", parte, "Dou fé, {cartorio}.")
    assert ELEM.conferir("NOTAS", "NOTAS_RECONHECIMENTO_SINAL", "ENCERRAMENTO",
                         "Dou fé, {quem}.") == ""


def test_a_tela_e_o_balcao_conferem_o_claro_das_notas_com_a_mesma_regua():
    """UMA RÉGUA, NOS DOIS LADOS: o recado da tela é o mesmo do `preencher`
    que o montador chama — a 3ª volta do LF06D juntou a conferência das Notas
    à `conferir_claros`, como o LF06C fez com a do civil. E o papel que não tem
    claro nenhum (o fecho do teor) diz isso, e não «Os que ele tem: .»."""
    import modelos_elementos as ELEM
    torto = "E, de como assim o disse, dou fé em {cartorio}."
    na_tela = ELEM.conferir("NOTAS", "NOTAS_FECHO_ESCRITURA", "CORPO", torto)
    assert na_tela.endswith("«{cartorio}». Este papel não tem claro nenhum.")
    with pytest.raises(MOD.ModeloError) as no_balcao:
        MOD.preencher("NOTAS_FECHO_ESCRITURA", torto, {})
    assert na_tela in str(no_balcao.value)
    # o padrão de cada papel das Notas passa na régua dele
    for chave in sorted(PAPEIS_DO_LF06D):
        c = MOD.POR_CHAVE[chave]
        if c.get("so_claros_do_padrao"):
            assert ELEM.conferir("NOTAS", chave, "CORPO", MOD.padrao_de(chave)) == "", chave


def test_o_termo_ja_lavrado_no_livro_nao_muda_quando_o_texto_muda(casa):
    """TEXTO EXPEDIDO E CONGELADO NÃO MUDA. O termo de abertura gravado no
    livro fica como foi lavrado; o ajuste da casa vale para o livro seguinte."""
    import modelos_elementos as ELEM
    import notas_livro as NL
    sv = OURO_D.SV
    con = _con(casa)
    with con:
        primeiro = NL.abrir_livro(con, "ESCRITURA", sv, "2026-10-19T09:00", OURO_D.DATA,
                                  numero="LF06D-1", folhas=10)
    lavrado = banco(con).valor("SELECT termo_abertura FROM nt_livros WHERE id = %s",
                               (primeiro,))
    assert lavrado == NL.texto_termo_abertura("ESCRITURA", "LF06D-1", 10, sv, OURO_D.DATA)
    with con:
        ELEM.salvar(con, atribuicao="NOTAS", ato="NOTAS_LIVRO_ABERTURA", parte="CORPO",
                    quem="mario", agora="2026-10-19T09:30",
                    corpo="TERMO DE ABERTURA DA CASA. Livro n. {numero}, de {serie}, "
                          "com {folhas} folhas. {cidade}-{uf}, {data_extenso}.")
        segundo = NL.abrir_livro(con, "ESCRITURA", sv, "2026-10-19T10:00", OURO_D.DATA,
                                 numero="LF06D-2", folhas=10)
    assert banco(con).valor("SELECT termo_abertura FROM nt_livros WHERE id = %s",
                            (primeiro,)) == lavrado
    assert banco(con).valor("SELECT termo_abertura FROM nt_livros WHERE id = %s",
                            (segundo,)) == (
        "TERMO DE ABERTURA DA CASA. Livro n. LF06D-2, de Escrituras Publicas, com 10 "
        "(dez) folhas. Cidade Exemplo-UF, " + OURO_D.DATA + ".")


# ------------------------------------------------ a revisão: o ajuste chega onde se grava


def _procuracao_no_livro(bd, folha: str, tipo: str = "PROCURACAO") -> int:
    """Um ato já lançado no livro (tem margem), sem dado de gente."""
    return int(bd.escrever(
        """INSERT INTO nt_atos(tipo, data, livro, folha, numero_ordem, situacao,
                               interessado, teor, criado_em)
           VALUES (%s, '2024-03-11', '27', %s, 100, 'LAVRADO',
                   'MARIA DE EXEMPLO', '<p>poderes de exemplo</p>',
                   '2026-10-19T09:00')
           RETURNING id""", (tipo, folha))[0]["id"])


def test_a_anotacao_a_margem_sai_com_o_ajuste_da_casa_e_a_ja_escrita_nao_muda(casa):
    """REVISÃO DO LF06D: `anotar` montava a margem SEM a conexão — o padrão, e
    nunca o ajuste —, e a casa editava a frase da margem e a anotação gravada
    continuava a de fábrica. Com o ajuste, a PRÓXIMA anotação sai com ele; a
    que já estava escrita na margem não muda."""
    import notas_anotacoes as NA
    con = _con(casa)
    bd = banco(con)
    with con:
        primeira = _procuracao_no_livro(bd, "139")
        segunda = _procuracao_no_livro(bd, "140")
        NA.anotar(con, primeira, "REVOGACAO", "2026-10-19T09:00", sv=OURO_D.SV,
                  data="2026-10-19")
    with con:
        MOD.salvar(con, "NOTAS_ANOTACAO_MARGEM__verbo_revogacao",
                   corpo="REVOGADA, CONFORME A CASA,", quem="mario",
                   agora="2026-10-19T09:30")
        MOD.salvar(con, "NOTAS_ANOTACAO_MARGEM",
                   corpo="por ato lavrado na {serventia}, de exemplo", quem="mario",
                   agora="2026-10-19T09:30")
        NA.anotar(con, segunda, "REVOGACAO", "2026-10-19T10:00", sv=OURO_D.SV,
                  data="2026-10-19")
    margem = {r["ato_id"]: r["texto"] for r in bd.ler(
        "SELECT ato_id, texto FROM nt_ato_anotacoes WHERE ato_id IN (%s, %s) "
        "ORDER BY ato_id", (primeira, segunda))}
    assert margem[primeira] == NA.texto_padrao("REVOGACAO", None, OURO_D.SV,
                                               "2026-10-19")
    assert margem[segunda] == (
        "REVOGADA, CONFORME A CASA, por ato lavrado na SERVENTIA EXTRAJUDICIAL DE "
        "EXEMPLO, de exemplo em 19/10/2026.")


def test_margem_que_nao_monta_recusa_a_anotacao_e_o_lancamento_nao_a_engole(
        casa, monkeypatch):
    """O ajuste antigo com claro que o montador não preenche vira a recusa do
    módulo (`AnotacaoError`, que a rota mostra) com o nome do papel. E
    `anotar_ato_anterior`, que engole a `AnotacaoError` de «já anotada», NÃO
    engole esta: o lançamento e a anotação são um ato só, e o lançamento
    sairia sem a margem que pediu."""
    import notas_anotacoes as NA
    con = _con(casa)
    bd = banco(con)
    with con:
        procuracao = _procuracao_no_livro(bd, "141")
        revogacao = _procuracao_no_livro(bd, "142", tipo="REVOGACAO")
        MOD.salvar(con, "NOTAS_ANOTACAO_MARGEM",
                   corpo="por ato lavrado em {cartorio}", quem="mario",
                   agora="2026-10-19T09:30")
    with pytest.raises(NA.AnotacaoError) as erro:
        with con:
            NA.anotar(con, procuracao, "REVOGACAO", "2026-10-19T10:00", sv=OURO_D.SV)
    assert "NOTAS_ANOTACAO_MARGEM" in str(erro.value)
    assert "{cartorio}" in str(erro.value)
    monkeypatch.setattr(NA, "localizar_ato_anterior",
                        lambda con, ato, sv: {"id": procuracao})
    with pytest.raises(NA.ModeloDaMargemError):
        with con:
            NA.anotar_ato_anterior(con, revogacao, OURO_D.SV, "2026-10-19T10:00",
                                   "mario")
    assert bd.valor("SELECT count(*) AS n FROM nt_ato_anotacoes WHERE ato_id = %s",
                    (procuracao,)) == 0


def test_termo_do_livro_que_nao_monta_e_recusa_do_livro_com_o_nome_do_papel(casa):
    """`abrir_livro` e `encerrar_livro` gravam o termo: o ajuste que não monta
    vira `LivroError` — a recusa que a rota já mostra —, e não erro 500."""
    import notas_livro as NL
    con = _con(casa)
    with con:
        lid = NL.abrir_livro(con, "ESCRITURA", OURO_D.SV, "2026-10-19T09:00",
                             OURO_D.DATA, numero="LF06D-7", folhas=10)
        MOD.salvar(con, "NOTAS_LIVRO_ABERTURA", corpo="Livro {numero} da {cartorio}.",
                   quem="mario", agora="2026-10-19T09:30")
        MOD.salvar(con, "NOTAS_LIVRO_ENCERRAMENTO", corpo="Encerro {livro}.",
                   quem="mario", agora="2026-10-19T09:30")
    with pytest.raises(NL.LivroError) as erro:
        with con:
            NL.abrir_livro(con, "ESCRITURA", OURO_D.SV, "2026-10-19T10:00",
                           OURO_D.DATA, numero="LF06D-8", folhas=10)
    assert "NOTAS_LIVRO_ABERTURA" in str(erro.value)
    with pytest.raises(NL.LivroError) as erro:
        with con:
            NL.encerrar_livro(con, lid, OURO_D.SV, "2026-10-19T10:00", OURO_D.DATA)
    assert "NOTAS_LIVRO_ENCERRAMENTO" in str(erro.value)
    assert banco(con).valor("SELECT encerrado FROM nt_livros WHERE id = %s",
                            (lid,)) == 0


def test_a_descricao_do_livro_fica_a_de_fabrica_e_o_termo_segue_o_ajuste(casa):
    """A DESCRIÇÃO DO LIVRO É DADO (as listas, a importação do E-Ofício): sai
    do padrão, com os bytes do `NOME_DA_SERIE` de antes, mesmo com o nome da
    série ajustado — mudar o nome dos livros novos é pergunta para o oficial.
    O termo de abertura é papel da casa, e segue o ajuste."""
    import notas_livro as NL
    con = _con(casa)
    with con:
        MOD.salvar(con, "NOTAS_LIVRO_ABERTURA__serie_escritura",
                   corpo="Escrituras Públicas da Casa", quem="mario",
                   agora="2026-10-19T09:30")
        lid = NL.abrir_livro(con, "ESCRITURA", OURO_D.SV, "2026-10-19T10:00",
                             OURO_D.DATA, numero="LF06D-9", folhas=10)
    linha = banco(con).um("SELECT descricao, termo_abertura FROM nt_livros "
                          "WHERE id = %s", (lid,))
    assert linha["descricao"] == "Escrituras Publicas"
    assert linha["descricao"] == MOD.padrao_de("NOTAS_LIVRO_ABERTURA__serie_escritura")
    assert "Livro n. LF06D-9, de Escrituras Públicas da Casa, contem" in (
        linha["termo_abertura"])


def test_o_titulo_e_o_periodo_da_certidao_das_notas_seguem_o_ajuste_nas_telas(
        casa, monkeypatch):
    """REVISÃO DO LF06D: a busca, a ficha e a moldura do .odt da certidão
    liam o período e o título SEM a conexão — o padrão —, enquanto a certidão
    que `emitir` congela já os lia com ela: a tela mostrava uma frase e o papel
    saía com outra. O teor congelado continua o de quando foi emitida."""
    import atribuicoes_web as AW
    import notas_certidao as NCE
    con = _con(casa)
    with con:
        MOD.salvar(con, "NOTAS_CERTIDAO_POSITIVA__periodo",
                   corpo="entre {de} e {ate}, conferido", quem="mario",
                   agora="2026-10-19T09:30")
        MOD.salvar(con, "NOTAS_CERTIDAO_NEGATIVA__titulo",
                   corpo="Certidão negativa de atos da casa", quem="mario",
                   agora="2026-10-19T09:30")
    cliente = casa["cliente"]
    busca = {"nome": "PESSOA INEXISTENTE DE EXEMPLO", "de": "2010-01-01",
             "ate": "2026-10-15"}
    html = " ".join(cliente.get("/notas/certidoes", query_string=busca)
                    .get_data(as_text=True).split())
    assert "entre 01/01/2010 e 15/10/2026, conferido" in html
    with con:
        r = NCE.emitir(con, hoje="2026-10-19", agora="2026-10-19T10:00",
                       nome=busca["nome"], periodo_de=busca["de"],
                       periodo_ate=busca["ate"], usuario="MARIO EXEMPLO DOS SANTOS",
                       usuario_funcao="Escrevente")
    assert r["tipo"] == "NEGATIVA"
    assert "entre 01/01/2010 e 15/10/2026, conferido" in r["teor"]
    html = " ".join(cliente.get(f"/notas/certidoes/{r['certidao_id']}")
                    .get_data(as_text=True).split())
    assert f"Certidão negativa de atos da casa n. {r['numero']}/{r['ano']}" in html
    capturado = []
    monkeypatch.setattr(AW, "gerar_odt",
                        lambda corpo, **_: capturado.append(corpo) or b"odt")
    resposta = cliente.get(f"/notas/certidoes/{r['certidao_id']}/odt",
                           query_string={"formato": "odt"})
    assert resposta.status_code == 200
    assert "CERTIDÃO NEGATIVA DE ATOS DA CASA" in capturado[0]


# ------------------------------------------------ as minutas na subida


def test_a_subida_semeia_as_minutas_com_o_texto_da_base(casa, ouro_d):
    """`nt_modelos` é onde mora o ajuste da casa, e continua lá: a subida
    (`notas_modelos.instalar`, pelo `init_schema`) semeia a linha de fábrica
    com o texto da base — o de antes, byte a byte — e não toca a editada."""
    import notas_modelos as NM
    con = _con(casa)
    bd = banco(con)
    for antes in map(_minuta_de_hoje, ouro_d["minutas"]):
        linha = bd.um("SELECT nome, corpo FROM nt_modelos WHERE codigo = %s "
                      "AND origem = 'SISTEMA'", (antes["codigo"],))
        assert linha and linha["corpo"] == antes["corpo"], antes["codigo"]
        assert linha["nome"] == antes["nome"]
    with con:
        bd.escrever("UPDATE nt_modelos SET corpo = %s, atualizado_em = %s "
                    "WHERE codigo = %s", ("MINUTA DA CASA", "2026-10-19T09:00",
                                          "NT-ESC-DOACAO"))
        assert NM.instalar(con, "2026-10-19T10:00")["atualizados"] == 0
    assert bd.valor("SELECT corpo FROM nt_modelos WHERE codigo = %s",
                    ("NT-ESC-DOACAO",)) == "MINUTA DA CASA"


def test_minuta_que_nao_esta_na_base_e_erro_claro(monkeypatch):
    """Sem a minuta na base, a subida não semeia folha em branco: o erro diz
    qual arquivo faltou."""
    monkeypatch.setattr(MOD, "_padroes",
                        lambda: {"padroes": {}, "origem": "base", "erro": None})
    with pytest.raises(MOD.ModeloError) as erro:
        MOD.minuta_de_fabrica("NT-ESC-DOACAO")
    assert "modelos_padrao/notas/minutas/NT-ESC-DOACAO.txt" in str(erro.value)


def test_nenhum_modulo_das_notas_le_a_base_na_hora_do_import():
    """«Nada de leitura da base na hora do import» (`docs/MODELOS_PADRAO.md`):
    o nome antigo (`TIPOS_AUTENTICACAO`, `NOME_DA_SERIE`, `MODELOS`…) responde
    quando é lido, e não quando o módulo carrega — senão a casa não subiria
    com a base fora do ar."""
    codigo = (
        "import modelos_da_casa as M\n"
        "def _nao(*a, **k):\n"
        "    raise SystemExit('leu a base na hora do import')\n"
        "M._padroes = _nao\n"
        "import notas_schema, notas_livro, notas_teor, notas_inutilizacao\n"
        "import notas_anotacoes, notas_certidao, notas_modelos\n"
        "import modelos_motor_etiqueta, notas_web\n")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]


# ================================== A RETIFICAÇÃO E A USUCAPIÃO — LF06G
#
#   Os papéis da retificação e da usucapião saíram de `rt_notificacao`,
#   `us_notificacao` e `usucapiao` para `modelos_padrao/retificacao/` e
#   `modelos_padrao/usucapiao/`, e cada frase que o processo decide virou peça
#   do papel dela. **A PROVA DE QUE NADA MUDOU É O OURO DO LOTE**, gravado
#   ANTES, no commit 2c41e90 (`fixtures/modelos_ouro/ouro_lf06g.py`): trinta
#   papéis montados, contexto por contexto — inclusive as recusas.

_ESPEC_G = importlib.util.spec_from_file_location(
    "ouro_lf06g", RAIZ / "tests" / "fixtures" / "modelos_ouro" / "ouro_lf06g.py")
OURO_G = importlib.util.module_from_spec(_ESPEC_G)
_ESPEC_G.loader.exec_module(OURO_G)

PAPEIS_DO_LF06G = ("RT_NOTIFICACAO_CONFRONTANTE", "US_NOTIFICACAO", "US_EDITAL",
                   "US_OFICIO_AO_ENTE", "US_DECISAO_PROCEDENTE",
                   "US_DECISAO_IMPROCEDENTE", "US_DECISAO_EXIGENCIA",
                   "US_DECISAO_REMESSA_JUIZO", "US_DOSSIE_PEDIDO")

# um processo de usucapião de exemplo, para os papéis que não leem o banco
P_US = {"numero": "2026.001", "ano": 2026, "modalidade": "EXTRAORDINARIA",
        "requerente_nome": "MARIA DE EXEMPLO",
        "imovel_descricao": "Lote 4 da Quadra B, de exemplo"}
N_US = {"destinatario": "SICRANO DE EXEMPLO", "destinatario_papel": "Confrontante",
        "endereco": "Rua Vizinha, 200", "forma": "PESSOAL",
        "prazo_chave": "CONFRONTANTE", "prazo_dias": 15}


@pytest.fixture(scope="module")
def ouro_g():
    return OURO_G.ouro()


def _processo_do_dossie(casa):
    con = _con(casa)
    with con:
        pid = OURO_G.processo_de_exemplo(con)
    return con, pid


def test_o_ouro_do_lf06g_foi_gravado_antes_da_mudanca(ouro_g):
    """Do commit de ANTES (2c41e90), com as constantes de então e os trinta
    papéis montados — seis deles recusas, que também são saída: a mudança não
    pode passar a aceitar o papel que o montador recusava."""
    assert ouro_g["commit"] == "2c41e90"
    assert len(ouro_g["funcoes"]) == 30
    assert sum(1 for v in ouro_g["funcoes"].values() if "erro" in v) == 6
    assert set(ouro_g["constantes"]) == {
        "rt_notificacao.MODELO", "us_notificacao.CABECA", "us_notificacao.CORPO",
        "us_notificacao.EDITAL", "us_notificacao.OFICIO_AO_ENTE",
        "rt_tjma.SILENCIO_VALE_ANUENCIA", "rt_tjma.COMO_NOTIFICAR"}


def test_os_papeis_da_retificacao_e_da_usucapiao_sao_do_registro_de_imoveis():
    """Retificação de área e usucapião extrajudicial são procedimentos DO
    oficial de registro de imóveis, e não atribuições: o papel deles fica na
    tela do Registro de Imóveis. E `{claro}` no meio do Jinja do RI não pode
    herdar o encerramento comum da atribuição — sairia escrito no papel."""
    for chave in PAPEIS_DO_LF06G:
        c = MOD.POR_CHAVE[chave]
        assert c["atribuicao"] == "Registro de Imóveis", chave
        assert MOD.formato_de(chave) == MOD.CHAVES, chave
        assert c["elementos_comuns"] is False, chave


def test_o_padrao_novo_e_byte_a_byte_a_constante_de_antes(ouro_g):
    """O texto que era constante foi para a pasta com os mesmos bytes — o
    arquivo, e o que a base devolve."""
    k = ouro_g["constantes"]
    for chave, antes in {
            "RT_NOTIFICACAO_CONFRONTANTE": k["rt_notificacao.MODELO"],
            "US_NOTIFICACAO": k["us_notificacao.CORPO"],
            "US_NOTIFICACAO__cabeca": k["us_notificacao.CABECA"],
            "US_EDITAL": k["us_notificacao.EDITAL"],
            "US_OFICIO_AO_ENTE": k["us_notificacao.OFICIO_AO_ENTE"]}.items():
        arquivo = RAIZ / MOD.arquivo_do_padrao(chave)
        assert arquivo.read_bytes() == antes.encode("utf-8"), chave
        assert MOD.padrao_de(chave) == antes, chave


def test_os_papeis_montados_saem_iguais_aos_de_antes(casa, ouro_g, monkeypatch):
    """O TESTE-OURO DO LOTE, pelo padrão da base: os trinta, saída por saída.

    E CADA PEÇA DA PASTA É LIDA POR ALGUM PAPEL — peça que nenhum montador
    alcança seria frase que ninguém imprime, e o ouro não a protegeria."""
    con, pid = _processo_do_dossie(casa)
    lidas: set[str] = set()
    original = MOD.padrao_de
    monkeypatch.setattr(MOD, "padrao_de", lambda chave: (
        lidas.add(PASTA.chave_normal(chave)) or original(chave)))
    for nome, f in OURO_G.chamadas(None, con, pid).items():
        assert OURO_G.normal(OURO_G.tenta(f)) == ouro_g["funcoes"][nome], nome
    pecas = {p.stem for pasta in ("retificacao", "usucapiao")
             for p in (RAIZ / "modelos_padrao" / pasta).glob("*__*.txt")}
    assert len(pecas) == 41
    assert pecas <= lidas, sorted(pecas - lidas)


def test_pela_busca_unica_sem_ajuste_o_papel_e_o_mesmo_de_antes(casa, ouro_g):
    """O mesmo ouro pelo caminho da rota — a conexão da casa, a busca única
    (ajuste → base) — sem ajuste nenhum gravado."""
    con, pid = _processo_do_dossie(casa)
    for nome, f in OURO_G.chamadas(con, con, pid).items():
        assert OURO_G.normal(OURO_G.tenta(f)) == ouro_g["funcoes"][nome], nome


def test_o_silencio_e_as_formas_do_papel_partem_da_norma():
    """A frase do papel e a da norma eram o MESMO objeto (`rt_tjma`). Agora a
    tela das normas mostra a lei e o papel imprime a peça — e o padrão de
    fábrica da peça continua sendo o texto da norma. Se a leitura da norma for
    corrigida, este teste avisa que o padrão do papel ficou para trás. E toda
    forma da norma tem a sua peça no recibo: forma nova sem peça seria papel
    que não sai."""
    import rt_tjma as NORMA
    assert MOD.padrao_de("RT_NOTIFICACAO_CONFRONTANTE__silencio") == (
        NORMA.SILENCIO_VALE_ANUENCIA["o_que"])
    for f in NORMA.COMO_NOTIFICAR:
        assert MOD.padrao_de(f"US_NOTIFICACAO__forma_{f['forma'].lower()}") == (
            f["o_que"]), f["forma"]


def test_a_tela_confere_com_os_mesmos_claros_que_o_padrao_usa():
    """A lista de claros do conferidor é a que o montador preenche. Os três
    papéis expedidos usam todos eles; as quatro decisões, juntas, também (a
    improcedente não fala do imóvel, e pode passar a falar). Uma lista a mais
    ou a menos seria a tela aprovando o que o papel não monta, ou recusando o
    que ele monta."""
    import rt_notificacao as RTN
    import us_notificacao as UN
    import usucapiao as US
    for chave, claros in {"RT_NOTIFICACAO_CONFRONTANTE": RTN.CLAROS,
                          **UN.CLAROS_POR_PAPEL}.items():
        assert set(MOD.POR_CHAVE[chave]["campos"]) == set(claros), chave
    decisoes = set()
    for chave in US.PAPEL_DA_DECISAO.values():
        assert set(MOD.POR_CHAVE[chave]["campos"]) <= set(US.CLAROS_DA_DECISAO)
        decisoes |= set(MOD.POR_CHAVE[chave]["campos"])
    assert decisoes == set(US.CLAROS_DA_DECISAO)
    assert MOD.POR_CHAVE["US_DOSSIE_PEDIDO"]["campos"] == []


def test_cada_papel_novo_tem_conferidor_que_aceita_o_padrao_e_recusa_o_resto(casa):
    """A tela confere CHAVES com a régua de quem monta — e não com o Jinja
    genérico, que aprovaria `{claro_inventado}` como texto qualquer."""
    conferidores = casa["app"].extensions.get("conferidores_de_modelo", {})
    for chave in PAPEIS_DO_LF06G:
        assert conferidores[chave](MOD.padrao_de(chave)) == "", chave
        assert "nao_existe" in conferidores[chave]("Texto {nao_existe}."), chave
        assert "Jinja" in conferidores[chave]("Texto {{ a.numero }}."), chave


def test_a_tela_abre_cada_papel_novo_para_editar(casa):
    """O pedido era «editar com mais facilidade»: cada papel novo abre no
    editor, diz de que arquivo o padrão sai e com que marcador se escreve."""
    for chave in PAPEIS_DO_LF06G:
        html = _tela(casa, editar=chave)
        assert "textarea" in html, chave
        assert MOD.POR_CHAVE[chave]["arquivo"] in html, chave
        assert "uma chave" in html, chave


def test_a_tela_recusa_a_notificacao_com_claro_que_ela_nao_tem(casa):
    """Claro inventado estouraria na hora de notificar, com o confrontante
    esperando; a tela o recusa ao gravar, e diz qual."""
    r = _gravar(casa, "RT_NOTIFICACAO_CONFRONTANTE", "Fica notificado {vizinho}.")
    html = " ".join(r.get_data(as_text=True).split())
    assert "não foi gravado" in html and "vizinho" in html
    assert banco(_con(casa)).um(
        "SELECT 1 AS um FROM mo_elementos WHERE ato = %s",
        ("RT_NOTIFICACAO_CONFRONTANTE",)) is None


def _retificacao_com_dois_confrontantes(casa):
    import retificacao as RT
    import rt_tjma as NORMA
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, situacao, criado_em)
               VALUES ('3247', '2', 'ATIVA', ?)""", (OURO_G.AGORA,))
        pid = RT.autuar(
            con, numero="9/2026", especie=NORMA.GEORREFERENCIADA,
            fundamento=NORMA.A_REQUERIMENTO, matricula_id=int(cur.lastrowid),
            rural=True, agora=OURO_G.AGORA, usuario="mario", ano=2026,
            requerente_nome="ANTONIO DE EXEMPLO")
        ids = []
        for nome in ("SICRANO DE EXEMPLO", "BELTRANO DE EXEMPLO"):
            cur = con.execute(
                """INSERT INTO rt_confrontantes (processo_id, papel, nome,
                       nome_norm, endereco, divisa_afetada, criado_em)
                   VALUES (?, 'CONFRONTANTE', ?, ?, 'Rua Exemplo, 10', 0, ?)""",
                (pid, nome, nome.lower(), OURO_G.AGORA))
            ids.append(int(cur.lastrowid))
    return con, ids


def _notificar_na_retificacao(con, confrontante_id: int) -> str:
    import retificacao as RT
    with con:
        RT.notificar(con, confrontante_id, forma="CORREIO", quando=OURO_G.HOJE,
                     agora=OURO_G.AGORA, prazo_ate="2026-11-09",
                     serventia=OURO_G.SERVENTIA,
                     hoje_extenso=OURO_G.HOJE_EXTENSO)
    return con.execute(
        "SELECT teor_expedido FROM rt_confrontantes WHERE id = ?",
        (confrontante_id,)).fetchone()["teor_expedido"]


def test_o_ajuste_da_casa_vale_na_proxima_notificacao_e_a_expedida_nao_muda(casa):
    """O PEDIDO DO OFICIAL, de ponta a ponta: o texto se edita na tela, e a
    próxima notificação sai com ele. **E O TEXTO EXPEDIDO NÃO MUDA**: o que o
    confrontante já recebeu continua congelado como foi entregue."""
    con, (primeiro, segundo) = _retificacao_com_dois_confrontantes(casa)
    antes = _notificar_na_retificacao(con, primeiro)
    assert "NOTIFICAÇÃO — RETIFICAÇÃO DE ÁREA" in antes

    ajuste = MOD.padrao_de("RT_NOTIFICACAO_CONFRONTANTE").replace(
        "NOTIFICAÇÃO — RETIFICAÇÃO DE ÁREA", "NOTIFICACAO AJUSTADA PELA CASA")
    assert _gravar(casa, "RT_NOTIFICACAO_CONFRONTANTE", ajuste).status_code == 200

    depois = _notificar_na_retificacao(con, segundo)
    assert "NOTIFICACAO AJUSTADA PELA CASA" in depois
    assert "NOTIFICAÇÃO — RETIFICAÇÃO DE ÁREA" not in depois
    assert con.execute(
        "SELECT teor_expedido FROM rt_confrontantes WHERE id = ?",
        (primeiro,)).fetchone()["teor_expedido"] == antes


def test_a_peca_ajustada_pela_casa_entra_no_papel(casa):
    """A peça não tem linha na tela de Modelos (LF06A); o ajuste dela mora em
    `mo_modelos`, com a chave da peça, e a busca única o encontra."""
    import us_notificacao as UN
    con = _con(casa)
    with con:
        MOD.salvar(con, "US_NOTIFICACAO__silencio",
                   corpo="O SILENCIO, NESTA CASA, SE ESCREVE ASSIM.",
                   quem="mario", agora=OURO_G.AGORA)
    teor = UN.montar(processo=P_US, notificacao=N_US, serventia=OURO_G.SERVENTIA,
                     hoje_extenso=OURO_G.HOJE_EXTENSO, con=con)
    assert "O SILENCIO, NESTA CASA, SE ESCREVE ASSIM." in teor
    assert "INTERPRETADO COMO CONCORDÂNCIA" not in teor
    # sem a conexão da casa, o padrão de fábrica
    assert "INTERPRETADO COMO CONCORDÂNCIA" in UN.montar(
        processo=P_US, notificacao=N_US, serventia=OURO_G.SERVENTIA,
        hoje_extenso=OURO_G.HOJE_EXTENSO)


def test_ajuste_quebrado_recusa_o_papel_pelo_nome_e_a_ficha_continua_abrindo(casa):
    """Gravado por fora da tela (que o recusaria), o ajuste com claro
    inventado não vira `KeyError`: o edital é recusado com o nome do papel e do
    claro, e a ficha do processo continua abrindo — a decisão quebrada aparece
    no lugar dela, dizendo qual."""
    import us_notificacao as UN
    import usucapiao as US
    con = _con(casa)
    with con:
        MOD.salvar(con, "US_EDITAL", corpo="EDITAL {inventado}", quem="mario",
                   agora=OURO_G.AGORA)
        MOD.salvar(con, "US_DECISAO_EXIGENCIA", corpo="NOTA {inventado}",
                   quem="mario", agora=OURO_G.AGORA)
    with pytest.raises(UN.NotificacaoError) as erro:
        UN.montar_edital(processo=P_US, serventia=OURO_G.SERVENTIA, con=con)
    assert "US_EDITAL" in str(erro.value) and "inventado" in str(erro.value)
    modelos = US.modelos_de_decisao(P_US, OURO_G.SV, con=con)
    assert "US_DECISAO_EXIGENCIA" in modelos["EXIGENCIA"]
    assert "inventado" in modelos["EXIGENCIA"]
    assert modelos["PROCEDENTE"].startswith("DECISÃO. Processo de usucapião")


def test_a_decisao_ajustada_na_tela_chega_a_ficha_do_processo(casa):
    """A ficha do processo oferece o modelo que a casa gravou — e não o de
    fábrica, que era o único que ela conhecia antes do LF06G."""
    con, pid = _processo_do_dossie(casa)
    _gravar(casa, "US_DECISAO_PROCEDENTE",
            "DECISAO AJUSTADA PELA CASA. Processo {numero}, de {requerente}.")
    html = casa["cliente"].get(f"/usucapiao/{pid}").get_data(as_text=True)
    assert "DECISAO AJUSTADA PELA CASA. Processo US-2026-901" in html


def test_o_pedido_do_dossie_ajustado_na_tela_vai_no_dossie(casa):
    """O pedido a quem analisa é texto da casa; o resto do dossiê é o processo
    listado, e continua igual."""
    import usucapiao as US
    con, pid = _processo_do_dossie(casa)
    _gravar(casa, "US_DOSSIE_PEDIDO",
            "## O que esta casa pede\n\nAnalise o processo {numero}, "
            "modalidade {modalidade}.")
    texto = US.montar_dossie(con, pid, hoje=OURO_G.HOJE)["texto"]
    assert "Analise o processo US-2026-901, modalidade Extraordinária." in texto
    assert "O que se pede a quem analisar" not in texto
    assert "## Peças juntadas (1)" in texto


# AS RESSALVAS DA REVISÃO DO LF06G, fechadas no LX18 (19/10/2026): o ajuste
# quebrado do pedido do dossiê, o recado do modelo quebrado no teor da decisão
# e a forma da notificação. Gravados por fora da tela, que os recusaria — mas
# `/ri/modelos` confere só chaves e Jinja, e um ajuste antigo não passou por
# régua nenhuma.

def test_o_dossie_com_o_pedido_quebrado_e_recusa_com_o_nome_e_nao_erro_500(casa):
    """O `ModeloError` do pedido subia cru de `montar_dossie`, e a rota do
    dossiê dava 500. Agora é `UsucapiaoError`, com o nome do papel e do claro,
    e a rota volta à ficha com o recado. Não se põe o recado no lugar do
    pedido: o dossiê é papel que sai da casa."""
    import usucapiao as US
    con, pid = _processo_do_dossie(casa)
    with con:
        MOD.salvar(con, "US_DOSSIE_PEDIDO", corpo="Analise o processo {inventado}.",
                   quem="mario", agora=OURO_G.AGORA)
    with pytest.raises(US.UsucapiaoError) as erro:
        US.montar_dossie(con, pid, hoje=OURO_G.HOJE)
    assert "US_DOSSIE_PEDIDO" in str(erro.value)
    assert "inventado" in str(erro.value)
    con.close()
    for args in ("", "?formato=txt"):
        r = casa["cliente"].get(f"/usucapiao/{pid}/dossie{args}")
        assert r.status_code == 302, args
        assert r.headers["Location"].endswith(f"/usucapiao/{pid}"), args
    html = " ".join(casa["cliente"].get(f"/usucapiao/{pid}").get_data(
        as_text=True).split())
    assert "O dossiê não sai" in html and "inventado" in html


def test_o_recado_do_modelo_quebrado_nao_se_lavra_como_decisao(casa):
    """A ficha põe o recado no lugar do modelo que não monta, e o botão do
    modelo o carrega no teor; «Lavrar decisão» o gravava em
    `us_decisoes.teor`, o papel que se assina. Agora o domínio recusa — o
    recado inteiro, ou o miolo dele no meio de um teor —, e a rota volta com o
    porquê. E o teor que o oficial escreve continua lavrando, senão a trava
    passaria no vazio."""
    import usucapiao as US
    con, pid = _processo_do_dossie(casa)
    with con:
        MOD.salvar(con, "US_DECISAO_EXIGENCIA", corpo="NOTA {inventado}",
                   quem="mario", agora=OURO_G.AGORA)
    recado = US.modelos_de_decisao(US.processo(con, pid), OURO_G.SV,
                                   con=con)["EXIGENCIA"]
    assert recado.startswith("[O modelo «US_DECISAO_EXIGENCIA» não monta")
    ficha = casa["cliente"].get(f"/usucapiao/{pid}").get_data(as_text=True)
    assert "US_DECISAO_EXIGENCIA" in ficha, "a ficha não ofereceu o recado"

    def decisoes():
        return banco(con).valor(
            "SELECT count(*) AS n FROM us_decisoes WHERE processo_id = %s",
            (pid,))

    fundamento = "Falta a planta do imóvel de exemplo, assinada por profissional."
    dados = {"csrf_token": _token(ficha), "sentido": "EXIGENCIA",
             "fundamento": fundamento, "teor": recado}
    r = casa["cliente"].post(f"/usucapiao/{pid}/decidir", data=dados,
                             follow_redirects=True)
    html = " ".join(r.get_data(as_text=True).split())
    assert "recado de um modelo que não monta" in html
    assert decisoes() == 0
    with pytest.raises(US.UsucapiaoError) as erro:
        with con:
            US.decidir(con, pid, sentido="EXIGENCIA", fundamento=fundamento,
                       teor="Decido: " + recado[1:-1], agora=OURO_G.AGORA)
    assert "US_DECISAO_EXIGENCIA" in str(erro.value)
    assert decisoes() == 0

    dados["teor"] = "EXIGÊNCIA. Junte-se a planta do imóvel de exemplo."
    casa["cliente"].post(f"/usucapiao/{pid}/decidir", data=dados)
    assert decisoes() == 1
    con.close()


def test_a_peca_da_forma_que_existe_e_nao_monta_continua_sendo_recusa(casa):
    """A forma sem peça cai no texto da norma (`test_us_notificacao`); a que
    TEM peça, com um ajuste que não monta, é recusa com o nome da peça — e não
    a norma posta no lugar sem ninguém saber."""
    import us_notificacao as UN
    con = _con(casa)
    with con:
        MOD.salvar(con, "US_NOTIFICACAO__forma_pessoal",
                   corpo="Pessoalmente, {inventado}", quem="mario",
                   agora=OURO_G.AGORA)
    with pytest.raises(UN.NotificacaoError) as erro:
        UN.montar(processo=P_US, notificacao=N_US, serventia=OURO_G.SERVENTIA,
                  hoje_extenso=OURO_G.HOJE_EXTENSO, con=con)
    assert "US_NOTIFICACAO__forma_pessoal" in str(erro.value)
    assert "inventado" in str(erro.value)
    con.close()


# ============================================ AS FRASES DO RI — LF06B
#
#   O LF06A levou os treze papéis do RI que já eram modelo; sobravam as FRASES
#   que os módulos do RI montavam em f-string (a cláusula das prenotações, o
#   teor do encerramento, a ata do expurgo…). Cada uma virou papel do catálogo,
#   com o texto em `modelos_padrao/ri/` e lida por `ri_frases`. A regra que
#   escolhe a frase ficou no módulo.
#
#   **A PROVA DE QUE NADA MUDOU É O OURO DO LF06B**, gravado na árvore do
#   commit de antes (2c41e90, exportada sem checkout): os montadores do RI,
#   chamados com contexto de teste, saída por saída (`fixtures/modelos_ouro/
#   lf06b_<parte>.py` e `LF06B_<parte>.json`).

_ESPEC_B = importlib.util.spec_from_file_location(
    "ouro_lf06b", RAIZ / "tests" / "fixtures" / "modelos_ouro" / "ouro_lf06b.py")
OURO_B = importlib.util.module_from_spec(_ESPEC_B)
_ESPEC_B.loader.exec_module(OURO_B)


def test_o_ouro_das_frases_do_ri_foi_gravado_na_arvore_de_antes():
    """Toda parte tem o ouro dela, do commit de antes, e o ouro tem as MESMAS
    chamadas que o teste refaz — nem uma a menos."""
    assert OURO_B.partes(), "o LF06B não gravou ouro nenhum"
    for nome in OURO_B.partes():
        ouro_da_parte = OURO_B.ouro(nome)
        assert ouro_da_parte["commit"] == OURO_B.COMMIT_DE_ANTES == "2c41e90"
        assert set(ouro_da_parte["funcoes"]) == set(OURO_B.parte(nome).chamadas()), nome
        assert ouro_da_parte["funcoes"], nome


@pytest.mark.parametrize("nome", OURO_B.partes())
def test_as_frases_do_ri_saem_byte_a_byte_como_saiam_do_codigo(nome):
    """O TESTE-OURO DO LF06B: a regra continua no módulo e escolhe a frase; o
    texto agora vem da base — e o papel montado é o mesmo de antes."""
    # O que mudou de propósito depois do ouro (o papel reprográfico no modelo
    # da casa, LH02; a validade pelo art. 553, LH13) está em `_lh02_no_ouro_b`
    # e `_lh13_no_ouro_b`, saída por saída.
    ouro_da_parte = _lh13_no_ouro_b(
        nome, _lh02_no_ouro_b(nome, OURO_B.ouro(nome)["funcoes"]))
    for chamada, f in OURO_B.parte(nome).chamadas().items():
        saida = OURO_B.normal(OURO_B.tenta(f))
        esperado = ouro_da_parte[chamada]
        if callable(esperado):
            assert esperado(saida), chamada
        else:
            assert saida == esperado, chamada


def test_toda_frase_do_ri_tem_um_txt_e_uma_ficha_sem_elementos_comuns():
    """A frase entra DENTRO de um papel: o fecho e o rodapé da atribuição,
    se ela os herdasse, sairiam no meio da certidão."""
    frases = _frases_do_ri_lf06b()
    assert frases, "nenhuma frase do RI no catálogo"
    for chave in frases:
        c = MOD.POR_CHAVE[chave]
        assert c["pasta"] == "ri" and c["atribuicao"] == "Registro de Imóveis"
        assert c.get("elementos_comuns") is False, chave
        assert c["padrao"] == ("ri_frases", chave)
        assert MOD.formato_de(chave) == MOD.JINJA, chave
        assert (RAIZ / c["arquivo"]).is_file(), chave


def test_o_ajuste_da_casa_numa_frase_do_ri_e_o_que_o_papel_usa(casa):
    """A busca única vale para as frases também: com `con`, o ajuste da casa
    (gravado pela tela, em `mo_elementos`) vence o padrão da base."""
    import modelos_elementos as ELEM
    import ri_frases
    con = _con(casa)
    for chave in sorted(_frases_do_ri_lf06b()):
        assert ri_frases.texto(chave, con) == ri_frases.texto(chave) == MOD.padrao_de(chave)
        with con:
            ELEM.salvar(con, atribuicao=ELEM.atribuicao_do_ato(chave), ato=chave,
                        parte=ELEM.CORPO, corpo="FRASE DA CASA {{ 1 + 1 }}",
                        quem="mario", agora="2026-10-19T09:00")
        assert ri_frases.frase(chave, con) == "FRASE DA CASA 2", chave
        # sem `con` (montador puro) sai o padrão — é o piso
        assert ri_frases.texto(chave) == MOD.padrao_de(chave)


def test_a_frase_do_ri_aparece_na_tela_de_modelos_e_se_edita(casa):
    """O pedido do oficial: editar com facilidade. A frase aparece no grupo do
    Registro de Imóveis, abre no editor e o que se grava passa a valer."""
    chave = sorted(_frases_do_ri_lf06b())[0]
    html = _tela(casa, editar=chave)
    assert "textarea" in html and MOD.POR_CHAVE[chave]["arquivo"] in html
    _gravar(casa, chave, "FRASE AJUSTADA PELA CASA")
    assert MOD.texto_do_papel(_con(casa), chave) == "FRASE AJUSTADA PELA CASA"
    _gravar(casa, chave, "x", acao="restaurar")
    assert MOD.texto_do_papel(_con(casa), chave) == MOD.padrao_de(chave)


def _textos_do_codigo_do_ri() -> list[str]:
    """Os textos literais dos módulos do RI, sem docstring nem comentário — é
    ali que uma cópia esquecida da frase continuaria valendo.

    SÓ OS DO RI (`ri_*`, `ra_*`, `atrib_certidao`, e as funções do Livro 3 de
    `atribuicoes_web`): a mesma fórmula — «O referido é verdade e dou fé.»,
    «CERTIDÃO CANCELADA —» — é também do Registro Civil, das Notas, do
    Protesto e do RCPJ/RTD, e lá ela é do lote de cada um (LF06C a LF06F), e
    não cópia desta."""
    import ast
    textos = []
    arquivos = sorted({*RAIZ.glob("ri_*.py"), *RAIZ.glob("ra_*.py"),
                       RAIZ / "atrib_certidao.py", RAIZ / "atribuicoes_web.py"})
    for p in arquivos:
        try:
            arvore = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        docstrings = {id(n.value) for n in ast.walk(arvore)
                      if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        raizes = [arvore]
        if p.name == "atribuicoes_web.py":      # a casa inteira mora ali
            raizes = [n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef)
                      and "livro3" in n.name.lower()]
            assert raizes, "as funções do Livro 3 sumiram de atribuicoes_web"
        for n in (no for r in raizes for no in ast.walk(r)):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                    and id(n) not in docstrings:
                textos.append(n.value)
    return textos


def test_o_texto_das_frases_do_ri_saiu_mesmo_do_codigo():
    """Uma cópia da frase esquecida num literal do módulo seria o «duas fontes
    para a mesma coisa»: a casa editaria a da base e o papel imprimiria a do
    código. O trecho mais longo de cada padrão (sem os claros) não pode estar
    em nenhum literal do código."""
    textos = _textos_do_codigo_do_ri()
    for chave in sorted(_frases_do_ri_lf06b()):
        trechos = re.split(r"{{.*?}}|{%.*?%}", MOD.padrao_de(chave), flags=re.S)
        trecho = max(trechos, key=len).strip()
        if len(trecho) < 40:
            continue                       # frase curta demais para ser prova
        assert not any(trecho in t for t in textos), (chave, trecho)


# ============================== A REPROGRÁFICA NO MODELO DA CASA — LH02
#
#   «As certidões reprográficas estão saindo num modelo muito inadequado.
#    (...) gostaria que você integrasse ao modelo de certidão (...) e que todas
#    saiam neste modelo.» — a substituta, 20/10/2026 (HOTFIX-2026-10-20-02, na
#   produção desde a 3.6.293.4). O papel de `ri_digitalizacao.odt_da_
#   digitalizacao` mudou inteiro: o cabeçalho do cadastro, o título, o
#   CERTIFICO com a identificação, a ressalva, as folhas, o fecho, o lugar e a
#   data, quem assina, «Selo digital» e o QR derivado do número.
#
#   O TEXTO DO MODELO FOI PARA A BASE, como o das outras frases do RI: a
#   `RI_REPROGRAFICA_CAPA` (a frase da capa antiga) virou o CERTIFICO e a
#   ressalva, e o fecho do papel é a frase nova `RI_REPROGRAFICA_FECHO_DO_PAPEL`
#   — por isso o catálogo tem uma linha a mais.
#
#   O OURO DO LF06B NÃO SE REGRAVA: as três saídas do papel (`[content.xml]`)
#   são refeitas abaixo a partir das GRAVADAS, peça por peça, e conferidas
#   byte a byte; as outras do grupo B (o corpo congelado, o fecho do livro, o
#   título) continuam as de antes. Que o papel é o da produção — com o mesmo
#   cadastro, os mesmos bytes do `depois/` da 3.6.293.4 — foi medido fora da
#   suíte e está no relatório do LH02 (a árvore da produção não vem ao Git).

NOVOS_NO_CATALOGO_LH02 = 1      # RI_REPROGRAFICA_FECHO_DO_PAPEL

# O texto do modelo da substituta, palavra por palavra (o padrão da base).
_LH02_CERTIFICO = (
    "CERTIFICO, a requerimento da parte interessada e no exercício das "
    "atribuições desta Serventia, que a reprodução reprográfica inserida no "
    "espaço abaixo foi extraída do documento/assento constante do acervo sob "
    "a identificação ")
_LH02_RESSALVA = (
    "A reprodução que integra a presente certidão corresponde à imagem do "
    "documento/assento consultado, ressalvadas as características de "
    "legibilidade e conservação do original.")
_LH02_FECHO = ("Era o que constava no documento/assento reproduzido. Nada mais. "
               "Certifico e dou fé.")
# O QR que a casa não guardava: o papel o deriva do número do selo.
_LH02_QR = ('<draw:frame draw:style-name="Fr-qr" text:anchor-type="as-char" '
            'svg:width="1.3cm" svg:height="1.3cm"><draw:image '
            'xlink:href="Pictures/selo_cert_1.png" xlink:type="simple" '
            'xlink:show="embed" xlink:actuate="onLoad"/></draw:frame>')
# As três chamadas do ouro: (páginas, a identificação que o papel escreve).
# Sem `identificacao`, ela sai do resumo congelado; sem resumo, a frase geral.
_LH02_PAPEIS = {
    "ri_digitalizacao.odt_da_digitalizacao(paginas=1)[content.xml]": (
        1, "indicada na digitalização oficial arquivada nesta Serventia, em "
           "1 (uma) página."),
    "ri_digitalizacao.odt_da_digitalizacao(paginas=2)[content.xml]": (
        2, "indicada na digitalização oficial arquivada nesta Serventia, em "
           "2 (duas) páginas."),
    "ri_digitalizacao.odt_da_digitalizacao(corpo, titulo)[content.xml]": (
        1, "Matrícula nº 1.234, em 1 (uma) página."),
}


def _lh02_papel(antes: str, paginas: int, identificacao: str) -> str:
    """O papel GRAVADO refeito no modelo da casa. Só calcula.

    Do de antes saem a capa, a nota e as folhas de página inteira; ficam o
    carimbo (com o QR, agora) e quem expediu (na linha do fecho). As folhas
    escalam pela mesma régua de antes — que se confere aqui contra as
    medidas gravadas — na área do modelo (o teste do servidor confere a
    área)."""
    import ri_digitalizacao as RDIGI
    assert "Reprodução fiel da matrícula digitalizada" in antes
    assert "P-digi-titulo" in antes and "As folhas seguintes reproduzem" in antes
    carimbo = re.search(r'<table:table table:name="CarimboDoSelo".*</table:table>',
                        antes, flags=re.S).group(0)
    sem_qr = '<text:p text:style-name="P-selo-compacto"></text:p>'
    assert carimbo.count(sem_qr) == 1, "o carimbo de antes já tinha QR"
    carimbo = carimbo.replace(
        sem_qr, f'<text:p text:style-name="P-selo-compacto">{_LH02_QR}</text:p>')
    # A régua de escala é a de antes: 124×175 px (as folhas do gerador) na
    # área de antes dá as medidas gravadas.
    medidas = re.findall(r'draw:name="digi\d\.png"[^>]*svg:width="([0-9.]+)cm" '
                         r'svg:height="([0-9.]+)cm"', antes)
    assert len(medidas) == paginas
    assert {(float(w), float(h)) for w, h in medidas} == {
        RDIGI._escala_ficha_na_folha(124, 175, area_w_cm=18.9, area_h_cm=27.6)}
    area_w = 21.0 - 2 * 2.2
    area_h = 29.7 - 0.51 - 2.06 - 0.15 - 2.0 - 0.6
    linhas = [
        '<text:p text:style-name="P-repro-cab1">REPÚBLICA FEDERATIVA DO BRASIL</text:p>',
        '<text:p text:style-name="P-repro-cab1">ESTADO DO MARANHÃO</text:p>',
        '<text:p text:style-name="P-repro-titulo">CERTIDÃO REPROGRÁFICA</text:p>',
        f'<text:p text:style-name="P-repro-texto">{_LH02_CERTIFICO}<text:span '
        f'text:style-name="T-italico">{identificacao}</text:span></text:p>',
        f'<text:p text:style-name="P-repro-texto">{_LH02_RESSALVA}</text:p>']
    for i in range(paginas):
        alt_max = area_h - 9.0 if i == 0 else area_h
        if i == paginas - 1 and paginas > 1:
            alt_max = area_h - 12.6
        w, h = RDIGI._escala_ficha_na_folha(124, 175, area_w_cm=area_w,
                                            area_h_cm=alt_max)
        estilo = "P-repro-img" if i == 0 else "P-repro-img-quebra"
        linhas.append(
            f'<text:p text:style-name="{estilo}"><draw:frame draw:name="digi{i + 1}'
            f'.png" text:anchor-type="as-char" svg:width="{w}cm" svg:height="{h}cm">'
            f'<draw:image xlink:href="Pictures/digi{i + 1}.png" xlink:type="simple" '
            'xlink:show="embed" xlink:actuate="onLoad"/></draw:frame></text:p>')
    linhas += [f'<text:p text:style-name="P-repro-fecho">{_LH02_FECHO}</text:p>',
               '<text:p text:style-name="P-repro-fecho-centro">____ de '
               '__________________ de ______.</text:p>']
    quem = re.findall(r'<text:p text:style-name="P-centro">([^<]+)</text:p>', antes)
    linhas += [f'<text:p text:style-name="P-repro-fecho-assina">{q}</text:p>'
               for q in quem]
    linhas.append('<text:p text:style-name="P-repro-fecho-centro">Selo digital: '
                  'SELOEXEMPLO123</text:p>')
    return ("<office:body><office:text>\n" + "\n".join(linhas) + "\n" + carimbo
            + "\n </office:text>")


def _lh02_no_ouro_b(nome: str, funcoes: dict) -> dict:
    """O ouro gravado da parte, com as saídas do papel reprográfico refeitas
    no modelo da casa. Cada uma tem de MUDAR — senão a lista explicaria uma
    mudança que não houve."""
    saida = dict(funcoes)
    if nome != "b":
        return saida
    for chamada, (paginas, ident) in _LH02_PAPEIS.items():
        antes = saida[chamada]
        assert set(antes) == {"ok"}, chamada
        saida[chamada] = {"ok": _lh02_papel(antes["ok"], paginas, ident)}
        assert saida[chamada] != antes, chamada
    return saida


def test_o_papel_reprografico_le_as_duas_frases_do_modelo_com_o_ajuste_da_casa(casa, tmp_path):
    """O PEDIDO DO LF06B VALE PARA O MODELO NOVO: o que a casa grava na tela de
    Modelos (o CERTIFICO, o fecho) é o que o papel imprime, com o claro da
    identificação preenchido pela regra. Sem `con`, o padrão da base."""
    import io
    import zipfile

    import modelos_elementos as ELEM
    import ri_digitalizacao as RDIGI
    from PIL import Image
    arq = tmp_path / "ficha.png"
    Image.new("RGB", (124, 175), "white").save(arq)

    def papel(**kw) -> str:
        odt = RDIGI.odt_da_digitalizacao(arq, selo_texto="", nome="t",
                                         identificacao="Matrícula nº 9.003", **kw)
        with zipfile.ZipFile(io.BytesIO(odt)) as z:
            return z.read("content.xml").decode("utf-8")

    con = _con(casa)
    ajustes = {"RI_REPROGRAFICA_CAPA": "<p>CERTIFICO DA CASA: <i>{{ identificacao }}</i></p>",
               "RI_REPROGRAFICA_FECHO_DO_PAPEL": "<p>FECHO DA CASA.</p>"}
    for chave, corpo in ajustes.items():
        with con:
            ELEM.salvar(con, atribuicao=ELEM.atribuicao_do_ato(chave), ato=chave,
                        parte=ELEM.CORPO, corpo=corpo, quem="mario",
                        agora="2026-10-21T09:00")
    xml = papel(con=con)
    assert ('<text:p text:style-name="P-repro-texto">CERTIFICO DA CASA: <text:span '
            'text:style-name="T-italico">Matrícula nº 9.003, em 1 (uma) página.'
            '</text:span></text:p>') in xml
    assert '<text:p text:style-name="P-repro-fecho">FECHO DA CASA.</text:p>' in xml
    assert _LH02_FECHO not in xml and "ressalvadas as características" not in xml
    padrao = papel()
    assert _LH02_FECHO in padrao and _LH02_RESSALVA in padrao
    assert "DA CASA" not in padrao


# ===================================== A VALIDADE PELO ART. 553 — LH13 (item 14)
#
#   «14 a» — o oficial, 21/10/2026: a validade de 30 dias das certidões do RI
#   cita o art. 553 do Código de Normas da CGJ/TJMA (Prov. COGEX 28/2026: «e
#   consignará a validade de 30 (trinta) dias»), e não o art. 53, que no
#   Código vigente trata da sentença na suscitação de dúvida. Mudaram os
#   quatro padrões que a citavam: RI_CERTIDAO (nos dois desenhos, o do inteiro
#   teor e o dos outros), RI_CERTIDAO_NEGATIVA_IMOVEL, RI_REPROGRAFICA_VALIDADE
#   e RI_LIVRO3_CERTIDAO_FECHO.
#
#   OS OUROS NÃO SE REGRAVAM: a troca é a mesma frase, achada UMA vez em cada
#   saída que a tinha, e o resto continua byte a byte — o do LF06A (o texto e
#   a prévia das duas certidões do Livro 2) e o do LF06B (a validade da
#   reprográfica, parte E, e o fecho da certidão do Livro 3, parte F).
_LH13_VALIDADE = ("na forma do art. 53 do Código de Normas",
                  "na forma do art. 553 do Código de Normas")
_LH13_ANTES_DA_VALIDADE = ("{% endif %}<p><b>VALIDADE: </b>30 (trinta) dias contados "
                           "da data de expedição, ",
                           "{% endif %}\n<p><b>VALIDADE: </b>30 (trinta) dias contados "
                           "da data de expedição, ")
MUDOU_DEPOIS_DO_OURO["RI_CERTIDAO"] = {
    # o molde tem a frase duas vezes — cada desenho a sua —, e cada troca tem
    # de se achar uma vez só: vai com o que vem antes dela em cada desenho
    "texto": tuple((antes + _LH13_VALIDADE[0], antes + _LH13_VALIDADE[1])
                   for antes in _LH13_ANTES_DA_VALIDADE),
    "papel": (_LH13_VALIDADE,),
}
MUDOU_DEPOIS_DO_OURO["RI_CERTIDAO_NEGATIVA_IMOVEL"] = {
    "texto": (_LH13_VALIDADE,), "papel": (_LH13_VALIDADE,)}
# As saídas do LF06B que citavam a validade, por parte — e só estas mudam.
_LH13_SAIDAS_DO_OURO_B = {"e": 2, "f": 7}
# E o CANCELAMENTO DO LIVRO 3 (parte C), cujo ouro guarda a escrita inteira —
# o SQL e os parâmetros. «15 a» (LH13): o ato do Livro 3 grava quem o praticou
# (`ra_atos.lavrado_*`), e o INSERT ganhou as três colunas, vazias na chamada do
# ouro (ela não diz quem lavrou). A frase do teor e o resto, iguais.
_LH13_INSERT_DO_CANCELAMENTO = (
    "INSERT INTO ra_atos(registro_id, tipo, numero, data_ato, teor, motivo_cancelamento, "
    "origem, criado_em, criado_por) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "RETURNING id",
    "INSERT INTO ra_atos(registro_id, tipo, numero, data_ato, teor, motivo_cancelamento, "
    "origem, criado_em, criado_por, lavrado_nome, lavrado_titulo, lavrado_tratamento) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id")
_LH13_CANCELAMENTOS_DO_OURO_C = ("ra_registro.cancelar(com_partes)",
                                 "ra_registro.cancelar(sem_partes)")


def _lh13_no_ouro_b(nome: str, funcoes: dict) -> dict:
    """O ouro da parte com o que o LH13 mudou de propósito. Só calcula.

    Cada saída gravada que citava o art. 53 passa a citar o 553 — a frase
    achada uma vez nela —, e a conta das que mudam é a declarada em
    `_LH13_SAIDAS_DO_OURO_B`: outra que mude, ou uma a menos, é vermelho. Na
    parte C, a escrita do ato do cancelamento do Livro 3 leva as três colunas
    de quem o praticou (`_LH13_INSERT_DO_CANCELAMENTO`), achada uma vez."""
    saida = dict(funcoes)
    mudaram = 0
    for chamada, antes in funcoes.items():
        if callable(antes) or _LH13_VALIDADE[0] not in json.dumps(antes, ensure_ascii=False):
            continue
        assert set(antes) == {"ok"} and antes["ok"].count(_LH13_VALIDADE[0]) == 1, chamada
        saida[chamada] = {"ok": antes["ok"].replace(*_LH13_VALIDADE)}
        mudaram += 1
    assert mudaram == _LH13_SAIDAS_DO_OURO_B.get(nome, 0), (nome, mudaram)
    if nome == "c":
        for chamada in _LH13_CANCELAMENTOS_DO_OURO_C:
            antes = json.loads(json.dumps(saida[chamada]))
            do_ato = [e for e in antes["ok"]["escritas"]
                      if e["sql"] == _LH13_INSERT_DO_CANCELAMENTO[0]]
            assert len(do_ato) == 1, chamada
            do_ato[0]["sql"] = _LH13_INSERT_DO_CANCELAMENTO[1]
            do_ato[0]["parametros"] += [None, None, None]
            saida[chamada] = antes
    return saida


def test_a_validade_das_certidoes_do_ri_cita_o_art_553_em_todo_padrao():
    """Nenhum padrão do RI cita mais a validade pelo art. 53 — e os quatro que
    a dizem citam o 553 (LH13, «14 a»)."""
    pasta = RAIZ / "modelos_padrao" / "ri"
    assert not [p.name for p in pasta.glob("*.txt")
                if "art. 53 " in p.read_text(encoding="utf-8")]
    for chave in ("RI_CERTIDAO", "RI_CERTIDAO_NEGATIVA_IMOVEL",
                  "RI_REPROGRAFICA_VALIDADE", "RI_LIVRO3_CERTIDAO_FECHO"):
        assert _LH13_VALIDADE[1] in MOD.padrao_de(chave), chave


# ============================================ OS PAPÉIS DO REGISTRO CIVIL — LF06C
#
#   O texto dos papéis do civil que eram montados no código — o termo, as
#   certidões, a averbação de retificação, as anotações da CRC, as
#   comunicações, o edital e a certidão de habilitação — foi para
#   `modelos_padrao/rcpn/`: o papel inteiro, ou, quando uma REGRA decide se a
#   frase entra (sexo, plural, edital ou pessoal), a frase como PEÇA do papel
#   (`RC_TERMO_OBITO__sepultamento`). A regra ficou no código.
#
#   **A PROVA DE QUE NADA MUDOU É O OURO DO LF06C**, gravado por grupo de
#   módulos ANTES de cada grupo ser tocado, na árvore do commit 2c41e90
#   exportada intocada (`fixtures/modelos_ouro/ouro_lf06c*.py`).

import rc_textos as TEXTOS                                       # noqa: E402


def test_o_ouro_do_lf06c_foi_gravado_antes_e_cobre_os_seis_grupos():
    """Um ouro por grupo, todos do commit de ANTES. Grupo sem ouro seria
    «nada mudou» afirmado sem medida."""
    for grupo in OURO_C.GRUPOS:
        gravado = OURO_C.ouro(grupo)
        assert gravado["commit"] == "2c41e90", grupo
        assert gravado["grupo"] == grupo
        assert gravado["funcoes"], f"{grupo}: ouro sem chamada nenhuma"
        assert set(gravado["funcoes"]) == set(OURO_C.chamadas(grupo)), grupo


# AS SAÍDAS QUE MUDARAM DE PROPÓSITO DEPOIS DO OURO — uma por uma, com o lote
# e o porquê. O ouro é da árvore de antes e não se regrava (regravar faria o
# teste comparar o código com ele mesmo); a troca fica escrita aqui.
#
#   LT01 (20/10/2026): «pessoa não identificada» saiu da declaração do art.
#   255, § 1º, do CN-MA (`rc_modelos_do_livro.frase_dos_ignorados`). Não é item
#   do artigo — é o assento de desconhecido (LRP art. 81; CN-MA art. 257) —, e
#   a pergunta não respondida fazia o termo de uma falecida com nome e CPF
#   declarar que ela não foi identificada. `varre.obito` é o resumo (sha256)
#   das 1.272 montagens do óbito, que contêm a mesma frase.
_LT01_ANTES = "deixou bens, deixou filhos e pessoa não identificada"
_LT01_DEPOIS = "deixou bens e deixou filhos"
MUDARAM_DE_PROPOSITO = {"termos": {
    "ign.none": None, "ob.montado.corpo_da_casa": None,
    "ob.montado.nada_perguntado": None, "ob.valores.nada_perguntado": None,
    "varre.obito": {"ok": {"erros": 0, "n": 1272, "sha256": (
        "f7c1c5d26e37a5f4658525baf0351c7098433ffce48f38b10fe5fde2c2c887fb")}},
}}


def _ouro_com_as_mudancas_explicadas(grupo: str, funcoes: dict) -> dict:
    """O ouro gravado, com a troca de cada saída de `MUDARAM_DE_PROPOSITO`.

    A troca só vale onde o texto de antes ESTAVA — senão a lista explicaria
    uma mudança que não houve, e esconderia a que houve."""
    import json
    saida = dict(funcoes)
    for nome, novo in MUDARAM_DE_PROPOSITO.get(grupo, {}).items():
        if novo is None:
            antes = json.dumps(saida[nome], ensure_ascii=False)
            assert _LT01_ANTES in antes, nome
            novo = json.loads(antes.replace(_LT01_ANTES, _LT01_DEPOIS))
        saida[nome] = novo
    return _hab22_no_ouro(grupo, _ld22_no_ouro(grupo, _lh05_no_ouro(
        grupo, _ld01_no_ouro(grupo, saida))))


# ------------------------------- 22/10/2026 — a «Conferência» saiu da habilitação
#
#   «verificar também pq saiu um número de conferência no final da certidão de
#   habilitação» — o oficial. A linha `Conferência: <hash>` foi tirada da
#   certidão e do edital (`habilitacao_web`). Nas saídas do ouro ela some do
#   HTML; o hash do `.odt` e do corpo mudam por causa disso e só por isso — o
#   HTML sem a linha tem de sair IGUAL, e é o HTML que diz o que o papel traz.
import re as _re_hab  # noqa: E402

_HAB22_LINHA = _re_hab.compile(r'<p></p><p class="small">Conferência: [^<]*</p>')
_HAB22_HASHES = ("content_xml_sha256", "corpo_sha256")


def _hab22_sem_hashes(valor):
    if isinstance(valor, dict):
        return {k: _hab22_sem_hashes(v) for k, v in valor.items() if k not in _HAB22_HASHES}
    if isinstance(valor, list):
        return [_hab22_sem_hashes(v) for v in valor]
    return valor


def _hab22_no_ouro(grupo: str, saida: dict) -> dict:
    import json as _json
    if grupo != "habilitacao":
        return saida
    saida = dict(saida)
    for nome, valor in list(saida.items()):
        if callable(valor):
            continue
        texto = _json.dumps(valor, ensure_ascii=False)
        if "Conferência:" not in texto:
            continue
        limpo = _json.loads(texto)
        _hab22_tirar_linha(limpo)
        esperado = _hab22_sem_hashes(limpo)
        saida[nome] = (lambda depois, esperado=esperado:
                       _hab22_sem_hashes(depois) == esperado)
    return saida


def _hab22_tirar_linha(valor):
    """Tira a linha da Conferência de todo texto dentro do valor, no lugar."""
    if isinstance(valor, dict):
        for k, v in valor.items():
            if isinstance(v, str):
                valor[k] = _HAB22_LINHA.sub("", v)
            else:
                _hab22_tirar_linha(v)
    elif isinstance(valor, list):
        novos = []
        for v in valor:
            if isinstance(v, str):
                limpo = _HAB22_LINHA.sub("", v)
                if limpo or not v:      # o trecho que era SÓ a linha sai inteiro
                    novos.append(limpo)
            else:
                _hab22_tirar_linha(v)
                novos.append(v)
        valor[:] = novos


# ------------------------------------------------ LD01 — de propósito, regra a regra
#
#   «corrija tudo» — o oficial, 21/10/2026, sobre a lista dos defeitos do RCPN
#   que os lotes LT01 a LT06 acharam (`tests/test_requisitos_rcpn.py`,
#   `tests/test_fluxo_rcpn.py`). Cada regra abaixo é uma mudança que o LD01 fez
#   de propósito nos montadores do civil, com o artigo; `_ld01_no_ouro` a
#   aplica às saídas GRAVADAS, e todo o resto tem de sair igual. Regra que não
#   muda a saída a que se diz aplicar é vermelho: a lista explicaria uma
#   mudança que não houve.

#: Os claros novos dos termos, opcionais — vazios, o rótulo deles vai para
#: «não é o caso» (`montar_do_formulario`), na ordem dos campos.
_LD01_CAMPOS_NOVOS = {"NASCIMENTO": ("frase_natimorto", "testemunhas"),
                      "CASAMENTO": ("frase_da_celebracao",)}
#: O termo de óbito concorda com o sexo de quem faleceu (LRP art. 80, 3º; CN-MA
#: art. 255, III) — as peças eram uma só, no masculino. A falecida do ouro é
#: «MARIA DE EXEMPLO», com CPF: a qualificação dela passa a dizer o sexo.
_LD01_FEMININO = (("Não era eleitor.", "Não era eleitora."),
                  ("Era eleitor.", "Era eleitora."),
                  ("Filho de ", "Filha de "), ("Sepultado em ", "Sepultada em "),
                  ("inscrita no CPF n.º 00000000191",
                   "inscrita no CPF n.º 00000000191, do sexo feminino"))
#: A inscrição do art. 21, parágrafo único, da LRP (CN-MA art. 386) na
#: certidão do assento alterado (por averbação ou retificação).
_LD01_INSCRICAO = ('Inscrição (Lei n.º 6.015/1973, art. 21, parágrafo único): '
                   '"a presente certidão envolve elementos de averbação à margem '
                   'do termo".')
#: Os três resumos das varreduras que as regras de cima alcançam. **Não se
#: refazem caso a caso dentro da suíte** (o ouro guarda só o sha256): a prova
#: de que, das 6.224 montagens, nenhuma mudou por outro motivo é o
#: `fixtures/modelos_ouro/ld01_varreduras.py`, rodado contra a árvore de
#: antes do LD01 (commit 71f21f4) — 1.728 natimortos com «nasceu morta», 40
#: casamentos com os proclamas desta casa, 1.272 óbitos no feminino, e zero
#: casos não explicados.
_LD01_VARREDURAS = {
    "varre.nascimento": {"ok": {"erros": 0, "n": 3968, "sha256": (
        "f0e4f4c2bd26c5c613586c92952034c6dbea867f2492fe579b1672ae0550556d")}},
    "varre.casamento": {"ok": {"erros": 0, "n": 984, "sha256": (
        "f3871a211b29045be09fb116c6264bd0fbbd04991af6834e52be0664d5e1bfc6")}},
    # o LT01 já a tinha mudado (`MUDARAM_DE_PROPOSITO`); o LD01 muda de novo
    "varre.obito": {"ok": {"erros": 0, "n": 1272, "sha256": (
        "b104866eb7b96bad18fcb05b6fef0017eb3d0419505a97f7e0b2515026a37dd2")}},
}


def _ld01_textos(valor, f):
    """`f` em cada texto de dentro da saída (dicionário, lista ou texto)."""
    if isinstance(valor, str):
        return f(valor)
    if isinstance(valor, list):
        return [_ld01_textos(v, f) for v in valor]
    if isinstance(valor, dict):
        return {k: _ld01_textos(v, f) for k, v in valor.items()}
    return valor


def _ld01_trocas(valor, trocas, *, todas: bool = True):
    """As trocas em cada texto da saída. `todas`: cada uma tem de se achar."""
    achadas = set()

    def trocar(texto):
        for velho, novo in trocas:
            if velho in texto:
                achadas.add(velho)
                texto = texto.replace(velho, novo)
        return texto
    novo = _ld01_textos(valor, trocar)
    faltam = [v for v, _ in trocas if v not in achadas]
    assert achadas and not (todas and faltam), f"troca declarada não achada: {faltam}"
    return novo


def _ld01_chaves(valor, chaves: dict):
    """Os valores do termo ganham os claros novos (que não existiam)."""
    ok = dict(valor["ok"])
    assert not set(chaves) & set(ok), sorted(set(chaves) & set(ok))
    return {"ok": {**ok, **chaves}}


def _ld01_nao_e_o_caso(valor, especie: str, vazios: tuple):
    """«Não é o caso» ganha os rótulos dos campos novos vazios, na ordem."""
    import rc_modelos_do_livro as L
    ordem = [c["rotulo"] for c in L.campos_do(especie)]
    rotulos = {c["nome"]: c["rotulo"] for c in L.campos_do(especie)}
    ok = dict(valor["ok"])
    novos = [rotulos[c] for c in vazios]
    assert not set(novos) & set(ok["nao_e_o_caso"])
    ok["nao_e_o_caso"] = sorted(ok["nao_e_o_caso"] + novos, key=ordem.index)
    return {"ok": ok}


def _ld01_inscricao(texto: str) -> str:
    """A inscrição do art. 21 logo depois das averbações e das anotações."""
    import re
    if "OBSERVAÇÕES/AVERBAÇÕES A ACRESCER:\n" in texto:        # o teor
        return re.sub(r"(OBSERVAÇÕES/AVERBAÇÕES A ACRESCER:\n.*?)"
                      r"(\n\n(?:O referido|CERTIFICO ainda))",
                      lambda m: f"{m.group(1)}\n{_LD01_INSCRICAO}{m.group(2)}",
                      texto, count=1, flags=re.S)
    if "\nCERTIFICO ainda" in texto:                         # o quadro
        return texto.replace("\nCERTIFICO ainda",
                             f"\n{_LD01_INSCRICAO}\nCERTIFICO ainda", 1)
    return f"{texto}\n{_LD01_INSCRICAO}"


def _ld01_hash_do_teor(valor):
    """A emissão grava o hash do teor (`rc_certidao.hash_certidao`): o teor
    mudou, o hash é o dele. Refeito com os mesmos campos da linha gravada."""
    import rc_certidao as RCE
    import json as _json
    texto = _json.dumps(valor, ensure_ascii=False)
    for linha in valor["ok"]["gravado"]:
        numero, ano, _aid, _esp, nome, *_m = linha
        teor, velho, agora = linha[9], linha[10], linha[11]
        novo = RCE.hash_certidao(numero, ano, nome, teor, agora)
        texto = texto.replace(velho, novo)
    return _json.loads(texto)


def _ld01_sem_municipio_da_rua(xml: str) -> str:
    """No papel do nascimento, a célula MUNICÍPIO DE NASCIMENTO e a da UF
    saem em branco quando o assento não diz o município — antes elas liam o
    «Endereço do local» (LRP art. 54, 1º)."""
    i = xml.index("HOSPITAL DE EXEMPLO")
    fim = xml.index("FEMININO", i)
    trecho = xml[i:fim]
    assert trecho.count(">Cidade Exemplo<") == 1 and trecho.count(">MA<") == 1
    novo = trecho.replace(">Cidade Exemplo<", "> <").replace(">MA<", "> <")
    return xml[:i] + novo + xml[fim:]


def _ld01_e_papel(valor) -> bool:
    """O papel do natimorto saiu: um `.odt` (zip), e não a recusa."""
    return set(valor) == {"ok"} and str(valor["ok"]).startswith("b'PK")


_LD01_OBITO_COM_A_FALECIDA = (
    "ob.montado.cheio_nao", "ob.montado.cheio_sim", "ob.montado.corpo_da_casa",
    "ob.montado.nada_perguntado", "ob.valores.cheio_nao", "ob.valores.cheio_sim",
    "ob.valores.com_documento", "ob.valores.desconhecido_com_documento",
    "ob.valores.so_mae")
_LD01_COM_AVERBACAO = (
    "emitir(NASC, resumo, com atos)", "emitir(OBITO cancelado, resumo)",
    "montar_teor(NASC completo, atos)", "montar_teor(OBITO completo, cancelado)",
    "montar_teor(OUTRO, cancelado)", "montar_teor(PROCLAMAS, cancelado)",
    "montar_teor(XYZ, cancelado)", "montar_teor(chaves no teor do ato)",
    "montar_teor(vazio, cancelado)",
    "sem_linha_de_assinatura_a_mao(montar_teor(NASC))",
    "quadro(NASC ativo)", "quadro(NASC cancelado, atos)", "quadro(OBITO cancelado)")
_LD01_OBITO_NO_BREVE_RELATO = (
    "emitir(OBITO cancelado, resumo)", "montar_teor(OBITO acervo blob)",
    "montar_teor(OBITO acervo intIdade)", "montar_teor(OBITO completo, cancelado)")


def _ld01_regras(grupo: str):
    """(as saídas, a mudança, o porquê) — na ordem em que se aplicam."""
    import fnmatch
    nasc, cas = _LD01_CAMPOS_NOVOS["NASCIMENTO"], _LD01_CAMPOS_NOVOS["CASAMENTO"]
    if grupo == "termos":
        return [
            # O natimorto «nasceu morta» (LRP art. 53, § 1º; art. 54, 5º) e as
            # testemunhas do parto (art. 54, 9º): dois claros no termo.
            ("nasc.valores.*", lambda n, v: _ld01_chaves(v, {
                "frase_natimorto": " morta" if n.endswith(".natimorto") else "",
                "testemunhas": ""})),
            ("nasc.montado.*", lambda n, v: _ld01_nao_e_o_caso(
                v, "NASCIMENTO", nasc[1:] if n.endswith(".natimorto") else nasc)),
            ("nasc.montado.natimorto", lambda n, v: _ld01_trocas(
                v, (("nasceu uma criança", "nasceu morta uma criança"),))),
            ("form.NASCIMENTO.vazio", lambda n, v: _ld01_nao_e_o_caso(
                v, "NASCIMENTO", nasc)),
            ("form.NASCIMENTO.quem_assina", lambda n, v: _ld01_nao_e_o_caso(
                v, "NASCIMENTO", nasc)),
            ("form.NASCIMENTO.claros_preenchidos", lambda n, v: _ld01_trocas(v, (
                ("nasceu uma criança", "nasceu [frase_natimorto] x uma criança"),
                ("[frase_cpf] x Lido", "[frase_cpf] x [testemunhas] x Lido")))),
            # A data da celebração no termo de casamento (LRP art. 70, 4º).
            ("cas.valores.*", lambda n, v: _ld01_chaves(
                v, {"frase_da_celebracao": ""})),
            ("cas.montado.*", lambda n, v: _ld01_nao_e_o_caso(v, "CASAMENTO", cas)),
            ("form.CASAMENTO.vazio", lambda n, v: _ld01_nao_e_o_caso(
                v, "CASAMENTO", cas)),
            ("form.CASAMENTO.quem_assina", lambda n, v: _ld01_nao_e_o_caso(
                v, "CASAMENTO", cas)),
            ("form.CASAMENTO.claros_preenchidos", lambda n, v: _ld01_trocas(v, (
                ("casados sob o regime", "casados [frase_da_celebracao] x sob o regime"),))),
            # O óbito no feminino e o sexo da falecida (art. 80, 3º).
            *((nome, lambda n, v: _ld01_trocas(v, _LD01_FEMININO, todas=False))
              for nome in _LD01_OBITO_COM_A_FALECIDA),
            *((nome, lambda n, v, novo=novo: novo)
              for nome, novo in _LD01_VARREDURAS.items()),
        ]
    if grupo == "certidoes":
        return [
            # A inscrição do art. 21 (LRP, parágrafo único; CN-MA art. 386).
            *((nome, lambda n, v: _ld01_textos(v, lambda t: _ld01_inscricao(t)
                                               if "Averbacao:" in t
                                               or "Retificacao:" in t else t))
              for nome in _LD01_COM_AVERBACAO),
            # Se era eleitor, se deixou bens e os filhos — o que o termo do
            # óbito declara (LRP art. 80, 7º, 10º e 11º), no breve relato.
            *((nome, lambda n, v: _ld01_trocas(v, ((
                "\n\nFILIAÇÃO:",
                "\nERA ELEITOR\nND\nDEIXOU BENS\nND\nDEIXOU FILHOS\nND"
                "\n\nFILIAÇÃO:"),)))
              for nome in _LD01_OBITO_NO_BREVE_RELATO),
            # O teor mudou, o hash da emissão é o do teor novo.
            ("emitir(NASC, resumo, com atos)", lambda n, v: _ld01_hash_do_teor(v)),
            ("emitir(OBITO cancelado, resumo)", lambda n, v: _ld01_hash_do_teor(v)),
            # O município do papel é o do local, e não a rua; e a UF sozinha
            # não vai para a célula do município (LRP art. 54, 1º).
            *((nome, lambda n, v: {"ok": {**v["ok"], "municipio_nascimento": "",
                                          "municipio_nascimento_uf": ""}})
              for nome in ("quadro(NASC ativo)", "quadro(NASC cancelado, atos)",
                           "quadro(NASC cancelado, sem atos)",
                           "quadro(NASC cpf da certidao)")),
            ("odt.arquivo_da_certidao(NASC).content.xml", lambda n, v: {
                "ok": _ld01_inscricao_no_papel(_ld01_sem_municipio_da_rua(v["ok"]))}),
            # A Declaração de Óbito no quadro — o papel do natimorto a imprime.
            *((nome, lambda n, v: _ld01_chaves(v, {"numero_do": ""}))
              for nome in ("quadro._quadro_obito(blob)", "quadro._quadro_obito(pessoas)",
                           "quadro(OBITO cancelado)", "quadro(sem assento, NATIMORTO)")),
            # O vocabulário do molde ganhou os marcadores dos papéis novos.
            *((nome, lambda n, v: _ld01_chaves(v, {
                "@numerodo": " ", "@titulolivroe": "CERTIDÃO",
                "@livroe_especie": " ", "@livroe_titulo": " ",
                "@livroe_indicacoes": " "}))
              for nome in fnmatch.filter(sorted(OURO_C.ouro("certidoes")["funcoes"]),
                                         "odt.valores(*")),
            # E os valores do papel montados do quadro do nascimento: sem o
            # município, a caixa única «local, município» fica só com o local;
            # e a inscrição do art. 21 entra nas averbações.
            ("odt.valores(quadro NASC, 2 selos)", lambda n, v: {"ok": {
                **v["ok"], "@averbacoes": _ld01_inscricao(v["ok"]["@averbacoes"]),
                "@nomelocalnascimento": "HOSPITAL DE EXEMPLO",
                "@municipio_nascimento": " ", "@uf_nascimento": " "}}),
            # O natimorto tem papel: a recusa deu lugar ao `.odt`.
            ("odt.arquivo_da_certidao(NATIMORTO): recusa", lambda n, v: _ld01_e_papel),
            # Os títulos das seis espécies do Livro E (LRP arts. 19, 89 a 94-A).
            ("rc_certidao.MODELOS", lambda n, v: _ld01_chaves(v, {
                "EMANCIPACAO": "CERTIDÃO DE EMANCIPAÇÃO",
                "INTERDICAO": "CERTIDÃO DE INTERDIÇÃO",
                "AUSENCIA": "CERTIDÃO DE AUSÊNCIA", "TUTELA": "CERTIDÃO DE TUTELA",
                "UNIAO_ESTAVEL": "CERTIDÃO DE UNIÃO ESTÁVEL",
                "OPCAO_NACIONALIDADE": "CERTIDÃO DE OPÇÃO DE NACIONALIDADE"})),
        ]
    return []


def _ld01_inscricao_no_papel(xml: str) -> str:
    """A inscrição na célula das anotações/averbações do papel."""
    assert xml.count("Anotacao:\nCERTIFICO ainda") == 1
    return xml.replace("Anotacao:\nCERTIFICO ainda",
                       f"Anotacao:\n{_LD01_INSCRICAO}\nCERTIFICO ainda")


def _ld01_no_ouro(grupo: str, saida: dict) -> dict:
    """As regras do LD01 aplicadas às saídas gravadas. Uma saída nova pode ser
    um predicado (o papel do natimorto: um `.odt`, e não bytes a comparar)."""
    import fnmatch
    saida = dict(saida)
    for padrao, regra in _ld01_regras(grupo):
        nomes = fnmatch.filter(sorted(saida), padrao) if "*" in padrao else [padrao]
        assert nomes, f"regra do LD01 sem saída: {padrao}"
        for nome in nomes:
            antes = saida[nome]
            saida[nome] = regra(nome, antes)
            assert saida[nome] != antes, f"a regra do LD01 não mudou {nome}"
    return saida


# ------------------------------------------------ LH05 — o registro tardio
#
#   O termo de nascimento ganhou o claro `{frase_tardio}` (os hotfixes
#   «registro tardio» do servidor, 21/10/2026: LRP art. 46; CN-MA art. 249). Fora
#   do tardio ele sai vazio e o termo montado é o de antes; nas saídas gravadas
#   muda o claro a mais nos valores, o rótulo «Registro tardio» no «não é o
#   caso» e o resumo da varredura do nascimento, que guarda os valores. A prova
#   da varredura é o `fixtures/modelos_ouro/lh05_varreduras.py`, rodado contra a
#   árvore de antes do LH05 (commit 87b045e): os 3.968 casos ganham só
#   `frase_tardio: ""`, e o casamento e o óbito não mudam.
_LH05_VARREDURAS = {
    "varre.nascimento": {"ok": {"erros": 0, "n": 3968, "sha256": (
        "d20c0d100378de9fc17eab3ef96f00041b2695ca7d9e9f01eea4da02939a5326")}},
}


def _lh05_regras(grupo: str):
    """(as saídas, a mudança) do LH05 — aplicadas depois das do LD01."""
    if grupo != "termos":
        return []
    vazio = ("frase_tardio",)
    return [
        ("nasc.valores.*", lambda n, v: _ld01_chaves(v, {"frase_tardio": ""})),
        ("nasc.montado.*", lambda n, v: _ld01_nao_e_o_caso(v, "NASCIMENTO", vazio)),
        ("form.NASCIMENTO.vazio", lambda n, v: _ld01_nao_e_o_caso(
            v, "NASCIMENTO", vazio)),
        ("form.NASCIMENTO.quem_assina", lambda n, v: _ld01_nao_e_o_caso(
            v, "NASCIMENTO", vazio)),
        ("form.NASCIMENTO.claros_preenchidos", lambda n, v: _ld01_trocas(v, (
            ("[frase_cpf] x [testemunhas] x Lido",
             "[frase_cpf] x [frase_tardio] x [testemunhas] x Lido"),))),
        *((nome, lambda n, v, novo=novo: novo)
          for nome, novo in _LH05_VARREDURAS.items()),
    ]


# ---------------------------------------- 22/10/2026 — a inscrição do art. 21
#
#   «a expressao elementos a margem do termo so aparecem quando houver
#   averbacao que nao aparece na certidao» — o oficial, sobre a certidão
#   159/2026. Nos casos do ouro as averbações e retificações têm texto e são
#   transcritas: a inscrição que o LD01 pôs SAI. E o rótulo do ato ganha o
#   acento («Averbação:», e não «Averbacao:»). O hash da emissão é o do teor.
_LD22_ROTULOS = (("Averbacao:", "Averbação:"), ("Anotacao:", "Anotação:"),
                 ("Retificacao:", "Retificação:"))
_LD22_EMISSOES = ("emitir(NASC, resumo, com atos)", "emitir(OBITO cancelado, resumo)")


def _ld22_no_ouro(grupo: str, saida: dict) -> dict:
    """A regra de 22/10/2026 nas saídas do grupo das certidões. Saída que a
    regra não muda fica como estava; e o ouro não tem alteração sem texto
    (se tivesse, a inscrição dela teria de ficar)."""
    import json as _json
    import re as _re
    if grupo != "certidoes":
        return saida
    saida = dict(saida)
    for nome, valor in list(saida.items()):
        if callable(valor):
            continue
        texto = _json.dumps(valor, ensure_ascii=False)
        # Alteração SEM TEXTO PRÓPRIO (o rótulo seguido só de «Lavrado por»,
        # «Selo:» ou nada): a certidão não a transcreve, e a inscrição FICA.
        fora = _re.search(r"(Averbacao|Retificacao):\s*(\\n|Lavrado por|Selo:)", texto)
        novo = texto if fora else texto.replace(
            _json.dumps("\n" + _LD01_INSCRICAO, ensure_ascii=False)[1:-1], "")
        for antes, depois in _LD22_ROTULOS:
            novo = novo.replace(antes, depois)
        if novo != texto:
            saida[nome] = _json.loads(novo)
    for nome in _LD22_EMISSOES:
        saida[nome] = _ld22_hash_do_teor(saida[nome])
    return saida


def _ld22_hash_do_teor(valor):
    """O hash gravado na emissão refeito do teor desta regra (a linha gravada
    traz o teor já trocado, e o hash ainda o do LD01)."""
    import rc_certidao as RCE
    import json as _json
    texto = _json.dumps(valor, ensure_ascii=False)
    for linha in valor["ok"]["gravado"]:
        numero, ano, _aid, _esp, nome, *_m = linha
        teor, velho, agora = linha[9], linha[10], linha[11]
        texto = texto.replace(velho, RCE.hash_certidao(numero, ano, nome, teor, agora))
    return _json.loads(texto)


def _lh05_no_ouro(grupo: str, saida: dict) -> dict:
    """As regras do LH05 nas saídas, já com as do LD01. Regra que não muda a
    saída a que se diz aplicar é vermelho, como no LD01."""
    import fnmatch
    saida = dict(saida)
    for padrao, regra in _lh05_regras(grupo):
        nomes = fnmatch.filter(sorted(saida), padrao) if "*" in padrao else [padrao]
        assert nomes, f"regra do LH05 sem saída: {padrao}"
        for nome in nomes:
            antes = saida[nome]
            saida[nome] = regra(nome, antes)
            assert saida[nome] != antes, f"a regra do LH05 não mudou {nome}"
    return saida


@pytest.mark.parametrize("grupo", OURO_C.GRUPOS)
def test_os_papeis_do_civil_saem_iguais_aos_de_antes(grupo):
    """O TESTE-OURO DO LF06C. As mesmas chamadas do gerador, refeitas depois
    da mudança, saída por saída — o texto agora vem da base dos padrões, e a
    regra que escolhe a frase continua no módulo. As mudanças de depois do
    ouro estão em `MUDARAM_DE_PROPOSITO`, cada uma explicada."""
    gravado = OURO_C.ouro(grupo)
    esperado = _ouro_com_as_mudancas_explicadas(grupo, gravado["funcoes"])
    depois = OURO_C.saidas(grupo)
    mudaram = sorted(n for n in depois
                     if not (esperado[n](depois[n]) if callable(esperado[n])
                             else depois[n] == esperado[n]))
    assert not mudaram, f"{len(mudaram)} saída(s) mudaram: {mudaram[:10]}"
    # e as constantes de texto que viraram peça respondem o texto de antes
    assert OURO_C.normal(OURO_C.textos(grupo)) == gravado["textos"]


def test_a_base_tem_os_papeis_e_as_pecas_do_civil_com_os_bytes_da_pasta(casa):
    """Cada `.txt` de `modelos_padrao/rcpn/` — papel ou peça — está na base,
    byte a byte. É de lá que a emissão lê."""
    MOD.carregar_base()
    linhas = banco(_con(casa)).ler(
        f'SELECT chave, corpo FROM "{MOD.schema_da_base()}".padroes ORDER BY chave')
    na_base = {r["chave"]: r["corpo"] for r in linhas}
    arquivos = sorted((RAIZ / "modelos_padrao" / "rcpn").glob("*.txt"))
    assert len(arquivos) > len(OURO_C.PAPEIS_NOVOS)
    for arq in arquivos:
        chave = PASTA.chave_normal(arq.stem)
        assert na_base[chave].encode("utf-8") == arq.read_bytes(), chave


def test_a_peca_e_a_frase_e_a_cola_fica_no_codigo():
    """**O AJUSTE DA CASA É GRAVADO COM `strip()`**: uma peça que começasse
    com o espaço que a cola à frase anterior o perderia no primeiro ajuste, e
    o termo sairia com duas palavras grudadas. A cola — o espaço, a vírgula
    solta, o «e» — é do código; a peça é a frase, e tem redação própria."""
    pecas = sorted((RAIZ / "modelos_padrao" / "rcpn").glob("*__*.txt"))
    assert pecas, "o LF06C não deixou peça nenhuma"
    for arq in pecas:
        texto = arq.read_bytes().decode("utf-8")
        assert texto == texto.strip(), f"{arq.name} começa ou termina em branco"
        palavras = [p for p in re.split(r"\W+", _texto_que_nao_e_marcador(texto))
                    if p.isalpha() and len(p) > 1]
        assert palavras, f"{arq.name} é só cola, sem redação"
        for campo in TEXTOS.claros_de(texto):
            assert campo.isidentifier(), f"{arq.name}: claro «{campo}»"


def test_os_papeis_novos_do_civil_tem_conferidor_e_nao_herdam_o_rodape_dos_termos(casa):
    """O encerramento e o rodapé comuns do civil são os dos TERMOS: herdados por
    um edital ou uma certidão, sairiam no papel errado. E todo papel novo tem
    o conferidor de claros, que aprova o próprio padrão."""
    assert set(TEXTOS.CLAROS_FECHADOS) == set(OURO_C.PAPEIS_NOVOS)
    conferidores = casa["app"].extensions["conferidores_de_modelo"]
    for chave in OURO_C.PAPEIS_NOVOS:
        assert MOD.POR_CHAVE[chave].get("elementos_comuns") is False, chave
        assert MOD.formato_de(chave) == MOD.CHAVES, chave
        assert conferidores[chave](MOD.padrao_de(chave)) == "", chave


def test_a_tela_recusa_claro_que_o_papel_do_civil_nao_tem(casa):
    """`{nome_do_cacique}` passaria na conferência da forma e estouraria
    `KeyError` na hora de mandar o ofício. A recusa é na tela, que é onde há
    tempo de consertar."""
    corpo = MOD.padrao_de("RC_OFICIO_FUNAI") + "Cacique: {nome_do_cacique}\n"
    html = " ".join(_gravar(casa, "RC_OFICIO_FUNAI", corpo).get_data(
        as_text=True).split())
    assert "claros que este papel não tem" in html
    assert "nome_do_cacique" in html
    assert banco(_con(casa)).um(
        "SELECT 1 AS um FROM mo_elementos WHERE ato = %s AND parte = 'CORPO'",
        ("RC_OFICIO_FUNAI",)) is None, "a tela gravou o claro inventado"


def test_o_ajuste_da_casa_num_papel_do_civil_vale_na_busca_unica(casa):
    """O papel é editável na tela de Modelos, e o que se grava é o que a
    emissão lê — ajuste da casa, depois o padrão da base."""
    ajuste = ("Edital desta casa: pretendem casar-se {nubente1_nome} e "
              "{nubente2_nome}; quem souber de impedimento o diga na forma da lei.")
    _gravar(casa, "RC_EDITAL_PROCLAMAS", ajuste)
    assert MOD.texto_do_papel(_con(casa), "RC_EDITAL_PROCLAMAS") == ajuste
    assert TEXTOS.texto("RC_EDITAL_PROCLAMAS", _con(casa)) == ajuste
    assert TEXTOS.texto("RC_EDITAL_PROCLAMAS") == MOD.padrao_de("RC_EDITAL_PROCLAMAS")


def test_na_lavratura_o_termo_le_a_qualificacao_ajustada_pela_casa(casa):
    """**A QUALIFICAÇÃO É LIDA DEZ CHAMADAS ABAIXO DE QUEM TEM A CONEXÃO.** O
    `rc_termo` abre `lendo_da_casa(con)` em volta da montagem, e aí o ajuste
    da ordem vale; fora dele — a prévia sem conexão — vale o padrão."""
    import rc_modelos_do_livro as LIVRO
    _gravar(casa, "RC_QUALIFICACAO", "{nome}, {cpf}")
    maria = {"nome": "MARIA DE EXEMPLO", "sexo": "F",
             "nacionalidade": "brasileira", "cpf": "000.000.001-91"}
    assert LIVRO.qualificacao_inteira(maria) == (
        "MARIA DE EXEMPLO, brasileira, inscrita no CPF n.º 000.000.001-91")
    with TEXTOS.lendo_da_casa(_con(casa)):
        assert LIVRO.qualificacao_inteira(maria) == (
            "MARIA DE EXEMPLO, inscrita no CPF n.º 000.000.001-91")
    assert LIVRO.qualificacao_inteira(maria) == (
        "MARIA DE EXEMPLO, brasileira, inscrita no CPF n.º 000.000.001-91")
