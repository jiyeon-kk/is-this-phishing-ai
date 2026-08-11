import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'

import AppShell from './components/AppShell'
import Splash from './components/Splash'

import Home from './pages/Home'
import Analyze from './pages/Analyze'
import Graph from './pages/Graph'
import Report from './pages/Report'
import Trends from './pages/Trends'
import Adversarial from './pages/Adversarial'

const SPLASH_DURATION_MS = 1300

function App() {
  const [showSplash, setShowSplash] = useState(true)

  useEffect(() => {
    const timer = setTimeout(
      () => setShowSplash(false),
      SPLASH_DURATION_MS,
    )

    return () => clearTimeout(timer)
  }, [])

  if (showSplash) {
    return <Splash />
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Home />} />
          <Route path="/analyze" element={<Analyze />} />
          <Route path="/graph" element={<Graph />} />
          <Route path="/report" element={<Report />} />
          <Route path="/trends" element={<Trends />} />

          {/* 우회 대응 검증용 별도 페이지 */}
          <Route
            path="/adversarial"
            element={<Adversarial />}
          />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App