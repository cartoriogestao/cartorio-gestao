# Pacote 3.6.69 — 07/09/2026

Empacota no mesmo ATUALIZAR_SISTEMA:

## Firmas / ficha de autógrafo (notas_web.py)
- Selo de abertura + QR (PNG, padrão etiqueta/certidão) na ficha ODT
- Layout anverso: linhas de assinatura na largura útil da lauda (16 cm)
- Espaço vertical um pouco maior para autógrafos
- Testes: tests/test_cartao_ficha.py

## Modelos (Claude / teste cart)
- modelos_elementos*.py / modelos_da_casa.py / modelos_web.py
- Registrados em app.py / database.py
- Templates: modelos.html, modelos_atribuicao.html, RCPN modelos
- Testes: test_modelos_elementos*.py, test_modelos_da_casa.py

## Como subir
Rodar como Admin: SERVIDOR\ATUALIZAR_SISTEMA.cmd
Copia *.py, templates, static, pasta modelos, VERSAO.txt.
Não rodar sem ordem explícita do oficial.