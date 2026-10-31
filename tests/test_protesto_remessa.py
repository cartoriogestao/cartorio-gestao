"""
Testes da REMESSA DA CRA — o passo do meio-dia do roteiro do oficial.

O QUE ELES CONFEREM

    Que O MESMO ARQUIVO NAO ENTRA DUAS VEZES, e que a trava sobrevive a ele
    ser salvo noutro programa: CRLF e LF sao o mesmo arquivo. Subir a mesma
    remessa de novo apontaria tudo outra vez, e apontamento nao se desfaz.

    Que UM ARQUIVO COM MAIS DE UM LOTE entra com cada titulo no apresentante
    QUE O APRESENTOU. Medido: 6 dos 197 arquivos reais sao multi-lote e 3
    trazem apresentantes diferentes no mesmo arquivo. Ler so o primeiro
    cabecalho faria o retorno voltar para quem nao apresentou — e o defeito so
    apareceria la, meses depois.

    Que TITULO RUIM NAO DERRUBA O LOTE, e que o motivo da recusa fica
    guardado: quando o apresentante ligar perguntando por que aquele titulo
    nao voltou, e essa a resposta.

    Que A CONFIRMACAO CONFIRMA O QUE ENTROU. Medido em 138 pares
    remessa-confirmacao um para um dos arquivos reais desta casa: 130 trazem
    exatamente os titulos da remessa, 8 trazem menos, e NENHUMA traz titulo
    que nao veio.

    E que `conferir()` NAO GRAVA NADA — porque e a tela que o balcao abre
    primeiro, e tela de conferencia que grava e tela que ja recebeu.
"""
from __future__ import annotations

import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import ato_selado as AS
import protesto_arquivo as PA
import protesto_cra_xml as PCX
import protesto_remessa as PRM
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-08-25T12:00:00"
EXTENSO = "vinte e cinco de agosto de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}

EXEMPLO = (Path(__file__).parent / "cra_remessa_exemplo.txt").read_bytes()
RETORNO = (Path(__file__).parent / "cra_retorno_exemplo.txt").read_bytes()


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    init_pt_schema(c)
    yield c
    c.close()


def receber(con, conteudo=EXEMPLO, **kw):
    kw.setdefault("agora", AGORA)
    kw.setdefault("data_extenso", EXTENSO)
    kw.setdefault("sv", SV)
    return PRM.receber(con, conteudo, **kw)


def com_dois_lotes(*, apresentantes=("001", "237")) -> bytes:
    """Um arquivo com dois lotes, de apresentantes diferentes.

    Montado do exemplo real trocando o apresentante do segundo lote — que e
    exatamente a forma dos 3 arquivos reais em que os lotes sao de
    apresentantes distintos.
    """
    texto = EXEMPLO.decode("latin-1")
    linhas = [x for x in texto.replace("\r\n", "\n").split("\n") if x.strip()]

    def trocar(linha: str, codigo: str) -> str:
        # O codigo do apresentante ocupa as posicoes 2 a 4 no cabecalho, no
        # titulo e no rodape — as mesmas em que ele foi medido.
        campo = next(c for c in PA.CABECALHO
                     if c.nome == "codigo_do_apresentante")
        largura = campo.tamanho
        return (linha[:campo.inicio - 1] + codigo.ljust(largura)[:largura]
                + linha[campo.fim:])

    primeiro = [trocar(x, apresentantes[0]) for x in linhas]
    segundo = [trocar(x, apresentantes[1]) for x in linhas]
    # O segundo lote leva outro numero de titulo, senao seriam o mesmo papel.
    campo = next(c for c in PA.TITULO_NA_REMESSA if c.nome == "numero_do_titulo")
    segundo = [
        (x[:campo.inicio - 1] + "OUTRO".ljust(campo.tamanho)[:campo.tamanho]
         + x[campo.fim:]) if x[:1] == "1" else x
        for x in segundo]
    return "\r\n".join(primeiro + segundo).encode("latin-1")


# ------------------------------------------------------------- conferir


