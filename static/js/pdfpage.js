/* ==========================================================================
 * One PDF builder, for any screen that has a document on it.
 *
 * This was the payslip's own code, inline in payroll_slip.html, and it was
 * the only working "save a PDF" in the application. The worker report had a
 * button labelled "Save PDF" with a PDF icon that called window.print() —
 * which in a desktop browser opens a dialog you can save from, and inside
 * the Android WebView the app actually ships as does nothing whatsoever.
 * No dialog, no file, no error: a dead button on a screen whose only
 * control it is. Rather than write a second exporter, the first one moved
 * here.
 *
 * What it does: rasterise the document, then cut it into A4 pages only at
 * boundaries the DOM says are safe, and draw a running header and a page
 * number on each one.
 *
 *   [data-pdf-block]      an atomic block, never split
 *   [data-pdf-split]      a finer row, used only when a block alone is
 *                         taller than a whole page
 *   [data-pdf-keep-prev]  never start a page with this block
 *
 * Rasterising rather than drawing native text is deliberate and is
 * explained where PDF_NATIVE_TEXT is set in payroll_slip.html: jsPDF's
 * built-in helvetica is Latin-1, so pdf.text() cannot encode Devanagari at
 * all, and embedding a Devanagari face would add ~300KB to a bundle that
 * gets downloaded over 2G at a construction site.
 *
 * The page supplies its own chrome, because the header text is the one
 * genuinely page-specific thing here — a payslip says "Payslip, October
 * 2026" and a report says "Profile Report".
 *
 * Requires html2canvas, jspdf and filesave.js.
 * ========================================================================== */
