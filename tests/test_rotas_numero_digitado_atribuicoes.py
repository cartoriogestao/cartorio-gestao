"""O NÚMERO QUE A TELA MANDA NÃO DERRUBA A TELA — LD13, 21/10/2026.

O PEDIDO DO OFICIAL: «nenhuma pendência». A revisão do LD10 achou, no RI,
`int(...)` cru sobre o que o formulário ou o endereço trazem, e o LD13 fez a
mesma varredura nos outros módulos de tela. Este arquivo é a dos dois que
mais têm: `atribuicoes_web` (Protesto, RCPN, RCPJ/RTD, Livro 3, Notas) e
`rg_web` (o título do RCPJ/RTD).

O QUE CAÍA, E POR QUÊ
    «abc» num campo de número era `ValueError` e a tela de erro. O guarda
    `isdigit()` deixava passar o «²» (é dígito para o Python, e o `int()` o
    recusa) e o número de 5.000 dígitos (o Python recusa converter mais de
    4.300). O de 30 dígitos passava pelos dois e estourava no banco, quando
    ia gravado ou virava OFFSET de página. Vários desses pontos estão DEPOIS
    de o ato estar lavrado: a tela de erro escondia de quem lavrou que o ato
    tinha saído.

A RÉGUA É UMA SÓ (`seguranca_web.numero_digitado`): o texto ruim segue o
caminho que a tela já tinha para «não achei» ou «nada marcado», ou volta
com recado — nunca 500. Cada caso abaixo FALHAVA antes do conserto (a prova
está no relatório do LD13), menos três que ficam de régua porque a rota
mudou e já não caía: a lista do Protesto (que corta a página no total), a
busca da certidão do Protesto (só lê) e o assento dos gêmeos (o `except`
já pegava o texto).

Dados fictícios (LGPD): «MARIO EXEMPLO DOS SANTOS», «EMPRESA DE EXEMPLO
LTDA», CPF 000.000.001-91, CNS 000000.
"""
from __future__ import annotations

import hashlib
import itertools
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from bd_nativo import banco  # noqa: E402

#: O número que CABE no `bigint` (18 dígitos) e ainda assim derrubava: a
#: página, que o OFFSET multiplica, e o que se grava em coluna `integer`.
GRANDE = "9" * 18

#: O que a tela não devia mandar e manda: texto, o «²» que passa pelo
#: `isdigit()`, o número grande, o que não cabe no banco e o que o Python
#: não converte.
RUINS = ("abc", "²", GRANDE, "9" * 30, "9" * 5000)

NOME = "MARIO EXEMPLO DOS SANTOS"     # o ADMIN de `cg_casa_logada`
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO/MA",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA", "ri_cns": "000000",
      "serventia_titular": NOME,
      "serventia_titulo": "Tabelião e Oficial de Registro"}
EXTENSO = "vinte e um de outubro de dois mil e vinte e seis"
#: Cada preparo é um título, uma folha, um registro NOVO: o número ruim que
#: passa (depois do conserto) lavra o ato, e o seguinte não pode achar o
#: título já registrado — pararia antes do ponto que se quer medir.
_SEQUENCIA = itertools.count(1)
TITULO_DO_PROTESTO = {
    "especie": "DMI", "numero_titulo": "LD13/1",
    "data_emissao": "2025-12-01", "data_vencimento": "2025-12-20",
    "valor": "100.00", "saldo": "100.00", "praca_protesto": "CIDADE EXEMPLO",
    "tipo_moeda": "1", "tipo_protesto": "C", "motivo_protesto": "1",
    "cedente": {"nome": "CREDOR DE EXEMPLO", "documento": "00000000000000",
                "cidade": "Cidade Exemplo", "uf": "MA"},
    "devedores": [{"nome": "DEVEDOR DE EXEMPLO", "CPF": "00000000191",
                   "enderecos": [{"endereco": "Rua Exemplo, 10", "bairro": "Centro",
                                  "cidade": "Cidade Exemplo", "uf": "MA"}]}]}


# ============================================================ a bancada


