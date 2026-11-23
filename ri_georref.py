"""A CONFERÊNCIA DO GEORREFERENCIAMENTO NO ATO — art. 343-F, II, do Código Nacional de Normas.

    «Compete aos oficiais de registro de imóveis [...] II — quando da prática de atos que
    envolvam a abertura de matrícula ou a atualização, a correção ou a alteração da
    descrição perimetral do imóvel, analisar o mosaico registral criado no SIG-RI, a fim
    de verificar a ocorrência de alguma das situações abaixo: a) descrição perimétrica que
    apresente coordenadas polares com erros de fechamento do polígono; b) sobreposições de
    área com outros imóveis.»
    (CNN, art. 343-F, II, incluído pelo Provimento CN n. 195, de 3.6.2025;
    `base_normativa/nacional/codigo_nacional_de_normas_cnj.md`)

O QUE ESTE MÓDULO FAZ — E O QUE NÃO FAZ
    Faz o PASSO: no ato que abre matrícula ou mexe no perímetro, a tela pergunta se o
    mosaico foi conferido e **grava quem respondeu, quando e o quê** — uma linha em
    `ri_georref_conferencias`, ao lado do ato, como a consulta à CNIB (`ri_atos_cnib`).

    **Não consulta o SIG-RI** (o Gestão não fala com o Mapa do ONR) e **não decide** se há
    erro de fechamento ou sobreposição: o que se grava é a DECLARAÇÃO da pessoa. Quando a
    geometria estiver guardada aqui (`ri_geo.py`, PR seguinte), a tela do mapa faz essas
    duas contas; este passo continua sendo o registro de que alguém olhou.

AVISA, NÃO BLOQUEIA — ordem da tarefa RI011
    Conferência em branco, «conferirei depois» ou conta de robô: o ato sai do mesmo jeito,
    com a conferência gravada como PENDENTE e um aviso na tela. O que esteja pendente
    aparece na ficha e na lista `/registro-imoveis/georreferenciamento`, e se resolve
    depois, por uma linha nova que aponta para a pendente (`refere_id`) — a linha antiga
    não se apaga nem se reescreve: o que se afirmou fica.

QUEM CONFERE É PESSOA
    Como a afirmação expressa (`afirmacoes_expressas`), conferência é de pessoa: conta de
    robô não confere. O nome vem de `usuario_nome()`, que devolve a marca «PENDENTE — assina
    quem selar» quando a sessão é de robô; aí a linha nasce PENDENTE, sem nome de máquina.

QUAIS ATOS PEDEM O PASSO
    `exige_conferencia`: a natureza (vocabulário do SAUIN, `ri_naturezas`) que abre matrícula
    ou muda o perímetro — loteamento, usucapião, desmembramento, unificação, remembramento,
    atualização de confrontação, retificação de área, novas divisas — e os modelos de
    georreferenciamento e de unificação. **A lista é conservadora e é do oficial**: natureza
    fora dela também pode ser conferida (o campo existe em todo ato); o que ela decide é só
    o aviso quando fica em branco. A abertura de matrícula (`/registro-imoveis/nova`) pede o
    passo sempre.

O QUE FICA FORA DESTE PASSO
    O inciso III do mesmo artigo — «em qualquer ato, valer-se do SIG-RI para averiguar
    especialidade objetiva, disponibilidade e unicidade» — é outra conferência, em todo ato,
    e não está aqui. A alimentação do SIG-RI com os perímetros (inciso I) também não.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Mapping

from bd_nativo import banco

#: O dispositivo, como a tela o cita.
DISPOSITIVO = "art. 343-F, II, do Código Nacional de Normas (Provimento CNJ 195/2025)"

# Em que momento a conferência foi feita.
OCASIAO_ABERTURA = "ABERTURA"   # abertura de matrícula (`/registro-imoveis/nova`)
OCASIAO_ATO = "ATO"             # ato que altera o perímetro (ou qualquer ato em que se quis conferir)
OCASIAO_AVULSA = "AVULSA"       # feita depois, pela ficha, sem ato novo
OCASIOES = (OCASIAO_ABERTURA, OCASIAO_ATO, OCASIAO_AVULSA)

# O que a pessoa declarou.
SEM_OCORRENCIA = "SEM_OCORRENCIA"                # conferido: fechamento e sobreposição, nada
COM_OCORRENCIA = "COM_OCORRENCIA"                # conferido: achou erro de fechamento ou sobreposição
NAO_GEORREFERENCIADO = "NAO_GEORREFERENCIADO"    # o imóvel não tem coordenadas: não há mosaico a conferir
PENDENTE = "PENDENTE"                            # não conferiu ainda («depois», em branco ou robô)
SITUACOES = (SEM_OCORRENCIA, COM_OCORRENCIA, NAO_GEORREFERENCIADO, PENDENTE)

#: O que o formulário escolhe. «PENDENTE» é a escolha explícita de deixar para depois; o campo em
#: branco dá o mesmo resultado, com o aviso de que ninguém respondeu.
ROTULOS = {
    SEM_OCORRENCIA: "Conferi o mosaico: sem erro de fechamento e sem sobreposição",
    COM_OCORRENCIA: "Conferi o mosaico: há ocorrência (descreva abaixo)",
    NAO_GEORREFERENCIADO: "O imóvel não tem coordenadas (não georreferenciado): não há mosaico a conferir",
    PENDENTE: "Conferirei depois",
}
#: As que fecham a obrigação do passo. `PENDENTE` não.
CONFERIDAS = (SEM_OCORRENCIA, COM_OCORRENCIA, NAO_GEORREFERENCIADO)

#: O texto da ocorrência não pode ser só pontuação: o piso é de letras, como nas outras afirmações da casa.
MINIMO_DE_LETRAS_DA_OCORRENCIA = 10

#: Naturezas de `ri_naturezas` que abrem matrícula ou alteram o perímetro. Ver o cabeçalho: a lista é do oficial.
CODIGOS_QUE_PEDEM = frozenset({
    28, 29,        # loteamento urbano / rural
    34, 35,        # usucapião (sentença / extrajudicial)
    84, 85, 86,    # desmembramento, unificação, remembramento
    92,            # indicação ou atualização de confrontação
    93,            # retificação de área
    124,           # alteração de novas divisas
})
#: Os modelos de `ri_modelos_atos` que são o próprio georreferenciamento ou a unificação.
MODELOS_QUE_PEDEM = frozenset({"AV-GEORREFERENCIAMENTO", "AV-UNIFICACAO"})
#: Quando a natureza vem escrita à mão e não casa com a lista, a palavra decide (sem acento, minúscula).
PALAVRAS_QUE_PEDEM = ("georreferenc", "desmembr", "unificac", "remembr", "retificacao de area",
                      "novas divisas", "perimetro", "confrontac")

SCHEMA = """
CREATE TABLE IF NOT EXISTS ri_georref_conferencias (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    matricula_id INTEGER NOT NULL,
    -- Sem chave estrangeira no ato, como `ri_atos_cnib`: o ato que sai do livro (suspenso ou
    -- expurgado) larga a conferência (`soltar_do_ato`), e ela fica na ficha.
    ato_id INTEGER,
    ato_rotulo TEXT,
    ocasiao TEXT NOT NULL,
    natureza_titulo TEXT,
    situacao TEXT NOT NULL,
    observacao TEXT,
    -- A linha que esta resolve: uma PENDENTE a que a pessoa voltou. A pendente não se reescreve.
    refere_id INTEGER,
    conferido_por TEXT,
    conferido_por_id INTEGER,
    conferido_em TEXT NOT NULL,
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id)
);
CREATE INDEX IF NOT EXISTS ix_ri_georref_mat ON ri_georref_conferencias(matricula_id);
CREATE INDEX IF NOT EXISTS ix_ri_georref_ato ON ri_georref_conferencias(ato_id);
CREATE INDEX IF NOT EXISTS ix_ri_georref_refere ON ri_georref_conferencias(refere_id);
"""


class GeorrefError(ValueError):
    """O pedido não cabe no contrato (ocasião ou situação desconhecida, linha que não existe)."""


def init_georref_schema(con) -> None:
    """A tabela. Idempotente; roda a cada subida, depois de `init_ri_schema` (a chave estrangeira)."""
    bd = banco(con)
    for comando in SCHEMA.split(";"):
        if comando.strip():
            bd.escrever(comando)


# ------------------------------------------------------------------ quais atos pedem

def _sem_acento(texto: Any) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or ""))
                   if unicodedata.category(c) != "Mn").lower()


def exige_conferencia(natureza_titulo: Any = None, modelo_codigo: Any = None) -> bool:
    """O ato abre matrícula ou altera o perímetro? Só calcula.

    Por modelo (`AV-GEORREFERENCIAMENTO`, `AV-UNIFICACAO`); senão pelo nome exato da natureza na tabela do SAUIN;
    senão pela palavra — e a palavra **não vale para cancelamento**, como em `ri_cnib.codigo_reconhecido`:
    «Cancelamento de Matrícula» não muda o perímetro de ninguém.
    """
    import ri_naturezas as NAT
    if str(modelo_codigo or "").strip().upper() in MODELOS_QUE_PEDEM:
        return True
    texto = str(natureza_titulo or "").strip()
    if not texto:
        return False
    achado = NAT.POR_NOME.get(texto.lower())
    if achado is not None:
        return int(achado[0]) in CODIGOS_QUE_PEDEM
    sem = _sem_acento(texto)
    if "cancel" in sem:
        return False
    return any(p in sem for p in PALAVRAS_QUE_PEDEM)


# ------------------------------------------------------------------ gravar

def _letras(texto: Any) -> int:
    return sum(1 for c in str(texto or "") if c.isalpha())


def interpretar(situacao: Any, observacao: Any, *, robo: bool = False) -> tuple[str, str, list[str]]:
    """`(situação, observação, avisos)` que vão para a linha. Nunca recusa: o passo avisa, não bloqueia.

    Em branco ou desconhecida vira PENDENTE; conta de robô também (máquina não confere). A ocorrência sem texto
    grava assim mesmo — e o aviso diz que falta descrevê-la.
    """
    avisos: list[str] = []
    obs = " ".join(str(observacao or "").split())
    escolhida = str(situacao or "").strip().upper()
    if robo:
        if escolhida in CONFERIDAS:
            avisos.append("Conferência é de pessoa: esta conta é de robô, e a conferência ficou PENDENTE. "
                          "Quem lavra confere no próprio usuário.")
        escolhida = PENDENTE
    elif escolhida not in SITUACOES:
        if escolhida:
            avisos.append(f"Situação «{escolhida}» desconhecida: a conferência ficou PENDENTE.")
        escolhida = PENDENTE
    if escolhida == COM_OCORRENCIA and _letras(obs) < MINIMO_DE_LETRAS_DA_OCORRENCIA:
        avisos.append("A ocorrência foi gravada sem descrição: diga na ficha qual (erro de fechamento, "
                      "sobreposição com qual matrícula).")
    return escolhida, obs, avisos


def registrar(con, *, matricula_id: int, ocasiao: str, situacao: Any, observacao: Any = "",
              ato_id: int | None = None, ato_rotulo: str | None = None,
              natureza_titulo: str | None = None, refere_id: int | None = None,
              quem: str | None = None, quem_id: int | None = None,
              robo: bool = False, agora: str) -> dict:
    """Grava a conferência e devolve a linha, com `avisos` (lista de frases) e `pendente` (bool).

    Chamar **na transação do ato** (ou da abertura): se o ato não entra, a conferência não fica órfã. Quem
    chama já sabe se a sessão é de robô (`usuario_nome()` devolveu a marca de pendente): passa `robo=True`.
    """
    if ocasiao not in OCASIOES:
        raise GeorrefError(f"Ocasião desconhecida: {ocasiao!r}.")
    bd = banco(con)
    if refere_id is not None:
        antiga = bd.um("SELECT id, matricula_id, situacao FROM ri_georref_conferencias WHERE id = %s",
                       (int(refere_id),))
        if not antiga or int(antiga["matricula_id"]) != int(matricula_id):
            raise GeorrefError("A conferência que se quer resolver não é desta matrícula.")
    escolhida, obs, avisos = interpretar(situacao, observacao, robo=robo)
    nome = None if robo else ((quem or "").strip() or None)
    novo = bd.escrever(
        """INSERT INTO ri_georref_conferencias
              (matricula_id, ato_id, ato_rotulo, ocasiao, natureza_titulo, situacao, observacao,
               refere_id, conferido_por, conferido_por_id, conferido_em)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (int(matricula_id), ato_id, ato_rotulo, ocasiao, (natureza_titulo or None), escolhida,
         obs or None, refere_id, nome, None if robo else quem_id, agora))
    return {"id": int(novo[0]["id"]), "matricula_id": int(matricula_id), "ato_id": ato_id,
            "ato_rotulo": ato_rotulo, "ocasiao": ocasiao, "situacao": escolhida,
            "observacao": obs, "refere_id": refere_id, "conferido_por": nome,
            "conferido_em": agora, "avisos": avisos, "pendente": escolhida == PENDENTE}


