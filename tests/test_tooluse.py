# Aula 0.2 - Tool use, o mecanismo cru.
#
# O ciclo de quatro etapas (declarar, o modelo pede, voce executa,
# voce devolve) escrito na mao, nos dois providers, sem abstracao.
# Estes testes batem na API real: custam token e exigem rede.
# Por isso levam o marcador "integration" e SO rodam quando voce
# chama de proposito: pytest -m integration

import json

import pytest
from dotenv import load_dotenv

# O conftest.py injeta chaves FALSAS para a suite rapida rodar sem
# configuracao. Os testes de integracao precisam das chaves REAIS,
# entao recarregamos o .env com override=True, que substitui as
# falsas se o arquivo existir. Sem .env, nada muda (e os testes de
# integracao nem devem ser rodados).
load_dotenv(override=True)


# ---------- a ferramenta de verdade: Python comum ----------

def buscar_info_lead(email: str) -> dict:
    """Busca dados de um lead pela chave de email.
    Mock: em producao seria uma consulta a CRM ou banco."""
    base_fake = {
        "ana@techflow.com": {
            "nome": "Ana Prado", "empresa": "TechFlow",
            "plano": "trial", "mrr": 0,
        },
        "carlos@datalog.io": {
            "nome": "Carlos Nunes", "empresa": "DataLog",
            "plano": "pro", "mrr": 490,
        },
    }
    return base_fake.get(email, {"erro": "lead nao encontrado"})


# ---------- o MESMO contrato, no dialeto de cada provider ----------

@pytest.fixture
def tool_anthropic():
    # Anthropic: name, description e input_schema no topo.
    return {
        "name": "buscar_info_lead",
        "description": (
            "Busca os dados cadastrais de um lead a partir do email. "
            "Use quando precisar saber empresa, plano ou MRR de um lead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Email do lead, ex: nome@empresa.com",
                }
            },
            "required": ["email"],
        },
    }


@pytest.fixture
def tool_openai():
    # OpenAI: tudo aninhado em "function", e o schema chama "parameters".
    return {
        "type": "function",
        "function": {
            "name": "buscar_info_lead",
            "description": (
                "Busca os dados cadastrais de um lead a partir do email. "
                "Use quando precisar saber empresa, plano ou MRR de um lead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "Email do lead, ex: nome@empresa.com",
                    }
                },
                "required": ["email"],
            },
        },
    }


# ---------- o ciclo completo na Anthropic ----------

@pytest.mark.integration
def test_ciclo_tool_use_anthropic(tool_anthropic):
    from anthropic import Anthropic

    from nucleo import config

    client = Anthropic()  # le ANTHROPIC_API_KEY do ambiente
    pergunta = "Qual e o plano do lead carlos@datalog.io?"
    msgs = [{"role": "user", "content": pergunta}]

    # 1a chamada: o modelo PEDE a ferramenta (etapas 1 e 2).
    resp1 = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=1024,              # obrigatorio na Anthropic
        tools=[tool_anthropic],
        messages=msgs,
    )
    assert resp1.stop_reason == "tool_use"

    tool_block = next(b for b in resp1.content if b.type == "tool_use")
    assert tool_block.name == "buscar_info_lead"
    # Na Anthropic o input JA vem como dicionario Python.
    assert tool_block.input == {"email": "carlos@datalog.io"}

    # Etapa 3: VOCE executa a funcao de verdade.
    resultado = buscar_info_lead(**tool_block.input)

    # Etapa 4: devolve o pedido do modelo + o resultado, pareados
    # pelo tool_use_id, numa mensagem de role "user".
    msgs.append({"role": "assistant", "content": resp1.content})
    msgs.append({
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": tool_block.id,
            "content": json.dumps(resultado),
        }],
    })

    # 2a chamada: agora o modelo RESPONDE em texto.
    resp2 = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=1024,
        tools=[tool_anthropic],
        messages=msgs,
    )
    texto = resp2.content[0].text.lower()
    # "pro" e "datalog" so existem no mock: se aparecem, o modelo
    # leu o resultado da ferramenta, nao inventou.
    assert "pro" in texto or "datalog" in texto


# ---------- o mesmo ciclo na OpenAI ----------

@pytest.mark.integration
def test_ciclo_tool_use_openai(tool_openai):
    from openai import OpenAI

    from nucleo import config

    client = OpenAI()  # le OPENAI_API_KEY do ambiente
    pergunta = "Qual e o plano do lead carlos@datalog.io?"
    msgs = [{"role": "user", "content": pergunta}]

    r1 = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        tools=[tool_openai],
        messages=msgs,
    )
    msg = r1.choices[0].message
    tool_call = msg.tool_calls[0]
    assert tool_call.function.name == "buscar_info_lead"

    # DIFERENCA 2: arguments vem como STRING JSON, nao como dict.
    args = json.loads(tool_call.function.arguments)
    resultado = buscar_info_lead(**args)

    # DIFERENCA 3: devolve com role "tool" e tool_call_id.
    msgs.append(msg)  # a mensagem do assistant com o tool_call
    msgs.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(resultado),
    })

    r2 = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        tools=[tool_openai],
        messages=msgs,
    )
    texto = r2.choices[0].message.content.lower()
    assert "pro" in texto or "datalog" in texto
