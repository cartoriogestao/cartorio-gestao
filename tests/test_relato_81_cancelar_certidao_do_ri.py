"""O CANCELAMENTO DA CERTIDÃO DO RI NA FICHA DA MATRÍCULA — relato #81.

    «dar a possibilidade de cancelar certidao emitida, nos termos que ja temos
    no RCPN, cancelar depois de baixar o selo e declarar»
    «ter mais controle das certidoes emitidas»

    — o oficial, 17/09/2026, e o relato veio com o endereço: `/registro-imoveis/5378`,
    que é a ficha de uma matrícula.

O QUE FALTAVA, MEDIDO ANTES DE MEXER
    A rota existia desde 15/09, e a lista de certidões
    (`/registro-imoveis/certidoes`) tinha o formulário inteiro: motivo
    obrigatório, a declaração do selo no TJMA, e o motivo à vista depois. **A
    ficha da matrícula não tinha nada disso.** Ela listava as certidões emitidas
    — número, tipo, requerente, quem expediu, selo — e não havia o que fazer com
    elas: a linha da cancelada dizia `(cancelada)` e calava o motivo.

    É o relato #36 outra vez, pelo lado da tela: não «função pronta que ninguém
    chama», e sim **formulário pronto que uma tela tem e a outra não**. E das
    duas, a que faltava é a pior de faltar — quem abre a matrícula e vê a
    certidão errada (matrícula trocada, requerente errado) é quem sabe que ela
    está errada. Mandá-lo à lista de certidões é largar o imóvel que ele estava
    conferindo.

O QUE ESTES TESTES PROVAM, um a um
    1. a ficha da matrícula **tem** o formulário (é o relato);
    2. as DUAS telas usam a MESMA macro — duas cópias divergiriam no primeiro
       conserto, e o que diverge é o cancelamento de um papel que já saiu;
    3. a lista de perfis da macro é a mesma da rota (a tela esconde por
       educação; quem recusa é a rota);
    4. cancelar da ficha **volta para a ficha**;
    5. cancelar da lista volta para a lista;
    6. o destino do redirecionamento **não vem de fora** — só a palavra
       `ficha` desvia, e isto é porta que alguém abriria;
    7. certidão órfã (sem matrícula) não estoura ao voltar para a ficha;
    8. o motivo aparece nas **duas vistas, com o mesmo texto** (relato #23);
    9. quem cancelou é o **nome**, e não o login — a mesma convenção do
       `emitida_por_nome` que fica na linha de cima da mesma tabela;
    10. a gaveta da ficha conta quantas estão canceladas — e conta a **ficha
        inteira**, e não a janela de vinte certidões que a tabela mostra;
    11. sem a declaração do selo no TJMA não cancela (é o pedido: «cancelar
        depois de baixar o selo e declarar»);
    12. motivo com menos de dez letras não cancela — **e o piso é o MESMO do
        RCPN**, medido na fronteira nos dois módulos, porque o relato pediu
        «nos termos que já temos no RCPN» e o RI tinha o dez escrito de novo,
        dentro da própria rota;
    13. certidão já cancelada não se cancela de novo, e o motivo original fica.

A CERTIDÃO DO TESTE SAI COM O SELO DIGITADO, E ISSO NÃO É ATALHO
    A emissão do RI sela **sozinha** — e, quando o selador não responde, a
    certidão **não é emitida**: a rota grava `cancelada=1` com o motivo «Selo não
    emitido: …», para o papel não sair como se estivesse selado. Nesta bancada
    não há selador (é uma máquina da rede local), de modo que a emissão pela tela
    nasceria **já cancelada** e nada aqui poderia ser medido.

    Por isso o `selo_texto` vai no formulário, que é o caminho legítimo de
    quando o aparelho está fora do ar — e é o que a casa faz. **Nenhuma regra foi
    contornada**: o que se mede é o cancelamento de uma certidão emitida e viva.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import cancelamento_certidao as CANC
import rc_certidao as CE

# A certidão do teste é a de inteiro teor desta matrícula, e o nome do requerente
# não importa para nada aqui — o que se mede é o cancelamento.
REQUERENTE = "FULANO DE TAL"

# O SELO DIGITADO À MÃO — o caminho de quando o aparelho da rede não responde.
# Sem ele a emissão se auto-cancela nesta bancada, e o teste mediria o defeito
# errado. São os 28 caracteres que a coluna guarda.
SELO = "CERINT000000B5L9KK4F2QJ5ZQ95"


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _abrir(casa, *, numero: int = 4016) -> int:
    """Abre a ficha da matrícula e devolve o id dela."""
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf,
                   teor, teor_formato)
               VALUES (?, '2', '2', 'ATIVA', 'ESTRUTURADA', 'MANUAL',
                       '2026-09-17T09:00', '2026-09-14', 'Cidade Exemplo', 'MA',
                       '<p>FICHA DE ABERTURA - IMÓVEL RURAL.</p>', 'html')""",
            (numero,))
        mid = int(cur.lastrowid)
    con.close()
    return mid


