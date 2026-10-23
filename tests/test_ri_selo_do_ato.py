"""O selo do ato do RI sai do selador — 14/09/2026, ordem do oficial.

    «o modulo do RI está desatualizado, ainda tem campo para colar o qr code
     do selo emitido fora. Tire essas parte, incorpore o selador automatizado
     de dentro do sistema, incorpore o visualizador em tempo real do
     registro/averbação (nos moldes que temos nas escrituras) e resolva
     eventuais problemas encontrados»

O QUE ESTES TESTES GUARDAM

    **Que o envelope é o que ESTA CASA mandou**, e não um que eu desenhei. O
    teste monta o envelope a partir de um selo real do acervo e exige que saia
    igual — é a lição do «teste que aplica a suposição aos dois lados não testa
    a suposição», que neste projeto custou o defeito mais caro (o `dadosSelo`
    embrulhado, que impedia o sistema inteiro de selar).

    **Que o caminho sai do VALOR, e não do tipo do ato.** Há averbação com
    valor e registro sem, e mandar um pelo caminho do outro é selar por
    caminho que não é o do ato.

    **Que o QR colado saiu da tela** — e que as colunas ficaram: apagar coluna
    é apagar o que o acervo trouxer amanhã.

    **Que a prévia do RI não é a das Notas.** Lá o teor é HTML; aqui é texto.
    A barra de negrito escreveria `<b>` literal dentro do ato, e o `<b>`
    sairia impresso na ficha.

    **Que selo recusado não derruba o ato.** Quando a recusa chega, o ato já
    está na cadeia de hash — e ele aparece na lista de quem ficou sem selo.
"""
from __future__ import annotations

import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — aponta producao / acervo especial
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS                                          # noqa: E402

SENHA = "Senha#12345"
ACERVO = Path("C:/ProgramData/CartorioGestao/acervo_eoficio.sqlite3")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return achado.group(1) if achado else ""


@pytest.fixture()
def casa(tmp_path):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA,
                                "ADMIN")
    # LX16: selo pago só sai com protocolo pago — o escrevente atende um
    # protocolo do balcão com os itens do RI que estes testes lavram.
    from protocolo_de_teste import atender_protocolo_pago
    with Database(banco).transaction() as con_cx:
        atender_protocolo_pago(con_cx, usuario="MARIO EXEMPLO DOS SANTOS",
                               codigos=("16.3", "16.39"), atribuicao="RI")
    c = app.test_client()
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    con.execute(
        """INSERT INTO ri_matriculas(numero, livro, folha, tipo_ficha,
                                     situacao, criado_em)
           VALUES ('4016','2-S','1','ESTRUTURADA','ATIVA','2026-09-14T10:00')""")
    con.commit()
    mid = con.execute(
        "SELECT id FROM ri_matriculas WHERE numero='4016'").fetchone()[0]
    return {"app": app, "c": c, "con": con, "mid": mid,
            "banco": banco, "dados": dados, "db": Database(banco)}


def _lavrar(casa, **campos):
    ficha = casa["c"].get(
        f"/registro-imoveis/{casa['mid']}?lavrar=1").get_data(as_text=True)
    dados = {"csrf_token": _token(ficha), "tipo": "R",
             "teor": "Registro de compra e venda.",
             "natureza_titulo": "Compra e venda"}
    dados.update(campos)
    return casa["c"].post(f"/registro-imoveis/{casa['mid']}/atos", data=dados,
                          follow_redirects=True)


# --------------------------------------------- o envelope, contra o acervo


def _envelopes_reais() -> list[dict]:
    """Os 120 selos de verdade que esta casa mandou pelos dois caminhos."""
    if not ACERVO.exists():
        return []
    con = sqlite3.connect(f"file:{ACERVO}?mode=ro", uri=True)
    return [json.loads(m) for (m,) in con.execute(
        "SELECT memJson FROM tbSeloIndividual WHERE strURLAto IN (?,?) "
        "AND memJson IS NOT NULL",
        (AS.CAMINHO_DO_ATO_DO_RI_SEM_VALOR,
         AS.CAMINHO_DO_ATO_DO_RI_COM_VALOR))]