def soltar_do_ato(con, ato_id: int) -> None:
    """O ato saiu do livro (suspenso ou expurgado): a conferência fica na ficha."""
    banco(con).escrever("UPDATE ri_georref_conferencias SET ato_id = NULL WHERE ato_id = %s",
                        (int(ato_id),))


# ------------------------------------------------------------------ ler

def da_matricula(con, matricula_id: int) -> dict:
    """Tudo o que a ficha mostra: `{por_ato, abertura, avulsas, pendentes}`.

    `por_ato`     a última conferência de cada ato (`{ato_id: linha}`)
    `abertura`    a última da abertura da matrícula, ou `None`
    `avulsas`     as feitas depois, pela ficha, da mais nova para a mais antiga
    `pendentes`   as PENDENTES a que ninguém voltou, da mais antiga (a que espera há mais tempo) para a mais nova
    """
    linhas = banco(con).ler(
        "SELECT * FROM ri_georref_conferencias WHERE matricula_id = %s ORDER BY id",
        (int(matricula_id),))
    resolvidas = {int(r["refere_id"]) for r in linhas if r["refere_id"] is not None}
    por_ato: dict[int, dict] = {}
    abertura = None
    avulsas: list[dict] = []
    for r in linhas:
        if r["ato_id"] is not None:
            por_ato[int(r["ato_id"])] = r
        if r["ocasiao"] == OCASIAO_ABERTURA and r["refere_id"] is None:
            abertura = r
        if r["ocasiao"] == OCASIAO_AVULSA:
            avulsas.append(r)
    pendentes = [r for r in linhas
                 if r["situacao"] == PENDENTE and int(r["id"]) not in resolvidas]
    return {"por_ato": por_ato, "abertura": abertura, "avulsas": avulsas[::-1],
            "pendentes": pendentes, "resolvidas": resolvidas}