def _emitir(casa, mid: int) -> dict:
    """Emite a certidão pela tela de verdade e devolve a linha gravada.

    Pela TELA, e não por INSERT: é o caminho que grava `emitida_por_nome`, e é
    com ele que o nome de quem cancelou tem de concordar (teste 9).

    **ELA TEM DE SAIR VIVA.** Sem o selo no formulário, a rota tenta selar,
    falha (não há selador nesta bancada) e **cancela a certidão** — que é o
    comportamento certo na produção e tornaria todo este arquivo uma medição do
    nada.
    """
    tela = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    casa["c"].post(f"/registro-imoveis/{mid}/certidao", data={
        "csrf_token": _token(tela), "tipo": "INTEIRO_TEOR",
        "fonte_corpo": "TEXTO", "requerente": REQUERENTE,
        "selo_texto": SELO}, follow_redirects=True)
    con = _con(casa)
    linha = con.execute(
        "SELECT * FROM ri_certidoes WHERE matricula_id=? ORDER BY id DESC LIMIT 1",
        (mid,)).fetchone()
    con.close()
    assert linha, "a certidão não foi emitida"
    assert not linha["cancelada"], (
        "a certidão do teste nasceu cancelada — sem selador a emissão se "
        f"auto-cancela ({linha['motivo_cancelamento']!r}); o selo digitado é o "
        "que a mantém viva")
    return dict(linha)


def _linha(casa, certidao_id: int) -> dict:
    con = _con(casa)
    linha = con.execute("SELECT * FROM ri_certidoes WHERE id=?",
                        (certidao_id,)).fetchone()
    con.close()
    return dict(linha)


def _pagina_da_certidao(casa, certidao_id: int) -> str:
    """A tela onde o formulário daquela certidão aparece — a ficha, ou a lista.

    As duas telas mostram a mesma linha; a órfã só aparece na lista.
    """
    mid = _linha(casa, certidao_id)["matricula_id"]
    pagina = f"/registro-imoveis/{mid}" if mid else "/registro-imoveis/certidoes"
    return casa["c"].get(pagina).get_data(as_text=True)


def _cancelar(casa, certidao_id: int, *,
              motivo="Emitida com a matrícula trocada.",
              declaracao=True, voltar="ficha"):
    """Posta o cancelamento pela TELA, com o token que ela trouxe.

    Os campos são os que o formulário tem — se ele deixar de mandar algum, este
    teste falha junto com o balcão, que é o que se quer.
    """
    tela = _pagina_da_certidao(casa, certidao_id)
    dados = {"csrf_token": _token(tela), "motivo": motivo}
    if declaracao:
        dados["selo_cancelado_tjma"] = "1"
    if voltar is not None:
        dados["voltar"] = voltar
    return casa["c"].post(f"/registro-imoveis/certidoes/{certidao_id}/cancelar",
                          data=dados, follow_redirects=True)


# =====================================================================
# 1. A FICHA DA MATRÍCULA TEM O FORMULÁRIO — é o relato, e ele tem endereço
# =====================================================================


