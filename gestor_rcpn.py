"""O agente do RCPN — fiscaliza o ato, orienta o balcão e resolve o que é objetivo.

    «Agente de RCPN: esse agente fica responsavel por fiscalizar, orientar e
     resolver problemas do RCPN no cartorio» — o oficial, 09/10/2026

A FRONTEIRA COM O AGENTE DE CARGAS DO RCPN (combinada entre as duas sessões
em 09/10/2026)
    | é deste agente                         | é do `gestor_cargas_rcpn`          |
    |----------------------------------------|------------------------------------|
    | o ASSENTO: duplicidade, sem número,    | SIRC e cancelamento no SIRC, CRC,  |
    | sem termo, dado obrigatório faltando   | IBGE, FUNAI, óbitos mensais,       |
    | as anotações do art. 367 (5 dias)      | e-Proclamas, declaração de         |
    | habilitação de casamento               | inexistência                       |
    | retificação do RCPN (`rr_processos`)   |                                    |
    | pedidos da ON-RCPN (`rc_pedidos`)      |                                    |
    | a folha de segurança                   |                                    |
    | o BOLETIM DO DIA do Registro Civil     |                                    |

    As regras de Central do `gestor_conferencia` (SIRC, CRC…) não foram
    tocadas. O boletim as LISTA, lendo `ge_achados`; não recalcula nada — duas
    réguas para o mesmo prazo divergiriam no primeiro conserto.

O QUE ESTE AGENTE ACHOU NO DIA EM QUE NASCEU (produção, só leitura, 09/10/2026)
    - **um óbito lavrado duas vezes no mesmo dia**: MOACIR SILVA PEREIRA,
      termos 1983 e 1984 (assentos 8375 e 8376), com 87 segundos de diferença,
      mesma data do fato (26/09) e os dois ATIVOS;
    - **um nascimento ATIVO sem número de termo** (8362, PAULO DUARTINO SILVA
      GOMES), com a mesma DNV do termo 19578 (8363) — a primeira tentativa,
      que ninguém cancelou;
    - **o casamento 1013 sem termo**: nem o assento nem o ato de registro têm
      texto — o livro B-4, fl. 41, não tem o que dizer;
    - **12 anotações do art. 367 pendentes**, a mais velha de 23/09 (o prazo é
      de cinco dias) — e duas delas nascem do óbito 1981 CANCELADO (8311), que
      nunca valeu;
    - **uma habilitação aberta (nº 2) para um casal que já casou** pela
      habilitação nº 1, aberta no mesmo dia.
    Nenhuma regra do gestor olhava qualquer uma dessas coisas.

AS TRÊS PALAVRAS DO PEDIDO
    FISCALIZAR — `conferir`, uma regra do gestor: os achados entram em
      `ge_achados` e viram tarefa do Registro Civil (rodízio Elisa/Debora)
      pelo caminho de sempre, que fecha sozinha quando o achado some.
    ORIENTAR — `GUIA` (por que existe e como resolver, regra a regra, com a
      tela) entra no texto didático das tarefas; e o BOLETIM DO DIA
      (`publicar_boletim`) junta numa tarefa só tudo o que o Registro Civil
      tem para hoje, de todas as fontes, na ordem do prazo.
    RESOLVER — `resolver` faz SOZINHO só o que é objetivo e não toca ato:
      dispensa a anotação devida por assento CANCELADO (assento cancelado
      nunca valeu; a anotação devida é a do assento que vale). Todo o resto ele
      PREPARA: a matrícula calculada, o termo que falta, o caminho da tela.
      Cada coisa que faz fica em `ge_rcpn_resolvidos`, com o antes e o porquê,
      e o interruptor `rcpn_agente_resolver` (settings) desliga a mão dele.

O QUE ELE NÃO FAZ
    Não lavra, não sela, não cancela assento, não escreve termo, não grava
    matrícula, não decide qual de dois assentos duplicados vale. Duplicidade é
    o caso mais grave da lista e é justamente o que ele NÃO resolve: cancelar
    um termo é ato do oficial (e no SIRC, «cancelamento» se identifica só pela
    matrícula — ver `sirc_remessa`).

AS REGRAS SÃO CÓDIGO
    Como no gestor: prazo e dado obrigatório têm resposta certa. Regra que
    quebra vira `NAO_MEDIU` com o erro à vista, nunca zero. O corte de
    10/09/2026 (ordem do oficial) vale aqui também: ato anterior não vira
    achado.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from gestor_conferencia import IMPLANTACAO, JANELA_DE_AVISO, ORIGENS_DO_ACERVO

QUEM = "agente do RCPN"
SETOR = "RCPN"

#: A tarefa do dia do Registro Civil. NÃO é `GESTOR`: a sincronização do gestor
#: fecha sozinha toda tarefa GESTOR que não tem achado, e o boletim não tem.
SOURCE_BOLETIM = "RCPN_DIA"

#: O interruptor da mão do agente. Configuração ganha do código.
CHAVE_RESOLVER = "rcpn_agente_resolver"

#: Art. 367 do Código de Normas do TJMA — «no prazo de cinco dias», corridos
#: (a mesma leitura de `rc_anotacao.fora_do_prazo`, que não inventa «úteis»).
ANOTACAO_DIAS = 5
#: Tolerâncias DA CASA, e não da norma — declaradas como tais nos achados.
HABILITACAO_PARADA_DIAS = 30
PEDIDO_PARADO_DIAS = 2
AGENTE_DIAS_TOLERADOS = 1

ESPECIES_COM_TERMO = ("NASCIMENTO", "CASAMENTO", "CASAMENTO_RELIGIOSO", "OBITO",
                      "NATIMORTO", "PROCLAMAS")

ROTULOS = {
    "RCPN_DUPLICIDADE": "Registro Civil — a mesma pessoa em dois assentos ativos",
    "RCPN_INACABADO": "Registro Civil — assento ativo sem número de termo",
    "RCPN_SEM_TERMO": "Registro Civil — assento lavrado sem termo",
    "RCPN_DADO_OBRIGATORIO": "Registro Civil — dado obrigatório do assento faltando",
    "RCPN_DADO_COMPLEMENTAR": "Registro Civil — dado complementar do assento",
    "RCPN_ANOTACAO": "Registro Civil — anotações do art. 367 (5 dias)",
    "RCPN_ANOTACAO_DE_CANCELADO": "Registro Civil — anotação devida por assento cancelado",
    "RCPN_HABILITACAO": "Registro Civil — habilitações de casamento",
    "RCPN_PEDIDO_CENTRAL": "Registro Civil — pedidos da ON-RCPN sem resposta",
    "RCPN_RETIFICACAO": "Registro Civil — retificações com prazo",
    "RCPN_FOLHA_SEGURANCA": "Registro Civil — folha de segurança acabando",
    "RCPN_AGENTE_PARADO": "Registro Civil — o agente do RCPN não rodou",
    # a conferência dos dados (11/10/2026) — `rc_conferencia_dados`
    "RCPN_DADOS_CONTRADITORIOS": "Registro Civil — termo, campos e pessoas que se contradizem",
    "RCPN_DADOS_A_CONFERIR": "Registro Civil — dados do assento a conferir",
    "RCPN_TERMO_ALTERADO": "Registro Civil — termo alterado depois de lavrado",
}

#: Medidas e relatadas (boletim, relatório), sem tarefa: não geram dano a
#: terceiro (ordem do oficial de 06/10/2026, art. 22 da Lei 8.935).
REGRAS_SEM_TAREFA = frozenset({"RCPN_DADO_COMPLEMENTAR", "RCPN_FOLHA_SEGURANCA",
                               "RCPN_DADOS_A_CONFERIR"})

#: «Onde abrir», no formato de `gestor_didatica.TELA`.
TELA = {
    "RCPN_DUPLICIDADE": ("Registro Civil → Assentos", "/rcpn/assentos"),
    "RCPN_INACABADO": ("Registro Civil → Assentos", "/rcpn/assentos"),
    "RCPN_SEM_TERMO": ("Registro Civil → ficha do assento → Termo", "/rcpn/assentos"),
    "RCPN_DADO_OBRIGATORIO": ("Registro Civil → ficha do assento", "/rcpn/assentos"),
    "RCPN_DADO_COMPLEMENTAR": ("Registro Civil → ficha do assento", "/rcpn/assentos"),
    "RCPN_ANOTACAO": ("Registro Civil → Anotações", "/rcpn/anotacoes"),
    "RCPN_ANOTACAO_DE_CANCELADO": ("Registro Civil → Anotações", "/rcpn/anotacoes"),
    "RCPN_HABILITACAO": ("Registro Civil → Habilitações", "/rcpn/habilitacoes"),
    "RCPN_PEDIDO_CENTRAL": ("Registro Civil → Pedidos da Central", "/rcpn/pedidos"),
    "RCPN_RETIFICACAO": ("Registro Civil → Retificações", "/rcpn/retificacoes"),
    "RCPN_FOLHA_SEGURANCA": ("Registro Civil → Folha de segurança", "/rcpn/papel"),
    "RCPN_DADOS_CONTRADITORIOS": ("Registro Civil → ficha do assento", "/rcpn/assentos"),
    "RCPN_DADOS_A_CONFERIR": ("Registro Civil → ficha do assento", "/rcpn/assentos"),
    "RCPN_TERMO_ALTERADO": ("Registro Civil → ficha do assento → Termo", "/rcpn/assentos"),
}

#: regra → (por que existe, [passos]). Entra no texto didático das tarefas.
GUIA: dict[str, tuple[str, list[str]]] = {
    "RCPN_DUPLICIDADE": (
        "A mesma pessoa está em dois assentos ATIVOS da mesma espécie (mesma DNV, "
        "ou mesmo nome e mesma data do fato). Dois termos para um fato são duas "
        "certidões no mundo, duas comunicações ao SIRC e, no óbito, o risco de o "
        "INSS cancelar o benefício errado. É o caso mais grave desta lista.",
        ["Abra os dois assentos e compare com o papel assinado no livro.",
         "Leve ao oficial: só ele decide qual termo vale e cancela o outro "
         "(averbação de cancelamento, com o motivo).",
         "Não emita certidão de nenhum dos dois até decidir.",
         "O agente de cargas segura os dois fora do SIRC e da CRC enquanto a "
         "duplicidade existir."]),
    "RCPN_INACABADO": (
        "O assento está ATIVO e não tem número de termo: começou a ser lavrado e "
        "não terminou, nem foi cancelado. Quase sempre é a primeira tentativa de "
        "um registro que depois saiu certo em outro assento.",
        ["Abra o assento. Se há outro assento com a mesma pessoa já numerado, "
         "este é a sobra: peça ao oficial o cancelamento com motivo.",
         "Se não há, termine a lavratura ou cancele — assento ativo sem número "
         "não pode ficar."]),
    "RCPN_SEM_TERMO": (
        "O assento foi lavrado (tem número, livro e folha) e não tem termo "
        "escrito. O termo é o texto que vai ao livro e que o declarante assina; "
        "sem ele a certidão de inteiro teor e a conferência do livro não têm "
        "o que mostrar.",
        ["Abra a ficha do assento → Termo. A prévia monta dos campos.",
         "Confira a prévia contra o papel assinado no livro.",
         "Clique em «Escrever o termo». Ele não se reescreve depois — corrigir é "
         "averbar ao lado."]),
    "RCPN_DADO_OBRIGATORIO": (
        "Falta no assento um dado que a lei exige no registro e na certidão "
        "(Lei 6.015/1973, arts. 54, 70 e 80): DNV, filiação, matrícula, causa "
        "da morte, regime de bens… Certidão com campo obrigatório vazio sai com "
        "«ND» num papel assinado.",
        ["Abra a ficha do assento e veja qual campo falta (está no detalhe).",
         "Se o dado está no papel assinado e só não foi digitado, complete na "
         "ficha. Se não está no livro, a correção é averbação/retificação — "
         "leve ao oficial.",
         "Matrícula: o agente já calculou a que corresponde a livro, folha e "
         "termo (no detalhe); confira e grave pela ficha."]),
    "RCPN_DADO_COMPLEMENTAR": (
        "Dados que o assento deveria ter e que não impedem a certidão: CPF do "
        "registrado, hora do nascimento, cor/raça, declarante, CPF gravado com "
        "pontuação.",
        ["Complete na ficha quando houver o dado. Não vira tarefa: aparece no "
         "boletim do dia."]),
    "RCPN_ANOTACAO": (
        "Todo casamento e todo óbito lavrado aqui manda anotar os assentos "
        "anteriores da pessoa — o nascimento e o casamento (art. 372). Se o "
        "assento anterior é daqui, anota-se aqui; se é de outra serventia, "
        "comunica-se. O prazo é de CINCO DIAS (art. 367).",
        ["Abra Registro Civil → Anotações.",
         "Para cada pendência: localize o assento anterior (CRC, se for de "
         "fora).",
         "Daqui: «Anotar aqui». De fora: gere o ofício e registre o envio "
         "(canal e protocolo).",
         "Não há assento anterior (ex.: nunca casou)? «Dispensar», com o "
         "motivo escrito."]),
    "RCPN_ANOTACAO_DE_CANCELADO": (
        "A anotação foi declarada por um assento que depois foi CANCELADO. "
        "Assento cancelado nunca valeu: não há o que anotar por ele.",
        ["O agente dispensa sozinho, com o motivo escrito, quando o interruptor "
         "«rcpn_agente_resolver» está ligado.",
         "Desligado: dispense em Registro Civil → Anotações, com o motivo."]),
    "RCPN_HABILITACAO": (
        "Habilitação de casamento com prazo correndo ou parada: edital que "
        "venceu sem decisão, habilitação perto de perder a eficácia de 90 dias "
        "(CC art. 1.532), processo aberto para um casal que já casou.",
        ["Abra Registro Civil → Habilitações e o processo do detalhe.",
         "Edital vencido: habilite ou registre a oposição.",
         "Habilitação vencida: NÃO celebre com ela — arquive e abra outra.",
         "Processo duplicado de casal já casado: arquive, com o motivo."]),
    "RCPN_PEDIDO_CENTRAL": (
        "Pedido da Central (ON-RCPN) baixado e ainda sem resposta. Quem pediu "
        "está esperando a certidão ou o registro do outro lado.",
        ["Abra Registro Civil → Pedidos da Central e atenda, rejeite ou "
         "dispense com o motivo.",
         "Pedido de REGISTRO (Unidade Interligada, e-Óbito) se lavra pela tela "
         "de assento novo, e depois se marca como registrado."]),
    "RCPN_RETIFICACAO": (
        "Processo de retificação/restauração/suprimento do RCPN com prazo "
        "correndo ou vencido (arts. 348 a 355 do Código de Normas).",
        ["Abra Registro Civil → Retificações e o processo.",
         "Antes de decidir, a consulta à CRC é obrigatória (art. 348, § 2º)."]),
    "RCPN_FOLHA_SEGURANCA": (
        "O estoque de folha de segurança está acabando. Sem folha não sai a "
        "certidão — e a primeira via do registro de nascimento é gratuita e "
        "obrigatória.",
        ["Peça a remessa ao fornecedor e registre a chegada em Registro Civil → "
         "Folha de segurança."]),
    "RCPN_DADOS_CONTRADITORIOS": (
        "O assento já lavrado tem dado que contradiz a si mesmo: a testemunha é o "
        "próprio registrado, o termo ficou com o traço de quem assina em branco, um "
        "CPF não fecha o dígito, a DNV do campo não é a do termo. É o que a "
        "conferência de 11/10/2026 passou a recusar na lavratura — estes vieram "
        "antes dela.",
        ["Abra a ficha do assento e compare com o papel assinado no livro.",
         "Se o LIVRO está certo e o erro é só do cadastro (testemunha a mais, "
         "sexo ou lado dos avós), corrija pela ficha — «corrigir informações».",
         "Se o erro está no TERMO (o texto do livro), não se reescreve: lavre a "
         "retificação ou a averbação na ficha (arts. 97 e 110 da Lei 6.015/1973).",
         "Não corrija por script direto no banco: o agente acusa termo alterado "
         "depois de lavrado."]),
    "RCPN_DADOS_A_CONFERIR": (
        "Dado que pode estar certo e merece olho humano: idade declarada que não "
        "bate com as datas, avós cujo sobrenome é o do outro genitor, CPF no "
        "campo e fora do termo.",
        ["Confira com o documento digitalizado. Não vira tarefa: aparece no "
         "boletim do dia."]),
    "RCPN_TERMO_ALTERADO": (
        "O texto do termo mudou depois de o agente o ver lavrado — sem averbação. "
        "O termo é o papel que o declarante assinou; reescrevê-lo no banco faz o "
        "sistema discordar do livro.",
        ["Leve ao oficial: ele compara o termo de antes (no detalhe) com o livro "
         "de papel.",
         "Se a mudança tem de ficar, faz-se a retificação/averbação que a "
         "justifica e o oficial reconhece o texto novo (gestor_rcpn "
         "--aceitar-termo <id>).",
         "Se não tem, o termo volta ao que estava."]),
}


# ----------------------------------------------------------------- miúdos

def _agora() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _tem_tabela(con, nome: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (nome,)).fetchone() is not None


def configuracao(con, chave: str, padrao: str = "") -> str:
    if not _tem_tabela(con, "settings"):
        return padrao
    r = con.execute("SELECT value FROM settings WHERE key=?", (chave,)).fetchone()
    return (r[0] or "").strip() if r and (r[0] or "").strip() else padrao


def resolver_ligado(con) -> bool:
    return configuracao(con, CHAVE_RESOLVER, "LIGADO").upper() != "DESLIGADO"


def _dia(texto) -> date | None:
    try:
        return date.fromisoformat(str(texto or "")[:10])
    except ValueError:
        return None


def _br(d) -> str:
    d = d if isinstance(d, date) else _dia(d)
    return f"{d:%d/%m/%Y}" if d else "—"


def _digitos(v) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def _norm(nome) -> str:
    import pt_schema
    return pt_schema.normalizar_nome(nome) or ""


def _vazio(v) -> bool:
    return v is None or str(v).strip() == ""


def _achado(chave, regra, gravidade, titulo, detalhe="", prazo=None,
            fundamento="", setor=SETOR) -> dict:
    return {"chave": chave, "regra": regra, "gravidade": gravidade,
            "setor": setor, "titulo": titulo, "detalhe": detalhe,
            "prazo": prazo.isoformat() if isinstance(prazo, date) else prazo,
            "fundamento": fundamento}


def _rotulo_do_assento(a) -> str:
    especie = str(a["especie"] or "").replace("_", " ").lower()
    num = f"nº {a['numero']}" if a["numero"] is not None else "sem número"
    return f"{especie} {num} ({a['nome'] or '—'})"


def _do_sistema_desde_o_corte() -> str:
    """O pedaço de WHERE dos assentos que esta casa lavrou depois do corte."""
    return (f"data_ato >= ? AND COALESCE(origem,'') NOT IN "
            f"({','.join('?' * len(ORIGENS_DO_ACERVO))})")


SCHEMA = """
-- O DIÁRIO DO AGENTE DO RCPN: cada rodada, o que resolveu e onde quebrou.
CREATE TABLE IF NOT EXISTS ge_rcpn_execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hoje TEXT NOT NULL,
    iniciada_em TEXT NOT NULL,
    terminada_em TEXT,
    situacao TEXT NOT NULL DEFAULT 'RODANDO',   -- RODANDO | OK | ERRO
    detalhe TEXT
);

