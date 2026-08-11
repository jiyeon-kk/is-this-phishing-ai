import { useEffect, useState } from 'react'
import {
  TrendingUp,
  MessageSquareText,
  Link2,
  AlertTriangle,
  ExternalLink,
  ShieldAlert,
} from 'lucide-react'

import { getThreatFeed, getTrends } from '../api/client'
import RankedBarList from '../components/RankedBarList'


// getTrends() 실패 시 사용하는 목업 데이터
const MOCK_TRENDS = {
  top_phrases: [
    { label: '계좌 정지 안내', count: 42 },
    { label: '택배 배송 조회', count: 35 },
    { label: '환급금 조회', count: 28 },
    { label: '본인인증 필요', count: 19 },
  ],
  top_urls: [
    { label: 'phish-bank.kr', count: 37 },
    { label: 'bit.ly/abcxyz', count: 31 },
    { label: 'gov-refund.net', count: 24 },
    { label: 'short.url/kk22', count: 15 },
  ],
}


const SECTIONS = [
  {
    key: 'top_phrases',
    title: '주요 피싱 유형',
    icon: MessageSquareText,
    colorClass: 'bg-slate-900',
  },
  {
    key: 'top_urls',
    title: '최다 신고 URL',
    icon: Link2,
    colorClass: 'bg-slate-900',
  },
]


const sumCounts = (items) =>
  items?.reduce((sum, item) => sum + item.count, 0) ?? 0


function formatDate(dateString) {
  if (!dateString) {
    return '날짜 정보 없음'
  }

  const date = new Date(dateString)

  if (Number.isNaN(date.getTime())) {
    return dateString
  }

  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}


function getSourceStyle(source) {
  switch (source) {
    case 'KISA':
      return 'border-blue-200 bg-blue-50 text-blue-700'

    case '경찰청':
      return 'border-indigo-200 bg-indigo-50 text-indigo-700'

    case '금융감독원':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700'

    case 'SKT':
    case 'SK텔레콤':
      return 'border-violet-200 bg-violet-50 text-violet-700'

    default:
      return 'border-slate-200 bg-slate-50 text-slate-700'
  }
}


