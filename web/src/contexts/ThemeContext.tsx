/**
 * ThemeContext - Global theme state management with light/dark/system support
 */

import { createContext, useContext, useState, useEffect, useMemo, ReactNode } from 'react';
import { ThemeProvider as MuiThemeProvider, createTheme, Theme } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';

// Theme mode options
export type ThemeMode = 'light' | 'dark' | 'system';

// Resolved theme (what's actually applied)
export type ResolvedTheme = 'light' | 'dark';

// Context value interface
interface ThemeContextValue {
  mode: ThemeMode;
  resolvedMode: ResolvedTheme;
  setMode: (mode: ThemeMode) => void;
  toggleMode: () => void;
}

// Storage key for persisting theme preference
const STORAGE_KEY = 'cairn-theme';

// Create context
const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

// Base theme options shared between light and dark
const baseTheme = {
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h1: { fontSize: '2.5rem', fontWeight: 500 },
    h2: { fontSize: '2rem', fontWeight: 500 },
    h3: { fontSize: '1.75rem', fontWeight: 500 },
    h4: { fontSize: '1.5rem', fontWeight: 500 },
    h5: { fontSize: '1.25rem', fontWeight: 500 },
    h6: { fontSize: '1rem', fontWeight: 500 },
  },
  shape: { borderRadius: 12 },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          transition: 'box-shadow 0.3s cubic-bezier(.25,.8,.25,1)',
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: 8, fontWeight: 500 },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 8, textTransform: 'none' as const, fontWeight: 500 },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: { boxShadow: '0 1px 3px rgba(0,0,0,0.12)' },
      },
    },
  },
};

// Light theme
const lightTheme = createTheme({
  ...baseTheme,
  palette: {
    mode: 'light',
    primary: { main: '#1976d2', light: '#42a5f5', dark: '#1565c0' },
    secondary: { main: '#dc004e', light: '#f06292', dark: '#c51162' },
    error: { main: '#d32f2f' },
    warning: { main: '#ed6c02' },
    info: { main: '#0288d1' },
    success: { main: '#2e7d32' },
    background: { default: '#fafafa', paper: '#ffffff' },
    text: { primary: 'rgba(0, 0, 0, 0.87)', secondary: 'rgba(0, 0, 0, 0.6)' },
  },
  components: {
    ...baseTheme.components,
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: '#fafafa',
          color: 'rgba(0, 0, 0, 0.87)',
        },
        // Global scrollbar styling - thin, subtle scrollbars (light mode)
        '*::-webkit-scrollbar': {
          width: 6,
          height: 6,
        },
        '*::-webkit-scrollbar-track': {
          background: 'transparent',
        },
        '*::-webkit-scrollbar-thumb': {
          background: 'rgba(0,0,0,0.2)',
          borderRadius: 3,
        },
        '*::-webkit-scrollbar-thumb:hover': {
          background: 'rgba(0,0,0,0.3)',
        },
        // Firefox
        '*': {
          scrollbarWidth: 'thin',
          scrollbarColor: 'rgba(0,0,0,0.2) transparent',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          ...baseTheme.components.MuiCard.styleOverrides.root,
          boxShadow: '0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24)',
          '&:hover': {
            boxShadow: '0 4px 8px rgba(0,0,0,0.15), 0 2px 4px rgba(0,0,0,0.15)',
          },
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: '#ffffff',
          borderRight: '1px solid rgba(0, 0, 0, 0.12)',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#ffffff',
          color: '#1976d2',
          boxShadow: '0 1px 3px rgba(0,0,0,0.12)',
        },
      },
    },
  },
});

// M3 AMOLED Color Tokens
const m3AmoledColors = {
  // Surfaces - tonal hierarchy for AMOLED
  surface: '#000000',              // Absolute black - main background
  surfaceContainerLowest: '#0a0a0a',
  surfaceContainerLow: '#121212',  // Navigation drawer
  surfaceContainer: '#1E1E1E',     // Cards, elevated surfaces
  surfaceContainerHigh: '#252525',
  surfaceContainerHighest: '#2C2C2C',

  // On-surface text colors
  onSurface: '#E6E1E5',
  onSurfaceVariant: '#CAC4D0',     // Secondary text, snippets

  // Primary tonal
  primary: '#D0BCFF',
  primaryContainer: '#4F378B',
  onPrimaryContainer: '#EADDFF',

  // Secondary tonal (for active indicators)
  secondary: '#CCC2DC',
  secondaryContainer: '#4A4458',
  onSecondaryContainer: '#E8DEF8',

  // Outline
  outline: '#938F99',
  outlineVariant: '#49454F',
};

