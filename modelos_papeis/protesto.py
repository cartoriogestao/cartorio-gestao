"""Papéis do catálogo — Protesto."""
from __future__ import annotations

PAPEIS: tuple[dict, ...] = (
    {'chave': 'PT_TERMO_PROTESTO', 'atribuicao': 'Protesto', 'nome': 'Termo do registro de protesto', 'padrao': ('protesto_termo', 'TERMO_DO_PROTESTO'), 'formato': 'CHAVES', 'explica': 'O texto que se escreve no Livro de Registro de Protestos. Monta-se de frases inteiras: {base} e {posteriori} são suas; {edital} o sistema monta dos fatos do título — se a intimação foi por edital, em que data e por qual motivo.'},
    {'chave': 'PT_INSTRUMENTO_PROTESTO', 'atribuicao': 'Protesto', 'nome': 'Instrumento de protesto', 'padrao': ('protesto_instrumento', 'INSTRUMENTO_DE_PROTESTO'), 'formato': 'CHAVES', 'explica': 'O papel que se entrega ao apresentante (art. 20 da Lei 9.492/1997). {serventia}, {praca} e {motivo} saem do titulo; {copia} o sistema monta do que existe — se ha imagem do titulo arquivada, ele escreve a mencao do § unico do art. 22, e se nao ha, diz que a dispensa nao se aplica; {intimacao} e a certidao do inciso IV, que diz se foi por edital ou em maos.'},
    {'chave': 'PT_CERTIDAO_NEGATIVA', 'atribuicao': 'Protesto', 'nome': 'Certidão negativa de protesto', 'padrao': ('protesto_certidao', 'MODELO_CERTIDAO_NEGATIVA'), 'formato': 'CHAVES', 'explica': 'Certifica que a busca não encontrou protestos no período.'},
    {'chave': 'PT_CERTIDAO_POSITIVA', 'atribuicao': 'Protesto', 'nome': 'Certidão positiva de protesto', 'padrao': ('protesto_certidao', 'MODELO_CERTIDAO_POSITIVA'), 'formato': 'CHAVES', 'explica': 'Certifica os protestos encontrados e seus dados.'},
    {'chave': 'PT_CERTIDAO_CANCELAMENTO', 'atribuicao': 'Protesto', 'nome': 'Certidão de protestos cancelados', 'padrao': ('protesto_certidao', 'MODELO_CERTIDAO_CANCELAMENTO'), 'formato': 'CHAVES', 'explica': 'Certifica protestos encontrados e as respectivas baixas e cancelamentos.'},
)
