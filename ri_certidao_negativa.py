"""Certidao negativa de imovel — busca nos livros/indicadores do RI.

Pedido da substituta Beatriz (25/09/2026): emitir certidao que afirme que,
feitas as buscas, NAO CONSTA matricula/registro em nome da pessoa (ou sobre
o imovel indicado).

POR QUE NAO MORA NA FICHA DA MATRICULA
    Problema #75 (18/09/2026): a opcao «negativa de matricula» saiu da tela
    da matricula porque o texto dela nao certifica ESTA matricula — e busca
    pelo nome nos livros todos. Esta tela e a certa: Indicador Pessoal
    (nome/documento) e Indicador Real (descricao do imovel).

O QUE E MEDIDO, E O QUE NAO E
    O E-Oficio desta casa NUNCA teve modelo de «negativa» no RI
    (`tbCertidoes`: zero linhas com «negativ» no nome). O texto abaixo
    reaproveita a prosa que esta casa ja tinha escrito quando a opcao
    existia por engano na ficha («NADA CONSTA em nome … nos livros de
    Registro de Imoveis desta Serventia»), e o desenho da negativa de
    Protesto (busca de novo no POST; recusa se achou algo).

SELO
    Mesmo caminho `/selo/imovel/certidao`, item `16.24.1` (certidao comum
    com uma folha) — codigo ja medido na tabela e usado por PROPRIEDADE.
    Nao se inventa item novo.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, timedelta
from typing import Any

from certidao_texto import sem_linha_de_assinatura_a_mao
from ri_schema import VALIDADE_CERTIDAO_DIAS, normalizar_busca

TIPO = "NEGATIVA_IMOVEL"
NOME_DO_TIPO = "Certidão negativa de imóvel"

# Chave do papel no catalogo (Administrativo → Modelos). Texto de fabrica
# abaixo; o oficial edita na tela sem tocar no codigo.
CHAVE_MODELO = "RI_CERTIDAO_NEGATIVA_IMOVEL"


class CertidaoNegativaError(ValueError):
    """Recusa de dominio: busca achou algo, ou faltou criterio."""


MODELO_PADRAO = """\
<p align="center"><b>{{ serventia.nome|upper }}</b></p>
<p align="center">CNS {{ serventia.cns }} — {{ serventia.cidade }}/{{ serventia.uf }}</p>
<p align="center"><b>CERTIDÃO NEGATIVA DE IMÓVEL</b></p>
<p>Certifico, a pedido de parte interessada{% if requerente %} — <b>{{ requerente }}</b>{% if requerente_documento %}, {{ requerente_documento }}{% endif %}{% endif %}, que, feitas as buscas nos livros e indicadores do Registro de Imóveis a meu cargo{% if criterio_rotulo %} — <b>{{ criterio_rotulo }}</b>{% endif %} —, <b>NADA CONSTA</b> de matrícula ou registro{% if pesquisado %} em nome de <b>{{ pesquisado }}</b>{% if pesquisado_documento %}, {{ pesquisado_documento }}{% endif %}{% endif %}{% if imovel_busca %} sobre o imóvel indicado («{{ imovel_busca }}»){% endif %} nos livros de Registro de Imóveis desta Serventia, até a presente data.</p>
{% if finalidade %}<p><b>FINALIDADE: </b>{{ finalidade }}</p>{% endif %}
{% if protocolo %}<p><b>PROTOCOLO/PRENOTAÇÃO: </b>{{ protocolo }}</p>{% endif %}
<p><b>VALIDADE: </b>30 (trinta) dias contados da data de expedição, na forma do art. 53 do Código de Normas da CGJ/TJMA. Certidão emitida em {{ hoje_extenso }}{% if hora_emissao %}, às {{ hora_emissao }}{% endif %}. Dou fé.</p>
<p align="center">{{ serventia.cidade }}/{{ serventia.uf }}, {{ hoje_extenso }}.</p>
<p align="center">{{ lavrou_nome }}</p>
<p align="center">{{ lavrou_funcao }}</p>
"""


def so_digitos(texto: Any) -> str:
    return "".join(ch for ch in str(texto or "") if ch.isdigit())


def buscar_por_pessoa(con: sqlite3.Connection, busca: str,
                      *, so_proprietarios: bool = False) -> list[dict]:
    """A mesma régua do Indicador Pessoal: nome normalizado por trecho;
    documento completo. Devolve os grupos achados (pode ser lista vazia)."""
    busca = (busca or "").strip()
    if not busca:
        raise CertidaoNegativaError(
            "Informe o nome ou o CPF/CNPJ para buscar antes de emitir a "
            "certidão negativa.")
    doc = so_digitos(busca) or busca
    onde = ["(p.nome_norm LIKE ? OR p.documento_numero = ?)"]
    params: list[Any] = [f"%{normalizar_busca(busca)}%", doc]
    if so_proprietarios:
        onde.append("p.proprietario_ativo = 1")
    filtro = " AND ".join(onde)
    rows = con.execute(
        f"""SELECT COALESCE(NULLIF(p.documento_numero,''), p.nome_norm) chave,
                  MAX(p.nome) nome, MAX(p.documento_tipo) doc_tipo,
                  MAX(p.documento_numero) doc,
                  COUNT(DISTINCT p.matricula_id) n_matriculas
           FROM ri_partes p WHERE {filtro}
           GROUP BY chave ORDER BY n_matriculas DESC, nome LIMIT 60""",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def buscar_por_imovel(con: sqlite3.Connection, busca: str,
                      *, bairro: str = "", tipo: str = "") -> list[dict]:
    """A mesma régua do Indicador Real: descrição normalizada por trecho."""
    busca = (busca or "").strip()
    if not busca and not (bairro or "").strip():
        raise CertidaoNegativaError(
            "Informe a descrição do imóvel (ou o bairro) para buscar antes "
            "de emitir a certidão negativa.")
    onde, params = ["1=1"], []
    if busca:
        onde.append("m.imovel_norm LIKE ?")
        params.append(f"%{normalizar_busca(busca)}%")
    if (bairro or "").strip():
        onde.append("m.bairro = ?")
        params.append(bairro.strip())
    if tipo in ("R", "U"):
        onde.append("m.rural_urbano = ?")
        params.append(tipo)
    filtro = " AND ".join(onde)
    rows = con.execute(
        f"""SELECT m.id, m.numero, m.logradouro, m.bairro
            FROM ri_matriculas m WHERE {filtro}
            ORDER BY CAST(m.numero AS INTEGER) LIMIT 60""",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def conferir_negativa(achados: list) -> None:
    """Negativa só sai quando a busca realmente não achou."""
    if achados:
        raise CertidaoNegativaError(
            f"Não se emite certidão negativa: a busca achou "
            f"{len(achados)} resultado(s). Negativa só quando nada consta.")


def montar_identificacao(busca: str, *, modo: str) -> dict:
    """O que entra no papel sobre o critério da busca."""
    busca = (busca or "").strip()
    doc = so_digitos(busca)
    if modo == "PESSOA":
        if doc and len(doc) in (11, 14) and doc == so_digitos(busca):
            # Busca foi só o documento.
            return {
                "criterio_rotulo": f"pelo documento {doc}",
                "pesquisado": "",
                "pesquisado_documento": doc,
                "imovel_busca": "",
            }
        return {
            "criterio_rotulo": f"pelo nome «{busca}»",
            "pesquisado": busca,
            "pesquisado_documento": "",
            "imovel_busca": "",
        }
    return {
        "criterio_rotulo": f"pela descrição do imóvel «{busca}»",
        "pesquisado": "",
        "pesquisado_documento": "",
        "imovel_busca": busca,
    }


def hash_do_corpo(numero: int, ano: int, corpo: str, data_emissao: str,
                  criterio: str) -> str:
    payload = json.dumps(
        {"numero": int(numero), "ano": int(ano), "tipo": TIPO,
         "criterio": (criterio or "").strip(), "corpo": corpo or "",
         "data": (data_emissao or "").strip()},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validade_ate(hoje: date) -> str:
    return (hoje + timedelta(days=VALIDADE_CERTIDAO_DIAS)).isoformat()


def limpar_corpo(corpo: str) -> str:
    """Preferência da casa: sem traço de assinatura à mão na certidão."""
    return sem_linha_de_assinatura_a_mao(corpo or "")
