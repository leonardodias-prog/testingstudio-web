"""
caixa_branca.py — Motor de Teste Estrutural (Caixa-Branca) do TestingStudio Web · Sprint 2
===========================================================================================
Base: DELAMARO, MALDONADO e JINO (2007, Teste Estrutural) · McCABE (1976).

GFC — Grafo de Fluxo de Controle: cada NÓ é um bloco de comandos que sempre executam
juntos (entra pelo primeiro, sai pelo último); cada ARESTA é um desvio possível.

Complexidade ciclomática V(G) = número de caminhos independentes = o esforço mínimo
de teste para exercitar toda a lógica. Três formas que precisam bater:
  1. V(G) = E − N + 2        (arestas − nós + 2, a fórmula do slide)
  2. V(G) = P + 1            (P = nós de decisão; um CASE com k saídas vale k − 1)
  3. V(G) = nº de caminhos básicos que o algoritmo consegue montar

Python puro — a IA não monta o grafo nem conta nada aqui.
"""

import ast
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from fractions import Fraction

from caixa_preta import ler_txt  # noqa: F401  (reexportado por conveniência)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Estruturas
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class No:
    id: int
    tipo: str                                   # "inicio", "bloco", "decisao" ou "fim"
    linhas: list = field(default_factory=list)  # linhas do arquivo
    comandos: list = field(default_factory=list)
    condicao: str = ""                          # texto da decisão


@dataclass
class Aresta:
    origem: int
    destino: int
    rotulo: str = ""                            # "V", "F", "caso 1", "outro"...


@dataclass
class Grafo:
    nome: str
    nos: dict                                   # id → No (já numerados N1, N2…)
    arestas: list
    entrada: int
    saida: int
    decisoes_codigo: int                        # decisões contadas na estrutura do código
    avisos: list = field(default_factory=list)


# comandos do código (a "árvore" que vira grafo)
@dataclass
class _Cmd:
    linha: int
    texto: str


@dataclass
class _Se:
    linha: int
    texto: str
    entao: list
    senao: list | None


@dataclass
class _Laco:
    linha: int
    texto: str
    corpo: list
    senao: list | None = None                   # for/while ... else (Python)


@dataclass
class _Escolha:
    linha: int
    texto: str
    casos: list                                 # [(linha, rótulo, corpo)]
    padrao: list | None = None                  # OTHERWISE / case _
    implicito: bool = True                      # sem padrão, existe a saída "nenhum caso"


@dataclass
class _Retorno:
    linha: int
    texto: str


@dataclass
class _Sai:                                     # EXIT WHILE / break
    linha: int
    texto: str


@dataclass
class _Continua:                                # CONTINUE WHILE / continue
    linha: int
    texto: str


# ═══════════════════════════════════════════════════════════════════════════
# 2. Leitura do Informix-4GL
# ═══════════════════════════════════════════════════════════════════════════
_RE_FUNCAO = re.compile(r"^[ \t]*FUNCTION\s+(\w+)\s*\(([^)]*)\)(.*?)^[ \t]*END\s+FUNCTION", re.I | re.M | re.S)
_FIM_DE_COMANDO = r"(?:(?!\bEND\s+(?:IF|WHILE|FOR|FOREACH|CASE)\b|\bELSE\b)[^\n])*"
_EVENTOS = re.compile(rf"""
    (?P<fim>\bEND\s+(?:IF|WHILE|FOR|FOREACH|CASE)\b)
  | (?P<se>\bIF\b(?:(?!\bTHEN\b).)*?\bTHEN\b)
  | (?P<senao>\bELSE\b)
  | (?P<enquanto>\bWHILE\b[^\n]*)
  | (?P<paracada>\bFOREACH\b[^\n]*)
  | (?P<para>\bFOR\s+\w+(?:\.\w+)?\s*=[^\n]*)
  | (?P<caso>\bCASE\b[^\n]*)
  | (?P<quando>\bWHEN\b[^\n]*)
  | (?P<outro>\bOTHERWISE\b)
  | (?P<retorno>\bRETURN\b{_FIM_DE_COMANDO})
  | (?P<encerra>\bEXIT\s+PROGRAM\b{_FIM_DE_COMANDO})
  | (?P<sai>\bEXIT\s+(?:WHILE|FOR|FOREACH|CASE)\b)
  | (?P<continua>\bCONTINUE\s+(?:WHILE|FOR|FOREACH)\b)
""", re.I | re.S | re.X)
_FECHA = {"se": "IF", "enquanto": "WHILE", "para": "FOR", "paracada": "FOREACH", "caso": "CASE"}


