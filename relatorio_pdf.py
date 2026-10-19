"""
relatorio_pdf.py — Relatório em PDF do TestingStudio Web
=========================================================
Visual de relatório técnico: capa com resumo, sumário clicável, cabeçalho e rodapé,
seções numeradas, cartões de indicadores, caixas de achados e tabelas zebradas.
Fontes: Segoe UI + Consolas (Windows) ou DejaVu (vem com o matplotlib) nos outros sistemas.
Os desenhos (régua, grafo, cobertura) vêm de graficos.py — os mesmos da tela.
"""

import logging
import os
import re
from datetime import datetime
from io import BytesIO

import matplotlib
from fontTools.ttLib import TTFont
from fpdf import FPDF
from fpdf.fonts import FontFace
from PIL import Image

import graficos as gr
import rtm

logging.getLogger("fontTools").setLevel(logging.ERROR)   # avisos da tabela MERG da Segoe UI

# ─── Fontes ────────────────────────────────────────────────────────────────
_WIN = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_MPL = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")


def _primeira(*caminhos):
    return next(c for c in caminhos if os.path.exists(c))


FONTES = {
    ("Texto", ""): _primeira(os.path.join(_WIN, "segoeui.ttf"), os.path.join(_MPL, "DejaVuSans.ttf")),
    ("Texto", "B"): _primeira(os.path.join(_WIN, "segoeuib.ttf"), os.path.join(_MPL, "DejaVuSans-Bold.ttf")),
    ("Texto", "I"): _primeira(os.path.join(_WIN, "segoeuii.ttf"), os.path.join(_MPL, "DejaVuSans-Oblique.ttf")),
    ("Semi", ""): _primeira(os.path.join(_WIN, "seguisb.ttf"), os.path.join(_MPL, "DejaVuSans-Bold.ttf")),
    ("Mono", ""): _primeira(os.path.join(_WIN, "consola.ttf"), os.path.join(_MPL, "DejaVuSansMono.ttf")),
    ("Reserva", ""): os.path.join(_MPL, "DejaVuSans.ttf"),          # símbolos que faltarem (✔ ✘ ⚠)
    ("Reserva", "B"): os.path.join(_MPL, "DejaVuSans-Bold.ttf"),
}
_GLIFOS = set(TTFont(FONTES[("Texto", "")]).getBestCmap()) | set(TTFont(FONTES[("Reserva", "")]).getBestCmap())
_TROCAS = {"✅": "✔", "❌": "✘", "⚠️": "⚠", "❓": "?", "\ufe0f": "", "📌": "", "🧠": "", "🤝": ""}

# ─── Paleta ────────────────────────────────────────────────────────────────
NAVY, AZUL, VERDE, VERMELHO = (23, 43, 77), (0, 82, 204), (0, 135, 90), (222, 53, 11)
AMBAR, ROXO, CINZA, TEXTO = (178, 98, 0), (82, 67, 170), (107, 119, 140), (37, 46, 64)
CLARO, BORDA = (244, 245, 247), (223, 225, 230)
FUNDO = {"info": (233, 242, 255), "sucesso": (227, 252, 239), "alerta": (255, 247, 230), "erro": (255, 235, 230)}
COR = {"info": AZUL, "sucesso": VERDE, "alerta": AMBAR, "erro": VERMELHO}


def _limpo(texto) -> str:
    """Troca emojis por símbolos que a fonte tem e tira o que nenhuma fonte desenha."""
    s = str(texto)
    for de, para in _TROCAS.items():
        s = s.replace(de, para)
    return "".join(c for c in s if c in "\n\t" or ord(c) in _GLIFOS)


def _status(valor: str):
    """Cor do texto da célula: ✔/válida em verde, ✘/inválida em vermelho, ⚠ em âmbar."""
    v = valor.strip()
    if v.startswith("✔") or v in ("válida", "válido"):
        return FontFace(color=VERDE)
    if v.startswith("✘") or v in ("inválida", "inválido"):
        return FontFace(color=VERMELHO)
    if v.startswith("⚠"):
        return FontFace(color=AMBAR)
    return None


