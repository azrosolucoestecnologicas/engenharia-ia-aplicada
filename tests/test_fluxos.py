# Aula 1.2 - Testes de chaining e routing.
#
# Nenhuma chamada de API. Os fluxos rodam de verdade; so as respostas
# do modelo sao nossas.
#
# Dois testes aqui valem mais que os outros: o que prova que a versao
# pura e a versao em grafo produzem o MESMO resultado, e o que mede a
# diferenca de custo entre workflow e agente. O segundo e a tese da
# aula virando numero.

import json

import pytest

from nucleo import (agente, banco, estruturado, fluxos, grafo_fluxos,
                    providers)
from nucleo.fluxos import Triagem
from nucleo.observabilidade import resumo
from nucleo.providers import PedidoFerramenta, RespostaLLM

TRIAGEM_SUPORTE = {"intencao": "suporte", "email": "ana@techflow.com",
                   "urgencia": "alta", "resumo": "erro 500 no login"}

HANDLERS = {
    "comercial": lambda t: f"[vendas] proposta para {t.email}",
    "suporte": lambda t: f"[suporte] ticket {t.urgencia}",
    "duvida": lambda t: f"[faq] {t.resumo}",
}


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "CAMINHO_BANCO", tmp_path / "fluxos.db")
    banco.criar_schema(semear=True)
    yield


def _modelo(monkeypatch, triagem=None, redacao="Ola, recebemos seu pedido."):
    """Fixa as respostas do modelo nos dois pontos onde ele e chamado."""
    dados = json.dumps(triagem or TRIAGEM_SUPORTE)
    monkeypatch.setattr(estruturado, "chat", lambda *a, **k: dados)
    monkeypatch.setattr(fluxos, "chat", lambda *a, **k: redacao)


def _crm(email):
    from nucleo.ferramentas import buscar_atualizar_crm
    return buscar_atualizar_crm(email=email)


# ---------- 1. o chaining percorre os tres passos, na ordem ----------

def test_chaining_executa_os_tres_passos(monkeypatch):
    _modelo(monkeypatch)

    resposta, triagem = fluxos.triar_mensagem("A Ana reportou erro", _crm)

    assert resposta == "Ola, recebemos seu pedido."
    assert triagem.intencao == "suporte"
    assert triagem.urgencia == "alta"


# ---------- 2. o gate PARA antes de gastar os passos seguintes ----------

def test_gate_barra_sem_email(monkeypatch):
    chamou_crm = []
    _modelo(monkeypatch, {"intencao": "duvida", "email": "",
                          "urgencia": "baixa", "resumo": "quanto custa"})

    def crm_espiao(email):
        chamou_crm.append(email)
        return "nao deveria ser chamado"

    resposta, _ = fluxos.triar_mensagem("quanto custa?", crm_espiao)

    assert "email" in resposta.lower()
    # O ponto do gate: os passos seguintes NAO rodaram. Parar cedo e
    # barato; seguir com dado faltando e caro.
    assert chamou_crm == []


# ---------- 3. O TESTE DA AULA: puro e grafo dao o mesmo resultado ----------

def test_chaining_puro_equivale_ao_grafo(monkeypatch):
    _modelo(monkeypatch)
    r_puro, t_puro = fluxos.triar_mensagem("A Ana reportou erro", _crm)

    _modelo(monkeypatch)
    r_grafo, t_grafo, passos = grafo_fluxos.rodar_chaining(
        "A Ana reportou erro", _crm)

    assert r_puro == r_grafo
    assert t_puro.model_dump() == t_grafo.model_dump()
    assert passos == ["extrair", "consultar", "redigir"]


# ---------- 4. o desvio do gate tambem equivale ----------

def test_gate_no_grafo_desvia_o_caminho(monkeypatch):
    _modelo(monkeypatch, {"intencao": "duvida", "email": "",
                          "urgencia": "baixa", "resumo": "quanto custa"})

    resposta, _, passos = grafo_fluxos.rodar_chaining("quanto custa?", _crm)

    assert "email" in resposta.lower()
    # No grafo da para VER o caminho percorrido. No if do Python puro,
    # so o resultado.
    assert passos == ["extrair", "pedir_email"]


# ---------- 5. o router manda para o handler certo, nas duas versoes ----------

@pytest.mark.parametrize("intencao,marca", [
    ("comercial", "[vendas]"),
    ("suporte", "[suporte]"),
    ("duvida", "[faq]"),
])
def test_router_equivale_nas_duas_versoes(monkeypatch, intencao, marca):
    dados = dict(TRIAGEM_SUPORTE, intencao=intencao)

    _modelo(monkeypatch, dados)
    r_puro, _ = fluxos.rotear("mensagem", HANDLERS)

    _modelo(monkeypatch, dados)
    r_grafo, _ = grafo_fluxos.rodar_router("mensagem", HANDLERS)

    assert marca in r_puro
    assert r_puro == r_grafo


