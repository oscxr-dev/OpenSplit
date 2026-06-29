// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { SplitRuleForm } from './SplitRuleForm';

afterEach(cleanup);

const noop = async () => {};

describe('SplitRuleForm initial state', () => {
  it('mounts an empty form when no defaultValues are given (the "New rule" case)', () => {
    render(<SplitRuleForm onSubmit={noop} onCancel={() => {}} />);

    expect((screen.getByLabelText('Rule name') as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText('Label') as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText('Lightning address') as HTMLInputElement).value).toBe('');
    // A fresh form is not yet allocated, so Save is disabled.
    expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('loads the rule data when defaultValues are provided (the "Edit" case)', () => {
    render(
      <SplitRuleForm
        defaultValues={{
          name: 'BitCrew',
          targets: [{ label: 'Alice', ln_address: 'alice@wallet.com', percentage: 100, order: 0 }],
        }}
        onSubmit={noop}
        onCancel={() => {}}
      />
    );

    expect((screen.getByLabelText('Rule name') as HTMLInputElement).value).toBe('BitCrew');
    expect((screen.getByLabelText('Label') as HTMLInputElement).value).toBe('Alice');
    expect((screen.getByLabelText('Lightning address') as HTMLInputElement).value).toBe('alice@wallet.com');
  });

  it('does not leak the previous rule across separate mounts (New after Edit)', () => {
    // First mount edits a rule…
    const edit = render(
      <SplitRuleForm
        defaultValues={{
          name: 'BitCrew',
          targets: [{ label: 'Alice', ln_address: 'alice@wallet.com', percentage: 100, order: 0 }],
        }}
        onSubmit={noop}
        onCancel={() => {}}
      />
    );
    expect((screen.getByLabelText('Rule name') as HTMLInputElement).value).toBe('BitCrew');
    edit.unmount();

    // …a subsequent fresh mount (what "New rule" does after the parent fix) is empty.
    render(<SplitRuleForm onSubmit={noop} onCancel={() => {}} />);
    expect((screen.getByLabelText('Rule name') as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText('Label') as HTMLInputElement).value).toBe('');
  });
});
