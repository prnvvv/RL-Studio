import { BrowserRouter } from 'react-router-dom'
import { ClerkProvider } from '@clerk/react'
import { ThemeProvider } from '../contexts/ThemeContext'
import { AppRouter } from './router'

function App() {
  return (
    <BrowserRouter>
      <ClerkProvider>
        <ThemeProvider>
          <AppRouter />
        </ThemeProvider>
      </ClerkProvider>
    </BrowserRouter>
  )
}

export default App
