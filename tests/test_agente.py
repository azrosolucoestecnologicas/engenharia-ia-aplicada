# Aula 0.3 - Testes do loop de agente.
#
# Nenhum teste aqui chama API. O que esta sob teste e a MECANICA do
# laco e da normalizacao: encadear, parar, pedir em paralelo, contornar
# ferramenta desconhecida, e traduzir cada dialeto para o formato
# neutro. Se o modelo escolheria bem as ferramentas e pergunta de
# avaliacao, com instrumento proprio, na Fase 3.

import json
from types import SimpleNamespace

from nucleo import agente, providers
from nucleo.providers import PedidoFerramenta, RespostaLLM


# ---------- ferramentas e executores falsos ----------

FERRAMENTAS = {"anthropic": [], "openai": []}  # o dublê ignora os schemas


def _executores(chamadas):
    """Executores que registram cada chamada, para podermos afirmar
    que o laco realmente executou o que o modelo pediu."""
    def buscar_info_lead(email):
        chamadas.append(("buscar_info_lead", email))
        return {"empresa": "DataLog", "plano": "pro", "mrr": 490}

    def calcular_score_lead(plano, mrr):
        chamadas.append(("calcular_score_lead", plano, mrr))
        return {"score": 70}

    return {"buscar_info_lead": buscar_info_lead,
            "calcular_score_lead": calcular_score_lead}


def _roteiro(monkeypatch, respostas):
    """Troca chat_ferramentas por um roteiro pre-escrito de RespostaLLM.
    O laco roda de verdade; so as decisoes do modelo sao nossas."""
    fila = list(respostas)
    contador = {"n": 0}

    def fake(provider, messages, ferramentas, system=None, max_tokens=1024):
        contador["n"] += 1
        return fila.pop(0)

    monkeypatch.setattr(agente, "chat_ferramentas", fake)
    # mensagens_de_resultado tambem vira dublê simples: o formato real de
    # cada dialeto e testado separadamente, mais abaixo.
    monkeypatch.setattr(agente, "mensagens_de_resultado",
                        lambda provider, resp, res: [{"volta": len(res)}])
    return contador


# ---------- 1. o laco encadeia duas ferramentas e para sozinho ----------

def test_encadeia_duas_ferramentas_e_para(monkeypatch):
    chamadas = []
    contador = _roteiro(monkeypatch, [
        RespostaLLM("", [PedidoFerramenta("1", "buscar_info_lead",
                                          {"email": "carlos@datalog.io"})]),
        RespostaLLM("", [PedidoFerramenta("2", "calcular_score_lead",
                                          {"plano": "pro", "mrr": 490})]),
        RespostaLLM("Lead qualificado, score 70.", []),
    ])

    exe = agente.rodar_agente("O lead e bom?", FERRAMENTAS,
                              _executores(chamadas), verbose=False)

    assert exe.parou_por == "resposta_final"
    assert exe.iteracoes == 3
    assert contador["n"] == 3
    assert "score 70" in exe.resposta
    # A ordem de execucao seguiu a decisao do modelo.
    assert [c[0] for c in chamadas] == ["buscar_info_lead",
                                        "calcular_score_lead"]


# ---------- 2. o teto de iteracoes e respeitado e sinalizado ----------

def test_limite_de_iteracoes_nao_e_sucesso(monkeypatch):
    chamadas = []
    # Um modelo "confuso" que pede ferramenta para sempre.
    sempre = RespostaLLM("", [PedidoFerramenta("x", "buscar_info_lead",
                                               {"email": "a@b.c"})])
    _roteiro(monkeypatch, [sempre] * 10)

    exe = agente.rodar_agente("?", FERRAMENTAS, _executores(chamadas),
                              max_iteracoes=3, verbose=False)

    assert exe.parou_por == "limite_de_iteracoes"
    assert exe.iteracoes == 3
    assert exe.resposta == ""        # nao mascara falha como resposta
    assert len(chamadas) == 3


# ---------- 3. pedidos paralelos numa mesma volta ----------

