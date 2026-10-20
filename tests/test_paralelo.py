# Aula 1.3 - Testes de parallelization e orchestrator-workers.
#
# Nenhuma chamada de API. O que nos interessa provar aqui nao e o texto
# que o modelo devolve, e sim o COMPORTAMENTO DA TOPOLOGIA:
#
#   1. as tres analises rodam DE FATO ao mesmo tempo (teste de tempo)
#   2. nenhum resultado se perde no merge (o bug do reducer errado)
#   3. o numero de workers vem do modelo, nao do codigo
#   4. um worker que falha nao derruba os outros
#   5. puro e grafo dao o mesmo resultado

import json
import time

import pytest

from nucleo import banco, estruturado, grafo_paralelo, paralelo
from nucleo.observabilidade import resumo
from nucleo.paralelo import Subtarefa

PLANO_TRES = {"subtarefas": [
    {"tipo": "comercial", "pedido": "quer migrar para o plano Pro"},
    {"tipo": "suporte", "pedido": "erro 500 ao exportar relatorio"},
    {"tipo": "agenda", "pedido": "remarcar a call de quinta"},
]}

PLANO_UM = {"subtarefas": [
    {"tipo": "suporte", "pedido": "erro 500 ao exportar relatorio"},
]}

WORKERS = {
    "comercial": lambda s: f"[vendas] {s.pedido}",
    "suporte": lambda s: f"[suporte] {s.pedido}",
    "agenda": lambda s: f"[agenda] {s.pedido}",
}


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "CAMINHO_BANCO", tmp_path / "paralelo.db")
    banco.criar_schema(semear=True)
    yield


def _modelo(monkeypatch, plano=None, sintese="Resposta unificada."):
    """Fixa o modelo nos dois pontos: decomposicao e sintese/analise."""
    dados = json.dumps(plano or PLANO_TRES)
    monkeypatch.setattr(estruturado, "chat", lambda *a, **k: dados)
    monkeypatch.setattr(paralelo, "chat", lambda *a, **k: sintese)


# ---------- 1. O TESTE DA AULA: as analises rodam ao mesmo tempo ----------

def test_paralelizacao_e_mais_rapida_que_a_soma(monkeypatch):
    """Tres chamadas de 200ms levam ~200ms, nao 600ms.

    Este e o unico teste do curso que mede TEMPO, e ele existe porque
    o ganho do padrao e temporal: nao da para provar paralelismo
    olhando so o resultado, que e identico ao da versao sequencial.

    A margem e generosa (400ms) de proposito: teste de tempo em CI
    compartilhada falha por ruido, nao por regressao.
    """
    def lento(*a, **k):
        time.sleep(0.2)
        return "ok"

    monkeypatch.setattr(paralelo, "chat", lento)

    inicio = time.perf_counter()
    saida = paralelo.analisar_em_paralelo("mensagem qualquer")
    gasto = time.perf_counter() - inicio

    assert len(saida) == 3
    assert gasto < 0.4          # sequencial seria >= 0.6
    # Repare no que NAO melhorou: continuam sendo tres chamadas, e voce
    # paga pelas tres. Paralelizar troca latencia, nao custo.


# ---------- 2. nenhum resultado se perde no merge ----------

def test_as_tres_analises_aparecem_nas_duas_versoes(monkeypatch):
    monkeypatch.setattr(paralelo, "chat",
                        lambda provider, msgs, system=None: f"r:{system[:3]}")

    puro = paralelo.analisar_em_paralelo("mensagem")
    grafo = grafo_paralelo.rodar_analise("mensagem")

    assert set(puro) == {"tom", "urgencia", "oportunidade"}
    assert puro == grafo
    # Se o reducer do estado fosse o default (sobrescrever em vez de
    # juntar), este teste pegaria so UMA chave aqui. E o resultado
    # pareceria plausivel: so faltaria coisa. Bug de fan-out e assim.


# ---------- 3. o numero de workers vem do MODELO ----------

@pytest.mark.parametrize("plano,esperado", [(PLANO_TRES, 3), (PLANO_UM, 1)])
def test_quantidade_de_workers_segue_o_plano(monkeypatch, plano, esperado):
    """A marca do padrao: o mesmo codigo roda 1 ou 3 workers.

    Nenhuma linha do nosso codigo decide esse numero. Ele sai do
    modelo. E por isso que nao da para desenhar este grafo de
    antemao, e e por isso que a Send API existe.
    """
    _modelo(monkeypatch, plano)
    _, _, resultados = paralelo.orquestrar("mensagem", WORKERS)
    assert len(resultados) == esperado

    _modelo(monkeypatch, plano)
    _, res_grafo = grafo_paralelo.rodar_orquestrador("mensagem", WORKERS)
    assert len(res_grafo) == esperado


