"""Aula 0.5 - As tres ferramentas reais do dominio (FlowDesk).

A regra de arquitetura desta aula:

    A REGRA DE NEGOCIO MORA NO PROMPT. A CAPACIDADE MORA NA FERRAMENTA.

abrir_ticket nao decide QUANDO um ticket deve ser aberto: ela sabe
abrir. Quem decide e o agente, orientado pela instrucao de sistema.
Misturar as duas coisas produz ferramentas que so servem para um
cliente, e o Nucleo precisa ser replicavel.

Cada docstring aqui e PROMPT: o resumo diz quando usar a ferramenta, e
o bloco Args descreve cada argumento. Os dois textos entram no schema
e sao o que o modelo le para decidir.
"""

from typing import Literal

from nucleo.banco import conectar
from nucleo.registro import ferramenta


@ferramenta
def buscar_atualizar_crm(email: str, status: str = "",
                         notas: str = "") -> str:
    """Consulta um lead no CRM pelo email e, opcionalmente, atualiza.

    Use SEMPRE antes de qualquer outra acao sobre o lead, para
    confirmar que ele existe e conhecer plano, MRR e status. Se status
    ou notas forem informados, o cadastro e atualizado; se nao, a
    ferramenta apenas consulta.

    Args:
        email: Email do lead, ex: nome@empresa.com
        status: Novo status do lead. Deixe vazio para apenas consultar.
        notas: Observacao a acrescentar ao cadastro. Vazio nao altera.
    """
    con = conectar()
    cur = con.cursor()

    linha = cur.execute(
        "SELECT * FROM leads WHERE email = ?", (email,)).fetchone()

    if linha is None:
        con.close()
        # Texto, nao codigo de erro: quem le isto e o modelo.
        return f"Lead nao encontrado no CRM: {email}"

    alteracoes = []
    if status:
        cur.execute("UPDATE leads SET status = ? WHERE email = ?",
                    (status, email))
        alteracoes.append(f"status agora e '{status}'")
    if notas:
        cur.execute("UPDATE leads SET notas = ? WHERE email = ?",
                    (notas, email))
        alteracoes.append("notas atualizadas")

    if alteracoes:
        con.commit()
        linha = cur.execute(
            "SELECT * FROM leads WHERE email = ?", (email,)).fetchone()
    con.close()

    # Resultado RICO: o modelo compoe a resposta a partir deste texto.
    # Um {"ok": true} nao ajudaria ninguem.
    texto = (f"{linha['nome']} ({linha['empresa']}), plano "
             f"{linha['plano']}, MRR {linha['mrr']}, status "
             f"{linha['status']}.")
    if linha["notas"]:
        texto += f" Notas: {linha['notas']}"
    if alteracoes:
        texto += " Atualizado: " + ", ".join(alteracoes) + "."
    return texto


@ferramenta
def agendar_reuniao(email: str, data: str, horario: str,
                    assunto: str) -> str:
    """Agenda uma reuniao com um lead na agenda comercial.

    Use quando o lead demonstrar interesse em conversar, pedir demo ou
    proposta. Confirme antes que o lead existe no CRM.

    Args:
        email: Email do lead com quem sera a reuniao
        data: Data no formato AAAA-MM-DD, ex: 2026-08-14
        horario: Horario no formato HH:MM, 24 horas, ex: 10:30
        assunto: Pauta da reuniao, em uma frase
    """
    con = conectar()
    cur = con.cursor()

    lead = cur.execute(
        "SELECT nome FROM leads WHERE email = ?", (email,)).fetchone()
    if lead is None:
        con.close()
        return (f"Nao foi possivel agendar: o lead {email} nao existe "
                "no CRM. Verifique o email.")

    # Conflito de horario e regra da CAPACIDADE (a agenda nao comporta
    # dois compromissos no mesmo slot), nao regra de negocio comercial.
    ocupado = cur.execute(
        "SELECT 1 FROM reunioes WHERE data = ? AND horario = ?",
        (data, horario)).fetchone()
    if ocupado:
        con.close()
        return (f"Horario indisponivel: ja existe reuniao em {data} as "
                f"{horario}. Sugira outro horario ao lead.")

    cur.execute(
        "INSERT INTO reunioes (email_lead, data, horario, assunto) "
        "VALUES (?, ?, ?, ?)", (email, data, horario, assunto))
    con.commit()
    con.close()

    return (f"Reuniao agendada com {lead['nome']} em {data} as "
            f"{horario}. Pauta: {assunto}.")


@ferramenta
def abrir_ticket(email: str, assunto: str, descricao: str,
                 prioridade: Literal["baixa", "media", "alta"]) -> str:
    """Abre um chamado de suporte tecnico para um lead ou cliente.

    Use quando o lead relatar problema, erro ou indisponibilidade no
    produto. Nao use para duvidas comerciais ou pedidos de proposta.

    Args:
        email: Email de quem relatou o problema
        assunto: Titulo curto do chamado
        descricao: O problema relatado, com os detalhes disponiveis
        prioridade: Urgencia do chamado
    """
    con = conectar()
    cur = con.cursor()

    if cur.execute("SELECT 1 FROM leads WHERE email = ?",
                   (email,)).fetchone() is None:
        con.close()
        return f"Nao foi possivel abrir o ticket: {email} nao esta no CRM."

    cur.execute(
        "INSERT INTO tickets (email_lead, assunto, descricao, prioridade) "
        "VALUES (?, ?, ?, ?)", (email, assunto, descricao, prioridade))
    con.commit()
    numero = cur.lastrowid
    con.close()

    return (f"Ticket #{numero} aberto para {email}, prioridade "
            f"{prioridade}. Assunto: {assunto}.")
