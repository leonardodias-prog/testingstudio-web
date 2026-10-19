# 🧪 TestingStudio Web

Laboratório de Teste de Software I (Ementa 62371) · Prof. Frank Piffer
Base teórica: DELAMARO, MALDONADO e JINO (2007), *Introdução ao Teste de Software* · McCABE (1976).

| Aba | Aula | O que o app faz |
|---|---|---|
| **Sprint 1 — Caixa-Preta** | 05/10 | lê o CAD0001 e aplica **PCE** e **AVL com ε** (o Python calcula, não a IA) + régua On/Off/Interior/Exterior |
| **Sprint 2 — Caixa-Branca** | — | **sobre a mesma base**: monta o **Grafo de Fluxo de Controle (GFC)**, calcula **V(G) de McCabe** de três formas e lista os **caminhos básicos** |
| **Aula 14/10 — Casos de teste + RTM** | 14/10 | requisitos → casos de teste (fluxo principal, alternativo e exceção) → **Matriz de Rastreabilidade** com cobertura de ida e volta |
| **Exportar PDF** | — | relatório com capa, sumário clicável, as seções escolhidas, gráficos e (opcional) os textos da IA |

```
Você (auditor) ──► Streamlit (tela web) ──► Python: caixa_preta.py · caixa_branca.py · rtm.py  (as contas)
                                        ├─► graficos.py      (régua, grafo e cobertura — tela e PDF)
                                        ├─► Gemini API: ia_gemini.py  (explica, sugere e revisa)
                                        └─► relatorio_pdf.py (PDF)
```

---

## 1. Instalação

| Item | Situação |
|---|---|
| Python 3.11+ | ✅ |
| `streamlit`, `google-genai`, `matplotlib`, `fpdf2` | ✅ instalados — lista em `requirements.txt` (o `rodar.bat` instala se faltar) |
| **Chave da Gemini API** | cada pessoa cria a sua (abaixo) |

### Criar a chave (2 minutos, grátis)

1. Acesse **https://aistudio.google.com/apikey** e entre com sua conta Google.
2. Clique em **Create API key** e copie a chave.
3. Abra `.streamlit/secrets.toml` (no Bloco de Notas mesmo) e troque `COLE_SUA_CHAVE_AQUI`
   pela sua chave, **mantendo as aspas**: `GEMINI_API_KEY = "AIza..."`. Salve.
   Se o arquivo não existir (projeto baixado do GitHub), copie `.streamlit/secrets.toml.exemplo`
   com o nome `secrets.toml` e faça o mesmo.

> Sem chave o app funciona assim mesmo: as análises são Python puro. Só os botões de IA ficam
> desligados. Também dá para colar a chave na barra lateral (vale só enquanto o app estiver aberto).

---

## 2. Como abrir

**Dois cliques em `rodar.bat`.** O navegador abre em `http://localhost:8501`. Para fechar, feche a janela preta.

Ou, num terminal dentro desta pasta:

```bash
python -m streamlit run app.py
```

---

## 3. Sprint 1 — Auditoria de Caixa-Preta do CAD0001

1. **Ler o arquivo** — *Upload* do `.txt` ou um dos exemplos: **CAD0001 do manual** (regra: valores
   negativos devolvem `-1`) ou **CAD0001 completo** (o `.txt` com inclusão/alteração/exclusão).
2. **Entender com a IA** — o Gemini explica a unidade (entradas, saídas, regras).
3. **Aplicar a caixa-preta** — o Python lê o código e preenche as entradas sozinho: tipo, casas
   decimais, NULL tratado e a **regra de negócio** (`IF ... < 0 THEN RETURN -1` vira "mínimo 0,00").
   Abas de resultado:

| Aba | O que mostra |
|---|---|
| **ε Épsilon** | o ε de cada variável, como foi calculado e de onde vêm os limites |
| **PCE — classes** | classes válidas e inválidas, representante e quais casos cobrem cada uma |
| **AVL — limites** | para cada fronteira X: X − ε, X e X + ε |
| **📊 Gráfico de fronteira** | uma régua com os 4 pontos do manual: **On** (0,00) · **Off** (−0,01) · **Interior** (100,00) · **Exterior** (−100,00) e o resultado esperado de cada um |
| **Casos de teste** | a tabela final com o **resultado esperado** (CSV para Excel) |

4. **Revisão com a IA** — o Gemini aponta o que faltou; você decide (**Protocolo 4**).

