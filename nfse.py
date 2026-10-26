"""A NFS-e DOS EMOLUMENTOS — uma nota por recibo, pelo emissor nacional.

POR QUE EXISTE (LG01, 19/10/2026)
    O oficial precisa começar a emitir NFS-e, uma por cliente (o tomador), dos
    emolumentos recebidos. A prefeitura usa o EMISSOR NACIONAL (Sefin Nacional
    / ADN — confirmado por ele em 19/10). O ponto de partida é o RECIBO: é ele
    a prova do pagamento (Código de Normas do MA, art. 87, IX — «dar recibo dos
    emolumentos percebidos»), tem número por exercício e teor congelado, e já
    diz quem pagou. A nota nasce do recibo, e o número e a chave dela voltam
    para ele (`cx_recibos.nfse_numero` e `nfse_chave`).

A BASE DO ISS É O EMOLUMENTO, E SÓ ELE — A ESCOLHA, E POR QUÊ
    O recibo junta duas coisas que não são da mesma natureza: o EMOLUMENTO,
    que é o preço do serviço do delegatário, e os FUNDOS (FERC, FADEP, FEMP,
    FERRFIS), que a lei manda cobrar junto e que a serventia só repassa. O
    sistema já separa os dois em cada lançamento (`cx_lancamentos.emolumentos`
    e as colunas de cada fundo), e o ISS nunca entra na conta do cliente
    (`custas.py`, conferido em 400 valores reais de 2026). O Código de Normas
    do MA também os escritura separados: o Livro Diário Auxiliar leva «valor
    discriminado dos emolumentos», «do FERJ» e «do ISSQN» em colunas próprias
    (art. 190, I, j a l).

    **NO MARANHÃO, A BASE É O EMOLUMENTO MENOS O FERJ** (o oficial, em
    25/10/2026: «no Maranhão a base de cálculo do tributo deve ser
    Emolumentos − FERJ»). O FERJ NÃO é o FERC — correção do mesmo dia, do
    oficial: «ferj e ferc são diferentes; ferj é uns 12%, ferc é 3%, mas não
    abate dos emolumentos». O FERJ é a taxa de fiscalização de 12% «sobre os
    valores efetivamente devidos de emolumentos» (LC estadual 48/2000, art.
    3º, V), que a serventia recolhe toda semana ao Tribunal: sai de DENTRO do
    emolumento, e não é coluna do caixa. O FERC (3%) é cobrado por cima e
    não se desconta. O percentual é configuração (`nfse_percentual_ferj`,
    12,00 por padrão), porque lei muda e outra unidade da federação não o tem.

    Por isso o valor do serviço na DPS é a SOMA DOS EMOLUMENTOS MENOS O FERJ
    dos lançamentos do recibo, e os fundos ficam fora — ditos na descrição, para
    quem ler a nota saber que o cliente pagou mais do que o serviço. Repasse
    a terceiro não é receita do prestador, e tributá-lo seria pagar ISS sobre
    dinheiro do Tribunal, do MP e da Defensoria. **Se a lei do município
    disser outra coisa, a regra muda aqui, em `base_do_recibo`, e em mais
    lugar nenhum** — conferir com a prefeitura antes de ligar a produção.

    Lançamento que não separa emolumento de fundo (lançamento manual sem as
    parcelas) NÃO vira base por palpite: vira pendência, com o número do
    lançamento. Recibo cujo emolumento é zero (ato gratuito) não tem nota.

QUEM É O TOMADOR
    Quem está no recibo: `pagador` e `pagador_documento`. O recibo não guarda
    endereço em partes (CEP, município, logradouro), e o leiaute pede em
    partes; o balcão completa na tela da pendência e o cadastro fica em
    `nfse_tomadores`, pelo CPF/CNPJ, para o próximo recibo da mesma pessoa.
    O teor do recibo NÃO se corrige: quando falta o documento ou o nome
    nele, o que o balcão digita mora em `nfse_tomador_do_recibo`. É dado
    pessoal tratado por obrigação legal (LGPD, art. 7º, II) e não sai em
    rastro nenhum: a auditoria leva o CPF mascarado.

O CAMINHO DA NOTA, E POR QUE SÃO DUAS TRANSAÇÕES
    1. `preparar` (na transação da rota): confere as pendências, numera a DPS
       sob trava, monta, assina e grava a nota como ENVIANDO.
    2. `enviar` (fora de qualquer transação): fala com o emissor, e grava o
       resultado numa transação curta. **A rede nunca roda com a trava do
       banco presa** — um emissor lento não pode parar o caixa inteiro.

    O REENVIO É IDEMPOTENTE: a DPS tem `Id` fixo (município + prestador +
    série + número). Uma nota que ficou ENVIANDO porque a rede caiu é
    reenviada com o MESMO XML; antes de reenviar, a casa pergunta à Sefin se
    aquela DPS já virou nota, e só manda de novo se não virou. Dois cliques
    juntos mandam a mesma DPS e recebem a mesma chave.

DESLIGADA POR PADRÃO
    `nfse_ligada` nasce «0» e o ambiente nasce «homologacao». Quem liga é o
    ADMIN, no Gestor. O certificado A1 (`.pfx`) e a senha dele moram FORA do
    banco e fora do código, na mesma pasta do `selador.cred` e dos `.cred`
    das Centrais (`centrais_cred.pasta_de_dados`) — o backup do banco sai da
    serventia, e o certificado não pode ir junto.

BASE NORMATIVA
    LC 116/2003, item 21.01 da lista (serviços de registros públicos,
    cartorários e notariais) e art. 8º, II (alíquota máxima de 5%); Código de
    Normas do MA (Prov. COGEX 28/2026), arts. 87, IX, e 190, I, j a l; o
    leiaute da DPS e a API da Sefin Nacional estão na documentação técnica do
    emissor nacional (gov.br/nfse) — conferir no texto oficial a versão
    vigente antes de ligar a produção.
"""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import cpf_cnpj
import nfse_dps as DPS
import nfse_provedor as PROV
from bd_nativo import banco
from caixa_schema import centavos, reais
from serventia import mascarar_documento

ENVIANDO, EMITIDA, REJEITADA, CANCELADA = "ENVIANDO", "EMITIDA", "REJEITADA", "CANCELADA"
SITUACOES = {
    ENVIANDO: "Enviada, aguardando a resposta do emissor",
    EMITIDA: "Emitida",
    REJEITADA: "Recusada pelo emissor — corrija e reenvie",
    CANCELADA: "Cancelada",
}

ARQUIVO_DO_CERTIFICADO = "nfse_a1.pfx"
ARQUIVO_DA_SENHA = "nfse.cred"

FUNDOS_FORA_DA_BASE = ("ferc", "fadep", "femp", "ferrfis")

# A CONFIGURAÇÃO, COM O PADRÃO DE QUEM NUNCA MEXEU. Mora em `settings`; o que
# não está gravado vale isto. **Ligada nasce «0» e o ambiente nasce
# homologação**: começar pela produção por omissão é emitir nota de verdade
# no primeiro teste.
PADRAO: dict[str, str] = {
    "nfse_ligada": "0",
    "nfse_provedor": PROV.NACIONAL,
    "nfse_ambiente": "homologacao",
    "nfse_municipio": "",                 # código IBGE do município (7 dígitos)
    "nfse_prestador_documento": "",       # CNPJ da serventia ou CPF do delegatário
    "nfse_inscricao_municipal": "",
    "nfse_codigo_tributacao": "210101",   # cTribNac: item 21.01 da LC 116
    "nfse_codigo_municipal": "",
    "nfse_aliquota": "",                  # «5,00»; vazio = a do cadastro do município
    "nfse_optante_simples": "1",          # opSimpNac: 1 = não optante
    "nfse_regime_especial": "4",          # regEspTrib: 4 = notário ou registrador
    "nfse_serie": "1",
    "nfse_exige_endereco": "1",
    "nfse_inicio": "",                    # só recibos emitidos a partir desta data
    # cNBS: «1.1304.00.00 — Serviços notariais e de registro», Anexo B v1.01
    # (lista NBS 2.0) do gov.br/nfse, medido em 24/10/2026.
    "nfse_codigo_nbs": "113040000",
    # O FERJ (Maranhão): 12% «sobre os valores efetivamente devidos de
    # emolumentos» (LC estadual 48/2000, art. 3º, V). Sai da base da nota.
    "nfse_percentual_ferj": "12,00",
    # O CONVÊNIO DO MUNICÍPIO NO SISTEMA NACIONAL: «1» ativo, «0» não, vazio
    # não conferido. Quem marca é o ADMIN, depois de ler os parâmetros que o
    # emissor devolve (`conferir_no_emissor`). Ele decide a alíquota: com
    # convênio ativo e serventia fora do Simples, a regra E0617 do Anexo I
    # recusa a DPS que informa a alíquota (ela vem do cadastro do município).
    "nfse_convenio_ativo": "",
    # O GRUPO DO IBS/CBS (LC 214/2025). Vazios, a nota sai sem o grupo — o
    # que a NT 004 v2.0 (10/12/2025) manteve aceito. CST e classificação são
    # decisão de quem responde pelo tributo, e por isso não têm padrão; o
    # indicador da operação nasce em 100301 (Anexo C: «demais serviços, em
    # operações onerosas — local do domicílio principal do adquirente»), que
    # também se confere com o contador.
    "nfse_ibscbs_cst": "",
    "nfse_ibscbs_classificacao": "",
    "nfse_ibscbs_indicador_operacao": "100301",
}

