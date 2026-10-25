import { Routes, Route } from 'react-router-dom'

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<div>Self-Healing RL Studio - Frontend Initialized</div>} />
    </Routes>
  )
}