def _limpar_4gl(codigo: str) -> str:
    """Apaga comentários e o miolo das strings, mantendo posições e quebras de linha."""
    codigo = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'', lambda m: m.group(0)[0] + " " * (len(m.group(0)) - 2) + m.group(0)[-1], codigo)
    branco = lambda m: re.sub(r"[^\n]", " ", m.group(0))   # noqa: E731
    codigo = re.sub(r"\{[^}]*\}", branco, codigo)
    return re.sub(r"(#|--)[^\n]*", branco, codigo)


def _sem_comentario(texto: str) -> str:
    return re.sub(r"\s*(#|--).*$", "", texto).strip()


def _tokens_4gl(limpo: str, original: str, inicio: int, fim: int, linha0: int) -> list:
    """Lista de (tipo, texto, linha) do corpo da função; texto livre vira 'cmd' (1 por linha)."""
    tokens = []

    def linha_de(pos):
        return linha0 + limpo.count("\n", inicio, pos)

    def livre(a, b):
        pos = a
        for pedaco in limpo[a:b].split("\n"):
            if pedaco.strip():
                desloc = len(pedaco) - len(pedaco.lstrip())
                texto = _sem_comentario(original[pos + desloc: pos + len(pedaco)])
                if texto:
                    tokens.append(("cmd", texto, linha_de(pos)))
            pos += len(pedaco) + 1

    pos = inicio
    for m in _EVENTOS.finditer(limpo, inicio, fim):
        livre(pos, m.start())
        tipo = m.lastgroup
        texto = " ".join(_sem_comentario(original[m.start():m.end()]).split())
        if tipo == "fim":
            texto = m.group(0).split()[-1].upper()
        tokens.append((tipo, texto, linha_de(m.start())))
        pos = m.end()
    livre(pos, fim)
    return tokens


def _condicao_4gl(texto_se: str) -> str:
    return re.sub(r"^IF\s+|\s+THEN$", "", texto_se, flags=re.I).strip()


def _fim_define(tokens: list, i: int) -> int:
    """Pula o DEFINE inteiro, que pode seguir nas linhas de baixo: vírgula no fim da linha
    (DEFINE a DECIMAL(12,2), b DECIMAL(12,2)) ou RECORD … END RECORD."""
    abertos = 0
    while i < len(tokens) and tokens[i][0] == "cmd":
        texto = tokens[i][1]
        fecha = len(re.findall(r"\bEND\s+RECORD\b", texto, re.I))
        abre = len(re.findall(r"\bRECORD\b", texto, re.I)) - fecha - len(re.findall(r"\bRECORD\s+LIKE\b", texto, re.I))
        abertos += abre - fecha
        i += 1
        if abertos <= 0 and not texto.endswith(","):
            break
    return i


