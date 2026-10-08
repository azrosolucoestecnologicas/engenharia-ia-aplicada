"""Aula 0.7 - Observabilidade desde o berco.

TODA a dependencia de plataforma de tracing mora NESTE arquivo. Os
outros modulos chamam as funcoes daqui, nunca o SDK direto. Trocar de
plataforma e reescrever este arquivo e mais nada.

Duas camadas, de proposito:

  1. Um rastreador LOCAL, sempre ligado, que monta a arvore da execucao
     em memoria. E ele que faz a aula funcionar sem conta em lugar
     nenhum, e que torna a instrumentacao TESTAVEL sem rede.

  2. Uma ponte OPCIONAL para o Langfuse, ligada so quando as
     credenciais existem no ambiente. Se o pacote nao estiver
     instalado ou as chaves faltarem, o sistema roda normalmente.

Observabilidade nunca pode ser requisito duro para o projeto subir.
"""

import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Carrega o .env AQUI tambem: este modulo pode ser importado antes do
# config (o agente.py faz isso), e a checagem abaixo roda na importacao.
load_dotenv()

# A ponte so liga com credencial no ambiente. Sem isso, so o rastreador
# local roda, e nada quebra.
TRACING_ATIVO = bool(os.getenv("LANGFUSE_PUBLIC_KEY"))


# ---------------------------------------------------------------------------
# O VOCABULARIO (padrao da industria, nao invencao de nenhuma ferramenta)
#
#   trace      -> uma execucao inteira, de ponta a ponta
#   span       -> um passo dentro dela, com inicio, fim e duracao
#   generation -> um span especial: uma chamada ao modelo, que alem da
#                 duracao carrega modelo e tokens, e portanto custo
# ---------------------------------------------------------------------------
@dataclass
class Passo:
    """Um no da arvore de execucao."""
    nome: str
    tipo: str                      # "trace", "span" ou "generation"
    entrada: object = None
    saida: object = None
    inicio: float = 0.0
    fim: float = 0.0
    modelo: str = ""
    tokens_entrada: int = 0
    tokens_saida: int = 0
    filhos: list = field(default_factory=list)

    @property
    def duracao_ms(self):
        return int((self.fim - self.inicio) * 1000)

    def totais(self):
        """Soma tokens da subarvore inteira, recursivamente."""
        entrada = self.tokens_entrada
        saida = self.tokens_saida
        for f in self.filhos:
            e, s = f.totais()
            entrada += e
            saida += s
        return entrada, saida


# O trace corrente. ContextVar em vez de variavel global para o dia em
# que o Nucleo rodar com varias requisicoes simultaneas (Fase 4): cada
# contexto enxerga o seu proprio trace.
_pilha: ContextVar = ContextVar("pilha_de_passos", default=None)


@contextmanager
def observar(nome, tipo="span", entrada=None, modelo=""):
    """Abre um passo e o fecha ao sair do bloco.

    O aninhamento sai de graca: cada passo aberto vira filho do que
    estiver no topo da pilha. E isso que forma a arvore.
    """
    pilha = _pilha.get()
    if pilha is None:
        # Ninguem abriu um trace: nao rastreamos, mas o codigo roda.
        yield None
        return

    passo = Passo(nome=nome, tipo=tipo, entrada=entrada,
                  modelo=modelo, inicio=time.time())
    if pilha:
        pilha[-1].filhos.append(passo)
    pilha.append(passo)

    # A ponte com a plataforma externa, quando existir, abre o mesmo
    # passo la. Nada do resto do Nucleo precisa saber disso.
    externo = _abrir_externo(nome, tipo, entrada)
    try:
        yield passo
    finally:
        passo.fim = time.time()
        pilha.pop()
        _fechar_externo(externo, passo)


@contextmanager
def iniciar_trace(nome, entrada=None):
    """Abre a execucao inteira. Tudo que acontecer dentro vira filho."""
    token = _pilha.set([])
    try:
        with observar(nome, tipo="trace", entrada=entrada) as raiz:
            yield raiz
    finally:
        _pilha.reset(token)
        _enviar_pendentes()


