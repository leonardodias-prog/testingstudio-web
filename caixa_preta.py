"""
caixa_preta.py — Motor de Teste Funcional (Caixa-Preta) do TestingStudio Web
=============================================================================
Base teórica: DELAMARO, MALDONADO e JINO (2007), "Introdução ao Teste de Software".

  PCE  Particionamento em Classes de Equivalência — divide o domínio de cada
       entrada (e da saída) em classes válidas e inválidas e testa UM
       representante de cada classe.
  AVL  Análise do Valor Limite — os defeitos se escondem nas fronteiras, então
       testa X − ε, X e X + ε em cada limite X (das entradas e da saída).

Épsilon (ε) = a menor variação que o TIPO de dado consegue representar:
  INTEGER, SMALLINT, BIGINT   ε = 1
  DECIMAL(p,s)                ε = 10^-s        ex.: DECIMAL(12,2) → ε = 0.01
  CHAR(n)                     ε = 1 caractere  (a fronteira é o tamanho do texto)
  FLOAT                       ε = ulp(X)       distância até o próximo float

Este arquivo é Python puro — a IA não decide nada aqui. As contas usam Decimal,
que é exato (com float, 0.1 + 0.2 dá 0.30000000000000004).
"""

import ast
import math
import operator
import re
import sys
from dataclasses import dataclass, field, replace
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

NULO = None  # o NULL do banco / 4GL
TIPOS = ["DECIMAL", "INTEGER", "SMALLINT", "BIGINT", "CHAR", "FLOAT"]

# Informix: o menor negativo de cada inteiro é reservado para representar o NULL
LIMITES_INTEIROS = {
    "SMALLINT": (-32767, 32767),
    "INTEGER": (-2147483647, 2147483647),
    "BIGINT": (-9223372036854775807, 9223372036854775807),
}
SINONIMOS = {
    "DEC": "DECIMAL", "NUMERIC": "DECIMAL", "MONEY": "DECIMAL",
    "INT": "INTEGER", "SERIAL": "INTEGER", "INT8": "BIGINT", "SERIAL8": "BIGINT",
    "CHARACTER": "CHAR", "VARCHAR": "CHAR", "NCHAR": "CHAR", "NVARCHAR": "CHAR",
    "SMALLFLOAT": "FLOAT", "REAL": "FLOAT",
}


# ═══════════════════════════════════════════════════════════════════════════
# 1. Leitura do arquivo .txt
# ═══════════════════════════════════════════════════════════════════════════
def ler_txt(dados: bytes) -> str:
    """Bytes do arquivo → texto. Aceita UTF-8 e o ANSI do Windows (cp1252)."""
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            return dados.decode(codificacao)
        except UnicodeDecodeError:
            pass
    return dados.decode("latin-1")  # nunca falha


# ═══════════════════════════════════════════════════════════════════════════
# 2. Modelo de dados
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class Entrada:
    """Uma variável da unidade em teste (entrada ou saída)."""
    nome: str
    tipo: str = ""                 # um dos TIPOS
    tamanho: int | None = None     # p de DECIMAL(p,s) ou n de CHAR(n)
    casas: int | None = None       # s de DECIMAL(p,s)
    minimo: str = ""               # limite inferior da regra (vazio = o do tipo)
    maximo: str = ""               # limite superior da regra (vazio = o do tipo)
    aceita_nulo: bool = False      # o código trata NULL? (IF x IS NULL THEN LET x = 0)
    se_nulo: str = "0"             # valor que o NULL assume
    tipico: str = ""               # valor típico (vazio = automático)

    def tipo_txt(self) -> str:
        if self.tipo == "DECIMAL":
            casas = "?" if self.casas is None else self.casas
            return f"DECIMAL({self.tamanho or 16},{casas})"
        if self.tipo == "CHAR":
            return f"CHAR({self.tamanho or 1})"
        return self.tipo or "?"


@dataclass
class Unidade:
    """Uma FUNCTION do programa: entradas, saída e a regra que calcula a saída."""
    nome: str
    entradas: list
    formula: str = ""              # ex.: (p_val1 * p_val2) + p_val3
    saida: Entrada | None = None   # variável devolvida no RETURN
    erro_codigo: str = ""          # o que a função devolve quando a regra é violada (ex.: -1)
    limites_regra: dict = field(default_factory=dict)   # {"val_param1": {"min": "0"}} vindos do código

    def erro(self):
        """Regra de negócio no formato que analisar() recebe (ou None)."""
        return {"codigo": self.erro_codigo, "limites": self.limites_regra} if self.erro_codigo else None


def _vazio(v) -> bool:
    """Célula vazia? (None, NaN e <NA> do pandas contam como vazio)."""
    return str(v).strip() in ("", "None", "nan", "NaN", "<NA>")


def _txt(v) -> str:
    return "" if _vazio(v) else str(v).strip()


def _int(v):
    try:
        return None if _vazio(v) else int(float(v))
    except ValueError:
        return None


