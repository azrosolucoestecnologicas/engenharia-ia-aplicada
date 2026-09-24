"""Aula 0.4 - Registro de ferramentas e schema portavel.

Uma ferramenta tem duas metades: a DEFINICAO (o contrato que o modelo
enxerga) e a EXECUCAO (a funcao Python que roda). Este modulo guarda as
duas num lugar so e gera o schema de cada provider automaticamente.

A regra da aula: adicionar uma ferramenta nova e escrever uma funcao.
Nada mais. O laco da Aula 0.3 nao muda uma linha.
"""

import inspect                   # le assinatura e docstring das funcoes
from dataclasses import dataclass, field


# Traducao de type hint do Python para tipo do JSON Schema. Sao os
# quatro tipos simples que cobrem a maioria das ferramentas reais.
# Tipos compostos ficam para quando o projeto precisar: nao
# antecipamos complexidade.
MAPA_TIPOS = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


@dataclass
class Ferramenta:
    """O contrato neutro de uma ferramenta, sem dialeto de provider."""
    nome: str                     # liga a definicao a execucao
    descricao: str                # o que o modelo le para decidir usar
    funcao: object                # a funcao Python que executa de verdade
    propriedades: dict = field(default_factory=dict)  # JSON Schema dos params
    obrigatorios: list = field(default_factory=list)  # params sem default


# O cartorio: nome da ferramenta -> Ferramenta. E um dict de modulo,
# entao importar nucleo.registro em qualquer lugar enxerga o mesmo
# registro.
REGISTRO = {}


def ferramenta(func):
    """Decorator que REGISTRA a funcao como ferramenta do agente.

    Ele nao modifica nada: le a assinatura e a docstring, monta o
    contrato neutro, guarda no REGISTRO e devolve a funcao ORIGINAL,
    intocada. Por isso voce continua podendo chamar a funcao como
    Python comum, inclusive nos testes.
    """
    assinatura = inspect.signature(func)

    propriedades = {}
    obrigatorios = []

    for nome_param, param in assinatura.parameters.items():
        anotacao = param.annotation

        if anotacao is inspect.Parameter.empty:
            # Sem type hint nao da para gerar schema. Falhar alto aqui
            # e melhor do que o modelo receber um contrato incompleto
            # e errar o argumento em producao.
            raise TypeError(
                f"A ferramenta '{func.__name__}' tem o parametro "
                f"'{nome_param}' sem type hint. Anote o tipo."
            )

        tipo_json = MAPA_TIPOS.get(anotacao)
        if tipo_json is None:
            raise TypeError(
                f"Tipo nao suportado em '{func.__name__}.{nome_param}': "
                f"{anotacao}. Use str, int, float ou bool."
            )

        propriedades[nome_param] = {"type": tipo_json}

        # Sem valor padrao = obrigatorio. E o sinal que o inspect da.
        if param.default is inspect.Parameter.empty:
            obrigatorios.append(nome_param)

    descricao = inspect.getdoc(func) or ""
    if not descricao:
        # Descricao de ferramenta e PROMPT: e o texto que o modelo le
        # para decidir usar. Sem ela, a acuracia de selecao despenca.
        raise ValueError(
            f"A ferramenta '{func.__name__}' nao tem docstring. "
            "A descricao e o que o modelo le para decidir usa-la."
        )

    REGISTRO[func.__name__] = Ferramenta(
        nome=func.__name__,
        descricao=descricao,
        funcao=func,
        propriedades=propriedades,
        obrigatorios=obrigatorios,
    )

    return func                   # a funcao ORIGINAL, sem wrapper


# ---------------------------------------------------------------------------
# TRADUCAO: o miolo (JSON Schema) e identico; so a embalagem muda.
# ---------------------------------------------------------------------------

def _miolo(f):
    """O JSON Schema dos parametros, igual nos dois providers."""
    return {
        "type": "object",
        "properties": f.propriedades,
        "required": f.obrigatorios,
    }


def _schema_anthropic(f):
    # Anthropic: name, description e input_schema no topo, sem envelope.
    return {"name": f.nome, "description": f.descricao,
            "input_schema": _miolo(f)}


def _schema_openai(f):
    # OpenAI: tudo dentro de "function"; o schema chama "parameters".
    return {"type": "function", "function": {
        "name": f.nome, "description": f.descricao,
        "parameters": _miolo(f)}}


def schemas_para(provider):
    """Lista de schemas de TODAS as ferramentas, no dialeto pedido."""
    if provider == "anthropic":
        return [_schema_anthropic(f) for f in REGISTRO.values()]
    if provider == "openai":
        return [_schema_openai(f) for f in REGISTRO.values()]
    raise ValueError(f"Provider desconhecido: {provider}")


def schemas():
    """O dict {"anthropic": [...], "openai": [...]} que rodar_agente
    espera. Substitui os schemas escritos a mao na Aula 0.3."""
    return {"anthropic": schemas_para("anthropic"),
            "openai": schemas_para("openai")}


def executores():
    """O dict {nome: funcao} que rodar_agente espera."""
    return {nome: f.funcao for nome, f in REGISTRO.items()}


def executar_ferramenta(nome, argumentos):
    """Executa a ferramenta pelo nome, com os argumentos do modelo.

    A ligacao entre o que o modelo pediu e o que roda e apenas o NOME.
    Esse desacoplamento e o que permite trocar de framework depois sem
    reescrever o dominio, e e o que o MCP formaliza na Fase 2.
    """
    f = REGISTRO.get(nome)
    if f is None:
        # Nao levantamos excecao: ferramenta desconhecida vira
        # observacao que o agente le e contorna (Aulas 0.3 e 0.6).
        return {"erro": f"ferramenta desconhecida: {nome}"}
    return f.funcao(**argumentos)
