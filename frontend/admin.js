const loginSection = document.getElementById('login-section');
const adminMain = document.getElementById('admin-main');
const adminKeyInput = document.getElementById('admin-key-input');
const loginBtn = document.getElementById('login-btn');
const loginError = document.getElementById('login-error');

const fileInput = document.getElementById('file-input');
const uploadBtn = document.getElementById('upload-btn');
const uploadStatus = document.getElementById('upload-status');

const refreshBtn = document.getElementById('refresh-btn');
const docTableBody = document.getElementById('doc-table-body');
const emptyState = document.getElementById('empty-state');

function getAdminKey() {
    return sessionStorage.getItem('adminKey') || '';
}

function setAdminKey(key) {
    sessionStorage.setItem('adminKey', key);
}

async function tryUnlock(key) {
    // Validate the key by attempting to list documents
    const res = await fetch('/api/admin/documents', {
        headers: { 'X-Admin-Key': key },
    });
    if (res.status === 401) return false;
    if (!res.ok) throw new Error('Could not reach the server.');
    return true;
}

loginBtn.addEventListener('click', async () => {
    const key = adminKeyInput.value.trim();
    if (!key) return;
    loginError.textContent = '';
    loginBtn.disabled = true;
    loginBtn.textContent = 'Checking...';
    try {
        const ok = await tryUnlock(key);
        if (!ok) {
            loginError.textContent = 'Invalid admin key.';
        } else {
            setAdminKey(key);
            loginSection.style.display = 'none';
            adminMain.style.display = 'block';
            loadDocuments();
        }
    } catch (e) {
        loginError.textContent = e.message || 'Something went wrong.';
    } finally {
        loginBtn.disabled = false;
        loginBtn.textContent = 'Unlock';
    }
});

adminKeyInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') loginBtn.click();
});

function statusBadge(status) {
    if (status === 'ready') return `<span class="badge ready">ready</span>`;
    if (status === 'processing') return `<span class="badge processing">processing</span>`;
    return `<span class="badge failed" title="${status}">failed</span>`;
}

async function loadDocuments() {
    docTableBody.innerHTML = '';
    try {
        const res = await fetch('/api/admin/documents', {
            headers: { 'X-Admin-Key': getAdminKey() },
        });
        const result = await res.json();
        if (!result.success) throw new Error(result.error || 'Failed to load documents.');

        const docs = result.data.documents || [];
        emptyState.style.display = docs.length ? 'none' : 'block';

        docs.forEach((doc) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${escapeHtml(doc.original_name)}</td>
                <td>${doc.file_type.toUpperCase()}</td>
                <td>${doc.num_chunks}</td>
                <td>${statusBadge(doc.status)}</td>
                <td>${new Date(doc.uploaded_at).toLocaleString()}</td>
                <td><button class="danger" data-id="${doc.id}">Delete</button></td>
            `;
            docTableBody.appendChild(tr);
        });

        docTableBody.querySelectorAll('button.danger').forEach((btn) => {
            btn.addEventListener('click', () => deleteDocument(btn.dataset.id));
        });
    } catch (e) {
        emptyState.style.display = 'block';
        emptyState.textContent = e.message;
    }
}

async function deleteDocument(id) {
    if (!confirm('Remove this document and all knowledge derived from it? This cannot be undone.')) return;
    try {
        const res = await fetch(`/api/admin/documents/${id}`, {
            method: 'DELETE',
            headers: { 'X-Admin-Key': getAdminKey() },
        });
        const result = await res.json();
        if (!result.success) throw new Error(result.error || 'Delete failed.');
        loadDocuments();
    } catch (e) {
        alert(e.message);
    }
}

uploadBtn.addEventListener('click', async () => {
    const file = fileInput.files[0];
    if (!file) {
        uploadStatus.textContent = 'Choose a file first.';
        uploadStatus.className = 'status-text error';
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    uploadBtn.disabled = true;
    uploadStatus.className = 'status-text';
    uploadStatus.textContent = 'Uploading and processing (embedding can take a moment)...';

    try {
        const res = await fetch('/api/admin/documents', {
            method: 'POST',
            headers: { 'X-Admin-Key': getAdminKey() },
            body: formData,
        });
        const result = await res.json();
        if (!result.success || result.data?.success === false) {
            throw new Error(result.error || result.data?.error || 'Upload failed.');
        }
        uploadStatus.textContent = `Success: ${result.data.chunks_created} chunks added from "${result.data.original_name}".`;
        uploadStatus.className = 'status-text success';
        fileInput.value = '';
        loadDocuments();
    } catch (e) {
        uploadStatus.textContent = e.message;
        uploadStatus.className = 'status-text error';
    } finally {
        uploadBtn.disabled = false;
    }
});

refreshBtn.addEventListener('click', loadDocuments);

function escapeHtml(str) {
    const div = document.createElement('div');
    div.innerText = str;
    return div.innerHTML;
}

// Auto-unlock if a key is already stored in this browser session
(function init() {
    const storedKey = getAdminKey();
    if (storedKey) {
        tryUnlock(storedKey)
            .then((ok) => {
                if (ok) {
                    loginSection.style.display = 'none';
                    adminMain.style.display = 'block';
                    loadDocuments();
                }
            })
            .catch(() => {});
    }
})();
