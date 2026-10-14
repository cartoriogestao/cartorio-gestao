"""Extrai do menu e dos templates um inventário verificável para o manual.

Não atribui significado jurídico a campos: registra os nomes e comandos que
estão literalmente na interface, com indicação da tela de origem.
"""
from __future__ import annotations

import ast
import html
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
OUTPUT = ROOT / "DOCUMENTACAO" / "MANUAL_TELAS_E_CAMPOS.md"


def clear_jinja(value: str) -> str:
    value = re.sub(r"\{#.*?#\}", "", value, flags=re.S)
    value = re.sub(r"\{%.*?%\}", " ", value, flags=re.S)
    value = re.sub(r"\{\{.*?\}\}", " ", value, flags=re.S)
    value = re.sub(r"<[^>]*>", " ", value, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def attr(tag: str, name: str) -> str:
    match = re.search(rf"\b{name}\s*=\s*(['\"])(.*?)\1", tag, flags=re.S | re.I)
    return html.unescape(match.group(2)).strip() if match else ""


def visible_name(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").strip().capitalize()


def normalized_field_name(value: str) -> str:
    value = re.sub(r"\{\{\s*chave\('([^']+)'\)\s*\}\}", r"\1", value)
    return re.sub(r"\{\{.*?\}\}", "{item}", value)


def fields_and_actions(path: Path) -> tuple[list[str], list[str], list[str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"\{#.*?#\}", "", raw, flags=re.S)
    # A barra de formatação guarda fragmentos HTML em atributos; os sinais
    # `<` e `>` deles não são tags e confundem uma extração por regex.
    raw = re.sub(r"\sdata-inserir\s*=\s*(?:\"[^\"]*\"|'[^']*')", "", raw)
    fields: list[str] = []
    for match in re.finditer(r"<(input|select|textarea)\b[^>]*>", raw, flags=re.S | re.I):
        tag = match.group(0)
        name = normalized_field_name(attr(tag, "name"))
        if not name or name in {"csrf_token", "_csrf_token"} or attr(tag, "type").lower() == "hidden":
            continue
        before = raw[:match.start()]
        open_label = before.rfind("<label")
        close_label = before.rfind("</label")
        label = ""
        if open_label > close_label:
            start = before.find(">", open_label) + 1
            label = clear_jinja(before[start:])
        if len(label) > 75:
            label = label[:72].rsplit(" ", 1)[0] + "..."
        if not re.search(r"[A-Za-zÀ-ÿ]", label):
            label = visible_name(name)
        required = " (obrigatório na tela)" if re.search(r"\brequired\b", tag, re.I) else ""
        item = f"{label} [{name}]{required}"
        if item not in fields:
            fields.append(item)
    actions: list[str] = []
    for match in re.finditer(r"<button\b[^>]*>(.*?)</button>", raw, flags=re.S | re.I):
        label = clear_jinja(match.group(1))[:85]
        if len(label) <= 2:
            title = clear_jinja(attr(match.group(0).split(">", 1)[0], "title"))
            label = title or ("Inserir marcador" if "data-marcador" in match.group(0) else label)
        if label and re.search(r"[A-Za-zÀ-ÿ]", label) and label not in actions:
            actions.append(label)
    links: list[str] = []
    for match in re.finditer(r"<a\b[^>]*>(.*?)</a>", raw, flags=re.S | re.I):
        label = clear_jinja(match.group(1))[:75]
        if label and re.search(r"[A-Za-zÀ-ÿ]", label) and label not in links:
            links.append(label)
    return fields, actions, links


def route_templates() -> dict[str, str]:
    mapping: dict[str, str] = {}
    redirects: dict[str, str] = {}
    delegates: dict[str, str] = {}
    for path in sorted(ROOT.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            candidates = []
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                fn = inner.func
                if not isinstance(fn, ast.Name) or fn.id != "render_template" or not inner.args:
                    continue
                value = inner.args[0]
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    candidates.append(value.value)
            if candidates and node.name not in mapping:
                mapping[node.name] = candidates[0]
            if node.name not in mapping:
                for inner in ast.walk(node):
                    if (not isinstance(inner, ast.Call) or not isinstance(inner.func, ast.Name)
                            or inner.func.id != "url_for" or not inner.args):
                        continue
                    target = inner.args[0]
                    if isinstance(target, ast.Constant) and isinstance(target.value, str):
                        redirects.setdefault(node.name, target.value)
                        break
            for inner in node.body:
                if isinstance(inner, ast.Return) and isinstance(inner.value, ast.Call):
                    target = inner.value.func
                    if isinstance(target, ast.Name):
                        delegates.setdefault(node.name, target.id)
    for name, target in redirects.items():
        if name not in mapping and target in mapping:
            mapping[name] = mapping[target]
    for name, target in delegates.items():
        if name not in mapping and target in mapping:
            mapping[name] = mapping[target]
    for name in ("ri_modelos_papeis", "notas_modelos_papeis", "rcpn_modelos_papeis",
                 "rcpj_rtd_modelos_papeis", "protesto_modelos_papeis", "caixa_modelos_papeis"):
        mapping[name] = "modelos_atribuicao.html"
    return mapping


def menu_entries() -> list[dict[str, str]]:
    raw = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    raw = re.sub(r"\{#.*?#\}", "", raw, flags=re.S)
    nav_start = raw.find("<nav>")
    nav_end = raw.find("</nav>", nav_start)
    if nav_start >= 0 and nav_end > nav_start:
        raw = raw[nav_start:nav_end]
    pattern = re.compile(
        r"<summary\b[^>]*>(.*?)</summary>|"
        r"<div\s+class=\"nav-secao\"[^>]*>(.*?)</div>|"
        r"<a\b[^>]*href=\"\{\{\s*url_for\('([^']+)'[^\"]*\}\}\"[^>]*>(.*?)</a>",
        flags=re.S | re.I,
    )
    module = "Geral"
    section = ""
    entries = []
    for match in pattern.finditer(raw):
        if match.group(1) is not None:
            value = clear_jinja(match.group(1))
            if value:
                module, section = value, ""
        elif match.group(2) is not None:
            section = clear_jinja(match.group(2))
        elif match.group(3) is not None:
            label = clear_jinja(match.group(4))
            if label:
                entries.append({"module": module, "section": section,
                                "label": label, "endpoint": match.group(3)})
    return entries


def build() -> dict[str, int]:
    version = (ROOT / "VERSAO.txt").read_text(encoding="utf-8").strip()
    routes = route_templates()
    entries = menu_entries()
    by_module: dict[str, list[dict[str, str]]] = defaultdict(list)
    for entry in entries:
        by_module[entry["module"]].append(entry)
    lines = [
        "# Manual das telas, campos e comandos do Cartório Gestão",
        "",
        f"Versão de referência: {version}. Este volume é extraído do menu `templates/base.html` e das telas HTML da mesma versão. O nome de um campo ou botão abaixo é uma transcrição da interface; sua obrigatoriedade pode depender do tipo de ato e da etapa. Confirme a regra e a mensagem exibida na própria tela antes de gravar.",
        "",
        "## Como ler este volume",
        "",
        "Cada entrada informa o caminho do menu, o arquivo de tela, os campos nomeados e os comandos identificados no HTML. `{item}` representa o identificador dinâmico de uma linha ou pessoa; ele muda conforme o registro aberto. Campos dinâmicos de listas e componentes compartilhados podem aparecer apenas quando houver registro ou permissão. Campos indicados como obrigatórios têm atributo `required` no HTML; o servidor também pode exigir outros campos conforme a operação. Os comandos apresentados não autorizam seu uso sem conferência do ato.",
        "",
        "O inventário cobre 162 entradas do menu e 102 telas complementares identificadas nesta versão. Componentes compartilhados iniciados por sublinhado aparecem dentro das telas que os incluem. Este volume descreve o que está no código, sem substituir a conferência do registro concreto.",
        "",
    ]
    mapped = 0
    used_templates: set[str] = set()
    for module, items in by_module.items():
        lines += [f"## {module}", ""]
        for entry in items:
            template = routes.get(entry["endpoint"], "")
            lines += [f"### {entry['label']}", ""]
            path_label = " > ".join(part for part in (module, entry["section"], entry["label"]) if part)
            lines += [f"Caminho: {path_label}."]
            if template and (TEMPLATES / template).is_file():
                mapped += 1
                used_templates.add(template)
                fields, actions, links = fields_and_actions(TEMPLATES / template)
                lines += [f"Tela-fonte: `templates/{template}`."]
                lines += ["Campos da tela: " + ("; ".join(fields[:40]) + (f"; e mais {len(fields)-40} campos" if len(fields)>40 else "") if fields else "nenhum campo de formulário nomeado nesta tela") + "."]
                lines += ["Comandos: " + ("; ".join(actions[:30]) + (f"; e mais {len(actions)-30} comandos" if len(actions)>30 else "") if actions else "nenhum botão local nomeado") + "."]
                if links:
                    lines += ["Acessos relacionados: " + "; ".join(links[:12]) + (f"; e mais {len(links)-12} links" if len(links)>12 else "") + "."]
            else:
                lines += ["Tela-fonte: rota do menu sem um único template estático identificado; a tela pode escolher modelo conforme o contexto. Use o nome acima para localizá-la no sistema."]
            lines += [""]
    extras = [path for path in sorted(TEMPLATES.glob("*.html"))
              if not path.name.startswith("_") and path.name != "base.html"
              and path.name not in used_templates]
    lines += ["## Telas de ficha, etapa e documento", "",
              "Estas telas não têm entrada própria no menu principal. Abrem a partir de listas, fichas, etapas ou links de outra tela. O nome abaixo vem do título HTML quando há um título estático; caso contrário, do arquivo. Para voltar ao processo ou registro, use o link de retorno da própria tela.", ""]
    for path in extras:
        raw = path.read_text(encoding="utf-8", errors="replace")
        title_match = re.search(r"<h1\b[^>]*>(.*?)</h1>", raw, flags=re.S | re.I)
        title = clear_jinja(title_match.group(1)) if title_match else ""
        title = title or visible_name(path.stem)
        fields, actions, links = fields_and_actions(path)
        lines += [f"### {title}", "", f"Tela-fonte: `templates/{path.name}`.",
                  "Campos da tela: " + ("; ".join(fields[:40]) + (f"; e mais {len(fields)-40} campos" if len(fields)>40 else "") if fields else "nenhum campo de formulário nomeado nesta tela") + ".",
                  "Comandos: " + ("; ".join(actions[:30]) + (f"; e mais {len(actions)-30} comandos" if len(actions)>30 else "") if actions else "nenhum botão local nomeado") + "."]
        if links:
            lines += ["Acessos relacionados: " + "; ".join(links[:12]) + (f"; e mais {len(links)-12} links" if len(links)>12 else "") + "."]
        lines += [""]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    return {"entries": len(entries), "mapped": mapped, "extra_templates": len(extras),
            "modules": len(by_module), "lines": len(lines)}


if __name__ == "__main__":
    print(build())
