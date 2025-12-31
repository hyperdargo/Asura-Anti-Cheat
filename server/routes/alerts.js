const express = require('express');
const router = express.Router();
const db = require('../config/database');
const mlAnalysis = require('../services/mlAnalysis');

// Get all alerts
router.get('/', async (req, res) => {
  try {
    const { status, severity, exam_id } = req.query;
    let query = 'SELECT * FROM alerts WHERE 1=1';
    const params = [];

    if (status) {
      query += ' AND status = ?';
      params.push(status);
    }
    if (severity) {
      query += ' AND severity = ?';
      params.push(severity);
    }
    if (exam_id) {
      query += ' AND exam_id = ?';
      params.push(exam_id);
    }

    query += ' ORDER BY created_at DESC';

    db.all(query, params, (err, rows) => {
      if (err) {
        return res.status(500).json({ error: err.message });
      }
      res.json(rows);
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Get alert by ID
router.get('/:id', (req, res) => {
  const query = 'SELECT * FROM alerts WHERE id = ?';
  db.get(query, [req.params.id], (err, row) => {
    if (err) {
      return res.status(500).json({ error: err.message });
    }
    if (!row) {
      return res.status(404).json({ error: 'Alert not found' });
    }
    res.json(row);
  });
});

// Update alert status
router.patch('/:id/status', (req, res) => {
  const { status, notes } = req.body;
  const query = 'UPDATE alerts SET status = ?, notes = ?, updated_at = ? WHERE id = ?';
  
  db.run(query, [status, notes, new Date().toISOString(), req.params.id], function(err) {
    if (err) {
      return res.status(500).json({ error: err.message });
    }
    res.json({ message: 'Alert updated successfully', changes: this.changes });
  });
});

// Trigger manual analysis
router.post('/analyze', async (req, res) => {
  try {
    const { examId, studentId } = req.body;
    const activities = await mlAnalysis.analyzeLogs(examId, studentId);
    res.json({ 
      message: 'Analysis completed',
      suspiciousActivities: activities
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;