def test_conferir_le_o_lote_e_nao_grava_nada(con):
    visto = PRM.conferir(con, EXEMPLO)
    assert visto["quantidade_de_lotes"] == 1
    lote = visto["lotes"][0]
    assert lote["apresentante_codigo"] == "001"
    assert lote["quantidade"] == len(lote["titulos"]) == 1
    assert lote["aceitos"] == 1 and lote["recusados"] == 0
    assert lote["titulos"][0]["devedor"]
    # NADA foi gravado: e a tela que o balcao abre primeiro.
    assert con.execute("SELECT COUNT(*) c FROM pt_remessas").fetchone()["c"] == 0
    assert con.execute("SELECT COUNT(*) c FROM pt_titulos").fetchone()["c"] == 0


def test_arquivo_que_nao_e_remessa_e_recusado_dizendo_o_que_e(con):
    # AS PASTAS DO E-OFICIO MENTEM: ha remessa dentro de `Retorno`. Quem manda
    # e o tipo do cabecalho, e a mensagem tem de dizer o que o arquivo E.
    with pytest.raises(PRM.RemessaError) as erro:
        PRM.conferir(con, RETORNO)
    assert "não é uma remessa" in str(erro.value)
    assert "SDTBFORTP" in str(erro.value)


def test_arquivo_vazio_nao_passa_por_remessa(con):
    with pytest.raises((PRM.RemessaError, PA.ArquivoError)):
        PRM.conferir(con, b"")


# -------------------------------------------------------------- receber


def test_a_remessa_entra_aponta_e_confirma(con):
    r = receber(con)
    assert r["recebidos"] == 1 and r["apontados"] == 1
    assert len(r["remessas"]) == 1 and len(r["confirmacoes"]) == 1

    tit = con.execute("SELECT * FROM pt_titulos").fetchone()
    assert tit["situacao"] == "APONTADO"
    assert tit["apresentante_codigo"] == "001"
    assert tit["remessa_id"] == r["remessas"][0]
    # O PROTOCOLO NASCE COM O APONTAMENTO — e o numero que volta para a CRA.
    assert tit["protocolo"]

    ato = con.execute("SELECT * FROM pt_atos WHERE tipo='APONTAMENTO'").fetchone()
    assert ato["origem"] == "CRA"
    assert ato["livro_id"] and ato["numero_ordem"]


def test_a_confirmacao_e_arquivo_de_600_posicoes_que_volta_a_ser_lido(con):
    r = receber(con)
    linha = con.execute("SELECT * FROM pt_retornos WHERE id=?",
                        (r["confirmacoes"][0],)).fetchone()
    assert linha["tipo"] == PRM.TIPO_DA_CONFIRMACAO
    # Nome FEBRABAN desde 13/10/2026 (era «SDTBFOCRT-001-…txt», que a CRA
    # recusa): C + apresentante + DDMM da remessa + .AA + sequência.
    import re
    assert re.fullmatch(r"C001\d{4}\.\d{3}", linha["nome_arquivo"])

    volta = PA.ler(linha["conteudo"])
    assert volta.tipo == PRM.TIPO_DA_CONFIRMACAO
    assert volta.achados == []
    assert len(volta.titulos) == 1
    assert str(volta.cabecalho["codigo_do_apresentante"]).strip() == "001"


def com_tres_titulos(*, sem_devedor_no: int | None = None) -> bytes:
    """Um lote só com três títulos, montado do exemplo real, que tem um.

    Os títulos ganham número e nosso número próprios e o sequencial certo; o
    cabeçalho (h09 a h11) e o rodapé dizem três, como a remessa real que a CRA
    mandou. `sem_devedor_no` apaga o devedor daquele título: o contrato o recusa.
    """
    texto = EXEMPLO.decode("latin-1")
    cab, tit, rod = [x for x in texto.replace("\r\n", "\n").split("\n")
                     if x.strip()]

    def trocar(linha: str, campos, nome: str, valor: str) -> str:
        campo = next(c for c in campos if c.nome == nome)
        return (linha[:campo.inicio - 1] + valor.ljust(campo.tamanho)[:campo.tamanho]
                + linha[campo.fim:])

    titulos = []
    for i in (1, 2, 3):
        linha = trocar(tit, PA.TITULO_NA_REMESSA, "numero_do_titulo", f"8471{i}/1")
        linha = trocar(linha, PA.TITULO_NA_REMESSA, "nosso_numero",
                       f"97559000006018{i}")
        if i == sem_devedor_no:
            linha = trocar(linha, PA.TITULO_NA_REMESSA, "devedor_nome", "")
        titulos.append(linha[:596] + f"{i + 1:04d}")
    cab = cab[:67] + "0003" * 3 + cab[79:]
    rod = trocar(rod, PA.RODAPE, "quantidade_de_registros", "00005")
    rod = trocar(rod, PA.RODAPE, "soma_dos_valores", f"{148278 * 3:015d}")
    rod = rod[:596] + "0005"
    return "\r\n".join([cab, *titulos, rod]).encode("latin-1")


