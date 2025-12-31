const db = require('../config/database');

class MLAnalysisService {
  constructor() {
    // Suspicious behavior patterns
    this.suspiciousPatterns = {
      EXCESSIVE_COPY: { threshold: 5, weight: 0.8 },
      EXCESSIVE_PASTE: { threshold: 5, weight: 0.9 },
      WINDOW_SWITCHING: { threshold: 10, weight: 0.7 },
      UNAUTHORIZED_APP: { threshold: 1, weight: 1.0 },
      NETWORK_ACCESS: { threshold: 3, weight: 0.85 },
      EXCESSIVE_IDLE: { threshold: 300, weight: 0.5 }, // 5 minutes
      RAPID_TYPING: { threshold: 200, weight: 0.4 }, // chars per minute
      MULTIPLE_DEVICES: { threshold: 1, weight: 0.95 }
    };
  }

  async analyzeLogs(examId, studentId) {
    try {
      const logs = await this.getStudentLogs(examId, studentId);
      const suspiciousActivities = this.detectSuspiciousActivities(logs);
      
      if (suspiciousActivities.length > 0) {
        await this.createAlert(examId, studentId, suspiciousActivities);
        await this.notifyStaff(examId, studentId, suspiciousActivities);
      }

      return suspiciousActivities;
    } catch (error) {
      console.error('ML Analysis error:', error);
      throw error;
    }
  }

  async getStudentLogs(examId, studentId) {
    const query = `
      SELECT * FROM activity_logs 
      WHERE exam_id = ? AND student_id = ?
      ORDER BY timestamp DESC
    `;
    return new Promise((resolve, reject) => {
      db.all(query, [examId, studentId], (err, rows) => {
        if (err) reject(err);
        else resolve(rows || []);
      });
    });
  }

  detectSuspiciousActivities(logs) {
    const activities = [];
    const activityCounts = {};

    logs.forEach(log => {
      const type = log.activity_type;
      activityCounts[type] = (activityCounts[type] || 0) + 1;
    });

    // Check for excessive copy operations
    if (activityCounts['COPY'] >= this.suspiciousPatterns.EXCESSIVE_COPY.threshold) {
      activities.push({
        type: 'EXCESSIVE_COPY',
        severity: 'HIGH',
        description: `Excessive copy operations detected (${activityCounts['COPY']} times)`,
        weight: this.suspiciousPatterns.EXCESSIVE_COPY.weight
      });
    }

    // Check for excessive paste operations
    if (activityCounts['PASTE'] >= this.suspiciousPatterns.EXCESSIVE_PASTE.threshold) {
      activities.push({
        type: 'EXCESSIVE_PASTE',
        severity: 'HIGH',
        description: `Excessive paste operations detected (${activityCounts['PASTE']} times)`,
        weight: this.suspiciousPatterns.EXCESSIVE_PASTE.weight
      });
    }

    // Check for window switching
    if (activityCounts['WINDOW_SWITCH'] >= this.suspiciousPatterns.WINDOW_SWITCHING.threshold) {
      activities.push({
        type: 'WINDOW_SWITCHING',
        severity: 'MEDIUM',
        description: `Frequent window switching detected (${activityCounts['WINDOW_SWITCH']} times)`,
        weight: this.suspiciousPatterns.WINDOW_SWITCHING.weight
      });
    }

    // Check for unauthorized applications
    const unauthorizedApps = logs.filter(log => 
      log.activity_type === 'APP_OPENED' && this.isUnauthorizedApp(log.details)
    );
    if (unauthorizedApps.length > 0) {
      activities.push({
        type: 'UNAUTHORIZED_APP',
        severity: 'CRITICAL',
        description: `Unauthorized application detected: ${unauthorizedApps[0].details}`,
        weight: this.suspiciousPatterns.UNAUTHORIZED_APP.weight
      });
    }

    // Check for network access attempts
    if (activityCounts['NETWORK_ACCESS'] >= this.suspiciousPatterns.NETWORK_ACCESS.threshold) {
      activities.push({
        type: 'NETWORK_ACCESS',
        severity: 'HIGH',
        description: `Multiple network access attempts detected (${activityCounts['NETWORK_ACCESS']} times)`,
        weight: this.suspiciousPatterns.NETWORK_ACCESS.weight
      });
    }

    return activities;
  }

  isUnauthorizedApp(appName) {
    const unauthorizedApps = ['chrome', 'firefox', 'edge', 'whatsapp', 'telegram', 'discord', 'slack'];
    return unauthorizedApps.some(app => appName.toLowerCase().includes(app));
  }

  async createAlert(examId, studentId, suspiciousActivities) {
    const [student, exam] = await Promise.all([
      this.getStudentInfo(studentId),
      this.getExamInfo(examId)
    ]);

    const alertData = {
      exam_id: examId,
      exam_name: exam.title,
      student_id: studentId,
      student_name: student.name,
      alert_type: suspiciousActivities[0].type,
      severity: suspiciousActivities[0].severity,
      description: suspiciousActivities.map(a => a.description).join('; '),
      status: 'PENDING',
      created_at: new Date().toISOString()
    };

    const query = `
      INSERT INTO alerts (exam_id, exam_name, student_id, student_name, alert_type, severity, description, status, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `;

    return new Promise((resolve, reject) => {
      db.run(query, Object.values(alertData), function(err) {
        if (err) reject(err);
        else resolve({ id: this.lastID, ...alertData });
      });
    });
  }

  async getStudentInfo(studentId) {
    const query = 'SELECT * FROM users WHERE id = ?';
    return new Promise((resolve, reject) => {
      db.get(query, [studentId], (err, row) => {
        if (err) reject(err);
        else resolve(row);
      });
    });
  }

  async getExamInfo(examId) {
    const query = 'SELECT * FROM exams WHERE id = ?';
    return new Promise((resolve, reject) => {
      db.get(query, [examId], (err, row) => {
        if (err) reject(err);
        else resolve(row);
      });
    });
  }

  async notifyStaff(examId, studentId, suspiciousActivities) {
    const teachers = await this.getExamTeachers(examId);
    const student = await this.getStudentInfo(studentId);
    
    // Store notifications in database
    const notifications = teachers.map(teacher => ({
      user_id: teacher.id,
      type: 'CHEATING_ALERT',
      message: `Alert: ${student.name} - ${suspiciousActivities[0].description}`,
      read: 0,
      created_at: new Date().toISOString()
    }));

    // Insert notifications
    for (const notification of notifications) {
      const query = `
        INSERT INTO notifications (user_id, type, message, read, created_at)
        VALUES (?, ?, ?, ?, ?)
      `;
      await new Promise((resolve, reject) => {
        db.run(query, Object.values(notification), (err) => {
          if (err) reject(err);
          else resolve();
        });
      });
    }
  }

  async getExamTeachers(examId) {
    const query = `
      SELECT u.* FROM users u
      INNER JOIN exams e ON e.teacher_id = u.id
      WHERE e.id = ? AND u.role = 'teacher'
    `;
    return new Promise((resolve, reject) => {
      db.all(query, [examId], (err, rows) => {
        if (err) reject(err);
        else resolve(rows || []);
      });
    });
  }
}

module.exports = new MLAnalysisService();
