# Aula 0.6 - Testes de resiliencia e saida estruturada.
#
# Nenhuma chamada de API. O que esta sob teste e a nossa logica: o
# erro virando observacao, o contrato validando, e o ciclo de
# correcao quando o modelo erra o formato.

import pytest

from nucleo import banco, estruturado, ferramentas
from nucleo.modelos import QualificacaoLead
from nucleo.resiliencia import (ErroIrrecuperavel, executores_seguros,
                                proteger)


@pytest.fixture(autouse=True)
def banco_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "CAMINHO_BANCO", tmp_path / "teste.db")
    banco.criar_schema(semear=True)
    yield


# ---------- 1. valor fora do enum vira observacao, nao excecao ----------

def test_valor_fora_do_enum_vira_texto():
    ex = executores_seguros()
    saida = ex["abrir_ticket"](email="ana@techflow.com", assunto="x",
                               descricao="y", prioridade="urgentissima")
    assert isinstance(saida, str)
    assert "ERRO DE ARGUMENTO" in saida
    # O texto precisa dizer O QUE corrigir, senao o modelo repete o erro.
    assert "prioridade" in saida
    assert "baixa" in saida


# ---------- 2. argumento faltando tambem vira observacao ----------

def test_argumento_faltando_vira_texto():
    ex = executores_seguros()
    saida = ex["agendar_reuniao"](email="ana@techflow.com",
                                  data="2026-10-02")
    assert "ERRO DE ARGUMENTO" in saida
    assert "horario" in saida


# ---------- 3. argumento inventado nao quebra o laco ----------

def test_argumento_inventado_nao_levanta():
    ex = executores_seguros()
    saida = ex["buscar_atualizar_crm"](email="ana@techflow.com",
                                       campo_que_nao_existe=1)
    assert isinstance(saida, str)
    assert "ERRO DE ARGUMENTO" in saida


# ---------- 4. ferramenta que quebra sozinha vira observacao ----------

def test_excecao_da_ferramenta_vira_texto():
    def ferramenta_quebrada(x: int) -> str:
        """Quebra de proposito."""
        raise RuntimeError("banco indisponivel")

    saida = proteger(ferramenta_quebrada)(x=1)
    assert "ERRO NA FERRAMENTA" in saida
    assert "banco indisponivel" in saida


# ---------- 5. erro irrecuperavel SOBE, nao vira observacao ----------

def test_erro_irrecuperavel_sobe():
    def ferramenta_sem_credencial(x: int) -> str:
        """Simula credencial expirada."""
        raise ErroIrrecuperavel("chave de API expirada")

    with pytest.raises(ErroIrrecuperavel):
        proteger(ferramenta_sem_credencial)(x=1)
    # O agente nao contorna isso. Insistir so queimaria token.


# ---------- 6. o caminho feliz continua igual ----------

def test_chamada_valida_passa_intacta():
    ex = executores_seguros()
    saida = ex["buscar_atualizar_crm"](email="carlos@datalog.io")
    assert "Carlos Nunes" in saida


# ---------- 7. o contrato rejeita o que viola as regras ----------

def test_contrato_rejeita_pontuacao_invalida():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        QualificacaoLead(email="a@b.c", status="qualificado",
                         pontuacao=150, justificativa="x",
                         proxima_acao="y")


def test_contrato_rejeita_status_fora_do_literal():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        QualificacaoLead(email="a@b.c", status="talvez", pontuacao=50,
                         justificativa="x", proxima_acao="y")


# ---------- 8. extracao bem-sucedida na primeira tentativa ----------

VALIDO = ('{"email": "carlos@datalog.io", "status": "qualificado", '
          '"pontuacao": 85, "justificativa": "Plano pro", '
          '"proxima_acao": "Agendar demo"}')


def test_extrai_na_primeira(monkeypatch):
    chamadas = {"n": 0}

    def fake_chat(provider, mensagens, system=None, max_tokens=1024):
        chamadas["n"] += 1
        return VALIDO

    monkeypatch.setattr(estruturado, "chat", fake_chat)
    obj = estruturado.extrair_estruturado("relato", QualificacaoLead)

    assert obj.pontuacao == 85
    assert obj.status == "qualificado"
    assert chamadas["n"] == 1


# ---------- 9. modelo erra, recebe o erro e corrige ----------

def test_corrige_na_segunda_tentativa(monkeypatch):
    respostas = [
        # Primeira: pontuacao fora da faixa e cercado de markdown.
        '```json\n{"email": "c@d.io", "status": "qualificado", '
        '"pontuacao": 150, "justificativa": "x", "proxima_acao": "y"}\n```',
        VALIDO,
    ]
    enviadas = []

    def fake_chat(provider, mensagens, system=None, max_tokens=1024):
        enviadas.append(list(mensagens))
        return respostas.pop(0)

    monkeypatch.setattr(estruturado, "chat", fake_chat)
    obj = estruturado.extrair_estruturado("relato", QualificacaoLead)

    assert obj.pontuacao == 85
    # Na segunda chamada, o historico levou o erro de volta ao modelo.
    texto_segunda = str(enviadas[1])
    assert "nao passou na validacao" in texto_segunda


# ---------- 10. esgotar tentativas falha alto ----------

def test_esgota_tentativas_e_levanta(monkeypatch):
    monkeypatch.setattr(estruturado, "chat",
                        lambda *a, **k: '{"nada": "aqui"}')
    with pytest.raises(ValueError):
        estruturado.extrair_estruturado("relato", QualificacaoLead)
    # Devolver um objeto meia-boca seria pior do que falhar.
