import React, { useState } from 'react';
import AlertsTab from './AlertsTab';

const AdminDashboard = () => {
  const [activeTab, setActiveTab] = useState('overview'); // or your default tab

  return (
    <div className="admin-dashboard">
      <nav className="dashboard-tabs">
        {/* ...existing tabs... */}
        <button 
          className={activeTab === 'alerts' ? 'active' : ''}
          onClick={() => setActiveTab('alerts')}
        >
          🚨 Alerts
        </button>
        {/* ...existing tabs... */}
      </nav>

      <div className="tab-content">
        {activeTab === 'alerts' && <AlertsTab />}
        {/* ...existing tab content... */}
      </div>
    </div>
  );
};

export default AdminDashboard;