class Relatorio(FPDF):
    def __init__(self, aluno: str = ""):
        super().__init__("P", "mm", "A4")
        for (familia, estilo), caminho in FONTES.items():
            self.add_font(familia, estilo, caminho)
        self.set_fallback_fonts(["Reserva"], exact_match=False)
        self.set_margins(18, 21, 18)
        self.set_auto_page_break(True, margin=17)
        self.aluno = aluno.strip()
        self.secao_atual = ""
        self.set_title("TestingStudio Web — Relatório de Testes")
        self.set_author(self.aluno or "TestingStudio Web")
        self.set_creator("TestingStudio Web")

    # ─── moldura ──────────────────────────────────────────────────────────
    def header(self):
        if self.page_no() == 1:
            return
        self.set_y(9)
        self.set_font("Semi", "", 7.5)
        self.set_text_color(*AZUL)
        self.cell(0, 5, "TESTINGSTUDIO WEB")
        self.set_x(self.l_margin)
        self.set_font("Texto", "", 7.5)
        self.set_text_color(*CINZA)
        self.cell(0, 5, _limpo(self.secao_atual), align="R")
        self.set_draw_color(*BORDA)
        self.set_line_width(0.25)
        self.line(self.l_margin, 15, self.w - self.r_margin, 15)
        self.set_y(self.t_margin)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-11)
        self.set_font("Texto", "", 7.5)
        self.set_text_color(*CINZA)
        quem = f" · {self.aluno}" if self.aluno else ""
        self.cell(0, 5, _limpo(f"Teste de Software I · Prof. Frank Piffer{quem}"))
        self.set_x(self.l_margin)
        self.cell(0, 5, f"{self.page_no()} / {{nb}}", align="R")

    # ─── blocos de conteúdo ───────────────────────────────────────────────
    def secao(self, numero, selo, titulo, subtitulo=""):
        self.secao_atual = f"{numero}. {titulo}"        # antes do add_page: o cabeçalho já usa o nome novo
        if self.page_no() == 1 or self.get_y() > self.t_margin + 4:
            self.add_page()
        self.start_section(_limpo(f"{numero}. {titulo}"), level=0)
        self.set_font("Semi", "", 8)
        self.set_text_color(*AZUL)
        self.cell(0, 5, _limpo(selo.upper()), new_x="LMARGIN", new_y="NEXT")
        self.set_font("Texto", "B", 19)
        self.set_text_color(*NAVY)
        self.multi_cell(0, 8.5, _limpo(f"{numero}. {titulo}"), new_x="LMARGIN", new_y="NEXT")
        if subtitulo:
            self.ln(0.5)
            self.set_font("Texto", "", 9.5)
            self.set_text_color(*CINZA)
            self.multi_cell(0, 5, _limpo(subtitulo), new_x="LMARGIN", new_y="NEXT")
        y = self.get_y() + 2
        self.set_draw_color(*AZUL)
        self.set_line_width(0.9)
        self.line(self.l_margin, y, self.l_margin + 20, y)
        self.set_y(y + 6)

    def sub(self, numero, titulo, espaco=35):
        if self.will_page_break(espaco):
            self.add_page()
        self.ln(2.5)
        self.start_section(_limpo(f"{numero} {titulo}"), level=1)
        self.set_font("Texto", "B", 12)
        self.set_text_color(*NAVY)
        self.cell(0, 7, _limpo(f"{numero}   {titulo}"), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def texto(self, s, tamanho=9.5, cor=TEXTO, estilo="", markdown=False):
        self.set_font("Texto", estilo, tamanho)
        self.set_text_color(*cor)
        self.multi_cell(0, tamanho * 0.52, _limpo(s), markdown=markdown, align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(1.2)

    def destaque(self, corpo, tipo="info", titulo=""):
        largura = self.epw - 9
        self.set_font("Texto", "", 9)
        linhas = self.multi_cell(largura, 4.7, _limpo(corpo), dry_run=True, output="LINES", markdown=True, align="L")
        altura = len(linhas) * 4.7 + (5.5 if titulo else 0) + 5.5
        if self.will_page_break(altura + 2):
            self.add_page()
        x, y = self.l_margin, self.get_y()
        self.set_fill_color(*FUNDO[tipo])
        self.rect(x, y, self.epw, altura, "F", round_corners=True, corner_radius=1.6)
        self.set_fill_color(*COR[tipo])
        self.rect(x, y, 1.3, altura, "F")
        self.set_xy(x + 5.5, y + 2.7)
        if titulo:
            self.set_font("Texto", "B", 9.5)
            self.set_text_color(*COR[tipo])
            self.cell(0, 5, _limpo(titulo), new_x="LMARGIN", new_y="NEXT")
            self.set_x(x + 5.5)
        self.set_font("Texto", "", 9)
        self.set_text_color(*TEXTO)
        self.multi_cell(largura, 4.7, _limpo(corpo), markdown=True, align="L", new_x="LMARGIN", new_y="NEXT")
        self.set_y(y + altura + 3)

    def cartoes(self, itens):
        """Linha de cartões: [(valor, rótulo, cor)]."""
        n, espaco, h = len(itens), 4, 21
        w = (self.epw - espaco * (n - 1)) / n
        if self.will_page_break(h + 4):
            self.add_page()
        x, y = self.l_margin, self.get_y()
        for valor, rotulo, cor in itens:
            self.set_fill_color(*CLARO)
            self.rect(x, y, w, h, "F", round_corners=True, corner_radius=2)
            self.set_fill_color(*cor)
            self.rect(x, y + 4, 1.1, h - 8, "F")
            self.set_xy(x + 4.5, y + 3)
            texto = _limpo(valor)
            self.set_font("Texto", "B", 16 if len(texto) <= 7 else 12 if len(texto) <= 12 else 10)
            self.set_text_color(*cor)
            self.cell(w - 6, 8, texto)
            self.set_xy(x + 4.5, y + 12)
            self.set_font("Texto", "", 7.8)
            self.set_text_color(*CINZA)
            self.multi_cell(w - 6, 3.6, _limpo(rotulo), align="L")
            x += w + espaco
        self.set_y(y + h + 5)

    def tabela(self, linhas, colunas=None, larguras=None, alinhar=None, tamanho=8, largura=None, posicao="CENTER"):
        if not linhas:
            self.texto("(nenhuma linha)", 8.5, CINZA, "I")
            return
        colunas = colunas or [c for c in linhas[0] if not c.startswith("_")]
        self.set_font("Texto", "", tamanho)
        self.set_text_color(*TEXTO)
        self.set_draw_color(*BORDA)
        self.set_fill_color(255, 255, 255)        # o fpdf2 pinta as linhas ímpares com a cor atual
        self.set_line_width(0.2)
        with self.table(col_widths=larguras, text_align=alinhar or "LEFT", line_height=tamanho * 0.5,
                        padding=(1.3, 1.6), borders_layout="HORIZONTAL_LINES", width=largura or self.epw,
                        align=posicao,
                        cell_fill_color=CLARO, cell_fill_mode="ROWS",
                        headings_style=FontFace(family="Texto", emphasis="BOLD", color=(255, 255, 255),
                                                fill_color=NAVY)) as t:
            cabecalho = t.row()
            for c in colunas:
                cabecalho.cell(_limpo(c))
            for linha in linhas:
                r = t.row()
                for c in colunas:
                    valor = _limpo(linha.get(c, ""))
                    r.cell(valor, style=_status(valor))
        self.ln(3)

    def codigo(self, texto, linha_inicial=1):
        linhas = texto.expandtabs(4).rstrip().split("\n")
        self.set_font("Mono", "", 7.5)
        alt, num = 3.55, 8
        i = 0
        while i < len(linhas):
            cabem = int((self.page_break_trigger - self.get_y() - 5) // alt)
            if cabem < 5:
                self.add_page()
                continue
            trecho = linhas[i:i + cabem]
            x, y = self.l_margin, self.get_y()
            h = len(trecho) * alt + 4
            self.set_fill_color(*CLARO)
            self.rect(x, y, self.epw, h, "F", round_corners=True, corner_radius=1.5)
            self.set_fill_color(*AZUL)
            self.rect(x, y, 1, h, "F")
            for k, linha in enumerate(trecho):
                self.set_xy(x + 2, y + 2 + k * alt)
                self.set_text_color(*CINZA)
                self.cell(num, alt, str(linha_inicial + i + k), align="R")
                self.set_x(x + num + 5)
                self.set_text_color(*TEXTO)
                conteudo = _limpo(linha)
                self.cell(self.epw - num - 8, alt, conteudo if len(conteudo) <= 110 else conteudo[:109] + "…")
            self.set_y(y + h + 3)
            i += len(trecho)

    def imagem(self, png, largura=None, altura_max=None):
        px_w, px_h = Image.open(BytesIO(png)).size
        w = largura or self.epw
        h = w * px_h / px_w
        if altura_max and h > altura_max:
            h = altura_max
            w = h * px_w / px_h
        if self.will_page_break(h + 2):
            self.add_page()
        self.image(BytesIO(png), x=self.l_margin + (self.epw - w) / 2, y=self.get_y(), w=w, h=h)
        self.set_y(self.get_y() + h + 3)

    def legenda(self, itens):
        """Quadradinhos coloridos + texto, numa linha (legenda do grafo)."""
        self.set_font("Texto", "", 7.8)
        x, y = self.l_margin, self.get_y()
        for texto, (fundo, borda) in itens:
            rgb = tuple(int(borda[i:i + 2], 16) for i in (1, 3, 5))
            self.set_fill_color(*rgb)
            self.rect(x, y + 1.2, 3, 3, "F", round_corners=True, corner_radius=0.6)
            self.set_xy(x + 4.2, y)
            self.set_text_color(*TEXTO)
            self.cell(self.get_string_width(texto) + 6, 5.4, _limpo(texto))
            x = self.get_x()
        self.set_y(y + 8)


# ═══════════════════════════════════════════════════════════════════════════
# Capa e sumário
# ═══════════════════════════════════════════════════════════════════════════
def _capa(pdf: Relatorio, resumo: list):
    pdf.add_page()
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, pdf.w, 100, "F")
    pdf.set_fill_color(*AZUL)
    pdf.rect(0, 100, pdf.w, 2.2, "F")
    pdf.set_xy(18, 26)
    pdf.set_font("Semi", "", 10)
    pdf.set_text_color(160, 196, 255)
    pdf.cell(0, 6, "TESTINGSTUDIO WEB")
    pdf.set_xy(18, 36)
    pdf.set_font("Texto", "B", 27)
    pdf.set_text_color(255, 255, 255)
    pdf.multi_cell(170, 11.5, "Relatório de Auditoria\nde Testes de Software")
    pdf.set_xy(18, 66)
    pdf.set_font("Texto", "", 10.5)
    pdf.set_text_color(214, 228, 255)
    pdf.multi_cell(170, 5.6, "Teste de Software I · Ementa 62371 · Prof. Frank Piffer\n"
                             "Base teórica: Delamaro, Maldonado e Jino (2007) — Introdução ao Teste de Software")

    pdf.set_y(114)
    campos = [("ALUNO(A) / EQUIPE", pdf.aluno or "—"), ("GERADO EM", datetime.now().strftime("%d/%m/%Y às %H:%M"))]
    x = pdf.l_margin
    for rotulo, valor in campos:
        pdf.set_xy(x, 114)
        pdf.set_font("Semi", "", 7.5)
        pdf.set_text_color(*CINZA)
        pdf.cell(85, 4.5, rotulo)
        pdf.set_xy(x, 119)
        pdf.set_font("Texto", "B", 12)
        pdf.set_text_color(*NAVY)
        pdf.cell(85, 6.5, _limpo(valor))
        x += 90
    pdf.set_y(136)
    pdf.set_font("Texto", "B", 13)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, "Resumo", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    for titulo, cartoes in resumo:
        pdf.set_font("Semi", "", 8.5)
        pdf.set_text_color(*AZUL)
        pdf.cell(0, 5, _limpo(titulo.upper()), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        pdf.cartoes(cartoes)
    pdf.set_y(-26)
    pdf.set_font("Texto", "I", 7.8)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 4, "Análises calculadas em Python (ε, PCE, AVL, GFC, V(G) e RTM). A IA (Gemini) aparece só "
                         "como parceira de pareamento, no anexo — Protocolo 4: nada de copiar e colar cego.")


def _sumario(pdf: Relatorio, outline):
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Texto", "B", 19)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 10, "Sumário", new_x="LMARGIN", new_y="NEXT")
    y = pdf.get_y() + 1
    pdf.set_draw_color(*AZUL)
    pdf.set_line_width(0.9)
    pdf.line(pdf.l_margin, y, pdf.l_margin + 20, y)
    pdf.set_y(y + 6)
    for secao in outline:
        nivel = secao.level
        link = pdf.add_link(page=secao.page_number)
        if nivel == 0:
            pdf.ln(2.5)
            pdf.set_font("Semi", "", 11)
            pdf.set_text_color(*NAVY)
            altura = 7
        else:
            pdf.set_font("Texto", "", 9.5)
            pdf.set_text_color(*TEXTO)
            altura = 5.8
        recuo = 8 * nivel
        pdf.set_x(pdf.l_margin + recuo)
        pdf.cell(pdf.epw - recuo - 14, altura, secao.name, link=link)
        pdf.cell(14, altura, str(secao.page_number), align="R", link=link, new_x="LMARGIN", new_y="NEXT")
        if nivel == 0:
            pdf.set_draw_color(*BORDA)
            pdf.set_line_width(0.2)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())


# ═══════════════════════════════════════════════════════════════════════════
# Sprint 1 — Caixa-preta
# ═══════════════════════════════════════════════════════════════════════════
def _resumo_sprint1(d):
    r = d["resultado"]
    eps = r["epsilon"][0]["ε"] if r["epsilon"] else "—"
    return [(len(r["casos"]), "casos de teste", AZUL), (len(r["classes"]), "classes de equivalência", ROXO),
            (len(r["limites"]), "fronteiras (AVL)", AMBAR), (eps, "épsilon (ε)", VERDE)]


def _sprint1(pdf: Relatorio, d: dict, n: int):
    r = d["resultado"]
    pdf.secao(n, "Sprint 1 · Teste funcional", "Auditoria de Caixa-Preta (PCE e AVL)",
              f"Unidade {d['unidade']} · arquivo {d.get('arquivo') or '—'} · regra da saída: {d.get('formula') or '—'}")
    pdf.cartoes(_resumo_sprint1(d))
    achados = list(d.get("notas", [])) + list(r["avisos"])
    estouro = [c["CT"] for c in r["casos"] if "Estouro" in c["Resultado esperado"]]
    if estouro:
        achados.append(f"{len(estouro)} caso(s) com **estouro da saída** ({', '.join(estouro[:8])}"
                       f"{'…' if len(estouro) > 8 else ''}): entradas válidas geram um resultado que não cabe no "
                       "tipo — o programa precisa tratar.")
    inviaveis = [c["ID"] for c in r["classes"] if c["Coberta por"].startswith("⚠")]
    if inviaveis:
        achados.append(f"Classe(s) sem caso possível: {', '.join(inviaveis)} — verifique se são inviáveis "
                       "(ex.: saída negativa quando as entradas são ≥ 0).")
    for achado in achados:
        pdf.destaque(achado, "alerta", "Achado do teste")

    pdf.sub(f"{n}.1", "Código-fonte da unidade")
    pdf.codigo(d["codigo"], d.get("linha_inicial", 1))
    pdf.sub(f"{n}.2", "Épsilon (ε) e faixas válidas")
    pdf.texto("ε é a menor variação que o tipo de dado consegue representar — calculado pelo Python, não pela IA.",
              8.5, CINZA, "I")
    pdf.tabela(r["epsilon"], larguras=[15, 15, 6, 24, 20, 27], tamanho=7.6)
    pdf.sub(f"{n}.3", "Classes de equivalência (PCE)")
    pdf.tabela(r["classes"], larguras=[6, 15, 9, 33, 15, 20], tamanho=7.8)
    pdf.sub(f"{n}.4", "Valores-limite (AVL): X − ε, X e X + ε")
    pdf.tabela(r["limites"], larguras=[15, 17, 7, 16, 16, 16], tamanho=7.8)
    if r.get("pontos"):
        pdf.sub(f"{n}.5", "Pontos de fronteira: On · Off · Interior · Exterior", espaco=50)
        pdf.texto("On = na fronteira · Off = 1º ponto fora (X ∓ ε) · Interior = bem dentro · Exterior = bem fora.",
                  8.5, CINZA, "I")
        grupos = {}
        for p in r["pontos"]:
            grupos.setdefault((p["Variável"], p["Fronteira"]), []).append(p)
        for grupo in grupos.values():
            pdf.imagem(gr.regua(grupo), largura=pdf.epw)
    variaveis = [c for c in r["casos"][0] if c not in ("CT", "Técnica", "Objetivo", "Classes cobertas", "Resultado esperado")]
    colunas = ["CT", "Técnica", "Objetivo", *variaveis, "Resultado esperado"]
    if len(variaveis) > 3:
        pdf.add_page("L")
    pdf.sub(f"{n}.6", "Casos de teste com o resultado esperado")
    pdf.tabela(r["casos"], colunas=colunas, larguras=_larguras_casos(pdf, r["casos"], variaveis, 7), tamanho=7)


def _larguras_casos(pdf: Relatorio, casos, variaveis, tamanho):
    """Larguras (mm) da tabela de casos: CT e valores numa linha só; o resto vai para objetivo e resultado."""
    def maior(textos, estilo=""):
        pdf.set_font("Texto", estilo, tamanho)
        return max(pdf.get_string_width(_limpo(t)) for t in textos) + 3.6
    ct = maior([c["CT"] for c in casos] + ["CT"], "B")
    tecnica = 12
    valores = [min(32, max(maior([str(c.get(v, "")) for c in casos]), maior([v], "B"))) for v in variaveis]
    sobra = pdf.epw - ct - tecnica - sum(valores)
    return [ct, tecnica, sobra * 0.44, *valores, sobra * 0.56]


# ═══════════════════════════════════════════════════════════════════════════
# Sprint 2 — Caixa-branca
# ═══════════════════════════════════════════════════════════════════════════
def _cor_risco(vg):
    return VERDE if vg <= 10 else AMBAR if vg <= 20 else VERMELHO


def _resumo_sprint2(d):
    a = d["analise"]
    return [(a["N"], "nós (N)", AZUL), (a["E"], "arestas (E)", AZUL), (a["P"], "decisões (P)", AMBAR),
            (f"V(G) = {a['vg']}", f"risco {a['risco'].split(' —')[0]}", _cor_risco(a["vg"]))]


def _sprint2(pdf: Relatorio, d: dict, n: int):
    a = d["analise"]
    pdf.secao(n, "Sprint 2 · Teste estrutural", "Caixa-Branca: GFC e Complexidade Ciclomática",
              f"Unidade {d['unidade']} · arquivo {d.get('arquivo') or '—'} · McCabe (1976) · "
              "Delamaro, Maldonado e Jino (2007)")
    pdf.cartoes(_resumo_sprint2(d))
    pdf.destaque(f"V(G) = {a['vg']}: são necessários pelo menos **{a['vg']} casos de teste** para exercitar "
                 f"todos os caminhos independentes da unidade. Risco segundo McCabe: {a['risco']}.",
                 "sucesso" if a["confere"] else "alerta", "Esforço de teste")
    if d.get("vg_alternativo") and d["vg_alternativo"] != a["vg"]:
        modo = "separando" if not d.get("separar") else "sem separar"
        pdf.destaque(f"A unidade tem condição composta (OR/AND). Neste relatório ela conta como "
                     f"{'uma decisão para cada condição' if d.get('separar') else 'uma única decisão'}; "
                     f"{modo} as condições, V(G) = {d['vg_alternativo']}. Confirme com o professor qual convenção usar.",
                     "info", "Condições compostas")
    # tamanho natural do desenho (o PNG sai a 220 dpi): não amplia grafo pequeno
    png = d.get("png_grafo") or gr.grafo(d["grafo"])        # a tela manda o grafo; o desenho é feito aqui
    px_w, px_h = Image.open(BytesIO(png)).size
    nat_w, nat_h = px_w / 220 * 25.4, px_h / 220 * 25.4
    if nat_w > nat_h:
        # grafo largo: desenho em cima, tabela de nós embaixo
        pdf.sub(f"{n}.1", "Grafo de Fluxo de Controle (GFC) e seus nós", espaco=min(nat_h, 120) + 14)
        pdf.imagem(png, largura=min(nat_w, pdf.epw), altura_max=150)
        pdf.legenda(gr.legenda_grafo())
        pdf.tabela(a["nos"], larguras=[8, 11, 10, 71], tamanho=7.4)
    else:
        # grafo alto e estreito (o comum): desenho à esquerda e a tabela de nós ao lado.
        # Se sobra bastante espaço nesta página, encolhe um pouco o desenho em vez de pular de página.
        livre = pdf.page_break_trigger - pdf.get_y() - 24          # título do item + legenda
        teto = livre if livre >= 105 else 172
        escala = min(1, 92 / nat_w, teto / nat_h)
        larg_img, alt_img = nat_w * escala, nat_h * escala
        pdf.sub(f"{n}.1", "Grafo de Fluxo de Controle (GFC) e seus nós", espaco=alt_img + 12)
        pagina, y0 = pdf.page, pdf.get_y()
        pdf.image(BytesIO(png), x=pdf.l_margin, y=y0, w=larg_img, h=alt_img)
        pdf.set_y(y0)
        pdf.tabela(a["nos"], larguras=[8, 11, 10, 46], tamanho=7.2, largura=pdf.epw - larg_img - 5,
                   posicao="RIGHT")
        pdf.set_y(max(y0 + alt_img, pdf.get_y()) + 2 if pdf.page == pagina else pdf.get_y() + 2)
        pdf.legenda(gr.legenda_grafo())
    pdf.sub(f"{n}.2", "V(G) calculado de três formas")
    pdf.tabela(a["formas"], larguras=[40, 30, 12], tamanho=8.5)
    if a["confere"]:
        pdf.destaque(f"As três formas batem (e a contagem de decisões no código-fonte dá {a['decisoes_codigo']} + 1): "
                     "o grafo está consistente.", "sucesso")
    pdf.sub(f"{n}.3", "Caminhos básicos (um caso de teste por caminho)")
    pdf.texto("Método da linha de base de McCabe: parte do caminho mais curto e, em cada decisão, troca de lado — "
              "cada caminho novo acrescenta uma aresta que nenhum outro cobria."
              + (" Juntos, cobrem todos os arcos (critério todos-arcos)." if a["todos_arcos"] else "")
              + " Atenção: um caminho pode ser inviável (nenhuma entrada o percorre); nesse caso, troque-o por outro "
                "caminho independente.", 8.5, CINZA, "I")
    pdf.tabela(a["caminhos"], colunas=["Caminho", "Sequência de nós", "Decisões tomadas"], larguras=[9, 34, 57],
               tamanho=7.6)
    if d.get("visao"):
        pdf.sub(f"{n}.4", "Complexidade de todas as unidades do arquivo")
        pdf.tabela(d["visao"], larguras=[30, 8, 8, 9, 38], tamanho=8)
        total = sum(v["V(G)"] for v in d["visao"] if isinstance(v["V(G)"], int))
        pdf.texto(f"Esforço total do arquivo: **{total} caminhos independentes** para testar. "
                  "Escala de McCabe: 1–10 baixo · 11–20 moderado · 21–50 alto · acima de 50 muito alto.",
                  8.8, TEXTO, markdown=True)
    pdf.sub(f"{n}.5", "Código-fonte com a numeração usada no grafo")
    pdf.codigo(d["codigo"], d.get("linha_inicial", 1))


# ═══════════════════════════════════════════════════════════════════════════
# Aula 14/10 — Derivação de casos de teste e RTM
# ═══════════════════════════════════════════════════════════════════════════
def _resumo_rtm(d):
    m = d["rtm"]
    ida, volta = m["ida"], m["volta"]
    return [(rtm.percentual(ida), f"ida: {ida[0]}/{ida[1]} requisitos cobertos", VERDE if ida[0] == ida[1] else VERMELHO),
            (rtm.percentual(volta), f"volta: {volta[0]}/{volta[1]} testes rastreados",
             VERDE if volta[0] == volta[1] else VERMELHO),
            (len(d["casos"]), "casos de teste", AZUL),
            (" · ".join(str(x) for x in m["por_fluxo"].values()), "principal · alternativo · exceção", ROXO)]


def _rtm(pdf: Relatorio, d: dict, n: int):
    m = d["rtm"]
    pdf.secao(n, "Aula 14/10 · Requisitos", "Derivação de Casos de Teste e RTM",
              f"Cenário: {d.get('cenario') or 'livre'} · Delamaro, Maldonado e Jino (2007, cap. 2) · "
              "Molinari (2008) · SWEBOK V3.0")
    pdf.cartoes(_resumo_rtm(d))
    problemas = ([f"{r} não tem nenhum caso de teste (falha na ida)." for r in m["nao_cobertos"]]
                 + [f"{c} não aponta para nenhum requisito — teste órfão (falha na volta)." for c in m["orfaos"]]
                 + [f"{c} aponta para {r}, que não existe na lista de requisitos." for c, r in m["inexistentes"]])
    if problemas:
        pdf.destaque("\n".join(problemas), "erro", "Lacunas de rastreabilidade")
    elif d["casos"]:
        pdf.destaque("Cobertura bidirecional completa: tudo o que foi pedido foi testado e tudo o que foi "
                     "testado foi pedido.", "sucesso", "RTM fechada")
    pdf.sub(f"{n}.1", "Requisitos do cenário")
    pdf.tabela([{"ID": r.id, "Requisito": r.descricao} for r in d["requisitos"]], larguras=[12, 88], tamanho=8.5)
    if m["linhas"]:
        pdf.sub(f"{n}.2", "Cobertura por requisito", espaco=45)
        pdf.imagem(gr.cobertura(m), largura=pdf.epw * 0.85)
    ct = [c.id for c in d["casos"]]
    if len(ct) > 9:
        pdf.add_page("L")
    pdf.sub(f"{n}.3", "Matriz de Rastreabilidade de Requisitos (RTM)")
    largura_desc = 40 if len(ct) <= 9 else 50
    pdf.tabela(m["linhas"], larguras=[10, largura_desc] + [5] * len(ct) + [8, 8],
               alinhar=["LEFT", "LEFT"] + ["CENTER"] * len(ct) + ["CENTER", "CENTER"], tamanho=7.4)
    pdf.add_page("L")
    pdf.sub(f"{n}.4", "Casos de teste derivados")
    pdf.tabela(rtm.tabela_casos(d["casos"]), larguras=[6, 20, 13, 13, 18, 30, 22, 26], tamanho=7.2)


# ═══════════════════════════════════════════════════════════════════════════
# Anexo — textos da IA (Markdown simples → PDF)
# ═══════════════════════════════════════════════════════════════════════════
_LATEX = {r"\varepsilon": "ε", r"\epsilon": "ε", r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥",
          r"\neq": "≠", r"\times": "×", r"\cdot": "·", r"\pm": "±", r"\rightarrow": "→", r"\to": "→"}


def _inline(s: str) -> str:
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\$([^$\n]+)\$", r"\1", s)
    for comando, simbolo in _LATEX.items():
        s = s.replace(comando, simbolo)
    s = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+)(?<!\*)\*(?!\*)", r"\1", s)
    return s.replace("--", "—")


