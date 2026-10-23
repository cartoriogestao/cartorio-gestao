"""Dados de ensaio ? registro de obito (RC-OBITO-ENSAIO) no sandbox."""
from __future__ import annotations

from datetime import date
from typing import Any

import ato_selado as AS
from bd_nativo import banco
import rc_assento as RC
import rc_certidao as RCE
import rc_marcas_do_obito as MARCA
import rc_termo as RCT
from ri_web import data_por_extenso
from serventia import dados as dados_serventia

MARCADOR = "ensaio-revisao-modular-rcpn-obito"
ORIGEM = "ENSAIO"
NOME_FALECIDO = "TESTE JORGE DELTA SANDBOX"
DATA_FATO = "2026-09-15"
DATA_ATO = "2026-09-27"
NUMERO_DO = "2026.000123456-7"
SELO_ENSAIO = "REGOBT{cns}JKJGSNRKW974SAN"

PESSOAS: tuple[dict[str, Any], ...] = (
    {"papel": "FALECIDO", "nome": NOME_FALECIDO, "sexo": "M",
     "data_nascimento": "1958-03-12", "estado_civil": "casado",
     "profissao": "aposentado", "nacionalidade": "brasileira",
     "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "MA",
     "documento_tipo": "CPF", "documento_numero": "000.000.047-74",
     "endereco": "Rua Ficticia de Ensaio, 45, Cidade Exemplo/MA"},
    {"papel": "PAI", "nome": "TESTE ANTONIO DELTA SANDBOX", "sexo": "M"},
    {"papel": "MAE", "nome": "TESTE HELENA DELTA SANDBOX", "sexo": "F"},
    {"papel": "DECLARANTE", "nome": "TESTE MARIA DELTA SANDBOX", "sexo": "F",
     "documento_tipo": "CPF", "documento_numero": "529.981.246-03"},
    {"papel": "TESTEMUNHA", "nome": "TESTE PAULO ENSAIO SANDBOX", "sexo": "M",
     "documento_tipo": "CPF", "documento_numero": "321.654.987-00"},
)

IBGE = {"numero_do": NUMERO_DO, "natureza_obito": "1", "local_obito": "1"}

TERMO_DADOS = {
    "cor_raca": "parda", "hora_fato": "17:30",
    "local_fato_nome": "Hospital Municipal Ficticio de Ensaio",
    "local_fato_endereco": "Av. Sandbox, 100",
    "naturalidade_declarada": "Cidade Exemplo/MA",
    "causa_morte": "Infarto agudo do miocardio",
    "atestante": "Dr. Teste Silva CRM-MA 00000",
    "atestante_documento": "32165498700",
    "local_sepultamento": "Cemiterio Municipal de Cidade Exemplo",
    "testamento": "NAO",
}

MARCAS_RESPOSTAS = {
    "obito_eleitor": MARCA.NAO,
    "obito_possui_bens": MARCA.SIM,
    "obito_possui_filho": MARCA.SIM,
    "obito_desconhecido": MARCA.NAO,
}


def assento_precisa_remontar(teor: str | None) -> bool:
    t = (teor or "").strip()
    if len(t) < 600 or NOME_FALECIDO not in t:
        return True
    if "Hospital Municipal Ficticio" not in t:
        return True
    return "infarto" not in t.lower()


def certidao_precisa_remontar(teor: str | None, especie: str | None) -> bool:
    if str(especie or "").upper() != "OBITO":
        return True
    t = (teor or "").strip()
    if len(t) < 400 or NOME_FALECIDO not in t:
        return True
    u = t.upper()
    return "CERTID" not in u or "BITO" not in u


def montar_teor_certidao(con, db, assento_id: int, *, hoje: str | None = None) -> str:
    bd = banco(con)
    assento = bd.um("SELECT * FROM rc_assentos WHERE id=%s", (assento_id,))
    if not assento:
        raise RuntimeError(f"Assento {assento_id} ausente")
    pessoas = [dict(p) for p in bd.ler(
        "SELECT * FROM rc_pessoas WHERE assento_id=%s ORDER BY ordem, id", (assento_id,))]
    atos = [dict(a) for a in bd.ler(
        "SELECT * FROM rc_atos WHERE assento_id=%s ORDER BY id", (assento_id,))]
    sv = dados_serventia(db.get_settings)
    h = hoje or date.today().isoformat()
    lugar = RCE.lugar_do_assento(con, assento_id)
    return RCE.montar_teor(
        assento=dict(assento), pessoas_do_assento=pessoas, atos=atos, sv=sv, hoje=h,
        lugar=lugar,
        data_extenso=data_por_extenso(date.fromisoformat(h)),
        data_fato_extenso=data_por_extenso(date.fromisoformat(str(assento["data_fato"] or DATA_FATO))),
    )