def entrada_de_dict(d: dict) -> Entrada:
    """Monta uma Entrada a partir de um dicionário (tabela da tela ou JSON da IA)."""
    tipo = _txt(d.get("tipo")).upper()
    tipo = SINONIMOS.get(tipo, tipo)
    return Entrada(
        nome=_txt(d.get("nome")),
        tipo=tipo if tipo in TIPOS else "",
        tamanho=_int(d.get("tamanho")),
        casas=_int(d.get("casas")),
        minimo=_txt(d.get("minimo")),
        maximo=_txt(d.get("maximo")),
        aceita_nulo=_txt(d.get("aceita_nulo")).lower() in ("true", "1", "sim"),
        se_nulo=_txt(d.get("se_nulo")) or "0",
        tipico=_txt(d.get("tipico")),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Extração do fonte Informix-4GL (expressões regulares — sem IA)
# ═══════════════════════════════════════════════════════════════════════════
_TIPOS_4GL = (r"DECIMAL|DEC|NUMERIC|MONEY|INTEGER|INT8|INT|SMALLINT|BIGINT|SERIAL8|SERIAL"
              r"|CHARACTER|CHAR|NVARCHAR|VARCHAR|NCHAR|SMALLFLOAT|FLOAT|REAL")
_RE_DECLARACAO = re.compile(   # aceita "a DECIMAL(12,2)" e "a, b, c DECIMAL(12,2)"
    rf"\b(\w+(?:\s*,\s*\w+)*)\s+({_TIPOS_4GL})\b(?:\s*\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\))?", re.I)
_RE_FUNCAO = re.compile(
    r"^[ \t]*FUNCTION\s+(\w+)\s*\(([^)]*)\)(.*?)^[ \t]*END\s+FUNCTION", re.I | re.M | re.S)


def _sem_comentarios(codigo: str) -> str:
    codigo = re.sub(r"\{.*?\}", " ", codigo, flags=re.S)   # { bloco }
    return re.sub(r"(#|--).*", "", codigo)                  # # linha   -- linha


def _declaracoes(trecho: str) -> dict:
    """Acha 'nome TIPO(p,s)' e devolve {nome em minúsculas: Entrada}."""
    achadas = {}
    for nomes, tipo, n1, n2 in _RE_DECLARACAO.findall(trecho):
        original = tipo.upper()
        casas = int(n2) if n2 else (2 if original == "MONEY" else None)
        for nome in re.split(r"\s*,\s*", nomes):
            achadas[nome.lower()] = Entrada(nome=nome, tipo=SINONIMOS.get(original, original),
                                            tamanho=int(n1) if n1 else None, casas=casas)
    return achadas


def codigo_da_unidade(codigo: str, nome: str) -> str:
    """O trecho FUNCTION ... END FUNCTION de uma unidade (para o relatório)."""
    for m in _RE_FUNCAO.finditer(codigo):
        if m.group(1).lower() == nome.lower():
            return m.group(0).strip("\n")
    return codigo


def extrair_unidades(codigo: str) -> list:
    """Lê um fonte Informix-4GL e devolve cada FUNCTION como uma Unidade."""
    limpo = _sem_comentarios(codigo)
    globais = _declaracoes(_RE_FUNCAO.sub(" ", limpo))   # RECORDs e variáveis globais
    unidades = []
    for funcao in _RE_FUNCAO.finditer(limpo):
        nome, parametros, corpo = funcao.groups()
        locais = _declaracoes(corpo)
        entradas = []

        # a) parâmetros: FUNCTION cad0001_calcula_valor(val_param1, val_param2, val_param3).
        #    Apelido: "LET p_val1 = val_param1" → p_val1 é o parâmetro com outro nome
        #    (e o tipo do parâmetro vem do DEFINE de p_val1).
        params = [x.strip() for x in parametros.split(",") if x.strip()]
        por_minusculo = {p.lower(): p for p in params}
        apelidos = {}
        for local, origem in re.findall(r"\bLET\s+(\w+)\s*=\s*(\w+)\b(?!\s*[-+*/(.\[])", corpo, re.I):
            if origem.lower() in por_minusculo and local.lower() not in por_minusculo:
                apelidos[local.lower()] = por_minusculo[origem.lower()]

        def parametro(nome_var: str) -> str:    # p_val1 → val_param1 (ou o próprio nome)
            return apelidos.get(nome_var.lower(), nome_var)

        for p in params:
            achada = locais.get(p.lower()) or next(
                (locais[local] for local, alvo in apelidos.items() if alvo == p and local in locais), None)
            entradas.append(replace(achada, nome=p) if achada else Entrada(nome=p))

        # b) campos de RECORD global que a função LÊ (ex.: mr_item.cod_item).
        #    Campo que a função só calcula (LET mr_item.x = ...) é saída, não entrada.
        usados = {c.lower() for c in re.findall(r"\b\w+\.(\w+)", corpo)}
        calculados = {c.lower() for c in re.findall(r"\bLET\s+\w+\.(\w+)\s*=", corpo, re.I)}
        ja_tem = {e.nome.lower() for e in entradas}
        for campo, declarada in globais.items():
            if campo in usados and campo not in calculados and campo not in ja_tem:
                entradas.append(replace(declarada))

        # c) NULL tratado no código: IF x IS NULL THEN LET x = 0  (ou LET apelido_de_x = 0)
        tratados = re.findall(r"\bIF\s+([\w.]+)\s+IS\s+NULL\s+THEN\s+LET\s+([\w.]+)\s*=\s*(\S+)", corpo, re.I)
        for var, destino, valor in tratados:
            alvo = parametro(var.split(".")[-1])
            if parametro(destino.split(".")[-1]).lower() != alvo.lower():
                continue                         # o LET mexe em outra variável: não é tratamento de NULL
            for e in entradas:
                if e.nome.lower() == alvo.lower():
                    e.aceita_nulo, e.se_nulo = True, valor

        # d) regra de negócio com código de erro: IF p_val1 < 0 OR p_val2 < 0 THEN RETURN -1
        #    vira limite da faixa válida (mínimo 0) e o oráculo passa a esperar "Erro (-1)".
        erro_codigo, limites_regra = "", {}
        regra = r"\bIF\s+((?:(?!\bTHEN\b|\bIF\b).)+?)\s+THEN\s+RETURN\s+(-?[\w.]+)"
        for condicao, codigo_retorno in re.findall(regra, corpo, re.I | re.S):
            comparacoes = [re.fullmatch(r"([\w.]+)\s*(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)", parte.strip())
                           for parte in re.split(r"\s+OR\s+", condicao.strip(), flags=re.I)]
            if not all(comparacoes):
                continue                         # só regras do tipo "x < N OR y > M"
            for comparacao in comparacoes:
                var, op, n = comparacao.groups()
                e = next((x for x in entradas if x.nome.lower() == parametro(var.split(".")[-1]).lower()), None)
                if e is None or not e.tipo:
                    continue
                eps = calcular_epsilon(e)[0] or Decimal(0)
                lim = limites_regra.setdefault(e.nome, {})
                if op == "<":                    # x < N é erro → válido a partir de N
                    e.minimo = lim["min"] = n
                elif op == "<=":                 # x <= N é erro → válido a partir de N + ε
                    e.minimo = lim["min"] = fmt(Decimal(n) + eps)
                elif op == ">":                  # x > N é erro → válido até N
                    e.maximo = lim["max"] = n
                else:                            # x >= N é erro → válido até N − ε
                    e.maximo = lim["max"] = fmt(Decimal(n) - eps)
            erro_codigo = codigo_retorno
            break

        # e) saída: RETURN <variável declarada>; o LET que a calcula vira a regra (oráculo)
        saida, formula = None, ""
        for retorno in re.findall(r"\bRETURN\s+(\w+)", corpo, re.I):
            if retorno.lower() in locais:
                saida = locais[retorno.lower()]
                let = re.search(rf"\bLET\s+{retorno}\s*=\s*(.+)", corpo, re.I)
                formula = let.group(1).strip() if let else ""
                break
        formula = re.sub(r"\b\w+\b", lambda m: parametro(m.group()), formula)   # p_val1 → val_param1
        unidades.append(Unidade(nome, entradas, formula, saida, erro_codigo, limites_regra))
    return unidades


# ═══════════════════════════════════════════════════════════════════════════
# 4. Épsilon, domínio do tipo e fronteiras
# ═══════════════════════════════════════════════════════════════════════════
def numero(texto, tipo: str = "DECIMAL"):
    """Texto → número exato. Aceita 1234.56, 1234,56 e 1.234,56."""
    t = str(texto).strip().replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t) if tipo == "FLOAT" else Decimal(t)
    except (ValueError, InvalidOperation):
        raise ValueError(f"'{texto}' não é um número válido") from None


