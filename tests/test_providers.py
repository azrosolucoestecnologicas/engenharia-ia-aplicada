from types import SimpleNamespace

import pytest

from nucleo import providers


# ---------- dublês: imitam a FORMA da resposta de cada SDK ----------

def _fake_anthropic(texto):
    # A Anthropic devolve uma lista de blocos com .text.
    return SimpleNamespace(content=[SimpleNamespace(text=texto)])


def _fake_openai(texto):
    # A OpenAI devolve choices -> message -> content.
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=texto))])


# ---------- 1. provider desconhecido falha alto ----------

def test_provider_desconhecido_levanta_erro():
    with pytest.raises(ValueError):
        providers.chat("gemini", [{"role": "user", "content": "oi"}])


# ---------- 2. na Anthropic, o system vai separado ----------

def test_anthropic_manda_system_separado(monkeypatch):
    chamadas = {}  # guarda com o que o SDK foi chamado

    class FakeMessages:
        def create(self, **kwargs):
            chamadas.update(kwargs)
            return _fake_anthropic("ok")

    # Troca, so neste teste, o cliente real pelo duble.
    monkeypatch.setattr(providers._anthropic, "messages", FakeMessages())

    resultado = providers.chat(
        "anthropic", [{"role": "user", "content": "oi"}], system="seja breve")

    assert resultado == "ok"
    assert chamadas["system"] == "seja breve"   # parametro a parte
    assert len(chamadas["messages"]) == 1       # a lista fica intacta
    assert "max_tokens" in chamadas             # obrigatorio na Anthropic


# ---------- 3. na OpenAI, o system vira a 1a mensagem ----------

def test_openai_transforma_system_em_primeira_mensagem(monkeypatch):
    chamadas = {}

    class FakeCompletions:
        def create(self, **kwargs):
            chamadas.update(kwargs)
            return _fake_openai("ok")

    monkeypatch.setattr(providers._openai, "chat",
                        SimpleNamespace(completions=FakeCompletions()))

    providers.chat("openai", [{"role": "user", "content": "oi"}],
                   system="seja breve")

    # O system tem que ter virado a 1a mensagem da lista.
    enviadas = chamadas["messages"]
    assert enviadas[0] == {"role": "system", "content": "seja breve"}
    assert enviadas[1] == {"role": "user", "content": "oi"}


# ---------- 4. sem system, nada e adicionado ----------

def test_sem_system_nao_adiciona_mensagem(monkeypatch):
    chamadas = {}

    class FakeCompletions:
        def create(self, **kwargs):
            chamadas.update(kwargs)
            return _fake_openai("ok")

    monkeypatch.setattr(providers._openai, "chat",
                        SimpleNamespace(completions=FakeCompletions()))

    providers.chat("openai", [{"role": "user", "content": "oi"}])

    enviadas = chamadas["messages"]
    assert len(enviadas) == 1
    assert enviadas[0]["role"] == "user"


# ---------- 5. a lista original de quem chamou nunca e mutada ----------

def test_nao_muta_lista_original(monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            return _fake_openai("ok")

    monkeypatch.setattr(providers._openai, "chat",
                        SimpleNamespace(completions=FakeCompletions()))

    originais = [{"role": "user", "content": "oi"}]
    providers.chat("openai", originais, system="seja breve")

    # A versao ingenua (insert na lista) alteraria a lista de quem
    # chamou. Bug que so aparece em conversa longa e e horrivel de achar.
    assert len(originais) == 1
    assert originais[0]["role"] == "user"
