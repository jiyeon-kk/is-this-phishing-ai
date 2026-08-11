import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ShieldAlert,
  ScanSearch,
  Info,
  FlaskConical,
} from 'lucide-react'

import { analyze } from '../api/client'
import Result from '../components/Result'
import {
  loadHistory,
  addHistoryEntry,
  formatRelativeTime,
} from '../utils/history'


const HISTORY_BADGE =
  'border-slate-300 bg-white text-slate-700'

const HISTORY_LABEL = {
  safe: '안전',
  suspicious: '주의',
  danger: '위험',
}


function Analyze() {
  const [text, setText] = useState('')
  const [sender, setSender] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [history, setHistory] = useState(
    () => loadHistory(),
  )


  const handleAnalyze = async () => {
    if (!text.trim()) {
      setError('문자 내용을 입력해주세요.')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const data = await analyze(
        text,
        sender,
      )

      setResult(data)

      setHistory(
        addHistoryEntry({
          text,
          sender,
          level: data.level,
        }),
      )
    } catch {
      setError(
        '분석 요청에 실패했습니다. 잠시 후 다시 시도해주세요.',
      )
    } finally {
      setLoading(false)
    }
  }


  // 다시 분석하기
  const handleReset = () => {
    setText('')
    setSender('')
    setResult(null)
    setError(null)
  }


  return (
    <div className="flex flex-col gap-8">

      {/* ================================================== */}
      {/* 페이지 제목 */}
      {/* ================================================== */}

      <div className="flex items-start justify-between gap-4">

        <div className="flex flex-col gap-1.5">

          <div className="flex items-center gap-2">
            <ShieldAlert
              className="text-slate-900"
              size={22}
              strokeWidth={2.25}
            />

            <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              문자 위험도 분석
            </h1>
          </div>


          <p className="text-sm text-slate-500">
            수신한 문자를 그대로 붙여넣으면 AI가 스미싱 위험도를 즉시 분석합니다.
          </p>

        </div>


        {/* 우회 대응 테스트 보조 버튼 */}

        <Link
          to="/adversarial"
          className="
            mt-1
            inline-flex
            flex-shrink-0
            items-center
            gap-1.5
            rounded-lg
            border
            border-slate-200
            bg-white
            px-3
            py-1.5
            text-[11px]
            font-medium
            text-slate-500
            shadow-sm
            transition
            hover:border-blue-200
            hover:bg-blue-50/40
            hover:text-blue-600
          "
        >
          <FlaskConical size={13} />

          우회 대응 테스트
        </Link>

      </div>


      {/* ================================================== */}
      {/* 분석 입력 */}
      {/* ================================================== */}

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-8">

        <div className="flex flex-col gap-5">

          {/* 문자 내용 */}

          <div className="flex flex-col gap-2">

            <label className="text-sm font-medium text-slate-700">
              문자 내용
            </label>

            <textarea
              value={text}
              onChange={(e) =>
                setText(e.target.value)
              }
              placeholder="문자 내용을 입력하세요"
              rows={6}
              className="
                w-full
                resize-none
                rounded-xl
                border
                border-slate-200
                bg-slate-50
                px-4
                py-3
                text-slate-900
                placeholder-slate-400
                outline-none
                transition
                focus:border-slate-900
                focus:bg-white
                focus:ring-2
                focus:ring-slate-900/10
              "
            />

          </div>


          {/* 발신번호 */}

          <div className="flex flex-col gap-2">

            <label className="text-sm font-medium text-slate-700">
              발신번호 (선택)
            </label>

            <input
              type="text"
              value={sender}
              onChange={(e) =>
                setSender(e.target.value)
              }
              placeholder="발신번호 (선택)"
              className="
                w-full
                rounded-xl
                border
                border-slate-200
                bg-slate-50
                px-4
                py-3
                text-slate-900
                placeholder-slate-400
                outline-none
                transition
                focus:border-slate-900
                focus:bg-white
                focus:ring-2
                focus:ring-slate-900/10
              "
            />

          </div>


          {/* 분석 버튼 */}

          <button
            type="button"
            onClick={handleAnalyze}
            disabled={
              loading ||
              !text.trim()
            }
            className="
              mt-2
              flex
              items-center
              justify-center
              gap-2
              rounded-xl
              bg-slate-900
              px-6
              py-3
              text-base
              font-semibold
              text-white
              shadow-lg
              shadow-slate-900/20
              transition
              hover:bg-slate-800
              active:scale-[0.98]
              disabled:cursor-not-allowed
              disabled:opacity-60
              disabled:active:scale-100
            "
          >
            <ScanSearch
              size={18}
              strokeWidth={2.25}
            />

            {loading
              ? '분석 중...'
              : '위험도 분석하기'}
          </button>

        </div>
      </div>


      {/* ================================================== */}
      {/* 입력 안내 */}
      {/* ================================================== */}

      <div className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm">

        <Info
          size={16}
          className="mt-0.5 flex-shrink-0 text-slate-400"
        />

        <div>

          <p className="font-semibold text-slate-700">
            입력 안내
          </p>

          <p className="text-slate-500">
            문자 본문은 필수 입력 항목입니다. 발신번호는 분석 정확도를 높입니다.
          </p>

        </div>

      </div>


      {/* ================================================== */}
      {/* 분석 결과 */}
      {/* ================================================== */}

      <Result
        result={result}
        loading={loading}
        error={error}
        text={text}
        sender={sender}
        onReset={handleReset}
      />


      {/* ================================================== */}
      {/* 최근 분석 결과 */}
      {/* ================================================== */}

      {history.length > 0 && (

        <div className="flex flex-col gap-3">

          <h2 className="text-sm font-semibold text-slate-700">
            최근 분석 결과
          </h2>


          {history.map((h) => (

            <div
              key={h.id}
              className="
                flex
                items-start
                justify-between
                gap-3
                rounded-xl
                border
                border-slate-200
                bg-white
                p-4
                shadow-sm
              "
            >

              <div className="flex min-w-0 flex-col gap-0.5">

                <p className="text-xs text-slate-400">
                  {h.sender || '발신번호 없음'}
                  {' · '}
                  {formatRelativeTime(
                    h.timestamp,
                  )}
                </p>

                <p className="break-words text-sm text-slate-700">
                  {h.snippet}
                </p>

              </div>


              <span
                className={`
                  flex-shrink-0
                  rounded-full
                  border
                  px-3
                  py-1
                  text-xs
                  font-semibold
                  ${HISTORY_BADGE}
                `}
              >
                {
                  HISTORY_LABEL[
                    h.level
                  ] ?? '주의'
                }
              </span>

            </div>

          ))}

        </div>

      )}

    </div>
  )
}


export default Analyze