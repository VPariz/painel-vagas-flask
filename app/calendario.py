"""
calendario.py - Motor de geração iCalendar (RFC 5545) e links diretos para Google Calendar.
Compatível com Google Agenda, Apple Calendar, Microsoft Outlook e clientes mobile.
"""

from datetime import datetime, timedelta, timezone
import urllib.parse
import socket


def get_local_ip():
    """Detecta o IP local na rede LAN para facilitar a sincronização via dispositivos móveis."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def escape_ical_text(text):
    """Escapa caracteres especiais segundo a especificação RFC 5545."""
    if not text:
        return ""
    text = str(text)
    text = text.replace('\\', '\\\\')
    text = text.replace(';', r'\;')
    text = text.replace(',', r'\,')
    text = text.replace('\r\n', r'\n').replace('\n', r'\n')
    return text


def criar_google_calendar_url(titulo, data_str, descricao="", subtitulo=""):
    """
    Gera link direto (template URL) para adicionar evento de dia inteiro no Google Calendar.
    data_str: 'YYYY-MM-DD'
    """
    try:
        d_obj = datetime.strptime(data_str.strip(), '%Y-%m-%d').date()
        d_end = d_obj + timedelta(days=1)
        dates = f"{d_obj.strftime('%Y%m%d')}/{d_end.strftime('%Y%m%d')}"
    except Exception:
        dates = ""

    detalhes = []
    if subtitulo:
        detalhes.append(subtitulo)
    if descricao:
        detalhes.append(descricao)
    detalhes.append("\n[Sincronizado via Painel de Vagas]")

    params = {
        'action': 'TEMPLATE',
        'text': titulo,
        'dates': dates,
        'details': '\n\n'.join(detalhes)
    }
    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"


def gerar_ics(conn, incluir_concluidas=True):
    """
    Gera arquivo iCalendar (.ics) padrão RFC 5545 com alarmes integrados (VALARM).
    """
    now_stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

    where = "WHERE data_prazo != '' AND data_prazo IS NOT NULL"
    if not incluir_concluidas:
        where += " AND concluida = 0"

    tarefas = conn.execute(f"SELECT * FROM tarefas {where} ORDER BY data_prazo ASC").fetchall()

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PainelDeVagas//Painel de Vagas e Processos Seletivos//PT",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Painel de Vagas",
        "X-WR-CALDESC:Prazos de candidaturas, entrevistas técnicas e metas de carreira",
        "X-WR-TIMEZONE:America/Sao_Paulo"
    ]

    for t in tarefas:
        dp = t['data_prazo']
        if not dp:
            continue
        try:
            d_obj = datetime.strptime(dp.strip(), '%Y-%m-%d').date()
            d_end = d_obj + timedelta(days=1)
            dtstart = d_obj.strftime('%Y%m%d')
            dtend = d_end.strftime('%Y%m%d')
        except Exception:
            continue

        cat = t['categoria'] or 'Geral'
        tit = t['titulo'] or 'Tarefa'
        summary = escape_ical_text(f"[{cat}] {tit}")

        desc_parts = []
        if t['subtitulo']:
            desc_parts.append(t['subtitulo'])
        if t['prioridade']:
            desc_parts.append(f"Prioridade: {t['prioridade']}")
        if t['descricao']:
            desc_parts.append(t['descricao'])
        if t['notas']:
            desc_parts.append(f"Notas: {t['notas']}")
        status_txt = "Concluída" if t['concluida'] == 1 else "Pendente"
        desc_parts.append(f"Status: {status_txt}")

        desc_escaped = escape_ical_text("\n\n".join(desc_parts))
        uid = f"task-{t['id']}@painelvagas.local"

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc_escaped}",
            f"CATEGORIES:{escape_ical_text(cat)}",
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:Lembrete: {summary}",
            "TRIGGER:-P1D",
            "END:VALARM",
            "END:VEVENT"
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def get_sync_info(conn):
    """Retorna metadados de sincronização e lista de prazos ativos."""
    local_ip = get_local_ip()
    tarefas = conn.execute(
        "SELECT * FROM tarefas WHERE data_prazo != '' AND data_prazo IS NOT NULL ORDER BY data_prazo ASC"
    ).fetchall()

    marcos = []
    for t in tarefas:
        dp = t['data_prazo']
        url = criar_google_calendar_url(
            f"[{t['categoria']}] {t['titulo']}",
            dp,
            t['descricao'] or '',
            t['subtitulo'] or ''
        )
        marcos.append({
            'id': t['id'],
            'titulo': t['titulo'],
            'categoria': t['categoria'],
            'data_prazo': dp,
            'prioridade': t['prioridade'],
            'concluida': t['concluida'],
            'google_url': url
        })

    return {
        'total_eventos': len(tarefas),
        'local_ip': local_ip,
        'marcos': marcos
    }
