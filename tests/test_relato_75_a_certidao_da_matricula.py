"""A CERTIDÃO DA MATRÍCULA — problema #75, 18/09/2026.

O PEDIDO DO OFICIAL, com as palavras dele:

    «não faz sentido ter opção de emitir certidão negativa de matrícula dentro
     da tela da matrícula → tirar a opção de certidão negativa de matrícula e
     estrutura um modelo base, considerando os modelos de outras certidões do
     cartório, para os demais modelos de certidão»

DUAS COISAS, E A SEGUNDA É A QUE MUDA O DESENHO.

1. A «CERTIDÃO NEGATIVA DE MATRÍCULA» SAI, e ele tem razão pelo que o próprio
   texto dela dizia: «NADA CONSTA **em nome do requerente** nos livros de
   Registro de Imóveis desta Serventia». Isso não certifica ESTA matrícula — é
   busca pelo NOME da pessoa nos livros todos, que é outra pergunta e de outra
   tela (e esta casa não a emite por aqui). As três que ficam respondem todas à
   mesma pergunta: o que está nesta matrícula — o inteiro teor dela, os ônus
   que a atingem, e quem é o dono.

2. O MODELO BASE. Eram quatro tipos dentro de UM texto, separados por
   `{% if tipo_certidao == ... %}`. Quem abria a tela de editar via o papel dos
   quatro misturado, e mexer no que é comum — a abertura, a finalidade, a
   validade do art. 53, quem assina — exigia mexer também no que é de cada um.
   Agora são **um molde e um miolo por tipo**, e a emenda entre os dois é UMA
   só: `{{ miolo_do_tipo }}`.

A MEDIÇÃO QUE TORNOU O CONSERTO SEGURO

    Antes de mexer, conferiu-se que os três tipos que ficam saem, no papel,
    CARACTERE A CARECE como saíam — o molde velho e o novo foram
    contrastados pela conversão `.odf`, que é o que a impressora recebe.
    Nenhuma certidão desta casa mudou de forma: mudou de ENDEREÇO.

A EMENDA É A ÚNICA COISA QUE NÃO PODE SE PERDER

    Molde salvo sem o marcador sai com a abertura, a validade e a assinatura, e
    **sem o teor** — a certidão afirmando «cujo inteiro teor segue:» e não
    reproduzindo nada. É o relato #79 (do dia anterior) pelo outro lado, e por
    isso a recusa vale nos DOIS lados: na tela que grava (onde há tempo de
    consertar) e na emissão (onde quem lê o erro está com o cliente na frente).
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS
import modelos_da_casa as MODELOS
import ri_odt
import ri_schema as RS

# O texto que a ficha tem, no formato em que a casa guarda — e com um `{{ }}`
# DENTRO de propósito, para provar que o teor não é lido como modelo.
TEOR_COM_CHAVE = (
    "<p>FICHA DE ABERTURA - IMÓVEL RURAL. DENOMINAÇÃO: FAZENDA BOA LEMBRANÇA."
    "</p><p>Área de {{ 7 * 7 }} hectares e o percentual de {% if 1 %}50{% endif %}."
    "</p>")


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _abrir(casa, *, numero="4016", teor=TEOR_COM_CHAVE) -> int:
    """Abre a ficha — devolve o id da matrícula. Só o que a certidão lê."""
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf,
                   teor, teor_formato)
               VALUES (?, '2', '2', 'ATIVA', 'ESTRUTURADA', 'MANUAL',
                       '2026-09-18T09:00', '2026-09-14', 'Cidade Exemplo', 'MA',
                       ?, 'html')""", (numero, teor))
        mid = int(cur.lastrowid)
    con.close()
    return mid


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _emitir(casa, mid, tipo="INTEIRO_TEOR") -> str:
    """Emite pela tela e devolve o CORPO CONGELADO em `ri_certidoes`.

    É o corpo gravado, e não o que a tela mostra: é ele o papel que sai.
    """
    tela = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    casa["c"].post(f"/registro-imoveis/{mid}/certidao", data={
        "csrf_token": _token(tela), "tipo": tipo,
        "fonte_corpo": "TEXTO", "requerente": "FULANO DE TAL"},
        follow_redirects=True)
    con = _con(casa)
    linha = con.execute(
        "SELECT * FROM ri_certidoes ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert linha, f"a certidão {tipo} não foi emitida"
    return str(linha["corpo"])


def _semear_corpo(casa, chave: str, corpo: str, parte: str = "CORPO") -> None:
    """Grava um corpo direto no armazém dos modelos, como a tela faria.

    Usado para provar a recusa do lado da EMISSÃO: semear por fora é o que
    simula um ajuste que já estava gravado antes da guarda existir.
    """
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO mo_elementos (atribuicao, ato, parte, corpo,
                   atualizado_em)
               VALUES ('RI', ?, ?, ?, '2026-09-18T09:00')""",
            (chave, parte, corpo))
    con.close()


# ----------------------------------------------- 1. a negativa saiu da tela


def test_a_tela_da_matricula_nao_oferece_a_certidao_negativa(cg_casa_logada):
    """O pedido, na primeira metade. `NEGATIVA` não é opção nenhuma, e não
    basta sair da lista do Python: quem escolhe é o `<option>` do molde."""
    casa = cg_casa_logada
    mid = _abrir(casa)
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    assert 'value="NEGATIVA"' not in html, (
        "a «certidão negativa de matrícula» continua sendo oferecida — é o #75")
    for tipo in RS.TIPOS_CERTIDAO:
        assert f'value="{tipo}"' in html, f"{tipo} sumiu da tela da matrícula"


def test_as_opcoes_do_tipo_saem_da_lista_da_casa(cg_casa_logada):
    """A lista escrita à mão no molde envelhece na tarde em que é escrita.

    Quem tira um tipo do sistema é `ri_schema.TIPOS_CERTIDAO`, e o molde tem de
    obedecer — foi assim que a negativa saiu: tirando-a de UM lugar, e não de
    dois. Aqui se conta o que a tela oferece contra o que a casa declara.
    """
    casa = cg_casa_logada
    mid = _abrir(casa)
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    # O SELETOR DA CERTIDÃO, e não o primeiro `name="tipo"` da página: a ficha
    # tem outros — o da minuta, por exemplo —, e ler o do papel errado aqui
    # faria o teste acusar a tela certa (a régua que erra o endereço acusa quem
    # está certo).
    formulario = re.search(r'action="[^"]*/certidao".*?</form>', html, re.DOTALL)
    assert formulario, "a ficha não tem mais o formulário de emitir certidão"
    dentro = re.search(r'<select name="tipo".*?</select>',
                       formulario.group(0), re.DOTALL)
    assert dentro, "o formulário da certidão não tem o seletor do tipo"
    oferecidos = re.findall(r'<option value="([^"]+)"', dentro.group(0))
    assert sorted(oferecidos) == sorted(RS.TIPOS_CERTIDAO), (
        "a tela e a lista da casa divergiram: "
        f"tela={sorted(oferecidos)} lista={sorted(RS.TIPOS_CERTIDAO)}")


def test_o_mapa_do_miolo_tem_exatamente_os_tipos_da_tela():
    """Tipo sem miolo no mapa sai com a abertura e sem o teor; tipo no mapa que
    a tela não oferece é caminho aberto para o próximo código pedir o texto de
    uma certidão que a casa não emite. Os dois conjuntos são iguais."""
    assert set(ri_odt.MIOLO_DA_CERTIDAO) == set(RS.TIPOS_CERTIDAO)


def test_o_mapa_do_selo_tambem_so_tem_os_tipos_da_tela():
    """O selo segue o tipo — problema #75. Mapa de selo que aceita um tipo que a
    tela não emite faria o selador responder por uma busca que não foi feita."""
    assert set(AS.CODIGO_DA_CERTIDAO_DO_RI) == set(RS.TIPOS_CERTIDAO)
    assert "NEGATIVA" not in AS.CODIGO_DA_CERTIDAO_DO_RI


# ------------------------------------------ 2. o molde, o miolo, e a emenda


def test_o_molde_carrega_a_emenda_e_nao_escolhe_mais_o_texto_do_tipo():
    """O molde diz ONDE o miolo entra, e não escolhe mais o TEXTO por `{% if %}`.

    Fica vermelho se alguém devolver o texto de um tipo para dentro do molde: aí
    os textos voltam a morar juntos, e o conserto do #75 se perde.

    **A comparação com `INTEIRO_TEOR` FICA, e ela não é sobra:** o molde tem
    dois DESENHOS — o do inteiro teor, que já traz o cabeçalho da ficha, e o dos
    outros, que abre com o timbre —, e o tipo escolhido decide qual sai. Isso é
    paginação, e não o texto do tipo; o texto, esse, saiu inteiro para os miolos.
    """
    assert ri_odt.MARCADOR_DO_MIOLO in ri_odt.MODELO_CERTIDAO_PADRAO, (
        "o molde da certidão perdeu o ponto onde o texto do tipo entra")
    for tipo in ("ONUS", "PROPRIEDADE", "NEGATIVA"):
        assert f'tipo_certidao == "{tipo}"' not in ri_odt.MODELO_CERTIDAO_PADRAO, (
            f"o molde voltou a escolher o texto por `{tipo}` dentro dele")
    # A negativa não tem miolo — e o molde não guarda o texto dela em lugar
    # nenhum: quem a reler não deve achá-la viva por descuido.
    assert "em nome do requerente nos livros" not in ri_odt.MODELO_CERTIDAO_PADRAO


def test_cada_miolo_do_catalogo_e_o_texto_do_seu_tipo():
    """O miolo se lê COMO A EMISSÃO O LÊ — pelo catálogo, que é quem diz onde o
    texto mora. `getattr(ri_odt, <chave>)` procuraria pelo nome errado: a chave
    é `RI_CERTIDAO_ONUS` e a constante é `MIOLO_CERTIDAO_ONUS`."""
    esperado = {
        "INTEIRO_TEOR": "{% if teor_odf %}{{ teor_odf }}{% endif %}",
        "ONUS": "NADA CONSTA",
        "PROPRIEDADE": "propriedade do imóvel acima descrito",
        # A dominial e a vintenária — 28/09/2026, reconstituídas em 14/10/2026
        # (ver `tests/test_ri_certidao_dominial_vintenaria.py`).
        "DOMINIAL": "CADEIA DOMINIAL",
        "VINTENARIA": "TRANSMISSÕES DE DOMÍNIO NO PERÍODO",
    }
    assert set(esperado) == set(RS.TIPOS_CERTIDAO), (
        "entrou tipo novo na tela sem miolo declarado neste teste")
    for tipo, frase in esperado.items():
        chave = ri_odt.MIOLO_DA_CERTIDAO[tipo]
        texto = MODELOS.padrao_de(chave)
        assert texto.strip(), f"o miolo de {tipo} saiu vazio"
        assert frase in texto, f"o miolo de {tipo} não é o texto dele"


def test_quem_nao_e_molde_nao_tem_marcador():
    """Só o molde tem emenda. Se `marcador_do_miolo` devolvesse o marcador para
    todo papel, a guarda passaria a exigir `{{ miolo_do_tipo }}` de um termo do
    civil — a mesma palavra em dois lugares, pela enésima vez."""
    assert MODELOS.marcador_do_miolo("RI_CERTIDAO") == ri_odt.MARCADOR_DO_MIOLO
    assert MODELOS.marcador_do_miolo("RI_CERTIDAO_ONUS") == ""
    assert MODELOS.marcador_do_miolo("RI_FICHA") == ""


def test_conferir_marcadores_aceita_o_padrao_e_recusa_o_molde_sem_emenda():
    assert MODELOS.conferir_marcadores(
        "RI_CERTIDAO", ri_odt.MODELO_CERTIDAO_PADRAO) == ""
    assert "miolo_do_tipo" in MODELOS.conferir_marcadores(
        "RI_CERTIDAO", "<p>Certifico que… cujo inteiro teor segue:</p>")


# ------------------------------------------------- 3. a certidão de cada tipo


def test_a_certidao_de_cada_tipo_sai_com_a_abertura_E_o_texto_do_tipo(
        cg_casa_logada):
    """O papel inteiro: o que toda certidão tem MAIS o que é daquele tipo.

    Antes os dois pedaços moravam no mesmo texto, e por isso este teste olha os
    dois na MESMA emissão — só o miolo, ou só a abertura, não distingue o certo
    das duas formas de errar.
    """
    casa = cg_casa_logada
    mid = _abrir(casa, teor=TEOR_COM_CHAVE)
    do_tipo = {
        "INTEIRO_TEOR": "Fazenda".upper(),
        "ONUS": "NADA CONSTA",
        "PROPRIEDADE": "propriedade do imóvel acima descrito",
    }
    for tipo, frase in do_tipo.items():
        corpo = _emitir(casa, mid, tipo)
        assert frase in corpo, f"a certidão {tipo} saiu sem o texto do tipo"
        assert "neles encontrei a" in corpo, (
            f"a certidão {tipo} saiu sem a abertura do molde")
        assert "art. 53 do Código de Normas" in corpo, (
            f"a certidão {tipo} saiu sem a validade — o que é comum se perdeu")
        assert "MATRÍCULA Nº 4016" in corpo, (
            f"a certidão {tipo} não diz de que matrícula é")


def test_o_teor_da_ficha_nao_e_interpretado_como_modelo(cg_casa_logada):
    """O miolo é renderizado ANTES de entrar no molde, e o que entra é papel.

    Se o teor fosse colado dentro do molde antes de renderizar, o `{{ }}` que a
    ficha tem — e o teor do acervo tem chave de tudo quanto é jeito — seria
    lido como marcador do Jinja, e o papel sairia com a conta feita no lugar do
    texto do livro.
    """
    casa = cg_casa_logada
    mid = _abrir(casa, teor=TEOR_COM_CHAVE)
    corpo = _emitir(casa, mid, "INTEIRO_TEOR")

    assert "{{ 7 * 7 }}" in corpo, "o teor foi interpretado como modelo"
    assert "{% if 1 %}50{% endif %}" in corpo, "o teor foi interpretado como modelo"
    assert ">49<" not in corpo, "o Jinja fez a conta que estava no teor do livro"


# --------------------------------------- 4. a recusa, nos dois lados da régua


def test_a_tela_recusa_gravar_o_molde_sem_a_emenda(cg_casa_logada):
    """O lado onde há tempo de consertar. Gravar primeiro e avisar depois
    deixaria o molde quebrado valendo até alguém voltar na tela — e quem
    descobre é o escrevente, com o cliente na frente."""
    casa = cg_casa_logada
    sem_emenda = "<p>Certifico que, revendo os livros, neles encontrei a " \
                 "MATRÍCULA Nº {{ m.numero }}, cujo inteiro teor segue:</p>"
    tela = casa["c"].get("/modelos?editar=RI_CERTIDAO").get_data(as_text=True)
    casa["c"].post("/modelos", data={
        "csrf_token": _token(tela), "acao": "salvar",
        "chave": "RI_CERTIDAO", "corpo": sem_emenda})

    con = _con(casa)
    gravado = con.execute(
        """SELECT corpo FROM mo_elementos
            WHERE ato = 'RI_CERTIDAO' AND parte = 'CORPO'""").fetchone()
    con.close()
    assert gravado is None, "a tela gravou um molde que o papel não sabe montar"

    aviso = casa["c"].get("/modelos?editar=RI_CERTIDAO").get_data(as_text=True)
    assert "perdeu o ponto onde o texto do tipo entra" in aviso, (
        "a recusa não disse o que faltava — quem edita não sabe o que repor")


def test_a_emissao_tambem_recusa_o_molde_sem_a_emenda(cg_casa_logada):
    """O lado onde o erro chega com o cliente esperando.

    Aqui o ajuste foi semeado POR FORA, como ficaria um corpo gravado antes de
    a guarda existir: a emissão tem de recusar dizendo o motivo, e NÃO emitir a
    certidão que afirmaria «inteiro teor» sem teor nenhum.
    """
    casa = cg_casa_logada
    mid = _abrir(casa)
    _semear_corpo(casa, "RI_CERTIDAO",
                  "<p>Certifico… cujo inteiro teor segue:</p>")

    tela = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    resposta = casa["c"].post(f"/registro-imoveis/{mid}/certidao", data={
        "csrf_token": _token(tela), "tipo": "INTEIRO_TEOR",
        "fonte_corpo": "TEXTO"}, follow_redirects=True)
    html = resposta.get_data(as_text=True)

    con = _con(casa)
    quantas = con.execute("SELECT COUNT(*) n FROM ri_certidoes").fetchone()["n"]
    con.close()
    assert quantas == 0, "a certidão saiu com o molde quebrado"
    assert "perdeu o ponto onde o texto do tipo entra" in html, (
        "a emissão recusou sem dizer o que faltava")


def test_o_conferidor_do_molde_vale_mesmo_em_instalacao_sem_matricula(
        cg_casa_logada):
    """O RI confere contra uma matrícula DE VERDADE, e isso é melhor que o
    boneco — mas numa instalação nova não há matrícula nenhuma, e o conferidor
    devolve `None` («não tinha com que conferir»), que não é erro.

    A guarda da emenda NÃO pode depender disso: sem matrícula, um molde sem o
    marcador ainda é um molde quebrado — e este teste roda sem ficha nenhuma,
    que é o caso da casa que acabou de instalar.
    """
    casa = cg_casa_logada
    conferir = casa["app"].extensions["conferidores_de_modelo"]

    # Os quatro papéis da certidão entram na lista: o molde e os três miolos.
    # Um miolo com um `for` aberto estoura na emissão, com o cliente na frente.
    for chave in ["RI_CERTIDAO", *ri_odt.MIOLO_DA_CERTIDAO.values()]:
        assert chave in conferir, f"{chave} ficou sem conferidor próprio"

    # `""` («conferi, está bom») e `None` («não tinha com que conferir») são
    # coisas diferentes: os dois não são erro, e tratar `None` como falha
    # faria a instalação nova reprovar todo modelo que ela tem.
    assert conferir["RI_CERTIDAO"](ri_odt.MODELO_CERTIDAO_PADRAO) in ("", None)
    assert "miolo_do_tipo" in conferir["RI_CERTIDAO"]("<p>sem emenda</p>")
    # E o miolo não tem emenda a exigir: o que o confere é o próprio texto.
    assert conferir["RI_CERTIDAO_ONUS"](
        MODELOS.padrao_de("RI_CERTIDAO_ONUS")) in ("", None)


def test_o_texto_da_negativa_nao_sobrou_em_lugar_nenhum():
    """A negativa saiu do sistema, e o rastro dela não fica escondido num
    módulo que alguém possa religar — nem no molde, nem na lista dos tipos.

    **A VARREDURA PROCURA O LITERAL, E NÃO A PALAVRA** — a lição que este
    projeto pagou cinco vezes: «NEGATIVA» é também a certidão NEGATIVA DE
    PROTESTO (que existe e é outra coisa), e a `protesto_certidao.TIPOS` e a
    `rg_titulo.NEGATIVA` são desta casa. O que não pode voltar é a chave do
    tipo da certidão da matrícula e a frase que a definia.
    """
    frases = ('"NEGATIVA"', "'NEGATIVA'", "em nome do requerente")
    # **`ato_selado.py` NÃO ENTRA NA LISTA, E ISSO É MEDIÇÃO, E NÃO ESQUECIMENTO.**
    # Ali a palavra existe de verdade — `("pt_certidoes", "NEGATIVA")` é a
    # certidão negativa do PROTESTO, outra coisa, de outra atribuição. Varrer
    # aquele arquivo por palavra acusaria quem está certo; a chave do RI se
    # guarda pelo mapa dele, e disso cuida
    # `test_o_mapa_do_selo_tambem_so_tem_os_tipos_da_tela`.
    for modulo in ("ri_odt.py", "ri_schema.py",
                   "templates/ri_ficha.html", "templates/ri_certidoes.html"):
        for n, linha in enumerate(
                (RAIZ / modulo).read_text(encoding="utf-8").splitlines(), 1):
            codigo = linha.split("#", 1)[0]      # a prosa de explicação fica
            for frase in frases:
                assert frase not in codigo, (
                    f"{modulo}:{n}: a «certidão negativa de matrícula» voltou "
                    f"como código: {linha.strip()}")