def test_o_envelope_reproduz_os_120_QUE_A_CASA_MANDOU():
    """**A prova é o acervo inteiro, e não a minha ideia do envelope.**

    Remonta cada um dos 120 selos reais e compara. É a lição mais cara deste
    projeto — «teste que aplica a suposição aos dois lados não testa a
    suposição»: 37 testes conferiam o pedido de selo contra a MINHA ideia do
    envelope e passavam todos, com o defeito que impedia a casa inteira de
    selar.

    **E ELE FIXA O QUE AINDA DIFERE, com o número de cada caso**, para
    diferença NOVA ficar vermelha aqui em vez de aparecer no balcão:

      `folha`          a casa mandou `'0'` em 42; daqui sai ausente, que é a
                       forma dos outros 78. Ver o cabeçalho do módulo.
      caixa do texto   `descricaoNatureza` sai em MAIÚSCULAS, como no envelope
                       irmão da prenotação. 115 dos 120 já vinham assim; os
                       outros 5 são a mesma frase noutra caixa.
      valor zero       **um** ato foi por `com-valor` declarando `baseCalculo:
                       0.0` — uma averbação de encerramento de matrícula, que
                       não tem valor econômico. Daqui ele sairia por
                       `sem-valor`, e é o certo: zero não é valor declarado.
      espaço à direita 24 campos vêm preenchidos até a largura da coluna
                       (`'2-Q       '`), porque o E-Ofício usa `char(10)`. É o
                       mesmo artefato que `ri_schema.norm` existe para limpar,
                       e a docstring dela diz por quê: «é por aí que os
                       vínculos se perdem». Daqui sai sem o preenchimento.
    """
    reais = _envelopes_reais()
    if not reais:
        pytest.skip("o acervo do E-Ofício não está nesta máquina")
    assert len(reais) == 120, "o acervo mudou de tamanho — meça de novo"

    iguais = com_folha = so_a_caixa = valor_zero = com_espaco = 0
    diferentes = []
    for real in reais:
        ds = real["dadosSelo"]
        meu = AS.envelope_do_ato_do_ri(
            matricula=real["matricula"],
            numero_do_ato=real["registroAverbacao"],
            escrevente=ds["escrevente"],
            versao_tabela=ds["versaoTabelaDeCustas"],
            descricao_natureza=ds["descricaoNatureza"], livro=ds["livro"],
            codigo_tj=ds["codigoTipoAto"], protocolo=real["protocolo"],
            base_calculo=real.get("baseCalculo"),
            partes=ds["partes"]["parteAto"])
        esperado = json.loads(json.dumps(real))

        if esperado["dadosSelo"].pop("folha", None) is not None:
            com_folha += 1
        if ds["descricaoNatureza"] != ds["descricaoNatureza"].upper():
            so_a_caixa += 1
        # O PREENCHIMENTO DO `char(10)` NÃO É CONTEÚDO — compara-se o que foi
        # escrito, e não até onde a coluna do E-Ofício ia.
        for campo in ("livro", "descricaoNatureza"):
            if esperado["dadosSelo"][campo] != esperado["dadosSelo"][campo].strip():
                com_espaco += 1
        esperado["dadosSelo"]["livro"] = ds["livro"].strip()
        esperado["dadosSelo"]["descricaoNatureza"] = \
            ds["descricaoNatureza"].strip().upper()
        if "baseCalculo" in esperado and float(esperado["baseCalculo"]) == 0:
            esperado.pop("baseCalculo")
            esperado["quantidade"] = 1
            valor_zero += 1

        if meu == esperado:
            iguais += 1
        else:
            diferentes.append((real.get("matricula"), meu, esperado))

    assert not diferentes, (
        f"{len(diferentes)} envelope(s) não se reproduzem — o primeiro é da "
        f"matrícula {diferentes[0][0]}")
    assert iguais == 120
    assert (com_folha, so_a_caixa, valor_zero, com_espaco) == (42, 5, 1, 24), (
        "o que difere mudou de tamanho: meça de novo antes de mexer no teste")


