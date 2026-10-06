# Aula 0.7 - Testes da instrumentacao.
#
# Nenhuma rede, nenhuma plataforma externa. O que esta sob teste e a
# arvore que o rastreador local monta: aninhamento, duracao, tokens e
# os numeros do resumo. E tambem que o sistema roda igual quando o
# tracing esta desligado.

import time

import pytest

from nucleo import agente, observabilidade
from nucleo.observabilidade import (arvore, iniciar_trace, observar,
                                    registrar_uso, resumo)
from nucleo.providers import PedidoFerramenta, RespostaLLM


# ---------- 1. o aninhamento forma a arvore ----------

def test_passos_se_aninham():
    with iniciar_trace("execucao") as raiz:
        with observar("passo_externo"):
            with observar("passo_interno"):
                pass
        with observar("outro_passo"):
            pass

    assert raiz.tipo == "trace"
    assert [f.nome for f in raiz.filhos] == ["passo_externo", "outro_passo"]
    assert raiz.filhos[0].filhos[0].nome == "passo_interno"


# ---------- 2. duracao e medida de verdade ----------

def test_duracao_e_medida():
    with iniciar_trace("execucao") as raiz:
        with observar("lento"):
            time.sleep(0.02)
    assert raiz.filhos[0].duracao_ms >= 15
    assert raiz.duracao_ms >= raiz.filhos[0].duracao_ms


# ---------- 3. tokens sobem pela arvore ----------

def test_tokens_somam_na_subarvore():
    with iniciar_trace("execucao") as raiz:
        with observar("c1", tipo="generation") as g1:
            registrar_uso(g1, 1000, 50)
        with observar("c2", tipo="generation") as g2:
            registrar_uso(g2, 1500, 80)

    entrada, saida = raiz.totais()
    assert entrada == 2500
    assert saida == 130
    # O custo de uma sessao e a soma de TODAS as voltas, nao da ultima.


# ---------- 4. o resumo traz os numeros que importam ----------

def test_resumo_conta_geracoes_e_ferramentas():
    with iniciar_trace("execucao") as raiz:
        with observar("decisao 1", tipo="generation") as g:
            registrar_uso(g, 900, 30)
        with observar("buscar_atualizar_crm"):
            pass
        with observar("decisao 2", tipo="generation") as g:
            registrar_uso(g, 1200, 40)

    r = resumo(raiz)
    assert r["chamadas_ao_modelo"] == 2
    assert r["ferramentas_executadas"] == 1
    assert r["tokens_entrada"] == 2100


# ---------- 5. sem trace aberto, nada quebra ----------

def test_observar_fora_de_trace_nao_quebra():
    # Codigo instrumentado precisa rodar em qualquer contexto, inclusive
    # num teste que nao abriu trace nenhum.
    with observar("solto") as passo:
        assert passo is None


# ---------- 6. sem credencial, o sistema roda igual ----------

def test_sem_credencial_nao_envia_nada(monkeypatch):
    monkeypatch.setattr(observabilidade, "TRACING_ATIVO", False)
    with iniciar_trace("execucao") as raiz:
        with observar("passo"):
            pass
    assert raiz.filhos[0].nome == "passo"
    # Observabilidade nunca pode ser requisito duro para o projeto subir.


# ---------- 7. o laco produz a arvore da execucao ----------

FER = {"anthropic": [], "openai": []}


def _executores(registro):
    def buscar_info_lead(email):
        registro.append(email)
        return {"plano": "pro"}
    return {"buscar_info_lead": buscar_info_lead}


def test_agente_produz_arvore(monkeypatch):
    fila = [
        RespostaLLM("", [PedidoFerramenta("1", "buscar_info_lead",
                                          {"email": "c@d.io"})],
                    {"role": "assistant", "content": []},
                    tokens_entrada=1000, tokens_saida=40,
                    modelo="modelo-x"),
        RespostaLLM("Pronto.", [], None,
                    tokens_entrada=1400, tokens_saida=25,
                    modelo="modelo-x"),
    ]
    monkeypatch.setattr(agente, "chat_ferramentas",
                        lambda *a, **k: fila.pop(0))
    monkeypatch.setattr(agente, "mensagens_de_resultado",
                        lambda p, r, res: [{"role": "user", "content": "x"}])

    exe = agente.rodar_agente("?", FER, _executores([]), verbose=False)

    assert exe.trace is not None
    nomes = [f.nome for f in exe.trace.filhos]
    assert nomes == ["decisao 1", "buscar_info_lead", "decisao 2"]

    r = resumo(exe.trace)
    assert r["chamadas_ao_modelo"] == 2
    assert r["tokens_entrada"] == 2400       # as duas voltas somadas
    assert r["ferramentas_executadas"] == 1


# ---------- 8. a ferramenta registra argumentos e resultado ----------

def test_span_de_ferramenta_guarda_entrada_e_saida(monkeypatch):
    fila = [
        RespostaLLM("", [PedidoFerramenta("1", "buscar_info_lead",
                                          {"email": "c@d.io"})],
                    {"role": "assistant", "content": []}),
        RespostaLLM("ok", []),
    ]
    monkeypatch.setattr(agente, "chat_ferramentas",
                        lambda *a, **k: fila.pop(0))
    monkeypatch.setattr(agente, "mensagens_de_resultado",
                        lambda p, r, res: [{"role": "user", "content": "x"}])

    exe = agente.rodar_agente("?", FER, _executores([]), verbose=False)
    span = [f for f in exe.trace.filhos if f.nome == "buscar_info_lead"][0]

    assert span.entrada == {"email": "c@d.io"}
    assert span.saida == {"plano": "pro"}
    # E assim que se descobre, na segunda-feira, com que argumentos o
    # agente chamou a ferramenta no sabado.


# ---------- 9. a arvore em texto e legivel ----------

def test_arvore_desenha_hierarquia():
    with iniciar_trace("qualificar") as raiz:
        with observar("decisao 1", tipo="generation") as g:
            registrar_uso(g, 100, 10)

    texto = arvore(raiz)
    assert "[TRACE] qualificar" in texto
    assert "  [gen] decisao 1" in texto
    assert "100 in / 10 out" in texto
