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

async function syncPendingItems() {
  if (!navigator.onLine) return;
  const items = await getQueuedItems();
  let synced = 0;

  for (const item of items) {
    try {
      const res = await fetch(item.url, {
        method: item.method,
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: item.body,
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
  interceptOfflineForms();
  await updateOfflineUI();

  if (navigator.onLine) {
    await syncPendingItems();
  }
});