def test_o_caminho_sai_do_valor_e_nao_do_tipo_do_ato():
    """Há averbação COM valor e registro SEM — quem decide é o valor."""
    assert AS.caminho_do_ato_do_ri(None) == AS.CAMINHO_DO_ATO_DO_RI_SEM_VALOR
    assert AS.caminho_do_ato_do_ri(0) == AS.CAMINHO_DO_ATO_DO_RI_SEM_VALOR
    assert AS.caminho_do_ato_do_ri(243000.0) == \
        AS.CAMINHO_DO_ATO_DO_RI_COM_VALOR


def test_as_duas_formas_do_envelope_sao_exclusivas():
    """`quantidade` no sem valor, `baseCalculo` no com valor — nunca os dois.

    Medido em 120/120: mandar os dois faria o envelope não ser nenhum dos
    dois que a casa mandou.
    """
    comum = dict(matricula="4014", numero_do_ato=1, escrevente="FULANA",
                 versao_tabela="0220260101", descricao_natureza="Compra",
                 livro="2-S", codigo_tj="16.3")
    sem = AS.envelope_do_ato_do_ri(**comum)
    com = AS.envelope_do_ato_do_ri(**comum, base_calculo=1000.0)
    assert sem["quantidade"] == 1 and "baseCalculo" not in sem
    assert com["baseCalculo"] == 1000.0 and "quantidade" not in com


def test_a_parte_sem_documento_vai_so_com_o_nome():
    """A casa mandou `{nome}` sozinho em 46 dos 236 blocos de parte.

    Um `documento: ""` seria campo inventado.
    """
    envelope = AS.envelope_do_ato_do_ri(
        matricula="4014", numero_do_ato=1, escrevente="FULANA",
        versao_tabela="0220260101", descricao_natureza="Compra", livro="2-S",
        codigo_tj="16.3",
        partes=[{"nome": "SEM DOCUMENTO"},
                {"nome": "COM DOCUMENTO", "documento": "000.000.030-26"}])
    partes = envelope["dadosSelo"]["partes"]["parteAto"]
    assert partes[0] == {"nome": "SEM DOCUMENTO"}
    assert partes[1] == {"nome": "COM DOCUMENTO",
                         "documento": "00000003026"}


def test_o_caminho_do_ato_do_ri_nao_responde_pela_tabela():
    """`caminho_do_ato('ri_atos', ...)` devolve None DE PROPÓSITO.

    Ela não recebe o valor declarado, e é ele que escolhe. O None daqui não
    quer dizer «a casa nunca selou isto» — ela selou 120 vezes.
    """
    assert AS.caminho_do_ato("ri_atos", "R") is None
    assert AS.caminho_do_ato("ri_atos", "AV") is None


# ------------------------------------------------------------- a tela


def test_o_qr_colado_saiu_da_tela(casa):
    html = casa["c"].get(
        f"/registro-imoveis/{casa['mid']}?lavrar=1").get_data(as_text=True)
    assert "selo-qr-area" not in html
    assert "Ctrl+V" not in html, "o campo de colar imagem voltou"
    assert 'name="selo_qr"' not in html


def test_a_tela_oferece_os_itens_que_a_casa_usou(casa):
    """Medidos no acervo, na ordem de uso — e não uma lista escrita à mão."""
    html = casa["c"].get(
        f"/registro-imoveis/{casa['mid']}?lavrar=1").get_data(as_text=True)
    assert 'name="codigo_tj"' in html
    assert "16.22.2" in html and "16.3" in html


def test_a_previa_em_tempo_real_esta_ligada_e_sabe_que_e_texto(casa):
    """**A prévia do RI não é a das Notas.**

    Lá o teor é HTML e sai com `innerHTML`; aqui é texto, e `innerHTML`
    perderia toda quebra de linha e leria um `<` digitado como etiqueta.
    """
    html = casa["c"].get(
        f"/registro-imoveis/{casa['mid']}?lavrar=1").get_data(as_text=True)
    assert 'data-teor="texto"' in html
    assert 'data-teor-previa="texto"' in html


