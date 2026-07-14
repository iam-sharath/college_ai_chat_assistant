// backend/middleware/adminAuth.js
// Protects /api/admin/* routes with a simple shared-secret key.
// Set ADMIN_API_KEY in backend/.env (must match rag-engine/.env's ADMIN_API_KEY).

function adminAuth(req, res, next) {
  const configuredKey = process.env.ADMIN_API_KEY;

  if (!configuredKey) {
    return res.status(500).json({
      success: false,
      error: 'Server misconfigured: ADMIN_API_KEY not set in backend/.env',
    });
  }

  const providedKey = req.headers['x-admin-key'];

  if (!providedKey || providedKey !== configuredKey) {
    return res.status(401).json({
      success: false,
      error: 'Unauthorized. Provide a valid X-Admin-Key header.',
    });
  }

  next();
}

module.exports = adminAuth;
