"""
O SELO QUE FALTOU num ato do Protesto, emitido depois pelo item já pago.

O caso real, medido na produção em 29/10/2026 (só leitura): o pagamento do
título 9614 (ato 4131) saiu com sete selos, e o do item 17.4.5 falhou — pedido
pela faixa, que o aparelho não conhece. A auditoria tem a reserva estornada com
o item. O PR #109 passou a mandar o item (17.4) no lugar da faixa, mas o 4131
ficou com o item pago e sem o selo, e o Protesto não tinha «selar depois».

O QUE ELES CONFEREM, com o selador de mentira da bancada (um servidor de
verdade numa porta local, `selador_de_bancada`):
    - a ação emite o que falta: o selo sai pelo item do Tribunal (17.4), grava
      a cobertura CONFIRMADA com o item e o `sd_selos` do ato, gasta a unidade,
      e não lavra ato nem cobra de novo — com a auditoria SELO_EMITIDO_DEPOIS;
    - não repete: o item que já tem selo é recusado, e o aparelho não é chamado;
    - recusa o robô (e quem não é o oficial), o ato cancelado e o item não pago;
    - a falha do selador não muda nada e diz o motivo;
    - a obrigação «falta o selo do item X — emita na ficha» aparece e some;
    - o código que o caminho nunca selou só vai com afirmação expressa.

Pessoas e documentos fictícios só (`tests/fixtures/anti_vazamento/`).
"""
from __future__ import annotations

import ast
import html as _html
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from bd_nativo import banco as nativo            # noqa: E402

SENHA = "Senha#12345"
DEVEDOR = "PEDRO EXEMPLO DOS SANTOS"
CPF_DEVEDOR = "00000000191"
CNPJ_CREDOR = "00000001000055"          # 00.000.001/0000-55
PROTOCOLO_DO_TITULO = "2610290001"
AFIRMACAO_BOA = ("Afirmo, sob minha responsabilidade, que este item serve "
                 "para este ato, conforme a tabela do Tribunal de Justiça.")
SERVENTIA = {
    "unit_name": "TABELIONATO DE PROTESTO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "modulo_protesto_ligado": "1",
}


# ------------------------------------------------------------ só calcula


def test_o_codigo_sai_da_referencia_do_selo():
    import protesto_selo_que_faltou as PSF
    assert PSF._codigo_da_referencia("pt_atos:4131:17.2:1") == "17.2"
    assert PSF._codigo_da_referencia(" pt_atos : 4131 : 17.9 : 4 ") == "17.9"
    assert PSF._codigo_da_referencia("pt_atos:4131") is None
    assert PSF._codigo_da_referencia(None) is None


def test_a_pendencia_tem_a_frase_pedida():
    """«falta o selo do item X — emita na ficha»: a frase do pedido, com o
    protocolo e o item do Tribunal quando a faixa muda."""
    import protesto_selo_que_faltou as PSF
    frase = PSF.explicacao(
        {"id": 7, "tipo": "PAGAMENTO", "criado_em": "2026-10-29T19:56:06"},
        {"codigo": "17.4.5", "codigo_selo": "17.4", "livres": 1, "serve": True,
         "protocolo_id": 3, "protocolo_numero": "2026.10.1",
         "tentativa": {"quando": "2026-10-29T19:56:07",
                       "motivo": "o selador falhou ou recusou"}})
    assert frase.startswith("falta o selo do item 17.4.5 — emita na ficha")
    assert "2026.10.1" in frase and "sai como 17.4" in frase
    assert "29/10/2026" in frase


def test_a_rota_usa_o_mesmo_envelope_do_lancamento():
    """Duas montagens do envelope divergiriam no primeiro conserto, e o selo
    de depois declararia outro livro ou outro devedor."""
    fonte = (RAIZ / "atribuicoes_web.py").read_text(encoding="utf-8")
    for peca in ("_contexto_do_selo_do_protesto(con,",
                 "_envelope_do_selo_do_protesto(",
                 "_pedir_um_selo_do_protesto("):
        # a definição, o lançamento e a rota do selo que faltou
        assert fonte.count(peca) >= 3, peca
    assert "def protesto_selo_que_faltou(" in fonte
    assert "PSF.preparar(" in fonte and "PSF.desfazer(" in fonte
    assert "PSF.concluir(" in fonte and "PSF.ACAO_DA_AUDITORIA" in fonte


