"""Aula 1.2 - Workflows I: prompt chaining e routing, em Python puro.

A diferenca que organiza a Fase 1 inteira cabe numa pergunta:
QUEM CONTROLA O CAMINHO?

    Workflow -> VOCE controla. O caminho esta escrito no codigo, e o
                modelo so preenche as etapas.
    Agente   -> O MODELO controla. Ele escolhe a proxima ferramenta, e
                voce nao sabe de antemao por onde ele vai passar.

A Fase 0 inteira construiu um agente. Esta aula constroi os dois
workflows mais simples, e o motivo nao e academico: boa parte do que se
chama de agente por ai deveria ser um destes dois. Eles sao mais
baratos, mais previsiveis e mais faceis de testar.

A regra que vale o curso inteiro: COMECE PELO PADRAO MAIS SIMPLES QUE
RESOLVE O PROBLEMA, e so suba para autonomia quando ele exigir.

Este arquivo tem a versao em Python puro. O grafo_fluxos.py tem os
mesmos dois padroes no LangGraph, e um teste prova que produzem o
mesmo resultado.
"""

from typing import Literal

from pydantic import BaseModel, Field

from nucleo.estruturado import extrair_estruturado
from nucleo.observabilidade import iniciar_trace, observar
from nucleo.providers import chat


# ---------------------------------------------------------------------------
# O CONTRATO DA TRIAGEM
#
# Mora aqui, e nao em modelos.py, de proposito: contrato especifico de
# fluxo mora com o fluxo. O modelos.py guarda o contrato de SAIDA do
# Nucleo, que e consumido por outros sistemas, e a Fase 1 nao mexe em
# arquivo da Fase 0.
# ---------------------------------------------------------------------------
class Triagem(BaseModel):
    """O que extraimos da mensagem do lead ANTES de decidir o que fazer."""

    intencao: Literal["comercial", "suporte", "duvida"] = Field(
        description="comercial: quer comprar, migrar de plano ou falar "
                    "com vendas. suporte: relatou erro, falha ou "
                    "indisponibilidade. duvida: pergunta sobre o "
                    "produto que nao e problema tecnico")

    email: str = Field(
        description="Email do lead, se aparecer na mensagem. "
                    "String vazia se nao aparecer")

    urgencia: Literal["baixa", "media", "alta"] = Field(
        description="Urgencia percebida na mensagem")

    resumo: str = Field(description="O pedido em uma frase")


# ===========================================================================
# PADRAO 1 - PROMPT CHAINING
#
# Decompor a tarefa em passos SEQUENCIAIS e FIXOS: a saida de um
# alimenta o proximo. Use quando as etapas sao conhecidas e
# verificaveis.
#
# O ganho nao e so custo. Cada passo recebe um contexto menor e uma
# instrucao mais estreita, e por isso erra menos. Decompor e tambem uma
# forma de melhorar qualidade, nao so de economizar.
# ===========================================================================

def _passo_extrair(mensagem, provider="anthropic"):
    """PASSO 1 - transformar texto livre em dado estruturado.

    Reaproveita o extrair_estruturado da Aula 0.6 inteiro, inclusive o
    ciclo de correcao quando o modelo erra o formato.
    """
    with observar("extrair", entrada=mensagem):
        return extrair_estruturado(mensagem, Triagem, provider=provider)


def _gate_tem_email(triagem):
    """O GATE entre os passos.

    Um chaining sem gate e so uma sequencia de chamadas. O gate e o que
    permite PARAR no meio quando o resultado parcial nao serve, em vez
    de levar lixo adiante e descobrir no fim.

    Este e deterministico de proposito: checar se uma string tem "@" e
    trabalho de codigo, nao de modelo.
    """
    return "@" in triagem.email


