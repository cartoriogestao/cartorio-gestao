"""Papéis do catálogo — Registro Civil das Pessoas Naturais."""
from __future__ import annotations

PAPEIS: tuple[dict, ...] = (
    {'chave': 'RC_TERMO_NASCIMENTO', 'atribuicao': 'Registro Civil das Pessoas Naturais', 'nome': 'Termo de nascimento', 'padrao': ('rc_modelos_do_livro', 'TERMO_NASCIMENTO'), 'formato': 'CHAVES', 'explica': 'O texto que se escreve no Livro A — e no C-Auxiliar, para o natimorto. É o papel que o declarante lê e assina.'},
    {'chave': 'RC_TERMO_CASAMENTO', 'atribuicao': 'Registro Civil das Pessoas Naturais', 'nome': 'Termo de casamento', 'padrao': ('rc_modelos_do_livro', 'TERMO_CASAMENTO'), 'formato': 'CHAVES', 'explica': 'O texto do Livro B — e do B-Auxiliar, no religioso com efeito civil.'},
    {'chave': 'RC_TERMO_OBITO', 'atribuicao': 'Registro Civil das Pessoas Naturais', 'nome': 'Termo de óbito', 'padrao': ('rc_modelos_do_livro', 'TERMO_OBITO'), 'formato': 'CHAVES', 'explica': 'O texto do Livro C.'},
    {'chave': 'RC_TERMO_LIVRO_E', 'atribuicao': 'Registro Civil das Pessoas Naturais', 'nome': 'Termo do Livro E', 'padrao': ('rc_modelos_do_livro', 'TERMO_LIVRO_E'), 'formato': 'CHAVES', 'explica': 'O texto compartilhado do Livro E — ausência, interdição, tutela, emancipação, união estável, opção de nacionalidade e outro. Mesmo modelo; o título do ato muda pela espécie.'},
)