-- O QUE O AGENTE FEZ SOZINHO, com o antes e o porquê. É a fila de revisão do
-- oficial para a mão do agente: «ele fiscaliza e revisa depois».
CREATE TABLE IF NOT EXISTS ge_rcpn_resolvidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    o_que TEXT NOT NULL,                        -- ANOTACAO_DISPENSADA
    tabela TEXT NOT NULL,
    registro_id INTEGER NOT NULL,
    antes TEXT,
    depois TEXT,
    motivo TEXT NOT NULL,
    feito_em TEXT NOT NULL,
    revisado_em TEXT,
    revisado_por TEXT
);

-- A IMPRESSÃO DIGITAL DE CADA TERMO LAVRADO NESTA CASA (11/10/2026). A
-- primeira vez que o agente vê o termo, guarda o sha256 e o texto; se o texto
-- mudar depois, sem averbação, a conferência acusa. Existe porque termos
-- assinados foram reescritos por script direto no banco, e só o próprio script
-- sabia disso.
CREATE TABLE IF NOT EXISTS ge_rcpn_termos (
    assento_id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL,
    teor TEXT NOT NULL,
    visto_em TEXT NOT NULL,
    aceito_por TEXT
);
"""


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


# ======================================================= 1. O ASSENTO

def duplicidades(con: sqlite3.Connection) -> list[dict]:
    """Grupos de assentos ATIVOS da mesma pessoa. SÓ LÊ.

    Nascimento: mesma DNV (só os dígitos — o balcão escreve com e sem traço).
    Óbito e casamento: mesmo nome e mesma data do fato. Gêmeos não caem aqui:
    cada um tem a sua DNV e o seu nome. Só entram grupos em que ao menos um
    assento é desta casa e posterior ao corte — o acervo não vira atraso.

    Não diz qual vale (`manter_sugerido` fica None): isso é do oficial.
    Também chamada pelo agente de cargas do RCPN, que retém os grupos da carga.
    """
    con.row_factory = sqlite3.Row
    linhas = [dict(r) for r in con.execute(
        """SELECT id, especie, numero, nome, data_fato, data_ato, dnv, origem
             FROM rc_assentos WHERE COALESCE(situacao,'ATIVO') = 'ATIVO'
              AND especie IN ('NASCIMENTO','OBITO','CASAMENTO','CASAMENTO_RELIGIOSO',
                              'NATIMORTO')""")]
    chaves: dict[tuple, list[dict]] = {}
    for a in linhas:
        if a["especie"] == "NASCIMENTO":
            dnv = _digitos(a["dnv"])
            if len(dnv) >= 8 and set(dnv) != {"0"}:
                chaves.setdefault(("DNV", dnv), []).append(a)
        elif not _vazio(a["nome"]) and not _vazio(a["data_fato"]):
            chaves.setdefault(("NOME+DATA_FATO", a["especie"], _norm(a["nome"]),
                               str(a["data_fato"])[:10]), []).append(a)
    grupos = []
    for chave, membros in chaves.items():
        if len(membros) < 2:
            continue
        novos = [m for m in membros if str(m["data_ato"] or "") >= IMPLANTACAO
                 and (m["origem"] or "") not in ORIGENS_DO_ACERVO]
        if not novos:
            continue
        membros.sort(key=lambda m: m["id"])
        grupos.append({"especie": membros[0]["especie"], "por": chave[0],
                       "ids": [m["id"] for m in membros],
                       "numeros": [m["numero"] for m in membros],
                       "nome": membros[0]["nome"], "membros": membros,
                       "manter_sugerido": None})
    return grupos


def inacabados(con: sqlite3.Connection) -> list[dict]:
    """Assentos ATIVOS desta casa, desde o corte, sem número de termo. SÓ LÊ.

    `gemeo_de` é o assento numerado com a mesma DNV — a sobra quase sempre é
    a primeira tentativa dele. Também chamada pelo agente de cargas.
    """
    con.row_factory = sqlite3.Row
    saida = []
    for a in con.execute(
            f"""SELECT id, especie, numero, nome, dnv, data_ato, criado_por
                  FROM rc_assentos WHERE {_do_sistema_desde_o_corte()}
                   AND COALESCE(situacao,'ATIVO') = 'ATIVO' AND numero IS NULL""",
            (IMPLANTACAO, *ORIGENS_DO_ACERVO)).fetchall():
        par = None
        dnv = _digitos(a["dnv"])
        if dnv:
            for b in con.execute(
                    """SELECT id, numero, dnv FROM rc_assentos WHERE id <> ?
                          AND numero IS NOT NULL AND COALESCE(situacao,'ATIVO')='ATIVO'
                          AND especie = ?""", (a["id"], a["especie"])):
                if _digitos(b["dnv"]) == dnv:
                    par = {"id": b["id"], "numero": b["numero"]}
                    break
        saida.append({"id": a["id"], "especie": a["especie"], "nome": a["nome"],
                      "data_ato": a["data_ato"], "criado_por": a["criado_por"],
                      "gemeo_de": par["id"] if par else None,
                      "gemeo_numero": par["numero"] if par else None})
    return saida


def _registro_do_assento(con, assento_id: int):
    """O ato de REGISTRO (livro, folha, termo) e o número do livro."""
    r = con.execute(
        """SELECT t.id, t.livro_id, t.folha, t.numero_ordem, t.teor, l.numero AS livro,
                  l.serie
             FROM rc_atos t LEFT JOIN nu_livros l ON l.id = t.livro_id
            WHERE t.assento_id = ? AND t.tipo = 'REGISTRO' ORDER BY t.id DESC LIMIT 1""",
        (assento_id,)).fetchone()
    return dict(r) if r else None


def _nome_do_livro(reg: dict) -> str:
    """«B-4», como o livro de papel se chama: a letra sai da série (RC_B)."""
    serie = str(reg.get("serie") or "")
    letra = serie[3:] if serie.startswith("RC_") else ""
    return f"{letra}-{reg['livro']}" if letra else str(reg["livro"])


def matricula_proposta(con, assento: dict) -> str | None:
    """A matrícula de 32 dígitos que livro, folha e termo dão. NÃO GRAVA.

    «O que se calcula pode ser mostrado sem ser gravado»: quem grava é o
    balcão, pela ficha, depois de conferir.
    """
    import rc_matricula
    cns = configuracao(con, "ri_cns", "")
    reg = _registro_do_assento(con, assento["id"])
    if not cns or not reg or _vazio(reg.get("livro")) or _vazio(reg.get("folha")):
        return None
    try:
        return rc_matricula.compor_do_assento(
            {**assento, "livro": reg["livro"], "folha": reg["folha"]}, cns=cns)
    except Exception:                                   # noqa: BLE001
        return None


#: O que falta, por espécie: (rótulo, como saber se falta). CRÍTICO.
def _faltas_obrigatorias(con, a: dict, papeis: set[str]) -> list[str]:
    esp = a["especie"]
    falta = []
    if _vazio(a["matricula"]):
        falta.append("matrícula")
    if esp == "NASCIMENTO":
        if _vazio(a["dnv"]) and not a["registro_tardio"]:
            falta.append("DNV (e não está marcado como registro tardio)")
        for papel, nome in (("REGISTRADO", "a pessoa registrada"), ("MAE", "a mãe")):
            if papel not in papeis:
                falta.append(nome)
    elif esp == "OBITO":
        if "FALECIDO" not in papeis:
            falta.append("a pessoa falecida")
        if _vazio(a["causa_morte"]):
            falta.append("causa da morte (art. 80, 6º)")
        if _vazio(a["local_sepultamento"]):
            falta.append("lugar do sepultamento (art. 80, 8º)")
        if _vazio(a["numero_do"]) and not a["obito_desconhecido"]:
            falta.append("número da Declaração de Óbito")
    elif esp in ("CASAMENTO", "CASAMENTO_RELIGIOSO"):
        for papel in ("NUBENTE1", "NUBENTE2"):
            if papel not in papeis:
                falta.append(f"o {papel[-1]}º cônjuge")
        if _vazio(a["regime_bens"]):
            falta.append("regime de bens (art. 70, 6º)")
    return falta


def _faltas_complementares(a: dict, papeis: set[str]) -> list[str]:
    falta = []
    if a["especie"] == "NASCIMENTO":
        if _vazio(a["cpf_registrado"]):
            falta.append("CPF do registrado")
        if _vazio(a["hora_fato"]):
            falta.append("hora do nascimento")
        if _vazio(a["cor_raca"]):
            falta.append("cor/raça")
        if "DECLARANTE" not in papeis:
            falta.append("declarante")
    cpf = str(a["cpf_registrado"] or "")
    if cpf and cpf != _digitos(cpf):
        falta.append(f"CPF gravado com pontuação («{cpf}» — as remessas esperam só os dígitos)")
    return falta


def conferir_assentos(con, hoje: date) -> list[dict]:
    con.row_factory = sqlite3.Row
    achados: list[dict] = []
    for g in duplicidades(con):
        novo = g["membros"][-1]
        lista = "; ".join(f"assento {m['id']} — {_rotulo_do_assento(m)}, lavrado em "
                          f"{_br(m['data_ato'])}" for m in g["membros"])
        por = "mesma DNV" if g["por"] == "DNV" else "mesmo nome e mesma data do fato"
        achados.append(_achado(
            f"RCPN_DUP:rc_assentos:{novo['id']}", "RCPN_DUPLICIDADE", "CRITICO",
            f"{str(g['especie']).lower()} de {g['nome']} em {len(g['ids'])} assentos "
            f"ativos ({por})",
            f"{lista}. Abrir: " + ", ".join(f"/rcpn/assentos/{i}" for i in g["ids"])
            + ". Decisão do oficial: qual termo vale; o outro se cancela com motivo.",
            None, "Lei 6.015/1973; art. 365 do Código de Normas (duplicidade)"))
    for i in inacabados(con):
        par = (f" Há o assento {i['gemeo_de']} (termo nº {i['gemeo_numero']}) com a "
               "mesma DNV — este é, quase certamente, a primeira tentativa dele."
               if i["gemeo_de"] else "")
        achados.append(_achado(
            f"RCPN_INACABADO:rc_assentos:{i['id']}", "RCPN_INACABADO", "CRITICO",
            f"{str(i['especie']).lower()} de {i['nome']} ativo e sem número de termo",
            f"Criado em {_br(i['data_ato'])} por {i['criado_por'] or '—'}.{par} "
            f"Abrir: /rcpn/assentos/{i['id']}.", None, "Lei 6.015/1973"))
    assentos = [dict(r) for r in con.execute(
        f"""SELECT * FROM rc_assentos WHERE {_do_sistema_desde_o_corte()}
               AND COALESCE(situacao,'ATIVO') = 'ATIVO' AND numero IS NOT NULL""",
        (IMPLANTACAO, *ORIGENS_DO_ACERVO))]
    for a in assentos:
        papeis = {r[0] for r in con.execute(
            "SELECT DISTINCT papel FROM rc_pessoas WHERE assento_id = ?", (a["id"],))}
        rot = _rotulo_do_assento(a)
        if a["especie"] in ESPECIES_COM_TERMO and _vazio(a["teor"]):
            reg = _registro_do_assento(con, a["id"])
            onde = (f" Livro {_nome_do_livro(reg)}, fl. {reg['folha']}."
                    if reg and reg.get("livro") else "")
            achados.append(_achado(
                f"RCPN_TERMO:rc_assentos:{a['id']}", "RCPN_SEM_TERMO", "CRITICO",
                f"{rot}: lavrado sem termo",
                f"Lavrado em {_br(a['data_ato'])}.{onde} Abrir: "
                f"/rcpn/assentos/{a['id']}/termo — a prévia monta dos campos; "
                "conferir com o papel e escrever.", None,
                "Lei 6.015/1973, arts. 54, 70 e 80"))
        faltas = _faltas_obrigatorias(con, a, papeis)
        if faltas:
            detalhe = f"Falta: {', '.join(faltas)}."
            if "matrícula" in faltas:
                prop = matricula_proposta(con, a)
                detalhe += (f" Matrícula calculada pelo agente (livro, folha e termo "
                            f"do ato de registro): {prop} — conferir e gravar pela ficha."
                            if prop else " O agente não conseguiu calcular a matrícula "
                            "(falta livro/folha no ato de registro ou o CNS em "
                            "Configurações).")
            achados.append(_achado(
                f"RCPN_DADO:rc_assentos:{a['id']}", "RCPN_DADO_OBRIGATORIO", "CRITICO",
                f"{rot}: {', '.join(faltas)}", detalhe + f" Abrir: /rcpn/assentos/{a['id']}.",
                None, "Lei 6.015/1973, arts. 54, 70 e 80"))
        compl = _faltas_complementares(a, papeis)
        if compl:
            achados.append(_achado(
                f"RCPN_COMPL:rc_assentos:{a['id']}", "RCPN_DADO_COMPLEMENTAR", "ATENCAO",
                f"{rot}: {', '.join(compl)}", f"Abrir: /rcpn/assentos/{a['id']}."))
    return achados


# ======================================================= 2. AS ANOTAÇÕES

def conferir_anotacoes(con, hoje: date) -> list[dict]:
    if not _tem_tabela(con, "rc_anotacoes"):
        return []
    con.row_factory = sqlite3.Row
    achados = []
    for n in con.execute(
            """SELECT n.id, n.assento_id, n.especie_alvo, a.especie, a.numero, a.nome,
                      a.data_ato, COALESCE(a.situacao,'ATIVO') AS situacao
                 FROM rc_anotacoes n JOIN rc_assentos a ON a.id = n.assento_id
                WHERE n.situacao = 'PENDENTE' AND a.data_ato >= ?
             ORDER BY a.data_ato, n.id""", (IMPLANTACAO,)).fetchall():
        rot = _rotulo_do_assento(n)
        alvo = str(n["especie_alvo"] or "").lower()
        if n["situacao"] != "ATIVO":
            achados.append(_achado(
                f"RCPN_ANOT_CANC:rc_assentos:{n['assento_id']}:{n['id']}",
                "RCPN_ANOTACAO_DE_CANCELADO", "ATENCAO",
                f"{rot} está {n['situacao']}: a anotação no {alvo} não é devida",
                "Assento cancelado nunca valeu. Dispensar com esse motivo "
                "(o agente faz isso sozinho com o interruptor ligado).", None,
                "art. 367 do Código de Normas do TJMA"))
            continue
        lavrado = _dia(n["data_ato"])
        if lavrado is None:
            continue
        prazo = lavrado + timedelta(days=ANOTACAO_DIAS)
        gravidade = "VENCIDO" if hoje > prazo else "PRAZO"
        achados.append(_achado(
            f"RCPN_ANOT:rc_assentos:{n['assento_id']}:{n['id']}", "RCPN_ANOTACAO",
            gravidade, f"{rot}: anotar no {alvo} anterior",
            f"Lavrado em {_br(lavrado)}; prazo de cinco dias até {_br(prazo)}. "
            "Localize o assento anterior; daqui, anote; de fora, comunique; sem "
            "assento anterior, dispense com motivo.", prazo,
            "arts. 367 a 372 do Código de Normas do TJMA"))
    return achados


# ======================================================= 3. OS PROCESSOS

def conferir_habilitacoes(con, hoje: date) -> list[dict]:
    if not _tem_tabela(con, "hc_habilitacoes"):
        return []
    con.row_factory = sqlite3.Row
    habs = [dict(r) for r in con.execute("SELECT * FROM hc_habilitacoes")]
    casados = {}
    for h in habs:
        if h["situacao"] == "CELEBRADO":
            casados[frozenset((_norm(h["nubente1_nome"]), _norm(h["nubente2_nome"])))] = h
    achados = []
    for h in habs:
        if h["situacao"] in ("CELEBRADO", "ARQUIVADO"):
            continue
        rot = (f"habilitação nº {h['numero']}/{h['ano']} ({h['nubente1_nome']} e "
               f"{h['nubente2_nome']})")
        abrir = f" Abrir: /rcpn/habilitacoes/{h['id']}."
        par = casados.get(frozenset((_norm(h["nubente1_nome"]), _norm(h["nubente2_nome"]))))
        if par is not None:
            achados.append(_achado(
                f"RCPN_HAB_DUP:hc_habilitacoes:{h['id']}", "RCPN_HABILITACAO", "ATENCAO",
                f"{rot}: o casal já casou pela habilitação nº {par['numero']}/{par['ano']}",
                f"Casamento celebrado em {_br(par['celebrado_em'])} (assento "
                f"{par['casamento_assento_id']}). Este processo é duplicado: arquivar "
                "com o motivo." + abrir))
            continue
        if h["situacao"] == "HABILITADO" and _dia(h["habilitacao_vale_ate"]):
            vale = _dia(h["habilitacao_vale_ate"])
            if hoje > vale:
                achados.append(_achado(
                    f"RCPN_HAB_VENCIDA:hc_habilitacoes:{h['id']}", "RCPN_HABILITACAO",
                    "CRITICO", f"{rot}: a habilitação perdeu a eficácia em {_br(vale)}",
                    "Não celebrar com ela (CC art. 1.532): arquivar e abrir outra." + abrir,
                    vale, "Código Civil, art. 1.532"))
            elif (vale - hoje).days <= JANELA_DE_AVISO:
                achados.append(_achado(
                    f"RCPN_HAB_VENCE:hc_habilitacoes:{h['id']}", "RCPN_HABILITACAO",
                    "PRAZO", f"{rot}: a habilitação vale até {_br(vale)}",
                    "Celebrar até essa data, ou a habilitação perde a eficácia." + abrir,
                    vale, "Código Civil, art. 1.532"))
        elif h["situacao"] == "EDITAL_PUBLICADO" and _dia(h["edital_prazo_ate"]) \
                and hoje > _dia(h["edital_prazo_ate"]):
            achados.append(_achado(
                f"RCPN_HAB_EDITAL:hc_habilitacoes:{h['id']}", "RCPN_HABILITACAO",
                "ATENCAO", f"{rot}: o prazo do edital correu em "
                f"{_br(h['edital_prazo_ate'])} e o processo não andou",
                "Habilitar (se não houve oposição) ou registrar a oposição." + abrir,
                None, "Código Civil, arts. 1.527 e 1.531"))
        elif h["situacao"] == "EM_ANALISE" and _dia(h["data_entrada"]) and \
                (hoje - _dia(h["data_entrada"])).days > HABILITACAO_PARADA_DIAS:
            achados.append(_achado(
                f"RCPN_HAB_PARADA:hc_habilitacoes:{h['id']}", "RCPN_HABILITACAO",
                "ATENCAO", f"{rot}: em análise desde {_br(h['data_entrada'])}",
                f"Mais de {HABILITACAO_PARADA_DIAS} dias sem edital (tolerância da casa). "
                "Cobrar os documentos ou arquivar com motivo." + abrir))
    return achados


def conferir_pedidos(con, hoje: date) -> list[dict]:
    if not _tem_tabela(con, "rc_pedidos"):
        return []
    con.row_factory = sqlite3.Row
    limite = (hoje - timedelta(days=PEDIDO_PARADO_DIAS)).isoformat()
    achados = []
    for p in con.execute(
            """SELECT id, modulo, ambiente, numero_pedido, especie, baixado_em, resumo
                 FROM rc_pedidos WHERE situacao = 'PENDENTE' AND baixado_em < ?
                  AND COALESCE(ambiente,'') NOT IN ('HOMOLOGACAO','TESTES')""",
            (limite,)):
        achados.append(_achado(
            f"RCPN_PEDIDO:rc_pedidos:{p['id']}", "RCPN_PEDIDO_CENTRAL", "ATENCAO",
            f"Pedido {p['numero_pedido'] or p['id']} ({p['modulo']}) sem resposta desde "
            f"{_br(p['baixado_em'])}",
            f"{p['resumo'] or ''} Mais de {PEDIDO_PARADO_DIAS} dias (tolerância da casa; "
            f"o prazo da Central não foi lido nesta casa — A CONFERIR). Abrir: "
            f"/rcpn/pedidos/{p['id']}."))
    return achados


def conferir_retificacoes(con, hoje: date) -> list[dict]:
    if not _tem_tabela(con, "rr_processos"):
        return []
    con.row_factory = sqlite3.Row
    achados = []
    for r in con.execute(
            """SELECT id, numero, ano, instituto, requerente_nome, prazo_ate, fase
                 FROM rr_processos WHERE situacao = 'EM_ANDAMENTO'
                  AND COALESCE(prazo_ate,'') <> ''"""):
        prazo = _dia(r["prazo_ate"])
        if prazo is None:
            continue
        if hoje > prazo:
            gravidade = "VENCIDO"
        elif (prazo - hoje).days <= JANELA_DE_AVISO:
            gravidade = "PRAZO"
        else:
            continue
        achados.append(_achado(
            f"RCPN_RR:rr_processos:{r['id']}", "RCPN_RETIFICACAO", gravidade,
            f"{str(r['instituto'] or 'processo').lower()} nº {r['numero']}/{r['ano']} "
            f"({r['requerente_nome'] or '—'}): prazo até {_br(prazo)}",
            f"Fase: {r['fase'] or '—'}. Abrir: /rcpn/retificacoes.", prazo,
            "arts. 348 a 355 do Código de Normas do TJMA"))
    return achados


def conferir_folha(con, hoje: date) -> list[dict]:
    if not _tem_tabela(con, "pp_folhas"):
        return []
    import papel_seguranca
    e = papel_seguranca.estoque(con)
    if not e["acabando"]:
        return []
    return [_achado(
        "RCPN_FOLHA:estoque", "RCPN_FOLHA_SEGURANCA",
        "CRITICO" if e["acabou"] else "ATENCAO",
        "Folha de segurança: " + ("acabou" if e["acabou"] else
                                  f"{e['em_branco']} em branco (piso {e['piso']})"),
        "Sem folha, a certidão não sai. Pedir a remessa e registrar a chegada.")]


# ======================================================= 4. O PRÓPRIO AGENTE

def _ultima_rodada(con):
    if not _tem_tabela(con, "ge_rcpn_execucoes"):
        return None
    return con.execute("SELECT * FROM ge_rcpn_execucoes ORDER BY id DESC LIMIT 1").fetchone()


def conferir_o_agente(con, hoje: date) -> list[dict]:
    r = _ultima_rodada(con)
    if r is None or (r["iniciada_em"] or "")[:10] < (
            hoje - timedelta(days=AGENTE_DIAS_TOLERADOS)).isoformat():
        return [_achado("RCPN_AGENTE", "RCPN_AGENTE_PARADO", "ATENCAO",
                        "O agente do RCPN não rodou desde "
                        f"{_br(r['iniciada_em']) if r else 'nunca'}",
                        "A rodada das 07:30 chama gestor_rcpn.rodada; veja o "
                        "CONFERENCIA_DIARIA.log.", setor="TI")]
    if r["situacao"] == "ERRO":
        return [_achado("RCPN_AGENTE", "RCPN_AGENTE_PARADO", "CRITICO",
                        "O agente do RCPN quebrou na última rodada",
                        str(r["detalhe"] or "")[:500], setor="TI")]
    return []


# ======================================================= 5. OS DADOS DO TERMO

def _lavrados_nesta_casa(con):
    return con.execute(
        f"""SELECT id, especie, numero, nome, teor FROM rc_assentos
             WHERE {_do_sistema_desde_o_corte()} AND origem = 'MANUAL'
               AND COALESCE(situacao,'ATIVO') = 'ATIVO' AND numero IS NOT NULL""",
        (IMPLANTACAO, *ORIGENS_DO_ACERVO)).fetchall()


def _sha(texto: str) -> str:
    import hashlib
    return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()


def conferir_dados(con, hoje: date) -> list[dict]:
    """A régua de `rc_conferencia_dados` sobre todo assento lavrado nesta casa
    desde o corte, e a impressão digital do termo. SÓ LÊ."""
    import rc_conferencia_dados as CONF
    con.row_factory = sqlite3.Row
    vistos = {}
    if _tem_tabela(con, "ge_rcpn_termos"):
        vistos = {r["assento_id"]: dict(r) for r in con.execute(
            "SELECT * FROM ge_rcpn_termos")}
    # A LAVRATURA FORÇADA (11/10/2026) não some da fiscalização: ela entra com
    # o nome de quem forçou e o motivo, até o assento ser arrumado.
    forcadas = {}
    if _tem_tabela(con, "rc_lavraturas_forcadas"):
        forcadas = {r["assento_id"]: dict(r) for r in con.execute(
            "SELECT * FROM rc_lavraturas_forcadas")}
    achados = []
    for a in _lavrados_nesta_casa(con):
        rot = _rotulo_do_assento(a)
        probs = CONF.conferir_assento(con, a["id"])
        trava, olha = CONF.bloqueios(probs), CONF.avisos(probs)
        if trava:
            f = forcadas.get(a["id"])
            quem = (f" — lavrado POR CIMA DA TRAVA por {f['forcado_por']} em "
                    f"{(f['forcado_em'] or '')[:10]}, motivo: «{f['motivo']}»."
                    if f else "")
            achados.append(_achado(
                f"RCPN_DADOS:rc_assentos:{a['id']}", "RCPN_DADOS_CONTRADITORIOS",
                "CRITICO", f"{rot}: {len(trava)} dado(s) que se contradizem"
                + (" (lavratura forçada)" if f else ""),
                " ".join(p["mensagem"] for p in trava) + quem
                + f" Abrir: /rcpn/assentos/{a['id']}.", None,
                "Lei 6.015/1973, arts. 54, 80, 97 e 110"))
        if olha:
            achados.append(_achado(
                f"RCPN_DADOS_OLHAR:rc_assentos:{a['id']}", "RCPN_DADOS_A_CONFERIR",
                "ATENCAO", f"{rot}: {len(olha)} dado(s) a conferir",
                " ".join(p["mensagem"] for p in olha)
                + f" Abrir: /rcpn/assentos/{a['id']}."))
        visto = vistos.get(a["id"])
        teor = (a["teor"] or "").strip()
        if visto and teor and _sha(teor) != visto["sha256"]:
            antes = visto["teor"]
            i = next((k for k, (x, y) in enumerate(zip(antes, teor)) if x != y),
                     min(len(antes), len(teor)))
            achados.append(_achado(
                f"RCPN_TERMO_ALT:rc_assentos:{a['id']}", "RCPN_TERMO_ALTERADO",
                "CRITICO", f"{rot}: o termo mudou depois de lavrado",
                f"Visto em {_br(visto['visto_em'])}. Antes: «…{antes[max(0, i - 60):i + 80]}…» "
                f"Agora: «…{teor[max(0, i - 60):i + 80]}…». Nenhuma averbação muda o "
                f"texto do termo. Abrir: /rcpn/assentos/{a['id']}/termo.", None,
                "Lei 6.015/1973, arts. 97 e 110"))
    return achados


def registrar_termos(con, agora: str) -> int:
    """Guarda a impressão digital dos termos lavrados que o agente ainda não
    tinha visto. ESCREVE (só `ge_rcpn_termos`). Não regrava o que já viu: é
    isso que permite acusar a mudança."""
    init_schema(con)
    n = 0
    for a in _lavrados_nesta_casa(con):
        teor = (a["teor"] or "").strip()
        if teor:
            n += con.execute(
                "INSERT OR IGNORE INTO ge_rcpn_termos (assento_id, sha256, teor, visto_em) "
                "VALUES (?,?,?,?)", (a["id"], _sha(teor), teor, agora)).rowcount
    return n


def aceitar_termo_atual(con, assento_id: int, *, quem: str, agora: str) -> None:
    """O oficial reconhece o texto atual do termo (depois da averbação que o
    justifica). ESCREVE `ge_rcpn_termos`. Chamada pela linha de comando."""
    a = con.execute("SELECT teor FROM rc_assentos WHERE id=?", (int(assento_id),)).fetchone()
    if not a or not (a[0] or "").strip():
        raise ValueError(f"O assento {assento_id} não tem termo.")
    teor = a[0].strip()
    init_schema(con)
    con.execute("""INSERT INTO ge_rcpn_termos (assento_id, sha256, teor, visto_em, aceito_por)
                   VALUES (?,?,?,?,?) ON CONFLICT(assento_id) DO UPDATE SET
                   sha256=excluded.sha256, teor=excluded.teor, visto_em=excluded.visto_em,
                   aceito_por=excluded.aceito_por""",
                (int(assento_id), _sha(teor), teor, agora, quem))


#: As partes da conferência — cada uma isolada: a que quebra vira NAO_MEDIU.
PARTES = (
    ("RCPN_DADOS", conferir_dados),
    ("RCPN_ASSENTOS", conferir_assentos),
    ("RCPN_ANOTACOES", conferir_anotacoes),
    ("RCPN_HABILITACOES", conferir_habilitacoes),
    ("RCPN_PEDIDOS", conferir_pedidos),
    ("RCPN_RETIFICACOES", conferir_retificacoes),
    ("RCPN_FOLHA", conferir_folha),
    ("RCPN_AGENTE", conferir_o_agente),
)


def conferir(con: sqlite3.Connection, hoje: date) -> list[dict]:
    """Todos os achados do RCPN. SÓ LÊ. Uma regra do gestor (`regra_rcpn`)."""
    con.row_factory = sqlite3.Row
    achados: list[dict] = []
    for nome, parte in PARTES:
        try:
            achados.extend(parte(con, hoje))
        except Exception as erro:                       # noqa: BLE001
            achados.append(_achado(
                f"NAO_MEDIU:{nome}", nome, "NAO_MEDIU",
                f"A conferência do RCPN «{nome}» não conseguiu medir",
                f"{type(erro).__name__}: {erro}", setor="TI"))
    return achados


# ================================================================ RESOLVER

def resolver(con: sqlite3.Connection, hoje: date, *, agora: str | None = None) -> dict:
    """O que o agente faz SOZINHO. ESCREVE — só o que está na lista abaixo.

    1. Dispensa a anotação pendente cujo assento de origem está CANCELADO.
       Critério objetivo, nenhum ato tocado, motivo escrito, antes guardado em
       `ge_rcpn_resolvidos`.

    Com o interruptor desligado não faz nada e diz isso.
    """
    import rc_anotacao
    init_schema(con)
    agora = agora or _agora()
    if not resolver_ligado(con):
        # A impressão digital não é a mão do agente no ato: é a memória dele,
        # e sem ela não há como acusar termo reescrito. Roda sempre.
        return {"ligado": False, "dispensadas": 0,
                "termos_registrados": registrar_termos(con, agora)}
    feitas = 0
    if _tem_tabela(con, "rc_anotacoes"):
        con.row_factory = sqlite3.Row
        for n in con.execute(
                """SELECT n.id, n.especie_alvo, a.id AS assento_id, a.especie, a.numero,
                          a.situacao
                     FROM rc_anotacoes n JOIN rc_assentos a ON a.id = n.assento_id
                    WHERE n.situacao = 'PENDENTE'
                      AND COALESCE(a.situacao,'ATIVO') = 'CANCELADO'""").fetchall():
            motivo = (f"Dispensada pelo agente do RCPN em {_br(hoje)}: o assento de "
                      f"origem ({str(n['especie']).lower()} nº {n['numero'] or '—'}, "
                      f"id {n['assento_id']}) está CANCELADO e nunca valeu; a anotação "
                      "devida é a do assento que vale.")
            rc_anotacao.dispensar(con, n["id"], motivo=motivo, agora=agora, usuario=QUEM)
            con.execute(
                """INSERT INTO ge_rcpn_resolvidos (o_que, tabela, registro_id, antes,
                       depois, motivo, feito_em) VALUES (?,?,?,?,?,?,?)""",
                ("ANOTACAO_DISPENSADA", "rc_anotacoes", n["id"], "PENDENTE",
                 "DISPENSADA", motivo, agora))
            feitas += 1
    # 2. A impressão digital dos termos novos (não toca ato: só a tabela dele).
    termos = registrar_termos(con, agora)
    return {"ligado": True, "dispensadas": feitas, "termos_registrados": termos}


def rodada(con: sqlite3.Connection, banco: Path | None = None, hoje: date | None = None,
           *, escrever=None) -> dict:
    """A rodada do agente, chamada pela rodada das 07:30 do gestor ANTES da
    conferência: o que ele resolve sozinho já não vira tarefa."""
    hoje = hoje or date.today()
    init_schema(con)
    exe = con.execute("INSERT INTO ge_rcpn_execucoes (hoje, iniciada_em) VALUES (?,?)",
                      (hoje.isoformat(), _agora())).lastrowid
    con.commit()
    try:
        feito = resolver(con, hoje)
        con.execute("UPDATE ge_rcpn_execucoes SET terminada_em=?, situacao='OK', "
                    "detalhe=? WHERE id=?",
                    (_agora(), json.dumps(feito, ensure_ascii=False), exe))
        con.commit()
    except Exception as erro:                           # noqa: BLE001
        con.rollback()
        feito = {"erro": f"{type(erro).__name__}: {erro}"}
        con.execute("UPDATE ge_rcpn_execucoes SET terminada_em=?, situacao='ERRO', "
                    "detalhe=? WHERE id=?",
                    (_agora(), json.dumps(feito, ensure_ascii=False), exe))
        con.commit()
    if escrever:
        escrever(f"  agente do RCPN: {feito}")
    return feito


# ================================================================ ORIENTAR

def registrar_na_didatica() -> None:
    """Põe o texto didático e as telas do RCPN em `gestor_didatica` — o mesmo
    caminho do agente das Notas e do RTD/PJ. Só texto de tarefa."""
    try:
        import gestor_didatica as D
    except ImportError:
        return
    for k, v in GUIA.items():
        D.GUIA.setdefault(k, v)
    for k, v in TELA.items():
        D.TELA.setdefault(k, v)


_ORDEM_GRAV = {"NAO_MEDIU": 0, "CRITICO": 1, "VENCIDO": 2, "PRAZO": 3, "ATENCAO": 4}


def _passo_da_regra(regra: str) -> str:
    if regra in GUIA:
        return GUIA[regra][1][0]
    try:
        import gestor_didatica
        guia = gestor_didatica.GUIA.get(regra)
        return guia[1][0] if guia else ""
    except Exception:                                   # noqa: BLE001
        return ""


def boletim_texto(con: sqlite3.Connection, hoje: date) -> str:
    """O dia do Registro Civil, numa tarefa só. SÓ LÊ `ge_achados` e `tasks`.

    Junta o que é deste agente e o que é das Centrais (agente de cargas e
    gestor), sem recalcular nada: a fonte de cada achado é quem o mediu.
    """
    import gestor_rotina as GR
    con.row_factory = sqlite3.Row
    rotulos = {**GR.ROTULOS, **ROTULOS}
    linhas = [f"O DIA DO REGISTRO CIVIL — {hoje:%d/%m/%Y}",
              "Boletim do agente do RCPN: tudo o que o RCPN tem para hoje, na ordem "
              "do aperto. Cada item é cobrado na própria tarefa; aqui é o mapa.", ""]
    abertos = []
    if _tem_tabela(con, "ge_achados"):
        abertos = [dict(r) for r in con.execute(
            "SELECT * FROM ge_achados WHERE setor = ? AND resolvido_em IS NULL",
            (SETOR,))]
    abertos.sort(key=lambda a: (_ORDEM_GRAV.get(a["gravidade"], 9), a["prazo"] or "9999"))
    blocos = (("1. JÁ VENCEU OU É GRAVE — fazer primeiro",
               ("NAO_MEDIU", "CRITICO", "VENCIDO")),
              ("2. COM PRAZO CORRENDO", ("PRAZO",)),
              ("3. PARA CONFERIR QUANDO DER", ("ATENCAO",)))
    vistas: set[str] = set()
    for titulo, gravs in blocos:
        do_bloco = [a for a in abertos if a["gravidade"] in gravs]
        linhas.append(f"{titulo} ({len(do_bloco)})")
        por_regra: dict[str, list[dict]] = {}
        for a in do_bloco:
            por_regra.setdefault(a["regra"], []).append(a)
        for regra, itens in por_regra.items():
            linhas.append(f"   ■ {rotulos.get(regra, regra)} — {len(itens)}")
            if regra not in vistas:
                passo = _passo_da_regra(regra)
                if passo:
                    linhas.append(f"     Como: {passo}")
                vistas.add(regra)
            for a in itens[:8]:
                prazo = f" (prazo {_br(a['prazo'])})" if a["prazo"] else ""
                linhas.append(f"     - {a['titulo']}{prazo}")
            if len(itens) > 8:
                linhas.append(f"     … e mais {len(itens) - 8} na tarefa da regra.")
        if not do_bloco:
            linhas.append("   nada")
        linhas.append("")
    tarefas = [dict(r) for r in con.execute(
        """SELECT t.id, t.title, t.priority, t.due_date, t.source_type, u.full_name
             FROM tasks t LEFT JOIN users u ON u.id = t.assigned_user_id
            WHERE t.sector = 'RCPN' AND t.status NOT IN ('CONCLUIDA','CANCELADA')
              AND t.source_type NOT IN (?, 'GESTOR')
            ORDER BY COALESCE(t.due_date,'9999'), t.id""", (SOURCE_BOLETIM,))]
    linhas.append(f"4. OUTRAS TAREFAS DO RCPN — inspeção, malote e manuais ({len(tarefas)})")
    for t in tarefas[:25]:
        prazo = f" — prazo {_br(t['due_date'])}" if t["due_date"] else ""
        venc = " — VENCIDA" if t["due_date"] and t["due_date"] < hoje.isoformat() else ""
        linhas.append(f"   #{t['id']} [{t['priority']}] {t['title']} "
                      f"({t['full_name'] or 'sem responsável'}){prazo}{venc}")
    linhas.append("")
    feitos = []
    if _tem_tabela(con, "ge_rcpn_resolvidos"):
        feitos = con.execute(
            "SELECT o_que, registro_id, motivo FROM ge_rcpn_resolvidos WHERE feito_em >= ?",
            (hoje.isoformat(),)).fetchall()
    linhas.append(f"5. O QUE O AGENTE RESOLVEU SOZINHO HOJE ({len(feitos)})")
    linhas += [f"   {f['o_que']} #{f['registro_id']}: {f['motivo']}" for f in feitos] \
        or ["   nada"]
    linhas += ["", "Este boletim se renova a cada rodada (07:30, 14:00, 14:30); o de "
               "ontem fecha sozinho."]
    return "\n".join(linhas)


def publicar_boletim(con: sqlite3.Connection, hoje: date) -> int | None:
    """O boletim do dia do RCPN — num RELATO para o responsável, e não numa tarefa.

    Ordem do oficial em 12/10/2026 («os relatos diários ficarem num campo
    próprio»). A tarefa-boletim aberta fecha, com a nota do porquê. Devolve o id
    do relato."""
    import gestor_rotina as GR
    import relatos_diarios as RD
    con.row_factory = sqlite3.Row
    responsavel, _ = GR.escolher_responsavel(con, GR.inferir_responsaveis(con), SETOR)
    if responsavel is None:
        responsavel = GR._admin(con)
    if responsavel is None:
        return None
    RD.aposentar_tarefas_diarias(con, SOURCE_BOLETIM, "O boletim do dia passou a ser um relato "
                                 "(painel → Relatos do dia), por ordem do oficial em 12/10/2026.")
    return RD.publicar(con, dia=hoje, origem="RCPN_BOLETIM", destinatario_id=responsavel,
                       setor=SETOR, titulo=f"O dia do Registro Civil — {hoje:%d/%m/%Y}",
                       corpo=boletim_texto(con, hoje).replace(
                           "Este boletim se renova a cada rodada (07:30, 14:00, 14:30); o de "
                           "ontem fecha sozinho.", "Este relato se renova a cada rodada."))


def main(argv=None) -> int:
    """`--banco X` só confere e imprime (abre o banco SÓ PARA LER).
    `--rodar` faz a rodada (resolve) e publica o boletim — escreve."""
    p = argparse.ArgumentParser(description="O agente do RCPN.")
    p.add_argument("--banco", required=True)
    p.add_argument("--rodar", action="store_true")
    p.add_argument("--hoje")
    p.add_argument("--aceitar-termo", type=int, metavar="ASSENTO_ID",
                   help="o oficial reconhece o texto atual do termo (escreve)")
    p.add_argument("--quem", default="", help="quem reconhece (com --aceitar-termo)")
    a = p.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    hoje = date.fromisoformat(a.hoje) if a.hoje else date.today()
    if a.aceitar_termo:
        if len(a.quem.strip()) < 3:
            print("Diga quem reconhece o termo: --quem «nome».")
            return 2
        con = sqlite3.connect(a.banco, timeout=60)
        try:
            aceitar_termo_atual(con, a.aceitar_termo, quem=a.quem.strip(), agora=_agora())
            con.commit()
        finally:
            con.close()
        print(f"Termo do assento {a.aceitar_termo} reconhecido por {a.quem.strip()}.")
        return 0
    if a.rodar:
        con = sqlite3.connect(a.banco, timeout=60)
        try:
            rodada(con, Path(a.banco), hoje, escrever=print)
            print("  boletim:", publicar_boletim(con, hoje))
            con.commit()
        finally:
            con.close()
        return 0
    con = sqlite3.connect(f"file:{a.banco}?mode=ro", uri=True, timeout=60)
    try:
        achados = conferir(con, hoje)
    finally:
        con.close()
    for x in sorted(achados, key=lambda x: (_ORDEM_GRAV.get(x["gravidade"], 9), x["regra"])):
        print(f"[{x['gravidade']}] {x['regra']}: {x['titulo']}")
        if x["detalhe"]:
            print(f"      {x['detalhe']}")
    print(f"\n{len(achados)} achado(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
