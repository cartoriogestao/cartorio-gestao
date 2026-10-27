"""Traz para a ficha do RI o que a FICHA DE ABERTURA em `.docx` já diz.

ORDEM DO OFICIAL EM 15/09/2026: «agora importe e regularize a abertura,
inclusive com selo, da matricula 4016».

O QUE ESTAVA ACONTECENDO. A matrícula 4.016 nasceu do transporte da 3.110
    (AV-06) e ficou **só com o teor**: medido em 15/09/2026, **zero partes,
    zero atos, `selo_abertura_texto` e `emolumentos_abertura` vazios** — e ela
    não é exceção: das **1.982** matrículas desta casa, **nenhuma** tem selo de
    abertura gravado. As colunas existem desde sempre e nada nunca as escreveu.

    O documento que o oficial guarda no Drive tem todos esses dados escritos,
    rotulados um a um. Este script os traz para os CAMPOS, sem inventar nada.

O QUE ELE FAZ, E O QUE NÃO FAZ
    Faz: as **partes da matrícula** (proprietário e cônjuge, com CPF e
    qualificação), a área, a descrição perimétrica, o registro anterior e a
    relação de emolumentos da abertura.

    **NÃO SELA.** Selar fala com a rede e é ato que custa dinheiro; o caminho
    é a tela. **Não lavra ato, não numera e não cobra.** E **não toca no
    teor**: ele já está na ficha, veio do mesmo documento, e reescrevê-lo aqui
    seria a segunda fonte que diverge da primeira.

AS QUATRO RECUSAS
    1. **Ficha que já tem parte não recebe nada.** Importar por cima
       duplicaria os nomes de quem é dono do imóvel.
    2. **O número da matrícula no DOCUMENTO tem de ser o que se pediu.** O
       arquivo traz «MATRÍCULA N° 4.016» escrito; casar pelo nome do arquivo
       poria a qualificação de um imóvel na ficha de outro.
    3. **Parte sem nome ou sem CPF não entra, e o script para.** Nome de
       proprietário é o que identifica a pessoa na pesquisa nacional de bens;
       importar pela metade é pior que não importar.
    4. **Só mede por padrão.** Nada é gravado sem `--confirmar`, e tudo é
       impresso antes — com cópia do banco (`VACUUM INTO`) na hora de gravar.

COMO USAR
    python tools/importar_ficha_de_abertura.py <banco> --docx <arquivo> --matricula 4016
    python tools/importar_ficha_de_abertura.py <banco> --docx <arquivo> --matricula 4016 --confirmar
"""
from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import banco_pg  # noqa: E402
import identidade_do_robo as IDR  # noqa: E402
# COM OUTRO NOME: `main` chama de `banco` o caminho do arquivo, e o nome curto
# escondia a função — era o TypeError da revisão do L021.
from bd_nativo import banco as abrir_banco  # noqa: E402

# OS ROTULOS SAO OS DO DOCUMENTO DA CASA, e nao inventados: conferidos no
# `MATRICULA_4016_FICHA_ABERTURA.docx` em 15/09/2026, os onze aparecem.
FIM = object()


def texto_do_docx(caminho: Path) -> tuple[str, list[str]]:
    """O corpo do documento e todos os paragrafos. So le.

    O CORPO E O MAIOR PARAGRAFO, e isso e medido: no documento da 4.016 ele
    tem 5.220 caracteres contra 45 do segundo maior — os outros dezesseis sao
    cabecalho (o nome da serventia, o numero da ficha, o da pasta). Procurar
    os rotulos no documento inteiro acharia «MATRICULA N° 4.016» do cabecalho
    onde se quer o «REGISTRO ANTERIOR: Matricula n° 3.110» do corpo.
    """
    xml = zipfile.ZipFile(caminho).read("word/document.xml").decode("utf-8")
    paragrafos = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        t = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.S))
        for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                     ("&quot;", '"'), ("&apos;", "'")):
            t = t.replace(a, b)
        if t.strip():
            paragrafos.append(t.strip())
    if not paragrafos:
        raise ValueError(f"{caminho.name} não tem texto")
    return max(paragrafos, key=len), paragrafos


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").upper()


