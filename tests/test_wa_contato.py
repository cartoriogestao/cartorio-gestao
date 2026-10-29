"""QUEM É A PESSOA DO WHATSAPP (29/10/2026) — a régua que casa o número da
conversa com o telefone do cartão de firma e do protocolo (`wa_contato`).
Números fictícios."""
import wa_contato as C


def test_o_numero_do_whatsapp_vira_ddd_e_oito_digitos():
    assert C._chave("5511987654321") == ("11", "87654321")
    # o WhatsApp às vezes guarda sem o 9 da frente
    assert C._chave("551187654321") == ("11", "87654321")
    assert C._chave("16315551181") is None      # número de fora do Brasil
    assert C._chave("") is None


def test_mesmo_ddd_casa_e_ddd_diferente_nao():
    assert C._casa("(11) 98765-4321", "11", "87654321") == ""
    assert C._casa("11 8765-4321", "11", "87654321") == ""
    assert C._casa("(21) 98765-4321", "11", "87654321") is None


def test_sem_ddd_no_cadastro_casa_e_diz_que_nao_tinha_ddd():
    assert C._casa("98765-4321", "11", "87654321") == "sem DDD no cadastro"
    assert C._casa("987654321", "11", "87654321") == "sem DDD no cadastro"


def test_final_diferente_ou_curto_nao_casa():
    assert C._casa("98765-4320", "11", "87654321") is None
    assert C._casa("4321", "11", "87654321") is None
    assert C._casa(None, "11", "87654321") is None
    assert C._casa("...", "11", "87654321") is None