def registrar_uso(passo, tokens_entrada, tokens_saida, modelo=""):
    """Anota o consumo de tokens de uma generation.

    Tokens sao a unica regua de custo que existe nesta area, e e por
    isso que eles sobem ate o topo da arvore no resumo.
    """
    if passo is None:
        return
    passo.tokens_entrada = tokens_entrada
    passo.tokens_saida = tokens_saida
    if modelo:
        passo.modelo = modelo


# ---------------------------------------------------------------------------
# LEITURA DA ARVORE (o que substitui o print espalhado pelo codigo)
# ---------------------------------------------------------------------------

def arvore(raiz, nivel=0):
    """Desenha a arvore da execucao em texto."""
    recuo = "  " * nivel
    etiqueta = {"trace": "TRACE", "span": "span",
                "generation": "gen"}.get(raiz.tipo, raiz.tipo)
    linha = f"{recuo}[{etiqueta}] {raiz.nome}  {raiz.duracao_ms}ms"
    if raiz.tokens_entrada or raiz.tokens_saida:
        linha += f"  ({raiz.tokens_entrada} in / {raiz.tokens_saida} out)"
    linhas = [linha]
    for f in raiz.filhos:
        linhas.append(arvore(f, nivel + 1))
    return "\n".join(linhas)


def resumo(raiz):
    """Os numeros que importam numa execucao."""
    entrada, saida = raiz.totais()
    geracoes = _contar(raiz, "generation")
    return {
        "duracao_ms": raiz.duracao_ms,
        "chamadas_ao_modelo": geracoes,
        "ferramentas_executadas": _contar(raiz, "span"),
        "tokens_entrada": entrada,
        "tokens_saida": saida,
    }


def _contar(passo, tipo):
    n = 1 if passo.tipo == tipo else 0
    for f in passo.filhos:
        n += _contar(f, tipo)
    return n


# ---------------------------------------------------------------------------
# A PONTE COM O LANGFUSE (opcional, isolada, e a unica parte acoplada)
#
# A API do SDK do Langfuse mudou entre versoes maiores. O codigo abaixo
# segue o SDK v3, baseado em OpenTelemetry:
#
#     from langfuse import get_client
#     langfuse = get_client()
#     with langfuse.start_as_current_observation(as_type="span", name=...)
#     langfuse.flush()
#
# CONFIRME a assinatura da versao que voce instalou antes de assumir que
# estes nomes valem. Se mudarem, muda AQUI, e so aqui.
# ---------------------------------------------------------------------------

def _cliente():
    if not TRACING_ATIVO:
        return None
    try:
        from langfuse import get_client
        return get_client()
    except Exception:
        # Pacote ausente ou credencial invalida: seguimos sem tracing
        # externo. O rastreador local continua funcionando.
        return None


def _abrir_externo(nome, tipo, entrada):
    cliente = _cliente()
    if cliente is None:
        return None
    try:
        as_type = "generation" if tipo == "generation" else "span"
        cm = cliente.start_as_current_observation(as_type=as_type,
                                                  name=nome,
                                                  input=entrada)
        return (cm, cm.__enter__())
    except Exception:
        return None


def _fechar_externo(externo, passo):
    if externo is None:
        return
    cm, _ = externo
    try:
        cm.__exit__(None, None, None)
    except Exception:
        pass


def _enviar_pendentes():
    """Forca o envio do lote antes do processo morrer.

    CAUSA NUMERO UM de "o trace nao apareceu": as plataformas enviam
    em lote, de forma assincrona, e script curto termina antes do
    envio. Em servidor de longa duracao isso nao aparece, o que torna
    o problema ainda mais confuso quando volta.
    """
    cliente = _cliente()
    if cliente is not None:
        try:
            cliente.flush()
        except Exception:
            pass