ROTULOS: dict[str, str] = {
    "nfse_ligada": "Emissão ligada",
    "nfse_provedor": "Provedor",
    "nfse_ambiente": "Ambiente",
    "nfse_municipio": "Município (código IBGE)",
    "nfse_prestador_documento": "CNPJ/CPF do prestador",
    "nfse_inscricao_municipal": "Inscrição municipal",
    "nfse_codigo_tributacao": "Código de tributação nacional",
    "nfse_codigo_municipal": "Código de tributação municipal",
    "nfse_aliquota": "Alíquota do ISS (%)",
    "nfse_optante_simples": "Simples Nacional",
    "nfse_regime_especial": "Regime especial de tributação",
    "nfse_serie": "Série da DPS",
    "nfse_exige_endereco": "Exigir endereço do tomador",
    "nfse_inicio": "Emitir para recibos a partir de",
    "nfse_codigo_nbs": "Código NBS",
    "nfse_percentual_ferj": "Percentual do FERJ descontado da base (%)",
    "nfse_convenio_ativo": "Convênio do município no emissor nacional",
    "nfse_ibscbs_cst": "CST do IBS/CBS",
    "nfse_ibscbs_classificacao": "Classificação tributária do IBS/CBS (cClassTrib)",
    "nfse_ibscbs_indicador_operacao": "Indicador da operação (cIndOp)",
}

CONVENIO = {"": "Não conferido", "1": "Ativo", "0": "Não ativo"}

REGIMES_ESPECIAIS = {
    "0": "Nenhum", "1": "Ato cooperado", "2": "Estimativa",
    "3": "Microempresa municipal", "4": "Notário ou registrador",
    "5": "Profissional autônomo", "6": "Sociedade de profissionais",
}
OPCOES_SIMPLES = {"1": "Não optante", "2": "MEI", "3": "ME/EPP"}
AMBIENTES = {"homologacao": "Homologação (produção restrita, sem valor fiscal)",
             "producao": "Produção"}

CAMPOS_DO_TOMADOR = ("documento", "nome", "cep", "municipio", "logradouro",
                     "numero", "complemento", "bairro", "email")

# TABELAS NOVAS, UM COMANDO POR LINHA, E CADA UM SÓ SE O OBJETO FALTA — o
# `to_regclass` acha tabela e índice. As duas colunas do recibo entram pelo
# `tem_coluna`, logo abaixo.
SCHEMA: tuple[tuple[str, str], ...] = (
    ("nfse_notas", """
        CREATE TABLE IF NOT EXISTS nfse_notas (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            recibo_id bigint NOT NULL REFERENCES cx_recibos(id),
            provedor TEXT NOT NULL,
            ambiente TEXT NOT NULL CHECK (ambiente IN ('homologacao', 'producao')),
            situacao TEXT NOT NULL
                CHECK (situacao IN ('ENVIANDO', 'EMITIDA', 'REJEITADA', 'CANCELADA')),
            serie TEXT NOT NULL,
            numero_dps bigint NOT NULL,
            id_dps TEXT NOT NULL,
            tomador_documento TEXT NOT NULL,
            tomador_nome TEXT NOT NULL,
            valor_servico bigint NOT NULL,
            aliquota TEXT NOT NULL DEFAULT '',
            valor_iss bigint,
            xml_dps TEXT NOT NULL,
            chave TEXT,
            numero_nfse TEXT,
            xml_nfse TEXT,
            danfse bytea,
            mensagem TEXT NOT NULL DEFAULT '',
            tentativas integer NOT NULL DEFAULT 0,
            criado_em TEXT NOT NULL,
            criado_por TEXT NOT NULL DEFAULT '',
            enviado_em TEXT,
            emitida_em TEXT,
            cancelada_em TEXT,
            cancelada_por TEXT,
            motivo_cancelamento TEXT,
            UNIQUE (ambiente, id_dps),
            UNIQUE (ambiente, serie, numero_dps)
        )"""),
    # UMA NOTA VIVA POR RECIBO EM CADA AMBIENTE, e a trava mora no banco. A
    # cancelada sai da regra, porque cancelar por erro e emitir de novo é o
    # caminho legítimo. O ambiente entra na chave porque a nota da homologação
    # não tem valor fiscal: o teste do oficial não pode impedir a nota de
    # verdade do mesmo recibo quando a casa passar à produção.
    ("ux_nfse_notas_recibo", """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_nfse_notas_recibo
            ON nfse_notas (recibo_id, ambiente) WHERE situacao <> 'CANCELADA'"""),
    ("ux_nfse_notas_chave", """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_nfse_notas_chave
            ON nfse_notas (ambiente, chave) WHERE chave IS NOT NULL"""),
    ("ix_nfse_notas_situacao",
     "CREATE INDEX IF NOT EXISTS ix_nfse_notas_situacao ON nfse_notas (situacao, id)"),
    ("nfse_eventos", """
        CREATE TABLE IF NOT EXISTS nfse_eventos (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            nota_id bigint NOT NULL REFERENCES nfse_notas(id),
            quando TEXT NOT NULL,
            operacao TEXT NOT NULL,
            resultado TEXT NOT NULL,
            mensagem TEXT NOT NULL DEFAULT '',
            usuario TEXT NOT NULL DEFAULT ''
        )"""),
    ("ix_nfse_eventos_nota",
     "CREATE INDEX IF NOT EXISTS ix_nfse_eventos_nota ON nfse_eventos (nota_id, id)"),
    ("nfse_tomadores", """
        CREATE TABLE IF NOT EXISTS nfse_tomadores (
            documento TEXT PRIMARY KEY,
            nome TEXT NOT NULL DEFAULT '',
            cep TEXT NOT NULL DEFAULT '',
            municipio TEXT NOT NULL DEFAULT '',
            logradouro TEXT NOT NULL DEFAULT '',
            numero TEXT NOT NULL DEFAULT '',
            complemento TEXT NOT NULL DEFAULT '',
            bairro TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            atualizado_por TEXT NOT NULL DEFAULT '',
            atualizado_em TEXT NOT NULL DEFAULT ''
        )"""),
    ("nfse_tomador_do_recibo", """
        CREATE TABLE IF NOT EXISTS nfse_tomador_do_recibo (
            recibo_id bigint PRIMARY KEY REFERENCES cx_recibos(id),
            documento TEXT NOT NULL,
            nome TEXT NOT NULL DEFAULT '',
            atualizado_por TEXT NOT NULL DEFAULT '',
            atualizado_em TEXT NOT NULL DEFAULT ''
        )"""),
)

COLUNAS_DO_RECIBO = (("nfse_numero", "TEXT"), ("nfse_chave", "TEXT"))


class NfseError(ValueError):
    """Impedimento da emissão, com a frase pronta para o balcão."""


class Pendente(NfseError):
    """O recibo ainda não pode virar nota. `pendencias` diz o que falta."""

    def __init__(self, pendencias: list[str]):
        super().__init__("; ".join(pendencias))
        self.pendencias = list(pendencias)


def init_nfse_schema(con) -> None:
    """Cria as tabelas `nfse_*` e as colunas do recibo que faltarem. Idempotente.

    Depois do caixa: as notas apontam para `cx_recibos`.
    """
    bd = banco(con)
    for nome, comando in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(comando)
    for coluna, tipo in COLUNAS_DO_RECIBO:
        if not bd.tem_coluna("cx_recibos", coluna):
            bd.escrever(f"ALTER TABLE cx_recibos ADD COLUMN {coluna} {tipo}")


def _agora() -> datetime:
    """A hora da emissão, com o fuso, calculada no Python (regra da casa)."""
    return datetime.now().astimezone().replace(microsecond=0)


def _carimbo(quando: datetime) -> str:
    return quando.replace(tzinfo=None).isoformat(timespec="seconds")


def _curto(valor: Any, limite: int = 300) -> str:
    return " ".join(str(valor or "").split())[:limite]


# ------------------------------------------------------------ a configuração

def configuracao(con) -> dict[str, str]:
    """O que está gravado, sobre o padrão. Só LÊ."""
    gravado = {r["key"]: r["value"] for r in banco(con).ler(
        "SELECT key, value FROM settings WHERE key = ANY(%s) ORDER BY key",
        (list(PADRAO),))}
    return {k: (gravado.get(k) if gravado.get(k) is not None else v)
            for k, v in PADRAO.items()}


def ligada(cfg: Mapping[str, str]) -> bool:
    return str(cfg.get("nfse_ligada") or "0") == "1"


