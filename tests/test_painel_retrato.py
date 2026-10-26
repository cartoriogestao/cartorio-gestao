"""O retrato que sai da casa e a página que o recebe na VPS — sem rede.

Pedido de 26/10/2026: «não exponha o servidor; o servidor empurra um retrato
assinado; uma página mínima na VPS com login próprio forte». Os testes ligam
as duas pontas na mesma máquina: o envelope que `painel_retrato` assina é o
que `vps/painel/painel_vps.py` confere — nenhum dos dois lados é imitado.

Nada aqui fala com a internet: o envio é um `http_post` de mentira, e a VPS é
chamada como WSGI, com uma pasta temporária.
"""
from __future__ import annotations

import base64
import io
import json
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "vps" / "painel"))

import painel_numeros as PN                   # noqa: E402
import painel_retrato as PR                   # noqa: E402
import painel_vps as VPS                      # noqa: E402

RETRATO = {
    "formato": PN.FORMATO, "gerado_em": "2026-10-26T10:00:00", "hoje": "2026-10-26",
    "periodos": {"dia": {"rotulo": "Hoje", "inicio": "2026-10-26", "fim": "2026-10-26",
                         "receita_centavos": 12345, "selos_usados": 2,
                         "atos_por_atribuicao": {"RI": 1, "Notas": 1}}},
    "agora": {"tarefas": {"atrasadas": 3}}, "nao_mediu": [],
}


class BancoDeMentira:
    def __init__(self):
        self.s = {}

    def get_setting(self, chave, padrao=""):
        return self.s.get(chave, padrao)

    def set_settings(self, valores):
        self.s.update(valores)


@pytest.fixture
def casa(tmp_path):
    pasta = tmp_path / "dados_da_casa"
    pasta.mkdir()
    PR.gerar_chave(pasta)
    return pasta


@pytest.fixture
def vps(tmp_path, monkeypatch, casa):
    monkeypatch.setenv("PAINEL_VPS_DADOS", str(tmp_path / "dados_da_vps"))
    monkeypatch.delenv("PAINEL_VPS_PREFIXO", raising=False)
    monkeypatch.delenv("PAINEL_VPS_CONFIA_PROXY", raising=False)
    conf = {"chave_publica": PR.chave_publica(casa), "usuarios": {}}
    VPS.gravar_json("config.json", conf)
    return tmp_path / "dados_da_vps"


# ------------------------------------------------------------ a chave


def test_a_chave_mora_no_cofre_e_nao_se_troca_sem_pedir(casa):
    publica = PR.chave_publica(casa)
    assert len(base64.b64decode(publica)) == 32
    assert (casa / "painel.cred").is_file()
    assert publica not in (casa / "painel.cred").read_text(encoding="utf-8")
    with pytest.raises(PR.RetratoError):
        PR.gerar_chave(casa)
    assert PR.gerar_chave(casa, trocar=True) != publica


# ------------------------------------------------------------ as duas pontas


def test_o_retrato_assinado_aqui_e_aceito_la(casa, vps):
    env = PR.envelope(RETRATO, casa)
    VPS.receber_retrato(json.dumps(env).encode("ascii"))
    guardado = VPS.ler_json("retrato.json", None)
    assert guardado["periodos"]["dia"]["receita_centavos"] == 12345


def test_retrato_alterado_no_caminho_e_recusado(casa, vps):
    env = PR.envelope(RETRATO, casa)
    env["retrato"] = env["retrato"].replace("12345", "99999")
    with pytest.raises(VPS.Recusa) as r:
        VPS.receber_retrato(json.dumps(env).encode("ascii"))
    assert r.value.status.startswith("403")


def test_retrato_de_outra_chave_e_recusado(casa, vps, tmp_path):
    outra = tmp_path / "outra_casa"
    outra.mkdir()
    PR.gerar_chave(outra)
    with pytest.raises(VPS.Recusa) as r:
        VPS.receber_retrato(json.dumps(PR.envelope(RETRATO, outra)).encode("ascii"))
    assert r.value.status.startswith("403")


