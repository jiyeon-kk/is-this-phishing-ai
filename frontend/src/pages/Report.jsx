import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft, RotateCw, ShieldCheck, ExternalLink } from 'lucide-react'
import { report } from '../api/client'
import { buildReportText } from '../utils/buildReportText'

const CARD_CLASS =
  'rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-8'

const OFFICIAL_REPORT_TARGETS = [
  {
    key: 'kisa',
    label: 'KISA 스팸신고로 이동',
    url: 'https://spam.kisa.or.kr',
  },
]
const REPORT_STATUS_LABELS = {
  pending: '신고 후보',
  suspected: '의심 사례',
  confirmed: '확정 사례',
  false_positive: '정상 판정',
}

const REPORT_STATUS_DESCRIPTIONS = {
  pending: '최초 신고가 접수되어 추가 신고와 근거를 확인 중입니다.',
  suspected: '동일 사례가 반복 신고되어 의심 사례로 분류되었습니다.',
  confirmed: '반복 신고 기준을 충족하여 확정 사례로 분류되었습니다.',
  false_positive: '검토 결과 정상 사례로 판정되었습니다.',
}

const REPORT_STATUS_STYLES = {
  pending: 'border-slate-200 bg-slate-50 text-slate-700',
  suspected: 'border-amber-200 bg-amber-50 text-amber-700',
  confirmed: 'border-red-200 bg-red-50 text-red-700',
  false_positive: 'border-emerald-200 bg-emerald-50 text-emerald-700',
}

// AnalyzeResponse엔 urls 필드가 없음(계약 ①) → evidence에서 URL 관련 항목을 뽑아 씀.
// type 값은 자유 텍스트라(backend/rules.py) 'url' 같은 고정값이 아니라 실제 타입 문자열로 매칭
const URL_EVIDENCE_TYPES = new Set(['피싱 URL 명단', '단축 URL', '의심 TLD'])
function extractUrls(result) {
  if (result?.urls?.length) return result.urls
  return (
    result?.evidence
      ?.filter((e) => URL_EVIDENCE_TYPES.has(e.type))
      .map((e) => e.detail) ?? []
  )
}

