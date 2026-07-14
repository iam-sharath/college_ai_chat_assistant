// backend/routes/admin.js
const express = require('express');
const router = express.Router();
const axios = require('axios');
const multer = require('multer');
const FormData = require('form-data');
const { formatResponse } = require('../utils/response');
const adminAuth = require('../middleware/adminAuth');

const RAG_URL = process.env.RAG_ENGINE_URL || 'http://localhost:5001';
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 25 * 1024 * 1024 }, // 25MB per file
});

// All admin routes require the admin key
router.use(adminAuth);

// ── List knowledge-base documents ───────────────────────────────
router.get('/documents', async (req, res) => {
  try {
    const ragRes = await axios.get(`${RAG_URL}/admin/documents`, {
      headers: { 'X-Admin-Key': process.env.ADMIN_API_KEY },
      timeout: 10000,
    });
    return res.json(formatResponse(true, ragRes.data));
  } catch (error) {
    return handleRagError(error, res);
  }
});

// ── Upload a new PDF/DOCX/TXT into the knowledge base ───────────
router.post('/documents', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json(formatResponse(false, null, 'No file uploaded (field name must be "file").'));
    }

    const form = new FormData();
    form.append('file', req.file.buffer, { filename: req.file.originalname });

    const ragRes = await axios.post(`${RAG_URL}/admin/documents`, form, {
      headers: {
        ...form.getHeaders(),
        'X-Admin-Key': process.env.ADMIN_API_KEY,
      },
      maxBodyLength: Infinity,
      maxContentLength: Infinity,
      timeout: 120000, // ingestion (embedding) can take a little while
    });

    return res.json(formatResponse(true, ragRes.data));
  } catch (error) {
    return handleRagError(error, res);
  }
});

// ── Delete a document (and its chunks) from the knowledge base ─
router.delete('/documents/:id', async (req, res) => {
  try {
    const ragRes = await axios.delete(`${RAG_URL}/admin/documents/${req.params.id}`, {
      headers: { 'X-Admin-Key': process.env.ADMIN_API_KEY },
      timeout: 15000,
    });
    return res.json(formatResponse(true, ragRes.data));
  } catch (error) {
    return handleRagError(error, res);
  }
});

function handleRagError(error, res) {
  console.error('❌ Admin route error:', error.message);
  if (error.code === 'ECONNREFUSED') {
    return res.status(503).json(formatResponse(false, null, 'RAG engine is offline. Start the Python server first.'));
  }
  if (error.response) {
    return res.status(error.response.status).json(formatResponse(false, null, error.response.data?.error || 'RAG engine error.'));
  }
  return res.status(500).json(formatResponse(false, null, 'Internal server error contacting RAG engine.'));
}

module.exports = router;