// Dark theme (M3 AMOLED-optimized)
const darkTheme = createTheme({
  ...baseTheme,
  palette: {
    mode: 'dark',
    primary: { main: m3AmoledColors.primary, light: '#E8DEF8', dark: '#9A82DB' },
    secondary: { main: m3AmoledColors.secondary, light: '#E8DEF8', dark: '#9A82DB' },
    error: { main: '#F2B8B5', dark: '#8C1D18' },
    warning: { main: '#ffa726' },
    info: { main: '#29b6f6' },
    success: { main: '#66bb6a' },
    background: {
      default: m3AmoledColors.surface,           // #000000
      paper: m3AmoledColors.surfaceContainer,    // #1E1E1E
    },
    text: {
      primary: m3AmoledColors.onSurface,         // #E6E1E5
      secondary: m3AmoledColors.onSurfaceVariant, // #CAC4D0
    },
  },
  components: {
    ...baseTheme.components,
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: m3AmoledColors.surface,
          color: m3AmoledColors.onSurface,
        },
        // Global scrollbar styling - thin, subtle scrollbars (dark mode)
        '*::-webkit-scrollbar': {
          width: 6,
          height: 6,
        },
        '*::-webkit-scrollbar-track': {
          background: 'transparent',
        },
        '*::-webkit-scrollbar-thumb': {
          background: 'rgba(255,255,255,0.2)',
          borderRadius: 3,
        },
        '*::-webkit-scrollbar-thumb:hover': {
          background: 'rgba(255,255,255,0.3)',
        },
        // Firefox
        '*': {
          scrollbarWidth: 'thin',
          scrollbarColor: 'rgba(255,255,255,0.2) transparent',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          ...baseTheme.components.MuiCard.styleOverrides.root,
          backgroundColor: m3AmoledColors.surfaceContainer,
          // M3: No borders, use tonal surfaces for containment
          border: 'none',
          boxShadow: 'none',
          '&:hover': {
            backgroundColor: m3AmoledColors.surfaceContainerHigh,
            boxShadow: 'none',
            border: 'none',
          },
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: m3AmoledColors.surfaceContainerLow, // #121212
          borderRight: 'none', // M3: No borders
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: m3AmoledColors.surface, // #000000
          boxShadow: 'none',
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 28, // M3 Active Indicator pill shape
          '&.Mui-selected': {
            backgroundColor: m3AmoledColors.secondaryContainer,
            '&:hover': {
              backgroundColor: m3AmoledColors.secondaryContainer,
            },
          },
        },
      },
    },
    MuiFab: {
      styleOverrides: {
        root: {
          backgroundColor: m3AmoledColors.primaryContainer,
          color: m3AmoledColors.onPrimaryContainer,
          '&:hover': {
            backgroundColor: '#5E4994',
          },
        },
        extended: {
          borderRadius: 16,
          padding: '0 20px',
          height: 56,
        },
      },
    },
  },
});

// Export M3 colors for use in components
export { m3AmoledColors };

// Get initial mode from localStorage or default to system
function getInitialMode(): ThemeMode {
  if (typeof window === 'undefined') return 'system';
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    return stored;
  }
  return 'system';
}

// Resolve system preference to light or dark
function resolveSystemPreference(): ResolvedTheme {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

// Provider props
interface ThemeProviderProps {
  children: ReactNode;
}

// Theme provider component
export function ThemeProvider({ children }: ThemeProviderProps) {
  const [mode, setModeState] = useState<ThemeMode>(getInitialMode);
  const [systemPreference, setSystemPreference] = useState<ResolvedTheme>(resolveSystemPreference);

  // Listen for system preference changes
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const handleChange = (e: MediaQueryListEvent) => {
      setSystemPreference(e.matches ? 'dark' : 'light');
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  // Listen for storage changes (sync across tabs)
  useEffect(() => {
    const handleStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue) {
        if (e.newValue === 'light' || e.newValue === 'dark' || e.newValue === 'system') {
          setModeState(e.newValue);
        }
      }
    };

    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  // Resolve the actual theme to apply
  const resolvedMode: ResolvedTheme = mode === 'system' ? systemPreference : mode;

  // Get the MUI theme based on resolved mode
  const theme: Theme = resolvedMode === 'dark' ? darkTheme : lightTheme;

  // Set mode and persist
  const setMode = (newMode: ThemeMode) => {
    setModeState(newMode);
    localStorage.setItem(STORAGE_KEY, newMode);
  };

  // Cycle through modes: light -> dark -> system -> light
  const toggleMode = () => {
    const nextMode: ThemeMode = mode === 'light' ? 'dark' : mode === 'dark' ? 'system' : 'light';
    setMode(nextMode);
  };

  // Update document theme-color meta tag
  useEffect(() => {
    const themeColor = resolvedMode === 'dark' ? '#000000' : '#ffffff';
    let metaTag = document.querySelector('meta[name="theme-color"]');
    if (!metaTag) {
      metaTag = document.createElement('meta');
      metaTag.setAttribute('name', 'theme-color');
      document.head.appendChild(metaTag);
    }
    metaTag.setAttribute('content', themeColor);
  }, [resolvedMode]);

  const contextValue = useMemo(
    () => ({ mode, resolvedMode, setMode, toggleMode }),
    [mode, resolvedMode]
  );

  return (
    <ThemeContext.Provider value={contextValue}>
      <MuiThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </MuiThemeProvider>
    </ThemeContext.Provider>
  );
}

// Hook to use theme context
export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}

// Export tag colors (can be used in both themes)
export const tagColors: Record<string, string> = {
  work: '#1976d2',
  finance: '#2e7d32',
  todo: '#ed6c02',
  priority: '#d32f2f',
  personal: '#9c27b0',
  dev: '#0288d1',
  shopping: '#fbc02d',
  travel: '#c2185b',
  social: '#00897b',
  newsletter: '#757575',
  junk: '#795548',
  action: '#ff8f00',     // amber - action tags
};