function Report() {
  const location = useLocation()
  const navigate = useNavigate()
  const result = location.state?.result

  const [text, setText] = useState(location.state?.text ?? '')
  const [sender, setSender] = useState(location.state?.sender ?? '')
  const [previewText, setPreviewText] = useState(() =>
    buildReportText({
      text: location.state?.text ?? '',
      sender: location.state?.sender ?? '',
      urls: extractUrls(result),
      riskScore: Math.round((result?.risk_score ?? 0) * 100),
      reasons: result?.reasons,
    }),
  )
  const [submitting, setSubmitting] = useState(false)
  const [reportResult, setReportResult] = useState(null)
  const [reportError, setReportError] = useState('')

  const regeneratePreview = () => {
    setPreviewText(
      buildReportText({
        text,
        sender,
        urls: extractUrls(result),
        riskScore: Math.round((result?.risk_score ?? 0) * 100),
        reasons: result?.reasons,
      }),
    )
  }

  // n21(PhishGuard 신고 제출) → n22(완료 메시지) → n23(그래프 갱신) → n24(조직 그래프 화면)
const handleReportToDb = async () => {
  setSubmitting(true)
  setReportError('')

  try {
    const response = await report(text, sender)

    setReportResult({
      status: response.status,
      reportCount: response.report_count,
      clusterCount: response.cluster_count,
    })
  } catch (err) {
    console.error('신고 요청 실패:', err)
    setReportError('신고 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.')
  } finally {
    setSubmitting(false)
  }
}
 const handleGoToGraph = () => {
  navigate('/graph', {
    state: {
      justReported: true,
      reportedText: text,
      reportedSender: sender,
      reportedUrls: extractUrls(result),
    },
  })
}

  const handleOfficialReport = async (url) => {
    try {
      await navigator.clipboard.writeText(previewText)
    } catch (err) {
      console.error('신고 문구 복사 실패:', err)
    }
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="flex flex-col gap-8">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 self-start text-sm text-slate-500 transition hover:text-slate-800"
      >
        <ArrowLeft size={15} strokeWidth={2.25} />
        돌아가기
      </button>

      <div className="flex flex-col gap-1.5">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          스미싱 신고
        </h1>
        <p className="text-sm text-slate-500">
          내용을 확인·수정한 뒤 PhishGuard DB 또는 공식 신고처로 접수할 수
          있습니다.
        </p>
      </div>

      <div className={CARD_CLASS}>
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-slate-700">
              문자 내용
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="문자 내용을 입력하세요"
              rows={6}
              className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 placeholder-slate-400 outline-none transition focus:border-slate-900 focus:bg-white focus:ring-2 focus:ring-slate-900/10"
            />
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-slate-700">
              발신번호 (선택)
            </label>
            <input
              type="text"
              value={sender}
              onChange={(e) => setSender(e.target.value)}
              placeholder="발신번호 (선택)"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 placeholder-slate-400 outline-none transition focus:border-slate-900 focus:bg-white focus:ring-2 focus:ring-slate-900/10"
            />
          </div>

          <button
            type="button"
            onClick={regeneratePreview}
            className="flex items-center gap-1.5 self-start text-sm font-medium text-slate-700 underline transition hover:text-slate-900"
          >
            <RotateCw size={14} strokeWidth={2.25} />
            신고 문구 미리보기 새로고침
          </button>
        </div>
      </div>

      <div className={CARD_CLASS}>
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-slate-700">
              신고 문구 미리보기 (수정 가능)
            </label>
            <p className="text-xs text-slate-400">
              문구를 검토하고 필요시 수정 후 신고해주세요.
            </p>
            <textarea
              value={previewText}
              onChange={(e) => setPreviewText(e.target.value)}
              rows={12}
              className="w-full resize-none whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 font-mono text-sm text-slate-800 outline-none transition focus:border-slate-900 focus:bg-white focus:ring-2 focus:ring-slate-900/10"
            />
          </div>
          {reportResult && (
            <div
              className={`rounded-xl border p-4 ${
                REPORT_STATUS_STYLES[reportResult.status] ??
                'border-slate-200 bg-slate-50 text-slate-700'
              }`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex flex-col gap-1">
                  <p className="text-sm font-bold">
                    {REPORT_STATUS_LABELS[reportResult.status] ?? '신고 접수 완료'}
                  </p>

                  <p className="text-xs leading-5 opacity-80">
                    {REPORT_STATUS_DESCRIPTIONS[reportResult.status] ??
                      '신고가 정상적으로 접수되었습니다.'}
                  </p>
                </div>

                <ShieldCheck size={20} strokeWidth={2.25} />
              </div>

              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-current/10 bg-white/60 px-3 py-2">
                  <p className="text-[11px] opacity-70">동일 사례 누적 신고</p>
                  <p className="text-lg font-bold">
                    {reportResult.reportCount}건
                  </p>
                </div>

                <div className="rounded-lg border border-current/10 bg-white/60 px-3 py-2">
                  <p className="text-[11px] opacity-70">현재 클러스터 수</p>
                  <p className="text-lg font-bold">
                    {reportResult.clusterCount}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={handleGoToGraph}
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-white px-4 py-2.5 text-sm font-semibold shadow-sm transition hover:bg-white/80"
              >
                그래프에서 반영 결과 보기
                <ExternalLink size={14} strokeWidth={2.25} />
              </button>
            </div>
          )}
          {reportError && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {reportError}
            </div>
          )}
          
          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={handleReportToDb}
              disabled={submitting || Boolean(reportResult)}
              className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-900/20 transition hover:bg-slate-800 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <ShieldCheck size={16} strokeWidth={2.25} />
              {submitting
                ? '제출 중...'
                : reportResult
                  ? '신고 완료'
                  : 'PhishGuard에 신고'}
            </button>

            {OFFICIAL_REPORT_TARGETS.map(({ key, label, url }) => (
              <button
                key={key}
                type="button"
                onClick={() => handleOfficialReport(url)}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-6 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-100"
              >
                <ExternalLink size={15} strokeWidth={2.25} />
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export default Report
