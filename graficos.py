"""
graficos.py — Desenhos do TestingStudio Web (matplotlib), usados na tela e no PDF
==================================================================================
  regua(...)      a régua da fronteira: On · Off · Interior · Exterior (Sprint 1)
  grafo(...)      o Grafo de Fluxo de Controle com camadas (Sprint 2)
  cobertura(...)  casos de teste por requisito (RTM)
Tudo devolve PNG (bytes). Usa Figure em vez de pyplot: seguro dentro do Streamlit.
"""

import io
import re
from collections import defaultdict

from matplotlib import font_manager
from matplotlib.figure import Figure
from matplotlib.patches import Circle, FancyArrowPatch, Polygon, Rectangle
from matplotlib.path import Path

# paleta (a mesma do PDF)
NAVY, AZUL, VERDE, VERMELHO, AMBAR, ROXO = "#172B4D", "#0052CC", "#00875A", "#DE350B", "#FF8B00", "#5243AA"
CINZA, CINZA_CLARO, BORDA = "#6B778C", "#F4F5F7", "#DFE1E6"
VERDE_CLARO, VERMELHO_CLARO = "#E3FCEF", "#FFEBE6"
COR_NO = {"inicio": ("#E3FCEF", VERDE), "bloco": ("#DEEBFF", AZUL), "decisao": ("#FFF0B3", AMBAR), "fim": ("#EAE6FF", ROXO)}

_disponiveis = {f.name for f in font_manager.fontManager.ttflist}
FONTE = next((f for f in ("Segoe UI", "Calibri", "DejaVu Sans") if f in _disponiveis), "DejaVu Sans")


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=220, bbox_inches="tight", pad_inches=0.06, facecolor="white")
    return buf.getvalue()


def _resultado_curto(texto: str) -> str:
    """'❌ Erro (-1) — val_param1 < 0.00' → 'Erro (-1)';  '✅ Aceitar → retorna 52.00' → 'retorna 52.00'."""
    t = re.sub(r"^[^\w(]+", "", str(texto)).strip()
    if t.startswith("Erro"):
        return t.split(" —")[0]
    if t.startswith("Aceitar"):
        return t.split("→")[-1].strip() if "→" in t else "aceita"
    if t.startswith("Estouro"):
        return "estouro na saída"
    if t.startswith("Rejeitar"):
        return "rejeita (fora do tipo)"
    return t[:22]


# ═══════════════════════════════════════════════════════════════════════════
# Régua da fronteira (Sprint 1)
# ═══════════════════════════════════════════════════════════════════════════
def regua(pontos: list, largura: float = 7.2) -> bytes:
    """Régua como no slide do kickoff: região inválida (vermelha) × válida (verde) e os
    4 pontos com o valor exato e o resultado esperado. Não depende da escala dos números."""
    minimo = pontos[0]["Fronteira"].startswith("mín")
    pos = ({"Exterior": 0.09, "Off": 0.41, "On": 0.5, "Interior": 0.91} if minimo
           else {"Interior": 0.09, "On": 0.5, "Off": 0.59, "Exterior": 0.91})
    fig = Figure(figsize=(largura, 1.75))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(-1.15, 1.0)
    ax.axis("off")

    invalida_x = 0.03 if minimo else 0.5
    valida_x = 0.5 if minimo else 0.03
    ax.add_patch(Rectangle((invalida_x, -0.1), 0.47, 0.2, fc=VERMELHO_CLARO, ec="none"))
    ax.add_patch(Rectangle((valida_x, -0.1), 0.47, 0.2, fc=VERDE_CLARO, ec="none"))
    for x in [i / 100 for i in range(4, 97, 2)]:                           # risquinhos de régua
        ax.plot([x, x], [-0.1, -0.1 + (0.09 if round(x * 100) % 10 == 0 else 0.05)], color=BORDA, lw=0.6)
    ax.plot([0.5, 0.5], [-0.32, 0.32], color=NAVY, lw=1.2, ls=(0, (3, 2)))
    ax.text(invalida_x + 0.235, 0.14, "região inválida", fontsize=7, color=VERMELHO, family=FONTE, ha="center")
    ax.text(valida_x + 0.235, 0.14, "região válida", fontsize=7, color=VERDE, family=FONTE, ha="center")

    for p in pontos:
        x = pos[p["Ponto"]]
        ok = p["Válido?"] == "✅"
        cor = VERDE if ok else VERMELHO
        cor_resultado = AMBAR if "Estouro" in p["Resultado esperado"] else cor
        ax.plot([x], [0], marker="o", ms=9, color=cor, mec="white", mew=1.4, zorder=5)
        # perto da fronteira (On/Off) o texto "abre" para fora, para não encavalar
        if p["Ponto"] in ("On", "Off") and abs(pos["On"] - pos["Off"]) < 0.2:
            ha = "left" if x > (pos["On"] + pos["Off"]) / 2 else "right"
            dx = 0.012 if ha == "left" else -0.012
        else:
            ha, dx = "center", 0
        ax.text(x + dx, 0.5, p["Ponto"], ha=ha, fontsize=9.5, weight="bold", color=NAVY, family=FONTE)
        ax.text(x + dx, 0.3, p["Valor"], ha=ha, fontsize=8, color=CINZA, family=FONTE)
        ax.text(x + dx, -0.42, _resultado_curto(p["Resultado esperado"]), ha=ha, fontsize=7.5, color=cor_resultado,
                family=FONTE, weight="bold")
    on, off = pos["On"], pos["Off"]
    ax.annotate("", xy=(off, -0.78), xytext=(on, -0.78),
                arrowprops=dict(arrowstyle="<|-|>", color=CINZA, lw=0.8, shrinkA=0, shrinkB=0, mutation_scale=7))
    ax.text((on + off) / 2, -1.08, "ε", ha="center", fontsize=10, color=CINZA, family=FONTE)
    ax.text(0.0, 0.88, f"{pontos[0]['Variável']} · fronteira {pontos[0]['Fronteira']}", fontsize=8.5,
            color=NAVY, family=FONTE, weight="bold", va="top")
    return _png(fig)


