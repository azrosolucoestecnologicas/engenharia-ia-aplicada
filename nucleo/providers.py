# SDKs oficiais de cada provider.
from anthropic import Anthropic
from openai import OpenAI

# Nossa config (nomes de modelo), que mora no pacote nucleo.
from nucleo import config

# Um cliente de cada. Eles leem a chave do ambiente sozinhos.
_anthropic = Anthropic()
_openai = OpenAI()


def _chamar_anthropic(messages, system=None, max_tokens=1024):
    # Monta os argumentos da chamada num dicionario.
    kwargs = {
        "model": config.ANTHROPIC_MODEL,  # qual modelo usar
        "max_tokens": max_tokens,         # teto de saida (obrigatorio)
        "messages": messages,             # o historico da conversa
    }
    # Na Anthropic o system e um parametro a parte; so vai se existir.
    if system:
        kwargs["system"] = system
    # Faz a chamada de verdade e recebe a resposta.
    resposta = _anthropic.messages.create(**kwargs)
    # A resposta vem como lista de blocos; pegamos o texto do 1o.
    return resposta.content[0].text


def _chamar_openai(messages, system=None, max_tokens=1024):
    # Copiamos a lista para nao alterar a original de quem chamou.
    mensagens_openai = list(messages)
    # Na OpenAI o system NAO e separado: vira a 1a mensagem da lista.
    if system:
        mensagens_openai = [{"role": "system", "content": system}] + mensagens_openai
    # Mesma ideia da Anthropic, com nomes de campo diferentes.
    resposta = _openai.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=mensagens_openai,
        max_completion_tokens=max_tokens,  # nome novo nos modelos atuais
    )
    # Aqui a resposta mora noutro caminho, nao em .content[0].text.
    return resposta.choices[0].message.content


def chat(provider, messages, system=None, max_tokens=1024):
    # Uma porta so: escolhe a funcao certa pelo nome do provider.
    if provider == "anthropic":
        return _chamar_anthropic(messages, system, max_tokens)
    if provider == "openai":
        return _chamar_openai(messages, system, max_tokens)
    # Nome desconhecido falha na hora, com mensagem clara.
    raise ValueError(f"Provider desconhecido: {provider}")


# ===========================================================================
# Aula 0.3 - Tool use normalizado para o loop.
#
# A chat() da aula 0.1 continua intocada. Daqui para baixo entra o que o
# LOOP precisa: uma chamada que oferece ferramentas e devolve SEMPRE o
# mesmo objeto neutro, seja qual for o provider, e a funcao que monta as
# mensagens de devolucao no dialeto certo. A diferenca entre os providers
# morre neste arquivo; o laco em agente.py nunca ve dialeto.
# ===========================================================================

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class PedidoFerramenta:
    """Um pedido de ferramenta feito pelo modelo, ja normalizado."""
    id: str            # id do pedido; usado para parear o resultado depois
    nome: str          # nome da ferramenta pedida
    argumentos: dict   # SEMPRE dict, mesmo na OpenAI (que manda string JSON)


@dataclass
class RespostaLLM:
    """Uma volta do modelo, normalizada."""
    texto: str                      # texto que o modelo escreveu (pode ser "")
    pedidos: list                   # list[PedidoFerramenta]; vazia = acabou
    mensagem_assistant: Any = None  # o turno CRU do assistant, para o historico


def chat_ferramentas(provider, messages, ferramentas, system=None,
                     max_tokens=1024):
    """Igual a chat() da aula 0.1, porem oferecendo ferramentas ao modelo.

    Devolve sempre um RespostaLLM, seja qual for o provider.
    'ferramentas' e o dict {"anthropic": [...], "openai": [...]} com os
    schemas em cada dialeto (a aula 0.4 vai gerar isso automaticamente).
    """
    if provider == "anthropic":
        kwargs = {
            "model": config.ANTHROPIC_MODEL,
            "max_tokens": max_tokens,            # obrigatorio na Anthropic
            "tools": ferramentas["anthropic"],
            "messages": messages,
        }
        if system:
            kwargs["system"] = system            # parametro, nunca mensagem

        resp = _anthropic.messages.create(**kwargs)

        # A resposta vem como LISTA DE BLOCOS: separamos texto de pedidos.
        texto = ""
        pedidos = []
        for bloco in resp.content:
            if bloco.type == "text":
                texto += bloco.text
            elif bloco.type == "tool_use":
                # Na Anthropic o input JA e dicionario. Sem json.loads.
                pedidos.append(PedidoFerramenta(
                    id=bloco.id, nome=bloco.name, argumentos=bloco.input))

        return RespostaLLM(
            texto=texto,
            pedidos=pedidos,
            # O turno do assistant volta CRU para o historico: a API exige
            # rever o proprio pedido antes de receber o resultado.
            mensagem_assistant={"role": "assistant", "content": resp.content},
        )

    if provider == "openai":
        msgs = list(messages)                    # nunca mutar a lista original
        if system:
            msgs = [{"role": "system", "content": system}] + msgs

        resp = _openai.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=msgs,
            tools=ferramentas["openai"],
            max_completion_tokens=max_tokens,
        )
        msg = resp.choices[0].message

        pedidos = []
        for tc in (msg.tool_calls or []):
            pedidos.append(PedidoFerramenta(
                id=tc.id,
                nome=tc.function.name,
                # Na OpenAI os argumentos chegam como STRING JSON.
                argumentos=json.loads(tc.function.arguments),
            ))

        return RespostaLLM(
            texto=msg.content or "",
            pedidos=pedidos,
            mensagem_assistant=msg,              # a mensagem crua do SDK
        )

    raise ValueError(f"Provider desconhecido: {provider}")


def mensagens_de_resultado(provider, resposta, resultados):
    """Monta as mensagens de devolucao no dialeto do provider.

    resposta   -> o RespostaLLM da volta (traz o turno cru do assistant)
    resultados -> list[(PedidoFerramenta, str)], o texto ja serializado

    Devolve a lista de mensagens a ANEXAR ao historico. E a etapa 4 do
    ciclo da aula 0.2, agora escrita uma unica vez.
    """
    if provider == "anthropic":
        # Anthropic: reinsere o turno do assistant e devolve TODOS os
        # resultados num unico turno de user, um bloco por pedido.
        blocos = [
            {"type": "tool_result", "tool_use_id": pedido.id,
             "content": saida}
            for pedido, saida in resultados
        ]
        return [resposta.mensagem_assistant,
                {"role": "user", "content": blocos}]

    if provider == "openai":
        # OpenAI: reinsere o turno do assistant e devolve UMA mensagem
        # de role "tool" por pedido, pareada pelo tool_call_id.
        msgs = [resposta.mensagem_assistant]
        for pedido, saida in resultados:
            msgs.append({
                "role": "tool",
                "tool_call_id": pedido.id,
                "content": saida,
            })
        return msgs

    raise ValueError(f"Provider desconhecido: {provider}")
