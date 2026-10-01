import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from './App';

describe('foundation app shell', () => {
  it('renders the product name and honest milestone status', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'MicroTrace' })).toBeInTheDocument();
    expect(screen.getByText('M0 — Foundation')).toBeInTheDocument();
  });
});
