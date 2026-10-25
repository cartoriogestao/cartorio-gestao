"""O cofre da automação — os segredos que um processo precisa usar, atrás de uma senha-mestra.

    «o cofre abre com uma senha-mestra, digitada por mim quando o Windows liga;
     e prepare a migração para, no futuro, o servidor rodar em macOS»
     — o oficial, 24/10/2026 (esta decisão substitui a DPAPI da primeira versão)

A API PÚBLICA É ESTÁVEL — outro módulo depende dela (o agente financeiro guarda
aqui o certificado `.crt`/`.key` e o par ClientId/ClientSecret do banco):

    ler(nome) -> dict                     os campos do segredo, EM CLARO — pede ao guardião
    metadados(nome) -> dict               tipo, datas, validade, campos_presentes (sem valores)
    gravar(nome, campos, *, tipo, validade=None, por) -> dict   exige o cofre ABERTO
    remover(nome, *, por) -> bool                               exige o cofre ABERTO
    listar() -> list[metadados]           funciona com o cofre trancado
    estado() -> dict                      aberto/trancado, desde quando

    Todas aceitam `caminho=` (o arquivo do cofre); sem ele vale `caminho_do_cofre()`.

O ARQUIVO — IGUAL NO WINDOWS E NO macOS
    Um JSON versionado (`formato`, `versao`), com o KDF e os parâmetros dele,
    o sal, um VERIFICADOR e os itens. A chave sai da senha-mestra por KDF
    memory-hard (Argon2id quando a biblioteca tem; senão scrypt), e cada item
    é cifrado com AES-256-GCM, nonce próprio e, como dado associado (AAD), o
    nome do item MAIS os metadados dele: quem trocar a validade ou o tipo no
    arquivo à mão faz o item deixar de abrir (falha do GCM), em vez de mentir.
    O verificador (um texto conhecido, cifrado) diz se a senha está certa sem
    decifrar item nenhum. O mesmo arquivo copiado de um servidor para o outro
    abre com a mesma senha.

A SENHA E A CHAVE NUNCA VÃO A DISCO
    Quem guarda a chave é o GUARDIÃO (`automacao_guardiao.py`), um processo
    de longa duração iniciado no logon, que a mantém SÓ EM MEMÓRIA e responde
    por um canal local (127.0.0.1, com um token de sessão aleatório gravado
    num arquivo de permissão restrita). Este módulo só fala com ele. Nada aqui
    escreve a senha nem a chave em arquivo, log, banco ou relato.

AS TRÊS REGRAS QUE NÃO SE DOBRAM
    1. **`ler` nunca é chamado pela camada web** — com uma requisição web em
       curso ele levanta `CofreRecusado`, e há teste que varre os `*_web.py`.
    2. **O segredo nunca vai ao modelo de IA** — processo de IA não tem
       credencial (`automacao.salvar`), e o agente não importa este módulo.
    3. **O segredo nunca vai ao log** — o corredor mascara os valores na saída
       do script, e o guardião registra cada leitura (quem, qual item, para
       qual processo), nunca o valor.
"""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import socket
import stat
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

try:                                      # Argon2id existe na `cryptography` 44+
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
except ImportError:                       # pragma: no cover — scrypt continua valendo
    Argon2id = None

FORMATO = "cg-automacao-cofre"
VERSAO = 1
NOME_DO_ARQUIVO = "cofre.json"
NOME_DA_PASTA = "cofre_automacao"
NOME_DO_CANAL = "guardiao.json"
NOME_DAS_LEITURAS = "leituras.log"
#: O texto conhecido do verificador. Não é segredo: saber que a senha abre
#: ESTE texto é o que se quer conferir.
TEXTO_DO_VERIFICADOR = b"cartorio-gestao/cofre/verificador/ok"

SENHA, CERTIFICADO, TOKEN, API = "SENHA", "CERTIFICADO", "TOKEN", "API"
TIPOS = (SENHA, CERTIFICADO, TOKEN, API)
NOME_DO_TIPO = {SENHA: "usuário e senha", CERTIFICADO: "certificado (.pfx, ou .crt + .key)",
                TOKEN: "token / chave de API", API: "credencial de API (client_id e client_secret)"}