def _casas(x: Decimal) -> int:
    return max(0, -x.as_tuple().exponent)


def calcular_epsilon(e: Entrada):
    """ε = a menor variação que o tipo representa. Devolve (ε, explicação)."""
    if e.tipo in LIMITES_INTEIROS:
        return Decimal(1), "inteiro: não existe valor entre X e X + 1 → ε = 1"
    if e.tipo == "CHAR":
        return Decimal(1), "texto: a fronteira é o tamanho → ε = 1 caractere"
    if e.tipo == "FLOAT":
        return None, "ponto flutuante: ε = ulp(X), a distância até o próximo float"
    if e.tipo == "DECIMAL":
        if e.casas is not None:
            return Decimal(1).scaleb(-e.casas), f"{e.casas} casa(s) decimal(is) → ε = 10^-{e.casas}"
        # escala não declarada: usa as casas dos limites digitados (ex.: 18.5 → 0.1)
        s = max([_casas(numero(v)) for v in (e.minimo, e.maximo) if not _vazio(v)] or [0])
        return Decimal(1).scaleb(-s), f"escala não declarada; pelos limites, {s} casa(s) → ε = 10^-{s}"
    raise ValueError(f"escolha o tipo da variável '{e.nome}' na tabela")


def dominio_do_tipo(e: Entrada, eps):
    """Menor e maior valor que o TIPO consegue guardar (no Informix)."""
    if e.tipo in LIMITES_INTEIROS:
        return tuple(Decimal(x) for x in LIMITES_INTEIROS[e.tipo])
    if e.tipo == "CHAR":
        return Decimal(0), Decimal(e.tamanho or 1)          # tamanho de 0 a n
    if e.tipo == "FLOAT":
        return -sys.float_info.max, sys.float_info.max
    teto = Decimal(10) ** ((e.tamanho or 16) - _casas(eps)) - eps   # DECIMAL(12,2) → 9999999999.99
    return -teto, teto