def test_a_ficha_da_matricula_tem_o_formulario_de_cancelar(cg_casa_logada):
    """Ela listava as certidões e não tinha o que fazer com elas."""
    casa = cg_casa_logada
    mid = _abrir(casa)
    certidao = _emitir(casa, mid)

    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    assert f"/registro-imoveis/certidoes/{certidao['id']}/cancelar" in html, (
        "a ficha da matrícula não oferece o cancelamento — é o relato #81")
    assert 'name="motivo" required' in html, "falta o motivo obrigatório"
    assert 'name="selo_cancelado_tjma"' in html, (
        "falta a declaração do selo no TJMA — «cancelar depois de baixar o selo "
        "e declarar» é a metade do pedido que se cobra antes, e não depois")


def test_o_formulario_e_o_MESMO_nas_duas_telas():
    """Duas cópias divergiriam no primeiro conserto.

    O formulário mora numa macro, e as duas telas a chamam: a lista de certidões
    e a ficha da matrícula. Este teste fica vermelho se alguém reescrever o
    formulário dentro de uma delas — e a divergência seria num campo que só uma
    das telas cobra, com o cliente na frente.

    **O DESTINO DE CADA TELA TAMBÉM É UM SÓ**: a ficha passa `'ficha'`; a lista
    usa o padrão da macro, que é `'certidoes'`. Escrever o destino de novo na
    lista não é errado — é o que a macro já faz, e duplicá-lo é como as duas
    versões nascem.
    """
    macro = (RAIZ / "templates"
             / "_cancelar_certidao.html").read_text(encoding="utf-8")
    assert "{% macro formulario(" in macro, "a macro do formulário sumiu"
    padrao = re.search(r"\{%\s*macro formulario\([^)]*voltar='([^']*)'",
                       macro)
    assert padrao, "a macro perdeu o destino padrão"
    assert padrao.group(1) == "certidoes", (
        "o padrão da macro deixou de ser a lista de certidões")

    # O FORMULÁRIO INTEIRO VIVE NA MACRO, e em nenhuma das telas: o endereço da
    # rota e a declaração do selo são os dois pedaços que só existem aqui.
    #
    #   **NÃO SE VARRRE `name="motivo"` NA TELA**, e isto é uma medição: a ficha
    #   tem OUTRO campo com esse nome, no formulário de descartar a minuta do RI.
    #   Procurar a palavra no arquivo inteiro acusa a tela certa pelo motivo
    #   errado — é a lição dos varredores que batem na própria prosa, e a
    #   primeira vez que ela aparece num teste de tela escrito por mim.
    for campo in ('name="motivo"', 'name="selo_cancelado_tjma"'):
        assert campo in macro, f"o campo {campo} saiu da macro"

    for arquivo, destino in (("ri_certidoes.html", None),
                             ("ri_ficha.html", "'ficha'")):
        tela = (RAIZ / "templates" / arquivo).read_text(encoding="utf-8")
        assert "_cancelar_certidao.html" in tela, (
            f"{arquivo} não importa o formulário — a tela teria o seu próprio")
        assert "cancelar_certidao(" in tela, (
            f"{arquivo} importa a macro e não a chama")
        if destino:
            assert destino in tela, (
                f"{arquivo} não diz para onde voltar depois de cancelar")
        assert "ri_cancelar_certidao" not in tela, (
            f"{arquivo} monta o endereço do cancelamento por fora da macro — "
            "é assim que nascem dois formulários")
        assert "selo_cancelado_tjma" not in tela, (
            f"{arquivo} voltou a escrever a declaração do selo — agora são duas")


