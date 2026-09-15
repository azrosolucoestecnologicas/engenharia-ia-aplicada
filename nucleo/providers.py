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