@dataclass
class Faixa:
    """Entrada pronta para as contas: limites numéricos e ε."""
    entrada: Entrada
    minimo: object       # Decimal (float em FLOAT); em CHAR é o tamanho
    maximo: object
    epsilon: object      # Decimal; None em FLOAT (lá o ε muda com X)
    regra: str           # como o ε foi calculado
    aviso: str = ""
    erro_min: str = ""   # código que o programa devolve abaixo do mínimo (ex.: "-1"), se a regra estiver no código
    erro_max: str = ""   # idem, acima do máximo


def resolver(e: Entrada) -> Faixa:
    """Junta tipo + limites da regra de negócio: devolve a faixa válida e o ε."""
    eps, regra = calcular_epsilon(e)
    lo_tipo, hi_tipo = dominio_do_tipo(e, eps)
    conversao = "FLOAT" if e.tipo == "FLOAT" else "DECIMAL"
    padrao_lo = Decimal(1) if e.tipo == "CHAR" else lo_tipo   # CHAR: exige 1 caractere
    lo = padrao_lo if _vazio(e.minimo) else numero(e.minimo, conversao)
    hi = hi_tipo if _vazio(e.maximo) else numero(e.maximo, conversao)
    if lo > hi:
        raise ValueError(f"'{e.nome}': o limite inferior é maior que o superior")
    if eps is not None:                    # 50 vira 50.00 quando ε = 0.01
        lo, hi = _no_passo(lo, eps), _no_passo(hi, eps)
    aviso = ""
    if lo < lo_tipo or hi > hi_tipo:
        aviso = (f"'{e.nome}': a regra vai de {fmt(lo)} a {fmt(hi)}, mas {e.tipo_txt()} só guarda "
                 f"de {fmt(lo_tipo)} a {fmt(hi_tipo)} — possível defeito de especificação.")
    return Faixa(e, lo, hi, eps, regra, aviso)


def _no_passo(x: Decimal, eps: Decimal) -> Decimal:
    ajustado = x.quantize(eps)
    return ajustado if ajustado == x else x


def vizinhos(f: Faixa, x):
    """(X − ε, X, X + ε). Em FLOAT: o float imediatamente anterior e o posterior."""
    if f.epsilon is None:
        return math.nextafter(x, -math.inf), x, math.nextafter(x, math.inf)
    return x - f.epsilon, x, x + f.epsilon