(function () {
    'use strict';

    var DEFAULT_GEOM = {
        pageW: 210, pageH: 297,
        marginX: 12,
        contentTop: 24,      // below the running header band
        contentBottom: 285,  // above the page-number footer
        /* Capture width drives the effective type size in the PDF: the
           document is rendered at this pixel width and then placed 186mm
           wide, so a narrower capture means larger printed text and more
           pages. 560px puts the smallest type on the payslip at 9.0pt — the
           legibility floor. Widening to 760px would fit it on 2 pages but
           drops that to 6.7pt. */
        captureWidth: 560
    };

    /* Fonts and images must be settled before html2canvas snapshots the DOM,
       otherwise the capture uses fallback metrics or draws a blank image. */
    function waitForAssets(root) {
        var fontsReady = (document.fonts && document.fonts.ready)
            ? document.fonts.ready.catch(function () {}) : Promise.resolve();
        var images = Array.prototype.slice.call(root.querySelectorAll('img'));
        var imagesReady = Promise.all(images.map(function (img) {
            if (img.complete && img.naturalWidth > 0) return Promise.resolve();
            if (typeof img.decode === 'function') return img.decode().catch(function () {});
            return new Promise(function (resolve) { img.onload = img.onerror = resolve; });
        }));
        return Promise.all([fontsReady, imagesReady]);
    }

    /* Two frames is enough for layout to settle after the width change. */
    function nextFrame() {
        return new Promise(function (resolve) {
            requestAnimationFrame(function () { requestAnimationFrame(resolve); });
        });
    }

    /* Collect legal cut offsets (in CSS px from the top of the document). */
    function cutCandidates(root) {
        var base = root.getBoundingClientRect().top;
        var coarse = [], fine = [], keepPrevTops = [];
        root.querySelectorAll('[data-pdf-block]').forEach(function (el) {
            var r = el.getBoundingClientRect();
            coarse.push(r.bottom - base);
            if (el.hasAttribute('data-pdf-keep-prev')) keepPrevTops.push(r.top - base);
        });
        root.querySelectorAll('[data-pdf-split]').forEach(function (el) {
            fine.push(el.getBoundingClientRect().bottom - base);
        });
        coarse.sort(function (a, b) { return a - b; });
        fine.sort(function (a, b) { return a - b; });
        return { coarse: coarse, fine: fine, keepPrevTops: keepPrevTops };
    }

    /* Greedy: take the lowest legal cut that still fits on the page. */
    function paginate(cand, totalPx, usablePx) {
        function best(list, cursor, limit) {
            var pick = null;
            for (var i = 0; i < list.length; i++) {
                var v = list[i];
                if (v <= cursor + 0.5 || v > limit) continue;
                // Never cut immediately before a keep-prev block — that
                // would strand the signature row at the top of a page on
                // its own.
                var blocked = cand.keepPrevTops.some(function (t) {
                    return Math.abs(t - v) < 4;
                });
                if (blocked) continue;
                if (pick === null || v > pick) pick = v;
            }
            return pick;
        }
        var pages = [], cursor = 0, guard = 0;
        while (totalPx - cursor > usablePx && guard++ < 100) {
            var limit = cursor + usablePx;
            // The lowest legal cut of either kind, not block boundaries
            // first. Preferring coarse cuts meant stopping at the end of a
            // block when a row boundary further down would have filled the
            // page: the slip ended a page at 59% and ran to four pages for a
            // month that fits in three. A fine cut falls between table rows,
            // so nothing is split that should not be.
            var coarseCut = best(cand.coarse, cursor, limit);
            var fineCut = best(cand.fine, cursor, limit);
            var cut = (coarseCut === null) ? fineCut
                    : (fineCut === null) ? coarseCut
                    : Math.max(coarseCut, fineCut);
            if (cut === null) cut = limit;   // nothing fits: hard cut
            pages.push({ start: cursor, end: cut });
            cursor = cut;
        }
        pages.push({ start: cursor, end: totalPx });
        return pages;
    }

    /* White background and JPEG, not a transparent PNG: jsPDF stores a PNG
       that has an alpha channel as a raw bitmap plus a soft mask, which took
       the header strip alone from 10KB to 451KB and the whole Hindi payslip
       to five times the size of the English one. The chrome sits on a white
       page, so there is nothing for the transparency to do. */
    function rasterise(el) {
        return html2canvas(el, { scale: 2, backgroundColor: '#ffffff', logging: false })
            .then(function (c) {
                return { url: c.toDataURL('image/jpeg', 0.92), w: c.width, h: c.height };
            });
    }

    /* opts:
     *   root          the element to capture (required)
     *   filename      what to save it as (required)
     *   geom          overrides for DEFAULT_GEOM
     *   hideSelector  things to hide during capture; default '.no-print'
     *                 except the busy overlay
     *   busyId        id of the "Building PDF…" overlay, shown while working
     *   prepareChrome fn(pageCount) -> Promise, run once before the pages
     *   drawChrome    fn(pdf, geom, pageNo, pageCount), run per page
     *   onError       fn(err); the default alerts
     *
     * Resolves with what SmartWorkerSave.blob resolved with.
     */
    function build(opts) {
        var root = opts.root;
        var geom = {};
        Object.keys(DEFAULT_GEOM).forEach(function (k) { geom[k] = DEFAULT_GEOM[k]; });
        Object.keys(opts.geom || {}).forEach(function (k) { geom[k] = opts.geom[k]; });

        var busy = opts.busyId ? document.getElementById(opts.busyId) : null;
        var hidden = Array.prototype.slice.call(document.querySelectorAll(
            opts.hideSelector || '.no-print:not(#pdf-busy)'));
        var prevWidth = root.style.width;
        var prevMaxWidth = root.style.maxWidth;

        function restore() {
            root.style.width = prevWidth;
            root.style.maxWidth = prevMaxWidth;
            root.classList.remove('pdf-capturing');
            hidden.forEach(function (el) { el.style.visibility = ''; });
            if (busy) busy.classList.add('hidden');
        }

        if (busy) busy.classList.remove('hidden');
        // html2canvas draws the screen's styles, not the print stylesheet, so
        // a document that is a rounded card on screen arrives in the PDF as a
        // rounded card floating on A4, drop shadow and all. This class is the
        // hook for a page to say what it looks like on paper; @media print
        // cannot be used, because nothing here is printing.
        root.classList.add('pdf-capturing');
        hidden.forEach(function (el) { el.style.visibility = 'hidden'; });

        return waitForAssets(root)
            .then(function () {
                // Render at page proportions rather than phone width, so the
                // document does not have to be blown up 2x to fill an A4
                // column.
                root.style.width = geom.captureWidth + 'px';
                root.style.maxWidth = 'none';
                return nextFrame();
            })
            .then(function () {
                var widthPx = root.getBoundingClientRect().width;
                var totalPx = root.getBoundingClientRect().height;
                var cand = cutCandidates(root);
                var imgW = geom.pageW - geom.marginX * 2;
                var pxPerMm = widthPx / imgW;
                var usablePx = (geom.contentBottom - geom.contentTop) * pxPerMm;
                var pages = paginate(cand, totalPx, usablePx);

                var prepared = opts.prepareChrome
                    ? opts.prepareChrome(pages.length) : Promise.resolve();

                return prepared.then(function () {
                    return html2canvas(root, {
                        scale: 2, useCORS: true, backgroundColor: '#ffffff',
                        logging: false, windowWidth: geom.captureWidth
                    });
                }).then(function (canvas) {
                    var scale = canvas.width / widthPx;
                    var jsPDF = window.jspdf.jsPDF;
                    var pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });

                    pages.forEach(function (p, i) {
                        if (i > 0) pdf.addPage();
                        var sy = Math.round(p.start * scale);
                        var sh = Math.max(1, Math.round((p.end - p.start) * scale));
                        var crop = document.createElement('canvas');
                        crop.width = canvas.width;
                        crop.height = sh;
                        var ctx = crop.getContext('2d');
                        ctx.fillStyle = '#ffffff';
                        ctx.fillRect(0, 0, crop.width, crop.height);
                        ctx.drawImage(canvas, 0, sy, canvas.width, sh, 0, 0, canvas.width, sh);
                        // JPEG, not PNG: these documents are full of
                        // gradients and antialiased text, which PNG stores
                        // terribly — the same payslip came to ~20MB lossless
                        // versus well under 1MB here, at a quality that is
                        // indistinguishable in print.
                        pdf.addImage(crop.toDataURL('image/jpeg', 0.94), 'JPEG',
                                     geom.marginX, geom.contentTop, imgW,
                                     sh / scale / pxPerMm);
                        if (opts.drawChrome) {
                            opts.drawChrome(pdf, geom, i + 1, pages.length);
                        }
                    });

                    restore();
                    // pdf.save() ends in an <a download>, which the Android
                    // WebView ignores — the file never reached the device.
                    // Hand the blob to the shared saver instead.
                    return SmartWorkerSave.blob(pdf.output('blob'), opts.filename,
                                                'application/pdf')
                        .then(function (r) { SmartWorkerSave.toast(r); return r; });
                });
            })
            .catch(function (err) {
                restore();
                console.error('PDF export failed', err);
                if (opts.onError) opts.onError(err);
                else SmartWorkerSave.fail(err);
                throw err;
            });
    }

    window.SmartWorkerPDF = {
        build: build,
        rasterise: rasterise,
        GEOM: DEFAULT_GEOM
    };
}());
