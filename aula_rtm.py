"""
aula_rtm.py — Tela da aula de 14/10: Derivação de Casos de Teste e RTM
=======================================================================
(A Sprint 2 do projeto é a Caixa-Branca — sprint2_caixa_branca.py. Esta aba é o laboratório da aula.)
Laboratório: "aplique a derivação em um cenário livre no ambiente da plataforma".
  1. Cenário e requisitos (texto, .txt ou o exemplo da aula)
  2. Derivar os casos de teste: fluxo principal, alternativos (limites) e exceção
  3. RTM: ida (todo requisito tem teste?) e volta (todo teste foi pedido?)
  4. Revisão com a IA
Quem confere a cobertura é rtm.py (Python puro); a IA só sugere casos e revisa.
"""

import hashlib
from dataclasses import asdict
from functools import partial

import pandas as pd
import streamlit as st

import caixa_preta as cp
import ia_gemini as ia
import relatorio_pdf
import rtm

CAMPOS = ["id", "titulo", "fluxo", "requisitos", "pre_condicoes", "passos", "dados", "resultado_esperado"]


def _para_tabela(casos: list) -> list:
    return [{**asdict(c), "requisitos": ", ".join(c.requisitos)} for c in casos]


def _trocar_casos(casos: list):
    st.session_state.rtm_casos = _para_tabela(casos)
    st.session_state.rtm_versao += 1


def _exemplo():
    st.session_state.rtm_texto = rtm.EXEMPLO_REQUISITOS
    _trocar_casos(rtm.EXEMPLO_CASOS)


