/*
 * app.js - Controlador Frontend Modular do Painel de Vagas
 */

let state = {
    tarefas: [],
    vagas: [],
    pessoas: [],
    fichas: []
};

document.addEventListener('DOMContentLoaded', () => {
    refreshAll();
});

async function refreshAll() {
    await Promise.all([
        loadKPIs(),
        loadTarefas(),
        loadVagas(),
        loadPessoas(),
        loadFichas()
    ]);
}

function switchTab(tabId, btnEl) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    const target = document.getElementById(tabId);
    if (target) target.classList.add('active');
    if (btnEl) btnEl.classList.add('active');
}

function openModal(id) {
    document.getElementById(id).classList.add('open');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('open');
}

// ═══════════════════════════════════════════════════════
// KPIs & ANALYTICS
// ═══════════════════════════════════════════════════════
async function loadKPIs() {
    try {
        const res = await fetch('/api/analytics_kpi');
        const data = await res.json();
        document.getElementById('kpi-vagas').textContent = data.vagas_ativas ?? 0;
        document.getElementById('kpi-contatos').textContent = data.total_contatos ?? 0;
        document.getElementById('kpi-taxa').textContent = (data.taxa_conexao ?? 0) + '%';
        document.getElementById('kpi-tarefas').textContent = data.tarefas_pendentes ?? 0;
    } catch (e) {
        console.error('Erro ao carregar KPIs:', e);
    }
}

// ═══════════════════════════════════════════════════════
// KANBAN DE TAREFAS & DEADLINES
// ═══════════════════════════════════════════════════════
async function loadTarefas() {
    try {
        const res = await fetch('/api/tarefas');
        state.tarefas = await res.json();
        renderTarefas();
    } catch (e) {
        console.error('Erro ao carregar tarefas:', e);
    }
}

function renderTarefas() {
    const container = document.getElementById('tarefas-list');
    if (!state.tarefas.length) {
        container.innerHTML = '<p style="color:var(--text-muted);">Nenhuma tarefa cadastrada.</p>';
        return;
    }

    container.innerHTML = state.tarefas.map(t => `
        <div class="card" style="opacity: ${t.concluida ? '0.6' : '1'}; border-left: 4px solid ${t.concluida ? 'var(--success)' : 'var(--primary)'};">
            <div>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                    <span class="badge">${escapeHtml(t.categoria)}</span>
                    <span style="font-size:0.78rem;color:var(--text-muted);">${escapeHtml(t.prioridade)}</span>
                </div>
                <h3 style="font-size:1.05rem;margin-bottom:0.25rem;text-decoration:${t.concluida ? 'line-through' : 'none'};">
                    ${escapeHtml(t.titulo)}
                </h3>
                ${t.subtitulo ? `<div style="font-size:0.82rem;color:var(--primary);margin-bottom:0.4rem;">${escapeHtml(t.subtitulo)}</div>` : ''}
                <p style="font-size:0.86rem;color:var(--text-muted);">${escapeHtml(t.descricao || '')}</p>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.8rem;padding-top:0.6rem;border-top:1px solid var(--border);">
                <span style="font-size:0.78rem;color:var(--warning);">
                    ${t.data_prazo ? '📅 ' + escapeHtml(t.data_prazo) : 'Sem data limite'}
                </span>
                <div style="display:flex;gap:0.4rem;">
                    <button class="btn-outline" style="padding:0.3rem 0.65rem;font-size:0.78rem;" onclick="toggleTarefa(${t.id})">
                        ${t.concluida ? '↩ Reabrir' : '✓ Concluir'}
                    </button>
                    <button class="btn-danger" onclick="deleteTarefa(${t.id})">Excluir</button>
                </div>
            </div>
        </div>
    `).join('');
}