function Trends() {
  const [trends, setTrends] = useState(MOCK_TRENDS)
  const [loadError, setLoadError] = useState(null)

  const [officialAlerts, setOfficialAlerts] = useState([])
  const [threatFeedError, setThreatFeedError] = useState(null)
  const [threatFeedLoading, setThreatFeedLoading] = useState(true)


  useEffect(() => {
    getTrends()
      .then((data) => {
        setTrends(data)
        setLoadError(null)
      })
      .catch((err) => {
        console.error('트렌드 로드 실패:', err)

        setLoadError(
          '실시간 데이터를 불러오지 못해 예시 데이터를 보여드립니다.',
        )
      })
  }, [])


  useEffect(() => {
    setThreatFeedLoading(true)

    getThreatFeed()
      .then((data) => {
        setOfficialAlerts(data?.items ?? [])
        setThreatFeedError(null)
      })
      .catch((err) => {
        console.error('공식기관 위협 경보 로드 실패:', err)

        setOfficialAlerts([])
        setThreatFeedError(
          '공식기관 최신 위협 경보를 불러오지 못했습니다.',
        )
      })
      .finally(() => {
        setThreatFeedLoading(false)
      })
  }, [])


  return (
    <div className="flex flex-col gap-8">
      {/* ---------------------------------------------------------- */}
      {/* 페이지 제목 */}
      {/* ---------------------------------------------------------- */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <TrendingUp
            size={24}
            strokeWidth={2.25}
            className="text-slate-900"
          />

          <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            위협 트렌드
          </h1>
        </div>

        <p className="text-sm text-slate-500">
          최근 접수된 신고와 공식기관 경보를 기반으로 최신 스미싱 위협
          동향을 확인합니다.
        </p>
      </div>


      {/* ---------------------------------------------------------- */}
      {/* 사용자 신고 데이터 오류 */}
      {/* ---------------------------------------------------------- */}
      {loadError && (
        <div className="flex items-start gap-3 rounded-2xl border border-slate-300 bg-slate-50 p-4 text-sm text-slate-700 [animation:card-in_0.3s_ease-out]">
          <AlertTriangle
            size={16}
            className="mt-0.5 flex-shrink-0"
          />

          <span>{loadError}</span>
        </div>
      )}


      {/* ---------------------------------------------------------- */}
      {/* 사용자 신고 통계 */}
      {/* ---------------------------------------------------------- */}
      <section className="flex flex-col gap-5">
        <div>
          <h2 className="text-base font-bold text-slate-900">
            PhishGuard 신고 동향
          </h2>

          <p className="mt-1 text-xs text-slate-400">
            PhishGuard에 접수된 사용자 신고를 기준으로 집계합니다.
          </p>
        </div>


        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-center shadow-sm">
            <p className="text-xl font-bold text-slate-900">
              {(
                sumCounts(trends.top_phrases) +
                sumCounts(trends.top_urls)
              ).toLocaleString()}
            </p>

            <p className="text-xs text-slate-400">
              총 신고
            </p>
          </div>


          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-center shadow-sm">
            <p className="text-xl font-bold text-slate-900">
              {trends.top_urls?.length ?? 0}
            </p>

            <p className="text-xs text-slate-400">
              위험 도메인
            </p>
          </div>
        </div>


        {SECTIONS.map(
          (
            {
              key,
              title,
              icon,
              colorClass,
            },
            index,
          ) => (
            <RankedBarList
              key={key}
              title={title}
              icon={icon}
              colorClass={colorClass}
              items={trends[key] ?? []}
              delayMs={index * 80}
            />
          ),
        )}
      </section>


      {/* ---------------------------------------------------------- */}
      {/* 구분선 */}
      {/* ---------------------------------------------------------- */}
      <div className="border-t border-slate-200" />


      {/* ---------------------------------------------------------- */}
      {/* 공식기관 위협 경보 */}
      {/* ---------------------------------------------------------- */}
      <section className="flex flex-col gap-5">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white">
            <ShieldAlert
              size={18}
              strokeWidth={2.25}
            />
          </div>

          <div>
            <h2 className="text-lg font-bold text-slate-900">
              공식기관 최신 위협 경보
            </h2>

            <p className="mt-1 text-sm leading-5 text-slate-500">
              KISA·경찰청·금융감독원 등 공신력 있는 기관에서 안내한
              최신 피싱·스미싱 경보를 확인합니다.
            </p>
          </div>
        </div>


        {/* 공식기관 API 오류 */}
        {threatFeedError && (
          <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            <AlertTriangle
              size={16}
              className="mt-0.5 flex-shrink-0"
            />

            <span>{threatFeedError}</span>
          </div>
        )}


        {/* 로딩 */}
        {threatFeedLoading && (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 text-center text-sm text-slate-400 shadow-sm">
            공식기관 최신 경보를 불러오는 중입니다...
          </div>
        )}


        {/* 경보 없음 */}
        {!threatFeedLoading &&
          !threatFeedError &&
          officialAlerts.length === 0 && (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 text-center text-sm text-slate-400 shadow-sm">
              현재 표시할 공식기관 경보가 없습니다.
            </div>
          )}


        {/* 경보 카드 */}
        {!threatFeedLoading &&
          officialAlerts.length > 0 && (
            <div className="flex flex-col gap-3">
              {officialAlerts.map((alert) => (
                <article
                  key={alert.id}
                  className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-slate-300 hover:shadow-md"
                >
                  <div className="flex flex-col gap-4">
                    {/* 출처 / 날짜 / 카테고리 */}
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-full border px-2.5 py-1 text-[11px] font-bold ${
                          getSourceStyle(alert.source)
                        }`}
                      >
                        {alert.source}
                      </span>

                      {alert.category && (
                        <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-500">
                          {alert.category}
                        </span>
                      )}

                      <span className="ml-auto text-xs text-slate-400">
                        {formatDate(alert.published_at)}
                      </span>
                    </div>


                    {/* 제목 */}
                    <div>
                      <h3 className="text-[15px] font-bold leading-6 text-slate-900">
                        {alert.title}
                      </h3>

                      <p className="mt-2 text-sm leading-6 text-slate-600">
                        {alert.summary}
                      </p>
                    </div>


                    {/* 키워드 */}
                    {alert.keywords?.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {alert.keywords.map(
                          (
                            keyword,
                            index,
                          ) => (
                            <span
                              key={`${alert.id}-${keyword}-${index}`}
                              className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-500"
                            >
                              #{keyword}
                            </span>
                          ),
                        )}
                      </div>
                    )}


                    {/* 원문 이동 */}
                    {alert.url && (
                      <div className="border-t border-slate-100 pt-3">
                        <a
                          href={alert.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-700 transition hover:text-slate-950"
                        >
                          공식 원문 보기

                          <ExternalLink
                            size={13}
                            strokeWidth={2.25}
                          />
                        </a>
                      </div>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
      </section>
    </div>
  )
}


export default Trends