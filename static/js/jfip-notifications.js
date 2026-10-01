/* ============================================================
   JFIP Notification System
   Replaces native alert/confirm with styled toast & dialog popups.
   ============================================================ */

(function () {
  'use strict';

  // ---- Toast Container ----
  const CONTAINER_ID = 'jfip-toast-container';

  function getContainer() {
    let container = document.getElementById(CONTAINER_ID);
    if (!container) {
      container = document.createElement('div');
      container.id = CONTAINER_ID;
      Object.assign(container.style, {
        position: 'fixed',
        top: '1.5rem',
        right: '1.5rem',
        zIndex: '10000',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        maxWidth: '420px',
        width: '100%',
        pointerEvents: 'none'
      });
      document.body.appendChild(container);
    }
    return container;
  }

  // ---- Icon SVGs ----
  const ICONS = {
    success: '<svg width="22" height="22" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="#27ae60" stroke-width="2"/><path d="M8 12l2.5 2.5L16 9" stroke="#27ae60" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    error: '<svg width="22" height="22" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="#e74c3c" stroke-width="2"/><path d="M15 9l-6 6M9 9l6 6" stroke="#e74c3c" stroke-width="2" stroke-linecap="round"/></svg>',
    warning: '<svg width="22" height="22" fill="none" viewBox="0 0 24 24"><path d="M12 3L2 21h20L12 3z" stroke="#F39C12" stroke-width="2" stroke-linejoin="round"/><path d="M12 10v4M12 17h.01" stroke="#F39C12" stroke-width="2" stroke-linecap="round"/></svg>',
    info: '<svg width="22" height="22" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="#4A90E2" stroke-width="2"/><path d="M12 11v5M12 8h.01" stroke="#4A90E2" stroke-width="2" stroke-linecap="round"/></svg>'
  };

  const COLORS = {
    success: { bg: '#f0faf4', border: '#27ae60', text: '#1e8449' },
    error: { bg: '#fef5f4', border: '#e74c3c', text: '#922b21' },
    warning: { bg: '#fefbf0', border: '#F39C12', text: '#7d6608' },
    info: { bg: '#f2f9fe', border: '#4A90E2', text: '#1a5276' }
  };

  /**
   * Show a toast notification.
   * @param {string} message - Text to display
   * @param {'success'|'error'|'warning'|'info'} type - Notification type
   * @param {number} duration - Duration in ms (0 = manual dismiss only)
   */
  function showToast(message, type = 'info', duration = 4000) {
    const container = getContainer();
    const colors = COLORS[type] || COLORS.info;
    const icon = ICONS[type] || ICONS.info;

    const toast = document.createElement('div');
    toast.className = 'jfip-toast';
    Object.assign(toast.style, {
      display: 'flex',
      alignItems: 'flex-start',
      gap: '0.75rem',
      padding: '1rem 1.25rem',
      background: colors.bg,
      border: `1px solid ${colors.border}`,
      borderLeft: `4px solid ${colors.border}`,
      borderRadius: '0.75rem',
      boxShadow: '0 8px 24px rgba(44,62,80,0.12)',
      color: colors.text,
      fontSize: '0.92rem',
      fontWeight: '500',
      lineHeight: '1.4',
      pointerEvents: 'all',
      opacity: '0',
      transform: 'translateX(30px) scale(0.95)',
      transition: 'all 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
      cursor: 'pointer',
      maxWidth: '100%',
      wordBreak: 'break-word'
    });

    toast.innerHTML = `
      <span style="flex-shrink:0; margin-top:1px;">${icon}</span>
      <span style="flex:1;">${escapeHtml(message)}</span>
      <button style="background:none; border:none; color:${colors.text}; opacity:0.6; cursor:pointer; font-size:1.2rem; line-height:1; padding:0; margin-left:0.5rem;" aria-label="Close">&times;</button>
    `;

    container.appendChild(toast);

    // Trigger entrance animation
    requestAnimationFrame(() => {
      toast.style.opacity = '1';
      toast.style.transform = 'translateX(0) scale(1)';
    });

    // Close handlers
    const dismiss = () => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(30px) scale(0.95)';
      setTimeout(() => toast.remove(), 350);
    };

    toast.querySelector('button').addEventListener('click', (e) => {
      e.stopPropagation();
      dismiss();
    });
    toast.addEventListener('click', dismiss);

    if (duration > 0) {
      setTimeout(dismiss, duration);
    }

    return toast;
  }

  /**
   * Show a confirmation dialog (replaces native confirm()).
   * @param {string} message - Question text
   * @param {object} options - { title, confirmText, cancelText, type }
   * @returns {Promise<boolean>} - Resolves true if confirmed
   */
  function showConfirm(message, options = {}) {
    const {
      title = 'Confirm Action',
      confirmText = 'Confirm',
      cancelText = 'Cancel',
      type = 'warning'
    } = options;

    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      Object.assign(overlay.style, {
        position: 'fixed',
        inset: '0',
        zIndex: '10001',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(44, 62, 80, 0.45)',
        backdropFilter: 'blur(4px)',
        opacity: '0',
        transition: 'opacity 0.3s ease',
        padding: '1rem'
      });

      const colors = COLORS[type] || COLORS.warning;

      const dialog = document.createElement('div');
      Object.assign(dialog.style, {
        background: '#fff',
        borderRadius: '1rem',
        padding: '2rem',
        maxWidth: '440px',
        width: '100%',
        boxShadow: '0 16px 48px rgba(44,62,80,0.2)',
        transform: 'scale(0.9) translateY(10px)',
        transition: 'all 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
        textAlign: 'center'
      });

      dialog.innerHTML = `
        <div style="margin-bottom:1.25rem;">
          ${ICONS[type] ? `<div style="margin-bottom:0.75rem;">${ICONS[type].replace(/width="22" height="22"/g, 'width="40" height="40"')}</div>` : ''}
          <h5 style="font-weight:700; color:#2C3E50; margin:0 0 0.5rem;">${escapeHtml(title)}</h5>
          <p style="color:#5a6d7e; margin:0; font-size:0.95rem; line-height:1.5;">${escapeHtml(message)}</p>
        </div>
        <div style="display:flex; gap:0.75rem; justify-content:center;">
          <button class="jfip-confirm-cancel" style="
            padding:0.6rem 1.5rem; border-radius:0.5rem; border:1.5px solid #dce3ea;
            background:#fff; color:#5a6d7e; font-weight:600; cursor:pointer;
            transition:all 0.15s ease; font-size:0.9rem;
          ">${escapeHtml(cancelText)}</button>
          <button class="jfip-confirm-ok" style="
            padding:0.6rem 1.5rem; border-radius:0.5rem; border:none;
            background:${type === 'error' ? '#e74c3c' : '#4A90E2'}; color:#fff; font-weight:600; cursor:pointer;
            transition:all 0.15s ease; font-size:0.9rem;
            box-shadow:0 4px 12px ${type === 'error' ? 'rgba(231,76,60,0.3)' : 'rgba(74,144,226,0.3)'};
          ">${escapeHtml(confirmText)}</button>
        </div>
      `;

      overlay.appendChild(dialog);
      document.body.appendChild(overlay);

      // Animate in
      requestAnimationFrame(() => {
        overlay.style.opacity = '1';
        dialog.style.transform = 'scale(1) translateY(0)';
      });

      const close = (result) => {
        overlay.style.opacity = '0';
        dialog.style.transform = 'scale(0.9) translateY(10px)';
        setTimeout(() => {
          overlay.remove();
          resolve(result);
        }, 300);
      };

      dialog.querySelector('.jfip-confirm-cancel').addEventListener('click', () => close(false));
      dialog.querySelector('.jfip-confirm-ok').addEventListener('click', () => close(true));
      overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });

      // Keyboard support
      const keyHandler = (e) => {
        if (e.key === 'Escape') { close(false); document.removeEventListener('keydown', keyHandler); }
        if (e.key === 'Enter') { close(true); document.removeEventListener('keydown', keyHandler); }
      };
      document.addEventListener('keydown', keyHandler);

      // Hover effects
      const cancelBtn = dialog.querySelector('.jfip-confirm-cancel');
      cancelBtn.addEventListener('mouseenter', () => { cancelBtn.style.background = '#f0f4f8'; cancelBtn.style.borderColor = '#b0bec5'; });
      cancelBtn.addEventListener('mouseleave', () => { cancelBtn.style.background = '#fff'; cancelBtn.style.borderColor = '#dce3ea'; });

      const okBtn = dialog.querySelector('.jfip-confirm-ok');
      okBtn.addEventListener('mouseenter', () => { okBtn.style.transform = 'translateY(-1px)'; okBtn.style.boxShadow = `0 6px 16px ${type === 'error' ? 'rgba(231,76,60,0.4)' : 'rgba(74,144,226,0.4)'}`; });
      okBtn.addEventListener('mouseleave', () => { okBtn.style.transform = 'translateY(0)'; okBtn.style.boxShadow = `0 4px 12px ${type === 'error' ? 'rgba(231,76,60,0.3)' : 'rgba(74,144,226,0.3)'}`; });
    });
  }

  // ---- Utility ----
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ---- Override native alert/confirm ----
  window._nativeAlert = window.alert;
  window._nativeConfirm = window.confirm;

  window.alert = function (msg) {
    showToast(msg, 'info', 5000);
  };

  // Note: native confirm is synchronous; this async shim works when callers
  // already use it in an async context. For legacy synchronous usage (like
  // onsubmit="return confirm(...)"), pages should migrate to jfipConfirm.
  // We keep the native fallback for synchronous contexts.

  // ---- Public API ----
  window.jfipToast = showToast;
  window.jfipConfirm = showConfirm;

})();
