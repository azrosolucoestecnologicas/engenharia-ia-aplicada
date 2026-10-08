# Aula 0.8 - Consolidacao da Fase 0.
#
# Dois tipos de teste aqui, e eles respondem perguntas diferentes:
#
#   FUMACA  -> o pacote se monta? a API publica esta de pe?
#              Nao testa comportamento. Pega o import quebrado depois
#              de uma refatoracao, e custa dez linhas.
#
#   PONTA A PONTA -> as cinco camadas da Fase 0 funcionam JUNTAS?
#              Cada aula testou a sua peca isoladamente. Ninguem tinha
#              testado o conjunto.

import json

import pytest

import nucleo
from nucleo import banco
from nucleo.providers import PedidoFerramenta, RespostaLLM


# ---------- FUMACA ----------

def test_api_publica_esta_de_pe():
    """Todo simbolo anunciado em __all__ existe de verdade."""
    faltando = [n for n in nucleo.__all__ if not hasattr(nucleo, n)]
    assert faltando == []


def test_todos_os_modulos_importam():
    """Pega o import circular ou quebrado depois de uma refatoracao."""
    from nucleo import (agente, banco, config, estruturado, ferramentas,
                        modelos, observabilidade, providers, registro,
                        resiliencia)
    assert all([agente, banco, config, estruturado, ferramentas, modelos,
                observabilidade, providers, registro, resiliencia])


def test_motor_e_dominio_sao_separados():
    """Importar o pacote NAO registra as ferramentas do FlowDesk.

    E isso que torna o Nucleo replicavel: outro cliente pluga o proprio
    dominio sem herdar o nosso. Se este teste quebrar, alguem importou
    nucleo.ferramentas dentro do __init__.
    """
    import importlib
    import sys

    for mod in ["nucleo", "nucleo.registro", "nucleo.ferramentas"]:
        sys.modules.pop(mod, None)

    limpo = importlib.import_module("nucleo")
    assert limpo.schemas()["anthropic"] == []

    # Agora sim, pedindo o dominio explicitamente:
    importlib.import_module("nucleo.ferramentas")
    nomes = {s["name"] for s in limpo.schemas()["anthropic"]}
    assert nomes == {"buscar_atualizar_crm", "agendar_reuniao",
                     "abrir_ticket"}


# ---------- PONTA A PONTA ----------

@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Banco temporario mais as tres ferramentas do dominio."""
    monkeypatch.setattr(banco, "CAMINHO_BANCO", tmp_path / "fase0.db")
    banco.criar_schema(semear=True)
    from nucleo import ferramentas            # registra o dominio
    return ferramentas


def _roteiro(monkeypatch, respostas):
    """Substitui o modelo por decisoes pre-escritas.

    O laco, as ferramentas, o banco, a resiliencia e o tracing rodam de
    verdade. So a escolha do modelo e nossa, porque testar a escolha
    dele e avaliacao, nao teste (Fase 3).
    """
    fila = list(respostas)
    monkeypatch.setattr(nucleo.agente, "chat_ferramentas",
                        lambda *a, **k: fila.pop(0))


def test_fluxo_completo_com_recuperacao(ambiente, monkeypatch):
    """As cinco camadas juntas, com um erro no meio do caminho.

    O modelo erra a prioridade (fora do enum), le o erro como
    observacao, corrige e conclui. Tudo isso rastreado.
    """
    turno = {"role": "assistant", "content": []}
    _roteiro(monkeypatch, [
        RespostaLLM("", [PedidoFerramenta(
            "1", "buscar_atualizar_crm", {"email": "ana@techflow.com"})],
            turno, tokens_entrada=1180, tokens_saida=62),
        RespostaLLM("", [PedidoFerramenta(
            "2", "abrir_ticket", {"email": "ana@techflow.com",
                                  "assunto": "Erro no login",
                                  "descricao": "Erro 500 no SSO",
                                  "prioridade": "urgentissima"})],
            turno, tokens_entrada=1420, tokens_saida=88),
        RespostaLLM("", [PedidoFerramenta(
            "3", "abrir_ticket", {"email": "ana@techflow.com",
                                  "assunto": "Erro no login",
                                  "descricao": "Erro 500 no SSO",
                                  "prioridade": "alta"})],
            turno, tokens_entrada=1690, tokens_saida=85),
        RespostaLLM("Ticket #1 aberto com prioridade alta.", [], None,
                    tokens_entrada=1810, tokens_saida=31),
    ])

    exe = nucleo.rodar_agente(
        "A Ana do TechFlow relatou erro 500 no login.",
        nucleo.schemas(), nucleo.executores_seguros(), verbose=False)

    # 1. O agente concluiu, apesar do erro no meio.
    assert exe.parou_por == "resposta_final"
    assert exe.iteracoes == 4

    # 2. O efeito colateral aconteceu de verdade, no banco.
    con = banco.conectar()
    tickets = con.execute(
        "SELECT prioridade FROM tickets").fetchall()
    con.close()
    assert len(tickets) == 1              # o invalido NAO gravou
    assert tickets[0]["prioridade"] == "alta"

    # 3. A execucao inteira ficou rastreada.
    r = nucleo.resumo(exe.trace)
    assert r["chamadas_ao_modelo"] == 4
    assert r["ferramentas_executadas"] == 3
    assert r["tokens_entrada"] == 6100    # a soma das quatro voltas


def test_troca_de_provider_e_configuracao(ambiente, monkeypatch):
    """O mesmo fluxo roda nos dois providers sem editar codigo."""
    vistos = []

    def espiao(provider, *a, **k):
        vistos.append(provider)
        return RespostaLLM("ok", [])

    for prov in ["anthropic", "openai"]:
        monkeypatch.setattr(nucleo.agente, "chat_ferramentas", espiao)
        exe = nucleo.rodar_agente("oi", nucleo.schemas(),
                                  nucleo.executores_seguros(),
                                  provider=prov, verbose=False)
        assert exe.parou_por == "resposta_final"

    assert vistos == ["anthropic", "openai"]


def test_saida_estruturada_fecha_o_ciclo(ambiente, monkeypatch):
    """A resposta em texto vira contrato pronto para outro sistema."""
    valido = json.dumps({
        "email": "ana@techflow.com", "status": "nutrir", "pontuacao": 45,
        "justificativa": "Plano trial, problema tecnico aberto",
        "proxima_acao": "Acompanhar apos resolucao do ticket"})
    monkeypatch.setattr(nucleo.estruturado, "chat",
                        lambda *a, **k: valido)

    dados = nucleo.extrair_estruturado("relato do agente",
                                       nucleo.QualificacaoLead)
    assert dados.status == "nutrir"
    assert 0 <= dados.pontuacao <= 100