def _markdown(pdf: Relatorio, texto: str):
    linhas = texto.splitlines()
    i = 0
    while i < len(linhas):
        linha = linhas[i].rstrip()
        if linha.strip().startswith("|"):
            bloco = []
            while i < len(linhas) and linhas[i].strip().startswith("|"):
                if not re.fullmatch(r"\|?[\s:\-|]+\|?", linhas[i].strip()):
                    bloco.append([_inline(c.strip()).replace("**", "") for c in linhas[i].strip().strip("|").split("|")])
                i += 1
            if len(bloco) > 1:
                cab = bloco[0]
                pdf.tabela([dict(zip(cab, l)) for l in bloco[1:]], colunas=cab, tamanho=7.4)
            continue
        titulo = re.match(r"#{1,6}\s+(.*)", linha)
        if titulo:
            pdf.ln(1)
            pdf.texto(_inline(titulo.group(1)).replace("**", ""), 10.5, NAVY, "B")
        elif re.fullmatch(r"\s*[-*_]{3,}\s*", linha):
            pdf.ln(1)
        elif re.match(r"\s*[-*•]\s+", linha):
            recuo = (len(linha) - len(linha.lstrip())) // 2
            pdf.set_x(pdf.l_margin + 3 + 4 * recuo)
            pdf.set_font("Texto", "", 9)
            pdf.set_text_color(*TEXTO)
            pdf.multi_cell(0, 4.7, "•  " + _limpo(_inline(re.sub(r"^\s*[-*•]\s+", "", linha))), markdown=True,
                           new_x="LMARGIN", new_y="NEXT")
        elif linha.strip():
            pdf.texto(_inline(linha), 9, markdown=True)
        else:
            pdf.ln(1.5)
        i += 1