def _arvore_4gl(tokens: list) -> list:
    """Transforma a lista de tokens na árvore de comandos (IF/WHILE/FOR/CASE aninhados)."""
    def espera_fim(i, tipo, abertura):
        if i < len(tokens) and tokens[i][0] == "fim" and tokens[i][1] == tipo:
            return i + 1
        raise ValueError(f"'{abertura[1][:40]}' da linha {abertura[2]} não tem END {tipo}")

    def bloco(i, fechamentos):
        itens = []
        while i < len(tokens):
            tipo, texto, linha = tokens[i]
            if tipo in fechamentos:
                return itens, i
            if tipo == "cmd":
                if re.match(r"DEFINE\b", texto, re.I):       # declaração não executa: fica fora do grafo
                    i = _fim_define(tokens, i)
                else:
                    itens.append(_Cmd(linha, texto))
                    i += 1
            elif tipo == "se":
                entao, i = bloco(i + 1, {"senao", "fim"})
                senao = None
                if i < len(tokens) and tokens[i][0] == "senao":
                    senao, i = bloco(i + 1, {"fim"})
                i = espera_fim(i, "IF", (tipo, texto, linha))
                itens.append(_Se(linha, _condicao_4gl(texto), entao, senao))
            elif tipo in ("enquanto", "para", "paracada"):
                corpo, i = bloco(i + 1, {"fim"})
                i = espera_fim(i, _FECHA[tipo], (tipo, texto, linha))
                itens.append(_Laco(linha, texto, corpo))
            elif tipo == "caso":
                i += 1
                casos, padrao = [], None
                while i < len(tokens) and tokens[i][0] in ("quando", "outro", "cmd"):
                    if tokens[i][0] == "quando":
                        _, rotulo, linha_q = tokens[i]
                        corpo, i = bloco(i + 1, {"quando", "outro", "fim"})
                        casos.append((linha_q, rotulo, corpo))
                    elif tokens[i][0] == "outro":
                        padrao, i = bloco(i + 1, {"fim"})
                    else:
                        i += 1                           # texto solto antes do 1º WHEN
                i = espera_fim(i, "CASE", (tipo, texto, linha))
                itens.append(_Escolha(linha, texto, casos, padrao))
            elif tipo in ("retorno", "encerra"):
                itens.append(_Retorno(linha, texto))
                i += 1
            elif tipo == "sai":
                itens.append(_Sai(linha, texto))
                i += 1
            elif tipo == "continua":
                itens.append(_Continua(linha, texto))
                i += 1
            else:
                raise ValueError(f"'{texto}' na linha {linha} sem o comando que o abre")
        return itens, i

    itens, i = bloco(0, set())
    return itens


def _funcoes_4gl(codigo: str) -> list:
    """[(nome, linha inicial, árvore ou mensagem de erro)] de cada FUNCTION."""
    limpo = _limpar_4gl(codigo)
    unidades = []
    for m in _RE_FUNCAO.finditer(limpo):
        linha0 = limpo.count("\n", 0, m.start(3)) + 1
        try:
            tokens = _tokens_4gl(limpo, codigo, m.start(3), m.end(3), linha0)
            unidades.append((m.group(1), limpo.count("\n", 0, m.start()) + 1, _arvore_4gl(tokens)))
        except ValueError as erro:
            unidades.append((m.group(1), limpo.count("\n", 0, m.start()) + 1, str(erro)))
    return unidades