async function saveTarefa(e) {
    e.preventDefault();
    const payload = {
        categoria: document.getElementById('t-categoria').value,
        titulo: document.getElementById('t-titulo').value,
        subtitulo: document.getElementById('t-subtitulo').value,
        descricao: document.getElementById('t-descricao').value,
        data_prazo: document.getElementById('t-data-prazo').value,
        prioridade: document.getElementById('t-prioridade').value
    };
    await fetch('/api/tarefas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    e.target.reset();
    closeModal('modal-tarefa');
    await refreshAll();
}

async function toggleTarefa(id) {
    await fetch(`/api/tarefas/${id}/toggle`, { method: 'POST' });
    await refreshAll();
}

async function deleteTarefa(id) {
    await fetch(`/api/tarefas/${id}`, { method: 'DELETE' });
    await refreshAll();
}

// ═══════════════════════════════════════════════════════
// PIPELINE DE VAGAS & ESTÁGIOS
// ═══════════════════════════════════════════════════════
async function loadVagas() {
    try {
        const res = await fetch('/api/vagas');
        state.vagas = await res.json();
        renderVagas();
    } catch (e) {
        console.error('Erro ao carregar vagas:', e);
    }
}

function renderVagas() {
    const tbody = document.getElementById('vagas-tbody');
    if (!state.vagas.length) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">Nenhuma oportunidade cadastrada.</td></tr>';
        return;
    }
    tbody.innerHTML = state.vagas.map(v => `
        <tr>
            <td><strong>${escapeHtml(v.empresa)}</strong></td>
            <td>${escapeHtml(v.cargo)}</td>
            <td><span class="badge">${escapeHtml(v.local_modalidade)}</span></td>
            <td>${escapeHtml(v.stack)}</td>
            <td>${escapeHtml(v.remuneracao || '—')}</td>
            <td>${escapeHtml(v.deadline || '—')}</td>
            <td>
                <span class="badge" style="background:rgba(16,185,129,0.15);color:#34d399;">${escapeHtml(v.status)}</span>
                <button class="btn-danger" style="margin-left:0.5rem;" onclick="deleteVaga(${v.id})">×</button>
            </td>
        </tr>
    `).join('');
}

async function saveVaga(e) {
    e.preventDefault();
    const payload = {
        empresa: document.getElementById('v-empresa').value,
        cargo: document.getElementById('v-cargo').value,
        local_modalidade: document.getElementById('v-modalidade').value,
        stack: document.getElementById('v-stack').value,
        remuneracao: document.getElementById('v-remuneracao').value,
        deadline: document.getElementById('v-deadline').value,
        status: document.getElementById('v-status').value,
        notas: document.getElementById('v-notas').value
    };
    await fetch('/api/vagas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    e.target.reset();
    closeModal('modal-vaga');
    await refreshAll();
}

async function deleteVaga(id) {
    await fetch(`/api/vagas/${id}`, { method: 'DELETE' });
    await refreshAll();
}

// ═══════════════════════════════════════════════════════
// NETWORKING & CONTATOS (CRM)
// ═══════════════════════════════════════════════════════
async function loadPessoas() {
    try {
        const res = await fetch('/api/pessoas');
        state.pessoas = await res.json();
        renderPessoas();
    } catch (e) {
        console.error('Erro ao carregar contatos:', e);
    }
}

function renderPessoas() {
    const q = (document.getElementById('search-pessoas')?.value || '').toLowerCase();
    const filtered = state.pessoas.filter(p =>
        p.nome.toLowerCase().includes(q) ||
        p.empresa.toLowerCase().includes(q) ||
        p.cargo.toLowerCase().includes(q)
    );

    const tbody = document.getElementById('pessoas-tbody');
    if (!filtered.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);">Nenhum contato encontrado.</td></tr>';
        return;
    }

    tbody.innerHTML = filtered.map(p => `
        <tr>
            <td><strong>${escapeHtml(p.nome)}</strong></td>
            <td>${escapeHtml(p.empresa)}</td>
            <td>${escapeHtml(p.cargo)}</td>
            <td><span class="badge">${escapeHtml(p.status)}</span></td>
            <td>${escapeHtml(p.prioridade)}</td>
            <td style="display:flex;gap:0.4rem;">
                <button class="btn-outline" style="padding:0.3rem 0.6rem;font-size:0.78rem;" onclick="gerarPromptContato(${p.id})">✨ Gerar Abordagem IA</button>
                <button class="btn-danger" onclick="deletePessoa(${p.id})">×</button>
            </td>
        </tr>
    `).join('');
}

