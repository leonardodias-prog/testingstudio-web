"""
rtm.py — Derivação de Casos de Teste e Matriz de Rastreabilidade (Sprint 2)
============================================================================
Base: DELAMARO, MALDONADO e JINO (2007, cap. 2) · MOLINARI (2008) · SWEBOK V3.0 (IEEE).

Caso de uso = a intenção do usuário. Dele saem os fluxos que viram casos de teste (CT):
  Principal   — caminho feliz: tudo dá certo
  Alternativo — desvios aceitáveis e condições de LIMITE (AVL com ε)
  Exceção     — bloqueios e erros: o sistema precisa barrar a operação

RTM (Matriz de Rastreabilidade de Requisitos) = prova da cobertura BIDIRECIONAL:
  ida   → "Tudo o que foi pedido foi coberto?"   (todo requisito tem pelo menos 1 CT)
  volta → "Tudo o que foi testado foi pedido?"   (todo CT aponta para um requisito que existe)

Python puro: a IA pode SUGERIR casos, mas quem confere a cobertura é este arquivo.
"""

import re
from dataclasses import dataclass, field

FLUXOS = ["Principal (caminho feliz)", "Alternativo (limite)", "Exceção (bloqueio)"]
SIGLA = {"Principal (caminho feliz)": "P", "Alternativo (limite)": "A", "Exceção (bloqueio)": "E"}

_RE_ID = re.compile(r"\b(REQ|RF|RNF|RN|CT)\s*[-_]?\s*(\d+)\b", re.I)


@dataclass
class Requisito:
    id: str
    descricao: str


@dataclass
class CasoTeste:
    id: str
    titulo: str = ""
    fluxo: str = FLUXOS[0]
    requisitos: list = field(default_factory=list)   # ["REQ01", "REQ04", "REQ05"]
    pre_condicoes: str = ""
    passos: str = ""
    dados: str = ""
    resultado_esperado: str = ""


def normalizar_id(texto: str) -> str:
    """'req 1' → 'REQ01' · '[RF3]' → 'RF03' · 'ct-12' → 'CT12'."""
    m = _RE_ID.search(str(texto))
    return f"{m.group(1).upper()}{int(m.group(2)):02d}" if m else str(texto).strip().upper()


def ids_em(texto) -> list:
    """Todos os IDs citados num texto: 'REQ01 → REQ04, req5' → ['REQ01', 'REQ04', 'REQ05']."""
    if isinstance(texto, (list, tuple)):
        texto = " ".join(map(str, texto))
    vistos = []
    for prefixo, numero in _RE_ID.findall(str(texto)):
        rid = f"{prefixo.upper()}{int(numero):02d}"
        if rid not in vistos:
            vistos.append(rid)
    return vistos


# ═══════════════════════════════════════════════════════════════════════════
# 1. Leitura dos requisitos (texto livre ou .txt)
# ═══════════════════════════════════════════════════════════════════════════
def ler_requisitos(texto: str):
    """Uma linha por requisito, ex.: '[REQ01]: Cadastro de novos livros...'.
    Se nenhuma linha tiver ID, cada linha vira REQ01, REQ02… A primeira linha sem ID
    (quando as outras têm) é tratada como o nome do cenário. Devolve (cenario, requisitos)."""
    linhas = [l.strip(" \t-•*") for l in str(texto).splitlines() if l.strip()]
    com_id = [l for l in linhas if re.match(r"^\W*(REQ|RF|RNF|RN)\s*[-_]?\s*\d+", l, re.I)]
    cenario, requisitos = "", []
    if com_id:
        for linha in linhas:
            m = re.match(r"^\W*((?:REQ|RF|RNF|RN)\s*[-_]?\s*\d+)\W*\s*(.*)$", linha, re.I)
            if m and m.group(2).strip():
                requisitos.append(Requisito(normalizar_id(m.group(1)), m.group(2).strip()))
            elif not m and not cenario and not requisitos:
                cenario = linha
    else:
        requisitos = [Requisito(f"REQ{i:02d}", l) for i, l in enumerate(linhas, 1)]
    return cenario, requisitos