@pytest.fixture()
def balcao(cg_casa_logada):
    """O ADMIN logado, o Protesto ligado e o cadastro do selo da casa."""
    db = cg_casa_logada["db"]
    db.set_settings({"modulo_protesto_ligado": "1", "ri_cns": "000000",
                     "selo_tabela_custas_em": "2026-01-01"})
    with cg_casa_logada["c"].session_transaction() as sessao:
        token = sessao["csrf_token"]
    return {**cg_casa_logada, "token": token}


def _agora(db) -> str:
    return db.now()


def _caixa_aberto(b) -> dict:
    """O caixa do operador aberto: sem ele a cobrança para antes do número."""
    with b["db"].transaction() as con:
        banco(con).escrever(
            """INSERT INTO cx_caixas(data, operador_nome, aberto_em, situacao)
               VALUES (%s,%s,%s,'ABERTO') ON CONFLICT DO NOTHING""",
            (_agora(b["db"])[:10], NOME, _agora(b["db"])))
    return {}


def _selo_a_mao() -> str:
    """Um selo digitado desta casa (CNS 000000), diferente a cada ato: o mesmo
    número em dois atos é recusado («um selo serve a um ato só»)."""
    return f"AVESVD000000LD13SELO{next(_SEQUENCIA):08d}"


def _registro_rtd(b) -> dict:
    """Um registro do RTD com número — a ficha de onde as prévias saem."""
    import rg_registro as RG
    with b["db"].transaction() as con:
        r = RG.abrir_registro(con, serie="TD_B", sv=SV, agora=_agora(b["db"]),
                              data_extenso=EXTENSO,
                              natureza="Notificação extrajudicial",
                              requerente_nome="EMPRESA DE EXEMPLO LTDA",
                              teor="Texto de exemplo da notificação.")
    return {"registro_id": r["registro_id"], "selo": _selo_a_mao()}


def _registro_com_caixa(b) -> dict:
    return {**_caixa_aberto(b), **_registro_rtd(b)}


def _servico_do_rtd(b) -> int:
    """Um item da tabela do RTD com preço: o que a tela marca para cobrar, e
    de que o selo do ato sai quando não há protocolo."""
    with b["db"].transaction() as con:
        bd = banco(con)
        bd.escrever("""INSERT INTO cx_vigencias(codigo, descricao, vigente, inicio, fim)
                       VALUES (814, 'LD13', 1, '2020-01-01', NULL)
                       ON CONFLICT DO NOTHING""")
        bd.escrever("""INSERT INTO cx_servicos(codigo, codigo_tj, descricao)
                       VALUES (9914, '15.1', 'Registro de exemplo')
                       ON CONFLICT DO NOTHING""")
        bd.escrever("""INSERT INTO cx_servico_valores(servico, vigencia, emolumentos,
                           ferc, femp, fadep, ferrfis, total)
                       VALUES (9914,814,'10,00','0,00','0,00','0,00','0,00','10,00')
                       ON CONFLICT DO NOTHING""")
    return 9914


def _registro_com_servico(b) -> dict:
    return {**_registro_com_caixa(b), "servico": _servico_do_rtd(b)}


def _titulo_qualificado(b) -> dict:
    """Um título do RTD recebido e qualificado: pronto para o registro."""
    import rg_titulo as TIT
    with b["db"].transaction() as con:
        feito = TIT.receber(con, atribuicao=TIT.RTD, sv=SV, agora=_agora(b["db"]),
                            data_extenso=EXTENSO,
                            data_apresentacao=_agora(b["db"])[:10],
                            apresentante="EMPRESA DE EXEMPLO LTDA",
                            apresentante_documento="00000010000127",
                            natureza="Notificação extrajudicial", usuario=NOME)
        TIT.qualificar(con, feito["titulo_id"], resultado=TIT.POSITIVA,
                       agora=_agora(b["db"]), usuario=NOME)
    return {"titulo_id": feito["titulo_id"]}


def _titulo_qualificado_com_caixa(b) -> dict:
    return {**_caixa_aberto(b), **_titulo_qualificado(b)}


def _titulo_qualificado_com_servico(b) -> dict:
    return {**_titulo_qualificado_com_caixa(b), "servico": _servico_do_rtd(b)}


def _titulo_registrado(b) -> dict:
    """O título do RTD já com o registro de número — o da prévia do teor."""
    t = _titulo_qualificado(b)
    r = _registro_rtd(b)
    with b["db"].transaction() as con:
        banco(con).escrever("UPDATE rg_titulos SET registro_id=%s WHERE id=%s",
                            (r["registro_id"], t["titulo_id"]))
    return {**t, **r}