def test_a_faixa_ligada_paga_o_selo_do_item():
    """O passo 1 da trava acha a faixa ligada pelo item do Tribunal."""
    fonte = (RAIZ / "ato_selado.py").read_text(encoding="utf-8")
    assert "CXP.subitem_da_faixa(it.get(\"codigo_ato\")) == codigo" in fonte


def _literais_por_funcao(caminho: Path) -> dict[str, list[str]]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    saida: dict[str, list[str]] = {}
    for f in arvore.body:
        if not isinstance(f, ast.FunctionDef):
            continue
        doc = (f.body[0].value if f.body and isinstance(f.body[0], ast.Expr)
               and isinstance(f.body[0].value, ast.Constant) else None)
        saida[f.name] = [n.value for n in ast.walk(f)
                         if isinstance(n, ast.Constant) and isinstance(n.value, str)
                         and n is not doc]
    return saida


def test_so_preparar_e_desfazer_escrevem_sql():
    """A conta só lê; quem escreve é a emissão (e `concluir`, pelo caixa)."""
    quem = set()
    for nome, textos in _literais_por_funcao(
            RAIZ / "protesto_selo_que_faltou.py").items():
        for texto in textos:
            if any(c in texto.upper() for c in ("INSERT ", "UPDATE ", "DELETE ")):
                quem.add(nome)
    assert quem == {"preparar", "desfazer"}


def test_o_sql_novo_nao_aumenta_o_acoplamento():
    for textos in _literais_por_funcao(
            RAIZ / "protesto_selo_que_faltou.py").values():
        for texto in textos:
            baixo = texto.lower()
            for proibido in ("substr(", "||", "strftime(", "julianday(", "pragma"):
                assert proibido not in baixo, (proibido, texto[:60])


def test_o_robo_nao_alcanca_a_rota():
    import rotas_do_robo as RR
    import selo_robo as SR
    assert "protesto_selo_que_faltou" not in RR.ROTAS_PERMITIDAS_AO_ROBO
    assert not SR.rota_permitida_ao_robo("protesto_selo_que_faltou")


# ------------------------------------------------------------ a bancada


@pytest.fixture()
def s(cg_casa_logada):
    """A casa logada como o oficial (ADMIN), com o selador de mentira.

    `protocolo_pago=False`: o protocolo pago é o que cada teste monta — a
    bancada não pode montar o dela por cima, ou o selo sairia pago pelo
    protocolo da bancada e não pelo do atendimento.
    """
    from selador_de_bancada import ligar_o_selador
    cg_casa_logada["db"].set_settings(SERVENTIA)
    with ligar_o_selador(cg_casa_logada, protocolo_pago=False) as aparelho:
        cg_casa_logada["aparelho"] = aparelho
        yield cg_casa_logada


def _ler(s, sql: str, args=()) -> list[dict]:
    with s["db"].connect() as con:
        return nativo(con).ler(sql, args)


def _um(s, sql: str, args=()) -> dict | None:
    linhas = _ler(s, sql, args)
    return linhas[0] if linhas else None


