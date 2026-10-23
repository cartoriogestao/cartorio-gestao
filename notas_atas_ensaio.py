"""Dados de ensaio — ata notarial (NT-ATA-NOTARIAL) no sandbox."""
from __future__ import annotations

from typing import Any

from jinja2.sandbox import SandboxedEnvironment

from ri_modelos_atos import preencher as preencher_modelo
from serventia import dados as dados_serventia
import notas_teor as NT
from bd_nativo import banco

MARCADOR = "ensaio-revisao-modular-ata-notarial"
ORIGEM = "ENSAIO"
MODELO_CODIGO = "NT-ATA-NOTARIAL"
INTERESSADO = "SANDBOX ENSAIO ATA NOTARIAL"
ESPECIE_SELO = "SIMPLES"
ITEM_EMOLUMENTO = "13.9.3"

PARTES = (
    {
        "nome": "JOSE ANTONIO DELTA SANDBOX",
        "documento": "000.000.047-74",
        "tipo_pessoa": "F",
        "qualificacao": "SOLICITANTE",
        "nacionalidade": "brasileira",
        "estado_civil": "casado",
        "profissao": "comerciante",
        "endereco": "Rua Ficticia de Ensaio, 300, Cidade Exemplo/MA",
        "testemunha": 0,
        "ordem": 1,
    },
    {
        "nome": "ANA LUCIA DELTA SANDBOX",
        "documento": "529.981.246-03",
        "tipo_pessoa": "F",
        "qualificacao": "TESTEMUNHA",
        "nacionalidade": "brasileira",
        "estado_civil": "solteira",
        "profissao": "professora",
        "endereco": "Rua Ficticia de Ensaio, 301, Cidade Exemplo/MA",
        "testemunha": 1,
        "ordem": 2,
    },
)

MODELO_VALORES = {
    "dia_por_extenso": "vinte e sete",
    "dia_em_algarismos": "27",
    "mes_por_extenso": "setembro",
    "ano_por_extenso": "dois mil e vinte e seis",
    "ano_em_algarismos": "2026",
    "hora_por_extenso": "dezessete",
    "hora_em_algarismos": "17",
    "hora_do_encerramento_por_extenso": "dezessete e trinta",
    "hora_do_encerramento_em_algarismos": "17:30",
    "op_lugar_da_lavratura": "nesta serventia",
    "narracao_circunstanciada_dos_fatos_em_ordem_cronologica_com_": (
        "compareci ao balcao da serventia e verifiquei, com os proprios sentidos, "
        "que o solicitante apresentava capturas de tela (ficticias) de conversa "
        "de WhatsApp referentes a entrega de mercadoria no cenario SANDBOX ENSAIO; "
        "constatei a sequencia cronologica das mensagens, a data visivel "
        "(27/09/2026) e a ausencia de edicao aparente nas imagens exibidas no "
        "aparelho movel do solicitante, sem emitir juizo sobre a veracidade do "
        "conteudo ou sobre direito de terceiros"
    ),
    "assinantes_do_ato_e_a_condicao_em_que_assinam": (
        "JOSE ANTONIO DELTA SANDBOX, solicitante; ANA LUCIA DELTA SANDBOX, testemunha"
    ),
}

SELO_ENSAIO = "ATANOT{cns}JKJGSNRKW977SAN"


def montar_teor(
    con,
    db,
    *,
    lavrado_nome: str = "SANDBOX — OFICIAL DELEGATARIO",
    lavrado_titulo: str = "Tabeliao e Oficial de Registro",
) -> str:
    """Mesma cadeia de `notas_ato_preencher` (Jinja + campos do modelo)."""
    row = banco(con).um(
        "SELECT corpo FROM nt_modelos WHERE codigo = %s AND ativo = 1",
        (MODELO_CODIGO,),
    )
    if not row:
        raise RuntimeError(f"Modelo {MODELO_CODIGO} ausente no banco")
    partes = [dict(p) for p in PARTES]
    ctx = NT.contexto_jinja_partes(partes)
    env = SandboxedEnvironment(autoescape=False)
    corpo_jinja = env.from_string(row["corpo"]).render(
        sv=dados_serventia(db.get_settings),
        lavrado_nome=lavrado_nome,
        lavrado_titulo=lavrado_titulo,
        **ctx,
    )
    return preencher_modelo({"corpo": corpo_jinja}, dict(MODELO_VALORES))


def teor_precisa_remontar(teor: str | None) -> bool:
    t = (teor or "").strip()
    if not t or len(t) < 800:
        return True
    if "presente escritura foi lida" in t.lower():
        return True
    if "WhatsApp" not in t:
        return True
    if "{LUGAR DA LAVRATURA" in t:
        return True
    if "ata notarial virem" not in t.lower():
        return True
    return False


def claros_documento() -> dict[str, Any]:
    return {
        "modelo_codigo": MODELO_CODIGO,
        "partes": list(PARTES),
        "modelo_valores": dict(MODELO_VALORES),
        "marcador": MARCADOR,
    }