def _protesto_da_central(b) -> dict:
    """Título da central (CRA): o regime é o a posteriori — o ato antes do
    desfecho fica DEVENDO, e é por `_diferir_se_pedido` que passa."""
    import protesto as PT
    with b["db"].transaction() as con:
        tid = PT.cadastrar_titulo(con, dict(TITULO_DO_PROTESTO), origem="CRA",
                                  origem_chave=f"LD13:{next(_SEQUENCIA)}",
                                  agora=_agora(b["db"]))
    return {"titulo_id": tid}


def _protesto_com_devido(b) -> dict:
    """O título apontado com um item devido, a tabela e o caixa aberto: o
    pagamento cobra o devido por `_cobrar_os_diferidos`."""
    import protesto as PT
    import protesto_posteriori as POST
    agora = _agora(b["db"])
    with b["db"].transaction() as con:
        bd = banco(con)
        bd.escrever("""INSERT INTO cx_vigencias(codigo, descricao, vigente, inicio, fim)
                       VALUES (813, 'LD13', 1, '2020-01-01', NULL)
                       ON CONFLICT DO NOTHING""")
        bd.escrever("""INSERT INTO cx_servicos(codigo, codigo_tj, descricao)
                       VALUES (9913, '17.5.1', 'Item de exemplo')
                       ON CONFLICT DO NOTHING""")
        bd.escrever("""INSERT INTO cx_servico_valores(servico, vigencia, emolumentos,
                           ferc, femp, fadep, ferrfis, total)
                       VALUES (9913,813,'10,00','0,00','0,00','0,00','0,00','10,00')
                       ON CONFLICT DO NOTHING""")
        tid = PT.cadastrar_titulo(con, dict(TITULO_DO_PROTESTO), origem="CRA",
                                  origem_chave=f"LD13:{next(_SEQUENCIA)}", agora=agora)
        PT.lancar_apontamento(con, tid, sv=SV, agora=agora, data_extenso=EXTENSO)
        [ap] = bd.ler("SELECT id FROM pt_atos WHERE titulo_id=%s AND tipo='APONTAMENTO'",
                      (tid,))
        POST.diferir(con, titulo_id=tid, ato_id=ap["id"], tipo_ato="APONTAMENTO",
                     itens=[{"servico": 9913}], data_do_ato=agora[:10], agora=agora)
    return {**_caixa_aberto(b), "titulo_id": tid}


def _lote_de_avisos(b) -> dict:
    """Um PDF de avisos à espera do registro, com o nome que o sistema dá."""
    import pymupdf
    doc = pymupdf.open()
    doc.new_page()
    conteudo = doc.tobytes()
    sha = hashlib.sha256(conteudo).hexdigest()
    pasta = (Path(b["app"].extensions["archive_root"]()) / "Protesto"
             / "Intimacoes" / "lotes")
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{sha}.pdf").write_bytes(conteudo)
    return {"sha": sha}


def _registro_do_livro3(b) -> dict:
    """Uma cédula registrada no Livro 3 — a ficha onde se averba."""
    import ra_registro as RA
    with b["db"].transaction() as con:
        r = RA.registrar(con, natureza="CEDULA_CREDITO_RURAL", agora=_agora(b["db"]),
                         titulo_tipo="Cédula Rural Pignoratícia de exemplo")
    return {"registro_id": r["registro_id"]}


def _folha_de_seguranca(b) -> dict:
    """A folha em branco que a lavratura do RCPN gasta."""
    codigo = f"99913{next(_SEQUENCIA):02d}"
    with b["db"].transaction() as con:
        bd = banco(con)
        rid = bd.escrever(
            """INSERT INTO pp_remessas(fornecedor, codigo_de, codigo_ate, quantas,
                   recebida_em)
               VALUES ('TESTE', %s, %s, 1, '2026-08-25T00:00:00')
               RETURNING id""", (codigo, codigo))[0]["id"]
        bd.escrever("""INSERT INTO pp_folhas(codigo, remessa_id, situacao, criada_em)
                       VALUES (%s, %s, 'EM BRANCO', '2026-08-25T00:00:00')""",
                    (codigo, rid))
    return {"folha": codigo, "selo": _selo_a_mao()}


