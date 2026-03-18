import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Terminal, CheckCircle, XCircle } from 'lucide-react';
import { CodeBlock } from './CodeBlock';

interface CommandInfo {
  description: string;
  command: string | string[];
  dbTable?: string;
  dbCountQuery?: string;
  expectedOutput?: string;
  note?: string;
}

interface TerminalGuideProps {
  commands: CommandInfo[];
  title?: string;
  defaultExpanded?: boolean;
  showComparison?: boolean;
}

export const TerminalGuide: React.FC<TerminalGuideProps> = ({
  commands,
  title = '터미널에서 직접 실행하기',
  defaultExpanded = false,
  showComparison = true,
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg overflow-hidden mb-4">
      {/* 헤더 */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-blue-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Terminal className="w-5 h-5 text-blue-600" />
          <span className="font-semibold text-blue-900">{title}</span>
        </div>
        {expanded ? (
          <ChevronUp className="w-5 h-5 text-blue-600" />
        ) : (
          <ChevronDown className="w-5 h-5 text-blue-600" />
        )}
      </button>

      {/* 내용 */}
      {expanded && (
        <div className="px-4 pb-4 space-y-4">
          {/* 웹 UI vs 터미널 비교 */}
          {showComparison && (
            <div className="bg-white rounded-lg p-4 space-y-3">
              <h3 className="font-semibold text-gray-900 mb-2">왜 터미널에서 실행하나요?</h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* 웹 UI */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-700">웹 UI 실행</span>
                  </div>
                  <div className="space-y-1 text-sm">
                    <div className="flex items-start gap-2">
                      <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                      <span className="text-gray-600">클릭 한 번으로 실행</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <XCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                      <span className="text-gray-600">백그라운드 실행 시 불안정</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <XCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                      <span className="text-gray-600">실시간 로그 확인 어려움</span>
                    </div>
                  </div>
                </div>

                {/* 터미널 */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-700">터미널 실행 (권장)</span>
                  </div>
                  <div className="space-y-1 text-sm">
                    <div className="flex items-start gap-2">
                      <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                      <span className="text-gray-600">안정적인 실행</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                      <span className="text-gray-600">실시간 로그 확인</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                      <span className="text-gray-600">DB 저장 검증 가능</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 명령어 목록 */}
          <div className="space-y-4">
            <h3 className="font-semibold text-gray-900">실행 명령어</h3>

            {commands.map((cmd, index) => (
              <div key={index} className="space-y-2">
                <div className="flex items-start gap-2">
                  <span className="inline-flex items-center justify-center w-6 h-6 bg-blue-600 text-white text-xs font-bold rounded-full flex-shrink-0">
                    {index + 1}
                  </span>
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900 mb-2">{cmd.description}</p>
                    <CodeBlock code={cmd.command} copyable={true} />
                  </div>
                </div>

                {/* DB 검증 */}
                {cmd.dbCountQuery && (
                  <div className="ml-8 mt-2 p-3 bg-green-50 border border-green-200 rounded">
                    <p className="text-xs font-semibold text-green-900 mb-1">DB 저장 확인:</p>
                    <CodeBlock code={cmd.dbCountQuery} copyable={true} language="bash" />
                    {cmd.expectedOutput && (
                      <p className="text-xs text-green-700 mt-2">
                        예상 출력: {cmd.expectedOutput}
                      </p>
                    )}
                  </div>
                )}

                {/* 참고사항 */}
                {cmd.note && (
                  <div className="ml-8 mt-2 p-3 bg-yellow-50 border border-yellow-200 rounded">
                    <p className="text-xs text-yellow-800">💡 {cmd.note}</p>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* 실행 후 워크플로우 */}
          <div className="bg-gray-50 rounded-lg p-4 space-y-2">
            <h3 className="font-semibold text-gray-900 text-sm">실행 후 확인 절차</h3>
            <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
              <li>위 명령어를 Windows PowerShell 또는 CMD에서 실행</li>
              <li>스크립트 실행 완료까지 대기 (로그 확인)</li>
              <li>DB 검증 명령어로 데이터 저장 확인</li>
              <li>웹 UI에서 F5 새로고침하여 데이터 확인</li>
            </ol>
          </div>
        </div>
      )}
    </div>
  );
};
