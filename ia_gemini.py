"""
ia_gemini.py — Conexão com a Gemini API (motor de análise baseado em IA)
=========================================================================
A IA é parceira de pareamento (Protocolo 4): ela EXPLICA o código, INTERPRETA
textos e REVISA os casos de teste. Quem calcula PCE, AVL e ε é o Python
(caixa_preta.py) — a lógica não é terceirizada para a IA.

Chave gratuita: https://aistudio.google.com/apikey
"""

import json

import httpx
from google import genai
from google.genai import errors, types

from caixa_preta import TIPOS

# estáveis e menos disputados primeiro (os mais novos vivem sobrecarregados, erro 503);
# se nenhum existir, vale o 1º "flash" da lista. Dá para trocar na barra lateral.
PREFERIDOS = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-2.5-flash", "gemini-3.6-flash",
              "gemini-3.7-flash", "gemini-3.8-flash"]
NAO_TEXTO = ("tts", "image", "live", "audio", "embedding", "transcribe", "computer",
             "robotics", "veo", "lyria", "imagen", "research", "antigravity")
OCUPADO = (404, 429, 500, 503, 504)   # modelo indisponível, ocupado ou no limite: tenta o próximo
ESPERA_MAXIMA = 45                    # segundos por modelo; passou disso, tenta o próximo

PAPEL = ("Você é engenheiro(a) de testes e professor(a) de Teste de Software. "
         "Base teórica: DELAMARO, MALDONADO e JINO (2007), 'Introdução ao Teste de Software'. "
         "Responda em português do Brasil, em Markdown, de forma direta e didática. "
         "Não use LaTeX nem $...$: escreva valores e nomes de variáveis como `código`.")


def conectar(chave: str):
    """Cria o cliente da API (ainda não usa a internet)."""
    return genai.Client(api_key=chave)


def listar_modelos(cliente) -> list:
    """Modelos de texto liberados para a chave. Também serve para testar a conexão."""
    config = types.ListModelsConfig(http_options=types.HttpOptions(timeout=15_000))
    modelos = []
    for m in cliente.models.list(config=config):
        nome = (m.name or "").removeprefix("models/")
        if ("generateContent" in (m.supported_actions or []) and nome.startswith("gemini")
                and not any(p in nome for p in NAO_TEXTO)):
            modelos.append(nome)
    modelos.sort(key=lambda n: (PREFERIDOS.index(n) if n in PREFERIDOS else len(PREFERIDOS),
                                "flash" not in n, "lite" in n, "preview" in n or "exp" in n, n))
    return modelos


def chave_recusada(erro: Exception) -> bool:
    """O erro é da CHAVE (inválida/sem permissão)? Se for só lentidão, a IA continua ligada."""
    if not isinstance(erro, errors.APIError):
        return False
    texto = f"{erro.status or ''} {erro.message or ''}"
    return "API key" in texto or "API_KEY" in texto or erro.code in (401, 403)


def _gerar(cliente, modelos, prompt: str, json_saida: bool = False) -> str:
    """Pede ao 1º modelo da lista; se ele estiver ocupado ou demorar, tenta os próximos (até 4)."""
    tentativas = ([modelos] if isinstance(modelos, str) else list(modelos))[:4]
    config = types.GenerateContentConfig(
        response_mime_type="application/json" if json_saida else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        http_options=types.HttpOptions(timeout=ESPERA_MAXIMA * 1000),   # em milissegundos
    )
    for i, modelo in enumerate(tentativas):
        try:
            resposta = cliente.models.generate_content(model=modelo, contents=prompt, config=config)
        except (errors.APIError, httpx.TimeoutException) as erro:
            ocupado = isinstance(erro, httpx.TimeoutException) or erro.code in OCUPADO
            if ocupado and i < len(tentativas) - 1:
                continue   # modelo ocupado ou lento: tenta o próximo da lista
            raise
        texto = resposta.text or ""
        if i > 0 and not json_saida:
            texto += f"\n\n*(Respondido pelo {modelo}: o {tentativas[0]} estava ocupado.)*"
        return texto


