import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'dark' | 'light' | 'system'

interface ThemeState {
  // State
  theme: Theme
  resolvedTheme: 'dark' | 'light'

  // Actions
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  initialize: () => void
}

// Get system theme preference
const getSystemTheme = (): 'dark' | 'light' => {
  if (typeof window === 'undefined') return 'dark'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

// Resolve theme to actual dark/light value
const resolveTheme = (theme: Theme): 'dark' | 'light' => {
  if (theme === 'system') {
    return getSystemTheme()
  }
  return theme
}

// Update DOM class
const updateDOMTheme = (theme: 'dark' | 'light') => {
  if (typeof document === 'undefined') return

  const root = document.documentElement

  if (theme === 'dark') {
    root.classList.add('dark')
    root.style.backgroundColor = '#000000'
    root.style.colorScheme = 'dark'
  } else {
    root.classList.remove('dark')
    root.style.backgroundColor = '#ffffff'
    root.style.colorScheme = 'light'
  }

  // Update meta theme-color
  const metaThemeColor = document.querySelector('meta[name="theme-color"]')
  if (metaThemeColor) {
    metaThemeColor.setAttribute('content', theme === 'dark' ? '#000000' : '#ffffff')
  }
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      // Initial state
      theme: 'dark',
      resolvedTheme: 'dark',

      // Set theme
      setTheme: (theme: Theme) => {
        const resolvedTheme = resolveTheme(theme)
        updateDOMTheme(resolvedTheme)
        set({ theme, resolvedTheme })
      },

      // Toggle theme
      toggleTheme: () => {
        const { resolvedTheme } = get()
        const newTheme = resolvedTheme === 'dark' ? 'light' : 'dark'
        updateDOMTheme(newTheme)
        set({
          theme: newTheme,
          resolvedTheme: newTheme,
        })
      },

      // Initialize theme
      initialize: () => {
        const { theme } = get()
        const resolvedTheme = resolveTheme(theme)
        updateDOMTheme(resolvedTheme)
        set({ resolvedTheme })
      },
    }),
    {
      name: 'theme-storage',
      onRehydrateStorage: () => (state) => {
        if (state) {
          const resolvedTheme = resolveTheme(state.theme)
          updateDOMTheme(resolvedTheme)
          state.resolvedTheme = resolvedTheme
        }
      },
    }
  )
)

// Listen for system theme changes
if (typeof window !== 'undefined') {
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQuery.addEventListener('change', () => {
    const { theme } = useThemeStore.getState()
    if (theme === 'system') {
      const resolvedTheme = getSystemTheme()
      updateDOMTheme(resolvedTheme)
      useThemeStore.setState({ resolvedTheme })
    }
  })
}
