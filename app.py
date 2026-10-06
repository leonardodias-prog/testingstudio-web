"""
app.py — TestingStudio Web · Sprint 1 (Marco Zero)
===================================================
Laboratório de Teste de Software I · Módulo 1: Teste Funcional (Caixa-Preta)

  Objetivo 1  Setup Core .......... esta aplicação Streamlit
  Objetivo 2  Autenticação ........ chave da Gemini API (barra lateral)
  Objetivo 3  Processamento NLP ... a IA interpreta o código        → ia_gemini.py
  Objetivo 4  Interface Input ..... caixa de texto + análise PCE/AVL → caixa_preta.py

Para abrir:  python -m streamlit run app.py   (ou dois cliques em rodar.bat)
"""

import hashlib
import os
from pathlib import Path

import pandas as pd
import streamlit as st

import caixa_preta as cp
import ia_gemini as ia

EXEMPLO = Path(__file__).parent / "exemplos" / "cad0001_item_calculo.txt"
SECRETS = Path(__file__).parent / ".streamlit" / "secrets.toml"
CHAVE_EXEMPLO = "COLE_SUA_CHAVE_AQUI"   # o texto que vem no secrets.toml
COLUNAS = {   # coluna da tabela na tela → campo da Entrada (caixa_preta.py)
    "variável": "nome", "tipo": "tipo", "tamanho (p/n)": "tamanho", "casas (s)": "casas",
    "limite inferior": "minimo", "limite superior": "maximo",
    "aceita NULL": "aceita_nulo", "NULL vira": "se_nulo", "valor típico": "tipico",
}

st.set_page_config(page_title="TestingStudio Web", page_icon="🧪", layout="wide")
st.session_state.setdefault("codigo", "")
st.session_state.setdefault("versao_tabela", 0)


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


def carregar_exemplo():
    st.session_state.codigo = cp.ler_txt(EXEMPLO.read_bytes())


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
        st.info("Sem chave a IA fica desligada — o Python continua aplicando PCE e AVL normalmente.")
    st.divider()
    st.markdown("**Sprint 1 — Marco Zero**  \n"
                "1. Setup Core (Streamlit)  \n"
                "2. Autenticação (Gemini API Key)  \n"
                "3. Processamento NLP (a IA interpreta)  \n"
                "4. Interface Input (PCE / AVL)")

st.title("🧪 TestingStudio Web")
st.caption("Auditor de testes de software · Módulo 1 — Teste Funcional (Caixa-Preta): "
           "PCE + AVL com ε · base: Delamaro, Maldonado e Jino (2007)")

# ─── Passo 1: ler o arquivo (Objetivo 4 — caixa de texto) ──────────────────
st.header("1️⃣ Ler o arquivo .txt")
col_arquivo, col_exemplo = st.columns([4, 1], vertical_alignment="bottom")
arquivo = col_arquivo.file_uploader("Envie o código ou o requisito",
                                    type=["txt", "4gl", "py", "java", "c", "md"])
col_exemplo.button("📄 Exemplo CAD0001", on_click=carregar_exemplo, help="Carrega o código que o professor passou")
if arquivo is not None and st.session_state.get("arquivo_lido") != arquivo.file_id:
    st.session_state.codigo = cp.ler_txt(arquivo.getvalue())
    st.session_state.arquivo_lido = arquivo.file_id

codigo = st.text_area("Conteúdo lido — pode editar ou colar aqui", key="codigo", height=300,
                      placeholder="Envie um .txt, clique em 'Usar o exemplo' ou cole o código / requisito…")
if not codigo.strip():
    st.info("👆 Envie um arquivo ou use o exemplo para começar.")
    st.stop()