def test_o_script_da_previa_nao_poe_a_barra_de_marcas_no_teor_de_texto():
    """A barra escreveria `<b>` literal dentro do ato, e ele sairia impresso."""
    js = (RAIZ / "static" / "teor-marcas.js").read_text(encoding="utf-8")
    assert 'if (formato !== "texto") montarBarra(campo)' in js
    assert "previa.textContent = campo.value" in js


# ------------------------------------------------------- lavrar e selar


def test_lavra_guardando_o_valor_em_centavos_e_o_item(casa):
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(casa):
        _lavrar(casa, codigo_tj="16.3", base_calculo="243.000,00")
    a = casa["con"].execute(
        "SELECT * FROM ri_atos WHERE matricula_id=?", (casa["mid"],)).fetchone()
    assert a["base_calculo_centavos"] == 24300000, "dinheiro não é float aqui"
    assert a["codigo_tj"] == "16.3"


def test_selo_recusado_NAO_DEIXA_O_ATO_MEIO_PRONTO_NO_LIVRO(casa):
    """**A regra mudou DUAS vezes, e este teste afirmava a do meio.**

    Ele nasceu dizendo «selo recusado não derruba o ato» — a regra de agosto.
    Em 15/09 o oficial a desfez («deu problema no av05 e foi lavrado, mas
    cancelado só pq não saiu selo. não eh assim que deve operar»), e o teste
    passou a cobrar o ato **cancelado no livro, com o motivo escrito**.

    **Em 16/09 ele desfez também essa**: «selo recusado suspende ato (fica
    salvo como minuta para lavrar de novo)». Não há mais cancelamento por
    selo: `RI_ATO_NAO_LAVRADO_SELO_FALHOU` e a frase «Ato NÃO mantido» não
    existem em lugar nenhum do sistema. O teste continuava cobrando os dois —
    **teste vermelho que afirma o errado é pior que teste nenhum**, e a data
    de cada mudança é dele, não minha.

    O QUE ELE COBRA AGORA é o caso desta instalação de ensaio, sem selador
    apontado: a falha também suspende, guarda o texto como minuta e diz onde
    configurar o aparelho. Ausência e recusa produzem o mesmo risco no livro.
    """
    r = _lavrar(casa, codigo_tj="16.3", base_calculo="1.000,00")
    html = " ".join(r.get_data(as_text=True).split())
    a = casa["con"].execute(
        "SELECT * FROM ri_atos WHERE matricula_id=?", (casa["mid"],)).fetchone()
    assert a is None, "a instalação sem selador deixou ato incompleto no livro"
    assert "NÃO foi lavrado" in html
    assert "selador ainda não foi apontado" in html
    minutas = casa["con"].execute(
        "SELECT COUNT(*) FROM ri_minutas WHERE matricula_id=?",
        (casa["mid"],)).fetchone()[0]
    assert minutas == 1, "o texto não ficou guardado para nova tentativa"
    marcas = [x[0] for x in casa["con"].execute(
        "SELECT action FROM audit_logs WHERE entity_type='RI_ATO'")]
    assert "RI_ATO_SUSPENSO_SEM_SELO" in marcas
    assert "RI_ATO_NAO_LAVRADO_SELO_FALHOU" not in marcas


