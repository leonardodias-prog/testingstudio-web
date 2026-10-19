"""
sprint1_caixa_preta.py — Tela da Sprint 1: Auditoria de Caixa-Preta do CAD0001
================================================================================
Checklist do professor (manual da Sprint 1):
  1. Leitura do CAD0001 ...... o código aparece na caixa de texto
  2. Análise de PCE .......... tabela com as classes válidas e inválidas
  3. AVL com Épsilon ......... ε = 0,01 justificado pelo tipo DECIMAL(12,2)
  4. Dashboard gráfico ....... aba com os pontos On, Off, Interior e Exterior
A matemática fica em caixa_preta.py (Python puro); a IA só explica e revisa.
"""

import hashlib
from functools import partial
from pathlib import Path

import pandas as pd
import streamlit as st

import caixa_preta as cp
import graficos as gr
import ia_gemini as ia
import relatorio_pdf

EXEMPLOS = Path(__file__).parent / "exemplos"
COLUNAS = {   # coluna da tabela na tela → campo da Entrada (caixa_preta.py)
    "variável": "nome", "tipo": "tipo", "tamanho (p/n)": "tamanho", "casas (s)": "casas",
    "limite inferior": "minimo", "limite superior": "maximo",
    "aceita NULL": "aceita_nulo", "NULL vira": "se_nulo", "valor típico": "tipico",
}


def carregar_exemplo(arquivo: str):
    """Botões de exemplo (Sprint 1 e Sprint 2 usam o mesmo código)."""
    st.session_state.codigo = cp.ler_txt((EXEMPLOS / arquivo).read_bytes())
    st.session_state.nome_arquivo = arquivo


@st.cache_data(show_spinner=False)
def _regua(pontos: list) -> bytes:
    return gr.regua(pontos)


