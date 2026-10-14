"""
Cadastro de parte: aproveitar a ficha de firma ou cadastrar do zero.

O PROBLEMA QUE ISTO RESOLVE
    A serventia tem 4.061 cartoes de autografo com o cadastro completo — nome,
    CPF, RG, filiacao, estado civil, profissao, endereco. Quando alguem
    comparece para uma escritura ou uma procuracao, na esmagadora maioria das
    vezes ja assinou aqui antes. Redigitar tudo e trabalho perdido e, pior,
    e fonte de divergencia: o mesmo Jose vira "JOSE", "José" e "Jose da Silva"
    em tres atos, e o indicador pessoal deixa de encontra-lo.

    Entao o cadastro de parte tem dois caminhos, e o balcao escolhe:

      APROVEITAR   busca no cartao de autografo e traz tudo preenchido, com a
                   assinatura digitalizada ao lado para conferencia visual
      NOVO         cadastra do zero, e — se o operador quiser — ja abre o
                   cartao de autografo junto, para a proxima vez ser o caso 1

A BUSCA
    Por nome sem acento e sem caixa, ou por CPF/CNPJ com ou sem pontuacao. O
    acervo tem 4.061 cartoes: procurar por igualdade exata nao serve, e
    procurar por LIKE em qualquer posicao devolve lixo. Aqui o nome casa por
    prefixo de palavra — quem digita "silva" acha "JOSE DA SILVA".

O QUE ELE NAO FAZ
    Nao decide se a pessoa e quem diz ser. A conferencia de identidade e a
    comparacao da assinatura sao do tabeliao; o sistema traz o cartao, mostra
    a assinatura e avisa quando o cartao esta bloqueado.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from typing import Any

import cpf_cnpj as CPFDOC

# Quantos candidatos a busca devolve. Mais do que isto nao se le na tela, e
# quem tem mais de vinte homonimos precisa refinar a busca, nao rolar a lista.
LIMITE_BUSCA = 20

# Campos que a ficha de firma entrega prontos para o cadastro da parte.
CAMPOS_HERDADOS = (
    "nome", "documento", "tipo_pessoa", "rg", "rg_orgao", "rg_uf",
    "nascimento", "nacionalidade", "naturalidade", "estado_civil", "conjuge",
    "profissao", "pai", "mae", "endereco", "endereco_numero",
    "endereco_complemento", "bairro", "cidade", "uf", "cep",
    "telefone", "celular", "email",
)


def normalizar(texto: Any) -> str:
    """Sem acento, sem caixa, sem espaco repetido."""
    s = str(texto or "").strip()
    if not s:
        return ""
    t = unicodedata.normalize("NFD", s.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def so_digitos(valor: Any) -> str:
    return CPFDOC.so_digitos(valor)


def documento_valido(valor: Any) -> bool | None:
    """Confere o digito verificador do CPF ou do CNPJ.

    Devolve None quando nao ha documento — ausencia nao e erro.
    Delegado ao helper central `cpf_cnpj`.
    """
    return CPFDOC.documento_valido(valor)



def buscar_cartoes(con: sqlite3.Connection, termo: str,
                   limite: int = LIMITE_BUSCA,
                   incluir_bloqueados: bool = True) -> list[dict]:
    """Procura no cartao de autografo por nome ou por documento.

    O documento tem prioridade: quem digita um CPF inteiro quer aquela pessoa,
    nao uma lista de parecidos.
    """
    termo = (termo or "").strip()
    if len(termo) < 3:
        return []

    con.row_factory = sqlite3.Row
    digitos = so_digitos(termo)
    onde, params = [], []

    if len(digitos) >= 11:
        onde.append("c.documento = ?")
        params.append(digitos)
    else:
        alvo = normalizar(termo)
        # Prefixo de palavra: 'silva' acha 'JOSE DA SILVA', e nao acha
        # 'SILVANIA' por acidente de substring no meio de outra palavra.
        onde.append("(c.nome_norm LIKE ? OR c.nome_norm LIKE ?)")
        params += [f"{alvo}%", f"% {alvo}%"]
        if digitos:
            onde.append("c.documento LIKE ?")
            params.append(f"%{digitos}%")
            onde = [f"({' OR '.join(onde)})"]

    if not incluir_bloqueados:
        onde.append("c.bloqueado = 0")
    filtro = " AND ".join(onde)

    linhas = con.execute(f"""
        SELECT c.*,
               (SELECT COUNT(*) FROM nt_cartao_imagens i WHERE i.cartao_id = c.id) imagens,
               (SELECT i.id FROM nt_cartao_imagens i WHERE i.cartao_id = c.id
                 ORDER BY i.favorita DESC, i.ordem LIMIT 1) imagem_id
        FROM nt_cartoes c
        WHERE {filtro}
        ORDER BY c.ativo DESC, c.bloqueado, c.nome_norm
        LIMIT ?""", params + [limite]).fetchall()
    return [dict(r) for r in linhas]


def dados_para_parte(cartao: dict | sqlite3.Row) -> dict:
    """Traduz o cartao de autografo em campos de parte, prontos para o ato."""
    c = dict(cartao)
    dados = {campo: c.get(campo) for campo in CAMPOS_HERDADOS}
    dados["cartao_id"] = c.get("id")
    dados["nome_norm"] = normalizar(c.get("nome"))
    # Endereco completo numa linha so, que e como entra na qualificacao do ato.
    partes = [c.get("endereco"), c.get("endereco_numero"),
              c.get("endereco_complemento"), c.get("bairro")]
    lugar = ", ".join(p for p in partes if p)
    cidade = ", ".join(p for p in (c.get("cidade"), c.get("uf")) if p)
    dados["endereco_completo"] = " — ".join(p for p in (lugar, cidade) if p) or None
    return dados


def avisos_do_cartao(cartao: dict | sqlite3.Row) -> list[str]:
    """O que o balcao precisa ver antes de usar este cartao.

    Nao impede nada: quem decide e o tabeliao. Mas cartao bloqueado usado sem
    ninguem perceber e como nao ter bloqueado.
    """
    c = dict(cartao)
    avisos: list[str] = []
    if c.get("bloqueado"):
        motivo = (c.get("motivo_bloqueio") or "").strip()
        avisos.append("Cartão BLOQUEADO." + (f" Motivo: {motivo}" if motivo else ""))
    if not c.get("ativo"):
        avisos.append("Cartão inativo.")
    if c.get("pessoa_exposta"):
        avisos.append("Pessoa politicamente exposta — Provimento CNJ 88/2019, "
                      "art. 20: o atendimento exige diligência reforçada.")
    if c.get("restricao_terrorismo"):
        avisos.append("Restrição por vínculo com terrorismo ou financiamento. "
                      "Lei 13.810/2019: comunicar imediatamente.")
    if not (c.get("documento") or "").strip():
        avisos.append("Cartão sem CPF/CNPJ cadastrado.")
    elif documento_valido(c.get("documento")) is False:
        avisos.append("O CPF/CNPJ deste cartão não passa na conferência do "
                      "dígito verificador — confira o documento original.")
    if c.get("somente_autenticidade"):
        avisos.append("Este cartão só admite reconhecimento por autenticidade.")
    return avisos


def campos_faltantes(dados: dict, para: str = "ATO") -> list[str]:
    """O que ainda falta para qualificar a parte no ato.

    A qualificacao completa e exigencia do art. 215, § 1º, do Codigo Civil:
    nome, nacionalidade, estado civil, profissao, domicilio e documento. Sem
    isso a escritura nasce com defeito.
    """
    exigidos = {
        "nome": "nome", "documento": "CPF ou CNPJ",
        "nacionalidade": "nacionalidade", "estado_civil": "estado civil",
        "profissao": "profissão", "endereco": "endereço",
    }
    if para == "RECONHECIMENTO":
        exigidos = {"nome": "nome", "documento": "CPF ou CNPJ"}
    return [rotulo for campo, rotulo in exigidos.items()
            if not str(dados.get(campo) or "").strip()]


def criar_cartao(con: sqlite3.Connection, dados: dict, agora: str,
                 usuario: str | None = None) -> int:
    """Abre um cartao de autografo novo e devolve o id.

    Serve tanto para o cadastro direto no balcao quanto para o caso em que a
    parte foi digitada do zero num ato e o operador pediu para guardar a ficha.
    """
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise ValueError("O cartão precisa de nome.")
    documento = so_digitos(dados.get("documento")) or None
    campos = {
        "nome": nome, "nome_norm": normalizar(nome),
        "tipo_pessoa": (dados.get("tipo_pessoa") or "F")[:1].upper(),
        "documento": documento,
        "pessoa_exposta": 1 if dados.get("pessoa_exposta") else 0,
        "restricao_terrorismo": 1 if dados.get("restricao_terrorismo") else 0,
        "ativo": 1, "abertura": dados.get("abertura") or agora[:10],
        "origem": "MANUAL", "criado_em": agora,
    }
    for campo in ("rg", "rg_orgao", "rg_uf", "nascimento", "sexo",
                  "nacionalidade", "naturalidade", "estado_civil", "conjuge",
                  "profissao", "pai", "mae", "endereco", "endereco_numero",
                  "endereco_complemento", "bairro", "cidade", "uf",
                  "local_trabalho", "endereco_trabalho", "como_assina",
                  "observacao"):
        valor = (dados.get(campo) or "").strip() if dados.get(campo) else None
        if valor:
            campos[campo] = valor
    for campo in ("cep", "telefone", "celular"):
        valor = so_digitos(dados.get(campo))
        if valor:
            campos[campo] = valor
    email = (dados.get("email") or "").strip()
    if email:
        campos["email"] = email

    colunas = ", ".join(campos)
    marcas = ", ".join("?" for _ in campos)
    cur = con.execute(f"INSERT INTO nt_cartoes ({colunas}) VALUES ({marcas})",
                      list(campos.values()))
    return int(cur.lastrowid)


def possivel_duplicata(con: sqlite3.Connection, nome: str,
                       documento: Any = None) -> list[dict]:
    """Antes de abrir cartao novo, ver se ja nao existe um.

    Cartao duplicado e o comeco de um acervo que nao se consulta: metade dos
    atos aponta para uma ficha e metade para a outra, e nenhuma das duas conta
    a historia inteira da pessoa.
    """
    con.row_factory = sqlite3.Row
    digitos = so_digitos(documento)
    if digitos:
        achados = con.execute(
            "SELECT * FROM nt_cartoes WHERE documento = ? LIMIT 5", (digitos,)).fetchall()
        if achados:
            return [dict(r) for r in achados]
    alvo = normalizar(nome)
    if len(alvo) < 5:
        return []
    return [dict(r) for r in con.execute(
        "SELECT * FROM nt_cartoes WHERE nome_norm = ? LIMIT 5", (alvo,)).fetchall()]