def test_sem_selador_configurado_o_ato_do_RI_fica_suspenso(casa):
    """Sem aparelho, o RI não grava ato incompleto e informa o motivo."""
    r = _lavrar(casa, codigo_tj="16.3", base_calculo="1.000,00")
    html = r.get_data(as_text=True)
    a = casa["con"].execute(
        "SELECT * FROM ri_atos WHERE matricula_id=?", (casa["mid"],)).fetchone()
    assert a is None
    assert "NÃO foi lavrado" in html
    assert "selador ainda não foi apontado" in html
    linha = casa["con"].execute(
        """SELECT COUNT(*) FROM audit_logs
            WHERE action='RI_ATO_LAVRADO_SEM_SELO_POR_DECISAO'""").fetchone()[0]
    # A MARCA CONTINUA SE CHAMANDO «POR DECISÃO», E NINGUÉM DECIDIU NADA AQUI
    # — resíduo do desvio que o relato #77 tirou em 16/09/2026. Está declarado
    # ao oficial; renomear marca de auditoria é decisão dele, porque o rastro
    # desta casa não se reescreve por conta própria.
    assert linha == 0, "voltou a marca antiga de lavratura sem selo"


def test_o_selo_digitado_a_mao_ganha_e_o_automatico_nem_e_pedido(casa):
    """Pedir os dois faria a casa comprar dois selos para o mesmo ato."""
    r = _lavrar(casa, codigo_tj="16.3",
                selo_texto="Poder Judiciário - TJMA. Selo: REGAVD000000NARRKWVNJCRSVO21")
    html = r.get_data(as_text=True)
    a = casa["con"].execute(
        "SELECT selo_texto FROM ri_atos WHERE matricula_id=?",
        (casa["mid"],)).fetchone()
    assert "REGAVD000000NARRKWVNJCRSVO21" in (a["selo_texto"] or "")
    assert "SEM SELO" not in html


def test_sem_item_de_custa_a_RECUSA_E_ANTES_e_nada_se_lavra(casa):
    """**Contrato de 15/09, e este teste ainda afirmava o de antes dele.**

    Ele dizia «o ato entra mas a tela diz por quê» — a regra de agosto, em
    que a falta do item só aparecia na hora do selo. O oficial a desfez:
    «se deu problema no selo deve voltar e permitir retificar o erro e tentar
    lavrar novamente o mesmo ato». O que a TELA sabe antes de qualquer rede —
    falta natureza, falta item, isento sem motivo — passou a ser recusado
    **antes de o ato nascer**, em `falta_para_selar`, com o cliente ainda na
    frente. Recusar depois custa um ato desfeito no livro.

    **E A FICHA DE ACERVO É A EXCEÇÃO**, por ordem dele em 16/09: «ato de
    acerto fica sem item de custa». Aquele ato já foi cobrado e selado no
    papel, anos atrás. Está provado em
    `tests/test_ri_suspende_so_quando_ha_recusa.py`.
    """
    r = _lavrar(casa, codigo_tj="")
    html = r.get_data(as_text=True)
    assert casa["con"].execute(
        "SELECT COUNT(*) FROM ri_atos WHERE matricula_id=?",
        (casa["mid"],)).fetchone()[0] == 0, (
        "o ato nasceu para ser desfeito depois — e a recusa e antes")
    assert "item da tabela de custas" in html, (
        "recusar sem dizer o que falta deixa quem atende sem saida")


# ------------------------------------------- a lista de quem ficou sem selo


def test_a_lista_de_sem_selo_le_a_coluna_certa_de_cada_tabela(casa):
    """**Defeito achado em 14/09/2026, e ele era anterior.**

    `atos_sem_selo` supunha que toda tabela de ato tem coluna `selo`, e
    quebrava com `no such column: selo` em quatro das cinco — as mesmas
    quatro sobre as quais este projeto mais escreveu «o ato sem selo aparece
    em `atos_sem_selo`».
    """
    for tabela in ("ri_atos", "ri_certidoes", "ri_protocolos", "nt_cartoes",
                   "rc_atos"):
        AS.atos_sem_selo(casa["con"], tabela)  # não pode estourar


