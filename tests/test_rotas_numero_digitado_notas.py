"""O NÚMERO QUE A TELA MANDA, NAS NOTAS — LD13, 21/10/2026 («nenhuma pendência»).

A revisão do LD10 achou, no Registro de Imóveis, `int(...)` direto sobre o
que a tela manda; o LD13 fez a mesma varredura nos outros módulos de tela.
Em `notas_web` cada caso abaixo era a tela de erro (500), por um destes três
caminhos:

  - «abc» no `int(request...)` sem guarda nenhuma;
  - «²» e 5.000 dígitos onde o guarda era `isdigit()`: o «²» é dígito para o
    `isdigit()` e não é para o `int()`, e o número de 5.000 dígitos passa
    pelos dois guardas e o Python recusa a conversão (mais de 4.300 dígitos);
  - 30 dígitos onde o número vai ao banco: o OFFSET da página e a coluna
    `bigint` gravada («bigint out of range»), inclusive dentro do `try` que só
    apanhava o `ValueError`.

Agora tudo passa pela régua da casa (`seguranca_web.numero_digitado`), e o
texto que não é número segue o caminho que a tela já tinha para «nada
marcado» ou «não achei» — ou volta com recado. Nenhum caso pode dar 500.

A quantidade de folhas do arquivamento confere mais que o 500: com 30 dígitos
ela passava pela conversão, ia ao selo e só estourava no UPDATE de
`folhas_arquivamento`, DEPOIS de o selo sair. Ela tem de parar antes, com o
recado de sempre («informe a quantidade de folhas»).

Os dados são só os fictícios da casa.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from bd_nativo import banco  # noqa: E402

# Os textos que não são número que o banco guarde.
RUINS = {"abc": "abc", "sobrescrito": "²", "30-digitos": "9" * 30,
         "5000-digitos": "9" * 5000}

#: (rota, método, caminho, campos). `{X}` é o texto ruim; `{ato}` e `{rej}` são
#: as linhas que o teste cria (uma escritura selada e uma quarentena).
ROTAS = [
    ("reconhecer-cartao", "POST", "/notas/reconhecimento",
     {"acao": "reconhecer", "cartao_id": "{X}"}),
    ("pagina-dos-reconhecimentos", "GET", "/notas/reconhecimentos", {"pagina": "{X}"}),
    ("pagina-dos-atos", "GET", "/notas/atos", {"pagina": "{X}"}),
    ("livro-dos-atos", "GET", "/notas/atos", {"livro_id": "{X}"}),
    ("termo-dos-atos", "GET", "/notas/atos", {"termo": "{X}"}),
    ("busca-dos-atos", "GET", "/notas/atos", {"busca": "{X}"}),
    ("folha-dos-atos", "GET", "/notas/atos", {"livro": "1", "folha": "{X}"}),
    ("parte-pelo-cartao", "POST", "/notas/atos/{ato}",
     {"acao": "parte_cartao", "cartao_id": "{X}"}),
    ("remover-parte", "POST", "/notas/atos/{ato}",
     {"acao": "remover_parte", "parte_id": "{X}"}),
    ("folhas-da-autenticacao", "POST", "/notas/autenticacao",
     {"acao": "autenticar", "folhas": "{X}"}),
    ("folhas-do-arquivamento", "POST", "/notas/atos/{ato}/selar-arquivamento",
     {"folhas_arquivamento": "{X}"}),
    ("natureza-ato", "POST", "/notas/escrituras/natureza", {"ato": "{X}|cep|1"}),
    ("natureza-valor", "POST", "/notas/escrituras/natureza", {"ato": "{ato}|cesdi|{X}"}),
    ("natureza-sem-campo", "POST", "/notas/escrituras/natureza", {"ato": "{X}"}),
    ("valor-declarado", "POST", "/notas/escrituras/{ato}/valor", {"valor": "{X}"}),
    ("quarentena-ato", "POST", "/notas/escrituras/quarentena/{rej}",
     {"ato_id": "{X}", "parte": "1|OUTORGANTE"}),
    ("quarentena-parte", "POST", "/notas/escrituras/quarentena/{rej}",
     {"ato_id": "{ato}", "parte": "{X}|OUTORGANTE"}),
    ("quarentena-parte-sem-qualificacao", "POST", "/notas/escrituras/quarentena/{rej}",
     {"ato_id": "{ato}", "parte": "{X}"}),
    ("remessas-ano", "GET", "/notas/remessas", {"ano": "{X}"}),
    ("remessas-mes", "GET", "/notas/remessas", {"mes": "{X}"}),
    ("remessas-quinzena", "GET", "/notas/remessas", {"quinzena": "{X}"}),
    ("pendencias-ano", "GET", "/notas/remessas/CEP/pendencias", {"ano": "{X}"}),
    ("pendencias-quinzena", "GET", "/notas/remessas/CEP/pendencias", {"quinzena": "{X}"}),
    ("enviar-api", "POST", "/notas/remessas/enviar-api",
     {"ano": "{X}", "mes": "10", "quinzena": "1"}),
    ("gerar-remessa", "POST", "/notas/remessas/CEP/gerar",
     {"ano": "2026", "mes": "{X}", "quinzena": "1"}),
    ("sinal-publico", "POST", "/notas/sinais/reconhecimento",
     {"acao": "reconhecer", "sinal_id": "{X}"}),
]

#: O que a rota tem de dizer, além de não cair.
RECADO = {"folhas-do-arquivamento": "informe a quantidade de folhas"}


def _semear(db) -> dict:
    """Uma escritura selada (sem arquivamento) e uma linha da quarentena."""
    with db.transaction() as con:
        bd = banco(con)
        ato = bd.escrever(
            """INSERT INTO nt_atos (tipo, situacao, origem, data, criado_em, selo)
               VALUES ('ESCRITURA', 'LAVRADO', 'MANUAL', '2026-10-20',
                       '2026-10-20T10:00', 'SELO DE TESTE 0001')
               RETURNING id""")[0]["id"]
        rej = bd.escrever(
            """INSERT INTO nt_rejeitados (tabela, chave, motivo, conteudo, criado_em)
               VALUES ('nt_ato_partes', 'P-1', 'ato ambíguo', %s, '2026-10-20T10:00')
               RETURNING id""", (json.dumps({"livro": "1", "folha": "1"}),))[0]["id"]
    return {"ato": str(ato), "rej": str(rej)}


def _preencher(valor: str, ruim: str, linhas: dict) -> str:
    return (valor.replace("{X}", ruim).replace("{ato}", linhas["ato"])
            .replace("{rej}", linhas["rej"]))


@pytest.mark.parametrize("ruim", list(RUINS.values()), ids=list(RUINS))
@pytest.mark.parametrize("rota,metodo,caminho,campos", ROTAS, ids=[r[0] for r in ROTAS])
def test_o_numero_que_nao_cabe_no_banco_nao_derruba_tela_nenhuma_das_notas(
        cg_casa_logada, rota, metodo, caminho, campos, ruim):
    """«abc», «²», 30 e 5.000 dígitos em cada campo numérico das Notas: a tela
    responde (recado, volta para a lista ou a quinzena de hoje) e nunca cai."""
    casa = cg_casa_logada
    linhas = _semear(casa["db"])
    c = casa["c"]
    caminho = _preencher(caminho, ruim, linhas)
    dados = {k: _preencher(v, ruim, linhas) for k, v in campos.items()}
    if metodo == "GET":
        r = c.get(caminho, query_string=dados)
    else:
        with c.session_transaction() as s:
            dados["csrf_token"] = s["csrf_token"]
        r = c.post(caminho, data=dados)
    assert r.status_code in (200, 302), (
        f"{rota} com {len(ruim)} caractere(s) deu {r.status_code}")
    if rota in RECADO:
        with c.session_transaction() as s:
            recados = " ".join(texto for _, texto in s.get("_flashes", []))
        assert RECADO[rota] in recados.lower(), recados
