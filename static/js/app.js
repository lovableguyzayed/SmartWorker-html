// SmartWorker Application JavaScript

// ── DOMContentLoaded shim for SPA navigation ─────────────────
// Page templates register init code via DOMContentLoaded. After the first
// load the document never re-parses (screens are swapped in place), so any
// handler registered later runs immediately instead of never firing.
window.__domReady = false;
(() => {
    const origAdd = document.addEventListener.bind(document);
    document.addEventListener = function (type, fn, opts) {
        if (type === 'DOMContentLoaded' && window.__domReady) {
            queueMicrotask(() => fn.call(document, new Event('DOMContentLoaded')));
            return;
        }
        return origAdd(type, fn, opts);
    };
    origAdd('DOMContentLoaded', () => { window.__domReady = true; });
})();

// Global app configuration
const SmartWorker = {
    config: {
        apiBase: '/api',
        version: '1.0.0',
        debug: true
    },
    
    // Utility functions
    utils: {
        // Format date for display
        formatDate(date, format = 'short') {
            const options = {
                short: { year: 'numeric', month: 'short', day: 'numeric' },
                long: { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' },
                time: { hour: '2-digit', minute: '2-digit' }
            };
            
            return new Date(date).toLocaleDateString('en-US', options[format]);
        },
        
        // Format currency
        formatCurrency(amount, currency = 'INR') {
            return new Intl.NumberFormat('en-IN', {
                style: 'currency',
                currency: currency,
                minimumFractionDigits: 0
            }).format(amount);
        },
        
        // Debounce function for search inputs
        debounce(func, wait, immediate) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    timeout = null;
                    if (!immediate) func(...args);
                };
                const callNow = immediate && !timeout;
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
                if (callNow) func(...args);
            };
        },
        
        // Show toast notification
        showToast(message, type = 'info', duration = 5000) {
            const toast = document.createElement('div');
            toast.className = `fixed top-4 right-4 z-50 p-4 rounded-lg shadow-lg max-w-sm ${this.getToastClass(type)} slide-up`;
            toast.innerHTML = `
                <div class="flex items-center justify-between">
                    <div class="flex items-center">
                        <i class="fa-solid ${this.getToastIcon(type)} mr-2"></i>
                        <span>${message}</span>
                    </div>
                    <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-current opacity-70 hover:opacity-100">
                        <i class="fa-solid fa-times"></i>
                    </button>
                </div>
            `;
            
            document.body.appendChild(toast);
            
            // Auto remove after duration
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.remove();
                }
            }, duration);
        },
        
        getToastClass(type) {
            const classes = {
                success: 'bg-green-500 text-white',
                error: 'bg-red-500 text-white',
                warning: 'bg-yellow-500 text-white',
                info: 'bg-blue-500 text-white'
            };
            return classes[type] || classes.info;
        },
        
        getToastIcon(type) {
            const icons = {
                success: 'fa-check-circle',
                error: 'fa-exclamation-circle',
                warning: 'fa-exclamation-triangle',
                info: 'fa-info-circle'
            };
            return icons[type] || icons.info;
        },
        
        // Validate form fields
        validateForm(formElement) {
            const inputs = formElement.querySelectorAll('input[required], select[required], textarea[required]');
            let isValid = true;
            
            inputs.forEach(input => {
                if (!input.value.trim()) {
                    this.showFieldError(input, 'This field is required');
                    isValid = false;
                } else {
                    this.clearFieldError(input);
                }
                
                // Email validation
                if (input.type === 'email' && input.value) {
                    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
                    if (!emailRegex.test(input.value)) {
                        this.showFieldError(input, 'Please enter a valid email address');
                        isValid = false;
                    }
                }
                
                // Phone validation
                if (input.type === 'tel' && input.value) {
                    const phoneRegex = /^[\+]?[1-9][\d]{0,15}$/;
                    if (!phoneRegex.test(input.value.replace(/\s/g, ''))) {
                        this.showFieldError(input, 'Please enter a valid phone number');
                        isValid = false;
                    }
                }
            });
            
            return isValid;
        },
        
        showFieldError(input, message) {
            input.classList.add('form-error');
            let errorElement = input.parentNode.querySelector('.field-error');
            if (!errorElement) {
                errorElement = document.createElement('div');
                errorElement.className = 'field-error text-red-500 text-xs mt-1';
                input.parentNode.appendChild(errorElement);
            }
            errorElement.textContent = message;
        },
        
        clearFieldError(input) {
            input.classList.remove('form-error');
            const errorElement = input.parentNode.querySelector('.field-error');
            if (errorElement) {
                errorElement.remove();
            }
        }
    },
    
    // Search functionality
    search: {
        init() {
            const searchInputs = document.querySelectorAll('[data-search]');
            searchInputs.forEach(input => {
                input.addEventListener('input', SmartWorker.utils.debounce(this.performSearch.bind(this), 300));
            });
        },
        
        performSearch(event) {
            const query = event.target.value.toLowerCase();
            const target = event.target.dataset.search;
            const items = document.querySelectorAll(`[data-searchable="${target}"]`);
            
            items.forEach(item => {
                const searchText = item.textContent.toLowerCase();
                if (searchText.includes(query)) {
                    item.style.display = '';
                    item.classList.add('fade-in');
                } else {
                    item.style.display = 'none';
                    item.classList.remove('fade-in');
                }
            });
        }
    },
    
    // Modal management
    modal: {
        show(modalId) {
            const modal = document.getElementById(modalId);
            if (modal) {
                modal.classList.remove('hidden');
                modal.classList.add('fade-in');
                document.body.style.overflow = 'hidden';
                
                // Focus trap
                this.trapFocus(modal);
            }
        },
        
        hide(modalId) {
            const modal = document.getElementById(modalId);
            if (modal) {
                modal.classList.add('hidden');
                modal.classList.remove('fade-in');
                document.body.style.overflow = '';
            }
        },
        
        trapFocus(element) {
            const focusableElements = element.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
            );
            const firstElement = focusableElements[0];
            const lastElement = focusableElements[focusableElements.length - 1];
            
            element.addEventListener('keydown', (e) => {
                if (e.key === 'Tab') {
                    if (e.shiftKey) {
                        if (document.activeElement === firstElement) {
                            lastElement.focus();
                            e.preventDefault();
                        }
                    } else {
                        if (document.activeElement === lastElement) {
                            firstElement.focus();
                            e.preventDefault();
                        }
                    }
                }
                
                if (e.key === 'Escape') {
                    this.hide(element.id);
                }
            });
            
            firstElement?.focus();
        }
    },
    
    // Form handling
    forms: {
        init() {
            // Add form validation to all forms with data-validate attribute
            const forms = document.querySelectorAll('form[data-validate]');
            forms.forEach(form => {
                form.addEventListener('submit', this.handleSubmit.bind(this));
                
                // Real-time validation
                const inputs = form.querySelectorAll('input, select, textarea');
                inputs.forEach(input => {
                    input.addEventListener('blur', () => {
                        this.validateField(input);
                    });
                });
            });
        },
        
        handleSubmit(event) {
            event.preventDefault();
            const form = event.target;
            
            if (SmartWorker.utils.validateForm(form)) {
                // Show loading state
                const submitButton = form.querySelector('button[type="submit"]');
                const originalText = submitButton.textContent;
                submitButton.textContent = 'Saving...';
                submitButton.disabled = true;
                
                // Submit form after validation
                setTimeout(() => {
                    form.submit();
                }, 500);
            } else {
                SmartWorker.utils.showToast('Please fix the errors and try again', 'error');
            }
        },
        
        validateField(input) {
            if (input.hasAttribute('required') && !input.value.trim()) {
                SmartWorker.utils.showFieldError(input, 'This field is required');
                return false;
            } else {
                SmartWorker.utils.clearFieldError(input);
                return true;
            }
        }
    },
    
    // Attendance specific functions
    attendance: {
        markAttendance(workerId, status, date) {
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/mark_attendance';
            
            const fields = {
                worker_id: workerId,
                status: status,
                date: date
            };
            
            Object.keys(fields).forEach(key => {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = key;
                input.value = fields[key];
                form.appendChild(input);
            });
            
            document.body.appendChild(form);
            form.submit();
        },
        
        bulkMarkAttendance(status, date) {
            if (confirm(`Mark all workers as ${status} for ${date}?`)) {
                const form = document.createElement('form');
                form.method = 'POST';
                form.action = '/mark_attendance';
                
                const fields = {
                    bulk_action: 'true',
                    status: status,
                    date: date
                };
                
                Object.keys(fields).forEach(key => {
                    const input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = key;
                    input.value = fields[key];
                    form.appendChild(input);
                });
                
                document.body.appendChild(form);
                form.submit();
            }
        }
    },
    
    // Storage utilities
    storage: {
        set(key, value) {
            try {
                localStorage.setItem(`smartworker_${key}`, JSON.stringify(value));
            } catch (error) {
                console.warn('localStorage not available:', error);
            }
        },
        
        get(key, defaultValue = null) {
            try {
                const item = localStorage.getItem(`smartworker_${key}`);
                return item ? JSON.parse(item) : defaultValue;
            } catch (error) {
                console.warn('localStorage not available:', error);
                return defaultValue;
            }
        },
        
        remove(key) {
            try {
                localStorage.removeItem(`smartworker_${key}`);
            } catch (error) {
                console.warn('localStorage not available:', error);
            }
        }
    },
    
    // Initialize the application
    init() {
        console.log('SmartWorker App v' + this.config.version + ' initializing...');
        
        // Initialize modules
        this.search.init();
        this.forms.init();
        
        // Add global event listeners
        this.addGlobalListeners();
        
        // Load user preferences
        this.loadUserPreferences();
        
        console.log('SmartWorker App initialized successfully');
    },
    
    addGlobalListeners() {
        // Close modals when clicking outside
        document.addEventListener('click', (event) => {
            if (event.target.classList.contains('modal-backdrop')) {
                const modal = event.target.closest('[id$="-modal"]');
                if (modal) {
                    this.modal.hide(modal.id);
                }
            }
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (event) => {
            // Ctrl/Cmd + K for quick search
            if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
                event.preventDefault();
                const searchInput = document.querySelector('input[type="search"], input[data-search]');
                if (searchInput) {
                    searchInput.focus();
                }
            }
        });
        
        // Handle network status
        window.addEventListener('online', () => {
            this.utils.showToast('Connection restored', 'success');
        });
        
        window.addEventListener('offline', () => {
            this.utils.showToast('Connection lost', 'warning');
        });
    },
    
    loadUserPreferences() {
        // Load theme preference
        const theme = this.storage.get('theme', 'light');
        document.documentElement.setAttribute('data-theme', theme);
        
        // Load other preferences
        const preferences = this.storage.get('preferences', {});
        if (preferences.notifications !== false) {
            this.requestNotificationPermission();
        }
    },
    
    requestNotificationPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }
};