def _cenario(s, *, tipo: str = "PAGAMENTO", cancelado: bool = False,
             faltou: str = "17.4.5", faltou_pago: bool = True) -> dict:
    """O 4131 de mentira: o ato de pé, com o protocolo pago; o 17.2 e o 17.9
    (duas unidades) selados e cobertos, e o item `faltou` com a reserva
    estornada na auditoria — o que o aparelho deixou quando recusou."""
    import ato_selado as AS
    import caixa_protocolo as CXP
    agora = s["db"].now()
    caminho = AS.caminho_do_ato("pt_atos", tipo)
    with s["db"].transaction() as con:
        bd = nativo(con)
        # os campos que a ficha lê, como nos outros testes que a abrem
        tid = int(bd.escrever(
            """INSERT INTO pt_titulos (especie, numero_titulo, nosso_numero,
                   valor_centavos, saldo_centavos, protocolo,
                   apresentante_codigo, apresentante_nome, motivo_protesto,
                   tipo_protesto, situacao, origem, origem_chave, criado_em,
                   cedente_nome, cedente_documento)
               VALUES ('DMI', 'SF-0001', 'SF-0001', 123456, 123456, %s, '237',
                       'BANCO DE EXEMPLO', '1', 'C', %s, 'CRA', %s, %s,
                       'EMPRESA DE EXEMPLO S.A.', %s) RETURNING id""",
            (PROTOCOLO_DO_TITULO, "PAGO" if tipo == "PAGAMENTO" else "CANCELADO",
             f"teste:selo-que-faltou:{tipo}", agora, CNPJ_CREDOR))[0]["id"])
        bd.escrever("""INSERT INTO pt_devedores (titulo_id, nome, documento_tipo,
                           documento_numero) VALUES (%s, %s, 'CPF', %s)""",
                    (tid, DEVEDOR, CPF_DEVEDOR))
        ato = int(bd.escrever(
            """INSERT INTO pt_atos (titulo_id, tipo, data_ato, detalhe_json,
                   origem, cancelado, motivo_cancelamento, criado_em, criado_por)
               VALUES (%s, %s, %s, '{}', 'MANUAL', %s, %s, %s,
                       'MARIO EXEMPLO DOS SANTOS') RETURNING id""",
            (tid, tipo, agora[:10], 1 if cancelado else 0,
             "Desfeito no teste." if cancelado else None, agora))[0]["id"])
        p = CXP.abrir(bd, data_abertura=agora[:10], agora=agora,
                      atribuicao="PROTESTO", interessado="CLIENTE DE EXEMPLO")
        itens = {}
        for codigo, qtd, pago in (("17.2", 1, True), ("17.9", 2, True),
                                  (faltou, 1, faltou_pago)):
            itens[codigo] = int(bd.escrever(
                """INSERT INTO cx_protocolo_atos (protocolo_id, descricao,
                       codigo_ato, quantidade, valor_total, quitado,
                       quitado_em, quitado_por)
                   VALUES (%s, %s, %s, %s, '56,32', %s, %s, %s) RETURNING id""",
                (p["protocolo_id"], f"Item {codigo}", codigo, qtd,
                 1 if pago else 0, agora if pago else None,
                 "CAIXA DE TESTE" if pago else None))[0]["id"])
        n = 0
        for codigo, qtd in (("17.2", 1), ("17.9", 2)):
            CXP.consumir_item(bd, itens[codigo], ato_id=ato, tabela="pt_atos",
                              agora=agora, quantas=qtd, origem=CXP.ORIGEM_SELO,
                              quem="MARIO EXEMPLO DOS SANTOS")
            for i in range(1, qtd + 1):
                n += 1
                ref = f"pt_atos:{ato}:{codigo}:{i}"
                bd.escrever(
                    """INSERT INTO cx_selo_coberturas (referencia, tabela, ato_id,
                           forma, protocolo_id, item_id, valor_centavos, usuario,
                           criado_em, situacao, unidades_gastas, confirmada_em)
                       VALUES (%s, 'pt_atos', %s, 'ITEM_PAGO', %s, %s, 5632,
                               'MARIO EXEMPLO DOS SANTOS', %s, 'CONFIRMADA', 1, %s)""",
                    (ref, ato, p["protocolo_id"], itens[codigo], agora, agora))
                bd.escrever(
                    """INSERT INTO sd_selos (numero, obtido_em, caminho, tabela,
                           ato_id, referencia, atribuicao, usado_em)
                       VALUES (%s, %s, %s, 'pt_atos', %s, %s, 'PROTESTO', %s)""",
                    (f"PROTIT000000TESTEDEANTES{n:04d}", agora, caminho, ato,
                     ref, agora))
        AS._auditar(bd, acao="SELO_RESERVA_ESTORNADA", usuario="MARIO EXEMPLO DOS SANTOS",
                    usuario_id=None, agente="estorno da reserva do selo",
                    entidade="pt_atos", entidade_id=ato,
                    detalhes={"referencia": f"pt_atos:{ato}:{faltou}:1",
                              "forma": "ITEM_PAGO", "item_id": itens[faltou],
                              "valor_centavos": 5632, "unidades": 1,
                              "motivo": "o selador falhou ou recusou"},
                    agora=agora)
    return {"titulo_id": tid, "ato_id": ato, "itens": itens,
            "protocolo": p["numero"], "caminho": caminho}


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _avisos(resposta) -> list[str]:
    return [_html.unescape(m).strip() for m in re.findall(
        r'<div class="flash \w+" data-aviso>([^<]*)',
        resposta.get_data(as_text=True))]


def _emitir(s, c: dict, item: str, cliente=None, **campos):
    cliente = cliente or s["c"]
    ficha = cliente.get(f"/protesto/{c['titulo_id']}")
    token = _token(ficha.get_data(as_text=True))
    return cliente.post(
        f"/protesto/{c['titulo_id']}/atos/{c['ato_id']}/selo-que-faltou",
        data={"csrf_token": token, "item_id": str(c["itens"][item]), **campos},
        follow_redirects=True)


