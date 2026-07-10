import React, { useState, useEffect } from 'react';
import { AlertOctagon, AlertTriangle, Info, Check, X, ThumbsUp } from 'lucide-react';
import { getAnomalies, dismissAnomaly, confirmAnomaly } from '../utils/api';

const AnomalyAlerts = () => {
  const [anomalies, setAnomalies] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchAnomalies = async () => {
    try {
      const data = await getAnomalies();
      setAnomalies(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnomalies();
  }, []);

  const handleDismiss = async (id) => {
    setAnomalies(prev => prev.filter(a => a.id !== id));
    try {
      await dismissAnomaly(id);
    } catch (err) {
      console.error(err);
      fetchAnomalies(); 
    }
  };

  const handleConfirm = async (id) => {
    setAnomalies(prev => prev.filter(a => a.id !== id));
    try {
      await confirmAnomaly(id);
    } catch (err) {
      console.error(err);
      fetchAnomalies();
    }
  };

  if (loading) return null;

  if (anomalies.length === 0) {
    return (
      <div className="card" style={{ marginBottom: '32px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <ThumbsUp size={24} color="#10B981" />
        <div>
          <h3 style={{ margin: 0, fontSize: '1.1rem', color: 'var(--text-main)' }}>No unusual activity detected 👍</h3>
          <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-muted)' }}>Your spending looks normal based on recent history.</p>
        </div>
      </div>
    );
  }

  const getSeverityColor = (severity) => {
    switch(severity) {
      case 'critical': return '#EF4444'; // Red
      case 'warning': return '#F59E0B'; // Amber
      case 'info': return '#3B82F6'; // Blue
      default: return 'var(--text-muted)';
    }
  };

  const getSeverityIcon = (severity) => {
    switch(severity) {
      case 'critical': return <AlertOctagon size={20} color="#EF4444" />;
      case 'warning': return <AlertTriangle size={20} color="#F59E0B" />;
      case 'info': return <Info size={20} color="#3B82F6" />;
      default: return <Info size={20} />;
    }
  };

  const getTypeLabel = (type) => {
    switch(type) {
      case 'price_jump': return 'Price increase';
      case 'duplicate': return 'Possible duplicate charge';
      case 'unfamiliar_merchant': return 'New large expense';
      default: return 'Unusual activity';
    }
  };

  return (
    <div style={{ marginBottom: '32px' }}>
      <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <AlertTriangle size={24} color="#F59E0B" /> Anomaly Alerts
      </h3>
      
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {anomalies.map(a => (
          <div key={a.id} className="card" style={{ borderLeft: `4px solid ${getSeverityColor(a.severity)}`, display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', gap: '12px' }}>
                {getSeverityIcon(a.severity)}
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{getTypeLabel(a.type)}</div>
                  <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '4px' }}>{a.message}</div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button onClick={() => handleConfirm(a.id)} className="btn-secondary" style={{ padding: '6px 12px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '4px', borderColor: 'var(--border-color)', color: 'var(--text-main)' }}>
                  <Check size={14} /> Flag as issue
                </button>
                <button onClick={() => handleDismiss(a.id)} className="btn-secondary" style={{ padding: '6px 12px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '4px', borderColor: 'transparent', color: 'var(--text-muted)' }}>
                  <X size={14} /> Dismiss
                </button>
              </div>
            </div>
            
            <div style={{ backgroundColor: 'var(--bg-color)', padding: '12px', borderRadius: '6px', fontSize: '0.85rem', display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', flexWrap: 'wrap', gap: '12px' }}>
              <span>Merchant: <strong>{a.merchant}</strong></span>
              {a.dates && a.dates.length > 0 ? (
                <span>Dates: <strong>{a.dates.join(', ')}</strong></span>
              ) : (
                a.date && <span>Date: <strong>{a.date}</strong></span>
              )}
              {a.amount !== null && a.amount !== undefined && <span>Amount: <strong>₹{a.amount}</strong></span>}
              {a.percent_increase && <span>Increase: <strong>{a.percent_increase}%</strong></span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AnomalyAlerts;
