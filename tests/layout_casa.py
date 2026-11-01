"""A casa de ensaio: uma serventia fictícia com uma linha de cada coisa que tem tela.

POR QUE EXISTE
    Das 548 rotas de leitura, 220 pedem um número no endereço (`/rcpn/<assento_id>`). Sem uma
    linha no banco, elas respondem 404, e o teste passaria sem nunca ter visto a ficha. E é nas
    fichas que moram as fases, as abas e os formulários que mais importam.

COMO SE MONTA
    A base é a carga de demonstração do sandbox (`tools/carga_de_demonstracao.py`), que já é
    mantida: serventia, livros, folhas, um nascimento, um óbito, uma procuração, uma certidão
    de protesto e uma matrícula. Em cima dela, cada atribuição tem o seu `layout_semente_*.py`,
    e cada um diz, com `casa.pagina(...)`, quais endereços passaram a existir.

    O caminho preferido é o da própria tela (`casa.postar`), porque ele já prova o fluxo. Quando
    o fluxo exige o que o teste não tem, como um selo de verdade, vale a função de domínio, e só
    por último `casa.inserir`, que preenche o que a tabela exige e deixa o resto vazio.

ROTA NOVA COM NÚMERO
    `test_layout_semente` fica vermelho até ela ter semente, ou até estar em `SEM_SEMENTE` do
    módulo da área, com o motivo escrito. É a mesma regra de `navegacao.PAI`: tela nova não entra
    calada.

O CONGELAMENTO
    Depois de semeada, a casa é congelada: uma cópia das tabelas em outro esquema. Quem manda
    formulário devolve o banco ao congelado antes de cada envio, e assim um «apagar» não leva
    consigo o que o formulário seguinte precisa.
"""
from __future__ import annotations

import importlib
import os
import sys
from datetime import date
from pathlib import Path

import pytest
from flask import url_for

RAIZ = Path(__file__).resolve().parent.parent
for _pasta in (RAIZ, RAIZ / "tests"):
    if str(_pasta) not in sys.path:
        sys.path.insert(0, str(_pasta))

import banco_pg  # noqa: E402
import caixa_aviso as CA  # noqa: E402
import layout_ensaio as E  # noqa: E402
from bd_nativo import banco  # noqa: E402

#: Cada rota com número pertence a uma área pelo começo do endereço. A primeira que casa leva.
AREAS = {
    "ri": ("/registro-imoveis", "/ri/", "/usucapiao", "/andamento/prenotacao", "/revisao-previa/ri", "/livro3"),
    "civil": ("/rcpn",),
    "notas": ("/notas", "/revisao-previa/", "/agente-minutas"),
    "protesto": ("/protesto",),
    "rcpj": ("/rcpj-rtd", "/apostila", "/atribuicoes"),
    "gestao": ("/",),
}


def area_da_regra(regra: str) -> str:
    return next(nome for nome, prefixos in AREAS.items() if any(regra.startswith(p) for p in prefixos))


def _agora() -> str:
    return date.today().isoformat()