def test_o_ato_sem_selo_aparece_na_tela_com_onde_resolver(casa):
    """Promessa que nada cumpre é o carimbo que mente numa rede de segurança.

    Até aqui `atos_sem_selo` não tinha **um único chamador** em todo o
    sistema, embora oito comentários prometessem esta lista ao operador.
    """
    # Só o acervo histórico pode existir sem item/selo. Um ato novo sem
    # aparelho seria suspenso antes de chegar a esta lista.
    with casa["con"] as con:
        con.execute("""UPDATE ri_matriculas
                          SET tipo_ficha='ACERVO', numero='4014'
                        WHERE id=?""",
                    (casa["mid"],))
    _lavrar(casa, codigo_tj="", base_calculo="", numero="1")
    ato = casa["con"].execute(
        "SELECT id, selo_texto FROM ri_atos WHERE matricula_id=?",
        (casa["mid"],)).fetchone()
    assert ato is not None, "o ato histórico de acervo não ficou no livro"
    resposta = casa["c"].get("/registro-imoveis/selos")
    html = resposta.get_data(as_text=True)
    cabecalhos = re.findall(r"<title>(.*?)</title>|<h1[^>]*>(.*?)</h1>",
                            html, re.S | re.I)
    assert "Lavrados sem selo" in html, (
        f"status={resposta.status_code}; pagina={cabecalhos!r}")
    assert "R-1" in html, "a lista não disse QUAL ato está sem selo"
    assert f"/registro-imoveis/{casa['mid']}" in html, "sem por onde resolver"


def test_a_lista_de_itens_nao_e_escrita_a_mao(casa):
    """**Ela é a medida do acervo, e não uma segunda cópia.**

    A primeira versão desta função escrevia os itens à mão em `ato_selado`, e
    **já nasceu divergente**: faltava o `16.22.4.2`, de um uso só, que
    `atribuicoes.ITENS_DE_CUSTA_POR_CAMINHO` — gerado dos 24.849 selos reais —
    tem. Duas réguas para o mesmo fato divergem no primeiro conserto; esta
    divergiu antes dele.
    """
    import atribuicoes as ATR

    medidos = AS.itens_medidos_do_ato_do_ri()
    do_acervo = set()
    for caminho in (AS.CAMINHO_DO_ATO_DO_RI_SEM_VALOR,
                    AS.CAMINHO_DO_ATO_DO_RI_COM_VALOR):
        do_acervo |= set(ATR.itens_de_custa_do_ato(caminho))
    assert {c for c, _ in medidos} == do_acervo
    assert "16.22.4.2" in do_acervo, "o item de um uso só sumiu da medição"
    # E a ordem é a de uso: o que responde pela maioria vem primeiro.
    assert [n for _, n in medidos] == sorted(
        (n for _, n in medidos), reverse=True)


# ------------------------------------------------- a gratuidade, que é exceção


def test_o_envelope_isento_manda_a_forma_QUE_O_APARELHO_ACEITA():
    """**`isento` booleano mais `motivoIsentoGratuito` — e nada mais.**

    A casa pagou caro por esta forma: em 10/09/2026 o oficial relatou «o
    problema do selo gratuito de certidão», e a causa era o envelope sair só
    com `isentoGratuito`, que o contrato do selador não declara em schema
    nenhum. **A consequência era certidão sem selo.** A forma provada contra o
    aparelho é esta, e é a mesma que a prenotação deste módulo manda em 48
    envelopes reais.
    """
    envelope = AS.envelope_do_ato_do_ri(
        matricula="4014", numero_do_ato=1, escrevente="FULANA",
        versao_tabela="0220260101", descricao_natureza="REURB", livro="2-S",
        codigo_tj="16.22.2", isento=True,
        motivo_isencao="reurb-s, lei 13.465/2017")
    dados = envelope["dadosSelo"]
    assert dados["isento"] is True
    assert dados["motivoIsentoGratuito"] == "REURB-S, LEI 13.465/2017", \
        "o motivo vai em maiúsculas, como nos 48 envelopes medidos"


def test_o_envelope_recusa_gratuidade_sem_motivo():
    """Sem o motivo escrito a correição não tem o que ler no selo."""
    with pytest.raises(AS.AtoError) as erro:
        AS.envelope_do_ato_do_ri(
            matricula="4014", numero_do_ato=1, escrevente="FULANA",
            versao_tabela="0220260101", descricao_natureza="REURB",
            livro="2-S", codigo_tj="16.22.2", isento=True)
    assert "motivo" in str(erro.value).lower()