def _confirmacao_e_protocolos(con, r) -> tuple[list[str], dict]:
    conteudo = con.execute("SELECT conteudo FROM pt_retornos WHERE id=?",
                           (r["confirmacoes"][0],)).fetchone()["conteudo"]
    protocolos = {x["numero_titulo"]: x["protocolo"] for x in con.execute(
        "SELECT numero_titulo, protocolo FROM pt_titulos").fetchall()}
    return [x for x in conteudo.split("\r\n") if x], protocolos


def test_a_confirmacao_de_tres_titulos_leva_os_tres(con):
    """A remessa de 3 saía com 1, e a CRA recusava com 2122 (medido, 30/10/2026):
    o laço dos campos 43 a 45 pisava no contador dos títulos do lote."""
    r = receber(con, com_tres_titulos())
    assert r["recebidos"] == 3 and r["apontados"] == 3
    linhas, protocolos = _confirmacao_e_protocolos(con, r)

    assert [x[:1] for x in linhas] == ["0", "1", "1", "1", "9"]
    assert all(len(x) == 600 for x in linhas)
    assert [x[596:] for x in linhas] == ["0001", "0002", "0003", "0004", "0005"]
    assert len(set(protocolos.values())) == 3
    for linha, numero in zip(linhas[1:4], ("84711/1", "84712/1", "84713/1")):
        assert linha[216:227].strip() == numero
        assert linha[447:457] == protocolos[numero], "cada um com o seu protocolo"

    volta = PA.ler("\r\n".join(linhas) + "\r\n")
    assert volta.achados == [] and len(volta.titulos) == 3


def test_o_titulo_recusado_no_meio_do_lote_nao_leva_o_vizinho_junto(con):
    r = receber(con, com_tres_titulos(sem_devedor_no=2))
    assert r["recebidos"] == 2
    linhas, protocolos = _confirmacao_e_protocolos(con, r)

    assert [x[:1] for x in linhas] == ["0", "1", "1", "9"]
    assert [x[596:] for x in linhas] == ["0001", "0002", "0003", "0004"]
    assert [x[216:227].strip() for x in linhas[1:3]] == ["84711/1", "84713/1"]
    assert linhas[2][447:457] == protocolos["84713/1"]


# O que `protesto_cra_xml.ler` exige de um lote de 3: h10 = 3, h11 + h12 = 3 e o
# t05 como somatório de segurança (3 + 3 + 3 + 0).
COMO_A_CRA_MANDA = {"h09_a_h12": "0003000300030000", "t05": "00009"}
SALDO = 148278


def _com_contagens(bruto: bytes, *, h09_a_h12: str, t05: str) -> bytes:
    linhas = bruto.decode("latin-1").split("\r\n")
    linhas[0] = linhas[0][:67] + h09_a_h12 + linhas[0][83:]
    linhas[-1] = linhas[-1][:52] + t05 + linhas[-1][57:]
    return "\r\n".join(linhas).encode("latin-1")


def _contagens(linhas: list[str]) -> dict:
    cab, rod = linhas[0], linhas[-1]
    return {"h09": cab[67:71], "h10": cab[71:75], "h11": cab[75:79],
            "h12": cab[79:83], "t05": rod[52:57], "t06": rod[57:75],
            "t08": rod[596:]}


