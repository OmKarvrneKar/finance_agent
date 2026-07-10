import React, { useState } from 'react';
import { Upload, Camera, Loader } from 'lucide-react';
import { uploadReceipt } from '../utils/api';

const ReceiptUpload = ({ onUploadSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setLoading(true);
    setError(null);
    try {
      const res = await uploadReceipt(file);
      if (onUploadSuccess) onUploadSuccess(res);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to upload receipt.");
    } finally {
      setLoading(false);
      e.target.value = null; 
    }
  };

  return (
    <div className="card" style={{ marginBottom: '32px' }}>
      <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
        <Camera size={24} color="var(--primary-blue)" /> Upload Receipt
      </h2>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '24px' }}>
        Take a photo or upload a receipt to auto-extract the details using AI.
      </p>

      <div style={{ border: '2px dashed var(--border-color)', borderRadius: '8px', padding: '32px', textAlign: 'center', backgroundColor: 'var(--bg-color)', position: 'relative', overflow: 'hidden' }}>
        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
            <Loader size={32} color="var(--primary-blue)" />
            <span style={{ color: 'var(--text-muted)' }}>Reading your receipt...</span>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
            <Upload size={32} color="var(--text-muted)" />
            <div style={{ color: 'var(--text-main)', fontWeight: 500 }}>Click to upload or take photo</div>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>JPG, PNG up to 10MB</div>
            <input 
              type="file" 
              accept="image/*" 
              capture="environment"
              onChange={handleFileChange} 
              style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', opacity: 0, cursor: 'pointer' }}
            />
          </div>
        )}
      </div>
      {error && <div style={{ color: '#EF4444', marginTop: '16px', fontSize: '0.875rem', textAlign: 'center' }}>{error}</div>}
    </div>
  );
};

export default ReceiptUpload;
