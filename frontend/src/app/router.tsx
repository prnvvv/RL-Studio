import { Routes, Route } from 'react-router-dom'
import { RouteErrorBoundary } from '../components/feedback/RouteErrorBoundary'
import { HomePage } from '../pages/HomePage'
import { TrainingPage } from '../pages/TrainingPage'
import { EnvironmentsPage } from '../pages/EnvironmentsPage'
import { MonitoringPage } from '../pages/MonitoringPage'
import { DiagnosisRecoveryPage } from '../pages/DiagnosisRecoveryPage'
import { ReportsPage } from '../pages/ReportsPage'
import { SettingsPage } from '../pages/SettingsPage'
import { NotFoundPage } from '../pages/NotFoundPage'

export function AppRouter() {
  return (
    <RouteErrorBoundary>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/training" element={<TrainingPage />} />
        <Route path="/environments" element={<EnvironmentsPage />} />
        <Route path="/monitoring" element={<MonitoringPage />} />
        <Route path="/diagnosis-recovery" element={<DiagnosisRecoveryPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </RouteErrorBoundary>
  )
}