# ═══════════════════════════════════════════════════════════════════════════
# 3. Leitura de Python (módulo ast) — para listas de exercícios em Python
# ═══════════════════════════════════════════════════════════════════════════
def _funcoes_python(codigo: str) -> list:
    try:
        modulo = ast.parse(codigo)
    except SyntaxError:
        return []
    linhas = codigo.splitlines()

    def texto(no):
        return linhas[no.lineno - 1].strip() if 0 < no.lineno <= len(linhas) else ast.unparse(no)

    def conv(comandos):
        itens = []
        for s in comandos:
            if isinstance(s, ast.If):
                itens.append(_Se(s.lineno, ast.unparse(s.test), conv(s.body), conv(s.orelse) or None))
            elif isinstance(s, ast.While):
                itens.append(_Laco(s.lineno, f"while {ast.unparse(s.test)}", conv(s.body), conv(s.orelse) or None))
            elif isinstance(s, (ast.For, ast.AsyncFor)):
                itens.append(_Laco(s.lineno, f"for {ast.unparse(s.target)} in {ast.unparse(s.iter)}",
                                   conv(s.body), conv(s.orelse) or None))
            elif isinstance(s, (ast.Return, ast.Raise)):
                itens.append(_Retorno(s.lineno, texto(s)))
            elif isinstance(s, ast.Break):
                itens.append(_Sai(s.lineno, "break"))
            elif isinstance(s, ast.Continue):
                itens.append(_Continua(s.lineno, "continue"))
            elif isinstance(s, (ast.With, ast.AsyncWith)):
                itens.append(_Cmd(s.lineno, texto(s)))
                itens += conv(s.body)
            elif isinstance(s, ast.Try):
                casos = [(s.lineno, "sem exceção", conv(s.body) + conv(s.orelse))]
                casos += [(h.lineno, "except " + (ast.unparse(h.type) if h.type else ""), conv(h.body))
                          for h in s.handlers]
                itens.append(_Escolha(s.lineno, "try", casos, None, implicito=False))
                itens += conv(s.finalbody)
            elif hasattr(ast, "Match") and isinstance(s, ast.Match):
                casos, padrao = [], None
                for c in s.cases:
                    curinga = isinstance(c.pattern, ast.MatchAs) and c.pattern.pattern is None and c.guard is None
                    if curinga:
                        padrao = conv(c.body)
                    else:
                        casos.append((c.pattern.lineno, f"case {ast.unparse(c.pattern)}", conv(c.body)))
                itens.append(_Escolha(s.lineno, f"match {ast.unparse(s.subject)}", casos, padrao))
            else:
                itens.append(_Cmd(s.lineno, texto(s)))
        return itens

    unidades = []
    for no in ast.walk(modulo):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            corpo = no.body
            if corpo and isinstance(corpo[0], ast.Expr) and isinstance(getattr(corpo[0], "value", None), ast.Constant) \
                    and isinstance(corpo[0].value.value, str):
                corpo = corpo[1:]                         # pula a docstring
            unidades.append((no.name, no.lineno, conv(corpo)))
    return sorted(unidades, key=lambda u: u[1])


# ═══════════════════════════════════════════════════════════════════════════
# 4. Construção do grafo
# ═══════════════════════════════════════════════════════════════════════════
def _dividir_condicao(condicao: str):
    """'a < 0 OR b < 0' → (['a < 0', 'b < 0'], 'OR'). Só divide no nível de fora dos parênteses
    e só quando todas as junções são iguais (só OR ou só AND)."""
    partes, juncoes, nivel, inicio = [], [], 0, 0
    for m in re.finditer(r"\(|\)|\s+(OR|AND|or|and)\s+", condicao):
        if m.group(0) == "(":
            nivel += 1
        elif m.group(0) == ")":
            nivel -= 1
        elif nivel == 0:
            partes.append(condicao[inicio:m.start()].strip())
            juncoes.append(m.group(1).upper())
            inicio = m.end()
    partes.append(condicao[inicio:].strip())
    if len(partes) > 1 and len(set(juncoes)) == 1:
        return partes, juncoes[0]
    return [condicao], None


