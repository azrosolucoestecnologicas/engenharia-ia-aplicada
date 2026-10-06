# Aula 0.3 - O loop de agente, em Python puro.
#
# O laco nao sabe qual provider esta rodando nem quais ferramentas
# existem no sistema. Ele conhece apenas o ciclo:
#
#     CONTEXTO -> DECISAO -> ACAO -> OBSERVACAO -> (repete)
#
# A frase que resume a aula: o agente nao e o modelo, o agente e o loop.
#
# Depende de (aulas anteriores):
#     nucleo/config.py     -> nomes de modelo                   (aula 0.1)
#     nucleo/providers.py  -> chat_ferramentas(),
#                             mensagens_de_resultado() e as
#                             dataclasses PedidoFerramenta e
#                             RespostaLLM                       (aula 0.3)

import json                        # serializa o retorno da ferramenta
from dataclasses import dataclass  # classe de dados sem boilerplate

from nucleo.observabilidade import (iniciar_trace, observar,
                                    registrar_uso, resumo)
from nucleo.providers import chat_ferramentas, mensagens_de_resultado


# ---------------------------------------------------------------------------
# O RESULTADO DE UMA EXECUCAO
#
# Nao devolvemos so a string da resposta. Devolvemos tambem a prestacao
# de contas do caminho percorrido. Isso e o embriao da observabilidade
# que vira trace no Langfuse na aula 0.7 e estado persistido na Fase 1.
# ---------------------------------------------------------------------------
@dataclass
class Execucao:
    """O que o agente devolve ao fim de uma tarefa."""

    resposta: str
    # Texto final que o agente produziu para o usuario.

    iteracoes: int
    # Quantas voltas o laco deu. Metrica direta de custo e de latencia.

    parou_por: str
    # "resposta_final" ou "limite_de_iteracoes".
    # Saber POR QUE parou e o que permite diagnosticar agente travado.

    historico: list
    # A conversa completa: pergunta, decisoes do modelo e observacoes.
    # Este e o ESTADO do agente. Hoje ele vive na memoria e morre com o
    # processo. Persistir isto e o tema de checkpointing na Fase 1.

    trace: object = None
    # Aula 0.7: a raiz da arvore de execucao. Traz duracao por passo e
    # tokens por chamada. Use arvore(exe.trace) para desenhar.


# ---------------------------------------------------------------------------
# O LACO
# ---------------------------------------------------------------------------
def rodar_agente(
    pergunta,
    ferramentas,
    executores,
    provider="anthropic",
    system=None,
    max_iteracoes=6,
    verbose=True,
):
    """Roda o agente ate ele responder ou ate bater o teto de iteracoes.

    pergunta      -> texto do usuario que inicia a tarefa
    ferramentas   -> dict {"anthropic": [...], "openai": [...]} com os schemas
    executores    -> dict {nome_da_ferramenta: funcao_python}
    provider      -> "anthropic" ou "openai"
    system        -> instrucao de sistema, opcional
    max_iteracoes -> teto de voltas. E orcamento, nao paranoia.
    verbose       -> imprime o caminho percorrido, util em aula e depuracao
    """

    historico = [{"role": "user", "content": pergunta}]
    # O HISTORICO E O ESTADO. Nao existe memoria magica: o modelo
    # "lembra" porque reenviamos a conversa inteira a cada volta, com
    # um item a mais.

    # Aula 0.7: toda a execucao vira um trace. Os passos de dentro se
    # aninham sozinhos, formando a arvore.
    with iniciar_trace("rodar_agente", entrada=pergunta) as raiz:

        # Usamos 'for' em vez de 'while True' de proposito: o teto de
        # iteracoes ja vem embutido na propria estrutura, entao e
        # impossivel esquecer dele.
        for iteracao in range(1, max_iteracoes + 1):

            # DECISAO: o modelo le o contexto e escolhe o proximo passo.
            # Chamada ao modelo e GENERATION: e nela que mora o custo.
            with observar(f"decisao {iteracao}", tipo="generation") as gen:
                resposta = chat_ferramentas(
                    provider, historico, ferramentas, system=system)
                registrar_uso(gen, resposta.tokens_entrada,
                              resposta.tokens_saida, resposta.modelo)

            # PARADA 1: respondeu sem pedir ferramenta. Caso feliz.
            if not resposta.pedidos:
                if verbose:
                    print(f"[volta {iteracao}] resposta final")
                if raiz is not None:
                    raiz.saida = resposta.texto
                return Execucao(
                    resposta=resposta.texto,
                    iteracoes=iteracao,
                    parou_por="resposta_final",
                    historico=historico,
                    trace=raiz,
                )

            # ACAO: executa cada pedido. Podem vir varios numa volta so.
            resultados = []
            for pedido in resposta.pedidos:
                if verbose:
                    print(f"[volta {iteracao}] "
                          f"{pedido.nome}({pedido.argumentos})")

                # Execucao de ferramenta e SPAN: tem duracao, nao tem
                # token. E aqui que se descobre o agente chamando a
                # mesma coisa tres vezes.
                with observar(pedido.nome, entrada=pedido.argumentos) as sp:
                    funcao = executores.get(pedido.nome)
                    if funcao is None:
                        # Ferramenta desconhecida NAO derruba o agente:
                        # vira observacao que ele le e contorna.
                        saida = {"erro": f"ferramenta desconhecida: "
                                         f"{pedido.nome}"}
                    else:
                        saida = funcao(**pedido.argumentos)
                    if sp is not None:
                        sp.saida = saida

                # O resultado e TEXTO que o modelo vai ler na proxima
                # volta. ensure_ascii=False preserva os acentos.
                resultados.append(
                    (pedido, json.dumps(saida, ensure_ascii=False)))

            # OBSERVACAO: o turno do assistant e os resultados voltam
            # para o historico, no dialeto certo.
            historico.extend(
                mensagens_de_resultado(provider, resposta, resultados))

        # PARADA 2: estourou o teto. Isto NAO e sucesso.
        if verbose:
            print(f"[fim] limite de {max_iteracoes} iteracoes atingido")
        return Execucao(
            resposta="",
            iteracoes=max_iteracoes,
            parou_por="limite_de_iteracoes",
            historico=historico,
            trace=raiz,
        )
