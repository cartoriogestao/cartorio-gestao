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

# A POSITIVA POR PESSOA — 25/10/2026, o oficial («relação dos imóveis
# atuais»), para os pedidos do ONR por pessoa (PEDIDO_POR 6). Até aqui só a
# negativa existia por pessoa: quando a busca achava, nenhum papel dizia O QUE
# se achou. Ela lista as matrículas ABERTAS em que a pessoa escolhida consta
# HOJE como proprietária (`ri_partes.proprietario_ativo`). Mesma rota, mesmo
# número, mesmo selo (16.24.1, o da negativa e da propriedade) e mesmo hash.
#
#   A PESSOA SE ESCOLHE, E NÃO SE DEDUZ. 71% das partes do acervo não têm
#   documento, e a busca por nome devolve homônimos: a certidão afirma QUEM é o
#   dono, e quem decide qual dos grupos é a pessoa pedida é o escrevente
#   (`pessoa_chave`, a mesma chave do Indicador Pessoal).
TIPO_POSITIVA = "POSITIVA_PESSOA"
NOME_DO_TIPO_POSITIVA = "Certidão de propriedade por pessoa (positiva)"
CHAVE_MODELO_POSITIVA = "RI_CERTIDAO_POSITIVA_PESSOA"


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


def _numero_da_matricula(numero: Any) -> int:
    digitos = ""
    for ch in str(numero or ""):
        if not ch.isdigit():
            break
        digitos += ch
    return int(digitos) if digitos else 0


def candidatas_da_positiva(con: Any, chave: str) -> list[dict]:
    """As matrículas que a positiva PODE listar para a pessoa escolhida, cada
    uma com os proprietários como estão na ficha. Só LÊ.

    O ESCREVENTE MARCA UMA A UMA (o oficial, 25/10/2026). A chave do
    Indicador Pessoal junta homônimos sem documento e parte a mesma pessoa
    que tem CPF numa matrícula e não noutra (revisão do Agente RI). Por isso
    entram também as matrículas de OUTROS grupos com o mesmo nome — e a
    certidão sai só com as que o escrevente conferiu e marcou.

    O CPF NÃO INCLUI NEM EXCLUI SOZINHO — e houve regra que dizia o contrário,
    revogada pelo oficial no mesmo dia (25/10/2026): «as matrículas aqui são
    muito bagunçadas para excluir por CPF, tem gente com CPF de outra pessoa».
    O documento só aparece na tela, para o escrevente decidir."""
    bd = banco(con)
    chave = (chave or "").strip()
    nomes = [r["nome_norm"] for r in bd.ler(
        """SELECT DISTINCT nome_norm FROM ri_partes
            WHERE COALESCE(NULLIF(documento_numero,''), nome_norm) = %s
              AND COALESCE(nome_norm,'') <> ''""", (chave,))]
    marcas = ",".join(["%s"] * len(nomes)) or "NULL"
    linhas = bd.ler(
        f"""SELECT m.id, m.numero, m.livro_norm, m.tipo_imovel, m.rural_urbano,
                   m.logradouro, m.numero_predial, m.complemento_endereco,
                   m.bairro, m.cidade, m.uf, m.area_valor, m.area_unidade,
                   MAX(CASE WHEN COALESCE(NULLIF(p.documento_numero,''), p.nome_norm) = %s
                            THEN 1 ELSE 0 END) AS da_pessoa
              FROM ri_partes p JOIN ri_matriculas m ON m.id = p.matricula_id
             WHERE p.proprietario_ativo = 1 AND COALESCE(m.encerrada, 0) = 0
               AND (COALESCE(NULLIF(p.documento_numero,''), p.nome_norm) = %s
                    OR p.nome_norm IN ({marcas}))
             GROUP BY m.id""", (chave, chave, *nomes))
    # OS DONOS DE TODAS DE UMA VEZ (revisão do Agente RI): uma consulta por
    # matrícula daria centenas para abrir o Indicador Pessoal num nome comum.
    ids = [int(m["id"]) for m in linhas]
    donos: dict[int, list[dict]] = {i: [] for i in ids}
    if ids:
        for d in bd.ler(
                f"""SELECT matricula_id, nome, documento_numero FROM ri_partes
                     WHERE proprietario_ativo = 1
                       AND matricula_id IN ({",".join(["%s"] * len(ids))})
                     ORDER BY id""", ids):
            donos[int(d["matricula_id"])].append(
                {"nome": d["nome"], "documento_numero": d["documento_numero"]})
    saida = []
    for m in sorted(linhas, key=lambda m: (_numero_da_matricula(m.get("numero")), m["id"])):
        m = dict(m)
        m["donos"] = donos.get(int(m["id"]), [])
        saida.append(m)
    return saida


def conferir_marcadas(candidatas: list, marcadas: list) -> list[dict]:
    """As matrículas marcadas pelo escrevente, conferidas contra as candidatas."""
    ids = set()
    for valor in marcadas or []:
        try:
            ids.add(int(valor))
        except (TypeError, ValueError):
            continue
    if not ids:
        raise CertidaoNegativaError(
            "Marque, uma a uma, as matrículas que são da pessoa pedida — a "
            "certidão positiva sai só com as conferidas.")
    por_id = {int(c["id"]): c for c in candidatas}
    fora = ids - set(por_id)
    if fora:
        raise CertidaoNegativaError(
            "Uma matrícula marcada não é de proprietário atual com este nome. "
            "Busque de novo e marque outra vez.")
    return [c for c in candidatas if int(c["id"]) in ids]


def conferir_positiva(achados: list, pessoa_chave: str) -> dict:
    """A pessoa escolhida está entre as achadas? Devolve o grupo dela.

    Positiva só sai sobre a pessoa que o escrevente escolheu na busca: com mais
    de um grupo e nada escolhido, recusa — escolher pelo sistema seria afirmar
    a propriedade de um homônimo."""
    pessoa_chave = (pessoa_chave or "").strip()
    if not achados:
        raise CertidaoNegativaError(
            "A busca não achou ninguém: não há o que certificar como positiva. "
            "Se nada consta, emita a certidão negativa.")
    if not pessoa_chave:
        if len(achados) > 1:
            raise CertidaoNegativaError(
                f"A busca achou {len(achados)} pessoas. Escolha qual delas é a "
                "pedida antes de emitir a certidão positiva.")
        return achados[0]
    for grupo in achados:
        if str(grupo.get("chave") or "") == pessoa_chave:
            return grupo
    raise CertidaoNegativaError(
        "A pessoa escolhida não está entre as que a busca achou. Busque de novo.")


def descricao_curta(m: dict) -> str:
    """Uma linha do imóvel para a relação da positiva. Só calcula."""
    endereco = ", ".join(x for x in (
        str(m.get("logradouro") or "").strip(),
        str(m.get("numero_predial") or "").strip(),
        str(m.get("complemento_endereco") or "").strip()) if x)
    partes = [str(m.get("tipo_imovel") or "").strip(), endereco,
              str(m.get("bairro") or "").strip()]
    lugar = "/".join(x for x in (str(m.get("cidade") or "").strip(),
                                 str(m.get("uf") or "").strip()) if x)
    if lugar:
        partes.append(lugar)
    area = str(m.get("area_valor") or "").strip()
    if area:
        partes.append(f"área {area} {str(m.get('area_unidade') or '').strip()}".strip())
    return " — ".join(x for x in partes if x)


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
                  criterio: str, tipo: str = TIPO) -> str:
    payload = json.dumps(
        {"numero": int(numero), "ano": int(ano), "tipo": tipo,
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
