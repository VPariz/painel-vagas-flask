"""
google_sync.py - Integração OAuth 2.0 com a API do Google Calendar.
Permite sincronizar prazos de tarefas e candidaturas em uma agenda secundária dedicada.
"""

import os
import json
import requests
from datetime import datetime, timedelta

try:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'google_credentials.json')
TOKEN_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'google_token.json')

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]

CALENDAR_NAME = os.environ.get("PAINEL_CALENDAR_NAME", "Painel de Vagas")


def get_client_config():
    """Carrega o client_id e client_secret do Google Cloud OAuth 2.0."""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'web' in data:
                    return data
                elif 'installed' in data:
                    return {'web': data['installed']}
                elif 'client_id' in data and 'client_secret' in data:
                    return {
                        'web': {
                            'client_id': data['client_id'],
                            'client_secret': data['client_secret'],
                            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                            'token_uri': 'https://oauth2.googleapis.com/token'
                        }
                    }
        except Exception as e:
            print(f"Erro ao ler {CREDENTIALS_FILE}: {e}")
            return None
    return None


def save_client_credentials(client_id, client_secret):
    """Salva as credenciais OAuth 2.0 fornecidas pelo usuário localmente em data/."""
    client_id = client_id.strip()
    client_secret = client_secret.strip()
    config = {
        'web': {
            'client_id': client_id,
            'client_secret': client_secret,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': ['http://localhost:5000/api/google/callback']
        }
    }
    os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
    with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    return True


def get_credentials():
    """Retorna objeto Credentials válido, renovando o token automaticamente se expirado."""
    if not GOOGLE_LIBS_AVAILABLE or not os.path.exists(TOKEN_FILE):
        return None
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                f.write(creds.to_json())
        return creds
    except Exception as e:
        print(f"Erro ao renovar token Google: {e}")
        return None


def get_status():
    """Retorna o estado atual da integração com o Google Calendar."""
    config = get_client_config()
    configured = config is not None
    creds = get_credentials()
    authenticated = creds is not None and creds.valid

    email = None
    if authenticated:
        try:
            r = requests.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {creds.token}'},
                timeout=5
            )
            if r.status_code == 200:
                email = r.json().get('email')
        except Exception:
            pass

    return {
        'libs_installed': GOOGLE_LIBS_AVAILABLE,
        'configured': configured,
        'authenticated': authenticated,
        'email': email,
        'calendar_name': CALENDAR_NAME
    }


def create_flow(redirect_uri):
    """Inicializa o fluxo OAuth 2.0 do Google."""
    if not GOOGLE_LIBS_AVAILABLE:
        raise RuntimeError("Bibliotecas google-auth-oauthlib não instaladas. Execute: pip install -r requirements.txt")
    config = get_client_config()
    if not config:
        raise ValueError("Credenciais OAuth não configuradas. Informe seu Client ID e Client Secret.")

    return Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redirect_uri)


