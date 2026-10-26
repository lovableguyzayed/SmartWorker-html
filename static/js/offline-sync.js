const SW_DB_NAME = 'smartworker-offline';
const SW_DB_VERSION = 1;
const SW_STORE = 'sync-queue';

function openSyncDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(SW_DB_NAME, SW_DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(SW_STORE)) {
        db.createObjectStore(SW_STORE, { keyPath: 'id', autoIncrement: true });
      }
    };
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = reject;
  });
}

async function queueRequest(url, method, body, description) {
  const db = await openSyncDB();
  return new Promise((resolve) => {
    const tx = db.transaction(SW_STORE, 'readwrite');
    tx.objectStore(SW_STORE).add({ url, method, body, description, timestamp: Date.now() });
    tx.oncomplete = resolve;
  });
}

async function getQueuedItems() {
  const db = await openSyncDB();
  return new Promise((resolve) => {
    const tx = db.transaction(SW_STORE, 'readonly');
    const req = tx.objectStore(SW_STORE).getAll();
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = () => resolve([]);
  });
}

async function deleteQueuedItem(id) {
  const db = await openSyncDB();
  return new Promise((resolve) => {
    const tx = db.transaction(SW_STORE, 'readwrite');
    tx.objectStore(SW_STORE).delete(id);
    tx.oncomplete = resolve;
  });
}

async function updateOfflineUI() {
  const items = await getQueuedItems();
  const count = items.length;
  const isOnline = navigator.onLine;

  const indicator = document.getElementById('offline-indicator');
  const statusText = document.getElementById('offline-status-text');
  const pendingBadge = document.getElementById('pending-sync-badge');

  if (!indicator) return;

  if (!isOnline) {
    indicator.className = 'fixed top-0 left-0 right-0 z-50 bg-red-600 text-white text-center text-xs py-1.5 px-3 flex items-center justify-center gap-2';
    statusText.textContent = count > 0
      ? `Offline — ${count} item${count > 1 ? 's' : ''} waiting to sync`
      : 'You are offline — data will sync when connected';
    indicator.classList.remove('hidden');
  } else if (count > 0) {
    indicator.className = 'fixed top-0 left-0 right-0 z-50 bg-yellow-500 text-white text-center text-xs py-1.5 px-3 flex items-center justify-center gap-2';
    statusText.textContent = `Syncing ${count} pending item${count > 1 ? 's' : ''}...`;
    indicator.classList.remove('hidden');
  } else {
    indicator.classList.add('hidden');
  }

  if (pendingBadge) {
    pendingBadge.textContent = count;
    pendingBadge.classList.toggle('hidden', count === 0);
  }
}

function withCurrentCsrf(body) {
  const meta = document.querySelector('meta[name=csrf-token]');
  if (!meta) return body;
  const params = new URLSearchParams(body || '');
  params.set('csrf_token', meta.getAttribute('content'));
  return params.toString();
}

/* One drain at a time, and never two.
 *
 * Two 'online' events arriving close together — a phone finding the
 * network, flapping, and finding it again, or the event racing the sync
 * that DOMContentLoaded starts — had both handlers reach getQueuedItems()
 * before either had deleted anything. Both read the same row, both posted
 * it, both succeeded, and the item was written twice: a worker marked
 * present twice, or a wage payment recorded twice. Then both deleted it,
 * so the queue looked correct afterwards and nothing said otherwise.
 *
 * Found by tests/test_offline_queue.py, which fires the event by hand on
 * top of the browser's own and asserts the row lands exactly once.
 *
 * `again` covers the honest case for a second run: something queued while
 * a drain was in flight. It runs after, rather than alongside.
 */
let draining = false;
let drainAgain = false;

async function syncPendingItems() {
  if (!navigator.onLine) return;
  if (draining) { drainAgain = true; return; }
  draining = true;
  try {
    await drainQueue();
    while (drainAgain) {
      drainAgain = false;
      await drainQueue();
    }
  } finally {
    draining = false;
    drainAgain = false;
  }
}

async function drainQueue() {
  const items = await getQueuedItems();
  let synced = 0;

  for (const item of items) {
    try {
      // The token captured when the request was queued may be hours old by
      // the time the signal returns; swap in the one this page holds.
      const body = withCurrentCsrf(item.body);
      const res = await fetch(item.url, {
        method: item.method,
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body,
        credentials: 'same-origin'
      });
      if (res.ok || res.redirected || res.status === 302) {
        await deleteQueuedItem(item.id);
        synced++;
      }
    } catch (err) {
      break;
    }
  }

  await updateOfflineUI();

  if (synced > 0) {
    showSyncToast(`${synced} item${synced > 1 ? 's' : ''} synced to server successfully!`, 'success');
  }
}

function showSyncToast(message, type = 'info') {
  const colors = { success: 'bg-green-600', warning: 'bg-yellow-600', info: 'bg-blue-600', error: 'bg-red-600' };
  const toast = document.createElement('div');
  toast.className = `fixed bottom-6 left-1/2 transform -translate-x-1/2 ${colors[type] || colors.info} text-white text-sm px-5 py-3 rounded-xl shadow-lg z-50 flex items-center gap-2 transition-all`;
  toast.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : type === 'warning' ? 'exclamation-triangle' : 'info-circle'}"></i> ${message}`;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 400); }, 4000);
}

