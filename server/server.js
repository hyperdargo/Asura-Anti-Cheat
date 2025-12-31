const express = require('express');
const app = express();
const port = 3000;

const alertsRoutes = require('./routes/alerts');

app.use('/api/alerts', alertsRoutes);

app.listen(port, () => {
  console.log(`Server is running on http://localhost:${port}`);
});