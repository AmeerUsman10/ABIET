let token = localStorage.getItem('token');

function showLoggedIn() {
    document.getElementById('login').classList.add('hidden');
    document.getElementById('home').classList.remove('hidden');
    document.getElementById('queryLink').classList.remove('hidden');
    document.getElementById('learningLink').classList.remove('hidden');
    document.getElementById('logoutBtn').classList.remove('hidden');
}

function showLoggedOut() {
    document.getElementById('login').classList.remove('hidden');
    document.getElementById('home').classList.add('hidden');
    document.getElementById('query').classList.add('hidden');
    document.getElementById('learning').classList.add('hidden');
    document.getElementById('queryLink').classList.add('hidden');
    document.getElementById('learningLink').classList.add('hidden');
    document.getElementById('logoutBtn').classList.add('hidden');
}

if (token) {
    showLoggedIn();
} else {
    showLoggedOut();
}

document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const msg = document.getElementById('loginMsg');
    msg.textContent = 'Logging in...';
    try {
        const response = await fetch('/api/v1/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await response.json();
        if (response.ok) {
            token = data.access_token;
            localStorage.setItem('token', token);
            showLoggedIn();
        } else {
            msg.textContent = `Login failed: ${data.detail || JSON.stringify(data)}`;
        }
    } catch (err) {
        msg.textContent = 'Network error: ' + err.message;
    }
});

document.getElementById('logoutBtn').addEventListener('click', () => {
    token = null;
    localStorage.removeItem('token');
    showLoggedOut();
});

document.getElementById('queryForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!token) {
        document.getElementById('resultBox').textContent = 'Please log in first.';
        return;
    }
    const dbType = document.getElementById('dbType').value;
    const query = document.getElementById('sqlQuery').value.trim();
    if (!query) {
        document.getElementById('resultBox').textContent = 'Please enter a SQL query.';
        return;
    }
    document.getElementById('resultBox').textContent = 'Running...';
    try {
        const response = await fetch('/api/v1/db/execute', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ db_type: dbType, query })
        });
        const data = await response.json();
        if (response.ok) {
            document.getElementById('resultBox').textContent = JSON.stringify(data, null, 2);
        } else {
            document.getElementById('resultBox').textContent = `Error ${response.status}: ${data.detail || JSON.stringify(data)}`;
        }
    } catch (err) {
        document.getElementById('resultBox').textContent = 'Network error: ' + err.message;
    }
});
