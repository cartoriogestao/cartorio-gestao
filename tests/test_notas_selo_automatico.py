"""O selo automático do balcão de Notas, pelas telas.

«Tentei praticar um reconhecimento de firma e ainda não tenho botão pra selar
automático» — o oficial, em 27/08/2026. Não faltava botão: faltava a amarração.
As Notas foram a última atribuição a ser ligada, e são a MAIOR —
`/selo/notas/reconhecimento-firma` sozinho é metade dos 26.130 selos que esta
casa emitiu.

O QUE ESTES TESTES PROTEGEM
    O selador é máquina da rede local e, num banco de teste, ele não existe.
    Por isso o que se prova aqui não é que o selo sai — é o que acontece
    QUANDO ELE NÃO SAI: o reconhecimento de firma não pode ficar lavrado sem
    selo em silêncio. Só fica se quem lavra marcar decisão expressa, e a falha
    precisa ficar escrita.

UM SELO POR FIRMA, e isso é medido: no E-Ofício cada firma era um ato e um
    selo — 13.213 reconhecimentos, **todos com uma firma só** —, e o envelope
    levava UMA pessoa em `nomesReconhecido.parteAto` nos 13.776 selos medidos.
    Um selo para três firmas seria a serventia cobrando três e selando uma.
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

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def serventia(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA,
                                "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "cliente": c, "banco": banco}


def _con(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _cartao(s, nome: str, documento: str) -> int:
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO nt_cartoes (nome, documento, criado_em)
               VALUES (?,?,datetime('now'))""", (nome, documento))
    return int(cur.lastrowid)


def _reconhecer(s, ids: list[int], **extra):
    html = s["cliente"].get("/notas/reconhecimento").get_data(as_text=True)
    dados = {"acao": "reconhecer", "cartao_id": [str(i) for i in ids],
             "especie": "SEMELHANCA", "csrf_token": _token(html)}
    dados.update(extra)
    return s["cliente"].post("/notas/reconhecimento", data=dados,
                             follow_redirects=True)


def test_o_reconhecimento_nao_lavra_sem_selo_por_padrao(serventia):
    """O aparelho não existe no teste — sem decisão expressa, nada é lavrado."""
    cid = _cartao(serventia, "MARIA DA SILVA", "00000001082")
    resposta = _reconhecer(serventia, [cid])
    assert resposta.status_code == 200
    assert _con(serventia).execute(
        "SELECT COUNT(*) n FROM nt_reconhecimentos").fetchone()["n"] == 0
    html = resposta.get_data(as_text=True)
    assert "Reconhecimento NÃO lavrado" in html
    assert "Motivo:" in html


def test_a_falha_do_selo_fica_na_auditoria_quando_nao_lavra(serventia):
    """Jargão não chega ao balcão, mas o motivo tem de ficar escrito."""
    cid = _cartao(serventia, "MARIA DA SILVA", "00000001082")
    _reconhecer(serventia, [cid])
    linha = _con(serventia).execute(
        """SELECT * FROM audit_logs
             WHERE action='NT_RECONHECIMENTO_NAO_LAVRADO_SELO_FALHOU'"""
    ).fetchone()
    assert linha is not None
    assert "motivo" in linha["details"]
    # E não pode mais dizer «Falta colar o selo», que era o texto de quando
    # nenhuma tela chamava o selador.
    assert "Falta colar o selo" not in linha["details"]


def test_nao_lavra_nem_com_o_campo_do_desvio_mandado_na_mao(serventia):
    """A exceção ACABOU — relato #77, 16/09/2026, ordem do oficial.

        «se falhar o selo, sempre suspender o ato para corrigir o problema»

    Este teste provava o contrário até 16/09: que marcando a caixa o ato ficava
    de pé sem selo. **Ele foi virado, e não apagado** — porque o campo ainda
    pode ser mandado na mão, por um favorito antigo ou por uma tela que não foi
    atualizada, e é justamente esse o caminho que não pode ressuscitar o
    desvio.
    """
    cid = _cartao(serventia, "MARIA DA SILVA", "00000001082")
    html = _reconhecer(serventia, [cid], lavrar_sem_selo="1").get_data(as_text=True)
    assert "Reconhecimento NÃO lavrado" in html
    assert _con(serventia).execute(
        "SELECT COUNT(*) n FROM nt_reconhecimentos").fetchone()["n"] == 0, (
        "o campo `lavrar_sem_selo` mandado na mão ainda lavra sem selo — o "
        "desvio que o relato #77 mandou tirar de todo módulo")
    assert _con(serventia).execute(
        """SELECT COUNT(*) n FROM audit_logs
             WHERE action='NT_RECONHECIMENTO_LAVRADO_SEM_SELO_POR_DECISAO'"""
    ).fetchone()["n"] == 0


