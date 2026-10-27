"""O CONVITE DA PESQUISA CHEGA AO CLIENTE (26/10/2026) — `satisfacao_envio`.

O QUE SE PROVA AQUI
    - sem o portal (PR #29) ou sem o e-mail da automação (PR #11) instalados, a
      rodada NÃO quebra: o convite fica na fila com o motivo escrito;
    - o ciclo inteiro: o convite vai à VPS SEM dado pessoal (só a chave, a
      atribuição e as datas), o e-mail sai com o link da VPS e a validade e sem
      número de protocolo, CPF ou nome; a resposta dada na VPS volta e é gravada
      pela mesma `satisfacao.registrar`, com o atendente e a chave do protocolo;
    - o código do link não fica em banco nenhum (só o hash);
    - o teto por rodada e o limite de tentativas;
    - o WhatsApp fica na fila com a frase da Meta; o convite vencido não sai;
    - a resposta de quem já avaliou na página da casa não dobra;
    - cada envio e cada resposta gravada vão à auditoria com `agente` e
      `a_mando_de`, sem o e-mail do cliente;
    - o endereço da VPS é configuração do oficial, só https;
    - (com a central da automação instalada) o processo está no catálogo.

AS OUTRAS PONTAS SÃO FALSAS DE PROPÓSITO
    O e-mail da automação e o portal entram por `sys.modules` (o
    `monkeypatch` os devolve no fim): neste ramo eles ainda não existem, e na
    máquina do merge o falso toma o lugar do verdadeiro só durante o teste.
    A VPS é o programa de verdade (`vps/pesquisa/pesquisa_vps.py`), chamado
    sem rede — o transporte falso entrega o pedido direto a ele.

Equipe fictícia (mario, beatriz). Nada de dado real. Testes escritos para a
máquina do merge (26/10/2026: nada de pytest nesta máquina, por ordem do
oficial).
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import types
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import satisfacao as SAT                     # noqa: E402
import satisfacao_envio as ENVIO             # noqa: E402
from bd_nativo import banco                  # noqa: E402

TOKEN = "t" * 48
URL = "https://pesquisa.exemplo.invalid/pesquisa"
EMAIL_FICTICIO = "cliente@exemplo.invalid"
TELEFONE_FICTICIO = "(99) 90000-0000"
SENHA = "Senha#12345"


# ------------------------------------------------------------------ as pontas falsas


class _Smtp:
    """O `automacao_avisos` falso: guarda o que «mandou», ou falha quando mandado."""

    def __init__(self, host="smtp.exemplo.invalid"):
        self.host = host
        self.enviados: list[dict] = []
        self.falhar = False
        self.modulo = types.ModuleType("automacao_avisos")
        self.modulo.configuracao_de_email = lambda con: {
            "host": self.host, "porta": "587", "usuario": "robo", "remetente": "robo@exemplo.invalid",
            "seguranca": "STARTTLS", "destinos": []}
        self.modulo._senha_do_smtp = lambda pasta, cfg: "senha-de-teste"
        self.modulo.ENVIO = {"email": self._mandar}

    def _mandar(self, cfg, senha, *, assunto, corpo):
        if self.falhar:
            raise ConnectionError("o SMTP de teste recusou")
        self.enviados.append({"para": list(cfg["destinos"]), "assunto": assunto, "corpo": corpo})


def _vps(tmp_path):
    espec = importlib.util.spec_from_file_location(
        "pesquisa_vps_teste", RAIZ / "vps" / "pesquisa" / "pesquisa_vps.py")
    m = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(m)
    return m, m.Pesquisa(str(tmp_path / "vps.sqlite3"), TOKEN, prefixo="/pesquisa")


def _transporte(pesquisa, chamadas: list):
    """O `HTTP["chamar"]` falso: entrega o pedido ao programa da VPS, sem rede."""
    def chamar(metodo, url, token, corpo=None, timeout=None):
        chamadas.append((metodo, url))
        if token != TOKEN:
            return 401, '{"ok": false}'
        caminho = url[len(URL):]
        try:
            if metodo == "POST" and caminho == ENVIO.CAMINHO_CONVITES:
                return 200, json.dumps(pesquisa.receber(corpo))
            if metodo == "GET" and caminho == ENVIO.CAMINHO_RESPOSTAS:
                return 200, json.dumps({"ok": True, "respostas": pesquisa.respostas()})
            if metodo == "POST" and caminho == ENVIO.CAMINHO_CONFIRMAR:
                return 200, json.dumps(pesquisa.confirmar(corpo))
        except ValueError as erro:
            return 400, json.dumps({"ok": False, "motivo": str(erro)})
        return 404, "{}"
    return chamar


@pytest.fixture()
def pontas(monkeypatch, tmp_path):
    """O e-mail da automação, o portal (token e régua do endereço) e a VPS."""
    import cofre_cred
    smtp = _Smtp()
    portal = types.ModuleType("portal_cliente")
    portal.CHAVE_TOKEN = "token_da_vps"

    def endereco_valido(url):
        texto = str(url or "").strip().rstrip("/")
        if texto and not texto.startswith("https://"):
            raise ValueError("O endereço do portal tem de começar com https://")
        return texto
    portal.endereco_valido = endereco_valido
    monkeypatch.setitem(sys.modules, "automacao_avisos", smtp.modulo)
    monkeypatch.setitem(sys.modules, "portal_cliente", portal)
    monkeypatch.setattr(cofre_cred, "PORTAL", "portal.cred", raising=False)
    monkeypatch.setattr(cofre_cred, "ler_segredo",
                        lambda con, nome, chave: TOKEN if nome == "portal.cred" else "")
    modulo_vps, pesquisa = _vps(tmp_path)
    chamadas: list = []
    monkeypatch.setitem(ENVIO.HTTP, "chamar", _transporte(pesquisa, chamadas))
    return {"smtp": smtp, "vps": pesquisa, "m": modulo_vps, "chamadas": chamadas}


# ------------------------------------------------------------------ a casa


def _segredo(casa) -> str:
    return casa["app"].config["SECRET_KEY"]


def _ctx(casa, tmp_path, *, agora: datetime | None = None, parametros: dict | None = None):
    pasta = tmp_path / "dados"
    pasta.mkdir(exist_ok=True)
    (pasta / "secret.key").write_text(_segredo(casa), encoding="utf-8")
    agora = agora or datetime.now().replace(microsecond=0)
    return types.SimpleNamespace(
        db=casa["db"], agora=agora, hoje=agora.date(), pasta_dados=pasta,
        parametros=parametros or {},
        processo={"codigo": ENVIO.CODIGO_DO_PROCESSO, "alterado_por": "mario"})


def _usuario(casa, login: str, nome: str, papel: str) -> int:
    casa["db"].create_user(login, nome, SENHA, papel)
    with casa["db"].connect() as con:
        return int(banco(con).um("SELECT id FROM users WHERE username=%s", (login,))["id"])


def _protocolo(casa, numero: str, criado_por: int | None, *, atribuicao="RI",
               telefone: str | None = None, email: str | None = EMAIL_FICTICIO) -> dict:
    with casa["db"].transaction() as con:
        banco(con).escrever(
            "INSERT INTO cx_protocolos (numero, data_abertura, atribuicao, telefone, email, "
            "criado_em, criado_por) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (numero, date.today().isoformat(), atribuicao, telefone, email, casa["db"].now(),
             criado_por))
        return SAT.protocolo_por_numero(con, numero)


def _na_fila(casa, protocolo: dict, atendente: int | None, *, criado_em: str | None = None):
    with casa["db"].transaction() as con:
        linhas = SAT.enfileirar_convite(con, protocolo, atendente_id=atendente,
                                        criado_por=atendente,
                                        agora=criado_em or casa["db"].now())
    return linhas


def _fila(casa, protocolo_id: int) -> list[dict]:
    with casa["db"].connect() as con:
        return [dict(x) for x in banco(con).ler(
            "SELECT * FROM ou_satisfacao_convites WHERE protocolo_id=%s ORDER BY id",
            (int(protocolo_id),))]


def _configurar(casa, url: str = URL):
    with casa["db"].transaction() as con:
        SAT.init_satisfacao_schema(con)
        ENVIO.gravar_endereco(con, url)


def _codigo_do_email(corpo: str) -> str:
    return re.search(r"/r/([A-Z2-7]{32})", corpo).group(1)


# ------------------------------------------------------------------ as pontas que faltam


def test_sem_portal_o_convite_fica_na_fila_com_o_motivo(cg_casa, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "portal_cliente", None)    # import → ImportError
    smtp = _Smtp()
    monkeypatch.setitem(sys.modules, "automacao_avisos", smtp.modulo)
    mario = _usuario(cg_casa, "mario", "MARIO EXEMPLO", "ADMIN")
    p = _protocolo(cg_casa, "2026.10.801", mario)
    _na_fila(cg_casa, p, mario)
    r = ENVIO.rodar(_ctx(cg_casa, tmp_path))
    assert r["situacao"] == "AVISO" and ENVIO.SEM_PORTAL in r["relato"]
    linha = _fila(cg_casa, p["id"])[0]
    assert linha["situacao"] == "NA_FILA" and linha["erro"] == ENVIO.SEM_PORTAL
    assert int(linha["tentativas"]) == 0 and smtp.enviados == []


def test_sem_email_da_automacao_o_convite_fica_na_fila_com_o_motivo(cg_casa, tmp_path,
                                                                    monkeypatch, pontas):
    monkeypatch.setitem(sys.modules, "automacao_avisos", None)
    mario = _usuario(cg_casa, "mario", "MARIO EXEMPLO", "ADMIN")
    _configurar(cg_casa)
    p = _protocolo(cg_casa, "2026.10.802", mario)
    _na_fila(cg_casa, p, mario)
    r = ENVIO.rodar(_ctx(cg_casa, tmp_path))
    assert r["situacao"] == "AVISO"
    linha = _fila(cg_casa, p["id"])[0]
    assert linha["situacao"] == "NA_FILA" and linha["erro"] == ENVIO.SEM_EMAIL_DA_AUTOMACAO
    # O convite foi à VPS (o portal está), mas nenhum e-mail saiu.
    assert linha["na_vps_em"] and pontas["smtp"].enviados == []


def test_sem_endereco_nada_vai_a_vps_nem_sai(cg_casa, tmp_path, pontas):
    mario = _usuario(cg_casa, "mario", "MARIO EXEMPLO", "ADMIN")
    p = _protocolo(cg_casa, "2026.10.803", mario)
    _na_fila(cg_casa, p, mario)
    ENVIO.rodar(_ctx(cg_casa, tmp_path))
    linha = _fila(cg_casa, p["id"])[0]
    assert linha["erro"] == ENVIO.SEM_URL and not linha["na_vps_em"]
    assert pontas["chamadas"] == [] and pontas["smtp"].enviados == []


# ------------------------------------------------------------------ o ciclo inteiro


def test_o_ciclo_inteiro_convite_email_resposta(cg_casa, tmp_path, pontas):
    mario = _usuario(cg_casa, "mario", "MARIO EXEMPLO", "ADMIN")
    beatriz = _usuario(cg_casa, "beatriz", "BEATRIZ EXEMPLO", "USER")
    _configurar(cg_casa)
    p = _protocolo(cg_casa, "2026.10.804", beatriz, telefone=TELEFONE_FICTICIO)
    _na_fila(cg_casa, p, beatriz)

    r = ENVIO.rodar(_ctx(cg_casa, tmp_path))
    assert r["situacao"] == "OK", r["relato"]

    # 1. A VPS recebeu UM convite, sem dado pessoal.
    m, vps = pontas["m"], pontas["vps"]
    with vps._con() as con:
        convites = [dict(x) for x in con.execute("SELECT * FROM convites")]
    assert len(convites) == 1
    assert convites[0]["atribuicao"] == "RI"
    assert "2026.10.804" not in json.dumps(convites)
    assert EMAIL_FICTICIO not in json.dumps(convites)

    # 2. O e-mail saiu para o e-mail do protocolo, com o link e a validade, e
    #    sem número de protocolo nem nome de ninguém.
    [enviado] = pontas["smtp"].enviados
    assert enviado["para"] == [EMAIL_FICTICIO]
    assert URL + "/r/" in enviado["corpo"]
    vale = (date.today() + timedelta(days=SAT.DIAS_DO_CONVITE)).strftime("%d/%m/%Y")
    assert vale in enviado["corpo"]
    for proibido in ("2026.10.804", "BEATRIZ", "MARIO", "R$", TELEFONE_FICTICIO):
        assert proibido not in enviado["corpo"] and proibido not in enviado["assunto"]
    codigo = _codigo_do_email(enviado["corpo"])
    assert m.chave_do_codigo(codigo) == convites[0]["chave"]

    # 3. A fila: e-mail ENVIADO, WhatsApp esperando o modelo da Meta.
    fila = {x["canal"]: x for x in _fila(cg_casa, p["id"])}
    assert fila["EMAIL"]["situacao"] == "ENVIADO" and int(fila["EMAIL"]["tentativas"]) == 1
    assert fila["WHATSAPP"]["situacao"] == "NA_FILA"
    assert fila["WHATSAPP"]["erro"] == ENVIO.SEM_MODELO_DA_META
    # O código não está na fila (só o hash).
    assert codigo not in json.dumps(list(fila.values()), default=str)

    # 4. O cliente responde na VPS; a rodada seguinte traz e grava.
    assert vps.responder(codigo, "2", "Demorou um pouco.", "10.0.0.9") == "ok"
    r = ENVIO.rodar(_ctx(cg_casa, tmp_path))
    with cg_casa["db"].connect() as con:
        avaliacoes = [dict(x) for x in banco(con).ler("SELECT * FROM ou_satisfacao")]
    assert len(avaliacoes) == 1
    a = avaliacoes[0]
    assert a["nota"] == 2 and a["comentario"] == "Demorou um pouco."
    assert a["origem"] == "CONVITE" and int(a["atendente_id"]) == beatriz
    assert a["atribuicao"] == "RI"
    assert a["protocolo_chave"] == SAT.chave_do_protocolo(_segredo(cg_casa), p["id"])
    # A chave da VPS não se cruza com a da avaliação.
    assert a["protocolo_chave"] != convites[0]["chave"]
    # Confirmada: a resposta saiu da VPS; nenhum segundo e-mail saiu.
    assert vps.respostas() == [] and len(pontas["smtp"].enviados) == 1

    # 5. A auditoria: agente e a mando de quem, e nunca o e-mail do cliente.
    with cg_casa["db"].connect() as con:
        linhas = banco(con).ler(
            "SELECT action, user_id, details FROM audit_logs WHERE action LIKE 'SATISFACAO_%%'")
    acoes = {x["action"]: json.loads(x["details"]) for x in linhas}
    for acao in ("SATISFACAO_CONVITE_ENVIADO", "SATISFACAO_RESPOSTA_DA_VPS"):
        assert acoes[acao]["agente"] == f"automacao:{ENVIO.CODIGO_DO_PROCESSO}"
        assert acoes[acao]["a_mando_de"] == "mario"
    assert all(x["user_id"] is None for x in linhas)
    assert EMAIL_FICTICIO not in json.dumps([x["details"] for x in linhas])
    assert codigo not in json.dumps([x["details"] for x in linhas])


def test_resposta_de_quem_ja_avaliou_na_casa_nao_dobra(cg_casa, tmp_path, pontas):
    mario = _usuario(cg_casa, "mario", "MARIO EXEMPLO", "ADMIN")
    _configurar(cg_casa)
    p = _protocolo(cg_casa, "2026.10.805", mario)
    _na_fila(cg_casa, p, mario)
    ENVIO.rodar(_ctx(cg_casa, tmp_path))
    codigo = _codigo_do_email(pontas["smtp"].enviados[0]["corpo"])
    # Avaliou antes pela página da casa (o mesmo protocolo).
    with cg_casa["db"].transaction() as con:
        SAT.registrar(con, nota=5, dia=date.today(), convite={"atendente_id": mario},
                      protocolo_chave=SAT.chave_do_protocolo(_segredo(cg_casa), p["id"]))
    pontas["vps"].responder(codigo, "1", "", "10.0.0.9")
    r = ENVIO.rodar(_ctx(cg_casa, tmp_path))
    with cg_casa["db"].connect() as con:
        assert int(banco(con).valor("SELECT COUNT(*) FROM ou_satisfacao")) == 1
    assert pontas["vps"].respostas() == []           # confirmada: não volta toda rodada
    assert "1 já avaliada" in r["relato"]


# ------------------------------------------------------------------ tetos e tentativas


def test_teto_por_rodada(cg_casa, tmp_path, pontas):
    mario = _usuario(cg_casa, "mario", "MARIO EXEMPLO", "ADMIN")
    _configurar(cg_casa)
    for n in range(3):
        _na_fila(cg_casa, _protocolo(cg_casa, f"2026.10.81{n}", mario), mario)
    r = ENVIO.rodar(_ctx(cg_casa, tmp_path, parametros={"max_por_rodada": 2}))
    assert len(pontas["smtp"].enviados) == 2
    assert "1 para a próxima rodada" in r["relato"]
    ENVIO.rodar(_ctx(cg_casa, tmp_path, parametros={"max_por_rodada": 2}))
    assert len(pontas["smtp"].enviados) == 3


def test_tentativas_limitadas(cg_casa, tmp_path, pontas):
    mario = _usuario(cg_casa, "mario", "MARIO EXEMPLO", "ADMIN")
    _configurar(cg_casa)
    p = _protocolo(cg_casa, "2026.10.820", mario)
    _na_fila(cg_casa, p, mario)
    pontas["smtp"].falhar = True
    for esperado in ("NA_FILA", "NA_FILA", "FALHOU"):
        r = ENVIO.rodar(_ctx(cg_casa, tmp_path, parametros={"max_tentativas": 3}))
        assert r["situacao"] == "AVISO"
        assert _fila(cg_casa, p["id"])[0]["situacao"] == esperado
    linha = _fila(cg_casa, p["id"])[0]
    assert int(linha["tentativas"]) == 3 and "ConnectionError" in linha["erro"]
    # Desistido: a quarta rodada não tenta de novo.
    pontas["smtp"].falhar = False
    ENVIO.rodar(_ctx(cg_casa, tmp_path, parametros={"max_tentativas": 3}))
    assert pontas["smtp"].enviados == []


def test_convite_vencido_nao_sai(cg_casa, tmp_path, pontas):
    mario = _usuario(cg_casa, "mario", "MARIO EXEMPLO", "ADMIN")
    _configurar(cg_casa)
    p = _protocolo(cg_casa, "2026.10.830", mario)
    antigo = (datetime.now() - timedelta(days=SAT.DIAS_DO_CONVITE + 2)).isoformat()
    _na_fila(cg_casa, p, mario, criado_em=antigo)
    ENVIO.rodar(_ctx(cg_casa, tmp_path))
    linha = _fila(cg_casa, p["id"])[0]
    assert linha["situacao"] == "FALHOU" and linha["erro"] == ENVIO.VENCIDO
    assert pontas["smtp"].enviados == [] and pontas["vps"].contar()["convites"] == 0


def test_protesto_vai_a_vps_sem_o_nome_da_atribuicao(cg_casa, tmp_path, pontas):
    mario = _usuario(cg_casa, "mario", "MARIO EXEMPLO", "ADMIN")
    _configurar(cg_casa)
    p = _protocolo(cg_casa, "2026.10.840", mario, atribuicao="PROTESTO")
    _na_fila(cg_casa, p, mario)
    ENVIO.rodar(_ctx(cg_casa, tmp_path))
    with pontas["vps"]._con() as con:
        assert [x[0] for x in con.execute("SELECT atribuicao FROM convites")] == [""]


def test_vps_fora_do_ar_o_convite_espera_e_a_rodada_nao_quebra(cg_casa, tmp_path, pontas,
                                                               monkeypatch):
    mario = _usuario(cg_casa, "mario", "MARIO EXEMPLO", "ADMIN")
    _configurar(cg_casa)
    p = _protocolo(cg_casa, "2026.10.850", mario)
    _na_fila(cg_casa, p, mario)
    monkeypatch.setitem(ENVIO.HTTP, "chamar", lambda *a, **k: (0, "conexão recusada"))
    r = ENVIO.rodar(_ctx(cg_casa, tmp_path))
    assert r["situacao"] == "AVISO" and "conexão recusada" in r["relato"]
    linha = _fila(cg_casa, p["id"])[0]
    assert linha["situacao"] == "NA_FILA" and not linha["na_vps_em"]
    assert pontas["smtp"].enviados == []


# ------------------------------------------------------------------ a configuração


def _entrar(casa, usuario: str, nome: str, papel: str):
    casa["db"].create_user(usuario, nome, SENHA, papel)
    c = casa["app"].test_client()
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get("/login").get_data(as_text=True)).group(1)
    c.post("/login", data={"username": usuario, "password": SENHA, "csrf_token": token},
           follow_redirects=True)
    return c


def _post(c, rota: str, /, **dados):
    # `rota`, e não `url`: o formulário do endereço da VPS tem um campo `url`.
    with c.session_transaction() as s:
        token = s["csrf_token"]
    return c.post(rota, data={"csrf_token": token, **dados})


def test_so_o_oficial_grava_o_endereco_e_so_https(cg_casa):
    oficial = _entrar(cg_casa, "mario", "MARIO EXEMPLO", "ADMIN")
    balcao = _entrar(cg_casa, "beatriz", "BEATRIZ EXEMPLO", "USER")
    r = _post(balcao, "/administrativo/satisfacao/vps", url=URL)
    assert r.status_code in (302, 403)
    assert cg_casa["db"].get_setting(ENVIO.CHAVE_URL, "") == ""
    _post(oficial, "/administrativo/satisfacao/vps", url="http://sem-s.exemplo.invalid/pesquisa")
    assert cg_casa["db"].get_setting(ENVIO.CHAVE_URL, "") == ""
    _post(oficial, "/administrativo/satisfacao/vps", url=URL + "/")
    assert cg_casa["db"].get_setting(ENVIO.CHAVE_URL, "") == URL
    html = oficial.get("/administrativo/satisfacao").get_data(as_text=True)
    assert URL in html and "satisfacao/vps" in html


# ------------------------------------------------------------------ a central da automação


def test_o_processo_entra_no_catalogo_da_automacao():
    """Com a central da automação instalada (PR #11), a rodada é um processo
    DESLIGADO trazido por este módulo. Fica vermelho até a máquina do merge
    acrescentar «satisfacao_envio» a `MODULOS_COM_PROCESSOS` — de propósito."""
    PROC = pytest.importorskip("automacao_processos")
    assert "satisfacao_envio" in PROC.MODULOS_COM_PROCESSOS
    sementes = {s["codigo"]: s for s in PROC.todas_as_sementes()}
    s = sementes[ENVIO.CODIGO_DO_PROCESSO]
    assert s["alvo"] == "satisfacao_envio:rodar"


def test_o_catalogo_declara_o_que_a_central_le():
    [item] = ENVIO.CATALOGO
    assert item["funcao"] == "satisfacao_envio.rodar" and callable(ENVIO.rodar)
    assert item["parametros"]["max_por_rodada"] == ENVIO.MAX_POR_RODADA_PADRAO
    assert item["parametros"]["max_tentativas"] == ENVIO.MAX_TENTATIVAS_PADRAO
