const BACKEND_URL = 'http://localhost:8000';

// Initialize token from localStorage
let token = localStorage.getItem('token');

function showLoggedIn() {
    document.getElementById('login').classList.add('hidden');
    document.getElementById('home').classList.remove('hidden');
    document.getElementById('connectionsLink').classList.remove('hidden');
    document.getElementById('queryLink').classList.remove('hidden');
    document.getElementById('learningLink').classList.remove('hidden');
    document.getElementById('logoutBtn').classList.remove('hidden');
    loadSavedConnections();
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
    // Check for existing token
    if (token) {
        showLoggedIn();
    } else {
        showLoggedOut();
    }
});

document.getElementById('registerForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('regUsername').value;
    const email = document.getElementById('regEmail').value;
    const password = document.getElementById('regPassword').value;
    
    try {
        const response = await fetch(`${BACKEND_URL}/api/v1/auth/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, email, password }),
        });
        
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('registerMsg').textContent = 'Registration successful! You can now log in.';
            // Clear form
            document.getElementById('regUsername').value = '';
            document.getElementById('regEmail').value = '';
            document.getElementById('regPassword').value = '';
        } else {
            document.getElementById('registerMsg').textContent = data.detail || 'Registration failed';
        }
    } catch (error) {
        document.getElementById('registerMsg').textContent = 'Network error. Please try again.';
        console.error('Registration error:', error);
    }
});

document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    
    try {
        const response = await fetch(`${BACKEND_URL}/api/v1/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, password }),
        });
        
        const data = await response.json();
        
        if (response.ok) {
            token = data.access_token;
            localStorage.setItem('token', token);
            showLoggedIn();
            document.getElementById('loginMsg').textContent = 'Login successful!';
        } else {
            document.getElementById('loginMsg').textContent = data.detail || 'Login failed';
        }
    } catch (error) {
        document.getElementById('loginMsg').textContent = 'Network error. Please try again.';
        console.error('Login error:', error);
    }
});

document.getElementById('logoutBtn').addEventListener('click', () => {
    token = null;
    localStorage.removeItem('token');
    showLoggedOut();
});

// Database connections management
let savedConnections = JSON.parse(localStorage.getItem('dbConnections') || '[]');

function saveConnection(type, connection) {
    const id = Date.now().toString();
    const conn = { id, type, ...connection };
    savedConnections.push(conn);
    localStorage.setItem('dbConnections', JSON.stringify(savedConnections));
    loadSavedConnections();
    return conn;
}

function deleteConnection(id) {
    savedConnections = savedConnections.filter(conn => conn.id !== id);
    localStorage.setItem('dbConnections', JSON.stringify(savedConnections));
    loadSavedConnections();
}

function loadSavedConnections() {
    const list = document.getElementById('savedConnections');
    list.innerHTML = '';
    
    const select = document.getElementById('connectionSelect');
    select.innerHTML = '<option value="">Select a connection...</option>';
    
    savedConnections.forEach(conn => {
        const li = document.createElement('li');
        li.innerHTML = `
            <span>${conn.type.toUpperCase()} - ${conn.database} (${conn.host}:${conn.port})</span>
            <button class="delete-btn" data-id="${conn.id}">Delete</button>
        `;
        list.appendChild(li);
        
        // Add to query dropdown
        const option = document.createElement('option');
        option.value = conn.id;
        option.textContent = `${conn.type.toUpperCase()} - ${conn.database} (${conn.host}:${conn.port})`;
        select.appendChild(option);
    });
    
    // Add delete event listeners
    document.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            deleteConnection(e.target.dataset.id);
        });
    });
}

async function testConnection(connection) {
    try {
        const response = await fetch(`${BACKEND_URL}/api/v1/db/test`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify(connection),
        });
        
        if (response.ok) {
            return { success: true, message: 'Connection successful!' };
        } else {
            const data = await response.json();
            return { success: false, message: data.detail || 'Connection failed' };
        }
    } catch (error) {
        return { success: false, message: 'Network error' };
    }
}

// Tab switching for connections
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        const tab = e.target.dataset.tab;
        
        // Update active tab button
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        
        // Show selected tab content
        document.querySelectorAll('.tab-content').forEach(content => content.classList.add('hidden'));
        document.getElementById(`${tab}-tab`).classList.remove('hidden');
    });
});

document.getElementById('localConnectionForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const connection = {
        type: document.getElementById('localType').value,
        host: document.getElementById('localHost').value,
        port: parseInt(document.getElementById('localPort').value),
        database: document.getElementById('localDatabase').value,
        username: document.getElementById('localUsername').value,
        password: document.getElementById('localPassword').value,
    };
    
    saveConnection('local', connection);
    document.getElementById('localMsg').textContent = 'Connection saved!';
    e.target.reset();
    document.getElementById('localHost').value = 'host.docker.internal';
    document.getElementById('localPort').value = '1433';
});

document.getElementById('remoteConnectionForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const connection = {
        type: document.getElementById('remoteType').value,
        host: document.getElementById('remoteHost').value,
        port: parseInt(document.getElementById('remotePort').value),
        database: document.getElementById('remoteDatabase').value,
        username: document.getElementById('remoteUsername').value,
        password: document.getElementById('remotePassword').value,
    };
    
    saveConnection('remote', connection);
    document.getElementById('remoteMsg').textContent = 'Connection saved!';
    e.target.reset();
    document.getElementById('remotePort').value = '1433';
});

document.getElementById('testLocalBtn').addEventListener('click', async () => {
    const connection = {
        type: document.getElementById('localType').value,
        host: document.getElementById('localHost').value,
        port: parseInt(document.getElementById('localPort').value),
        database: document.getElementById('localDatabase').value,
        username: document.getElementById('localUsername').value,
        password: document.getElementById('localPassword').value,
    };
    
    const result = await testConnection(connection);
    document.getElementById('localMsg').textContent = result.message;
});

document.getElementById('testRemoteBtn').addEventListener('click', async () => {
    const connection = {
        type: document.getElementById('remoteType').value,
        host: document.getElementById('remoteHost').value,
        port: parseInt(document.getElementById('remotePort').value),
        database: document.getElementById('remoteDatabase').value,
        username: document.getElementById('remoteUsername').value,
        password: document.getElementById('remotePassword').value,
    };
    
    const result = await testConnection(connection);
    document.getElementById('remoteMsg').textContent = result.message;
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
    
    const connectionId = document.getElementById('connectionSelect').value;
    if (!connectionId) {
        alert('Please select a database connection.');
        return;
    }
    
    const connection = savedConnections.find(conn => conn.id === connectionId);
    if (!connection) {
        alert('Selected connection not found.');
        return;
    }
    
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
        const response = await fetch(BACKEND_URL + '/api/v1/query/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ 
                query,
                connection: {
                    type: connection.type,
                    host: connection.host,
                    port: connection.port,
                    database: connection.database,
                    username: connection.username,
                    password: connection.password
                }
            })
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
