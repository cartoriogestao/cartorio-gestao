"""Dados de ensaio — procuracao publica (NT-PROC-PUBLICA) no sandbox."""
from __future__ import annotations

import json
from typing import Any

from jinja2.sandbox import SandboxedEnvironment

from ri_modelos_atos import preencher as preencher_modelo
from serventia import dados as dados_serventia
import notas_teor as NT

MARCADOR = "ensaio-revisao-modular-procuracao"
ORIGEM = "ENSAIO"
MODELO_CODIGO = "NT-PROC-PUBLICA"
INTERESSADO = "SANDBOX ENSAIO PROCURACAO PUBLICA"
ESPECIE_SELO = "SIMPLES"
ITEM_EMOLUMENTO = "13.9.3"

PARTES = (
    {
        "nome": "CARLOS EDUARDO BETA SANDBOX",
        "documento": "529.981.246-03",
        "tipo_pessoa": "F",
        "qualificacao": "OUTORGANTE",
        "nacionalidade": "brasileira",
        "estado_civil": "solteiro",
        "profissao": "engenheiro",
        "endereco": "Rua Ficticia de Ensaio, 100, Cidade Exemplo/MA",
        "testemunha": 0,
        "ordem": 1,
    },
    {
        "nome": "MARIA HELENA BETA SANDBOX",
        "documento": "000.000.047-74",
        "tipo_pessoa": "F",
        "qualificacao": "PROCURADOR",
        "nacionalidade": "brasileira",
        "estado_civil": "casada",
        "profissao": "advogada",
        "endereco": "Rua Ficticia de Ensaio, 200, Cidade Exemplo/MA",
        "testemunha": 0,
        "ordem": 2,
    },
)

MODELO_VALORES = {
    "dia_por_extenso": "vinte e sete",
    "dia_em_algarismos": "27",
    "mes_por_extenso": "setembro",
    "ano_por_extenso": "dois mil e vinte e seis",
    "ano_em_algarismos": "2026",
    "descricao_dos_poderes_conferidos_de_forma_clara_e_precisa": (
        "representar o outorgante perante o Banco Sandbox S/A, podendo movimentar "
        "conta corrente n. 12345-6, firmar contratos de credito e dar quitacao"
    ),
    "prazo": "O presente mandato vigorara por prazo indeterminado",
    "assinantes_do_ato_e_a_condicao_em_que_assinam": (
        "CARLOS EDUARDO BETA SANDBOX, outorgante; MARIA HELENA BETA SANDBOX, "
        "outorgada"
    ),
}

SELO_ENSAIO = "PROCPUB{cns}JKJGSNRKW976SAN"


def montar_teor(
    con,
    db,
    *,
    lavrado_nome: str = "SANDBOX — OFICIAL DELEGATARIO",
    lavrado_titulo: str = "Tabeliao e Oficial de Registro",
) -> str:
    """Mesma cadeia de `notas_ato_preencher` (Jinja + campos do modelo)."""
    row = con.execute(
        "SELECT corpo FROM nt_modelos WHERE codigo=? AND ativo=1",
        (MODELO_CODIGO,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Modelo {MODELO_CODIGO} ausente no banco")
    partes = [dict(p) for p in PARTES]
    ctx = NT.contexto_jinja_partes(partes)
    env = SandboxedEnvironment(autoescape=False)
    corpo_jinja = env.from_string(row[0]).render(
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
    if "Banco Sandbox" not in t:
        return True
    return False


def claros_documento() -> dict[str, Any]:
    return {
        "modelo_codigo": MODELO_CODIGO,
        "partes": list(PARTES),
        "modelo_valores": dict(MODELO_VALORES),
        "marcador": MARCADOR,
    }