def _dois_nascimentos(b) -> dict:
    """Dois assentos de nascimento lavrados pela tela: os gêmeos."""
    ids = []
    for nome in ("ANA DE EXEMPLO", "JOANA DE EXEMPLO"):
        ctx = _folha_de_seguranca(b)
        r = _pede(b, "POST", "/rcpn/novo",
                  _monta({**NASCIMENTO, "nome": nome, "pessoa_nome": nome}, ctx, ""))
        assert r.status_code == 302 and "/rcpn/" in r.headers["Location"], (
            "o nascimento de preparo não foi lavrado")
        ids.append(int(r.headers["Location"].rstrip("/").rsplit("/", 1)[1]))
    return {"assento_id": ids[0], "irmao_id": ids[1]}


PREPAROS = {
    "nada": lambda b: {"selo": _selo_a_mao()},
    "caixa": _caixa_aberto,
    "registro": _registro_rtd,
    "registro_e_caixa": _registro_com_caixa,
    "titulo_qualificado": _titulo_qualificado,
    "titulo_qualificado_e_caixa": _titulo_qualificado_com_caixa,
    "titulo_registrado": _titulo_registrado,
    "registro_e_servico": _registro_com_servico,
    "titulo_qualificado_e_servico": _titulo_qualificado_com_servico,
    "protesto_da_central": _protesto_da_central,
    "protesto_com_devido": _protesto_com_devido,
    "lote": _lote_de_avisos,
    "folha": _folha_de_seguranca,
    "livro3": _registro_do_livro3,
    "gemeos": _dois_nascimentos,
}

CERTIDAO_DO_PROTESTO = {"nome": "FULANO DE EXEMPLO", "documento": "00000000191",
                        "requerente": "FULANO DE EXEMPLO", "finalidade": "Exemplo"}
NASCIMENTO = {"especie": "NASCIMENTO", "nome": "ANA DE EXEMPLO",
              "pessoa_nome": "ANA DE EXEMPLO", "pessoa_sexo": "F",
              "data_fato": "2026-08-20", "local_fato_nome": "Hospital de Exemplo",
              "ibge_local": "1", "filiacao1_nome": "MARIA DE EXEMPLO",
              "filiacao2_nome": "IGNORADO", "declarante_nome": "MARIA DE EXEMPLO",
              "paternidade_tipo": "NEGATIVO",   # pai ignorado: termo (23/10/2026)
              "acao": "lavrar", "folha_seguranca": "{folha}",
              "selo": "{selo}"}


def _caso(id_, preparo, metodo, rota, campos=None):
    return pytest.param(preparo, metodo, rota, campos or {}, id=id_)