def test_lote_de_tres_com_um_recusado_sai_com_cabecalho_e_rodape_de_dois(con):
    """A CRA recusou com 2122 (medido, 30/10/2026): a soma dos registros do
    arquivo não conferia com o total que o cabeçalho informava."""
    bruto = _com_contagens(com_tres_titulos(sem_devedor_no=2), **COMO_A_CRA_MANDA)
    r = receber(con, bruto)
    assert r["recebidos"] == 2
    linhas, _ = _confirmacao_e_protocolos(con, r)

    assert all(len(x) == 600 for x in linhas)
    assert _contagens(linhas) == {
        "h09": "0002", "h10": "0002", "h11": "0002", "h12": "0000",
        "t05": "00006", "t06": f"{SALDO * 2:018d}", "t08": "0004"}

    # E SÓ ISSO MUDOU: o resto do cabeçalho e do rodapé é o da remessa.
    remessa = bruto.decode("latin-1").split("\r\n")
    assert linhas[0][:52] == remessa[0][:52]
    assert linhas[0][52:61] == "SDTBFOCRT"
    assert linhas[0][61:67] == remessa[0][61:67]
    assert linhas[0][83:] == remessa[0][83:]
    assert linhas[-1][:52] == remessa[-1][:52]
    assert linhas[-1][75:596] == remessa[-1][75:596]

    gravado = con.execute("SELECT titulos, soma_centavos FROM pt_retornos WHERE id=?",
                          (r["confirmacoes"][0],)).fetchone()
    assert gravado["titulos"] == 2 and gravado["soma_centavos"] == SALDO * 2


def test_a_confirmacao_parcial_fecha_as_contas_do_xml_que_vai_a_cra(con):
    """As mesmas contas que `protesto_cra_xml.ler` cobra do lote da remessa."""
    r = receber(con, _com_contagens(com_tres_titulos(sem_devedor_no=1),
                                    **COMO_A_CRA_MANDA))
    conteudo = con.execute("SELECT conteudo FROM pt_retornos WHERE id=?",
                           (r["confirmacoes"][0],)).fetchone()["conteudo"]
    raiz = ET.fromstring(PCX.escrever_xml(conteudo, "SDTBFOCRT").encode("latin-1"))
    hd, trs, tl = raiz.find("hd"), raiz.findall("tr"), raiz.find("tl")

    assert len(trs) == 2 == int(hd.get("h10"))
    assert int(hd.get("h11")) + int(hd.get("h12")) == 2
    assert int(tl.get("t05")) == sum(int(hd.get(f"h{i:02}")) for i in range(9, 13))
    assert int(tl.get("t06")) == sum(int(t.get("t18")) for t in trs)
    assert [int(hd.get("h17")), *(int(t.get("t52")) for t in trs),
            int(tl.get("t08"))] == [1, 2, 3, 4]


def test_o_lote_txt_que_conta_registros_no_rodape_continua_contando(con):
    """`protesto_arquivo.RODAPE`: cabeçalho + títulos + rodapé. Ali 5 viram 4, e
    a confirmação continua sendo lida sem achado."""
    r = receber(con, com_tres_titulos(sem_devedor_no=3))
    linhas, _ = _confirmacao_e_protocolos(con, r)
    assert _contagens(linhas)["t05"] == "00004"
    assert _contagens(linhas)["h10"] == "0002"
    assert PA.ler("\r\n".join(linhas) + "\r\n").achados == []


@pytest.mark.parametrize("h11_h12,esperado", [
    ("00030000", ("0002", "0000")),
    ("00000003", ("0000", "0002")),
])
def test_quem_tem_um_tipo_so_de_titulo_continua_com_ele(con, h11_h12, esperado):
    bruto = _com_contagens(com_tres_titulos(sem_devedor_no=2),
                           h09_a_h12="00030003" + h11_h12, t05="00009")
    linhas, _ = _confirmacao_e_protocolos(con, receber(con, bruto))
    assert (_contagens(linhas)["h11"], _contagens(linhas)["h12"]) == esperado
    assert _contagens(linhas)["t05"] == "00006"


def test_lote_misto_fecha_as_contas_sem_afirmar_qual_foi_o_recusado(con):
    """O registro do título não diz se é indicação ou original: a divisão não está
    medida, e por isso este teste cobra só a conta."""
    bruto = _com_contagens(com_tres_titulos(sem_devedor_no=2),
                           h09_a_h12="0003000300020001", t05="00009")
    c = _contagens(_confirmacao_e_protocolos(con, receber(con, bruto))[0])
    assert int(c["h11"]) + int(c["h12"]) == 2
    assert c["t05"] == "00006"


