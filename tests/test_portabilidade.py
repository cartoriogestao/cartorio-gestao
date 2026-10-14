"""
O acoplamento ao SQLite não pode crescer.

POR QUE ESTE ARQUIVO EXISTE
    Em 25/08/2026 o oficial perguntou o que custaria migrar para PostgreSQL ou
    SQL Server. A resposta saiu de medição, e está em
    `DOCUMENTACAO/MIGRAR_DE_BANCO.md`: hoje não compensa — 111 MB, seis
    usuários e **zero** "database is locked" em um ano de uso.

    A decisão foi: **não pagar a migração agora, e parar de aumentar a dívida.**
    Este arquivo é a segunda metade disso.

O QUE ELE GUARDA, E O QUE ELE NÃO GUARDA
    Ele NÃO tenta impedir todo SQL específico. Os 686 comandos escritos à mão,
    os 71 `lastrowid` e os 43 `INSERT OR IGNORE` ficam onde estão: não há
    alternativa barata para eles, e trocá-los agora seria pagar a migração sem
    migrar.

    Ele guarda só o acoplamento **gratuito** — aquele onde a forma portátil
    custa o mesmo ou menos:

      - data e hora calculadas **no SQL** (`strftime`, `julianday`), quando o
        Python faz igual. `protesto_certidao.data_limite` já é assim de
        propósito: subtrair ano de texto ISO é conta de inteiro.
      - `substr(` e `||` no SQL, que o Python faz na volta.
      - `PRAGMA` fora dos módulos de esquema, onde ele é da casa.

    O número de hoje vira TETO. Módulo novo entra sem nenhum; módulo antigo
    pode diminuir, nunca aumentar.

COMO BAIXAR UM TETO
    Tirando o uso e ajustando o número aqui, na mesma mudança. O teto é
    registro do que existe, e não meta: baixá-lo é a única direção permitida.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — referencia acervo_eoficio ou sqlite de producao

import ast
import re
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

FONTES = sorted(p for p in RAIZ.glob("*.py"))

# Onde o `PRAGMA` é da casa: os esquemas o usam para decidir migração
# (`PRAGMA table_info`), e `database.py` o usa para ligar WAL e chaves
# estrangeiras. Fora daqui, ele é acoplamento que não precisa existir.
DONOS_DO_PRAGMA = {
    "database.py", "acervo_eoficio.py", "acervo_carga.py",
    # cervo_eo_vivo.py entrou em 07/09/2026: puxa tbAvisoProtesto/tbPessoa
    # do MSSQL ao vivo para o sqlite. O PRAGMA table_info e a mesma disciplina
    # de acervo_carga — saber quais colunas o acervo ja tem antes de reinscrever.
    "acervo_eo_vivo.py",
    "ajuda.py",
    "caixa_schema.py", "fr_schema.py", "notas_schema.py", "nucleo_schema.py",
    "pt_schema.py", "ra_schema.py", "rc_schema.py", "rg_schema.py",
    "ri_schema.py", "rt_schema.py", "us_schema.py", "ex_schema.py",
    "rr_schema.py", "ajuda_problemas.py",
    # `as_schema.py` entrou em 01/09/2026, com a fila de assinatura digital.
    # E modulo de ESQUEMA como os outros: o PRAGMA dele esta na passada de
    # `MIGRACOES`, que e onde este projeto o permite.
    "as_schema.py",
    # `cn_schema.py` entrou em 02/09/2026, com as pendencias da CENPROT. E
    # modulo de ESQUEMA como os outros catorze: tem `SCHEMA`, tem `MIGRACOES`,
    # e o `PRAGMA table_info` dele e a maquina da migracao — a mesma linha,
    # palavra por palavra, que `as_schema` e `pt_schema` tem.
    "cn_schema.py",
    # `rc_pedidos_schema.py` entrou em 03/09/2026, com a fila da Central de
    # Certidoes do ON-RCPN. E modulo de ESQUEMA como os outros dezesseis: tem
    # `SCHEMA`, tem `MIGRACOES`, e o `PRAGMA table_info` dele e a maquina da
    # migracao — a mesma linha, palavra por palavra, que `cn_schema` tem.
    "rc_pedidos_schema.py",
    # `ri_onr_central_schema.py` entrou em 03/09/2026, com o rastro do que
    # sobe ao ONR. E modulo de ESQUEMA como os outros dezessete.
    "ri_onr_central_schema.py",
    # `rc_modelos_livres_schema.py` entrou em 07/09/2026, com o modulo
    # «Modelos» do E-Oficio copiado. E modulo de ESQUEMA como os outros: tem
    # `SCHEMA`, tem `MIGRACOES`, e o `PRAGMA table_info` dele e a maquina da
    # migracao — a mesma linha, palavra por palavra, que `rc_pedidos_schema`
    # tem.
    "rc_modelos_livres_schema.py",
    # `robo_schema.py` entrou em 07/09/2026, com os robos do cartorio. E
    # modulo de ESQUEMA como os outros: tem `SCHEMA`, tem `MIGRACOES`, e o
    # `PRAGMA table_info` dele esta dentro de `init_robo_schema`, na passada
    # da migracao. **Declarado por quem nao o escreveu**, e por isso conferido
    # linha a linha antes: e a mesma linha que `rc_pedidos_schema` tem.
    "robo_schema.py",
    # `modelos_elementos_schema.py` entrou em 07/09/2026, com os seis
    # submodulos de modelos. E modulo de ESQUEMA como os outros: tem `SCHEMA`,
    # tem `MIGRACOES`, e o `PRAGMA table_info` dele e a maquina da migracao.
    "modelos_elementos_schema.py",
    # `agente_schema.py` entrou em 14/09/2026, com o agente do sistema. E
    # modulo de ESQUEMA como os outros: tem `SCHEMA`, tem `MIGRACOES` (vazio
    # hoje, porque as quatro tabelas nascem inteiras) e o `PRAGMA table_info`
    # dele esta dentro do `init_agente_schema`, na passada da migracao — a
    # mesma linha, palavra por palavra, que `robo_schema` tem.
    "agente_schema.py",
    # `wa_schema.py` entrou em 02/09/2026, com a fila do WhatsApp. E modulo de
    # ESQUEMA como os outros quinze — tem `SCHEMA`, tem `MIGRACOES`, e o
    # `PRAGMA table_info` dele e a maquina da migracao. **Este PRAGMA e de
    # verdade** (esta dentro do SQL), ao contrario do `strftime` que o mesmo
    # varredor acusou no `wa_balcao.py` e que era Python.
    "wa_schema.py",
    # `gestor_schema.py` entrou em 06/10/2026, com o gestor da casa (a
    # conferência diária). E modulo de ESQUEMA como os outros: tem `SCHEMA`,
    # tem `_COLUNAS_TARDIAS` (as migrações dele), e o `PRAGMA table_info` esta
    # dentro de `init_gestor_schema`, na passada da migracao — a mesma linha
    # que `robo_schema` tem.
    "gestor_schema.py",
    # `atrib_certidao.py` e `rc_certidao.py` entraram em 10/09/2026, e a
    # omissão é antiga: os dois ganharam migração quando nasceu a declaração
    # do selo no TJMA (`declaracao_selo_tjma_em`/`_por`) e **ninguém os
    # declarou aqui** — de modo que este varredor estava VERMELHO, e varredor
    # vermelho não guarda nada. Eles não têm nome `*_schema`, mas são a mesma
    # coisa: têm `SCHEMA`, têm a passada de migração dentro do
    # `init_*_schema`, e o `PRAGMA table_info` deles é a máquina dela — a
    # mesma linha, palavra por palavra, que `rc_pedidos_schema` tem.
    #
    # **Declarados por quem não os escreveu**, e por isso conferidos linha a
    # linha antes: `atrib_certidao.py:429` e `rc_certidao.py:152`, os dois
    # dentro do `init`, os dois só para saber que coluna já existe antes do
    # `ALTER TABLE`. É «suba o teto na mesma mudança e diga por quê», e a
    # mudança é o conserto do `MIGRACOES` de `atrib_certidao` no mesmo dia.
    "atrib_certidao.py", "rc_certidao.py",
    # 12/10/2026 («resolve as 7»): `modelos_editor_schema.py` é módulo de
    # ESQUEMA (tem `SCHEMA` e `MIGRACOES`, e o `PRAGMA table_info` é a máquina
    # da migração); `sqlite_esquema.py` nasceu para ser O lugar onde módulo de
    # domínio pergunta as colunas — gestor_conferencia, produtividade e
    # rc_averbacao_modelos_web perguntavam ao SQLite direto, cada um a seu modo.
    "modelos_editor_schema.py", "sqlite_esquema.py",
}
# `ajuda.py` passou a ter migração no Lote 1 da privacidade obrigatória.
# Como `ajuda_problemas.py`, ele cria e atualiza as próprias tabelas; a leitura
# do esquema serve somente para acrescentar as quatro colunas de auditoria em
# bancos existentes, sem apagar o histórico anterior.
# `ajuda_problemas.py` entrou em 30/08/2026, com o campo de nota de
# desenvolvimento (relato #35). **Ele nao se chama `_schema` e e modulo de
# esquema assim mesmo**: tem `SCHEMA`, tem `MIGRACOES`, e o `PRAGMA table_info`
# dele e a mesma maquina de migracao dos dezesseis acima, palavra por palavra.
# Quem manda aqui e o que o modulo FAZ, e nao como ele se chama — a lista por
# nome de arquivo e a lista escrita a mao que envelhece.
# `rt_schema.py` entrou em 29/08/2026, com a retificacao de area. Ele e modulo
# de ESQUEMA como os outros doze, e o `PRAGMA table_info` dele e a maquina da
# migracao — a mesma linha que `us_schema` e `ri_schema` tem, palavra por
# palavra. Nao e divida nova: e o padrao da casa aplicado a uma tabela nova.
#
# `ex_schema.py` entrou no mesmo dia, com «o que comecou e nao terminou». Ele
# **nao tem migracao nenhuma hoje**, e o `PRAGMA` esta ali num laco que nao roda
# — e fica, porque a alternativa seria escrever o laco no dia da primeira
# migracao, que e justamente o dia em que ninguem lembra que ele nao existe.
# Modulo de esquema nasce com a maquina inteira.

# O TETO MEDIDO EM 25/08/2026. Um número por módulo, para que quem baixar um
# veja o que baixou — e para que um módulo novo não se esconda atrás do total.
# **ESTE TETO TINHA DOZE MÓDULOS E TRINTA E CINCO USOS; TEM UM E QUATRO.**
#
# Medido em 02/09/2026, quando o varredor passou a olhar dentro das strings em
# vez de procurar a palavra no arquivo: **onze dos doze módulos não tinham uma
# única data calculada no SQL**. O que ele achava era `datetime.strftime`, que
# é Python e roda igual em Postgres, em SQL Server e em papel.
#
# Os quatro que sobram são reais, e são os dois `julianday` de `database.py`
# (contados duas vezes cada, porque a linha tem `julianday(a) - julianday(b)`):
# a espera e o atendimento do painel de senhas.
#
# **Nada foi consertado para o teto baixar** — o que baixou foi a mentira.
TETO_DATA_NO_SQL = {
    "database.py": 4,
}
TETO_TEXTO_NO_SQL = {
    "ri_web.py": 8, "database.py": 2, "caixa_depositos.py": 1,
    "caixa_web.py": 1,
    # **`selo_consulta.py` SAIU DAQUI EM 15/09/2026, E NAO POR RECORTE NO SQL.**
    # Ele tinha 3 — `SUBSTR(numero,1,6)`, `SUBSTR(obtido_em,1,7)` e
    # `DATE(obtido_em)` —, e o comentario que o justificava dizia que recortar
    # em Python traria as 26 mil linhas a cada pergunta. O modulo foi
    # **apagado** na consolidacao das duas telas de selos, e o agrupamento vivo
    # (`selos_emitidos.por_grupo`) corta o prefixo e o mes **depois de ler**.
    #
    #   **A CONTA QUE O COMENTARIO TEMIA FOI MEDIDA**, e e pequena:
    #   `por_grupo` responde em **0,046 a 0,054 s** sobre os 26.278 selos da
    #   producao — duas a quatro vezes o `GROUP BY` no banco, e cinquenta
    #   milesimos em numero absoluto. A pergunta era «trava ou responde?», e ela
    #   se responde com o relogio, nao com o argumento. A medicao esta em
    #   `selos_emitidos.por_grupo` e em `tmp/o_33_o_por_grupo_responde.py`.
    # OS DOIS ABAIXO ENTRARAM EM 14/09/2026, E NAO SAO DESTA PASSADA — sao
    # DECLARADOS, e nao consertados: quem nao esta construindo o modulo nao
    # mexe nele (regra de 02/09). Ficam aqui para a divida ter dono e tamanho,
    # em vez de deixar a suite vermelha para todo mundo.
    #
    #   `caixa_protocolo.py` e divida DE VERDADE: `ORDER BY CAST(SUBSTR(numero,
    #   ?) AS INTEGER)` ordena o protocolo pelo numero depois do prefixo. Quem
    #   o construiu sabe se da para ordenar por coluna propria.
    "caixa_protocolo.py": 1,
    #   `acervo_eo_vivo.py` e FALSO POSITIVO, e vale dizer qual: os dois `||`
    #   dele nao sao SQL — um e `-join ' || '` de PowerShell dentro de um
    #   script, e o outro e `"||".join(conexoes)`, separador de string em
    #   Python. **E a familia «o varredor conta a palavra em vez do SQL» pela
    #   decima terceira vez neste projeto**, e desta vez a regua nao tem como
    #   distinguir: ele ja le so literais, e `"||"` E um literal. Consertar a
    #   regua exigiria ela saber que aquela string vira SQL — que e
    #   justamente o que ela nao pode saber.
    "acervo_eo_vivo.py": 1,
}
# E DOIS TETOS AQUI DECLARAVAM DIVIDA QUE NUNCA EXISTIU — achado em
# 01/09/2026, quando o varredor parou de contar a diretiva de ferramenta.
# `notas_censec.py: 1` e `notas_doi.py: 1` estavam escritos, e nos dois o
# unico «pragma» do arquivo e o `# pragma: no cover` de um `__repr__`:
# **zero PRAGMA de SQL nos dois.** Quem lesse esta lista para saber o
# tamanho do acoplamento ao SQLite contaria dois modulos a mais.
#
# **Teto que mente e pior que teto alto**: o alto se paga, o que mente
# manda pagar o que nao se deve. Sao o «carimbo que mente» na forma de
# divida declarada, e por isso sairam da lista — e nao viraram `0`, porque
# modulo fora do teto ja entra com zero.
# **E DOIS DESTES TAMBEM ERAM MENTIRA — 02/09/2026.** Com o varredor olhando
# dentro das strings, `emolumentos.py` e `notas_import.py` cairam para ZERO:
# a palavra que ele achava neles nao e SQL. Sao o terceiro e o quarto caso da
# mesma familia neste teto, depois de `notas_censec` e `notas_doi` em 01/09.
#
# **Quem os achou foi o guarda que ja existia** — `test_o_teto_nao_lista_
# modulo_que_ja_nao_usa` —, e nao a releitura: ele compara o teto com o que o
# arquivo tem, e reclama quando o teto e maior. Sem ele, a divida inventada
# ficaria declarada para sempre, porque teto folgado nunca fica vermelho.
TETO_PRAGMA_FORA_DE_CASA = {
    "custas.py": 1,
    # `centrais_log.py` entrou em 12/10/2026 com 1: `PRAGMA busy_timeout` na
    # conexão que grava o registro de uma chamada às Centrais. É ajuste da
    # CONEXÃO (como o WAL de database.py), e não pergunta de esquema: o log
    # espera pouco pela trava para nunca segurar o balcão. O sqlite3 do Python
    # só aceita esse tempo ao abrir a conexão, e quem abre é `db.connect()`.
    "centrais_log.py": 1,
    "ri_import.py": 1,
    # `importar_padrao.py` entrou em 30/08/2026, com o padrao de importacao
    # (relato #31), e **o `PRAGMA` dele e a razao de o modulo existir**.
    #
    #   A lista de campos que o arquivo aceita e MEDIDA do esquema, e nao
    #   escrita: escrita a mao, ela envelheceria na tarde em que fosse escrita,
    #   e quem preparasse o arquivo mandaria um campo que a tela nao le mais.
    #   E o mesmo defeito do menu, das cargas e do teste que devia guardar as
    #   duas — so que aqui quem paga e uma serventia de fora, que refaz a
    #   exportacao inteira.
    #
    #   `SELECT * LIMIT 0` seria portavel e nao serve: `cursor.description` da
    #   o NOME da coluna e nao diz se ela e obrigatoria — e e o obrigatorio que
    #   faz a conferencia valer. Ao migrar, `information_schema.columns`
    #   responde o mesmo nos dois outros bancos.
    #
    #   **SUBIU PARA 2 EM 14/09/2026, e a regra permite subir dizendo por que.**
    #   O segundo e `PRAGMA foreign_key_list`, em `_criado_por_e_fk_de_usuario`.
    #   Ele nasceu de um defeito real: `criado_por` e FK para `users(id)` SO em
    #   `ri_matriculas`, e o modulo gravava ali o NOME de quem importou —
    #   `usuario_nome()`, uma string. A importacao de matricula estourava com
    #   `IntegrityError` em toda tela, e nenhum teste pegava porque a fixture
    #   nao ligava `foreign_keys`.
    #
    #   PERGUNTAR AO ESQUEMA E O QUE EVITA A LISTA ESCRITA A MAO, que e o mesmo
    #   motivo do primeiro `PRAGMA`: escrever «so `ri_matriculas` tem essa FK»
    #   seria verdade hoje e mentira no dia em que outra tabela ganhasse a
    #   dela. Ao migrar, `information_schema.table_constraints` responde o
    #   mesmo nos dois outros bancos.
    "importar_padrao.py": 2,
    # ------------------------------------------------------------------
    # ESTES TRES ENTRARAM EM 15/09/2026, **E NAO SAO MEUS** — vieram da
    # passada que construiu as MINUTAS e o TEOR do RI nesta mesma arvore,
    # no mesmo dia. Foi o `.cgu` da 3.6.99 (11/09, 20h03) quem respondeu
    # «esta falha e minha?»: la os tres ou nao estavam no pacote
    # (`ri_lavrar_teor.py`) ou nao tinham `PRAGMA` nenhum. E o procedimento
    # de 10/09 — **quem nao esta construindo o modulo nao mexe nele** —, e
    # por isso nao toquei nos tres modulos. O que se faz aqui e **declarar a
    # divida que eles contraíram**, que e o que este teto existe para
    # obrigar: a suite inteira ficava vermelha por uma divida de outra
    # passada, e vermelho que ninguem declara deixa de ser lido.
    #
    # OS TRES SAO A MESMA FAMILIA DE `custas.py`, e por isso entram com 1:
    # `PRAGMA table_info` para **perguntar ao esquema se a coluna existe**
    # antes de usá-la. Nao e capricho — e o banco que ja existe, migrado
    # pelo `MIGRACOES` (`ALTER TABLE ADD COLUMN`), onde a coluna nova pode
    # nao estar; sem a pergunta, a consulta estoura em instalacao antiga e
    # passa na nova, que e o defeito do `SUM()` sem `COALESCE` pela outra
    # ponta. **Escrever a lista de colunas a mao** seria verdade hoje e
    # mentira no dia em que outra coluna nascesse — a licao do menu, das
    # cargas e do teste que devia guarda-las.
    #
    #   `caixa_depositos.py`:107 e `ri_lavrar_teor.py`:267 perguntam por
    #   `cx_protocolos`; `caixa_protocolo.py`:305 e a versao com o nome da
    #   tabela recebido por parametro, que confere antes de escrever.
    #
    # AO MIGRAR DE BANCO: `information_schema.columns` responde o mesmo nos
    # dois outros, como ja esta escrito nos dois primeiros do teto.
    #
    # **QUEM FECHAR A CONTA E A PASSADA QUE ESCREVEU OS TRES**: se o uso
    # nao for necessario, o certo e tirar — e este comentario some junto.
    "caixa_depositos.py": 1,
    "caixa_protocolo.py": 1,
    "ri_lavrar_teor.py": 1,
}


# O JAVASCRIPT NAO E SQL, e o varredor lia os dois como se fossem.
#
#   **QUINTO CASO DESTA FAMILIA**, em 30/08/2026. Os quatro anteriores foram o
#   varredor batendo na PROSA dos comentarios (um `substr(` citado, uma mensagem
#   do SQLite copiada, o nome de uma funcao que o comentario dizia nao chamar) e
#   o `DO UPDATE SET` do `ON CONFLICT`, que fez o varredor acusar escrita numa
#   tabela chamada «SET».
#
#   Aqui e o bookmarklet de `rc_cpf.py`: `(tds[i].textContent||'')` casa com
#   `\|\|\s*'`, o padrao da concatenacao SQL. **Em JavaScript `||` e «ou».**
#
#   E declarar `rc_cpf.py: 2` no teto seria pior que o falso alarme: registraria
#   como divida de SQL o que e JavaScript, e quem viesse depois procuraria uma
#   consulta que nao existe. **Teto e para uso real; falso achado se conserta no
#   varredor.**
SEM_JAVASCRIPT = re.compile(r'"""javascript:.*?"""', re.DOTALL)


# `# pragma: no cover` E DIRETIVA DE FERRAMENTA, E NAO SQL — e o varredor do
# `PRAGMA` batia nela. Sexta vez neste projeto que um varredor acha a palavra
# fora do codigo que ele quer medir; as cinco anteriores foram prosa de
# comentario, e esta e pior, porque `# pragma: no cover` e escrita normal em
# Python: quem a usasse levaria a acusacao de acoplar ao SQLite.
SEM_DIRETIVA_DE_FERRAMENTA = re.compile(r"#\s*pragma\s*:.*")


def _strings_de_codigo(fonte: str) -> list[str]:
    """As strings do módulo — **sem docstring e sem comentário**.

    **É AQUI QUE MORA O SQL, E SÓ AQUI.** Um `SELECT ... strftime(...)` é uma
    string; um `data.strftime("%d/%m/%Y")` é código Python, e não tem nada de
    SQLite. Contar a palavra no arquivo inteiro confunde os dois.

    O comentário nem chega: ele não vira nó da árvore. A docstring vira, e por
    isso sai fora — **é a prosa que este projeto já viu enganar seis
    varredores**, e num teste que fala de `strftime` na própria explicação ela
    enganaria o sétimo.
    """
    arvore = ast.parse(fonte)
    prosa = set()
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                           ast.ClassDef)) and corpo:
            primeiro = corpo[0]
            if (isinstance(primeiro, ast.Expr)
                    and isinstance(primeiro.value, ast.Constant)
                    and isinstance(primeiro.value.value, str)):
                prosa.add(id(primeiro.value))
        # string solta no meio do corpo também é prosa, e não SQL
        if (isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant)
                and isinstance(no.value.value, str)):
            prosa.add(id(no.value))
    return [n.value for n in ast.walk(arvore)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in prosa
            # o bloco de JavaScript é string e não é SQL — a exclusão que o
            # `SEM_JAVASCRIPT` já fazia, agora pelo conteúdo
            and not n.value.lstrip().startswith("javascript:")]


def _contar(padrao: str) -> Counter:
    """Quantos usos daquele padrão **dentro do SQL** de cada módulo.

    **ELE CONTAVA A PALAVRA, E ISSO ERA A SÉTIMA VEZ.** Este projeto já viu
    seis varredores acharem o que procuravam fora do código que queriam
    medir — o `substr(` citado num comentário, a mensagem do SQLite copiada ao
    pé da letra, o nome da função no comentário que explicava tê-la tirado, o
    `DO UPDATE SET` do `ON CONFLICT`, o `# pragma: no cover`, e a palavra
    «algo» num HTML. Esta é a sétima, e a maior: **dos 35 usos de data que o
    teto declarava, 4 eram SQL** — os outros 31 eram `datetime.strftime`, que
    é Python puro e roda igual em qualquer banco.

    **Teto que mente é pior que teto alto**: o alto se paga, e o que mente
    manda pagar o que não se deve.
    """
    achados: Counter = Counter()
    for p in FONTES:
        fonte = p.read_text(encoding="utf-8", errors="replace")
        try:
            pedacos = _strings_de_codigo(fonte)
        except SyntaxError:
            # Arquivo que não compila não se mede — e o erro aparece na suíte,
            # que é onde ele tem de aparecer.
            continue
        n = sum(len(re.findall(padrao, s, re.IGNORECASE)) for s in pedacos)
        if n:
            achados[p.name] = n
    return achados


def _conferir(achados: Counter, teto: dict[str, int], o_que: str,
              como: str) -> None:
    piores = []
    for nome, quantos in achados.items():
        limite = teto.get(nome, 0)
        if quantos > limite:
            piores.append(
                f"  {nome}: {quantos} {o_que} (o teto é {limite}). {como}")
    assert not piores, (
        "O acoplamento ao SQLite cresceu:\n" + "\n".join(piores)
        + "\n\nVer DOCUMENTACAO/MIGRAR_DE_BANCO.md. Se o uso for mesmo "
          "necessário, suba o teto na mesma mudança e diga por quê."
    )


def test_data_e_hora_nao_se_calculam_no_sql():
    """`strftime` e `julianday` não existem em Postgres nem em SQL Server.

    O Python faz o mesmo, e o resultado fica testável sem banco.
    """
    _conferir(_contar(r"\b(?:strftime|julianday)\s*\("), TETO_DATA_NO_SQL,
              "uso(s) de strftime/julianday",
              "Calcule a data em Python, como `protesto_certidao.data_limite`.")


def test_texto_nao_se_recorta_no_sql():
    """`substr(` e `||` mudam de nome fora do SQLite, e o Python faz igual."""
    _conferir(_contar(r"\bsubstr\s*\(|\|\|\s*'"), TETO_TEXTO_NO_SQL,
              "recorte/concatenação em SQL",
              "Recorte e junte em Python, depois de ler.")


def test_pragma_so_mora_onde_ele_e_da_casa():
    """`PRAGMA` não tem equivalente em nenhum outro banco.

    Nos esquemas ele é a máquina da migração e fica; fora deles, é dívida.
    """
    achados = Counter({nome: n for nome, n in _contar(r"\bPRAGMA\b").items()
                       if nome not in DONOS_DO_PRAGMA})
    _conferir(achados, TETO_PRAGMA_FORA_DE_CASA, "PRAGMA(s)",
              "Um módulo de domínio não precisa perguntar o esquema ao banco.")


def test_o_teto_nao_lista_modulo_que_ja_nao_usa():
    """Teto de módulo que já foi limpo é teto que mente.

    Se alguém tirou o uso e esqueceu de tirar a linha daqui, o próximo a ler
    acha que a dívida é maior do que é.
    """
    atual = {
        "data no SQL": (_contar(r"\b(?:strftime|julianday)\s*\("),
                        TETO_DATA_NO_SQL),
        "texto no SQL": (_contar(r"\bsubstr\s*\(|\|\|\s*'"), TETO_TEXTO_NO_SQL),
        "PRAGMA fora de casa": (
            Counter({n: q for n, q in _contar(r"\bPRAGMA\b").items()
                     if n not in DONOS_DO_PRAGMA}),
            TETO_PRAGMA_FORA_DE_CASA),
    }
    sobrando = []
    for rotulo, (achados, teto) in atual.items():
        for nome, limite in teto.items():
            if achados.get(nome, 0) < limite:
                sobrando.append(
                    f"  {rotulo} — {nome}: o teto diz {limite} e o arquivo tem "
                    f"{achados.get(nome, 0)}. Baixe o teto.")
    assert not sobrando, (
        "Teto acima do que existe (isso é bom — só falta registrar):\n"
        + "\n".join(sobrando))


def test_o_mapa_da_migracao_existe():
    """A resposta ao oficial fica escrita, e não na cabeça de quem respondeu.

    O CAMINHO APONTAVA PARA A PASTA ANTIGA — achado em 09/09/2026, ao
    reorganizar a raiz do projeto. `RAIZ.parent.parent/DOCUMENTACAO` é a
    pasta que ficava solta na raiz (72 documentos, retrato de agosto,
    consolidação de 29/08/2026); o arquivo que viaja com o sistema, e que a
    Ajuda do sistema lê, está em `RAIZ/DOCUMENTACAO/` — dentro de
    INSTALAR_CARTORIO_GESTAO. O teste só não tinha estourado porque a cópia
    velha continuava por acaso na raiz.
    """
    mapa = RAIZ / "DOCUMENTACAO" / "MIGRAR_DE_BANCO.md"
    assert mapa.exists(), f"falta {mapa}"
    texto = mapa.read_text(encoding="utf-8")
    # O gatilho medido tem de estar lá, com o nome do arquivo que o registra.
    assert "disputas_de_escrita.log" in texto
    assert "database is locked" in texto