def garantir_assento(db, *, operador: str, agora: str | None = None) -> dict[str, Any]:
    agora = agora or db.now()
    hoje = agora[:10]
    sv = db.get_settings()
    serv = dados_serventia(sv)
    out: dict[str, Any] = {"feito": False, "motivo": None, "marcador": MARCADOR}

    with db.connect() as con:
        row = banco(con).um(
            "SELECT id, teor FROM rc_assentos WHERE origem=%s AND origem_chave=%s ORDER BY id LIMIT 1",
            (ORIGEM, MARCADOR))

    if row and not assento_precisa_remontar(row["teor"]):
        out.update({"motivo": "ja_existia", "assento_id": int(row["id"])})
        return out

    with db.transaction() as con:
        bd = banco(con)
        if row:
            assento_id = int(row["id"])
            out["motivo"] = "remontado"
            bd.escrever("DELETE FROM rc_pessoas WHERE assento_id=%s", (assento_id,))
            bd.escrever("UPDATE rc_assentos SET teor=NULL, data_ato=%s WHERE id=%s", (DATA_ATO, assento_id))
            for p in PESSOAS:
                RC.registrar_pessoa(con, assento_id, especie="OBITO", agora=agora, **dict(p))
        else:
            r = RC.lavrar_assento(
                con, especie="OBITO", nome=NOME_FALECIDO, sv=sv, agora=agora,
                data_extenso=data_por_extenso(date.fromisoformat(hoje)),
                data_fato=DATA_FATO, usuario=operador, origem=ORIGEM, origem_chave=MARCADOR,
                ibge=dict(IBGE), termo_dados=dict(TERMO_DADOS),
                pessoas=[dict(p) for p in PESSOAS],
            )
            assento_id = int(r["assento_id"])
            out.update({"feito": True, "motivo": "criado", "ato_id": r["ato_id"]})
            bd.escrever("UPDATE rc_assentos SET data_ato=%s WHERE id=%s", (DATA_ATO, assento_id))

        RC.anotar_para_o_ibge(con, assento_id, especie="OBITO", **IBGE)
        RC.anotar_do_termo(con, assento_id, especie="OBITO", **TERMO_DADOS)
        MARCA.responder(con, assento_id, MARCAS_RESPOSTAS)

        ato = bd.um(
            "SELECT id, selo FROM rc_atos WHERE assento_id=%s AND tipo='REGISTRO' ORDER BY id LIMIT 1",
            (assento_id,))
        ato_id = int(ato["id"])
        out["ato_id"] = ato_id
        if not str(ato["selo"] or "").strip():
            AS.registrar_selo_obtido_a_mao(
                con, SELO_ENSAIO.format(cns=db.get_setting("ri_cns", "")), tabela="rc_atos", ato_id=ato_id, atribuicao="RCPN",
                agora=agora, cns=db.get_setting("ri_cns", ""), usuario=operador,
                texto="Selo de ensaio ? registro de obito sandbox")

        teor = (bd.valor("SELECT teor FROM rc_assentos WHERE id=%s", (assento_id,)) or "")
        if assento_precisa_remontar(teor):
            RCT.congelar(con, assento_id, serventia=serv, agora=agora)
        out["assento_id"] = assento_id
        out["teor_len"] = len(bd.valor("SELECT teor FROM rc_assentos WHERE id=%s", (assento_id,)) or "")
    return out


def garantir_certidao(db, assento_id: int, *, operador: str) -> dict[str, Any]:
    agora = db.now()
    hoje = agora[:10]
    sv = db.get_settings()
    out: dict[str, Any] = {"feito": False, "motivo": None}
    with db.connect() as con:
        row = banco(con).um(
            "SELECT id, especie, teor FROM rc_certidoes WHERE assento_id=%s ORDER BY id LIMIT 1",
            (int(assento_id),))
    if row and not certidao_precisa_remontar(row["teor"], row["especie"]):
        return {"motivo": "ja_existia", "certidao_id": int(row["id"])}
    with db.transaction() as con:
        if row:
            cert_id = int(row["id"])
            teor = montar_teor_certidao(con, db, assento_id, hoje=hoje)
            banco(con).escrever(
                "UPDATE rc_certidoes SET teor=%s, especie='OBITO', nome=%s WHERE id=%s",
                (teor, NOME_FALECIDO, cert_id))
            return {"feito": True, "motivo": "remontada", "certidao_id": cert_id}
        r = RCE.emitir(
            con, int(assento_id), sv=sv, hoje=hoje, agora=agora,
            requerente="SANDBOX ENSAIO RCPN OBITO",
            finalidade="Revisao modular ? certidao de obito", usuario=operador)
        esp = str(banco(con).valor("SELECT especie FROM rc_assentos WHERE id=%s", (assento_id,))).upper()
        if RCE.eh_primeira_certidao_do_registro(con, assento_id, certidao_id=r["certidao_id"], especie=esp):
            out["selo_registro"] = RCE.espelhar_selo_do_registro_na_certidao(con, r["certidao_id"], assento_id)
        return {"feito": True, "certidao_id": r["certidao_id"], "numero": f"{r['numero']}/{r['ano']}"}
