"""
sprint2_caixa_branca.py — Tela da Sprint 2: Auditoria de Caixa-Branca do CAD0001
=================================================================================
Teste estrutural SOBRE A MESMA BASE da Sprint 1 (o código lido lá):
  1. O código ................ o mesmo CAD0001 (ou outro .txt, ou código Python)
  2. GFC ..................... Grafo de Fluxo de Controle: nós (blocos) e arestas (desvios)
  3. V(G) .................... complexidade ciclomática de McCabe, calculada de três formas
  4. Caminhos básicos ........ um caso de teste por caminho independente (a IA sugere as entradas)
A conta fica em caixa_branca.py (Python puro); a IA só sugere entradas para os caminhos.
"""

import hashlib
from functools import partial

import pandas as pd
import streamlit as st

import caixa_branca as cb
import ia_gemini as ia
import relatorio_pdf
from sprint1_caixa_preta import carregar_exemplo


@st.cache_data(show_spinner=False)
def _grafos(codigo: str, separar: bool) -> dict:
    return cb.extrair_grafos(codigo, separar)


def _vg(g) -> int:
    return len(g.arestas) - len(g.nos) + 2 if isinstance(g, cb.Grafo) else 0


def mostrar(cliente, modelo) -> dict | None:
    """Desenha a aba da Sprint 2 e devolve os dados para o PDF (ou None)."""
    st.session_state.setdefault("codigo", "")
    st.caption("Teste estrutural **sobre a mesma base** da Sprint 1: o Grafo de Fluxo de Controle (GFC) e a "
               "Complexidade Ciclomática de McCabe, V(G) = E − N + 2. Base: Delamaro, Maldonado e Jino (2007) · "
               "McCabe (1976).")

    # ─── 1. O código (o mesmo da Sprint 1) ─────────────────────────────────
    st.header("1️⃣ O código (a mesma base da Sprint 1)")
    col_info, col_manual, col_completo = st.columns([3, 1, 1], vertical_alignment="bottom")
    col_manual.button("📄 CAD0001 do manual", key="s2_manual", on_click=carregar_exemplo,
                      args=("cad0001_manual_sprint1.txt",))
    col_completo.button("📄 CAD0001 completo", key="s2_completo", on_click=carregar_exemplo,
                        args=("cad0001_item_calculo.txt",))
    codigo = st.session_state.codigo
    if not codigo.strip():
        col_info.info("Carregue um exemplo aqui ou leia o arquivo na aba **Sprint 1**.")
        return None
    nome_arquivo = st.session_state.get("nome_arquivo") or "texto colado"
    col_info.markdown(f"**Arquivo:** `{nome_arquivo}` · {codigo.count(chr(10)) + 1} linhas  \n"
                      "Para trocar ou editar o código, use a aba **Sprint 1** — as duas usam o mesmo texto.")

    # ─── 2. GFC ────────────────────────────────────────────────────────────
    st.header("2️⃣ Grafo de Fluxo de Controle (GFC)")
    col_unidade, col_separar = st.columns([3, 2], vertical_alignment="bottom")
    separar = col_separar.toggle(
        "Separar condições compostas (OR / AND)", key="s2_separar",
        help="Desligado: `IF a < 0 OR b < 0 THEN` é UMA decisão. Ligado: cada condição simples vira um nó de "
             "decisão — o V(G) aumenta e o teste fica mais rigoroso. Confirme com o professor qual convenção usar.")
    grafos = _grafos(codigo, separar)
    if not grafos:
        st.info("Não achei nenhuma FUNCTION (Informix-4GL) nem def (Python) no texto para montar o grafo.")
        return None
    nomes = list(grafos)
    preferida = st.session_state.get("s1_unidade")           # a mesma unidade escolhida na Sprint 1
    padrao = nomes.index(preferida) if preferida in nomes else max(range(len(nomes)), key=lambda i: _vg(grafos[nomes[i]]))
    nome = col_unidade.selectbox("Unidade (FUNCTION) para montar o grafo", nomes, index=padrao,
                                 help="Funções que o Python encontrou no arquivo.")
    g = grafos[nome]
    if isinstance(g, str):
        st.error(f"Não deu para montar o grafo de `{nome}`: {g}.")
        return None
    a = cb.analisar(g)
    vg_alternativo = _vg(_grafos(codigo, not separar).get(nome)) or a["vg"]
    contexto = f"{nome}:{separar}:" + hashlib.md5(codigo.encode()).hexdigest()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Nós (N)", a["N"], border=True, help="Blocos de comandos que sempre executam juntos")
    m2.metric("Arestas (E)", a["E"], border=True, help="Desvios possíveis entre os blocos")
    m3.metric("Decisões (P)", a["P"], border=True, help="Nós com mais de uma saída (IF, WHILE, CASE…)")
    m4.metric("V(G) = E − N + 2", a["vg"], border=True, help="Caminhos independentes = mínimo de casos de teste")
    m5.metric("Risco (McCabe)", a["risco"].split(" —")[0], border=True, help=a["risco"])

    col_grafo, col_lado = st.columns([2, 3], gap="large")
    with col_lado:
        sequencia = {c["Caminho"]: c["Sequência de nós"] for c in a["caminhos"]}
        escolha = st.selectbox("Destacar um caminho básico no grafo", ["—", *sequencia], key=f"s2_destaque:{contexto}",
                               format_func=lambda c: "nenhum" if c == "—" else f"{c}: {sequencia[c]}")
        destaque = next((c["_arestas"] for c in a["caminhos"] if c["Caminho"] == escolha), None)
        aba_nos, aba_arestas = st.tabs([f"Nós ({a['N']})", f"Arestas ({a['E']})"])
        with aba_nos:                       # st.table quebra a linha: o comando aparece inteiro
            st.table(pd.DataFrame(a["nos"]), hide_index=True, border="horizontal")
        with aba_arestas:
            st.table(pd.DataFrame(a["arestas"]), hide_index=True, border="horizontal")
    with col_grafo:
        st.graphviz_chart(cb.dot(g, destaque))
        st.caption("🟩 início · 🟦 bloco · 🔶 decisão (losango) · 🟪 fim (círculo duplo) · **V**/**F** = condição "
                   "verdadeira/falsa. Passe o mouse num nó para ver as linhas e os comandos.")

    # ─── 3. V(G) ───────────────────────────────────────────────────────────
    st.header("3️⃣ Complexidade ciclomática V(G)")
    st.dataframe(pd.DataFrame(a["formas"]), hide_index=True)
    if a["confere"]:
        st.success(f"As três formas dão **V(G) = {a['vg']}** (as decisões contadas no código-fonte também: "
                   f"{a['decisoes_codigo']} + 1). São necessários pelo menos **{a['vg']} casos de teste** para "
                   f"exercitar todos os caminhos independentes. Risco: {a['risco']}.")
    else:
        st.warning(f"As formas não bateram (decisões contadas no código-fonte: {a['decisoes_codigo']} + 1). "
                   "Confira os avisos abaixo — código que nunca executa ou um desvio que o Python não reconheceu.")
    for aviso in a["avisos"]:
        st.warning(aviso)
    if vg_alternativo != a["vg"]:
        st.info(f"📌 Esta unidade tem condição composta (OR/AND). "
                f"{'Separando' if not separar else 'Sem separar'} as condições, V(G) = {vg_alternativo}. "
                "Use a chave **Separar condições compostas** para comparar e confirme com o professor qual convenção usar.")
    st.caption("Escala de McCabe: 1–10 baixo · 11–20 moderado · 21–50 alto · acima de 50 muito alto.")

    # ─── 4. Caminhos básicos → casos de teste ──────────────────────────────
    st.header("4️⃣ Caminhos básicos → casos de teste")
    st.caption("Método da linha de base (McCabe): parte do caminho mais curto e, em cada decisão, troca de lado. "
               "Cada caminho vira um caso de teste. Atenção: um caminho pode ser **inviável** (nenhuma entrada o "
               "percorre); nesse caso, troque-o por outro caminho independente.")
    caminhos = pd.DataFrame(a["caminhos"]).drop(columns=["_arestas"])
    st.table(caminhos, hide_index=True, border="horizontal")
    if a["todos_arcos"]:
        st.caption("✅ Juntos, os caminhos passam por todas as arestas do grafo (critério todos-arcos).")
    st.download_button("⬇️ Caminhos básicos (CSV para Excel)", caminhos.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       file_name=f"caminhos_basicos_{nome}.csv", mime="text/csv", on_click="ignore")

    trecho, linha0 = cb.trecho_da_unidade(codigo, nome)
    if cliente is None:
        st.info("Conecte a Gemini API na barra lateral para a IA sugerir as entradas de cada caminho.")
    elif st.button("🧠 Sugerir entradas para cada caminho",
                   help="A IA propõe valores que forçam cada caminho e avisa quando um caminho é inviável"):
        with st.spinner("O Gemini está pensando nas entradas de cada caminho…"):
            try:
                nos = "\n".join(f"{n['Nó']} (linhas {n['Linhas']}): {n['Comandos']}" for n in a["nos"])
                lista = "\n".join(f"{c['Caminho']}: {c['Sequência de nós']} | {c['Decisões tomadas']}"
                                  for c in a["caminhos"])
                st.session_state.s2_sugestao = (contexto, ia.sugerir_caminhos(cliente, modelo, trecho, nome, nos, lista))
            except Exception as erro:
                st.error(ia.explicar_erro(erro))
    textos = []
    if st.session_state.get("s2_sugestao", ("",))[0] == contexto:
        with st.container(border=True):
            st.markdown(st.session_state.s2_sugestao[1])
        textos.append((f"Sprint 2 — Entradas sugeridas para os caminhos ({nome})", st.session_state.s2_sugestao[1]))

    # ─── Arquivo inteiro e código com a numeração do grafo ────────────────
    visao = cb.visao_arquivo(grafos)
    total = sum(v["V(G)"] for v in visao if isinstance(v["V(G)"], int))
    with st.expander(f"📁 Complexidade de todas as unidades do arquivo — esforço total: {total} caminhos"):
        st.dataframe(pd.DataFrame(visao), hide_index=True)
    with st.expander("📄 Código da unidade com a numeração usada no grafo"):
        st.code("\n".join(f"{linha0 + i:>4}  {linha}" for i, linha in enumerate(trecho.split("\n"))), language=None)

    dados = {"arquivo": st.session_state.get("nome_arquivo", ""), "unidade": nome, "codigo": trecho,
             "linha_inicial": linha0, "analise": a, "grafo": g, "visao": visao, "separar": separar,
             "vg_alternativo": vg_alternativo, "textos_ia": textos}
    st.divider()
    st.download_button("📄 Baixar PDF da Sprint 2", type="primary", mime="application/pdf", on_click="ignore",
                       file_name=f"sprint2_caixa_branca_{nome}.pdf",
                       data=partial(relatorio_pdf.gerar, aluno=st.session_state.get("pdf_aluno", ""),
                                    sprint2=dados, textos_ia=textos))
    return dados
