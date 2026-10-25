"""O cofre da automação e o guardião — senha-mestra, formato portátil, canal local.

O QUE ESTES TESTES PROVAM
    - a ida e a volta do formato (o arquivo abre de novo, com a mesma senha,
      num guardião novo — é o «copiar de um servidor para o outro»);
    - a senha e a chave NUNCA vão a disco (varre todos os arquivos da pasta);
    - senha errada é recusada, e cinco seguidas bloqueiam as tentativas;
    - arquivo adulterado (cifra ou metadado trocado) não abre: falha do GCM;
    - cofre trancado levanta `CofreTrancado` (com `cofre_trancado = True`),
      diferente de senha errada, item inexistente e arquivo adulterado;
    - `metadados` e `listar` funcionam trancados; `gravar` exige aberto;
    - `ler` recusa dentro de requisição web, e nenhum `*_web.py` nem módulo do
      agente de IA chama `ler` do cofre.
Nada aqui usa banco.
"""
from __future__ import annotations

import ast
import base64
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import automacao_cofre as C  # noqa: E402
import automacao_guardiao as G  # noqa: E402

SENHA = "senha-mestra-de-teste-1"
#: KDF leve SÓ no teste (o de fábrica é Argon2id de 64 MiB).
KDF_LEVE = {"nome": "scrypt", "n": 2 ** 10, "r": 8, "p": 1}


@pytest.fixture
def guardiao(tmp_path):
    g = G.Guardiao(tmp_path / C.NOME_DA_PASTA / C.NOME_DO_ARQUIVO, kdf_novo=KDF_LEVE)
    g.iniciar()
    yield g
    g.parar()


def _abrir(g):
    if not g.caminho.is_file():
        return C.desbloquear(SENHA, confirmacao=SENHA, caminho=g.caminho)
    return C.desbloquear(SENHA, caminho=g.caminho)


def test_a_ida_e_volta_do_formato_e_a_mesma_senha_noutro_guardiao(guardiao, tmp_path):
    _abrir(guardiao)
    meta = C.gravar("banco_cobranca", {"client_id": "id-de-teste", "client_secret": "segredo-de-teste-xyz",
                                       "crt_pem": "-----BEGIN CERTIFICATE-----\nAAA\n-----END CERTIFICATE-----"},
                    tipo=C.API, validade="2027-10-24", por="mario", caminho=guardiao.caminho)
    assert meta["campos_presentes"] == ["client_id", "client_secret", "crt_pem"]
    assert "segredo-de-teste-xyz" not in json.dumps(meta)
    dados = json.loads(guardiao.caminho.read_text(encoding="utf-8"))
    assert dados["formato"] == C.FORMATO and dados["versao"] == C.VERSAO
    assert {"nome", "sal"} <= set(dados["kdf"]) and "verificador" in dados
    assert C.ler("banco_cobranca", caminho=guardiao.caminho, quem="teste", processo="T")["client_secret"] == \
        "segredo-de-teste-xyz"
    # o mesmo arquivo, noutra pasta (outro servidor), abre com a mesma senha
    copia = tmp_path / "outro" / C.NOME_DO_ARQUIVO
    copia.parent.mkdir()
    copia.write_bytes(guardiao.caminho.read_bytes())
    g2 = G.Guardiao(copia)
    g2.desbloquear(SENHA)
    assert g2.ler("banco_cobranca")["client_id"] == "id-de-teste"
    leituras = (guardiao.caminho.parent / C.NOME_DAS_LEITURAS).read_text(encoding="utf-8")
    assert '"item": "banco_cobranca"' in leituras and '"processo": "T"' in leituras
    assert "segredo-de-teste-xyz" not in leituras


def test_a_senha_e_a_chave_nunca_vao_a_disco(guardiao):
    _abrir(guardiao)
    C.gravar("smtp", {"usuario": "u", "senha": "senha-do-smtp-teste"}, tipo=C.SENHA, por="mario",
             caminho=guardiao.caminho)
    chave = guardiao._chave
    proibidos = [SENHA.encode(), chave, base64.b64encode(chave), chave.hex().encode(), b"senha-do-smtp-teste"]
    for arquivo in guardiao.caminho.parent.rglob("*"):
        if arquivo.is_file():
            bruto = arquivo.read_bytes()
            for p in proibidos:
                assert p not in bruto, f"{arquivo.name} guarda o que não pode"


def test_senha_errada_e_recusada_e_cinco_bloqueiam(guardiao):
    _abrir(guardiao)
    C.trancar(caminho=guardiao.caminho)
    for _ in range(G.TENTATIVAS_ANTES_DE_BLOQUEAR):
        with pytest.raises(C.SenhaErrada):
            C.desbloquear("senha-errada-123", caminho=guardiao.caminho)
    with pytest.raises(C.CofreError, match="só depois"):
        C.desbloquear(SENHA, caminho=guardiao.caminho)              # bloqueado, mesmo com a certa
    assert C.estado(caminho=guardiao.caminho)["bloqueado_ate"]