# ═══════════════════════════════════════════════════════════════════════════
# Ponto de entrada
# ═══════════════════════════════════════════════════════════════════════════
def gerar(aluno: str = "", sprint1: dict | None = None, sprint2: dict | None = None,
          rtm_dados: dict | None = None, textos_ia: list | None = None) -> bytes:
    """Monta o PDF. Cada parâmetro é o dicionário que a tela montou (ou None para pular)."""
    pdf = Relatorio(aluno)
    partes = [("Sprint 1 · Caixa-Preta", sprint1, _sprint1, _resumo_sprint1),
              ("Sprint 2 · Caixa-Branca", sprint2, _sprint2, _resumo_sprint2),
              ("Aula 14/10 · Derivação e RTM", rtm_dados, _rtm, _resumo_rtm)]
    _capa(pdf, [(titulo, resumo(d)) for titulo, d, _, resumo in partes if d])
    pdf.add_page()
    pdf.insert_toc_placeholder(_sumario, pages=1, reset_page_indices=False)
    numero = 1
    for _, d, montar, _ in partes:
        if d:
            montar(pdf, d, numero)
            numero += 1
    if textos_ia:
        pdf.secao(numero, "Anexo", "Textos da IA (Gemini)",
                  "Sugestões da IA usada como parceira de pareamento (Protocolo 4) — revisadas pelo autor.")
        for k, (titulo, md) in enumerate(textos_ia, 1):
            pdf.sub(f"{numero}.{k}", titulo)
            _markdown(pdf, md)
    return bytes(pdf.output())