class Casa:
    def __init__(self, app, boot, pasta_temporaria: Path):
        self.app = app
        self.boot = boot
        self.db = app.extensions["db"]
        self.pasta_temporaria = pasta_temporaria
        self.hoje = _agora()
        self.paginas: list[tuple[str, str]] = []     # (endpoint, endereço)
        self.ids: dict[str, int] = {}                # o que uma semente quer contar à outra
        self._sessoes: dict[tuple[str, str], str] = {}
        self._congelada = None

    # ---------------------------------------------------------------- o banco

    def con(self):
        return self.db.connect()

    def transacao(self):
        return self.db.transaction()

    def sql(self, comando: str, parametros=()) -> list[dict]:
        """Um comando só, com `%s`. Grava, e devolve as linhas se houver `RETURNING`."""
        with self.db.transaction() as con:
            return banco(con).escrever(comando, parametros)

    def ler(self, comando: str, parametros=()) -> list[dict]:
        with self.db.connect() as con:
            return banco(con).ler(comando, parametros)

    def um(self, comando: str, parametros=()):
        with self.db.connect() as con:
            return banco(con).um(comando, parametros)

    def inserir(self, tabela: str, **campos):
        """Uma linha, com o que a tabela exige e o resto vazio. Devolve o id, se houver.

        Chave estrangeira e `CHECK` não se adivinham: passe em `campos` o que a tabela recusar.
        """
        with self.db.transaction() as con:
            bd = banco(con)
            colunas = bd.ler(
                "SELECT column_name, data_type, is_nullable, column_default, is_identity "
                "FROM information_schema.columns WHERE table_schema = current_schema() "
                "AND table_name = %s ORDER BY ordinal_position", (tabela,))
            assert colunas, f"a tabela {tabela} não existe"
            linha = dict(campos)
            for c in colunas:
                exigida = (c["is_nullable"] == "NO" and c["column_default"] is None
                           and c["is_identity"] != "YES")
                if exigida and c["column_name"] not in linha:
                    linha[c["column_name"]] = _valor_para(c["column_name"], c["data_type"], self.hoje)
            nomes = ", ".join(f'"{n}"' for n in linha)
            marcas = ", ".join(["%s"] * len(linha))
            tem_id = any(c["column_name"] == "id" for c in colunas)
            sql = f'INSERT INTO "{tabela}" ({nomes}) VALUES ({marcas})' + (" RETURNING id" if tem_id else "")
            voltou = bd.escrever(sql, tuple(linha.values()))
            return int(voltou[0]["id"]) if tem_id and voltou else None

    def congelar(self) -> None:
        import conftest as C
        semente = banco_pg.schema_do_caminho(self.boot["data_dir"] / "_casa_congelada.sqlite3")
        C._pg_semear(self.boot["db_path"], self.boot["data_dir"] / "_casa_congelada.sqlite3")
        esquema = banco_pg.schema_do_caminho(self.boot["db_path"])
        with C._pg_cru() as pg, pg.cursor() as c:
            tabelas = C._pg_tabelas(c, esquema)
            c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s", (semente,))
            cheias = {r[0] for r in c.fetchall()}
            contagem = {}
            for t in tabelas:
                c.execute(f'SELECT count(*) FROM "{esquema}"."{t}"')
                contagem[t] = c.fetchone()[0]
            c.execute("SELECT txid_current() % 4294967296")
            marco = c.fetchone()[0]
        self._congelada = {"semente": semente, "esquema": esquema, "cheias": cheias, "contagem": contagem, "marco": marco}

    def restaurar(self) -> None:
        """Devolve o banco ao congelado. Só refaz a tabela que mudou, e por isso custa pouco.

        `conftest._pg_restaurar` refaz todas as que têm linha, e aqui ele rodaria a cada formulário.
        Tabela mudada é a que tem outra contagem, ou uma linha gravada depois do marco (`xmin`).
        """
        import conftest as C
        q = self._congelada
        esquema, semente = q["esquema"], q["semente"]
        with C._pg_cru() as pg, pg.cursor() as c:
            c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name=%s "
                      "AND state LIKE 'idle in transaction%%' AND pid<>pg_backend_pid()", (esquema[:60],))
            perguntas = [f"""SELECT '{t}' WHERE (SELECT count(*) FROM "{esquema}"."{t}") <> {n}
                             OR EXISTS (SELECT 1 FROM "{esquema}"."{t}" WHERE xmin::text::bigint >= {q["marco"]})"""
                         for t, n in q["contagem"].items()]
            c.execute(" UNION ALL ".join(perguntas))
            mudadas = [r[0] for r in c.fetchall()]
            if mudadas:
                c.execute("SET session_replication_role = replica")
                for t in mudadas:
                    c.execute(f'DELETE FROM "{esquema}"."{t}"')
                    if t in q["cheias"]:
                        c.execute(f'INSERT INTO "{esquema}"."{t}" SELECT * FROM "{semente}"."{t}"')
                c.execute(
                    "SELECT k.relname, a.attname FROM pg_attribute a JOIN pg_class k ON k.oid=a.attrelid "
                    "JOIN pg_namespace n ON n.oid=k.relnamespace WHERE n.nspname=%s AND "
                    "a.attidentity IN ('a','d') AND k.relname = ANY(%s)", (esquema, mudadas))
                for t, coluna in c.fetchall():
                    c.execute(f"""SELECT setval(pg_get_serial_sequence('"{esquema}"."{t}"', '{coluna}'),
                                  COALESCE((SELECT MAX("{coluna}") FROM "{esquema}"."{t}"), 0) + 1, false)""")
                c.execute("SET session_replication_role = origin")
            c.execute("SELECT txid_current() % 4294967296")
            q["marco"] = c.fetchone()[0]

    # ---------------------------------------------------------------- as pessoas

    def preparar_sessao(self, papel: str, layout: str) -> None:
        """Uma pessoa por papel e por moldura: a escolha do layout é da pessoa."""
        if (papel, layout) in self._sessoes:
            return
        # O ADMIN DE ENSAIO É O TITULAR: despesas, balanço e carnê-leão recusam os outros ADMIN, e a
        # varredura passaria sem ver essas telas. Quem cobra a recusa é `test_layout_todas_as_telas`.
        nome = self.db.get_setting("serventia_titular", "") if papel == "ADMIN" else ""
        c = E.entrar(self.app, f"ensaio_{papel.lower()}_{layout}", papel, layout, nome)
        self._sessoes[(papel, layout)] = c.get_cookie("session").value

    def cliente(self, papel: str = "ADMIN", layout: str = "novo"):
        """Um cliente novo com a sessão daquela pessoa. O formulário de sair não a tira dos outros."""
        self.preparar_sessao(papel, layout)
        c = self.app.test_client()
        c.set_cookie("session", self._sessoes[(papel, layout)])
        return c

    def token(self, c) -> str:
        with c.session_transaction() as sessao:
            return sessao["csrf_token"]

    def postar(self, endereco: str, /, papel: str = "ADMIN", _cliente=None, **campos):
        """Manda um formulário como a tela manda, com o token. Devolve a resposta, sem seguir."""
        c = _cliente or self.cliente(papel, "novo")
        return c.post(endereco, data={"csrf_token": self.token(c), **campos})

    # ---------------------------------------------------------------- os endereços

    def pagina(self, endpoint: str, _consulta: dict | None = None, **args) -> str:
        """Anota um endereço que passou a existir. A varredura abre todos."""
        with self.app.test_request_context():
            endereco = url_for(endpoint, **args, **(_consulta or {}))
        if (endpoint, endereco) not in self.paginas:
            self.paginas.append((endpoint, endereco))
        return endereco

    def enderecos(self, areas=None) -> list[tuple[str, str]]:
        """O que se abre: toda rota de leitura sem número, mais o que as sementes anotaram."""
        fora = {"static"}
        saida = [(r.endpoint, r.rule) for r in E.regras_de_leitura(self.app)
                 if not r.arguments and r.endpoint not in fora
                 and (areas is None or area_da_regra(r.rule) in areas)]
        saida += [p for p in self.paginas if areas is None or _area_do_endereco(p[1]) in areas]
        return list(dict.fromkeys(saida))


