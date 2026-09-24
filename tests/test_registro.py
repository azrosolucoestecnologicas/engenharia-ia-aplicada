# Aula 0.4 - Testes do registro de ferramentas.
#
# Tudo aqui e deterministico: nenhum LLM, nenhuma rede. O que esta sob
# teste e a geracao de schema a partir da funcao e a execucao pelo nome.

import pytest

from nucleo import registro
from nucleo.registro import ferramenta, schemas_para, executar_ferramenta


@pytest.fixture(autouse=True)
def registro_limpo():
    """O REGISTRO e um dict de MODULO: ferramentas registradas num
    teste vazariam para o seguinte. Salvamos e restauramos o estado.
    Padrao que vale sempre que houver estado global."""
    original = dict(registro.REGISTRO)
    registro.REGISTRO.clear()
    yield
    registro.REGISTRO.clear()
    registro.REGISTRO.update(original)


def _exemplo():
    @ferramenta
    def buscar_lead(email: str, limite: int = 5) -> dict:
        """Busca um lead pelo email. Use antes de agir sobre o lead."""
        return {"email": email, "limite": limite}
    return buscar_lead


# ---------- 1. o decorator nao modifica a funcao ----------

def test_decorator_devolve_funcao_original():
    f = _exemplo()
    # Continua sendo Python comum: chamavel direto, sem o agente.
    assert f("ana@x.io") == {"email": "ana@x.io", "limite": 5}
    assert f.__name__ == "buscar_lead"


# ---------- 2. o contrato e derivado da assinatura ----------

def test_obrigatorio_vem_de_parametro_sem_default():
    _exemplo()
    f = registro.REGISTRO["buscar_lead"]
    assert f.propriedades == {"email": {"type": "string"},
                              "limite": {"type": "integer"}}
    assert f.obrigatorios == ["email"]      # limite tem default
    assert "Busca um lead pelo email" in f.descricao


# ---------- 3 e 4. os dois dialetos, do mesmo contrato ----------

def test_schema_anthropic():
    _exemplo()
    s = schemas_para("anthropic")[0]
    assert s["name"] == "buscar_lead"
    assert s["input_schema"]["required"] == ["email"]
    assert "function" not in s              # sem envelope na Anthropic


def test_schema_openai():
    _exemplo()
    s = schemas_para("openai")[0]
    assert s["type"] == "function"
    assert s["function"]["name"] == "buscar_lead"
    # O miolo e IDENTICO ao da Anthropic: so a embalagem muda.
    assert s["function"]["parameters"] == \
        schemas_para("anthropic")[0]["input_schema"]


# ---------- 5. execucao pelo nome ----------

def test_executar_ferramenta_pelo_nome():
    _exemplo()
    assert executar_ferramenta("buscar_lead", {"email": "ana@x.io"}) == \
        {"email": "ana@x.io", "limite": 5}


# ---------- 6. ferramenta desconhecida vira observacao ----------

def test_ferramenta_desconhecida_nao_levanta():
    saida = executar_ferramenta("fantasma", {})
    assert "erro" in saida                  # o agente le e contorna


# ---------- 7 e 8. contratos incompletos falham alto, no registro ----------

def test_parametro_sem_type_hint_falha():
    with pytest.raises(TypeError):
        @ferramenta
        def sem_tipo(email):
            """Tem docstring, mas falta o type hint."""


def test_ferramenta_sem_docstring_falha():
    with pytest.raises(ValueError):
        @ferramenta
        def sem_doc(email: str):
            pass


# ---------- 9. o registro alimenta o laco da Aula 0.3 ----------

def test_schemas_e_executores_no_formato_do_laco():
    _exemplo()
    fer = registro.schemas()
    exe = registro.executores()
    # Exatamente o formato que rodar_agente ja espera desde a 0.3.
    assert set(fer) == {"anthropic", "openai"}
    assert callable(exe["buscar_lead"])
    assert "buscar_lead" in {s["name"] for s in fer["anthropic"]}


# ---------- 10. provider desconhecido falha alto ----------

def test_provider_desconhecido():
    with pytest.raises(ValueError):
        schemas_para("gemini")