# ---------- 4. puro e grafo dao o mesmo resultado ----------

def test_orquestrador_puro_equivale_ao_grafo(monkeypatch):
    _modelo(monkeypatch)
    r_puro, _, res_puro = paralelo.orquestrar("mensagem", WORKERS)

    _modelo(monkeypatch)
    r_grafo, res_grafo = grafo_paralelo.rodar_orquestrador(
        "mensagem", WORKERS)

    assert r_puro == r_grafo == "Resposta unificada."
    # A ordem do fan-out nao e garantida nas duas versoes: comparamos
    # como conjunto. Depender da ordem de chegada de workers paralelos
    # e um bug esperando acontecer.
    assert sorted(res_puro) == sorted(res_grafo)


# ---------- 5. um worker que falha nao derruba os outros ----------

def test_worker_que_falha_nao_derruba_o_fan_out(monkeypatch):
    """Resiliencia da Aula 0.6, agora num fan-out.

    Aqui ela pesa mais: as outras partes podem ter dado certo, e jogar
    tudo fora por causa de uma seria desperdicio.
    """
    def explode(s):
        raise RuntimeError("API do CRM fora")

    workers = dict(WORKERS, suporte=explode)
    _modelo(monkeypatch)

    _, _, resultados = paralelo.orquestrar("mensagem", workers)
    por_tipo = dict(resultados)

    assert len(resultados) == 3
    assert "falhou" in por_tipo["suporte"]
    assert "RuntimeError" in por_tipo["suporte"]
    # As duas que deram certo continuam la, e a sintese recebe as tres,
    # inclusive a que falhou: o modelo pode avisar o cliente de que
    # aquela parte ficou pendente.
    assert por_tipo["comercial"].startswith("[vendas]")
    assert por_tipo["agenda"].startswith("[agenda]")


# ---------- 6. tipo sem worker registrado tambem nao derruba ----------

def test_tipo_sem_worker_vira_observacao(monkeypatch):
    _modelo(monkeypatch, PLANO_UM)
    _, _, resultados = paralelo.orquestrar("mensagem", {})   # nenhum worker
    assert "sem worker" in resultados[0][1]
    # Diferente do router da Aula 1.2, que levantava ValueError. A
    # diferenca e proposital: no router, a rota e UMA e sem ela nao ha
    # resposta. No fan-out, as outras partes seguem.


# ---------- 7. plano vazio nao chama sintese ----------

def test_plano_vazio_nao_sintetiza(monkeypatch):
    chamou = []
    monkeypatch.setattr(estruturado, "chat",
                        lambda *a, **k: json.dumps({"subtarefas": []}))
    monkeypatch.setattr(paralelo, "chat",
                        lambda *a, **k: chamou.append(1) or "nao deveria")

    resposta, _, resultados = paralelo.orquestrar("oi", WORKERS)

    assert resultados == []
    assert chamou == []          # nada a sintetizar, nada a pagar
    assert "detalhar" in resposta

    # No grafo, o mesmo caso desvia para o sintetizador sem passar por
    # worker nenhum: o `return "sintetizar"` da funcao de distribuicao.
    monkeypatch.setattr(estruturado, "chat",
                        lambda *a, **k: json.dumps({"subtarefas": []}))
    r_grafo, res_grafo = grafo_paralelo.rodar_orquestrador("oi", WORKERS)
    assert res_grafo == []
    assert "detalhar" in r_grafo


# ---------- 8. a Send cria N instancias de UM no declarado ----------

def test_send_instancia_o_mesmo_no_varias_vezes(monkeypatch):
    """O grafo tem UM no worker. Tres subtarefas = tres execucoes dele.

    Contamos as execucoes para provar que a instanciacao e dinamica.
    Um grafo estatico com tres nos nao conseguiria atender a um plano
    de cinco itens; este consegue.
    """
    execucoes = []

    def espiao(s):
        execucoes.append(s.tipo)
        return f"[{s.tipo}] ok"

    workers = {t: espiao for t in ("comercial", "suporte", "agenda")}
    _modelo(monkeypatch)

    grafo_paralelo.rodar_orquestrador("mensagem", workers)
    assert sorted(execucoes) == ["agenda", "comercial", "suporte"]


