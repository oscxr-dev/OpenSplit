import { QRCodeSVG } from 'qrcode.react';
import { Copy, Check } from 'lucide-react';
import { useState } from 'react';
import { formatSats, copyToClipboard } from '@/lib/utils';

interface InvoiceQRProps {
  bolt11: string;
  amount: number;
}

export function InvoiceQR({ bolt11, amount }: InvoiceQRProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await copyToClipboard(bolt11);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <p className="text-lg font-semibold text-gray-900">
        {formatSats(amount)}
      </p>

      <div className="bg-white p-4 rounded-2xl shadow-md border border-gray-200">
        <QRCodeSVG
          value={bolt11}
          size={220}
          level="M"
          fgColor="#1a1a1a"
          style={{ borderRadius: '8px' }}
        />
      </div>

      <button
        onClick={handleCopy}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-bitcoin transition-colors"
      >
        {copied ? (
          <>
            <Check className="w-4 h-4 text-green-500" />
            <span className="text-green-600">Copied</span>
          </>
        ) : (
          <>
            <Copy className="w-4 h-4" />
            <span>Copy invoice</span>
          </>
        )}
      </button>

      <p className="text-xs text-gray-400 break-all text-center max-w-xs">
        {bolt11.slice(0, 40)}...
      </p>
    </div>
  );
}
