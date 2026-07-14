// backend/utils/response.js

/**
 * Standardizes the API response format across the entire project.
 */
const formatResponse = (success, data = {}, error = null) => {
    if (success) {
        return {
            success: true,
            data: data,
            timestamp: new Date().toISOString()
        };
    } else {
        return {
            success: false,
            error: error || 'An unknown error occurred',
            timestamp: new Date().toISOString()
        };
    }
};

module.exports = { formatResponse };
