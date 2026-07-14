// backend/server.js
// Main Express server entry point

require('dotenv').config();
const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// ─── Middleware ───────────────────────────────────────────────────────────────
app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

// Serve frontend static files
app.use(express.static(path.join(__dirname, '../frontend')));

// ─── Routes ──────────────────────────────────────────────────────────────────
const chatRoutes = require('./routes/chat');
const whatsappRoutes = require('./routes/whatsapp');
const adminRoutes = require('./routes/admin');

app.use('/api/chat', chatRoutes);
app.use('/api/whatsapp', whatsappRoutes);
app.use('/api/admin', adminRoutes);

// ─── Health Check ─────────────────────────────────────────────────────────────
app.get('/health', (req, res) => {
  res.json({
    status: 'OK',
    message: 'College AI Assistant Backend is running',
    timestamp: new Date().toISOString(),
    version: '2.0.0',
  });
});

// ─── Root Route ───────────────────────────────────────────────────────────────
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '../frontend/index.html'));
});

// ─── Admin Page Route ─────────────────────────────────────────────────────────
app.get('/admin', (req, res) => {
  res.sendFile(path.join(__dirname, '../frontend/admin.html'));
});

// ─── 404 Handler ──────────────────────────────────────────────────────────────
app.use((req, res) => {
  res.status(404).json({ error: 'Route not found' });
});

// ─── Global Error Handler ─────────────────────────────────────────────────────
app.use((err, req, res, next) => {
  console.error('❌ Server Error:', err.message);
  res.status(500).json({
    error: 'Internal Server Error',
    message: err.message,
  });
});

// ─── Start Server ─────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log('');
  console.log('🎓 ================================================');
  console.log('   College AI Assistant Backend');
  console.log('🎓 ================================================');
  console.log(`✅ Server running on: http://localhost:${PORT}`);
  console.log(`🔍 Health check:      http://localhost:${PORT}/health`);
  console.log(`🛠  Admin panel:       http://localhost:${PORT}/admin`);
  console.log(`🌍 Environment:       ${process.env.NODE_ENV}`);
  console.log('🎓 ================================================');
  console.log('');
});