def _pedidos_de_selo(s) -> list[dict]:
    return [{"caminho": p["caminho"], "envelope": json.loads(p["corpo"])}
            for p in s["aparelho"].pedidos if p["caminho"].startswith("/selo/")]


def _retrato(s, c: dict) -> dict:
    """Tudo o que a emissão poderia mexer: o ato, o caixa, o item, a ligação,
    a cobertura, o razão e a marca de «aguardando cobertura»."""
    ato = c["ato_id"]
    return {
        "atos": _um(s, "SELECT count(*) AS n FROM pt_atos")["n"],
        "lancamentos": _um(s, "SELECT count(*) AS n FROM cx_lancamentos")["n"],
        "itens": _ler(s, """SELECT id, quantidade_usada, usado_em, usado_por_tabela,
                                   usado_por_ato_id, quitado
                              FROM cx_protocolo_atos WHERE id = ANY(%s) ORDER BY id""",
                      (list(c["itens"].values()),)),
        "ligacoes": _ler(s, """SELECT item_id, unidades, origem FROM cx_item_do_ato
                                WHERE tabela = 'pt_atos' AND ato_id = %s
                                ORDER BY item_id, origem""", (ato,)),
        "coberturas": _ler(s, """SELECT referencia, situacao, item_id
                                   FROM cx_selo_coberturas
                                  WHERE tabela = 'pt_atos' AND ato_id = %s
                                  ORDER BY referencia""", (ato,)),
        "selos": _ler(s, """SELECT numero, referencia FROM sd_selos
                             WHERE tabela = 'pt_atos' AND ato_id = %s
                             ORDER BY referencia""", (ato,)),
        "aguardando": _ler(s, """SELECT motivo FROM cx_selo_aguardando
                                  WHERE tabela = 'pt_atos' AND ato_id = %s""", (ato,)),
        "selo_do_ato": _um(s, "SELECT selo FROM pt_atos WHERE id = %s", (ato,))["selo"],
    }


def _pendencias(s, titulo_id: int) -> list[dict]:
    import protesto_selo_previo as PSELO
    with s["db"].connect() as con:
        return [p for p in PSELO.pendencias_do_selo(con, titulo_id=titulo_id)
                if p["especie"] == PSELO.ESPECIE_ITEM_SEM_SELO]


# ------------------------------------------------------------ emite o que falta


def test_a_lista_traz_so_o_item_pago_sem_selo(s):
    import protesto_selo_que_faltou as PSF
    c = _cenario(s)
    with s["db"].connect() as con:
        faltam = PSF.itens_sem_selo(con, c["ato_id"])
    assert [(x["codigo"], x["codigo_selo"], x["livres"]) for x in faltam] == [
        ("17.4.5", "17.4", 1)]
    [p] = _pendencias(s, c["titulo_id"])
    assert p["explicacao"].startswith("falta o selo do item 17.4.5 — emita na ficha")
    assert c["protocolo"] in p["explicacao"]
    assert p["ato_id"] == c["ato_id"] and p["item_id"] == c["itens"]["17.4.5"]
    # o contrato do roteiro: título, protocolo do título e a frase
    assert p["numero_titulo"] == "SF-0001"
    assert p["protocolo"] == PROTOCOLO_DO_TITULO
    # e a ficha oferece a ação ao oficial
    html = s["c"].get(f"/protesto/{c['titulo_id']}").get_data(as_text=True)
    assert "Emitir o selo que faltou" in html
    assert f"/protesto/{c['titulo_id']}/atos/{c['ato_id']}/selo-que-faltou" in html


