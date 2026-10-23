"""
A configuracao do selador: onde ele esta, quem somos nos para ele, e a senha.

O ACHADO QUE DEFINIU ESTE MODULO
    Eu havia suposto que o sistema chamaria o selador do Tribunal pela
    internet. A tabela `tbSeladorConfiguracao` do E-Oficio diz outra coisa, e
    ela tem exatamente tres colunas:

        strUrlSelador  = https://<IP do aparelho na rede local>:443
        strUsername    = «nome.sobrenome», 16 caracteres
        strPassword    = 8 caracteres, EM TEXTO CLARO

    O endereco e de REDE LOCAL. Esta casa nao sela pela internet:
    sela num Selador instalado numa maquina do escritorio, que e quem guarda o
    estoque e conversa com o TJMA. Por isso o endereco e CONFIGURAVEL e nao
    constante — e por isso `selador.py` nao assume base nenhuma.

POR QUE A SENHA NAO ENTRA NO BANCO
    Porque o banco VIAJA. Ele vai no backup, e uma copia dele foi para a minha
    maquina para ensaiar a correcao de 18/08 — se a senha estivesse la, teria
    ido junto. O `secret.key` desta casa ja mora fora do banco, num arquivo da
    pasta de dados, e o backup nao o alcanca (`backup.gerar_pacote` leva o
    banco e a pasta `arquivos`, e mais nada).

    Entao a credencial segue o mesmo caminho: arquivo proprio na pasta de
    dados, ao lado do `secret.key`. No banco fica so o que nao e segredo —
    endereco, usuario, ambiente e a data do ultimo teste.

    Isto NAO e criptografia, e nao vou chamar de criptografia. O servidor
    precisa recuperar a senha em claro para autenticar no Keycloak; qualquer
    esquema que ele consiga desfazer, quem tiver o disco tambem consegue. O
    que se ganha e concreto e vale a pena: a senha deixa de sair de casa
    dentro de backup e de copia de banco.

O QUE ESTE MODULO NAO FAZ
    Nao abre conexao e nao sela. Ele diz onde selar, com que usuario, e se
    esta tudo no lugar para selar. Quem chama e o cliente HTTP, que vem depois.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

import banco_pg
import selador
from bd_nativo import banco

NOME_DO_ARQUIVO = "selador.cred"

AMBIENTES = ("PRODUCAO", "HOMOLOGACAO", "SIMULADO", "SANDBOX")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sd_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    base_url TEXT,
    base_homologacao TEXT,
    -- O endereco de AUTENTICACAO, separado do de selagem.
    --
    -- ISTO CUSTOU UM TRAVAMENTO. Eu tinha deixado a autenticacao apontada para
    -- `selador.AUTH_PRODUCAO`, que e o Keycloak do Tribunal na internet. Numa
    -- casa que sela num aparelho da REDE LOCAL, isso manda a senha da
    -- serventia para fora e trava esperando resposta de um servidor que essa
    -- maquina talvez nem alcance. O teste pegou: o selo nunca voltava.
    --
    -- Vazio quer dizer «no mesmo lugar do selador, em /auth» — que e o
    -- arranjo normal de appliance. So quando a base E a de fabrica e que o
    -- endereco de fabrica entra.
    auth_url TEXT,
    ambiente TEXT NOT NULL DEFAULT 'PRODUCAO',
    usuario TEXT,                       -- identifica, nao autentica
    origem TEXT,                        -- MANUAL | E-OFICIO
    atualizado_em TEXT,
    atualizado_por TEXT,
    ultimo_teste_em TEXT,
    ultimo_teste_ok INTEGER,
    ultimo_teste_mensagem TEXT,
    -- A impressao digital do certificado do selador, em SHA-256.
    --
    -- O selador desta casa e uma maquina da rede local, e maquina de rede
    -- local nao tem certificado assinado por autoridade — tem certificado
    -- proprio. Validar pela cadeia falharia sempre, e desligar a validacao
    -- deixaria qualquer maquina da rede se passar pelo selador.
    --
    -- Entao FIXA-SE o certificado: na primeira conexao o sistema mostra a
    -- impressao digital, o oficial confirma, e dali em diante so aquele
    -- certificado serve. E mais forte que validar cadeia, nao menos.
    certificado_sha256 TEXT,
    certificado_assunto TEXT,
    certificado_valido_ate TEXT,
    certificado_fixado_em TEXT,
    certificado_fixado_por TEXT
);

-- ------------------------------------------------------------- o razao dos selos
--
-- POR QUE ESTA TABELA EXISTE, E ELA E A RESPOSTA A UM DEFEITO MEDIDO
--     No acervo do E-Oficio ha 26.130 selos. MIL TREZENTOS E QUATRO nunca
--     foram usados — 5% —, e apenas CINCO deles foram cancelados. E a marca de
--     quem repetiu a chamada depois de um erro de rede: cada tentativa gerou
--     selo novo, cobrado, e o anterior ficou orfao, sem ato e sem cancelamento.
--
--     Duas coisas fecham esse buraco. A primeira e o SID, que faz a repeticao
--     devolver o mesmo selo. A segunda e esta tabela: todo selo obtido entra
--     aqui NA HORA, antes de o ato ficar pronto. Se o ato falhar depois, o selo
--     esta registrado e aparece na tela de selo obtido e nao usado — em vez de
--     sumir.

CREATE TABLE IF NOT EXISTS sd_selos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    numero TEXT NOT NULL UNIQUE,
    texto TEXT,
    sid TEXT,
    caminho TEXT,                       -- o endpoint que o gerou
    atribuicao TEXT,
    referencia TEXT,                    -- o que identifica o ato na serventia
    tabela TEXT,                        -- preenchidos quando o ato fica pronto
    ato_id INTEGER,
    data_geracao TEXT,
    saldo_remanescente double precision, -- o REAL daqui e float4: perde centavo
    ambiente TEXT NOT NULL DEFAULT 'PRODUCAO',
    obtido_em TEXT NOT NULL,
    obtido_por TEXT,
    usado_em TEXT,
    cancelado_em TEXT,
    cancelado_por TEXT,
    motivo_cancelamento TEXT,

    -- ------------------------------- O QUE VAI DENTRO DO QR DA ETIQUETA
    --
    -- MEDIDO DECODIFICANDO UM QR REAL DO E-OFICIO, em 28/08/2026, depois de o
    -- oficial relatar que «o QR do selo direciona ao site generico».
    --
    --   O QR do TJMA **nao carrega URL nenhuma**. Ele carrega um token de 24
    --   caracteres — `MDGaPtZuqUKD4FtmC82CK5al` no selo que se decodificou —,
    --   e esse token e exatamente o `strvalorQRCode` que o E-Oficio guardava
    --   em `tbSeloIndividual`.
    --
    --   Medido: **25.642 dos 26.130** selos do acervo o tem (24 caracteres em
    --   25.626, e 28 em dezesseis).
    --
    -- POR QUE ISSO IMPORTA: o pedido do oficial — «o QR poderia ja direcionar
    -- a uma consulta ao proprio selo» — nao se resolve inventando um link.
    -- Quem resolve o token e o portal do Tribunal; nos so podemos carregar o
    -- token que o aparelho der.
    --
    -- E O CONTRATO DE 2017 NAO O DEVOLVE: `ResumoSeloGerado` tem `dataGeracao`,
    -- `numeroSelo`, `saldoRemanescente` e `textoSelo`, e mais nada. Para o selo
    -- NOVO o token continua sem vir — e isso e pergunta para quem mantem o
    -- aparelho, e nao coisa que se resolva aqui.
    qr_token TEXT);

CREATE INDEX IF NOT EXISTS ix_sd_selos_sid ON sd_selos(sid);
CREATE INDEX IF NOT EXISTS ix_sd_selos_ato ON sd_selos(tabela, ato_id);
CREATE INDEX IF NOT EXISTS ix_sd_selos_orfao
    ON sd_selos(usado_em, cancelado_em);
"""


