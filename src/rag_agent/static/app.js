(() => {
    const form = document.getElementById('chat-form');
    const input = document.getElementById('query-input');
    const messages = document.getElementById('messages');
    const sendBtn = document.getElementById('send-btn');
    const quotaText = document.getElementById('quota-text');
    const welcomeBox = document.getElementById('welcome');

    let quotaLimit = 30;
    let quotaRemaining = null;

    function autoResize() {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    }

    input.addEventListener('input', autoResize);

    function addMessage(text, type, citations, cached) {
        const div = document.createElement('div');
        div.className = `message ${type}`;

        let html = `<p>${escapeHtml(text)}</p>`;

        if (citations && citations.length > 0) {
            html += '<div class="citations">';
            html += '<div class="citations-title">Fuentes:</div>';
            citations.forEach(c => {
                const parts = [];
                if (c.video_title) parts.push(c.video_title);
                if (c.channel_name) parts.push(c.channel_name);
                if (c.comment_id) parts.push(`#${c.comment_id.slice(0, 8)}`);
                html += `<div class="citation-item">${escapeHtml(parts.join(' · ') || 'Sin detalle')}</div>`;
            });
            html += '</div>';
        }

        if (cached) {
            html += '<span class="cached-badge">cache</span>';
        }

        div.innerHTML = html;
        messages.appendChild(div);
        scrollToBottom();
        return div;
    }

    function addTypingIndicator() {
        const div = document.createElement('div');
        div.className = 'message bot';
        div.id = 'typing';
        div.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
        messages.appendChild(div);
        scrollToBottom();
        return div;
    }

    function removeTypingIndicator() {
        const el = document.getElementById('typing');
        if (el) el.remove();
    }

    function scrollToBottom() {
        messages.scrollTop = messages.scrollHeight;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // escapeHtml no escapa comillas, así que no sirve dentro de un atributo:
    // un valor con " cerraría el atributo antes de tiempo.
    function escapeAttr(str) {
        return escapeHtml(str).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    // limite null / restantes -1 = identidad sin tope (QUOTA_OVERRIDES).
    function updateQuota(remaining, limit) {
        if (limit !== undefined) quotaLimit = limit;
        quotaRemaining = remaining;
        if (quotaLimit === null || remaining < 0) {
            quotaText.textContent = 'Consultas hoy: sin límite';
            return;
        }
        quotaText.textContent = `Consultas hoy: ${quotaLimit - remaining}/${quotaLimit}`;
    }

    // La bienvenida se arma con lo que devuelve /welcome. Los DJs no se
    // escriben aquí: son los que tienen comentarios en el corpus, y cambian
    // solos cuando el pipeline alcanza un canal nuevo.
    async function loadWelcome() {
        try {
            const res = await fetch('/welcome');
            if (!res.ok) return;
            const d = await res.json();

            updateQuota(d.cuota.restantes, d.cuota.limite);

            const ejemplos = d.capacidades.map(c => `
                <li>
                    <span class="cap-title">${escapeHtml(c.titulo)}</span>
                    <button type="button" class="example" data-q="${escapeAttr(c.ejemplo)}">${escapeHtml(c.ejemplo)}</button>
                </li>`).join('');

            const djs = d.djs.length
                ? `<p class="djs"><strong>DJs disponibles:</strong> ${d.djs.map(escapeHtml).join(' · ')}</p>`
                : '';

            welcomeBox.innerHTML = `
                <p class="greeting">Hola, ${escapeHtml(d.nombre)}.</p>
                <p>${escapeHtml(d.descripcion)}</p>
                <p class="cap-heading"><strong>Qué puedes preguntarme</strong></p>
                <ul class="capabilities">${ejemplos}</ul>
                ${djs}
                <p class="quota-note">${d.cuota.limite === null
                    ? 'Tu cuenta no tiene límite diario de consultas.'
                    : `Tienes ${d.cuota.limite} consultas al día.`}</p>`;
            welcomeBox.hidden = false;

            welcomeBox.querySelectorAll('.example').forEach(btn => {
                btn.addEventListener('click', () => {
                    input.value = btn.dataset.q;
                    autoResize();
                    input.focus();
                });
            });
        } catch (err) {
            // Sin bienvenida se puede preguntar igual; no vale la pena
            // bloquear la UI por el saludo.
        }
    }

    function setLoading(loading) {
        sendBtn.disabled = loading;
        input.disabled = loading;
    }

    async function sendMessage(query) {
        addMessage(query, 'user');
        addTypingIndicator();
        setLoading(true);

        try {
            const res = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query }),
            });

            const data = await res.json();

            removeTypingIndicator();

            if (!res.ok) {
                addMessage(data.error || 'Error desconocido', 'error');
            } else {
                addMessage(data.response, 'bot', data.citations, data.cached);
                if (data.quota_remaining !== undefined) {
                    updateQuota(data.quota_remaining);
                }
            }
        } catch (err) {
            removeTypingIndicator();
            addMessage('Error de conexión. Verifica tu conexión e intenta de nuevo.', 'error');
        } finally {
            setLoading(false);
            input.focus();
        }
    }

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const query = input.value.trim();
        if (!query) return;
        input.value = '';
        autoResize();
        sendMessage(query);
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            form.dispatchEvent(new Event('submit'));
        }
    });

    input.focus();
    loadWelcome();
})();