def test_a_lista_de_perfis_da_tela_e_a_da_rota_sao_a_mesma():
    """A tela esconde por educação; quem recusa é a rota — e são os MESMOS.

    Lista escrita duas vezes envelhece na tarde em que se escreve, e aqui o
    resultado seria o botão escondido de quem pode, ou oferecido a quem não
    pode. Comparadas como CONJUNTO: a ordem de escrita é de cada arquivo.
    """
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    # Do decorador da rota, e não do `def`: `@roles_required` fica ENTRE os dois,
    # e cortar no `def` deixaria a lista da rota de fora — teste que erra o
    # recorte acusa quem está certo.
    i = codigo.index('"/registro-imoveis/certidoes/<int:certidao_id>/cancelar"')
    corpo = codigo[i:codigo.index("\n    @app.route(", i)]
    achado = re.search(r'@roles_required\(([^)]*)\)', corpo)
    assert achado, "a rota do cancelamento deixou de exigir perfil"
    da_rota = set(re.findall(r'"([A-Z]+)"', achado.group(1)))

    macro = (RAIZ / "templates"
             / "_cancelar_certidao.html").read_text(encoding="utf-8")
    achado = re.search(r"user\.role in \[([^\]]*)\]", macro)
    assert achado, "a macro deixou de perguntar o perfil"
    da_tela = set(re.findall(r"'([A-Z]+)'", achado.group(1)))

    assert da_tela == da_rota, (
        f"a tela oferece para {sorted(da_tela)} e a rota aceita "
        f"{sorted(da_rota)} — uma das duas envelheceu")


# =====================================================================
# 2. QUEM CANCELA VOLTA PARA ONDE ESTAVA
# =====================================================================


def test_cancelar_da_ficha_volta_para_a_ficha(cg_casa_logada):
    """O motivo de o relato existir: quem confere a matrícula fica nela.

    Sem isto, cancelar da ficha jogaria o escrevente na lista de certidões — e
    ele perderia o imóvel que estava conferindo para conferir outra coisa.
    """
    casa = cg_casa_logada
    mid = _abrir(casa)
    certidao = _emitir(casa, mid)

    r = _cancelar(casa, certidao["id"], voltar="ficha")
    assert r.status_code == 200, r.status_code
    assert r.request.path == f"/registro-imoveis/{mid}", (
        f"quem cancelou da ficha foi parar em {r.request.path}")
    assert _linha(casa, certidao["id"])["cancelada"] == 1


def test_cancelar_da_lista_volta_para_a_lista(cg_casa_logada):
    """A lista continua sendo a lista, e o padrão dela é voltar para ela."""
    casa = cg_casa_logada
    mid = _abrir(casa)
    certidao = _emitir(casa, mid)

    r = _cancelar(casa, certidao["id"], voltar="certidoes")
    assert r.request.path == "/registro-imoveis/certidoes", r.request.path
    assert _linha(casa, certidao["id"])["cancelada"] == 1


def test_o_destino_do_redirecionamento_NAO_vem_de_fora(cg_casa_logada):
    """Destino que vem de fora não é destino — e esta rota mexe num papel que
    já está na mão de alguém.

    A rota só conhece DUAS palavras: `ficha` desvia para a matrícula, e
    qualquer outra coisa cai na lista. Um endereço livre aqui seria redireção
    aberta, que é o defeito clássico de «voltar para onde o usuário pedir».
    """
    casa = cg_casa_logada
    mid = _abrir(casa)

    for tentativa in ("https://exemplo.invalido/x", "//exemplo.invalido",
                      "/administrativo/usuarios", "ficha/x", ""):
        # Cada tentativa precisa de uma certidão nova: a primeira já cancela.
        nova = _emitir(casa, mid)
        r = _cancelar(casa, nova["id"], voltar=tentativa)
        assert r.request.path == "/registro-imoveis/certidoes", (
            f"`voltar={tentativa!r}` levou para {r.request.path}")
        assert "exemplo.invalido" not in r.request.path