# ═══════════════════════════════════════════════════════════════════════════
# 2. Casos de teste: vindos da tabela da tela, da IA ou de modelos prontos
# ═══════════════════════════════════════════════════════════════════════════
def _txt(v) -> str:
    return "" if str(v).strip() in ("", "None", "nan", "NaN", "<NA>") else str(v).strip()


def fluxo_de(texto: str) -> str:
    """'exceção', 'bloqueio', 'limite', 'alternativo', 'caminho feliz'… → um dos FLUXOS."""
    t = _txt(texto).lower()
    if any(p in t for p in ("exce", "bloq", "erro", "falha", "impedi")):
        return FLUXOS[2]
    if any(p in t for p in ("alter", "limit", "fronteir", "avl", "desvio")):
        return FLUXOS[1]
    return FLUXOS[0]


def caso_de_dict(d: dict) -> CasoTeste:
    fluxo = fluxo_de(d.get("fluxo"))
    return CasoTeste(
        id=normalizar_id(_txt(d.get("id"))) if _txt(d.get("id")) else "",
        titulo=_txt(d.get("titulo")),
        fluxo=fluxo,
        requisitos=ids_em(d.get("requisitos") or ""),
        pre_condicoes=_txt(d.get("pre_condicoes")),
        passos=_txt(d.get("passos")),
        dados=_txt(d.get("dados")),
        resultado_esperado=_txt(d.get("resultado_esperado")),
    )


def numerar(casos: list) -> list:
    """Garante IDs únicos CT01, CT02… (mantém os que já são válidos e únicos)."""
    usados, saida = set(), []
    for c in casos:
        if c.id and c.id.startswith("CT") and c.id not in usados:
            usados.add(c.id)
            saida.append(c)
            continue
        n = 1
        while f"CT{n:02d}" in usados:
            n += 1
        c.id = f"CT{n:02d}"
        usados.add(c.id)
        saida.append(c)
    return saida


_PALAVRAS_EXCECAO = ("valid", "pendênc", "pendenc", "bloque", "não pode", "nao pode", "impedi",
                     "restri", "autoriz", "permiss", "senha", "login", "erro")
_RE_NUMERO = re.compile(r"R\$\s*\d|\d+\s*(%|dias?|horas?|anos?|unidades?|itens?|reais)|\d+[.,]\d+", re.I)


def modelos_sem_ia(requisitos: list) -> list:
    """Ponto de partida offline: 1 CT do fluxo principal por requisito, mais um de LIMITE
    se o requisito tem números/valores e um de EXCEÇÃO se ele valida ou restringe algo.
    Os campos ficam para você completar — derivar é trabalho do testador."""
    casos = []
    for r in requisitos:
        casos.append(CasoTeste("", f"{r.id} — caminho feliz", FLUXOS[0], [r.id],
                               resultado_esperado=f"Sistema atende: {r.descricao}"))
        if _RE_NUMERO.search(r.descricao):
            casos.append(CasoTeste("", f"{r.id} — valores-limite (AVL: X − ε, X, X + ε)", FLUXOS[1], [r.id],
                                   dados="Defina X (fronteira) e ε (menor variação) do valor do requisito"))
        if any(p in r.descricao.lower() for p in _PALAVRAS_EXCECAO):
            casos.append(CasoTeste("", f"{r.id} — condição impeditiva", FLUXOS[2], [r.id],
                                   resultado_esperado="Sistema bloqueia a operação e informa o motivo"))
    return numerar(casos)