def mostrar(cliente, modelo) -> dict | None:
    """Desenha a aba da aula de 14/10 e devolve os dados para o PDF (ou None)."""
    st.session_state.setdefault("rtm_texto", rtm.EXEMPLO_REQUISITOS)
    st.session_state.setdefault("rtm_casos", _para_tabela(rtm.EXEMPLO_CASOS))
    st.session_state.setdefault("rtm_versao", 0)
    st.caption("Aula de 14/10 — Derivação de Casos de Teste e Matriz de Rastreabilidade (RTM). "
               "Laboratório: aplique a derivação num **cenário livre**. Base: Delamaro, Maldonado e "
               "Jino (2007, cap. 2) · Molinari (2008) · SWEBOK V3.0.")

    # ─── 1. Cenário e requisitos ───────────────────────────────────────────
    st.header("1️⃣ Cenário e requisitos")
    col_arquivo, col_exemplo = st.columns([4, 1], vertical_alignment="bottom")
    arquivo = col_arquivo.file_uploader("Requisitos em .txt — um por linha, ex.: [REQ01]: Cadastro de livros…",
                                        type=["txt", "md"], key="rtm_upload")
    col_exemplo.button("📚 Exemplo da aula", on_click=_exemplo,
                       help="Sistema de Biblioteca Universitária (REQ01–REQ05) e os casos CT01–CT03 da aula de 14/10")
    if arquivo is not None and st.session_state.get("rtm_lido") != arquivo.file_id:
        st.session_state.rtm_texto = cp.ler_txt(arquivo.getvalue())
        st.session_state.rtm_lido = arquivo.file_id
    texto = st.text_area("Requisitos do cenário — troque pelos do seu cenário livre", key="rtm_texto", height=170)
    cenario_lido, requisitos = rtm.ler_requisitos(texto)
    cenario = st.text_input("Nome do cenário", value=cenario_lido or "Cenário livre", key=f"rtm_cenario:{cenario_lido}")
    if not requisitos:
        st.info("Escreva pelo menos um requisito (um por linha).")
        return None
    st.dataframe(pd.DataFrame([{"ID": r.id, "Requisito": r.descricao} for r in requisitos]), hide_index=True)

    # ─── 2. Derivar os casos de teste ──────────────────────────────────────
    st.header("2️⃣ Derivar os casos de teste")
    st.caption("Do caso de uso saem os fluxos: **principal** (caminho feliz) · **alternativos** (desvios e "
               "limites — AVL com ε) · **exceção** (bloqueios). Um caso pode rastrear vários requisitos.")
    col_ia, col_modelos, col_zero = st.columns(3)
    if col_ia.button("🧠 Derivar com a IA", disabled=cliente is None,
                     help="Conecte a Gemini API na barra lateral" if cliente is None else
                     "A IA sugere; você confere e edita na tabela"):
        with st.spinner("O Gemini está derivando os casos de teste… (pode levar até 1 minuto)"):
            try:
                dados = ia.derivar_casos(cliente, modelo, cenario, requisitos)
                _trocar_casos(rtm.numerar([rtm.caso_de_dict(d) for d in dados]))
            except Exception as erro:
                st.error(ia.explicar_erro(erro))
    if col_modelos.button("📝 Modelos sem IA", help="Um caso por fluxo que o Python identifica em cada requisito"):
        _trocar_casos(rtm.modelos_sem_ia(requisitos))
    if col_zero.button("🧹 Tabela vazia"):
        _trocar_casos([])

    editada = st.data_editor(
        pd.DataFrame(st.session_state.rtm_casos, columns=CAMPOS), num_rows="dynamic", hide_index=True,
        key=f"rtm_editor:{st.session_state.rtm_versao}",
        column_config={
            "id": st.column_config.TextColumn("CT", help="Em branco = numerado automaticamente"),
            "titulo": st.column_config.TextColumn("Título"),
            "fluxo": st.column_config.SelectboxColumn("Fluxo", options=rtm.FLUXOS, default=rtm.FLUXOS[0]),
            "requisitos": st.column_config.TextColumn("Rastreio (REQs)", help="IDs separados por vírgula: REQ01, REQ04"),
            "pre_condicoes": st.column_config.TextColumn("Pré-condições"),
            "passos": st.column_config.TextColumn("Passos"),
            "dados": st.column_config.TextColumn("Dados de teste"),
            "resultado_esperado": st.column_config.TextColumn("Resultado esperado", help="O oráculo: o que a especificação manda"),
        },
    )
    linhas = [l for l in editada.to_dict("records")
              if any(rtm._txt(l.get(c)) for c in ("titulo", "requisitos", "passos", "resultado_esperado"))]
    casos = rtm.numerar([rtm.caso_de_dict(l) for l in linhas])

    # ─── 3. RTM ────────────────────────────────────────────────────────────
    st.header("3️⃣ Matriz de Rastreabilidade (RTM)")
    m = rtm.matriz(requisitos, casos)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"Ida: {m['ida'][0]}/{m['ida'][1]} requisitos cobertos", rtm.percentual(m["ida"]),
              help="Tudo o que foi pedido foi coberto?")
    k2.metric(f"Volta: {m['volta'][0]}/{m['volta'][1]} testes rastreados", rtm.percentual(m["volta"]),
              help="Tudo o que foi testado foi pedido?")
    k3.metric("Casos de teste", len(casos))
    k4.metric("Principal · Alternat. · Exceção", " · ".join(str(n) for n in m["por_fluxo"].values()))
    if casos and not (m["nao_cobertos"] or m["orfaos"] or m["inexistentes"]):
        st.success("✅ Cobertura bidirecional completa: todo requisito tem teste e todo teste foi pedido.")
    for rid in m["nao_cobertos"]:
        st.warning(f"{rid} não tem nenhum caso de teste (falha na ida).")
    for cid in m["orfaos"]:
        st.warning(f"{cid} não aponta para nenhum requisito — teste órfão (falha na volta).")
    for cid, rid in m["inexistentes"]:
        st.warning(f"{cid} aponta para {rid}, que não existe na lista de requisitos.")
    if m["inexistentes"]:
        st.caption("Trocou os requisitos? Os casos acima são do cenário anterior: derive de novo "
                   "(🧠 IA ou 📝 modelos) ou corrija o rastreio na tabela.")
    st.dataframe(pd.DataFrame(m["linhas"]), hide_index=True)
    st.bar_chart(pd.DataFrame(m["linhas"]), x="Requisito", y="Nº de CTs", height=220)
    tabela_casos = pd.DataFrame(rtm.tabela_casos(casos))
    col_csv1, col_csv2 = st.columns(2)
    col_csv1.download_button("⬇️ RTM (CSV)", pd.DataFrame(m["linhas"]).to_csv(index=False, sep=";").encode("utf-8-sig"),
                             file_name="rtm.csv", mime="text/csv", on_click="ignore")
    col_csv2.download_button("⬇️ Casos de teste (CSV)", tabela_casos.to_csv(index=False, sep=";").encode("utf-8-sig"),
                             file_name="casos_de_teste_rtm.csv", mime="text/csv", on_click="ignore")

    # ─── 4. Revisão com a IA ───────────────────────────────────────────────
    st.header("4️⃣ Revisão com a IA (pair programming)")
    contexto = hashlib.md5((texto + tabela_casos.to_csv()).encode()).hexdigest()
    if cliente is None:
        st.info("Conecte a Gemini API na barra lateral para pedir a revisão.")
    elif st.button("🤝 Revisar a derivação e a RTM"):
        with st.spinner("O Gemini está revisando…"):
            try:
                csv = tabela_casos.to_csv(index=False, sep=";")
                st.session_state.rtm_revisao = (contexto, ia.revisar_rtm(cliente, modelo, cenario, requisitos, csv))
            except Exception as erro:
                st.error(ia.explicar_erro(erro))
    textos = []
    if st.session_state.get("rtm_revisao", ("",))[0] == contexto:
        with st.container(border=True):
            st.markdown(st.session_state.rtm_revisao[1])
        textos.append((f"Aula 14/10 — Revisão da derivação ({cenario})", st.session_state.rtm_revisao[1]))

    dados = {"cenario": cenario, "requisitos": requisitos, "casos": casos, "rtm": m, "textos_ia": textos}
    st.divider()
    st.download_button("📄 Baixar PDF da aula 14/10 (RTM)", type="primary", mime="application/pdf", on_click="ignore",
                       file_name="aula1410_casos_de_teste_rtm.pdf",
                       data=partial(relatorio_pdf.gerar, aluno=st.session_state.get("pdf_aluno", ""),
                                    rtm_dados=dados, textos_ia=textos))
    return dados
