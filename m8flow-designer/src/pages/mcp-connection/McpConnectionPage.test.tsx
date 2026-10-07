import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const URL = 'https://qa.m8flow.ai/mcp';

async function renderPage(url: string) {
  vi.stubEnv('VITE_MCP_SERVER_URL', url);
  vi.resetModules();
  const { default: McpConnectionPage } = await import('./McpConnectionPage');
  render(<McpConnectionPage />);
}

// Restored after each test so a stubbed clipboard never leaks into other tests.
const originalClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard');

afterEach(() => {
  vi.unstubAllEnvs();
  if (originalClipboard) {
    Object.defineProperty(navigator, 'clipboard', originalClipboard);
  } else {
    delete (navigator as { clipboard?: Clipboard }).clipboard;
  }
});

describe('McpConnectionPage', () => {
  it('shows the server URL and client setup cards', async () => {
    await renderPage(URL);
    expect(screen.getByText(URL)).toBeInTheDocument();
    for (const title of ['Claude Code', 'Cursor', 'Claude.ai']) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
    }
  });

  it('copies the URL, the Claude Code command and the Cursor config', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    await renderPage(URL);

    fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
    fireEvent.click(screen.getByRole('button', { name: 'Copy command' }));
    fireEvent.click(screen.getByRole('button', { name: 'Copy config' }));

    expect(await screen.findAllByRole('button', { name: 'Copied' })).toHaveLength(3);
    expect(writeText).toHaveBeenNthCalledWith(1, URL);
    expect(writeText).toHaveBeenNthCalledWith(2, `claude mcp add --transport http m8flow ${URL}`);
    expect(JSON.parse(writeText.mock.calls[2][0])).toEqual({ mcpServers: { m8flow: { url: URL } } });
  });

  it('opens the Claude.ai connector steps', async () => {
    await renderPage(URL);
    fireEvent.click(screen.getByRole('button', { name: 'View steps' }));
    expect(await screen.findByRole('dialog')).toHaveTextContent('Add custom connector');
  });

  it('shows a notice and no client cards when the URL is not configured', async () => {
    await renderPage('');
    expect(screen.getByText(/not configured/)).toBeInTheDocument();
    expect(screen.queryByText('Claude Code')).not.toBeInTheDocument();
  });
});
