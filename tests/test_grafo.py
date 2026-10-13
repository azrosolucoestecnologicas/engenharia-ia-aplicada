# Aula 1.1 - Testes do grafo de estado.
#
# Nenhuma chamada de API. O grafo roda de verdade; so a decisao do
# modelo e nossa.
#
# O teste mais importante deste arquivo nao e sobre LangGraph: e o que
# prova que o grafo e o laco da Fase 0 produzem o MESMO resultado. Se
# a migracao mudasse o comportamento, nao seria migracao.

import pytest

from nucleo import agente, banco, grafo
from nucleo.providers import PedidoFerramenta, RespostaLLM
from nucleo.registro import schemas
from nucleo.resiliencia import executores_seguros

TURNO = {"role": "assistant", "content": []}


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "CAMINHO_BANCO", tmp_path / "grafo.db")
    banco.criar_schema(semear=True)
    from nucleo import ferramentas              # noqa: F401 - registra
    yield


def _roteiro(monkeypatch, respostas, alvo):
    """Troca chat_ferramentas por decisoes pre-escritas no modulo alvo."""
    fila = list(respostas)
    monkeypatch.setattr(alvo, "chat_ferramentas",
                        lambda *a, **k: fila.pop(0))


def _duas_voltas():
    """Consulta o CRM e responde. Dois turnos do modelo."""
    return [
        RespostaLLM("", [PedidoFerramenta(
            "1", "buscar_atualizar_crm", {"email": "carlos@datalog.io"})],
            TURNO, tokens_entrada=1000, tokens_saida=40, modelo="m"),
        RespostaLLM("Carlos esta qualificado.", [], None,
                    tokens_entrada=1300, tokens_saida=20, modelo="m"),
    ]


# ---------- 1. o grafo encadeia e para sozinho ----------

def test_grafo_encadeia_e_para(monkeypatch):
    _roteiro(monkeypatch, _duas_voltas(), grafo)

    exe = grafo.rodar_grafo("O Carlos esta qualificado?",
                            schemas(), executores_seguros())

    assert exe.parou_por == "resposta_final"
    assert exe.iteracoes == 2
    assert "qualificado" in exe.resposta


# ---------- 2. O TESTE DA AULA: grafo e laco dao o mesmo resultado ----------

def test_grafo_equivale_ao_laco_da_fase_0(monkeypatch):
    """Mesma entrada, mesmas decisoes, mesmo resultado.

    Se este teste falhar, a migracao mudou o comportamento, e aí nao e
    migracao: e reescrita.
    """
    _roteiro(monkeypatch, _duas_voltas(), agente)
    pelo_laco = agente.rodar_agente("O Carlos esta qualificado?",
                                    schemas(), executores_seguros(),
                                    verbose=False)

    _roteiro(monkeypatch, _duas_voltas(), grafo)
    pelo_grafo = grafo.rodar_grafo("O Carlos esta qualificado?",
                                   schemas(), executores_seguros())

    assert pelo_grafo.resposta == pelo_laco.resposta
    assert pelo_grafo.iteracoes == pelo_laco.iteracoes
    assert pelo_grafo.parou_por == pelo_laco.parou_por
    assert len(pelo_grafo.historico) == len(pelo_laco.historico)


# ---------- 3. o reducer acumula em vez de substituir ----------

def test_reducer_acumula_o_historico(monkeypatch):
    _roteiro(monkeypatch, _duas_voltas(), grafo)

    exe = grafo.rodar_grafo("?", schemas(), executores_seguros())

    # pergunta + turno do assistant + resultado da ferramenta = 3.
    # Sem o Annotated[list, operator.add], o no `agir` teria
    # SUBSTITUIDO o historico e sobraria so o que ele devolveu.
    assert len(exe.historico) == 3
    assert exe.historico[0]["content"] == "?"


# ---------- 4. o teto de iteracoes continua valendo ----------

def test_limite_de_iteracoes_nao_e_sucesso(monkeypatch):
    sempre = RespostaLLM("", [PedidoFerramenta(
        "x", "buscar_atualizar_crm", {"email": "ana@techflow.com"})],
        TURNO)
    monkeypatch.setattr(grafo, "chat_ferramentas", lambda *a, **k: sempre)

    exe = grafo.rodar_grafo("?", schemas(), executores_seguros(),
                            max_iteracoes=3)

    # recursion_limit do LangGraph e o max_iteracoes da Aula 0.3:
    # mesmo conceito, outro nome.
    assert exe.parou_por == "limite_de_iteracoes"
    assert exe.resposta == ""      # nao mascara falha como resposta


# ---------- 5. a resiliencia da Aula 0.6 atravessou intacta ----------

def test_erro_de_ferramenta_ainda_vira_observacao(monkeypatch):
    _roteiro(monkeypatch, [
        RespostaLLM("", [PedidoFerramenta(
            "1", "abrir_ticket", {"email": "ana@techflow.com",
                                  "assunto": "x", "descricao": "y",
                                  "prioridade": "urgentissima"})],
            TURNO),
        RespostaLLM("", [PedidoFerramenta(
            "2", "abrir_ticket", {"email": "ana@techflow.com",
                                  "assunto": "x", "descricao": "y",
                                  "prioridade": "alta"})], TURNO),
        RespostaLLM("Ticket aberto.", [], None),
    ], grafo)

    exe = grafo.rodar_grafo("Abra um ticket urgente",
                            schemas(), executores_seguros())

    assert exe.parou_por == "resposta_final"
    con = banco.conectar()
    tickets = con.execute("SELECT prioridade FROM tickets").fetchall()
    con.close()
    assert len(tickets) == 1               # o invalido nao gravou
    assert tickets[0]["prioridade"] == "alta"


# ---------- 6. a observabilidade da Aula 0.7 tambem ----------

def test_grafo_continua_rastreado(monkeypatch):
    from nucleo.observabilidade import resumo
    _roteiro(monkeypatch, _duas_voltas(), grafo)

    exe = grafo.rodar_grafo("?", schemas(), executores_seguros())
    r = resumo(exe.trace)

    assert r["chamadas_ao_modelo"] == 2
    assert r["ferramentas_executadas"] == 1
    assert r["tokens_entrada"] == 2300     # as duas voltas somadas


# ---------- 7. o grafo e inspecionavel; o while nao era ----------

def test_estrutura_do_grafo_e_legivel():
    g = grafo.construir_grafo(schemas(), executores_seguros())
    desenho = g.get_graph()

    assert {"decidir", "agir"} <= set(desenho.nodes)
    # O mesmo objeto gera o diagrama da documentacao. Topologia que se
    # desenha e topologia que se discute em revisao de arquitetura.
    assert "decidir" in desenho.draw_mermaid()


# ---------- 8. o gancho da Aula 1.6: o estado sobrevive ----------

def test_estado_sobrevive_com_checkpointer(monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver

    memoria = InMemorySaver()
    g = grafo.construir_grafo(schemas(), executores_seguros(),
                              checkpointer=memoria)
    monkeypatch.setattr(grafo, "chat_ferramentas",
                        lambda *a, **k: RespostaLLM("Oi.", [], None))

    config = {"configurable": {"thread_id": "lead-ana"}}
    grafo.rodar_grafo("oi", schemas(), executores_seguros(),
                      grafo=g, config=config)

    # A execucao terminou, e o estado CONTINUA LA, recuperavel pelo id
    # da conversa. Na Fase 0 isso morria com a variavel local. E esta
    # a porta para persistencia e human-in-the-loop.
    estado = g.get_state(config)
    assert estado.values["iteracoes"] == 1
    assert estado.values["historico"][0]["content"] == "oi"
