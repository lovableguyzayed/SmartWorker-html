/* Sign in / sign up screens (templates/login.html, templates/register.html).
 *
 * A file of its own rather than an inline block: the Content-Security-Policy
 * refuses inline handlers, and this way the page needs no nonce for it.
 * Safe to run twice (the app swaps screens without reloading), and it does
 * nothing on a page without these forms. */
(function () {
    'use strict';

    var $ = function (id) { return document.getElementById(id); };

    /* ---- show / hide password, on either screen ---- */
    document.querySelectorAll('.sw-eye').forEach(function (eye) {
        if (eye.dataset.wired) return;
        eye.dataset.wired = '1';
        eye.addEventListener('click', function () {
            var input = eye.parentElement.querySelector('input');
            var show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            eye.setAttribute('aria-label', show ? eye.dataset.labelHide : eye.dataset.labelShow);
            eye.querySelector('i').className = show ? 'fa-solid fa-eye-slash' : 'fa-solid fa-eye';
        });
    });

    /* ---- a busy button cannot be pressed twice ---- */
    function busy(btn, on) {
        if (!btn) return;
        btn.disabled = !!on;
        btn.setAttribute('aria-busy', on ? 'true' : 'false');
    }
    document.querySelectorAll('.sw-auth form[method="POST"]').forEach(function (form) {
        if (form.dataset.wired) return;
        form.dataset.wired = '1';
        form.addEventListener('submit', function () {
            // After the event, so the app's own submit handling still sees
            // an enabled form; the button only stops a second tap.
            var btn = form.querySelector('button[type=submit]');
            setTimeout(function () { busy(btn, true); }, 0);
            setTimeout(function () { busy(btn, false); }, 15000);
        });
    });

    /* ---- the OTP flow (only rendered when SMS is connected) ---- */
    var start = $('otp-start');
    if (!start || start.dataset.wired) return;
    start.dataset.wired = '1';

    var panels = ['otp-start', 'otp-code', 'otp-details', 'signin-form'];
    var mobile = '';
    var timer = null;

    function show(id) {
        panels.forEach(function (p) { if ($(p)) $(p).hidden = (p !== id); });
        var first = $(id) && $(id).querySelector('input:not([type=hidden])');
        if (first) setTimeout(function () { first.focus(); }, 50);
    }
    document.querySelectorAll('[data-show]').forEach(function (b) {
        b.addEventListener('click', function () { show(b.dataset.show); });
    });

    function say(id, text, kind) {
        var box = $(id);
        if (!box) return;
        box.hidden = !text;
        box.className = 'sw-msg ' + (kind || 'bad');
        box.textContent = text || '';
    }

    /* Same rule as the server: +91, 91, a leading 0, spaces and dashes all
     * fall away; what is left must be ten digits starting 6-9. */
    function indianMobile(value) {
        var d = (value || '').replace(/\D/g, '');
        if (d.length === 12 && d.indexOf('91') === 0) d = d.slice(2);
        else if (d.length === 11 && d.charAt(0) === '0') d = d.slice(1);
        return /^[6-9]\d{9}$/.test(d) ? d : '';
    }
    function pretty(d) { return '+91 ' + d.slice(0, 5) + ' ' + d.slice(5); }

    function post(url, body) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(body)
        }).then(function (res) {
            return res.json().catch(function () { return {}; }).then(function (data) {
                data.status = res.status;
                return data;
            });
        });
    }
    var offline = start.dataset.msgNetwork;

    /* 1. number -> code */
    var phoneInput = $('otp-mobile');
    phoneInput.addEventListener('input', function () {
        // A pasted "+91 98765-43210" becomes the ten digits right away.
        var d = indianMobile(phoneInput.value);
        if (d && phoneInput.value !== d) phoneInput.value = d;
        say('otp-start-msg', '');
    });

    function countdown(seconds) {
        clearInterval(timer);
        var left = seconds;
        $('otp-wait').hidden = false;
        $('otp-resend').hidden = true;
        var tick = function () {
            $('otp-timer').textContent = Math.floor(left / 60) + ':' + ('0' + (left % 60)).slice(-2);
            if (left-- <= 0) {
                clearInterval(timer);
                $('otp-wait').hidden = true;
                $('otp-resend').hidden = false;
            }
        };
        tick();
        timer = setInterval(tick, 1000);
    }

    function send() {
        var d = indianMobile(phoneInput.value);
        if (!d) {
            say('otp-start-msg', start.dataset.msgInvalid);
            phoneInput.setAttribute('aria-invalid', 'true');
            phoneInput.focus();
            return Promise.resolve(false);
        }
        phoneInput.removeAttribute('aria-invalid');
        var btn = $('otp-send-btn');
        busy(btn, true);
        return post(start.dataset.send, { mobile: d }).then(function (r) {
            busy(btn, false);
            if (!r.success) {
                say($('otp-code').hidden ? 'otp-start-msg' : 'otp-code-msg', r.message);
                if (r.retry_after && !$('otp-code').hidden) countdown(r.retry_after);
                return false;
            }
            mobile = d;
            $('otp-sent-to').textContent = pretty(d);
            $('otp-input').value = '';
            paint();
            say('otp-code-msg', '');
            show('otp-code');
            countdown(r.resend_after || 30);
            return true;
        }, function () {
            busy(btn, false);
            say($('otp-code').hidden ? 'otp-start-msg' : 'otp-code-msg', offline);
            return false;
        });
    }
    start.addEventListener('submit', function (e) { e.preventDefault(); send(); });
    $('otp-resend').addEventListener('click', function () { phoneInput.value = mobile; send(); });

    /* 2. the code: one input under six painted boxes */
    var codeInput = $('otp-input');
    var boxes = $('otp-boxes').querySelectorAll('.boxes span');
    function paint() {
        var v = codeInput.value;
        boxes.forEach(function (b, i) {
            b.textContent = v.charAt(i) || '';
            b.className = (i < v.length ? 'f' : '') + (i === Math.min(v.length, 5) && document.activeElement === codeInput ? ' cur' : '');
        });
        $('otp-boxes').classList.remove('bad');
    }
    codeInput.addEventListener('input', function () {
        codeInput.value = codeInput.value.replace(/\D/g, '').slice(0, 6);
        paint();
        say('otp-code-msg', '');
        // The SMS autofill drops all six digits at once: go straight on.
        if (codeInput.value.length === 6) verify();
    });
    codeInput.addEventListener('focus', paint);
    codeInput.addEventListener('blur', paint);

    var verifying = false;
    function verify() {
        if (verifying) return;
        if (codeInput.value.length !== 6) {
            say('otp-code-msg', start.dataset.msgCode);
            codeInput.focus();
            return;
        }
        verifying = true;
        var btn = $('otp-verify-btn');
        busy(btn, true);
        post(start.dataset.verify, { mobile: mobile, otp: codeInput.value }).then(function (r) {
            verifying = false;
            busy(btn, false);
            if (!r.success) {
                $('otp-boxes').classList.add('bad');
                say('otp-code-msg', r.message);
                codeInput.select();
                return;
            }
            if (r.new_user) {
                $('otp-verified-number').textContent = pretty(mobile);
                show('otp-details');
                return;
            }
            window.location.href = r.redirect_url || '/';
        }, function () {
            verifying = false;
            busy(btn, false);
            say('otp-code-msg', offline);
        });
    }
    $('otp-code').addEventListener('submit', function (e) { e.preventDefault(); verify(); });

    /* 3. first time: name, and that is all that is required */
    var details = $('otp-details');
    details.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = $('otp-details-btn');
        busy(btn, true);
        details.querySelectorAll('[aria-invalid]').forEach(function (el) { el.removeAttribute('aria-invalid'); });
        post(start.dataset.details, {
            full_name: $('d-name').value,
            business_name: $('d-business').value,
            email: $('d-email').value
        }).then(function (r) {
            busy(btn, false);
            if (!r.success) {
                say('otp-details-msg', r.message);
                var field = r.field && details.querySelector('[name="' + r.field + '"]');
                if (field) { field.setAttribute('aria-invalid', 'true'); field.focus(); }
                return;
            }
            window.location.href = r.redirect_url || '/';
        }, function () {
            busy(btn, false);
            say('otp-details-msg', offline);
        });
    });
}());
