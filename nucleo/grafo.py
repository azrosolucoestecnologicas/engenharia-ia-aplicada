"""Aula 1.1 - Do laco ao grafo de estado (LangGraph).

A mesma maquina da Aula 0.3, agora com o estado EXPLICITO.

O que muda: o `while` artesanal vira um grafo de nos e arestas, e o
historico sai de uma variavel local para dentro de um estado declarado.

O que NAO muda, e e o ponto da aula: providers, registro, ferramentas,
resiliencia e observabilidade continuam intocados. Este arquivo so
orquestra o que a Fase 0 ja construiu. Se voce precisasse reescrever o
motor para usar framework, o motor estava acoplado ao laco.

Por que trocar um laco que funciona: na Fase 0 o historico vivia numa
variavel local de `rodar_agente`. Ninguem de fora conseguia ler, pausar
ou retomar aquilo. Estado explicito e a porta para persistencia (1.6) e
human-in-the-loop (1.7), que sao o motivo real desta fase.

Verificado contra langgraph 1.2.15. A API deste pacote muda entre
versoes maiores: confira a sua com `pip show langgraph` e, na duvida,
`inspect.signature(StateGraph.compile)`.
"""

import json
import operator
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from nucleo.agente import Execucao
from nucleo.observabilidade import iniciar_trace, observar, registrar_uso
from nucleo.providers import (PedidoFerramenta, RespostaLLM,
                              chat_ferramentas, mensagens_de_resultado)


# ---------------------------------------------------------------------------
# O ESTADO
#
# Na Aula 0.3 isto era uma variavel local chamada `historico`. Declarar
# o estado e a mudanca conceitual da aula inteira: o que antes vivia na
# pilha de uma funcao agora e um objeto que o grafo carrega entre os
# nos, e que um checkpointer consegue salvar.
#
# REGRA: tudo que entra aqui precisa ser serializavel, porque vai ser
# persistido na Aula 1.6. Por isso ferramentas e executores (que sao
# funcoes Python) NAO moram no estado: eles sao capturados por closure
# na construcao do grafo.
# ---------------------------------------------------------------------------
class EstadoAgente(TypedDict):
    """O estado que percorre o grafo."""

    historico: Annotated[list, operator.add]
    # O Annotated com um REDUCER e o coracao do LangGraph. Sem ele, um
    # no que devolve `historico` SUBSTITUIRIA o valor anterior. Com
    # operator.add, cada no devolve apenas o DELTA e o framework
    # concatena. E o `historico.extend(...)` da Aula 0.3, agora
    # declarado em vez de escrito a mao.

    iteracoes: Annotated[int, operator.add]
    # Mesmo mecanismo com numero: cada volta devolve 1, o reducer soma.

    provider: str          # "anthropic" ou "openai"
    system: Optional[str]  # instrucao de sistema, opcional
    resposta: str          # texto final, preenchido na ultima volta

    pedidos: list
    # Os pedidos da volta corrente, como DICTS puros, nao como objetos
    # PedidoFerramenta. Nao e preciosismo: um checkpointer precisa
    # serializar isto, e dataclass custom vira aviso hoje e erro
    # amanha. O no `agir` reconstroi os objetos quando precisa deles.

    turno_assistant: Any
    # O turno cru do assistant, exigido pela API na devolucao (Aula
    # 0.2). DIVIDA ASSUMIDA: este campo guarda objetos do SDK do
    # provider, que NAO sao serializaveis. Com o checkpointer em
    # memoria funciona; num checkpointer de banco, na Aula 1.6, vai
    # ser preciso serializar isto. Deixamos o problema visivel e
    # nomeado em vez de escondido.


# Por que nao usamos o `add_messages` que o LangGraph oferece: aquele
# reducer e feito para objetos de mensagem do LangChain e faria o nosso
# motor depender daquele formato. O nosso historico e uma lista de
# dicts no dialeto de cada provider, e e assim que a Fase 0 o mantem
# agnostico. operator.add acumula exatamente igual, sem acoplamento.