// ── NativeShell: SPA navigation engine ───────────────────────
// The WebView loads the document exactly once. Every link tap and form
// submit afterwards is fetched over XHR and the new screen is swapped into
// the live document — no full page reloads, no browser loading indicator,
// no white flash. Combined with the service worker cache this makes screen
// changes effectively instant, like a native Android activity switch.
const NativeShell = {
    loadedAssets: new Set(),
    skeletonTimer: null,
    navigating: false,

    PRELOAD_SCREENS: ['/dashboard', '/workers', '/attendance', '/payroll',
                      '/transactions', '/assignments', '/settings',
                      '/notifications', '/closures', '/profile'],

    init() {
        // Remember assets already in the document so swaps never re-run them
        document.querySelectorAll('script[src]').forEach((s) =>
            this.loadedAssets.add(new URL(s.src, location.href).pathname));
        document.querySelectorAll('link[rel="stylesheet"]').forEach((l) =>
            this.loadedAssets.add(new URL(l.href, location.href).pathname));

        document.addEventListener('click', (e) => this.onClick(e));
        document.addEventListener('submit', (e) => this.onSubmit(e));
        window.addEventListener('popstate', () => this.visit(location.href, { push: false }));
        if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

        // Touch-warm prefetch: pages enter the SW cache before the tap lands
        const warm = (e) => {
            const link = e.target.closest('a[href]');
            if (!link) return;
            const href = link.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('javascript')) return;
            try {
                const url = new URL(href, location.href);
                if (url.origin !== location.origin) return;
                fetch(url.href, { credentials: 'same-origin', headers: { 'Accept': 'text/html' } }).catch(() => {});
            } catch (_) {}
        };
        document.addEventListener('touchstart', warm, { passive: true });

        this.preloadMainScreens();
        // Re-check after each swap: the post-login swap is when the bottom
        // nav first appears and preloading becomes worthwhile.
        document.addEventListener('page:load', () => this.preloadMainScreens());
    },

    // After login, warm every main screen into the SW cache so switching
    // between them is instant — even on first visit and even offline later.
    preloadMainScreens() {
        if (!document.querySelector('nav.app-bottom-nav')) return;
        if (sessionStorage.getItem('sw-preloaded')) return;
        sessionStorage.setItem('sw-preloaded', '1');
        const run = () => {
            this.PRELOAD_SCREENS
                .filter((p) => p !== location.pathname)
                .forEach((path, i) => {
                    setTimeout(() => {
                        fetch(path, { credentials: 'same-origin', headers: { 'Accept': 'text/html' } }).catch(() => {});
                    }, 400 * i);
                });
        };
        ('requestIdleCallback' in window) ? requestIdleCallback(run, { timeout: 3000 }) : setTimeout(run, 1200);
    },

    onClick(e) {
        if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        const link = e.target.closest('a[href]');
        if (!link) return;
        const href = link.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
        if (link.target && link.target !== '_self') return;
        if (link.hasAttribute('download') || link.hasAttribute('data-native')) return;
        let url;
        try { url = new URL(href, location.href); } catch (_) { return; }
        if (url.origin !== location.origin) return;
        if (url.protocol !== 'http:' && url.protocol !== 'https:') return;
        e.preventDefault();
        this.visit(url.href);
    },

    onSubmit(e) {
        if (e.defaultPrevented) return;
        const form = e.target;
        if (!(form instanceof HTMLFormElement) || form.hasAttribute('data-native')) return;
        if (form.target && form.target !== '_self') return;
        const method = (form.getAttribute('method') || 'get').toUpperCase();
        // Offline POSTs belong to offline-sync.js (it queues them locally)
        if (method !== 'GET' && !navigator.onLine) return;
        let action;
        try { action = new URL(form.getAttribute('action') || location.href, location.href); } catch (_) { return; }
        if (action.origin !== location.origin) return;
        e.preventDefault();

        const fd = new FormData(form);
        const sub = e.submitter;
        if (sub && sub.name) fd.append(sub.name, sub.value || '');

        if (method === 'GET') {
            action.search = new URLSearchParams(fd).toString();
            this.visit(action.href);
        } else {
            this.visit(action.href, { method, body: fd });
        }
    },

    async visit(href, opts = {}) {
        if (this.navigating) return;
        this.navigating = true;
        document.dispatchEvent(new Event('page:before-swap'));
        this.scheduleSkeleton();
        try {
            const res = await fetch(href, {
                method: opts.method || 'GET',
                body: opts.body || null,
                credentials: 'same-origin',
                headers: { 'Accept': 'text/html' },
                redirect: 'follow',
            });
            const html = await res.text();
            this.render(html, res.url || href, opts.push !== false);
        } catch (err) {
            // No network and no cache — do a real navigation as last resort
            this.cancelSkeleton();
            this.navigating = false;
            if ((opts.method || 'GET') === 'GET') location.href = href;
            return;
        }
        this.navigating = false;
    },

    render(html, url, push) {
        this.cancelSkeleton();
        const doc = new DOMParser().parseFromString(html, 'text/html');

        // Merge page-specific head assets (print styles, jsPDF, QR library…)
        doc.querySelectorAll('head link[rel="stylesheet"], head style, head script[src]').forEach((node) => {
            const key = node.src || node.href;
            if (key) {
                const path = new URL(key, location.href).pathname;
                if (this.loadedAssets.has(path)) return;
                this.loadedAssets.add(path);
            }
            document.head.appendChild(this.executable(node));
        });

        document.title = doc.title;
        document.body.innerHTML = doc.body.innerHTML;

        // innerHTML never executes scripts — replace each with a live clone
        document.body.querySelectorAll('script').forEach((old) => {
            if (old.src) {
                const path = new URL(old.src, location.href).pathname;
                if (this.loadedAssets.has(path)) { old.remove(); return; }
                this.loadedAssets.add(path);
            }
            old.replaceWith(this.executable(old));
        });

        if (push && url !== location.href) history.pushState({}, '', url);
        else if (push) history.replaceState({}, '', url);
        window.scrollTo(0, 0);
        document.dispatchEvent(new Event('page:load'));
    },

    executable(node) {
        if (node.tagName !== 'SCRIPT') return node.cloneNode(true);
        const s = document.createElement('script');
        [...node.attributes].forEach((a) => s.setAttribute(a.name, a.value));
        s.textContent = node.textContent;
        return s;
    },

    // Skeleton shimmer — only appears if a screen takes longer than 150ms
    // (cached screens swap instantly and never show it)
    scheduleSkeleton() {
        this.skeletonTimer = setTimeout(() => {
            if (document.getElementById('skeleton-overlay')) return;
            const el = document.createElement('div');
            el.id = 'skeleton-overlay';
            el.innerHTML = '<div class="sk-bar sk-header"></div>' +
                           '<div class="sk-bar sk-card"></div>' +
                           '<div class="sk-bar sk-card"></div>' +
                           '<div class="sk-bar sk-line"></div>' +
                           '<div class="sk-bar sk-line short"></div>';
            document.body.appendChild(el);
        }, 150);
    },

    cancelSkeleton() {
        clearTimeout(this.skeletonTimer);
        const el = document.getElementById('skeleton-overlay');
        if (el) el.remove();
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    SmartWorker.init();
    NativeShell.init();
});

// Expose SmartWorker globally for use in templates
window.SmartWorker = SmartWorker;

// Service Worker registration disabled for now
// Will be enabled when PWA support is needed

// Additional utility functions for specific pages
window.togglePassword = function(fieldId) {
    const field = document.getElementById(fieldId);
    const eye = document.getElementById(fieldId + '-eye');
    
    if (field.type === 'password') {
        field.type = 'text';
        eye.classList.remove('fa-eye');
        eye.classList.add('fa-eye-slash');
    } else {
        field.type = 'password';
        eye.classList.remove('fa-eye-slash');
        eye.classList.add('fa-eye');
    }
};

// Export data function
window.exportData = function() {
    if (confirm('Export all worker and attendance data?')) {
        const link = document.createElement('a');
        link.href = '/export_data';
        link.download = `smartworker_data_${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
};

// Print function
window.printElement = function(elementId) {
    const element = document.getElementById(elementId);
    const printWindow = window.open('', '_blank');
    printWindow.document.write(`
        <html>
            <head>
                <title>SmartWorker - Print</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; }
                    .no-print { display: none !important; }
                </style>
            </head>
            <body>
                ${element.outerHTML}
            </body>
        </html>
    `);
    printWindow.document.close();
    printWindow.print();
};