**Resultado no CAD0001 do manual** — ε = 0,01 (`DECIMAL(12,2)`), e os pontos batem com a Tabela 1:

| Ponto | Valor | Esperado |
|---|---|---|
| On | 0,00 | sucesso (cálculo ok) |
| Off | −0,01 | **Erro (−1)** |
| Interior | 100,00 | sucesso |
| Exterior | −100,00 | **Erro (−1)** |

**Achados para o relatório:**
* **NULL** — o manual classifica NULL como classe inválida, mas o código troca NULL por 0. O app
  avisa: para seguir o manual, desmarque "aceita NULL" e registre a divergência.
* **Estouro** — cada entrada aceita até 9.999.999.999,99, mas o *produto* estoura o `DECIMAL(12,2)`
  da saída bem antes. O app acha a fronteira exata (ex.: `50 × 51 + 9999997449,99` = 9.999.999.999,99
  e +0,01 já estoura). O código não trata isso: execute no Logix e registre o que acontece.

---

## 4. Sprint 2 — Auditoria de Caixa-Branca (sobre a mesma base)

> Caixa-preta olha **o que** o programa faz (entradas e saídas). Caixa-branca olha **como** ele faz:
> a estrutura do código. O app usa **o mesmo código** lido na Sprint 1.

1. **O código** — o mesmo da aba Sprint 1 (ou os botões de exemplo da própria aba). Também lê
   funções Python (`def`), para exercícios em Python.
