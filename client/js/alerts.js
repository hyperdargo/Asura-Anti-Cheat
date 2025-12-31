const API_URL = 'http://localhost:5000/api';
let currentAlertId = null;

// Load alerts on page load
document.addEventListener('DOMContentLoaded', () => {
    fetchAlerts();
    
    // Add event listeners for filters
    document.getElementById('severityFilter').addEventListener('change', fetchAlerts);
    document.getElementById('statusFilter').addEventListener('change', fetchAlerts);
    
    // Auto-refresh every 30 seconds
    setInterval(fetchAlerts, 30000);
});

async function fetchAlerts() {
    try {
        const severity = document.getElementById('severityFilter').value;
        const status = document.getElementById('statusFilter').value;
        
        let url = `${API_URL}/alerts?`;
        if (severity !== 'all') url += `severity=${severity}&`;
        if (status !== 'all') url += `status=${status}`;
        
        const response = await fetch(url);
        const alerts = await response.json();
        
        displayAlerts(alerts);
        updateStats(alerts);
    } catch (error) {
        console.error('Error fetching alerts:', error);
        document.getElementById('alertsList').innerHTML = 
            '<div class="no-alerts">Error loading alerts. Please try again.</div>';
    }
}

function displayAlerts(alerts) {
    const alertsList = document.getElementById('alertsList');
    
    if (alerts.length === 0) {
        alertsList.innerHTML = '<div class="no-alerts">No alerts found</div>';
        return;
    }
    
    alertsList.innerHTML = alerts.map(alert => `
        <div class="alert-card" onclick="showAlertDetails(${alert.id})">
            <div class="alert-card-header">
                <div class="alert-info">
                    <span class="severity-badge severity-${alert.severity.toLowerCase()}">
                        ${alert.severity}
                    </span>
                    <span class="status-badge status-${alert.status.toLowerCase()}">
                        ${formatStatus(alert.status)}
                    </span>
                </div>
                <span class="alert-time">
                    ${formatDate(alert.created_at)}
                </span>
            </div>
            <div class="alert-card-body">
                <h3>${alert.exam_name}</h3>
                <p class="student-name">Student: ${alert.student_name}</p>
                <p class="alert-description">${alert.description}</p>
                <p class="alert-type">Type: ${formatAlertType(alert.alert_type)}</p>
            </div>
        </div>
    `).join('');
}

function updateStats(alerts) {
    const criticalCount = alerts.filter(a => a.severity === 'CRITICAL').length;
    const highCount = alerts.filter(a => a.severity === 'HIGH').length;
    const pendingCount = alerts.filter(a => a.status === 'PENDING').length;
    
    document.getElementById('criticalCount').textContent = criticalCount;
    document.getElementById('highCount').textContent = highCount;
    document.getElementById('pendingCount').textContent = pendingCount;
    document.getElementById('totalCount').textContent = alerts.length;
}

async function showAlertDetails(alertId) {
    try {
        const response = await fetch(`${API_URL}/alerts/${alertId}`);
        const alert = await response.json();
        
        currentAlertId = alertId;
        
        const modalBody = document.getElementById('modalBody');
        modalBody.innerHTML = `
            <div class="detail-row">
                <strong>Exam:</strong>
                <p>${alert.exam_name}</p>
            </div>
            <div class="detail-row">
                <strong>Student:</strong>
                <p>${alert.student_name}</p>
            </div>
            <div class="detail-row">
                <strong>Severity:</strong>
                <p><span class="severity-badge severity-${alert.severity.toLowerCase()}">${alert.severity}</span></p>
            </div>
            <div class="detail-row">
                <strong>Status:</strong>
                <p><span class="status-badge status-${alert.status.toLowerCase()}">${formatStatus(alert.status)}</span></p>
            </div>
            <div class="detail-row">
                <strong>Type:</strong>
                <p>${formatAlertType(alert.alert_type)}</p>
            </div>
            <div class="detail-row">
                <strong>Description:</strong>
                <p>${alert.description}</p>
            </div>
            <div class="detail-row">
                <strong>Created:</strong>
                <p>${formatDate(alert.created_at)}</p>
            </div>
            ${alert.notes ? `
            <div class="detail-row">
                <strong>Notes:</strong>
                <p>${alert.notes}</p>
            </div>
            ` : ''}
        `;
        
        document.getElementById('alertModal').style.display = 'flex';
    } catch (error) {
        console.error('Error fetching alert details:', error);
        alert('Error loading alert details');
    }
}

async function updateStatus(status) {
    if (!currentAlertId) return;
    
    const notes = prompt(`Enter notes for ${formatStatus(status)}:`);
    if (notes === null) return;
    
    try {
        const response = await fetch(`${API_URL}/alerts/${currentAlertId}/status`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status, notes })
        });
        
        if (response.ok) {
            alert('Alert updated successfully');
            closeModal();
            fetchAlerts();
        } else {
            alert('Error updating alert');
        }
    } catch (error) {
        console.error('Error updating alert:', error);
        alert('Error updating alert');
    }
}

function closeModal() {
    document.getElementById('alertModal').style.display = 'none';
    currentAlertId = null;
}

function refreshAlerts() {
    fetchAlerts();
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatStatus(status) {
    return status.replace(/_/g, ' ')
        .split(' ')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join(' ');
}

function formatAlertType(type) {
    return type.replace(/_/g, ' ')
        .split(' ')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join(' ');
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('alertModal');
    if (event.target === modal) {
        closeModal();
    }
}
