// C 트랙 API 클라이언트 — 개발가이드 계약 ①②③ + B6(신고/트렌드) 기준.
//
// 백엔드가 INTEGRATION.md 계약대로 응답하면
// 이 파일은 가능하면 손대지 않고 사용한다.
//
// 계약 필드명이 바뀌면 normalize.js에서 대응한다.
// analyze/report/threat-feed는 현재 응답을 그대로 전달한다.

import {
  normalizeGraph,
  normalizeTrends,
} from './normalize'


async function handleResponse(res) {
  if (!res.ok) {
    throw new Error(`요청 실패 (${res.status})`)
  }

  return res.json()
}


// ----------------------------------------------------------------------
// 계약 ①
// POST /api/analyze
//
// 요청:
// {
//   text,
//   sender
// }
//
// 응답:
// AnalyzeResponse
//
// {
//   risk_score,
//   level,
//   reasons,
//   evidence,
//   signals,
//   cluster,
//   campaign,
//   urls,
//   confidence,
//   review_required,
//   review_reason,
//   signal_agreement,
//   signal_disagreement
// }
// ----------------------------------------------------------------------
export const analyze = (
  text,
  sender,
) =>
  fetch('/api/analyze', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      text,
      sender,
    }),
  }).then(handleResponse)


// ----------------------------------------------------------------------
// 계약 ②
// GET /api/graph
//
// 응답:
// {
//   nodes,
//   edges,
//   cluster_count
// }
// ----------------------------------------------------------------------
export const getGraph = () =>
  fetch('/api/graph')
    .then(handleResponse)
    .then(normalizeGraph)


// ----------------------------------------------------------------------
// 계약 ④
// GET /api/trends
//
// 응답:
// {
//   top_phrases,
//   top_urls
// }
// ----------------------------------------------------------------------
export const getTrends = () =>
  fetch('/api/trends')
    .then(handleResponse)
    .then(normalizeTrends)


// ----------------------------------------------------------------------
// 계약 ③
// POST /api/report
//
// 요청:
// {
//   text,
//   sender
// }
//
// 응답:
// {
//   ok,
//   cluster_count,
//   status,
//   report_count
// }
// ----------------------------------------------------------------------
export const report = (
  text,
  sender,
) =>
  fetch('/api/report', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      text,
      sender,
    }),
  }).then(handleResponse)


// ----------------------------------------------------------------------
// 우회 공격 시뮬레이션
// POST /api/adversarial
//
// 요청:
// {
//   text
// }
//
// 응답:
// {
//   original,
//   variants: [
//     {
//       type,
//       label,
//       text
//     }
//   ]
// }
// ----------------------------------------------------------------------
export const generateAdversarialVariants = (
  text,
) =>
  fetch('/api/adversarial', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      text,
    }),
  }).then(handleResponse)


// ----------------------------------------------------------------------
// 공식기관 최신 피싱·스미싱 위협 경보
// GET /api/threat-feed
//
// 응답:
// {
//   items: [
//     {
//       id,
//       source,
//       title,
//       published_at,
//       category,
//       summary,
//       keywords,
//       url
//     }
//   ]
// }
// ----------------------------------------------------------------------
// 공식기관 최신 피싱·스미싱 위협 경보
export const getThreatFeed = () =>
  fetch('/api/threat-feed')
    .then(handleResponse)