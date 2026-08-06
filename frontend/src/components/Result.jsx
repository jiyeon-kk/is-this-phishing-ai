import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  ShieldQuestion,
  Building2,
  Flag,
  RotateCw,
  Home as HomeIcon,
  ChevronRight,
  CircleAlert,
} from 'lucide-react'

const LEVEL_STYLES = {
  safe: {
    label: '안전',
    badge: 'border-emerald-300 bg-emerald-50 text-emerald-700',
    bar: 'bg-emerald-500',
    text: 'text-emerald-600',
    icon: ShieldCheck,
    message: '위험 신호가 발견되지 않았습니다.',
  },
  suspicious: {
    label: '의심',
    badge: 'border-amber-300 bg-amber-50 text-amber-700',
    bar: 'bg-amber-500',
    text: 'text-amber-600',
    icon: ShieldAlert,
    message: '신중한 확인이 필요합니다.',
  },
  danger: {
    label: '위험',
    badge: 'border-red-300 bg-red-50 text-red-700',
    bar: 'bg-red-500',
    text: 'text-red-600',
    icon: ShieldX,
    message: '즉각적인 주의가 필요합니다.',
  },
}

// API 응답 필드명이 바뀌면 이 값들만 고치면 됨
const SIGNAL_FIELDS = {
  model: 'model',
  rule: 'rule',
  reputation: 'reputation',
}

// 계약(docs/INTEGRATION.md, backend/schemas.py Cluster): {id, size, report_count, risk}
// org_count는 실제 스키마에 없는 필드 — size(클러스터 노드 수)를 씀
const CLUSTER_FIELDS = {
  orgCount: 'size',
  reportCount: 'report_count',
}

const SIGNAL_ITEMS = [
  {
    key: SIGNAL_FIELDS.model,
    label: '모델',
    desc: 'AI 모델이 학습한 스팸·피싱 패턴과의 유사도',
    barClass: 'bg-red-500',
    textClass: 'text-red-600',
  },
  {
    key: SIGNAL_FIELDS.rule,
    label: '규칙',
    desc: '등록된 위험 도메인·URL 패턴 규칙 일치도',
    barClass: 'bg-orange-500',
    textClass: 'text-orange-600',
  },
  {
    key: SIGNAL_FIELDS.reputation,
    label: '평판',
    desc: '신고 이력·평판 데이터베이스 기반 위험도',
    barClass: 'bg-yellow-400',
    textClass: 'text-yellow-600',
  },
]

// 근거 순위 배지 — 테두리만 있는 무채색 번호 원
const REASON_RANK_STYLE = 'border border-slate-300 bg-white text-slate-700'

const CARD_CLASS = 'rounded-2xl border border-slate-200 bg-white shadow-sm'
const COUNT_UP_MS = 600

// 위험도 %를 0에서 실제 값까지 부드럽게 채워 보여줌 (ease-out)
function useCountUp(target, durationMs) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    let frame
    const start = performance.now()

    const tick = (now) => {
      const progress = Math.min((now - start) / durationMs, 1)
      const eased = 1 - (1 - progress) ** 3
      setValue(Math.round(target * eased))
      if (progress < 1) frame = requestAnimationFrame(tick)
    }

    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs])

  return value
}

function LoadingState() {
  return (
    <div
      className={`flex flex-col items-center gap-4 p-10 text-center ${CARD_CLASS}`}
    >
      <p className="text-base font-bold text-slate-900">분석 진행 중</p>
      <div className="flex gap-2">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="h-2.5 w-2.5 animate-bounce rounded-full bg-slate-300"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
      <div className="flex flex-col gap-1">
        <p className="text-sm text-slate-500">보안 데이터베이스를 검색하고 있습니다</p>
        <p className="text-xs text-slate-400">잠시만 기다려주세요</p>
      </div>
    </div>
  )
}

// 실제 에러 코드는 백엔드 계약에 없어 고정 문자열로 표기 (추후 서버 에러 코드 붙이면 교체)
function ErrorState({ message, onRetry }) {
  const navigate = useNavigate()

  return (
    <div className={`flex flex-col items-center gap-5 p-8 text-center ${CARD_CLASS}`}>
      <div className="flex flex-col gap-2">
        <p className="text-lg font-bold text-slate-900">분석 오류 발생</p>
        <p className="text-sm text-slate-500">{message}</p>
      </div>

      <div className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-left">
        <p className="text-xs text-slate-400">오류 코드</p>
        <p className="font-mono text-sm text-slate-600">ERR_ANALYZE_FAILED</p>
      </div>

      <div className="flex w-full flex-col gap-3">
        <button
          type="button"
          onClick={onRetry}
          className="flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-900/20 transition hover:bg-slate-800"
        >
          <RotateCw size={15} strokeWidth={2.25} />
          다시 분석하기
        </button>
        <button
          type="button"
          onClick={() => navigate('/')}
          className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-6 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
        >
          <HomeIcon size={15} strokeWidth={2.25} />
          홈으로 돌아가기
        </button>
      </div>
    </div>
  )
}