def pendentes(con, limite: int = 500) -> list[dict]:
    """As conferências pendentes de toda a serventia, da que espera há mais tempo, com a matrícula.

    Matrícula encerrada fica de fora: não se confere mosaico de ficha que não vale mais — o mesmo corte do
    mapa (`ri_mapa_onr`).
    """
    return banco(con).ler(
        """SELECT c.*, m.numero AS matricula_numero, m.complemento AS matricula_complemento
             FROM ri_georref_conferencias c
             JOIN ri_matriculas m ON m.id = c.matricula_id
            WHERE c.situacao = %s
              AND NOT EXISTS (SELECT 1 FROM ri_georref_conferencias r WHERE r.refere_id = c.id)
              AND COALESCE(m.encerrada, 0) = 0
            ORDER BY c.id
            LIMIT %s""",
        (PENDENTE, int(limite)))


def frase(linha: Mapping[str, Any] | None) -> str:
    """Uma linha de texto para a ficha: o que se declarou, por quem e quando."""
    if not linha:
        return ""
    rotulo = ROTULOS.get(linha["situacao"], linha["situacao"])
    quem = f" por {linha['conferido_por']}" if linha["conferido_por"] else ""
    quando = str(linha["conferido_em"] or "")[:16].replace("T", " ")
    obs = f" — {linha['observacao']}" if linha["observacao"] else ""
    return f"{rotulo}{obs} · {quando}{quem}"


def aviso_do_ato(natureza_titulo: Any, linha: Mapping[str, Any] | None) -> str | None:
    """A frase de aviso depois de lavrar, ou `None` quando não há o que avisar."""
    if not linha:
        return None
    if linha["situacao"] == PENDENTE:
        return ("Georreferenciamento: a conferência do mosaico no SIG-RI (" + DISPOSITIVO + ") ficou PENDENTE. "
                "O ato foi lavrado; a conferência pode ser feita depois, na ficha, em «Georreferenciamento».")
    if linha["situacao"] == COM_OCORRENCIA:
        return ("Georreferenciamento: a conferência apontou ocorrência. Confira a descrição do perímetro e as "
                "matrículas vizinhas — o ato foi lavrado.")
    return None