# ═══════════════════════════════════════════════════════════════════════════
# Grafo de Fluxo de Controle (Sprint 2)
# ═══════════════════════════════════════════════════════════════════════════
def _layout(g):
    """Layout em camadas (Sugiyama): 1) acha as arestas de volta dos laços; 2) camada = caminho
    mais longo desde a entrada; 3) arestas longas ganham nós 'fantasmas' nas camadas do meio;
    4) ordena cada camada pelo baricentro dos vizinhos (menos cruzamentos)."""
    saidas = defaultdict(list)
    for i, a in enumerate(g.arestas):
        saidas[a.origem].append(i)
    for lista in saidas.values():
        lista.sort(key=lambda i: {"V": 0, "F": 2}.get(g.arestas[i].rotulo, 1))
    estado, volta, ordem = {}, set(), []

    def dfs(u):
        estado[u] = 1
        ordem.append(u)
        for i in saidas[u]:
            v = g.arestas[i].destino
            if estado.get(v) == 1:
                volta.add(i)
            elif v not in estado:
                dfs(v)
        estado[u] = 2
    dfs(g.entrada)

    camada = {n: 0 for n in g.nos}
    grau = defaultdict(int)
    for i, a in enumerate(g.arestas):
        if i not in volta:
            grau[a.destino] += 1
    fila = [n for n in g.nos if grau[n] == 0]
    while fila:
        u = fila.pop(0)
        for i in saidas[u]:
            if i not in volta:
                v = g.arestas[i].destino
                camada[v] = max(camada[v], camada[u] + 1)
                grau[v] -= 1
                if grau[v] == 0:
                    fila.append(v)

    pred, succ, fantasmas = defaultdict(list), defaultdict(list), {}
    for i, a in enumerate(g.arestas):
        if i in volta or a.origem == a.destino:
            continue
        cadeia = [a.origem]
        for c in range(camada[a.origem] + 1, camada[a.destino]):
            fantasma = ("f", i, c)
            camada[fantasma] = c
            cadeia.append(fantasma)
        cadeia.append(a.destino)
        fantasmas[i] = cadeia[1:-1]
        for u, v in zip(cadeia, cadeia[1:]):
            succ[u].append(v)
            pred[v].append(u)

    prioridade = {n: k for k, n in enumerate(ordem)}
    camadas = defaultdict(list)
    for n in sorted(camada, key=lambda n: (prioridade.get(n, 10 ** 6), str(n))):
        camadas[camada[n]].append(n)
    posicao = {n: k for c in camadas.values() for k, n in enumerate(c)}

    def media(vizinhos, n):
        return sum(posicao[v] for v in vizinhos) / len(vizinhos) if vizinhos else posicao[n]
    for _ in range(8):                                   # desce e sobe pelo baricentro
        for sentido, lista in ((pred, sorted(camadas)), (succ, sorted(camadas, reverse=True))):
            for c in lista:
                camadas[c].sort(key=lambda n: media(sentido[n], n))
                for k, n in enumerate(camadas[c]):
                    posicao[n] = k
    coords = {n: (k - (len(nos) - 1) / 2, -c) for c, nos in camadas.items() for k, n in enumerate(nos)}
    return coords, volta, fantasmas