def _area_do_endereco(endereco: str) -> str:
    return area_da_regra(endereco)


def _valor_para(nome: str, tipo: str, hoje: str):
    if tipo in ("integer", "bigint", "smallint"):
        return 1
    if tipo in ("numeric", "double precision", "real"):
        return 0
    if tipo == "boolean":
        return False
    if tipo in ("date",):
        return hoje
    if tipo.startswith("timestamp"):
        return f"{hoje}T10:00:00"
    if nome.endswith(("_em", "_data")) or nome.startswith("data") or nome in ("em", "criado", "quando"):
        return f"{hoje}T10:00:00"
    return "Ensaio"


# ------------------------------------------------------------------- as áreas

MODULOS_DAS_AREAS = {nome: f"layout_semente_{nome}" for nome in AREAS}


def modulo_da_area(nome: str):
    return importlib.import_module(MODULOS_DAS_AREAS[nome])


def areas_pedidas() -> list[str]:
    """`CG_LAYOUT_AREAS=ri,civil` semeia e abre só essas: é como se trabalha numa área de cada vez."""
    pedidas = [a.strip() for a in os.environ.get("CG_LAYOUT_AREAS", "").split(",") if a.strip()]
    return pedidas or list(AREAS)


def sem_semente() -> dict[str, str]:
    """Rotas com número que não têm como abrir aqui, cada uma com o motivo escrito."""
    fora: dict[str, str] = {}
    for nome in areas_pedidas():
        fora.update(getattr(modulo_da_area(nome), "SEM_SEMENTE", {}))
    return fora


