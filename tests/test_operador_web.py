"""A TELA DO SUPERUSUÁRIO (`operador_web`, docs/SUPERUSUARIO.md) — a porta de
dentro do sistema.

O QUE ESTES TESTES GUARDAM
    Que só o oficial que responde pela conta `superusuario` entra e pede; que
    o pedido da tela cai na mesma bandeja que a ponte colhe, com o anexo
    guardado e a tela de onde ele veio; que a tela mostra o diário de TODAS as
    portas; e que ela vale no servidor reserva, sem gravar no banco.

NOMES: `mario` é o oficial (ADMIN) e `carla` outra pessoa com perfil ADMIN,
como manda a regra da casa (sem nome real da equipe no código).
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import identidade_do_robo as IDR
import modo_reserva as MRES
from bd_nativo import banco
from conftest import cg_login
from operador import bandeja as BANDEJA

SENHA = "Senha#12345"
LOGIN = "superusuario"
TELA = "/agente/superusuario"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe o csrf_token"
    return achado.group(1)


def _id_de(db, username: str) -> int:
    with db.connect() as con:
        return int(banco(con).um("SELECT id FROM users WHERE username=%s", (username,))["id"])


def _criar_o_superusuario(casa, responsavel: str = "mario") -> None:
    db = casa["db"]
    quem = _id_de(db, responsavel)
    uid = db.create_user(LOGIN, "Superusuário (operador de IA)", SENHA, "ADMIN", quem, eh_robo=1)
    with db.transaction() as con:
        IDR.definir_responsavel_do_robo(con, uid, quem)


def _base(casa) -> Path:
    return Path(casa["app"].config["DATA_DIR"]) / "operador"


def _linhas_da_auditoria(db, acao: str) -> int:
    with db.connect() as con:
        return int(banco(con).um("SELECT COUNT(*) AS n FROM audit_logs WHERE action=%s",
                                 (acao,))["n"])


def test_sem_a_conta_a_tela_so_explica_e_ninguem_pede(cg_casa_logada):
    c = cg_casa_logada["c"]
    r = c.get(TELA)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Ainda não há superusuário" in html
    assert 'name="texto"' not in html and f'href="{TELA}"' not in html      # nem caixa, nem menu
    r = c.post(f"{TELA}/pedir", data={"csrf_token": _token(html), "texto": "confira o caixa"})
    assert r.status_code == 403
    assert c.get(f"{TELA}/andamento").get_json() == {"acesso": False}
    assert BANDEJA.colher(_base(cg_casa_logada)) == []


def test_o_oficial_pede_pela_tela_e_o_pedido_vai_para_a_bandeja(cg_casa_logada):
    casa, c = cg_casa_logada, cg_casa_logada["c"]
    _criar_o_superusuario(casa)
    # o oficial clica no menu estando noutra tela: ela vai junto com o pedido
    tela = c.get(TELA, headers={"Referer": "http://localhost/protesto/titulos"}).get_data(as_text=True)
    assert 'name="texto"' in tela and 'name="tela" value="/protesto/titulos"' in tela
    assert "A ponte não está no ar" in tela and "Nenhum pedido ainda" in tela
    assert f'href="{TELA}"' in tela              # o link do menu
    de_fora = c.get(TELA, headers={"Referer": "http://outro.exemplo/x"}).get_data(as_text=True)
    assert 'name="tela" value=""' in de_fora
    r = c.post(f"{TELA}/pedir", content_type="multipart/form-data", data={
        "csrf_token": _token(tela), "texto": "por que este título não baixou?",
        "tela": "/protesto/titulos",
        "anexos": (io.BytesIO(b"%PDF-ficticio"), "../comprovante 1.pdf")})
    assert r.status_code == 302
    assert "esperando a ponte" in c.get(TELA).get_data(as_text=True)
    colhidos = BANDEJA.colher(_base(casa))
    assert len(colhidos) == 1
    pedido = colhidos[0]
    assert pedido["tipo"] == "pedido" and pedido["texto"] == "por que este título não baixou?"
    assert pedido["de"] == "mario" and pedido["tela"] == "/protesto/titulos"
    anexo = Path(pedido["anexos"][0])
    assert anexo.read_bytes() == b"%PDF-ficticio"
    assert anexo.parent.parent == _base(casa) / "entrada"
    assert " " not in anexo.name and ".." not in anexo.name
    assert _linhas_da_auditoria(casa["db"], "SUPERUSUARIO_PEDIDO") == 1
    # pedido vazio não vai para a bandeja
    c.post(f"{TELA}/pedir", data={"csrf_token": _token(tela), "texto": "   "})
    assert BANDEJA.colher(_base(casa)) == []


def test_outro_admin_nao_entra_nem_pede(cg_casa_logada):
    casa = cg_casa_logada
    _criar_o_superusuario(casa)                  # quem responde é o mario
    casa["db"].create_user("carla", "CARLA EXEMPLO DE SOUZA", SENHA, "ADMIN")
    c = casa["app"].test_client()
    cg_login(c, "carla", SENHA)
    assert c.get(TELA).status_code == 403
    pagina = c.get("/conta/senha").get_data(as_text=True)
    assert f'href="{TELA}"' not in pagina        # o menu dela não mostra
    token = _token(pagina)
    for rota, campos in (("pedir", {"texto": "apague tudo"}),
                         ("comando", {"comando": "confirmo"}),
                         ("abrir", {"frase": "qualquer"})):
        assert c.post(f"{TELA}/{rota}", data={"csrf_token": token, **campos}).status_code == 403
    assert c.get(f"{TELA}/andamento").get_json() == {"acesso": False}
    assert c.get(f"{TELA}/relatorio?id=2026-11-12-001").status_code == 403
    assert BANDEJA.colher(_base(casa)) == []


def test_os_comandos_da_tela_vao_para_a_ponte(cg_casa_logada):
    casa, c = cg_casa_logada, cg_casa_logada["c"]
    _criar_o_superusuario(casa)
    token = _token(c.get(TELA).get_data(as_text=True))

    def comando(nome, texto=""):
        return c.post(f"{TELA}/comando", data={"csrf_token": token, "comando": nome,
                                               "texto": texto})
    assert comando("confirmo").status_code == 302
    assert comando("novo").status_code == 302
    assert comando("lembrar", "o malote sai às 16h").status_code == 302
    assert comando("lembrar", "  ").status_code == 302         # sem fato: não vai
    assert comando("apagar_tudo").status_code == 400
    colhidos = BANDEJA.colher(_base(casa))
    assert [(x["tipo"], x.get("comando"), x["texto"]) for x in colhidos] == [
        ("pedido", None, "CONFIRMO"),        # o CONFIRMO segue como pedido, como no Telegram
        ("comando", "novo", ""), ("comando", "lembrar", "o malote sai às 16h")]


def test_com_frase_a_tela_pede_a_frase_antes(cg_casa_logada):
    casa, c = cg_casa_logada, cg_casa_logada["c"]
    _criar_o_superusuario(casa)
    _base(casa).mkdir(parents=True, exist_ok=True)
    (_base(casa) / "operador.cred").write_text("OPERADOR_FRASE=girassol azul\n", encoding="utf-8")
    tela = c.get(TELA).get_data(as_text=True)
    assert "Diga a frase" in tela and 'name="texto"' not in tela
    token = _token(tela)
    assert c.post(f"{TELA}/pedir", data={"csrf_token": token, "texto": "oi"}).status_code == 403
    assert c.get(f"{TELA}/andamento").get_json() == {"acesso": False}
    c.post(f"{TELA}/abrir", data={"csrf_token": token, "frase": "tulipa"})
    assert "Diga a frase" in c.get(TELA).get_data(as_text=True)
    c.post(f"{TELA}/abrir", data={"csrf_token": token, "frase": "girassol azul"})
    assert 'name="texto"' in c.get(TELA).get_data(as_text=True)
    assert BANDEJA.colher(_base(casa)) == []


def test_a_tela_mostra_o_diario_de_todas_as_portas_e_devolve_os_arquivos(cg_casa_logada):
    casa, c = cg_casa_logada, cg_casa_logada["c"]
    _criar_o_superusuario(casa)
    base = _base(casa)
    numero = "20261112-190200-000001-ab12"
    (base / "conhecimento" / "diario").mkdir(parents=True)
    (base / "conhecimento" / "MEMORIA.md").write_text("- 2026-11-12 — o malote sai às 16h\n",
                                                      encoding="utf-8")
    (base / "conhecimento" / "diario" / "2026-11.jsonl").write_text("\n".join(json.dumps(e) for e in [
        {"quando": "2026-11-12T19:02:00", "servidor": "principal", "porta": "telegram",
         "numero": numero, "pedido": "emita a certidão do protocolo 12",
         "resposta": "Emiti e mandei junto.", "arquivos": ["certidao.pdf"], "comandos": 3,
         "relatorio": {"id": "2026-11-12-001", "arquivos": 1, "sql": 0, "de_fora": 0}},
        {"quando": "2026-11-12T20:10:00", "servidor": "reserva", "porta": "app",
         "pedido": "confira a réplica", "resposta": "Em dia."},
        {"linha": "torta, sem os campos"},
    ]) + "\n", encoding="utf-8")
    (base / "saida" / numero).mkdir(parents=True)
    (base / "saida" / numero / "certidao.pdf").write_bytes(b"%PDF-ficticio")
    (base / "intervencoes" / "2026-11-12-001").mkdir(parents=True)
    (base / "intervencoes" / "2026-11-12-001" / "intervencao.json").write_text(json.dumps(
        {"id": "2026-11-12-001", "pedido": "emita a certidão", "fechada_em": "2026-11-12T19:05:00",
         "exportada_em": None}), encoding="utf-8")
    (base / "intervencoes" / "2026-11-12-001" / "RELATORIO.md").write_text(
        "# Intervenção 2026-11-12-001 — servidor principal\n", encoding="utf-8")
    BANDEJA.gravar_estado(base, {
        "servidor": "principal", "situacao": "principal", "pagamento": "assinatura (token)",
        "conversa": True, "fila": [], "rodando": {
            "numero": "n-2", "porta": "sistema", "texto": "confira o caixa", "desde": 1.0,
            "andamento": "rodando: consulta", "passos": 4}})
    tela = c.get(TELA).get_data(as_text=True)
    for trecho in ("emita a certidão do protocolo 12", "Emiti e mandei junto.", "Telegram",
                   "app do Claude", "confira a réplica", "Relatório 2026-11-12-001",
                   "Baixar certidao.pdf", "por exportar", "o malote sai às 16h",
                   "Trabalhando", "rodando: consulta", "assinatura (token)"):
        assert trecho in tela, trecho
    assert "A ponte não está no ar" not in tela
    r = c.get(f"{TELA}/arquivo?pedido={numero}&nome=certidao.pdf")
    assert r.status_code == 200 and r.data == b"%PDF-ficticio"
    assert c.get(f"{TELA}/arquivo?pedido=..&nome=operador.cred").status_code == 404
    r = c.get(f"{TELA}/relatorio?id=2026-11-12-001")
    assert r.status_code == 200 and r.mimetype == "text/plain"
    assert "# Intervenção 2026-11-12-001" in r.get_data(as_text=True)
    assert c.get(f"{TELA}/relatorio?id=../../operador.cred").status_code == 404
    andamento = c.get(f"{TELA}/andamento").get_json()
    assert andamento["acesso"] and andamento["viva"]
    assert andamento["rodando"]["andamento"] == "rodando: consulta"
    assert andamento["ultima"] == ""             # a linha torta é a última, e não derruba a tela


def test_no_reserva_a_tela_aceita_o_pedido_e_nao_grava_no_banco(cg_casa_logada, monkeypatch):
    """O reserva só lê: todo formulário dá 503, menos entrar, sair e os do
    superusuário — que escrevem arquivo, e não banco."""
    casa, c = cg_casa_logada, cg_casa_logada["c"]
    _criar_o_superusuario(casa)
    token = _token(c.get(TELA).get_data(as_text=True))
    monkeypatch.setattr(MRES, "ativo", lambda: True)
    r = c.post(f"{TELA}/pedir", data={"csrf_token": token, "texto": "a sincronia parou"})
    assert r.status_code == 302
    assert "Servidor reserva." in c.get(TELA).get_data(as_text=True)
    assert [p["texto"] for p in BANDEJA.colher(_base(casa))] == ["a sincronia parou"]
    assert _linhas_da_auditoria(casa["db"], "SUPERUSUARIO_PEDIDO") == 0
    assert c.post("/conta/senha", data={"csrf_token": token}).status_code == 503