def save_token_from_code(code, redirect_uri):
    """Troca o authorization code por tokens OAuth e salva localmente."""
    flow = create_flow(redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        f.write(creds.to_json())
    return creds


def disconnect():
    """Remove o token de sessão OAuth armazenado."""
    if os.path.exists(TOKEN_FILE):
        try:
            os.remove(TOKEN_FILE)
        except Exception:
            pass
    return True


def sync_events_to_google(conn):
    """
    Sincroniza tarefas com prazo do banco SQLite para a agenda dedicada no Google Calendar.
    Evita duplicatas rastreando o identificador [ID:task-X] na descrição do evento.
    """
    creds = get_credentials()
    if not creds or not creds.valid:
        raise ValueError("Conta Google não autenticada ou sessão expirada.")

    headers = {
        'Authorization': f'Bearer {creds.token}',
        'Content-Type': 'application/json'
    }

    # 1. Obter ou criar a agenda secundária dedicada
    cal_res = requests.get('https://www.googleapis.com/calendar/v3/users/me/calendarList', headers=headers, timeout=10)
    calendar_id = None
    if cal_res.status_code == 200:
        for cal in cal_res.json().get('items', []):
            if cal.get('summary') == CALENDAR_NAME:
                calendar_id = cal.get('id')
                break

    if not calendar_id:
        create_res = requests.post(
            'https://www.googleapis.com/calendar/v3/calendars',
            headers=headers,
            json={
                'summary': CALENDAR_NAME,
                'description': 'Prazos de candidaturas, entrevistas técnicas e tarefas sincronizadas via Painel de Vagas'
            },
            timeout=10
        )
        if create_res.status_code in (200, 201):
            calendar_id = create_res.json().get('id')
        else:
            calendar_id = 'primary'

    # 2. Mapear eventos existentes para atualizar em vez de duplicar
    existing_events = {}
    try:
        events_res = requests.get(
            f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events?maxResults=250',
            headers=headers,
            timeout=10
        )
        if events_res.status_code == 200:
            for ev in events_res.json().get('items', []):
                desc = ev.get('description', '')
                summary = ev.get('summary', '')
                if '[ID:task-' in desc:
                    start_pos = desc.find('[ID:task-') + len('[ID:task-')
                    end_pos = desc.find(']', start_pos)
                    if end_pos != -1:
                        t_id = desc[start_pos:end_pos]
                        existing_events[t_id] = ev.get('id')
                else:
                    existing_events[summary] = ev.get('id')
    except Exception as e:
        print(f"Aviso ao listar eventos existentes: {e}")

    # 3. Sincronizar tarefas do SQLite
    tarefas = conn.execute(
        "SELECT * FROM tarefas WHERE data_prazo != '' AND data_prazo IS NOT NULL"
    ).fetchall()

    synced_count = 0
    errors = []

    for t in tarefas:
        dp = t['data_prazo'].strip()
        try:
            d_obj = datetime.strptime(dp, '%Y-%m-%d').date()
            d_end = d_obj + timedelta(days=1)
            start_str = d_obj.strftime('%Y-%m-%d')
            end_str = d_end.strftime('%Y-%m-%d')
        except Exception:
            continue

        cat = t['categoria'] or 'Geral'
        summary = f"[{cat}] {t['titulo']}"
        desc_parts = [
            f"[ID:task-{t['id']}]",
            f"Categoria: {cat}",
            f"Prioridade: {t['prioridade'] or 'Média'}"
        ]
        if t['subtitulo']:
            desc_parts.append(f"Subtítulo: {t['subtitulo']}")
        if t['descricao']:
            desc_parts.append(f"\n{t['descricao']}")
        if t['notas']:
            desc_parts.append(f"\nNotas: {t['notas']}")
        status_txt = "Concluída" if t['concluida'] == 1 else "Pendente"
        desc_parts.append(f"\nStatus: {status_txt}")
        desc_parts.append("\nSincronizado via Painel de Vagas")

        event_body = {
            'summary': summary,
            'description': '\n'.join(desc_parts),
            'start': {'date': start_str},
            'end': {'date': end_str},
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 1440},
                    {'method': 'popup', 'minutes': 120}
                ]
            }
        }

        existing_event_id = existing_events.get(str(t['id'])) or existing_events.get(summary)
        if existing_event_id:
            up_res = requests.put(
                f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{existing_event_id}',
                headers=headers,
                json=event_body,
                timeout=10
            )
            if up_res.status_code in (200, 201):
                synced_count += 1
            else:
                errors.append(f"Erro ao atualizar {summary}: {up_res.text}")
        else:
            post_res = requests.post(
                f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events',
                headers=headers,
                json=event_body,
                timeout=10
            )
            if post_res.status_code in (200, 201):
                synced_count += 1
            else:
                errors.append(f"Erro ao criar {summary}: {post_res.text}")

    return {
        'total_synced': synced_count,
        'calendar_id': calendar_id,
        'calendar_name': CALENDAR_NAME,
        'errors': errors
    }
