/* ==========================================================================
 * One way to put a file on the user's device.
 *
 * Android's WebView is not a browser: it has no download manager, and it
 * ignores <a download>. Everything this app exported went through that
 * mechanism — jsPDF's save(), the PNG anchor click, and the two CSV links —
 * so on the APK the user tapped Export, the spinner finished, and no file
 * ever appeared. In a desktop browser the exact same code works, which is
 * why it looked fine in testing.
 *
 * SmartWorkerSave.blob() hides the difference:
 *   inside Cordova -> write with cordova-plugin-file, then hand the file to
 *                     whatever app can open it (cordova-plugin-file-opener2)
 *   in a browser   -> the ordinary object-URL download
 *
 * Callers do not need to know which one they got.
 * ========================================================================== */
(function () {
    'use strict';

    function inCordova() {
        return !!(window.cordova && window.cordova.file);
    }

    /* Where a saved file should live on Android. externalDataDirectory is the
     * app's own folder on shared storage: visible to the user, and writable
     * without any runtime permission on every supported API level. */
    function targetDir() {
        var f = window.cordova.file;
        return f.externalDataDirectory || f.dataDirectory || f.externalRootDirectory;
    }

    function browserDownload(blob, filename) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.rel = 'noopener';
        document.body.appendChild(a);
        a.click();
        setTimeout(function () {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 2000);
        return Promise.resolve({ via: 'browser', name: filename });
    }

    function cordovaSave(blob, filename, mime) {
        return new Promise(function (resolve, reject) {
            window.resolveLocalFileSystemURL(targetDir(), function (dir) {
                dir.getFile(filename, { create: true, exclusive: false }, function (entry) {
                    entry.createWriter(function (writer) {
                        writer.onwriteend = function () {
                            var path = entry.toURL();
                            // Offer to open it. If nothing on the device can
                            // handle the type the file is still saved, so a
                            // failure here is not a failure to export.
                            var opener = window.cordova.plugins && window.cordova.plugins.fileOpener2;
                            if (opener) {
                                opener.open(path, mime, {
                                    error: function () { resolve({ via: 'cordova', name: filename, path: path, opened: false }); },
                                    success: function () { resolve({ via: 'cordova', name: filename, path: path, opened: true }); }
                                });
                            } else {
                                resolve({ via: 'cordova', name: filename, path: path, opened: false });
                            }
                        };
                        writer.onerror = reject;
                        writer.write(blob);
                    }, reject);
                }, reject);
            }, reject);
        });
    }

    var SmartWorkerSave = {
        /* Save a Blob under `filename`. Resolves once the file exists. */
        blob: function (blob, filename, mime) {
            mime = mime || blob.type || 'application/octet-stream';
            if (inCordova() && window.resolveLocalFileSystemURL) {
                return cordovaSave(blob, filename, mime).catch(function (err) {
                    // Never leave the user with nothing: fall back to the
                    // browser path rather than failing silently.
                    console.error('Cordova file save failed, falling back', err);
                    return browserDownload(blob, filename);
                });
            }
            return browserDownload(blob, filename);
        },

        /* Save a same-origin URL (a server-generated CSV, say).
         *
         * Fetching it rather than linking to it fixes a second bug: the SPA
         * router in app.js intercepts every same-origin link, so a plain
         * <a href> to a CSV endpoint was fetched as if it were a page and its
         * contents painted into the document body. */
        url: function (href, filename) {
            return fetch(href, { credentials: 'same-origin' })
                .then(function (res) {
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    var name = filename;
                    if (!name) {
                        var cd = res.headers.get('Content-Disposition') || '';
                        var m = /filename="?([^"';]+)"?/i.exec(cd);
                        name = (m && m[1]) || 'download';
                    }
                    return res.blob().then(function (b) {
                        return SmartWorkerSave.blob(b, name, res.headers.get('Content-Type'));
                    });
                });
        },

        /* Small confirmation so a save is never silent. */
        toast: function (result) {
            var text = result && result.via === 'cordova'
                ? 'Saved to your device' + (result.opened ? '' : ': ' + (result.name || 'file'))
                : 'Downloaded ' + ((result && result.name) || 'file');
            if (window.MultiSelect && typeof window.MultiSelect.toast === 'function') {
                window.MultiSelect.toast(text, 'success');
            }
        },

        fail: function (err) {
            console.error('Export failed', err);
            var text = 'Could not save the file. Please try again.';
            if (window.MultiSelect && typeof window.MultiSelect.toast === 'function') {
                window.MultiSelect.toast(text, 'error');
            } else {
                alert(text);
            }
        }
    };

    window.SmartWorkerSave = SmartWorkerSave;

    /* Any element can become an export button:
     *     <button data-export-url="/payroll/export.csv" data-export-name="pay.csv">
     * Delegated, so it survives SPA swaps. */
    document.addEventListener('click', function (e) {
        var el = e.target.closest && e.target.closest('[data-export-url]');
        if (!el) return;
        e.preventDefault();
        if (el.dataset.exporting) return;      // guard the double-tap
        el.dataset.exporting = '1';
        var done = function () { delete el.dataset.exporting; };
        SmartWorkerSave.url(el.getAttribute('data-export-url'),
                            el.getAttribute('data-export-name') || null)
            .then(function (r) { SmartWorkerSave.toast(r); done(); })
            .catch(function (err) { SmartWorkerSave.fail(err); done(); });
    });
})();
