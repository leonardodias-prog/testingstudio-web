# 🧪 TestingStudio Web — Sprint 1 (Marco Zero)

Laboratório de Teste de Software I · Módulo 1: **Teste Funcional (Caixa-Preta)**
Base teórica: DELAMARO, MALDONADO e JINO (2007), *Introdução ao Teste de Software*.

O app lê um arquivo `.txt` (código ou requisito), deixa a IA (Gemini) explicar o código e
aplica a caixa-preta: **PCE** (classes de equivalência) e **AVL** (valor-limite) com o
**ε calculado pelo Python** — como pede o manual, a IA não faz a conta.

```
Você (auditor) ──► Streamlit (tela web) ──► Python: caixa_preta.py (PCE, AVL, ε)
                                        └─► Gemini API: ia_gemini.py (explica e revisa)
```

---

## 1. O que já está instalado e o que falta

| Item | Situação |
|---|---|
| Python 3.11 | ✅ já estava no seu PC |
| `streamlit` (tela web) e `google-genai` (Gemini API) | ✅ instalados (`requirements.txt`) |
| **Chave da Gemini API** | ❌ **só você pode criar** (passo abaixo) |

### Criar a chave (2 minutos, grátis)

1. Acesse **https://aistudio.google.com/apikey** e entre com sua conta Google.
2. Clique em **Create API key** e copie a chave.
3. Abra o arquivo `.streamlit/secrets.toml` (no Bloco de Notas mesmo) e troque
   `COLE_SUA_CHAVE_AQUI` pela sua chave, **mantendo as aspas**:
   `GEMINI_API_KEY = "AIza..."`. Salve.
   Se o arquivo não existir (projeto baixado do GitHub), copie
   `.streamlit/secrets.toml.exemplo` com o nome `secrets.toml` e faça o mesmo.

> Sem chave o app funciona assim mesmo: os Passos 1 e 3 (leitura + caixa-preta) são Python
> puro. Só os Passos 2 e 4 (IA) ficam desligados. Também dá para colar a chave na barra
> lateral do app, mas aí ela vale só enquanto o app estiver aberto.

---

## 2. Como abrir

**Dois cliques em `rodar.bat`.** O navegador abre em `http://localhost:8501`.
Para fechar, feche a janela preta.

Ou, num terminal dentro desta pasta:

```bash
python -m streamlit run app.py
```

---

## 3. Passo a passo no app

**1️⃣ Ler o arquivo .txt** — clique em *Upload* e escolha o `.txt` (ou em *Exemplo CAD0001*).
O conteúdo aparece na caixa de texto (pode editar ou colar outro código ali). Escolha a
**unidade** (FUNCTION). O app já abre na regra de negócio: `cad0001_calcula_valor`.

**2️⃣ Entender com a IA** — *Explicar esta unidade com o Gemini*: a IA descreve o que a
função faz, entradas, saídas, regras de negócio e sugere classes. Use isso para **estudar**
o código antes de testar.

**3️⃣ Aplicar a caixa-preta** — o Python lê o código e preenche a tabela de entradas
sozinho (tipo, tamanho, casas decimais, se aceita NULL). Você só confere e, se a regra de
negócio tiver limites, preenche *limite inferior/superior* (ex.: `cod_item` ≥ 1).
Os resultados saem em 4 abas:

| Aba | O que mostra |
|---|---|
| **ε Épsilon** | o ε de cada variável e como foi calculado |
| **PCE — classes** | classes válidas/inválidas, representante e quais casos cobrem cada classe |
| **AVL — limites** | para cada fronteira X: X − ε, X, X + ε (✅ válido / ❌ inválido) |
| **Casos de teste** | a tabela final com o **resultado esperado** — botão para baixar em CSV (Excel) |

**4️⃣ Revisão com a IA** — *Pedir revisão*: o Gemini aponta classes ou limites que
faltaram. Você decide o que aceitar (**Protocolo 4: nada de copiar e colar cego**).

> Texto que não é Informix-4GL (Python, Java, um enunciado em português)? Use o botão
> **Preencher a tabela com a IA** no Passo 3, ou adicione as linhas à mão na tabela.