function Result({ result, loading, error, text, sender, onReset }) {
  const navigate = useNavigate()
  const percent = Math.round((result?.risk_score ?? 0) * 100)
  const animatedPercent = useCountUp(percent, COUNT_UP_MS)

  if (loading) return <LoadingState />

  if (error) return <ErrorState message={error} onRetry={onReset} />

  if (!result) {
    return (
      <div
        className={`flex flex-col items-center gap-3 p-10 text-center ${CARD_CLASS}`}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-50 text-slate-300">
          <ShieldQuestion size={24} strokeWidth={1.75} />
        </div>
        <p className="text-sm text-slate-400">
          아직 분석 결과가 없습니다. 문자 내용을 입력하고 분석하기 버튼을
          눌러주세요.
        </p>
      </div>
    )
  }

  const {
  level,
  reasons,
  evidence,
  signals,
  cluster,
  campaign,
  confidence,
  review_required,
  review_reason,
} = result

  const levelStyle = LEVEL_STYLES[level] ?? LEVEL_STYLES.suspicious
  const LevelIcon = levelStyle.icon

  const confidenceLabel = {
    high: '높음',
    medium: '보통',
    low: '낮음',
  }[confidence] ?? '확인 필요'

  const confidenceStyle = {
    high: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    medium: 'border-amber-200 bg-amber-50 text-amber-700',
    low: 'border-red-200 bg-red-50 text-red-700',
  }[confidence] ?? 'border-slate-200 bg-slate-50 text-slate-700'

  const summaryMessage = review_required
    ? '위험 가능성이 있지만 추가 확인이 필요합니다.'
    : levelStyle.message

  return (
    <div
      className={`flex flex-col gap-6 p-5 sm:p-8 ${CARD_CLASS} [animation:card-in_0.35s_ease-out]`}
    >
      <div className="flex flex-col gap-1">
        <p className="text-sm font-semibold text-slate-700">분석 결과</p>
        <p className="text-xs text-slate-400">최종 판정 및 탐지 근거 요약</p>
      </div>

      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm text-slate-400">위험도</p>
          <p
            className={`text-4xl font-extrabold ${levelStyle.text}`}
            style={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {animatedPercent}%
          </p>
        </div>
        <span
          className={`flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-sm font-semibold [animation:badge-pop_0.3s_ease-out] ${levelStyle.badge}`}
        >
          <LevelIcon size={15} strokeWidth={2.25} />
          {levelStyle.label}
        </span>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={`h-full rounded-full transition-all duration-500 ${levelStyle.bar}`}
            style={{ width: `${percent}%` }}
          />
        </div>
        <div className="flex justify-between text-[11px] text-slate-300">
          <span>0</span>
          <span>50</span>
          <span>100</span>
        </div>
        <p className="text-xs font-medium text-slate-500">
          {summaryMessage}
        </p>
      </div>

      {confidence && (
  <div className="flex flex-col gap-3">
    <div
      className={`flex items-center justify-between rounded-xl border px-4 py-3 ${confidenceStyle}`}
    >
      <div className="flex items-center gap-2">
        <ShieldQuestion size={16} strokeWidth={2.25} />
        <span className="text-sm font-semibold">판단 신뢰도</span>
      </div>

      <span className="text-sm font-bold">{confidenceLabel}</span>
    </div>

    {review_required && (
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
        <div className="flex items-start gap-2">
          <CircleAlert
            size={17}
            strokeWidth={2.25}
            className="mt-0.5 flex-shrink-0 text-amber-600"
          />

          <div className="flex flex-col gap-1">
            <p className="text-sm font-bold text-amber-800">
              추가 확인 필요
            </p>

            {review_reason && (
              <p className="text-xs leading-5 text-amber-700">
                {review_reason}
              </p>
            )}
          </div>
        </div>
      </div>
    )}
  </div>
)}
      {reasons?.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-slate-700">근거</p>
          <ul className="flex flex-col gap-2.5">
            {reasons.map((reason, i) => (
              <li key={i} className="flex items-start gap-3 text-sm">
                <span
                  className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold ${REASON_RANK_STYLE}`}
                >
                  {i + 1}
                </span>
                <div className="flex flex-col">
                  <span className="text-slate-700">{reason}</span>
                  <span className="text-xs text-slate-400">우선순위 {i + 1}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {evidence?.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-slate-700">탐지 증거</p>
          <div className="flex flex-wrap gap-2">
            {evidence.map((e, i) => (
              <span
                key={i}
                className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600"
              >
                <span className="font-semibold text-slate-400">{e.type}</span>
                {' · '}
                {e.detail}
              </span>
            ))}
          </div>
        </div>
      )}

      {signals && (
        <div className="flex flex-col gap-3">
          <p className="text-sm font-medium text-slate-700">
            신호 분석
          </p>
          {SIGNAL_ITEMS.map(({ key, label, desc, barClass, textClass }) => {
            const value = signals[key]
            if (value == null) return null
            const signalPercent = Math.round(value * 100)
            return (
              <div key={key} className="flex flex-col gap-1">
                <div className="flex justify-between text-xs text-slate-500">
                  <span className="font-medium text-slate-600">{label}</span>
                  <span className={`font-semibold ${textClass}`}>{signalPercent}%</span>
                </div>
                <p className="text-[11px] text-slate-400">{desc}</p>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${barClass}`}
                    style={{ width: `${signalPercent}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}

      {campaign?.matched && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-700">
              유사 피싱 캠페인
            </p>

            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                campaign.status === 'rapidly_spreading'
                  ? 'bg-red-50 text-red-700'
                  : campaign.status === 'active'
                    ? 'bg-amber-50 text-amber-700'
                    : 'bg-slate-100 text-slate-600'
              }`}
            >
              {campaign.status === 'rapidly_spreading'
                ? '빠르게 확산 중'
                : campaign.status === 'active'
                  ? '활동 중'
                  : '과거 사례'}
            </span>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm font-semibold text-slate-800">
              기존 {campaign.similar_case_count}건의 신고와 연결되었습니다.
            </p>

            <p className="mt-1 text-xs text-slate-500">
              연결 근거:{' '}
              {campaign.match_type === 'domain'
                ? '동일 도메인'
                : campaign.match_type === 'sender'
                  ? '동일 발신번호'
                  : '유사 문구'}
            </p>

            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-lg bg-white px-3 py-2">
                <p className="text-[11px] text-slate-400">동일 도메인</p>
                <p className="text-lg font-bold text-slate-900">
                  {campaign.shared_domain_count}건
                </p>
              </div>

              <div className="rounded-lg bg-white px-3 py-2">
                <p className="text-[11px] text-slate-400">유사 문구</p>
                <p className="text-lg font-bold text-slate-900">
                  {campaign.similar_phrase_count}건
                </p>
              </div>

              <div className="rounded-lg bg-white px-3 py-2">
                <p className="text-[11px] text-slate-400">동일 발신번호</p>
                <p className="text-lg font-bold text-slate-900">
                  {campaign.shared_sender_count}건
                </p>
              </div>

              <div className="rounded-lg bg-white px-3 py-2">
                <p className="text-[11px] text-slate-400">최근 24시간</p>
                <p className="text-lg font-bold text-slate-900">
                  {campaign.reports_last_24h}건
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
      {cluster && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-slate-700">클러스터 요약</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
              <p className="text-xs text-slate-400">연결된 특징 수</p>
              <p className="text-xl font-bold text-slate-900">
                {cluster[CLUSTER_FIELDS.orgCount]}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
              <p className="text-xs text-slate-400">연결된 캠페인 신고</p>
              <p className="text-xl font-bold text-slate-900">
                {cluster[CLUSTER_FIELDS.reportCount]}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => navigate('/graph')}
            className="flex items-center gap-1 self-start text-xs font-medium text-slate-700 underline transition hover:text-slate-900"
          >
            <Building2 size={13} strokeWidth={2.25} />
            그래프에서 자세히 보기
            <ChevronRight size={13} strokeWidth={2.25} />
          </button>
        </div>
      )}

      <div className="flex flex-col gap-3 sm:flex-row">
        <button
          type="button"
          onClick={() => navigate('/report', { state: { text, sender, result } })}
          className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-900/20 transition hover:bg-slate-800 active:bg-slate-950"
        >
          <Flag size={16} strokeWidth={2.25} />
          신고하기
        </button>
        <button
          type="button"
          onClick={onReset}
          className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-6 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-100"
        >
          <RotateCw size={15} strokeWidth={2.25} />
          다시 분석하기
        </button>
      </div>
    </div>
  )
}

export default Result