def test_campo_em_branco_na_remessa_nao_passa_a_declarar_nada(con):
    bruto = _com_contagens(com_tres_titulos(sem_devedor_no=2),
                           h09_a_h12=" " * 16, t05=" " * 5)
    linhas, _ = _confirmacao_e_protocolos(con, receber(con, bruto))
    assert all(len(x) == 600 for x in linhas)
    c = _contagens(linhas)
    assert (c["h09"], c["h10"], c["h11"], c["h12"]) == ("    ",) * 4
    assert c["t05"] == "     "
    assert c["t06"] == f"{SALDO * 2:018d}" and c["t08"] == "0004"


@pytest.mark.parametrize("contagens", [
    COMO_A_CRA_MANDA,
    {"h09_a_h12": "0003000300030000", "t05": "00005"},
    # Contas que não fecham: sem recusa, nada se conserta nem se recalcula.
    {"h09_a_h12": "0007000300010002", "t05": "00013"},
])
def test_lote_inteiro_aceito_sai_com_cabecalho_e_rodape_da_remessa(con, contagens):
    bruto = _com_contagens(com_tres_titulos(), **contagens)
    linhas, _ = _confirmacao_e_protocolos(con, receber(con, bruto))
    remessa = bruto.decode("latin-1").split("\r\n")
    assert linhas[0] == remessa[0][:52] + "SDTBFOCRT" + remessa[0][61:]
    assert linhas[-1] == remessa[-1]


def test_apontar_falso_deixa_o_titulo_esperando(con):
    r = receber(con, apontar=False)
    assert r["recebidos"] == 1 and r["apontados"] == 0
    assert con.execute("SELECT situacao FROM pt_titulos").fetchone()[0] == "RECEBIDO"
    assert con.execute(
        "SELECT COUNT(*) c FROM pt_atos").fetchone()["c"] == 0


# ------------------------------------------------- a trava do arquivo


def test_o_mesmo_arquivo_nao_entra_duas_vezes(con):
    # A TRAVA QUE IMPORTA. Subir de novo apontaria tudo outra vez, sairia
    # protocolo dobrado, folha gasta e dois avisos para o mesmo devedor.
    receber(con)
    with pytest.raises(PRM.RemessaError) as erro:
        receber(con)
    assert "já entrou" in str(erro.value)
    assert con.execute("SELECT COUNT(*) c FROM pt_titulos").fetchone()["c"] == 1


def test_crlf_e_lf_sao_o_mesmo_arquivo(con):
    # O mesmo arquivo salvo noutro programa troca CRLF por LF e continua sendo
    # o mesmo arquivo. Sem normalizar antes de assinar, a trava nao valeria.
    receber(con)
    outro = EXEMPLO.decode("latin-1").replace("\r\n", "\n").encode("latin-1")
    assert outro != EXEMPLO
    with pytest.raises(PRM.RemessaError):
        receber(con, outro)


def test_linha_em_branco_no_fim_nao_faz_arquivo_novo(con):
    receber(con)
    with pytest.raises(PRM.RemessaError):
        receber(con, EXEMPLO + b"\r\n\r\n")


def test_conferir_avisa_que_a_remessa_ja_entrou_sem_estourar(con):
    # A tela de conferencia MOSTRA; quem recusa e o recebimento.
    receber(con)
    visto = PRM.conferir(con, EXEMPLO)
    assert visto["ja_entrou"]
    assert visto["ja_entrou"][0]["recebidos"] == 1


# --------------------------------------------------------- multi-lote


def test_arquivo_com_dois_lotes_entra_como_duas_remessas(con):
    # O PIOR CASO MEDIDO: dois lotes de apresentantes diferentes no mesmo
    # arquivo. Ler so o primeiro cabecalho poria os titulos do segundo no
    # primeiro, e o retorno voltaria para quem nao apresentou.
    r = receber(con, com_dois_lotes())
    assert r["quantidade_de_lotes"] == 2
    assert r["apresentantes"] == ["001", "237"]
    assert r["recebidos"] == 2 and len(r["remessas"]) == 2

    por_apresentante = {
        x["apresentante_codigo"]: x["remessa_id"] for x in r["lotes"]}
    for codigo, remessa_id in por_apresentante.items():
        titulos = PRM.titulos_da_remessa(con, remessa_id)
        assert len(titulos) == 1
        dono = con.execute(
            "SELECT apresentante_codigo FROM pt_titulos WHERE remessa_id=?",
            (remessa_id,)).fetchone()[0]
        assert dono == codigo