def test_executa_todos_os_pedidos_da_volta(monkeypatch):
    chamadas = []
    _roteiro(monkeypatch, [
        RespostaLLM("", [
            PedidoFerramenta("1", "buscar_info_lead", {"email": "a@x.io"}),
            PedidoFerramenta("2", "buscar_info_lead", {"email": "b@y.io"}),
        ]),
        RespostaLLM("Pronto.", []),
    ])

    exe = agente.rodar_agente("Compare os dois leads", FERRAMENTAS,
                              _executores(chamadas), verbose=False)

    # Assumir um pedido por volta descartaria o segundo em silencio.
    assert len(chamadas) == 2
    assert exe.iteracoes == 2


# ---------- 4. ferramenta desconhecida vira observacao ----------

def test_ferramenta_desconhecida_nao_derruba(monkeypatch):
    registro = {}

    def fake_msgs(provider, resp, resultados):
        registro["saida"] = resultados[0][1]
        return [{"role": "user", "content": "..."}]

    _roteiro(monkeypatch, [
        RespostaLLM("", [PedidoFerramenta("1", "ferramenta_fantasma", {})]),
        RespostaLLM("Nao consegui, mas segui.", []),
    ])
    monkeypatch.setattr(agente, "mensagens_de_resultado", fake_msgs)

    exe = agente.rodar_agente("?", FERRAMENTAS, {}, verbose=False)

    assert exe.parou_por == "resposta_final"
    assert "ferramenta desconhecida" in registro["saida"]


# ---------- 5. normalizacao Anthropic: blocos -> formato neutro ----------

def test_chat_ferramentas_normaliza_anthropic(monkeypatch):
    resposta_crua = SimpleNamespace(content=[
        SimpleNamespace(type="text", text="Vou consultar."),
        SimpleNamespace(type="tool_use", id="tu_1", name="buscar_info_lead",
                        input={"email": "carlos@datalog.io"}),
    ])
    monkeypatch.setattr(providers._anthropic, "messages",
                        SimpleNamespace(create=lambda **kw: resposta_crua))

    r = providers.chat_ferramentas("anthropic", [], FERRAMENTAS)

    assert r.texto == "Vou consultar."
    assert r.pedidos == [PedidoFerramenta("tu_1", "buscar_info_lead",
                                          {"email": "carlos@datalog.io"})]
    assert r.mensagem_assistant["role"] == "assistant"


# ---------- 6. normalizacao OpenAI: string JSON -> dict ----------

def test_chat_ferramentas_normaliza_openai(monkeypatch):
    msg = SimpleNamespace(content=None, tool_calls=[SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="buscar_info_lead",
                                 arguments='{"email": "carlos@datalog.io"}'),
    )])
    resposta_crua = SimpleNamespace(choices=[SimpleNamespace(message=msg)])
    monkeypatch.setattr(providers._openai, "chat", SimpleNamespace(
        completions=SimpleNamespace(create=lambda **kw: resposta_crua)))

    r = providers.chat_ferramentas("openai", [], FERRAMENTAS)

    assert r.texto == ""                          # content None vira ""
    assert r.pedidos[0].argumentos == {"email": "carlos@datalog.io"}
    assert isinstance(r.pedidos[0].argumentos, dict)


# ---------- 7. devolucao no dialeto certo ----------

def test_mensagens_de_resultado_nos_dois_dialetos():
    p1 = PedidoFerramenta("id1", "f", {})
    p2 = PedidoFerramenta("id2", "f", {})
    resultados = [(p1, '{"a": 1}'), (p2, '{"b": 2}')]

    # Anthropic: turno do assistant + UM turno de user com dois blocos.
    ra = RespostaLLM("", [p1, p2], {"role": "assistant", "content": []})
    ma = providers.mensagens_de_resultado("anthropic", ra, resultados)
    assert len(ma) == 2
    assert ma[1]["role"] == "user"
    assert [b["tool_use_id"] for b in ma[1]["content"]] == ["id1", "id2"]

    # OpenAI: turno do assistant + UMA mensagem role "tool" por pedido.
    ro = RespostaLLM("", [p1, p2], "msg-crua")
    mo = providers.mensagens_de_resultado("openai", ro, resultados)
    assert len(mo) == 3
    assert [m["tool_call_id"] for m in mo[1:]] == ["id1", "id2"]
    assert all(m["role"] == "tool" for m in mo[1:])