unidades = cp.extrair_unidades(codigo)
if unidades:
    padrao = next((i for i, u in enumerate(unidades) if u.formula),
                  next((i for i, u in enumerate(unidades) if u.entradas), 0))
    nome_escolhido = st.selectbox("Unidade (FUNCTION) a analisar", [u.nome for u in unidades], index=padrao,
                                  help="Funções que o Python encontrou no arquivo.")
    unidade = next(u for u in unidades if u.nome == nome_escolhido)
    resumo = ", ".join(f"`{e.nome}` {e.tipo_txt()}" for e in unidade.entradas) or "nenhuma"
    if unidade.saida:
        resumo += f" · **Saída:** `{unidade.saida.nome}` {unidade.saida.tipo_txt()}"
    if unidade.formula:
        resumo += f" · **Regra:** `{unidade.formula}`"
    st.caption(f"**Entradas:** {resumo}")
else:
    unidade = cp.Unidade("texto inteiro", [])
    st.caption("Nenhuma FUNCTION Informix-4GL encontrada: o texto inteiro é a unidade. "
               "Preencha as entradas no Passo 3 (ou peça para a IA preencher).")
contexto = unidade.nome + ":" + hashlib.md5(codigo.encode()).hexdigest()

# ─── Passo 2: entender com a IA (Objetivo 3) ───────────────────────────────
st.header("2️⃣ Entender a unidade com a IA")
if cliente is None:
    st.info("Conecte a Gemini API na barra lateral para a IA explicar o código. "
            "(Opcional: o Passo 3 funciona sem IA.)")
elif st.button("🧠 Explicar esta unidade com o Gemini"):
    with st.spinner("O Gemini está lendo o código…"):
        try:
            st.session_state.explicacao = (contexto, ia.explicar(cliente, modelo, codigo, unidade.nome))
        except Exception as erro:
            st.error(ia.explicar_erro(erro))
if st.session_state.get("explicacao", ("",))[0] == contexto:
    with st.container(border=True):
        st.markdown(st.session_state.explicacao[1])

# ─── Passo 3: caixa-preta — PCE + AVL com ε (Python puro) ──────────────────
st.header("3️⃣ Aplicar a caixa-preta (PCE + AVL com ε)")
st.caption("Confira as entradas. Limite em branco = o que o TIPO suporta; troque pelo limite da regra "
           "de negócio, se houver (ex.: cod_item ≥ 1). Em CHAR, os limites são o tamanho do texto.")

chave_ia = f"entradas_ia:{contexto}"
if cliente is not None:
    col_ia, col_volta = st.columns(2)
    if col_ia.button("🧠 Preencher a tabela com a IA",
                     help="Útil quando o texto não é Informix-4GL (outra linguagem ou requisito em português)."):
        with st.spinner("O Gemini está interpretando o texto…"):
            try:
                dados = ia.extrair_entradas(cliente, modelo, codigo, unidade.nome)
                st.session_state[chave_ia] = [cp.entrada_de_dict(d) for d in dados]
                st.session_state.versao_tabela += 1
            except Exception as erro:
                st.error(ia.explicar_erro(erro))
    if chave_ia in st.session_state and col_volta.button("↩️ Voltar ao que o Python extraiu"):
        del st.session_state[chave_ia]
        st.session_state.versao_tabela += 1

entradas_base = st.session_state.get(chave_ia, unidade.entradas)
tabela = pd.DataFrame([{col: getattr(e, campo) for col, campo in COLUNAS.items()} for e in entradas_base],
                      columns=list(COLUNAS))
for col in ("tamanho (p/n)", "casas (s)"):
    tabela[col] = pd.to_numeric(tabela[col], errors="coerce")
