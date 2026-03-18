import React, { useState, useRef, useEffect } from 'react';
import { Clipboard, Check } from 'lucide-react';
import { IconButton } from '@/components/ui/Button';

interface CodeBlockProps {
  code: string | string[];
  language?: 'bash' | 'powershell' | 'sql';
  title?: string;
  copyable?: boolean;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({
  code,
  language = 'bash',
  title,
  copyable = true,
}) => {
  const [copied, setCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 컴포넌트 언마운트 시 타이머 정리
  useEffect(() => {
    return () => {
      if (copyTimerRef.current) {
        clearTimeout(copyTimerRef.current);
      }
    };
  }, []);

  const codeString = Array.isArray(code) ? code.join(' ') : code;

  const handleCopy = async () => {
    try {
      // 클립보드 API 사용 (HTTPS 환경)
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(codeString);
      } else {
        // Fallback: execCommand 사용
        const textArea = document.createElement('textarea');
        textArea.value = codeString;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }

      setCopied(true);
      // 이전 타이머가 있으면 취소
      if (copyTimerRef.current) {
        clearTimeout(copyTimerRef.current);
      }
      copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('클립보드 복사 실패:', err);
    }
  };

  const getLanguageLabel = () => {
    switch (language) {
      case 'powershell':
        return 'PowerShell';
      case 'sql':
        return 'SQL';
      default:
        return 'Bash';
    }
  };

  return (
    <div className="relative">
      {title && (
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700">{title}</span>
          <span className="text-xs text-gray-500">{getLanguageLabel()}</span>
        </div>
      )}

      <div className="relative bg-gray-900 rounded-lg overflow-hidden">
        <pre className="p-4 overflow-x-auto">
          <code className="text-sm text-green-400 font-mono">{codeString}</code>
        </pre>

        {copyable && (
          <IconButton
            icon={copied ? <Check className="w-5 h-5 text-green-400" /> : <Clipboard className="w-5 h-5 text-gray-400" />}
            onClick={handleCopy}
            title="클립보드에 복사"
            className="absolute top-2 right-2 p-2 bg-gray-800 hover:bg-gray-700 rounded"
          />
        )}
      </div>

      {copied && (
        <div className="absolute top-0 right-0 mt-12 mr-2 px-3 py-1 bg-green-600 text-white text-xs rounded shadow-lg">
          복사됨!
        </div>
      )}
    </div>
  );
};
