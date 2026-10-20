"""Aula 1.3 - Paralelizacao e orquestrador como grafo.

No Python puro, paralelizar foi trabalho seu: ThreadPoolExecutor,
submit, result. No grafo e DECLARATIVO: voce diz que tres arestas saem
do mesmo no, e o LangGraph roda os tres juntos. Isso se chama fan-out,
e o reencontro depois se chama fan-in.

E para o orquestrador entra a peca que nao existia ate aqui: a Send
API. Toda aresta que voce desenhou ate agora ligava no a no, decidida
na MONTAGEM. Send cria destinos em TEMPO DE EXECUCAO, um por item de
uma lista que so existe depois que o modelo respondeu.

E por isso que o orquestrador precisa de grafo e os padroes da Aula
1.2 nao precisavam: nao da para desenhar de antemao um grafo com N
nos quando N e decidido na hora.

Verificado contra langgraph 1.2.15.
"""

import operator
from typing import Annotated, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from nucleo.observabilidade import iniciar_trace, observar
from nucleo.paralelo import (ANALISES, Plano, Subtarefa, _analisar,
                             _rodar_worker, decompor, sintetizar)


# ===========================================================================
# PARALELIZACAO COMO GRAFO (fan-out estatico)
# ===========================================================================
class EstadoAnalise(TypedDict):
    mensagem: str
    provider: str
    analises: Annotated[dict, operator.or_]
    # operator.or_ e o merge de dicionarios do Python (o mesmo do
    # operador |). Cada no devolve a SUA chave, e o reducer junta as
    # tres. Sem ele, o ultimo no a terminar sobrescreveria os outros, e
    # esse bug e dificil de ver porque o resultado parece plausivel:
    # so falta coisa.


def construir_analise(analises=None, checkpointer=None):
    """Fan-out estatico: as analises sao conhecidas na montagem."""
    analises = analises or ANALISES

    def _fazer_no(nome, pergunta):
        def no(estado: EstadoAnalise) -> dict:
            saida = _analisar(nome, pergunta, estado["mensagem"],
                              estado["provider"])
            return {"analises": {nome: saida}}   # so a propria chave
        return no

    g = StateGraph(EstadoAnalise)
    for nome, pergunta in analises.items():
        g.add_node(nome, _fazer_no(nome, pergunta))
        # Varias arestas saindo de START: e isto, e so isto, que
        # declara o paralelismo. O LangGraph roda no mesmo super-step
        # tudo que esta pronto para rodar.
        g.add_edge(START, nome)
        g.add_edge(nome, END)

    return g.compile(checkpointer=checkpointer)


def rodar_analise(mensagem, provider="anthropic", grafo=None,
                  analises=None):
    """Roda as analises em paralelo pelo grafo."""
    if grafo is None:
        grafo = construir_analise(analises)

    with iniciar_trace("paralelizacao_grafo", entrada=mensagem):
        final = grafo.invoke({"mensagem": mensagem, "provider": provider,
                              "analises": {}})
    return final["analises"]


# ===========================================================================
# ORCHESTRATOR-WORKERS COMO GRAFO (fan-out DINAMICO, com Send)
# ===========================================================================
class EstadoOrquestra(TypedDict):
    mensagem: str
    provider: str
    subtarefas: Optional[list]
    resultados: Annotated[list, operator.add]
    resposta: str


class EstadoWorker(TypedDict):
    """O estado que UM worker recebe.

    Repare que e diferente do estado do grafo. Isso e proposital e e
    um recurso do Send: cada worker recebe so o seu pedaco, em vez do
    estado inteiro. Contexto menor por worker, pela mesma regra da
    Aula 1.2.
    """
    subtarefa: dict
    provider: str


def construir_orquestrador(workers, checkpointer=None):
    """Monta o orquestrador. O numero de workers e decidido em runtime."""

    def planejar(estado: EstadoOrquestra) -> dict:
        plano = decompor(estado["mensagem"], estado["provider"])
        # Guardamos dicts, nao objetos: a regra do estado serializavel
        # da Aula 1.1 continua valendo.
        return {"subtarefas": [s.model_dump() for s in plano.subtarefas]}

    def distribuir(estado: EstadoOrquestra):
        """A funcao de fan-out dinamico.

        Ela nao devolve o NOME de um no, como as condicionais que voce
        ja escreveu. Devolve uma LISTA de Send, e cada Send e uma
        instancia do no worker com a sua propria entrada.

        Tres subtarefas viram tres execucoes paralelas de um unico no
        declarado. E assim que um grafo estatico atende a uma
        decomposicao dinamica.
        """
        if not estado["subtarefas"]:
            return "sintetizar"           # nada a delegar
        return [Send("worker", {"subtarefa": s,
                                "provider": estado["provider"]})
                for s in estado["subtarefas"]]

    def worker(estado: EstadoWorker) -> dict:
        subtarefa = Subtarefa(**estado["subtarefa"])
        saida = _rodar_worker(subtarefa, workers)
        # O reducer acumula os resultados dos N workers numa lista so.
        return {"resultados": [(subtarefa.tipo, saida)]}

    def sintetizar_no(estado: EstadoOrquestra) -> dict:
        if not estado["resultados"]:
            return {"resposta": ("Nao identifiquei um pedido claro na "
                                 "mensagem. Pode detalhar?")}
        with observar("sintetizar_no"):
            texto = sintetizar(estado["mensagem"], estado["resultados"],
                               estado["provider"])
        return {"resposta": texto}

    g = StateGraph(EstadoOrquestra)
    g.add_node("planejar", planejar)
    g.add_node("worker", worker)
    g.add_node("sintetizar", sintetizar_no)

    g.add_edge(START, "planejar")
    g.add_conditional_edges("planejar", distribuir,
                            ["worker", "sintetizar"])
    # O FAN-IN: todo worker desagua no sintetizador, e o LangGraph so
    # roda o sintetizador quando TODOS terminarem. Essa espera e de
    # graca; no Python puro ela foi o .result() de cada futuro.
    g.add_edge("worker", "sintetizar")
    g.add_edge("sintetizar", END)

    return g.compile(checkpointer=checkpointer)


def rodar_orquestrador(mensagem, workers, provider="anthropic",
                       grafo=None):
    """Roda o orquestrador pelo grafo. Devolve (resposta, resultados)."""
    if grafo is None:
        grafo = construir_orquestrador(workers)

    with iniciar_trace("orquestrador_grafo", entrada=mensagem) as raiz:
        final = grafo.invoke({
            "mensagem": mensagem, "provider": provider,
            "subtarefas": None, "resultados": [], "resposta": "",
        })
        if raiz is not None:
            raiz.saida = final["resposta"]

    return final["resposta"], final["resultados"]