def test_certidao_orfa_nao_estoura_ao_voltar_para_a_ficha(cg_casa_logada):
    """Certidão sem matrícula não tem ficha para onde voltar.

    O `url_for('ri_ficha', matricula_id=None)` estouraria na cara do balcão —
    HTTP 500 no meio de um cancelamento que já teria sido gravado. Vai para a
    lista, que é onde a certidão órfã aparece.
    """
    casa = cg_casa_logada
    mid = _abrir(casa)
    certidao = _emitir(casa, mid)
    con = _con(casa)
    with con:
        con.execute("UPDATE ri_certidoes SET matricula_id=NULL WHERE id=?",
                    (certidao["id"],))
    con.close()

    r = _cancelar(casa, certidao["id"], voltar="ficha")
    assert r.status_code == 200, r.status_code
    assert r.request.path == "/registro-imoveis/certidoes", r.request.path
    assert _linha(casa, certidao["id"])["cancelada"] == 1, (
        "o cancelamento se perdeu por causa do destino — o destino não é mais "
        "importante que o ato")


# =====================================================================
# 3. O MOTIVO, NAS DUAS VISTAS, COM O MESMO TEXTO
# =====================================================================


def test_o_motivo_aparece_nas_duas_telas(cg_casa_logada):
    """«Duas vistas do mesmo fato precisam do mesmo texto» — relato #23.

    A lista mostrava o motivo desde 15/09 e a ficha calava: quem abrisse só a
    ficha (que é a tela do imóvel) concluiria que ninguém sabe por que aquela
    certidão foi cancelada.
    """
    casa = cg_casa_logada
    mid = _abrir(casa)
    certidao = _emitir(casa, mid)
    motivo = "Requerente trocado na emissão; segunda via emitida ao interessado."
    _cancelar(casa, certidao["id"], motivo=motivo)

    na_ficha = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    na_lista = casa["c"].get("/registro-imoveis/certidoes").get_data(
        as_text=True)

    for tela, html in (("ficha", na_ficha), ("lista", na_lista)):
        assert motivo in html, f"o motivo do cancelamento não sai na {tela}"
        assert "Cancelada em" in html, f"a data do cancelamento não sai na {tela}"


def test_quem_cancelou_e_o_NOME_e_nao_o_login(cg_casa_logada):
    """A mesma convenção da linha de cima da mesma tabela.

    `emitida_por_nome` grava «MARIO EXEMPLO DOS SANTOS» — é o nome que a
    certidão imprime embaixo da assinatura. O cancelamento gravava
    `_usuario_atual()`, que devolve «mario»: duas convenções na mesma linha, e
    quem lê meses depois pergunta «quem cancelou isto?», que o login não
    responde. É a régua do rastro da minuta e da reabertura, e a mesma do RCPN,
    que o relato mandou imitar — e o defeito só apareceu porque a ficha passou a
    MOSTRAR o campo.
    """
    casa = cg_casa_logada
    mid = _abrir(casa)
    certidao = _emitir(casa, mid)
    _cancelar(casa, certidao["id"])

    linha = _linha(casa, certidao["id"])
    assert linha["cancelada_por"] == linha["emitida_por_nome"], (
        f"quem expediu ficou como {linha['emitida_por_nome']!r} e quem cancelou "
        f"como {linha['cancelada_por']!r} — a mesma linha com duas convenções")
    assert linha["cancelada_por"] != "mario", "gravou o login, e não o nome"
    assert linha["declaracao_selo_tjma_por"] == linha["cancelada_por"], (
        "a declaração do selo ficou com outra assinatura que o cancelamento")

    # E o que está gravado é o que a tela mostra — o nome inteiro, na ficha.
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert linha["cancelada_por"] in html, (
        "a tela não mostra quem cancelou")


def test_a_gaveta_da_ficha_conta_as_canceladas(cg_casa_logada):
    """«Ter mais controle das certidões emitidas» é a segunda metade do relato.

    O título da gaveta dizia só o total, e «2 certidões» com uma cancelada
    dentro não é o mesmo que duas válidas: quem lê a ficha para decidir se emite
    uma segunda via precisa saber disso antes de abrir a lista.
    """
    casa = cg_casa_logada
    mid = _abrir(casa)
    primeira = _emitir(casa, mid)
    segunda = _emitir(casa, mid)          # esta fica válida
    _cancelar(casa, primeira["id"])

    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert re.search(r"\(\s*2\s*,\s*1 cancelada\s*\)", html), (
        "a gaveta não diz quantas estão canceladas")

    # E com DUAS canceladas o plural é o certo — a conta é a mesma.
    _cancelar(casa, segunda["id"])
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert re.search(r"\(\s*2\s*,\s*2 canceladas\s*\)", html), (
        "o plural da contagem saiu errado")