def test_emite_o_que_falta_pelo_item_do_tribunal_sem_ato_nem_cobranca_nova(s):
    c = _cenario(s)
    antes = _retrato(s, c)
    r = _emitir(s, c, "17.4.5")
    avisos = _avisos(r)
    assert any(a.startswith("Selo ") and "emitido para o item 17.4.5" in a
               for a in avisos), avisos
    # UM pedido ao aparelho, pelo caminho do ato, com o ITEM e não a faixa
    [pedido] = _pedidos_de_selo(s)
    assert pedido["caminho"] == c["caminho"]
    assert pedido["envelope"]["ato"]["codigo"] == "17.4"
    assert pedido["envelope"]["selo"]["protocolo"] == PROTOCOLO_DO_TITULO
    depois = _retrato(s, c)
    # nenhum ato novo, nada cobrado de novo
    assert depois["atos"] == antes["atos"]
    assert depois["lancamentos"] == antes["lancamentos"]
    # o selo no razão, amarrado ao ato, com a referência do item do Tribunal
    novos = [x for x in depois["selos"] if x not in antes["selos"]]
    assert [x["referencia"] for x in novos] == [f"pt_atos:{c['ato_id']}:17.4:1"]
    assert depois["selo_do_ato"] == novos[0]["numero"]
    # a cobertura CONFIRMADA, com o item que pagou
    [cob] = [x for x in depois["coberturas"] if x not in antes["coberturas"]]
    assert cob["situacao"] == "CONFIRMADA"
    assert cob["item_id"] == c["itens"]["17.4.5"]
    # a unidade gasta, pela ligação do quadro
    item = next(x for x in depois["itens"] if x["id"] == c["itens"]["17.4.5"])
    assert item["quantidade_usada"] == 1
    assert {"item_id": c["itens"]["17.4.5"], "unidades": 1,
            "origem": "QUADRO"} in depois["ligacoes"]
    # a auditoria com o ato, o item e o selo
    linha = _um(s, """SELECT details FROM audit_logs
                       WHERE action = 'SELO_EMITIDO_DEPOIS' AND entity_id = %s""",
                (c["ato_id"],))
    detalhe = json.loads(linha["details"])
    assert detalhe["ato_id"] == c["ato_id"]
    assert detalhe["item_id"] == c["itens"]["17.4.5"]
    assert detalhe["codigo_do_item"] == "17.4.5" and detalhe["codigo_do_selo"] == "17.4"
    assert detalhe["selo"] == novos[0]["numero"]
    # e a obrigação some sozinha
    assert _pendencias(s, c["titulo_id"]) == []


def test_nao_repete_o_selo_que_ja_saiu(s):
    c = _cenario(s)
    _emitir(s, c, "17.4.5")
    assert len(_pedidos_de_selo(s)) == 1
    antes = _retrato(s, c)
    r = _emitir(s, c, "17.4.5")
    assert any("já tem selo confirmado" in a for a in _avisos(r)), _avisos(r)
    assert len(_pedidos_de_selo(s)) == 1          # o aparelho não foi chamado
    assert _retrato(s, c) == antes
    # nem o item que já tinha selo antes da ação
    r = _emitir(s, c, "17.2")
    assert any("já tem selo confirmado" in a for a in _avisos(r)), _avisos(r)
    assert len(_pedidos_de_selo(s)) == 1


# ------------------------------------------------------------ as travas


def test_robo_nao_emite(s):
    """O robô leva 403 na rota, e o domínio recusa de novo mesmo com o papel
    do oficial na mão."""
    import protesto_selo_que_faltou as PSF
    from conftest import cg_login
    c = _cenario(s)
    antes = _retrato(s, c)
    s["db"].create_user("robo_protesto", "Robo do Protesto", SENHA, "USER",
                        eh_robo=1)
    s["db"].set_settings({"modulo_protesto_alcance": "TODOS"})
    robo = s["app"].test_client()
    cg_login(robo, "robo_protesto", SENHA)
    token = _token(robo.get("/").get_data(as_text=True))
    r = robo.post(f"/protesto/{c['titulo_id']}/atos/{c['ato_id']}/selo-que-faltou",
                  data={"csrf_token": token, "item_id": str(c["itens"]["17.4.5"])})
    assert r.status_code == 403
    with pytest.raises(PSF.SeloQueFaltouError, match="Robô não emite"):
        with s["db"].transaction() as con:
            PSF.preparar(con, ato_id=c["ato_id"], item_id=c["itens"]["17.4.5"],
                         papel="ADMIN", eh_robo=True, usuario="Robo do Protesto",
                         agora=s["db"].now())
    assert _pedidos_de_selo(s) == []
    assert _retrato(s, c) == antes


