# Tarefas pendentes — modal e faixa (sandbox, v3.6.261+)

## Comportamento

- **Mesmas regras de sessão/dia** do modal de avisos v2 (`nu_avisos_overlay_fechado` / `nu_avisos_overlay_data`, modo teste no sandbox).
- **Modal** (`_nu_avisos_modal.html`): avisos como antes; bloco extra de tarefas **só contagem + link**:
  - Texto: **«Você possui N tarefa(s) pendente(s)»** (N=1 → singular; N>1 → plural).
  - Contagem: vistas **Comigo** + **Pediram minha resposta** via `tarefa_processo.contagem_pendentes_notificacao` (usa `contagem_por_vista`).
  - Link **Ver todas** → `/tarefas` (classe `nu-avisos-link-lista`).
- **ADMIN**: bloco separado para tarefas **sem responsável** em aberto (`contagem_sem_responsavel_abertas`) — texto «Há N tarefa(s) em aberto sem responsável» + **Ver tarefas**.
- **Faixa compacta** (`_faixas_compactas.html`, após implantação/disputas, antes das faixas de avisos): mesma contagem/link quando o overlay foi fechado e `banco_e_sandbox` (UX compacta). Oculta se contagem=0 (e sem bloco admin).
- **Sem** lista de títulos, e-mail ou push.

## Arquivos principais

- `tarefa_processo.py` — contagem e textos
- `nu_avisos_web.py` — context processor e supressão do modal em `/tarefas`
- `templates/_nu_avisos_modal.html`, `templates/_faixas_compactas.html`
- `static/nu_avisos_modal.js` — fecha overlay ao clicar em `/tarefas`
- `tests/test_tarefas_notificacao_modal.py`

## Validação manual (sandbox :8899)

1. Login com usuário que tenha tarefa **Comigo** ou **Pediram minha resposta** → modal com frase de contagem + **Ver todas** (sem títulos de tarefa no modal).
2. Fechar modal (×) → faixa **Ver tarefas** acima do título; avisos importantes/normais inalterados.
3. Concluir/cancelar tarefas até contagem 0 → faixa some.
4. ADMIN com tarefa aberta sem responsável → bloco/faixa separados; usuário comum não vê sem responsável.
