"""Aula 1.2 - Os mesmos dois workflows, agora como grafo.

O fluxos.py tem chaining e routing em Python puro. Este arquivo tem os
dois no LangGraph, e um teste prova que produzem o mesmo resultado.

A pergunta honesta desta aula: se a versao pura funciona, por que
desenhar um grafo? Tres respostas, e a terceira e a que importa:

  1. A topologia vira objeto: da para imprimir e discutir (como na 1.1).
  2. O estado vira explicito: da para persistir e retomar (Aula 1.6).
  3. Um fluxo de tres passos NAO precisa de grafo. Um fluxo que precisa
     pausar no meio para um humano aprovar, PRECISA. O grafo so se paga
     quando voce quer uma dessas coisas.

Quem desenha grafo para um chaining de tres passos que nunca vai
pausar esta pagando complexidade sem receber nada em troca. Saber
disso e o conteudo da aula tanto quanto o codigo.
"""

import operator
from typing import Annotated, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from nucleo.fluxos import (Triagem, _gate_tem_email, _passo_consultar,
                           _passo_extrair, _passo_redigir, classificar)
from nucleo.observabilidade import iniciar_trace, observar


# ===========================================================================
# CHAINING COMO GRAFO
# ===========================================================================
class EstadoChaining(TypedDict):
    """Estado do fluxo de triagem.

    A regra da Aula 1.1 continua valendo: tudo que entra aqui precisa
    ser serializavel. Por isso a triagem mora como DICT, e os nos que
    precisam do objeto Pydantic o reconstroem na hora.
    """

    mensagem: str
    provider: str
    triagem: Optional[dict]
    dados_crm: Optional[str]
    resposta: str
    passos: Annotated[list, operator.add]
    # Registro do caminho percorrido. Num grafo com desvio, saber POR
    # ONDE passou vale tanto quanto o resultado.


def construir_chaining(consultar_crm, checkpointer=None):
    """Monta o chaining como grafo. Mesmos tres passos do fluxos.py."""

    def extrair(estado: EstadoChaining) -> dict:
        triagem = _passo_extrair(estado["mensagem"], estado["provider"])
        return {"triagem": triagem.model_dump(), "passos": ["extrair"]}

    def consultar(estado: EstadoChaining) -> dict:
        triagem = Triagem(**estado["triagem"])
        dados = _passo_consultar(triagem, consultar_crm)
        return {"dados_crm": dados, "passos": ["consultar"]}

    def redigir(estado: EstadoChaining) -> dict:
        triagem = Triagem(**estado["triagem"])
        texto = _passo_redigir(triagem, estado["dados_crm"],
                               estado["provider"])
        return {"resposta": texto, "passos": ["redigir"]}

    def pedir_email(estado: EstadoChaining) -> dict:
        """O caminho de saida quando o gate barra."""
        return {"resposta": ("Nao identifiquei o email na mensagem. "
                             "Poderia confirmar o email de cadastro?"),
                "passos": ["pedir_email"]}

    # O GATE vira aresta condicional. No Python puro ele era um `if`
    # que dava return; aqui ele e uma funcao que escolhe o proximo no.
    # Mesma decisao, declarada em vez de escrita.
    def gate(estado: EstadoChaining) -> str:
        triagem = Triagem(**estado["triagem"])
        return "consultar" if _gate_tem_email(triagem) else "pedir_email"

    g = StateGraph(EstadoChaining)
    g.add_node("extrair", extrair)
    g.add_node("consultar", consultar)
    g.add_node("redigir", redigir)
    g.add_node("pedir_email", pedir_email)

    g.add_edge(START, "extrair")
    g.add_conditional_edges("extrair", gate,
                            {"consultar": "consultar",
                             "pedir_email": "pedir_email"})
    g.add_edge("consultar", "redigir")   # caminho FIXO: a marca do chaining
    g.add_edge("redigir", END)
    g.add_edge("pedir_email", END)

    return g.compile(checkpointer=checkpointer)


def rodar_chaining(mensagem, consultar_crm, provider="anthropic",
                   grafo=None):
    """Roda o chaining em grafo e devolve (resposta, triagem, passos)."""
    if grafo is None:
        grafo = construir_chaining(consultar_crm)

    with iniciar_trace("chaining_grafo", entrada=mensagem) as raiz:
        final = grafo.invoke({
            "mensagem": mensagem, "provider": provider,
            "triagem": None, "dados_crm": None,
            "resposta": "", "passos": [],
        })
        if raiz is not None:
            raiz.saida = final["resposta"]

    return (final["resposta"], Triagem(**final["triagem"]),
            final["passos"])


# ===========================================================================
# ROUTING COMO GRAFO
#
# Aqui o grafo mostra servico de verdade: uma aresta condicional com
# tres saidas. No Python puro isso era um dict de handlers; no grafo, e
# a topologia, e da para desenhar.
# ===========================================================================
class EstadoRouting(TypedDict):
    mensagem: str
    provider: str
    triagem: Optional[dict]
    resposta: str
    rota: str


def construir_router(handlers, checkpointer=None):
    """Monta o router como grafo.

    handlers -> dict {"comercial": fn, "suporte": fn, "duvida": fn}
    Cada chave vira um no, entao acrescentar uma rota e acrescentar uma
    entrada no dict: o grafo se monta sozinho a partir dele.
    """

    def classificar_no(estado: EstadoRouting) -> dict:
        triagem = classificar(estado["mensagem"], estado["provider"])
        return {"triagem": triagem.model_dump(),
                "rota": triagem.intencao}

    def _fazer_no(nome, funcao):
        def no(estado: EstadoRouting) -> dict:
            triagem = Triagem(**estado["triagem"])
            with observar(f"handler:{nome}") as sp:
                resposta = funcao(triagem)
                if sp is not None:
                    sp.saida = resposta
            return {"resposta": resposta}
        return no

    g = StateGraph(EstadoRouting)
    g.add_node("classificar", classificar_no)
    for nome, funcao in handlers.items():
        g.add_node(nome, _fazer_no(nome, funcao))
        g.add_edge(nome, END)

    g.add_edge(START, "classificar")
    # path_map com uma entrada por rota. O LangGraph valida que todo
    # destino existe: rota sem no vira erro na MONTAGEM, nao em
    # producao. E uma garantia que o dict de handlers nao dava.
    g.add_conditional_edges("classificar", lambda e: e["rota"],
                            {n: n for n in handlers})

    return g.compile(checkpointer=checkpointer)


def rodar_router(mensagem, handlers, provider="anthropic", grafo=None):
    """Roda o router em grafo e devolve (resposta, triagem)."""
    if grafo is None:
        grafo = construir_router(handlers)

    with iniciar_trace("routing_grafo", entrada=mensagem) as raiz:
        final = grafo.invoke({
            "mensagem": mensagem, "provider": provider,
            "triagem": None, "resposta": "", "rota": "",
        })
        if raiz is not None:
            raiz.saida = final["resposta"]

    return final["resposta"], Triagem(**final["triagem"])
