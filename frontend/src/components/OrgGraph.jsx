import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import ForceGraph2D from 'react-force-graph-2d'
import { Network } from 'lucide-react'

import { MOCK_GRAPH } from '../utils/mockGraph'


// API 응답 필드명이 바뀌면 이 값들만 수정
const GRAPH_FIELDS = {
  nodes: 'nodes',
  edges: 'edges',
  clusterCount: 'cluster_count',
}


const NODE_TYPE_COLORS = {
  number: '#0284c7',
  url: '#db2777',
  phrase: '#ca8a04',
}

const DEFAULT_NODE_COLOR = '#64748b'

// 방금 신고한 URL 강조색
const HIGHLIGHT_COLOR = '#2563eb'


const NODE_TYPE_LABELS = {
  number: '발신번호',
  url: 'URL',
  phrase: '핵심 문구',
}


const LEGEND_ITEMS = [
  {
    type: 'number',
    label: '발신번호',
  },
  {
    type: 'url',
    label: 'URL',
  },
  {
    type: 'phrase',
    label: '핵심 문구',
  },
]


const EMPTY_SET = new Set()


// ------------------------------------------------------------
// 노드 크기
// URL > 번호 > 문구
// ------------------------------------------------------------

function getNodeSize(node) {
  if (node.type === 'url') {
    return 1.45
  }

  if (node.type === 'number') {
    return 1.2
  }

  if (node.type === 'phrase') {
    return 0.72
  }

  return 1
}


// ------------------------------------------------------------
// Hover 설명
// ------------------------------------------------------------

function getNodeLabel(node) {
  const typeLabel =
    NODE_TYPE_LABELS[node.type] ??
    '연결 정보'

  const cluster =
    node.cluster != null
      ? `연결 그룹 ${node.cluster + 1}`
      : ''

  return [
    `${typeLabel}: ${node.label ?? ''}`,
    cluster,
  ]
    .filter(Boolean)
    .join('\n')
}


// ------------------------------------------------------------
// 강조 노드
// ------------------------------------------------------------

function drawHighlightNode(
  node,
  ctx,
  globalScale,
) {
  const r = 8

  // 본체
  ctx.beginPath()

  ctx.arc(
    node.x,
    node.y,
    r,
    0,
    2 * Math.PI,
  )

  ctx.fillStyle =
    HIGHLIGHT_COLOR

  ctx.fill()

  // 강조 링
  ctx.lineWidth =
    2 / globalScale

  ctx.strokeStyle =
    '#1e3a8a'

  ctx.beginPath()

  ctx.arc(
    node.x,
    node.y,
    r + 2,
    0,
    2 * Math.PI,
  )

  ctx.stroke()

  // URL 라벨
  const fontSize =
    Math.max(
      11 / globalScale,
      r * 0.9,
    )

  ctx.font =
    `600 ${fontSize}px sans-serif`

  ctx.textAlign =
    'center'

  ctx.textBaseline =
    'top'

  ctx.fillStyle =
    '#1e3a8a'

  ctx.fillText(
    node.label ?? '',
    node.x,
    node.y + r + 4,
  )
}


