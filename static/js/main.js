// Contexta — Main JavaScript

document.addEventListener('DOMContentLoaded', () => {
    initStatusPolling();
    initAutoFlashDismiss();
});

// ── Automation Status Polling ──────────────────────────────────────────────

function initStatusPolling() {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    if (!dot || !text) return;

    async function fetchStatus() {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();
            const status = data.status;

            if (status === 'running') {
                dot.style.background = '#10b981';
                dot.style.animation = 'pulse 1s infinite';
                text.textContent = 'Running';
            } else if (status === 'failed') {
                dot.style.background = '#ef4444';
                dot.style.animation = '';
                text.textContent = 'Failed';
            } else {
                dot.style.background = '#94a3b8';
                dot.style.animation = '';
                text.textContent = 'Idle';
            }
        } catch (e) {
            dot.style.background = '#94a3b8';
        }
    }

    fetchStatus();
    setInterval(fetchStatus, 10000);
}

// ── Flash Message Auto-dismiss ─────────────────────────────────────────────

function initAutoFlashDismiss() {
    const flashes = document.querySelectorAll('.flash');
    flashes.forEach(flash => {
        setTimeout(() => {
            flash.style.transition = 'opacity 0.5s, transform 0.5s';
            flash.style.opacity = '0';
            flash.style.transform = 'translateY(-6px)';
            setTimeout(() => flash.remove(), 500);
        }, 4000);
    });
}

// ── Utility: Confirm Dialog ────────────────────────────────────────────────

window.confirmAction = function (message) {
    return confirm(message);
};
