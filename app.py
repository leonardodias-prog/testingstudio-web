"""
app.py — TestingStudio Web · Laboratório de Teste de Software I (Prof. Frank Piffer)
=====================================================================================
  Sprint 1 (05/10)  Caixa-Preta: PCE + AVL com ε no CAD0001 ........... sprint1_caixa_preta.py
  Sprint 2          Caixa-Branca: GFC + V(G) de McCabe (mesma base) .... sprint2_caixa_branca.py
  Aula 14/10        Derivação de Casos de Teste + RTM .................. aula_rtm.py
  Exportar PDF .......................................................... relatorio_pdf.py
  Motores em Python puro: caixa_preta.py · caixa_branca.py · rtm.py   |   IA (Gemini): ia_gemini.py
  Desenhos da tela e do PDF (régua de fronteira, grafo, cobertura): graficos.py

Objetivos do Marco Zero: Setup Core (este app) · Autenticação (barra lateral) ·
Processamento NLP (a IA interpreta) · Interface Input (caixa de texto + PCE/AVL).

Para abrir:  python -m streamlit run app.py   (ou dois cliques em rodar.bat)
"""

import os
from datetime import datetime
from functools import partial
from pathlib import Path

import streamlit as st

import aula_rtm
import ia_gemini as ia
import relatorio_pdf
import sprint1_caixa_preta as sprint1
import sprint2_caixa_branca as sprint2

SECRETS = Path(__file__).parent / ".streamlit" / "secrets.toml"
CHAVE_EXEMPLO = "COLE_SUA_CHAVE_AQUI"   # o texto que vem no secrets.toml

st.set_page_config(page_title="TestingStudio Web", page_icon="🧪", layout="wide")


def chave_configurada():
    """Objetivo 2 — a chave nunca fica no código: vem do secrets.toml ou do ambiente."""
    try:
        do_arquivo = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
    except Exception:                     # secrets.toml não existe ou tem erro de formato
        do_arquivo = ""
        if SECRETS.exists():
            st.warning('O arquivo .streamlit/secrets.toml tem erro de formato. A chave precisa '
                       'ficar entre aspas:  \n`GEMINI_API_KEY = "sua-chave"`')
    do_ambiente = os.environ.get("GEMINI_API_KEY", "").strip()
    for chave, origem in ((do_arquivo, "arquivo .streamlit/secrets.toml"),
                          (do_ambiente, "variável de ambiente GEMINI_API_KEY")):
        if chave and chave != CHAVE_EXEMPLO:   # o Streamlit também copia o secrets.toml para o ambiente
            return chave, origem
    return "", ""


@st.cache_resource
def conectar(chave: str):
    return ia.conectar(chave)


@st.cache_data(ttl=600, show_spinner="Testando a conexão com a Gemini API...")
def testar_conexao(chave: str):
    """Lista os modelos (valida a chave). O resultado fica guardado por 10 minutos,
    então o Google lento não trava a tela a cada clique."""
    try:
        return ia.listar_modelos(conectar(chave)), "", False
    except Exception as erro:
        return [], ia.explicar_erro(erro), ia.chave_recusada(erro)


# ─── Barra lateral: Autenticação (Objetivo 2) ──────────────────────────────
with st.sidebar:
    st.header("🔑 Gemini API")
    chave, origem = chave_configurada()
    if not chave:
        chave = st.text_input("Cole sua API Key", type="password",
                              help="Crie grátis em https://aistudio.google.com/apikey. "
                                   "Para não digitar sempre, salve em .streamlit/secrets.toml")
        origem = "digitada nesta sessão (não é salva)"
    cliente = modelo = None
    if chave:
        modelos, erro, recusada = testar_conexao(chave)
        if recusada:                            # chave errada: IA desligada
            st.error(erro)
            st.caption(f"Chave lida de: {origem}")
        else:                                   # chave aceita (ou Google só lento)
            cliente = conectar(chave)
            modelos = modelos or ia.PREFERIDOS
            escolhido = st.selectbox("Modelo", modelos,
                                     help="Se ele estiver ocupado, o app tenta os próximos da lista.")
            modelo = [escolhido] + [m for m in modelos if m != escolhido]   # ordem de tentativa
            if erro:
                st.warning(f"Não deu para confirmar a conexão agora. {erro} "
                           "A IA tenta de novo quando você usar.")
                st.button("🔄 Testar a conexão de novo", on_click=testar_conexao.clear)
            else:
                st.success(f"Conectado ✅  \nChave: {origem}")
    else:
        st.info("Sem chave a IA fica desligada — o Python continua fazendo as análises normalmente.")
    st.divider()
    st.markdown("**Sprints do projeto**  \n"
                "1. ✅ Caixa-Preta: PCE + AVL com ε (05/10)  \n"
                "2. ✅ Caixa-Branca: GFC + V(G) de McCabe (mesma base)  \n"
                "3. ⏭️ Próximo módulo: fluxo de dados (def-uso) e mutação  \n\n"
                "**Aulas**  \n"
                "📋 14/10 — Derivação de casos de teste + RTM")

st.title("🧪 TestingStudio Web")
st.caption("Auditor de testes de software · Teste de Software I (Ementa 62371) · "
           "base: Delamaro, Maldonado e Jino (2007)")

aba1, aba2, aba3, aba4 = st.tabs(["⬛ Sprint 1 · Caixa-Preta", "⬜ Sprint 2 · Caixa-Branca",
                                  "📋 Aula 14/10 · Casos de Teste e RTM", "📄 Exportar PDF"])
with aba1:
    dados1 = sprint1.mostrar(cliente, modelo)
with aba2:
    dados2 = sprint2.mostrar(cliente, modelo)
with aba3:
    dados3 = aula_rtm.mostrar(cliente, modelo)
with aba4:
    st.header("📄 Exportar relatório em PDF")
    st.caption("Capa com resumo, sumário clicável, as análises escolhidas e, se quiser, os textos da IA em anexo. "
               "Cada aba também tem o seu botão de PDF.")
    st.text_input("Aluno(a) / equipe — vai na capa", key="pdf_aluno")
    partes = [("Sprint 1 · Caixa-Preta — código, ε, PCE, AVL, régua On/Off/Interior/Exterior e casos de teste", dados1),
              ("Sprint 2 · Caixa-Branca — GFC, V(G) de três formas, caminhos básicos e complexidade do arquivo", dados2),
              ("Aula 14/10 — requisitos, casos de teste derivados e RTM", dados3)]
    marcadas = [st.checkbox(rotulo, value=d is not None, disabled=d is None) for rotulo, d in partes]
    s1, s2, s3 = [d if marcada else None for marcada, (_, d) in zip(marcadas, partes)]
    textos = [t for d in (s1, s2, s3) if d for t in d["textos_ia"]]
    incluir_ia = st.checkbox(f"Anexar os textos da IA ({len(textos)})", value=bool(textos), disabled=not textos)
    st.download_button("⬇️ Baixar PDF", type="primary", mime="application/pdf", on_click="ignore",
                       file_name=f"testingstudio_relatorio_{datetime.now():%Y%m%d_%H%M}.pdf",
                       disabled=not (s1 or s2 or s3),
                       data=partial(relatorio_pdf.gerar, aluno=st.session_state.get("pdf_aluno", ""),
                                    sprint1=s1, sprint2=s2, rtm_dados=s3, textos_ia=textos if incluir_ia else None))
