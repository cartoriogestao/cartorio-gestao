# Roteiro 3.6.201 — Certidão negativa de imóvel (busca)

**25/09/2026 — pedido da substituta escrevente (CNS 000000).**

## O que já existia
- **Certidão negativa de ônus reais** (`ONUS`) na ficha da matrícula:
  Registro de Imóveis → abrir matrícula → Emitir certidão → tipo «Certidão negativa de ônus reais».
  Quando não há ônus, o miolo diz **NADA CONSTA** de ônus/gravames.

## O que não existia (e o #75 tirou do lugar errado)
- Certidão de que **não consta matrícula/registro em nome da pessoa** (ou sobre o imóvel).
  Isso não cabe na ficha da matrícula (#75, 18/09/2026).

## O que esta versão entrega
- Emissão de **Certidão negativa de imóvel** pelos indicadores:
  1. **Indicador Pessoal** (nome/CPF) — se a busca não achar ninguém, aparece o formulário de emitir.
  2. **Indicador Real** (descrição/bairro) — se `total == 0`, aparece o formulário.
- O POST **refaz a busca**; se achar algo, **recusa** (não inventa negativa).
- Selo automático em `/selo/imovel/certidao`, item **16.24.1** (já medido; não inventado).
- Sem bypass «mesmo se o selo falhar»: selo falhou → certidão cancelada.
- Sem traço de assinatura à mão; mantém nome/função de quem lavrou.
- Tipo `NEGATIVA_IMOVEL` **não** volta ao seletor da ficha (`TIPOS_CERTIDAO` intacto).

## Como escrevente emite
1. Menu **Registro de Imóveis** → **Indicador Pessoal** (ou **Indicador Real**).
2. Digite o nome/CPF (ou a descrição do imóvel) → **Buscar**.
3. Se **nada constar**, preencha requerente/finalidade e clique **Emitir certidão negativa**.
4. O PDF abre em seguida (lista também em **Certidões**).

## Arquivos
- `ri_certidao_negativa.py` (novo)
- `ri_web.py`, `ri_schema.py`, `ato_selado.py`, `modelos_da_casa.py`, `app.py`, `VERSAO.txt`
- templates: `ri_indicador_pessoal.html`, `ri_indicador_real.html`, `ri_certidoes.html`
- teste: `tests/test_ri_certidao_negativa_imovel.py`