def construir_grafo(ferramentas, executores, checkpointer=None):
    """Monta o grafo com as ferramentas e executores do Nucleo.

    ferramentas  -> dict {"anthropic": [...], "openai": [...]} (Aula 0.4)
    executores   -> dict {nome: funcao} (Aula 0.6, ja protegidos)
    checkpointer -> opcional; sem ele o estado morre no fim da execucao.
                    E o gancho da Aula 1.6.

    Devolve o grafo COMPILADO, pronto para invoke().
    """

    # -----------------------------------------------------------------
    # NO 1 - DECIDIR. E a etapa DECISAO da Aula 0.3, sem uma linha nova.
    # -----------------------------------------------------------------
    def decidir(estado: EstadoAgente) -> dict:
        volta = estado["iteracoes"] + 1

        # Chamada ao modelo e generation: e nela que mora o custo.
        with observar(f"decisao {volta}", tipo="generation") as gen:
            resposta = chat_ferramentas(
                estado["provider"],
                estado["historico"],
                ferramentas,
                system=estado.get("system"),
            )
            registrar_uso(gen, resposta.tokens_entrada,
                          resposta.tokens_saida, resposta.modelo)

        # O no devolve apenas o que MUDOU. Quem acumula e o reducer.
        return {
            "iteracoes": 1,
            # Guardamos dicts, nao objetos: ver a nota no EstadoAgente.
            "pedidos": [{"id": p.id, "nome": p.nome,
                         "argumentos": p.argumentos}
                        for p in resposta.pedidos],
            "turno_assistant": resposta.mensagem_assistant,
            "resposta": resposta.texto if not resposta.pedidos else "",
        }

    # -----------------------------------------------------------------
    # NO 2 - AGIR. E a etapa ACAO mais a OBSERVACAO da Aula 0.3.
    # -----------------------------------------------------------------
    def agir(estado: EstadoAgente) -> dict:
        # Reconstruimos os objetos a partir dos dicts do estado. O
        # motor da Fase 0 continua recebendo exatamente o que sempre
        # recebeu, e o estado continua serializavel.
        pedidos = [PedidoFerramenta(**p) for p in estado["pedidos"]]
        resultados = []

        for pedido in pedidos:
            # Execucao de ferramenta e span: tem duracao, nao tem token.
            with observar(pedido.nome, entrada=pedido.argumentos) as sp:
                funcao = executores.get(pedido.nome)
                if funcao is None:
                    # Ferramenta desconhecida nao derruba o grafo: vira
                    # observacao que o modelo le e contorna (Aula 0.6).
                    saida = {"erro": f"ferramenta desconhecida: "
                                     f"{pedido.nome}"}
                else:
                    saida = funcao(**pedido.argumentos)
                if sp is not None:
                    sp.saida = saida

            resultados.append(
                (pedido, json.dumps(saida, ensure_ascii=False)))

        # mensagens_de_resultado e da Aula 0.3, reaproveitada inteira:
        # ela sabe o dialeto de devolucao de cada provider. Ela so
        # precisa do turno cru, entao montamos um RespostaLLM efemero
        # em vez de carregar o objeto inteiro no estado.
        novas = mensagens_de_resultado(
            estado["provider"],
            RespostaLLM("", pedidos, estado["turno_assistant"]),
            resultados)

        return {"historico": novas}   # o reducer concatena ao que havia

    # -----------------------------------------------------------------
    # A ARESTA CONDICIONAL. E o `if not resposta.pedidos` da Aula 0.3,
    # agora como funcao de roteamento: ela nao executa nada, so decide
    # para onde ir.
    # -----------------------------------------------------------------
    def tem_ferramenta_a_executar(estado: EstadoAgente) -> str:
        return "agir" if estado["pedidos"] else END

    # -----------------------------------------------------------------
    # A MONTAGEM. Leia as quatro linhas abaixo e compare com o laco da
    # Aula 0.3: e o mesmo ciclo, declarado em vez de escrito.
    # -----------------------------------------------------------------
    construtor = StateGraph(EstadoAgente)
    construtor.add_node("decidir", decidir)
    construtor.add_node("agir", agir)

    construtor.add_edge(START, "decidir")
    construtor.add_conditional_edges(
        "decidir", tem_ferramenta_a_executar, {"agir": "agir", END: END})
    construtor.add_edge("agir", "decidir")   # e o ciclo que fecha o laco

    return construtor.compile(checkpointer=checkpointer)


def rodar_grafo(pergunta, ferramentas, executores, provider="anthropic",
                system=None, max_iteracoes=6, grafo=None, config=None):
    """Roda o grafo e devolve a MESMA Execucao da Aula 0.3.

    Manter a assinatura e o retorno permite rodar o laco artesanal e o
    grafo lado a lado e comparar. Se o contrato mudasse, a comparacao
    seria entre coisas diferentes.
    """
    if grafo is None:
        grafo = construir_grafo(ferramentas, executores)

    estado_inicial = {
        "historico": [{"role": "user", "content": pergunta}],
        "iteracoes": 0,
        "provider": provider,
        "system": system,
        "resposta": "",
        "pedidos": [],
        "turno_assistant": None,
    }

    # O teto de iteracoes da Aula 0.3 vira recursion_limit aqui. Mesmo
    # conceito, outro nome. Cada volta do ciclo consome dois passos
    # (decidir + agir), mais o passo final: por isso o x2 + 1.
    cfg = dict(config or {})
    cfg.setdefault("recursion_limit", max_iteracoes * 2 + 1)

    with iniciar_trace("rodar_grafo", entrada=pergunta) as raiz:
        try:
            final = grafo.invoke(estado_inicial, config=cfg)
            parou_por = "resposta_final"
            resposta = final["resposta"]
            historico = final["historico"]
            iteracoes = final["iteracoes"]
        except Exception as e:
            # O LangGraph levanta GraphRecursionError ao estourar o
            # limite. Importamos pelo nome para nao depender do caminho
            # exato do modulo, que ja mudou entre versoes.
            if type(e).__name__ != "GraphRecursionError":
                raise
            # Estourar o teto NAO e sucesso, igual na Aula 0.3.
            parou_por = "limite_de_iteracoes"
            resposta = ""
            historico = []
            iteracoes = max_iteracoes

        if raiz is not None:
            raiz.saida = resposta

    return Execucao(resposta=resposta, iteracoes=iteracoes,
                    parou_por=parou_por, historico=historico, trace=raiz)
