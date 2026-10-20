"""Aula 1.3 - Os dois padroes rodando de verdade, com API real.

    python exemplos/orquestrar_pedido.py

Precisa de ANTHROPIC_API_KEY no .env. Gasta tokens: sao 5 chamadas ao
modelo na parte do orquestrador e 3 na parte das analises.

A mensagem de exemplo e proposital: ela traz TRES pedidos diferentes
num paragrafo so. Nenhum dos padroes da Aula 1.2 expressa isso. O
chaining tem caminho fixo e o router escolhe UMA rota.
"""

import time

from nucleo import banco, ferramentas                 # noqa: F401
from nucleo.ferramentas import (abrir_ticket, agendar_reuniao,
                                buscar_atualizar_crm)
from nucleo.observabilidade import arvore, resumo
from nucleo.paralelo import (ANALISES, _analisar, analisar_em_paralelo,
                             orquestrar)

MENSAGEM = (
    "Oi, aqui e a Ana da TechFlow (ana@techflow.com). Tres coisas: "
    "primeiro, o relatorio de exportacao esta dando erro 500 desde "
    "ontem e isso esta travando o meu time. Segundo, a gente quer "
    "entender o plano Pro porque vamos crescer para 40 usuarios no "
    "trimestre. E terceiro, preciso remarcar a call de quinta, nao vou "
    "conseguir estar."
)


# ---------------------------------------------------------------------------
# OS WORKERS
#
# Cada worker reaproveita as ferramentas da Fase 0. Repare que eles sao
# funcoes comuns: o worker nao precisa ser um agente. Na duvida, nao
# seja. Autonomia dentro do worker e custo a mais por pouca coisa.
# ---------------------------------------------------------------------------
def worker_suporte(s):
    return abrir_ticket(email="ana@techflow.com", assunto="Erro 500",
                        descricao=s.pedido, prioridade="alta")


def worker_comercial(s):
    return buscar_atualizar_crm(email="ana@techflow.com")


def worker_agenda(s):
    return agendar_reuniao(email="ana@techflow.com",
                           assunto=s.pedido, dia="2026-10-27")


WORKERS = {"suporte": worker_suporte,
           "comercial": worker_comercial,
           "agenda": worker_agenda}


def medir_sequencial():
    """O contrafactual: as mesmas tres analises, uma apos a outra.

    Sem este numero o ganho do paralelismo e fe. Com ele, e medida.
    """
    inicio = time.perf_counter()
    for nome, pergunta in ANALISES.items():
        _analisar(nome, pergunta, MENSAGEM, "anthropic")
    return time.perf_counter() - inicio


if __name__ == "__main__":
    banco.criar_schema(semear=True)

    print("=" * 70)
    print("PARTE 1 - PARALLELIZATION (tres analises que voce escreveu)")
    print("=" * 70)

    gasto_seq = medir_sequencial()

    inicio = time.perf_counter()
    analises = analisar_em_paralelo(MENSAGEM)
    gasto_par = time.perf_counter() - inicio

    for nome, saida in analises.items():
        print(f"\n[{nome}] {saida}")

    print(f"\nsequencial: {gasto_seq:.2f}s")
    print(f"paralelo:   {gasto_par:.2f}s")
    print(f"ganho:      {gasto_seq / gasto_par:.1f}x")
    print("E as tres chamadas continuam custando o mesmo. Latencia, "
          "nao dinheiro.")

    print()
    print("=" * 70)
    print("PARTE 2 - ORCHESTRATOR-WORKERS (o modelo decide quantas)")
    print("=" * 70)

    resposta, plano, resultados = orquestrar(MENSAGEM, WORKERS)

    print(f"\nO modelo decompos em {len(plano.subtarefas)} subtarefas:")
    for s in plano.subtarefas:
        print(f"  - {s.tipo:10} {s.pedido}")

    print("\nO que cada worker devolveu:")
    for tipo, saida in resultados:
        print(f"  - {tipo:10} {saida}")

    print(f"\nRESPOSTA SINTETIZADA:\n{resposta}")

    print("\nNenhuma linha deste arquivo decidiu que eram tres. Mande "
          "uma mensagem com um pedido so e o mesmo codigo roda um "
          "worker.")