def explicar(cliente, modelos, codigo: str, unidade: str) -> str:
    """Passo 2 — a IA lê o código e explica a unidade em linguagem natural."""
    return _gerar(cliente, modelos, f"""{PAPEL}

Analise a unidade `{unidade}` do código abaixo como um testador CAIXA-PRETA:
1. **O que faz** — 2 ou 3 frases simples.
2. **Entradas e saídas** — nome, tipo de dado e domínio válido de cada uma.
3. **Regras de negócio** — ex.: tratamento de NULL, fórmulas, transação (COMMIT/ROLLBACK).
4. **Classes de equivalência (PCE)** — válidas e inválidas, em tabela.
5. **Valores-limite (AVL)** — as fronteiras e o ε (menor variação) de cada tipo.
Não escreva código.

```
{codigo}
```""")


def extrair_entradas(cliente, modelos, texto: str, unidade: str) -> list:
    """Passo 3 (opcional) — interpreta qualquer texto (outra linguagem ou um requisito
    em português) e devolve as entradas como dicionários para a tabela."""
    resposta = _gerar(cliente, modelos, f"""{PAPEL}

Liste as VARIÁVEIS DE ENTRADA da unidade "{unidade}" no texto abaixo (código ou requisito).
Responda SOMENTE com um JSON: uma lista de objetos com as chaves
  "nome" (texto), "tipo" (um de {TIPOS}),
  "tamanho" (p de DECIMAL(p,s) ou n de CHAR(n); null se não houver),
  "casas" (s de DECIMAL(p,s); null se não houver),
  "minimo" e "maximo" (limites da regra de negócio, como texto; "" se o texto não disser),
  "aceita_nulo" (true/false) e "se_nulo" (valor que o NULL assume, ex.: "0").
Não invente limites: se o texto não define, deixe "".

{texto}""", json_saida=True)
    dados = json.loads(resposta)
    if isinstance(dados, dict):              # às vezes vem {"entradas": [...]}
        dados = next((v for v in dados.values() if isinstance(v, list)), [])
    return [d for d in dados if isinstance(d, dict)]


def revisar(cliente, modelos, codigo: str, unidade: str, casos_csv: str) -> str:
    """Passo 4 — revisão (pair programming) dos casos que o Python gerou."""
    return _gerar(cliente, modelos, f"""{PAPEL}

Você está revisando, em pair programming, os casos de teste abaixo. Eles foram gerados por
um programa Python aplicando PCE e AVL (ε calculado pelo tipo de dado) na unidade `{unidade}`.
Aponte SÓ o que falta ou está errado:
1. Classes de equivalência esquecidas (de regras de negócio, da saída, de combinações).
2. Valores-limite que faltam ou estão incorretos.
3. Resultados esperados suspeitos.
4. Até 5 casos de teste extras, numa tabela Markdown.

--- CÓDIGO ---
{codigo}

--- CASOS DE TESTE (CSV) ---
{casos_csv}""")


def explicar_erro(erro: Exception) -> str:
    """Traduz os erros mais comuns da API para algo que dá para resolver."""
    if isinstance(erro, errors.APIError):
        if chave_recusada(erro):
            return "Chave da Gemini API inválida ou sem permissão. Gere outra em https://aistudio.google.com/apikey"
        if erro.code == 404:
            return "Modelo não encontrado para esta chave — escolha outro na barra lateral."
        if erro.code == 429:
            return "Limite gratuito da Gemini API atingido. Espere um minuto e tente de novo."
        if erro.code >= 500:
            return "Os modelos do Gemini estão sobrecarregados agora. Tente de novo em instantes."
        return f"Erro da Gemini API ({erro.code}): {erro.message}"
    if isinstance(erro, httpx.TimeoutException):
        return ("O Gemini demorou demais para responder (modelos sobrecarregados). "
                "Tente de novo em instantes ou escolha outro modelo na barra lateral.")
    if isinstance(erro, json.JSONDecodeError):
        return "A IA não devolveu um JSON válido. Tente de novo."
    return f"Não foi possível falar com a Gemini API (confira a internet): {erro}"
