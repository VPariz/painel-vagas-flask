"""
gerenciar.py - Interface de Linha de Comando (CLI) para o Painel de Vagas.
Permite consultar rapidamente contatos, vagas, tarefas e fichas técnicas via terminal.
"""

import os
import sys
import argparse
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'painel_vagas.db')


def get_db():
    if not os.path.exists(DB_PATH):
        print(f"Banco de dados não encontrado em '{DB_PATH}'. Inicie 'python app/app.py' primeiro para inicializar o schema.")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def comando_contatos():
    conn = get_db()
    rows = conn.execute('SELECT * FROM pessoas ORDER BY id').fetchall()
    conn.close()
    print("=== CONTATOS & NETWORKING ===")
    for i, r in enumerate(rows, start=1):
        print(f"[{i:02d}] {r['nome']} ({r['empresa']} - {r['cargo']}) | Status: {r['status']} | Prioridade: {r['prioridade']}")


def comando_vagas():
    conn = get_db()
    rows = conn.execute('SELECT * FROM vagas ORDER BY id').fetchall()
    conn.close()
    print("=== PIPELINE DE VAGAS & OPORTUNIDADES ===")
    for r in rows:
        print(f"  - [{r['status']}] {r['empresa']} — {r['cargo']} ({r['local_modalidade']}) | Stack: {r['stack']} | Prazo: {r['deadline'] or 'N/A'}")


def comando_tarefas():
    conn = get_db()
    rows = conn.execute('SELECT * FROM tarefas ORDER BY concluida ASC, data_prazo ASC').fetchall()
    conn.close()
    print("=== TAREFAS & DEADLINES ===")
    for r in rows:
        check = "[X]" if r['concluida'] else "[ ]"
        print(f"  [{check}] ({r['categoria']}) {r['titulo']} | Prioridade: {r['prioridade']} | Prazo: {r['data_prazo'] or 'Sem prazo'}")


def comando_fichas():
    conn = get_db()
    rows = conn.execute('SELECT * FROM fichas ORDER BY id').fetchall()
    conn.close()
    print("=== FICHAS TÉCNICAS DE EMPRESAS ===")
    for r in rows:
        print(f"  [{r['id']}] {r['nome']} ({r['tipo']}) | Stack: {r['stack']}")


def main():
    parser = argparse.ArgumentParser(description="CLI de consulta ao banco SQLite do Painel de Vagas.")
    subparsers = parser.add_subparsers(dest="comando")

    subparsers.add_parser("contatos", help="Lista contatos de networking cadastrados.")
    subparsers.add_parser("vagas", help="Lista pipeline de vagas e oportunidades.")
    subparsers.add_parser("tarefas", help="Lista tarefas e prazos cadastrados.")
    subparsers.add_parser("fichas", help="Lista fichas de contexto de empresas.")

    args = parser.parse_args()

    if args.comando == "contatos":
        comando_contatos()
    elif args.comando == "vagas":
        comando_vagas()
    elif args.comando == "tarefas":
        comando_tarefas()
    elif args.comando == "fichas":
        comando_fichas()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