# ---------- 9. o fan-out inteiro aparece num trace so ----------

def test_fan_out_aparece_no_trace(monkeypatch):
    _modelo(monkeypatch)

    import nucleo.observabilidade as obs
    from contextlib import contextmanager

    capturado = {}
    original = obs.iniciar_trace

    @contextmanager
    def espiao(nome, entrada=None):
        with original(nome, entrada=entrada) as raiz:
            capturado["raiz"] = raiz
            yield raiz

    monkeypatch.setattr(paralelo, "iniciar_trace", espiao)
    paralelo.orquestrar("mensagem", WORKERS)

    raiz = capturado["raiz"]
    nomes = sorted(f.nome for f in raiz.filhos)
    assert nomes == ["decompor", "sintetizar", "worker:agenda",
                     "worker:comercial", "worker:suporte"]
    # Os cinco passos num trace so, mesmo tendo rodado em threads
    # diferentes. Se os workers aparecessem em traces separados, voce
    # perderia justamente a visao do conjunto, que e o que interessa
    # num fan-out.
    assert resumo(raiz)["chamadas_ao_modelo"] == 2   # decompor + sintetizar


# ---------- 10. a regressao do tracer: thread nao perde o trace ----------

def test_span_dentro_de_thread_entra_na_arvore():
    """O bug que esta aula descobriu, virado teste.

    Ate a Aula 1.2 o tracer guardava uma pilha mutavel num ContextVar.
    Funcionou enquanto tudo era sequencial. Numa thread, o observar()
    virava no-op e o trace ficava com um buraco: resultado certo,
    observabilidade mentindo.

    Sem o em_thread(), este teste falha. Com ele, passa. E e por isso
    que ele existe: bug silencioso so nao volta se tiver teste.
    """
    from concurrent.futures import ThreadPoolExecutor

    from nucleo.observabilidade import em_thread, iniciar_trace, observar

    def trabalho(nome):
        with observar(nome) as sp:
            return sp is not None

    with iniciar_trace("fan_out") as raiz:
        with ThreadPoolExecutor(2) as ex:
            futuros = [ex.submit(em_thread(trabalho, f"t{i}"))
                       for i in range(2)]
            criados = [f.result() for f in futuros]

    assert all(criados)
    assert sorted(f.nome for f in raiz.filhos) == ["t0", "t1"]
    # Os dois sao filhos da RAIZ, nao um filho do outro. Com a pilha
    # compartilhada da versao antiga, o aninhamento virava sorteio.


def test_grafo_preserva_o_trace_sem_ajuda_nenhuma(monkeypatch):
    """O mesmo fan-out em grafo: nenhum em_thread, e funciona.

    O LangGraph copia o contexto para os nos paralelos por conta
    propria. Este teste mede, em codigo, uma coisa concreta que o
    framework resolve para voce. Tenha isso em mente ao decidir entre
    puro e grafo: nao e so topologia.
    """
    monkeypatch.setattr(paralelo, "chat", lambda *a, **k: "ok")

    import nucleo.observabilidade as obs
    from contextlib import contextmanager

    capturado = {}
    original = obs.iniciar_trace

    @contextmanager
    def espiao(nome, entrada=None):
        with original(nome, entrada=entrada) as raiz:
            capturado["raiz"] = raiz
            yield raiz

    monkeypatch.setattr(grafo_paralelo, "iniciar_trace", espiao)
    grafo_paralelo.rodar_analise("mensagem")

    nomes = sorted(f.nome for f in capturado["raiz"].filhos)
    assert nomes == ["oportunidade", "tom", "urgencia"]


# ---------- 11. o contrato limita o que o modelo pode inventar ----------

def test_tipo_fora_do_literal_e_rejeitado():
    """O Literal da Subtarefa e a cerca do orquestrador.

    Sem ele, o modelo inventaria tipos ("financeiro", "juridico") e o
    fan-out mandaria trabalho para workers que nao existem. A regra da
    Aula 0.5 vale aqui tambem: contrato primeiro.
    """
    from pydantic import ValidationError

    Subtarefa(tipo="suporte", pedido="erro 500")       # ok
    with pytest.raises(ValidationError):
        Subtarefa(tipo="financeiro", pedido="segunda via")
