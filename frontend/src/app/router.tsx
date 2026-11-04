import { Navigate, Routes, Route } from 'react-router-dom'
import { RouteErrorBoundary } from '../components/feedback/RouteErrorBoundary'
import { useActiveProject } from '../contexts/ActiveProjectContext'
import { HomePage } from '../pages/HomePage'
import { StudioPage } from '../pages/StudioPage'
import { ProjectsPage } from '../pages/ProjectsPage'
import { ProjectWorkspacePage } from '../pages/ProjectWorkspacePage'
import { MonitoringPage } from '../pages/MonitoringPage'
import { DiagnosisRecoveryPage } from '../pages/DiagnosisRecoveryPage'
import { ReportsPage } from '../pages/ReportsPage'
import { RunDetailPage } from '../pages/RunDetailPage'
import { SettingsPage } from '../pages/SettingsPage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { LoginPage } from '../pages/LoginPage'

export function AppRouter() {
  const { activeProjectId } = useActiveProject()
  return (
    <RouteErrorBoundary>
      {/* Switching project remounts every page, so nothing fetched for one project can linger in another. */}
      <Routes key={activeProjectId ?? 'no-project'}>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectWorkspacePage />} />
        <Route path="/studio" element={<StudioPage />} />
        {/* The old standalone training page is retired; the Studio workspace is where training runs. */}
        <Route path="/training" element={<Navigate to="/studio?view=training" replace />} />
        <Route path="/monitoring" element={<MonitoringPage />} />
        <Route path="/diagnosis-recovery" element={<DiagnosisRecoveryPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/reports/:runId" element={<RunDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </RouteErrorBoundary>
  )
}
