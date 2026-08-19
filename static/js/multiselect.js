/* ==========================================================================
 * MultiSelect — one reusable selection layer for every list in the app.
 *
 * Screens do not write JavaScript. They declare markup and this file does
 * the rest:
 *
 *   <div data-ms-scope="workers" data-ms-noun="worker">
 *       <div data-ms-item="12" data-ms-label="Ravi Kumar"> ... </div>
 *   </div>
 *   {% include '_selection_bar.html' %}   <- renders [data-ms-bar="workers"]
 *
 * Everything is delegated from `document`, for two reasons. The SPA engine in
 * app.js replaces document.body.innerHTML on every navigation, so listeners
 * bound to individual rows would die on the first screen change. And a single
 * delegated listener costs the same whether the list holds 10 rows or 10,000
 * — there is no per-row setup to pay for.
 *
 * Interaction contract (see the UX notes in each handler):
 *   long-press an item   -> enter selection mode with that item selected
 *   tap an item          -> toggle it, but only while selection mode is on;
 *                           otherwise the row's normal link/tap still works
 *   Cancel               -> leave selection mode, clear everything
 * ========================================================================== */
(function () {
    'use strict';

    var LONG_PRESS_MS = 450;
    var MOVE_TOLERANCE = 10;   // px of finger drift that still counts as a press

    var MultiSelect = {
        scope: null,           // active scope name, or null when idle
        pending: null,         // action button waiting on a picker dialog
        pushedState: false,    // we own one history entry while selecting
        swallowPop: false,     // set when we retire that entry ourselves
        selected: new Set(),   // ids (as strings) in the active scope
        busy: false,

        /* ---- element lookup ------------------------------------------- */

        container: function (scope) {
            return document.querySelector('[data-ms-scope="' + scope + '"]');
        },

        bar: function (scope) {
            return document.querySelector('[data-ms-bar="' + scope + '"]');
        },

        items: function (scope) {
            var box = this.container(scope);
            return box ? Array.prototype.slice.call(box.querySelectorAll('[data-ms-item]')) : [];
        },

        /* ---- state ----------------------------------------------------- */

        enter: function (scope) {
            if (this.scope === scope) return;
            if (this.scope) this.exit();
            this.scope = scope;
            this.selected.clear();
            var box = this.container(scope);
            if (box) box.classList.add('ms-on');
            document.body.classList.add('ms-active');
            var bar = this.bar(scope);
            if (bar) {
                // #mobile-app carries a transform, which makes it the
                // containing block for position:fixed — a bar left inside it
                // anchors to the app column instead of the viewport and ends
                // up below the fold. The app's own bottom nav sits outside
                // #mobile-app for exactly this reason; move the bar there too.
                if (bar.parentElement !== document.body) document.body.appendChild(bar);
                bar.hidden = false;
            }
            // Give the system Back button something to consume, so it exits
            // selection mode instead of leaving the screen. app.js checks
            // this state before it treats a pop as navigation.
            if (!this.pushedState) {
                try { history.pushState({ ms: 1 }, '', location.href); this.pushedState = true; }
                catch (e) { this.pushedState = false; }
            }
        },

        exit: function (fromPop) {
            this.closePrompt();
            if (!this.scope) return;
            var box = this.container(this.scope);
            if (box) {
                box.classList.remove('ms-on');
                box.querySelectorAll('[data-ms-item].ms-picked').forEach(function (el) {
                    el.classList.remove('ms-picked');
                });
            }
            var bar = this.bar(this.scope);
            if (bar) bar.hidden = true;
            document.body.classList.remove('ms-active');
            this.scope = null;
            this.selected.clear();
            // Cancel/action exits leave our history entry behind, so step off
            // it. fromPop means the entry is already gone.
            if (this.pushedState) {
                this.pushedState = false;
                if (!fromPop && !this.leavingPage) {
                    this.swallowPop = true;
                    history.back();
                }
            }
        },

        toggle: function (el) {
            var id = el.getAttribute('data-ms-item');
            if (this.selected.has(id)) {
                this.selected.delete(id);
                el.classList.remove('ms-picked');
            } else {
                this.selected.add(id);
                el.classList.add('ms-picked');
            }
            // Deselecting the last row leaves selection mode, so a mis-tap
            // does not strand the user in a mode with nothing selected.
            if (!this.selected.size) { this.exit(); return; }
            this.refresh();
        },

        selectAll: function () {
            var self = this;
            var all = this.items(this.scope);
            var everything = all.length && all.every(function (el) {
                return self.selected.has(el.getAttribute('data-ms-item'));
            });
            all.forEach(function (el) {
                var id = el.getAttribute('data-ms-item');
                if (everything) { self.selected.delete(id); el.classList.remove('ms-picked'); }
                else { self.selected.add(id); el.classList.add('ms-picked'); }
            });
            if (!this.selected.size) { this.exit(); return; }
            this.refresh();
        },

        /* ---- bar rendering ---------------------------------------------- */

        refresh: function () {
            var bar = this.bar(this.scope);
            if (!bar) return;
            var box = this.container(this.scope);
            var n = this.selected.size;
            var noun = (box && box.getAttribute('data-ms-noun')) || 'item';
            var plural = (box && box.getAttribute('data-ms-plural')) || (noun + 's');

            var count = bar.querySelector('[data-ms-count]');
            if (count) count.textContent = n + ' ' + (n === 1 ? noun : plural) + ' selected';

            var total = this.items(this.scope).length;
            var all = bar.querySelector('[data-ms-selectall]');
            if (all) all.textContent = (n === total && total > 0) ? 'Clear all' : 'Select all';

            // An action can require a minimum selection (data-ms-min) — used
            // by actions that only make sense on one record at a time.
            bar.querySelectorAll('[data-ms-action]').forEach(function (btn) {
                var max = parseInt(btn.getAttribute('data-ms-max') || '0', 10);
                btn.disabled = !n || (max > 0 && n > max);
            });
        },

        /* ---- submitting -------------------------------------------------- */

        /* Some actions need input before they can run — "assign to which
         * site?". The button points at a dialog with data-ms-prompt; the
         * fields inside it (data-ms-field) become extra POST params. This
         * stays generic so any screen can attach a picker to any action. */
        prompt: function (btn) {
            var dialog = document.querySelector(btn.getAttribute('data-ms-prompt'));
            if (!dialog) { this.run(btn); return; }
            this.pending = btn;
            dialog.classList.remove('hidden');
            dialog.hidden = false;
        },

        closePrompt: function () {
            if (!this.pending) return;
            var dialog = document.querySelector(this.pending.getAttribute('data-ms-prompt'));
            if (dialog) { dialog.classList.add('hidden'); dialog.hidden = true; }
            this.pending = null;
        },

        confirmPrompt: function () {
            var btn = this.pending;
            if (!btn) return;
            var dialog = document.querySelector(btn.getAttribute('data-ms-prompt'));
            var extra = {};
            if (dialog) {
                dialog.querySelectorAll('[data-ms-field]').forEach(function (field) {
                    extra[field.getAttribute('data-ms-field')] = field.value;
                });
            }
            this.closePrompt();
            this.run(btn, extra);
        },

        run: function (btn, extra) {
            if (this.busy || !this.scope || !this.selected.size) return;
            var scope = this.scope;
            var box = this.container(scope);
            var bar = this.bar(scope);
            var action = btn.getAttribute('data-ms-action');
            var ids = Array.from(this.selected);
            var n = ids.length;
            var noun = (box && box.getAttribute('data-ms-noun')) || 'item';
            var plural = (box && box.getAttribute('data-ms-plural')) || (noun + 's');

            // Destructive actions confirm before touching anything.
            var ask = btn.getAttribute('data-ms-confirm');
            if (ask) {
                ask = ask.replace('%n', n).replace('%s', n === 1 ? noun : plural);
                if (!window.confirm(ask)) return;
            }

            var endpoint = (bar && bar.getAttribute('data-ms-endpoint'))
                        || (box && box.getAttribute('data-ms-endpoint'));
            if (!endpoint) return;

            var body = new FormData();
            body.append('action', action);
            ids.forEach(function (id) { body.append('ids', id); });
            var token = document.querySelector('meta[name="csrf-token"]');
            if (token) body.append('csrf_token', token.getAttribute('content'));

            // Screens pass extra context (the attendance date, the payroll
            // month/year) as data-ms-param-* on the bar.
            if (bar) {
                Array.prototype.forEach.call(bar.attributes, function (attr) {
                    if (attr.name.indexOf('data-ms-param-') === 0) {
                        body.append(attr.name.slice('data-ms-param-'.length), attr.value);
                    }
                });
                // Some actions carry their own extra field, e.g. a target
                // status chosen on the button itself.
                Array.prototype.forEach.call(btn.attributes, function (attr) {
                    if (attr.name.indexOf('data-ms-param-') === 0) {
                        body.append(attr.name.slice('data-ms-param-'.length), attr.value);
                    }
                });
            }
            // Values collected from a picker dialog, if this action used one.
            Object.keys(extra || {}).forEach(function (key) {
                body.append(key, extra[key]);
            });

            this.busy = true;
            if (bar) bar.classList.add('ms-busy');

            var self = this;
            fetch(endpoint, { method: 'POST', body: body, credentials: 'same-origin',
                              headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function (res) { return res.json().catch(function () { return null; }); })
                .then(function (data) {
                    self.busy = false;
                    if (bar) bar.classList.remove('ms-busy');
                    if (!data) { self.toast('Something went wrong. Please try again.', 'error'); return; }
                    (data.messages || []).forEach(function (m) { self.toast(m.text, m.category); });
                    self.exit();
                    // Re-fetch the screen so every derived figure on it — counts,
                    // totals, status pills — reflects what just changed.
                    if (data.success !== false) self.reload();
                })
                .catch(function () {
                    self.busy = false;
                    if (bar) bar.classList.remove('ms-busy');
                    self.toast('Network error. Nothing was changed.', 'error');
                });
        },

        reload: function () {
            if (window.NativeShell && typeof window.NativeShell.visit === 'function') {
                window.NativeShell.visit(location.href, { push: false });
            } else {
                location.reload();
            }
        },

        toast: function (text, category) {
            if (!text) return;
            var host = document.getElementById('ms-toasts');
            if (!host) {
                host = document.createElement('div');
                host.id = 'ms-toasts';
                document.body.appendChild(host);
            }
            var el = document.createElement('div');
            el.className = 'ms-toast ms-toast-' + (category || 'info');
            el.textContent = text;
            host.appendChild(el);
            setTimeout(function () {
                el.classList.add('ms-toast-out');
                setTimeout(function () { el.remove(); }, 250);
            }, 3200);
        }
    };

    /* ====================== event wiring (delegated) ====================== */

    var press = { timer: null, el: null, x: 0, y: 0, fired: false };

    function clearPress() {
        if (press.timer) clearTimeout(press.timer);
        press.timer = null;
        if (press.el) press.el.classList.remove('ms-pressing');
        press.el = null;
    }

    function itemOf(target) {
        var el = target.closest && target.closest('[data-ms-item]');
        if (!el) return null;
        // An item only participates if it sits inside a declared scope.
        return el.closest('[data-ms-scope]') ? el : null;
    }

    function startPress(e, point) {
        var el = itemOf(e.target);
        if (!el) return;
        // Already selecting: a plain tap toggles, no long press needed.
        if (MultiSelect.scope) return;
        press.el = el;
        press.x = point.clientX;
        press.y = point.clientY;
        press.fired = false;
        el.classList.add('ms-pressing');
        press.timer = setTimeout(function () {
            press.fired = true;
            var scope = el.closest('[data-ms-scope]').getAttribute('data-ms-scope');
            el.classList.remove('ms-pressing');
            MultiSelect.enter(scope);
            MultiSelect.toggle(el);
            if (navigator.vibrate) navigator.vibrate(18);
        }, LONG_PRESS_MS);
    }

    function movePress(point) {
        if (!press.timer) return;
        if (Math.abs(point.clientX - press.x) > MOVE_TOLERANCE ||
            Math.abs(point.clientY - press.y) > MOVE_TOLERANCE) clearPress();
    }

    document.addEventListener('touchstart', function (e) {
        if (e.touches.length !== 1) { clearPress(); return; }
        startPress(e, e.touches[0]);
    }, { passive: true });

    document.addEventListener('touchmove', function (e) {
        if (e.touches.length) movePress(e.touches[0]);
    }, { passive: true });

    document.addEventListener('touchend', clearPress, { passive: true });
    document.addEventListener('touchcancel', clearPress, { passive: true });

    // Desktop parity: press-and-hold with the mouse behaves the same way.
    document.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return;
        startPress(e, e);
    });
    document.addEventListener('mousemove', function (e) { movePress(e); });
    document.addEventListener('mouseup', clearPress);

    // A long press on mobile raises the context menu; suppress it on items so
    // the gesture reads as "select", not "copy text".
    document.addEventListener('contextmenu', function (e) {
        if (itemOf(e.target)) e.preventDefault();
    });

    document.addEventListener('click', function (e) {
        // Swallow the click that the browser fires right after a long press.
        if (press.fired) { press.fired = false; e.preventDefault(); e.stopPropagation(); return; }

        // Picker dialog for actions that need a target chosen first.
        if (e.target.closest && e.target.closest('[data-ms-prompt-ok]')) {
            e.preventDefault(); MultiSelect.confirmPrompt(); return;
        }
        if (e.target.closest && e.target.closest('[data-ms-prompt-cancel]')) {
            e.preventDefault(); MultiSelect.closePrompt(); return;
        }

        var bar = e.target.closest && e.target.closest('[data-ms-bar]');
        if (bar) {
            if (e.target.closest('[data-ms-cancel]')) { e.preventDefault(); MultiSelect.exit(); return; }
            if (e.target.closest('[data-ms-selectall]')) { e.preventDefault(); MultiSelect.selectAll(); return; }
            var act = e.target.closest('[data-ms-action]');
            if (act) {
                e.preventDefault();
                if (act.hasAttribute('data-ms-prompt')) MultiSelect.prompt(act);
                else MultiSelect.run(act);
                return;
            }
            return;
        }

        if (!MultiSelect.scope) return;   // idle: normal navigation, untouched

        var el = itemOf(e.target);
        if (!el) return;
        // In selection mode the whole row is a checkbox — links and buttons
        // inside it must not navigate or submit.
        e.preventDefault();
        e.stopPropagation();
        MultiSelect.toggle(el);
    }, true);

    // System Back: leave selection mode, stay on the screen.
    window.addEventListener('popstate', function () {
        if (MultiSelect.scope) MultiSelect.exit(true);
    });

    // Escape is the keyboard equivalent of Cancel.
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && MultiSelect.scope) MultiSelect.exit();
    });

    // Every SPA swap replaces the list that was being selected from, so the
    // selection cannot survive it.
    document.addEventListener('page:before-swap', function () {
        // A genuine navigation is under way; drop the selection without
        // rewinding history, or we would cancel the navigation itself.
        MultiSelect.leavingPage = true;
        MultiSelect.exit(true);
        MultiSelect.leavingPage = false;
    });
    document.addEventListener('page:load', function () { clearPress(); });

    window.MultiSelect = MultiSelect;
})();