2. **GFC — Grafo de Fluxo de Controle** — cada **nó** é um bloco de comandos que sempre executam
   juntos; cada **aresta** é um desvio possível. Decisão = losango, com as saídas **V**/**F**.
   Passe o mouse num nó para ver as linhas e os comandos; escolha um caminho para pintá-lo de verde.
   * **Separar condições compostas** — desligado, `IF a < 0 OR b < 0` é *uma* decisão; ligado,
     cada condição simples vira um nó de decisão (V(G) maior, teste mais rigoroso).
3. **V(G) — complexidade ciclomática de McCabe**, de três formas que precisam bater:
   `E − N + 2` (arestas − nós + 2) · `P + 1` (nós de decisão + 1) · nº de caminhos básicos.
   Escala: 1–10 baixo · 11–20 moderado · 21–50 alto · acima de 50 muito alto.
4. **Caminhos básicos → casos de teste** — método da linha de base: parte do caminho mais curto e,
   em cada decisão, troca de lado. Um caso de teste por caminho; juntos cobrem todas as arestas.
   * 🧠 **Sugerir entradas para cada caminho** — o Gemini propõe valores que forçam cada caminho e
     avisa quando um caminho é **inviável** (nenhuma entrada o percorre).
5. **Arquivo inteiro** — V(G) de todas as unidades e o esforço total de teste.

**Resultado no CAD0001 do manual** (`cad0001_calcula_valor`):

| Forma | Conta | V(G) |
|---|---|---|
| Arestas − nós + 2 | 16 − 13 + 2 | **5** |
| Nós de decisão + 1 | 4 + 1 | **5** |
| Caminhos básicos | C1 … C5 | **5** |

São necessários pelo menos **5 casos de teste** · risco baixo. No **CAD0001 completo**:
`main` 1 · `calcula_valor` 4 · `incluir` 3 · `alterar` 3 · `excluir` 3 → esforço total de **14 caminhos**.

**Pergunte ao professor:** a linha `IF p_val1 < 0 OR p_val2 < 0 OR p_val3 < 0` conta como
**1 decisão** (V(G) = 5) ou como **3 condições** (V(G) = 7)? O app mostra as duas contas.

---

## 5. Aula 14/10 — Derivação de casos de teste e RTM

> Laboratório: *aplique a derivação em um cenário livre no ambiente da plataforma.*

1. **Cenário e requisitos** — o exemplo da aula (*Sistema de Biblioteca Universitária*, REQ01–REQ05)
   já vem carregado. Para o cenário livre, troque o texto (um requisito por linha, ex.
   `[REQ01]: Cadastro de livros…`) ou envie um `.txt`.
2. **Derivar os casos de teste** — do caso de uso saem os fluxos:
   **principal** (caminho feliz) · **alternativos** (desvios e limites, com AVL e ε) · **exceção** (bloqueios).
   * 🧠 **Derivar com a IA** — o Gemini sugere de 1 a 3 casos por requisito (uns 20 s).
   * 📝 **Modelos sem IA** — o Python cria um caso por fluxo que identifica em cada requisito; você completa.
   * Edite à vontade na tabela; um caso pode rastrear vários requisitos (`REQ01, REQ04, REQ05`).
3. **Matriz de Rastreabilidade (RTM)** — calculada pelo Python (`rtm.py`):
   * **Ida** — *tudo o que foi pedido foi coberto?* (todo requisito tem caso de teste)
   * **Volta** — *tudo o que foi testado foi pedido?* (todo caso aponta para um requisito que existe)
   * Avisa requisito sem teste, teste órfão e rastreio para requisito inexistente.
4. **Revisão com a IA** — fluxos de exceção e limites que faltaram, oráculos vagos, rastreios errados.

Exemplo da aula na RTM: CT01 (caminho feliz) → REQ01, REQ04, REQ05 · CT02 (exceção) → REQ02 ·
CT03 (limite da multa: 0, 1 e 2 dias → R$ 0,00 · 2,00 · 4,00) → REQ03 — ida 5/5 e volta 3/3.

---

## 6. Exportar PDF

Aba **📄 Exportar PDF**: escreva seu nome/equipe (vai na capa), marque as seções e, se quiser,
anexe os textos da IA. Cada aba também tem o seu botão **Baixar PDF**.

O relatório tem: **capa** com o resumo em cartões · **sumário clicável** · cabeçalho com a seção e
rodapé com a página · caixas de **achados** (estouro, NULL, condição composta) · código com
numeração de linhas · tabelas zebradas · a **régua** de cada fronteira · o **GFC** ao lado da tabela
de nós · a RTM e o gráfico de cobertura · e, no anexo, os textos da IA.

---

## 7. Mapa do código

| Arquivo | Papel |
|---|---|
| `app.py` | a casca: página, autenticação (barra lateral), abas e exportação |
| `sprint1_caixa_preta.py` | tela da Sprint 1 |
| `sprint2_caixa_branca.py` | tela da Sprint 2 |
| `aula_rtm.py` | tela da aula de 14/10 (casos de teste + RTM) |
| `caixa_preta.py` | **motor da Sprint 1** (Python puro): leitura do `.txt`, extração do 4GL, ε, PCE, AVL, pontos de fronteira e oráculo |
| `caixa_branca.py` | **motor da Sprint 2** (Python puro): GFC do 4GL ou do Python, V(G) de três formas e caminhos básicos |
| `rtm.py` | **motor da RTM** (Python puro): requisitos, casos de teste e cobertura bidirecional |
| `graficos.py` | desenhos (matplotlib): régua de fronteira, grafo e cobertura |
| `ia_gemini.py` | Gemini: explicar, interpretar, sugerir, derivar e revisar (com troca automática de modelo) |
| `relatorio_pdf.py` | o PDF (fpdf2) |
| `exemplos/` | CAD0001 do manual e o `.txt` completo |
| `.streamlit/secrets.toml` | sua chave — fica **fora** do Git |

---

## 8. Git (Protocolo 2)

> "Código não salvo no repositório é código que não existe."

```bash
git add .
```

```bash
git commit -m "Sprint 2: caixa-branca (GFC + V(G)), RTM da aula 14/10 e PDF novo"
```

```bash
git push
```

**E a chave?** O `.streamlit/secrets.toml` está no `.gitignore`: a chave fica só no seu PC.
Antes de commitar, rode `git status` — o `secrets.toml` **não** pode aparecer na lista.

---

## 9. Problemas comuns

| Mensagem | O que fazer |
|---|---|
| `python não é reconhecido` | instale o Python 3.11+ (python.org, marque *Add to PATH*) |
| *Chave inválida* | gere outra no AI Studio; confira as aspas no `secrets.toml` |
| *secrets.toml tem erro de formato* | a chave está sem aspas — veja a seção 1 |
| *Modelos sobrecarregados* / demora | o app já tenta outros modelos sozinho; espere 1 minuto e tente de novo |
| *Limite gratuito atingido* | espere 1 minuto e tente de novo |
| *não tem END IF* (Sprint 2) | o código tem um `IF`/`WHILE`/`CASE` sem o fechamento — confira a linha indicada |
| mudou algum `.py` e o app não mudou | feche a janela preta e abra o `rodar.bat` de novo |
| a página não abre | veja na janela preta o endereço (pode ser `localhost:8502`) |
