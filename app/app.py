"""
app.py - Servidor Principal do Painel de Vagas & Processos Seletivos.
Arquitetura modular com Flask, SQLite3, autenticação PBKDF2-SHA256,
exportação iCalendar (RFC 5545) e sincronização OAuth 2.0 com Google Calendar.
"""

import sys
sys.dont_write_bytecode = True
import os
import json
import sqlite3
import secrets
import urllib.request
from datetime import datetime, date, timedelta
from flask import Flask, render_template, jsonify, request, Response, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

import calendario
import google_sync

app = Flask(__name__)

# ═══════════════════════════════════════════════════════
# CONFIGURAÇÃO DE SEGURANÇA, SESSÃO E VARIÁVEIS DE AMBIENTE
# ═══════════════════════════════════════════════════════
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'painel_vagas.db')
SECRET_KEY_FILE = os.path.join(DATA_DIR, '.secret_key')
AUTH_CONFIG_FILE = os.path.join(DATA_DIR, 'auth_config.json')


def init_security_config():
    """Inicializa chave secreta de sessão e hash PBKDF2 do PIN de acesso."""
    os.makedirs(DATA_DIR, exist_ok=True)

    env_secret = os.environ.get('FLASK_SECRET_KEY')
    if env_secret:
        secret_key = env_secret
    elif os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, 'r', encoding='utf-8') as f:
            secret_key = f.read().strip()
    else:
        secret_key = secrets.token_hex(32)
        with open(SECRET_KEY_FILE, 'w', encoding='utf-8') as f:
            f.write(secret_key)

    default_pin = os.environ.get('CRM_DEFAULT_PIN', '1234')
    if os.path.exists(AUTH_CONFIG_FILE):
        try:
            with open(AUTH_CONFIG_FILE, 'r', encoding='utf-8') as f:
                auth_cfg = json.load(f)
        except Exception:
            auth_cfg = {}
    else:
        auth_cfg = {}

    if 'pin_hash' not in auth_cfg:
        auth_cfg = {
            'pin_hash': generate_password_hash(default_pin, method='pbkdf2:sha256'),
            'allow_lan': os.environ.get('CRM_ALLOW_LAN', 'false').lower() == 'true',
            'updated_at': datetime.now().isoformat()
        }
        with open(AUTH_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(auth_cfg, f, indent=2)

    return secret_key, auth_cfg


app.secret_key, AUTH_CONFIG = init_security_config()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=30)
)

FAILED_LOGINS = {}  # { ip: {'count': int, 'lock_until': datetime} }


