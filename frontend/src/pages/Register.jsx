import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Wallet } from 'lucide-react';

function validatePassword(pw) {
  const errors = [];
  if (pw.length < 8) errors.push('at least 8 characters');
  if (!/[A-Z]/.test(pw)) errors.push('one uppercase letter');
  if (!/[a-z]/.test(pw)) errors.push('one lowercase letter');
  if (!/\d/.test(pw)) errors.push('one digit');
  return errors;
}

const Register = () => {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const { register, loading } = useAuth();
  const navigate = useNavigate();

  const passwordErrors = validatePassword(password);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (passwordErrors.length > 0) {
      setError('Password does not meet requirements.');
      return;
    }
    try {
      await register(email, password, fullName);
      setSuccess(true);
      setTimeout(() => navigate('/login'), 1500);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 'calc(100vh - 128px)' }}>
      <div style={{ width: '100%', maxWidth: '400px', padding: '0 24px' }}>
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <Wallet size={40} style={{ color: 'var(--primary-blue)' }} />
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginTop: '12px', color: 'var(--text-main)' }}>Create account</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>Start tracking your finances</p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {error && (
            <div style={{ padding: '12px', borderRadius: '8px', backgroundColor: 'var(--debit-bg)', color: 'var(--debit-text)', fontSize: '0.875rem' }}>
              {error}
            </div>
          )}
          {success && (
            <div style={{ padding: '12px', borderRadius: '8px', backgroundColor: 'var(--credit-bg)', color: 'var(--credit-text)', fontSize: '0.875rem' }}>
              Account created! Redirecting to login...
            </div>
          )}

          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, marginBottom: '6px', color: 'var(--text-main)' }}>Full name</label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', border: '1px solid var(--border-color)', fontSize: '0.875rem', outline: 'none', boxSizing: 'border-box' }}
              placeholder="John Doe"
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, marginBottom: '6px', color: 'var(--text-main)' }}>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', border: '1px solid var(--border-color)', fontSize: '0.875rem', outline: 'none', boxSizing: 'border-box' }}
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, marginBottom: '6px', color: 'var(--text-main)' }}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', border: '1px solid var(--border-color)', fontSize: '0.875rem', outline: 'none', boxSizing: 'border-box' }}
              placeholder="Min 8 characters"
            />
            {password.length > 0 && (
              <div style={{ marginTop: '6px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {passwordErrors.length === 0 ? (
                  <span style={{ color: 'var(--credit-text)' }}>Password meets requirements</span>
                ) : (
                  <span>Must include: {passwordErrors.join(', ')}</span>
                )}
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || success}
            style={{ width: '100%', padding: '10px 16px', borderRadius: '8px', border: 'none', backgroundColor: 'var(--primary-blue)', color: 'white', fontSize: '0.875rem', fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.7 : 1 }}
          >
            {loading ? 'Creating account...' : 'Create account'}
          </button>

          <p style={{ textAlign: 'center', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Already have an account? <Link to="/login" style={{ color: 'var(--accent-color)', textDecoration: 'none', fontWeight: 500 }}>Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  );
};

export default Register;