function OrgGraph({
  graph = MOCK_GRAPH,
  highlightIds = EMPTY_SET,
}) {
  const fgRef =
    useRef(null)

  const wrapRef =
    useRef(null)

  const fittedRef =
    useRef(false)

  const [dims, setDims] =
    useState({
      width: 0,
      height: 0,
    })


  const nodes =
    graph[GRAPH_FIELDS.nodes] ?? []

  const edges =
    graph[GRAPH_FIELDS.edges] ?? []


  // graphData 안정화
  const data =
    useMemo(
      () => ({
        nodes,
        links: edges,
      }),
      [nodes, edges],
    )


  const hasHighlight =
    highlightIds.size > 0


  // ----------------------------------------------------------
  // 컨테이너 크기 측정
  // ----------------------------------------------------------

  useLayoutEffect(() => {
    const el =
      wrapRef.current

    if (!el) {
      return undefined
    }

    const measure = () => {
      setDims({
        width:
          el.clientWidth,

        height:
          el.clientHeight,
      })
    }

    measure()

    const ro =
      new ResizeObserver(
        measure,
      )

    ro.observe(el)

    return () =>
      ro.disconnect()
  }, [])


  // ----------------------------------------------------------
  // 강조 노드로 이동
  // ----------------------------------------------------------

  const focusHighlight = () => {
    const fg =
      fgRef.current

    if (!fg) {
      return false
    }

    const targets =
      (data.nodes ?? []).filter(
        (node) =>
          highlightIds.has(
            node.id,
          ) &&
          node.x != null &&
          node.y != null,
      )

    if (!targets.length) {
      return false
    }

    const cx =
      targets.reduce(
        (sum, node) =>
          sum + node.x,
        0,
      ) /
      targets.length

    const cy =
      targets.reduce(
        (sum, node) =>
          sum + node.y,
        0,
      ) /
      targets.length

    fg.centerAt(
      cx,
      cy,
      800,
    )

    fg.zoom(
      3.2,
      800,
    )

    return true
  }


  // ----------------------------------------------------------
  // 전체 그래프 맞춤
  // ----------------------------------------------------------

  const fitAll = () => {
    fgRef.current?.zoomToFit(
      500,
      60,
    )
  }


  // ----------------------------------------------------------
  // 그래프 force 설정
  // ----------------------------------------------------------

  useEffect(() => {
    fittedRef.current =
      false

    const fg =
      fgRef.current

    if (!fg) {
      return
    }

    // 노드 사이 간격을 조금 더 벌림
    fg
      .d3Force('charge')
      ?.strength(-170)
      .distanceMax(360)

    fg
      .d3Force('link')
      ?.distance(42)

    fg.d3ReheatSimulation()
  }, [data])


  // ----------------------------------------------------------
  // 강조 노드 좌표 안정화 대기
  // ----------------------------------------------------------

  useEffect(() => {
    if (!hasHighlight) {
      return undefined
    }

    let tries = 0

    const timer =
      setInterval(() => {
        tries += 1

        if (
          focusHighlight() ||
          tries >= 10
        ) {
          clearInterval(
            timer,
          )
        }
      }, 200)

    return () =>
      clearInterval(timer)

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    highlightIds,
    hasHighlight,
    data,
  ])


  // ----------------------------------------------------------
  // 화면 리사이즈
  // ----------------------------------------------------------

  useEffect(() => {
    if (
      dims.width &&
      fittedRef.current &&
      !hasHighlight
    ) {
      fitAll()
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    dims.width,
    dims.height,
  ])


  return (
    <div
      className="
        flex flex-col gap-3
        rounded-2xl
        border border-slate-200
        bg-white
        p-5
        shadow-sm
        sm:p-8
        [animation:card-in_0.35s_ease-out]
      "
    >
      {/* -------------------------------------------------- */}
      {/* 헤더 */}
      {/* -------------------------------------------------- */}

      <div
        className="
          flex items-center
          justify-between
        "
      >
        <div
          className="
            flex items-center
            gap-2
          "
        >
          <Network
            size={16}
            className="
              text-slate-400
            "
            strokeWidth={2.25}
          />

          <div>
            <p
              className="
                text-sm
                font-semibold
                text-slate-700
              "
            >
              연관 피싱 사례 네트워크
            </p>

            <p
              className="
                mt-0.5
                text-[11px]
                text-slate-400
              "
            >
              URL·발신번호·핵심 문구의
              연결 관계
            </p>
          </div>
        </div>


        <span
          className="
            rounded-full
            bg-slate-50
            px-2.5
            py-1
            text-xs
            font-medium
            text-slate-500
          "
        >
          연결 그룹{' '}
          {
            graph[
              GRAPH_FIELDS
                .clusterCount
            ] ?? 0
          }
          개
        </span>
      </div>


      {/* -------------------------------------------------- */}
      {/* 그래프 */}
      {/* -------------------------------------------------- */}

      <div
        ref={wrapRef}
        className="
          h-[420px]
          w-full
          overflow-hidden
          rounded-xl
          border
          border-slate-200
          bg-slate-50
        "
      >
        <ForceGraph2D
          ref={fgRef}
          graphData={data}

          width={
            dims.width ||
            undefined
          }

          height={
            dims.height ||
            undefined
          }

          backgroundColor="#F8FAFC"

          nodeColor={(node) =>
            NODE_TYPE_COLORS[
              node.type
            ] ??
            DEFAULT_NODE_COLOR
          }

          nodeLabel={
            getNodeLabel
          }

          nodeRelSize={6}

          nodeVal={(node) => {
            if (
              highlightIds.has(
                node.id,
              )
            ) {
              return 2.8
            }

            return getNodeSize(
              node,
            )
          }}

          linkColor={() =>
            'rgba(148, 163, 184, 0.32)'
          }

          linkWidth={0.8}

          warmupTicks={50}
          cooldownTicks={220}

          onEngineStop={() => {
            if (
              hasHighlight
            ) {
              focusHighlight()
            } else if (
              !fittedRef.current
            ) {
              fittedRef.current =
                true

              fitAll()
            }
          }}

          nodeCanvasObjectMode={(
            node,
          ) =>
            highlightIds.has(
              node.id,
            )
              ? 'replace'
              : undefined
          }

          nodeCanvasObject={(
            node,
            ctx,
            globalScale,
          ) => {
            if (
              highlightIds.has(
                node.id,
              )
            ) {
              drawHighlightNode(
                node,
                ctx,
                globalScale,
              )
            }
          }}
        />
      </div>


      {/* -------------------------------------------------- */}
      {/* 범례 */}
      {/* -------------------------------------------------- */}

      <div
        className="
          flex
          flex-wrap
          items-center
          gap-x-4
          gap-y-2
        "
      >
        {LEGEND_ITEMS.map(
          ({
            type,
            label,
          }) => (
            <span
              key={type}
              className="
                flex
                items-center
                gap-1.5
                text-xs
                text-slate-500
              "
            >
              <span
                className="
                  h-2.5
                  w-2.5
                  rounded-full
                "
                style={{
                  backgroundColor:
                    NODE_TYPE_COLORS[
                      type
                    ],
                }}
              />

              {label}
            </span>
          ),
        )}


        {hasHighlight && (
          <span
            className="
              flex
              items-center
              gap-1.5
              text-xs
              font-semibold
            "
            style={{
              color:
                HIGHLIGHT_COLOR,
            }}
          >
            <span
              className="
                h-2.5
                w-2.5
                rounded-full
              "
              style={{
                backgroundColor:
                  HIGHLIGHT_COLOR,
              }}
            />

            방금 신고한 URL
          </span>
        )}
      </div>


      {/* -------------------------------------------------- */}
      {/* 안내 */}
      {/* -------------------------------------------------- */}

      <p
        className="
          text-[11px]
          leading-5
          text-slate-400
        "
      >
        점 위에 마우스를 올리면
        연결된 URL·발신번호·문구 정보를
        확인할 수 있습니다.
      </p>
    </div>
  )
}


export default OrgGraph