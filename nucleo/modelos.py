"""Aula 0.6 - Os contratos de saida do Nucleo.

Um contrato Pydantic nao e documentacao: e codigo que VALIDA. Declarar
o formato esperado como classe faz a validacao vir de graca, com
mensagem de erro legivel, e serve de fonte para o JSON Schema que
pedimos ao modelo.

Aviso que vale para a aula inteira: validacao garante FORMATO, nunca
VERDADE. Um QualificacaoLead perfeitamente valido pode conter uma
pontuacao inventada. Formato e problema de engenharia e se resolve
aqui; verdade e problema de avaliacao e se resolve na Fase 3.
"""

from typing import Literal

from pydantic import BaseModel, Field


class QualificacaoLead(BaseModel):
    """O que o Nucleo devolve para outro sistema consumir."""

    email: str = Field(description="Email do lead qualificado")

    status: Literal["qualificado", "nutrir", "descartado"] = Field(
        description="Decisao final sobre o lead")

    pontuacao: int = Field(ge=0, le=100,
                           description="Score de 0 a 100")

    justificativa: str = Field(
        description="Por que este status, em uma frase")

    proxima_acao: str = Field(
        description="O proximo passo concreto, em uma frase")


# Literal fecha o vocabulario do status; ge e le impedem pontuacao 150.
# O contrato carrega as REGRAS, nao so os nomes dos campos.
