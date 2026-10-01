"""Aula 0.6 - Erro de ferramenta vira observacao, nao excecao.

O insight central da aula, e ele e contraintuitivo: quando uma
ferramenta falha, o instinto do programador e deixar a excecao subir.
Num agente isso quase sempre esta errado, porque a excecao mata o laco
e o agente perde a chance de contornar.

Pense em como um humano lidaria. Voce tenta agendar, o sistema diz que
o horario esta ocupado, e voce propoe outro. Nao abandona a tarefa. O
agente faz o mesmo, DESDE QUE o erro chegue ate ele como informacao.

A regra: erro que o agente PODE contornar vira texto de observacao.
Erro que ele NAO pode contornar (infraestrutura) sobe e para o laco.
"""

from pydantic import ValidationError, validate_call

from nucleo.registro import REGISTRO


class ErroIrrecuperavel(Exception):
    """Falha que o agente nao tem como contornar.

    Provider fora do ar, credencial expirada, banco inacessivel.
    Insistir so queima token: deixamos subir e o laco para.
    """


def _mensagem_de_validacao(erro):
    """Transforma o erro do Pydantic em instrucao para o modelo.

    Nao basta dizer que falhou: o texto precisa dizer QUAL campo e
    POR QUE, senao o modelo tenta de novo do mesmo jeito.
    """
    partes = []
    for e in erro.errors():
        campo = ".".join(str(x) for x in e["loc"]) or "(argumento)"
        partes.append(f"{campo}: {e['msg']}")
    return "; ".join(partes)


def proteger(func):
    """Embrulha uma ferramenta para que ela nunca derrube o agente.

    Faz duas coisas:
      1. valida os argumentos gerados pelo modelo contra os type hints
         da propria funcao (inclusive Literal, que virou enum na 0.5);
      2. captura a falha de execucao e devolve texto que o agente le.

    O wrapper aceita **kwargs em vez da assinatura real de proposito:
    se o modelo inventar um argumento que nao existe, queremos tratar
    isso como observacao, nao como TypeError do Python.
    """
    validada = validate_call(func)   # valida contra os type hints

    def executor_seguro(**kwargs):
        try:
            return validada(**kwargs)

        except ValidationError as e:
            # O modelo errou ou inventou um argumento. Devolvemos o
            # diagnostico para ele corrigir na proxima volta do laco.
            return (f"ERRO DE ARGUMENTO em {func.__name__}: "
                    f"{_mensagem_de_validacao(e)}. "
                    "Corrija os argumentos e chame a ferramenta de novo.")

        except TypeError as e:
            # Argumento a mais, a menos, ou com nome errado.
            return (f"ERRO DE ARGUMENTO em {func.__name__}: {e}. "
                    "Confira os parametros no schema da ferramenta.")

        except ErroIrrecuperavel:
            # Infraestrutura: o agente nao contorna. Deixa subir.
            raise

        except Exception as e:
            # A ferramenta quebrou por conta propria. Tambem e
            # observacao: o agente pode tentar outro caminho.
            return (f"ERRO NA FERRAMENTA {func.__name__}: "
                    f"{type(e).__name__}: {e}")

    executor_seguro.__name__ = func.__name__
    return executor_seguro


def executores_seguros():
    """Igual ao executores() da aula 0.4, porem com tudo protegido.

    E o que permite o laco da aula 0.3 continuar intocado: ele recebe
    um dicionario de funcoes e nao precisa saber que elas agora se
    defendem sozinhas.
    """
    return {nome: proteger(f.funcao) for nome, f in REGISTRO.items()}