def test_o_mesmo_retrato_nao_vale_duas_vezes_nem_o_mais_velho(casa, vps):
    t = datetime.now(timezone.utc)
    novo = json.dumps(PR.envelope(RETRATO, casa, agora_utc=t)).encode("ascii")
    velho = json.dumps(PR.envelope(RETRATO, casa, agora_utc=t - timedelta(minutes=1))).encode("ascii")
    VPS.receber_retrato(novo)
    for corpo in (novo, velho):
        with pytest.raises(VPS.Recusa) as r:
            VPS.receber_retrato(corpo)
        assert r.value.status.startswith("409")


def test_retrato_de_mais_de_quinze_minutos_nao_entra(casa, vps):
    antigo = datetime.now(timezone.utc) - timedelta(minutes=16)
    with pytest.raises(VPS.Recusa) as r:
        VPS.receber_retrato(json.dumps(PR.envelope(RETRATO, casa, agora_utc=antigo)).encode("ascii"))
    assert r.value.status.startswith("409")


def test_sem_chave_publica_a_vps_nao_aceita_nada(casa, vps):
    VPS.gravar_json("config.json", {"usuarios": {}})
    with pytest.raises(VPS.Recusa) as r:
        VPS.receber_retrato(json.dumps(PR.envelope(RETRATO, casa)).encode("ascii"))
    assert r.value.status.startswith("503")


def test_o_retrato_com_nome_nao_sai_assinado(casa):
    sujo = json.loads(json.dumps(RETRATO))
    sujo["agora"]["cliente"] = "CARLA EXEMPLO LIMA"
    with pytest.raises(PR.RetratoError):
        PR.envelope(sujo, casa)


# ------------------------------------------------------------ o envio


def test_empurrar_so_sai_ligado_e_em_https(casa, monkeypatch):
    monkeypatch.setattr(PN, "montar", lambda db, agora=None: RETRATO)
    db = BancoDeMentira()
    enviados = []

    def post(url, corpo):
        enviados.append((url, corpo))
        return 204, ""

    assert PR.empurrar(db, casa, http_post=post)["ok"] is False      # desligado
    with pytest.raises(PR.RetratoError):
        PR.salvar_configuracao(db, url="http://vps.exemplo.invalid/painel/retrato", ligado=True)
    PR.salvar_configuracao(db, url="https://vps.exemplo.invalid/painel/retrato", ligado=True)
    feito = PR.empurrar(db, casa, http_post=post)
    assert feito["ok"] is True and len(enviados) == 1
    url, corpo = enviados[0]
    assert url.startswith("https://")
    env = json.loads(corpo)
    assert env["formato"] == PR.FORMATO_DO_ENVELOPE
    # o resultado fica gravado, sem o corpo e sem segredo
    ultimo = json.loads(db.s[PR.CHAVE_ULTIMO_ENVIO])
    assert ultimo["ok"] is True and "retrato" not in ultimo
    assert PR.SEGREDO_DA_CHAVE not in json.dumps(db.s)


def test_vps_fora_do_ar_fica_anotado_e_nao_estoura(casa, monkeypatch):
    monkeypatch.setattr(PN, "montar", lambda db, agora=None: RETRATO)
    db = BancoDeMentira()
    PR.salvar_configuracao(db, url="https://vps.exemplo.invalid/painel/retrato", ligado=True)
    feito = PR.empurrar(db, casa, http_post=lambda u, c: (0, "URLError"))
    assert feito["ok"] is False and "sem conexão" in feito["motivo"]


# ------------------------------------------------------------ a página na VPS


def _chamar(metodo, caminho, corpo=b"", cookies=None, query=""):
    status, cabecalhos = {}, {}

    def start_response(s, h):
        status["s"] = s
        cabecalhos["h"] = h

    environ = {"REQUEST_METHOD": metodo, "PATH_INFO": caminho, "QUERY_STRING": query,
               "CONTENT_LENGTH": str(len(corpo)), "wsgi.input": io.BytesIO(corpo),
               "REMOTE_ADDR": "198.51.100.7",
               "HTTP_COOKIE": "; ".join(f"{k}={v}" for k, v in (cookies or {}).items())}
    saida = b"".join(VPS.application(environ, start_response))
    return status["s"], dict(cabecalhos["h"]), cabecalhos["h"], saida.decode("utf-8")