class ConfigError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


# A COLUNA NOVA PARA QUEM JA TEM O BANCO. `MIGRACOES` e so
# `ALTER TABLE ADD COLUMN`, como manda a casa.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    ("sd_selos", "qr_token", "TEXT"),
)


def init_selador_schema(con) -> None:
    """Cria a tabela. Idempotente, no padrao do sistema."""
    bd = banco(con)
    # Um comando por `;` de FIM DE LINHA: ha `;` dentro dos comentarios do SCHEMA.
    for comando in re.split(r";[ \t]*$", SCHEMA, flags=re.M):
        if comando.strip():
            bd.escrever(comando)


# ----------------------------------------------------------- a credencial
    for tabela, coluna, tipo in MIGRACOES:
        if not bd.tem_coluna(tabela, coluna):
            bd.escrever(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")

def caminho_da_credencial(pasta_de_dados: Any) -> Path:
    return Path(pasta_de_dados) / NOME_DO_ARQUIVO


def gravar_credencial(pasta_de_dados: Any, usuario: str, senha: str, *,
                      agora: str, usuario_do_sistema: str | None = None) -> Path:
    """Grava usuario e senha no arquivo proprio. Fora do banco, de proposito.

    Restringe a permissao onde o sistema operacional deixa. No Windows o
    `chmod` do Python nao mexe na ACL — a protecao ali e a pasta
    `C:\\ProgramData\\CartorioGestao`, que ja guarda o `secret.key` com o mesmo
    regime. Nao prometo mais do que isso.
    """
    u = (usuario or "").strip()
    s = senha or ""
    if not u:
        raise ConfigError("Informe o usuário do selador.")
    if not s:
        raise ConfigError("Informe a senha do selador.")
    alvo = caminho_da_credencial(pasta_de_dados)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    corpo = json.dumps({"usuario": u, "senha": s, "gravado_em": agora,
                        "gravado_por": usuario_do_sistema},
                       ensure_ascii=False, indent=1)
    provisorio = alvo.with_suffix(alvo.suffix + ".novo")
    provisorio.write_text(corpo, encoding="utf-8")
    try:
        os.chmod(provisorio, 0o600)
    except OSError:
        pass
    provisorio.replace(alvo)
    # a ACL na hora da gravação, e não só na subida (22/10/2026, M6)
    import centrais_cred as _CRED
    _CRED._so_do_servico(alvo)
    return alvo


def ler_credencial(pasta_de_dados: Any) -> dict | None:
    """A credencial em claro, ou None. SO chame na hora de autenticar.

    Todo o resto do sistema — tela, log, auditoria, relatorio — usa
    `situacao()`, que devolve a mesma coisa sem a senha.
    """
    alvo = caminho_da_credencial(pasta_de_dados)
    if not alvo.is_file():
        return None
    try:
        dados = json.loads(alvo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not dados.get("usuario") or not dados.get("senha"):
        return None
    return dados


def apagar_credencial(pasta_de_dados: Any) -> bool:
    alvo = caminho_da_credencial(pasta_de_dados)
    if alvo.is_file():
        alvo.unlink()
        return True
    return False


def mascarar(valor: Any) -> str:
    """`nome.sobrenome` -> `no**********me`. Para tela e para log."""
    texto = str(valor or "")
    if len(texto) <= 4:
        return "*" * len(texto)
    return texto[:2] + "*" * (len(texto) - 4) + texto[-2:]


# ------------------------------------------------------------ a configuracao


def _linha(con) -> dict | None:
    return banco(con).um("SELECT * FROM sd_config WHERE id=1")


def gravar(con, *, base_url: str | None = None,
           base_homologacao: str | None = None, auth_url: str | None = None,
           ambiente: str = "PRODUCAO",
           usuario: str | None = None, origem: str = "MANUAL",
           agora: str, usuario_do_sistema: str | None = None) -> None:
    """Grava o que NAO e segredo. ESCREVE. Dentro da transacao de quem chama."""
    amb = (ambiente or "PRODUCAO").strip().upper()
    if amb not in AMBIENTES:
        raise ConfigError(
            f"Ambiente {ambiente!r} não existe. São {' e '.join(AMBIENTES)}.")
    base = (base_url or "").strip().rstrip("/") or None
    homolog = (base_homologacao or "").strip().rstrip("/") or None
    auth = (auth_url or "").strip().rstrip("/") or None
    for rotulo, url in (("do selador", base), ("de homologação", homolog),
                        ("de autenticação", auth)):
        if url and not url.startswith(("http://", "https://")):
            raise ConfigError(
                f"O endereço {rotulo} precisa começar com http:// ou https:// "
                f"— veio {url!r}.")
    if amb == "HOMOLOGACAO" and not homolog:
        raise ConfigError(
            "Para trabalhar em homologação é preciso o endereço de "
            "homologação. Ele está no sistema antigo, na tela Selador — "
            "Propriedades, campo «URL de Homologação». Sem ele, deixar o "
            "ambiente em homologação faria o sistema selar na produção "
            "achando que era teste.")
    banco(con).escrever(
        """INSERT INTO sd_config(id, base_url, base_homologacao, auth_url,
               ambiente, usuario, origem, atualizado_em, atualizado_por)
           VALUES (1,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT(id) DO UPDATE SET
               base_url=excluded.base_url,
               base_homologacao=excluded.base_homologacao,
               auth_url=excluded.auth_url,
               ambiente=excluded.ambiente,
               usuario=excluded.usuario,
               origem=excluded.origem,
               atualizado_em=excluded.atualizado_em,
               atualizado_por=excluded.atualizado_por""",
        (base, homolog, auth, amb, (usuario or "").strip() or None, origem,
         agora, usuario_do_sistema))


def enderecos_que_mudam(con, *, base_url: str | None = None,
                        base_homologacao: str | None = None,
                        auth_url: str | None = None) -> list[str]:
    """Quais dos tres enderecos o formulario troca. SO LE.

    EXISTE POR CAUSA DO «TESTAR» (LX14; M8 do LS03). O teste manda o usuario
    e a senha do selador para `auth_url`/`base_url`; quem pudesse trocar o
    endereco por um servidor seu e clicar «testar» receberia a senha que
    nunca viu. A rota usa isto para deixar a troca de endereco so ao ADMIN —
    o mesmo dono da senha.
    """
    linha = _linha(con) or {}
    def limpo(url):
        return (url or "").strip().rstrip("/") or None
    novos = (("do selador", "base_url", base_url),
             ("de homologação", "base_homologacao", base_homologacao),
             ("de autenticação", "auth_url", auth_url))
    return [rotulo for rotulo, coluna, url in novos
            if limpo(url) != limpo(linha.get(coluna))]


# O HOST DO SELADOR NA CONFIGURACAO DA SERVENTIA (sanitizacao B0, 05/10/2026).
#     O IP do aparelho desta casa estava escrito no codigo (`selador.py` e este
#     docstring). Agora ele mora em `settings.selador_host` (`serventia.CAMPOS`),
#     e o codigo publico so conhece a semente generica. Quem SELA continua
#     lendo `sd_config.base_url` (abaixo); isto aqui e a SUGESTAO para a tela
#     de configuracao do selador e para a primeira instalacao.


def host_da_serventia(get_settings) -> str:
    """O `selador_host` gravado em settings, ou "" se nao houver. SO LE."""
    s = get_settings() if callable(get_settings) else dict(get_settings or {})
    return str((s or {}).get("selador_host") or "").strip()


def base_sugerida(get_settings, *, porta: int = 443) -> str | None:
    """`https://<selador_host>:<porta>` a partir de settings, ou None.

    NAO cai em endereco nenhum de fabrica nem da casa: sem `selador_host`
    gravado, devolve None e a tela pede o endereco.
    """
    host = host_da_serventia(get_settings)
    if not host:
        return None
    if host.startswith(("http://", "https://")):
        return host.rstrip("/")
    return f"https://{host}:{porta}"


def base_em_uso(con) -> str | None:
    """O endereco do ambiente escolhido, ou None se nao houver.

    NAO cai no endereco de fabrica. Cair no padrao seria mandar para a nuvem do
    Tribunal uma casa que sela num aparelho da sala ao lado — 401 no meio do
    atendimento, ou selo comprado duas vezes.
    """
    linha = _linha(con)
    if not linha:
        return None
    if (linha["ambiente"] or "PRODUCAO") == "HOMOLOGACAO":
        return linha["base_homologacao"] or None
    return linha["base_url"] or None


def auth_em_uso(con) -> str | None:
    """Onde pegar o token. Nunca a nuvem, se a casa sela na rede local.

    Sem `auth_url` gravado, presume-se `<base>/auth` — que e o arranjo normal
    de appliance, e mantem a senha dentro da rede. O endereco de fabrica so
    entra quando a propria base E a de fabrica.
    """
    base = base_em_uso(con)
    if not base:
        return None
    linha = _linha(con)
    proprio = (linha["auth_url"] if linha else None) or None
    if proprio:
        return proprio
    if base.rstrip("/") == selador.BASE_PRODUCAO.rstrip("/"):
        return selador.AUTH_PRODUCAO
    return base.rstrip("/") + "/auth"


def situacao(con, pasta_de_dados: Any) -> dict:
    """Tudo o que a tela precisa saber — e nada do que ela nao pode mostrar."""
    linha = _linha(con)
    cred = ler_credencial(pasta_de_dados)
    base = base_em_uso(con)
    faltas: list[str] = []
    if not linha:
        faltas.append("O selador ainda não foi configurado.")
    if not base:
        faltas.append(
            "Falta o endereço do selador. Nesta serventia ele é uma máquina da "
            "rede local — no sistema antigo aparece na tela Selador — "
            "Propriedades.")
    if not cred:
        faltas.append("Faltam o usuário e a senha do selador.")
    return {
        "configurado": bool(linha),
        "ambiente": (linha["ambiente"] if linha else "PRODUCAO"),
        "base_url": (linha["base_url"] if linha else None),
        "base_homologacao": (linha["base_homologacao"] if linha else None),
        "base_em_uso": base,
        "auth_url": (linha["auth_url"] if linha else None),
        "auth_em_uso": auth_em_uso(con),
        "na_rede_local": bool(base and _e_rede_local(base)),
        "usuario": mascarar(cred["usuario"]) if cred else None,
        "tem_credencial": bool(cred),
        "credencial_em": (cred or {}).get("gravado_em"),
        "origem": (linha["origem"] if linha else None),
        "atualizado_em": (linha["atualizado_em"] if linha else None),
        "atualizado_por": (linha["atualizado_por"] if linha else None),
        "ultimo_teste_em": (linha["ultimo_teste_em"] if linha else None),
        "ultimo_teste_ok": (bool(linha["ultimo_teste_ok"])
                            if linha and linha["ultimo_teste_ok"] is not None
                            else None),
        "ultimo_teste_mensagem": (linha["ultimo_teste_mensagem"] if linha else None),
        "pronto": not faltas,
        "faltas": faltas,
        "padrao_de_fabrica": selador.BASE_PRODUCAO,
    }


def _e_rede_local(url: str) -> bool:
    """Se o endereco e de rede privada — o caso desta serventia.

    Serve para a tela AVISAR: um selador na LAN so responde de dentro do
    escritorio. Quem tenta selar de casa, pela VPN caida, recebe tempo
    esgotado e nao entende por que.
    """
    corpo = str(url or "").split("//", 1)[-1].split("/")[0].split(":")[0]
    if corpo in ("localhost", "127.0.0.1"):
        return True
    partes = corpo.split(".")
    if len(partes) != 4 or not all(p.isdigit() for p in partes):
        return False
    a, b = int(partes[0]), int(partes[1])
    return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)


def registrar_teste(con, *, ok: bool, mensagem: str,
                    agora: str) -> None:
    """Guarda o resultado do ultimo teste de conexao. ESCREVE."""
    banco(con).escrever(
        """UPDATE sd_config SET ultimo_teste_em=%s, ultimo_teste_ok=%s,
                                ultimo_teste_mensagem=%s WHERE id=1""",
        (agora, 1 if ok else 0, (mensagem or "")[:500]))


def credencial_para_autenticar(con,
                               pasta_de_dados: Any) -> dict:
    """O que o cliente HTTP precisa para pegar o token. Recusa pela metade.

    Devolve a senha em claro — e o unico lugar do sistema que o faz. Quem
    chamar isto esta prestes a autenticar; qualquer outro uso e vazamento.
    """
    estado = situacao(con, pasta_de_dados)
    if not estado["pronto"]:
        raise ConfigError(" ".join(estado["faltas"]))
    cred = ler_credencial(pasta_de_dados)
    assert cred is not None
    return {
        "base": estado["base_em_uso"],
        "auth": estado["auth_em_uso"],
        "usuario": cred["usuario"],
        "senha": cred["senha"],
        "client_id": selador.CLIENT_ID,
        "grant_type": selador.GRANT_TYPE,
        "ambiente": estado["ambiente"],
    }


# ------------------------------------------------------- vindo do E-Oficio


def ler_do_eoficio(caminho_do_acervo: Any) -> dict:
    """Le `tbSeladorConfiguracao` do acervo do E-Oficio. SO LE o acervo.

    A tabela tem tres colunas e a senha esta em TEXTO CLARO nela. E por isso
    que esta funcao existe: o dado ja esta na casa, e faze-lo ser redigitado
    seria pedir para o escrevente abrir a tela do E-Oficio, ler uma senha e
    copiar — que e mais exposicao, nao menos.
    """
    caminho = Path(caminho_do_acervo)
    if not caminho.is_file():
        raise ConfigError(
            f"Não achei o acervo do E-Ofício em {caminho}. Ele costuma ficar "
            f"na pasta de dados, com o nome acervo_eoficio.sqlite3.")
    # O ACERVO E UM ARQUIVO SQLITE DE VERDADE, e continua sendo lido como tal:
    # so o banco do sistema foi para o PostgreSQL. Pela porta do SQLite (LH09),
    # que nao decide pelo nome do arquivo como o desvio do `sqlite3.connect`.
    con = banco_pg.conectar_sqlite(caminho)
    try:
        try:
            cur = con.execute("SELECT * FROM tbSeladorConfiguracao")
        except sqlite3.OperationalError as erro:
            if "no such table" not in str(erro):
                raise
            raise ConfigError(
                "O acervo não tem a tabela tbSeladorConfiguracao — este "
                "E-Ofício não guardava a configuração do selador.") from None
        fila = cur.fetchone()
        linha = (dict(zip([d[0] for d in cur.description], fila))
                 if fila else None)
    finally:
        con.close()
    if not linha:
        raise ConfigError("A tabela tbSeladorConfiguracao do acervo está vazia.")
    return {
        "base_url": (linha["strUrlSelador"] or "").strip() or None,
        "usuario": (linha["strUsername"] or "").strip() or None,
        "senha": linha["strPassword"] or None,
    }


def importar_do_eoficio(con, caminho_do_acervo: Any,
                        pasta_de_dados: Any, *, agora: str,
                        usuario_do_sistema: str | None = None) -> dict:
    """Traz endereco, usuario e senha do E-Oficio. ESCREVE nos dois lugares.

    Devolve o resumo SEM a senha — nem para a tela, nem para a auditoria.
    """
    achado = ler_do_eoficio(caminho_do_acervo)
    faltando = [k for k in ("base_url", "usuario", "senha") if not achado.get(k)]
    if faltando:
        raise ConfigError(
            f"A configuração do E-Ofício veio incompleta: falta "
            f"{', '.join(faltando)}. Complete à mão na tela do selador.")
    gravar(con, base_url=achado["base_url"], ambiente="PRODUCAO",
           usuario=achado["usuario"], origem="E-OFICIO", agora=agora,
           usuario_do_sistema=usuario_do_sistema)
    gravar_credencial(pasta_de_dados, achado["usuario"], achado["senha"],
                      agora=agora, usuario_do_sistema=usuario_do_sistema)
    return {
        "base_url": achado["base_url"],
        "usuario": mascarar(achado["usuario"]),
        "senha": "«não registrada em lugar nenhum além do arquivo próprio»",
        "na_rede_local": _e_rede_local(achado["base_url"]),
        "origem": "E-OFICIO",
    }
