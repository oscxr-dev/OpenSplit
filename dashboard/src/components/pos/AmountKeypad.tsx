import { Delete } from 'lucide-react';

interface AmountKeypadProps {
  value: string;
  onChange: (value: string) => void;
}

const keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', 'del'];

export function AmountKeypad({ value, onChange }: AmountKeypadProps) {
  function handleKey(key: string) {
    if (key === 'del') {
      onChange(value.slice(0, -1));
    } else if (key === '') {
      // empty button (spacer)
    } else {
      // Prevent leading zeros
      if (value === '0' && key === '0') return;
      if (value === '0') {
        onChange(key);
      } else {
        onChange(value + key);
      }
    }
  }

  return (
    <div className="mx-auto grid max-w-xs grid-cols-3 gap-2.5 sm:max-w-sm sm:gap-3">
      {keys.map((key) => {
        if (key === '') {
          return <div key={`spacer-${Math.random()}`} />;
        }
        if (key === 'del') {
          return (
            <button
              key={key}
              onClick={() => handleKey(key)}
              className="flex h-12 items-center justify-center rounded-2xl bg-white/[0.055] text-white/55 transition-colors hover:bg-white/10 active:bg-white/15 sm:h-14"
              aria-label="Borrar"
            >
              <Delete className="w-6 h-6" />
            </button>
          );
        }
        return (
          <button
            key={key}
            onClick={() => handleKey(key)}
            className="h-12 rounded-2xl bg-white/[0.055] text-xl font-semibold text-white/85 transition-colors hover:bg-white/10 active:bg-white/15 sm:h-14 sm:text-2xl"
          >
            {key}
          </button>
        );
      })}
    </div>
  );
}