def _cookies_de(lista):
    saida = {}
    for k, v in lista:
        if k == "Set-Cookie":
            nome, valor = v.split(";")[0].split("=", 1)
            saida[nome] = valor
    return saida


@pytest.fixture
def usuario(vps):
    segredo = base64.b32encode(b"0123456789abcdefghij").decode().rstrip("=")
    conf = VPS.configuracao()
    conf["usuarios"]["mario"] = {"senha": VPS.hash_da_senha("frase-longa-de-teste-123"),
                                 "totp": segredo}
    VPS.gravar_json("config.json", conf)
    return segredo


def _entrar(segredo, senha="frase-longa-de-teste-123", codigo=None, passo_extra=0):
    s, _, h, html = _chamar("GET", "/painel/")
    cookies = _cookies_de(h)
    csrf = cookies[VPS.COOKIE_CSRF]
    codigo = codigo or VPS.totp(segredo, int(time.time() // 30) + passo_extra)
    corpo = urllib.parse.urlencode({"csrf": csrf, "usuario": "mario", "senha": senha,
                                    "codigo": codigo}).encode()
    s, _, h, html = _chamar("POST", "/painel/entrar", corpo, cookies)
    cookies.update(_cookies_de(h))
    return s, cookies, html


def test_sem_login_a_vps_mostra_so_o_formulario(casa, vps, usuario):
    VPS.receber_retrato(json.dumps(PR.envelope(RETRATO, casa)).encode("ascii"))
    s, cab, _, html = _chamar("GET", "/painel/")
    assert s.startswith("200") and "Código de 6 dígitos" in html
    assert "123,45" not in html
    assert "frame-ancestors 'none'" in cab["Content-Security-Policy"]
    assert cab["Cache-Control"] == "no-store"


def test_senha_e_codigo_certos_entram_e_veem_os_numeros(casa, vps, usuario):
    VPS.receber_retrato(json.dumps(PR.envelope(RETRATO, casa)).encode("ascii"))
    s, cookies, _ = _entrar(usuario)
    assert s.startswith("303")
    assert VPS.COOKIE_SESSAO in cookies
    s, _, _, html = _chamar("GET", "/painel/", cookies=cookies)
    assert "R$ 123,45" in html


def test_a_sessao_vai_em_cookie_seguro_e_no_disco_fica_so_o_hash(vps, usuario):
    _, cookies, _ = _entrar(usuario)
    token = cookies[VPS.COOKIE_SESSAO]
    sessoes = (vps / "sessoes.json").read_text(encoding="utf-8")
    assert token not in sessoes
    _, _, h, _ = _chamar("GET", "/painel/")
    assert all("HttpOnly" in v and "Secure" in v and "SameSite=Strict" in v
               for k, v in h if k == "Set-Cookie")


def test_so_a_senha_nao_basta(vps, usuario):
    s, cookies, html = _entrar(usuario, codigo="000000")
    assert s.startswith("401") and VPS.COOKIE_SESSAO not in cookies


def test_o_mesmo_codigo_nao_entra_duas_vezes(vps, usuario):
    codigo = VPS.totp(usuario, int(time.time() // 30))
    assert _entrar(usuario, codigo=codigo)[0].startswith("303")
    assert _entrar(usuario, codigo=codigo)[0].startswith("401")


def test_cinco_erros_poem_em_espera_e_nem_a_senha_certa_entra(vps, usuario):
    for _ in range(5):
        assert _entrar(usuario, senha="errada-errada-errada")[0].startswith("401")
    s, cookies, html = _entrar(usuario)
    assert s.startswith("429") and VPS.COOKIE_SESSAO not in cookies


def test_post_sem_o_token_do_formulario_e_recusado(vps, usuario):
    corpo = urllib.parse.urlencode({"usuario": "mario", "senha": "x", "codigo": "1"}).encode()
    s, *_ = _chamar("POST", "/painel/entrar", corpo)
    assert s.startswith("400")


def test_usuario_que_nao_existe_gasta_o_mesmo_scrypt(monkeypatch):
    chamadas = []
    original = VPS.hashlib.scrypt
    monkeypatch.setattr(VPS.hashlib, "scrypt",
                        lambda *a, **k: chamadas.append(1) or original(*a, **k))
    assert VPS.senha_confere("qualquer", None) is False
    assert chamadas == [1]


def test_o_post_do_retrato_pelo_wsgi(casa, vps):
    corpo = json.dumps(PR.envelope(RETRATO, casa)).encode("ascii")
    s, *_ = _chamar("POST", "/painel/retrato", corpo)
    assert s.startswith("204")
    s, *_ = _chamar("POST", "/painel/retrato", b"x" * (VPS.TETO_DO_CORPO + 1))
    assert s.startswith("413")


# ------------------------------------------------------------ correções de segurança de 26/10/2026


def test_x_forwarded_for_vale_pelo_fim_e_so_quando_vem_do_servidor_web(monkeypatch):
    """O começo da lista é o que o cliente mandou; o fim é o que o servidor web
    acrescentou. E o cabeçalho de quem não é o servidor web não vale nada."""
    monkeypatch.setenv("PAINEL_VPS_CONFIA_PROXY", "1")
    forjado = {"REMOTE_ADDR": "127.0.0.1",
               "HTTP_X_FORWARDED_FOR": "10.0.0.1, 203.0.113.9"}
    assert VPS._ip(forjado) == "203.0.113.9"
    de_fora = {"REMOTE_ADDR": "198.51.100.7", "HTTP_X_FORWARDED_FOR": "10.0.0.1"}
    assert VPS._ip(de_fora) == "198.51.100.7"
    monkeypatch.delenv("PAINEL_VPS_CONFIA_PROXY")
    assert VPS._ip(forjado) == "127.0.0.1"


def test_variar_o_x_forwarded_for_nao_escapa_da_espera(vps, usuario, monkeypatch):
    """Cinco erros vindos do servidor web com começos diferentes no cabeçalho
    são cinco erros do MESMO endereço."""
    monkeypatch.setenv("PAINEL_VPS_CONFIA_PROXY", "1")
    agora = time.time()
    for n in range(5):
        ip = VPS._ip({"REMOTE_ADDR": "127.0.0.1",
                      "HTTP_X_FORWARDED_FOR": f"10.0.0.{n}, 203.0.113.9"})
        VPS.anotar_erro(f"outro{n}", ip, agora)
    ip = VPS._ip({"REMOTE_ADDR": "127.0.0.1",
                  "HTTP_X_FORWARDED_FOR": "10.0.0.99, 203.0.113.9"})
    assert VPS.em_espera("mais-um", ip, agora)


def test_tentativas_velhas_saem_do_arquivo(vps):
    agora = time.time()
    velho = agora - (VPS.JANELA_DOS_ERROS_S + VPS.ESPERA_S + 60)
    for n in range(50):
        VPS.anotar_erro(f"velho{n}", f"192.0.2.{n}", velho)
    VPS.anotar_erro("beatriz", "198.51.100.8", agora)
    erros = VPS.ler_json("tentativas.json", {})
    assert len(erros) == 2                       # só o usuário e o endereço de agora
    assert all(max(v) == agora for v in erros.values())


def test_tentativas_tem_teto_de_chaves(vps, monkeypatch):
    monkeypatch.setattr(VPS, "TETO_DE_CHAVES_DA_ESPERA", 10)
    agora = time.time()
    for n in range(30):
        VPS.anotar_erro(f"u{n}", f"192.0.2.{n}", agora - 30 + n)
    erros = VPS.ler_json("tentativas.json", {})
    assert len(erros) <= 10
    # a mais nova fica, e a espera dela continua contando
    assert any(max(v) == agora - 1 for v in erros.values())