#: Os parâmetros fortes de fábrica. Os testes passam parâmetros leves.
KDF_ARGON2ID = {"nome": "argon2id", "memoria_kib": 65536, "iteracoes": 3, "paralelismo": 4}
KDF_SCRYPT = {"nome": "scrypt", "n": 2 ** 17, "r": 8, "p": 1}
TAMANHO_MINIMO_DA_SENHA = 10
_NOME_VALIDO = re.compile(r"^[A-Za-z0-9_.-]{1,60}$")
_CAMPO_VALIDO = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
TETO_DO_CAMPO = 64 * 1024
TETO_DE_CAMPOS = 20
PRAZO_DO_CANAL_S = 5


class CofreError(RuntimeError):
    """Erro do cofre, com a frase pronta para a tela. É `RuntimeError` porque
    outro módulo (o agente financeiro) depende dela assim."""
    cofre_trancado = False


class CofreTrancado(CofreError):
    """O cofre está trancado: ninguém digitou a senha-mestra desde que a máquina
    ligou (ou o guardião não está rodando). Quem depende do cofre reconhece pelo
    atributo `cofre_trancado = True`; senha errada, item inexistente e arquivo
    adulterado são exceções DIFERENTES desta."""
    cofre_trancado = True


class CofreRecusado(CofreError):
    """O pedido veio de onde ele não pode ir (ler o segredo pela web)."""


class SenhaErrada(CofreError):
    """A senha-mestra não abre o verificador."""


class ItemInexistente(CofreError):
    """A credencial pedida não está cadastrada."""


class CofreAdulterado(CofreError):
    """O item (ou o verificador) não passa na autenticação do AES-GCM."""


# ------------------------------------------------------------------ onde mora


def pasta_de_dados() -> Path:
    """A pasta de dados do sistema — a mesma regra nos dois sistemas operacionais."""
    fixa = (os.environ.get("CARTORIO_GESTAO_DATA") or "").strip()
    if fixa:
        return Path(fixa)
    if sys.platform == "win32":
        return Path(os.environ.get("PROGRAMDATA") or Path.home()) / "CartorioGestao"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CartorioGestao"
    return Path.home() / ".local" / "share" / "CartorioGestao"


def caminho_do_cofre(pasta_dados: Any = None) -> Path:
    """O arquivo do cofre: `CG_COFRE_AUTOMACAO`, senão `<dados>/cofre_automacao/cofre.json`.

    Fora do banco (o banco vai no backup) e fora do repositório (a pasta de
    dados não é a do programa).
    """
    fixo = (os.environ.get("CG_COFRE_AUTOMACAO") or "").strip()
    if fixo:
        return Path(fixo)
    return Path(pasta_dados or pasta_de_dados()) / NOME_DA_PASTA / NOME_DO_ARQUIVO


def _caminho(caminho: Any) -> Path:
    return Path(caminho) if caminho else caminho_do_cofre()


