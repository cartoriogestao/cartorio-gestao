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
from datetime import date, timedelta
from typing import Any

from bd_nativo import banco
from certidao_texto import sem_linha_de_assinatura_a_mao
from ri_schema import VALIDADE_CERTIDAO_DIAS, normalizar_busca

TIPO = "NEGATIVA_IMOVEL"
NOME_DO_TIPO = "Certidão negativa de imóvel"

# Chave do papel no catalogo (Administrativo → Modelos). Texto de fabrica
# em `modelos_padrao/ri/` (LF06A); o oficial edita na tela sem tocar no codigo.
CHAVE_MODELO = "RI_CERTIDAO_NEGATIVA_IMOVEL"


class CertidaoNegativaError(ValueError):
    """Recusa de dominio: busca achou algo, ou faltou criterio."""


# `MODELO_PADRAO` — o texto de fábrica do papel RI_CERTIDAO_NEGATIVA_IMOVEL — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/ri/RI_CERTIDAO_NEGATIVA_IMOVEL.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.


def so_digitos(texto: Any) -> str:
    return "".join(ch for ch in str(texto or "") if ch.isdigit())


def buscar_por_pessoa(con: Any, busca: str,
                      *, so_proprietarios: bool = False) -> list[dict]:
    """A mesma régua do Indicador Pessoal: nome normalizado por trecho;
    documento completo. Devolve os grupos achados (pode ser lista vazia)."""
    busca = (busca or "").strip()
    if not busca:
        raise CertidaoNegativaError(
            "Informe o nome ou o CPF/CNPJ para buscar antes de emitir a "
            "certidão negativa.")
    doc = so_digitos(busca) or busca
    onde = ["(p.nome_norm ILIKE %s OR p.documento_numero = %s)"]
    params: list[Any] = [f"%{normalizar_busca(busca)}%", doc]
    if so_proprietarios:
        onde.append("p.proprietario_ativo = 1")
    filtro = " AND ".join(onde)
    return banco(con).ler(
        f"""SELECT COALESCE(NULLIF(p.documento_numero,''), p.nome_norm) chave,
                  MAX(p.nome) nome, MAX(p.documento_tipo) doc_tipo,
                  MAX(p.documento_numero) doc,
                  COUNT(DISTINCT p.matricula_id) n_matriculas
           FROM ri_partes p WHERE {filtro}
           GROUP BY chave ORDER BY n_matriculas DESC, nome, chave LIMIT 60""",
        params,
    )


def buscar_por_imovel(con: Any, busca: str,
                      *, bairro: str = "", tipo: str = "") -> list[dict]:
    """A mesma régua do Indicador Real: descrição normalizada por trecho."""
    busca = (busca or "").strip()
    if not busca and not (bairro or "").strip():
        raise CertidaoNegativaError(
            "Informe a descrição do imóvel (ou o bairro) para buscar antes "
            "de emitir a certidão negativa.")
    onde, params = ["1=1"], []
    if busca:
        onde.append("m.imovel_norm ILIKE %s")
        params.append(f"%{normalizar_busca(busca)}%")
    if (bairro or "").strip():
        onde.append("m.bairro = %s")
        params.append(bairro.strip())
    if tipo in ("R", "U"):
        onde.append("m.rural_urbano = %s")
        params.append(tipo)
    filtro = " AND ".join(onde)
    return banco(con).ler(
        f"""SELECT m.id, m.numero, m.logradouro, m.bairro
            FROM ri_matriculas m WHERE {filtro}
            ORDER BY coalesce(substring(m.numero FROM '^[0-9]+')::bigint, 0), m.id
            LIMIT 60""",
        params,
    )


def conferir_negativa(achados: list) -> None:
    """Negativa só sai quando a busca realmente não achou."""
    if achados:
        raise CertidaoNegativaError(
            f"Não se emite certidão negativa: a busca achou "
            f"{len(achados)} resultado(s). Negativa só quando nada consta.")


def montar_identificacao(busca: str, *, modo: str, con=None) -> dict:
    """O que entra no papel sobre o critério da busca.

    O TEXTO SAIU DAQUI — LF06B (19/10/2026): cada frase do critério é papel do
    catálogo (`modelos_padrao/ri/RI_NEGATIVA_CRITERIO_*.txt`), e a casa a edita
    na tela de Modelos. A REGRA ficou aqui: documento, nome ou descrição do
    imóvel é decidido pelo que se digitou e pelo modo. Sem `con`, sai o padrão
    da base.
    """
    import ri_frases as FRASES

    busca = (busca or "").strip()
    doc = so_digitos(busca)
    if modo == "PESSOA":
        if doc and len(doc) in (11, 14) and doc == so_digitos(busca):
            # Busca foi só o documento.
            return {
                "criterio_rotulo": FRASES.frase(
                    "RI_NEGATIVA_CRITERIO_DOCUMENTO", con, documento=doc),
                "pesquisado": "",
                "pesquisado_documento": doc,
                "imovel_busca": "",
            }
        return {
            "criterio_rotulo": FRASES.frase(
                "RI_NEGATIVA_CRITERIO_NOME", con, nome=busca),
            "pesquisado": busca,
            "pesquisado_documento": "",
            "imovel_busca": "",
        }
    return {
        "criterio_rotulo": FRASES.frase(
            "RI_NEGATIVA_CRITERIO_IMOVEL", con, descricao=busca),
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


def __getattr__(nome: str):
    """Os nomes antigos do texto de fábrica, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06A (19/10/2026) e mora em `modelos_padrao/`.
    Quem ainda importa o nome antigo recebe o padrão da base — o MESMO que o
    papel imprime, e não uma cópia que ficou para trás. Nome que não é de papel
    continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