# ---------- 6. rota sem handler falha, e em momentos diferentes ----------

def test_rota_sem_handler_falha_em_runtime(monkeypatch):
    _modelo(monkeypatch)
    with pytest.raises(ValueError):
        fluxos.rotear("mensagem", {"comercial": lambda t: "x"})
    # Na versao pura, a falta so aparece quando a mensagem daquele tipo
    # chega. Em producao, isso e um sabado.


def test_rota_sem_no_falha_na_montagem():
    """O grafo pega o mesmo erro ANTES de rodar.

    Um ganho concreto do grafo sobre o dict de handlers: o LangGraph
    valida que todo destino da aresta condicional existe como no, na
    compilacao. Erro de configuracao vira erro de inicializacao.
    """
    from langgraph.graph import END, START, StateGraph
    from typing import TypedDict

    class Estado(TypedDict):
        rota: str

    g = StateGraph(Estado)
    g.add_node("classificar", lambda e: {})
    g.add_node("comercial", lambda e: {})
    g.add_edge(START, "classificar")
    g.add_edge("comercial", END)
    g.add_conditional_edges("classificar", lambda e: e["rota"],
                            {"comercial": "comercial",
                             "suporte": "suporte"})   # no inexistente

    with pytest.raises(ValueError):
        g.compile()


# ---------- 7. A TESE DA AULA, EM NUMERO: workflow custa menos ----------

def test_workflow_gasta_menos_chamadas_que_o_agente(monkeypatch):
    """O mesmo caso, pelos dois caminhos, contando chamadas ao modelo.

    Nao e sobre o workflow ser melhor: e sobre ele ser SUFICIENTE
    quando o caminho e conhecido. Autonomia que voce nao precisa e
    custo que voce paga.
    """
    # --- pelo workflow: extrair + redigir = 2 chamadas ---
    chamadas_fluxo = {"n": 0}

    def conta_extracao(*a, **k):
        chamadas_fluxo["n"] += 1
        return json.dumps(TRIAGEM_SUPORTE)

    def conta_redacao(*a, **k):
        chamadas_fluxo["n"] += 1
        return "Ola, abrimos o chamado."

    monkeypatch.setattr(estruturado, "chat", conta_extracao)
    monkeypatch.setattr(fluxos, "chat", conta_redacao)
    fluxos.triar_mensagem("A Ana reportou erro 500", _crm)

    # --- pelo agente da Fase 0: cada volta do laco e uma chamada ---
    from nucleo.registro import schemas
    from nucleo.resiliencia import executores_seguros
    from nucleo import ferramentas                      # noqa: F401

    turno = {"role": "assistant", "content": []}
    roteiro = [
        RespostaLLM("", [PedidoFerramenta(
            "1", "buscar_atualizar_crm",
            {"email": "ana@techflow.com"})], turno),
        RespostaLLM("", [PedidoFerramenta(
            "2", "abrir_ticket", {"email": "ana@techflow.com",
                                  "assunto": "Erro", "descricao": "500",
                                  "prioridade": "alta"})], turno),
        RespostaLLM("Ticket aberto.", [], None),
    ]
    chamadas_agente = {"n": 0}

    def conta_agente(*a, **k):
        chamadas_agente["n"] += 1
        return roteiro.pop(0)

    monkeypatch.setattr(agente, "chat_ferramentas", conta_agente)
    agente.rodar_agente("A Ana reportou erro 500", schemas(),
                        executores_seguros(), verbose=False)

    assert chamadas_fluxo["n"] == 2
    assert chamadas_agente["n"] == 3
    assert chamadas_fluxo["n"] < chamadas_agente["n"]
    # E a diferenca cresce com a tarefa: cada volta do agente reenvia o
    # historico inteiro (Aula 0.7), enquanto cada passo do workflow
    # recebe so o contexto daquele passo.


# ---------- 8. o fluxo continua rastreado ----------

def test_chaining_aparece_no_trace(monkeypatch):
    _modelo(monkeypatch)

    import nucleo.observabilidade as obs
    capturado = {}
    original = obs.iniciar_trace

    from contextlib import contextmanager

    @contextmanager
    def espiao(nome, entrada=None):
        with original(nome, entrada=entrada) as raiz:
            capturado["raiz"] = raiz
            yield raiz

    monkeypatch.setattr(fluxos, "iniciar_trace", espiao)
    fluxos.triar_mensagem("A Ana reportou erro", _crm)

    raiz = capturado["raiz"]
    nomes = [f.nome for f in raiz.filhos]
    assert nomes == ["extrair", "consultar_crm", "redigir"]
    # A observabilidade da Aula 0.7 atravessou para a Fase 1 intacta,
    # igual na Aula 1.1.
    assert resumo(raiz)["chamadas_ao_modelo"] == 1   # so o redigir
