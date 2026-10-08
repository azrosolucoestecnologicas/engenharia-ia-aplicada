"""Demo da Fase 0: o Nucleo qualificando um lead de ponta a ponta.

Este arquivo e a documentacao executavel do projeto. Quem clona o
repositorio roda isto primeiro:

    python exemplos/qualificar_lead.py

Diferente dos rascunhos de scratch/, ele FICA no repositorio: e a porta
de entrada de quem chega, e o roteiro da demo gravada.

Requer um .env preenchido (veja o .env.example).
"""

from nucleo import banco, ferramentas          # noqa: F401 - registra o dominio
from nucleo import (QualificacaoLead, arvore, executores_seguros,
                    extrair_estruturado, resumo, rodar_agente, schemas)

# A politica comercial mora AQUI, no prompt, nao nas ferramentas.
# Trocar de cliente e trocar este texto e a base, nao o codigo.
SISTEMA = """Voce e o assistente comercial do FlowDesk, um SaaS B2B.

Consulte o CRM antes de qualquer acao sobre um lead. Considere
qualificado quem tem plano pro ou enterprise, ou MRR acima de 300;
nesse caso, atualize o status e proponha uma reuniao. Problema tecnico
vira ticket, nunca reuniao."""

PERGUNTA = ("A Ana do TechFlow escreveu: o login pelo SSO esta dando "
            "erro 500 desde ontem, e ela quer conversar sobre migrar "
            "de plano.")


def main():
    banco.criar_schema()                       # idempotente

    execucao = rodar_agente(PERGUNTA, schemas(), executores_seguros(),
                            system=SISTEMA, verbose=False)

    print("=" * 60)
    print("RESPOSTA\n")
    print(execucao.resposta)

    print("\n" + "=" * 60)
    print("COMO O AGENTE CHEGOU LA\n")
    print(arvore(execucao.trace))               # a arvore da Aula 0.7

    print("\n" + "=" * 60)
    print("CUSTO DESTA SESSAO\n")
    print(resumo(execucao.trace))

    print("\n" + "=" * 60)
    print("CONTRATO PARA O PROXIMO SISTEMA\n")
    dados = extrair_estruturado(execucao.resposta, QualificacaoLead)
    print(dados.model_dump_json(indent=2))      # o contrato da Aula 0.6


if __name__ == "__main__":
    main()
