const BACKEND_URL = 'http://localhost:8000';

// Initialize token from localStorage
let token = localStorage.getItem('token');

function showLoggedIn() {
    document.getElementById('login').classList.add('hidden');
    document.getElementById('home').classList.remove('hidden');
    document.getElementById('queryLink').classList.remove('hidden');
    document.getElementById('learningLink').classList.remove('hidden');
    document.getElementById('logoutBtn').classList.remove('hidden');
    loadHistory();
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

document.addEventListener('DOMContentLoaded', function() {
    // Auto-login for testing - set dummy token
    token = 'dummy';
    localStorage.setItem('token', 'dummy');
    showLoggedIn();
});

document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    // Bypass login for testing - set dummy token
    token = 'dummy';
    localStorage.setItem('token', 'dummy');
    showLoggedIn();
    document.getElementById('loginMsg').textContent = 'Logged in (demo mode)';
});

document.getElementById('logoutBtn').addEventListener('click', () => {
    token = null;
    localStorage.removeItem('token');
    showLoggedOut();
});

// Navigation handling
document.querySelectorAll('nav a').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const target = e.target.getAttribute('href').substring(1); // Remove #
        
        // Hide all sections
        document.querySelectorAll('main > section').forEach(section => {
            section.classList.add('hidden');
        });
        
        // Show target section
        const targetSection = document.getElementById(target);
        if (targetSection) {
            targetSection.classList.remove('hidden');
        }
        
        // Update URL hash
        window.location.hash = target;
    });
});

// Handle initial load with hash
window.addEventListener('load', () => {
    const hash = window.location.hash.substring(1);
    if (hash && document.getElementById(hash)) {
        document.querySelectorAll('main > section').forEach(section => {
            section.classList.add('hidden');
        });
        document.getElementById(hash).classList.remove('hidden');
    }
});

document.getElementById('queryForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!token) {
        alert('Please log in first.');
        return;
    }
    const dbType = document.getElementById('dbType').value;
    const query = document.getElementById('naturalQuery').value.trim();
    if (!query) {
        alert('Please enter a query.');
        return;
    }
    document.getElementById('sqlBox').textContent = 'Processing...';
    document.getElementById('resultsTable').classList.add('hidden');
    document.getElementById('noResults').classList.add('hidden');
    document.getElementById('feedbackSection').classList.add('hidden');
    try {
        const response = await fetch(BACKEND_URL + '/api/v1/query/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ query })
        });
        const data = await response.json();
        if (response.ok) {
            const parsed = data.data.parsed;
            document.getElementById('sqlBox').textContent = parsed.sql || 'No SQL generated';
            if (parsed.sql) {
                await executeSQL(parsed.sql, dbType);
            } else {
                document.getElementById('noResults').textContent = parsed.error || 'Unable to generate SQL';
                document.getElementById('noResults').classList.remove('hidden');
            }
            document.getElementById('feedbackSection').classList.remove('hidden');
            loadHistory(); // Refresh history
        } else {
            document.getElementById('sqlBox').textContent = `Error: ${data.detail || JSON.stringify(data)}`;
        }
    } catch (err) {
        document.getElementById('sqlBox').textContent = 'Network error: ' + err.message;
    }
});

async function executeSQL(sql, dbType) {
    try {
        const response = await fetch(BACKEND_URL + '/api/v1/db/execute', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ db_type: dbType, query: sql })
        });
        const data = await response.json();
        if (response.ok) {
            displayResults(data.rows);
        } else {
            document.getElementById('noResults').textContent = `Execution error: ${data.detail || JSON.stringify(data)}`;
            document.getElementById('noResults').classList.remove('hidden');
        }
    } catch (err) {
        document.getElementById('noResults').textContent = 'Network error: ' + err.message;
        document.getElementById('noResults').classList.remove('hidden');
    }
}

function displayResults(rows) {
    if (!rows || rows.length === 0) {
        document.getElementById('noResults').classList.remove('hidden');
        return;
    }
    const table = document.getElementById('resultsTable');
    const head = document.getElementById('tableHead');
    const body = document.getElementById('tableBody');
    head.innerHTML = '';
    body.innerHTML = '';
    const headers = Object.keys(rows[0]);
    const headerRow = document.createElement('tr');
    headers.forEach(h => {
        const th = document.createElement('th');
        th.textContent = h;
        headerRow.appendChild(th);
    });
    head.appendChild(headerRow);
    rows.forEach(row => {
        const tr = document.createElement('tr');
        headers.forEach(h => {
            const td = document.createElement('td');
            td.textContent = row[h];
            tr.appendChild(td);
        });
        body.appendChild(tr);
    });
    table.classList.remove('hidden');
}

document.getElementById('goodBtn').addEventListener('click', () => {
    submitFeedback('Good');
});

document.getElementById('badBtn').addEventListener('click', () => {
    document.getElementById('correctionInput').classList.remove('hidden');
    document.getElementById('submitCorrection').classList.remove('hidden');
});

document.getElementById('submitCorrection').addEventListener('click', () => {
    const correction = document.getElementById('correctionInput').value.trim();
    if (correction) {
        submitFeedback('Correction: ' + correction);
    }
});

async function submitFeedback(feedback) {
    // Get the latest interaction index
    const historyResponse = await fetch(BACKEND_URL + '/api/v1/learning/history?limit=1', {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    if (historyResponse.ok) {
        const historyData = await historyResponse.json();
        if (historyData.history.length > 0) {
            const latestIndex = historyData.history.length - 1;
            const response = await fetch(BACKEND_URL + '/api/v1/learning/feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ interaction_index: latestIndex, feedback })
            });
            if (response.ok) {
                alert('Feedback submitted');
                document.getElementById('correctionInput').classList.add('hidden');
                document.getElementById('submitCorrection').classList.add('hidden');
            } else {
                alert('Failed to submit feedback');
            }
        }
    }
}

async function loadHistory() {
    try {
        const response = await fetch(BACKEND_URL + '/api/v1/learning/history', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();
        if (response.ok) {
            const history = data.history;
            const list = document.getElementById('historyList');
            list.innerHTML = '';
            history.forEach((item, index) => {
                const li = document.createElement('li');
                li.textContent = `${new Date(item.timestamp).toLocaleString()}: ${item.natural_query}`;
                if (item.generated_sql) {
                    li.textContent += ` -> ${item.generated_sql}`;
                }
                if (item.feedback) {
                    li.textContent += ` [Feedback: ${item.feedback}]`;
                }
                list.appendChild(li);
            });
        }
    } catch (err) {
        console.error('Failed to load history:', err);
    }
}