def test_titulos_da_remessa_trazem_os_devedores_na_ordem_do_cadastro(con):
    """RESSALVA DO L012R: `ORDER BY t.id` sobre o JOIN dos devedores deixava
    ao PostgreSQL a ordem dos devedores do mesmo titulo. O SQLite dava a do
    cadastro (o `rowid`); agora o desempate e `d.id`."""
    r = receber(con)
    remessa_id = r["remessas"][0]
    tid = con.execute("SELECT id FROM pt_titulos WHERE remessa_id=?",
                      (remessa_id,)).fetchone()[0]
    con.execute("INSERT INTO pt_devedores(titulo_id, nome) VALUES (?, ?)",
                (tid, "SEGUNDO DEVEDOR DE EXEMPLO"))
    # O UPDATE de coluna com índice faz o PostgreSQL gravar a linha do primeiro
    # devedor de novo, depois da do segundo: a ordem em que as linhas estão
    # gravadas deixa de ser a do id.
    primeiro = con.execute(
        "SELECT id, nome FROM pt_devedores WHERE titulo_id=? ORDER BY id",
        (tid,)).fetchone()
    con.execute("UPDATE pt_devedores SET documento_numero='00000000191' "
                "WHERE id=?", (primeiro["id"],))
    nomes = [t["devedor_nome"] for t in PRM.titulos_da_remessa(con, remessa_id)]
    assert nomes == [primeiro["nome"], "SEGUNDO DEVEDOR DE EXEMPLO"]


def test_cada_lote_ganha_a_sua_confirmacao(con):
    r = receber(con, com_dois_lotes())
    assert len(r["confirmacoes"]) == 2
    codigos = []
    for confirmacao_id in r["confirmacoes"]:
        linha = con.execute("SELECT * FROM pt_retornos WHERE id=?",
                            (confirmacao_id,)).fetchone()
        volta = PA.ler(linha["conteudo"])
        assert volta.achados == []
        codigos.append(str(volta.cabecalho["codigo_do_apresentante"]).strip())
    assert sorted(codigos) == ["001", "237"]


def test_lote_repetido_recusa_o_arquivo_inteiro(con):
    # Receber metade deixaria o balcao sem saber o que ficou de fora, e o
    # resto so se descobriria pelo titulo que nunca voltou.
    receber(con)                                  # o lote de '001', sozinho
    antes = con.execute("SELECT COUNT(*) c FROM pt_titulos").fetchone()["c"]
    with pytest.raises(PRM.RemessaError) as erro:
        receber(con, com_dois_lotes())
    assert "já entrou" in str(erro.value)
    assert "001" in str(erro.value)
    depois = con.execute("SELECT COUNT(*) c FROM pt_titulos").fetchone()["c"]
    assert depois == antes


def test_separar_um_lote_so_devolve_uma_lista_de_um():
    # 191 dos 197 arquivos reais tem um lote so, e o caminho comum nao pode
    # ficar mais caro por causa dos 6.
    assert len(PRM.separar(EXEMPLO)) == 1
    assert len(PRM.separar(com_dois_lotes())) == 2
    assert PRM.separar(b"") == []


# ---------------------------------------------------- titulo recusado


def outra_remessa(numero: str = "0002") -> bytes:
    """O mesmo lote com outro numero de remessa — arquivo diferente de fato.

    Acrescentar espaco no fim NAO faz outro arquivo, e e de proposito:
    `normalizar` derruba linha em branco antes de assinar, senao a trava do
    hash cairia por um enter a mais.
    """
    texto = EXEMPLO.decode("latin-1")
    campo = next(c for c in PA.CABECALHO if c.nome == "numero_da_remessa")
    linhas = [x for x in texto.replace("\r\n", "\n").split("\n") if x.strip()]
    linhas = [(x[:campo.inicio - 1] + numero.rjust(campo.tamanho, "0")[:campo.tamanho]
               + x[campo.fim:]) if x[:1] in ("0", "9") else x for x in linhas]
    return "\r\n".join(linhas).encode("latin-1")