def test_a_contagem_e_da_FICHA_INTEIRA_e_nao_da_janela_de_vinte(cg_casa_logada):
    """O número do título responde pela matrícula, e não pelas vinte em tela.

    Medido no código antes de consertar: a conta era `sum(1 for c in certidoes
    ...)`, feita **dentro da janela** que a ficha carrega (`LIMIT 20`). Numa
    matrícula com vinte e duas emitidas e três canceladas, a gaveta diria
    «20, 1» — e quem lê o número o lê como o da **matrícula**, que é o que o
    título promete. **Número que mede outra coisa é o carimbo que mente**, e
    aqui ele é do tipo que ninguém confere: vinte certidões é um número
    plausível.

    **E NENHUMA FICHA DESTA CASA CHEGA LÁ — medido na produção em 17/09/2026:
    375 certidões do RI em 276 matrículas, a maior com 8.** Este teste descreve
    o defeito na fronteira em que ele apareceria, e não um número que alguém
    esteja vendo errado hoje; o que ele guarda é o dia em que a primeira ficha
    passar de vinte.

    As dezenove de baixo entram **direto na tabela**, e isso é deliberado: o que
    se mede é a CONTA da tela, não o caminho da emissão — que os outros testes
    percorrem inteiro, e que custaria dezenove selagens para medir o mesmo
    número. A linha que o teste insere tem os campos que a contagem lê, e mais
    nada; inventar um corpo de certidão aqui não mediria coisa nenhuma.
    """
    casa = cg_casa_logada
    mid = _abrir(casa)
    viva = _emitir(casa, mid)             # a de nº 1/2026 desta ficha
    cancelada = _emitir(casa, mid)        # a de nº 2/2026, que será cancelada
    _cancelar(casa, cancelada["id"])

    # Mais dezenove, das quais uma cancelada — vinte e uma no total, e a janela
    # da tela mostra vinte.
    con = _con(casa)
    with con:
        for n in range(9001, 9020):
            con.execute(
                """INSERT INTO ri_certidoes (numero, ano, tipo, matricula_id,
                       matricula_numero, requerente, data_emissao, corpo,
                       corpo_formato, cancelada, emitida_em, origem)
                   VALUES (?, 2026, 'INTEIRO_TEOR', ?, '4016', 'FULANO DE TAL',
                           '2026-09-17', '<p>x</p>', 'html', ?, '2026-09-17',
                           'MANUAL')""",
                (n, mid, 1 if n == 9001 else 0))
    con.close()

    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert re.search(r"\(\s*21\s*,\s*2 canceladas\s*\)", html), (
        "a gaveta contou a janela, e não a matrícula — 21 emitidas com duas "
        "canceladas, e não as 20 que a tabela mostra")
    assert "Mostrando as" in html and "20 mais recentes" in html, (
        "a tela conta vinte e uma e não diz que está mostrando vinte: quem lê "
        "procura a que falta")

    # e a certidão cancelada fora da janela continua contada — é o caso que a
    # conta antiga errava.
    assert _linha(casa, viva["id"])["cancelada"] == 0


# =====================================================================
# 4. AS TRÊS RECUSAS — e o que elas protegem
# =====================================================================


