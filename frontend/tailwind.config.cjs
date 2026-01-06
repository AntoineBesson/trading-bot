/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Black & White theme
        'primary': '#ffffff',
        'secondary': '#a3a3a3',
        'background': '#0a0a0a',
        'surface': '#141414',
        'surface-light': '#1f1f1f',
        'border': '#262626',
        'border-light': '#404040',
        // Chart colors
        'chart-green': '#22c55e',
        'chart-green-light': 'rgba(34, 197, 94, 0.15)',
        'chart-red': '#ef4444',
        'chart-red-light': 'rgba(239, 68, 68, 0.15)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}