def test_o_arquivo_adulterado_nao_abre(guardiao):
    _abrir(guardiao)
    C.gravar("item", {"senha": "valor-de-teste"}, tipo=C.SENHA, validade="2027-01-01", por="mario",
             caminho=guardiao.caminho)
    dados = json.loads(guardiao.caminho.read_text(encoding="utf-8"))
    dados["itens"]["item"]["validade"] = "2099-01-01"               # trocar o metadado à mão
    guardiao.caminho.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(C.CofreAdulterado):
        C.ler("item", caminho=guardiao.caminho)
    dados["itens"]["item"]["validade"] = "2027-01-01"
    bloco = dados["itens"]["item"]["bloco"]
    cifra = bytearray(base64.b64decode(bloco["cifra"]))
    cifra[0] ^= 0xFF                                                   # um bit da cifra
    bloco["cifra"] = base64.b64encode(bytes(cifra)).decode()
    guardiao.caminho.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(C.CofreAdulterado) as e:
        C.ler("item", caminho=guardiao.caminho)
    assert not getattr(e.value, "cofre_trancado")


def test_o_cofre_trancado_e_uma_excecao_propria(guardiao, tmp_path):
    assert issubclass(C.CofreTrancado, C.CofreError) and issubclass(C.CofreError, RuntimeError)
    assert C.CofreTrancado.cofre_trancado is True
    for outra in (C.SenhaErrada, C.ItemInexistente, C.CofreAdulterado):
        assert not issubclass(outra, C.CofreTrancado) and outra.cofre_trancado is False
    _abrir(guardiao)
    C.gravar("item", {"senha": "valor-de-teste"}, tipo=C.SENHA, por="mario", caminho=guardiao.caminho)
    with pytest.raises(C.ItemInexistente):
        C.ler("nao_existe", caminho=guardiao.caminho)
    C.trancar(caminho=guardiao.caminho)
    with pytest.raises(C.CofreTrancado) as e:
        C.ler("item", caminho=guardiao.caminho)
    assert e.value.cofre_trancado is True
    # sem guardião nenhum: também trancado
    with pytest.raises(C.CofreTrancado):
        C.ler("item", caminho=tmp_path / "sem_guardiao" / C.NOME_DO_ARQUIVO)


def test_metadados_e_lista_funcionam_trancados_e_gravar_exige_aberto(guardiao):
    _abrir(guardiao)
    C.gravar("cert", {"crt_pem": "x" * 10, "key_pem": "y" * 10}, tipo=C.CERTIFICADO, validade="2027-10-24",
             por="mario", caminho=guardiao.caminho)
    C.trancar(caminho=guardiao.caminho)
    meta = C.metadados("cert", caminho=guardiao.caminho)
    assert meta["campos_presentes"] == ["crt_pem", "key_pem"] and meta["validade"] == "2027-10-24"
    assert [m["nome"] for m in C.listar(caminho=guardiao.caminho)] == ["cert"]
    with pytest.raises(C.CofreTrancado):
        C.gravar("outro", {"senha": "z1"}, tipo=C.SENHA, por="mario", caminho=guardiao.caminho)
    with pytest.raises(C.CofreTrancado):
        C.remover("cert", por="mario", caminho=guardiao.caminho)
    assert C.estado(caminho=guardiao.caminho)["aberto"] is False


def test_o_canal_recusa_quem_nao_tem_o_token(guardiao):
    assert guardiao.atender({"token": "errado", "acao": "estado"})["ok"] is False


def test_ler_recusa_dentro_da_requisicao_web(guardiao):
    from flask import Flask
    _abrir(guardiao)
    C.gravar("item", {"senha": "valor-de-teste"}, tipo=C.SENHA, por="mario", caminho=guardiao.caminho)
    with Flask("t").test_request_context("/automacao/cofre"):
        with pytest.raises(C.CofreRecusado):
            C.ler("item", caminho=guardiao.caminho)


def test_nenhuma_tela_nem_o_agente_le_o_cofre():
    """`ler` não pode ser alcançado pela camada web nem pelo agente de IA."""
    suspeitos = sorted(RAIZ.glob("*_web.py")) + sorted(RAIZ.glob("agente*.py")) + [RAIZ / "app.py"]
    achados = []
    for p in suspeitos:
        arvore = ast.parse(p.read_text(encoding="utf-8"))
        apelidos = {"automacao_cofre"}
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                apelidos |= {a.asname or a.name for a in no.names if a.name == "automacao_cofre"}
            if isinstance(no, ast.ImportFrom) and no.module == "automacao_cofre":
                if any(a.name in ("ler", "ler_com_chave", "pedir") for a in no.names):
                    achados.append(f"{p.name}: importa a leitura do cofre")
        for no in ast.walk(arvore):
            if (isinstance(no, ast.Attribute) and no.attr in ("ler", "ler_com_chave")
                    and isinstance(no.value, ast.Name) and no.value.id in apelidos):
                achados.append(f"{p.name}:{no.lineno} chama {no.value.id}.{no.attr}")
        if p.name.startswith("agente") and "automacao_cofre" in p.read_text(encoding="utf-8"):
            achados.append(f"{p.name}: o agente de IA não pode conhecer o cofre")
    assert not achados, "\n".join(achados)


def test_o_cofre_novo_pede_a_senha_duas_vezes_e_uma_senha_forte(guardiao):
    with pytest.raises(C.CofreError, match="duas vezes"):
        C.desbloquear(SENHA, confirmacao="outra-coisa-qualquer", caminho=guardiao.caminho)
    with pytest.raises(C.CofreError, match="ao menos"):
        C.desbloquear("curta", confirmacao="curta", caminho=guardiao.caminho)
    assert not guardiao.caminho.exists()