def mostrar(cliente, modelo) -> dict | None:
    """Desenha a aba da Sprint 1 e devolve os dados para o PDF (ou None)."""
    st.session_state.setdefault("codigo", "")
    st.session_state.setdefault("versao_tabela", 0)
    st.caption("Manual da Sprint 1: ler o CAD0001 e fazer a análise funcional de Caixa-Preta com "
               "PCE e AVL (ε = 0,01). Base: Delamaro, Maldonado e Jino (2007).")

    # ─── 1. Ler o arquivo (Objetivo 4 — caixa de texto) ────────────────────
    st.header("1️⃣ Ler o arquivo .txt")
    col_arquivo, col_manual, col_completo = st.columns([3, 1, 1], vertical_alignment="bottom")
    arquivo = col_arquivo.file_uploader("Envie o código ou o requisito",
                                        type=["txt", "4gl", "py", "java", "c", "md"])
    col_manual.button("📄 CAD0001 do manual", on_click=carregar_exemplo, args=("cad0001_manual_sprint1.txt",),
                      help="A versão do manual da Sprint 1: valores negativos devolvem -1")
    col_completo.button("📄 CAD0001 completo", on_click=carregar_exemplo, args=("cad0001_item_calculo.txt",),
                        help="O .txt com cálculo, inclusão, alteração e exclusão")
    if arquivo is not None and st.session_state.get("arquivo_lido") != arquivo.file_id:
        st.session_state.codigo = cp.ler_txt(arquivo.getvalue())
        st.session_state.arquivo_lido = arquivo.file_id
        st.session_state.nome_arquivo = arquivo.name

    codigo = st.text_area("Conteúdo lido — pode editar ou colar aqui", key="codigo", height=300,
                          placeholder="Envie um .txt, use um dos exemplos ou cole o código / requisito…")
    if not codigo.strip():
        st.info("👆 Envie um arquivo ou use um dos exemplos do CAD0001 para começar.")
        return None

    unidades = cp.extrair_unidades(codigo)
    if unidades:
        padrao = next((i for i, u in enumerate(unidades) if u.formula),
                      next((i for i, u in enumerate(unidades) if u.entradas), 0))
        nome_escolhido = st.selectbox("Unidade (FUNCTION) a analisar", [u.nome for u in unidades], index=padrao,
                                      help="Funções que o Python encontrou no arquivo.")
        unidade = next(u for u in unidades if u.nome == nome_escolhido)
        st.session_state.s1_unidade = unidade.nome          # a Sprint 2 abre na mesma unidade
        resumo = ", ".join(f"`{e.nome}` {e.tipo_txt()}" for e in unidade.entradas) or "nenhuma"
        if unidade.saida:
            resumo += f" · **Saída:** `{unidade.saida.nome}` {unidade.saida.tipo_txt()}"
        if unidade.formula:
            resumo += f" · **Regra:** `{unidade.formula}`"
        if unidade.erro_codigo:
            resumo += f" · **Erro:** devolve `{unidade.erro_codigo}` fora da regra"
        st.caption(f"**Entradas:** {resumo}")
    else:
        unidade = cp.Unidade("texto inteiro", [])
        st.caption("Nenhuma FUNCTION Informix-4GL encontrada: o texto inteiro é a unidade. "
                   "Preencha as entradas no Passo 3 (ou peça para a IA preencher).")
    contexto = unidade.nome + ":" + hashlib.md5(codigo.encode()).hexdigest()

    # ─── 2. Entender com a IA (Objetivo 3) ─────────────────────────────────
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

    # ─── 3. Caixa-preta: PCE + AVL com ε (Python puro) ─────────────────────
    st.header("3️⃣ Aplicar a caixa-preta (PCE + AVL com ε)")
    st.caption("Confira as entradas. Limite em branco = o que o TIPO suporta; o Python já preenche a regra "
               "de negócio que acha no código (ex.: valores ≥ 0). Em CHAR, os limites são o tamanho do texto.")

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
        resultado = cp.analisar(entradas, formula, unidade.saida, unidade.erro())
    except ValueError as erro:
        mensagem = str(erro)
        st.warning(mensagem[:1].upper() + mensagem[1:] + ".")
        return None
    for aviso in resultado["avisos"]:
        st.warning(aviso)
    notas = []
    if unidade.erro_codigo and any(e.aceita_nulo for e in entradas):
        notas.append("Divergência para registrar: o manual da Sprint 1 classifica NULL como classe inválida, "
                     "mas o código troca NULL por 0 (válido). Para seguir o manual, desmarque 'aceita NULL'.")
        st.info("📌 " + notas[-1])

    casos = pd.DataFrame(resultado["casos"])
    st.success(f"**{len(casos)} casos de teste** a partir de **{len(resultado['classes'])} classes de "
               f"equivalência** e **{len(resultado['limites'])} fronteiras**.")
    aba_eps, aba_pce, aba_avl, aba_grafico, aba_casos = st.tabs(
        ["ε  Épsilon", "PCE — classes", "AVL — limites", "📊 Gráfico de fronteira", "✅ Casos de teste"])
    with aba_eps:
        st.caption("ε é a menor variação que o tipo de dado consegue representar — o Python calcula, não a IA.")
        st.dataframe(pd.DataFrame(resultado["epsilon"]), hide_index=True)
    with aba_pce:
        st.caption("Cada classe precisa de pelo menos um caso. Inválidas: uma por caso, para não mascarar defeitos.")
        st.dataframe(pd.DataFrame(resultado["classes"]), hide_index=True)
    with aba_avl:
        st.caption("Para cada fronteira X: X − ε, X e X + ε.  ✅ = válido · ❌ = inválido.")
        st.dataframe(pd.DataFrame(resultado["limites"]), hide_index=True)
    with aba_grafico:
        st.caption("Os 4 pontos do manual: **On** (na fronteira) · **Off** (1º ponto fora: X ∓ ε) · "
                   "**Interior** (bem dentro) · **Exterior** (bem fora).")
        grupos = {}
        for p in resultado["pontos"]:
            grupos.setdefault(f"{p['Variável']} — {p['Fronteira']}", []).append(p)
        if grupos:
            nomes = list(grupos)
            padrao = next((i for i, n in enumerate(nomes) if "regra" in n), 0)
            escolhida = st.selectbox("Fronteira", nomes, index=padrao, key=f"fronteira:{contexto}")
            st.image(_regua(grupos[escolhida]), width="stretch")
            st.dataframe(pd.DataFrame(grupos[escolhida]).drop(columns=["Variável", "Fronteira"]), hide_index=True)
            with st.expander("Todos os pontos de fronteira"):
                st.dataframe(pd.DataFrame(resultado["pontos"]), hide_index=True)
        else:
            st.info("Os pontos On/Off/Interior/Exterior valem para entradas numéricas.")
    with aba_casos:
        st.dataframe(casos, hide_index=True)
        st.download_button("⬇️ Baixar casos de teste (CSV para Excel)",
                           casos.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           file_name=f"casos_de_teste_{unidade.nome}.csv", mime="text/csv", on_click="ignore")

    # ─── 4. Revisão com a IA (Protocolo 4 — pair programming) ──────────────
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

    textos = [(f"Sprint 1 — {titulo} ({unidade.nome})", st.session_state[chave][1])
              for chave, titulo in (("explicacao", "Explicação da unidade"), ("revisao", "Revisão dos casos"))
              if st.session_state.get(chave, ("",))[0] == contexto]
    trecho = cp.codigo_da_unidade(codigo, unidade.nome) if unidades else codigo
    dados = {"arquivo": st.session_state.get("nome_arquivo", ""), "unidade": unidade.nome, "codigo": trecho,
             "linha_inicial": codigo.count("\n", 0, max(codigo.find(trecho), 0)) + 1,
             "formula": formula, "resultado": resultado, "notas": notas, "textos_ia": textos}
    st.divider()
    st.download_button("📄 Baixar PDF da Sprint 1", type="primary", mime="application/pdf", on_click="ignore",
                       file_name=f"sprint1_caixa_preta_{unidade.nome}.pdf",
                       data=partial(relatorio_pdf.gerar, aluno=st.session_state.get("pdf_aluno", ""),
                                    sprint1=dados, textos_ia=textos))
    return dados
