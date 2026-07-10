import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Navigation from './components/Navigation';
import Home from './pages/Home';
import Transactions from './pages/Transactions';
import AskAI from './pages/AskAI';
import Dashboard from './pages/Dashboard';
import Subscriptions from './pages/Subscriptions';
import BudgetsPage from './pages/BudgetsPage';

function App() {
  return (
    <Router>
      <div className="app-container">
        <Navigation />
        <main>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/ask" element={<AskAI />} />
            <Route path="/subscriptions" element={<Subscriptions />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/budgets" element={<BudgetsPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