# Cada caso: o preparo (refeito a cada número ruim: o que passa lavra o ato,
# e o seguinte não pode achar o título já registrado), o método, o endereço e
# os campos, com `{x}` onde o número ruim entra.
CASOS_DE_ATRIBUICOES = [
    # --- as listas: a página vira OFFSET
    _caso("rcpn-lista-pagina", "nada", "GET", "/rcpn?pagina={x}"),
    _caso("rcpj-rtd-lista-pagina", "nada", "GET", "/rcpj-rtd?pagina={x}"),
    _caso("livro3-lista-pagina", "nada", "GET", "/livro3?pagina={x}"),
    _caso("rcpj-rtd-atos-pagina", "nada", "GET", "/rcpj-rtd/atos?pagina={x}"),
    _caso("protesto-lista-pagina", "nada", "GET", "/protesto?pagina={x}"),
    # --- a certidão do Protesto: o período, a cobrança e o selo
    _caso("protesto-certidao-busca-anos", "nada", "GET",
          "/protesto/certidoes?nome=FULANO+DE+EXEMPLO&anos={x}"),
    _caso("protesto-certidao-emitir-anos", "nada", "POST", "/protesto/certidoes/emitir",
          {**CERTIDAO_DO_PROTESTO, "anos": "{x}"}),
    _caso("protesto-certidao-cobrar", "caixa", "POST", "/protesto/certidoes/emitir",
          {**CERTIDAO_DO_PROTESTO, "cobrar": "{x}"}),
    _caso("protesto-certidao-cobrar-protocolo", "caixa", "POST",
          "/protesto/certidoes/emitir",
          {**CERTIDAO_DO_PROTESTO, "cobrar": "9999", "protocolo_id": "{x}"}),
    _caso("protesto-certidao-item-a-cobrar", "caixa", "POST", "/protesto/certidoes/emitir",
          {**CERTIDAO_DO_PROTESTO, "cobrar_protocolo_item": "{x}"}),
    _caso("protesto-certidao-protocolo-do-selo", "nada", "POST",
          "/protesto/certidoes/emitir", {**CERTIDAO_DO_PROTESTO, "protocolo_id": "{x}"}),
    _caso("protesto-certidao-item-do-selo", "nada", "POST", "/protesto/certidoes/emitir",
          {**CERTIDAO_DO_PROTESTO, "protocolo_id": "1", "protocolo_item_id": "{x}"}),
    # --- o ato do título a posteriori: o que fica devido e o que se cobra
    _caso("protesto-diferir-cobrar", "protesto_da_central", "POST",
          "/protesto/{titulo_id}/lancar", {"ato": "APONTAMENTO", "cobrar": "{x}"}),
    _caso("protesto-diferir-item", "protesto_da_central", "POST",
          "/protesto/{titulo_id}/lancar",
          {"ato": "APONTAMENTO", "cobrar_protocolo_item": "{x}"}),
    _caso("protesto-diferir-protocolo", "protesto_da_central", "POST",
          "/protesto/{titulo_id}/lancar",
          {"ato": "APONTAMENTO", "cobrar_protocolo_item": "1", "protocolo_id": "{x}"}),
    _caso("protesto-cobrar-diferidos-protocolo", "protesto_com_devido", "POST",
          "/protesto/{titulo_id}/lancar",
          {"ato": "PAGAMENTO", "forma_pagamento": "PIX", "cobrar_diferidos": "1",
           "protocolo_id": "{x}"}),
    # --- o lote de avisos e a lista a protestar
    _caso("protesto-lote-folhas", "lote", "GET", "/protesto/avisos/lote/{sha}/folhas?p={x}"),
    _caso("protesto-lote-registrar", "lote", "POST", "/protesto/avisos/lote/{sha}/registrar",
          {"aviso_id": "{x}"}),
    _caso("protesto-a-protestar-lavrar", "nada", "POST", "/protesto/a-protestar/lavrar",
          {"titulo_id": "{x}"}),
    # --- as Notas
    _caso("notas-certidoes-ato", "nada", "GET", "/notas/certidoes?ato_id={x}"),
    _caso("notas-certidao-emitir-ato", "nada", "POST", "/notas/certidoes/emitir",
          {"ato_id": "{x}", "nome": "FULANO DE EXEMPLO"}),
    _caso("notas-certidao-emitir-protocolo", "nada", "POST", "/notas/certidoes/emitir",
          {"nome": "FULANO DE EXEMPLO", "documento": "00000000191",
           "protocolo_id": "{x}"}),
    # --- o RCPN
    _caso("rcpn-novo-habilitacao-e-leitura", "folha", "POST", "/rcpn/novo",
          {**NASCIMENTO, "habilitacao_id": "{x}", "leitura_id": "{x}"}),
    _caso("rcpn-cpf", "nada", "POST", "/rcpn/cpf",
          {"assento_id": "{x}", "cpf": "000.000.001-91"}),
    _caso("rcpn-obitos-por-perguntar", "nada", "POST", "/rcpn/obitos-por-perguntar",
          {"assento_id": "{x}"}),
    _caso("rcpn-crc", "nada", "POST", "/rcpn/crc", {"assento": "{x}"}),
    _caso("rcpn-crc-arquivo", "nada", "POST", "/rcpn/crc/arquivo", {"assento": "{x}"}),
    _caso("rcpn-crc-enviar", "nada", "POST", "/rcpn/crc/enviar", {"assento": "{x}"}),
    _caso("rcpn-crc-marcar-enviado", "nada", "POST", "/rcpn/crc/marcar-enviado",
          {"assento": "{x}"}),
    _caso("rcpn-formulario-assento", "nada", "GET", "/rcpn/formulario/nascimento?assento={x}"),
    _caso("rcpn-gemeos-assento", "nada", "POST", "/rcpn/gemeos",
          {"assento_id": "{x}", "irmao_id": "{x}", "ordem": "1"}),
    _caso("rcpn-gemeos-ordem", "gemeos", "POST", "/rcpn/gemeos",
          {"assento_id": "{assento_id}", "irmao_id": "{irmao_id}", "ordem": "{x}"}),
    _caso("rcpn-registro-tardio", "nada", "GET",
          "/rcpn/registro-tardio?conferir=1&idade=30&testemunhas={x}"),
    _caso("rcpn-ibge", "nada", "GET", "/rcpn/ibge?ano={x}&trimestre={x}"),
    # --- o RCPJ/RTD pela ficha do registro
    _caso("rcpj-rtd-ficha-protocolo", "registro", "GET",
          "/rcpj-rtd/{registro_id}?protocolo_id={x}"),
    _caso("rcpj-rtd-teor-previa", "registro", "GET",
          "/rcpj-rtd/{registro_id}/teor/previa?protocolo_id={x}&protocolo_item_id={x}"
          "&anexo_id={x}"),
    _caso("rcpj-rtd-certidao-previa", "registro", "GET",
          "/rcpj-rtd/{registro_id}/certidao/previa?ato_id={x}&anexo_id={x}"),
    _caso("rcpj-rtd-lancar-cobrar", "registro_e_caixa", "POST",
          "/rcpj-rtd/{registro_id}/lancar", {"tipo": "AVERBACAO", "cobrar": "{x}"}),
    _caso("rcpj-rtd-lancar-protocolo", "registro_e_caixa", "POST",
          "/rcpj-rtd/{registro_id}/lancar", {"tipo": "AVERBACAO", "protocolo_id": "{x}"}),
    _caso("rcpj-rtd-lancar-item", "registro_e_caixa", "POST",
          "/rcpj-rtd/{registro_id}/lancar",
          {"tipo": "AVERBACAO", "cobrar_protocolo_item": "{x}"}),
    _caso("rcpj-rtd-lancar-item-do-selo", "registro_e_caixa", "POST",
          "/rcpj-rtd/{registro_id}/lancar",
          {"tipo": "AVERBACAO", "protocolo_id": "1", "protocolo_item_id": "{x}"}),
    _caso("rcpj-rtd-lancar-protocolo-do-envelope", "registro_e_servico", "POST",
          "/rcpj-rtd/{registro_id}/lancar",
          {"tipo": "AVERBACAO", "cobrar": "{servico}", "protocolo_id": "{x}"}),
    _caso("rcpj-rtd-lancar-anexo", "registro", "POST", "/rcpj-rtd/{registro_id}/lancar",
          {"tipo": "AVERBACAO", "selo": "{selo}", "anexo_id": "{x}"}),
    _caso("certidao-rcpj-rtd-atos", "registro", "POST",
          "/atribuicoes/certidoes/RCPJ_RTD/{registro_id}",
          {"ato_id": "{x}", "requerente": "FULANO DE EXEMPLO"}),
    _caso("certidao-negativa-rtd-protocolo", "nada", "POST",
          "/atribuicoes/certidoes/RCPJ_RTD/negativa",
          {"protocolo_id": "{x}", "nome_pesquisado": "FULANO DE EXEMPLO"}),
    _caso("certidao-negativa-rtd-item", "nada", "POST",
          "/atribuicoes/certidoes/RCPJ_RTD/negativa",
          {"protocolo_id": "1", "atribuicao_da_busca": "RTD",
           "nome_pesquisado": "FULANO DE EXEMPLO", "documento_pesquisado": "00000000191",
           "requerente": "FULANO DE EXEMPLO", "protocolo_item_id": "{x}"}),
    _caso("livro3-novo-folhas-do-arquivamento", "nada", "POST", "/livro3/novo",
          {"natureza": "PACTO_ANTENUPCIAL", "selo": "{selo}",
           "gerar_arquivamento": "1", "folhas_arquivamento": "{x}"}),
    _caso("livro3-lancar-minuta", "livro3", "POST", "/livro3/{registro_id}/lancar",
          {"tipo": "AVERBACAO", "teor": "Averbação de exemplo.", "minuta_id": "{x}"}),
    _caso("livro3-lancar-folhas-do-arquivamento", "livro3", "POST",
          "/livro3/{registro_id}/lancar",
          {"tipo": "AVERBACAO", "teor": "Averbação de exemplo.",
           "gerar_arquivamento": "1", "folhas_arquivamento": "{x}"}),
]


