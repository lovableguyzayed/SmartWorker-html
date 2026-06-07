// SmartWorker Application JavaScript

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

// ── Native-feel page transition ──────────────────────────────
const NavProgress = {
    bar: null,
    timer: null,

    init() {
        this.bar = document.createElement('div');
        this.bar.id = 'nav-progress';
        document.body.prepend(this.bar);

        document.addEventListener('click', (e) => {
            const link = e.target.closest('a[href]');
            if (!link) return;
            const href = link.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('javascript')) return;
            if (link.target === '_blank') return;
            try {
                const url = new URL(href, window.location.origin);
                if (url.origin !== window.location.origin) return;
            } catch (_) { return; }
            this.start();
        });

        document.addEventListener('submit', () => this.start());
        window.addEventListener('pageshow', () => this.done());
    },

    start() {
        clearTimeout(this.timer);
        this.bar.style.opacity = '1';
        this.bar.style.width = '0%';
        // animate to 80% quickly, hold there until done
        requestAnimationFrame(() => {
            this.bar.style.transition = 'width 0.3s ease';
            this.bar.style.width = '75%';
        });
    },

    done() {
        this.bar.style.transition = 'width 0.15s ease';
        this.bar.style.width = '100%';
        this.timer = setTimeout(() => {
            this.bar.style.opacity = '0';
            setTimeout(() => { this.bar.style.width = '0%'; }, 250);
        }, 200);
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    SmartWorker.init();
    NavProgress.init();
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
