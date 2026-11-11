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
            
            return new Date(date).toLocaleDateString('en-IN', options[format]);
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
            // app-toast is what the close button climbs to. It used to walk
            // up two parentElements from an inline onclick; naming the root
            // means the dismissal survives a change to the markup inside.
            toast.className = `app-toast fixed top-4 right-4 z-50 p-4 rounded-lg shadow-lg max-w-sm ${this.getToastClass(type)} slide-up`;
            toast.innerHTML = `
                <div class="flex items-center justify-between">
                    <div class="flex items-center">
                        <i class="fa-solid ${this.getToastIcon(type)} mr-2"></i>
                        <span>${message}</span>
                    </div>
                    <button data-act="remove-closest" data-act-target=".app-toast" class="ml-4 text-current opacity-70 hover:opacity-100">
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
        
        // Notification permission used to be asked for here, on every
        // first page view. The app never shows a notification, so the
        // prompt asked for something it did not use; it is gone.
    }
};

// ── Interface language ───────────────────────────────────────
// The language lives in the server session, so the only thing the client has
// to do is keep <html lang> honest and throw away pages the service worker
// cached in the previous language.
function applyLanguage(lang) {
    const root = document.documentElement;
    if (root.getAttribute('lang') === lang) return;
    root.setAttribute('lang', lang);
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage({ type: 'purge-pages' });
    }
}

// ── NativeShell: SPA navigation engine ───────────────────────
// The WebView loads the document exactly once. Every link tap and form
// submit afterwards is fetched over XHR and the new screen is swapped into
// the live document — no full page reloads, no browser loading indicator,
// no white flash. Combined with the service worker cache this makes screen
// changes effectively instant, like a native Android activity switch.
const NativeShell = {
    loadedAssets: new Set(),
    navigating: false,

    // The one piece of the document that survives a screen change.
    NAV: 'nav.app-bottom-nav',

    PRELOAD_SCREENS: ['/dashboard', '/workers', '/attendance', '/payroll',
                      '/transactions', '/assignments', '/settings',
                      '/notifications', '/closures', '/profile'],

    init() {
        // Remember assets already in the document so swaps never re-run them
        document.querySelectorAll('script[src]').forEach((s) =>
            this.loadedAssets.add(new URL(s.src, location.href).pathname));
        document.querySelectorAll('link[rel="stylesheet"]').forEach((l) =>
            this.loadedAssets.add(new URL(l.href, location.href).pathname));
        // The <style> blocks this page came with. render() keeps this set in
        // step with each screen; a style a library adds later is not ours
        // and is left alone.
        document.querySelectorAll('head style').forEach((st) => {
            st.setAttribute('data-page-style', '');
        });

        document.addEventListener('click', (e) => this.onClick(e));
        document.addEventListener('submit', (e) => this.onSubmit(e));
        window.addEventListener('popstate', () => {
            // Back while multi-selection is active means "leave selection
            // mode", not "leave the screen" — the same convention Android
            // list apps use. MultiSelect pushed a history entry when it
            // opened; it consumes this pop itself, so skip navigating.
            var ms = window.MultiSelect;
            if (ms && (ms.scope || ms.swallowPop)) { ms.swallowPop = false; return; }
            this.visit(location.href, { push: false });
        });
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

    /* Where the reader had got to on the screen they are leaving.
     *
     * Written onto the history entry itself rather than a side table, so it
     * travels with the entry: the browser hands it straight back on the pop
     * that returns here, and a reload or a restored tab does not resurrect
     * a position from some other visit.
     */
    saveScroll() {
        try {
            history.replaceState(
                Object.assign({}, history.state, { y: window.scrollY }),
                '', location.href);
        } catch (_) { /* a history that will not take state is not fatal */ }
    },

    async visit(href, opts = {}) {
        if (this.navigating) return;
        this.navigating = true;
        // Before anything is fetched: once the body is replaced the old
        // scroll position is unrecoverable.
        if (opts.push !== false) this.saveScroll();
        this.back = opts.push === false;
        document.dispatchEvent(new Event('page:before-swap'));
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
            this.navigating = false;
            if ((opts.method || 'GET') === 'GET') location.href = href;
            return;
        }
        this.navigating = false;
    },

    render(html, url, push) {
        const doc = new DOMParser().parseFromString(html, 'text/html');

        // Merge page-specific head assets (jsPDF, QR library…)
        doc.querySelectorAll('head link[rel="stylesheet"], head script[src]').forEach((node) => {
            const key = node.src || node.href;
            if (key) {
                const path = new URL(key, location.href).pathname;
                if (this.loadedAssets.has(path)) return;
                this.loadedAssets.add(path);
            }
            document.head.appendChild(this.executable(node));
        });

        // A screen's own <style> leaves with it. They used to be added and
        // never removed, so every screen visited went on styling every
        // screen after it: Home's .att-row (a table grid) landed on the
        // Attendance header and put the closure-days button on top of the
        // title. The head now holds exactly the styles the incoming screen
        // was written with, as it would after a full load.
        const wanted = new Map();
        doc.querySelectorAll('head style').forEach((st) => wanted.set(st.textContent, st));
        document.querySelectorAll('head style[data-page-style]').forEach((st) => {
            if (wanted.has(st.textContent)) wanted.delete(st.textContent);
            else st.remove();
        });
        wanted.forEach((st) => {
            const copy = this.executable(st);
            copy.setAttribute('data-page-style', '');
            document.head.appendChild(copy);
        });

        document.title = doc.title;

        // Only the body is swapped, so <html lang> would keep whatever the
        // first full load set. Carry it over: a language switch is an ordinary
        // POST + redirect through here, and screen readers and the font
        // fallback both pick Devanagari off this attribute.
        const incomingLang = doc.documentElement.getAttribute('lang');
        if (incomingLang) applyLanguage(incomingLang);

        // The scripts as the parser produced them. Chrome blanks the nonce
        // attribute on any element that reaches a document — and strips it
        // outright from one created through innerHTML — so the copies about
        // to appear in the page carry nonce="". These still have their
        // attributes intact, which keeps the clone below honest. The nonce
        // it ends up with comes from pageNonce(), not from here: see there
        // for why the fetched page's own nonce is the wrong one to use.
        const incoming = [...doc.body.querySelectorAll('script')];

        // The tab bar outlives the screen. Replacing the body destroys it
        // and builds a new one, which is how a native-looking app gives
        // itself away: the bar blinks, its press animation restarts, and
        // the active tab arrives already lit instead of lighting up. Holding
        // a reference keeps the live node alive while it is detached, so the
        // same element — with its CSS state and its listeners — goes back in
        // afterwards and only its highlight changes.
        const keptNav = document.querySelector(this.NAV);

        document.body.innerHTML = doc.body.innerHTML;

        const freshNav = document.querySelector(this.NAV);
        if (keptNav && freshNav) {
            this.syncNav(freshNav, keptNav);
            freshNav.replaceWith(keptNav);
        }

        // innerHTML never executes scripts — replace each with a live clone.
        document.body.querySelectorAll('script').forEach((old, i) => {
            const source = incoming[i] || old;
            if (old.src) {
                const path = new URL(old.src, location.href).pathname;
                if (this.loadedAssets.has(path)) { old.remove(); return; }
                this.loadedAssets.add(path);
            }
            old.replaceWith(this.executable(source));
        });

        if (push && url !== location.href) history.pushState({}, '', url);
        else if (push) history.replaceState({}, '', url);

        // Going back puts the reader where they were; going forward starts
        // at the top. A list you had scrolled half way down and must scroll
        // again after a glance at one row is the clearest sign that these
        // are pages and not screens.
        const y = (!push && history.state && history.state.y) || 0;
        window.scrollTo(0, y);

        this.animate(this.back);
        document.dispatchEvent(new Event('page:load'));
    },

    /* Push forward, pop backward.
     *
     * The same arrival animation in both directions reads as a page that
     * re-rendered. Which way the screen comes from is the cue that says
     * whether you went somewhere or came back, and it is the cue people
     * read without noticing they are reading it.
     *
     * Set as a class rather than in the CSS for #mobile-app, so the rule
     * can be dropped whole under prefers-reduced-motion.
     */
    animate(back) {
        const screen = document.getElementById('mobile-app');
        if (!screen) return;
        screen.classList.add(back ? 'screen-pop' : 'screen-push');
    },

    /* Move the highlight from one tab to another, and nothing else.
     *
     * Which tab is lit is decided server-side — a worker profile lights
     * Workers, a payslip lights Payroll — so the answer is read off the
     * freshly rendered bar rather than worked out again here. Only the two
     * active classes are touched: anything else the live bar is carrying
     * (a press, a transition in flight) is left alone, which is the whole
     * point of keeping it.
     */
    syncNav(fresh, live) {
        const ACTIVE = ['app-nav-item-active', 'app-nav-fab-active'];
        const want = new Map();
        fresh.querySelectorAll('a[href]').forEach((a) =>
            want.set(a.getAttribute('href'),
                     ACTIVE.filter((c) => a.classList.contains(c))));
        live.querySelectorAll('a[href]').forEach((a) => {
            const on = want.get(a.getAttribute('href'));
            // A tab the new bar does not have at all: leave it as it is
            // rather than guess. The bar's shape only changes with the
            // user's role, and that cannot change without a fresh document.
            if (!on) return;
            ACTIVE.forEach((c) => a.classList.toggle(c, on.includes(c)));
        });
    },

    /* The nonce this document was served with.
     *
     * Not the one on the page being navigated to. The browser enforces the
     * Content-Security-Policy header of the document that is open, and that
     * header named a nonce minted for that one request; a script carrying
     * the *fetched* page's nonce is refused, because as far as the open
     * document is concerned it is an unknown value. So every re-created
     * script has to be stamped with the open document's own nonce.
     *
     * Read from the property rather than the attribute: browsers blank the
     * attribute once an element is in a document — nonce hiding, so that
     * markup an attacker injects cannot read a nonce off a neighbour. The
     * property stays readable to first-party code like this, which is
     * already running and could do anything it liked anyway.
     */
    pageNonce() {
        // Parked on window by base.html while this document was parsed, and
        // so still correct after the body has been replaced — every element
        // that carried the nonce is gone by then.
        return window.__swNonce || '';
    },

    executable(node) {
        if (node.tagName !== 'SCRIPT') return node.cloneNode(true);
        const s = document.createElement('script');
        [...node.attributes].forEach((a) => s.setAttribute(a.name, a.value));
        if (!node.src) {
            const nonce = this.pageNonce();
            if (nonce) s.nonce = nonce;
        }
        s.textContent = node.textContent;
        return s;
    },

    /* Nothing is drawn while a screen is on its way.
     *
     * Two things were tried here and both are gone. First a full-screen
     * grey skeleton after 150ms, which covered a perfectly readable screen
     * in placeholder for a tenth of a second — that flash IS the feeling of
     * a page loading. Then a blue hairline at the top, after 110ms and
     * later 500ms, as an acknowledgement that the tap had registered.
     *
     * The hairline had the same fault as the skeleton, just thinner. Every
     * screen in this app is an HTTP request to the host: the server answers
     * in 12–141ms measured on localhost and the network adds 300–600ms on
     * top, so the bar was on screen for most of most navigations. A loading
     * indicator that is nearly always visible is not an indicator, it is
     * the app's resting state — and a resting state that looks like
     * loading is exactly the "buffering" feeling this was meant to avoid.
     * Raising the delay only made it appear slightly less often.
     *
     * So the acknowledgement is the one a native app gives: the control
     * itself responds under the finger. .app-nav-item:active and
     * .app-nav-fab:active in custom.css dim and scale on touch, with no
     * delay at all because they are CSS, and the screen being left stays up
     * and readable until the next one is ready to replace it.
     *
     * If a wait is long enough to need explaining, the honest fix is a
     * faster host, not a bar that says so.
     */

    // Android hardware Back. Cordova's default is to exit the app the moment
    // there is nothing left in history, so one stray tap on the dashboard
    // closes SmartWorker with no warning and no chance to undo. Give the user
    // the usual "press again to exit" grace period instead, and let selection
    // mode and open dialogs consume the press first.
    initAndroidBack() {
        if (this._backHooked) return;
        this._backHooked = true;
        let armed = 0;
        document.addEventListener('backbutton', (e) => {
            e.preventDefault();

            // 1. Selection mode owns Back before anything else.
            const ms = window.MultiSelect;
            if (ms && ms.scope) { ms.exit(true); return; }

            // 2. Any visible dialog closes first — closed the same way the
            //    app itself closes it, so it can be reopened afterwards.
            //    Multi-select prompts toggle both the .hidden class and the
            //    attribute; ordinary modals toggle only the class, and setting
            //    the attribute on those would wedge them shut for good.
            const shown = (el) => !!el && el.getBoundingClientRect().width > 0;

            const prompt = document.querySelector('.ms-prompt:not(.hidden)');
            if (shown(prompt)) {
                if (ms && ms.pending) ms.closePrompt();
                else { prompt.classList.add('hidden'); prompt.hidden = true; }
                return;
            }

            const modal = document.querySelector('[id$="-modal"]:not(.hidden)');
            if (shown(modal)) { modal.classList.add('hidden'); return; }

            // 3. Somewhere to go back to — go there.
            if (history.length > 1) { history.back(); return; }

            // 4. At the root: confirm before leaving.
            if (Date.now() - armed < 2000) {
                if (navigator.app && navigator.app.exitApp) navigator.app.exitApp();
                return;
            }
            armed = Date.now();
            if (window.MultiSelect && typeof window.MultiSelect.toast === 'function') {
                window.MultiSelect.toast('Press back again to exit', 'info');
            }
        }, false);
    }
};

// ---------------------------------------------------------------------------
// The bottom bar steps aside while the keyboard is up.
//
// The bar is position:fixed; bottom:0. Android's WebView opens the keyboard
// with windowSoftInputMode=adjustResize, which shortens the viewport by the
// height of the keyboard — so "the bottom" moves up, and the bar rides up
// with it and parks itself on top of the keys, over the field being typed
// into. Nothing is animating it; it is sitting exactly where it was told to.
//
// So it is hidden while a text field has focus. Nobody needs to change
// screens mid-word, and this is the one behaviour that is the same in the
// WebView, in Chrome and on a desktop, without touching the Cordova shell
// (which would mean a new APK, where this reaches the phone from the server).
//
// Listeners are on `document` and delegated: NativeShell.visit() replaces
// document.body.innerHTML, so anything bound to an element inside it would
// be gone after the first navigation.
//
// The clearance padding on #mobile-app stays as it is. Removing it with the
// bar would reflow the page underneath the keyboard, moving the field the
// user is typing into — which is the one thing worse than a misplaced bar.
const KeyboardAware = {
    TEXTUAL: new Set(['text', 'password', 'email', 'number', 'tel', 'search',
                      'url', 'date', 'time', 'datetime-local', 'month']),

    isTextual(el) {
        if (!el) return false;
        const tag = el.tagName;
        if (tag === 'TEXTAREA') return true;
        if (el.isContentEditable) return true;
        // A <select> opens a picker, not a keyboard, on both platforms.
        if (tag !== 'INPUT') return false;
        return this.TEXTUAL.has((el.type || 'text').toLowerCase());
    },

    set(open) {
        document.body.classList.toggle('kb-open', !!open);
    },

    init() {
        document.addEventListener('focusin', (e) => {
            if (this.isTextual(e.target)) this.set(true);
        });
        document.addEventListener('focusout', () => {
            // Deferred, and then asked what actually has focus: tabbing from
            // one field to the next fires focusout before focusin, so acting
            // on it directly flickers the bar back for a frame between two
            // boxes on the same form.
            setTimeout(() => this.set(this.isTextual(document.activeElement)), 0);
        });
        // A screen change ends any typing, and the class lives on <body>,
        // which survives the innerHTML swap that the rest of it does not.
        document.addEventListener('page:load', () => this.set(false));
    },
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    SmartWorker.init();
    NativeShell.init();
    // Inside the app, Back is only routed to the page once Cordova has
    // finished starting; registering earlier can leave Android's default
    // (close the app) in charge.
    if (window.cordova) {
        document.addEventListener('deviceready', () => NativeShell.initAndroidBack(), { once: true });
        // window.print() is a no-op in an Android WebView: every Print button
        // (payslip, worker report) did nothing in the app. Route it to
        // Android's print service, which also offers "Save as PDF".
        document.addEventListener('deviceready', () => {
            // Read by the Print buttons: with this set they call window.print;
            // without it (an APK built before the bridge's print action) they
            // open the PDF in a viewer instead.
            window.SmartWorkerNativePrint = true;
            window.print = () => {
                window.dispatchEvent(new Event('beforeprint'));
                window.cordova.exec(() => window.dispatchEvent(new Event('afterprint')),
                    (err) => console.error('Print failed', err),
                    'RemoteBridge', 'print', [document.title || 'SmartWorker']);
            };
        }, { once: true });
    } else {
        NativeShell.initAndroidBack();
    }
    KeyboardAware.init();
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

// (The old window.exportData lived here. It shadowed profile.html's own
//  exportData() — this file loads last — so the Export button always ran the
//  <a download> version, which does nothing inside the Android WebView and
//  nothing at all once confirm() is dismissed. profile.html owns it now and
//  routes it through SmartWorkerSave.)

// (window.printElement lived here and was called from nowhere — grep the
//  whole repository and this definition is the only hit. It opened a popup
//  with window.open('', '_blank'), which an Android WebView returns null
//  for unless the native side implements onCreateWindow, so the next line
//  would have thrown on the one platform this app ships as. Printing goes
//  through the 'print' verb in actions.js, which knows about the WebView.)