def _monta(modelo, ctx: dict, x: str):
    if isinstance(modelo, dict):
        return {k: _monta(v, ctx, x) for k, v in modelo.items()}
    return str(modelo).replace("{x}", x).format(**ctx) if "{" in str(modelo) else modelo


def _pede(b, metodo: str, rota: str, campos: dict):
    c = b["c"]
    if metodo == "GET":
        return c.get(rota)
    return c.post(rota, data={"csrf_token": b["token"], **campos})


def _nenhuma_cai(b, preparo, metodo, rota, campos) -> None:
    caidas = []
    for x in RUINS:
        ctx = PREPAROS[preparo](b)
        r = _pede(b, metodo, _monta(rota, ctx, x), _monta(campos, ctx, x))
        if r.status_code >= 500:
            caidas.append(f"{x[:12]}…({len(x)}): {r.status_code}")
    assert not caidas, f"a tela caiu com: {caidas}"


@pytest.mark.parametrize("preparo,metodo,rota,campos", CASOS_DE_ATRIBUICOES)
def test_o_numero_ruim_nas_telas_das_atribuicoes_vira_recado_e_nao_tela_de_erro(
        balcao, preparo, metodo, rota, campos):
    """Texto, «²», 18, 30 e 5.000 dígitos em cada campo de número das telas
    de `atribuicoes_web`: a rota segue o caminho de «não achei/nada marcado»
    ou devolve recado — nunca a tela de erro (500). O de 18 dígitos cabe no
    `bigint` e ainda derrubava a página (OFFSET) e a gravação em coluna
    `integer`."""
    _nenhuma_cai(balcao, preparo, metodo, rota, campos)