def sem_devedor() -> bytes:
    """O exemplo com o nome do devedor apagado — o contrato recusa."""
    texto = EXEMPLO.decode("latin-1")
    campo = next(c for c in PA.TITULO_NA_REMESSA if c.nome == "devedor_nome")
    linhas = [x for x in texto.replace("\r\n", "\n").split("\n") if x.strip()]
    linhas = [(x[:campo.inicio - 1] + " " * campo.tamanho + x[campo.fim:])
              if x[:1] == "1" else x for x in linhas]
    return "\r\n".join(linhas).encode("latin-1")


def test_titulo_que_o_contrato_recusa_nao_entra_e_o_motivo_fica_guardado(con):
    visto = PRM.conferir(con, sem_devedor())
    lote = visto["lotes"][0]
    assert lote["recusados"] == 1 and lote["aceitos"] == 0
    assert any("sem nome" in f for f in lote["titulos"][0]["faltas"])

    r = receber(con, sem_devedor())
    assert r["recebidos"] == 0
    linha = PRM.remessa(con, r["remessas"][0])
    # A REMESSA ENTRA MESMO ASSIM: o lote chegou, e o que ele trouxe fica
    # registrado — inclusive o que foi recusado, e por que.
    assert linha["titulos"] == 1 and linha["recusados"] == 1
    recusas = PRM.recusas(linha)
    assert len(recusas) == 1
    assert any("sem nome" in f for f in recusas[0]["faltas"])


def test_lote_sem_nenhum_titulo_aceito_nao_gera_confirmacao(con):
    # Confirmar zero titulo seria mandar a Central um recibo de nada.
    r = receber(con, sem_devedor())
    assert r["confirmacoes"] == []
    assert PRM.remessa(con, r["remessas"][0])["confirmacao_id"] is None


def test_titulo_sem_vencimento_entra(con):
    """CORRECAO DE 25/08/2026, achada medindo as remessas reais.

    37 dos 343 titulos das remessas reais chegam com `99999999` no vencimento
    — a marca de sem vencimento —, todos da especie CDA. Eu os recusava na
    porta, o que faria o balcao digitar a mao 11% do que a Central manda
    pronto. A propria CRA tem codigo para o caso: irregularidade 33.
    """
    texto = EXEMPLO.decode("latin-1")
    campo = next(c for c in PA.TITULO_NA_REMESSA
                 if c.nome == "data_de_vencimento")
    linhas = [x for x in texto.replace("\r\n", "\n").split("\n") if x.strip()]
    linhas = [(x[:campo.inicio - 1] + PA.SEM_VENCIMENTO + x[campo.fim:])
              if x[:1] == "1" else x for x in linhas]
    sem = "\r\n".join(linhas).encode("latin-1")

    visto = PRM.conferir(con, sem)
    assert visto["aceitos"] == 1, visto["lotes"][0]["titulos"][0]["faltas"]
    assert receber(con, sem)["recebidos"] == 1


# --------------------------------------------------- o aviso, e nao recusa


def test_titulo_vivo_com_o_mesmo_nosso_numero_vira_AVISO(con):
    # O nosso numero se repete de verdade: 53 grupos e 111 titulos no acervo
    # desta casa. Pode ser reapresentacao legitima, e pode ser engano — quem
    # decide e quem esta no balcao.
    receber(con)
    visto = PRM.conferir(con, outra_remessa())
    lote = visto["lotes"][0]
    assert lote["avisados"] == 1
    assert lote["titulos"][0]["aceito"] is True
    assert lote["titulos"][0]["iguais"][0]["situacao"] == "APONTADO"


def test_reapresentacao_entra_como_titulo_novo(con):
    # A CHAVE DE ORIGEM E A POSICAO NO LOTE, e nao o nosso numero: chavear
    # pelo nosso numero faria a segunda apresentacao sumir dentro da primeira,
    # calada.
    receber(con)
    r = receber(con, outra_remessa())   # outro lote, o mesmo titulo dentro
    assert r["recebidos"] == 1
    assert con.execute("SELECT COUNT(*) c FROM pt_titulos").fetchone()["c"] == 2
    chaves = [x[0] for x in con.execute(
        "SELECT origem_chave FROM pt_titulos ORDER BY id")]
    assert chaves == [f"CRA:{r['remessas'][0] - 1}:1", f"CRA:{r['remessas'][0]}:1"]