def _passo_consultar(triagem, consultar_crm):
    """PASSO 2 - enriquecer com dados do CRM.

    Repare na diferenca para a Fase 0: aqui NAO perguntamos ao modelo
    se ele quer consultar o CRM. Nos sabemos que queremos. O caminho e
    nosso; o modelo so preenche as etapas.
    """
    with observar("consultar_crm", entrada=triagem.email) as sp:
        dados = consultar_crm(email=triagem.email)
        if sp is not None:
            sp.saida = dados
        return dados


def _passo_redigir(triagem, dados_crm, provider="anthropic"):
    """PASSO 3 - redigir a resposta ao lead.

    O contexto desta chamada e minusculo perto do historico que o
    agente da Fase 0 carregava na quarta volta: so o que este passo
    precisa. Contexto menor, resposta melhor, conta menor.
    """
    sistema = ("Voce e o assistente comercial do FlowDesk, um SaaS B2B. "
               "Escreva uma resposta curta, cordial e objetiva ao lead, "
               "em portugues. Nao invente dados que nao estao no "
               "contexto.")
    conteudo = (f"Pedido do lead: {triagem.resumo}\n"
                f"Intencao: {triagem.intencao} | "
                f"Urgencia: {triagem.urgencia}\n"
                f"Cadastro no CRM: {dados_crm}")

    with observar("redigir", tipo="generation", entrada=conteudo):
        return chat(provider, [{"role": "user", "content": conteudo}],
                    system=sistema)


def triar_mensagem(mensagem, consultar_crm, provider="anthropic"):
    """O chaining de tres passos, com um gate entre o primeiro e o segundo.

    extrair -> [gate] -> consultar CRM -> redigir

    Devolve (resposta, triagem). Quando o gate barra, a resposta diz o
    que falta, e os passos 2 e 3 nem chegam a rodar.
    """
    with iniciar_trace("chaining", entrada=mensagem):
        triagem = _passo_extrair(mensagem, provider)

        if not _gate_tem_email(triagem):
            # Parar cedo e barato. Seguir com dado faltando e caro.
            return ("Nao identifiquei o email na mensagem. Poderia "
                    "confirmar o email de cadastro?"), triagem

        dados = _passo_consultar(triagem, consultar_crm)
        resposta = _passo_redigir(triagem, dados, provider)
        return resposta, triagem


# ===========================================================================
# PADRAO 2 - ROUTING
#
# Classificar a entrada e mandar para o handler certo. Use quando os
# tipos de pedido sao bem distintos e cada um tem tratamento proprio.
#
# O ganho: cada handler fica com uma instrucao curta e especializada,
# em vez de um prompt gigante que tenta cobrir todos os casos. Prompt
# que tenta fazer tudo faz tudo mal.
# ===========================================================================

def classificar(mensagem, provider="anthropic"):
    """A etapa de roteamento: so classifica, nao resolve nada.

    Reusamos a Triagem: a classificacao ja esta no campo `intencao`.
    Um classificador separado seria uma chamada a mais pelo mesmo dado.
    """
    with observar("classificar", entrada=mensagem):
        return extrair_estruturado(mensagem, Triagem, provider=provider)


def rotear(mensagem, handlers, provider="anthropic"):
    """Classifica a mensagem e entrega ao handler da intencao.

    handlers -> dict {"comercial": fn, "suporte": fn, "duvida": fn}

    Cada handler recebe a Triagem ja pronta e devolve a resposta. O
    roteador nao sabe o que cada um faz, e e assim que deve ser: trocar
    um handler nao mexe no roteador.
    """
    with iniciar_trace("routing", entrada=mensagem) as raiz:
        triagem = classificar(mensagem, provider)

        handler = handlers.get(triagem.intencao)
        if handler is None:
            # Rota sem handler e erro de configuracao, nao de runtime:
            # falha alto, como na Aula 0.1.
            raise ValueError(
                f"Sem handler para a intencao '{triagem.intencao}'. "
                f"Handlers registrados: {sorted(handlers)}")

        with observar(f"handler:{triagem.intencao}") as sp:
            resposta = handler(triagem)
            if sp is not None:
                sp.saida = resposta

        if raiz is not None:
            raiz.saida = resposta
        return resposta, triagem