---

## 4. A metodologia aplicada no CAD0001

Unidade: `cad0001_calcula_valor(p_val1, p_val2, p_val3)` → `(p_val1 * p_val2) + p_val3`,
NULL vira 0, resultado em `DECIMAL(12,2)`.

* **ε** — `DECIMAL(12,2)` tem 2 casas → **ε = 10⁻² = 0.01**. Faixa do tipo:
  −9999999999.99 a 9999999999.99.
* **PCE** — para cada parâmetro: dentro da faixa (válida), abaixo (inválida), acima
  (inválida) e NULL (válida, vira 0). A **saída** também tem classes: dentro do tipo ou estouro.
* **AVL** — no máximo: `9999999999.98 ✅`, `9999999999.99 ✅`, `10000000000.00 ❌`.
* **AVL na saída** — o Python descobre o valor exato que leva o resultado à fronteira:
  com `p_val1 = 50.00` e `p_val2 = 51.00`, `p_val3 = 9999997449.99` dá exatamente
  9999999999.99 (cabe) e **+0.01 já estoura**.

**O que o teste revela:** cada entrada aceita até 9.999.999.999,99, mas o *produto*
estoura o `DECIMAL(12,2)` da saída bem antes disso (ex.: CT13, `9999999999.99 × 51 + 52`).
O código não trata esse estouro — execute esses casos no Logix e registre o que acontece.
Se o programa abortar ou gravar valor errado, é **defeito**.

---

## 5. Mapa do código

| Arquivo | Papel | Sprint 1 |
|---|---|---|
| `app.py` | a tela web (Streamlit), os 4 passos | Objetivos 1 e 4 |
| `caixa_preta.py` | leitura do `.txt`, extração do 4GL, **ε, PCE, AVL** e resultado esperado (Python puro) | Lógica de engenharia |
| `ia_gemini.py` | conexão com o Gemini: explicar, interpretar, revisar | Objetivos 2 e 3 |
| `.streamlit/secrets.toml` | sua chave (fica **fora** do Git) | Objetivo 2 |
| `exemplos/cad0001_item_calculo.txt` | o código do professor | — |

Funções-chave em `caixa_preta.py`, na ordem em que rodam:
`ler_txt` → `extrair_unidades` → `calcular_epsilon` → `classes_equivalencia` →
`valores_limite` → `casos_de_teste` → `resultado_esperado`.

---

## 6. Salvar no Git (Protocolo 2)

> "Código não salvo no repositório é código que não existe."

```bash
git init
```

```bash
git add .
```

```bash
git commit -m "Sprint 1: TestingStudio Web - marco zero"
```

Depois crie um repositório vazio no GitHub e siga as instruções de *push* que ele mostra.

**E a chave?** O `.streamlit/secrets.toml` está no `.gitignore`: o Git nem enxerga esse
arquivo, então a chave fica só no seu PC. Para o GitHub vai só o modelo
`secrets.toml.exemplo`; quem clonar o projeto cria o próprio `secrets.toml` com a própria chave.

* Antes do primeiro commit rode `git status`: o `secrets.toml` **não** pode aparecer na lista.
* Nunca use `git add -f` nesse arquivo nem cole a chave dentro do código (`app.py`).
* Se a chave vazar, apague-a no AI Studio e gere outra.

---

## 7. Problemas comuns

| Mensagem | O que fazer |
|---|---|
| `python não é reconhecido` | instale o Python 3.11+ (python.org, marque *Add to PATH*) |
| *Chave inválida* | gere outra no AI Studio; confira as aspas no `secrets.toml` |
| *secrets.toml tem erro de formato* | a chave está sem aspas — veja o passo 3 da seção 1 |
| *Modelos sobrecarregados* / demora | o app já tenta outros modelos sozinho; espere 1 minuto ou escolha outro na barra lateral |
| *Limite gratuito atingido* | espere 1 minuto e tente de novo |
| mudou algum `.py` e o app não mudou | feche a janela preta e abra o `rodar.bat` de novo |
| a página não abre | veja na janela preta o endereço (pode ser `localhost:8502`) |