def _borda(centro, rumo, raio):
    """Ponto na borda do nó, na direção de 'rumo'."""
    (x, y), (tx, ty) = centro, rumo
    dx, dy = tx - x, ty - y
    d = (dx * dx + dy * dy) ** 0.5 or 1
    return x + dx / d * raio, y + dy / d * raio


def grafo(g, destaque: list | None = None, largura_max: float = 6.6) -> bytes:
    """Desenha o GFC: blocos em círculo, decisões em losango, V/F nas arestas,
    laços contornando pela direita e o caminho escolhido em verde."""
    coords, volta, fantasmas = _layout(g)
    destaque = set(destaque or [])
    r = 0.27
    raio = {k: r * (1.12 if n.tipo == "decisao" else 1) for k, n in g.nos.items()}
    xs = [x for x, _ in coords.values()]
    ys = [y for _, y in coords.values()]

    # rotas das arestas: (vértices, códigos, ponto do rótulo)
    rotas, faixa_direita, pares = {}, defaultdict(int), defaultdict(int)
    for i, a in enumerate(g.arestas):
        p1, p2 = coords[a.origem], coords[a.destino]
        if i in volta or a.origem == a.destino:      # laço: sai pela direita e sobe por fora
            topo, base = max(p1[1], p2[1]), min(p1[1], p2[1])
            no_trecho = [x for (x, y) in coords.values() if base - 0.01 <= y <= topo + 0.01]
            xr = max(no_trecho) + 0.75 + 0.32 * faixa_direita[a.destino]
            faixa_direita[a.destino] += 1
            # desce até o "corredor" entre as camadas, corre para a direita e sobe por fora
            corredor = p1[1] - 0.5
            inicio = (p1[0] + raio[a.origem] * 0.6, p1[1] - raio[a.origem] * 0.8)
            meio = ((p1[0] + xr) / 2, corredor)
            fim = (p2[0] + raio[a.destino], p2[1])
            rotas[i] = ([inicio, (inicio[0] + 0.05, corredor), (inicio[0] + 0.2, corredor), meio,
                         (xr, corredor), (xr, p2[1]), fim], [1, 4, 4, 4, 4, 4, 4],
                        (meio[0], corredor - 0.13))
            continue
        meio = fantasmas.get(i, [])
        pontos = [coords[f] for f in meio]
        alvo1 = pontos[0] if pontos else p2
        alvo2 = pontos[-1] if pontos else p1
        inicio = _borda(p1, alvo1, raio[a.origem])
        fim = _borda(p2, alvo2, raio[a.destino])
        repeticao = pares[(a.origem, a.destino)]
        pares[(a.origem, a.destino)] += 1
        if pontos:                                   # curva suave passando pelos fantasmas
            verts, codes = [inicio], [1]
            for k, c in enumerate(pontos):
                prox = ((c[0] + pontos[k + 1][0]) / 2, (c[1] + pontos[k + 1][1]) / 2) if k + 1 < len(pontos) else fim
                verts += [c, prox]
                codes += [3, 3]
        elif repeticao:                              # aresta paralela: curva para o lado
            mx, my = (inicio[0] + fim[0]) / 2, (inicio[1] + fim[1]) / 2
            dx, dy = fim[0] - inicio[0], fim[1] - inicio[1]
            lado = 0.35 * (1 if repeticao % 2 else -1)
            verts, codes = [inicio, (mx - dy * lado, my + dx * lado), fim], [1, 3, 3]
        else:
            verts, codes = [inicio, fim], [1, 2]
        t = 0.3
        rotulo = (inicio[0] + (verts[1][0] - inicio[0]) * t, inicio[1] + (verts[1][1] - inicio[1]) * t)
        rotas[i] = (verts, codes, rotulo)

    todos_x = xs + [v[0] for verts, _, _ in rotas.values() for v in verts]
    largura_dados = max(todos_x) - min(todos_x) + 1.2
    altura_dados = max(ys) - min(ys) + 1.2
    escala = min(0.78, largura_max / largura_dados)
    fig = Figure(figsize=(max(2.4, largura_dados * escala), max(1.4, altura_dados * escala)))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(min(todos_x) - 0.6, max(todos_x) + 0.6)
    ax.set_ylim(min(ys) - 0.6, max(ys) + 0.6)

    for i, (verts, codes, ponto_rotulo) in rotas.items():
        a = g.arestas[i]
        cor, lw = (VERDE, 2.4) if i in destaque else ("#8993A4", 1.1)
        ax.add_patch(FancyArrowPatch(path=Path(verts, codes), arrowstyle="-|>", mutation_scale=9,
                                     color=cor, lw=lw, zorder=1, joinstyle="round", capstyle="round"))
        if a.rotulo:
            cor_rot = {"V": VERDE, "F": VERMELHO}.get(a.rotulo, CINZA)
            ax.text(*ponto_rotulo, a.rotulo[:10], fontsize=6.5, color=cor_rot, ha="center", va="center",
                    family=FONTE, weight="bold", zorder=4,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none"))

    for k, n in g.nos.items():
        x, y = coords[k]
        fundo, borda = COR_NO[n.tipo]
        em_destaque = destaque and (k == g.entrada or any(g.arestas[i].destino == k for i in destaque))
        if n.tipo == "decisao":
            forma = Polygon([(x, y + r * 1.15), (x + r * 1.15, y), (x, y - r * 1.15), (x - r * 1.15, y)],
                            closed=True, fc=fundo, ec=VERDE if em_destaque else borda, lw=2.2 if em_destaque else 1.4, zorder=2)
        else:
            forma = Circle((x, y), r, fc=fundo, ec=VERDE if em_destaque else borda, lw=2.2 if em_destaque else 1.4, zorder=2)
        ax.add_patch(forma)
        if k == g.saida:
            ax.add_patch(Circle((x, y), r * 0.8, fc="none", ec=borda, lw=0.9, zorder=3))
        ax.text(x, y, f"N{k}", ha="center", va="center", fontsize=8, weight="bold", color=NAVY, family=FONTE, zorder=4)
    return _png(fig)


def legenda_grafo() -> list:
    return [("início", COR_NO["inicio"]), ("bloco", COR_NO["bloco"]), ("decisão", COR_NO["decisao"]), ("fim", COR_NO["fim"])]


# ═══════════════════════════════════════════════════════════════════════════
# Cobertura da RTM (aula de 14/10)
# ═══════════════════════════════════════════════════════════════════════════
def cobertura(m: dict, largura: float = 6.8) -> bytes:
    """Barras horizontais: quantos casos de teste cobrem cada requisito (vermelho = nenhum)."""
    linhas = m["linhas"][::-1]
    fig = Figure(figsize=(largura, 0.42 * len(linhas) + 0.5))
    ax = fig.subplots()
    ids = [l["Requisito"] for l in linhas]
    qtd = [l["Nº de CTs"] for l in linhas]
    ax.barh(ids, qtd, color=["#4C9AFF" if q else VERMELHO for q in qtd], height=0.42)
    for y, q in enumerate(qtd):
        ax.text(q + 0.05, y, f"{q} caso(s)" if q else "sem caso de teste", va="center", fontsize=7.5,
                color=NAVY if q else VERMELHO, family=FONTE)
    ax.set_xlim(0, max(qtd + [1]) * 1.35)
    for lado in ("top", "right", "bottom"):
        ax.spines[lado].set_visible(False)
    ax.spines["left"].set_color(BORDA)
    ax.tick_params(axis="x", bottom=False, labelbottom=False)
    ax.tick_params(axis="y", labelsize=8, colors=NAVY, length=0)
    for rotulo in ax.get_yticklabels():
        rotulo.set_family(FONTE)
    return _png(fig)
