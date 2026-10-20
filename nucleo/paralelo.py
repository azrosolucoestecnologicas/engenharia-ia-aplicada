"""Aula 1.3 - Workflows II: parallelization e orchestrator-workers.

Os dois padroes da Aula 1.2 tinham o caminho escrito de antemao. Estes
dois tratam do que nao cabe num caminho fixo.

A diferenca entre eles e a aula inteira:

    PARALLELIZATION    -> VOCE sabe quais sao as subtarefas. Elas estao
                          escritas no codigo. So nao precisam esperar
                          umas pelas outras.

    ORCHESTRATOR       -> O MODELO decide quais e QUANTAS subtarefas
                          existem. Voce nao sabe antes de rodar.

O primeiro e um ganho de LATENCIA. O segundo e um ganho de
CAPACIDADE: ele resolve o que os padroes anteriores nao conseguiam
expressar.

Este arquivo tem a versao em Python puro. O grafo_paralelo.py tem os
mesmos dois no LangGraph.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, Field

from nucleo.estruturado import extrair_estruturado
from nucleo.observabilidade import em_thread, iniciar_trace, observar
from nucleo.providers import chat


# ===========================================================================
# PADRAO 3 - PARALLELIZATION
#
# Rodar subtarefas INDEPENDENTES ao mesmo tempo. Use quando o resultado
# de uma nao alimenta a outra.
#
# ATENCAO ao que se ganha: paralelizar economiza TEMPO, nao DINHEIRO.
# Tres chamadas continuam sendo tres chamadas e voce paga pelas tres. O
# que muda e esperar 2 segundos em vez de 6. Quem paraleliza esperando
# a conta cair vai se decepcionar.
# ===========================================================================

def _analisar(nome, pergunta, mensagem, provider):
    """Uma analise isolada sobre a mesma mensagem.

    Cada uma e uma chamada de modelo com uma pergunta estreita. Juntar
    as tres num prompt so seria mais barato, e pior: instrucoes que
    competem entre si produzem respostas piores (regra da Aula 1.2).
    """
    with observar(nome, tipo="generation", entrada=mensagem):
        return chat(provider,
                    [{"role": "user", "content": mensagem}],
                    system=pergunta)


# As tres perguntas sao FIXAS: nos as escrevemos. E essa a marca do
# padrao, e o que o separa do orquestrador logo abaixo.
ANALISES = {
    "tom": ("Classifique o tom da mensagem do cliente em uma palavra: "
            "calmo, impaciente ou irritado. Responda so a palavra."),
    "urgencia": ("A mensagem indica urgencia real de negocio? Responda "
                 "em uma frase curta, comecando com sim ou nao."),
    "oportunidade": ("Ha oportunidade comercial nesta mensagem (upgrade, "
                     "expansao, nova contratacao)? Responda em uma frase "
                     "curta, comecando com sim ou nao."),
}


def analisar_em_paralelo(mensagem, provider="anthropic", analises=None):
    """Roda as analises ao mesmo tempo e devolve {nome: resultado}.

    ThreadPoolExecutor e suficiente aqui porque chamada de API e
    I/O bound: a thread fica bloqueada esperando a rede, e o Python
    libera o interpretador nesse intervalo. Para trabalho de CPU isso
    nao valeria, e seria preciso processo em vez de thread.

    Repare no em_thread() envolvendo cada chamada. Sem ele o codigo
    roda igual e o TRACE fica vazio, porque thread nova nao herda
    contexto. E um bug silencioso: o resultado esta certo e a
    observabilidade mente.
    """
    analises = analises or ANALISES

    with iniciar_trace("paralelizacao", entrada=mensagem):
        with ThreadPoolExecutor(max_workers=len(analises)) as executor:
            futuros = {
                nome: executor.submit(
                    em_thread(_analisar, nome, pergunta, mensagem,
                              provider))
                for nome, pergunta in analises.items()
            }
            # .result() bloqueia ate aquele futuro terminar, mas os
            # tres ja estao rodando desde o submit. O tempo total e o
            # da analise mais lenta, nao a soma das tres.
            return {nome: f.result() for nome, f in futuros.items()}


# ===========================================================================
# PADRAO 4 - ORCHESTRATOR-WORKERS
#
# O orquestrador le a tarefa, DECIDE em quantas partes ela se divide,
# delega cada parte a um worker e sintetiza o resultado.
#
# Use quando o numero de subtarefas nao e conhecido antes de rodar. Uma
# mensagem pode trazer um pedido ou quatro, e nenhum caminho fixo
# expressa isso.
# ===========================================================================

class Subtarefa(BaseModel):
    """Uma parte do pedido, definida pelo proprio modelo."""

    tipo: Literal["comercial", "suporte", "agenda"] = Field(
        description="comercial: plano, preco, upgrade. suporte: erro ou "
                    "falha tecnica. agenda: marcar, remarcar ou cancelar "
                    "reuniao")
    pedido: str = Field(description="O que precisa ser resolvido, em "
                                    "uma frase")


class Plano(BaseModel):
    """O resultado da decomposicao: quantas partes e quais."""

    subtarefas: list[Subtarefa] = Field(
        description="Uma entrada por pedido distinto na mensagem. Se a "
                    "mensagem traz um pedido so, devolva uma entrada. "
                    "Nao invente pedidos que nao estao no texto")


def decompor(mensagem, provider="anthropic"):
    """A etapa de ORQUESTRACAO: so planeja, nao resolve nada.

    E aqui que o padrao se diferencia: o numero de subtarefas sai do
    modelo, nao do codigo. Duas mensagens diferentes geram planos de
    tamanhos diferentes.
    """
    with observar("decompor", tipo="generation", entrada=mensagem):
        return extrair_estruturado(mensagem, Plano, provider=provider)


def _rodar_worker(subtarefa, workers):
    """Executa um worker. Erro de um nao derruba os outros."""
    with observar(f"worker:{subtarefa.tipo}",
                  entrada=subtarefa.pedido) as sp:
        funcao = workers.get(subtarefa.tipo)
        if funcao is None:
            saida = f"[sem worker para '{subtarefa.tipo}']"
        else:
            try:
                saida = funcao(subtarefa)
            except Exception as e:
                # Mesma regra da Aula 0.6: falha de uma parte vira
                # informacao, nao morte do conjunto. Num fan-out isso
                # pesa mais ainda, porque as outras partes podem ter
                # dado certo.
                saida = f"[falhou: {type(e).__name__}: {e}]"
        if sp is not None:
            sp.saida = saida
        return saida


def sintetizar(mensagem, resultados, provider="anthropic"):
    """A etapa de SINTESE: junta as partes numa resposta so.

    Sem ela o cliente recebe tres respostas desconexas. O sintetizador
    e o que transforma N resultados num texto que parece escrito por
    uma pessoa.
    """
    partes = "\n".join(f"- {tipo}: {saida}" for tipo, saida in resultados)
    sistema = ("Voce e o assistente do FlowDesk, um SaaS B2B. Junte os "
               "resultados abaixo numa resposta unica, curta e cordial "
               "ao cliente, em portugues. Nao repita o que ja foi dito "
               "e nao invente nada que nao esteja nos resultados.")
    conteudo = f"Mensagem original: {mensagem}\n\nResultados:\n{partes}"

    with observar("sintetizar", tipo="generation", entrada=conteudo):
        return chat(provider, [{"role": "user", "content": conteudo}],
                    system=sistema)


def orquestrar(mensagem, workers, provider="anthropic", paralelo=True):
    """Decompoe, delega e sintetiza.

    workers  -> dict {"comercial": fn, "suporte": fn, "agenda": fn}
    paralelo -> roda os workers ao mesmo tempo (padrao) ou em sequencia

    Devolve (resposta, plano, resultados).
    """
    with iniciar_trace("orquestrador", entrada=mensagem) as raiz:
        plano = decompor(mensagem, provider)

        if not plano.subtarefas:
            return ("Nao identifiquei um pedido claro na mensagem. "
                    "Pode detalhar?"), plano, []

        # Os workers tambem rodam em paralelo: a decomposicao e
        # dinamica, mas as partes continuam independentes entre si.
        # Os dois padroes desta aula se combinam.
        if paralelo and len(plano.subtarefas) > 1:
            with ThreadPoolExecutor(
                    max_workers=len(plano.subtarefas)) as ex:
                futuros = [ex.submit(em_thread(_rodar_worker, s, workers))
                           for s in plano.subtarefas]
                saidas = [f.result() for f in futuros]
        else:
            saidas = [_rodar_worker(s, workers) for s in plano.subtarefas]

        resultados = [(s.tipo, saida)
                      for s, saida in zip(plano.subtarefas, saidas)]
        resposta = sintetizar(mensagem, resultados, provider)

        if raiz is not None:
            raiz.saida = resposta
        return resposta, plano, resultados