class _Construtor:
    def __init__(self, separar: bool):
        self.separar = separar
        self.nos, self.arestas, self.avisos = {}, [], []
        self.decisoes = 0
        self._ultimo = 0
        self.fim = self.novo("fim")

    def novo(self, tipo, linha=None, texto="", condicao=""):
        self._ultimo += 1
        self.nos[self._ultimo] = No(self._ultimo, tipo, [linha] if linha else [], [texto] if texto else [], condicao)
        return self._ultimo

    def ligar(self, pendentes, destino):
        for origem, rotulo in pendentes:
            self.arestas.append(Aresta(origem, destino, rotulo))

    def seq(self, itens, pendentes, laco=None):
        """Processa os comandos em ordem e devolve de onde o fluxo sai no fim ('pendentes')."""
        bloco = None
        for item in itens:
            if not pendentes:
                self.avisos.append(f"código inalcançável a partir da linha {item.linha}")
                break
            if isinstance(item, _Cmd):
                if bloco is not None and pendentes == [(bloco, "")]:
                    self.nos[bloco].linhas.append(item.linha)
                    self.nos[bloco].comandos.append(item.texto)
                else:
                    bloco = self.novo("bloco", item.linha, item.texto)
                    self.ligar(pendentes, bloco)
                    pendentes = [(bloco, "")]
                continue
            bloco = None
            if isinstance(item, _Se):
                pendentes = self._se(item, pendentes, laco)
            elif isinstance(item, _Laco):
                teste = self.novo("decisao", item.linha, item.texto, item.texto)
                self.decisoes += 1
                self.ligar(pendentes, teste)
                contexto = {"teste": teste, "saidas": []}
                self.ligar(self.seq(item.corpo, [(teste, "V")], contexto), teste)   # volta ao teste
                saida = [(teste, "F")]
                if item.senao:
                    saida = self.seq(item.senao, saida, laco)
                pendentes = saida + contexto["saidas"]
            elif isinstance(item, _Escolha):
                escolha = self.novo("decisao", item.linha, item.texto, item.texto)
                self.ligar(pendentes, escolha)
                novos = []
                for _, rotulo, corpo in item.casos:
                    rot = re.sub(r"^WHEN\s+", "", rotulo, flags=re.I)[:18]
                    novos += self.seq(corpo, [(escolha, rot)], laco) if corpo else [(escolha, rot)]
                if item.padrao is not None:
                    novos += self.seq(item.padrao, [(escolha, "outro")], laco) if item.padrao else [(escolha, "outro")]
                elif item.implicito:
                    novos.append((escolha, "nenhum"))
                saidas = len(item.casos) + (1 if item.padrao is not None or item.implicito else 0)
                self.decisoes += max(0, saidas - 1)
                pendentes = novos
            else:
                no = self.novo("bloco", item.linha, item.texto)
                self.ligar(pendentes, no)
                if isinstance(item, _Retorno):
                    self.arestas.append(Aresta(no, self.fim))
                elif laco is None:
                    self.avisos.append(f"'{item.texto}' fora de laço (linha {item.linha})")
                    self.arestas.append(Aresta(no, self.fim))
                elif isinstance(item, _Sai):
                    laco["saidas"].append((no, ""))
                else:
                    self.arestas.append(Aresta(no, laco["teste"]))
                pendentes = []
        return pendentes

    def _se(self, item, pendentes, laco):
        partes, juncao = _dividir_condicao(item.texto) if self.separar else ([item.texto], None)
        decisoes = [self.novo("decisao", item.linha, p, p) for p in partes]
        self.decisoes += len(decisoes)
        self.ligar(pendentes, decisoes[0])
        if juncao == "OR":        # qualquer parte verdadeira já entra no ENTÃO
            para_entao = [(d, "V") for d in decisoes]
            for a, b in zip(decisoes, decisoes[1:]):
                self.arestas.append(Aresta(a, b, "F"))
            para_senao = [(decisoes[-1], "F")]
        elif juncao == "AND":     # qualquer parte falsa já vai para o SENÃO
            for a, b in zip(decisoes, decisoes[1:]):
                self.arestas.append(Aresta(a, b, "V"))
            para_entao = [(decisoes[-1], "V")]
            para_senao = [(d, "F") for d in decisoes]
        else:
            para_entao, para_senao = [(decisoes[0], "V")], [(decisoes[0], "F")]
        fim_entao = self.seq(item.entao, para_entao, laco) if item.entao else para_entao
        fim_senao = self.seq(item.senao, para_senao, laco) if item.senao else para_senao
        return fim_entao + fim_senao


def _compactar(nos: dict, arestas: list, entrada: int, saida: int):
    """Junta cadeias A → B (A com 1 saída, B com 1 entrada): blocos que sempre executam juntos."""
    mudou = True
    while mudou:
        mudou = False
        saidas, entradas = defaultdict(list), defaultdict(list)
        for a in arestas:
            saidas[a.origem].append(a)
            entradas[a.destino].append(a)
        for u in list(nos):
            if len(saidas[u]) != 1:
                continue
            v = saidas[u][0].destino
            if v == u or len(entradas[v]) != 1 or nos[u].tipo == "decisao":
                continue
            nu, nv = nos[u], nos[v]
            nu.linhas += nv.linhas
            nu.comandos += nv.comandos
            if nv.tipo in ("decisao", "fim"):
                nu.tipo, nu.condicao = nv.tipo, nv.condicao
            elif nu.tipo == "inicio":
                nu.tipo = nv.tipo
            arestas = [a for a in arestas if a is not saidas[u][0]]
            for a in arestas:
                if a.origem == v:
                    a.origem = u
            del nos[v]
            saida = u if v == saida else saida
            mudou = True
            break
    return nos, arestas, entrada, saida


