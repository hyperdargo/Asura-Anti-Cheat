import React, { useState, useEffect } from 'react';
import './AlertsTab.css';

const AlertsTab = () => {
  const [alerts, setAlerts] = useState([]);
  const [filter, setFilter] = useState({ status: 'all', severity: 'all' });
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, [filter]);

  const fetchAlerts = async () => {
    try {
      const params = new URLSearchParams();
      if (filter.status !== 'all') params.append('status', filter.status);
      if (filter.severity !== 'all') params.append('severity', filter.severity);

      const response = await fetch(`http://localhost:5000/api/alerts?${params}`);
      const data = await response.json();
      setAlerts(data);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching alerts:', error);
      setLoading(false);
    }
  };

  const updateAlertStatus = async (alertId, status, notes) => {
    try {
      await fetch(`http://localhost:5000/api/alerts/${alertId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, notes })
      });
      fetchAlerts();
      setSelectedAlert(null);
    } catch (error) {
      console.error('Error updating alert:', error);
    }
  };

  const getSeverityColor = (severity) => {
    const colors = {
      CRITICAL: '#dc3545',
      HIGH: '#fd7e14',
      MEDIUM: '#ffc107',
      LOW: '#28a745'
    };
    return colors[severity] || '#6c757d';
  };

  const getStatusBadge = (status) => {
    const badges = {
      PENDING: { color: '#ffc107', text: 'Pending' },
      INVESTIGATING: { color: '#17a2b8', text: 'Investigating' },
      RESOLVED: { color: '#28a745', text: 'Resolved' },
      FALSE_POSITIVE: { color: '#6c757d', text: 'False Positive' }
    };
    return badges[status] || badges.PENDING;
  };

  if (loading) return <div className="alerts-loading">Loading alerts...</div>;

  return (
    <div className="alerts-container">
      <div className="alerts-header">
        <h2>Exam Cheating Alerts</h2>
        <div className="alerts-filters">
          <select 
            value={filter.severity} 
            onChange={(e) => setFilter({...filter, severity: e.target.value})}
          >
            <option value="all">All Severities</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
          <select 
            value={filter.status} 
            onChange={(e) => setFilter({...filter, status: e.target.value})}
          >
            <option value="all">All Status</option>
            <option value="PENDING">Pending</option>
            <option value="INVESTIGATING">Investigating</option>
            <option value="RESOLVED">Resolved</option>
            <option value="FALSE_POSITIVE">False Positive</option>
          </select>
        </div>
      </div>

      <div className="alerts-stats">
        <div className="stat-card critical">
          <span className="stat-number">{alerts.filter(a => a.severity === 'CRITICAL').length}</span>
          <span className="stat-label">Critical</span>
        </div>
        <div className="stat-card high">
          <span className="stat-number">{alerts.filter(a => a.severity === 'HIGH').length}</span>
          <span className="stat-label">High</span>
        </div>
        <div className="stat-card pending">
          <span className="stat-number">{alerts.filter(a => a.status === 'PENDING').length}</span>
          <span className="stat-label">Pending</span>
        </div>
      </div>

      <div className="alerts-list">
        {alerts.length === 0 ? (
          <div className="no-alerts">No alerts found</div>
        ) : (
          alerts.map(alert => (
            <div 
              key={alert.id} 
              className="alert-card"
              onClick={() => setSelectedAlert(alert)}
            >
              <div className="alert-card-header">
                <div className="alert-info">
                  <span 
                    className="severity-badge"
                    style={{ backgroundColor: getSeverityColor(alert.severity) }}
                  >
                    {alert.severity}
                  </span>
                  <span 
                    className="status-badge"
                    style={{ backgroundColor: getStatusBadge(alert.status).color }}
                  >
                    {getStatusBadge(alert.status).text}
                  </span>
                </div>
                <span className="alert-time">
                  {new Date(alert.created_at).toLocaleString()}
                </span>
              </div>
              <div className="alert-card-body">
                <h3>{alert.exam_name}</h3>
                <p className="student-name">Student: {alert.student_name}</p>
                <p className="alert-description">{alert.description}</p>
                <p className="alert-type">Type: {alert.alert_type.replace(/_/g, ' ')}</p>
              </div>
            </div>
          ))
        )}
      </div>

      {selectedAlert && (
        <div className="alert-modal" onClick={() => setSelectedAlert(null)}>
          <div className="alert-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Alert Details</h2>
              <button onClick={() => setSelectedAlert(null)}>&times;</button>
            </div>
            <div className="modal-body">
              <div className="detail-row">
                <strong>Exam:</strong> {selectedAlert.exam_name}
              </div>
              <div className="detail-row">
                <strong>Student:</strong> {selectedAlert.student_name}
              </div>
              <div className="detail-row">
                <strong>Severity:</strong> 
                <span style={{ color: getSeverityColor(selectedAlert.severity) }}>
                  {selectedAlert.severity}
                </span>
              </div>
              <div className="detail-row">
                <strong>Type:</strong> {selectedAlert.alert_type.replace(/_/g, ' ')}
              </div>
              <div className="detail-row">
                <strong>Description:</strong>
                <p>{selectedAlert.description}</p>
              </div>
              <div className="detail-row">
                <strong>Created:</strong> {new Date(selectedAlert.created_at).toLocaleString()}
              </div>
              {selectedAlert.notes && (
                <div className="detail-row">
                  <strong>Notes:</strong>
                  <p>{selectedAlert.notes}</p>
                </div>
              )}
            </div>
            <div className="modal-actions">
              <button 
                className="btn-investigating"
                onClick={() => updateAlertStatus(selectedAlert.id, 'INVESTIGATING', 'Under investigation')}
              >
                Mark Investigating
              </button>
              <button 
                className="btn-resolved"
                onClick={() => updateAlertStatus(selectedAlert.id, 'RESOLVED', 'Issue resolved')}
              >
                Mark Resolved
              </button>
              <button 
                className="btn-false"
                onClick={() => updateAlertStatus(selectedAlert.id, 'FALSE_POSITIVE', 'False alarm')}
              >
                False Positive
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AlertsTab;
