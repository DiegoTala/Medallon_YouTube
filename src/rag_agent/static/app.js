(() => {
    const form = document.getElementById('chat-form');
    const input = document.getElementById('query-input');
    const messages = document.getElementById('messages');
    const sendBtn = document.getElementById('send-btn');
    const quotaText = document.getElementById('quota-text');

    let quotaRemaining = 30;

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

    function updateQuota(remaining) {
        quotaRemaining = remaining;
        quotaText.textContent = `Consultas hoy: ${30 - remaining}/30`;
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
})();