def conferir_configuracao(valores: Mapping[str, Any]) -> dict[str, str]:
    """Normaliza o formulário do Gestor e recusa o que não cabe. Só calcula."""
    novo = {k: _curto(valores.get(k, PADRAO[k]), 60) for k in PADRAO}
    novo["nfse_ligada"] = "1" if str(valores.get("nfse_ligada") or "") in ("1", "on") else "0"
    novo["nfse_exige_endereco"] = (
        "1" if str(valores.get("nfse_exige_endereco") or "") in ("1", "on") else "0")
    if novo["nfse_ambiente"] not in AMBIENTES:
        raise NfseError("Ambiente desconhecido.")
    if novo["nfse_provedor"] not in PROV.PROVEDORES:
        raise NfseError("Provedor desconhecido.")
    if novo["nfse_regime_especial"] not in REGIMES_ESPECIAIS:
        raise NfseError("Regime especial desconhecido.")
    if novo["nfse_optante_simples"] not in OPCOES_SIMPLES:
        raise NfseError("Opção do Simples Nacional desconhecida.")
    for chave in ("nfse_municipio", "nfse_prestador_documento", "nfse_inscricao_municipal",
                  "nfse_codigo_tributacao", "nfse_codigo_municipal", "nfse_serie",
                  "nfse_codigo_nbs", "nfse_ibscbs_cst", "nfse_ibscbs_classificacao",
                  "nfse_ibscbs_indicador_operacao"):
        novo[chave] = DPS.digitos(novo[chave])
    if novo["nfse_convenio_ativo"] not in CONVENIO:
        raise NfseError("Situação do convênio desconhecida.")
    percentual_ferj(novo)
    if novo["nfse_codigo_nbs"] and len(novo["nfse_codigo_nbs"]) != 9:
        raise NfseError("O código NBS tem 9 dígitos (1.1304.00.00 = 113040000).")
    if novo["nfse_ibscbs_cst"] or novo["nfse_ibscbs_classificacao"]:
        try:
            DPS.conferir_ibscbs(_ibscbs(novo, exigir=True))
        except DPS.DpsError as erro:
            raise NfseError(str(erro)) from erro
    if novo["nfse_municipio"] and len(novo["nfse_municipio"]) != 7:
        raise NfseError("O código IBGE do município tem 7 dígitos.")
    doc = novo["nfse_prestador_documento"]
    if doc and cpf_cnpj.documento_valido(doc) is not True:
        raise NfseError("O CNPJ/CPF do prestador não confere.")
    if novo["nfse_codigo_tributacao"] and len(novo["nfse_codigo_tributacao"]) != 6:
        raise NfseError("O código de tributação nacional tem 6 dígitos (210101 = item 21.01).")
    if novo["nfse_aliquota"]:
        try:
            DPS.aliquota_decimal(novo["nfse_aliquota"])
        except DPS.DpsError as erro:
            raise NfseError(str(erro)) from erro
    if novo["nfse_inicio"]:
        try:
            datetime.strptime(novo["nfse_inicio"], "%Y-%m-%d")
        except ValueError as erro:
            raise NfseError("A data de início é dia/mês/ano (AAAA-MM-DD).") from erro
    return novo