def test_sem_a_declaracao_do_selo_nao_cancela(cg_casa_logada):
    """«Cancelar depois de baixar o selo e declarar» — o pedido, e a ordem dele.

    A folha de segurança volta ao estoque no mesmo ato, e o selo do TJMA
    continua valendo no portal se ninguém o cancelar lá. Declarar é o que
    transforma o clique em responsabilidade de quem clica.
    """
    casa = cg_casa_logada
    mid = _abrir(casa)
    certidao = _emitir(casa, mid)

    r = _cancelar(casa, certidao["id"], declaracao=False)
    assert r.status_code == 200, r.status_code
    html = r.get_data(as_text=True)
    assert "Selo do TJMA" in html, (
        "a recusa não explicou o que falta: a tela não trouxe a declaração "
        "obrigatória na cara de quem clicou")
    linha = _linha(casa, certidao["id"])
    assert not linha["cancelada"], "cancelou sem a declaração do selo"
    assert not linha["motivo_cancelamento"], "gravou motivo sem cancelar"


def test_motivo_curto_nao_cancela(cg_casa_logada):
    """Cancelar não apaga: o motivo é o que sobra no livro, e «erro» não diz nada."""
    casa = cg_casa_logada
    mid = _abrir(casa)
    certidao = _emitir(casa, mid)

    _cancelar(casa, certidao["id"], motivo="erro")
    assert not _linha(casa, certidao["id"])["cancelada"], (
        "cancelou com um motivo que não explica nada")

    # e com dez letras passa — o piso é dez, e não «parecido com dez»
    _cancelar(casa, certidao["id"], motivo="matrícula trocada")
    assert _linha(casa, certidao["id"])["cancelada"] == 1


# =====================================================================
# 11-B. O PISO DO MOTIVO É O MESMO NOS DOIS MÓDULOS — medido na fronteira
# =====================================================================