def construir(nome: str, itens: list, separar: bool = False) -> Grafo:
    """Árvore de comandos → GFC compactado e numerado N1, N2… na ordem do código."""
    b = _Construtor(separar)
    inicio = b.novo("inicio")
    b.ligar(b.seq(itens, [(inicio, "")]), b.fim)
    alcancaveis, fila = {inicio}, deque([inicio])
    while fila:                                    # tira nós que nunca são alcançados
        u = fila.popleft()
        for a in b.arestas:
            if a.origem == u and a.destino not in alcancaveis:
                alcancaveis.add(a.destino)
                fila.append(a.destino)
    nos = {k: v for k, v in b.nos.items() if k in alcancaveis}
    arestas = [a for a in b.arestas if a.origem in alcancaveis]
    nos, arestas, entrada, saida = _compactar(nos, arestas, inicio, b.fim)

    ordem = sorted(nos.values(), key=lambda n: (n.id != entrada, n.id == saida and not n.linhas,
                                                 min(n.linhas) if n.linhas else 10 ** 9, n.id))
    novo_id = {n.id: i for i, n in enumerate(ordem, 1)}
    for a in arestas:
        a.origem, a.destino = novo_id[a.origem], novo_id[a.destino]
    nos = {novo_id[n.id]: n for n in ordem}
    for i, n in nos.items():
        n.id = i
    return Grafo(nome, nos, arestas, novo_id[entrada], novo_id[saida], b.decisoes, b.avisos)


def extrair_grafos(codigo: str, separar: bool = False) -> dict:
    """{nome da unidade: Grafo (ou texto do erro)} para cada FUNCTION 4GL — ou def Python."""
    unidades = _funcoes_4gl(codigo) or _funcoes_python(codigo)
    return {nome: (itens if isinstance(itens, str) else construir(nome, itens, separar))
            for nome, _, itens in unidades}


def trecho_da_unidade(codigo: str, nome: str) -> tuple:
    """(código da unidade, nº da 1ª linha no arquivo) — o fonte com a mesma numeração do grafo."""
    for m in _RE_FUNCAO.finditer(_limpar_4gl(codigo)):
        if m.group(1).lower() == nome.lower():
            return codigo[m.start():m.end()].strip("\n"), codigo.count("\n", 0, m.start()) + 1
    try:
        for no in ast.walk(ast.parse(codigo)):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name == nome:
                inicio = min([no.lineno] + [d.lineno for d in no.decorator_list])
                return "\n".join(codigo.splitlines()[inicio - 1:no.end_lineno]), inicio
    except SyntaxError:
        pass
    return codigo, 1


# ═══════════════════════════════════════════════════════════════════════════
# 5. V(G), caminhos básicos e o resumo para a tela
# ═══════════════════════════════════════════════════════════════════════════
def _saidas(g: Grafo) -> dict:
    s = defaultdict(list)
    for i, a in enumerate(g.arestas):
        s[a.origem].append(i)
    for lista in s.values():   # ordem estável: V antes de F, depois o resto
        lista.sort(key=lambda i: {"V": 0, "F": 1}.get(g.arestas[i].rotulo, 2))
    return s


def _ate_saida(g: Grafo, saidas: dict, origem: int) -> list:
    """Menor caminho (em arestas) de 'origem' até o nó de saída."""
    anterior, fila = {origem: None}, deque([origem])
    while fila:
        u = fila.popleft()
        if u == g.saida:
            break
        for i in saidas[u]:
            v = g.arestas[i].destino
            if v not in anterior:
                anterior[v] = i
                fila.append(v)
    caminho, u = [], g.saida
    while anterior.get(u) is not None:
        caminho.append(anterior[u])
        u = g.arestas[anterior[u]].origem
    return caminho[::-1]


