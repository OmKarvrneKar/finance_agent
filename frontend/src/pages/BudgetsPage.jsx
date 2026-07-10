import React from 'react';
import BudgetGoals from '../components/BudgetGoals';
import WhatIfSimulator from '../components/WhatIfSimulator';

const BudgetsPage = () => {
  return (
    <div className="layout-container">
      <div className="page-header">
        <h1 className="page-title">Budgets & Goals</h1>
        <p className="page-description">Set spending caps and simulate hypothetical financial scenarios.</p>
      </div>
      
      <BudgetGoals />
      <WhatIfSimulator />
    </div>
  );
};

export default BudgetsPage;