def _texto(tamanho) -> str:
    """Texto de teste com o tamanho pedido: '1234567890123...' (fácil de contar)."""
    n = max(0, int(tamanho))
    return ("1234567890" * (n // 10 + 1))[:n]


def _valor(f: Faixa, medida):
    """Número/tamanho → valor que vai no caso de teste (em CHAR vira texto)."""
    return _texto(medida) if f.entrada.tipo == "CHAR" else medida


def _medida(v):
    return len(v) if isinstance(v, str) else v


def valido(f: Faixa, v) -> bool:
    if v is NULO:
        return f.entrada.aceita_nulo
    return f.minimo <= _medida(v) <= f.maximo


def tipico(f: Faixa, deslocamento: int = 0):
    """Representante da classe válida: meio da faixa, longe de 0 e das fronteiras.
    O deslocamento dá um valor diferente para cada variável — valores iguais
    mascaram defeitos (trocar p_val2 por p_val3 não mudaria o resultado)."""
    e = f.entrada
    if not _vazio(e.tipico):
        v = e.tipico if e.tipo == "CHAR" else numero(e.tipico, "FLOAT" if e.tipo == "FLOAT" else "DECIMAL")
        if not valido(f, v):
            raise ValueError(f"o valor típico de '{e.nome}' está fora da faixa válida")
        return v
    lo, hi = f.minimo, f.maximo
    if lo < 0 < hi:
        lo = type(lo)(0)
    hi = min(hi, lo + 100)
    meio = (lo + hi) / 2 + (0 if e.tipo == "CHAR" else deslocamento)
    meio = max(f.minimo, min(f.maximo, meio))
    if f.epsilon is not None:
        meio = meio.quantize(f.epsilon, rounding=ROUND_HALF_UP)
    return _valor(f, meio)


# ═══════════════════════════════════════════════════════════════════════════
# 5. PCE — Particionamento em Classes de Equivalência
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class Classe:
    id: str
    faixa: Faixa
    valida: bool
    condicao: str
    representante: object
    posicao: str         # "dentro", "abaixo", "acima" ou "nulo"


def classes_equivalencia(faixas, tipicos, saida_faixa=None) -> list:
    """Por entrada: 1 classe válida (dentro da faixa), 2 inválidas (abaixo e acima)
    e a classe NULL (válida só se o NULL é tratado). Se houver regra de saída,
    a SAÍDA também ganha classes: dentro do tipo ou estouro."""
    classes = []

    def nova(f, valida, condicao, representante, posicao):
        classes.append(Classe(f"CE{len(classes) + 1}", f, valida, condicao, representante, posicao))

    for f in faixas:
        e = f.entrada
        x = f"tamanho({e.nome})" if e.tipo == "CHAR" else e.nome
        nova(f, True, f"{fmt(f.minimo)} ≤ {x} ≤ {fmt(f.maximo)}", tipicos[e.nome], "dentro")
        # o representante inválido fica LONGE da fronteira (a fronteira é papel da AVL)
        if e.tipo == "CHAR":
            if f.minimo > 0:
                nova(f, False, f"{x} < {fmt(f.minimo)}", "", "abaixo")
            nova(f, False, f"{x} > {fmt(f.maximo)}", _texto(f.maximo + 10), "acima")
        else:
            nova(f, False, f"{x} < {fmt(f.minimo)}", f.minimo - _longe(f), "abaixo")
            nova(f, False, f"{x} > {fmt(f.maximo)}", f.maximo + _longe(f), "acima")
        if e.aceita_nulo:
            nova(f, True, f"{e.nome} = NULL (aceito: vira {e.se_nulo})", NULO, "nulo")
        else:
            nova(f, False, f"{e.nome} = NULL (não aceito)", NULO, "nulo")

    if saida_faixa is not None:
        s, nome = saida_faixa, f"{saida_faixa.entrada.nome} (saída)"
        nova(s, True, f"{fmt(s.minimo)} ≤ {nome} ≤ {fmt(s.maximo)}", NULO, "dentro")
        nova(s, False, f"{nome} < {fmt(s.minimo)} (estouro)", NULO, "abaixo")
        nova(s, False, f"{nome} > {fmt(s.maximo)} (estouro)", NULO, "acima")
    return classes


def _longe(f: Faixa):
    """Distância 'confortável' da fronteira: meia largura da faixa, no máximo 100 e no mínimo ε.
    Ex.: idade de 18 a 65 → -6 e 89; valor ≥ 0,00 → -100,00 (o 'Exterior' do manual)."""
    meia = f.maximo / 2 - f.minimo / 2          # assim não estoura em FLOAT
    if f.epsilon is None:
        return min(meia, 100.0) or 1.0
    return max(min(meia, Decimal(100)).quantize(f.epsilon, rounding=ROUND_HALF_UP), f.epsilon)


def _classe_de(classes, f, v) -> str:
    """Em qual classe de equivalência o valor v cai?"""
    if v is NULO:
        posicao = "nulo"
    else:
        m = _medida(v)
        posicao = "abaixo" if m < f.minimo else "acima" if m > f.maximo else "dentro"
    return next((c.id for c in classes if c.faixa is f and c.posicao == posicao), "")


# ═══════════════════════════════════════════════════════════════════════════
# 6. Oráculo — o resultado que a ESPECIFICAÇÃO manda esperar
# ═══════════════════════════════════════════════════════════════════════════
_OPERACOES = {ast.Add: operator.add, ast.Sub: operator.sub,
              ast.Mult: operator.mul, ast.Div: operator.truediv}


def avaliar(formula: str, valores: dict) -> Decimal:
    """Calcula a fórmula com Decimal. Só aceita + - * / e parênteses (nada de eval)."""
    def calc(no):
        if isinstance(no, ast.BinOp) and type(no.op) in _OPERACOES:
            return _OPERACOES[type(no.op)](calc(no.left), calc(no.right))
        if isinstance(no, ast.UnaryOp) and isinstance(no.op, (ast.UAdd, ast.USub)):
            return -calc(no.operand) if isinstance(no.op, ast.USub) else calc(no.operand)
        if isinstance(no, ast.Constant) and type(no.value) in (int, float):
            return Decimal(str(no.value))
        if isinstance(no, (ast.Name, ast.Attribute)):        # p_val1 ou mr_item.val_param1
            nome = (no.id if isinstance(no, ast.Name) else no.attr).lower()
            if nome not in valores:
                raise ValueError(f"'{nome}' não está na tabela de entradas")
            return valores[nome]
        raise ValueError("use só números, variáveis, + - * / e parênteses")
    try:
        arvore = ast.parse(formula.strip(), mode="eval")
    except SyntaxError:
        raise ValueError("a fórmula tem erro de sintaxe") from None
    return calc(arvore.body)


def _contexto(valores: dict, faixas) -> dict:
    """Valores do caso → números para a fórmula (o NULL vira o valor tratado)."""
    contexto = {}
    for f in faixas:
        v = valores[f.entrada.nome]
        if v is NULO:
            v = numero(f.entrada.se_nulo)
        elif isinstance(v, float):
            v = Decimal(repr(v))
        contexto[f.entrada.nome.lower()] = v
    return contexto


def resultado_esperado(valores, faixas, formula, saida_faixa):
    """Devolve (texto do resultado esperado, valor da saída ou None)."""
    problemas, codigos = [], set()
    for f in faixas:
        v = valores[f.entrada.nome]
        if valido(f, v):
            continue
        if v is NULO:
            problemas.append(f"{f.entrada.nome} NULL")
            codigos.add("")
        elif _medida(v) < f.minimo:
            problemas.append(f"{f.entrada.nome} < {fmt(f.minimo)}")
            codigos.add(f.erro_min)
        else:
            problemas.append(f"{f.entrada.nome} > {fmt(f.maximo)}")
            codigos.add(f.erro_max)
    if problemas:
        if len(codigos) == 1 and "" not in codigos:      # só violou a regra que o código trata
            return f"❌ Erro ({codigos.pop()}) — " + ", ".join(problemas), None
        return "❌ Rejeitar (" + ", ".join(problemas) + ")", None
    if _vazio(formula):
        return "✅ Aceitar", None
    try:
        r = avaliar(formula, _contexto(valores, faixas))
    except ZeroDivisionError:
        return "⚠️ Erro esperado: divisão por zero", None
    if saida_faixa is None:
        return f"✅ Aceitar → resultado {_resumir(r)}", r
    s = saida_faixa
    arredondado = r.quantize(s.epsilon, rounding=ROUND_HALF_UP) if s.epsilon is not None else r
    if not s.minimo <= arredondado <= s.maximo:
        return (f"⚠️ Estouro: {_resumir(arredondado)} não cabe em {s.entrada.tipo_txt()} — "
                f"o sistema deve tratar o erro"), arredondado
    nota = f" (arredondado de {_resumir(r)})" if arredondado != r else ""
    return f"✅ Aceitar → retorna {_resumir(arredondado)}{nota}", arredondado


def _resumir(r: Decimal) -> str:
    """Resultados de divisão podem ter dezenas de casas: mostra só 10."""
    if r == 0 or _casas(r) <= 10:
        return fmt(r)
    if abs(r) < Decimal("1e-6"):
        return f"≈ {r:.6e}"
    return "≈ " + fmt(r.quantize(Decimal("1e-10"), rounding=ROUND_HALF_UP).normalize())


# ═══════════════════════════════════════════════════════════════════════════
# 7. AVL — Análise do Valor Limite  +  montagem dos casos de teste
# ═══════════════════════════════════════════════════════════════════════════
_PONTOS = ("− ε", "", "+ ε")


def _fronteiras(f):
    return (("mín", f.minimo), ("máx", f.maximo))


def valores_limite(faixas, saida_faixa=None) -> list:
    """Tabela da AVL: para cada fronteira X, os valores X − ε, X e X + ε."""
    linhas = []
    for f in faixas + ([saida_faixa] if saida_faixa else []):
        nome = f.entrada.nome + (" (saída)" if f is saida_faixa else "")
        for nome_x, X in _fronteiras(f):
            celulas = []
            for medida in vizinhos(f, X):
                if f.entrada.tipo == "CHAR":
                    celulas.append("— (impossível)" if medida < 0 else
                                   f"{int(medida)} car. {'✅' if valido(f, _valor(f, medida)) else '❌'}")
                else:
                    celulas.append(f"{fmt(medida)} {'✅' if f.minimo <= medida <= f.maximo else '❌'}")
            linhas.append({"Variável": nome, "Fronteira": f"{nome_x} = {fmt(X)}", "ε": fmt_eps(f, X),
                           "X − ε": celulas[0], "X": celulas[1], "X + ε": celulas[2]})
    return linhas


def _limites_da_saida(faixas, tipicos, formula, s) -> list:
    """AVL na SAÍDA: para cada entrada em que a regra é linear (saída = a·x + b),
    calcula o x que leva a saída exatamente à fronteira Y e testa os vizinhos dele."""
    planejados = []
    if s.epsilon is None:                      # saída FLOAT: fica só com a AVL das entradas
        return planejados
    for f in faixas:
        if f.epsilon is None or f.entrada.tipo == "CHAR":
            continue

        def g(x):
            return avaliar(formula, _contexto({**tipicos, f.entrada.nome: x}, faixas))
        try:
            b, um, dois = g(Decimal(0)), g(Decimal(1)), g(Decimal(2))
        except (ValueError, TypeError, ArithmeticError):
            continue
        a = um - b
        if a == 0 or dois - um != a:          # não é linear nesta variável
            continue
        for nome_y, Y in _fronteiras(s):
            alvo = (Y - b) / a                 # X = o valor da entrada que faz a saída valer Y
            piso = alvo.quantize(f.epsilon, rounding=ROUND_FLOOR)
            if piso == alvo:                   # dá para acertar Y em cheio
                x_txt = f"X = {fmt(alvo)}"
                pontos = zip(("X − ε", "X", "X + ε"), vizinhos(f, piso))
            else:                              # Y cai entre dois valores possíveis da entrada
                x_txt = f"X ≈ {fmt(alvo.quantize(f.epsilon / 100))}"
                pontos = (("X arredondado p/ baixo", piso), ("X arredondado p/ cima", piso + f.epsilon))
            for rotulo, x in pontos:
                if f.minimo <= x <= f.maximo:  # a entrada é válida; quem está na fronteira é a saída
                    objetivo = f"saída no {nome_y} ({fmt(Y)}): {f.entrada.nome} = {rotulo}, com {x_txt}"
                    planejados.append(("AVL saída", objetivo, {**tipicos, f.entrada.nome: x}, []))
    return planejados


def casos_de_teste(faixas, classes, tipicos, formula, saida_faixa) -> list:
    nomes = [f.entrada.nome for f in faixas]
    planejados = []   # (técnica, objetivo, valores, classes cobertas)

    # PCE — um caso cobre todas as classes válidas "dentro da faixa" (valores típicos)
    dentro = [c.id for c in classes if c.posicao == "dentro" and c.faixa is not saida_faixa]
    planejados.append(("PCE", "todas as entradas válidas (valores típicos)", dict(tipicos), dentro))
    # PCE — as classes NULL válidas juntas num caso só
    nulos_ok = [c for c in classes if c.posicao == "nulo" and c.valida]
    if nulos_ok:
        valores = {**tipicos, **{c.faixa.entrada.nome: NULO for c in nulos_ok}}
        planejados.append(("PCE", "NULL nas entradas que aceitam NULL", valores, [c.id for c in nulos_ok]))
    # PCE — UMA classe inválida por caso (duas juntas podem mascarar um defeito)
    for c in classes:
        if not c.valida and c.faixa is not saida_faixa:
            valores = {**tipicos, c.faixa.entrada.nome: c.representante}
            planejados.append(("PCE", f"inválida: {c.condicao}", valores, [c.id]))
    # AVL — X − ε, X e X + ε em cada fronteira, variando uma entrada por vez
    for f in faixas:
        for nome_x, X in _fronteiras(f):
            for ponto, medida in zip(_PONTOS, vizinhos(f, X)):
                if f.entrada.tipo == "CHAR" and medida < 0:
                    continue
                v = _valor(f, medida)
                objetivo = f"{f.entrada.nome} = {nome_x} {ponto}".strip()
                planejados.append(("AVL", objetivo, {**tipicos, f.entrada.nome: v}, [_classe_de(classes, f, v)]))
    # AVL na saída — a fronteira da regra de negócio
    if saida_faixa is not None and not _vazio(formula):
        planejados += _limites_da_saida(faixas, tipicos, formula, saida_faixa)

    casos, por_valores = [], {}
    for tecnica, objetivo, valores, cobre in planejados:
        chave = tuple(fmt(valores[n]) for n in nomes)
        if chave in por_valores:              # mesmo caso já planejado: só anota
            caso = por_valores[chave]
            if tecnica not in caso["Técnica"]:
                caso["Técnica"] += " + " + tecnica
            caso["Objetivo"] += "; " + objetivo
            novas = [c for c in cobre if c and c not in caso["Classes cobertas"]]
            caso["Classes cobertas"] = ", ".join(filter(None, [caso["Classes cobertas"], *novas]))
            continue
        esperado, valor_saida = resultado_esperado(valores, faixas, formula, saida_faixa)
        if valor_saida is not None and saida_faixa is not None:
            cobre = cobre + [_classe_de(classes, saida_faixa, valor_saida)]
        caso = {"CT": f"CT{len(casos) + 1:02d}", "Técnica": tecnica, "Objetivo": objetivo}
        caso.update({n: fmt(valores[n]) for n in nomes})
        caso["Classes cobertas"] = ", ".join(c for c in cobre if c)
        caso["Resultado esperado"] = esperado
        por_valores[chave] = caso
        casos.append(caso)
    return casos


# ═══════════════════════════════════════════════════════════════════════════
# 8. Formatação e ponto de entrada
# ═══════════════════════════════════════════════════════════════════════════
def fmt(v) -> str:
    """Formata sem perder precisão (nada de 1E+10 ou 0.30000000000000004)."""
    if v is NULO:
        return "NULL"
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, Decimal):
        return format(abs(v) if v == 0 else v, "f")   # abs: evita "-0.00"
    return repr(v)


def fmt_eps(f: Faixa, X=None) -> str:
    if f.epsilon is None:
        return f"ulp = {math.ulp(X):.3g}" if X is not None else "ulp(X)"
    return f"{fmt(f.epsilon)} car." if f.entrada.tipo == "CHAR" else fmt(f.epsilon)


def _origem(f: Faixa, lado: str) -> str:
    if (f.erro_min if lado == "min" else f.erro_max):
        return f"regra do código (erro {f.erro_min or f.erro_max})"
    informado = f.entrada.minimo if lado == "min" else f.entrada.maximo
    return "informado na tabela" if not _vazio(informado) else (
        "padrão: 1 caractere" if f.entrada.tipo == "CHAR" and lado == "min" else "limite do tipo")


def pontos_fronteira(faixas, tipicos, formula, saida_faixa) -> list:
    """Os 4 pontos do manual da Sprint 1 em cada fronteira X:
    On (X, na fronteira) · Off (o 1º ponto fora: X ∓ ε) ·
    Interior (bem dentro: X ± 100) · Exterior (bem fora: X ∓ 100)."""
    linhas = []
    for f in faixas:
        if f.entrada.tipo == "CHAR":
            continue                              # a régua do manual é numérica
        for lado, X, sentido in (("min", f.minimo, 1), ("max", f.maximo, -1)):
            menos, _, mais = vizinhos(f, X)
            fora = menos if sentido == 1 else mais
            d = Decimal(100) if f.epsilon is not None else 100.0
            dentro = X + sentido * d
            if not f.minimo <= dentro <= f.maximo:  # faixa estreita: usa o meio
                dentro = tipicos[f.entrada.nome]
            pontos = (("On", X, "exatamente na fronteira"), ("Off", fora, "1º ponto fora (X ∓ ε)"),
                      ("Interior", dentro, "bem dentro da região válida"),
                      ("Exterior", X - sentido * d, "bem dentro da região inválida"))
            for ponto, v, condicao in pontos:
                esperado, _ = resultado_esperado({**tipicos, f.entrada.nome: v}, faixas, formula, saida_faixa)
                linhas.append({
                    "Variável": f.entrada.nome,
                    "Fronteira": f"{'mín' if lado == 'min' else 'máx'} = {fmt(X)} ({_origem(f, lado)})",
                    "Ponto": ponto,
                    "Valor": fmt(v),
                    "Condição": condicao,
                    "Válido?": "✅" if valido(f, v) else "❌",
                    "Resultado esperado": esperado,
                })
    return linhas


def analisar(entradas: list, formula: str = "", saida: Entrada | None = None, erro: dict | None = None) -> dict:
    """Aplica PCE + AVL nas entradas e devolve as tabelas prontas para a tela.
    erro: regra de negócio do código, ex.: {"codigo": "-1", "limites": {"val_param1": {"min": "0"}}}."""
    with localcontext() as ctx:
        ctx.prec = 60   # folga para DECIMAL(32): nenhuma conta é arredondada no meio
        entradas = [e for e in entradas if e.nome]
        if not entradas:
            raise ValueError("não há entradas para analisar — adicione variáveis na tabela")
        repetidas = {e.nome for e in entradas if [x.nome for x in entradas].count(e.nome) > 1}
        if repetidas:
            raise ValueError(f"variável repetida na tabela: {', '.join(sorted(repetidas))}")

        faixas = [resolver(e) for e in entradas]
        for f in faixas:   # o limite ainda é o da regra do código? então o esperado é o código de erro
            regra = (erro or {}).get("limites", {}).get(f.entrada.nome, {})
            if "min" in regra and numero(regra["min"]) == f.minimo:
                f.erro_min = erro["codigo"]
            if "max" in regra and numero(regra["max"]) == f.maximo:
                f.erro_max = erro["codigo"]
        tipicos, deslocamento = {}, 0
        for f in faixas:
            tipicos[f.entrada.nome] = tipico(f, deslocamento)
            if f.entrada.tipo != "CHAR":
                deslocamento += 1
        avisos = [f.aviso for f in faixas if f.aviso]

        saida_faixa = None
        if not _vazio(formula):
            try:   # a regra precisa funcionar com os valores típicos
                avaliar(formula, _contexto(tipicos, faixas))
                saida_faixa = resolver(saida) if saida is not None else None
            except (ValueError, TypeError, ArithmeticError) as erro:
                avisos.append(f"Regra da saída ignorada: {erro}.")
                formula = ""

        classes = classes_equivalencia(faixas, tipicos, saida_faixa)
        casos = casos_de_teste(faixas, classes, tipicos, formula, saida_faixa)
        cobertura = {c.id: [k["CT"] for k in casos if c.id in k["Classes cobertas"].split(", ")]
                     for c in classes}

        todas = faixas + ([saida_faixa] if saida_faixa else [])
        return {
            "epsilon": [{
                "Variável": f.entrada.nome + (" (saída)" if f is saida_faixa else ""),
                "Tipo": f.entrada.tipo_txt(),
                "ε": fmt_eps(f, f.maximo),
                "Como o ε foi calculado": f.regra,
                "Faixa válida": f"{fmt(f.minimo)} a {fmt(f.maximo)}"
                                + (" caracteres" if f.entrada.tipo == "CHAR" else ""),
                "Origem dos limites": f"mín: {_origem(f, 'min')} · máx: {_origem(f, 'max')}",
            } for f in todas],
            "classes": [{
                "ID": c.id,
                "Variável": c.faixa.entrada.nome + (" (saída)" if c.faixa is saida_faixa else ""),
                "Classe": "válida" if c.valida else "inválida",
                "Condição": c.condicao,
                "Representante": "—" if c.faixa is saida_faixa else fmt(c.representante),
                "Coberta por": ", ".join(cobertura[c.id]) or "⚠️ nenhum caso (pode ser inviável)",
            } for c in classes],
            "limites": valores_limite(faixas, saida_faixa),
            "pontos": pontos_fronteira(faixas, tipicos, formula, saida_faixa),
            "casos": casos,
            "avisos": avisos,
        }