async function savePessoa(e) {
    e.preventDefault();
    const payload = {
        nome: document.getElementById('p-nome').value,
        empresa: document.getElementById('p-empresa').value,
        cargo: document.getElementById('p-cargo').value,
        status: document.getElementById('p-status').value,
        prioridade: document.getElementById('p-prioridade').value,
        passo: document.getElementById('p-passo').value
    };
    await fetch('/api/pessoa/nova', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    e.target.reset();
    closeModal('modal-pessoa');
    await refreshAll();
}

async function deletePessoa(id) {
    await fetch(`/api/pessoa/${id}`, { method: 'DELETE' });
    await refreshAll();
}

async function gerarPromptContato(id) {
    const res = await fetch(`/api/gerar_mensagem/${id}`, { method: 'POST' });
    const data = await res.json();
    const box = document.getElementById('ai-output-box');
    const textEl = document.getElementById('ai-output-text');
    box.style.display = 'block';
    textEl.value = data.mensagem || data.prompt || 'Erro ao gerar mensagem.';
}

// ═══════════════════════════════════════════════════════
// FICHAS TÉCNICAS DE EMPRESAS
// ═══════════════════════════════════════════════════════
async function loadFichas() {
    try {
        const res = await fetch('/api/fichas');
        state.fichas = await res.json();
        renderFichas();
    } catch (e) {
        console.error('Erro ao carregar fichas:', e);
    }
}

function renderFichas() {
    const container = document.getElementById('fichas-grid');
    if (!state.fichas.length) {
        container.innerHTML = '<p style="color:var(--text-muted);">Nenhuma ficha cadastrada.</p>';
        return;
    }
    container.innerHTML = state.fichas.map(f => `
        <div class="card">
            <div>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                    <span class="badge">${escapeHtml(f.tipo)}</span>
                    <button class="btn-danger" onclick="deleteFicha(${f.id})">Excluir</button>
                </div>
                <h3 style="font-size:1.1rem;margin-bottom:0.35rem;">${escapeHtml(f.nome)}</h3>
                <p style="font-size:0.85rem;color:var(--text-muted);margin-bottom:0.5rem;"><strong>Produto/Core:</strong> ${escapeHtml(f.produto)}</p>
                <p style="font-size:0.85rem;color:var(--text-muted);margin-bottom:0.5rem;"><strong>Stack:</strong> ${escapeHtml(f.stack)}</p>
                <p style="font-size:0.85rem;color:var(--text-muted);"><strong>Conexão Técnica:</strong> ${escapeHtml(f.pontos_conexao)}</p>
            </div>
        </div>
    `).join('');
}

async function saveFicha(e) {
    e.preventDefault();
    const payload = {
        nome: document.getElementById('f-nome').value,
        tipo: document.getElementById('f-tipo').value,
        produto: document.getElementById('f-produto').value,
        stack: document.getElementById('f-stack').value,
        pontos_conexao: document.getElementById('f-conexao').value
    };
    await fetch('/api/fichas/novo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    e.target.reset();
    closeModal('modal-ficha');
    await loadFichas();
}

async function deleteFicha(id) {
    await fetch(`/api/fichas/${id}`, { method: 'DELETE' });
    await loadFichas();
}

// ═══════════════════════════════════════════════════════
// SINCRONIZAÇÃO DE CALENDÁRIO (RFC 5545 & GOOGLE OAUTH)
// ═══════════════════════════════════════════════════════
async function openSyncModal() {
    openModal('modal-sync');
    try {
        const [infoRes, statusRes] = await Promise.all([
            fetch('/api/calendario/info'),
            fetch('/api/google/status')
        ]);
        const info = await infoRes.json();
        const status = await statusRes.json();

        document.getElementById('sync-total-eventos').textContent = info.total_eventos ?? 0;
        const badgeEl = document.getElementById('google-status-badge');
        if (status.authenticated) {
            badgeEl.textContent = `Conectado (${status.email || 'Google OAuth'})`;
            badgeEl.style.color = '#34d399';
        } else {
            badgeEl.textContent = 'Não conectado (Use exportação .ICS ou configure OAuth)';
            badgeEl.style.color = '#fbbf24';
        }
    } catch (e) {
        console.error('Erro ao buscar status de agenda:', e);
    }
}

async function syncGoogleNow() {
    const btn = document.getElementById('btn-google-sync');
    btn.disabled = true;
    btn.textContent = 'Sincronizando...';
    try {
        const res = await fetch('/api/google/sync', { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.success) {
            alert(`✓ ${data.total_synced} eventos sincronizados na agenda '${data.calendar_name}'!`);
        } else {
            alert(data.error || 'Configure as credenciais OAuth antes de sincronizar.');
        }
    } catch (e) {
        alert('Erro ao sincronizar com Google Calendar.');
    } finally {
        btn.disabled = false;
        btn.textContent = '🔄 Sincronizar via Google Calendar API';
    }
}

function escapeHtml(str) {
    return String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