def test_so_o_oficial_emite(s):
    """O substituto (MANAGER) e o balcão não emitem: 403 na rota, e o
    domínio recusa o papel."""
    import protesto_selo_que_faltou as PSF
    from conftest import cg_login
    c = _cenario(s)
    s["db"].create_user("beatriz", "BEATRIZ EXEMPLO", SENHA, "MANAGER")
    outro = s["app"].test_client()
    cg_login(outro, "beatriz", SENHA)
    token = _token(outro.get("/").get_data(as_text=True))
    r = outro.post(f"/protesto/{c['titulo_id']}/atos/{c['ato_id']}/selo-que-faltou",
                   data={"csrf_token": token, "item_id": str(c["itens"]["17.4.5"])})
    assert r.status_code == 403
    with pytest.raises(PSF.SeloQueFaltouError, match="Só o oficial"):
        with s["db"].transaction() as con:
            PSF.preparar(con, ato_id=c["ato_id"], item_id=c["itens"]["17.4.5"],
                         papel="MANAGER", eh_robo=False, usuario="BEATRIZ EXEMPLO",
                         agora=s["db"].now())
    assert _pedidos_de_selo(s) == []


def test_ato_cancelado_nao_se_sela(s):
    import protesto_selo_que_faltou as PSF
    c = _cenario(s, cancelado=True)
    antes = _retrato(s, c)
    with s["db"].connect() as con:
        assert PSF.itens_sem_selo(con, c["ato_id"]) == []
    assert _pendencias(s, c["titulo_id"]) == []
    r = _emitir(s, c, "17.4.5")
    assert any("ato cancelado não se sela" in a for a in _avisos(r)), _avisos(r)
    assert _pedidos_de_selo(s) == []
    assert _retrato(s, c) == antes


def test_item_que_nao_esta_pago_e_recusado(s):
    import protesto_selo_que_faltou as PSF
    c = _cenario(s, faltou_pago=False)
    antes = _retrato(s, c)
    with s["db"].connect() as con:
        assert PSF.itens_sem_selo(con, c["ato_id"]) == []
    r = _emitir(s, c, "17.4.5")
    assert any("não está pago" in a for a in _avisos(r)), _avisos(r)
    assert _pedidos_de_selo(s) == []
    assert _retrato(s, c) == antes


def test_a_falha_do_selador_nao_muda_nada_e_diz_o_motivo(s):
    c = _cenario(s)
    antes = _retrato(s, c)
    s["aparelho"].recusar_com = (400, {"message": "Não foi encontrado um ato "
                                                  "para o código informado"})
    r = _emitir(s, c, "17.4.5")
    avisos = _avisos(r)
    assert any("NÃO saiu, e nada mudou" in a and "Motivo:" in a
               for a in avisos), avisos
    assert _pedidos_de_selo(s)                    # o aparelho foi chamado
    assert _retrato(s, c) == antes
    assert _um(s, """SELECT count(*) AS n FROM audit_logs
                      WHERE action = 'SELO_EMITIDO_DEPOIS'""")["n"] == 0
    # e a obrigação continua, para a próxima tentativa
    assert len(_pendencias(s, c["titulo_id"])) == 1
    s["aparelho"].recusar_com = None
    r = _emitir(s, c, "17.4.5")
    assert any("emitido para o item 17.4.5" in a for a in _avisos(r)), _avisos(r)


def test_o_codigo_que_o_caminho_nunca_selou_pede_afirmacao(s):
    """O 4106 (cancelamento, 28/10/2026) ficou com o 17.4.5 pago sem selo, e o
    caminho do cancelamento não conhece o 17.4: a faixa vai como está, e pedir
    de novo é insistir — só com afirmação expressa, como no lançamento."""
    import protesto_selo_previo as PSELO
    c = _cenario(s, tipo="CANCELAMENTO")
    [p] = _pendencias(s, c["titulo_id"])
    assert p["serve"] is False and p["codigo_selo"] == "17.4.5"
    antes = _retrato(s, c)
    r = _emitir(s, c, "17.4.5")
    assert any("Afirmo" in a and "nada foi gravado" in a for a in _avisos(r)), \
        _avisos(r)
    assert _pedidos_de_selo(s) == []
    assert _retrato(s, c) == antes
    r = _emitir(s, c, "17.4.5", afirmo="1", afirmacao=AFIRMACAO_BOA)
    assert any("emitido para o item 17.4.5" in a for a in _avisos(r)), _avisos(r)
    detalhe = json.loads(_um(s, "SELECT detalhe_json FROM pt_atos WHERE id = %s",
                             (c["ato_id"],))["detalhe_json"])
    [gravada] = detalhe[PSELO.CHAVE_NO_DETALHE]
    assert gravada["regra"] == PSELO.REGRA_ITEM_FORA_DO_CAMINHO
    assert _um(s, """SELECT count(*) AS n FROM audit_logs
                      WHERE action = %s AND entity_id = %s""",
               (PSELO.ACAO_DA_AFIRMACAO, c["ato_id"]))["n"] == 1