class _Independencia:
    """Eliminação de Gauss exata (frações): o caminho novo é independente dos anteriores?"""
    def __init__(self):
        self.linhas = []

    def adiciona(self, caminho) -> bool:
        v = defaultdict(Fraction)
        for i in caminho:
            v[i] += 1
        for pivo, linha in self.linhas:
            if v.get(pivo):
                fator = v[pivo] / linha[pivo]
                for k, x in linha.items():
                    v[k] -= fator * x
        v = {k: x for k, x in v.items() if x}
        if not v:
            return False
        self.linhas.append((min(v), v))
        return True


def caminhos_basicos(g: Grafo) -> list:
    """Método da linha de base (McCabe): parte do menor caminho e, a cada decisão, troca de
    lado — fica com os caminhos linearmente independentes até somar V(G)."""
    vg = len(g.arestas) - len(g.nos) + 2
    saidas = _saidas(g)
    base = _ate_saida(g, saidas, g.entrada)
    indep = _Independencia()
    indep.adiciona(base)
    caminhos, fila = [base], deque([base])
    while fila and len(caminhos) < vg:
        caminho = fila.popleft()
        for pos, i in enumerate(caminho):
            no = g.arestas[i].origem
            for alternativa in saidas[no]:
                if alternativa == i:
                    continue
                novo = caminho[:pos] + [alternativa] + _ate_saida(g, saidas, g.arestas[alternativa].destino)
                if indep.adiciona(novo):
                    caminhos.append(novo)
                    fila.append(novo)
                if len(caminhos) == vg:
                    return caminhos
    return caminhos


RISCO = [(10, "baixo — programa simples"), (20, "moderado"), (50, "alto — complexo"),
         (10 ** 9, "muito alto — praticamente não testável")]


def risco(vg: int) -> str:
    return next(texto for limite, texto in RISCO if vg <= limite)


def _resumo_no(n: No) -> str:
    if n.tipo == "decisao":
        return n.condicao
    return " · ".join(n.comandos)[:120] or {"inicio": "início", "fim": "fim"}.get(n.tipo, "—")


def linhas_txt(linhas: list) -> str:
    """[60, 61, 62, 65] → '60–65' (faixa); poucas linhas ficam separadas por vírgula."""
    unicas = sorted(set(linhas))
    if not unicas:
        return "—"
    return ", ".join(map(str, unicas)) if len(unicas) <= 3 else f"{unicas[0]}–{unicas[-1]}"


def analisar(g: Grafo) -> dict:
    """Tabelas prontas para a tela e para o PDF."""
    e, n = len(g.arestas), len(g.nos)
    saidas = _saidas(g)
    p = sum(max(0, len(saidas[k]) - 1) for k in g.nos)
    caminhos = caminhos_basicos(g)
    vg = e - n + 2

    linhas_caminho = []
    for k, caminho in enumerate(caminhos, 1):
        seq = [g.entrada] + [g.arestas[i].destino for i in caminho]
        condicoes = [f"N{g.arestas[i].origem}: {g.nos[g.arestas[i].origem].condicao} → {g.arestas[i].rotulo}"
                     for i in caminho if g.nos[g.arestas[i].origem].tipo == "decisao"]
        linhas_caminho.append({"Caminho": f"C{k}", "Sequência de nós": " → ".join(f"N{x}" for x in seq),
                               "Decisões tomadas": " · ".join(condicoes) or "(sem decisões)",
                               "_arestas": caminho})
    cobertos = {i for c in caminhos for i in c}
    return {
        "N": n, "E": e, "P": p, "vg": vg,
        "formas": [
            {"Forma": "1. Arestas − nós + 2", "Conta": f"{e} − {n} + 2", "V(G)": e - n + 2},
            {"Forma": "2. Nós de decisão + 1", "Conta": f"{p} + 1", "V(G)": p + 1},
            {"Forma": "3. Caminhos básicos encontrados", "Conta": f"{len(caminhos)} caminhos", "V(G)": len(caminhos)},
        ],
        "confere": len({e - n + 2, p + 1, len(caminhos), g.decisoes_codigo + 1}) == 1,
        "decisoes_codigo": g.decisoes_codigo,
        "risco": risco(vg),
        "nos": [{"Nó": f"N{k}", "Tipo": {"inicio": "início", "bloco": "bloco", "decisao": "decisão", "fim": "fim"}[x.tipo],
                 "Linhas": linhas_txt(x.linhas), "Comandos": _resumo_no(x)}
                for k, x in g.nos.items()],
        "arestas": [{"De": f"N{a.origem}", "Para": f"N{a.destino}", "Rótulo": a.rotulo or "—"} for a in g.arestas],
        "caminhos": linhas_caminho,
        "todos_arcos": len(cobertos) == e,
        "avisos": g.avisos,
    }