tabela["aceita NULL"] = tabela["aceita NULL"].fillna(False).astype(bool)
editada = st.data_editor(
    tabela, num_rows="dynamic", hide_index=True,
    key=f"tabela:{contexto}:{st.session_state.versao_tabela}",
    column_config={
        "variável": st.column_config.TextColumn(required=True),
        "tipo": st.column_config.SelectboxColumn(options=cp.TIPOS, required=True),
        "tamanho (p/n)": st.column_config.NumberColumn(min_value=1, max_value=32767, step=1, format="%d",
                                                       help="DECIMAL(p,s): p · CHAR(n): n"),
        "casas (s)": st.column_config.NumberColumn(min_value=0, max_value=32, step=1, format="%d",
                                                   help="DECIMAL(p,s): s"),
        "limite inferior": st.column_config.TextColumn(help="Vazio = o menor valor do tipo. Em CHAR, tamanho mínimo."),
        "limite superior": st.column_config.TextColumn(help="Vazio = o maior valor do tipo. Em CHAR, tamanho máximo."),
        "aceita NULL": st.column_config.CheckboxColumn(help="Marcado = NULL é válido (o código trata o NULL)."),
        "NULL vira": st.column_config.TextColumn(help="Valor que o NULL assume, ex.: 0"),
        "valor típico": st.column_config.TextColumn(help="Vazio = automático (meio da faixa)."),
    },
)
entradas = [cp.entrada_de_dict({campo: linha[col] for col, campo in COLUNAS.items()})
            for linha in editada.to_dict("records")]

formula = st.text_input(
    "Regra da saída (oráculo)", value=unidade.formula, key=f"formula:{contexto}",
    help="Use os nomes da tabela e + - * / ( ). Veio do código — confira com a especificação! "
         "Vazio = o resultado esperado fica só Aceitar/Rejeitar.")
if unidade.saida and formula.strip():
    st.caption(f"O resultado também é conferido contra o tipo da saída: "
               f"`{unidade.saida.nome}` {unidade.saida.tipo_txt()}.")

try:
    resultado = cp.analisar(entradas, formula, unidade.saida)
except ValueError as erro:
    mensagem = str(erro)
    st.warning(mensagem[:1].upper() + mensagem[1:] + ".")
    st.stop()
for aviso in resultado["avisos"]:
    st.warning(aviso)

casos = pd.DataFrame(resultado["casos"])
st.success(f"**{len(casos)} casos de teste** a partir de **{len(resultado['classes'])} classes de "
           f"equivalência** e **{len(resultado['limites'])} fronteiras**.")
aba_eps, aba_pce, aba_avl, aba_casos = st.tabs(["ε  Épsilon", "PCE — classes", "AVL — limites", "✅ Casos de teste"])
with aba_eps:
    st.caption("ε é a menor variação que o tipo de dado consegue representar — o Python calcula, não a IA.")
    st.dataframe(pd.DataFrame(resultado["epsilon"]), hide_index=True)
with aba_pce:
    st.caption("Cada classe precisa de pelo menos um caso de teste. Inválidas: uma por caso, para não mascarar defeitos.")
    st.dataframe(pd.DataFrame(resultado["classes"]), hide_index=True)
with aba_avl:
    st.caption("Para cada fronteira X: X − ε, X e X + ε.  ✅ = válido · ❌ = inválido.")
    st.dataframe(pd.DataFrame(resultado["limites"]), hide_index=True)
with aba_casos:
    st.dataframe(casos, hide_index=True)
    st.download_button("⬇️ Baixar casos de teste (CSV para Excel)",
                       casos.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       file_name=f"casos_de_teste_{unidade.nome}.csv", mime="text/csv")

# ─── Passo 4: revisão com a IA (Protocolo 4 — pair programming) ─────────────
st.header("4️⃣ Revisão com a IA (pair programming)")
st.caption("Protocolo 4 — Zero 'copiar e colar' cego: a IA sugere, quem decide é você.")
if cliente is None:
    st.info("Conecte a Gemini API na barra lateral para pedir a revisão.")
elif st.button("🤝 Pedir revisão dos casos de teste"):
    with st.spinner("O Gemini está revisando os casos…"):
        try:
            csv = casos.to_csv(index=False, sep=";")
            st.session_state.revisao = (contexto, ia.revisar(cliente, modelo, codigo, unidade.nome, csv))
        except Exception as erro:
            st.error(ia.explicar_erro(erro))
if st.session_state.get("revisao", ("",))[0] == contexto:
    with st.container(border=True):
        st.markdown(st.session_state.revisao[1])