def test_cada_firma_tem_a_sua_linha_para_o_selo(serventia):
    """Três firmas, três lugares onde o selo de cada uma vai morar.

    **A PROVA MUDOU DE LUGAR EM 16/09/2026, e não de conteúdo.** Ela se
    apoiava na lavratura sem selo para deixar as três linhas de pé; pelo
    relato #77 o ato é desfeito quando o selo não sai, e com ele as partes.
    O que se prova agora é o mesmo por onde continua sendo verdade: a
    **coluna** existe, e a tentativa registra as **três** firmas.

    Sem a coluna, três firmas dividiriam um selo — a serventia cobrando três
    e selando uma.
    """
    import json
    ids = [_cartao(serventia, f"PESSOA {n}", f"0172028531{n}")
           for n in range(1, 4)]
    _reconhecer(serventia, ids)
    colunas = [c["name"] for c in _con(serventia).execute(
        "PRAGMA table_info(nt_reconhecimento_partes)").fetchall()]
    assert "selo" in colunas, (
        "a coluna `selo` das partes não existe — sem ela, três firmas dividem "
        "um selo, que é a serventia cobrando três e selando uma")
    linha = _con(serventia).execute(
        """SELECT details FROM audit_logs
             WHERE action='NT_RECONHECIMENTO_TENTADO'""").fetchone()
    assert linha is not None, "a tentativa não ficou na auditoria"
    assert json.loads(linha["details"])["firmas"] == 3


def test_as_tres_tabelas_do_balcao_de_notas_sao_tabela_de_ato():
    """Tabela não registrada não dá erro de programação: dá ato perdido."""
    import ato_selado as AS
    for t in ("nt_reconhecimentos", "nt_autenticacoes", "nt_cartoes"):
        assert t in AS.TABELAS_DE_ATO, (
            f"{t} não está em TABELAS_DE_ATO — o selo seria recusado com «não "
            f"é tabela de ato», e o reconhecimento de firma é metade do "
            f"movimento desta casa")


def test_o_caminho_de_cada_tela_de_notas_existe_no_contrato():
    """Compor caminho que o selador não tem seria selar por onde ninguém selou."""
    import ato_selado as AS
    import selador
    for tabela, caminho in AS.CAMINHO_DAS_NOTAS.items():
        assert caminho in selador.ENDPOINTS, (
            f"{tabela} aponta para {caminho}, que não está no contrato")


@pytest.mark.parametrize("especie,tipo", [("AUTENTICIDADE", 0),
                                          ("SEMELHANCA", 1)])
def test_a_natureza_da_firma_e_a_do_contrato(especie, tipo):
    """0 é autenticidade e 1 é semelhança — a documentação da FPFTech.

    Medido no acervo: 11.919 selos com `tipo: 1` para 11.410 atos de
    semelhança, e 1.857 com `tipo: 0` para 1.802 de autenticidade.
    """
    import ato_selado as AS
    envelope = AS.envelope_das_notas(
        tabela="nt_reconhecimentos", codigo_tj="13.17.2",
        escrevente="JEAN", versao_tabela="0520260101", especie=especie,
        partes=[{"nome": "MARIA", "documento": "000.000.010-82"}])
    assert envelope["natureza"] == {"tipo": tipo}
    # O documento vai só com dígitos — é assim nos 13.776 medidos.
    assert envelope["nomesReconhecido"]["parteAto"][0]["documento"] == "00000001082"


