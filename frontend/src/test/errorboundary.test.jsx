import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ErrorBoundary from '../components/ErrorBoundary';
import NotFound from '../pages/NotFound';

// --- ErrorBoundary tests ---

function GoodComponent() {
  return <div>Everything is fine</div>;
}

let shouldThrow = false;
function SwitchableComponent() {
  if (shouldThrow) throw new Error('Test error');
  return <div>Everything is fine</div>;
}

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <GoodComponent />
      </ErrorBoundary>
    );
    expect(screen.getByText('Everything is fine')).toBeInTheDocument();
  });

  it('renders fallback UI when child throws', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    shouldThrow = true;
    render(
      <ErrorBoundary>
        <SwitchableComponent />
      </ErrorBoundary>
    );
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Try again')).toBeInTheDocument();
    expect(screen.getByText('Go to home page')).toBeInTheDocument();
    shouldThrow = false;
    consoleSpy.mockRestore();
  });

  it('Try again button resets error state', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    shouldThrow = true;
    render(
      <ErrorBoundary>
        <SwitchableComponent />
      </ErrorBoundary>
    );
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    // Stop throwing, then click Try again
    shouldThrow = false;
    fireEvent.click(screen.getByText('Try again'));
    expect(screen.getByText('Everything is fine')).toBeInTheDocument();
    consoleSpy.mockRestore();
  });

  it('Go to home page link points to /', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    shouldThrow = true;
    render(
      <ErrorBoundary>
        <SwitchableComponent />
      </ErrorBoundary>
    );
    const link = screen.getByText('Go to home page');
    expect(link).toHaveAttribute('href', '/');
    shouldThrow = false;
    consoleSpy.mockRestore();
  });
});

// --- NotFound tests ---

describe('NotFound', () => {
  it('renders 404 heading', () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    );
    expect(screen.getByText('404')).toBeInTheDocument();
  });

  it('renders page not found message', () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    );
    expect(screen.getByText('Page not found')).toBeInTheDocument();
    expect(screen.getByText(/doesn't exist or has been moved/)).toBeInTheDocument();
  });

  it('renders home page link', () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    );
    const link = screen.getByText('Go to home page');
    expect(link).toHaveAttribute('href', '/');
  });
});