def restringir(alvo: Path, *, conta_extra: str = "", rodar: Any = None) -> str | None:
    """Permissão restrita no sistema de arquivos. Os dois ramos ficam aqui.

    Windows: ACL sem herança, só SYSTEM, Administradores, a conta que roda isto
    e `conta_extra` (a do servidor web ou a do despachante). macOS/Linux:
    `chmod 700` na pasta, `600` no arquivo. Devolve o problema, ou None.
    """
    rodar = rodar or subprocess.run
    alvo = Path(alvo)
    if sys.platform != "win32":
        try:
            os.chmod(alvo, 0o700 if alvo.is_dir() else 0o600)
            return None
        except OSError as erro:
            return str(erro)
    contas = ["*S-1-5-18", "*S-1-5-32-544"]           # SYSTEM, Administradores
    try:
        import permissao_local as PERM
        proprio = PERM._sid_do_processo(rodar)
    except Exception:                                  # noqa: BLE001
        proprio = None
    if proprio:
        contas.append(proprio)
    if str(conta_extra or "").strip():
        contas.append(str(conta_extra).strip())
    heranca = "(OI)(CI)F" if alvo.is_dir() else "F"
    comando = ["icacls", str(alvo), "/inheritance:r", "/grant:r"] + [f"{c}:{heranca}" for c in dict.fromkeys(contas)]
    try:
        r = rodar(comando, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as erro:
        return f"o icacls não rodou: {erro}"
    return None if getattr(r, "returncode", 1) == 0 else (str(r.stderr or r.stdout or "")[:300] or "o icacls recusou")


def gravar_restrito(alvo: Path, texto: str, *, conta_extra: str = "") -> None:
    """Escreve atômico e com a permissão restrita (a pasta também)."""
    alvo = Path(alvo)
    nova = not alvo.parent.is_dir()
    alvo.parent.mkdir(parents=True, exist_ok=True)
    if nova:
        restringir(alvo.parent, conta_extra=conta_extra)
    temporario = alvo.with_name(alvo.name + ".tmp")
    temporario.write_text(texto, encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(temporario, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(temporario, alvo)


# ------------------------------------------------------------------ a cifra (portátil)


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode("ascii")


def _de_b64(texto: str) -> bytes:
    return base64.b64decode(texto.encode("ascii"))


def kdf_padrao() -> dict:
    return dict(KDF_ARGON2ID if Argon2id is not None else KDF_SCRYPT)


def derivar_chave(senha: str, kdf: dict) -> bytes:
    """A chave de 32 bytes que sai da senha. Memory-hard, com o sal do arquivo."""
    sal = _de_b64(kdf["sal"])
    if kdf["nome"] == "argon2id":
        if Argon2id is None:
            raise CofreError("Este cofre foi criado com Argon2id, e esta instalação não o tem "
                             "(atualize a biblioteca `cryptography`).")
        return Argon2id(salt=sal, length=32, iterations=int(kdf["iteracoes"]), lanes=int(kdf["paralelismo"]),
                        memory_cost=int(kdf["memoria_kib"])).derive(senha.encode("utf-8"))
    if kdf["nome"] == "scrypt":
        return Scrypt(salt=sal, length=32, n=int(kdf["n"]), r=int(kdf["r"]), p=int(kdf["p"])).derive(
            senha.encode("utf-8"))
    raise CofreError(f"KDF desconhecido no cofre: {kdf.get('nome')!r}.")


def _aad(nome: str, meta: dict) -> bytes:
    publico = {k: meta.get(k) for k in ("tipo", "validade", "campos_presentes", "criado_em",
                                        "criado_por", "alterado_em", "alterado_por")}
    return ("cg-cofre/item/" + nome + "\n" + json.dumps(publico, sort_keys=True, ensure_ascii=False)).encode("utf-8")


def _cifrar(chave: bytes, claro: bytes, aad: bytes) -> dict:
    nonce = secrets.token_bytes(12)
    return {"nonce": _b64(nonce), "cifra": _b64(AESGCM(chave).encrypt(nonce, claro, aad))}


def _decifrar(chave: bytes, bloco: dict, aad: bytes) -> bytes:
    try:
        return AESGCM(chave).decrypt(_de_b64(bloco["nonce"]), _de_b64(bloco["cifra"]), aad)
    except (InvalidTag, KeyError, ValueError) as erro:
        raise CofreAdulterado("O cofre não confere (arquivo adulterado ou corrompido): o item "
                              "não abre com esta senha.") from erro


def criar(caminho: Any, senha: str, *, kdf: dict | None = None, conta_extra: str = "") -> bytes:
    """Cria o arquivo do cofre com a senha-mestra. Devolve a chave (só para a memória)."""
    alvo = _caminho(caminho)
    if alvo.exists():
        raise CofreError("O cofre já existe — desbloqueie com a senha-mestra.")
    if len(senha or "") < TAMANHO_MINIMO_DA_SENHA:
        raise CofreError(f"A senha-mestra precisa de ao menos {TAMANHO_MINIMO_DA_SENHA} caracteres.")
    parametros = dict(kdf or kdf_padrao())
    parametros["sal"] = _b64(secrets.token_bytes(16))
    chave = derivar_chave(senha, parametros)
    dados = {"formato": FORMATO, "versao": VERSAO, "kdf": parametros,
             "verificador": _cifrar(chave, TEXTO_DO_VERIFICADOR, b"cg-cofre/verificador"),
             "criado_em": datetime.now().isoformat(timespec="seconds"), "itens": {}}
    gravar_restrito(alvo, json.dumps(dados, ensure_ascii=False, indent=1), conta_extra=conta_extra)
    return chave


def carregar(caminho: Any) -> dict:
    """O arquivo inteiro (só os metadados estão em claro). Recusa versão desconhecida."""
    alvo = _caminho(caminho)
    if not alvo.is_file():
        raise CofreError("O cofre ainda não foi criado — o guardião pede a senha-mestra na primeira vez.")
    try:
        dados = json.loads(alvo.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise CofreError(f"O arquivo do cofre não se lê ({type(erro).__name__}).") from erro
    if dados.get("formato") != FORMATO or not isinstance(dados.get("itens"), dict):
        raise CofreError("O arquivo do cofre não está no formato esperado.")
    if int(dados.get("versao") or 0) > VERSAO:
        raise CofreError(f"O cofre é da versão {dados.get('versao')} do formato, mais nova que esta "
                         "instalação: atualize o sistema.")
    return dados


def conferir_senha(caminho: Any, senha: str) -> bytes:
    """Deriva a chave e confere o verificador. Devolve a chave, ou levanta `SenhaErrada`."""
    dados = carregar(caminho)
    chave = derivar_chave(senha, dados["kdf"])
    try:
        if _decifrar(chave, dados["verificador"], b"cg-cofre/verificador") != TEXTO_DO_VERIFICADOR:
            raise SenhaErrada("A senha-mestra não confere.")
    except CofreAdulterado as erro:
        raise SenhaErrada("A senha-mestra não confere.") from erro
    return chave


def _validar_nome(nome: Any) -> str:
    texto = str(nome or "").strip()
    if not _NOME_VALIDO.match(texto):
        raise CofreError("O nome da credencial tem de ter de 1 a 60 caracteres, só letras sem "
                         "acento, números, ponto, hífen ou sublinhado (ex.: banco_cobranca).")
    return texto


def _validade(valor: Any) -> str | None:
    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        return date.fromisoformat(texto[:10]).isoformat()
    except ValueError as erro:
        raise CofreError("A validade tem de ser uma data (AAAA-MM-DD).") from erro


def _campos_limpos(campos: dict) -> dict[str, str]:
    limpos: dict[str, str] = {}
    for chave, valor in (campos or {}).items():
        chave = str(chave or "").strip().lower()
        texto = "" if valor is None else str(valor)
        if not texto:
            continue
        if not _CAMPO_VALIDO.match(chave):
            raise CofreError(f"O campo «{chave}» tem nome inválido: letras minúsculas, números e "
                             "sublinhado (ex.: client_secret).")
        if len(texto) > TETO_DO_CAMPO:
            raise CofreError(f"O campo «{chave}» passa de 64 KB — confira o arquivo enviado.")
        limpos[chave] = texto
    if not limpos:
        raise CofreError("Informe ao menos um campo (senha, token, certificado…). O cofre não "
                         "guarda segredo vazio.")
    if len(limpos) > TETO_DE_CAMPOS:
        raise CofreError(f"Uma credencial guarda no máximo {TETO_DE_CAMPOS} campos.")
    return limpos


def gravar_com_chave(caminho: Any, chave: bytes, nome: Any, campos: dict, *, tipo: Any,
                     validade: Any = None, por: str, conta_extra: str = "") -> dict:
    """Grava o item com a chave em memória (quem chama é o guardião)."""
    nome = _validar_nome(nome)
    tipo = str(tipo or "").strip().upper()
    if tipo not in TIPOS:
        raise CofreError("Escolha o tipo da credencial: senha, certificado, token ou API.")
    if not str(por or "").strip():
        raise CofreError("Diga quem está gravando a credencial.")
    limpos = _campos_limpos(campos)
    dados = carregar(caminho)
    anterior = dados["itens"].get(nome) or {}
    agora = datetime.now().isoformat(timespec="seconds")
    meta = {"tipo": tipo, "validade": _validade(validade), "campos_presentes": sorted(limpos),
            "criado_em": anterior.get("criado_em") or agora, "criado_por": anterior.get("criado_por") or str(por),
            "alterado_em": agora, "alterado_por": str(por)}
    item = dict(meta)
    item["bloco"] = _cifrar(chave, json.dumps(limpos, ensure_ascii=False).encode("utf-8"), _aad(nome, meta))
    dados["itens"][nome] = item
    gravar_restrito(_caminho(caminho), json.dumps(dados, ensure_ascii=False, indent=1), conta_extra=conta_extra)
    return _meta(nome, item)


def remover_com_chave(caminho: Any, chave: bytes, nome: Any) -> bool:
    nome = _validar_nome(nome)
    dados = carregar(caminho)
    conferir_chave(dados, chave)
    if nome not in dados["itens"]:
        return False
    del dados["itens"][nome]
    gravar_restrito(_caminho(caminho), json.dumps(dados, ensure_ascii=False, indent=1))
    return True


def conferir_chave(dados: dict, chave: bytes) -> None:
    _decifrar(chave, dados["verificador"], b"cg-cofre/verificador")


def ler_com_chave(caminho: Any, chave: bytes, nome: Any) -> dict:
    nome = _validar_nome(nome)
    item = carregar(caminho)["itens"].get(nome)
    if not item:
        raise ItemInexistente(f"A credencial «{nome}» não está cadastrada no cofre da automação.")
    campos = json.loads(_decifrar(chave, item["bloco"], _aad(nome, item)).decode("utf-8"))
    if not isinstance(campos, dict):
        raise CofreError(f"A credencial «{nome}» não está no formato esperado.")
    return campos


def _meta(nome: str, item: dict) -> dict:
    validade, dias = item.get("validade"), None
    if validade:
        try:
            dias = (date.fromisoformat(str(validade)[:10]) - date.today()).days
        except ValueError:
            dias = None
    return {"nome": nome, "tipo": item.get("tipo"), "nome_do_tipo": NOME_DO_TIPO.get(item.get("tipo"), item.get("tipo")),
            "criado_em": item.get("criado_em"), "criado_por": item.get("criado_por"),
            "alterado_em": item.get("alterado_em"), "alterado_por": item.get("alterado_por"),
            "validade": validade, "dias_para_vencer": dias,
            "campos_presentes": list(item.get("campos_presentes") or [])}


# ------------------------------------------------------------------ o canal com o guardião


#: O nome de cada exceção no canal (o guardião responde `tipo`; quem pede a
#: levanta de novo do lado de cá).
TIPO_DA_RESPOSTA = {"trancado": CofreTrancado, "senha": SenhaErrada, "recusado": CofreRecusado,
                    "inexistente": ItemInexistente, "adulterado": CofreAdulterado}
TIPO_DA_EXCECAO = {v: k for k, v in TIPO_DA_RESPOSTA.items()}


def caminho_do_canal(caminho: Any = None) -> Path:
    return _caminho(caminho).parent / NOME_DO_CANAL


def pedir(acao: str, *, caminho: Any = None, prazo: float = PRAZO_DO_CANAL_S, **dados) -> dict:
    """Um pedido ao guardião, pelo canal local. Sem guardião, o cofre está trancado."""
    canal = caminho_do_canal(caminho)
    try:
        info = json.loads(canal.read_text(encoding="utf-8"))
        with socket.create_connection(("127.0.0.1", int(info["porta"])), timeout=prazo) as s:
            s.sendall((json.dumps({"token": info["token"], "acao": acao, **dados}) + "\n").encode("utf-8"))
            arquivo = s.makefile("rb")
            linha = arquivo.readline()
    except (OSError, ValueError, KeyError) as erro:
        raise CofreTrancado("O cofre está trancado: o guardião do cofre não está rodando nesta "
                            "máquina (ele abre no logon e pede a senha-mestra).") from erro
    resposta = json.loads(linha.decode("utf-8") or "{}")
    if resposta.get("ok"):
        return resposta
    classe = TIPO_DA_RESPOSTA.get(resposta.get("tipo"), CofreError)
    raise classe(resposta.get("erro") or "O guardião recusou o pedido.")


def _em_requisicao_web() -> bool:
    try:
        from flask import has_request_context
    except ImportError:                    # pragma: no cover
        return False
    return bool(has_request_context())


# ------------------------------------------------------------------ a API pública


def ler(nome: Any, *, caminho: Any = None, quem: str = "", processo: str = "") -> dict:
    """Os campos do segredo, EM CLARO, para quem vai usá-los AGORA. **Recusa na web.**

    Pede ao guardião (que registra a leitura: quem, qual item, para qual
    processo). Cofre trancado → `CofreTrancado`.
    """
    if _em_requisicao_web():
        raise CofreRecusado("O segredo do cofre não sai para a tela — só o processo que roda "
                            "fora do servidor o lê.")
    nome = _validar_nome(nome)
    quem = quem or (os.environ.get("USERNAME") or os.environ.get("USER") or "?")
    return pedir("ler", caminho=caminho, nome=nome, quem=quem, processo=processo)["campos"]


def metadados(nome: Any, *, caminho: Any = None) -> dict:
    """Tipo, datas, validade e os NOMES dos campos. Funciona com o cofre trancado."""
    nome = _validar_nome(nome)
    item = carregar(caminho)["itens"].get(nome)
    if not item:
        raise ItemInexistente(f"A credencial «{nome}» não está cadastrada no cofre da automação.")
    return _meta(nome, item)


def listar(*, caminho: Any = None) -> list[dict]:
    """Os metadados de todas. Funciona com o cofre trancado; sem cofre, lista vazia."""
    try:
        itens = carregar(caminho)["itens"]
    except CofreError:
        return []
    return [_meta(n, i) for n, i in sorted(itens.items())]


def tem(nome: Any, *, caminho: Any = None) -> bool:
    return any(m["nome"] == str(nome or "").strip() for m in listar(caminho=caminho))


def gravar(nome: Any, campos: dict, *, tipo: Any, validade: Any = None, por: str,
           caminho: Any = None) -> dict:
    """Cadastra ou substitui. **Exige o cofre aberto** (quem cifra é o guardião)."""
    _validar_nome(nome)
    _campos_limpos(campos)
    return pedir("gravar", caminho=caminho, nome=str(nome).strip(), campos=campos, tipo=tipo,
                 validade=validade, por=por)["metadados"]


def remover(nome: Any, *, por: str, caminho: Any = None) -> bool:
    """Apaga a credencial. **Exige o cofre aberto.**"""
    return bool(pedir("remover", caminho=caminho, nome=_validar_nome(nome), por=por)["removido"])


def estado(*, caminho: Any = None) -> dict:
    """Aberto ou trancado, e desde quando. Sem guardião: trancado, guardião parado."""
    existe = _caminho(caminho).is_file()
    try:
        r = pedir("estado", caminho=caminho, prazo=1.5)
    except CofreError:
        return {"aberto": False, "guardiao": False, "desde": None, "existe": existe, "bloqueado_ate": None}
    return {"aberto": bool(r.get("aberto")), "guardiao": True, "desde": r.get("desde"),
            "existe": existe, "bloqueado_ate": r.get("bloqueado_ate")}


def desbloquear(senha: str, *, caminho: Any = None, confirmacao: str | None = None) -> dict:
    """Repassa a senha ao guardião (a tela local do ADMIN usa isto). Não grava nada."""
    return pedir("desbloquear", caminho=caminho, senha=senha, confirmacao=confirmacao, prazo=60)


def trancar(*, caminho: Any = None) -> dict:
    return pedir("trancar", caminho=caminho)
