"""
Testes do ARQUIVO DE DESISTENCIA da CRA — o quinto layout.

O QUE ELES CONFEREM

    Que o LAYOUT MEDIDO le os quatro arquivos reais sem achado nenhum. Sao
    dois apresentantes e quatro anos — de 26/08/2022 a 05/08/2026 —, e o de
    2026 e o que fechou a medicao: o numero do titulo dele, `NF-74654-/1`, tem
    forma inconfundivel e prende a fronteira do campo.

    Que A DESISTENCIA NAO SE APLICA SOZINHA. Cada titulo e uma escolha, e o
    que nao foi marcado nao entra. Desistencia lida errado e protesto lavrado
    contra quem o credor desistiu de protestar.

    Que O PROTOCOLO E A CHAVE, e que titulo que esta casa nao tem e DITO, e
    nao ignorado em silencio.

    Que a SOMA DO RODAPE e a conferencia que vale — ela fecha nos quatro —, e
    que a contagem que ninguem explicou AVISA em vez de recusar.

    E que aplicar em DOIS TURNOS funciona: metade de manha, o resto ao
    meio-dia, com o arquivo gravado uma vez so.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto as PT
import protesto_desistencia as DS
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-08-26T09:00:00"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}

EXEMPLO = (Path(__file__).parent / "cra_desistencia_exemplo.txt").read_bytes()
REMESSA = (Path(__file__).parent / "cra_remessa_exemplo.txt").read_bytes()


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    init_pt_schema(c)
    yield c
    c.close()


def titulo(con, *, protocolo: str, numero="NF-74654-/1", situacao=None) -> int:
    tid = PT.cadastrar_titulo(con, {
        "apresentante_codigo": "001", "apresentante_nome": "BANCO DO BRASIL",
        "especie": "DMI", "numero_titulo": numero, "nosso_numero": f"N{numero}",
        "data_emissao": "2026-07-01", "data_vencimento": "2026-08-01",
        "valor": "221.00", "saldo": "221.00", "praca_protesto": "CIDADE EXEMPLO",
        "cedente": {"nome": "LOJA CENTRAL", "documento": "00000017000149"},
        "devedores": [{"nome": "M M FERREIRA BEZERRIL MELLO",
                       "CNPJ": "00000017000149",
                       "enderecos": [{"endereco": "RUA GRANDE, 10",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }, origem="CRA", origem_chave=f"lote:{numero}", agora=AGORA)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    con.execute("UPDATE pt_titulos SET protocolo=? WHERE id=?",
                (protocolo, tid))
    if situacao:
        con.execute("UPDATE pt_titulos SET situacao=? WHERE id=?",
                    (situacao, tid))
    return tid


# ------------------------------------------------------------- o layout


def test_o_exemplo_real_le_sem_achado_nenhum():
    a = DS.ler(EXEMPLO)
    assert a["cabecalho"]["apresentante_codigo"] == "001"
    assert a["cabecalho"]["apresentante_nome"] == "BANCO DO BRASIL SA"
    assert a["cabecalho"]["dia"] == "2026-08-05"
    assert a["cabecalho"]["quantidade_de_titulos"] == 1
    assert a["pracas"] == [{"praca": "03", "quantidade_de_titulos": 1,
                            "cidade_ibge": "2905500", "sequencial": 2}]
    assert a["achados"] == []

    t = a["titulos"][0]
    assert t["protocolo"] == "2608030003"
    assert t["data"] == "2026-08-04"
    # O NUMERO DO TITULO DE 2026 foi o que fechou a medição: `NF-74654-/1` tem
    # forma inconfundível e prende a fronteira do campo.
    assert t["numero_do_titulo"] == "NF-74654-/1"
    assert t["devedor_nome"] == "M M FERREIRA BEZERRIL MELLO"
    assert t["valor_centavos"] == 22100
    assert t["cidade_ibge"] == "2905500"


def test_a_soma_do_rodape_fecha():
    # É a conferência que vale, e é o que pega arquivo truncado — que é como
    # um arquivo estraga na prática.
    a = DS.ler(EXEMPLO)
    assert a["rodape"]["soma_centavos"] == sum(
        t["valor_centavos"] for t in a["titulos"])


def test_os_reservados_se_leem_como_TEXTO():
    # Campo sem nome não se interpreta — foi essa regra que evitou quatro
    # defeitos no arquivo de 600 posições.
    t = DS.ler(EXEMPLO)["titulos"][0]
    assert t["reservado_90"] == "S"
    assert t["reservado_91"] == "0" * 12
    assert isinstance(t["reservado_117"], str)


def test_soma_que_nao_fecha_vira_achado():
    texto = DS.normalizar(EXEMPLO)
    linhas = texto.split("\n")
    rodape = linhas[-1]
    linhas[-1] = rodape[:62] + "00000000099999" + rodape[76:]
    achados = DS.ler("\n".join(linhas))["achados"]
    assert any("rodapé declara" in a for a in achados)


def test_a_contagem_que_ninguem_explicou_AVISA_e_nao_recusa():
    """Nos quatro arquivos medidos ela é o dobro dos títulos, e o que ela
    conta de fato nunca ficou estabelecido.

    Recusar o arquivo por causa dela seria travar o balcão por uma hipótese —
    e o rodapé da remessa já enganou uma medição inteira desta casa por ter
    sido lido como contador de títulos quando contava registros.
    """
    texto = DS.normalizar(EXEMPLO)
    linhas = texto.split("\n")
    rodape = linhas[-1]
    linhas[-1] = rodape[:57] + "00009" + rodape[62:]
    a = DS.ler("\n".join(linhas))
    assert any("dobro dos títulos" in x for x in a["achados"])
    assert a["titulos"]                       # e o arquivo continua legível


def test_arquivo_de_600_posicoes_e_recusado_dizendo_onde_abrir():
    # AS PASTAS MENTEM: a própria pasta `desistencia` do Proton Drive guarda um
    # arquivo de 600. A mensagem tem de dizer onde ele se abre.
    with pytest.raises(DS.DesistenciaError) as erro:
        DS.ler(REMESSA)
    assert "600" in str(erro.value)
    assert "remessa da CRA" in str(erro.value)


def test_arquivo_vazio_e_recusado():
    with pytest.raises(DS.DesistenciaError):
        DS.ler(b"")


def test_crlf_e_lf_sao_o_mesmo_arquivo():
    outro = EXEMPLO.decode("latin-1").replace("\r\n", "\n").encode("latin-1")
    assert DS.hash_arquivo(outro) == DS.hash_arquivo(EXEMPLO)


# ----------------------------------------------------------- conferir


def test_conferir_acha_o_titulo_pelo_protocolo_e_NAO_GRAVA(con):
    titulo(con, protocolo="2608030003")
    v = DS.conferir(con, EXEMPLO)
    assert v["quantidade"] == 1 and v["cabem"] == 1
    assert v["titulos"][0]["situacao"] == "APONTADO"
    assert v["titulos"][0]["cabe"] is True
    assert v["titulos"][0]["titulo"]["numero_titulo"] == "NF-74654-/1"
    assert con.execute(
        "SELECT COUNT(*) c FROM pt_desistencias").fetchone()["c"] == 0


def test_titulo_com_dois_devedores_mostra_o_primeiro_cadastrado(con):
    """RESSALVA DO L012R: `ORDER BY t.id LIMIT 1` sobre o JOIN dos devedores
    deixava ao PostgreSQL escolher QUAL devedor a conferência mostra. O SQLite
    dava o primeiro cadastrado (o `rowid`); agora o desempate é `d.id`."""
    tid = titulo(con, protocolo="2608030003")
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
    v = DS.conferir(con, EXEMPLO)
    assert v["titulos"][0]["titulo"]["devedor_nome"] == primeiro["nome"]


def test_titulo_que_a_casa_nao_tem_e_DITO(con):
    # Ignorar em silêncio faria o oficial achar que aplicou tudo.
    v = DS.conferir(con, EXEMPLO)
    assert v["nao_achados"] == 1 and v["cabem"] == 0
    linha = v["titulos"][0]
    assert linha["situacao"] == "SEM TÍTULO"
    assert "2608030003" in linha["porque"]


def test_titulo_ja_protestado_nao_cabe_e_a_tela_diz_por_que(con):
    titulo(con, protocolo="2608030003", situacao="PROTESTADO")
    v = DS.conferir(con, EXEMPLO)
    assert v["nao_cabem"] == 1 and v["cabem"] == 0
    assert "cancelamento" in v["titulos"][0]["porque"]


# ------------------------------------------------------------ aplicar


def test_aplicar_lanca_a_desistencia_do_titulo_marcado(con):
    tid = titulo(con, protocolo="2608030003")
    r = DS.aplicar(con, EXEMPLO, protocolos=["2608030003"], agora=AGORA,
                   nome_arquivo="DP0010508.261", usuario="tabeliao")
    assert len(r["aplicados"]) == 1 and not r["recusados"]

    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "DESISTIDO"
    ato = con.execute(
        "SELECT * FROM pt_atos WHERE tipo='DESISTENCIA'").fetchone()
    assert ato["origem"] == "CRA"
    assert ato["desistencia_id"] == r["desistencia_id"]
    # O MOTIVO DIZ DE ONDE VEIO: quando o apresentante ligar, é essa a resposta.
    assert "001" in ato["detalhe_json"] and "2026-08-05" in ato["detalhe_json"]


def test_o_que_nao_foi_marcado_NAO_entra(con):
    # A desistência não se aplica sozinha: cada título é uma escolha.
    titulo(con, protocolo="2608030003")
    with pytest.raises(DS.DesistenciaError) as erro:
        DS.aplicar(con, EXEMPLO, protocolos=[], agora=AGORA)
    assert "Nenhum título foi marcado" in str(erro.value)
    assert con.execute("SELECT situacao FROM pt_titulos").fetchone()[0] == "APONTADO"


def test_marcar_titulo_que_nao_cabe_devolve_o_motivo_e_nao_estoura(con):
    titulo(con, protocolo="2608030003", situacao="PROTESTADO")
    r = DS.aplicar(con, EXEMPLO, protocolos=["2608030003"], agora=AGORA)
    assert not r["aplicados"] and len(r["recusados"]) == 1
    assert "cancelamento" in r["recusados"][0]["porque"]


def test_o_arquivo_fica_guardado_inteiro_e_uma_vez_so(con):
    # Quando o apresentante ligar perguntando, é este teor que se lê.
    titulo(con, protocolo="2608030003")
    r = DS.aplicar(con, EXEMPLO, protocolos=["2608030003"], agora=AGORA)
    linha = DS.desistencia(con, r["desistencia_id"])
    assert linha["hash_arquivo"] == DS.hash_arquivo(EXEMPLO)
    assert DS.ler(linha["conteudo"])["titulos"][0]["protocolo"] == "2608030003"
    assert linha["titulos"] == 1 and linha["aplicados"] == 1

    # Subir de novo NÃO cria outro registro — e não faz nada, porque o domínio
    # recusa desistir de título já desistido.
    de_novo = DS.aplicar(con, EXEMPLO, protocolos=["2608030003"], agora=AGORA)
    assert de_novo["desistencia_id"] == r["desistencia_id"]
    assert not de_novo["aplicados"] and len(de_novo["recusados"]) == 1
    assert con.execute(
        "SELECT COUNT(*) c FROM pt_desistencias").fetchone()["c"] == 1


def test_aplicar_em_DOIS_TURNOS(con):
    """O caso comum do roteiro: metade de manhã, o resto ao meio-dia.

    É por isso que este módulo não recusa arquivo repetido como a remessa faz.
    Lá, receber duas vezes apontaria tudo de novo; aqui, aplicar o resto é
    exatamente o que se espera do segundo turno.
    """
    dois = _com_dois_titulos()
    titulo(con, protocolo="2608030003", numero="NF-74654-/1")
    titulo(con, protocolo="2608030004", numero="NF-74655-/1")

    manha = DS.aplicar(con, dois, protocolos=["2608030003"], agora=AGORA)
    assert len(manha["aplicados"]) == 1
    assert DS.desistencia(con, manha["desistencia_id"])["aplicados"] == 1

    meio_dia = DS.aplicar(con, dois, protocolos=["2608030004"], agora=AGORA)
    assert meio_dia["desistencia_id"] == manha["desistencia_id"]
    assert len(meio_dia["aplicados"]) == 1
    assert DS.desistencia(con, manha["desistencia_id"])["aplicados"] == 2
    assert len(DS.atos_da_desistencia(con, manha["desistencia_id"])) == 2


def test_a_lista_traz_os_arquivos_recebidos(con):
    titulo(con, protocolo="2608030003")
    DS.aplicar(con, EXEMPLO, protocolos=["2608030003"], agora=AGORA,
               nome_arquivo="DP0010508.261")
    linhas = DS.listar(con)
    assert len(linhas) == 1
    assert linhas[0]["nome_arquivo"] == "DP0010508.261"
    assert linhas[0]["apresentante_codigo"] == "001"
    assert linhas[0]["aplicados"] == 1


def _com_dois_titulos() -> bytes:
    """O exemplo com um segundo título, para o caso dos dois turnos."""
    linhas = DS.normalizar(EXEMPLO).split("\n")
    titulo_1 = linhas[2]
    titulo_2 = ("2" + "2608030004" + titulo_1[11:19] + "NF-74655-/1"
                + titulo_1[30:122] + "00004")
    assert len(titulo_2) == DS.TAMANHO_DO_REGISTRO, len(titulo_2)
    cabecalho = linhas[0][:57] + "00002" + "00002" + linhas[0][67:]
    rodape = linhas[-1]
    soma = f"{22100 * 2:014d}"
    rodape = rodape[:57] + "00004" + soma + rodape[76:]
    return "\r\n".join([cabecalho, linhas[1], titulo_1, titulo_2,
                        linhas[3], rodape]).encode("latin-1")


# ------------------------------------- a prova contra outra serventia
#
# O layout foi MEDIDO em quatro arquivos desta casa e PROVADO contra 384 de
# outra: em 26/08/2026 o oficial trouxe o acervo da CRA da serventia em que
# trabalhou, em Sergipe. Os 384 leem sem um unico achado, e a soma do rodape
# fecha nos 384.
#
# Esta fixture e o mais rico deles — 22 titulos, apresentante Itau, 2019 —, e
# fica aqui como guarda: o layout tem de continuar lendo o que ja leu.

SERGIPE = (Path(__file__).parent / "cra_desistencia_sergipe.txt").read_bytes()


def test_o_layout_le_o_arquivo_de_outra_serventia():
    a = DS.ler(SERGIPE)
    assert a["achados"] == []
    assert len(a["titulos"]) == 22
    assert a["cabecalho"]["apresentante_codigo"] == "341"
    assert a["cabecalho"]["dia"] == "2019-06-17"
    # A soma do rodapé fecha — é a conferência que vale.
    assert a["rodape"]["soma_centavos"] == sum(
        t["valor_centavos"] for t in a["titulos"]) == 1052677
    # E a contagem é o dobro dos títulos, como nos 388.
    assert a["rodape"]["contagem"] == 44


def test_quatro_digitos_antes_do_nome_sao_NOME_e_nao_campo():
    """A suspeita que a amostra grande levantou, e resolveu.

    Neste arquivo o apresentante vem como `341` + `2861ITAU UNIBANCO SA`, e os
    quatro dígitos colados parecem um campo que a leitura juntou ao nome.

    Não são: medido nos 384 de Sergipe, 315 trazem o nome direto e 69 trazem os
    quatro dígitos — e **o mesmo apresentante 341 aparece das duas formas**. Se
    fosse campo, seria sempre preenchido ou sempre vazio para o mesmo
    apresentante. É conteúdo do nome.
    """
    a = DS.ler(SERGIPE)
    assert a["cabecalho"]["apresentante_nome"].startswith("2861ITAU")
    assert a["cabecalho"]["apresentante_codigo"] == "341"


def test_uma_praca_por_arquivo_e_o_que_acontece_na_pratica():
    # 384 de 384 têm uma praça só, e 317 têm um título só. O layout comporta
    # mais, e a tela não se desenha em torno do que não acontece.
    a = DS.ler(SERGIPE)
    assert len(a["pracas"]) == 1
    assert all(t["praca"] == a["pracas"][0]["praca"] for t in a["titulos"])