def gravar_configuracao(con, valores: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    """Grava a configuração do Gestor. ESCREVE. Devolve o que mudou (de, para).

    O que mudou vai ao rastro inteiro — não há segredo aqui: o certificado e
    a senha dele não passam por `settings`.
    """
    novo = conferir_configuracao(valores)
    bd = banco(con)
    antes = configuracao(bd)
    for chave, valor in novo.items():
        bd.escrever(
            "INSERT INTO settings (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (chave, valor))
    return {k: (antes[k], v) for k, v in novo.items() if antes[k] != v}


# --------------------------------------------------------- o certificado A1

def pasta_da_credencial(pasta: Any = None) -> Path:
    """Onde o backup não alcança — a mesma do `selador.cred` e das Centrais."""
    if pasta:
        return Path(pasta)
    import centrais_cred
    return centrais_cred.pasta_de_dados()


def gravar_certificado(conteudo: bytes, senha: str, pasta: Any = None) -> dict:
    """Confere e guarda o `.pfx` e a senha. ESCREVE EM DISCO, não no banco."""
    if not conteudo:
        raise NfseError("Escolha o arquivo .pfx do certificado A1.")
    try:
        cert = DPS.abrir_pfx(conteudo, senha)
    except DPS.DpsError as erro:
        raise NfseError(str(erro)) from erro
    destino = pasta_da_credencial(pasta)
    destino.mkdir(parents=True, exist_ok=True)
    for nome, dados in ((ARQUIVO_DO_CERTIFICADO, conteudo),
                        (ARQUIVO_DA_SENHA, json.dumps({"senha": senha}).encode("utf-8"))):
        alvo = destino / nome
        provisorio = alvo.with_suffix(alvo.suffix + ".novo")
        provisorio.write_bytes(dados)
        try:
            os.chmod(provisorio, 0o600)
        except OSError:      # o Windows ignora o modo; a pasta já é só do serviço
            pass
        os.replace(provisorio, alvo)
        # o `.pfx` e a senha dele só do serviço, na hora (22/10/2026, M6)
        import centrais_cred as _CRED
        _CRED._so_do_servico(alvo)
    return _resumo_do_certificado(cert)


def apagar_certificado(pasta: Any = None) -> None:
    for nome in (ARQUIVO_DO_CERTIFICADO, ARQUIVO_DA_SENHA):
        (pasta_da_credencial(pasta) / nome).unlink(missing_ok=True)


def tem_certificado(pasta: Any = None) -> bool:
    p = pasta_da_credencial(pasta)
    return (p / ARQUIVO_DO_CERTIFICADO).is_file() and (p / ARQUIVO_DA_SENHA).is_file()


def ler_certificado(pasta: Any = None) -> DPS.CertificadoA1:
    """Abre o A1 guardado. Quem chama está prestes a ASSINAR — e só ele."""
    p = pasta_da_credencial(pasta)
    if not tem_certificado(p):
        raise NfseError("O certificado A1 da serventia não foi gravado. "
                        "Grave-o no Gestor → NFS-e.")
    try:
        senha = json.loads((p / ARQUIVO_DA_SENHA).read_text(encoding="utf-8-sig"))["senha"]
    except (OSError, ValueError, KeyError) as erro:
        raise NfseError("O arquivo da senha do certificado está ilegível. "
                        "Grave o certificado de novo no Gestor.") from erro
    try:
        return DPS.abrir_pfx((p / ARQUIVO_DO_CERTIFICADO).read_bytes(), senha)
    except DPS.DpsError as erro:
        raise NfseError(str(erro)) from erro


def _resumo_do_certificado(cert: DPS.CertificadoA1) -> dict:
    agora = datetime.now().astimezone()
    return {"titular": cert.titular,
            "valido_ate": cert.valido_ate.astimezone().date().isoformat(),
            "vencido": cert.valido_ate < agora}


def resumo_do_certificado(pasta: Any = None) -> dict | None:
    """Titular e validade do A1 guardado, para a tela. **Sem a senha.**"""
    if not tem_certificado(pasta):
        return None
    try:
        return _resumo_do_certificado(ler_certificado(pasta))
    except NfseError as erro:
        return {"titular": "", "valido_ate": "", "vencido": True, "erro": str(erro)}


def _ibscbs(cfg: Mapping[str, str], *, exigir: bool = False) -> DPS.IbsCbs | None:
    """O grupo do IBS/CBS da configuração, ou None quando a casa não o preencheu."""
    cst = DPS.digitos(cfg.get("nfse_ibscbs_cst"))
    classe = DPS.digitos(cfg.get("nfse_ibscbs_classificacao"))
    if not (cst or classe) and not exigir:
        return None
    return DPS.IbsCbs(cst=cst, classificacao=classe,
                      indicador_operacao=DPS.digitos(cfg.get("nfse_ibscbs_indicador_operacao")))


def aliquota_para_a_dps(cfg: Mapping[str, str]) -> str:
    """A alíquota que VAI na DPS — que nem sempre é a configurada.

    Regra E0617 do Anexo I v1.01: prestador fora do Simples (opSimpNac = 1)
    com o convênio do município ATIVO não pode informar `pAliq` — a Sefin a
    tira do cadastro do município. A configurada continua servindo à
    estimativa do ISS na fila; na nota, a que vale é a da Sefin.
    """
    if (str(cfg.get("nfse_optante_simples") or "1") == "1"
            and str(cfg.get("nfse_convenio_ativo") or "") == "1"):
        return ""
    return cfg.get("nfse_aliquota") or ""


def avisos_da_configuracao(cfg: Mapping[str, str]) -> list[str]:
    """O que não impede a nota, mas o ADMIN precisa saber. Só calcula."""
    avisos = []
    if not str(cfg.get("nfse_convenio_ativo") or ""):
        avisos.append("O convênio do município no emissor nacional não foi conferido: "
                      "use «Consultar os parâmetros do município» e marque a situação. "
                      "Ele decide se a alíquota pode ir na nota (regra E0617).")
    if _ibscbs(cfg) is None:
        avisos.append("A nota sai sem o grupo do IBS/CBS da reforma tributária (aceito "
                      "pela NT 004 v2.0 enquanto as validações dele estão suspensas). "
                      "Preencha o CST e a classificação tributária com o contador.")
    return avisos


def pendencias_da_configuracao(cfg: Mapping[str, str], pasta: Any = None) -> list[str]:
    """O que falta na casa para qualquer nota sair. Só LÊ."""
    faltas = []
    if not ligada(cfg):
        faltas.append("A emissão de NFS-e está desligada (Gestor → NFS-e).")
    if len(cfg.get("nfse_municipio") or "") != 7:
        faltas.append("Falta o código IBGE do município.")
    if cpf_cnpj.documento_valido(cfg.get("nfse_prestador_documento")) is not True:
        faltas.append("Falta o CNPJ/CPF do prestador.")
    if len(DPS.digitos(cfg.get("nfse_codigo_tributacao"))) != 6:
        faltas.append("Falta o código de tributação nacional (210101 = item 21.01).")
    resumo = resumo_do_certificado(pasta)
    if resumo is None:
        faltas.append("Falta o certificado A1 da serventia.")
    elif resumo.get("erro"):
        faltas.append(resumo["erro"])
    elif resumo["vencido"]:
        faltas.append(f"O certificado A1 venceu em {resumo['valido_ate']}.")
    return faltas


# ------------------------------------------------------- o recibo e a base

def _vazio(valor: Any) -> bool:
    return valor is None or not str(valor).strip()


def percentual_ferj(cfg: Mapping[str, Any]) -> int:
    """O percentual do FERJ em centésimos de ponto (12,00% → 1200). Só calcula."""
    texto = str(cfg.get("nfse_percentual_ferj") or "0").strip().replace("%", "").replace(",", ".")
    try:
        numero = float(texto or "0")
    except ValueError as erro:
        raise NfseError(f"Percentual do FERJ ilegível: «{texto}».") from erro
    if not 0 <= numero < 100:
        raise NfseError("O percentual do FERJ fica entre 0 e 100.")
    return round(numero * 100)


def ferj_do_emolumento(emolumento: int, pct_centesimos: int) -> int:
    """O FERJ que sai de dentro do emolumento, em centavos, arredondado ao centavo."""
    return (int(emolumento) * int(pct_centesimos) + 5000) // 10000


def base_do_recibo(recibo: Mapping[str, Any],
                   lancamentos: Iterable[Mapping[str, Any]],
                   pct_ferj: int = 0) -> tuple[int, list[str]]:
    """O valor do serviço (em centavos) e o que impede de calculá-lo. Só calcula.

    A SOMA DOS EMOLUMENTOS dos lançamentos do recibo, MENOS O FERJ — e não o
    total, que leva os fundos (ver o topo deste módulo). O FERJ não é coluna
    do caixa: é um percentual do emolumento que a serventia recolhe ao
    Tribunal (`pct_ferj`, em centésimos de ponto). Estornado, excluído e saída
    não contam. Lançamento sem parcela nenhuma separada é pendência: adivinhar
    a base é declarar ao fisco um número que ninguém conferiu.
    """
    vivos = [l for l in lancamentos
             if not l.get("estornado") and not l.get("excluido")
             and (l.get("sentido") or "ENTRADA") == "ENTRADA"]
    pendencias = []
    if vivos:
        base = 0
        for l in vivos:
            if all(_vazio(l.get(c)) for c in ("emolumentos",) + FUNDOS_FORA_DA_BASE):
                numero = f"{l['numero']}/{l['ano']}" if l.get("numero") else f"id {l['id']}"
                pendencias.append(
                    f"O lançamento {numero} não separa o emolumento dos fundos: "
                    f"corrija-o no caixa antes de emitir.")
                continue
            base += centavos(l.get("emolumentos"))
        return base - ferj_do_emolumento(base, pct_ferj), pendencias
    # Recibo sem lançamento ligado (o que veio de carga antiga): vale a
    # discriminação congelada nele, se ela disser o emolumento.
    try:
        fundos = (json.loads(recibo.get("discriminacao") or "{}") or {}).get("fundos") or {}
    except ValueError:
        fundos = {}
    if "emolumentos" in fundos:
        emolumento = centavos(fundos["emolumentos"])
        return emolumento - ferj_do_emolumento(emolumento, pct_ferj), []
    return 0, ["O recibo não diz quanto do valor é emolumento."]


def valor_do_iss(base: int, aliquota: Any) -> int | None:
    """O ISS da nota, em centavos, arredondado ao centavo. None sem alíquota."""
    texto = DPS.aliquota_decimal(aliquota)
    if not texto:
        return None
    centesimos = int(round(float(texto) * 100))
    return (int(base) * centesimos + 5000) // 10000


def descricao_do_servico(recibo: Mapping[str, Any], base: int) -> str:
    """O texto da nota: o que se pagou, sem dado pessoal do tomador."""
    try:
        dados = json.loads(recibo.get("discriminacao") or "{}") or {}
    except ValueError:
        dados = {}
    itens = []
    for item in dados.get("itens") or []:
        if not isinstance(item, dict):
            continue
        rotulo = " ".join(p for p in (str(item.get("codigo_ato") or "").strip(),
                                      str(item.get("descricao") or "").strip()) if p)
        qtd = int(item.get("quantidade") or 1)
        if rotulo:
            itens.append(f"{rotulo}{f' (x{qtd})' if qtd > 1 else ''}")
    protocolo = recibo.get("protocolo_numero")
    partes = [f"Emolumentos de serviços notariais e de registro (LC 116, item 21.01) — "
              f"recibo nº {recibo['numero']}/{recibo['ano']}"
              + (f", protocolo {protocolo}" if protocolo else "") + "."]
    if itens:
        partes.append("Atos: " + "; ".join(itens) + ".")
    total = centavos(recibo.get("valor_total"))
    if total > base:
        partes.append(
            # Sem a lista fechada de fundos: o lançamento também tem `fermoju`
            # e `outros` (caixa_schema.FUNDOS), e a frase não pode deixá-los de fora.
            f"Valor total do recibo R$ {reais(total)}, dos quais R$ {reais(total - base)} "
            f"não integram a base do serviço: fundos e taxas cobrados por força de lei "
            f"(como FERC, FADEP, FEMP e FERRFIS) e o FERJ, que sai do emolumento; no "
            f"Maranhão, a base é o emolumento menos o FERJ.")
    return " ".join(partes)


def _lancamentos_de(bd, recibo_ids: list[int]) -> dict[int, list[dict]]:
    por_recibo: dict[int, list[dict]] = {r: [] for r in recibo_ids}
    if not recibo_ids:
        return por_recibo
    for l in bd.ler(
            """SELECT id, recibo_id, numero, ano, sentido, valor, emolumentos,
                      ferc, fadep, femp, ferrfis, estornado,
                      COALESCE(excluido, 0) AS excluido
                 FROM cx_lancamentos WHERE recibo_id = ANY(%s)
                ORDER BY recibo_id, id""", (recibo_ids,)):
        por_recibo[int(l["recibo_id"])].append(l)
    return por_recibo


def _tomadores_de(bd, recibos: list[Mapping[str, Any]]) -> dict[int, DPS.Tomador]:
    """O tomador de cada recibo: o do recibo, corrigido pelo balcão e com o cadastro."""
    ids = [int(r["id"]) for r in recibos]
    sobre = {int(s["recibo_id"]): s for s in bd.ler(
        "SELECT * FROM nfse_tomador_do_recibo WHERE recibo_id = ANY(%s) ORDER BY recibo_id",
        (ids,))} if ids else {}
    documentos = {}
    for r in recibos:
        s = sobre.get(int(r["id"]))
        doc = DPS.digitos((s or {}).get("documento") or r.get("pagador_documento"))
        nome = ((s or {}).get("nome") or "").strip() or (r.get("pagador") or "").strip()
        if nome.casefold() == "não informado":
            nome = ""
        documentos[int(r["id"])] = (doc, nome)
    cadastro = {c["documento"]: c for c in bd.ler(
        "SELECT * FROM nfse_tomadores WHERE documento = ANY(%s) ORDER BY documento",
        (sorted({d for d, _ in documentos.values() if d}),))} if documentos else {}
    saida = {}
    for rid, (doc, nome) in documentos.items():
        c = cadastro.get(doc) or {}
        saida[rid] = DPS.Tomador(
            documento=doc, nome=nome or (c.get("nome") or ""),
            **{k: (c.get(k) or "") for k in CAMPOS_DO_TOMADOR if k not in ("documento", "nome")})
    return saida


def pendencias_do_tomador(tomador: DPS.Tomador, cfg: Mapping[str, str]) -> list[str]:
    faltas = []
    if not tomador.documento:
        faltas.append("Falta o CPF ou CNPJ do tomador.")
    elif cpf_cnpj.documento_valido(tomador.documento) is not True:
        faltas.append("O CPF/CNPJ do tomador não confere (dígito verificador).")
    if not tomador.nome.strip():
        faltas.append("Falta o nome do tomador.")
    if str(cfg.get("nfse_exige_endereco") or "1") == "1" and not tomador.tem_endereco:
        faltas.append("Falta o endereço do tomador (CEP, município IBGE, logradouro, "
                      "número e bairro).")
    elif tomador.tem_endereco and (len(DPS.digitos(tomador.cep)) != 8
                                   or len(DPS.digitos(tomador.municipio)) != 7):
        faltas.append("O CEP do tomador tem 8 dígitos e o município, 7 (código IBGE).")
    return faltas


def _nota_viva(bd, recibo_id: int, ambiente: str, *, prender: bool = False) -> dict | None:
    return bd.um(
        "SELECT * FROM nfse_notas WHERE recibo_id = %s AND ambiente = %s "
        "AND situacao <> 'CANCELADA' ORDER BY id DESC LIMIT 1"
        + (" FOR UPDATE" if prender else ""), (int(recibo_id), ambiente))


def avaliar(con, recibos: list[Mapping[str, Any]], cfg: Mapping[str, str]) -> list[dict]:
    """Para cada recibo: base, ISS, tomador, pendências e a nota viva. Só LÊ."""
    bd = banco(con)
    ids = [int(r["id"]) for r in recibos]
    lancamentos = _lancamentos_de(bd, ids)
    tomadores = _tomadores_de(bd, list(recibos))
    notas = {int(n["recibo_id"]): n for n in bd.ler(
        """SELECT id, recibo_id, situacao, numero_nfse, chave, mensagem, tentativas,
                  valor_servico, valor_iss, numero_dps, serie, ambiente
             FROM nfse_notas WHERE recibo_id = ANY(%s) AND ambiente = %s
              AND situacao <> 'CANCELADA'
            ORDER BY recibo_id, id""", (ids, cfg.get("nfse_ambiente")))} if ids else {}
    saida = []
    for r in recibos:
        rid = int(r["id"])
        base, pend = base_do_recibo(r, lancamentos[rid], percentual_ferj(cfg))
        tomador = tomadores[rid]
        pendencias = []
        if r.get("cancelado"):
            pendencias.append("O recibo foi cancelado.")
        pendencias += pend
        gratuito = not pend and base <= 0
        if gratuito:
            pendencias.append("Sem emolumento a tributar (ato gratuito ou recibo só de fundos).")
        pendencias += pendencias_do_tomador(tomador, cfg)
        try:
            iss = valor_do_iss(base, cfg.get("nfse_aliquota"))
        except DPS.DpsError as erro:
            iss, pendencias = None, pendencias + [str(erro)]
        saida.append({"recibo": dict(r), "base": base, "iss": iss, "tomador": tomador,
                      "gratuito": gratuito,
                      "documento_mascarado": mascarar_documento(tomador.documento),
                      "pendencias": pendencias, "nota": notas.get(rid)})
    return saida


def recibo(con, recibo_id: int) -> dict | None:
    return banco(con).um("SELECT * FROM cx_recibos WHERE id = %s", (int(recibo_id),))


def avaliar_recibo(con, recibo_id: int, cfg: Mapping[str, str]) -> dict | None:
    r = recibo(con, recibo_id)
    return avaliar(con, [r], cfg)[0] if r else None


def fila(con, cfg: Mapping[str, str], *, data: str | None = None,
         limite: int = 300) -> dict[str, list[dict]]:
    """A fila do balcão: o que falta dado, o que está pronto, o que ficou no meio.

    SÓ LÊ. Recibo cancelado sem nota não aparece; recibo cancelado COM nota
    emitida aparece — a nota continua valendo para o fisco até ser cancelada.
    """
    bd = banco(con)
    onde, params = ["(r.cancelado = 0 OR n.id IS NOT NULL)"], [cfg.get("nfse_ambiente")]
    if cfg.get("nfse_inicio"):
        onde.append("r.data_emissao >= %s")
        params.append(cfg["nfse_inicio"])
    if data:
        onde.append("r.data_emissao = %s")
        params.append(data)
    recibos = bd.ler(
        f"""SELECT r.* FROM cx_recibos r
              LEFT JOIN nfse_notas n ON n.recibo_id = r.id AND n.ambiente = %s
                                    AND n.situacao = 'EMITIDA'
             WHERE {' AND '.join(onde)}
             ORDER BY r.data_emissao DESC, r.id DESC LIMIT %s""",
        (*params, int(limite)))
    grupos: dict[str, list[dict]] = {"pendentes": [], "prontos": [], "enviando": [],
                                     "rejeitadas": [], "emitidas": [], "a_cancelar": []}
    for item in avaliar(bd, recibos, cfg):
        nota, cancelado = item["nota"], bool(item["recibo"].get("cancelado"))
        if nota and nota["situacao"] == EMITIDA:
            grupos["a_cancelar" if cancelado else "emitidas"].append(item)
        elif nota and nota["situacao"] == ENVIANDO:
            grupos["enviando"].append(item)
        elif nota and nota["situacao"] == REJEITADA:
            grupos["rejeitadas"].append(item)
        elif cancelado:
            continue
        elif item["gratuito"]:
            continue          # ato gratuito não é pendência: não há nota a emitir
        elif item["pendencias"]:
            grupos["pendentes"].append(item)
        else:
            grupos["prontos"].append(item)
    return grupos


def gravar_tomador(con, recibo_id: int, valores: Mapping[str, Any], *,
                   por: str, agora: str) -> DPS.Tomador:
    """Completa o tomador do recibo. ESCREVE. O teor do recibo não muda."""
    bd = banco(con)
    r = bd.um("SELECT id, pagador, pagador_documento FROM cx_recibos WHERE id = %s",
              (int(recibo_id),))
    if not r:
        raise NfseError("Recibo não encontrado.")
    campos = {k: _curto(valores.get(k), 255) for k in CAMPOS_DO_TOMADOR}
    doc = DPS.digitos(campos["documento"] or r["pagador_documento"])
    if not doc or cpf_cnpj.documento_valido(doc) is not True:
        raise NfseError("Informe um CPF ou CNPJ válido do tomador.")
    campos["cep"] = DPS.digitos(campos["cep"])
    campos["municipio"] = DPS.digitos(campos["municipio"])
    if campos["cep"] and len(campos["cep"]) != 8:
        raise NfseError("O CEP tem 8 dígitos.")
    if campos["municipio"] and len(campos["municipio"]) != 7:
        raise NfseError("O município é o código IBGE, de 7 dígitos.")
    nome = campos["nome"]
    if DPS.digitos(r["pagador_documento"]) != doc or (nome and nome != (r["pagador"] or "")):
        bd.escrever(
            """INSERT INTO nfse_tomador_do_recibo
                   (recibo_id, documento, nome, atualizado_por, atualizado_em)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (recibo_id) DO UPDATE SET documento = excluded.documento,
                   nome = excluded.nome, atualizado_por = excluded.atualizado_por,
                   atualizado_em = excluded.atualizado_em""",
            (int(recibo_id), doc, nome, por, agora))
    endereco = {k: campos[k] for k in CAMPOS_DO_TOMADOR if k not in ("documento",)}
    bd.escrever(
        f"""INSERT INTO nfse_tomadores (documento, {', '.join(endereco)},
                   atualizado_por, atualizado_em)
            VALUES (%s, {', '.join(['%s'] * len(endereco))}, %s, %s)
            ON CONFLICT (documento) DO UPDATE SET
                {', '.join(f'{k} = excluded.{k}' for k in endereco)},
                atualizado_por = excluded.atualizado_por,
                atualizado_em = excluded.atualizado_em""",
        (doc, *endereco.values(), por, agora))
    return DPS.Tomador(documento=doc, nome=nome or r["pagador"] or "",
                       **{k: v for k, v in endereco.items() if k != "nome"})


# ------------------------------------------------------------ a emissão

def _prestador(cfg: Mapping[str, str]) -> DPS.Prestador:
    return DPS.Prestador(documento=cfg["nfse_prestador_documento"],
                         inscricao_municipal=cfg.get("nfse_inscricao_municipal") or "",
                         municipio=cfg["nfse_municipio"],
                         optante_simples=cfg.get("nfse_optante_simples") or "1",
                         regime_especial=cfg.get("nfse_regime_especial") or "4")


def _evento(bd, nota_id: int, operacao: str, resultado: str, mensagem: str,
            usuario: str, quando: str) -> None:
    bd.escrever(
        """INSERT INTO nfse_eventos (nota_id, quando, operacao, resultado, mensagem, usuario)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (int(nota_id), quando, operacao, resultado, _curto(mensagem), usuario or ""))


def preparar(con, recibo_id: int, *, cfg: Mapping[str, str],
             certificado: DPS.CertificadoA1, usuario: str,
             agora: datetime | None = None) -> dict:
    """Numera, monta, assina e grava a DPS do recibo como ENVIANDO. ESCREVE.

    Devolve a nota a enviar. Nota EMITIDA volta como está (nada a fazer);
    ENVIANDO volta com o MESMO XML (é o reenvio); REJEITADA é remontada com o
    MESMO número, porque o dado pode ter sido corrigido e a DPS recusada não
    virou nota.

    A TRAVA DO NÚMERO VEM ANTES DA LINHA DO RECIBO (a ordem do `renumerar`):
    dois recibos emitidos juntos não pegam o mesmo número, e dois cliques no
    mesmo recibo não criam duas notas — o segundo espera e acha a do primeiro.
    """
    if not ligada(cfg):
        raise NfseError("A emissão de NFS-e está desligada. O ADMIN a liga no Gestor → NFS-e.")
    bd = banco(con)
    quando = agora or _agora()
    bd.travar("nfse_notas.numero_dps")
    bd._escrita()
    r = bd.um("SELECT * FROM cx_recibos WHERE id = %s FOR UPDATE", (int(recibo_id),))
    if not r:
        raise NfseError("Recibo não encontrado.")
    nota = _nota_viva(bd, recibo_id, cfg["nfse_ambiente"], prender=True)
    if nota and nota["situacao"] in (EMITIDA, ENVIANDO):
        return nota
    item = avaliar(bd, [r], cfg)[0]
    if item["pendencias"]:
        raise Pendente(item["pendencias"])
    serie = DPS.digitos(cfg.get("nfse_serie")) or "1"
    if nota:
        numero = int(nota["numero_dps"])
        serie = nota["serie"]
    else:
        numero = int(bd.valor(
            "SELECT COALESCE(max(numero_dps), 0) AS n FROM nfse_notas "
            "WHERE ambiente = %s AND serie = %s",
            (cfg["nfse_ambiente"], serie)) or 0) + 1
    servico = DPS.Servico(codigo_tributacao=cfg["nfse_codigo_tributacao"],
                          codigo_municipal=cfg.get("nfse_codigo_municipal") or "",
                          descricao=descricao_do_servico(r, item["base"]),
                          valor_centavos=item["base"], aliquota=aliquota_para_a_dps(cfg),
                          codigo_nbs=cfg.get("nfse_codigo_nbs") or "")
    prestador = _prestador(cfg)
    try:
        xml = DPS.assinar(DPS.montar_dps(
            ambiente=cfg["nfse_ambiente"], emitida_em=quando, serie=serie, numero=numero,
            prestador=prestador, tomador=item["tomador"], servico=servico,
            ibscbs=_ibscbs(cfg)), certificado)
    except DPS.DpsError as erro:
        raise NfseError(str(erro)) from erro
    # CONFERIR O QUE VAI SAIR ANTES DE SAIR: certificado trocado pela metade
    # (chave de um, certificado de outro) assina sem erro e é recusado lá.
    if not DPS.conferir_assinatura(xml):
        raise NfseError("A assinatura da DPS não confere com o certificado gravado. "
                        "Grave o certificado A1 de novo no Gestor.")
    id_dps = DPS.id_da_dps(prestador.municipio, prestador.documento, serie, numero)
    valores = (cfg["nfse_provedor"], cfg["nfse_ambiente"], serie, numero, id_dps,
               item["tomador"].documento, item["tomador"].nome, item["base"],
               DPS.aliquota_decimal(cfg.get("nfse_aliquota")), item["iss"],
               xml.decode("utf-8"))
    if nota:
        bd.escrever(
            """UPDATE nfse_notas SET provedor = %s, ambiente = %s, serie = %s,
                      numero_dps = %s, id_dps = %s, tomador_documento = %s,
                      tomador_nome = %s, valor_servico = %s, aliquota = %s,
                      valor_iss = %s, xml_dps = %s, situacao = 'ENVIANDO',
                      mensagem = '', tentativas = 0
                WHERE id = %s""", (*valores, int(nota["id"])))
        nota_id = int(nota["id"])
    else:
        nota_id = int(bd.escrever(
            """INSERT INTO nfse_notas (provedor, ambiente, serie, numero_dps, id_dps,
                   tomador_documento, tomador_nome, valor_servico, aliquota, valor_iss,
                   xml_dps, recibo_id, situacao, criado_em, criado_por)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ENVIANDO', %s, %s)
               RETURNING id""",
            (*valores, int(recibo_id), _carimbo(quando), usuario or ""))[0]["id"])
    _evento(bd, nota_id, "PREPARAR", "ok", f"DPS {serie}/{numero}", usuario, _carimbo(quando))
    return bd.um("SELECT * FROM nfse_notas WHERE id = %s", (nota_id,))


def _registrar(db, nota_id: int, *, operacao: str, resultado: str, mensagem: str,
               usuario: str, emitida: PROV.Emitida | None = None,
               situacao: str | None = None, visto: Mapping[str, Any] | None = None) -> dict:
    """Grava o que o emissor respondeu, numa transação curta. ESCREVE.

    `visto` é a nota como o CANCELAMENTO a leu, antes da rede. Entre aquela
    leitura e esta trava, um reenvio (outro clique, o lote do dia) pode ter
    feito a DPS virar nota: cancelar só aqui o que é NFS-e válida na Sefin
    seria imposto declarado sem registro na casa. Por isso o cancelamento só
    grava se, sob o `FOR UPDATE`, a nota ainda está como foi vista.
    """
    quando = _carimbo(_agora())
    conflito = ""
    with db.transaction() as con:
        bd = banco(con)
        bd._escrita()
        nota = bd.um("SELECT * FROM nfse_notas WHERE id = %s FOR UPDATE", (int(nota_id),))
        if nota is None:
            raise NfseError("Nota não encontrada.")
        if situacao == CANCELADA and visto is not None:
            if nota["situacao"] == CANCELADA:
                # Outro clique já cancelou: o segundo só fica no rastro.
                _evento(bd, nota_id, operacao, resultado, mensagem, usuario, quando)
                return nota
            if ((nota["situacao"], nota["chave"], nota["tentativas"])
                    != (visto["situacao"], visto["chave"], visto["tentativas"])):
                raise NfseError(
                    f"A nota mudou enquanto o cancelamento era pedido (agora está "
                    f"«{SITUACOES.get(nota['situacao'], nota['situacao'])}»). Confira a "
                    f"nota e peça o cancelamento de novo.")
        if nota["situacao"] == EMITIDA and emitida is None and situacao != CANCELADA:
            # Outro clique já gravou a nota: a resposta atrasada não a desfaz.
            _evento(bd, nota_id, operacao, resultado, mensagem, usuario, quando)
            return nota
        if (emitida is not None and nota["situacao"] == CANCELADA
                and bd.um("""SELECT id FROM nfse_notas
                              WHERE recibo_id = %s AND ambiente = %s AND id <> %s
                                AND situacao <> 'CANCELADA'
                              ORDER BY id LIMIT 1""",
                          (int(nota["recibo_id"]), nota["ambiente"], int(nota_id)))):
            # A DPS virou nota DEPOIS de cancelada aqui, e o recibo já ganhou
            # outra nota viva: as duas não cabem no índice de uma viva por
            # recibo. A chave fica no rastro da nota, e o balcão é avisado de
            # que há NFS-e válida a cancelar direto no emissor.
            conflito = (f"A DPS {nota['serie']}/{nota['numero_dps']} virou a NFS-e de chave "
                        f"{emitida.chave} depois de cancelada aqui, e o recibo já tem outra "
                        f"nota. Cancele essa chave direto no emissor nacional.")
            _evento(bd, nota_id, operacao, "alerta", conflito, usuario, quando)
        elif emitida is not None:
            bd.escrever(
                """UPDATE nfse_notas SET situacao = 'EMITIDA', chave = %s, numero_nfse = %s,
                          xml_nfse = COALESCE(NULLIF(%s, ''), xml_nfse), mensagem = %s,
                          emitida_em = COALESCE(emitida_em, %s), enviado_em = %s,
                          tentativas = tentativas + 1
                    WHERE id = %s""",
                (emitida.chave, emitida.numero or None, emitida.xml, _curto(mensagem),
                 quando, quando, int(nota_id)))
            # SÓ A NOTA DE PRODUÇÃO VAI AO RECIBO: a da homologação não tem
            # valor fiscal, e número de teste gravado no recibo ficaria lá
            # depois da virada, dizendo que há nota onde não há.
            if nota["ambiente"] == "producao":
                bd.escrever(
                    "UPDATE cx_recibos SET nfse_numero = %s, nfse_chave = %s WHERE id = %s",
                    (emitida.numero or None, emitida.chave, int(nota["recibo_id"])))
        elif situacao == CANCELADA:
            bd.escrever(
                """UPDATE nfse_notas SET situacao = 'CANCELADA', cancelada_em = %s,
                          cancelada_por = %s, motivo_cancelamento = %s
                    WHERE id = %s""", (quando, usuario or "", _curto(mensagem), int(nota_id)))
            bd.escrever("UPDATE cx_recibos SET nfse_numero = NULL, nfse_chave = NULL "
                        "WHERE id = %s AND nfse_chave = %s",
                        (int(nota["recibo_id"]), nota["chave"]))
        else:
            bd.escrever(
                """UPDATE nfse_notas SET situacao = %s, mensagem = %s, enviado_em = %s,
                          tentativas = tentativas + 1
                    WHERE id = %s""",
                (situacao or nota["situacao"], _curto(mensagem), quando, int(nota_id)))
        if not conflito:
            _evento(bd, nota_id, operacao, resultado, mensagem, usuario, quando)
            return bd.um("SELECT * FROM nfse_notas WHERE id = %s", (int(nota_id),))
    raise NfseError(conflito)


def _mesmo_ambiente(nota: Mapping[str, Any], provedor) -> None:
    """DPS da homologação não vai à produção, nem o contrário."""
    if getattr(provedor, "ambiente", nota["ambiente"]) != nota["ambiente"]:
        raise NfseError(f"Esta DPS é do ambiente «{nota['ambiente']}», e o emissor "
                        f"configurado é o de «{provedor.ambiente}». Volte o ambiente no "
                        f"Gestor para tratar dela.")


def enviar(db, nota_id: int, provedor, *, usuario: str) -> dict:
    """Manda a DPS ao emissor e grava a resposta. **Fora de transação.**

    Se a DPS já saiu uma vez (`tentativas > 0`), pergunta antes se ela virou
    nota: é o que torna o reenvio seguro mesmo quando o código de duplicidade
    da Sefin mudar.
    """
    with db.connect() as con:
        nota = banco(con).um("SELECT * FROM nfse_notas WHERE id = %s", (int(nota_id),))
    if not nota:
        raise NfseError("Nota não encontrada.")
    if nota["situacao"] != ENVIANDO:
        return nota
    _mesmo_ambiente(nota, provedor)

    def _pela_chave(chave: str, frase: str) -> dict:
        try:
            emitida = provedor.consultar(chave)
        except PROV.ProvedorError:
            emitida = PROV.Emitida(chave=chave)
        return _registrar(db, nota_id, operacao="EMITIR", resultado="ok", mensagem=frase,
                          usuario=usuario, emitida=emitida)

    try:
        if int(nota["tentativas"] or 0) > 0:
            chave = provedor.consultar_dps(nota["id_dps"])
            if chave:
                return _pela_chave(chave, "A DPS já tinha virado nota: chave recuperada.")
        emitida = provedor.emitir(nota["xml_dps"].encode("utf-8"))
    except PROV.Recusa as recusa:
        if recusa.ja_emitida:
            try:
                chave = provedor.consultar_dps(nota["id_dps"])
            except PROV.ProvedorError:
                chave = None
            if chave:
                return _pela_chave(chave, "A DPS já tinha virado nota: chave recuperada.")
        return _registrar(db, nota_id, operacao="EMITIR", resultado="recusa",
                          mensagem=str(recusa), usuario=usuario, situacao=REJEITADA)
    except PROV.Indisponivel as erro:
        return _registrar(db, nota_id, operacao="EMITIR", resultado="indisponivel",
                          mensagem=str(erro), usuario=usuario, situacao=ENVIANDO)
    frase = "; ".join(emitida.alertas) if emitida.alertas else ""
    return _registrar(db, nota_id, operacao="EMITIR", resultado="ok", mensagem=frase,
                      usuario=usuario, emitida=emitida)


def emitir(db, recibo_id: int, *, provedor, certificado: DPS.CertificadoA1,
           cfg: Mapping[str, str], usuario: str, agora: datetime | None = None) -> dict:
    """Do recibo à nota: prepara (com trava) e envia (sem trava)."""
    with db.transaction() as con:
        nota = preparar(con, recibo_id, cfg=cfg, certificado=certificado,
                        usuario=usuario, agora=agora)
    if nota["situacao"] == EMITIDA:
        return nota
    return enviar(db, int(nota["id"]), provedor, usuario=usuario)


def recibos_do_lote(con, cfg: Mapping[str, str], data: str) -> list[int]:
    """Os recibos do dia que a emissão em lote leva: os prontos e os que ficaram no meio."""
    grupos = fila(con, cfg, data=data, limite=1000)
    return [int(i["recibo"]["id"]) for i in grupos["prontos"] + grupos["enviando"]]


def emitir_lote(db, data: str, *, provedor, certificado: DPS.CertificadoA1,
                cfg: Mapping[str, str], usuario: str) -> dict[str, int]:
    """A emissão do dia, um recibo por vez. Um que falha não para os outros."""
    with db.connect() as con:
        ids = recibos_do_lote(con, cfg, data)
    contagem = {"emitidas": 0, "recusadas": 0, "na_fila": 0, "pendentes": 0}
    for rid in ids:
        try:
            nota = emitir(db, rid, provedor=provedor, certificado=certificado,
                          cfg=cfg, usuario=usuario)
        except NfseError:
            # A pendência que apareceu entre a lista e a vez dele (alguém
            # mexeu no recibo) espera o balcão; o lote segue com os outros.
            contagem["pendentes"] += 1
            continue
        chave = {EMITIDA: "emitidas", REJEITADA: "recusadas"}.get(nota["situacao"], "na_fila")
        contagem[chave] += 1
    return contagem


def nota(con, nota_id: int) -> dict | None:
    return banco(con).um("SELECT * FROM nfse_notas WHERE id = %s", (int(nota_id),))


def eventos(con, nota_id: int) -> list[dict]:
    return banco(con).ler(
        "SELECT * FROM nfse_eventos WHERE nota_id = %s ORDER BY id", (int(nota_id),))


def notas_do_recibo(con, recibo_id: int) -> list[dict]:
    return banco(con).ler(
        "SELECT * FROM nfse_notas WHERE recibo_id = %s ORDER BY id", (int(recibo_id),))


def cancelar(db, nota_id: int, *, provedor, certificado: DPS.CertificadoA1,
             cfg: Mapping[str, str], motivo: str, justificativa: str,
             usuario: str, agora: datetime | None = None) -> dict:
    """Pede o cancelamento ao emissor e, se aceito, marca a nota. Sem trava na rede.

    Nota REJEITADA ou ENVIANDO sem chave nunca virou NFS-e: cancela-se só
    aqui, sem evento ao emissor — e só depois de perguntar se a DPS virou nota.
    A nota lida aqui vai ao `_registrar` como `visto`: se ela mudou durante a
    rede, o cancelamento não grava.
    """
    with db.connect() as con:
        n = nota(con, nota_id)
    if not n or n["situacao"] == CANCELADA:
        raise NfseError("Nota não encontrada ou já cancelada.")
    _mesmo_ambiente(n, provedor)
    quando = agora or _agora()
    rotulo = DPS.MOTIVOS_DE_CANCELAMENTO.get(motivo, "")
    if motivo not in DPS.MOTIVOS_DE_CANCELAMENTO:
        raise NfseError("Escolha o motivo do cancelamento.")
    if n["situacao"] != EMITIDA:
        try:
            chave = (provedor.consultar_dps(n["id_dps"])
                     if n["situacao"] == ENVIANDO else None)
        except PROV.ProvedorError as erro:
            raise NfseError(f"Não consegui perguntar ao emissor se a DPS virou nota "
                            f"({erro}). Tente de novo.") from erro
        if chave:
            raise NfseError("Esta DPS virou nota no emissor. Reenvie para gravar a "
                            "chave, e depois cancele a nota.")
        return _registrar(db, nota_id, operacao="CANCELAR", resultado="ok",
                          mensagem=f"{rotulo}: {justificativa}", usuario=usuario,
                          situacao=CANCELADA, visto=n)
    try:
        evento = DPS.assinar(DPS.montar_cancelamento(
            ambiente=n["ambiente"], quando=quando,
            autor=cfg["nfse_prestador_documento"], chave=n["chave"], motivo=motivo,
            justificativa=justificativa), certificado)
    except DPS.DpsError as erro:
        raise NfseError(str(erro)) from erro
    try:
        provedor.cancelar(n["chave"], evento)
    except PROV.ProvedorError as erro:
        _registrar(db, nota_id, operacao="CANCELAR",
                   resultado="recusa" if isinstance(erro, PROV.Recusa) else "indisponivel",
                   mensagem=str(erro), usuario=usuario)
        raise NfseError(f"O emissor não cancelou: {erro}") from erro
    return _registrar(db, nota_id, operacao="CANCELAR", resultado="ok",
                      mensagem=f"{rotulo}: {justificativa}", usuario=usuario,
                      situacao=CANCELADA, visto=n)


def nomes_de_municipio(con):
    """`codigo IBGE -> (nome, UF)` de `ib_municipios`, para o DANFSe. Só LÊ."""
    bd = banco(con)

    def nome(codigo: str) -> tuple[str, str]:
        if not DPS.digitos(codigo):
            return "", ""
        try:
            r = bd.um("SELECT nome, uf FROM ib_municipios WHERE codigo_ibge = %s",
                      (int(DPS.digitos(codigo)),))
        except Exception:      # instalação sem a tabela do IBGE: o código fica
            return "", ""
        return (r["nome"], r["uf"]) if r else ("", "")
    return nome


def danfse(db, nota_id: int, *, usuario: str, provedor=None,
           formato: str = "pdf") -> bytes | str:
    """O DANFSe v2.0 da nota, montado aqui do XML dela (NT 008/2026). Não guarda o PDF.

    CORREÇÃO DE 24/10/2026: até aqui o PDF vinha do ADN e ficava guardado em
    `nfse_notas.danfse`. A NT SE/CGNFS-e 008/2026 suspendeu aquela API em
    1º/07/2026 e passou o DANFSe ao sistema emissor. Ele sai agora do XML da
    nota, a cada pedido — e por isso a nota cancelada sai com a marca
    «CANCELADA», o que o PDF guardado antes do cancelamento não teria. A
    coluna `danfse` fica (dado já gravado é dado), mas não é mais lida.

    Sem o XML gravado e com o `provedor` à mão, a nota é consultada na Sefin
    pela chave e o XML fica gravado — é a única ida à rede daqui.
    """
    import nfse_danfse as DAN
    with db.connect() as con:
        n = nota(con, nota_id)
    if not n or not n["chave"]:
        raise NfseError("Esta nota ainda não tem chave: não há DANFSe.")
    xml = n.get("xml_nfse") or ""
    if not xml:
        if provedor is None:
            raise NfseError("O XML desta NFS-e não está gravado. Consulte a nota no "
                            "emissor (ADMIN) para gravá-lo e imprimir o DANFSe.")
        _mesmo_ambiente(n, provedor)
        try:
            xml = provedor.consultar(n["chave"]).xml
        except PROV.ProvedorError as erro:
            raise NfseError(f"Não consegui trazer o XML da nota do emissor: {erro}") from erro
        if not xml:
            raise NfseError("O emissor não devolveu o XML desta NFS-e.")
        with db.transaction() as con:
            bd = banco(con)
            bd.escrever("UPDATE nfse_notas SET xml_nfse = %s WHERE id = %s "
                        "AND xml_nfse IS NULL", (xml, int(nota_id)))
            _evento(bd, nota_id, "CONSULTAR", "ok", "XML da nota gravado para o DANFSe",
                    usuario, _carimbo(_agora()))
    with db.connect() as con:
        municipios = nomes_de_municipio(con)
        try:
            if formato == "html":
                return DAN.html_da_nota(xml, cancelada=n["situacao"] == CANCELADA,
                                        nome_do_municipio=municipios)
            return DAN.pdf_da_nota(xml, cancelada=n["situacao"] == CANCELADA,
                                   nome_do_municipio=municipios,
                                   nome=f"danfse-{n.get('numero_nfse') or nota_id}",
                                   get_setting=getattr(db, "get_setting", None))
        except DAN.DanfseError as erro:
            raise NfseError(str(erro)) from erro


def provedor_da_casa(cfg: Mapping[str, str], certificado: DPS.CertificadoA1):
    """O provedor configurado, falando pelo HTTPS com o A1 da casa."""
    try:
        transporte = PROV.transporte_https(certificado)
        return PROV.provedor(cfg["nfse_provedor"], cfg["nfse_ambiente"], transporte)
    except PROV.ProvedorError as erro:
        raise NfseError(str(erro)) from erro
    except (OSError, ValueError) as erro:
        # O nome do erro, e não a mensagem: a do `ssl` traz o caminho da chave.
        raise NfseError(f"Não consegui preparar a conexão segura com o certificado "
                        f"A1 ({type(erro).__name__}).") from erro


# ------------------------------------------- os parâmetros do município no emissor

CHAVE_DOS_PARAMETROS = "nfse_parametros_municipais"


def conferir_no_emissor(provedor, cfg: Mapping[str, str], *,
                        agora: datetime | None = None) -> dict:
    """Pergunta ao emissor o convênio, o serviço e o contribuinte. NÃO GRAVA.

    Devolve o que veio, como veio: a forma do corpo dessas respostas não está
    no manual do contribuinte, e ler nelas um «ativo» por palpite seria a
    máquina decidindo a alíquota da nota. Quem lê e marca o convênio é o
    ADMIN, na tela.
    """
    mun = DPS.digitos(cfg.get("nfse_municipio"))
    if len(mun) != 7:
        raise NfseError("Informe o código IBGE do município antes de consultar.")
    perguntas = {
        "convenio": lambda: provedor.convenio(mun),
        "servico": lambda: provedor.parametros_do_servico(
            mun, cfg.get("nfse_codigo_tributacao") or ""),
        "contribuinte": lambda: provedor.parametros_do_contribuinte(
            mun, cfg.get("nfse_prestador_documento") or ""),
    }
    respostas: dict[str, Any] = {}
    for nome, pergunta in perguntas.items():
        try:
            respostas[nome] = pergunta()
        except PROV.ProvedorError as erro:
            respostas[nome] = {"erro": str(erro)}
    return {"consultado_em": _carimbo(agora or _agora()), "ambiente": cfg.get("nfse_ambiente"),
            "municipio": mun, "respostas": respostas}


def gravar_parametros(con, consulta: Mapping[str, Any]) -> None:
    """Guarda a última consulta, para a tela e o relatório. ESCREVE em `settings`."""
    banco(con).escrever(
        "INSERT INTO settings (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (CHAVE_DOS_PARAMETROS, json.dumps(consulta, ensure_ascii=False)))


def parametros_gravados(con) -> dict | None:
    r = banco(con).um("SELECT value FROM settings WHERE key = %s", (CHAVE_DOS_PARAMETROS,))
    if not r or not r["value"]:
        return None
    try:
        return json.loads(r["value"])
    except ValueError:
        return None


# ------------------------------------------------------- a apuração do mês

def _valor_xml(raiz, caminho: str) -> int | None:
    """Um valor em reais do XML da nota, em centavos; None se não há."""
    el = raiz.find(caminho, {"n": DPS.NS})
    if el is None or not (el.text or "").strip():
        return None
    try:
        return round(float(el.text) * 100)
    except ValueError:
        return None


def _do_xml(n: Mapping[str, Any]) -> dict:
    """Competência, ISS e IBS/CBS lidos do XML da nota (o da Sefin, se houver)."""
    from lxml import etree
    saida = {"competencia": "", "iss": None, "aliquota": "", "ibs": None, "cbs": None}
    for coluna in ("xml_nfse", "xml_dps"):
        texto = n.get(coluna) or ""
        if not texto:
            continue
        try:
            raiz = etree.fromstring(texto.encode("utf-8"))
        except etree.XMLSyntaxError:
            continue
        if not saida["competencia"]:
            el = raiz.find(".//n:dCompet", {"n": DPS.NS})
            saida["competencia"] = (el.text or "").strip() if el is not None else ""
        if coluna == "xml_nfse":
            saida["iss"] = _valor_xml(raiz, "n:infNFSe/n:valores/n:vISSQN")
            el = raiz.find("n:infNFSe/n:valores/n:pAliqAplic", {"n": DPS.NS})
            saida["aliquota"] = (el.text or "").strip() if el is not None else ""
            saida["ibs"] = _valor_xml(raiz, "n:infNFSe/n:IBSCBS/n:totCIBS/n:gIBS/n:vIBSTot")
            saida["cbs"] = _valor_xml(raiz, "n:infNFSe/n:IBSCBS/n:totCIBS/n:gCBS/n:vCBS")
    return saida


def apuracao_do_mes(con, mes: str, *, ambiente: str = "producao") -> dict:
    """O ISS do mês (AAAA-MM), nota por nota, pelo que a Sefin calculou. Só LÊ.

    A competência sai do `dCompet` da DPS, e o ISS do `vISSQN` do XML da NFS-e
    — o valor que a Sefin apurou, e não a estimativa da fila. Nota sem o XML
    da Sefin entra com o ISS estimado e a marca «estimado», para quem confere
    saber de onde veio cada número. Cancelada aparece à parte e não soma.

    Isto NÃO é a guia: a guia do ISS sai de quem cobra o imposto (o Módulo de
    Apuração Nacional, se o município aderiu, ou o sistema da prefeitura).
    O que este quadro faz é dizer quanto ela deve dar, e de quais notas.
    """
    try:
        inicio = datetime.strptime(mes, "%Y-%m")
    except ValueError as erro:
        raise NfseError("O mês é AAAA-MM.") from erro
    fim = datetime(inicio.year + (inicio.month == 12), inicio.month % 12 + 1, 1)
    # Uma folga de dois dias de cada lado no filtro do banco; quem decide a
    # competência é o `dCompet`, lido em Python logo abaixo.
    de = (inicio.replace(day=1)).isoformat()[:10]
    ate = fim.isoformat()[:10]
    linhas = banco(con).ler(
        """SELECT id, recibo_id, situacao, serie, numero_dps, numero_nfse, chave,
                  tomador_documento, tomador_nome, valor_servico, valor_iss, aliquota,
                  emitida_em, cancelada_em, xml_dps, xml_nfse
             FROM nfse_notas
            WHERE ambiente = %s AND situacao IN ('EMITIDA', 'CANCELADA')
              AND emitida_em >= %s AND emitida_em < %s
            ORDER BY emitida_em, id""",
        (ambiente, _deslocar(de, -2), _deslocar(ate, 2)))
    notas, canceladas = [], []
    soma = {"base": 0, "iss": 0, "ibs": 0, "cbs": 0, "estimadas": 0}
    for n in linhas:
        x = _do_xml(n)
        if not x["competencia"].startswith(mes):
            continue
        estimado = x["iss"] is None
        iss = x["iss"] if not estimado else (n["valor_iss"] or 0)
        item = {"id": n["id"], "recibo_id": n["recibo_id"], "numero": n["numero_nfse"] or "",
                "dps": f"{n['serie']}/{n['numero_dps']}", "chave": n["chave"] or "",
                "competencia": x["competencia"],
                "tomador": n["tomador_nome"],
                "tomador_documento": mascarar_documento(n["tomador_documento"]),
                "base": int(n["valor_servico"] or 0), "iss": int(iss or 0),
                "aliquota": x["aliquota"] or n["aliquota"] or "", "estimado": estimado,
                "ibs": x["ibs"] or 0, "cbs": x["cbs"] or 0,
                "cancelada_em": n["cancelada_em"] or ""}
        if n["situacao"] == CANCELADA:
            canceladas.append(item)
            continue
        notas.append(item)
        soma["base"] += item["base"]
        soma["iss"] += item["iss"]
        soma["ibs"] += item["ibs"]
        soma["cbs"] += item["cbs"]
        soma["estimadas"] += 1 if estimado else 0
    return {"mes": mes, "ambiente": ambiente, "notas": notas, "canceladas": canceladas,
            "total": soma, "quantidade": len(notas)}


def _deslocar(dia: str, dias: int) -> str:
    from datetime import timedelta
    return (datetime.strptime(dia, "%Y-%m-%d") + timedelta(days=dias)).date().isoformat()


# A FÓRMULA NO CSV (revisão de segurança de 26/10/2026, achado MÉDIO do PR #10).
# Até aqui o CSV se montava à mão, sem aspas, e o nome do tomador — que o
# balcão digita no cadastro do cliente — ia para a célula como veio. Um
# cliente gravado como «=HYPERLINK(...)» ou «=cmd|' /C calc'!A0» virava
# FÓRMULA quando o contador abrisse a apuração no Excel, fora da rede da casa.
# Célula que começa com um destes caracteres a planilha lê como fórmula; o
# apóstrofo na frente a faz ler como texto, e o valor continua legível.
# O helper único da casa (o mesmo conserto para o `csv_response` do app.py) é
# um achado transversal, de outra frente; este é o do próprio módulo.
_INICIO_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _campo_csv(texto: Any) -> str:
    """O campo de TEXTO que vai ao CSV, desarmado: o que começa como fórmula
    ganha um apóstrofo na frente. Só os campos de texto passam por aqui; os
    valores em dinheiro saem dos centavos gravados, e um «-» neles é sinal."""
    t = "" if texto is None else str(texto)
    return "'" + t if t.startswith(_INICIO_DE_FORMULA) else t


def apuracao_csv(apuracao: Mapping[str, Any]) -> str:
    """A apuração em CSV (separador «;», decimal com vírgula), para o contador.

    Todo campo vai entre aspas (`QUOTE_ALL`) — o «;» ou a quebra de linha
    dentro de um nome não desloca as colunas — e o texto passa por
    `_campo_csv`, que desarma a fórmula."""
    saida = io.StringIO()
    escrever = csv.writer(saida, delimiter=";", quoting=csv.QUOTE_ALL,
                          lineterminator="\r\n").writerow
    escrever(("competencia", "numero_nfse", "dps", "chave", "tomador", "documento", "base",
              "aliquota", "iss", "iss_estimado", "ibs", "cbs"))

    def r(c: int) -> str:
        return DPS.valor_decimal(c).replace(".", ",") if c is not None else ""
    for n in apuracao["notas"]:
        escrever((_campo_csv(n["competencia"]), _campo_csv(n["numero"]), _campo_csv(n["dps"]),
                  _campo_csv(n["chave"]), _campo_csv(n["tomador"]),
                  _campo_csv(n["tomador_documento"]), r(n["base"]),
                  str(n["aliquota"]).replace(".", ","), r(n["iss"]),
                  "sim" if n["estimado"] else "nao", r(n["ibs"]), r(n["cbs"])))
    t = apuracao["total"]
    escrever(("TOTAL", "", "", "", "", "", r(t["base"]), "", r(t["iss"]),
              str(t["estimadas"]), r(t["ibs"]), r(t["cbs"])))
    return saida.getvalue()


def para_o_rastro(n: Mapping[str, Any]) -> dict:
    """O que da nota vai a `audit_logs`: sem CPF inteiro, sem XML."""
    return {"recibo_id": n.get("recibo_id"), "situacao": n.get("situacao"),
            "ambiente": n.get("ambiente"), "dps": f"{n.get('serie')}/{n.get('numero_dps')}",
            "numero_nfse": n.get("numero_nfse"), "chave": n.get("chave"),
            "tomador": mascarar_documento(n.get("tomador_documento")),
            "valor_servico": reais(int(n.get("valor_servico") or 0))}