REGISTRO_DO_TITULO = {"serie": "TD_B", "teor": "Notificação de exemplo."}

CASOS_DO_TITULO = [
    _caso("titulo-registrar-cobrar", "titulo_qualificado_e_caixa", "POST",
          "/rcpj-rtd/titulo/{titulo_id}/registrar",
          {**REGISTRO_DO_TITULO, "cobrar": "{x}"}),
    _caso("titulo-registrar-cobrar-protocolo", "titulo_qualificado_e_caixa", "POST",
          "/rcpj-rtd/titulo/{titulo_id}/registrar",
          {**REGISTRO_DO_TITULO, "cobrar": "9999", "protocolo_id": "{x}"}),
    _caso("titulo-registrar-protocolo-do-selo", "titulo_qualificado", "POST",
          "/rcpj-rtd/titulo/{titulo_id}/registrar",
          {**REGISTRO_DO_TITULO, "protocolo_id": "{x}"}),
    _caso("titulo-registrar-item-do-selo", "titulo_qualificado", "POST",
          "/rcpj-rtd/titulo/{titulo_id}/registrar",
          {**REGISTRO_DO_TITULO, "protocolo_id": "1", "protocolo_item_id": "{x}"}),
    _caso("titulo-registrar-protocolo-do-envelope", "titulo_qualificado_e_servico", "POST",
          "/rcpj-rtd/titulo/{titulo_id}/registrar",
          {**REGISTRO_DO_TITULO, "cobrar": "{servico}", "protocolo_id": "{x}"}),
    _caso("titulo-teor-previa-anexo", "titulo_registrado", "GET",
          "/rcpj-rtd/titulo/{titulo_id}/teor/previa?anexo_id={x}"),
]


@pytest.mark.parametrize("preparo,metodo,rota,campos", CASOS_DO_TITULO)
def test_o_numero_ruim_nas_telas_do_titulo_do_rcpj_rtd_vira_recado_e_nao_tela_de_erro(
        balcao, preparo, metodo, rota, campos):
    """O mesmo de cima nas telas de `rg_web` (o título do RCPJ/RTD): o
    registro do título cobra, sela e liga os itens do protocolo pelo que a
    tela marcou, e a prévia do teor escolhe os anexos — o número ruim em
    qualquer um deles vira «nada marcado», e nunca a tela de erro."""
    _nenhuma_cai(balcao, preparo, metodo, rota, campos)