def secao(corpo: str, rotulo: str, ate) -> str:
    """O trecho entre um rotulo e o proximo. Devolve '' se nao houver."""
    plano = _sem_acento(corpo)
    i = plano.find(_sem_acento(rotulo))
    if i < 0:
        return ""
    if ate is FIM:
        j = len(corpo)
    else:
        j = plano.find(_sem_acento(ate), i + 1)
        if j < 0:
            j = len(corpo)
    trecho = corpo[i:j].strip().rstrip(".").strip()
    # O ROTULO NAO VAI DENTRO DO CAMPO — medido em 15/09/2026: os
    # `registro_anterior` que a casa ja tem sao «MATRICULA 2.765, Livro 2-P
    # fls. 002...», sem a palavra «REGISTRO ANTERIOR:» na frente. Guardar o
    # rotulo faria a coluna dizer o proprio nome, e a tela o repetiria.
    return re.sub(r"^[^:]{0,40}:\s*", "", trecho, count=1).strip()


CPF = re.compile(r"(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})")
# Como a casa escreve «e o outro»: medido no documento da 4.016 e nos irmaos.
CONJUGE = re.compile(r",\s*e\s+(?:seu|sua)\s+"
                     r"(?:c[oô]njuge|esposa|esposo|mulher|marido)\s+",
                     re.IGNORECASE)


def partes_do_bloco(bloco: str) -> list[dict]:
    """Lê «PROPRIETÁRIA: NOME, qualificação, CPF, e seu cônjuge NOME, ...».

    NAO ADIVINHA PAPEL: quem vem primeiro e o proprietario ATIVO, o segundo e
    o conjuge — e e assim que a casa ja guarda (medido na matricula 3.399:
    MARCOS com `proprietario_ativo=1` e GYEDRE com 0).
    """
    corpo = re.sub(r"^[^:]{0,40}:\s*", "", bloco, count=1)
    # A residencia e dos dois e nao e de ninguem: sai antes de partir.
    corpo = re.split(r",\s*residentes?\s+e\s+domiciliad", corpo,
                     flags=re.IGNORECASE)[0]
    pedacos = CONJUGE.split(corpo)
    saida = []
    for n, pedaco in enumerate(pedacos):
        pedaco = pedaco.strip().strip(",").strip()
        if not pedaco:
            continue
        nome = pedaco.split(",")[0].strip()
        achado = CPF.search(pedaco)
        qualificacao = pedaco[len(nome):].strip().lstrip(",").strip()
        # O CPF TEM COLUNA PROPRIA, e repeti-lo dentro da qualificacao daria
        # duas fontes para o mesmo numero. A casa guarda a qualificacao curta
        # — «BRASILEIRO, CASADO(A), COMERCIANTE», medido na 3.399.
        qualificacao = re.split(r",\s*inscrit[oa]\s+no\s+CP[FJ]",
                                qualificacao, flags=re.IGNORECASE)[0]
        qualificacao = qualificacao.strip().rstrip(",").strip()
        saida.append({
            "nome": nome,
            "documento_numero": (achado.group(1) if achado else ""),
            "qualificacao": qualificacao,
            "proprietario_ativo": 1 if n == 0 else 0,
        })
    return saida


