import React, { useState } from 'react';
import AlertsTab from '../admin/AlertsTab';

const StaffDashboard = () => {
  const [activeTab, setActiveTab] = useState('alerts');

  return (
    <div>
      <div className="tabs">
        <button 
          className={activeTab === 'alerts' ? 'active' : ''}
          onClick={() => setActiveTab('alerts')}
        >
          🚨 Alerts
        </button>
      </div>

      <div className="tab-content">
        {activeTab === 'alerts' && <AlertsTab />}
      </div>
    </div>
  );
};

export default StaffDashboard;