def test_a_caixa_do_sem_selo_nao_esta_em_tela_nenhuma():
    """A ordem dele foi «em nenhum serviço ou módulo» — e isso se varre.

        «nao precisa manter essa caixa de selecao em nenhum servico ou
         modulo» — o oficial, relato #77, 16/09/2026

    **ELE FOI CUMPRIDO PELA METADE, e é por isso que este varredor existe.**
    Em 16/09 às 20h37 o relato foi fechado com a nota «Removida a caixa
    "mesmo se o selo falhar" de todos os módulos»; os motores de fato pararam
    de ler o campo, e **catorze caixas continuaram desenhadas em doze telas**.

    O ESTRAGO É UM LAÇO NO BALCÃO: a recusa dizia «marque a opção de lavrar
    sem selo e tente novamente», o escrevente marcava a caixa — que estava
    ali, à vista —, e levava a mesma recusa mandando marcar o que ele acabou
    de marcar. Com o cliente na frente.

    Este teste ocupa o lugar de um que provava a exceção funcionando; ele
    passou a provar que ela não voltou.
    """
    telas = glob.glob(str(RAIZ / "templates" / "**" / "*.html"), recursive=True)
    assert len(telas) > 200, "a varredura não achou as telas"
    com_a_caixa = [Path(t).name for t in telas
                   if 'name="lavrar_sem_selo"' in
                   Path(t).read_text(encoding="utf-8", errors="replace")]
    assert not com_a_caixa, (
        "a caixa «mesmo se o selo falhar» voltou em "
        f"{', '.join(sorted(com_a_caixa))} — o relato #77 mandou tirá-la de "
        "todo módulo, e caixa que o motor não lê é o balcão marcando e "
        "levando a mesma recusa")


def test_a_recusa_nao_manda_marcar_o_que_nao_existe():
    """Recusa que aponta uma saída inexistente é pior que recusa seca.

    As quatro recusas do balcão de Notas mandavam «marque a opção de lavrar
    sem selo». Com a caixa fora, isso põe o escrevente a procurar pela tela
    inteira uma opção que não está em tela nenhuma.
    """
    codigo = (RAIZ / "notas_web.py").read_text(encoding="utf-8")
    assert "marque a opção de lavrar sem selo" not in codigo, (
        "a recusa ainda manda marcar a caixa que saiu no relato #77")


def test_a_autenticacao_NAO_fica_quando_o_selo_falha_sem_decisao(serventia):
    """A metade que faltava: a mesma tela, **sem** a autorização marcada.

    O reconhecimento já tinha este guarda (`test_..._nao_lavra...`), e a
    autenticação não — de modo que a regra valia para uma tela do balcão de
    Notas e não para a vizinha, que é o defeito que o teste do reconhecimento
    existia para impedir.
    """
    html = serventia["cliente"].get("/notas/autenticacao").get_data(as_text=True)
    r = serventia["cliente"].post(
        "/notas/autenticacao",
        data={"acao": "autenticar", "folhas": "3", "tipo": "PADRAO",
              "csrf_token": _token(html)}, follow_redirects=True)
    assert r.status_code == 200
    assert _con(serventia).execute(
        "SELECT COUNT(*) n FROM nt_autenticacoes").fetchone()["n"] == 0
    corpo = r.get_data(as_text=True)
    assert "Autenticação NÃO lavrada" in corpo
    assert "Motivo:" in corpo


def test_o_item_de_cada_tela_de_notas_e_o_medido():
    """Os itens saíram do acervo, um a um — não de suposição.

    Medido em 27/08/2026: `13.17.1` nos 2.667 selos de cartão de autógrafo,
    `13.17.2` / `13.17.3` / `13.17.4` no reconhecimento conforme o documento,
    e `13.18` na autenticação, que é por página.
    """
    from notas_schema import SERVICOS, servico_do_reconhecimento
    assert SERVICOS["CARTAO"] == 412          # 13.17.1
    assert SERVICOS["SEMELHANCA"] == 413      # 13.17.2
    assert SERVICOS["VEICULO"] == 414         # 13.17.3
    assert SERVICOS["FINANCEIRO"] == 416      # 13.17.4
    assert SERVICOS["AUTENTICACAO"] == 415    # 13.18
    # O ITEM NAO SAI DA ESPECIE, e sim do documento — medido: autenticidade
    # puxa para veículo (1.337 de 1.857), mas 183 autenticidades saíram pelo
    # item comum. Quem escolhe é quem atende.
    assert servico_do_reconhecimento("AUTENTICIDADE") == SERVICOS["SEMELHANCA"]
    assert servico_do_reconhecimento("SEMELHANCA", veiculo=True) == SERVICOS["VEICULO"]