def visao_arquivo(grafos: dict) -> list:
    """V(G) de todas as unidades do arquivo (esforço total de teste)."""
    linhas = []
    for nome, g in grafos.items():
        if isinstance(g, str):
            linhas.append({"Unidade": nome, "N": "—", "E": "—", "V(G)": "—", "Risco": f"erro: {g}"})
        else:
            vg = len(g.arestas) - len(g.nos) + 2
            linhas.append({"Unidade": nome, "N": len(g.nos), "E": len(g.arestas), "V(G)": vg, "Risco": risco(vg)})
    return linhas


# ═══════════════════════════════════════════════════════════════════════════
# 6. Desenho para a tela (Graphviz/DOT — o Streamlit desenha no navegador)
# ═══════════════════════════════════════════════════════════════════════════
def dot(g: Grafo, destaque: list | None = None) -> str:
    """DOT do grafo, igual ao desenho do PDF: decisão em losango, saída em círculo duplo e V/F coloridos.
    'destaque' = arestas de um caminho para pintar de verde."""
    destaque = set(destaque or [])
    nos_destaque = {g.entrada} | {g.arestas[i].destino for i in destaque} if destaque else set()
    estilo = {"inicio": 'fillcolor="#E3FCEF", color="#00875A"', "bloco": 'fillcolor="#DEEBFF", color="#0052CC"',
              "decisao": 'fillcolor="#FFF0B3", color="#FF8B00", shape=diamond, width=0.86, height=0.72',
              "fim": 'fillcolor="#EAE6FF", color="#5243AA"'}
    cor_rotulo = {"V": "#00875A", "F": "#DE350B"}
    linhas = ["digraph GFC {", 'graph [rankdir=TB, bgcolor="transparent", nodesep=0.45, ranksep=0.42];',
              'node [shape=circle, style=filled, fixedsize=true, width=0.62, fontname="Helvetica", '
              'fontsize=12, fontcolor="#172B4D", penwidth=1.6];',
              'edge [color="#7A869A", fontname="Helvetica-Bold", fontsize=10, arrowsize=0.7, penwidth=1.3];']
    for k, n in g.nos.items():
        forma = ", shape=doublecircle" if k == g.saida else ""
        realce = ', penwidth=3.2, color="#00875A"' if k in nos_destaque else ""
        dica = f"linhas {linhas_txt(n.linhas)}: {_resumo_no(n)}".replace('"', "'")
        linhas.append(f'N{k} [label="N{k}", tooltip="{dica}", {estilo[n.tipo]}{forma}{realce}];')
    for i, a in enumerate(g.arestas):
        atributos = [f'label=" {a.rotulo} ", fontcolor="{cor_rotulo.get(a.rotulo, "#7A869A")}"'] if a.rotulo else []
        if i in destaque:
            atributos.append('color="#00875A", penwidth=3.2')
        linhas.append(f"N{a.origem} -> N{a.destino} [{', '.join(atributos)}];")
    linhas.append("}")
    return "\n".join(linhas)
