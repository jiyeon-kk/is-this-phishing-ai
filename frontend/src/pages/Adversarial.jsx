import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  FlaskConical,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'

import {
  analyze,
  generateAdversarialVariants,
} from '../api/client'


const SAMPLE_TEXT = `[금융보안안내]
고객님의 계좌에서 비정상적인 접근이 확인되었습니다.
즉시 아래 주소에서 본인 인증을 완료하세요.

http://secure-account-check.xyz`


function percent(value) {
  if (value == null) {
    return '-'
  }

  const number = Number(value)

  if (Number.isNaN(number)) {
    return '-'
  }

  return `${Math.round(number * 100)}%`
}


function confidenceLabel(value) {
  if (value === 'high') {
    return '높음'
  }

  if (value === 'medium') {
    return '보통'
  }

  if (value === 'low') {
    return '낮음'
  }

  return '-'
}


function levelLabel(value) {
  if (value === 'danger') {
    return '위험'
  }

  if (value === 'suspicious') {
    return '의심'
  }

  if (value === 'safe') {
    return '안전'
  }

  return '-'
}


function ResultCard({
  title,
  subtitle,
  text,
  result,
  original = false,
}) {
  const signals =
    result?.signals ?? {}

  return (
    <div
      className={`
        rounded-2xl border bg-white p-5 shadow-sm
        ${
          original
            ? 'border-blue-200'
            : 'border-slate-200'
        }
      `}
    >
      <div
        className="
          mb-4 flex
          items-start justify-between
          gap-3
        "
      >
        <div>
          <div
            className="
              flex items-center gap-2
            "
          >
            {original ? (
              <ShieldCheck
                size={17}
                className="text-blue-600"
              />
            ) : (
              <Sparkles
                size={17}
                className="text-slate-400"
              />
            )}

            <p
              className="
                text-sm font-semibold
                text-slate-800
              "
            >
              {title}
            </p>
          </div>

          {subtitle && (
            <p
              className="
                mt-1 text-xs
                text-slate-400
              "
            >
              {subtitle}
            </p>
          )}
        </div>

        {original && (
          <span
            className="
              rounded-full
              bg-blue-50
              px-2.5 py-1
              text-[11px]
              font-semibold
              text-blue-600
            "
          >
            원본
          </span>
        )}
      </div>


      <div
        className="
          mb-5 whitespace-pre-wrap
          rounded-xl
          bg-slate-50
          p-4
          text-[13px]
          leading-6
          text-slate-600
        "
      >
        {text}
      </div>


      <div
        className="
          grid grid-cols-3 gap-2
        "
      >
        <div
          className="
            rounded-xl
            bg-slate-50
            px-3 py-3
            text-center
          "
        >
          <p
            className="
              text-[11px]
              text-slate-400
            "
          >
            위험도
          </p>

          <p
            className="
              mt-1 text-lg
              font-bold
              text-slate-800
            "
          >
            {percent(
              result?.risk_score,
            )}
          </p>
        </div>


        <div
          className="
            rounded-xl
            bg-slate-50
            px-3 py-3
            text-center
          "
        >
          <p
            className="
              text-[11px]
              text-slate-400
            "
          >
            판단
          </p>

          <p
            className="
              mt-1 text-sm
              font-semibold
              text-slate-700
            "
          >
            {levelLabel(
              result?.level,
            )}
          </p>
        </div>


        <div
          className="
            rounded-xl
            bg-slate-50
            px-3 py-3
            text-center
          "
        >
          <p
            className="
              text-[11px]
              text-slate-400
            "
          >
            신뢰도
          </p>

          <p
            className="
              mt-1 text-sm
              font-semibold
              text-slate-700
            "
          >
            {confidenceLabel(
              result?.confidence,
            )}
          </p>
        </div>
      </div>


      <div
        className="
          mt-3 grid
          grid-cols-3 gap-2
        "
      >
        <Signal
          label="AI 모델"
          value={
            signals.model ??
            signals.model_p
          }
        />

        <Signal
          label="규칙"
          value={
            signals.rule ??
            signals.rule_s
          }
        />

        <Signal
          label="평판"
          value={
            signals.reputation ??
            signals.rep ??
            signals.rep_s
          }
        />
      </div>
    </div>
  )
}