# ═══════════════════════════════════════════════════════════════════════════
# 3. RTM — Matriz de Rastreabilidade de Requisitos
# ═══════════════════════════════════════════════════════════════════════════
def matriz(requisitos: list, casos: list) -> dict:
    """Monta a RTM e mede a cobertura nos dois sentidos."""
    ids_req = [r.id for r in requisitos]
    linhas = []
    for r in requisitos:
        cobrem = [c for c in casos if r.id in c.requisitos]
        linha = {"Requisito": r.id, "Descrição": r.descricao}
        linha.update({c.id: "✔" if r.id in c.requisitos else "" for c in casos})
        linha["Nº de CTs"] = len(cobrem)
        linha["Fluxos"] = " ".join(sorted({SIGLA[c.fluxo] for c in cobrem}, key="PAE".index)) or "—"
        linhas.append(linha)

    nao_cobertos = [r.id for r in requisitos if not any(r.id in c.requisitos for c in casos)]
    orfaos = [c.id for c in casos if not c.requisitos]
    inexistentes = [(c.id, rid) for c in casos for rid in c.requisitos if rid not in ids_req]
    rastreados = [c.id for c in casos if c.requisitos and all(rid in ids_req for rid in c.requisitos)]
    return {
        "linhas": linhas,
        "ida": (len(requisitos) - len(nao_cobertos), len(requisitos)),   # pedidos cobertos
        "volta": (len(rastreados), len(casos)),                          # testes que foram pedidos
        "nao_cobertos": nao_cobertos,
        "orfaos": orfaos,
        "inexistentes": inexistentes,
        "por_fluxo": {f: sum(c.fluxo == f for c in casos) for f in FLUXOS},
    }


def percentual(par) -> str:
    feito, total = par
    return f"{100 * feito / total:.0f}%" if total else "—"


def tabela_casos(casos: list) -> list:
    """Casos de teste no formato de tabela (tela, CSV e PDF)."""
    return [{
        "CT": c.id, "Título": c.titulo, "Fluxo": c.fluxo, "Rastreio": " → ".join(c.requisitos),
        "Pré-condições": c.pre_condicoes, "Passos": c.passos, "Dados de teste": c.dados,
        "Resultado esperado": c.resultado_esperado,
    } for c in casos]


# Exemplo da aula de 14/10 (slides "Backlog de Requisitos" e "Derivando Casos de Teste")
EXEMPLO_REQUISITOS = """Sistema de Biblioteca Universitária
[REQ01]: Cadastro de novos livros informando ISBN, Título e Autor.
[REQ02]: Validação de pendências financeiras do usuário antes de realizar o empréstimo.
[REQ03]: Cálculo automático da multa de R$ 2,00 por dia de atraso na devolução.
[REQ04]: Busca de livros por título ou categoria.
[REQ05]: Emissão de comprovante digital de reserva por e-mail."""

EXEMPLO_CASOS = [
    CasoTeste("CT01", "Caminho feliz: cadastrar, buscar e reservar", FLUXOS[0], ["REQ01", "REQ04", "REQ05"],
              "Usuário bibliotecário autenticado",
              "1. Cadastrar livro com ISBN, título e autor  2. Buscar pelo título  3. Reservar",
              "ISBN fictício 978-85-00000-00-0 · 'Introdução ao Teste de Software' · Delamaro",
              "Livro cadastrado, encontrado na busca e comprovante de reserva enviado por e-mail"),
    CasoTeste("CT02", "Exceção: usuário com dívida tenta emprestar", FLUXOS[2], ["REQ02"],
              "Usuário com multa em aberto",
              "1. Solicitar empréstimo de um livro disponível",
              "Usuário com pendência de R$ 10,00",
              "Sistema barra o empréstimo e informa a pendência financeira"),
    CasoTeste("CT03", "Limite: multa exata por dia de atraso", FLUXOS[1], ["REQ03"],
              "Empréstimo com data prevista de devolução",
              "1. Devolver com 0, 1 e 2 dias de atraso (AVL com ε = 1 dia)",
              "0 dia · 1 dia · 2 dias",
              "Multa de R$ 0,00 · R$ 2,00 · R$ 4,00"),
]
