/* ==========================================================================
 * Actions — one delegated dispatcher, so no element needs an inline handler.
 *
 * A Content-Security-Policy worth having forbids `script-src 'unsafe-inline'`,
 * and that single directive is what stops an injected <script> or a crafted
 * attribute from running. But it does not distinguish our inline code from an
 * attacker's: an `onclick="showEditModal()"` written by us is blocked by
 * exactly the same rule. So the markup declares what it wants instead of how
 * to do it, and this file does it:
 *
 *     <button data-act="showEditModal">                 showEditModal(el, ev)
 *     <button data-act="bulkAction" data-act-args='["present"]'>
 *                                                       bulkAction('present', el, ev)
 *     <form   data-confirm="Delete this site?">         asks before submitting
 *     <select data-act="submit-form">                   submits the form it is in
 *
 * Arguments are JSON, parsed with JSON.parse. Nothing here evaluates a string
 * as code — no eval, no new Function, no setTimeout('...') — because a
 * dispatcher that did would hand back the hole the policy just closed, and
 * would need 'unsafe-eval' to run at all.
 *
 * Everything is delegated from `document`, for the same two reasons the
 * selection layer is: app.js replaces document.body.innerHTML on every
 * navigation, so listeners bound to individual elements would die on the
 * first screen change — and markup built in JavaScript after load, like the
 * attendance day view's panel, is covered without having to re-bind anything.
 * ========================================================================== */
(function () {
    'use strict';

    /* Verbs that belong to no page in particular. A page's own function is
     * looked up on window by name; these are the handful of things that were
     * written inline precisely because there was no function to call. */
    var VERBS = {
        /* <select data-act="submit-form"> — the filter selects that reload
         * the screen the moment you pick something. */
        'submit-form': function (el) {
            var form = el.form || (el.closest && el.closest('form'));
            if (form) form.submit();
        },

        /* The avatar picker: submit only once a file has actually been
         * chosen, so dismissing the file dialog does not post an empty form. */
        'submit-form-if-file': function (el) {
            if (!el.files || !el.files.length) return;
            var form = el.form || (el.closest && el.closest('form'));
            if (form) form.submit();
        },

        /* Dismiss the nearest enclosing thing — a flash toast, a modal.
         * data-act-target carries the selector to climb to. */
        'remove-closest': function (el) {
            var sel = el.getAttribute('data-act-target');
            var target = sel && el.closest ? el.closest(sel) : null;
            if (target) target.remove();
        },

        /* Dismiss something by id, for a panel that is not an ancestor. */
        'remove-target': function (el) {
            var target = document.getElementById(el.getAttribute('data-act-target'));
            if (target) target.remove();
        },

        /* Printing, on a platform that cannot print.
         *
         * window.print() is the right call in a browser. An Android
         * WebView does not implement it: printing there goes through the
         * native PrintManager, and nothing in the page can reach that. So
         * in the APK this verb did nothing at all — no dialog, no error,
         * no file — and the worker report's only control is a button
         * labelled "Save PDF" that calls it. A button that is silent is
         * indistinguishable from a broken app.
         *
         * A screen that can build its own PDF says so by defining
         * downloadPDF (see static/js/pdfpage.js). Inside the app that is
         * the route taken: the file is written with cordova-plugin-file
         * and handed to a viewer, and every Android PDF viewer can print.
         * A screen that cannot gets told so, rather than nothing. */
        'print': function () {
            var inApp = !!(window.cordova && window.cordova.file);
            if (inApp && typeof window.downloadPDF === 'function') {
                window.downloadPDF();
                return;
            }
            if (inApp) {
                window.alert('This device cannot print directly from the app. '
                           + 'Save the PDF and print it from there.');
                return;
            }
            window.print();
        }
    };

    function argsOf(el) {
        var raw = el.getAttribute('data-act-args');
        if (!raw) return [];
        try {
            var value = JSON.parse(raw);
            return Array.isArray(value) ? value : [value];
        } catch (e) {
            // A malformed attribute should cost one dead control, not the
            // whole screen, so fall through to calling with no arguments.
            return [];
        }
    }

    /* Call the named action. Page functions receive their declared arguments
     * first and then the element and the event, which is the order the inline
     * versions used — `bulkAction('present', this)` becomes
     * data-act-args='["present"]' and still arrives as (status, button). A
     * function that wants neither simply ignores the extra parameters. */
    function run(el, event) {
        var name = el.getAttribute('data-act');
        if (!name) return;
        var fn = VERBS[name] || window[name];
        if (typeof fn !== 'function') return;
        var result = fn.apply(null, argsOf(el).concat([el, event]));
        // `onsubmit="return foo()"` cancelled the submit by returning false.
        if (result === false && event.cancelable) event.preventDefault();
    }

    /* data-confirm asks before letting a submit through. It replaces
     * `onsubmit="return confirm('…')"`, which is how every destructive form
     * in the application used to guard itself. */
    function confirmed(el) {
        var question = el.getAttribute('data-confirm');
        return !question || window.confirm(question);
    }

    function closest(target, selector) {
        return target && target.closest ? target.closest(selector) : null;
    }

    document.addEventListener('click', function (event) {
        var el = closest(event.target, '[data-act]');
        if (!el) return;
        // A click-time confirmation, for a button that is not a submit.
        if (!confirmed(el)) { event.preventDefault(); return; }
        run(el, event);
    });

    document.addEventListener('change', function (event) {
        var el = closest(event.target, '[data-act]');
        // Only react to the element that changed, never to an ancestor that
        // happens to carry a click action of its own.
        if (el && el === event.target) run(el, event);
    });

    document.addEventListener('submit', function (event) {
        var form = closest(event.target, 'form');
        if (!form) return;
        if (!confirmed(form)) { event.preventDefault(); return; }
        if (form.hasAttribute('data-act')) run(form, event);
    }, true);   // capture, so the question is asked before anything else submits

    /* The font stylesheet is fetched as a preload and promoted to a real
     * stylesheet once it arrives, which used to be `onload="this.media='all'"`.
     * Same trick, no inline attribute. */
    function promote(link) {
        if (link.sheet) { link.media = 'all'; return; }
        link.addEventListener('load', function () { link.media = 'all'; });
    }
    function promoteAll() {
        var links = document.querySelectorAll('link[data-swap-media]');
        Array.prototype.forEach.call(links, promote);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', promoteAll);
    } else {
        promoteAll();
    }
    // app.js swaps the body on navigation; the head survives, but a freshly
    // served page runs this file again, so re-promoting is harmless.
    document.addEventListener('smartworker:navigated', promoteAll);
}());