def main() -> int:
    for saida in (sys.stdout, sys.stderr):
        try:
            saida.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("banco")
    ap.add_argument("--docx", required=True)
    ap.add_argument("--matricula", required=True)
    ap.add_argument("--confirmar", action="store_true")
    args = ap.parse_args()

    banco, docx = Path(args.banco), Path(args.docx)
    for p in (banco, docx):
        if not p.is_file():
            print(f"Não achei: {p}", file=sys.stderr)
            return 1

    corpo, paragrafos = texto_do_docx(docx)
    cabecalho = " · ".join(paragrafos[:12])

    # RECUSA 2: o documento tem de dizer de qual matricula ele e.
    pedido = re.sub(r"\D", "", args.matricula)
    numeros = [re.sub(r"\D", "", m) for m in
               re.findall(r"MATR[IÍ]CULA\s*N[º°]?\s*([\d.]+)", cabecalho,
                          re.IGNORECASE)]
    if pedido not in numeros:
        print(f"RECUSA: o documento não diz ser da matrícula {args.matricula}. "
              f"No cabeçalho dele está: {numeros or 'nenhum número'}.",
              file=sys.stderr)
        return 1

    # PELA PORTA DO BANCO, e não `sqlite3.connect`: fora do sistema ninguém
    # instala o desvio, e o `sqlite3` cru é recusado pelo acesso nativo.
    con = banco_pg.conectar(banco)
    bd = abrir_banco(con)
    m = bd.um("SELECT * FROM ri_matriculas WHERE numero=%s ORDER BY id LIMIT 1",
              (str(args.matricula).strip(),))
    if not m:
        print(f"Matrícula {args.matricula} não existe no banco.", file=sys.stderr)
        return 1

    print(f"=== Matrícula {m['numero']}, Livro {m['livro']} "
          f"(ri_matriculas.id={m['id']}) ===")
    print(f"  arquivo: {docx.name}")
    print(f"  teor na ficha: {len(m['teor'] or '')} caracteres "
          f"(NÃO será tocado)")

    campos = {
        "denominacao": secao(corpo, "DENOMINAÇÃO:", "LOCALIZAÇÃO"),
        "localizacao": secao(corpo, "LOCALIZAÇÃO:", "IMÓVEL:"),
        "imovel": secao(corpo, "IMÓVEL:", "DESCRIÇÃO PERIM"),
        "descricao_perimetro": secao(corpo, "DESCRIÇÃO PERIM", "SISTEMA GEOD"),
        "registro_anterior": secao(corpo, "REGISTRO ANTERIOR:",
                                   "ABERTURA/TRANSPORTE"),
        "protocolo": secao(corpo, "PROTOCOLO:", "EMOLUMENTOS E SELO"),
        "emolumentos": secao(corpo, "EMOLUMENTOS E SELO:", FIM),
    }
    bloco_partes = secao(corpo, "PROPRIET", "TÍTULO DE ORIGEM")

    print("\n=== o que o documento diz ===")
    for k, v in campos.items():
        print(f"  {k:22} {(v[:110] + '…') if len(v) > 110 else v or '—'}")

    partes = partes_do_bloco(bloco_partes) if bloco_partes else []
    print(f"\n=== partes lidas: {len(partes)} ===")
    for p in partes:
        papel = "PROPRIETÁRIO(A) ATIVO" if p["proprietario_ativo"] else "cônjuge"
        print(f"  {papel}: {p['nome']}")
        print(f"     CPF/CNPJ: {p['documento_numero'] or '*** NÃO ACHEI ***'}")
        print(f"     qualificação: {p['qualificacao'][:100]}")

    # RECUSA 3: parte pela metade nao entra.
    sem = [p["nome"] for p in partes if not p["nome"] or not p["documento_numero"]]
    if not partes or sem:
        print(f"\nRECUSA: não consegui ler nome e documento de toda parte "
              f"({sem or 'nenhuma parte encontrada'}). Nome de proprietário é "
              f"o que identifica a pessoa na pesquisa nacional de bens — "
              f"importar pela metade é pior que não importar.", file=sys.stderr)
        return 1

    # RECUSA 1: nao se importa por cima.
    ja_tem = bd.ler(
        "SELECT id, nome FROM ri_partes WHERE matricula_id=%s ORDER BY id", (m["id"],))
    print(f"\npartes que a ficha já tem: {len(ja_tem)}")
    if ja_tem:
        print(f"\nRECUSA: a ficha já tem {len(ja_tem)} parte(s) — "
              f"{', '.join(p['nome'] for p in ja_tem)}. Importar por cima "
              f"duplicaria quem é dono do imóvel.", file=sys.stderr)
        return 1

    # A area sai do proprio texto do imovel, e nao de uma conta.
    area = re.search(r"área de\s*([\d.,]+)\s*(ha|m²|m2|hectares?)",
                     campos["imovel"], re.IGNORECASE)
    print("\n=== o que vai para os campos da ficha ===")
    print(f"  area_valor / unidade : {area.group(1) if area else '—'} "
          f"{area.group(2) if area else ''}")
    print(f"  descricao_perimetro  : {len(campos['descricao_perimetro'])} caracteres")
    print(f"  registro_anterior    : {campos['registro_anterior'][:80]}")
    print(f"  emolumentos_abertura : {campos['emolumentos'][:80]}")
    # `rural_urbano` E UMA LETRA, e isso e medido: 'R' em 1.331 fichas e 'U'
    # em 370; 'RURAL' por extenso aparece em **tres**, e as tres sao as que o
    # importador de 14/09 criou. Escrever por extenso faria esta ficha nao
    # aparecer em nenhum filtro por 'R'.
    # E `RURAL` POR EXTENSO SE NORMALIZA, ao contrario dos outros campos.
    # Medido: a casa tem 'R' em 1.331 fichas e 'U' em 370; 'RURAL' aparece em
    # **tres**, e as tres sao as que o importador de 14/09 criou (4.016, 4.017
    # e 4.018). Toda a LOGICA do sistema le `.upper().startswith("R")` e nao se
    # incomoda — mas os dois `<select>` das telas comparam `== 'R'`, e com
    # `RURAL` a caixa abre **sem opcao marcada**: quem salvar a ficha sem
    # tocar nela perde o campo. Por isso este e o unico campo que substitui o
    # que ja esta la, e so quando o que esta la nao e 'R' nem 'U'.
    rural = "R" if "RURAL" in _sem_acento(corpo[:400]) else None
    print(f"  rural_urbano         : {rural or '(não dito)'}"
          f"   (a casa usa 'R'/'U': 1.331 e 370)")
    print("\n  SELO: **não sai daqui**. Selar fala com a rede e custa "
          "dinheiro — o caminho é a tela.")

    if not args.confirmar:
        print("\nNada foi gravado — rode de novo com --confirmar.")
        con.close()
        return 0

    marca = datetime.now().strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005
    copia = banco.with_suffix(f".antes-da-abertura-{marca}.sqlite3")
    # FORA DA PASTA DO BANCO — ordem do oficial em 11/10/2026.
    import pasta_das_copias as _PC
    copia = _PC.destino_da_copia(copia, Path(banco))
    try:
        banco_pg.copiar_para_arquivo(banco, copia)
    except sqlite3.OperationalError:
        shutil.copy2(banco, copia)
    print(f"\nCópia do banco guardada em:\n  {copia}")

    agora = datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005
    with con:
        for p in partes:
            bd.escrever(
                """INSERT INTO ri_partes
                   (matricula_id, ato_id, nome, nome_norm, documento_tipo,
                    documento_numero, documento_valido, qualificacao, papel,
                    proprietario, proprietario_ativo, origem, origem_chave)
                   VALUES (%s, NULL, %s, %s, %s, %s, 0, %s, 'proprietario', %s, %s,
                           'MANUAL', %s)""",
                (m["id"], p["nome"], _sem_acento(p["nome"]),
                 "CNPJ" if "/" in p["documento_numero"] else "CPF",
                 re.sub(r"\D", "", p["documento_numero"]),
                 p["qualificacao"], p["proprietario_ativo"],
                 p["proprietario_ativo"], docx.name))
        bd.escrever(
            """UPDATE ri_matriculas
                  SET area_valor=COALESCE(NULLIF(area_valor,''), %s),
                      area_unidade=COALESCE(NULLIF(area_unidade,''), %s),
                      descricao_perimetro=COALESCE(NULLIF(descricao_perimetro,''), %s),
                      registro_anterior=COALESCE(NULLIF(registro_anterior,''), %s),
                      emolumentos_abertura=COALESCE(NULLIF(emolumentos_abertura,''), %s),
                      rural_urbano=CASE
                          WHEN rural_urbano IN ('R','U') THEN rural_urbano
                          ELSE COALESCE(%s, rural_urbano) END,
                      atualizado_em=%s
                WHERE id=%s""",
            (area.group(1) if area else None,
             (area.group(2).lower() if area else None),
             campos["descricao_perimetro"] or None,
             campos["registro_anterior"] or None,
             campos["emolumentos"] or None,
             rural,
             agora, m["id"]))
        # Quem grava por programa diz quem e e a mando de quem (26/10/2026).
        IDR.registrar(
            bd, ts=agora, user_id=None,
            username="tools/importar_ficha_de_abertura.py",
            action="RI_ABERTURA_IMPORTADA", entity_type="RI_MATRICULA",
            entity_id=int(m["id"]),
            details=('{"matricula": "%s", "arquivo": "%s", "partes": %d, '
                     '"motivo": "a ficha nasceu do transporte so com o teor; os '
                     'campos e as partes vieram do documento de abertura, por ordem '
                     'do delegatario. Nao selou e nao cobrou."}'
                     % (m["numero"], docx.name, len(partes))),
            agente="tools/importar_ficha_de_abertura.py",
            a_mando_de=IDR.PELO_RESPONSAVEL)

    print(f"\n{len(partes)} parte(s) gravadas e os campos preenchidos.")
    for d in bd.ler("""SELECT nome, documento_numero, proprietario_ativo
                         FROM ri_partes WHERE matricula_id=%s ORDER BY id""",
                    (m["id"],)):
        print(f"   {d['nome']} · {d['documento_numero']} · "
              f"{'ativo' if d['proprietario_ativo'] else 'cônjuge'}")
    print("\nFALTA O SELO DA ABERTURA — item 16.2. Ele não sai daqui.")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