/* ---------------------------------------------------------------------
 * Queue attendance writes made with fetch().
 *
 * The form interception below only ever saw <form> submits, but the
 * attendance screen posts through fetch() — so on a site with no signal the
 * request simply threw, nothing was stored, and the worker was never marked.
 * Tested offline in a browser: the fetch threw TypeError, the queue was
 * empty, and nothing reached the server when the signal came back.
 *
 * Only what somebody does standing in a field with a phone is queued, and
 * only things that add a row. Replaying a payroll run, a cancel or a
 * delete after the fact would be dangerous — the state they were deciding
 * against is hours old by the time the signal returns — and none of them
 * is done at a gate.
 *
 * Money was added to this list after the scanner learned to record it. A
 * wage payment handed over at the gate is the same shape of act as marking
 * somebody present: it happens where there is no signal, it appends one
 * row, and losing it silently is worse than sending it late. Before this
 * the scanner's payment simply threw on a dead network and nothing was
 * stored, which is precisely the failure the attendance queue exists to
 * prevent.
 * ------------------------------------------------------------------- */
const OFFLINE_QUEUEABLE = [
  '/api/mark_attendance',
  '/mark_attendance',
  '/api/attendance/bulk',
  '/api/attendance/times',
  // Advances and wages recorded at the gate.
  //
  // The worker's confirmation is deliberately NOT here. It is
  // /api/transaction_ack/<id>, and a queued payment has no id yet — the
  // row does not exist until the queue drains. Queuing an acknowledgement
  // would mean storing a confirmation of something that has not been
  // written, against an id that will never match. Offline, the payment is
  // saved and the confirmation is taken the next time both people are in
  // front of the phone with a signal.
  '/api/worker_transaction',
];

/* What to tell the person, per endpoint. "Attendance saved on this phone"
 * on a payment would be a small lie at exactly the moment they are
 * watching to see their money recorded. */
const QUEUED_AS = {
  '/api/worker_transaction': 'Payment saved on this phone',
};

function queuedDescription(path) {
  return QUEUED_AS[path] || 'Attendance saved on this phone';
}

function isQueueable(url, method) {
  if ((method || 'GET').toUpperCase() !== 'POST') return false;
  let path;
  try {
    path = new URL(url, window.location.origin);
    if (path.origin !== window.location.origin) return false;
    path = path.pathname;
  } catch (_) {
    return false;
  }
  return OFFLINE_QUEUEABLE.indexOf(path) !== -1;
}

/* A queued write has not happened yet, so the caller is told so plainly
 * rather than being handed a fake success. The attendance screen reads
 * `success`, and `queued` lets it say "saved on this phone" instead of
 * "marked present". */
function queuedResponse(description) {
  return new Response(
    JSON.stringify({ success: false, queued: true, offline: true,
                     message: description }),
    { status: 202, headers: { 'Content-Type': 'application/json' } });
}

async function bodyToString(body) {
  if (!body) return '';
  if (typeof body === 'string') return body;
  if (body instanceof URLSearchParams) return body.toString();
  if (typeof FormData !== 'undefined' && body instanceof FormData) {
    return new URLSearchParams(body).toString();
  }
  return String(body);
}

function interceptOfflineFetch() {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    const url = (typeof input === 'string') ? input : (input && input.url);
    const method = (init && init.method) || (input && input.method) || 'GET';

    if (navigator.onLine || !isQueueable(url, method)) {
      return nativeFetch(input, init);
    }

    const body = await bodyToString(init && init.body);
    const path = new URL(url, window.location.origin).pathname;
    const saved = queuedDescription(path);
    await queueRequest(path, 'POST', body, saved);
    await updateOfflineUI();
    showSyncToast('No internet. ' + saved +
                  ' and will upload automatically.', 'warning');
    return queuedResponse(saved);
  };
}

function interceptOfflineForms() {
  document.addEventListener('submit', async (e) => {
    if (navigator.onLine) return;

    const form = e.target;
    const method = (form.method || 'GET').toUpperCase();
    if (method !== 'POST') return;

    const action = form.getAttribute('action') || window.location.pathname;
    if (action.includes('/login') || action.includes('/logout')) return;

    e.preventDefault();

    const formData = new FormData(form);
    const body = new URLSearchParams(formData).toString();
    const desc = form.dataset.offlineDesc || `Action: ${action}`;

    await queueRequest(action, method, body, desc);
    await updateOfflineUI();

    showSyncToast('Saved locally. Will upload when internet returns.', 'warning');
  });
}

window.addEventListener('online', async () => {
  await updateOfflineUI();
  await syncPendingItems();
});

window.addEventListener('offline', async () => {
  await updateOfflineUI();
  showSyncToast('You are now offline. Data will be saved locally.', 'warning');
});

document.addEventListener('DOMContentLoaded', async () => {
  interceptOfflineFetch();
  interceptOfflineForms();
  await updateOfflineUI();

  if (navigator.onLine) {
    await syncPendingItems();
  }
});
