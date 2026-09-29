# Aula 0.5 - Testes das tres ferramentas do dominio.
#
# Nenhum LLM, nenhuma rede. Ferramenta e Python comum (o decorator nao
# a modifica), entao chamamos direto e conferimos o efeito no SQLite.
#
# Cada teste roda contra um banco TEMPORARIO, criado pela fixture. O
# banco de trabalho nunca e tocado.

import pytest

from nucleo import banco, ferramentas
from nucleo.registro import schemas_para


@pytest.fixture(autouse=True)
def banco_temporario(tmp_path, monkeypatch):
    """Aponta CAMINHO_BANCO para um arquivo novo a cada teste.

    tmp_path e uma pasta temporaria por teste, do proprio pytest.
    monkeypatch desfaz a troca no fim. E por isso que o caminho do
    banco e variavel de modulo, e nao constante dentro das funcoes.
    """
    monkeypatch.setattr(banco, "CAMINHO_BANCO", tmp_path / "teste.db")
    banco.criar_schema(semear=True)
    yield


# ---------- 1. consulta devolve texto rico, nao codigo de status ----------

def test_buscar_devolve_dados_legiveis():
    saida = ferramentas.buscar_atualizar_crm("carlos@datalog.io")
    assert "Carlos Nunes" in saida
    assert "DataLog" in saida
    assert "490" in saida          # MRR: o modelo precisa ver o numero


# ---------- 2. a mesma ferramenta atualiza quando recebe status ----------

def test_atualizar_status_persiste():
    ferramentas.buscar_atualizar_crm("ana@techflow.com",
                                     status="qualificado")
    depois = ferramentas.buscar_atualizar_crm("ana@techflow.com")
    assert "qualificado" in depois


# ---------- 3. lead inexistente vira observacao, nao excecao ----------

def test_lead_inexistente_nao_levanta():
    saida = ferramentas.buscar_atualizar_crm("ninguem@lugar.com")
    assert "nao encontrado" in saida.lower()   # o agente le e contorna


# ---------- 4. agendamento grava e informa ----------

def test_agendar_reuniao_grava():
    saida = ferramentas.agendar_reuniao(
        "carlos@datalog.io", "2026-08-14", "10:30", "Demo do produto")
    assert "agendada" in saida.lower()

    con = banco.conectar()
    linha = con.execute("SELECT * FROM reunioes").fetchone()
    con.close()
    assert linha["data"] == "2026-08-14"
    assert linha["email_lead"] == "carlos@datalog.io"


# ---------- 5. conflito de horario orienta o proximo passo ----------

def test_horario_ocupado_sugere_alternativa():
    ferramentas.agendar_reuniao(
        "carlos@datalog.io", "2026-08-14", "10:30", "Demo")
    saida = ferramentas.agendar_reuniao(
        "bia@scalelab.com", "2026-08-14", "10:30", "Renovacao")

    assert "indisponivel" in saida.lower()
    # O texto precisa DIZER o que fazer: e assim que o agente se
    # recupera sozinho, em vez de repetir a mesma chamada.
    assert "outro horario" in saida.lower()


# ---------- 6. ticket numerado, para o agente informar ao lead ----------

def test_abrir_ticket_devolve_numero():
    saida = ferramentas.abrir_ticket(
        "ana@techflow.com", "Erro no login",
        "Erro 500 ao entrar pelo SSO", "alta")
    assert "#1" in saida
    assert "alta" in saida


# ---------- 7. o enum chega ao schema (regra: fechar o vocabulario) ----------

def test_prioridade_e_enum_no_schema():
    esquema = {s["name"]: s for s in schemas_para("anthropic")}
    prio = esquema["abrir_ticket"]["input_schema"]["properties"]["prioridade"]
    assert prio["enum"] == ["baixa", "media", "alta"]
    # Sem enum, o modelo inventaria "urgentissima" e a validacao
    # quebraria so na hora de gravar.


# ---------- 8. a descricao de cada parametro chega ao schema ----------

def test_descricao_de_parametro_no_schema():
    esquema = {s["name"]: s for s in schemas_para("anthropic")}
    props = esquema["agendar_reuniao"]["input_schema"]["properties"]
    assert "AAAA-MM-DD" in props["data"]["description"]
    # O formato da data vive no PROMPT do schema. Sem isso, o modelo
    # manda "14 de agosto" e a ferramenta grava lixo.


# ---------- 9. as tres ferramentas estao registradas nos dois dialetos ----------

def test_tres_ferramentas_nos_dois_dialetos():
    nomes_ant = {s["name"] for s in schemas_para("anthropic")}
    nomes_oai = {s["function"]["name"] for s in schemas_para("openai")}
    esperadas = {"buscar_atualizar_crm", "agendar_reuniao", "abrir_ticket"}
    assert esperadas <= nomes_ant
    assert esperadas <= nomes_oai


# ---------- 10. parametro opcional nao entra em required ----------

def test_opcionais_fora_de_required():
    esquema = {s["name"]: s for s in schemas_para("anthropic")}
    req = esquema["buscar_atualizar_crm"]["input_schema"]["required"]
    assert req == ["email"]        # status e notas tem default
