"""Nucleo de Agentes Operacionais - Fase 0.

Um agente de acao em codigo puro, sem framework: agnostico de provider,
com registro de ferramentas, resiliencia a erro e observabilidade.

Este arquivo declara a API PUBLICA do pacote. Ate a Aula 0.7 ele estava
vazio, e tudo era importado pelo caminho interno. Declarar o que e
publico e dizer, para voce mesmo daqui a tres meses e para quem clonar
o repositorio, onde estao as portas da casa.

Uso minimo:

    from nucleo import banco, ferramentas          # registra as ferramentas
    from nucleo import rodar_agente, schemas, executores_seguros

    banco.criar_schema()
    exe = rodar_agente("A Ana relatou erro de login.",
                       schemas(), executores_seguros())
    print(exe.resposta)
"""

# A ordem dos imports abaixo segue as camadas do sistema, de baixo para
# cima. Ela e, na pratica, o mapa da Fase 0.

# Camada 1 - falar com o modelo (Aulas 0.1 e 0.3)
from nucleo.config import ANTHROPIC_MODEL, OPENAI_MODEL
from nucleo.providers import (PedidoFerramenta, RespostaLLM, chat,
                              chat_ferramentas, mensagens_de_resultado)

# Camada 2 - o laco (Aula 0.3)
from nucleo.agente import Execucao, rodar_agente

# Camada 3 - ferramentas: definicao, execucao e dominio (Aulas 0.4 e 0.5)
from nucleo.registro import (Ferramenta, executar_ferramenta, executores,
                             ferramenta, schemas, schemas_para)

# Camada 4 - contratos e resiliencia (Aula 0.6)
from nucleo.modelos import QualificacaoLead
from nucleo.estruturado import extrair_estruturado
from nucleo.resiliencia import (ErroIrrecuperavel, executores_seguros,
                                proteger)

# Camada 5 - observabilidade (Aula 0.7)
from nucleo.observabilidade import (arvore, iniciar_trace, observar,
                                    registrar_uso, resumo)

# ferramentas e banco NAO sao importados aqui de proposito: importar
# nucleo.ferramentas tem efeito colateral (registra as tres ferramentas
# do dominio no REGISTRO). Quem quer o dominio pede por ele
# explicitamente. O motor e o dominio ficam separados, e e isso que
# torna o Nucleo replicavel em outro cliente.

__all__ = [
    # provider
    "chat", "chat_ferramentas", "mensagens_de_resultado",
    "RespostaLLM", "PedidoFerramenta",
    "ANTHROPIC_MODEL", "OPENAI_MODEL",
    # agente
    "rodar_agente", "Execucao",
    # ferramentas
    "ferramenta", "schemas", "schemas_para", "executores",
    "executar_ferramenta", "Ferramenta",
    # contratos e resiliencia
    "QualificacaoLead", "extrair_estruturado",
    "proteger", "executores_seguros", "ErroIrrecuperavel",
    # observabilidade
    "iniciar_trace", "observar", "registrar_uso", "arvore", "resumo",
]

__version__ = "0.8.0"      # fim da Fase 0