def semear_base(casa: Casa) -> None:
    """O que toda área usa: a carga do sandbox, a sessão longa e o caixa aberto."""
    from tools import carga_de_demonstracao as CARGA
    from tools import iniciar_sandbox as KIT

    pasta = Path(casa.db.db_path).resolve().parent
    (pasta / KIT.MARCA).write_text("Pasta de teste do layout novo.\n", encoding="utf-8")
    casa.db.set_settings({"session_timeout_minutes": "100000", "session_absolute_hours": "100000",
                          "selo_trava_caixa": "DESLIGADA"})
    relatorio = CARGA.carregar(casa.db, casa.app)
    assert not relatorio["pulados"], f"a carga de demonstração pulou passos: {relatorio['pulados']}"
    # A mesma pessoa que o sandbox usa para lavrar: o caixa aberto é de quem atende.
    agora = f"{casa.hoje}T08:00:00"
    casa.preparar_sessao("ADMIN", "novo")
    admin = casa.um("SELECT id, full_name FROM users WHERE username=%s", ("ensaio_admin_novo",))
    casa.ids["admin"] = int(admin["id"])
    casa.ids["caixa"] = casa.inserir("cx_caixas", data=casa.hoje, operador_nome=admin["full_name"],
                                     saldo_inicial="0,00", aberto_em=agora, aberto_por=admin["id"],
                                     situacao="ABERTO")


def montar_casa(app, boot, pasta_temporaria: Path, areas=None) -> Casa:
    E.conferir_que_e_banco_de_teste(app.extensions["db"])
    E.ligar_trava(pasta_temporaria, boot["data_dir"])
    casa = Casa(app, boot, pasta_temporaria)
    semear_base(casa)
    # `CG_LAYOUT_SO_A_BASE=1`: só a carga do sandbox, para quem mexe na varredura e não nas sementes.
    if not os.environ.get("CG_LAYOUT_SO_A_BASE"):
        for nome in (areas if areas is not None else areas_pedidas()):
            modulo_da_area(nome).semear(casa)
    return casa


@pytest.fixture(scope="module")
def casa(cg_app, _cg_boot, tmp_path_factory):
    """A casa de ensaio do módulo de teste, com a trava ligada do começo ao fim."""
    # A CASA NÃO PODE DEPENDER DA HORA EM QUE RODA. O caixa dela fica aberto, e depois do fim do expediente o aviso de
    # fechar o caixa cobre toda tela: os testes de navegador só passavam de manhã. A chave é de cobrança, e o banco recusa
    # quem a grava por fora. Aqui nada se grava: muda só o padrão, neste processo, e ele volta no fim.
    fim_de_fabrica = CA.FIM_PADRAO
    CA.FIM_PADRAO = "23:59"
    c = montar_casa(cg_app, _cg_boot, tmp_path_factory.getbasetemp())
    for papel in E.PAPEIS:
        for layout in E.LAYOUTS:
            c.preparar_sessao(papel, layout)
    c.congelar()
    yield c
    E.desligar_trava()
    CA.FIM_PADRAO = fim_de_fabrica