def test_a_regua_do_motivo_e_a_MESMA_no_RI_e_no_RCPN(cg_casa_logada):
    """«Nos termos que já temos no RCPN» é a régua, e não só a cara da tela.

    O RCPN recusa motivo com menos de dez letras desde sempre. O RI recusava
    pelo **mesmo número escrito de novo**, dentro da rota — e dois números
    iguais em dois arquivos são dois números que divergem no primeiro conserto.
    O que diverge aqui não é enfeite: é o campo que explica, anos depois, por
    que um papel que está na mão de alguém foi cancelado.

    Hoje o RI pergunta a `cancelamento_certidao.motivo_curto`, que é módulo que
    os dois **já dividem** (o RCPN chama de lá a `concluir` e a declaração). O
    RCPN continua com o literal dele, que é o que está no ar, e **não foi
    tocado** — quem escrever nele depois vê esta vermelha, que é o que se quer.

    **A FRONTEIRA É MEDIDA NOS DOIS LADOS, e não lida nos dois arquivos.** Um
    teste que comparasse as duas constantes diria que os dois números são iguais
    mesmo que uma das rotas tenha deixado de usar a sua; aqui as duas passam por
    nove e por dez letras de verdade, e o veredito tem de ser o mesmo.

    Por isso ele fixa **dez**: mover a régua é mover as duas e vir mexer aqui,
    e é exatamente essa a decisão que se quer ver tomada de propósito.

    Da parte do RCPN a pergunta vai à função de domínio dele (`rc_certidao.
    cancelar`), porque é ela que guarda a régua; da parte do RI vai à ROTA
    (`/registro-imoveis/certidoes/<id>/cancelar`), porque `motivo_curto` existir
    não prova que a rota ainda a chama.

    **E O GUARDA FOI POSTO À PROVA.** `tmp/_81_prova_do_guarda.py` mexe a régua
    na memória nas duas direções — o RCPN para 12 e para 5 (por `exec` do texto
    do módulo, com o `10` trocado) e a compartilhada para 12 — e mostra qual
    destas afirmações dispara em cada caso. Sem isso, um teste que passa porque
    os dois lados concordam hoje passaria igual se estivesse medindo outra coisa.
    """
    casa = cg_casa_logada
    mid = _abrir(casa)
    NOVE, DEZ = "123456789", "1234567890"
    assert len(NOVE) == 9 and len(DEZ) == 10, "a fronteira do teste saiu do lugar"

    def _cancelou_pelo_rcpn(con, certidao_id, motivo) -> bool:
        """Devolve se o assento ficou cancelado — a régua do RCPN, em ato."""
        try:
            CE.cancelar(con, certidao_id, motivo=motivo,
                        agora="2026-09-17T10:00:00", selo_cancelado_tjma=True)
        except CE.CertidaoRCPNError:
            pass          # a recusa é o veredito, e ela diz o porquê
        return CE.ler(con, certidao_id)["cancelada_em"] is not None

    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    # `rc_certidoes` aponta para `rc_assentos`: o PostgreSQL cobra a FK, e
    # o banco da casa cria `rc_assentos` antes (database.init_db).
    # E `rc_atos.livro_id` aponta para `nu_livros`: o nucleo vem antes.
    import nucleo_schema
    import rc_schema
    nucleo_schema.init_nucleo_schema(con)
    rc_schema.init_rc_schema(con)
    CE.init_rc_certidao_schema(con)
    with con:
        assento_id = int(con.execute(
            """INSERT INTO rc_assentos (serie, especie, nome, criado_em)
               VALUES ('RC_A', 'NASCIMENTO', 'FULANO DE TAL',
                       '2026-09-17T09:00')""").lastrowid)
        cur = con.execute(
            """INSERT INTO rc_certidoes (numero, ano, assento_id, especie, nome,
                   teor, emitida_em, emitida_por)
               VALUES (1, 2026, ?, 'NASCIMENTO', 'FULANO DE TAL', '<p>x</p>',
                       '2026-09-17T09:00', 'FULANA DE TAL')""", (assento_id,))
        rc_id = int(cur.lastrowid)

    # o lado do RCPN
    assert not _cancelou_pelo_rcpn(con, rc_id, NOVE), (
        "o RCPN cancelou com nove letras — a régua dele saiu do lugar, e é o "
        "relato #81 pedindo «nos termos que já temos no RCPN»")
    assert _cancelou_pelo_rcpn(con, rc_id, DEZ), (
        "o RCPN recusou dez letras — a régua dele saiu do lugar")
    # e a mesma régua pela função que o RI consulta, para o par ficar medido:
    assert CANC.motivo_curto(NOVE) and not CANC.motivo_curto(DEZ), (
        "a régua compartilhada não põe a fronteira em dez")
    con.close()

    # o lado do RI, pela tela
    certidao = _emitir(casa, mid)
    r = _cancelar(casa, certidao["id"], motivo=NOVE)
    assert r.status_code == 200, r.status_code
    assert not _linha(casa, certidao["id"])["cancelada"], (
        "o RI cancelou com nove letras — o piso não é o do RCPN")
    assert "o motivo é o que explica a segunda via" in r.get_data(as_text=True), (
        "a recusa do RI não diz para que serve o motivo: a tela mostrou um erro "
        "que não ensina o que fazer")

    _cancelar(casa, certidao["id"], motivo=DEZ)
    assert _linha(casa, certidao["id"])["cancelada"] == 1, (
        "o RI recusou dez letras — o piso não é o do RCPN")


def test_certidao_ja_cancelada_nao_se_cancela_de_novo(cg_casa_logada):
    """O segundo clique não pode reescrever o motivo do primeiro.

    Quem cancelou e por quê é o rastro que a correição lê: sobrescrevê-lo faria
    a certidão ter sido cancelada por outro motivo, por outra pessoa.
    """
    casa = cg_casa_logada
    mid = _abrir(casa)
    certidao = _emitir(casa, mid)
    _cancelar(casa, certidao["id"], motivo="Matrícula trocada na emissão.")
    primeira = _linha(casa, certidao["id"])

    r = _cancelar(casa, certidao["id"],
                  motivo="Outro motivo completamente diverso.")
    assert r.status_code == 200, r.status_code

    depois = _linha(casa, certidao["id"])
    assert depois["motivo_cancelamento"] == primeira["motivo_cancelamento"], (
        "o segundo clique reescreveu o motivo")
    assert depois["cancelada_por"] == primeira["cancelada_por"]
    assert depois["cancelada_em"] == primeira["cancelada_em"]
