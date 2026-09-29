"""Aula 0.5 - O CRM mockado do FlowDesk, em SQLite.

Por que SQLite: zero dependencia, roda em qualquer maquina, e e
substituivel. Na Fase 4, trocar por Postgres e reescrever ESTE arquivo,
nao as ferramentas. A fronteira entre dados e capacidade fica aqui.
"""

import sqlite3
from pathlib import Path

# O caminho do banco e uma variavel de MODULO, nao uma constante
# enterrada nas funcoes. E isso que permite os testes apontarem para um
# banco temporario com monkeypatch, sem tocar no seu banco de trabalho.
CAMINHO_BANCO = Path("flowdesk.db")


def conectar():
    """Abre conexao com o banco, devolvendo linhas acessiveis por nome."""
    con = sqlite3.connect(CAMINHO_BANCO)
    # row_factory: cursor devolve objetos indexaveis por nome de coluna
    # (linha["email"]) em vez de tuplas posicionais. Codigo mais legivel.
    con.row_factory = sqlite3.Row
    return con


def criar_schema(semear=True):
    """Cria as tres tabelas e, por padrao, popula com dados de exemplo.

    Idempotente: pode rodar varias vezes sem quebrar.
    """
    con = conectar()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            email    TEXT PRIMARY KEY,
            nome     TEXT NOT NULL,
            empresa  TEXT NOT NULL,
            plano    TEXT NOT NULL,   -- trial | pro | enterprise
            mrr      INTEGER NOT NULL DEFAULT 0,
            status   TEXT NOT NULL DEFAULT 'novo',
            notas    TEXT DEFAULT ''
        )""")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reunioes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email_lead  TEXT NOT NULL,
            data        TEXT NOT NULL,   -- AAAA-MM-DD
            horario     TEXT NOT NULL,   -- HH:MM
            assunto     TEXT NOT NULL,
            FOREIGN KEY (email_lead) REFERENCES leads (email)
        )""")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email_lead  TEXT NOT NULL,
            assunto     TEXT NOT NULL,
            descricao   TEXT NOT NULL,
            prioridade  TEXT NOT NULL,   -- baixa | media | alta
            status      TEXT NOT NULL DEFAULT 'aberto',
            FOREIGN KEY (email_lead) REFERENCES leads (email)
        )""")

    if semear:
        # INSERT OR IGNORE: rodar de novo nao duplica nem explode.
        cur.executemany(
            "INSERT OR IGNORE INTO leads "
            "(email, nome, empresa, plano, mrr, status, notas) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("ana@techflow.com", "Ana Prado", "TechFlow",
                 "trial", 0, "novo", ""),
                ("carlos@datalog.io", "Carlos Nunes", "DataLog",
                 "pro", 490, "qualificado", "Pediu proposta em janeiro."),
                ("bia@scalelab.com", "BiaRocha", "ScaleLab",
                 "enterprise", 2400, "cliente", ""),
            ])

    con.commit()
    con.close()
