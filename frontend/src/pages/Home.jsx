import React, { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { Upload, FileText, CheckCircle, AlertCircle, Loader, List, Camera } from 'lucide-react';
import SummaryCard from '../components/SummaryCard';
import ReceiptUpload from '../components/ReceiptUpload';
import PendingReceipts from '../components/PendingReceipts';
import { uploadStatement } from '../utils/api';

const Home = () => {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('statement');
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      setFile(acceptedFiles[0]);
      setError(null);
      setResult(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv']
    },
    maxFiles: 1
  });

  const handleUpload = async () => {
    if (!file) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const data = await uploadStatement(file);
      
      // Transform category breakdown for chart
      const chartData = Object.entries(data.category_breakdown || {}).map(([name, count]) => ({
        name,
        count
      })).sort((a, b) => b.count - a.count);

      setResult({
        ...data,
        chartData
      });
    } catch (err) {
      console.error('Upload error:', err);
      setError(err.response?.data?.detail || err.message || 'An error occurred during upload.');
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setFile(null);
    setResult(null);
    setError(null);
  };

  return (
    <div className="layout-container">
      <div className="page-header">
        <h1 className="page-title">Import Transactions</h1>
        <p className="page-description">Upload your bank statement CSV or scan a receipt to automatically categorize your transactions using AI.</p>
      </div>

      <div style={{ display: 'flex', gap: '16px', marginBottom: '32px' }}>
        <button onClick={() => setActiveTab('statement')} className={activeTab === 'statement' ? 'btn-primary' : 'btn-secondary'} style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Upload size={18} /> Bank Statement
        </button>
        <button onClick={() => setActiveTab('receipt')} className={activeTab === 'receipt' ? 'btn-primary' : 'btn-secondary'} style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Camera size={18} /> Receipt / Cash
        </button>
      </div>

      {activeTab === 'statement' && (
        <>
          {!result && !loading && (
        <div className="card" style={{ maxWidth: '600px', margin: '0 auto' }}>
          <div 
            {...getRootProps()} 
            className={`upload-zone ${isDragActive ? 'active' : ''}`}
            style={{ marginBottom: '24px' }}
          >
            <input {...getInputProps()} />
            <Upload size={48} color={isDragActive ? 'var(--accent-color)' : 'var(--text-muted)'} style={{ margin: '0 auto 16px' }} />
            {file ? (
              <div>
                <FileText size={24} style={{ display: 'inline-block', verticalAlign: 'middle', marginRight: '8px', color: 'var(--text-main)' }} />
                <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>{file.name}</span>
              </div>
            ) : (
              <div>
                <p style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '8px', color: 'var(--text-main)' }}>Drag & drop your CSV file here</p>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>or click to select file</p>
              </div>
            )}
          </div>

          {error && (
            <div className="alert-error" style={{ marginBottom: '24px' }}>
              <AlertCircle size={20} />
              <span>{error}</span>
            </div>
          )}

          <button 
            className="btn-primary" 
            style={{ opacity: !file ? 0.5 : 1, width: '100%', padding: '14px', fontSize: '1rem' }}
            onClick={handleUpload}
            disabled={!file}
          >
            <Upload size={18} />
            Process Statement
          </button>
        </div>
      )}

      {loading && (
        <div className="card" style={{ maxWidth: '600px', margin: '0 auto', textAlign: 'center', padding: '64px 24px' }}>
          <Loader size={48} color="var(--accent-color)" style={{ margin: '0 auto 24px', animation: 'spin 2s linear infinite' }} />
          <h2 style={{ fontSize: '1.5rem', marginBottom: '8px' }}>Categorizing transactions...</h2>
          <p style={{ color: 'var(--text-muted)' }}>Our AI is analyzing each transaction. This may take a moment.</p>
        </div>
      )}

      {result && (
        <div>
          <div className="alert-success" style={{ marginBottom: '32px' }}>
            <CheckCircle size={24} />
            <div style={{ flex: 1 }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Processing Complete!</h3>
              <p style={{ margin: 0, opacity: 0.9 }}>Successfully imported and categorized your bank statement.</p>
            </div>
            <button onClick={reset} className="btn-secondary" style={{ backgroundColor: 'transparent', border: '1px solid var(--credit-border)', color: 'var(--credit-text)' }}>
              Upload another
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '24px', marginBottom: '32px' }}>
            <SummaryCard title="Total Transactions" value={result.total_transactions} icon={List} />
            <SummaryCard title="Total Spent" value={result.total_spent} icon={FileText} isCurrency={true} />
            <SummaryCard title="Total Income" value={result.total_income || 0} icon={CheckCircle} isCurrency={true} isIncome={true} />
          </div>

          <div className="card">
            <h3 style={{ marginBottom: '24px', fontSize: '1.25rem', fontWeight: 600 }}>Category Breakdown</h3>
            <div style={{ height: '400px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={result.chartData} layout="vertical" margin={{ top: 5, right: 30, left: 100, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="var(--border-color)" />
                  <XAxis type="number" stroke="var(--text-muted)" />
                  <YAxis dataKey="name" type="category" width={90} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} stroke="none" />
                  <Tooltip cursor={{ fill: 'rgba(0,0,0,0.03)' }} contentStyle={{ borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', boxShadow: 'var(--shadow-md)' }} />
                  <Bar dataKey="count" fill="var(--text-main)" radius={[0, 4, 4, 0]} name="Transactions" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
      </>
      )}

      {activeTab === 'receipt' && (
        <div style={{ maxWidth: '800px' }}>
          <ReceiptUpload onUploadSuccess={() => setRefreshTrigger(prev => prev + 1)} />
          <PendingReceipts refreshTrigger={refreshTrigger} onResolved={() => setRefreshTrigger(prev => prev + 1)} />
        </div>
      )}
    </div>
  );
};

export default Home;