def test_o_ato_que_nao_e_gratuito_nao_manda_motivo_nenhum():
    """Campo de isenção em ato cobrado seria campo inventado."""
    envelope = AS.envelope_do_ato_do_ri(
        matricula="4014", numero_do_ato=1, escrevente="FULANA",
        versao_tabela="0220260101", descricao_natureza="Compra", livro="2-S",
        codigo_tj="16.3")
    assert envelope["dadosSelo"]["isento"] is False
    assert "motivoIsentoGratuito" not in envelope["dadosSelo"]


def test_a_tela_assinala_que_a_gratuidade_e_excecao(casa):
    """«assinalando que é exceção dentro do RI» — pedido do oficial.

    E a exceção tem tamanho medido: 48 das 829 prenotações, e nenhum dos 120
    atos.
    """
    html = casa["c"].get(
        f"/registro-imoveis/{casa['mid']}?lavrar=1").get_data(as_text=True)
    # 12/10/2026: a tela foi redesenhada em 30/09/2026 (pedido da Beatriz):
    # o quadro diz que o selo será COBRADO e que só se marca a gratuidade com
    # norma que a dispense. A frase antiga («É exceção — 48 de 829») saiu, e
    # «É exceção» passou a casar só com o quadro do encerramento.
    assert "Este selo será COBRADO" in html
    assert "só se houver" in html, "a tela não diz que a gratuidade é exceção"
    assert 'name="isento"' in html and 'name="motivo_isencao"' in html
    # Os motivos medidos, para o balcão não redigitar a frase com erro.
    assert "13.465" in html


def test_gratuidade_sem_motivo_e_recusada_no_balcao_e_nada_e_lavrado(casa):
    """**A recusa é aqui, e não no selo.**

    No selo o ato já estaria lavrado e na cadeia de hash: sobraria um ato
    marcado como gratuito sem dizer por quê, e consertar exigiria averbação.
    """
    r = _lavrar(casa, codigo_tj="16.22.2", isento="1")
    assert "motivo escrito" in r.get_data(as_text=True)
    assert casa["con"].execute(
        "SELECT COUNT(*) FROM ri_atos").fetchone()[0] == 0


def test_o_ato_gratuito_fica_assinalado_na_ficha_com_o_motivo(casa):
    """Marca sem o porquê não responde à pergunta que a correição faz."""
    motivo = ("O REGISTRO DISPENSA O PAGAMENTO DE EMOLUMENTOS PREVISTO NA "
              "LEI Nº 13.465, DE 2017.")
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(casa):
        _lavrar(casa, codigo_tj="16.22.2", isento="1",
                motivo_isencao=motivo)
    a = casa["con"].execute("SELECT * FROM ri_atos").fetchone()
    assert a["isento"] == 1
    assert a["motivo_isencao"] == motivo, "o motivo não ficou gravado"
    html = casa["c"].get(
        f"/registro-imoveis/{casa['mid']}").get_data(as_text=True)
    assert "Ato gratuito" in html
    assert "13.465" in html, "a ficha marcou sem dizer por quê"


def test_os_motivos_oferecidos_sao_os_que_a_casa_escreveu():
    """Medidos nos 48 isentos — e a lista existe por causa dos erros neles.

    Os 48 são a mesma coisa escrita de quinze maneiras, com «INTERESE
    SOCILA», «PAGAEMENTO» e um «DE 2022» onde a lei é de 2017 — tudo isso
    impresso dentro do selo.
    """
    motivos = AS.MOTIVOS_DA_GRATUIDADE_DO_RI
    assert motivos, "a lista sumiu"
    # A ordem é a de uso: REURB-S responde por quase todos.
    assert motivos[0]["usos"] == 40
    assert "13.465" in motivos[0]["texto"]
    for m in motivos:
        assert m["texto"] == m["texto"].upper(), \
            "o motivo vai em maiúsculas no selo"
        assert m["fundamento"], "motivo sem fundamento não se confere"
