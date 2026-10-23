"""O protocolo do balcão que os testes de selo montam (LX16, 19/10/2026).

Desde o LX16, selo PAGO só sai com o ato ligado a um item de protocolo geral
e com o pagamento registrado (`ato_selado.cobrir_o_selo`). Os testes que
selam passam a montar o que o balcão monta — protocolo, item, pagamento — em
vez de desligar a regra: dado de teste, e não exceção na trava.

Dois jeitos, como na casa:
    - `cobrir_o_ato`: a tela do ato ligou o ato ao item (teste de unidade, em
      que o ato já existe antes do selo);
    - `atender_protocolo_pago`: o escrevente marcou o protocolo que está
      atendendo (teste de tela, em que o ato nasce e sela no mesmo pedido).
"""
from __future__ import annotations

from bd_nativo import banco

AGORA = "2026-10-19T09:00:00"


def preparar_caixa(con) -> None:
    """Garante as tabelas do caixa e da trava num banco de unidade montado à mão."""
    import ato_selado as AS
    from caixa_schema import init_caixa_schema
    bd = banco(con)
    if not bd.tem_tabela("cx_protocolos"):
        # `cx_protocolos` aponta para `users` e para a prenotação e a
        # matrícula do RI: o PostgreSQL cobra a FK, e o banco da casa cria as
        # três antes. Aqui basta o esqueleto (o padrão de `test_custas`).
        for tabela in ("users", "ri_protocolos", "ri_matriculas"):
            bd.escrever(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY)")
        init_caixa_schema(con)
    AS.init_trava_do_selo_schema(con)


def _protocolo_pago(con, *, codigos, quantidade: int, atribuicao: str | None) -> dict:
    import caixa_protocolo as CXP
    preparar_caixa(con)
    bd = banco(con)
    p = CXP.abrir(bd, data_abertura=AGORA[:10], agora=AGORA,
                  atribuicao=atribuicao, interessado="CLIENTE DE EXEMPLO")
    itens = []
    for codigo in codigos:
        itens.append(int(bd.escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato,
                   quantidade, valor_total, quitado, quitado_em, quitado_por)
               VALUES (%s,%s,%s,%s,'10,00',1,%s,'CAIXA DE TESTE') RETURNING id""",
            (p["protocolo_id"], f"Item {codigo}", str(codigo), int(quantidade),
             AGORA))[0]["id"]))
    return p | {"itens": itens}


def cobrir_o_ato(con, *, tabela: str, ato_id: int, codigo: str = "16.1",
                 atribuicao: str | None = None) -> dict:
    """Protocolo pago com o item já gasto por este ato. ESCREVE (não confirma)."""
    import caixa_protocolo as CXP
    p = _protocolo_pago(con, codigos=[codigo], quantidade=1, atribuicao=atribuicao)
    CXP.consumir_item(con, p["itens"][0], ato_id=int(ato_id), tabela=tabela,
                      agora=AGORA)
    return p


def atender_protocolo_pago(con, *, usuario: str, codigos, quantidade: int = 99,
                           atribuicao: str | None = None) -> dict:
    """Protocolo pago, com um item por código, em atendimento por `usuario`."""
    import caixa_protocolo as CXP
    p = _protocolo_pago(con, codigos=list(codigos), quantidade=quantidade,
                        atribuicao=atribuicao)
    CXP.atender(con, usuario=usuario, protocolo=p["numero"], agora=AGORA)
    return p


#: Data do protocolo da bancada: fora do mês de qualquer teste, para a
#: numeração `AAAA.MM.N` dos protocolos que o próprio teste abre não mudar.
DATA_DA_BANCADA = "2000-01-03"
INTERESSADO_DA_BANCADA = "CLIENTE DA BANCADA"


def codigos_da_casa(con) -> list[str]:
    """Todo item da tabela que esta casa sela: o catálogo e os caminhos medidos."""
    import atribuicoes as ATR
    import ato_selado as AS
    codigos = {c for itens in ATR.ITENS_DE_CUSTA_POR_CAMINHO.values() for c in itens}
    codigos |= set(AS.MOTIVO_DA_ISENCAO)
    bd = banco(con)
    if bd.tem_tabela("cx_servicos"):
        codigos |= {r["c"] for r in bd.ler(
            "SELECT DISTINCT btrim(codigo_tj) AS c FROM cx_servicos "
            "WHERE coalesce(btrim(codigo_tj), '') <> '' ORDER BY 1")}
    return sorted(codigos)


def atender_tudo_pago(con) -> dict | None:
    """O protocolo pago da bancada: um item por código, em atendimento por todos.

    É o balcão de um teste que sela sem falar de caixa: o cliente pagou tudo
    antes. A trava roda de verdade — acha o item pelo código, gasta a
    unidade —; só o dinheiro já está lá. Quem são «todos»: os usuários
    cadastrados e os nomes da casa que o selo usa quando a sessão é robô.
    """
    import caixa_protocolo as CXP
    preparar_caixa(con)
    bd = banco(con)
    # Chamado a cada selo (a bancada liga isto em `cobrir_o_selo`): o mesmo
    # protocolo serve a todos, e o que o aparelho recusou volta com a
    # transação dele — por isso se procura, em vez de lembrar.
    p = bd.um("""SELECT id AS protocolo_id, numero FROM cx_protocolos
                  WHERE interessado = %s ORDER BY id LIMIT 1""",
              (INTERESSADO_DA_BANCADA,))
    if not p:
        p = CXP.abrir(bd, data_abertura=DATA_DA_BANCADA, agora=AGORA,
                      atribuicao=None, interessado=INTERESSADO_DA_BANCADA)
        bd.escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato,
                   quantidade, valor_total, quitado, quitado_em, quitado_por)
               SELECT %s, 'Item da bancada ' || c, c, 9999, '10,00', 1, %s, 'BANCADA'
                 FROM unnest(%s::text[]) AS c""",
            (p["protocolo_id"], AGORA, codigos_da_casa(bd)))
    nomes = set()
    if bd.tem_coluna("users", "full_name"):
        for u in bd.ler("SELECT full_name, username FROM users ORDER BY id"):
            nomes |= {u["full_name"], u["username"]}
    if bd.tem_tabela("settings"):
        for r in bd.ler("""SELECT value FROM settings WHERE key IN
                ('ri_substituta','serventia_oficial','oficial_nome','ri_registrador')
                ORDER BY key"""):
            nomes.add(r["value"])
    for nome in sorted(n for n in nomes if str(n or "").strip()):
        # Quem já atende um protocolo — o que o próprio teste montou — fica
        # com o dele: é ele que o teste mede.
        if not CXP.em_atendimento(bd, nome):
            CXP.atender(bd, usuario=nome, protocolo=p["numero"], agora=AGORA)
    return p