function Signal({
  label,
  value,
}) {
  return (
    <div
      className="
        rounded-lg
        border border-slate-100
        px-3 py-2
      "
    >
      <p
        className="
          text-[10px]
          text-slate-400
        "
      >
        {label}
      </p>

      <p
        className="
          mt-0.5 text-xs
          font-semibold
          text-slate-600
        "
      >
        {percent(value)}
      </p>
    </div>
  )
}


function Adversarial() {
  const [text, setText] =
    useState(SAMPLE_TEXT)

  const [originalResult, setOriginalResult] =
    useState(null)

  const [variantResults, setVariantResults] =
    useState([])

  const [loading, setLoading] =
    useState(false)

  const [error, setError] =
    useState('')


  const successfulVariants =
    useMemo(() => {
      return variantResults.filter(
        (item) => {
          const score =
            item.result?.risk_score

          return (
            score != null &&
            Number(score) >= 0.5
          )
        },
      ).length
    }, [variantResults])


  const runTest = async () => {
    if (!text.trim()) {
      return
    }

    setLoading(true)
    setError('')
    setOriginalResult(null)
    setVariantResults([])

    try {
      // 1. 원본 분석
      const original =
        await analyze(
          text.trim(),
          null,
        )

      setOriginalResult(
        original,
      )

      // 2. 우회 변형 생성
      const generated =
        await generateAdversarialVariants(
          text.trim(),
        )

      const variants =
        generated?.variants ?? []

      // 3. 모든 변형을 실제 탐지 파이프라인에 재입력
      const analyzed =
        await Promise.all(
          variants.map(
            async (variant) => {
              const result =
                await analyze(
                  variant.text,
                  null,
                )

              return {
                ...variant,
                result,
              }
            },
          ),
        )

      setVariantResults(
        analyzed,
      )
    } catch (err) {
      console.error(err)

      setError(
        '우회 대응 테스트 중 오류가 발생했습니다.',
      )
    } finally {
      setLoading(false)
    }
  }


  return (
    <div
      className="
        mx-auto
        w-full
        max-w-5xl
        px-4
        pb-24
        pt-6
        sm:px-6
      "
    >
      {/* 상단 */}
      <div
        className="
          mb-6
          flex items-start
          justify-between
          gap-4
        "
      >
        <div>
          <div
            className="
              flex items-center gap-2
            "
          >
            <FlaskConical
              size={19}
              className="text-blue-600"
            />

            <h1
              className="
                text-lg
                font-bold
                text-slate-900
              "
            >
              AI 우회 대응 테스트
            </h1>
          </div>

          <p
            className="
              mt-2
              max-w-2xl
              text-sm
              leading-6
              text-slate-500
            "
          >
            문자 분할·문자 혼합·특수문자 삽입·URL 난독화 등
            탐지 회피 변형에도 위험 신호가 유지되는지 비교합니다.
          </p>
        </div>


        <Link
          to="/analyze"
          className="
            flex shrink-0
            items-center gap-1.5
            rounded-lg
            border border-slate-200
            bg-white
            px-3 py-2
            text-xs
            font-medium
            text-slate-500
            transition
            hover:bg-slate-50
          "
        >
          <ArrowLeft size={14} />

          분석으로
        </Link>
      </div>


      {/* 입력 */}
      <div
        className="
          rounded-2xl
          border border-slate-200
          bg-white
          p-5
          shadow-sm
          sm:p-6
        "
      >
        <div
          className="
            mb-3
            flex items-center
            justify-between
          "
        >
          <div>
            <p
              className="
                text-sm
                font-semibold
                text-slate-800
              "
            >
              테스트할 의심 문자
            </p>

            <p
              className="
                mt-1
                text-xs
                text-slate-400
              "
            >
              원본과 우회 변형의 탐지 결과를 자동 비교합니다.
            </p>
          </div>
        </div>


        <textarea
          value={text}
          onChange={(e) =>
            setText(
              e.target.value,
            )
          }
          className="
            min-h-[160px]
            w-full
            resize-none
            rounded-xl
            border
            border-slate-200
            bg-slate-50
            p-4
            text-sm
            leading-6
            text-slate-700
            outline-none
            transition
            focus:border-blue-300
            focus:ring-2
            focus:ring-blue-50
          "
        />


        <div
          className="
            mt-4
            flex justify-end
          "
        >
          <button
            type="button"
            onClick={runTest}
            disabled={
              loading ||
              !text.trim()
            }
            className="
              rounded-xl
              bg-slate-900
              px-5 py-2.5
              text-sm
              font-semibold
              text-white
              transition
              hover:bg-slate-800
              disabled:cursor-not-allowed
              disabled:opacity-40
            "
          >
            {loading
              ? '테스트 중...'
              : '우회 대응 테스트 실행'}
          </button>
        </div>


        {error && (
          <p
            className="
              mt-3
              text-sm
              text-red-500
            "
          >
            {error}
          </p>
        )}
      </div>


      {/* 종합 결과 */}
      {originalResult &&
        variantResults.length >
          0 && (
          <div
            className="
              mt-6
              grid
              grid-cols-3
              gap-3
              rounded-2xl
              border
              border-blue-100
              bg-blue-50/50
              p-5
            "
          >
            <div>
              <p
                className="
                  text-[11px]
                  text-slate-400
                "
              >
                테스트 변형
              </p>

              <p
                className="
                  mt-1 text-xl
                  font-bold
                  text-slate-800
                "
              >
                {
                  variantResults.length
                }
                종
              </p>
            </div>


            <div>
              <p
                className="
                  text-[11px]
                  text-slate-400
                "
              >
                탐지 유지
              </p>

              <p
                className="
                  mt-1 text-xl
                  font-bold
                  text-blue-700
                "
              >
                {
                  successfulVariants
                }
                /
                {
                  variantResults.length
                }
              </p>
            </div>


            <div>
              <p
                className="
                  text-[11px]
                  text-slate-400
                "
              >
                원본 위험도
              </p>

              <p
                className="
                  mt-1 text-xl
                  font-bold
                  text-slate-800
                "
              >
                {percent(
                  originalResult
                    .risk_score,
                )}
              </p>
            </div>
          </div>
        )}


      {/* 원본 */}
      {originalResult && (
        <div className="mt-6">
          <ResultCard
            title="원본 문자"
            subtitle="변형 전 탐지 결과"
            text={text}
            result={
              originalResult
            }
            original
          />
        </div>
      )}


      {/* 변형 */}
      {variantResults.length >
        0 && (
        <div className="mt-6">
          <div className="mb-3">
            <p
              className="
                text-sm
                font-semibold
                text-slate-800
              "
            >
              우회 변형 비교
            </p>

            <p
              className="
                mt-1
                text-xs
                text-slate-400
              "
            >
              각 변형을 동일한 탐지 파이프라인에 다시 입력한 결과입니다.
            </p>
          </div>


          <div
            className="
              grid
              gap-4
              lg:grid-cols-2
            "
          >
            {variantResults.map(
              (
                variant,
                index,
              ) => (
                <ResultCard
                  key={
                    `${variant.type}-${index}`
                  }
                  title={
                    variant.label ??
                    `우회 변형 ${index + 1}`
                  }
                  subtitle={
                    variant.type ??
                    '우회 변형'
                  }
                  text={
                    variant.text
                  }
                  result={
                    variant.result
                  }
                />
              ),
            )}
          </div>
        </div>
      )}
    </div>
  )
}


export default Adversarial