# ------------------------------------------------------------ consultas


def test_a_lista_traz_o_lote_com_a_confirmacao_do_lado(con):
    r = receber(con)
    linhas = PRM.listar(con)
    assert len(linhas) == 1
    assert linhas[0]["id"] == r["remessas"][0]
    assert linhas[0]["recebidos"] == 1 and linhas[0]["apontados"] == 1
    assert linhas[0]["confirmacao_nome"].startswith("C001")   # FEBRABAN, 13/10/2026


def test_o_arquivo_que_chegou_fica_guardado_inteiro(con):
    # Quando a Central reclamar de um titulo, e este teor que se le. E a mesma
    # regra do retorno.
    r = receber(con)
    linha = PRM.remessa(con, r["remessas"][0])
    assert PA.ler(linha["conteudo"]).tipo == PRM.TIPO_DA_REMESSA
    assert linha["hash_arquivo"] == PRM.hash_remessa(EXEMPLO)


def test_o_lote_nao_sela_e_nao_cobra(con):
    # Selar cinquenta titulos e cinquenta chamadas de rede de 20 s dentro de
    # um BEGIN IMMEDIATE: a casa inteira ficaria esperando o lote. Eles entram
    # e aparecem nas telas do outro lado.
    receber(con)
    ato = con.execute("SELECT * FROM pt_atos").fetchone()
    assert ato["selo"] is None
    assert ato["lancamento_id"] is None
    # E a tela do outro lado que os mostra, e ela ja existe.
    assert AS.atos_sem_selo(con, "pt_atos")


def test_remessa_de_apresentante_NOVO_entra(con):
    """A que quase nao entrou, e o defeito era meu.

    `_montar_saida` exigia a letra da posicao 566 dos tres arquivos de saida,
    porque e a mesma funcao para os tres. So que `reservado_566` existe no
    layout do RETORNO e em mais nenhum — na confirmacao aquela posicao cai
    dentro de `reservado_546`, medido como zeros e brancos nos 343 registros.

    Com a exigencia, a remessa de um apresentante NOVO nao podia ser recebida:
    a confirmacao pedia uma letra que so se aprende num retorno anterior, e
    apresentante novo nao tem retorno anterior. Um campo que nem e escrito
    travaria o balcao.
    """
    novo = "ZZZ"
    assert PA.marca_do_apresentante(novo) is None
    texto = EXEMPLO.decode("latin-1")
    campo = next(c for c in PA.CABECALHO if c.nome == "codigo_do_apresentante")
    linhas = [x for x in texto.replace("\r\n", "\n").split("\n") if x.strip()]
    linhas = [x[:campo.inicio - 1] + novo.ljust(campo.tamanho)[:campo.tamanho]
              + x[campo.fim:] for x in linhas]

    r = receber(con, "\r\n".join(linhas).encode("latin-1"))
    assert r["recebidos"] == 1
    assert len(r["confirmacoes"]) == 1
    volta = PA.ler(con.execute("SELECT conteudo FROM pt_retornos WHERE id=?",
                               (r["confirmacoes"][0],)).fetchone()[0])
    assert volta.achados == []


def test_dois_lotes_iguais_no_mesmo_arquivo_sao_recusados(con):
    # Nos 197 arquivos reais isso nunca aconteceu — mas a trava do banco
    # estouraria com IntegrityError, que vira tela branca. Erro de regra se
    # diz em portugues.
    duplo = (EXEMPLO.decode("latin-1").replace("\r\n", "\n").strip() + "\n"
             + EXEMPLO.decode("latin-1").replace("\r\n", "\n").strip())
    with pytest.raises(PRM.RemessaError) as erro:
        receber(con, duplo.encode("latin-1"))
    assert "idênticos" in str(erro.value)
    assert con.execute("SELECT COUNT(*) c FROM pt_remessas").fetchone()["c"] == 0