def get_db():
    """Retorna conexão SQLite com suporte a dicionários via sqlite3.Row."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db_schema():
    """Cria as tabelas relacionais e popula dados de demonstração neutros se o banco estiver vazio."""
    conn = get_db()
    cur = conn.cursor()

    # 1. Contatos & Networking (CRM)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pessoas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa TEXT DEFAULT '',
            nome TEXT DEFAULT '',
            cargo TEXT DEFAULT '',
            status TEXT DEFAULT '⏳ Pendente',
            mensagem TEXT DEFAULT '',
            retorno TEXT DEFAULT '',
            analise TEXT DEFAULT '',
            passo TEXT DEFAULT '',
            prioridade TEXT DEFAULT 'Média'
        )
    ''')

    # 2. Pipeline de Vagas & Estágios
    cur.execute('''
        CREATE TABLE IF NOT EXISTS vagas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa TEXT NOT NULL,
            cargo TEXT NOT NULL,
            local_modalidade TEXT DEFAULT 'Remoto',
            stack TEXT DEFAULT '',
            remuneracao TEXT DEFAULT '',
            deadline TEXT DEFAULT '',
            status TEXT DEFAULT 'Mapeada',
            notas TEXT DEFAULT ''
        )
    ''')

    # 3. Kanban de Tarefas & Prazos Sincronizáveis
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT NOT NULL,
            titulo TEXT NOT NULL,
            subtitulo TEXT DEFAULT '',
            descricao TEXT DEFAULT '',
            notas TEXT DEFAULT '',
            prazo TEXT DEFAULT '',
            data_prazo TEXT DEFAULT '',
            prioridade TEXT DEFAULT 'Média',
            concluida INTEGER DEFAULT 0,
            pessoa_id INTEGER DEFAULT NULL,
            data_criacao TEXT NOT NULL,
            data_conclusao TEXT DEFAULT NULL,
            FOREIGN KEY (pessoa_id) REFERENCES pessoas(id)
        )
    ''')

    # 4. Fichas de Contexto de Empresas (Base de Conhecimento)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS fichas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT DEFAULT 'Empresa Tech',
            produto TEXT DEFAULT '',
            stack TEXT DEFAULT '',
            pontos_conexao TEXT DEFAULT '',
            tom TEXT DEFAULT 'Técnico e objetivo'
        )
    ''')

    # Dados iniciais de demonstração (100% FICTÍCIOS / MOCK DATA)
    # ATENÇÃO: Criados unicamente para ilustrar o layout visual da interface.
    # Não utilize ou armazene nenhum dado real aqui.
    if cur.execute("SELECT COUNT(*) FROM vagas").fetchone()[0] == 0:
        vagas_demo = [
            (
                '[EXEMPLO] Empresa Alfa - Tecnologia (Fictício)',
                'Estagiário de Engenharia (Demonstração)',
                'Híbrido (Exemplo)',
                'C++, Python, Linux (Exemplo)',
                'R$ 0.000 (Valor Ilustrativo)',
                '2026-12-31',
                'Inscrito (Exemplo)',
                'Anotação de exemplo para demonstrar a tela. Nenhum dado real é utilizado.'
            ),
            (
                '[EXEMPLO] Empresa Beta - Sistemas (Fictício)',
                'Desenvolvedor Júnior (Demonstração)',
                'Remoto (Exemplo)',
                'Sistemas Embarcados, Hardware (Exemplo)',
                'R$ 0.000 (Valor Ilustrativo)',
                '2026-12-31',
                'Mapeada (Exemplo)',
                'Registro fictício para validação visual dos filtros e ordenação.'
            ),
            (
                '[EXEMPLO] Laboratório Gamma - P&D (Fictício)',
                'Pesquisador de Verão (Demonstração)',
                'Presencial (Exemplo)',
                'Processamento de Sinais, Simulação (Exemplo)',
                '0.000 EUR (Valor Ilustrativo)',
                '2026-12-31',
                'Entrevista Técnica (Exemplo)',
                'Candidatura fictícia para demonstração de oportunidade acadêmica.'
            )
        ]
        cur.executemany('''
            INSERT INTO vagas (empresa, cargo, local_modalidade, stack, remuneracao, deadline, status, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', vagas_demo)

    if cur.execute("SELECT COUNT(*) FROM pessoas").fetchone()[0] == 0:
        pessoas_demo = [
            (
                '[EXEMPLO] Empresa Alfa - Tecnologia (Fictício)',
                'Contato Demonstrativo 1 (Fictício)',
                'Engenheiro de Teste (Exemplo)',
                'Conectado (Exemplo)',
                'Texto meramente ilustrativo para demonstração do gerador de mensagens.',
                'Exemplo de retorno simulado para testes de interface.',
                'Anotação de teste sobre requisitos.',
                'Próximo passo simulado (Exemplo)',
                'Alta'
            ),
            (
                '[EXEMPLO] Empresa Beta - Sistemas (Fictício)',
                'Recrutador Demonstrativo 2 (Fictício)',
                'Recrutador de Teste (Exemplo)',
                'Pendente (Exemplo)',
                '',
                '',
                'Registro demonstrativo de triagem simulada.',
                'Aguardar retorno simulado (Exemplo)',
                'Média'
            )
        ]
        cur.executemany('''
            INSERT INTO pessoas (empresa, nome, cargo, status, mensagem, retorno, analise, passo, prioridade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', pessoas_demo)

    if cur.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0] == 0:
        hoje_iso = datetime.now().isoformat()
        prazo_1 = (date.today() + timedelta(days=7)).strftime('%Y-%m-%d')
        prazo_2 = (date.today() + timedelta(days=14)).strftime('%Y-%m-%d')
        tarefas_demo = [
            (
                'Demonstração',
                '[EXEMPLO] Tarefa Demonstrativa 1',
                'Subtítulo Ilustrativo',
                'Tarefa meramente ilustrativa para demonstrar o contador de pendências.',
                '',
                '7 dias',
                prazo_1,
                'Alta',
                0,
                hoje_iso,
                None
            ),
            (
                'Demonstração',
                '[EXEMPLO] Tarefa Demonstrativa 2',
                'Subtítulo Ilustrativo',
                'Exemplo para testar a sincronização de eventos com calendário .ics / Google Calendar.',
                '',
                '14 dias',
                prazo_2,
                'Média',
                0,
                hoje_iso,
                None
            )
        ]
        cur.executemany('''
            INSERT INTO tarefas (categoria, titulo, subtitulo, descricao, notas, prazo, data_prazo, prioridade, concluida, data_criacao, data_conclusao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', tarefas_demo)

    if cur.execute("SELECT COUNT(*) FROM fichas").fetchone()[0] == 0:
        fichas_demo = [
            (
                '[EXEMPLO] Empresa Alfa - Tecnologia (Fictício)',
                'Setor Demonstrativo',
                'Produto Fictício para Teste',
                'Stack Fictícia: C++, Python, Linux',
                'Pontos de interesse meramente ilustrativos',
                'Tom de comunicação demonstrativo'
            ),
            (
                '[EXEMPLO] Empresa Beta - Sistemas (Fictício)',
                'Setor Demonstrativo',
                'Sistema Fictício de Bancada',
                'Stack Fictícia: Hardware, Microcontroladores',
                'Critérios simulados de teste',
                'Tom de comunicação demonstrativo'
            )
        ]
        cur.executemany('''
            INSERT INTO fichas (nome, tipo, produto, stack, pontos_conexao, tom)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', fichas_demo)

    conn.commit()
    conn.close()


init_db_schema()


# ═══════════════════════════════════════════════════════
# MIDDLEWARE DE AUTENTICAÇÃO E CABEÇALHOS HTTP SEGUROS
# ═══════════════════════════════════════════════════════
@app.before_request
def check_security_access():
    client_ip = request.remote_addr or '127.0.0.1'
    is_localhost = client_ip in ('127.0.0.1', '::1', 'localhost')

    if not is_localhost and not AUTH_CONFIG.get('allow_lan', False):
        return Response(
            "Acesso negado: O servidor está em modo Somente Localhost. Ative 'allow_lan' em data/auth_config.json para acesso na rede local.",
            status=403,
            mimetype='text/plain'
        )

    allowed_paths = ('/login', '/api/login', '/static/')
    if any(request.path.startswith(p) for p in allowed_paths):
        return None

    if not session.get('authenticated'):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Não autenticado.', 'auth_required': True}), 401
        return redirect(url_for('login_page'))


@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


# ═══════════════════════════════════════════════════════
# ROTAS DE PÁGINAS E AUTENTICAÇÃO
# ═══════════════════════════════════════════════════════
@app.route('/login')
def login_page():
    if session.get('authenticated'):
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/api/login', methods=['POST'])
def api_login():
    client_ip = request.remote_addr or 'unknown'
    now = datetime.now()

    rec = FAILED_LOGINS.get(client_ip)
    if rec and rec.get('lock_until') and now < rec['lock_until']:
        secs = int((rec['lock_until'] - now).total_seconds())
        return jsonify({'error': f'Muitas tentativas incorretas. Aguarde {secs}s.'}), 429

    data = request.json or {}
    senha = str(data.get('senha', '')).strip()
    remember = bool(data.get('remember', True))

    if check_password_hash(AUTH_CONFIG['pin_hash'], senha):
        FAILED_LOGINS.pop(client_ip, None)
        session.clear()
        session['authenticated'] = True
        session.permanent = remember
        return jsonify({'success': True})

    if not rec:
        rec = {'count': 0, 'lock_until': None}
    rec['count'] += 1
    if rec['count'] >= 5:
        rec['lock_until'] = now + timedelta(minutes=5)
        FAILED_LOGINS[client_ip] = rec
        return jsonify({'error': 'Limite de 5 tentativas excedido. Acesso bloqueado por 5 minutos.'}), 429

    FAILED_LOGINS[client_ip] = rec
    restantes = 5 - rec['count']
    return jsonify({'error': f'PIN incorreto ({restantes} tentativas restantes).'}), 401


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/')
def index():
    return render_template('index.html')


# ═══════════════════════════════════════════════════════
# API: ANALYTICS & KPIs
# ═══════════════════════════════════════════════════════
@app.route('/api/analytics_kpi')
def api_kpis():
    try:
        conn = get_db()
        pessoas = [dict(r) for r in conn.execute('SELECT * FROM pessoas').fetchall()]
        vagas = [dict(r) for r in conn.execute('SELECT * FROM vagas').fetchall()]
        tarefas = [dict(r) for r in conn.execute('SELECT * FROM tarefas').fetchall()]
        conn.close()

        total_contatos = len(pessoas)
        conectados = sum(1 for p in pessoas if '✅' in p['status'] or 'conectad' in p['status'].lower() or 'respondid' in p['status'].lower())
        taxa_conexao = round((conectados / total_contatos * 100), 1) if total_contatos > 0 else 0

        total_vagas = len(vagas)
        vagas_ativas = sum(1 for v in vagas if v['status'].lower() not in ('encerrada', 'rejeitada'))

        tarefas_pendentes = sum(1 for t in tarefas if t['concluida'] == 0)
        tarefas_concluidas = sum(1 for t in tarefas if t['concluida'] == 1)

        return jsonify({
            'total_contatos': total_contatos,
            'conectados': conectados,
            'taxa_conexao': taxa_conexao,
            'total_vagas': total_vagas,
            'vagas_ativas': vagas_ativas,
            'tarefas_pendentes': tarefas_pendentes,
            'tarefas_concluidas': tarefas_concluidas
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ═══════════════════════════════════════════════════════
# API: PIPELINE DE VAGAS & OPORTUNIDADES
# ═══════════════════════════════════════════════════════
@app.route('/api/vagas', methods=['GET'])
def get_vagas():
    conn = get_db()
    rows = conn.execute('SELECT * FROM vagas ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/vagas', methods=['POST'])
def create_vaga():
    data = request.json or {}
    conn = get_db()
    cur = conn.execute('''
        INSERT INTO vagas (empresa, cargo, local_modalidade, stack, remuneracao, deadline, status, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('empresa', '').strip(),
        data.get('cargo', '').strip(),
        data.get('local_modalidade', 'Remoto').strip(),
        data.get('stack', '').strip(),
        data.get('remuneracao', '').strip(),
        data.get('deadline', '').strip(),
        data.get('status', 'Mapeada').strip(),
        data.get('notas', '').strip()
    ))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/vagas/<int:vaga_id>', methods=['PUT'])
def update_vaga(vaga_id):
    data = request.json or {}
    conn = get_db()
    conn.execute('''
        UPDATE vagas
        SET empresa = ?, cargo = ?, local_modalidade = ?, stack = ?, remuneracao = ?, deadline = ?, status = ?, notas = ?
        WHERE id = ?
    ''', (
        data.get('empresa', '').strip(),
        data.get('cargo', '').strip(),
        data.get('local_modalidade', 'Remoto').strip(),
        data.get('stack', '').strip(),
        data.get('remuneracao', '').strip(),
        data.get('deadline', '').strip(),
        data.get('status', 'Mapeada').strip(),
        data.get('notas', '').strip(),
        vaga_id
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/vagas/<int:vaga_id>', methods=['DELETE'])
def delete_vaga(vaga_id):
    conn = get_db()
    conn.execute('DELETE FROM vagas WHERE id = ?', (vaga_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ═══════════════════════════════════════════════════════
# API: CONTATOS & NETWORKING (CRM)
# ═══════════════════════════════════════════════════════
@app.route('/api/pessoas', methods=['GET'])
def get_pessoas():
    conn = get_db()
    rows = conn.execute('SELECT * FROM pessoas ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/pessoa/nova', methods=['POST'])
def create_pessoa():
    data = request.json or {}
    conn = get_db()
    cur = conn.execute('''
        INSERT INTO pessoas (empresa, nome, cargo, status, mensagem, retorno, analise, passo, prioridade)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('empresa', ''),
        data.get('nome', ''),
        data.get('cargo', ''),
        data.get('status', '⏳ Pendente'),
        data.get('mensagem', ''),
        data.get('retorno', ''),
        data.get('analise', ''),
        data.get('passo', ''),
        data.get('prioridade', 'Média')
    ))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/pessoa/<int:pessoa_id>', methods=['POST', 'PUT'])
def update_pessoa(pessoa_id):
    data = request.json or {}
    conn = get_db()
    conn.execute('''
        UPDATE pessoas
        SET empresa = ?, nome = ?, cargo = ?, status = ?, mensagem = ?, retorno = ?, analise = ?, passo = ?, prioridade = ?
        WHERE id = ?
    ''', (
        data.get('empresa', ''),
        data.get('nome', ''),
        data.get('cargo', ''),
        data.get('status', ''),
        data.get('mensagem', ''),
        data.get('retorno', ''),
        data.get('analise', ''),
        data.get('passo', ''),
        data.get('prioridade', ''),
        pessoa_id
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/pessoa/<int:pessoa_id>', methods=['DELETE'])
def delete_pessoa(pessoa_id):
    conn = get_db()
    conn.execute('DELETE FROM pessoas WHERE id = ?', (pessoa_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ═══════════════════════════════════════════════════════
# API: TAREFAS & KANBAN
# ═══════════════════════════════════════════════════════
@app.route('/api/tarefas', methods=['GET'])
def get_tarefas():
    conn = get_db()
    rows = conn.execute('SELECT * FROM tarefas ORDER BY concluida ASC, id DESC').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/tarefas', methods=['POST'])
def create_tarefa():
    data = request.json or {}
    hoje = datetime.now().isoformat()
    conn = get_db()
    cur = conn.execute('''
        INSERT INTO tarefas (categoria, titulo, subtitulo, descricao, notas, prazo, data_prazo, prioridade, concluida, data_criacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
    ''', (
        data.get('categoria', 'Geral'),
        data.get('titulo', '').strip(),
        data.get('subtitulo', '').strip(),
        data.get('descricao', '').strip(),
        data.get('notas', '').strip(),
        data.get('prazo', '').strip(),
        data.get('data_prazo', '').strip(),
        data.get('prioridade', 'Média'),
        hoje
    ))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/tarefas/<int:t_id>/toggle', methods=['POST'])
def toggle_tarefa(t_id):
    conn = get_db()
    row = conn.execute('SELECT concluida FROM tarefas WHERE id = ?', (t_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Tarefa não encontrada'}), 404
    novo_estado = 0 if row['concluida'] == 1 else 1
    data_conc = datetime.now().isoformat() if novo_estado == 1 else None
    conn.execute('UPDATE tarefas SET concluida = ?, data_conclusao = ? WHERE id = ?', (novo_estado, data_conc, t_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'concluida': novo_estado})


@app.route('/api/tarefas/<int:t_id>', methods=['DELETE'])
def delete_tarefa(t_id):
    conn = get_db()
    conn.execute('DELETE FROM tarefas WHERE id = ?', (t_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ═══════════════════════════════════════════════════════
# API: FICHAS DE CONTEXTO & GERADOR DE MENSAGENS IA
# ═══════════════════════════════════════════════════════
@app.route('/api/fichas', methods=['GET'])
def get_fichas():
    conn = get_db()
    rows = conn.execute('SELECT * FROM fichas ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/fichas/novo', methods=['POST'])
def create_ficha():
    data = request.json or {}
    conn = get_db()
    cur = conn.execute('''
        INSERT INTO fichas (nome, tipo, produto, stack, pontos_conexao, tom)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        data.get('nome', '').strip(),
        data.get('tipo', 'Empresa Tech').strip(),
        data.get('produto', '').strip(),
        data.get('stack', '').strip(),
        data.get('pontos_conexao', '').strip(),
        data.get('tom', 'Técnico e objetivo').strip()
    ))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/fichas/<int:ficha_id>', methods=['DELETE'])
def delete_ficha(ficha_id):
    conn = get_db()
    conn.execute('DELETE FROM fichas WHERE id = ?', (ficha_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/gerar_mensagem/<int:pessoa_id>', methods=['POST'])
def gerar_mensagem_ia(pessoa_id):
    """Gera mensagem personalizada de abordagem via Gemini API (se configurada) ou retorna prompt estruturado."""
    conn = get_db()
    pessoa = conn.execute('SELECT * FROM pessoas WHERE id = ?', (pessoa_id,)).fetchone()
    if not pessoa:
        conn.close()
        return jsonify({'error': 'Contato não encontrado'}), 404

    ficha = conn.execute('SELECT * FROM fichas WHERE LOWER(nome) LIKE ?', (f"%{pessoa['empresa'].lower()}%",)).fetchone()
    conn.close()

    contexto_empresa = ""
    if ficha:
        contexto_empresa = f"Produto/Core: {ficha['produto']} | Stack: {ficha['stack']} | Conexão Técnica: {ficha['pontos_conexao']}"

    prompt_text = (
        f"Elabore uma mensagem profissional, concisa e técnica (máximo de 3 parágrafos curtos) para abordagem no LinkedIn.\n"
        f"Destinatário: {pessoa['nome']} ({pessoa['cargo']} na empresa {pessoa['empresa']}).\n"
        f"Contexto Técnico da Empresa: {contexto_empresa or 'Engenharia e Tecnologia'}.\n"
        f"Objetivo: Apresentar interesse em oportunidades de estágio/colaboração técnica e destacar projetos práticos do portfólio.\n"
        f"Regras de tom: Evite clichês ou adjetivos exagerados; seja direto, cortês e objetivo."
    )

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            payload = json.dumps({"contents": [{"parts": [{"text": prompt_text}]}]}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as response:
                res_body = json.loads(response.read().decode('utf-8'))
                generated = res_body['candidates'][0]['content']['parts'][0]['text'].strip()
                conn = get_db()
                conn.execute("UPDATE pessoas SET mensagem = ? WHERE id = ?", (generated, pessoa_id))
                conn.commit()
                conn.close()
                return jsonify({'success': True, 'manual': False, 'mensagem': generated})
        except Exception as e:
            print(f"Aviso ao consultar API Gemini: {e}")

    return jsonify({'success': True, 'manual': True, 'prompt': prompt_text})


# ═══════════════════════════════════════════════════════
# API: EXPORTAÇÃO iCALENDAR (RFC 5545) & GOOGLE CALENDAR SYNC
# ═══════════════════════════════════════════════════════
@app.route('/api/calendario.ics')
def download_ics():
    conn = get_db()
    ics_content = calendario.gerar_ics(conn, incluir_concluidas=False)
    conn.close()
    response = Response(ics_content, mimetype='text/calendar; charset=utf-8')
    response.headers['Content-Disposition'] = 'attachment; filename=prazos_processos_seletivos.ics'
    return response


@app.route('/api/calendario/info')
def calendario_info():
    conn = get_db()
    info = calendario.get_sync_info(conn)
    conn.close()
    return jsonify(info)


@app.route('/api/google/status')
def api_google_status():
    return jsonify(google_sync.get_status())


@app.route('/api/google/credentials', methods=['POST'])
def api_google_save_creds():
    data = request.json or {}
    client_id = data.get('client_id', '').strip()
    client_secret = data.get('client_secret', '').strip()
    if not client_id or not client_secret:
        return jsonify({'error': 'Client ID e Client Secret são obrigatórios.'}), 400
    google_sync.save_client_credentials(client_id, client_secret)
    return jsonify({'success': True})


@app.route('/api/google/auth')
def api_google_auth():
    try:
        redirect_uri = url_for('api_google_callback', _external=True)
        flow = google_sync.create_flow(redirect_uri)
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        return redirect(auth_url)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/google/callback')
def api_google_callback():
    code = request.args.get('code')
    if not code:
        return "Código de autorização OAuth ausente.", 400
    try:
        redirect_uri = url_for('api_google_callback', _external=True)
        google_sync.save_token_from_code(code, redirect_uri)
        return redirect(url_for('index'))
    except Exception as e:
        return f"Erro na autenticação OAuth: {e}", 500


@app.route('/api/google/sync', methods=['POST'])
def api_google_sync_events():
    try:
        conn = get_db()
        res = google_sync.sync_events_to_google(conn)
        conn.close()
        return jsonify({'success': True, **res})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/google/disconnect', methods=['POST'])
def api_google_disconnect():
    google_sync.disconnect()
    return jsonify({'success': True})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Painel de Vagas iniciado em http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
