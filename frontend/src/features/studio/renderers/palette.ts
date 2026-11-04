import { useEffect, useState } from 'react'

export interface ScenePalette {
  background: string
  floor: string
  grid: string
  structure: string
  agent: string
  accent: string
  good: string
  bad: string
  text: string
}

const DARK: ScenePalette = {
  background: '#050505',
  floor: '#101010',
  grid: '#9a9a9a',
  structure: '#5a5a5a',
  agent: '#f2f2f2',
  accent: '#bdbdbd',
  good: '#4ade80',
  bad: '#f87171',
  text: '#a3a3a3',
}

const LIGHT: ScenePalette = {
  background: '#f2f2f2',
  floor: '#e4e4e4',
  grid: '#8a8a8a',
  structure: '#8a8a8a',
  agent: '#141414',
  accent: '#555555',
  good: '#16a34a',
  bad: '#dc2626',
  text: '#555555',
}

function currentTheme(): 'dark' | 'light' {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark'
}

/** Resolve the scene palette from the document theme without requiring a provider. */
export function useScenePalette(): ScenePalette {
  const [theme, setTheme] = useState(currentTheme)
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(currentTheme()))
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
    return () => observer.disconnect()
  }, [])
  return theme === 'light' ? LIGHT : DARK
}
